# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/schemas/email.py — HÌNH DẠNG của một Email (Nấc 1)              ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ MỤC ĐÍCH: mô tả CHÍNH XÁC một Email gồm những trường gì, kiểu gì.   ║
# ║ VÌ SAO: Frontend đã chốt shape ở docs/interface/01-DATA-MODEL.      ║
# ║         BE phải trả đúng tên trường đó thì FE mới hiểu.             ║
# ║ Pydantic giúp: (1) TỰ kiểm tra dữ liệu sai kiểu → báo lỗi sớm,      ║
# ║                (2) TỰ đổi object Python ↔ JSON.                     ║
# ╚══════════════════════════════════════════════════════════════════╝

from typing import Literal
from pydantic import BaseModel

# `Literal[...]` = "chỉ được nhận đúng các giá trị này". Nếu lỡ gán
# category="xyz", Pydantic sẽ BÁO LỖI ngay — chặn dữ liệu rác.
Category = Literal["moss", "sea", "sun", "cherry", "sky", "terra", "wine", "jade"]
# PA1 §4.2.9 — hai trục tách rời, chỉ gán cho thư mang tính công việc.
Priority = Literal["High", "Medium", "Low"]
TaskStatus = Literal["Todo", "Waiting", "Done"]
# `spam` TỪNG THIẾU ở đây, và đó là lý do bấm "Thư rác" ra thông báo "Không nạp được
# thư từ máy chủ" thay vì danh sách thư.
#
# Lỗi ở chỗ khó thấy: tầng dịch vụ ánh xạ 'spam' → nhãn SPAM và LẤY VỀ ĐÚNG, chỉ tới
# bước dựng đối tượng `Email` mới vỡ vì `folder='spam'` không nằm trong danh sách hợp
# lệ. Nên triệu chứng là một lỗi mạng chung chung, còn nguyên nhân lại nằm ở kiểm tra
# kiểu — hai chỗ chẳng liên quan gì tới nhau khi nhìn từ ngoài.
#
# Và nó CHỈ nổ khi hộp thư THẬT SỰ CÓ thư rác: hộp rỗng thì không đối tượng nào được
# dựng, không lỗi nào được ném, và mọi phép thử đều xanh. Đúng bẫy đã làm tôi kết luận
# nhầm là "tính năng chạy tốt, chỉ là hộp thư trống".
Folder = Literal["inbox", "sent", "drafts", "archive", "trash", "spam"]


class Attachment(BaseModel):
    name: str   # tên tệp, vd "Mau_SRS.docx"
    size: str   # cỡ ở dạng chữ để hiển thị, vd "248 KB"


class Email(BaseModel):
    # GHI CHÚ: mình đặt tên trường y hệt FE (camelCase như senderEmail)
    # để JSON trả ra KHỚP 100% cái FE đợi — đỡ phải ánh xạ qua lại.
    # (Trong dự án lớn người ta hay dùng alias để giữ snake_case bên Python,
    #  nhưng ở đây ưu tiên dễ đối chiếu với hợp đồng.)
    id: str
    sender: str             # tên hiển thị người gửi
    senderEmail: str        # email người gửi
    senderInitial: str      # 1 ký tự cho avatar tròn
    to: str                 # người nhận (hiển thị)
    subject: str
    preview: str            # 1 dòng snippet
    body: list[str]         # các đoạn văn; mỗi phần tử = 1 đoạn <p> bên FE
    time: str               # nhãn ngắn ở danh sách, vd "08:42"
    date: str               # nhãn đầy đủ ở chi tiết, vd "Hôm nay, 08:42"
    unread: bool
    starred: bool
    category: Category

    # Các trường có dấu "?" bên FE = KHÔNG bắt buộc → cho giá trị mặc định None.
    label: str | None = None
    html: str | None = None                 # thân thư HTML gốc (để FE render đúng chuẩn Gmail);
                                            # None khi thư chỉ có text hoặc lấy từ store
    attachments: list[Attachment] | None = None
    # CÓ tệp đính kèm hay không — TÁCH khỏi `attachments`, vì danh sách thư KHÔNG biết
    # được tên tệp: Gmail ở `format=metadata` không trả `payload.parts` (đã đo trên thư
    # thật). Nên dùng chung một trường thì danh sách buộc phải hoặc bịa tên, hoặc im
    # lặng coi như không có tệp. Cả hai đều tệ hơn một lá cờ nói đúng sự thật mình biết.
    hasAttachment: bool | None = None
    priority: Priority | None = None        # do AI gán; None = KHÔNG phải việc (không phải "việc nhẹ")
    status: TaskStatus | None = None        # đi kèm priority — có thì có cả hai, không thì cùng None
    tldr: str | None = None                 # tóm tắt do AI; ban đầu có thể trống
    folder: Folder | None = None            # thiếu = coi như "inbox"
    threadId: str | None = None             # id LUỒNG Gmail (nhóm thư trả lời nhau) — agent cần
                                            # để reply đúng thread
    threadCount: int = 1                    # SỐ THƯ trong luồng. Gmail gộp một cuộc trao đổi
                                            # thành MỘT dòng; nếu trả về từng thư riêng thì một
                                            # cuộc qua lại 5 lượt hiện thành 5 thẻ, khác hẳn
                                            # Gmail và làm hộp thư trông đầy gấp mấy lần thật.
