# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/services/mail.py — ĐIỀU PHỐI theo provider (Gmail / Outlook)   ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ Endpoint gọi mail.X(provider, token, ...) thay vì gọi thẳng service ║
# ║ Gmail. provider='google' (mặc định) → gọi Y HỆT hàm Gmail cũ (luồng ║
# ║ Gmail KHÔNG đổi hành vi). provider='microsoft' → gọi Graph API.     ║
# ╚══════════════════════════════════════════════════════════════════╝

from app.services import gmail_service, gmail_actions, gmail_send, outlook_service


def _ms(provider: str) -> bool:
    return provider == "microsoft"


def list_messages(provider: str, token: str, **kw):
    if _ms(provider):
        return outlook_service.list_messages(token, **kw)
    return gmail_service.list_messages(token, **kw)


def get_message(provider: str, token: str, msg_id: str):
    if _ms(provider):
        return outlook_service.get_message(token, msg_id)
    return gmail_service.get_message(token, msg_id)


def get_thread(provider: str, token: str, thread_id: str):
    """Mọi thư trong một luồng hội thoại, sắp CŨ → MỚI."""
    if _ms(provider):
        return outlook_service.get_thread(token, thread_id)
    return gmail_service.get_thread(token, thread_id)


def send_email(provider: str, token: str, to, subject, body, cc=None, bcc=None,
               attachments=None, html=None):
    if _ms(provider):
        return outlook_service.send_email(token, to, subject, body, cc=cc, bcc=bcc, html=html)
    return gmail_send.send_email(token, to, subject, body, cc=cc, bcc=bcc,
                                 attachments=attachments or [], html=html)


def forward_email(provider: str, token: str, msg_id: str, to: str, note: str = ""):
    """Chuyển tiếp thư tới một địa chỉ khác, kèm lời nhắn."""
    if _ms(provider):
        return outlook_service.forward_email(token, msg_id, to, note)
    return gmail_send.forward_email(token, msg_id, to, note)


def reply_email(provider: str, token: str, msg_id: str, body: str, reply_all: bool = False,
                html: str | None = None, attachments: list[dict] | None = None):
    """Trả lời thư. `reply_all=True` gửi cho cả những người có mặt trong thư gốc.
    `html` là bản có định dạng, gửi KÈM bản chữ thuần chứ không thay."""
    if _ms(provider):
        return outlook_service.reply_email(token, msg_id, body, reply_all=reply_all,
                                           html=html, attachments=attachments)
    return gmail_send.reply_email(token, msg_id, body, reply_all=reply_all, html=html,
                                  attachments=attachments)


def create_draft(provider: str, token: str, to, subject, body, cc=None, bcc=None, attachments=None):
    if _ms(provider):
        return outlook_service.create_draft(token, to, subject, body, cc=cc, bcc=bcc)
    return gmail_send.create_draft(token, to, subject, body, cc=cc, bcc=bcc,
                                   attachments=attachments or [])


def set_read(provider: str, token: str, ids: list[str], read: bool) -> int:
    if _ms(provider):
        return outlook_service.set_read(token, ids, read)
    if read:
        return gmail_actions.modify_labels(token, ids, remove=["UNREAD"])
    return gmail_actions.modify_labels(token, ids, add=["UNREAD"])


def set_flag(provider: str, token: str, ids: list[str], flagged: bool) -> int:
    if _ms(provider):
        return outlook_service.set_flag(token, ids, flagged)
    if flagged:
        return gmail_actions.modify_labels(token, ids, add=["STARRED"])
    return gmail_actions.modify_labels(token, ids, remove=["STARRED"])


def archive(provider: str, token: str, ids: list[str]) -> int:
    if _ms(provider):
        return outlook_service.archive(token, ids)
    return gmail_actions.modify_labels(token, ids, remove=["INBOX"])


def spam(provider: str, token: str, ids: list[str]) -> int:
    """Đánh dấu thư rác. Gmail: thêm nhãn SPAM và bỏ INBOX cùng lúc — thiếu vế bỏ INBOX
    thì thư nằm ở CẢ hai chỗ, và người dùng thấy thứ mình vừa vứt đi vẫn còn trong hộp
    thư."""
    if _ms(provider):
        return outlook_service.spam(token, ids)
    return gmail_actions.modify_labels(token, ids, add=["SPAM"], remove=["INBOX"])


def not_spam(provider: str, token: str, ids: list[str]) -> int:
    """Bỏ đánh dấu thư rác, trả thư về hộp thư — đường lùi của `spam`."""
    if _ms(provider):
        return outlook_service.not_spam(token, ids)
    return gmail_actions.modify_labels(token, ids, add=["INBOX"], remove=["SPAM"])


def trash(provider: str, token: str, ids: list[str]) -> int:
    if _ms(provider):
        return outlook_service.trash(token, ids)
    return gmail_actions.trash(token, ids)


def untrash(provider: str, token: str, ids: list[str]) -> int:
    if _ms(provider):
        return outlook_service.untrash(token, ids)
    return gmail_actions.untrash(token, ids)


def apply_label(provider: str, token: str, ids: list[str], label: str) -> int:
    if _ms(provider):
        return outlook_service.apply_category(token, ids, label)
    return gmail_actions.apply_label(token, ids, label)


def remove_label(provider: str, token: str, ids: list[str], label: str) -> int:
    if _ms(provider):
        return outlook_service.set_categories(token, ids, [])  # Outlook: xoá category
    return gmail_actions.modify_labels(token, ids, None, [label.upper()])


def list_labels(provider: str, token: str) -> list[str]:
    if _ms(provider):
        return []  # Outlook dùng 'categories' — v1 chưa liệt kê master list
    return gmail_actions.list_label_names(token)
