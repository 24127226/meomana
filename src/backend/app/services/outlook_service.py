# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/services/outlook_service.py — ĐỌC/GHI OUTLOOK qua Microsoft    ║
# ║ Graph API. Đối xứng gmail_service nhưng cho provider Microsoft.     ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ Dịch mỗi message Graph → schema Email chung (FE không cần biết      ║
# ║ nguồn Gmail hay Outlook). Phân loại nhãn dùng CHUNG engine          ║
# ║ classify() → category/label khớp Gmail.                            ║
# ╚══════════════════════════════════════════════════════════════════╝

from datetime import datetime
from zoneinfo import ZoneInfo
import re
import httpx
from app.schemas.email import Email
from app.core.labeling import classify, tu_ten_nhan

GRAPH = "https://graph.microsoft.com/v1.0"
_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

# Thư mục app → thư mục Graph (well-known folder names).
_FOLDER = {
    "inbox": "inbox", "sent": "sentitems", "drafts": "drafts",
    "trash": "deleteditems", "archive": "archive",
}


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _fmt_local(iso: str) -> tuple[str, str]:
    """ISO UTC của Graph → (giờ 'HH:MM', ngày 'dd/mm/YYYY HH:MM') theo giờ VN."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_TZ_VN)
        return dt.strftime("%H:%M"), dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso, iso


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _to_email(m: dict, folder: str = "inbox", full: bool = False) -> Email:
    frm = (m.get("from") or m.get("sender") or {}).get("emailAddress", {}) or {}
    to_list = m.get("toRecipients") or []
    to_addr = (to_list[0].get("emailAddress", {}).get("address", "") if to_list else "")
    name = frm.get("name") or frm.get("address") or "(không tên)"
    addr = frm.get("address", "")
    # Thư MÌNH GỬI (sent/drafts): hiện NGƯỜI NHẬN thay vì chính mình.
    display, display_email = (name, addr)
    if folder in ("sent", "drafts") and to_list:
        display = to_list[0].get("emailAddress", {}).get("name") or to_addr or "(chưa có người nhận)"
        display_email = to_addr

    snippet = m.get("bodyPreview", "") or ""
    subject = m.get("subject") or "(không tiêu đề)"
    time_s, date_s = _fmt_local(m.get("receivedDateTime", "") or m.get("sentDateTime", "") or "")
    # NGƯỜI DÙNG ĐÃ ĐẶT CATEGORY thì dùng cái đó; chưa thì mới để bộ phân loại đoán.
    # `apply_label` bên dưới GHI `categories` xuống Outlook, nhưng trước đây chỗ đọc này
    # bỏ qua hoàn toàn — thao tác được ghi rồi không bao giờ được đọc, nên gắn nhãn xong
    # quay lại là thấy nhãn cũ. Gmail đã sửa; thiếu ở đây thì lỗi vẫn còn nguyên với
    # người dùng Outlook, và chỉ lộ ra khi có tài khoản Outlook thật đăng nhập.
    # Outlook trả THẲNG TÊN category (không cần tra id như Gmail) nên đơn giản hơn.
    nhom = next((n for n in (tu_ten_nhan(c) for c in (m.get("categories") or [])) if n), None)
    if nhom is None:
        nhom = classify(addr, name, subject if subject != "(không tiêu đề)" else "", snippet).category

    html_body = None
    if full:
        b = m.get("body", {}) or {}
        raw = b.get("content", "") or snippet
        is_html = b.get("contentType", "").lower() == "html"
        html_body = raw if is_html else None    # HTML gốc để FE render đúng chuẩn
        text = _strip_html(raw) if is_html else raw
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] or [snippet]
    else:
        paragraphs = [snippet]

    flag = (m.get("flag") or {}).get("flagStatus")
    atts = [{"name": a.get("name", ""), "size": str(a.get("size", ""))}
            for a in (m.get("attachments") or [])] if full else None
    return Email(
        id=m["id"],
        sender=display,
        senderEmail=display_email,
        senderInitial=(display.lstrip("(")[:1].upper() or "?"),
        to=to_addr,
        subject=subject,
        preview=snippet,
        body=paragraphs,
        time=time_s,
        date=date_s,
        unread=(not m.get("isRead", True)),
        starred=(flag == "flagged"),
        category=nhom.color,           # type: ignore[arg-type]
        label=nhom.label,
        folder=folder,                 # type: ignore[arg-type]
        threadId=m.get("conversationId"),
        hasAttachment=bool(m.get("hasAttachments")),   # Graph nói thẳng, khỏi suy
        html=html_body,
        attachments=(atts or None),    # type: ignore[arg-type]
    )


# `categories` PHẢI có trong $select: Graph chỉ trả về đúng những trường được xin, nên
# thiếu nó thì nhãn người dùng đặt không bao giờ về tới nơi và bản vá ở _to_email vô
# hiệu — im lặng, không lỗi, chỉ là nhãn cứ quay về giá trị bộ phân loại đoán.
_SELECT = ("id,subject,from,toRecipients,receivedDateTime,sentDateTime,"
           "bodyPreview,isRead,hasAttachments,flag,conversationId,categories")


def list_messages(access_token: str, folder: str = "inbox", q: str | None = None,
                  max_results: int = 30, page_token: str | None = None,
                  scan_after: str | None = None,   # ngày ISO 'YYYY-MM-DD' — mốc sớm nhất được quét
                  **_ignore):
    """Danh sách thư 1 thư mục (hoặc tìm theo q). Trả (list[Email], next_url|None).

    NFR-SCO-01 — cửa sổ quét theo gói được áp bằng HAI cách, vì Graph **không cho**
    dùng `$search` chung với `$filter`:
      • không có `q`  → `$filter=receivedDateTime ge …` (server lọc, rẻ nhất)
      • có `q`        → lọc tại chỗ sau khi nhận kết quả
    Cách nào cũng cho ra cùng một tập thư, nên hành vi không đổi theo việc người dùng
    có gõ từ khoá hay không.
    """
    tag = folder if folder in _FOLDER else "inbox"
    params = {"$top": max_results, "$select": _SELECT}
    loc_tai_cho = False
    if q:
        params["$search"] = f'"{q}"'                      # tìm toàn hộp thư
        url = f"{GRAPH}/me/messages"
        loc_tai_cho = bool(scan_after)                    # $search không đi cùng $filter
    else:
        params["$orderby"] = "receivedDateTime desc"
        url = f"{GRAPH}/me/mailFolders/{_FOLDER[tag]}/messages"
        if scan_after:
            params["$filter"] = f"receivedDateTime ge {scan_after}T00:00:00Z"
    # page_token của Graph là URL @odata.nextLink đầy đủ → gọi thẳng.
    with httpx.Client(timeout=15) as c:
        r = c.get(page_token or url, headers=_hdr(access_token),
                  params=None if page_token else params)
        r.raise_for_status()
        data = r.json()
    raw = data.get("value", [])
    if loc_tai_cho:
        raw = [m for m in raw if (m.get("receivedDateTime") or "")[:10] >= scan_after]
    emails = [_to_email(m, tag) for m in raw]
    return emails, data.get("@odata.nextLink")


def get_message(access_token: str, msg_id: str) -> Email:
    with httpx.Client(timeout=15) as c:
        r = c.get(f"{GRAPH}/me/messages/{msg_id}",
                  headers=_hdr(access_token), params={"$expand": "attachments($select=name,size)"})
        r.raise_for_status()
    return _to_email(r.json(), "inbox", full=True)


def get_thread(access_token: str, thread_id: str) -> list[Email]:
    """Mọi thư trong một hội thoại, sắp CŨ → MỚI.

    Graph không có "threads.get" như Gmail; luồng ở đây là các thư cùng `conversationId`.
    Lọc theo nó trên TOÀN hộp thư (`/me/messages`) chứ không riêng Inbox — nếu không thì
    thư MÌNH ĐÃ TRẢ LỜI (nằm ở Sent) biến mất khỏi cuộc trao đổi, và người đọc chỉ thấy
    một nửa câu chuyện.
    """
    with httpx.Client(timeout=20) as c:
        r = c.get(f"{GRAPH}/me/messages", headers=_hdr(access_token), params={
            "$filter": f"conversationId eq '{thread_id}'",
            "$orderby": "receivedDateTime asc",
            "$top": 50,
            "$expand": "attachments($select=name,size)",
        })
        r.raise_for_status()
        ds = r.json().get("value", [])
    return [_to_email(m, "inbox", full=True) for m in ds]


def send_email(access_token: str, to: str, subject: str, body: str,
               cc=None, bcc=None, html: str | None = None, **_ignore) -> dict:
    def _recips(s):
        return [{"emailAddress": {"address": a.strip()}} for a in
                (s if isinstance(s, list) else str(s).split(",")) if str(a).strip()]
    # Graph chỉ nhận MỘT bản thân thư (khác Gmail gửi được cả hai). Có HTML thì gửi
    # HTML — Outlook tự sinh bản chữ thuần cho phía nhận khi cần.
    than = ({"contentType": "HTML", "content": html} if html and html.strip()
            else {"contentType": "Text", "content": body})
    msg = {"subject": subject, "body": than, "toRecipients": _recips(to)}
    if cc:
        msg["ccRecipients"] = _recips(cc)
    if bcc:
        msg["bccRecipients"] = _recips(bcc)
    with httpx.Client(timeout=15) as c:
        r = c.post(f"{GRAPH}/me/sendMail", headers=_hdr(access_token),
                   json={"message": msg, "saveToSentItems": True})
        r.raise_for_status()
    return {"id": "", "threadId": ""}   # Graph sendMail không trả id thư


def create_draft(access_token: str, to, subject: str, body: str,
                 cc=None, bcc=None, **_ignore) -> dict:
    """Lưu bản nháp trên Outlook: POST /me/messages (mặc định tạo message ở Drafts, chưa gửi)."""
    def _recips(s):
        return [{"emailAddress": {"address": a.strip()}} for a in
                (s if isinstance(s, list) else str(s).split(",")) if str(a).strip()]
    msg = {"subject": subject, "body": {"contentType": "Text", "content": body},
           "toRecipients": _recips(to)}
    if cc:
        msg["ccRecipients"] = _recips(cc)
    if bcc:
        msg["bccRecipients"] = _recips(bcc)
    with httpx.Client(timeout=15) as c:
        r = c.post(f"{GRAPH}/me/messages", headers=_hdr(access_token), json=msg)
        r.raise_for_status()
        d = r.json()
    return {"id": d.get("id", ""), "message": {"id": d.get("id", ""), "threadId": d.get("conversationId")}}


def reply_email(access_token: str, msg_id: str, body: str, reply_all: bool = False,
                html: str | None = None, **_ignore) -> dict:
    """Trả lời thư. `reply_all=True` dùng endpoint /replyAll của Graph — nó tự dựng danh
    sách người nhận, nên không phải tự lọc trùng/loại mình như bản Gmail."""
    duong = "replyAll" if reply_all else "reply"
    with httpx.Client(timeout=15) as c:
        # Graph nhận `comment` là chuỗi; gửi thẳng HTML vào đó thì Outlook hiện đúng
        # định dạng. Không có HTML thì giữ chữ thuần như cũ.
        r = c.post(f"{GRAPH}/me/messages/{msg_id}/{duong}",
                   headers=_hdr(access_token), json={"comment": (html or body)})
        r.raise_for_status()
    return {"id": "", "threadId": ""}


def forward_email(access_token: str, msg_id: str, to: str, note: str = "") -> dict:
    """Chuyển tiếp thư — Graph có sẵn endpoint /forward, tự trích thư gốc và giữ đính kèm.

    Ở đây Graph LÀM ĐƯỢC NHIỀU HƠN Gmail: nó tự đính kèm lại tệp gốc. Bản Gmail phải tự
    dựng nội dung nên không mang tệp theo — khác biệt đó được nói thẳng trong docstring
    của `gmail_send.forward_email` chứ không giấu đi.
    """
    with httpx.Client(timeout=20) as c:
        r = c.post(f"{GRAPH}/me/messages/{msg_id}/forward", headers=_hdr(access_token),
                   json={"comment": note,
                         "toRecipients": [{"emailAddress": {"address": to}}]})
        r.raise_for_status()
    return {"id": "", "threadId": ""}


def set_read(access_token: str, ids: list[str], read: bool) -> int:
    n = 0
    with httpx.Client(timeout=15) as c:
        for i in ids:
            r = c.patch(f"{GRAPH}/me/messages/{i}", headers=_hdr(access_token), json={"isRead": read})
            if r.status_code < 300:
                n += 1
    return n


def set_flag(access_token: str, ids: list[str], flagged: bool) -> int:
    n = 0
    status = "flagged" if flagged else "notFlagged"
    with httpx.Client(timeout=15) as c:
        for i in ids:
            r = c.patch(f"{GRAPH}/me/messages/{i}", headers=_hdr(access_token),
                        json={"flag": {"flagStatus": status}})
            if r.status_code < 300:
                n += 1
    return n


def _move(access_token: str, ids: list[str], dest: str) -> int:
    n = 0
    with httpx.Client(timeout=15) as c:
        for i in ids:
            r = c.post(f"{GRAPH}/me/messages/{i}/move", headers=_hdr(access_token),
                       json={"destinationId": dest})
            if r.status_code < 300:
                n += 1
    return n


def trash(access_token: str, ids: list[str]) -> int:
    return _move(access_token, ids, "deleteditems")


def untrash(access_token: str, ids: list[str]) -> int:
    """Đưa thư từ Deleted Items về Inbox — bản Outlook của `gmail_actions.untrash`."""
    return _move(access_token, ids, "inbox")


def archive(access_token: str, ids: list[str]) -> int:
    return _move(access_token, ids, "archive")


def spam(access_token: str, ids: list[str]) -> int:
    """Chuyển thư vào Thư rác (Junk Email)."""
    return _move(access_token, ids, "junkemail")


def not_spam(access_token: str, ids: list[str]) -> int:
    """Đưa thư từ Thư rác về Hộp thư — đường lùi của `spam`.

    Đây mới là chiều người ta cần gấp: thư quan trọng bị lọc nhầm vào Thư rác, và họ
    đang hoảng đi tìm. Có chiều đi mà không có chiều về thì tính năng chỉ làm được nửa
    việc, và là nửa ít quan trọng hơn.
    """
    return _move(access_token, ids, "inbox")


def set_categories(access_token: str, ids: list[str], cats: list[str]) -> int:
    """Đặt danh sách 'categories' cho thư (rỗng = bỏ category). Outlook không có label như Gmail."""
    n = 0
    with httpx.Client(timeout=15) as c:
        for i in ids:
            r = c.patch(f"{GRAPH}/me/messages/{i}", headers=_hdr(access_token),
                        json={"categories": cats})
            if r.status_code < 300:
                n += 1
    return n


def apply_category(access_token: str, ids: list[str], label: str) -> int:
    """Gán 1 category tên `label` (tương đương 'gắn nhãn' bên Gmail)."""
    return set_categories(access_token, ids, [label])
