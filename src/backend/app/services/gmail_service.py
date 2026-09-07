# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/services/gmail_service.py — ĐỌC GMAIL THẬT (tầng services/)   ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ Dùng access_token của user (lưu ở phiên) gọi Gmail API, rồi DỊCH   ║
# ║ mỗi thư Gmail sang khuôn `Email` mà Frontend hiểu.                 ║
# ╚══════════════════════════════════════════════════════════════════╝

import base64
import re
import time
from concurrent.futures import ThreadPoolExecutor
from email.utils import parseaddr, parsedate_to_datetime
from zoneinfo import ZoneInfo
import httpx
from app.schemas.email import Email
from app.core.retry import gmail_read_retry  # NFR-Reliability: tự thử lại lỗi mạng/429 (chỉ ĐỌC)
from app.core.labeling import classify  # UC009: gán category+label TẤT ĐỊNH theo nội dung (không băm ngẫu nhiên)

# Gmail trả giờ theo MÚI GIỜ trong header (thường UTC). Phải đổi sang giờ VIỆT NAM
# thì người dùng mới thấy ĐÚNG đồng hồ của mình (vd 06:21 UTC → 13:21 giờ VN).
_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _fmt_local(raw_date: str) -> tuple[str, str]:
    """Đổi chuỗi ngày Gmail → (giờ ngắn 'HH:MM', ngày đầy đủ 'dd/mm/YYYY HH:MM') THEO GIỜ VN.
    Parse được thì đổi múi giờ; không thì trả lại chuỗi gốc để khỏi sập."""
    try:
        dt = parsedate_to_datetime(raw_date)
        if dt.tzinfo is not None:          # có múi giờ → quy về giờ VN
            dt = dt.astimezone(_TZ_VN)
        return dt.strftime("%H:%M"), dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return raw_date, raw_date

# Số thư lấy metadata cùng lúc khi dựng danh sách. 8 là mức cân bằng: nhanh gấp ~8 lần
# so với gọi tuần tự mà chưa chạm ngưỡng chống dồn dập của Gmail (quota per-user-per-second).
_LIST_WORKERS = 8

GMAIL_LIST = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
GMAIL_MSG = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}"
# Tải nội dung 1 tệp đính kèm (Gmail tách riêng phần bytes nặng ra endpoint này).
GMAIL_ATTACH = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}/attachments/{aid}"
GMAIL_THREAD = "https://gmail.googleapis.com/gmail/v1/users/me/threads/{id}"
# Đồng bộ lũy tiến + Push (Pub/Sub): profile cho historyId gốc, history.list cho thay đổi,
# watch/stop để bật/tắt Gmail Push Notifications.
GMAIL_PROFILE = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
GMAIL_HISTORY = "https://gmail.googleapis.com/gmail/v1/users/me/history"
GMAIL_WATCH = "https://gmail.googleapis.com/gmail/v1/users/me/watch"
GMAIL_STOP = "https://gmail.googleapis.com/gmail/v1/users/me/stop"


class HistoryExpired(Exception):
    """historyId đã quá cũ (Gmail xoá lịch sử >~1 tuần) → phải resync đầy đủ."""

# Gmail không có "category màu" như FE → mình gán tạm 1 màu theo id cho danh sách
# đỡ đơn điệu. (Phân loại thông minh là việc của AI — UC009, để sau.)
_CATS = ["moss", "sea", "sun", "cherry", "sky", "terra", "wine"]


# ── CACHE kết quả Gmail (giảm số lần gọi API) — chạy trên kho KV CẮM-RÚT ──
# Ý tưởng giữ nguyên: cùng "khoá" (người + thư mục + từ khoá) trong _CACHE_TTL giây
# → trả bản cũ, khỏi gọi Gmail. MỚI: lưu qua app/core/kv — đặt REDIS_URL là cache
# chuyển sang Redis (đúng proposal, chia sẻ giữa nhiều worker), không đặt = in-memory.
# Khoá tuple cũ ("list"/"msg", access_token, ...) được đổi thành chuỗi có tiền tố
# "gmail:<hash-token>:" — token BĂM trước khi làm khoá (không để token thô lộ trong Redis).
import hashlib

from app.core.kv import kv
from app.core.limits import provider_slot  # trần số lệnh gọi Gmail song song toàn tiến trình
from app.core.breaker import guard_provider  # Gmail sập kéo dài → ngắt hẳn, hỏng nhanh thay vì chờ lâu

_CACHE_TTL = 60  # giây


def _kv_key(key: tuple) -> str:
    token_hash = hashlib.sha1(str(key[1]).encode()).hexdigest()[:12]
    rest = (key[0],) + tuple(key[2:])
    return f"gmail:{token_hash}:{rest!r}"


def _cache_get(key: tuple):
    return kv.get(_kv_key(key))


def _cache_set(key: tuple, value) -> None:
    kv.set(_kv_key(key), value, ttl=_CACHE_TTL)


def invalidate_cache(access_token: str) -> None:
    """Xoá MỌI mục cache của 1 người — gọi NGAY SAU khi GHI vào Gmail (gắn nhãn/xoá/gửi).
    Không dọn thì trong 60s sau hành động, người dùng vẫn thấy trạng thái CŨ từ cache
    và tưởng hành động thất bại. Xoá theo tiền tố hash-token của đúng người đó."""
    token_hash = hashlib.sha1(str(access_token).encode()).hexdigest()[:12]
    kv.delete_prefix(f"gmail:{token_hash}:")


def _header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


# ── NHÃN NGƯỜI DÙNG ĐÃ ĐẶT PHẢI THẮNG BỘ PHÂN LOẠI TỰ ĐỘNG ───────────────────
# Đây là gốc của lỗi "gắn nhãn xong, đi chỗ khác quay lại thì nhãn về như cũ".
# `apply_label` GHI nhãn thật xuống Gmail, nhưng lúc đọc lại thì `classify()` tính
# lại category/label TỪ NỘI DUNG và ghi đè — tức là thao tác của người dùng được ghi
# rồi KHÔNG BAO GIỜ được đọc. Nhìn từ ngoài giống hệt "app quên thao tác trước đó".
#
# Nguyên tắc: bộ phân loại tự động chỉ ĐOÁN khi chưa ai quyết. Người dùng đã quyết
# rồi thì quyết định đó là chân lý — nếu không, mọi lần gắn nhãn đều vô nghĩa.
_NHAN_MEOARC: dict[str, "object"] = {}   # điền lười ở dưới, tránh vòng lặp import


def _ban_do_nhan(access_token: str) -> dict[str, str]:
    """id → tên của mọi nhãn Gmail. Cần vì thư chỉ mang ID nhãn, không mang tên.

    Có cache riêng: danh sách nhãn đổi rất hiếm so với danh sách thư, mà gọi thêm một
    lần Gmail cho MỖI lần liệt kê thì vừa chậm vừa dễ chạm hạn mức."""
    key = ("labels", access_token, "", "")
    san = _cache_get(key)
    if san is not None:
        return san
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get("https://gmail.googleapis.com/gmail/v1/users/me/labels",
                      headers={"Authorization": f"Bearer {access_token}"})
            r.raise_for_status()
            ra = {lb["id"]: lb.get("name", "") for lb in (r.json().get("labels") or [])}
    except Exception:
        # Không lấy được nhãn thì LÙI VỀ bộ phân loại tự động, đừng làm hỏng cả danh
        # sách thư chỉ vì một lời gọi phụ.
        return {}
    _cache_set(key, ra)
    return ra


def _nhan_nguoi_dung_dat(label_ids: list[str], ban_do: dict[str, str]):
    """Trả Category mà NGƯỜI DÙNG đã gắn, hoặc None nếu chưa gắn nhãn MeoArc nào.

    Chỉ nhận nhãn TRÙNG TÊN với một trong 7 nhãn MeoArc. Nhãn Gmail khác của người
    dùng ("Du lịch", "Gia đình"…) bị bỏ qua có chủ ý: giao diện chỉ có 7 màu chip, và
    đoán màu cho một nhãn lạ là bịa ra thông tin không có thật."""
    if not label_ids or not ban_do:
        return None
    from app.core.labeling import tu_ten_nhan
    for lid in label_ids:
        nhom = tu_ten_nhan(ban_do.get(lid) or "")
        if nhom is not None:
            return nhom
    return None


def _co_dinh_kem(msg: dict) -> bool:
    """Thư này có tệp đính kèm không — suy từ mimeType, dùng cho DANH SÁCH.

    Ở `format=metadata` Gmail KHÔNG trả `payload.parts` (đã đo trên thư thật), nên không
    có cách nào biết TÊN tệp mà không tải thêm một lượt cho mỗi thư — tức nhân số lượt
    gọi Gmail lên gấp đôi chỉ để vẽ một cái kẹp giấy.
    `multipart/mixed` là khuôn Gmail dùng khi có tệp đính kèm; thư chỉ có text+HTML là
    `multipart/alternative`, thư có ảnh nhúng là `multipart/related`. Nên đây là suy
    luận có căn cứ, không phải đoán mò — và nó chỉ nói CÓ/KHÔNG, không bịa tên.
    """
    return (msg.get("payload", {}).get("mimeType") or "") == "multipart/mixed"


def _to_email(msg: dict, folder: str = "inbox", ban_do_nhan: dict[str, str] | None = None) -> Email:
    name, addr = parseaddr(_header(msg, "From"))  # tách "Tên <email>" → (tên, email)
    to_name, to_addr = parseaddr(_header(msg, "To"))
    sender = name or addr or "(không tên)"
    # Thư MÌNH GỬI (sent/drafts): From = chính mình → card phải hiện NGƯỜI NHẬN
    # (như Gmail thật hiện "Tới: X"). Trước đây luôn lấy From nên mọi thẻ ở mục
    # Đã gửi đều mang tên tài khoản của mình — trông như "MeoArc gửi MeoArc".
    display = sender
    display_email = addr
    if folder in ("sent", "drafts"):
        display = to_name or to_addr or "(chưa có người nhận)"
        display_email = to_addr
    raw_date = _header(msg, "Date")
    time_s, date_s = _fmt_local(raw_date)   # giờ hiển thị THEO GIỜ VN (đã sửa lệch múi giờ)
    labels = msg.get("labelIds", [])
    snippet = msg.get("snippet", "")
    raw_subject = _header(msg, "Subject") or ""
    # UC009: phân loại TẤT ĐỊNH theo người gửi + tiêu đề + snippet (engine rule-based).
    # Thay cho băm id ngẫu nhiên trước đây → mỗi lần fetch cho ĐÚNG MỘT category/label
    # (nhãn không "biến mất" sau khi làm mới), và khớp y hệt nhãn UC009 đề xuất/áp.
    # NGƯỜI DÙNG ĐÃ GẮN NHÃN thì dùng nhãn đó; chưa thì mới để bộ phân loại đoán.
    nhom = (_nhan_nguoi_dung_dat(labels, ban_do_nhan or {})
            or classify(addr, name, raw_subject, snippet).category)
    return Email(
        id=msg["id"],
        hasAttachment=_co_dinh_kem(msg),
        sender=display,
        senderEmail=display_email,
        senderInitial=(display.lstrip("(")[:1].upper() or "?"),
        to=to_addr,                 # người nhận thật (detail/FE dùng được)
        subject=raw_subject or "(không tiêu đề)",
        preview=snippet,
        body=[snippet],             # nấc này chỉ lấy snippet; body đầy đủ để sau
        time=time_s,
        date=date_s,
        unread=("UNREAD" in labels),
        starred=("STARRED" in labels),
        category=nhom.color,           # type: ignore[arg-type]  (1 trong 7 màu chip FE)
        label=nhom.label,              # tên nhãn tiếng Việt (Học tập/Công việc/…) hiện trên card
        folder=folder,              # type: ignore[arg-type]  (gắn đúng thư mục đang xem)
        threadId=msg.get("threadId"),  # id luồng THẬT từ Gmail (đóng nợ INTEGRATION #3)
    )


# Ánh xạ "thư mục" của app → "nhãn hệ thống" của Gmail.
_FOLDER_LABEL = {
    "inbox": "INBOX",
    "sent": "SENT",
    "drafts": "DRAFT",
    "trash": "TRASH",
    "starred": "STARRED",
    # SPAM TỪNG THIẾU Ở ĐÂY, và thiếu theo cách im lặng nhất có thể: `.get(folder,
    # "INBOX")` bên dưới nuốt mọi thư mục lạ rồi trả về INBOX. Nên bấm "Thư rác"
    # thì Gmail được hỏi về INBOX và MeoArc hiện lại đúng hộp thư đến — không lỗi,
    # không log, chỉ là dữ liệu sai.
    "spam": "SPAM",
}
# Các giá trị folder hợp lệ để gắn vào Email (khớp kiểu Folder bên schema).
# 'starred' KHÔNG nằm đây (nó là cờ, không phải thư mục) → gắn tạm 'inbox'.
_VALID_TAGS = {"inbox", "sent", "drafts", "archive", "trash", "spam"}


def _folder_from_labels(labels: list[str]) -> str:
    """Suy THƯ MỤC app từ nhãn hệ thống Gmail. Dùng khi lấy 1 thư (get_message) — nơi KHÔNG
    biết trước thư mục — để sync lũy tiến gán ĐÚNG (trước đây hardcode 'inbox' → thư Đã gửi/
    Lưu trữ/Thùng rác bị dồn nhầm vào Hộp thư đến)."""
    if "SPAM" in labels:
        return "spam"
    if "TRASH" in labels:
        return "trash"
    if "DRAFT" in labels:
        return "drafts"
    # ── INBOX PHẢI ĐỨNG TRƯỚC SENT ──
    # Một thư TỰ GỬI CHO CHÍNH MÌNH mang CẢ HAI nhãn INBOX và SENT. Gmail xếp nó vào
    # Hộp thư đến, nên ta cũng phải vậy.
    # Khi SENT đứng trước, lỗi hiện ra theo cách khó lần nhất: danh sách gắn "inbox"
    # (đúng, vì hỏi Gmail theo thư mục) nhưng mở chi tiết lại suy ra "sent" — thư BIẾN
    # MẤT khỏi hộp thư ngay khi bấm vào, và chỉ xảy ra với thư tự gửi. Đúng loại thư
    # dùng để tạo dữ liệu demo, nên nó chỉ đập vào mặt lúc trình bày.
    # SPAM/TRASH/DRAFT vẫn đứng trước vì chúng thật sự gỡ thư khỏi INBOX.
    if "INBOX" in labels:
        return "inbox"
    if "SENT" in labels:
        return "sent"
    return "archive"  # không còn ở inbox/trash/spam/draft → coi như đã lưu trữ


@gmail_read_retry
def list_messages(
    access_token: str,
    folder: str = "inbox",
    q: str | None = None,
    unread: bool | None = None,
    starred: bool | None = None,
    attachment: bool | None = None,
    page_token: str | None = None,
    max_results: int = 30,
    bypass_cache: bool = False,
    scan_after: str | None = None,   # ngày ISO 'YYYY-MM-DD' — mốc sớm nhất được quét
) -> tuple[list[Email], str | None]:
    """Lấy danh sách thư theo THƯ MỤC + LỌC + PHÂN TRANG, dịch sang Email.
    Trả về (danh_sách_Email, cursor_trang_kế) — cursor None nghĩa là hết thư.

    Ánh xạ thư mục → Gmail (inbox/sent/drafts/trash/starred → nhãn hệ thống; archive →
    thư ngoài inbox/trash/spam). Bộ lọc nhanh → toán tử Gmail: is:unread / is:starred /
    has:attachment (ghép được với cả thư mục lẫn từ khoá). Phân trang dùng pageToken.
    """
    # CACHE: khoá gồm ĐỦ tiêu chí (kể cả lọc + trang) để không trả nhầm kết quả cũ.
    cache_key = ("list", access_token, folder, q or "",
                 bool(unread), bool(starred), bool(attachment), page_token or "",
                 scan_after or "")
    # bypass_cache=True (nút "Làm mới") → KHÔNG đọc cache, ép hỏi Gmail lấy bản mới nhất.
    if not bypass_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    headers = {"Authorization": f"Bearer {access_token}"}
    params: dict = {"maxResults": max_results}
    if page_token:
        params["pageToken"] = page_token

    # Gom các toán tử lọc nhanh → ghép vào q (Gmail cho phép kèm cùng labelIds).
    extra = []
    # NFR-SCO-01: cửa sổ quét theo gói, vd `after:2026/05/09`. Ghép vào `extra` nên nó
    # tự có mặt ở CẢ BA nhánh dựng truy vấn bên dưới — thêm riêng từng nhánh thì kiểu gì
    # cũng sót một chỗ, và chỗ sót đó lặng lẽ quét quá phạm vi.
    if scan_after:
        extra.append(f"after:{scan_after.replace('-', '/')}")
    if unread:
        extra.append("is:unread")
    if starred:
        extra.append("is:starred")
    if attachment:
        extra.append("has:attachment")

    if q:  # có từ khoá → TÌM trên toàn hộp thư (kèm bộ lọc nếu có)
        params["q"] = " ".join([q, *extra])
    elif folder == "archive":
        # "Lưu trữ" = KHÔNG ở inbox/sent/draft/trash/spam. PHẢI loại cả sent/draft, nếu không
        # thư Đã gửi/Nháp (vốn không nằm inbox) sẽ lọt vào archive và bị gán nhầm thư mục.
        params["q"] = " ".join(["-in:inbox -in:sent -in:draft -in:trash -in:spam", *extra])
    else:
        params["labelIds"] = _FOLDER_LABEL.get(folder, "INBOX")
        # Gmail mặc định GIẤU cả thùng rác LẪN thư rác khỏi mọi truy vấn. Không bật
        # cờ này thì hỏi labelIds=SPAM vẫn trả về rỗng — đúng triệu chứng "Gmail có
        # thư mà MeoArc không thấy".
        if params["labelIds"] in ("TRASH", "SPAM"):
            params["includeSpamTrash"] = "true"
        if extra:                               # lọc nhanh trong 1 thư mục cụ thể
            params["q"] = " ".join(extra)

    tag = folder if folder in _VALID_TAGS else "inbox"  # nhãn folder gắn vào mỗi Email

    # Dùng chung 1 connection pool cho cả B1 lẫn B2 (giữ keep-alive, đỡ bắt tay TLS lại).
    http_limits = httpx.Limits(max_connections=_LIST_WORKERS, max_keepalive_connections=_LIST_WORKERS)
    # NFR-Scalability: xin SUẤT gọi nhà cung cấp. Mỗi request bắn 8 lệnh song song;
    # không có trần toàn cục thì 50 người vào cùng lúc = 400 kết nối → Gmail trả 429
    # hàng loạt và mọi người cùng hỏng. Hết suất thì xếp hàng, quá lâu thì báo bận.
    with provider_slot(), guard_provider(), httpx.Client(timeout=15, limits=http_limits) as client:
        # B1: lấy DANH SÁCH id thư (Gmail chỉ trả id) + token trang kế (nếu còn).
        listing = client.get(GMAIL_LIST, headers=headers, params=params)
        listing.raise_for_status()
        data = listing.json()
        ids = [m["id"] for m in data.get("messages", [])]
        next_cursor = data.get("nextPageToken")  # None khi đã hết thư

        # B2: với mỗi id, lấy METADATA (From/Subject/Date + nhãn + snippet).
        # Gmail KHÔNG trả sẵn metadata trong bước danh sách, nên buộc phải hỏi từng thư.
        # Trước đây gọi TUẦN TỰ: 30 thư = 30 lượt nối đuôi nhau, mỗi lượt ~200ms → 6s chờ.
        # Nay chạy SONG SONG có giới hạn: cùng số lượt gọi (không tốn thêm hạn mức API)
        # nhưng thời gian chờ giảm còn khoảng 1/8.
        def _fetch(mid: str):
            try:
                r = client.get(
                    GMAIL_MSG.format(id=mid), headers=headers,
                    params={"format": "metadata",
                            "metadataHeaders": ["From", "To", "Subject", "Date"]},
                )
                return r.json() if r.status_code == 200 else None
            except httpx.HTTPError:
                return None  # 1 thư lỗi thì bỏ qua, không làm hỏng cả trang

        emails: list[Email] = []
        if ids:
            # Lấy bản đồ nhãn MỘT LẦN cho cả trang (có cache riêng), để biết thư nào đã
            # được NGƯỜI DÙNG gắn nhãn — nhãn đó phải thắng bộ phân loại tự động.
            ban_do = _ban_do_nhan(access_token)
            with ThreadPoolExecutor(max_workers=min(_LIST_WORKERS, len(ids))) as pool:
                # map giữ ĐÚNG THỨ TỰ Gmail trả về — thư mới nhất vẫn nằm trên đầu.
                for raw in pool.map(_fetch, ids):
                    if raw is not None:
                        emails.append(_to_email(raw, tag, ban_do))
        result = (emails, next_cursor)
        _cache_set(cache_key, result)  # lưu lại để lần sau (trong TTL) khỏi gọi Gmail
        return result


# ── Lấy chi tiết 1 thư (thân thư đầy đủ + đính kèm) — UC004 ───────────

def _decode_b64url(data: str) -> str:
    """Gmail cất thân thư dưới dạng base64 (kiểu URL-safe). Giải mã về chữ thường."""
    if not data:
        return ""
    pad = "=" * (-len(data) % 4)  # thêm cho đủ bội số 4 ký tự (yêu cầu của base64)
    try:
        return base64.urlsafe_b64decode(data + pad).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(html: str) -> str:
    """Nếu thư chỉ có bản HTML → bỏ thẻ <...> cho ra chữ đọc được (cách thô)."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text)


def _human_size(num: int) -> str:
    if num < 1024:
        return f"{num} B"
    if num < 1024 * 1024:
        return f"{num // 1024} KB"
    return f"{num / 1024 / 1024:.1f} MB"


def _extract_body(payload: dict) -> tuple[str, str, list[dict]]:
    """Thư Gmail gồm nhiều 'mảnh' (parts) lồng nhau. Đi đệ quy qua từng mảnh để:
    lấy phần chữ (ưu tiên text/plain) và gom danh sách tệp đính kèm."""
    plain, html, attachments = "", "", []

    def walk(part: dict) -> None:
        nonlocal plain, html
        filename = part.get("filename", "")
        body = part.get("body", {})
        mime = part.get("mimeType", "")
        if filename:  # mảnh có tên tệp = đính kèm
            attachments.append({"name": filename, "size": _human_size(body.get("size", 0))})
        elif mime == "text/plain" and not plain:
            plain = _decode_b64url(body.get("data", ""))
        elif mime == "text/html" and not html:
            html = _decode_b64url(body.get("data", ""))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)
    return (plain or _strip_html(html)), html, attachments


@gmail_read_retry
def _to_email_day_du(msg: dict, ban_do_nhan: dict[str, str] | None = None) -> Email:
    """Thư ĐẦY ĐỦ từ Gmail (dict `format=full`) → Email.

    Tách khỏi `get_message` để `get_thread` dùng lại y hệt. Chép đoạn này sang chỗ khác
    là mở đường cho hai màn hình nói hai điều khác nhau về cùng một lá thư — sửa một bên
    thì bên kia lặng lẽ ở lại phiên bản cũ.
    """
    text, html, attachments = _extract_body(msg.get("payload", {}))
    # Tách thành các đoạn (ngăn bởi dòng trống) cho FE hiển thị từng <p>.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] or [msg.get("snippet", "")]
    name, addr = parseaddr(_header(msg, "From"))
    sender = name or addr or "(không tên)"
    raw_date = _header(msg, "Date")
    _, date_s = _fmt_local(raw_date)        # giờ VN (đồng nhất với danh sách)
    labels = msg.get("labelIds", [])
    raw_subject = _header(msg, "Subject") or ""
    # Cùng luật với danh sách: NHÃN NGƯỜI DÙNG ĐÃ ĐẶT thắng bộ phân loại tự động.
    # Thiếu ở đây thì mở chi tiết một thư vừa gắn nhãn sẽ thấy nhãn CŨ, còn danh sách
    # thấy nhãn MỚI — hai màn nói hai điều khác nhau về cùng một lá thư.
    nhom = (_nhan_nguoi_dung_dat(labels, ban_do_nhan)
            or classify(addr, name, raw_subject, msg.get("snippet", "")).category)
    return Email(
        id=msg["id"],
        threadId=msg.get("threadId"),
        sender=sender,
        senderEmail=addr,
        senderInitial=(sender[:1].upper() or "?"),
        to=_header(msg, "To"),
        cc=(_header(msg, "Cc") or None),
        subject=raw_subject or "(không tiêu đề)",
        preview=msg.get("snippet", ""),
        body=paragraphs,
        time=date_s,
        date=date_s,
        unread=("UNREAD" in labels),
        starred=("STARRED" in labels),
        category=nhom.color,           # type: ignore[arg-type]
        label=nhom.label,              # nhãn khớp danh sách → mở chi tiết không "nhảy màu"
        attachments=([{"name": a["name"], "size": a["size"]} for a in attachments] or None),  # type: ignore[arg-type]
        hasAttachment=bool(attachments),   # chi tiết BIẾT chắc, không phải suy từ mimeType
        html=(html or None),                  # HTML gốc để FE render đúng chuẩn Gmail
        folder=_folder_from_labels(labels),   # suy đúng thư mục từ nhãn (sent/drafts/trash/archive)
    )


def get_message(access_token: str, msg_id: str) -> Email:
    """Lấy 1 thư ĐẦY ĐỦ (thân thư + đính kèm) — dùng khi mở chi tiết."""
    # CACHE: mở lại đúng thư này trong TTL → trả bản cũ, khỏi tải lại từ Gmail.
    cache_key = ("msg", access_token, msg_id)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=15) as client:
        r = client.get(GMAIL_MSG.format(id=msg_id), headers=headers, params={"format": "full"})
        r.raise_for_status()
        msg = r.json()

    email = _to_email_day_du(msg, _ban_do_nhan(access_token))
    _cache_set(cache_key, email)
    return email


# ── Lấy CẢ LUỒNG hội thoại (UC004) ───────────────────────────────────
def get_thread(access_token: str, thread_id: str) -> list[Email]:
    """Mọi thư trong một luồng, sắp CŨ → MỚI (đúng thứ tự đọc một cuộc trao đổi).

    ── VÌ SAO CẦN HÀM NÀY ──
    Danh sách đã gộp luồng thành một dòng (`_gom_theo_luong`) — đúng như Gmail. Nhưng
    mở dòng đó ra thì `get_message` chỉ trả về ĐÚNG MỘT thư, nên bốn lượt trao đổi
    trước đó không có chỗ nào để xem. Gộp lại mà không mở ra được thì tệ hơn không gộp:
    người dùng còn không biết là mình đang bị giấu thứ gì.

    MỘT lượt gọi cho cả luồng (`threads.get?format=full`) chứ không lặp `get_message`
    cho từng thư: một cuộc trao đổi mười lượt sẽ thành mười lượt gọi Gmail, chậm và ăn
    hạn ngạch cho đúng thứ Gmail sẵn sàng trả trong một lần.
    """
    cache_key = ("thread", access_token, thread_id)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=20) as client:
        r = client.get(GMAIL_THREAD.format(id=thread_id), headers=headers,
                       params={"format": "full"})
        r.raise_for_status()
        data = r.json()

    ban_do = _ban_do_nhan(access_token)
    ds: list[Email] = []
    for msg in data.get("messages", []):
        try:
            ds.append(_to_email_day_du(msg, ban_do))
        except Exception as exc:      # một thư hỏng không được làm mất cả luồng
            logger.warning("thread %s: bỏ qua thư %s (%s)", thread_id, msg.get("id"), exc)
    _cache_set(cache_key, ds)
    return ds


# ── Tải 1 tệp đính kèm (UC004 — nút Download) ────────────────────────
def get_attachment(
    access_token: str, msg_id: str, filename: str
) -> tuple[bytes | None, str | None, str | None]:
    """Lấy BYTES của tệp đính kèm tên `filename` trong thư `msg_id`.
    Trả (dữ liệu, kiểu MIME, tên tệp) — hoặc (None, None, None) nếu không tìm thấy.

    Hai bước: (1) đọc thư đầy đủ, đi qua các 'mảnh' tìm mảnh có đúng tên tệp để lấy
    `attachmentId`; (2) gọi endpoint attachments lấy bytes (Gmail trả base64url)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    found: dict = {"aid": None, "mime": None, "name": None}

    def walk(part: dict) -> None:
        if found["aid"]:
            return
        if part.get("filename") == filename:           # đúng tệp cần
            found["aid"] = part.get("body", {}).get("attachmentId")
            found["mime"] = part.get("mimeType")
            found["name"] = part.get("filename")
            return
        for child in part.get("parts", []) or []:
            walk(child)

    with httpx.Client(timeout=20) as client:
        r = client.get(GMAIL_MSG.format(id=msg_id), headers=headers, params={"format": "full"})
        r.raise_for_status()
        walk(r.json().get("payload", {}))
        if not found["aid"]:
            return None, None, None
        ar = client.get(
            GMAIL_ATTACH.format(id=msg_id, aid=found["aid"]), headers=headers
        )
        ar.raise_for_status()
        data_b64 = ar.json().get("data", "")

    pad = "=" * (-len(data_b64) % 4)                    # bù cho đủ bội số 4 (yêu cầu base64)
    raw = base64.urlsafe_b64decode(data_b64 + pad)
    return raw, found["mime"], found["name"]


# ══════════ ĐỒNG BỘ LŨY TIẾN + PUSH (store-of-record) ══════════
# Ý tưởng: KHÔNG polling. Bật Gmail watch() (Pub/Sub) 1 lần → mỗi khi hộp thư đổi,
# Google đẩy 1 thông báo kèm historyId → worker gọi history.list(startHistoryId) chỉ để
# biết ID thư nào THÊM/XOÁ/ĐỔI NHÃN, rồi fetch đúng các thư đó về DB. Đọc web = đọc DB.

def get_profile_history_id(access_token: str) -> str | None:
    """historyId hiện tại của hộp thư — làm mốc bắt đầu cho các lần incremental sync sau."""
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=15) as client:
        r = client.get(GMAIL_PROFILE, headers=headers)
        r.raise_for_status()
        return str(r.json().get("historyId") or "") or None


def list_history(access_token: str, start_history_id: str) -> dict:
    """Lấy MỌI thay đổi kể từ `start_history_id`. Trả {added, deleted, updated, history_id}.
    added/updated/deleted = danh sách message id. Ném HistoryExpired nếu mốc quá cũ (HTTP 404)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    added: set[str] = set()
    deleted: set[str] = set()
    updated: set[str] = set()
    latest = start_history_id
    page_token: str | None = None
    with httpx.Client(timeout=15) as client:
        while True:
            params = {"startHistoryId": start_history_id, "maxResults": 500}
            if page_token:
                params["pageToken"] = page_token
            r = client.get(GMAIL_HISTORY, headers=headers, params=params)
            if r.status_code == 404:
                raise HistoryExpired(start_history_id)
            r.raise_for_status()
            data = r.json()
            latest = str(data.get("historyId") or latest)
            for h in data.get("history", []):
                for a in h.get("messagesAdded", []):
                    added.add(a["message"]["id"])
                for d in h.get("messagesDeleted", []):
                    deleted.add(d["message"]["id"])
                for key in ("labelsAdded", "labelsRemoved"):
                    for lc in h.get(key, []):
                        updated.add(lc["message"]["id"])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    # Thư vừa thêm rồi lại xoá trong cùng khoảng → coi là xoá.
    added -= deleted
    updated -= deleted
    return {"added": list(added), "deleted": list(deleted),
            "updated": list(updated - added), "history_id": latest}


def watch(access_token: str, topic_name: str, label_ids: list[str] | None = None) -> dict:
    """BẬT Gmail Push: mọi thay đổi hộp thư → Google publish lên Pub/Sub `topic_name`
    (dạng 'projects/<proj>/topics/<topic>'). Trả {historyId, expiration} — watch hết hạn ~7 ngày,
    phải gọi lại định kỳ. CẦN: đã tạo topic + cấp quyền publish cho gmail-api-push@system.gserviceaccount.com."""
    headers = {"Authorization": f"Bearer {access_token}"}
    body = {"topicName": topic_name, "labelIds": label_ids or ["INBOX"],
            "labelFilterBehavior": "INCLUDE"}
    with httpx.Client(timeout=15) as client:
        r = client.post(GMAIL_WATCH, headers=headers, json=body)
        r.raise_for_status()
        return r.json()


def stop_watch(access_token: str) -> None:
    """TẮT Gmail Push cho hộp thư này."""
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=15) as client:
        client.post(GMAIL_STOP, headers=headers)
