# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/services/gmail_send.py — GỬI & TRẢ LỜI thư thật (Nấc 6b)       ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ MỤC ĐÍCH: dựng một bức thư đúng chuẩn rồi nhờ Gmail GỬI đi.        ║
# ║ KHÁI NIỆM: thư email không phải JSON — nó là văn bản theo chuẩn    ║
# ║   MIME/RFC 2822 (các dòng "To:", "Subject:"... rồi tới thân thư).  ║
# ║   Gmail API yêu cầu ta gói nguyên bức thư đó thành base64url rồi   ║
# ║   gửi trong field "raw". Lớp `email.message.EmailMessage` của      ║
# ║   Python lo phần dựng chuẩn MIME giúp ta (khỏi tự nối chuỗi tay).  ║
# ║ Cần quyền gmail.send (đã thêm ở auth_service).                    ║
# ╚══════════════════════════════════════════════════════════════════╝

import base64
from email.message import EmailMessage
from email.utils import parseaddr
import httpx
from app.services import gmail_service
from app.services.gmail_actions import GmailPermissionError  # tái dùng lỗi 403 cho nhất quán

GMAIL_SEND = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
GMAIL_DRAFTS = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
# Lấy header của thư GỐC (khi trả lời) — chỉ cần vài header, nên format=metadata cho nhẹ.
GMAIL_GET = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}"


def create_draft(access_token: str, to: str, subject: str, body: str,
                 cc: list[str] | None = None, bcc: list[str] | None = None,
                 attachments: list[dict] | None = None) -> dict:
    """Lưu 1 BẢN NHÁP lên Gmail (users.drafts.create) — KHÔNG gửi đi. Trả dict
    {id, message:{id, threadId,...}} để nơi gọi biết id nháp + id message (hiện ở thư mục Nháp)."""
    raw = _build_raw(to, subject, body, cc=cc, bcc=bcc, attachments=attachments)
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=15) as client:
        r = client.post(GMAIL_DRAFTS, headers=headers, json={"message": {"raw": raw}})
        if r.status_code == 403:
            raise GmailPermissionError()
        r.raise_for_status()
        gmail_service.invalidate_cache(access_token)  # thư mục Nháp đổi → dọn cache
        return r.json()


def _build_raw(
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    extra_headers: dict[str, str] | None = None,
    attachments: list[dict] | None = None,
    from_addr: str | None = None,
) -> str:
    """Dựng bức thư MIME rồi mã hoá base64url (đúng thứ Gmail field "raw" cần).

    VÌ SAO base64url (không phải base64 thường): thư có thể chứa ký tự đặc biệt /
    xuống dòng; mã hoá để truyền an toàn qua JSON. 'url-safe' để '+' '/' không phá URL.

    attachments: danh sách {name, content(bytes), mime}. Khi có, EmailMessage tự chuyển
    bức thư thành 'multipart/mixed' (1 phần chữ + mỗi tệp 1 phần) đúng chuẩn.

    from_addr: đặt header "From" (dạng `"Tên hiển thị" <dia@chi>`). Bỏ trống thì Gmail
      tự điền địa chỉ tài khoản đang đăng nhập — đúng cho mọi luồng thật.
      ĐỊA CHỈ vẫn phải là tài khoản đang đăng nhập hoặc một alias đã xác minh; Gmail
      TỪ CHỐI gửi hộ địa chỉ lạ. Cái đổi được chỉ là TÊN HIỂN THỊ. Đây không phải kẽ
      hở để mạo danh người khác, mà để bộ thư demo hiện đúng tên người gửi thay vì
      tám thẻ cùng đề tên chủ tài khoản.
    """
    msg = EmailMessage()
    msg["To"] = to
    if from_addr:
        msg["From"] = from_addr
    if cc:
        msg["Cc"] = ", ".join(cc)        # nhiều người Cc → nối bằng dấu phẩy theo chuẩn
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    # extra_headers: dùng cho TRẢ LỜI (In-Reply-To / References) để Gmail gom đúng luồng.
    for k, v in (extra_headers or {}).items():
        msg[k] = v
    msg.set_content(body)                # thân thư dạng text thuần (phần "chữ" của email)

    for att in attachments or []:
        # mime kiểu "image/png" → tách thành maintype="image", subtype="png".
        # Thiếu/sai → mặc định application/octet-stream (kiểu "tệp nhị phân chung chung").
        maintype, _, subtype = (att.get("mime") or "application/octet-stream").partition("/")
        msg.add_attachment(
            att["content"],
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att["name"],
        )
    # as_bytes() = toàn bộ bức thư (header + thân + tệp) dưới dạng bytes → base64url → chuỗi.
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _post_send(access_token: str, raw: str, thread_id: str | None = None) -> dict:
    """Gọi Gmail API gửi bức thư đã dựng (dùng chung cho gửi mới lẫn trả lời)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    payload: dict = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id  # gắn vào ĐÚNG luồng hội thoại (khi trả lời)
    with httpx.Client(timeout=15) as client:
        r = client.post(GMAIL_SEND, headers=headers, json=payload)
        if r.status_code == 403:         # token thiếu quyền gmail.send → báo rõ lên trên
            raise GmailPermissionError()
        r.raise_for_status()             # các lỗi khác (4xx/5xx) → ném để API trả 500/khác
        gmail_service.invalidate_cache(access_token)  # vừa gửi → thư mục Sent đổi, dọn cache
        return r.json()                  # { id, threadId, labelIds } của thư vừa gửi


def send_email(
    access_token: str,
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[dict] | None = None,
    from_addr: str | None = None,
) -> dict:
    """GỬI một thư MỚI (kèm tệp nếu có). Trả dict Gmail ({id, threadId,...}) để FE biết đã gửi.

    from_addr: xem `_build_raw` — chỉ đổi được TÊN HIỂN THỊ, địa chỉ vẫn là tài khoản
      đang đăng nhập. Dùng cho kịch bản dựng bộ thư demo."""
    raw = _build_raw(to, subject, body, cc=cc, bcc=bcc, attachments=attachments,
                     from_addr=from_addr)
    return _post_send(access_token, raw)


def forward_email(access_token: str, msg_id: str, to: str, note: str = "") -> dict:
    """CHUYỂN TIẾP thư msg_id tới `to`, kèm lời nhắn `note` ở đầu.

    ── VÌ SAO PHẢI TRÍCH NỘI DUNG GỐC, KHÔNG CHỈ GỬI LỜI NHẮN ──
    Chuyển tiếp mà chỉ gửi mỗi câu "bạn xem giúp mình nhé" thì người nhận không có gì
    để xem. Trích cả khối gốc (người gửi, ngày, tiêu đề, thân thư) theo đúng quy ước
    "---------- Thư đã chuyển tiếp ----------" mà mọi ứng dụng thư đều dùng, nên người
    nhận đọc bằng Gmail/Outlook đều thấy đúng hình dạng quen thuộc.

    KHÔNG mang theo TỆP ĐÍNH KÈM (giới hạn đã biết, nói thẳng): làm được nhưng phải tải
    từng tệp về rồi đính lại, tức nhân đôi lưu lượng và có thể vượt trần dung lượng thư.
    Để lại chứ không làm nửa vời — và phần thân thư trích dẫn đã nêu tên tệp, nên người
    nhận biết là có.

    KHÔNG gắn In-Reply-To/References: chuyển tiếp là MỞ một cuộc trao đổi mới với người
    khác, không phải nối tiếp cuộc cũ. Gắn vào thì thư lạc vào luồng của người không
    liên quan.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    with httpx.Client(timeout=15) as client:
        r = client.get(GMAIL_GET.format(id=msg_id), headers=headers, params={"format": "full"})
        if r.status_code == 403:
            raise GmailPermissionError()
        r.raise_for_status()
        goc = r.json()

    def _h(name: str) -> str:
        for h in goc.get("payload", {}).get("headers", []):
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

    from app.services.gmail_service import _extract_body

    than, _html, dinh_kem = _extract_body(goc.get("payload", {}))
    subject = _h("Subject") or "(không tiêu đề)"
    if not subject.lower().startswith(("fwd:", "fw:")):
        subject = f"Fwd: {subject}"

    khoi = ["---------- Thư đã chuyển tiếp ----------",
            f"Từ: {_h('From')}",
            f"Ngày: {_h('Date')}",
            f"Tiêu đề: {_h('Subject')}",
            f"Tới: {_h('To')}"]
    if dinh_kem:
        khoi.append("Tệp đính kèm (không kèm theo thư này): "
                    + ", ".join(a["name"] for a in dinh_kem))
    khoi.append("")
    khoi.append(than or goc.get("snippet", ""))

    noi_dung = (f"{note.strip()}\n\n" if note.strip() else "") + "\n".join(khoi)
    return _post_send(access_token, _build_raw(to=to, subject=subject, body=noi_dung))


def cc_tra_loi_tat_ca(to_goc: str, cc_goc: str, nguoi_gui: str, toi: str) -> list[str] | None:
    """Danh sách Cc cho "trả lời tất cả" — mọi người có mặt trong thư gốc, TRỪ hai người.

    Tách ra khỏi phần gọi mạng vì đây mới là chỗ có logic, và là chỗ sai thì KHÔNG AI
    THẤY: thư vẫn gửi đi, chỉ là gửi nhầm người hoặc thiếu người.

    Loại CHÍNH MÌNH — không thì mỗi lần trả lời tất cả là tự gửi cho mình một bản.
    Loại NGƯỜI GỬI — họ đã nằm ở To rồi; để cả hai chỗ thì họ nhận hai bản.
    Khử trùng — một người có tên ở cả To lẫn Cc của thư gốc cũng nhận hai bản.

    Trả None (không phải danh sách rỗng) khi không còn ai: `_build_raw` bỏ qua Cc rỗng,
    nên trả None cho đúng ý "không có Cc" thay vì một header trống.
    """
    from email.utils import getaddresses

    da_co = {(toi or "").lower(), parseaddr(nguoi_gui)[1].lower()}
    da_co.discard("")
    ra: list[str] = []
    for _ten, dia in getaddresses([to_goc or "", cc_goc or ""]):
        d = (dia or "").lower()
        if d and d not in da_co:
            da_co.add(d)
            ra.append(dia)
    return ra or None


def _dia_chi_cua_toi(access_token: str) -> str:
    """Địa chỉ của chính tài khoản đang đăng nhập — để loại mình ra khỏi Cc khi trả lời
    tất cả. Không loại thì mỗi lần trả lời tất cả là tự gửi cho mình một bản."""
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(gmail_service.GMAIL_PROFILE, headers={"Authorization": f"Bearer {access_token}"})
            r.raise_for_status()
            return (r.json().get("emailAddress") or "").lower()
    except Exception:
        return ""


def reply_email(access_token: str, msg_id: str, body: str, reply_all: bool = False) -> dict:
    """TRẢ LỜI thư có id=msg_id: tự điền người nhận = người gửi gốc, tiêu đề "Re: …",
    và gắn các header In-Reply-To/References + threadId để Gmail XẾP vào đúng luồng."""
    headers = {"Authorization": f"Bearer {access_token}"}
    # B1: đọc vài header của thư GỐC để biết gửi cho ai, tiêu đề gì, thuộc luồng nào.
    with httpx.Client(timeout=15) as client:
        r = client.get(
            GMAIL_GET.format(id=msg_id),
            headers=headers,
            params={"format": "metadata",
                    # "To"/"Cc" là BẮT BUỘC cho trả-lời-tất-cả. Thiếu chúng thì Gmail trả về header
             # rỗng, danh sách Cc dựng ra rỗng theo, và "trả lời tất cả" IM LẶNG thành trả
             # lời thường — không lỗi, không cảnh báo, chỉ là mấy người kia không nhận được.
             "metadataHeaders": ["From", "To", "Cc", "Subject", "Message-ID", "References"]},
        )
        if r.status_code == 403:
            raise GmailPermissionError()
        r.raise_for_status()
        original = r.json()

    def _h(name: str) -> str:  # lấy 1 header theo tên (không phân biệt hoa thường)
        for h in original.get("payload", {}).get("headers", []):
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

    from_addr = _h("From")                 # trả lời thì gửi NGƯỢC về người gửi gốc
    subject = _h("Subject")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"          # thêm tiền tố Re: nếu chưa có
    msg_ref = _h("Message-ID")             # mã định danh thư gốc → để Gmail nối luồng
    references = (_h("References") + " " + msg_ref).strip()  # chuỗi nối các thư trong luồng

    # ── TRẢ LỜI TẤT CẢ ──
    # Cc = mọi người có mặt trong thư gốc (To + Cc), TRỪ chính mình và trừ người gửi
    # (đã nằm ở To rồi). Không loại mình thì mỗi lần trả lời tất cả là tự gửi cho mình
    # một bản; không khử trùng thì một người có tên ở cả To lẫn Cc sẽ nhận hai bản.
    cc: list[str] | None = None
    if reply_all:
        cc = cc_tra_loi_tat_ca(_h("To"), _h("Cc"), from_addr, _dia_chi_cua_toi(access_token))

    raw = _build_raw(
        to=from_addr, subject=subject, body=body, cc=cc,
        extra_headers={"In-Reply-To": msg_ref, "References": references},
    )
    # threadId của thư gốc → bảo Gmail xếp thư trả lời vào CÙNG hội thoại.
    return _post_send(access_token, raw, thread_id=original.get("threadId"))
