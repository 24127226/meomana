"""BỘ THƯ ĐỂ QUAY DEMO — mọi mốc thời gian tính theo LÚC CHẠY, không phải ngày cứng.

── VÌ SAO PHẢI TÍNH ĐỘNG ──
Bộ thư cũ ghi cứng "trước 18/9", "ngày 12/09"… Chạy đúng đầu tháng 9 thì hợp lý; chạy
muộn hai tuần là mọi hạn đều đã qua, và câu hỏi "tuần này tôi có gì?" trả về rỗng
trong khi màn hình vẫn đầy thư. Người xem không hiểu nổi vì sao, còn người trình bày
thì không kịp sửa.

Ở đây mỗi mốc là một khoảng cách so với HÔM NAY. Chạy lúc nào cũng khớp.

── DỮ LIỆU PHẢI ĂN NHẬP VỚI CÂU HỎI ──
Mỗi thư dưới đây tồn tại để phục vụ ít nhất một câu hỏi trong `docs/kich-ban-quay-demo.md`,
và mỗi câu hỏi trong tài liệu đó đều có thư đỡ. Nhãn `# → Q3` ở mỗi nhóm là mối nối
đó. Chạy `scripts/kiem_bo_quay_demo.py` để MÁY tự kiểm lại mối nối, đừng tin vào việc
đọc bằng mắt — bộ thư và bộ câu hỏi trôi xa nhau rất dễ mà không ai nhận ra.

── CÔNG THỨC "NGÀY QUÁ TẢI" ──
Trần một ngày là 360 phút (`cam_ket.TRAN_MOI_NGAY`). Ước lượng: thư trên 90 chữ = 60
phút, nhân đôi nếu KHẨN (`labeling._PAT_GAP`: "hạn chót", "gấp", "hôm nay", "ngày
mai"…). Nên bốn thư trên 90 chữ, có chữ "hạn chót", cùng hạn một ngày = 480 phút →
ngày đó chắc chắn đỏ. Đó là lý do nhóm A có đúng bốn thư và đều dài như nhau.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _moc() -> datetime:
    return datetime.now(_TZ_VN)


def bo_day_du(moc: datetime | None = None) -> list[tuple[str, str, str]]:
    """Bộ ĐẦY ĐỦ = 20 thư nền (tính ngày động) + 26 thư BẪY của bộ khó cũ.

    Bộ khó cũ chứa sáu chuỗi bẫy mà `docs/prompt-demo.md` dựa vào — lịch bảo vệ đổi
    ba lần, hoá đơn và biên lai nằm ở hai thư, hạn chôn giữa bản tin, hai người trùng
    tên, quảng cáo giả dạng cam kết, chuyến bay đổi giờ. Không có chúng thì "sáu câu
    làm khó" hỏi ra rỗng.

    ⚠️ MỐC THỜI GIAN CỦA BỘ KHÓ LÀ NGÀY CỨNG (15/9, 16/9, 20/9…). Chúng còn ở tương
    lai thì các bẫy còn đúng; chạy muộn quá là hỏng. `kiem_bo_quay_demo.py` có phép
    kiểm riêng cho chuyện này — đừng bỏ qua nó."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "_gtd", str(Path(__file__).resolve().parent / "gui_thu_demo.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    # Bộ nền TRƯỚC, bộ bẫy SAU, rồi thư "biên bản họp" đẩy xuống cuối cùng:
    # câu "tóm tắt lá thư mới nhất" bám vào việc nó là thư gửi sau chót.
    nen = bo_thu(moc)
    return [*nen[:-1], *list(g._THU_KHO), nen[-1]]


def bo_phan_loai(moc: datetime | None = None) -> list[tuple[str, str, str]]:
    """22 thư THÊM, dựng riêng để cho thấy PHÂN LOẠI chạy đúng — phủ đủ 8 nhãn.

    ── VÌ SAO LÀ BỘ RIÊNG, KHÔNG NHÉT VÀO `bo_day_du` ──
    46 thư kia đã nằm trong hộp thư rồi. Gộp vào là gửi trùng, và một hộp thư có hai
    bản của cùng một lá thư thì mọi con số đếm được (bao nhiêu chưa đọc, bao nhiêu
    việc) đều sai theo, mà sai một cách rất khó nhận ra.

    ── ĐIỀU KIỆN ĐỂ NÓ CHẠY ĐÚNG ──
    Thư tự gửi cho chính mình nên ĐỊA CHỈ người gửi không mang tín hiệu nào — mọi thư
    cùng một địa chỉ. Toàn bộ sức phân loại nằm ở TÊN HIỂN THỊ, và `gui_thu_demo.py`
    giữ được tên đó bằng `from_addr='"Tên" <địa@chỉ>'`. Gửi tay từ giao diện Gmail thì
    tên hiển thị thành tên tài khoản bạn, và bộ này mất tác dụng.

    ── CÓ CHỦ Ý ĐẶT MẤY CA KHÓ ──
    · Agoda nhắc "đã thanh toán 1.850.000đ" → phải là ĐI LẠI, không phải Tài chính:
      với người dùng thì đó là chuyến đi, biên lai chỉ là mặt phụ.
    · Vietcombank báo biến động số dư CỦA CHÍNH giao dịch đó → phải là TÀI CHÍNH.
      Hai thư nói về một việc mà về hai nhãn khác nhau, và cả hai đều đúng.
    · "EduMax Academy" bán khoá học → MUA SẮM, không phải Học tập. Mảnh `edu` quá
      ngắn nên cố ý không được khớp tên hiển thị (xem `_DAI_TOI_THIEU_TEN`).
    · "Nguyễn Văn Sơn (GVHD)" → HỌC TẬP dù là người thật.
    · "Mẹ", "Phạm Thu Trang" → CÁ NHÂN. Không phải thư nào cũng phải có nhãn kêu.
    """
    n = moc or _moc()

    def d(k: int) -> str:
        return (n + timedelta(days=k)).strftime("%d/%m")

    return [
        # ── ĐI LẠI (nhãn thứ 8) ──────────────────────────────────────────
        ("Vietjet Air", f"Xác nhận đặt chỗ VJ162 — SGN đi HAN ngày {d(21)}",
         f"Cảm ơn bạn đã đặt vé. Mã đặt chỗ: QT9R2K. Chuyến VJ162 khởi hành 07:15 "
         f"ngày {d(21)} từ Tân Sơn Nhất, hạ cánh Nội Bài 09:25. Vui lòng có mặt tại "
         f"quầy làm thủ tục trước giờ bay 60 phút."),
        ("Agoda", f"Đặt phòng đã xác nhận — Hanoi Old Quarter Hotel, {d(21)} - {d(23)}",
         f"Đặt phòng của bạn đã được xác nhận. Nhận phòng 14:00 ngày {d(21)}, trả "
         f"phòng 12:00 ngày {d(23)}. Bạn đã thanh toán 1.850.000đ. Huỷ miễn phí "
         f"trước ngày {d(19)}."),
        ("Traveloka", f"THAY ĐỔI GIỜ BAY — chuyến VN214 ngày {d(21)}",
         f"Hãng vừa thông báo đổi giờ khởi hành chuyến VN214 từ 06:00 sang 09:45 "
         f"ngày {d(21)}. Mã đặt chỗ XKPQ7M. Bạn không cần làm gì thêm."),
        ("Vexere", f"Vé xe khách Sài Gòn - Đà Lạt ngày {d(28)}",
         f"Vé của bạn đã đặt thành công. Nhà xe Phương Trang, giường nằm, khởi hành "
         f"22:00 ngày {d(28)} tại bến xe Miền Đông. Mã đặt chỗ VX88231."),

        # ── TÀI CHÍNH ─────────────────────────────────────────────────────
        ("Vietcombank", "Biến động số dư tài khoản 0071xxxx",
         "Tài khoản của bạn vừa ghi nợ 1.850.000đ. Số dư hiện tại 4.320.000đ. "
         "Nội dung: thanh toan dat phong khach san."),
        ("MoMo", "Hoá đơn tiền điện tháng này đã thanh toán thành công",
         "Giao dịch thanh toán hoá đơn tiền điện số tiền 412.000đ đã hoàn tất. "
         "Mã giao dịch MM20260905."),

        # ── HỌC TẬP ───────────────────────────────────────────────────────
        ("Giáo vụ HCMUS", f"[Hạn chót {d(7)}] Nộp phiếu đăng ký đề tài khoá luận",
         f"Sinh viên nộp phiếu đăng ký đề tài khoá luận trước 17:00 ngày {d(7)} tại "
         f"văn phòng khoa hoặc qua hệ thống. Quá hạn xem như không đăng ký."),
        ("Phòng CTSV", f"Đăng ký xét học bổng khuyến khích học kỳ 1",
         f"Sinh viên có điểm trung bình từ 8.0 nộp hồ sơ xét học bổng trước ngày "
         f"{d(15)}. Hồ sơ gồm bảng điểm và đơn theo mẫu."),
        ("CLB Học thuật FIT", f"Mời tham gia workshop Machine Learning {d(9)}",
         f"CLB tổ chức workshop về Machine Learning lúc 8h30 ngày {d(9)} tại phòng "
         f"E203. Bạn xác nhận tham dự trước ngày {d(7)} nhé."),
        ("IEEE Xplore", "Your manuscript requires revision",
         "Dear author, the reviewers have requested revisions to your submission. "
         "Please upload the revised manuscript within two weeks."),
        ("Nguyễn Văn Sơn (GVHD)", "Về bản chỉnh sửa chương 3",
         "Thầy đã xem qua chương 3. Phần đặc tả còn thiếu ràng buộc phi chức năng, "
         "em bổ sung rồi gửi lại thầy nhé."),

        # ── CÔNG VIỆC ─────────────────────────────────────────────────────
        ("TopCV", "3 việc làm Intern Backend phù hợp với hồ sơ của bạn",
         f"Chúng tôi tìm thấy 3 vị trí thực tập backend phù hợp. Hạn ứng tuyển sớm "
         f"nhất là ngày {d(13)}."),
        ("HR VNG Corporation", "Thư mời phỏng vấn vị trí Intern Software Engineer",
         f"Chúng tôi mời bạn tham dự buổi phỏng vấn lúc 14:00 ngày {d(12)} tại toà "
         f"nhà Z06. Vui lòng xác nhận trước ngày {d(10)}."),

        # ── MẠNG XÃ HỘI ───────────────────────────────────────────────────
        ("LinkedIn", "Nguyễn Minh Tuấn và 4 người khác đã xem hồ sơ của bạn",
         "Hồ sơ của bạn được xem 5 lần trong tuần qua. Xem ai đã quan tâm đến bạn."),
        ("Facebook", "Bạn có 3 lời mời kết bạn đang chờ",
         "Có 3 người muốn kết bạn với bạn. Đăng nhập để xem chi tiết."),

        # ── CẬP NHẬT & HỆ THỐNG ───────────────────────────────────────────
        ("GitHub", "[meoarc-integration] CI failed on branch integration",
         "The workflow Deploy to Azure failed at step webapps-deploy. "
         "View the run log for details."),
        ("Google", "Cảnh báo bảo mật: thiết bị mới đăng nhập vào tài khoản",
         "Một thiết bị Windows vừa đăng nhập vào tài khoản của bạn. Nếu không phải "
         "bạn, hãy đổi mật khẩu ngay."),
        ("Azure", "Your App Service plan is approaching its quota",
         "The App Service meoarc has used 82% of its monthly compute quota."),

        # ── MUA SẮM & ƯU ĐÃI ──────────────────────────────────────────────
        ("Shopee", "Săn deal 9.9 — giảm đến 50% toàn sàn",
         "Flash sale 9.9 bắt đầu lúc 0h. Voucher giảm 50% cho đơn từ 99k, "
         "số lượng có hạn."),
        ("EduMax Academy", "Khoá học Python MIỄN PHÍ 100% — ưu đãi cuối cùng",
         "Đăng ký ngay hôm nay để nhận khoá học Python trị giá 2.990.000đ hoàn toàn "
         "miễn phí. Ưu đãi kết thúc sau 2 ngày."),

        # ── CÁ NHÂN ───────────────────────────────────────────────────────
        ("Mẹ", "con nhớ ăn uống đầy đủ",
         "Mẹ gửi con ít tiền tiêu vặt rồi nhé. Nhớ ăn sáng đầy đủ, đừng thức khuya "
         "quá con nhé."),
        ("Phạm Thu Trang", "chiều nay đi cà phê không",
         "Rảnh chiều nay không, đi cà phê chỗ cũ đi. Mình có chuyện muốn kể."),
    ]


def bo_thu(moc: datetime | None = None) -> list[tuple[str, str, str]]:
    """Trả (tên người gửi, tiêu đề, thân thư). Thứ tự = thứ tự GỬI.

    Thư CUỐI CÙNG trong danh sách là thư MỚI NHẤT trong hộp thư sau khi gửi xong —
    câu hỏi "tóm tắt lá thư mới nhất" bám vào đúng nó, nên đừng đổi chỗ."""
    n = moc or _moc()

    def d(k: int) -> str:
        """Ngày cách hôm nay k hôm, dạng 'dd/mm'."""
        return (n + timedelta(days=k)).strftime("%d/%m")

    THU = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ nhật"]

    def t(k: int) -> str:
        return THU[(n + timedelta(days=k)).weekday()]

    return [
        # ══════════════════════════════════════════════════════════════════
        # NHÓM A — BỐN VIỆC CÙNG HẠN NGÀY MAI  → tạo NGÀY QUÁ TẢI
        # → Q4 "tuần này tôi có bị quá tải không?"  · Q3 "tuần này lịch trình"
        # Mỗi thư >90 chữ và có "hạn chót" nên được tính 120 phút; bốn thư = 480 > 360.
        # ══════════════════════════════════════════════════════════════════
        (
            "Giáo vụ HCMUS",
            f"[Hạn chót {d(1)}] Nộp báo cáo Testing PA3 — Nhóm 7",
            "Chào các em,\n\n"
            f"Hạn chót nộp báo cáo Testing (PA3) là 23:59 ngày {d(1)} ({t(1)}). Các nhóm "
            "nộp đầy đủ lên Moodle, kèm minh chứng chạy test và bảng phân công công việc "
            "của từng thành viên.\n\n"
            "Báo cáo cần có đủ các phần: kế hoạch kiểm thử, đặc tả ca kiểm thử cho toàn "
            "bộ use case đã đăng ký, kết quả chạy thực tế, phần đánh giá độ phủ, và phụ "
            "lục minh chứng. Nhóm nào dùng công cụ tự động thì đính kèm cả cấu hình và "
            "log chạy để thầy đối chiếu.\n\n"
            "Về quy cách nộp: đặt tên tệp theo mẫu Nhom07_PA3_Testing.pdf, phần phụ lục "
            "gộp chung vào một tệp nén riêng. Nhóm nào nộp nhiều tệp rời sẽ được yêu cầu "
            "nộp lại, và thời điểm tính hạn là lần nộp cuối cùng chứ không phải lần đầu.\n\n"
            "Về nội dung, thầy cô nhắc lại hai chỗ các nhóm khoá trước hay mất điểm nhất. "
            "Thứ nhất là bảng đặc tả ca kiểm thử chỉ ghi đầu vào mà không ghi kết quả "
            "mong đợi, khiến người chấm không đối chiếu được. Thứ hai là phần đánh giá độ "
            "phủ chỉ đưa một con số phần trăm mà không nói phần nào chưa phủ và vì sao. "
            "Một con số không kèm giải thích thì không chứng minh được điều gì cả.\n\n"
            "Đây là hạng mục chiếm trọng số lớn nhất của học phần nên các em bố trí thời "
            "gian sớm, đừng dồn vào buổi cuối. Nhóm nộp trễ sẽ bị trừ điểm theo quy định "
            "đã công bố đầu kỳ, không có ngoại lệ. Em nào có lý do đặc biệt thì liên hệ "
            "giáo vụ TRƯỚC hạn, sau hạn thì không giải quyết được nữa.\n\n"
            "Giáo vụ",
        ),
        (
            "GVHD Nguyễn Văn Sơn",
            f"[Hạn chót {d(1)}] Gửi slide bảo vệ đồ án trước buổi trình bày",
            "Chào em,\n\n"
            f"Hạn chót gửi slide là 17:00 ngày {d(1)}. Thầy cần xem trước để góp ý, nên "
            "em gửi đúng hạn giúp thầy.\n\n"
            "Slide nên đi theo mạch: bài toán và người dùng thật, kiến trúc tổng thể, "
            "phần nào nhóm tự làm và phần nào dùng thư viện, rồi tới demo. Phần demo nên "
            "quay sẵn một bản dự phòng phòng khi mạng ở phòng hội đồng chậm.\n\n"
            "Em nhớ chuẩn bị câu trả lời cho hai câu thầy chắc chắn sẽ hỏi: hệ thống xử "
            "lý thế nào khi mô hình trả lời sai, và dữ liệu người dùng được bảo vệ ra "
            "sao. Hai câu đó phân biệt nhóm hiểu việc mình làm với nhóm chỉ ghép thư "
            "viện lại.\n\n"
            "Thầy góp ý thêm về cách trình bày. Đừng dành quá nhiều thời gian cho phần "
            "giới thiệu bối cảnh, hội đồng đã đọc đề cương rồi. Vào thẳng chỗ nhóm giải "
            "quyết được vấn đề gì mà cách làm thông thường không giải quyết được, đó mới "
            "là phần đáng nghe. Mỗi slide giữ một ý, chữ to, và tuyệt đối không đọc lại "
            "nguyên văn slide.\n\n"
            "Phần demo em nên chọn đúng ba tình huống: một tình huống chạy trơn để người "
            "xem hiểu luồng, một tình huống hệ thống từ chối làm vì rủi ro, và một tình "
            "huống dữ liệu thiếu để cho thấy nó xử lý ra sao. Tình huống thứ hai và thứ "
            "ba mới là chỗ ghi điểm, vì nó chứng minh nhóm đã nghĩ tới lúc mọi thứ không "
            "diễn ra như ý.\n\n"
            "GVHD",
        ),
        (
            "Phòng Đào tạo HCMUS",
            f"[Hạn chót {d(1)}] Đăng ký học phần học kỳ 1",
            "Chào các em,\n\n"
            f"Hạn chót đăng ký học phần học kỳ 1 là 17:00 ngày {d(1)}. Sau thời điểm này "
            "hệ thống khoá lại, mọi trường hợp bổ sung phải làm đơn và chờ duyệt.\n\n"
            "Các em kiểm tra kỹ số tín chỉ tối thiểu, các môn tiên quyết, và lịch trùng "
            "giữa các lớp trước khi bấm xác nhận. Năm ngoái có khá nhiều trường hợp đăng "
            "ký xong mới phát hiện trùng lịch thi, và lúc đó không đổi được nữa.\n\n"
            "Sinh viên năm cuối lưu ý đăng ký đủ phần thực tập tốt nghiệp, vì đây là điều "
            "kiện xét tốt nghiệp đúng hạn. Trường hợp đã đi thực tập ngoài doanh nghiệp "
            "thì vẫn phải đăng ký học phần tương ứng, nếu không hệ thống sẽ không ghi "
            "nhận kết quả.\n\n"
            "Về mức thu, số tiền được tính theo số tín chỉ đã đăng ký tại thời điểm khoá "
            "hệ thống. Sinh viên rút bớt môn sau khi khoá vẫn phải đóng đủ phần đã đăng "
            "ký, nên các em cân nhắc kỹ khối lượng trước khi xác nhận. Kinh nghiệm các "
            "khoá trước là đừng đăng ký quá 22 tín chỉ nếu học kỳ đó còn làm đồ án.\n\n"
            "Danh sách lớp và phòng học sẽ công bố trong vòng ba ngày làm việc sau khi "
            "khoá đăng ký. Các em theo dõi thông báo trên cổng thông tin, phòng không gửi "
            "thư riêng cho từng trường hợp.\n\n"
            "Phòng Đào tạo",
        ),
        (
            "Trần Minh Khoa",
            f"Re: Đặc tả tool MCP — cần gấp trước {d(1)}",
            "Ok bạn,\n\n"
            f"Mình nhận phần MCP server. Bạn gửi lại đặc tả tool trước ngày {d(1)} để "
            "mình còn kịp làm, phần này gấp vì nó chặn cả hai người còn lại.\n\n"
            "Mình đề nghị gom phần confirm-gate về một chỗ thay vì để mỗi tool tự làm một "
            "kiểu. Làm rải rác thì lúc thêm tool mới rất dễ quên, mà quên đúng chỗ đó thì "
            "hệ thống gửi thư đi mà không hỏi ai — lỗi tệ nhất có thể có.\n\n"
            "Bạn cũng xem giúp phần đặt tên tham số cho thống nhất. Hiện có chỗ dùng "
            "camelCase, chỗ dùng snake_case, và mô hình sẽ gọi sai ở đúng những chỗ lệch "
            "đó. Mình đã gặp hai lần model sinh ra tên trường không tồn tại, cả hai lần "
            "đều rơi đúng vào tool có tên tham số lệch quy ước.\n\n"
            "Trong đặc tả, mỗi tool bạn ghi giúp mình bốn thứ: tham số bắt buộc và tham "
            "số tuỳ chọn, giá trị trả về khi thành công, hình dạng lỗi khi thất bại, và "
            "quan trọng nhất là tool đó có gây hậu quả ra bên ngoài hay không. Cái cuối "
            "quyết định nó có phải đi qua cổng xác nhận hay không, mà nhìn vào tên hàm "
            "thì không đoán được.\n\n"
            "Phần mô tả dành cho model thì bạn viết bằng câu mệnh lệnh ngắn, đừng viết "
            "kiểu tài liệu cho người đọc. Mình thử rồi: mô tả càng dài dòng thì model "
            "càng hay gọi nhầm tool, chắc vì nó bắt được nhiều từ khoá không liên quan.\n\n"
            "Khoa",
        ),
        # ══════════════════════════════════════════════════════════════════
        # NHÓM B — VIỆC HÔM NAY và TRONG TUẦN
        # → Q3 "tuần này lịch trình"  · Q2 "thư nào cần xử lý trước"
        # ══════════════════════════════════════════════════════════════════
        (
            "Thư ký khoa CNTT",
            "Xác nhận danh sách thành viên nhóm trong hôm nay",
            "Chào em,\n\n"
            "Khoa cần em xác nhận lại danh sách thành viên Nhóm 7 trước 16:00 hôm nay để "
            "kịp chốt danh sách hội đồng. Em phản hồi thẳng thư này là được.\n\n"
            "Nếu có thay đổi thành viên so với đăng ký đầu kỳ thì ghi rõ lý do.",
        ),
        (
            "Phòng CTSV",
            f"Thanh toán học phí học kỳ 1 trước {d(2)}",
            "Thông báo,\n\n"
            f"Sinh viên hoàn tất thanh toán học phí học kỳ 1 trước ngày {d(2)} qua cổng "
            "thanh toán của trường.\n\n"
            "Quá hạn sẽ bị khoá kết quả học tập cho tới khi hoàn tất. Sinh viên thuộc "
            "diện miễn giảm nộp đơn tại phòng CTSV trước hạn trên.\n\n"
            "Phòng CTSV",
        ),
        (
            "CLB Tin học HCMUS",
            f"Xác nhận tham dự workshop {d(3)}",
            "Chào bạn,\n\n"
            f"CLB tổ chức workshop về kiểm thử tự động vào {t(3)} ngày {d(3)} tại phòng "
            "C42. Bạn vui lòng xác nhận tham dự để CLB chuẩn bị chỗ ngồi.\n\n"
            "Workshop miễn phí cho sinh viên trong trường.",
        ),
        # ══════════════════════════════════════════════════════════════════
        # NHÓM C — PHẢI ĐI XA  → Q6 "mình cần đi công tác cho việc nào không?"
        # Có TÊN THÀNH PHỐ khác nơi ở + ngày rõ ràng thì bộ suy ý định mới nhận.
        # ══════════════════════════════════════════════════════════════════
        (
            "Ban tổ chức Hackathon",
            f"Xác nhận tham dự vòng chung kết {d(9)} tại Đà Nẵng",
            "Xin chào đội MeoArc,\n\n"
            f"Đội của bạn đã lọt vào vòng chung kết diễn ra ngày {d(9)} tại Đà Nẵng. Vui "
            "lòng xác nhận tham dự trong vòng 3 ngày làm việc kể từ khi nhận thư.\n\n"
            "Ban tổ chức hỗ trợ chi phí đi lại cho tối đa 3 thành viên mỗi đội. Đội cần "
            "có mặt tại địa điểm trước 7:30 sáng để nhận thẻ và kiểm tra thiết bị.",
        ),
        (
            "Ban tổ chức Hội thảo SV",
            f"Hội thảo sinh viên toàn quốc {d(17)} tại Hà Nội",
            "Chào bạn,\n\n"
            f"Hội thảo sinh viên toàn quốc năm nay diễn ra ngày {d(17)} tại Hà Nội. Bạn "
            f"đăng ký trước ngày {d(12)} nếu muốn tham gia trình bày poster.\n\n"
            "Ban tổ chức có hỗ trợ một phần chi phí cho sinh viên ở xa.",
        ),
        # ══════════════════════════════════════════════════════════════════
        # NHÓM D — HỌC PHÍ và CÁI BẪY "MIỄN PHÍ"
        # → Q7 "tìm thư về học phí". Thư bẫy PHẢI KHÔNG được lọt vào kết quả:
        #   Gmail tách "học phí" thành hai từ rời nên nó khớp cả "MIỄN PHÍ" nếu không
        #   bọc nguyên cụm. Đây là chỗ chứng minh bản sửa đó có tác dụng thật.
        # ══════════════════════════════════════════════════════════════════
        (
            "Ngân hàng ACB",
            "Biên lai thanh toán học phí",
            "Kính gửi Quý khách,\n\n"
            "Giao dịch thanh toán học phí của Quý khách đã được ghi nhận thành công. Vui "
            "lòng lưu biên lai này để đối chiếu khi cần.\n\n"
            "Trân trọng.",
        ),
        (
            "EduMax Academy",
            "🔥 Khoá học lập trình MIỄN PHÍ 100% — chỉ còn 2 ngày!",
            # ── KHÔNG ĐƯỢC CHỨA ĐỘNG TỪ CAM KẾT KÈM MỐC THỜI GIAN ──
            # Bản đầu viết "Đăng ký ngay hôm nay…" nên bộ trích nhận nó thành một VIỆC
            # PHẢI LÀM và nó chen vào giữa danh sách lịch trình. Đã thấy tận mắt khi chạy
            # thật: "🔥 Khoá học lập trình MIỄN PHÍ 100%" nằm ngay dòng thứ hai của thẻ
            # Lịch trình. Trên máy quay thì đó là lỗi rất khó chống chế.
            # Thư này chỉ cần làm bẫy cho phép TÌM KIẾM, không cần giục ai làm gì.
            "Đừng bỏ lỡ!\n\n"
            "Trọn bộ khoá học lập trình MIỄN PHÍ, không mất một đồng học phí nào. Ưu đãi "
            "dành cho 100 người sớm nhất.\n\n"
            "Nhấn vào đây để xem chi tiết.",
        ),
        # ══════════════════════════════════════════════════════════════════
        # NHÓM E — QUẢNG CÁO  → Q8 "xoá hết thư quảng cáo" (demo cổng xác nhận)
        # ══════════════════════════════════════════════════════════════════
        (
            "Shopee",
            "Sale 9.9 — giảm đến 50% toàn sàn",
            "Ngày hội mua sắm 9.9 đã bắt đầu!\n\n"
            "Hàng ngàn ưu đãi đang chờ bạn, giảm đến 50% và freeship toàn quốc.",
        ),
        (
            "Thẻ tín dụng VIB",
            "Ưu đãi hoàn tiền 10% cho chủ thẻ",
            "Kính gửi Quý khách,\n\n"
            "Chương trình hoàn tiền 10% áp dụng cho mọi giao dịch trực tuyến trong tháng "
            "này. Không cần đăng ký.",
        ),
        (
            "TechNews Weekly",
            "Bản tin công nghệ tuần này",
            "Chào bạn,\n\n"
            "Tuần này có gì mới: mô hình ngôn ngữ mở nguồn, chip di động thế hệ mới, và "
            "một vài công cụ dành cho lập trình viên.",
        ),
        (
            "Grab",
            "Mã giảm giá 50% cho 5 chuyến tiếp theo",
            "Nhập mã GRAB50 để được giảm 50% tối đa 30.000đ cho 5 chuyến xe tiếp theo. "
            "Ưu đãi có hạn.",
        ),
        # ══════════════════════════════════════════════════════════════════
        # NHÓM F — NGƯỜI KHÁC ĐANG CHỜ MÌNH  → Q5 "tôi đang nợ ai cái gì?"
        # ══════════════════════════════════════════════════════════════════
        (
            "Phạm Thu Trang",
            "Cho mình xin lại link repo với",
            "Chào bạn,\n\n"
            f"Bạn gửi lại link repo và quyền truy cập cho mình trước {d(1)} nhé, mình cần "
            "để viết phần tài liệu kiến trúc.\n\n"
            "Cảm ơn bạn nhiều.",
        ),
        (
            "Lê Anh Đức",
            "Phản hồi giúp mình về lịch họp nhóm",
            "Hi bạn,\n\n"
            f"Bạn phản hồi giúp mình xem {t(2)} ngày {d(2)} họp nhóm được không. Mình cần "
            "chốt phòng trước khi đăng ký.\n\n"
            "Nếu bận thì báo mình dời sang đầu tuần sau.",
        ),
        # ══════════════════════════════════════════════════════════════════
        # NHÓM G — BẪY: CÓ NGÀY THÁNG NHƯNG KHÔNG PHẢI VIỆC PHẢI LÀM
        # → Q3. Đây là chỗ chứng minh bộ trích không nhận bừa mọi thứ có con số.
        # ══════════════════════════════════════════════════════════════════
        (
            "Nguyễn Hoàng Nam",
            f"Sinh nhật mình ngày {d(5)} nha",
            "Mình tổ chức nhỏ ở nhà thôi, hẹn gặp lại mọi người nha. Ai rảnh thì qua "
            "chơi, không cần mang gì cả.",
        ),
        (
            "Hệ thống HCMUS",
            f"Thông báo bảo trì hệ thống đêm {d(4)}",
            "Hệ thống sẽ tạm ngưng để bảo trì từ 23:00 đến 02:00. Trong thời gian này "
            "cổng thông tin không truy cập được. Thư này chỉ để thông báo.",
        ),
        # ══════════════════════════════════════════════════════════════════
        # NHÓM H — THƯ DÀI, GỬI CUỐI CÙNG nên là THƯ MỚI NHẤT
        # → Q9 "tóm tắt lá thư mới nhất"  · Q10 "tóm tắt thư này giúp tôi"
        # ĐỪNG ĐỔI CHỖ THƯ NÀY: câu hỏi bám vào việc nó đứng cuối.
        # ══════════════════════════════════════════════════════════════════
        (
            "Nguyễn Văn Sơn (GVHD)",
            "Biên bản họp hội đồng — những điểm nhóm cần sửa",
            "Chào các em,\n\n"
            "Thầy tóm tắt lại buổi họp hội đồng sáng nay để nhóm nắm.\n\n"
            "Thứ nhất, hội đồng đánh giá cao phần cổng xác nhận trước khi gửi thư. Đây là "
            "điểm nhóm nên nhấn mạnh khi bảo vệ, vì phần lớn các nhóm khác để mô hình gửi "
            "thẳng.\n\n"
            "Thứ hai, phần tài liệu kiến trúc còn mỏng. Hội đồng muốn thấy rõ ranh giới "
            "giữa phần nhóm tự viết và phần dùng thư viện, kèm lý do chọn từng thư viện. "
            "Các em bổ sung một sơ đồ thành phần và một đoạn giải thích quyết định thiết "
            "kế quan trọng nhất.\n\n"
            "Thứ ba, về kiểm thử: hội đồng hỏi khá kỹ chuyện đo độ phủ. Các em chuẩn bị "
            "số liệu thật, đừng nói chung chung. Nếu độ phủ chưa cao thì nói thẳng con số "
            "và giải thích phần nào chưa phủ được, như thế đáng tin hơn nhiều so với việc "
            "tránh câu hỏi.\n\n"
            "Cuối cùng, thầy nhắc lại là buổi bảo vệ chấm cả phần trả lời câu hỏi, không "
            "chỉ phần trình bày. Các em chia nhau nắm chắc từng phần để ai bị hỏi cũng "
            "trả lời được.\n\n"
            "Thầy Sơn",
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# BỘ THEO CÂU HỎI THẬT — dựng NGƯỢC từ prompt, không phải từ code
# ══════════════════════════════════════════════════════════════════════════════
# Các bộ trên dựng từ tính năng đang có: "app phân loại được 8 nhãn nên gieo thư cho
# đủ 8 nhãn". Cách đó cho một hộp thư đẹp mà rỗng nghĩa — nó chứng minh app chạy đúng
# thứ app đã làm, chứ không chứng minh nó trả lời được câu người ta thật sự hỏi.
#
# Bộ này đi ngược lại: viết câu hỏi của một sinh viên năm hai sắp bảo vệ TRƯỚC, rồi
# mới gieo đúng những lá thư khiến câu hỏi đó có câu trả lời. Vài lá cố ý mâu thuẫn
# nhau, vì đời thật là vậy — và một trợ lý chỉ giỏi khi dữ liệu sạch thì không giúp
# được ai.


def luong_giao_vu(moc: datetime | None = None) -> list[tuple[str, str, str]]:
    """MỘT cuộc trao đổi ba lượt, trong đó yêu cầu BỊ ĐỔI ở lượt cuối.

    Trả [(tên người gửi, tiêu đề, thân thư)] — lượt đầu gửi mới, hai lượt sau TRẢ LỜI
    vào đúng luồng đó (xem `gui_thu_demo.py --bo-prompt`).

    Đây là thứ mọi bộ thư trước đây thiếu: chúng chỉ có thư RỜI. Mà câu đáng giá nhất
    của một trợ lý thư lại là câu về một CHUỖI — "thầy có đổi yêu cầu gì so với lần
    trước không". Không có luồng thật thì câu đó không kiểm được, và tính năng xem hội
    thoại chỉ là một cái khung rỗng.
    """
    m = moc or datetime.now()
    t6 = (m + timedelta(days=2)).strftime("%d/%m")
    cn = (m + timedelta(days=4)).strftime("%d/%m")
    return [
        (
            "Phòng Giáo vụ FIT",
            "Nhắc nộp báo cáo cuối kỳ môn Nhập môn Công nghệ phần mềm",
            "Chào các em,\n\n"
            f"Phòng Giáo vụ nhắc các nhóm nộp BÁO CÁO CUỐI KỲ trước 23:59 thứ Sáu {t6}.\n\n"
            "Bản nộp gồm HAI tệp: bản PDF và bản Word. Đặt tên theo mẫu "
            "NhomXX_BaoCao_CuoiKy.\n\n"
            "Nhóm nào nộp trễ sẽ bị trừ 20% điểm báo cáo.\n\n"
            "Trân trọng,\nPhòng Giáo vụ — Khoa CNTT",
        ),
        (
            "Anh Quân",
            "Re: Nhắc nộp báo cáo cuối kỳ môn Nhập môn Công nghệ phần mềm",
            "Dạ em chào thầy/cô,\n\n"
            "Em là Phạm Trần Anh Quân, nhóm trưởng Nhóm 7 (MSSV 24127226). Em xin xác "
            "nhận nhóm em sẽ nộp đúng hạn ạ.\n\n"
            "Cho em hỏi thêm: phần phụ lục mã nguồn có cần in vào báo cáo không, hay chỉ "
            "cần để đường dẫn kho mã ạ?\n\n"
            "Em cảm ơn thầy/cô.",
        ),
        (
            "Phòng Giáo vụ FIT",
            "Re: Nhắc nộp báo cáo cuối kỳ môn Nhập môn Công nghệ phần mềm",
            "Chào em,\n\n"
            "CẬP NHẬT QUAN TRỌNG, các em đọc kỹ vì có thay đổi so với thông báo trước:\n\n"
            f"1. Hạn nộp DỜI sang 23:59 CHỦ NHẬT {cn} — muộn hơn hai ngày so với thông "
            "báo cũ.\n"
            "2. KHÔNG cần nộp bản Word nữa, chỉ nộp DUY NHẤT bản PDF.\n"
            "3. Phụ lục mã nguồn: chỉ cần để đường dẫn kho mã, không in vào báo cáo.\n\n"
            "Các em cập nhật lại cho cả nhóm nhé.\n\n"
            "Trân trọng,\nPhòng Giáo vụ — Khoa CNTT",
        ),
    ]


def bo_prompt(moc: datetime | None = None) -> list[tuple[str, str, str]]:
    """Thư nền cho bộ câu hỏi tầng 1–5. Mỗi lá phục vụ ít nhất một câu cụ thể."""
    m = moc or datetime.now()

    def ngay(d: int) -> str:
        return (m + timedelta(days=d)).strftime("%d/%m")

    return [
        # "học phí kỳ này đóng chưa, hạn nào" — số tiền và hạn phải RÕ, để trả lời được
        # thì phải ĐỌC đúng thư này chứ không đoán.
        (
            "Phòng Kế hoạch Tài chính",
            "Thông báo đóng học phí học kỳ 1 năm học 2026-2027",
            "Kính gửi sinh viên,\n\n"
            "Nhà trường thông báo mức học phí học kỳ 1 và thời hạn đóng như sau:\n\n"
            "- Sinh viên khoá 2024, ngành Công nghệ thông tin: 8.750.000 đồng\n"
            f"- Hạn đóng: trước 17:00 ngày {ngay(9)}\n"
            "- Hình thức: chuyển khoản qua cổng thanh toán của trường, nội dung ghi "
            "MSSV_HoTen\n\n"
            "Sinh viên quá hạn sẽ bị khoá tài khoản đăng ký học phần học kỳ sau.\n\n"
            "Phòng Kế hoạch Tài chính",
        ),
        # "có ai hẹn phỏng vấn không, ngày mấy"
        (
            "Tuyển dụng VNG",
            "Thư mời phỏng vấn vị trí Backend Intern — vòng 1",
            "Chào bạn Phạm Trần Anh Quân,\n\n"
            "Cảm ơn bạn đã ứng tuyển vị trí Backend Intern tại VNG. Chúng tôi mời bạn "
            "tham dự phỏng vấn vòng 1:\n\n"
            f"- Thời gian: 14:00 ngày {ngay(3)}\n"
            "- Hình thức: trực tuyến qua Google Meet, đường dẫn gửi trước 30 phút\n"
            "- Nội dung: hỏi về dự án cá nhân và kiến thức nền tảng\n\n"
            f"Bạn vui lòng xác nhận tham dự bằng cách trả lời thư này trước 17:00 ngày "
            f"{ngay(1)}.\n\n"
            "Trân trọng,\nBộ phận Tuyển dụng — VNG",
        ),
        # "mình sắp đi Đà Nẵng dự hội thảo — gom giúp vé, khách sạn, lịch"
        (
            "Ban tổ chức Hội thảo SE 2026",
            "Xác nhận tham dự Hội thảo Công nghệ phần mềm 2026 — Đà Nẵng",
            "Chào bạn,\n\n"
            "Ban tổ chức xác nhận bạn có tên trong danh sách tham dự Hội thảo Công nghệ "
            "phần mềm 2026.\n\n"
            f"- Thời gian: hai ngày {ngay(19)} và {ngay(20)}\n"
            "- Địa điểm: Đại học Bách khoa Đà Nẵng, 54 Nguyễn Lương Bằng\n"
            "- Bạn tự lo phương tiện và chỗ ở; ban tổ chức hỗ trợ 500.000đ chi phí đi lại\n\n"
            "Vui lòng có mặt trước 8:00 ngày đầu tiên để nhận thẻ.\n\n"
            "Ban tổ chức",
        ),
        # "có thư nào trông giống lừa đảo không" — dựng đúng các dấu hiệu kinh điển:
        # gấp gáp, doạ khoá tài khoản, tên miền lạ, đòi PIN và OTP.
        (
            "Ngan hang ACB Online",
            "KHAN: Tai khoan cua ban se bi khoa trong 24h",
            "Kinh gui Quy khach,\n\n"
            "He thong ghi nhan giao dich bat thuong tren tai khoan cua Quy khach. De "
            "tranh bi KHOA VINH VIEN trong 24 gio toi, Quy khach vui long xac thuc lai "
            "thong tin ngay:\n\n"
            "http://acb-verify-online.secure-login-vn.com/xacthuc\n\n"
            "Quy khach can cung cap: so the, ma PIN va ma OTP de he thong doi chieu.\n\n"
            "Tran trong,\nBo phan An ninh ACB",
        ),
        # "ai là người mình trao đổi nhiều nhất về đồ án" — ba lá cùng một người.
        (
            "Trần Minh Khoa",
            "Phần backend nhóm 7 — mình push nhánh feat/mcp rồi nhé",
            "Ê Quân,\n\n"
            "Mình vừa push nhánh feat/mcp lên rồi, bạn kéo về xem giúp phần đăng ký tool "
            "nhé. Mình có tách riêng phần xác thực ra file khác cho dễ đọc.\n\n"
            "Còn phần tài liệu kiến trúc thì mình chưa đụng, bạn với Mai chia nhau nha.\n\n"
            "Khoa",
        ),
        (
            "Trần Minh Khoa",
            "Vướng chỗ phân trang khi gọi Gmail",
            "Quân ơi,\n\n"
            "Mình vướng chỗ phân trang khi gọi Gmail: lấy quá 30 thư một lần là chậm hẳn. "
            "Bạn xem giúp mình có nên cache lại không, hay cứ để gọi thẳng?\n\n"
            "Tối nay mình rảnh từ 8h, gọi bàn nhanh được không?\n\n"
            "Khoa",
        ),
        (
            "Trần Minh Khoa",
            "Slide bảo vệ — mình làm xong phần kiến trúc rồi",
            "Quân,\n\n"
            "Mình làm xong 6 slide phần kiến trúc, để trong Drive chung. Bạn xem rồi góp "
            "ý giúp mình trước tối mai nhé, để còn kịp sửa.\n\n"
            "Phần demo thì bạn chạy hay mình chạy? Mình nghĩ bạn chạy sẽ hợp hơn vì bạn "
            "nắm phần giao diện.\n\n"
            "Khoa",
        ),
        (
            "Lê Thị Mai",
            "Mình gửi phần kiểm thử nhóm 7",
            "Chào Quân,\n\n"
            "Mình viết xong phần kiểm thử cho ba use case chính rồi. Độ phủ hiện tại "
            "khoảng 68%, mình đang bổ sung thêm cho nhánh xử lý lỗi.\n\n"
            "Bạn nhắc Khoa gửi mình phần backend cuối cùng để mình kiểm nốt nhé.\n\n"
            "Mai",
        ),
        # "sáng nay có gì gấp không" — một việc GẤP THẬT, hạn ngay trong ngày.
        (
            "Phòng Công tác Sinh viên",
            "Hạn chót hôm nay: đăng ký xét học bổng học kỳ 1",
            "Chào các em,\n\n"
            "Hôm nay là ngày cuối nhận hồ sơ xét học bổng khuyến khích học tập học kỳ 1. "
            "Hạn nộp: 17:00 hôm nay, nộp trực tiếp tại phòng A11 hoặc qua cổng sinh viên.\n\n"
            "Hồ sơ gồm: đơn đăng ký, bảng điểm học kỳ trước, giấy xác nhận hoạt động.\n\n"
            "Sau 17:00 hệ thống đóng, không nhận bổ sung.\n\n"
            "Phòng Công tác Sinh viên",
        ),
        # Thư đời thường — để câu "có gì gấp không" phải biết LOẠI TRỪ, chứ không liệt kê hết.
        (
            "Mẹ",
            "Con nhớ ăn uống đầy đủ nhé",
            "Con ơi,\n\n"
            "Mẹ chuyển cho con tiền sinh hoạt tháng này rồi nhé, con kiểm tra tài khoản "
            "xem đã nhận chưa.\n\n"
            "Con nhớ ăn sáng đầy đủ, đừng thức khuya quá. Cuối tuần rảnh thì gọi về cho "
            "mẹ.\n\n"
            "Mẹ",
        ),
        (
            "Phạm Thu Trang",
            "Chiều nay đi cà phê không",
            "Quân ơi rảnh chiều nay không, đi cà phê chỗ cũ đi. Mình có chuyện muốn kể.\n\n"
            "Trang",
        ),
    ]
