# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/schemas/send.py — KHUÔN dữ liệu gửi/trả lời thư (Nấc 6b)       ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ Khớp `SendEmailInput` bên FE (api.ts) và hợp đồng mục D.           ║
# ╚══════════════════════════════════════════════════════════════════╝

from pydantic import BaseModel


class SendReq(BaseModel):
    """POST /emails/send — body khi soạn thư mới.
    cc/bcc là DANH SÁCH email (FE gửi mảng); để None nếu không có.
    attachmentIds: id các tệp ĐÃ upload trước qua /uploads → BE lấy bytes đính vào thư."""
    to: str
    subject: str
    body: str = ""
    cc: list[str] | None = None
    bcc: list[str] | None = None
    attachmentIds: list[str] | None = None
    # Bản CÓ ĐỊNH DẠNG (đậm/nghiêng/gạch chân/màu). Gửi KÈM `body` chứ không thay:
    # ứng dụng đọc được HTML thì hiện định dạng, chỗ nào không thì vẫn còn chữ để đọc.
    html: str | None = None


class ReplyReq(BaseModel):
    """POST /emails/{id}/reply — chỉ cần nội dung; người nhận/tiêu đề BE tự suy từ thư gốc.

    `replyAll=True` gửi cho cả những người có mặt trong thư gốc (To + Cc), trừ chính mình.
    Mặc định False để nút "Trả lời" cũ giữ nguyên hành vi."""
    body: str
    replyAll: bool = False
    html: str | None = None


class SendResult(BaseModel):
    """Trả về sau khi gửi: id thư Gmail vừa tạo (FE chỉ cần biết 'đã gửi, đây là id')."""
    id: str
    threadId: str | None = None
