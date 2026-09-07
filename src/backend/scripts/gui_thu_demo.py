"""Gửi bộ thư demo vào chính hộp thư đang đăng nhập, để màn Lịch trình có dữ liệu THẬT.

── VÌ SAO CẦN KỊCH BẢN NÀY ──
Bộ thư demo trong `src/frontend/src/data/demo-lich.ts` là DỮ LIỆU GIẢ nằm trong mã
nguồn frontend. Nó chỉ hiện ở chế độ mock (`VITE_API_BASE_URL` rỗng). Bản chạy thật
và bản deploy đều đọc Gmail thật, nên dữ liệu giả đó KHÔNG BAO GIỜ xuất hiện ở đó.

Muốn hộp thư thật có sự kiện để trình bày thì phải thật sự gửi thư vào nó. Kịch bản
này làm đúng việc đó: dùng phiên đăng nhập sẵn có trong DB để gửi thư TỪ tài khoản
của bạn TỚI chính nó.

── CÁCH CHẠY ──
    cd src/backend
    ./.venv/Scripts/python.exe scripts/gui_thu_demo.py            # xem trước, KHÔNG gửi
    ./.venv/Scripts/python.exe scripts/gui_thu_demo.py --gui-that # gửi thật (8 thư)

    # Thêm ~51 thư dồn cục để xem màn Lịch trình DƯỚI TẢI THẬT:
    ./.venv/Scripts/python.exe scripts/gui_thu_demo.py --bo-day             # xem trước
    ./.venv/Scripts/python.exe scripts/gui_thu_demo.py --bo-day --gui-that  # gửi 59 thư

Mặc định là XEM TRƯỚC. Gửi thư là việc không hoàn tác được — nó rời khỏi máy bạn và
nằm trong hộp thư thật — nên phải gõ thêm cờ mới gửi. Cùng nguyên tắc confirm-gate
mà sản phẩm này áp cho agent.

`--bo-day` gửi 59 thư, và vì thư tự gửi nằm ở CẢ Hộp thư đến LẪN Đã gửi nên hộp thư
sẽ có ~118 mục cần dọn. Kịch bản in cảnh báo kèm truy vấn dọn trước khi chạy. Nên gửi
trước buổi trình bày ít nhất một hôm để còn kịp kiểm tra.

── LƯU Ý ──
Thư gửi cho CHÍNH MÌNH sẽ nằm ở cả Đã gửi lẫn Hộp thư đến, và Gmail gộp chúng thành
một luồng. Đó là hành vi đúng của Gmail, không phải lỗi.

CÓ VÀO THƯ RÁC KHÔNG? Gần như chắc chắn là không. Thư đi qua chính Gmail API bằng
phiên OAuth của bạn, nên với Gmail đây là thư do CHÍNH BẠN gửi: xác thực đầy đủ
(SPF/DKIM/DMARC đều đạt vì nó thật sự phát từ máy chủ Google), người gửi lại nằm
trong danh bạ của chính mình. Bộ lọc rác không có gì để nghi.

Rủi ro thật nằm ở chỗ khác: Gmail có thể xếp thư "Sale 9.9" vào thẻ **Quảng cáo**
thay vì Chính. Điều đó KHÔNG ảnh hưởng tới MeoArc — thẻ phân loại chỉ là nhãn phụ,
thư vẫn mang nhãn INBOX nên vẫn về đủ. Chỉ khi mở Gmail bằng mắt mới thấy nó nằm tab
khác.

TÊN NGƯỜI GỬI: mỗi thư đặt tên hiển thị riêng (xem THU_DEMO). ĐỊA CHỈ thì vẫn là tài
khoản đang đăng nhập — Gmail từ chối gửi hộ địa chỉ lạ. Nên trong Gmail bạn sẽ thấy
"Giáo vụ HCMUS" nhưng địa chỉ thật là email của bạn. Đủ cho demo, và cũng đúng: đây
là thư demo, không phải giả mạo trường.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # để import bo_quay_demo

from app.core.db import SessionLocal              # noqa: E402
from app.models.user import User                  # noqa: E402
from app.services import gmail_send               # noqa: E402
from app.services.sync_service import _token_for_user  # noqa: E402

# Nội dung giữ ĐÚNG như bộ demo của frontend, để hai bên nói cùng một chuyện.
# Bốn tình huống bộ trích cam kết phải xử lý đúng + hai thư bẫy không phải cam kết.
#
# Phần tử đầu là TÊN HIỂN THỊ người gửi. Không có nó thì Gmail điền tên chủ tài khoản
# vào cả 8 thư, và màn Lịch trình hiện tám cái thẻ cùng đề tên bạn — lúc demo trông
# như hỏng. Địa chỉ thì vẫn là tài khoản đang đăng nhập (Gmail không cho gửi hộ địa
# chỉ lạ); chỉ tên hiển thị là đổi được.
THU_DEMO: list[tuple[str, str, str]] = [
    (
        "Phòng Đào tạo HCMUS",
        "Đăng ký học phần HK1 2026-2027",
        "Chào các em,\n\n"
        "Sinh viên hoàn tất đăng ký học phần học kỳ 1 năm học 2026-2027 trên cổng "
        "thông tin trước 17:00 ngày 5/9. Sau thời hạn này hệ thống sẽ khoá, các "
        "trường hợp bổ sung phải làm đơn.\n\n"
        "Lưu ý kiểm tra kỹ số tín chỉ tối thiểu và các môn tiên quyết.\n\n"
        "Phòng Đào tạo",
    ),
    (
        "GVHD Nguyễn Văn Sơn",
        "Lịch bảo vệ đồ án Nhập môn CNPM",
        "Chào em,\n\n"
        "Nhóm 7 chuẩn bị slide và bản demo chạy được. Buổi bảo vệ diễn ra lúc 8h "
        "thứ Ba tuần sau tại phòng I.53.\n\n"
        "Mỗi nhóm trình bày 15 phút, hỏi đáp 10 phút. Nhớ gửi slide trước một ngày.\n\n"
        "GVHD",
    ),
    (
        "Ban tổ chức Hackathon",
        "Xác nhận tham dự vòng chung kết 12/09",
        "Xin chào đội MeoArc,\n\n"
        "Đội của bạn đã lọt vào vòng chung kết ngày 12/09 tại Đà Nẵng. Vui lòng xác "
        "nhận tham dự trong vòng 3 ngày làm việc kể từ khi nhận thư này.\n\n"
        "Ban tổ chức hỗ trợ chi phí đi lại cho tối đa 3 thành viên mỗi đội.",
    ),
    (
        "Giáo vụ HCMUS",
        "Nộp báo cáo Testing (PA3) — Nhóm 7",
        "Chào các em,\n\n"
        "Các nhóm nộp báo cáo Testing (PA3) đầy đủ lên Moodle trước 23:59 ngày 18/9, "
        "kèm minh chứng chạy test và bảng phân công công việc của từng thành viên.\n\n"
        "Báo cáo cần có đủ: kế hoạch kiểm thử, đặc tả ca kiểm thử cho toàn bộ use case "
        "đã đăng ký, kết quả chạy thực tế, phần đánh giá độ phủ, và phụ lục minh chứng.\n\n"
        "Đây là hạng mục chiếm trọng số lớn nhất của học phần. Các em bố trí thời gian "
        "sớm, đừng để dồn vào tuần cuối.\n\n"
        "Giáo vụ",
    ),
    (
        "Trần Minh Khoa",
        "Re: Chia việc phần backend tuần này",
        "Ok bạn,\n\n"
        "Mình nhận phần MCP server. Bạn gửi lại đặc tả tool trước thứ Năm để mình còn "
        "kịp làm.\n\n"
        "Phần confirm-gate mình thấy nên gom về một chỗ, tránh mỗi tool tự làm một kiểu.",
    ),
    (
        "Phòng CTSV",
        "Đóng học phí học kỳ 1",
        "Thông báo,\n\n"
        "Sinh viên hoàn tất đóng học phí học kỳ 1 trước ngày 25/9 qua cổng thanh toán "
        "của trường.\n\n"
        "Quá hạn sẽ bị khoá kết quả học tập cho tới khi hoàn tất.\n\n"
        "Phòng CTSV",
    ),
    # ── HAI THƯ BẪY: có ngày tháng nhưng KHÔNG phải cam kết ──
    # Chúng ở đây để chứng minh bộ trích không nhận bừa mọi thứ có con số — đó là
    # câu hỏi khó nhất khi trình bày.
    (
        "Shopee",
        "Sale 9.9 — giảm đến 50% ngày 9/9",
        "Đừng bỏ lỡ ngày hội mua sắm 9/9 với hàng ngàn ưu đãi giảm đến 50% toàn sàn.",
    ),
    (
        "Lê Thu Hà",
        "Sinh nhật mình 15/9 nhé",
        "Mình tổ chức nhỏ ở nhà, hẹn gặp lại mọi người ngày 15/9 nha. Không cần mang gì đâu.",
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
# BỘ THƯ DÀY (--bo-day) — để xem màn Lịch trình DƯỚI TẢI THẬT trên hộp thư THẬT
#
# Bộ 8 thư ở trên rải đều nên ba cơ chế xử lý quá tải (xếp làn, chip "+N", bảng
# ngày) gần như không bao giờ chạy. Bộ này dồn cục: vài ngày 8–10 việc, hai đợt
# kéo dài nhiều tuần chồng nhau.
#
# GIỮ ĐỒNG BỘ với `src/frontend/src/data/demo-qua-tai.ts`. Hai nơi vì hai đích
# khác nhau — bên kia là dữ liệu giả cho chế độ mock, bên này là thư THẬT gửi vào
# hộp thư thật. Sửa một bên mà quên bên kia thì demo mock và demo thật lệch nhau,
# và đó là kiểu lệch chỉ lộ ra đúng lúc đang trình bày.
# ══════════════════════════════════════════════════════════════════════════════

# [ngày/tháng, giờ hạn, người gửi, động từ + việc]
_VIEC_DAY: list[tuple[str, str, str, str]] = [
    # ── Tuần 7–13/9 ──
    ("7/9", "17:00", "Giáo vụ HCMUS", "nộp danh sách nhóm đồ án"),
    ("7/9", "23:59", "Nguyễn Hoàng Anh", "gửi bản vẽ use case cho nhóm"),
    ("8/9", "09:00", "GVHD Nguyễn Văn Sơn", "trình bày tiến độ tuần 2"),
    ("8/9", "17:00", "Phòng Đào tạo HCMUS", "xác nhận lịch thi giữa kỳ"),
    ("8/9", "23:59", "Trần Minh Khoa", "gửi đặc tả API cho backend"),
    ("8/9", "23:59", "CLB Học thuật", "đăng ký suất trình bày seminar"),
    ("9/9", "12:00", "Thư viện HCMUS", "gia hạn sách mượn"),
    ("9/9", "17:00", "Lê Thu Hà", "phản hồi bản thiết kế giao diện"),
    ("9/9", "23:59", "Giáo vụ HCMUS", "nộp biên bản họp nhóm tuần 2"),
    ("11/9", "08:00", "Phòng CTSV", "nộp đơn xin miễn giảm học phí"),
    ("11/9", "17:00", "Nguyễn Hoàng Anh", "gửi số liệu đo hiệu năng"),
    ("11/9", "23:59", "Ban tổ chức Hackathon", "xác nhận danh sách thành viên dự thi"),
    ("11/9", "23:59", "Trần Minh Khoa", "trả lời góp ý pull request #48"),
    ("11/9", "23:59", "Đoàn khoa CNTT", "đăng ký tham gia ngày hội việc làm"),
    # ── Tuần 14–20/9: ĐỈNH ĐIỂM ──
    ("14/9", "09:00", "GVHD Nguyễn Văn Sơn", "trình bày tiến độ tuần 3"),
    ("14/9", "17:00", "Giáo vụ HCMUS", "nộp phiếu tự đánh giá giữa kỳ"),
    ("14/9", "23:59", "Lê Thu Hà", "gửi bản dịch phần tài liệu tiếng Anh"),
    ("14/9", "23:59", "Phòng Đào tạo HCMUS", "đăng ký môn học bổ sung"),
    ("14/9", "23:59", "Thư viện HCMUS", "trả sách quá hạn đợt hai"),
    ("15/9", "08:30", "Phòng Quan hệ Doanh nghiệp", "nộp nhật ký thực tập tuần 1"),
    ("15/9", "10:00", "Nguyễn Hoàng Anh", "trình bày phần kiến trúc cho nhóm"),
    ("15/9", "15:00", "Trần Minh Khoa", "gửi kết quả chạy kiểm thử tích hợp"),
    ("15/9", "17:00", "Giáo vụ HCMUS", "nộp bản mô tả ca kiểm thử"),
    ("15/9", "17:00", "Phòng CTSV", "xác nhận thông tin bảo hiểm y tế"),
    ("15/9", "23:59", "CLB Học thuật", "gửi slide buổi chia sẻ kỹ thuật"),
    ("15/9", "23:59", "Lê Thu Hà", "phản hồi bản nháp phần mở đầu"),
    ("15/9", "23:59", "Đoàn khoa CNTT", "đăng ký ca trực hỗ trợ tân sinh viên"),
    ("17/9", "09:00", "GVHD Nguyễn Văn Sơn", "bảo vệ tiến độ giữa kỳ"),
    ("17/9", "14:00", "Ban tổ chức Hackathon", "trình bày sản phẩm vòng loại"),
    ("17/9", "17:00", "Nguyễn Hoàng Anh", "gửi bản cập nhật sơ đồ lớp"),
    ("17/9", "23:59", "Trần Minh Khoa", "hoàn thành phần tài liệu triển khai"),
    ("17/9", "23:59", "Phòng Đào tạo HCMUS", "xác nhận đăng ký thi lại"),
    ("17/9", "23:59", "Thư viện HCMUS", "thanh toán phí phạt quá hạn"),
    ("18/9", "08:00", "Phòng Quan hệ Doanh nghiệp", "nộp nhật ký thực tập tuần 2"),
    ("18/9", "10:00", "Giáo vụ HCMUS", "nộp phụ lục minh chứng kiểm thử"),
    ("18/9", "15:00", "Lê Thu Hà", "gửi ảnh chụp giao diện đã dựng"),
    ("18/9", "17:00", "Nguyễn Hoàng Anh", "phản hồi bảng phân công công việc"),
    ("18/9", "23:59", "Trần Minh Khoa", "gửi bản ghi buổi họp nhóm"),
    ("18/9", "23:59", "CLB Học thuật", "xác nhận tham dự buổi tổng kết"),
    ("18/9", "23:59", "Phòng CTSV", "nộp đơn xin xác nhận thực tập"),
    # ── Tuần 21–27/9 ──
    ("22/9", "09:00", "GVHD Nguyễn Văn Sơn", "trình bày tiến độ tuần 4"),
    ("22/9", "17:00", "Giáo vụ HCMUS", "nộp bản chỉnh sửa theo góp ý"),
    ("22/9", "23:59", "Nguyễn Hoàng Anh", "gửi phần đánh giá độ phủ kiểm thử"),
    ("23/9", "17:00", "Phòng Quan hệ Doanh nghiệp", "nộp nhật ký thực tập tuần 3"),
    ("23/9", "23:59", "Trần Minh Khoa", "hoàn tất phần hướng dẫn cài đặt"),
    ("24/9", "10:00", "Ban tổ chức Hackathon", "xác nhận tham dự lễ trao giải"),
    ("24/9", "17:00", "Lê Thu Hà", "gửi bản in màu để nộp cứng"),
    ("24/9", "23:59", "Phòng Đào tạo HCMUS", "đăng ký học phần học kỳ 2"),
]

# Đợt kéo dài nhiều tuần — dạng "từ … đến …", tức khoảng NÓI THẲNG.
# [người gửi, tên đợt, từ, đến]
_DOT_DAY: list[tuple[str, str, str, str]] = [
    ("Phòng Khảo thí", "Đợt kiểm tra giữa kỳ toàn khoa", "14/9", "19/9"),
    ("Nhóm 7 — Anh Quân", "Giai đoạn hoàn thiện tài liệu PA3", "9/9", "22/9"),
    ("Phòng Quan hệ Doanh nghiệp", "Đợt thực tập doanh nghiệp", "7/9", "25/9"),
]


def _canh_bao_bo_day(tong: int, nguoi_nhan: str) -> None:
    """Nói THẲNG cái giá phải trả, trước khi người dùng bấm.

    Gửi thư là việc không hoàn tác được, và ~50 thư thì không phải "một chút lộn
    xộn" mà là hộp thư đổi hẳn diện mạo. Người bấm phải biết trước cả hậu quả lẫn
    cách dọn — chôn thông tin đó trong tài liệu thì lúc cần không ai tìm ra."""
    print("┌─ CẢNH BÁO ─────────────────────────────────────────────────────────")
    print(f"│ Kịch bản sẽ gửi {tong} thư vào {nguoi_nhan}.")
    print("│ KHÔNG HOÀN TÁC ĐƯỢC. Thư tự gửi nằm ở CẢ Hộp thư đến LẪN Đã gửi,")
    print("│ nên hộp thư sẽ có khoảng gấp đôi số đó cần dọn.")
    print("│")
    print("│ Dọn lại: mở Gmail, tìm  from:me to:me newer_than:1d  rồi chọn tất cả.")
    print("│ Nên gửi TRƯỚC buổi bảo vệ ít nhất một hôm để còn kịp kiểm tra.")
    print("└────────────────────────────────────────────────────────────────────")


# ══════════════════════════════════════════════════════════════════════════════
# BỘ THEO KỊCH BẢN (--kich-ban) — mỗi thư phục vụ MỘT câu hỏi cụ thể khi demo
#
# Bộ dày ở trên chỉ sinh ra một KIỂU thư: "hạn chót". Nó làm màn Lịch trình quá tải
# đúng như mong muốn, nhưng nhiều câu hỏi trong kịch bản kiểm thử lại không có gì để
# bấu víu — hỏi "thư nào đang chờ tôi phản hồi" trên một hộp thư toàn thông báo thì
# agent trả lời đúng mà nhìn vẫn như hỏng.
#
# Nên bộ này cố ý ĐA DẠNG chứ không nhiều: quảng cáo để thử xoá hàng loạt, thư hỏi
# thẳng chờ trả lời, một luồng họp để dựng brief, một chuyến công tác để gợi ý đi lại.
# ══════════════════════════════════════════════════════════════════════════════
_THU_KICH_BAN: list[tuple[str, str, str]] = [
    # ── Cho A1 "xoá hết thư quảng cáo": cần ĐỦ NHIỀU để con số trên thẻ duyệt gây ấn
    #    tượng, và cần RÕ RÀNG là quảng cáo để không ai tranh cãi agent xoá nhầm.
    ("Tiki", "Siêu sale tháng 9 — mã giảm 200K",
     "Nhập mã THANG9 để được giảm ngay 200.000đ cho đơn từ 500K. Áp dụng toàn sàn."),
    ("Lazada", "Flash Sale 12h hôm nay",
     "Săn deal đồng giá 9K khung giờ 12h. Số lượng có hạn, nhanh tay bạn nhé!"),
    ("Grab", "Ưu đãi 50% cho 5 chuyến tiếp theo",
     "Tặng bạn 5 mã giảm 50% cho chuyến GrabBike. Mã tự động áp dụng khi đặt xe."),
    ("Highlands Coffee", "Mua 1 tặng 1 cuối tuần",
     "Cuối tuần này mua 1 tặng 1 tất cả đồ uống size L tại toàn bộ cửa hàng."),
    ("Shopee", "Voucher freeship toàn sàn",
     "Nhận ngay bộ voucher freeship 0đ, áp dụng cho mọi đơn hàng trong tuần này."),
    ("Zalopay", "Hoàn tiền 30% khi thanh toán hoá đơn",
     "Thanh toán hoá đơn điện nước qua ZaloPay để nhận hoàn tiền lên tới 30%."),

    # ── Cho B1 "thư nào đang chờ tôi phản hồi": phải hỏi THẲNG và chờ MÌNH trả lời.
    #    Đây là thứ bộ dày không có — thư ở đó chỉ thông báo hạn, không ai đợi mình.
    ("Phạm Thu Trang", "Bạn xem giúp mình phần use case với",
     "Mình vừa đẩy bản vẽ use case lên nhánh của mình.\n\n"
     "Bạn xem qua rồi cho mình biết có cần tách UC007 ra không nhé? Mình đang đợi ý "
     "kiến của bạn mới dám sửa tiếp."),
    ("Trần Minh Khoa", "Chốt giúp mình định dạng response của tool",
     "Mình đang làm MCP server, kẹt ở chỗ định dạng trả về.\n\n"
     "Bạn trả lời giúp mình là dùng snake_case hay camelCase để mình còn viết tiếp. "
     "Mình dừng ở đây chờ bạn."),
    ("GVHD Nguyễn Văn Sơn", "Em xác nhận lại giúp thầy",
     "Thầy cần biết nhóm em trình bày mấy người để thầy xếp lịch phòng.\n\n"
     "Em phản hồi lại thầy trong hôm nay nhé."),
    ("Lê Thu Hà", "Nhóm mình họp thứ mấy?",
     "Mọi người rảnh thứ Năm hay thứ Sáu? Bạn chốt giúp mình một ngày để mình đặt phòng."),

    # ── Cho B6 "meeting brief": một LUỒNG có việc cần làm, người phụ trách, và hạn.
    ("Nguyễn Hoàng Anh", "Biên bản họp nhóm 7 — chuẩn bị bảo vệ",
     "Tóm tắt buổi họp chiều nay:\n\n"
     "1. Quân hoàn thiện màn Lịch trình và khung tra cứu đi lại — xong trước thứ Tư.\n"
     "2. Khoa viết lại phần MCP server cho khớp đặc tả — xong trước thứ Năm.\n"
     "3. Trang chuẩn bị slide phần an toàn (cổng xác nhận, cổng tiền) — xong thứ Sáu.\n"
     "4. Cả nhóm chạy thử 15 phút vào sáng thứ Bảy.\n\n"
     "Ai không kịp thì báo sớm để nhóm chia lại việc."),
    ("Trần Minh Khoa", "Re: Biên bản họp nhóm 7 — chuẩn bị bảo vệ",
     "Mình nhận mục 2.\n\n"
     "Nhưng phần đặc tả tool mình vẫn chưa nhận được. Ai gửi giúp mình trước thứ Ba "
     "thì mình mới kịp thứ Năm."),

    # ── Cho "đề xuất đi lại": phải có ĐỊA ĐIỂM KHÁC thành phố và mốc thời gian rõ.
    ("Ban tổ chức Hackathon", "Lịch chi tiết vòng chung kết tại Đà Nẵng",
     "Chào đội MeoArc,\n\n"
     "Vòng chung kết diễn ra ngày 12/9 tại Đà Nẵng, bắt đầu lúc 8h00 sáng.\n\n"
     "Các đội có mặt trước 7h30 để làm thủ tục. Ban tổ chức hỗ trợ chi phí đi lại "
     "cho tối đa 3 thành viên, các bạn tự đặt vé rồi gửi hoá đơn về sau."),
    ("Phòng Hợp tác Quốc tế", "Hội thảo sinh viên tại Hà Nội 20/9",
     "Trường cử sinh viên tham dự hội thảo tại Hà Nội ngày 20/9.\n\n"
     "Bạn đăng ký trước ngày 14/9 nếu muốn tham gia. Trường hỗ trợ một phần chi phí."),

    # ── Cho B4 "triage": ba mức độ khác nhau để nhóm ưu tiên nhìn ra sự khác biệt.
    ("Ngân hàng ACB", "Cảnh báo: đăng nhập từ thiết bị lạ",
     "Tài khoản của bạn vừa được đăng nhập từ một thiết bị mới.\n\n"
     "Nếu không phải bạn, hãy đổi mật khẩu NGAY."),
    ("Phòng Đào tạo HCMUS", "GẤP: bổ sung hồ sơ trước 16h hôm nay",
     "Hồ sơ của em còn thiếu bản sao bằng tốt nghiệp THPT.\n\n"
     "Em bổ sung trước 16h hôm nay, nếu không sẽ bị loại khỏi danh sách xét."),
    ("GitHub", "[MeoArc] CI passed on integration",
     "All checks have passed for commit on branch integration. No action needed."),
    ("Moodle HCMUS", "Điểm giữa kỳ đã được cập nhật",
     "Điểm giữa kỳ môn Nhập môn Công nghệ Phần mềm đã có trên hệ thống."),

    # ── Thư BẪY thứ ba: có động từ cam kết nhưng KHÔNG có mốc thời gian.
    #    Bộ trích phải bỏ qua. Đây là nửa còn lại của luật "cần CẢ hai".
    ("Nguyễn Hoàng Anh", "Nhớ gửi mình file nhé",
     "Khi nào rảnh bạn gửi mình file thiết kế nha, không gấp đâu."),

    # ══════════════════════════════════════════════════════════════════════════
    # PHỦ ĐỦ 7 NHÓM NHÃN + các dạng thư mà bộ cũ không có
    #
    # Nut "Phan loai tu dong" chi doi 7 nhom. Bo cu gan nhu toan Hoc tap/Cong viec,
    # nen bam vao thi widget hien 2 nhom va nhin nhu no chi biet co 2 — khong phan
    # biet duoc "engine chi co 2 nhom" voi "hop thu chi co 2 loai thu".
    # Tuong tu, Digest/Triage/Meeting Brief can DU DANG do uu tien va DU luong thu
    # moi cho ra thu dang xem.
    # ══════════════════════════════════════════════════════════════════════════

    # ── TÀI CHÍNH ──
    ("Vietcombank", "Biến động số dư tài khoản",
     "Tài khoản 0071xxxx1234 vừa ghi nợ 2.450.000 VND lúc 14:32 ngày hôm nay.\n\n"
     "Nội dung: THANH TOAN HOC PHI HK1. Số dư khả dụng: 3.120.000 VND."),
    ("Viettel", "Hoá đơn cước tháng 8/2026",
     "Cước dịch vụ tháng 8 của thuê bao 09xxxxxx89 là 187.000đ.\n\n"
     "Hạn thanh toán: ngày 10/9. Quá hạn dịch vụ sẽ tạm ngưng một chiều."),
    ("EVN HCMC", "Thông báo tiền điện kỳ 8/2026",
     "Chỉ số cũ 4521, chỉ số mới 4698, tiêu thụ 177 kWh.\n\n"
     "Số tiền: 486.300đ. Vui lòng thanh toán trước ngày 12/9."),

    # ── MẠNG XÃ HỘI ──
    ("Facebook", "Bạn có 12 thông báo mới",
     "Nguyễn Hoàng Anh và 5 người khác đã bình luận về bài viết của bạn."),
    ("LinkedIn", "5 việc làm mới phù hợp với bạn",
     "Fresher Backend Developer tại FPT Software và 4 vị trí khác đang tuyển."),
    ("YouTube", "Kênh bạn theo dõi vừa đăng video mới",
     "Kênh 'Học lập trình' vừa đăng: 'Xây dựng AI Agent với LangGraph'."),

    # ── CÔNG VIỆC / TUYỂN DỤNG ──
    ("FPT Software", "Thư mời phỏng vấn vị trí Fresher Backend",
     "Chào bạn,\n\n"
     "Chúng tôi mời bạn tham dự phỏng vấn vòng 1 vào 14h00 ngày 11/9 tại toà nhà "
     "FPT, Quận 9.\n\n"
     "Bạn xác nhận tham dự trước ngày 9/9 để chúng tôi sắp lịch. Vui lòng mang theo "
     "CV bản in và giấy tờ tuỳ thân."),
    ("VNG Corporation", "Kết quả vòng test online",
     "Bạn đã vượt qua vòng test online cho vị trí Backend Intern.\n\n"
     "Vui lòng hoàn tất bài tập về nhà và nộp trước 23:59 ngày 14/9."),

    # ── TIẾNG ANH — thử luật "tìm cả từ khoá tiếng Anh tương đương" ──
    ("GitHub", "[Security] New sign-in to your account",
     "We noticed a new sign-in to your GitHub account from a device in Ho Chi Minh City.\n\n"
     "If this was you, no action is needed. If not, secure your account immediately."),
    ("Google Cloud", "Your free trial ends in 7 days",
     "Your Google Cloud free trial will expire on September 13, 2026.\n\n"
     "Upgrade to a paid account to keep your resources running."),
    ("Coursera", "Assignment deadline reminder",
     "Your assignment for 'Machine Learning Specialization' is due on September 15, 2026.\n\n"
     "Submit before the deadline to receive full credit."),
    ("Overleaf", "Your collaborator left a comment",
     "Tran Minh Khoa commented on your document 'MeoArc-SRS.tex'.\n\n"
     "Please review and reply when you get a chance."),

    # ── LUỒNG THƯ 3 TIN — cho Meeting Brief có thứ để tóm ──
    ("GVHD Nguyễn Văn Sơn", "Họp review tiến độ nhóm 7 — thứ Năm 10/9",
     "Chào các em,\n\n"
     "Thầy hẹn nhóm 7 họp review tiến độ lúc 15h00 thứ Năm 10/9 tại phòng I.42.\n\n"
     "Các em chuẩn bị: bản demo chạy được, danh sách use case đã hoàn thành, và "
     "phần nào còn dang dở. Thầy sẽ hỏi từng người về phần mình phụ trách."),
    ("Nguyễn Hoàng Anh", "Re: Họp review tiến độ nhóm 7 — thứ Năm 10/9",
     "Dạ em xác nhận có mặt.\n\n"
     "Em phụ trách phần tài liệu SRS, hiện đã xong chương 1-3, còn chương 4 em nộp "
     "trước buổi họp."),
    ("Trần Minh Khoa", "Re: Họp review tiến độ nhóm 7 — thứ Năm 10/9",
     "Thầy ơi em xin phép vào trễ 15 phút vì trùng lịch thi.\n\n"
     "Phần MCP server em đã chạy được, em sẽ demo ngay khi tới."),

    # ── ƯU TIÊN THẤP — Triage cần có nhóm "chỉ để biết" mới phân biệt được ──
    ("Thư viện HCMUS", "Sách bạn mượn sắp đến hạn trả",
     "Cuốn 'Software Engineering (Sommerville, 9th ed.)' đến hạn trả ngày 20/9."),
    ("Moodle HCMUS", "Giảng viên vừa đăng tài liệu mới",
     "Môn Nhập môn Công nghệ Phần mềm vừa có tài liệu mới: 'Slide chương 8 - Testing'."),
    ("HCMUS Newsletter", "Bản tin tháng 9 — hoạt động sinh viên",
     "Điểm tin tháng này: hội thao khoa, cuộc thi lập trình, và lịch nghỉ lễ 2/9."),
    ("Spotify", "Playlist mới dành cho bạn",
     "Discover Weekly của bạn vừa được cập nhật với 30 bài hát mới."),

    # ── DẠNG KHÓ: nhiều mốc thời gian trong MỘT thư ──
    ("Phòng Đào tạo HCMUS", "Lịch thi giữa kỳ học kỳ 1",
     "Thông báo lịch thi giữa kỳ:\n\n"
     "- Nhập môn CNPM: 8h00 ngày 22/9, phòng F.201\n"
     "- Cơ sở dữ liệu: 13h30 ngày 24/9, phòng F.203\n"
     "- Mạng máy tính: 8h00 ngày 26/9, phòng E.101\n\n"
     "Sinh viên có mặt trước 15 phút, mang theo thẻ sinh viên."),

    # ── DẠNG KHÓ: hạn phụ thuộc điều kiện, KHÔNG phải mốc cố định ──
    ("GVHD Nguyễn Văn Sơn", "Về phần đề cương của nhóm em",
     "Em chỉnh lại phần phạm vi rồi nộp sau khi thầy duyệt đề cương nhé.\n\n"
     "Thầy sẽ xem trong tuần này."),

    # ── DẠNG KHÓ: thư dài, nhiều việc cho nhiều người ──
    ("Ban tổ chức Hackathon", "Hướng dẫn chuẩn bị vòng chung kết",
     "Gửi các đội,\n\n"
     "Để vòng chung kết ngày 12/9 diễn ra suôn sẻ, các đội hoàn tất những việc sau:\n\n"
     "1. Gửi slide trình bày (tối đa 10 trang) trước 23:59 ngày 10/9.\n"
     "2. Nộp mã nguồn lên repo chung trước 12h00 ngày 11/9.\n"
     "3. Cử một đại diện tham dự buổi kỹ thuật lúc 16h00 ngày 11/9.\n"
     "4. Chuẩn bị bản demo chạy offline phòng khi mạng hội trường yếu.\n\n"
     "Đội nào không nộp đúng hạn mục 1 và 2 sẽ bị trừ điểm trình bày."),

    # ── SPAM-LIKE nhưng KHÔNG phải spam: dễ bị phân loại nhầm ──
    ("Học bổng VEF", "Thông báo học bổng toàn phần 2027",
     "Chương trình học bổng toàn phần bậc thạc sĩ tại Hoa Kỳ đang nhận hồ sơ.\n\n"
     "Hạn nộp: 30/9. Yêu cầu GPA từ 3.2 và IELTS 6.5 trở lên."),

    # ── THƯ CÓ NGƯỜI KHÁC ĐANG CHỜ MÌNH, hạn gấp trong ngày ──
    ("Phạm Thu Trang", "Gấp: mình cần link repo trước 5h chiều nay",
     "Bạn ơi mình đang làm slide, cần link repo và ảnh chụp màn hình phần lịch trình.\n\n"
     "Bạn gửi giúp mình trước 17h hôm nay nhé, tối mình phải gửi cho thầy rồi."),
]


# ══════════════════════════════════════════════════════════════════════════════
# BỘ KHÓ (--kich-ban, nối tiếp bộ trên) — dựng để AGENT PHẢI SUY LUẬN
#
# Bộ trước đã đa dạng về THỂ LOẠI, nhưng mỗi thư vẫn tự đứng một mình: đọc một lá là
# biết ngay phải làm gì. Trình bày bằng bộ đó thì trợ lý trông như một bộ lọc từ khoá.
#
# Bộ này cố ý làm khó theo sáu hướng, mỗi hướng là một câu hỏi mà tìm kiếm thường
# KHÔNG trả lời được:
#   1. Thư SAU phủ định thư TRƯỚC   → phải biết lấy cái mới nhất
#   2. Thông tin nằm ở HAI lá khác nhau → phải nối lại mới ra kết luận
#   3. Việc CHÔN GIỮA một thư dài   → phải đọc hết chứ không lướt tiêu đề
#   4. Mốc thời gian NÓI MƠ HỒ      → phải quy ra ngày thật
#   5. HAI NGƯỜI TRÙNG TÊN          → phải phân biệt bằng ngữ cảnh
#   6. Thư TRÔNG NHƯ việc nhưng KHÔNG phải, và ngược lại
# ══════════════════════════════════════════════════════════════════════════════
_THU_KHO: list[tuple[str, str, str]] = [
    # ── (1) CHUỖI PHỦ ĐỊNH: ba lá, chỉ lá cuối còn đúng ──
    ("Phòng Đào tạo HCMUS", "Lịch bảo vệ đồ án — dự kiến 9h00 thứ Ba 15/9",
     "Thông báo lịch bảo vệ đồ án Nhập môn CNPM:\n\n"
     "Thời gian: 9h00 thứ Ba ngày 15/9\nĐịa điểm: phòng I.53\n\n"
     "Các nhóm có mặt trước 15 phút."),
    ("Phòng Đào tạo HCMUS", "Re: Lịch bảo vệ đồ án — DỜI sang chiều 15/9",
     "Do phòng I.53 trùng lịch thi, buổi bảo vệ DỜI sang 14h00 cùng ngày 15/9.\n\n"
     "Địa điểm giữ nguyên. Xin lỗi các em vì thay đổi gấp."),
    ("Phòng Đào tạo HCMUS", "Re: Re: Lịch bảo vệ đồ án — CHỐT 15h30 thứ Tư 16/9",
     "Thông báo CUỐI CÙNG, thay thế toàn bộ các thông báo trước:\n\n"
     "Buổi bảo vệ diễn ra 15h30 thứ Tư ngày 16/9 tại phòng E.202.\n\n"
     "Các em bỏ qua hai email trước. Không còn thay đổi nào nữa."),

    # ── (2) NỐI HAI LÁ: hoá đơn + xác nhận đã trả ──
    ("Phòng Kế hoạch Tài chính", "Thông báo học phí học kỳ 1 — 8.500.000đ",
     "Học phí học kỳ 1 năm học 2026-2027 của sinh viên là 8.500.000đ.\n\n"
     "Hạn thanh toán: trước 17h00 ngày 25/9. Quá hạn sẽ bị khoá kết quả học tập."),
    ("Vietcombank", "Xác nhận giao dịch thành công",
     "Giao dịch chuyển khoản đã hoàn tất.\n\n"
     "Số tiền: 8.500.000 VND\nNội dung: HOC PHI HK1 2026 2027\n"
     "Đơn vị thụ hưởng: TRUONG DH KHOA HOC TU NHIEN\nThời gian: 14:22 ngày 18/9"),

    # ── (2b) NỐI HAI LÁ kiểu khác: mời xác nhận + đã ghi nhận ──
    ("CLB Học thuật", "Mời tham gia buổi seminar 21/9",
     "Mời bạn tham dự seminar về AI trong giáo dục lúc 18h00 ngày 21/9 tại hội trường C.\n\n"
     "Bạn xác nhận tham dự trước ngày 19/9 để ban tổ chức chuẩn bị chỗ ngồi."),
    ("CLB Học thuật", "Re: Mời tham gia buổi seminar 21/9",
     "Cảm ơn bạn đã xác nhận. Ban tổ chức đã ghi nhận bạn vào danh sách tham dự.\n\n"
     "Không cần làm gì thêm, hẹn gặp bạn ngày 21/9."),

    # ── (3) VIỆC CHÔN GIỮA THƯ DÀI ──
    ("Ban Truyền thông HCMUS", "Bản tin sinh viên tháng 9 — nhiều hoạt động thú vị",
     "Chào các bạn sinh viên,\n\n"
     "Tháng 9 này trường có rất nhiều hoạt động đáng chú ý.\n\n"
     "Đầu tiên là Hội thao sinh viên, khai mạc ngày 20/9 tại sân vận động trường. "
     "Các môn thi đấu gồm bóng đá, bóng chuyền, cầu lông và điền kinh. Năm nay ban tổ "
     "chức mở rộng thêm hạng mục cờ vua.\n\n"
     "Tiếp theo, Câu lạc bộ Tiếng Anh khai giảng lớp giao tiếp miễn phí vào các tối "
     "thứ Ba và thứ Năm hàng tuần, bắt đầu từ tuần sau tại phòng B.12.\n\n"
     "Thư viện trường vừa bổ sung hơn 300 đầu sách chuyên ngành Công nghệ Thông tin, "
     "các bạn có thể tra cứu trên cổng thư viện điện tử.\n\n"
     "LƯU Ý QUAN TRỌNG: sinh viên khoá 2024 phải hoàn tất khảo sát đánh giá môn học "
     "trên cổng thông tin TRƯỚC NGÀY 23/9. Sinh viên không hoàn tất sẽ không xem được "
     "điểm cuối kỳ.\n\n"
     "Cuối cùng, chúc các bạn một tháng học tập hiệu quả.\n\nBan Truyền thông"),

    # ── (4) MỐC THỜI GIAN MƠ HỒ — phải quy ra ngày thật ──
    ("GVHD Nguyễn Văn Sơn", "Về bản chỉnh sửa chương 4",
     "Em xem lại phần đặc tả ca kiểm thử ở chương 4 nhé.\n\n"
     "Gửi lại thầy vào ĐẦU TUẦN SAU, thầy sẽ đọc trong tuần đó."),
    ("Trần Minh Khoa", "Phần MCP server",
     "Mình cần đặc tả tool của bạn để làm tiếp.\n\n"
     "Bạn gửi trong VÀI NGÀY TỚI nhé, chậm nhất là CUỐI TUẦN này."),
    ("Phòng CTSV", "Đăng ký học bổng khuyến khích học tập",
     "Sinh viên nộp hồ sơ xin học bổng TRƯỚC KHI KẾT THÚC THÁNG NÀY.\n\n"
     "Hồ sơ gồm: đơn xin học bổng, bảng điểm, và giấy xác nhận hoàn cảnh (nếu có)."),

    # ── (5) HAI NGƯỜI TRÙNG TÊN — phân biệt bằng ngữ cảnh ──
    ("Nguyễn Văn Sơn (GVHD)", "Nhắc nộp báo cáo tiến độ tuần 3",
     "Nhóm 7 nộp báo cáo tiến độ tuần 3 trước 17h thứ Sáu 18/9.\n\n"
     "Thầy cần thấy phần demo chạy được, không chỉ slide."),
    ("Nguyễn Văn Sơn (lớp trưởng)", "Thu tiền quỹ lớp học kỳ này",
     "Các bạn chuyển 100k tiền quỹ lớp cho mình trước thứ Sáu 18/9 nhé.\n\n"
     "Quỹ dùng cho hoạt động lớp và quà cho thầy cô dịp 20/11."),

    # ── (6) TRÔNG NHƯ VIỆC nhưng KHÔNG phải ──
    ("Booking.com", "Xác nhận đặt phòng của bạn — hạn huỷ miễn phí 20/9",
     "Đây là email quảng cáo. Bạn CHƯA đặt phòng nào cả.\n\n"
     "Nếu bạn đặt phòng trong tháng này, bạn sẽ được huỷ miễn phí đến ngày 20/9. "
     "Ưu đãi áp dụng cho hơn 1000 khách sạn tại Việt Nam."),
    ("LinkedIn", "Hạn chót ứng tuyển: 3 vị trí phù hợp đóng đơn ngày 22/9",
     "Ba vị trí phù hợp với hồ sơ của bạn sắp đóng đơn.\n\n"
     "Xem ngay để không bỏ lỡ cơ hội. Bạn chưa ứng tuyển vị trí nào."),

    # ── (6b) TRÔNG KHÔNG PHẢI VIỆC nhưng LẠI LÀ ──
    ("Mẹ", "con nhớ nhé",
     "Con ơi ngày 19/9 là giỗ ông nội, con thu xếp về nhà trước tối 18 nha.\n\n"
     "Mẹ đã nói với cô Ba là con về rồi đó."),
    ("Phạm Thu Trang", "hihi",
     "Ê nhớ mai 8h qua phòng lab phụ mình bê đồ cho buổi demo nha, mình một mình không xuể đâu."),

    # ── CHUỖI ĐI LẠI: đặt vé → đổi giờ → khách sạn ──
    ("Vietnam Airlines", "Xác nhận đặt chỗ — SGN đi HAN ngày 19/9",
     "Mã đặt chỗ: XKPQ7M\n\n"
     "Chuyến VN256, SGN đi HAN, khởi hành 06:00 ngày 19/9, hạ cánh 08:10.\n"
     "Vui lòng có mặt tại sân bay trước 2 tiếng."),
    ("Vietnam Airlines", "THAY ĐỔI LỊCH BAY — mã đặt chỗ XKPQ7M",
     "Chuyến VN256 ngày 19/9 đã đổi giờ khởi hành từ 06:00 sang 09:45.\n\n"
     "Bạn xác nhận chấp nhận thay đổi trước ngày 17/9, nếu không đặt chỗ sẽ tự huỷ."),
    ("Hanoi La Siesta Premium", "Xác nhận đặt phòng 19/9 - 21/9",
     "Cảm ơn bạn đã đặt phòng.\n\n"
     "Nhận phòng: 14h00 ngày 19/9\nTrả phòng: 12h00 ngày 21/9\n"
     "Loại phòng: Deluxe Double. Huỷ miễn phí đến hết ngày 17/9."),

    # ── THƯ TIẾNG ANH CÓ HẠN THẬT ──
    ("IEEE Xplore", "Your submission requires action before Sep 24",
     "Dear author,\n\n"
     "Your manuscript on agent-native email management has been reviewed. "
     "Please submit the revised version before September 24, 2026.\n\n"
     "Reviewers requested clarification on Section 3 (evaluation methodology)."),

    # ── THƯ RẤT DÀI, NHIỀU VIỆC CHO NHIỀU NGƯỜI (thử Meeting Brief) ──
    ("Nguyễn Hoàng Anh", "Tổng hợp việc còn lại trước bảo vệ — đọc kỹ giúp mình",
     "Chào cả nhóm,\n\n"
     "Còn 5 ngày nữa là bảo vệ. Mình tổng hợp lại toàn bộ việc còn dang dở:\n\n"
     "QUÂN — màn Lịch trình đã xong, nhưng phần tra cứu đi lại còn thiếu bộ lọc theo "
     "hãng. Ngoài ra bạn kiểm lại giúp phần đính kèm trong khung chat, hôm qua mình thử "
     "thì nút bấm không phản hồi. Hạn: trước tối thứ Tư.\n\n"
     "KHOA — MCP server chạy được rồi nhưng chưa có tài liệu hướng dẫn kết nối từ "
     "Claude Desktop. Thầy chắc chắn sẽ hỏi phần này. Hạn: trước trưa thứ Năm.\n\n"
     "TRANG — slide phần an toàn (cổng xác nhận, cổng tiền) mới có khung, chưa có nội "
     "dung. Bạn lấy số liệu từ file test của Khoa nhé. Hạn: trước tối thứ Năm.\n\n"
     "MÌNH — hoàn thiện SRS chương 4 và 5, và chuẩn bị phần mở đầu 2 phút.\n\n"
     "Sáng thứ Bảy cả nhóm chạy thử 15 phút, ai không tới được báo trước.\n\n"
     "Ai kẹt phần nào thì nói sớm để chia lại, đừng để tới thứ Sáu mới báo."),

    # ── THƯ NGẮN NHƯNG GẤP TRONG NGÀY ──
    ("Giáo vụ HCMUS", "GẤP: xác nhận danh sách trước 16h chiều nay",
     "Danh sách nhóm 7 còn thiếu MSSV của một thành viên.\n\n"
     "Em bổ sung và phản hồi email này TRƯỚC 16H CHIỀU NAY, sau giờ đó danh sách "
     "sẽ khoá và nhóm em không có tên trong lịch bảo vệ."),

    # ── THƯ HỆ THỐNG, KHÔNG PHẢI VIỆC ──
    ("GitHub", "[MeoArc] 3 workflow runs completed",
     "All checks passed on branch integration. 543 tests passed, 21 skipped."),
    ("Azure", "Your App Service was restarted",
     "meoarc was restarted at 10:49 UTC as part of a deployment. No action required."),
    ("Google", "Cảnh báo bảo mật: thiết bị mới đăng nhập",
     "Tài khoản của bạn vừa được đăng nhập trên một thiết bị Windows mới tại "
     "TP Hồ Chí Minh.\n\nNếu là bạn thì không cần làm gì."),
]


def _dung_bo_day() -> list[tuple[str, str, str]]:
    """Dựng bộ thư dày từ hai bảng gọn ở trên."""
    ra: list[tuple[str, str, str]] = []
    for ngay, gio, nguoi, viec in _VIEC_DAY:
        tieu_de = f"{viec[0].upper()}{viec[1:]} — hạn {ngay}"
        than = (
            "Chào bạn,\n\n"
            f"Bạn {viec} trước {gio} ngày {ngay}.\n\n"
            "Nếu có vướng mắc thì báo lại sớm để còn kịp xử lý trong tuần."
        )
        ra.append((nguoi, tieu_de, than))
    for nguoi, ten, tu, den in _DOT_DAY:
        than = (
            "Thông báo,\n\n"
            f"{ten} diễn ra từ ngày {tu} đến ngày {den}. Bạn hoàn thành các đầu việc "
            "được giao trong suốt đợt và nộp kết quả vào cuối đợt.\n\n"
            "Lịch chi tiết từng ngày xem trong tệp đính kèm của thông báo gốc."
        )
        ra.append((nguoi, f"{ten} ({tu} – {den})", than))
    return ra


def _dia_chi_cong(email: str, hau_to: str) -> str:
    """`quan@gmail.com` + `tai` → `quan+tai@gmail.com`.

    Gmail giao mọi thư gửi tới địa chỉ cộng về CHÍNH hộp thư gốc. Nhờ vậy thư demo có
    header Cc THẬT — điều kiện bắt buộc để "trả lời tất cả" khác "trả lời" — mà không
    một người thật nào nhận được thư tập dượt.
    """
    ten, _, mien = email.partition("@")
    return f"{ten}+{hau_to}@{mien}"


def _lam_giau_2(token: str, tai_khoan: str, nguoi_nhan: str, gui_that: bool) -> int:
    """Gửi bộ làm giàu vòng hai: thư có tệp/có Cc, rồi luồng ba lượt có tệp ở lượt đầu."""
    from bo_quay_demo import bo_lam_giau_2, luong_dac_ta_mcp

    bo = bo_lam_giau_2()
    luong = luong_dac_ta_mcp()

    print(f"Tài khoản : {tai_khoan}")
    print(f"Gửi tới   : {nguoi_nhan}")
    print(f"Số thư    : {len(bo)} thư rời + {len(luong)} lượt trong MỘT luồng\n")

    for i, (ng, td, _t, cc, tep) in enumerate(bo, 1):
        dau = []
        if tep:
            dau.append("📎 " + ", ".join(
                f"{t['name']} ({len(t['content']):,}B)" for t in tep))
        if cc:
            dau.append("Cc: " + ", ".join(_dia_chi_cong(tai_khoan, h) for h in cc))
        print(f"  {i:>2}. {ng:<26} │ {td}")
        for d in dau:
            print(f"      {d}")
    print(f"\n  ── luồng '{luong[0][1]}' ({len(luong)} lượt) ──")
    for k, (ng, td, _t, tep) in enumerate(luong, 1):
        ghi = ("  📎 " + ", ".join(t["name"] for t in tep)) if tep else ""
        print(f"  L{k}. {ng:<26} │ {td}{ghi}")

    if not gui_that:
        print("\n── XEM TRƯỚC, CHƯA GỬI GÌ ──")
        print("Gửi thư là việc KHÔNG HOÀN TÁC ĐƯỢC. Chạy lại kèm --gui-that nếu chắc chắn.")
        print("Dọn lại nếu cần: mở Gmail, tìm  from:me to:me newer_than:1d")
        return 0

    xong = 0
    for i, (ng, td, than, cc, tep) in enumerate(bo, 1):
        try:
            gmail_send.send_email(
                token, to=nguoi_nhan, subject=td, body=than,
                cc=[_dia_chi_cong(tai_khoan, h) for h in cc] or None,
                attachments=tep or None,
                from_addr=f'"{ng}" <{tai_khoan}>',
            )
            xong += 1
            print(f"  [{i}/{len(bo)}] đã gửi: {ng} │ {td}")
        except Exception as exc:
            print(f"  [{i}/{len(bo)}] LỖI: {td} — {exc}")
        if i < len(bo):
            time.sleep(0.5)

    # Luồng: gửi lượt đầu (KÈM TỆP) rồi trả lời vào chính nó hai lần, để Gmail gom
    # đúng một threadId. Ba thư rời cùng tiêu đề KHÔNG ra một luồng — xem chú thích ở
    # nhánh --bo-prompt.
    print(f"\n── Luồng ba lượt, TỆP nằm ở lượt ĐẦU ──")
    try:
        ng, td, than, tep = luong[0]
        dau = gmail_send.send_email(
            token, to=nguoi_nhan, subject=td, body=than,
            attachments=tep or None, from_addr=f'"{ng}" <{tai_khoan}>',
        )
        mid = dau.get("id", "")
        print(f"  [1/{len(luong)}] đã gửi kèm tệp: {ng} │ {td}")
        for k, (ng2, _td2, than2, tep2) in enumerate(luong[1:], start=2):
            time.sleep(1.0)
            tra = gmail_send.reply_email(
                token, mid, than2, attachments=tep2 or None,
                from_addr=f'"{ng2}" <{tai_khoan}>',
            )
            mid = tra.get("id", mid)
            print(f"  [{k}/{len(luong)}] đã trả lời trong luồng: {ng2}")
        xong += len(luong)
    except Exception as exc:
        print(f"  LỖI khi dựng luồng: {exc}")

    print(f"\nĐã gửi {xong}/{len(bo) + len(luong)} thư.")
    print("Mở MeoArc, bấm làm mới ở khung Thư. Kiểm ba thứ bằng MẮT trước khi tin:")
    print("  1. Thư của Tài/Tiến/Giáo vụ có hiện chip tệp đính kèm không")
    print("  2. Thư 'Góp ý slide bảo vệ' mở ra có thấy dòng Cc ba người không")
    print("  3. Mở luồng 'Đặc tả tool MCP', xem lượt ĐẦU có còn thấy tệp không")
    return 0 if xong else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Gửi bộ thư demo vào hộp thư đang đăng nhập.")
    ap.add_argument("--gui-that", action="store_true",
                    help="GỬI THẬT. Không có cờ này thì chỉ xem trước.")
    ap.add_argument("--email", default=None,
                    help="Địa chỉ NHẬN. Mặc định: chính tài khoản đang đăng nhập.")
    ap.add_argument("--tai-khoan", default=None,
                    help="Địa chỉ GỬI ĐI — chọn tài khoản nào trong DB. Mặc định: tài "
                         "khoản mới nhất còn phiên Gmail dùng được.")
    ap.add_argument("--kich-ban", action="store_true",
                    help="Gửi THÊM bộ thư ĐA DẠNG bám theo docs/kich-ban-kiem-thu-agent.md "
                         "(quảng cáo để thử xoá hàng loạt, thư chờ mình trả lời, luồng "
                         "họp, chuyến công tác). Bật sẵn khi dùng --bo-day.")
    ap.add_argument("--quay-demo", action="store_true",
                    help="Bộ thư DÀNH RIÊNG cho buổi quay demo: mọi mốc thời gian tính "
                         "theo NGÀY CHẠY (không phải ngày cứng), và mỗi thư bám đúng một "
                         "câu hỏi trong docs/kich-ban-quay-demo.md. Dùng RIÊNG, không "
                         "cộng thêm bộ nào khác. Kiểm trước bằng "
                         "scripts/kiem_bo_quay_demo.py.")
    ap.add_argument("--bo-day", action="store_true",
                    help="Gửi THÊM ~50 thư dồn cục để xem màn Lịch trình dưới tải "
                         "thật (xếp làn, chip +N, bảng ngày). Hộp thư sẽ rất lộn xộn "
                         "sau đó — đọc kỹ cảnh báo khi xem trước.")
    ap.add_argument("--phan-loai", action="store_true",
                    help="Gửi RIÊNG 22 thư mới phủ đủ 8 nhãn, để thấy rõ phân loại "
                         "chạy đúng. KHÔNG trùng với bộ --quay-demo đã gửi trước đó, "
                         "nên cộng thêm được vào hộp thư sẵn có.")
    ap.add_argument("--chi-luong", action="store_true",
                    help="CHỈ gửi cuộc trao đổi ba lượt, bỏ qua 11 thư nền. Dùng khi bộ "
                         "nền đã ở trong hộp thư rồi mà cần dựng lại riêng luồng.")
    ap.add_argument("--bo-prompt", action="store_true",
                    help="Gửi bộ thư dựng NGƯỢC TỪ CÂU HỎI (11 thư nền) KÈM một cuộc "
                         "trao đổi ba lượt với Giáo vụ, trong đó yêu cầu bị ĐỔI ở lượt "
                         "cuối. Luồng thật là thứ mọi bộ trước đây thiếu — không có nó "
                         "thì câu 'thầy có đổi yêu cầu gì so với lần trước không' không "
                         "kiểm được.")
    ap.add_argument("--lam-giau-2", action="store_true",
                    help="VÒNG LÀM GIÀU THỨ HAI: 10 thư có TỆP ĐÍNH KÈM và có Cc, kèm "
                         "một luồng ba lượt mà TỆP NẰM Ở LƯỢT ĐẦU. Gieo đúng bốn thứ "
                         "hộp thư hiện tại không có, nên bốn tính năng đã viết xong "
                         "(đính kèm, trả lời tất cả, đính kèm trong luồng, tìm theo "
                         "nghĩa) mới có chỗ để demo.")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        moi_nhat_truoc = db.query(User).order_by(User.id.desc()).all()
        if not moi_nhat_truoc:
            print("Chưa có người dùng nào trong DB. Đăng nhập vào MeoArc một lần rồi chạy lại.")
            return 1

        if args.tai_khoan:
            moi_nhat_truoc = [u for u in moi_nhat_truoc
                              if (u.email or "").lower() == args.tai_khoan.lower()]
            if not moi_nhat_truoc:
                print(f"Không có tài khoản {args.tai_khoan} trong DB.")
                return 1

        # Duyệt từ mới tới cũ, lấy tài khoản ĐẦU TIÊN còn phiên Gmail dùng được.
        # Bản trước chỉ lấy đúng người dùng mới nhất rồi bỏ cuộc — mà DB thường có
        # lẫn tài khoản test (vd qa…@example.test) nằm sau tài khoản thật, nên nó
        # báo "không có phiên" trong khi tài khoản thật vẫn đăng nhập tốt.
        user = token = None
        bo_qua: list[str] = []
        for u in moi_nhat_truoc:
            cap = _token_for_user(db, u.id)
            if cap is None:
                bo_qua.append(f"{u.email} (chưa/hết phiên đăng nhập)")
                continue
            tok, provider = cap
            if provider != "google":
                bo_qua.append(f"{u.email} (đăng nhập bằng {provider}, không phải Gmail)")
                continue

            # ── THỬ TOKEN BẰNG MỘT LỜI GỌI THẬT ──
            # `_token_for_user` chỉ nói "có token trong DB", KHÔNG nói token đó còn
            # sống. Token Google hết hạn mà refresh cũng hỏng thì nó vẫn trả về một
            # chuỗi — và kịch bản in ra "Tài khoản: ..." đầy tự tin, rồi gửi hỏng CẢ
            # 77 thư với lỗi 401 trôi lẫn trong output.
            # Người dùng đọc dòng đầu thấy tên tài khoản đúng nên tin là đã gửi xong,
            # rồi đi tìm nguyên nhân ở hộp thư NHẬN — sai chỗ hoàn toàn.
            # Một lời gọi đọc nhẹ ở đây biến hỏng-âm-thầm thành hỏng-nói-rõ.
            try:
                from app.services import gmail_service as _gs
                _gs.list_messages(tok, max_results=1)
            except Exception as exc:
                ma = "401" if "401" in str(exc) else type(exc).__name__
                bo_qua.append(f"{u.email} (token hết hạn — {ma})")
                continue

            user, token = u, tok
            break

        if user is None:
            print("Không tài khoản nào trong DB có phiên Gmail dùng được.\n")
            for d in bo_qua:
                print(f"  ✗ {d}")
            print("\nĐăng nhập vào MeoArc bằng Google rồi chạy lại.")
            return 1

        if bo_qua:
            print(f"(Bỏ qua {len(bo_qua)} tài khoản không dùng được: {', '.join(bo_qua)})\n")

        if args.lam_giau_2:
            return _lam_giau_2(token, user.email, args.email or user.email,
                               args.gui_that)

        if args.chi_luong:
            bo = []
            thanh_phan = ["chỉ luồng hội thoại"]
        elif args.bo_prompt:
            # BỘ DỰNG NGƯỢC TỪ CÂU HỎI. Các bộ khác gieo thư cho đủ tính năng; bộ này
            # gieo đúng những lá khiến câu người dùng thật sự hỏi có câu trả lời.
            from bo_quay_demo import bo_prompt as _bo_pr
            bo = list(_bo_pr())
            thanh_phan = [f"{len(bo)} thư theo câu hỏi"]
        elif args.phan_loai:
            # RIÊNG, không trộn: bộ này để soi PHÂN LOẠI, và 46 thư kia đã ở trong
            # hộp thư rồi — gửi lại là hàng đôi, mà hàng đôi thì mọi con số đếm được
            # (chưa đọc, số việc) đều sai theo một cách rất khó nhận ra.
            from bo_quay_demo import bo_phan_loai as _bo_pl
            bo = list(_bo_pl())
            thanh_phan = [f"{len(bo)} thư phân loại"]
        elif args.quay_demo:
            # DÙNG RIÊNG, không trộn. Bộ quay demo được cân đúng để mỗi câu hỏi trong
            # kịch bản có dữ liệu đỡ; trộn thêm thư khác vào là phá mất cân đó — nhất
            # là ngày quá tải, chỉ cần thêm vài việc nữa là các ngày khác cũng đỏ và
            # câu "ngày nào bận nhất" hết còn chỉ được vào đâu.
            from bo_quay_demo import bo_day_du as _bo_quay
            bo = list(_bo_quay())
            thanh_phan = [f"{len(bo)} thư quay demo"]
        else:
            bo = list(THU_DEMO)
            thanh_phan = [f"{len(THU_DEMO)} gốc"]
        # Bộ kịch bản đi kèm --bo-day, và cũng bật riêng được bằng --kich-ban: có lúc
        # chỉ cần dữ liệu ĐA DẠNG để thử agent, không cần hộp thư quá tải.
        if (args.kich_ban or args.bo_day) and not (args.quay_demo or args.phan_loai):
            bo += _THU_KICH_BAN + _THU_KHO
            thanh_phan.append(f"{len(_THU_KICH_BAN)} kịch bản")
            thanh_phan.append(f"{len(_THU_KHO)} khó")
        if args.bo_day and not (args.quay_demo or args.phan_loai):
            day = _dung_bo_day()
            bo += day
            thanh_phan.append(f"{len(day)} dày")

        nguoi_nhan = args.email or user.email
        print(f"Tài khoản : {user.email}")
        print(f"Gửi tới   : {nguoi_nhan}")
        print(f"Số thư    : {len(bo)}  ({' + '.join(thanh_phan)})\n")

        if not args.gui_that:
            for i, (nguoi_gui, tieu_de, _) in enumerate(bo, 1):
                print(f"  {i:>2}. {nguoi_gui:<26} │ {tieu_de}")
            print("\n── XEM TRƯỚC, CHƯA GỬI GÌ ──")
            print("Gửi thư là việc KHÔNG HOÀN TÁC ĐƯỢC. Chạy lại kèm --gui-that nếu chắc chắn.")
            if args.bo_day:
                _canh_bao_bo_day(len(bo), nguoi_nhan)
            return 0

        if args.bo_day:
            _canh_bao_bo_day(len(bo), nguoi_nhan)
            print()

        xong = 0
        for i, (nguoi_gui, tieu_de, than) in enumerate(bo, 1):
            try:
                gmail_send.send_email(
                    token, to=nguoi_nhan, subject=tieu_de, body=than,
                    # Địa chỉ vẫn là tài khoản đang đăng nhập — Gmail không cho gửi hộ
                    # địa chỉ lạ. Chỉ TÊN HIỂN THỊ là đổi, để thẻ lịch trình hiện
                    # "Giáo vụ HCMUS" thay vì tám thẻ cùng đề tên bạn.
                    from_addr=f'"{nguoi_gui}" <{user.email}>',
                )
                xong += 1
                print(f"  [{i}/{len(bo)}] đã gửi: {nguoi_gui} │ {tieu_de}")
            except Exception as exc:
                # Một thư hỏng KHÔNG được làm dừng cả bộ — báo rồi đi tiếp.
                print(f"  [{i}/{len(bo)}] LỖI: {tieu_de} — {exc}")
            # NGHỈ GIỮA CÁC LẦN GỬI. Bắn 50 lệnh liên tiếp rất dễ ăn 429 từ Gmail,
            # và lúc đó nửa bộ đã đi rồi nửa chưa — trạng thái tệ nhất, vì gửi lại
            # thì thành hàng đôi mà bỏ dở thì demo thiếu.
            if i < len(bo):
                time.sleep(0.4)

        # ── LUỒNG HỘI THOẠI THẬT ────────────────────────────────────────────
        # Gửi thư đầu như bình thường, rồi TRẢ LỜI vào chính nó hai lần. `reply_email`
        # gắn In-Reply-To/References + threadId nên Gmail gom đúng MỘT luồng.
        #
        # Không làm được bằng cách gửi ba thư rời cùng tiêu đề: giao diện Gmail gom
        # theo tiêu đề, nhưng `threadId` vẫn là ba luồng khác nhau — mà MeoArc đọc
        # threadId. Ba thư rời thì tính năng xem hội thoại không có gì để hiện.
        if args.bo_prompt or args.chi_luong:
            from bo_quay_demo import luong_giao_vu as _luong
            cac_luot = _luong()
            print("\n── Cuộc trao đổi ba lượt (Giáo vụ ĐỔI yêu cầu ở lượt cuối) ──")
            try:
                nguoi_gui, tieu_de, than = cac_luot[0]
                dau = gmail_send.send_email(
                    token, to=nguoi_nhan, subject=tieu_de, body=than,
                    from_addr=f'"{nguoi_gui}" <{user.email}>',
                )
                mid = dau.get("id", "")
                print(f"  [1/3] đã gửi: {nguoi_gui} │ {tieu_de}")
                for k, (ng, _td, th) in enumerate(cac_luot[1:], start=2):
                    time.sleep(1.0)      # Gmail cần một nhịp để thư trước có mặt
                    tra = gmail_send.reply_email(
                        token, mid, th, from_addr=f'"{ng}" <{user.email}>',
                    )
                    mid = tra.get("id", mid)   # trả lời vào lượt MỚI NHẤT → chuỗi nối dài
                    print(f"  [{k}/3] đã trả lời trong luồng: {ng}")
                xong += 3
            except Exception as exc:
                print(f"  LỖI khi dựng luồng: {exc}")

        print(f"\nĐã gửi {xong}/{len(bo)} thư.")
        print("Mở MeoArc, bấm nút làm mới ở khung Thư, rồi vào Lịch trình để xem.")
        if args.bo_day and xong:
            print("\nDỌN LẠI khi xong việc — mở Gmail, tìm bằng truy vấn này rồi chọn tất cả:")
            print("    from:me to:me newer_than:1d")
            print("(nhớ dọn ở CẢ Hộp thư đến lẫn Đã gửi — thư tự gửi nằm ở cả hai)")
        return 0 if xong else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
