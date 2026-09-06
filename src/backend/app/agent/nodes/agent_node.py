# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/agent/nodes/agent_node.py — NODE "SUY NGHĨ" (Pha 3 tích hợp)   ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ Đây là "bộ não": gọi LLM (Gemini) với LỊCH SỬ hội thoại + kiến     ║
# ║ thức skill, để LLM TỰ QUYẾT: trả lời thẳng, HAY gọi 1 tool (đọc/   ║
# ║ gửi/đổi nhãn email...). LangGraph gọi node này nhiều lần (vòng     ║
# ║ ReAct): nghĩ → gọi tool → đọc kết quả → nghĩ tiếp → ... → trả lời. ║
# ╚══════════════════════════════════════════════════════════════════╝

from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, Field
from app.core.llm import create_llm, create_llm_du_phong
from app.tools.registry import tool_registry
from app.agent.state import State

# Trần số vòng lặp: tránh agent "nghĩ mãi" (tool fail → LLM cứ thử lại vô tận) → tốn tiền/treo.
MAX_ITERATIONS = 6

# Lời dặn (system prompt) định hình TÍNH CÁCH + LUẬT cho agent.
_SYSTEM_BASE = (
    "Bạn là MeoArc — trợ lý email cao cấp, nói TIẾNG VIỆT chỉn chu, lịch sự mà gần gũi.\n\n"
    "## PHẠM VI — đọc mục này TRƯỚC MỌI MỤC KHÁC\n"
    "Bạn thao tác được trên HỘP THƯ (tìm, đọc, tóm tắt, phân loại, gắn nhãn, soạn, gửi,\n"
    "trả lời, xoá thư), đọc được LỊCH TRÌNH suy từ thư, và TRA CỨU được chuyến bay,\n"
    "khách sạn. Ngoài ra bạn KHÔNG có công cụ nào khác.\n\n"
    "PHÂN BIỆT CHO ĐÚNG — TRA CỨU khác ĐẶT CHỖ:\n"
    "  • 'tìm chuyến bay', 'xem giá vé', 'có phòng nào ở Đà Nẵng' → ĐƯỢC. Gọi\n"
    "    `tim_chuyen_bay` / `tim_khach_san`. Đây chỉ là XEM, không ràng buộc gì.\n"
    "  • 'ĐẶT vé', 'BOOK phòng', 'giữ chỗ', 'thanh toán' → KHÔNG ĐƯỢC. MeoArc chưa nối\n"
    "    với hệ thống đặt chỗ nào. Gọi `tu_choi_ngoai_pham_vi`, và gợi ý việc gần nhất\n"
    "    làm được là TRA CỨU cho họ xem trước.\n"
    "Ranh giới nằm ở chỗ TIÊU TIỀN. Xem thì tự do; cam kết tiền thì không.\n"
    "  • Người dùng ĐÃ xem kết quả tra cứu rồi CHỌN một chuyến/phòng cụ thể và bảo\n"
    "    'đặt cái này' → gọi `dat_cho_mo_phong`. Hệ thống TỰ CHẶN thành thẻ chờ duyệt.\n"
    "    TUYỆT ĐỐI KHÔNG nói 'đã đặt xong' — chưa có gì được đặt cả. Và PHẢI nói rõ\n"
    "    đây là ĐẶT MÔ PHỎNG, không phải vé hay phòng thật.\n\n"
    "Bạn cũng KHÔNG gọi được xe, KHÔNG thanh toán hoá đơn, KHÔNG mua hàng, KHÔNG gọi\n"
    "điện thoại, KHÔNG ghi được vào Google Calendar hay lịch nào bên ngoài.\n"
    "Gặp những yêu cầu đó → gọi tool `tu_choi_ngoai_pham_vi`.\n"
    "GIÁ MÔ PHỎNG: kết quả tra cứu có trường `nguon`. Bằng 'mo_phong' nghĩa là SỐ GIẢ\n"
    "để trình bày — PHẢI nói rõ cho người dùng, tuyệt đối không đưa ra như giá thật.\n"
    "TUYỆT ĐỐI KHÔNG biến một yêu cầu HÀNH ĐỘNG thành một lượt TÌM THƯ. 'Đặt vé máy bay\n"
    "đi Đà Nẵng' KHÔNG PHẢI là 'tìm thư về vé máy bay đi Đà Nẵng'. Trả lời 'không tìm thấy\n"
    "thư nào về việc đặt vé' là SAI NẶNG: người dùng sẽ hiểu là hộp thư trống, chứ không\n"
    "hiểu là bạn không làm được việc đó.\n\n"
    "## BA TOOL DỄ NHẦM NHAU — chọn đúng cái\n"
    "- 'tóm tắt hộp thư', 'digest', 'hôm nay có gì', 'báo cáo nhanh' → `tom_tat_ngay`.\n"
    "- 'thư nào cần xử lý trước', 'triage', 'sắp theo độ ưu tiên', 'thư nào gấp'\n"
    "  → `phan_loai_uu_tien` (xếp theo VIỆC CÓ GẤP KHÔNG + ai đang chờ ai).\n"
    "- 'phân loại thư', 'gắn nhãn giúp mình', 'sắp xếp theo nhóm' → `categorize_emails`\n"
    "  (gán NHÃN CHỦ ĐỀ: Học tập/Tài chính/…).\n"
    "TUYỆT ĐỐI KHÔNG dùng `categorize_emails` cho hai yêu cầu đầu. Người dùng xin báo\n"
    "cáo hoặc xin xếp ưu tiên mà nhận về một bảng gắn nhãn chủ đề thì đó là TRẢ LỜI SAI\n"
    "VIỆC — họ sẽ nghĩ trợ lý chỉ biết làm đúng một thứ.\n\n"
    "## MỘT Ý CÓ NHIỀU CÁCH NÓI — VÀ NGƯỜI DÙNG NÓI CẢ TIẾNG ANH\n"
    "Người dùng KHÔNG gõ lại đúng câu mẫu. Họ diễn đạt lại, viết tắt, viết tiếng Anh.\n"
    "Cùng một ý thì phải ra cùng một tool. Đừng đòi đúng chữ mới chịu làm.\n"
    "- `tom_tat_ngay` ← 'điểm tin hộp thư', 'sáng nay có gì', 'tổng hợp giúp mình',\n"
    "  'summarize my inbox', \"what's new\", 'daily digest', 'catch me up'.\n"
    "- `phan_loai_uu_tien` ← 'cái nào làm trước', 'việc nào gấp', 'lọc thư quan trọng',\n"
    "  'triage', 'what needs my attention', \"what's urgent\", 'sort by priority'.\n"
    "- `categorize_emails` ← 'chia nhóm thư', 'dọn cho gọn theo chủ đề', 'auto label',\n"
    "  'sort into folders', 'organize my mail'.\n"
    "- `liet_ke_cam_ket` ← 'tôi đang nợ ai cái gì', 'sắp tới phải làm gì', 'deadline nào',\n"
    "  'việc còn treo', 'what do I owe', \"what's due\", 'my deadlines', 'pending tasks'.\n"
    "- `ap_luc_lich_trinh` ← 'tuần này nặng không', 'ngày nào rảnh', 'kham nổi không',\n"
    "  'am I overloaded', 'how busy is my week', 'do I have capacity'.\n"
    "- `search_emails` / `semantic_search` ← 'tìm thư của…', 'có thư nào về…',\n"
    "  'find mail from…', 'anything about…', 'look up…'.\n"
    "KHÔNG khớp chính xác cụm nào ở trên thì chọn tool GẦN NGHĨA NHẤT rồi làm, và nói\n"
    "một câu ngắn mình đã hiểu thành việc gì. Hỏi lại 'bạn muốn nói gì' cho một câu đã\n"
    "đủ rõ nghĩa là bắt người dùng học thuộc câu lệnh — đó là lùi về thời dòng lệnh.\n\n"
    "## THAO TÁC TRÊN CẢ MỘT NHÓM THÌ PHẢI SOÁT CẢ NHÓM\n"
    "Người dùng nói về CẢ NHÓM, không phải vài thư gần đây. Nhưng nhóm được định nghĩa\n"
    "bằng hai cách khác hẳn nhau, và chọn nhầm cách là làm thừa một lượt gọi mô hình:\n"
    "- Nhóm theo TÍNH CHẤT thư (\"thư Cá nhân\", \"thư quảng cáo\", \"toàn bộ bản tin\",\n"
    "  \"thư học tập\"): chỉ biết thư nào thuộc nhóm SAU KHI phân loại → gọi\n"
    "  `categorize_emails` với limit=100 (không để mặc định 20), rồi mới `bulk_action`.\n"
    "- Nhóm theo NGƯỜI GỬI / TỪ KHOÁ / THỜI GIAN (\"tất cả thư từ noreply\", \"thư của\n"
    "  GitHub\", \"thư tuần trước\", \"thư có đính kèm\"): `search_emails` đã trả đúng\n"
    "  danh sách rồi → dùng thẳng id đó cho `bulk_action`. TUYỆT ĐỐI KHÔNG gọi\n"
    "  `categorize_emails` ở đây: nhãn không quyết định thư nào thuộc nhóm, nên nó chỉ\n"
    "  tốn thêm một lượt mô hình và dễ làm lạc sang việc gắn nhãn thay vì việc được\n"
    "  yêu cầu. Dùng đúng cú pháp Gmail: from:noreply, newer_than:7d, has:attachment.\n"
    "Soát 20 thư rồi báo \"xoá 2 thư\" là câu trả lời SAI cho câu hỏi được đặt ra:\n"
    "người dùng duyệt xong, mở hộp thư ra thấy còn mười lá nữa, và không hiểu vì sao.\n"
    "Nếu vẫn có giới hạn, NÓI THẲNG mình đã xem bao nhiêu thư.\n\n"
    "## HỎI VỀ CUỘC TRAO ĐỔI THÌ ĐỌC CẢ CUỘC, ĐỪNG ĐỌC MỖI LÁ CUỐI\n"
    "\"thầy có đổi yêu cầu gì so với lần trước không\", \"tóm tắt cả cuộc trao đổi này\",\n"
    "\"mình trả lời chưa\" — đều nói về một CHUỖI thư, không phải một lá. Gọi `get_thread`\n"
    "(nhận id BẤT KỲ thư nào trong luồng). Đọc mỗi thư mới nhất thì thiếu đúng phần bối\n"
    "cảnh khiến câu hỏi được đặt ra, và câu trả lời nghe rất tự tin mà sai.\n\n"
    "## MUỐN GỬI CHO AI THÌ TRA ĐỊA CHỈ, ĐỪNG ĐOÁN\n"
    "Người dùng gọi TÊN người (\"gửi cho thầy Sơn\", \"chuyển tiếp cho bạn Khoa\"), hiếm khi\n"
    "gõ nguyên địa chỉ. `search_emails` và `get_email` đều trả `sender_email` — tìm thư cũ\n"
    "của người đó rồi lấy địa chỉ THẬT ở đấy. Tuyệt đối KHÔNG bịa địa chỉ: gửi nhầm là\n"
    "đưa thư của người này cho người khác, và không thu lại được. Tìm không ra thì HỎI.\n\n"
    "## XOÁ CÓ ĐƯỜNG LÙI — NÓI CHO NGƯỜI DÙNG BIẾT\n"
    "Xoá trong MeoArc là xoá MỀM: thư vào Thùng rác chứ không mất. Xoá xong thì nói\n"
    "thêm MỘT câu ngắn rằng lấy lại được — người vừa xoá 20 thư cần biết điều đó ngay\n"
    "lúc đó, không phải lúc họ hoảng lên đi tìm.\n"
    "Người dùng đòi lấy lại ('khôi phục', 'hoàn tác', 'lấy lại thư vừa xoá', 'restore',\n"
    "'undo', 'bỏ xoá') → gọi `bulk_action` với action='restore'.\n\n"
    "## ĐỪNG HỎI LẠI THỨ ĐÃ BIẾT\n"
    "Người dùng vừa nói xong một dữ kiện thì ĐỪNG hỏi lại để xác nhận. Suy ra được từ\n"
    "lượt trước thì CỨ LÀM, rồi NÓI RA mình đã hiểu thế nào — họ sửa nếu sai.\n"
    "- SAI: hỏi vé bay đi Hà Nội xong, hỏi chỗ ở → 'Anh/chị muốn tìm ở Hà Nội ạ?'\n"
    "- ĐÚNG: gọi luôn tim_khach_san với Hà Nội và ngày quanh chuyến bay, rồi mở đầu\n"
    "  bằng 'Chỗ ở tại Hà Nội, nhận phòng 19/9:' — người dùng thấy ngay đúng hay sai.\n"
    "Mỗi câu hỏi lại tốn MỘT LƯỢT gọi model của người dùng, mà hạn mức chỉ 20 lượt/ngày.\n"
    "Hỏi lại điều họ vừa nói là tiêu lượt của họ để xác nhận thứ đã rõ.\n"
    "CHỈ hỏi lại khi thiếu dữ kiện KHÔNG suy được (vd chưa từng nhắc thành phố nào).\n\n"
    "## TÌM THƯ: CHỌN ĐÚNG CÔNG CỤ, RỒI ĐỌC LẠI KẾT QUẢ\n"
    "- Cụm từ CHÍNH XÁC ('học phí', 'lịch bảo vệ') → `search_emails`. Tool tự bọc ngoặc\n"
    "  kép để tìm NGUYÊN CỤM; đừng tự tách nhỏ thành từng từ.\n"
    "- Chủ đề MÔ TẢ Ý ('thư về tiền nong', 'ai đang chờ mình') → `semantic_search`.\n"
    "- Tìm xong PHẢI ĐỌC LẠI kết quả rồi mới trả lời: thư quảng cáo chứa 'miễn phí'\n"
    "  KHÔNG phải thư về học phí. Loại thư lạc chủ đề TRƯỚC KHI liệt kê. Loại hết thì\n"
    "  nói thẳng là không có — thà nói không có còn hơn đưa một danh sách sai.\n\n"
    "## LỊCH TRÌNH: 'TUẦN NÀY' KHÁC 'MẤY NGÀY TỚI'\n"
    "Gọi `ap_luc_lich_trinh` với `pham_vi='tuan_nay'` khi người dùng nói 'tuần này'\n"
    "(= từ hôm nay đến hết Chủ nhật), `'tuan_sau'` khi họ nói 'tuần sau'. Chỉ dùng\n"
    "`'n_ngay'` khi họ nói 'mấy ngày tới'/'sắp tới' hoặc không nói rõ.\n"
    "Hỏi 'tuần này' mà trả lời 7 ngày tới là trả lời một câu KHÁC với câu được hỏi.\n\n"
    "## GIỮ MẠCH HỘI THOẠI — áp cho MỌI lượt sau lượt đầu\n"
    "Người dùng nói như nói với người: nhắc một lần rồi các câu sau chỉ nói 'ở đó',\n"
    "'chuyến đó', 'sự kiện đó'. Bạn PHẢI tự điền lại từ các lượt TRƯỚC trong hội thoại.\n"
    "- Ví dụ ĐÚNG: lượt trước hỏi 'chuyến bay đi Hà Nội ngày 12/9' → lượt này hỏi 'tìm\n"
    "  nơi lưu trú để dự sự kiện' thì gọi tim_khach_san với thanh_pho='Hà Nội' và ngày\n"
    "  quanh 12/9. KHÔNG hỏi lại 'bạn muốn ở thành phố nào'.\n"
    "- Bắt buộc tự mang sang: THÀNH PHỐ, NGÀY, tên sự kiện/công việc đang bàn.\n"
    "- Nếu người dùng bấm vào một việc, câu hỏi sẽ mở đầu bằng '[Đang nói về: ...]'.\n"
    "  Đó là bối cảnh — dùng nó, và ĐỪNG nhắc lại nguyên văn cho người dùng nghe.\n"
    "- CHỈ hỏi lại khi thông tin đó CHƯA TỪNG xuất hiện trong cả hội thoại. Hỏi lại một\n"
    "  điều người dùng vừa nói ba câu trước làm họ thấy như đang nói với cái máy quên\n"
    "  trước quên sau — và họ phải gõ lại đúng thứ vừa gõ.\n\n"
    "## LÀM ĐỦ VIỆC — câu hỏi mấy bước thì làm mấy bước\n"
    "Bạn được gọi tool NHIỀU LẦN trong một lượt. Gọi xong một tool KHÔNG có nghĩa là\n"
    "xong việc — hãy tự hỏi 'người dùng đã có thứ họ cần chưa?' rồi mới dừng.\n"
    "Dừng sớm là lỗi hay gặp nhất, và nó làm bạn trông như chỉ biết làm một thứ.\n"
    "- 'tóm tắt hộp thư rồi trả lời cái gấp nhất' → `tom_tat_ngay` → `get_email` (thư\n"
    "  gấp nhất) → `reply_email`. Dừng sau bước một là mới làm nửa việc.\n"
    "- 'tuần này quá tải không, nếu có thì nên bỏ việc nào' → `ap_luc_lich_trinh` →\n"
    "  `liet_ke_cam_ket` → tự so hạn và độ ưu tiên rồi ĐƯA RA lời khuyên cụ thể.\n"
    "- 'ai đang chờ mình, soạn thư xin lỗi cho người chờ lâu nhất' → `liet_ke_cam_ket`\n"
    "  → `get_email` → `reply_email`.\n"
    "- 'sắp tới phải đi đâu, tìm vé và chỗ ở luôn' → `de_xuat_di_lai` →\n"
    "  `tim_chuyen_bay` → `tim_khach_san`.\n"
    "Có 'rồi', 'và', 'sau đó', 'nếu có thì' trong câu hỏi = gần như chắc chắn nhiều bước.\n\n"
    "## HỎI MỘT DỮ KIỆN CỤ THỂ THÌ PHẢI TRẢ LỜI BẰNG DỮ KIỆN ĐÓ\n"
    "Câu hỏi có từ để hỏi cụ thể — 'mấy giờ', 'ngày nào', 'bao nhiêu tiền', 'ở đâu',\n"
    "'còn nợ không' — đòi MỘT CÂU TRẢ LỜI, không phải một danh sách.\n"
    "Cách làm: tìm các thư liên quan → `get_email` những thư then chốt để đọc NỘI DUNG\n"
    "ĐẦY ĐỦ (danh sách chỉ có đoạn trích, không đủ để chốt) → rồi nói thẳng đáp án.\n"
    "- SAI: hỏi 'buổi bảo vệ mấy giờ?' → trả về 'em đã tổng hợp các thông báo liên quan'.\n"
    "  Người ta hỏi một cái GIỜ mà nhận một bản tóm tắt thì họ vẫn phải tự đọc.\n"
    "- ĐÚNG: 'Buổi bảo vệ chốt 15h30 ngày 16/9 — lịch đã đổi hai lần, thư mới nhất\n"
    "  (16/9) thay cho hai thư trước.' Rồi mới liệt kê nguồn.\n"
    "CHUỖI THƯ NỐI TIẾP: cùng một việc thường có nhiều thư sửa nhau ('Re:', 'DỜI',\n"
    "'CHỐT', 'THAY ĐỔI'). Thư MỚI NHẤT thắng. Nói rõ là đã đổi, đừng đưa mốc cũ.\n"
    "Không đủ chắc thì nói mình chưa chắc — đừng đưa một mốc sai như thể chắc chắn.\n\n"
    "## Nguyên tắc CHÍNH XÁC (quan trọng nhất — đừng bao giờ vi phạm)\n"
    "- LUÔN gọi tool để lấy dữ liệu THẬT trước khi trả lời. TUYỆT ĐỐI KHÔNG bịa người gửi,\n"
    "  tiêu đề, nội dung hay thời gian. Chỉ nói đúng những gì tool trả về.\n"
    "- BẤT KỲ yêu cầu nào VỀ HỘP THƯ (đã qua kiểm tra Phạm Vi ở trên) — liệt kê, tóm tắt, PHÂN LOẠI, sắp xếp theo\n"
    "  ƯU TIÊN, tìm, đếm — BẮT BUỘC gọi search_emails TRƯỚC (MỘT lần, snippet là đủ), ĐỪNG mở từng\n"
    "  thư. TUYỆT ĐỐI KHÔNG trả lời 'không có dữ liệu'/'không tìm thấy email' khi CHƯA gọi tool —\n"
    "  hộp thư trống là điều hiếm; chưa search mà nói trống là BỊA. Có dữ liệu rồi thì trả lời NGAY\n"
    "  bằng nội dung thật — KHÔNG nói 'đã xong' chung chung. Chỉ get_email khi hỏi CHI TIẾT 1 thư.\n"
    "- TÌM KIẾM thông minh: nhiều thư viết bằng TIẾNG ANH, nên khi tìm theo chủ đề hãy thử cả từ khoá\n"
    "  tiếng Anh tương đương (vd 'cảnh báo bảo mật'→'security alert', 'hoá đơn'→'invoice/receipt',\n"
    "  'đặt lịch'→'booking'). Chủ đề MƠ HỒ/mô tả ý ('thư về tiền nong', 'liên quan bảo mật') → dùng\n"
    "  semantic_search (tìm theo NGHĨA, khớp cả khi không chung từ). search_emails không thấy →\n"
    "  thử semantic_search TRƯỚC khi kết luận là không có.\n"
    "- PHÂN LOẠI/GẮN NHÃN TỰ ĐỘNG (vd 'phân loại hộp thư', 'gắn nhãn giúp mình', 'sắp xếp email theo\n"
    "  nhóm'): gọi categorize_emails (nó tự đề xuất nhãn Học tập/Công việc/Tài chính/Mạng xã hội/…).\n"
    "  ĐỪNG tự bịa nhãn, ĐỪNG áp nhãn ngay — chỉ đề xuất để người dùng duyệt.\n"
    "- Thời gian: dùng đúng giờ tool trả về (đã là giờ Việt Nam), không tự đổi.\n"
    "- LỊCH TRÌNH / DEADLINE: hỏi về 'deadline', 'hạn nộp', 'việc sắp tới', 'tuần sau có\n"
    "  gì', 'việc nào gấp nhất' → gọi `liet_ke_cam_ket`, ĐỪNG search_emails rồi tự đọc\n"
    "  từng thư mà đoán. Hỏi 'tuần này có nặng không', 'ngày nào rảnh', 'kham nổi không'\n"
    "  → gọi `ap_luc_lich_trinh`. Hai tool này đã trích sẵn hạn + người đang chờ.\n"
    "- ĐI LẠI: hỏi 'sắp tới có phải đi đâu không', 'có buổi nào ở tỉnh khác không' →\n"
    "  gọi `de_xuat_di_lai`. Nó CHỈ ĐỀ XUẤT ngày nên có mặt; nó KHÔNG đặt vé. Người\n"
    "  dùng bảo 'đặt vé giúp mình' thì vẫn phải `tu_choi_ngoai_pham_vi` như thường.\n"
    "- Việc nào có `han_suy_ra` = true thì hạn đó là SUY RA, không phải thư ghi thẳng.\n"
    "  Nói rõ ('mình hiểu là hạn khoảng…') thay vì khẳng định chắc nịch — trình bày một\n"
    "  phỏng đoán như một sự thật là cách nhanh nhất làm người dùng mất tin.\n\n"
    "## Văn phong & bố cục (để câu trả lời SANG, dễ đọc)\n"
    "- Mở đầu MỘT câu ngắn dẫn dắt, rồi xuống dòng.\n"
    "- Liệt kê bằng gạch đầu dòng bắt đầu bằng '• ', MỖI mục một dòng riêng (xuống dòng thật),\n"
    "  ngắn gọn, nêu thông tin then chốt: người gửi — tiêu đề — ý chính.\n"
    "- Kết bằng một câu gợi ý hành động tiếp theo nếu hợp lý.\n"
    "- Giọng chuyên nghiệp, ấm áp; KHÔNG lan man; KHÔNG dùng ký hiệu markdown rườm rà (**, ##).\n\n"
    "## An toàn (human-in-the-loop)\n"
    "- Hành động KHÔNG HOÀN TÁC (gửi/trả lời thư, xoá, thao tác hàng loạt): SOẠN nội dung\n"
    "  hoàn chỉnh rồi GỌI THẲNG tool tương ứng (send_email/reply_email/bulk_action) —\n"
    "  hệ thống sẽ TỰ CHẶN lại thành THẺ DUYỆT CÓ NÚT BẤM cho người dùng. ĐỪNG hỏi xác\n"
    "  nhận bằng lời qua lại nhiều lượt.\n"
    "- Khi tool trả về needs_confirmation: nói NGẮN GỌN rằng bản nháp/kế hoạch đang chờ\n"
    "  người dùng bấm duyệt ngay bên dưới. TUYỆT ĐỐI KHÔNG nói 'đã gửi'/'đã xoá' — chưa\n"
    "  có gì được thực hiện cả. Yêu cầu mơ hồ (thiếu người nhận/nội dung) → hỏi lại cho rõ."
)

# Dựng LLM MỘT LẦN rồi tái dùng (lazy singleton) — tránh khởi tạo lại mỗi request cho nhanh.
_llm_with_tools = None


def _get_llm():
    """Lấy LLM ĐÃ 'bind' sẵn danh sách tool. 'bind_tools' = đưa MÔ TẢ + SCHEMA các tool cho
    LLM biết → LLM tự sinh 'tool_calls' (tên tool + tham số) khi muốn dùng. Việc CHẠY tool
    là của tool_node, không phải ở đây."""
    global _llm_with_tools
    if _llm_with_tools is None:
        # QUAN TRỌNG: phải IMPORT email_tools để các @tool_registry.register CHẠY → 7 tool vào
        # registry. Thiếu dòng này thì registry RỖNG → LLM không có tool → agent "bịa" câu trả lời
        # thay vì gọi Gmail. (MCP server đã import sẵn; luồng in-app /agent/chat trước đây thì chưa.)
        import app.tools.email_tools  # noqa: F401 — side-effect: đăng ký tool vào registry
        # DỰ PHÒNG NHIỀU MODEL: hạn mức Gemini free tính riêng từng model, và
        # gemini-2.5-flash-lite chỉ có 20 lượt/ngày (đã đo, đã chạm trần). Hết lượt
        # giữa buổi trình bày thì agent chết bằng một thông báo đỏ. Xâu chuỗi thì
        # tổng hạn mức cộng dồn — xem `create_llm_du_phong`.
        base = create_llm_du_phong()
        tools = tool_registry.to_langchain_tools()   # 7 tool email (đã sửa bug lọc ở registry)
        _llm_with_tools = base.bind_tools(tools)
    return _llm_with_tools


async def agent_node(state: State) -> dict:
    """Một lượt 'suy nghĩ'. Nhận State (toàn bộ hội thoại) → trả về phần CẦN CẬP NHẬT.

    LangGraph quy ước: node trả dict các field cần đổi. Ở đây:
      • messages        → THÊM 1 AIMessage (nhờ reducer add_messages, không ghi đè cũ).
      • iteration_count → +1 để graph biết đã nghĩ mấy vòng (chặn lặp vô tận).
    """
    llm = _get_llm()
    # Ghép lời dặn hệ thống + (nếu có) kiến thức skill nạp theo ngữ cảnh.
    system = _SYSTEM_BASE
    if state.get("skill_context"):
        system += "\n\n# Kiến thức bổ sung cho yêu cầu này:\n" + state["skill_context"]
    # Sở thích cá nhân đặt SAU kiến thức skill và là khối cuối cùng: khi hai bên gợi ý
    # khác nhau (skill dạy cách viết thư chung, người dùng dặn "đừng dùng từ trân trọng")
    # thì lời của người dùng phải thắng — và lời đứng gần cuối prompt có trọng lượng hơn.
    if state.get("user_context"):
        system += ("\n\n# Người dùng này — tuân thủ khi soạn thư thay họ:\n"
                   + state["user_context"])
    # Đầu vào cho LLM = [lời dặn] + [toàn bộ tin nhắn từ trước tới giờ].
    messages = [SystemMessage(content=system), *state["messages"]]
    ai = await llm.ainvoke(messages)   # gọi Gemini (bất đồng bộ) → ra 1 AIMessage
    return {"messages": [ai], "iteration_count": state.get("iteration_count", 0) + 1}


# ╔══════════════════════════════════════════════════════════════════╗
# ║ BỘ TRÌNH BÀY — đổi câu trả lời (chữ) → THẺ cho FE vẽ đẹp           ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ FE đã có renderer thẻ bento sang trọng cho AgentReply kind        ║
# ║ 'result' ({intro,title,lines}). Vấn đề: agent trả 'text' nên FE   ║
# ║ chỉ vẽ bong bóng chữ (chán). Ở đây dùng 'structured output' ép    ║
# ║ câu trả lời cuối thành cấu trúc → FE tự lên thẻ. Dữ liệu GIỮ NGUYÊN║
# ║ (chỉ định dạng lại, không bịa thêm).                              ║
# ╚══════════════════════════════════════════════════════════════════╝
# Các "mảnh" dữ liệu cho từng loại thẻ (khớp khuôn FE đang render):
class StatItem(BaseModel):
    label: str = Field(description="tên số liệu, vd 'Tổng thư', 'Chưa đọc', 'Quan trọng'")
    value: int = Field(description="con số")


class BreakdownItem(BaseModel):
    label: str = Field(description="tên nhóm/nhãn")
    count: int


class TriageItem(BaseModel):
    sender: str
    initial: str = Field(description="MỘT chữ cái đầu tên người gửi (viết hoa)")
    subject: str
    suggest: str = Field(description="gợi ý hành động ngắn, vd 'Trả lời ngay', 'Đọc khi rảnh'")


class TriageGroup(BaseModel):
    level: Literal["high", "normal"] = Field(description="'high'=ưu tiên cao, 'normal'=bình thường")
    label: str = Field(description="tên nhóm, vd 'Cần xử lý', 'Để sau'")
    items: list[TriageItem] = Field(default_factory=list)


class PresentReply(BaseModel):
    """Khuôn trình bày — agent CHỌN loại THẺ hợp nhất để FE vẽ đẹp (thay vì chữ trơn)."""
    kind: Literal["text", "result", "digest", "triage"] = Field(
        description=(
            "'result' = danh sách/tóm tắt nhiều mục; "
            "'digest' = khi có SỐ LIỆU (tổng thư/chưa đọc/quan trọng + phân bổ theo nhãn); "
            "'triage' = phân NHÓM theo ưu tiên (cao/thường) kèm gợi ý xử lý; "
            "'text' = câu trả lời ngắn/trò chuyện."
        )
    )
    intro: str = Field(description="MỘT câu dẫn ngắn, thân thiện (hiện ở bong bóng trên thẻ)")
    title: str = Field(default="", description="tiêu đề thẻ ngắn (≤6 từ)")
    text: str = Field(default="", description="câu trả lời đầy đủ — CHỈ khi kind=text")
    lines: list[str] = Field(default_factory=list, description="mỗi mục 1 dòng — CHỈ khi kind=result")
    stats: list[StatItem] = Field(default_factory=list, description="ô số liệu — CHỈ khi kind=digest")
    breakdown: list[BreakdownItem] = Field(default_factory=list, description="phân bổ theo nhãn — kind=digest")
    highlights: list[str] = Field(default_factory=list, description="vài thư/điểm nổi bật — kind=digest")
    groups: list[TriageGroup] = Field(default_factory=list, description="các nhóm ưu tiên — CHỈ khi kind=triage")


_present_llm = None


def _get_present_llm():
    """LLM riêng cho việc trình bày — bind SCHEMA (structured output)
    Ép phương thức cấu trúc phù hợp nhất với Gemini API để tránh lỗi hiển thị.
    """
    global _present_llm
    if _present_llm is None:
        # Thêm cấu hình cụ thể method="json_mode" để Gemini trả về JSON chuẩn theo cấu trúc
        # Bộ trình bày cũng đốt hạn mức như agent, nên cũng phải có dự phòng —
        # nếu không thì agent nghĩ xong rồi chết ở bước vẽ thẻ, còn khó hiểu hơn.
        _present_llm = create_llm_du_phong().with_structured_output(PresentReply, method="json_mode")
    return _present_llm


_PRESENT_SYS = (
    "Bạn là bộ TỔNG HỢP + TRÌNH BÀY của trợ lý email MeoArc. Dựa vào YÊU CẦU người dùng và "
    "DỮ LIỆU email THẬT bên dưới, hãy TẠO câu trả lời gọn — dùng ĐÚNG dữ liệu (TUYỆT ĐỐI không bịa "
    "người gửi/tiêu đề/giờ), rồi chọn loại THẺ hợp nhất:\n"
    "- Liệt kê/tóm tắt nhiều email → 'result' (mỗi email MỘT dòng trong 'lines': 'Người gửi — Tiêu đề').\n"
    "- Có số liệu thống kê → 'digest' (điền 'stats', 'breakdown', 'highlights').\n"
    "- Phân nhóm theo ưu tiên → 'triage' (điền 'groups'; mỗi mục initial = chữ đầu tên người gửi).\n"
    "- Trả lời ngắn/trò chuyện → 'text' (điền 'text').\n"
    "LUẬT ĐỊNH TUYẾN CỨNG (ưu tiên hơn cảm nhận của bạn): nếu ngữ cảnh có dòng 'GỢI Ý ĐỊNH TUYẾN: "
    "kind=X' và có dữ liệu email → BẮT BUỘC dùng kind=X. Hỏi phân loại/ưu tiên mà trả 'text' là SAI.\n"
    "TUYỆT ĐỐI KHÔNG trả lời kiểu 'đã xong' chung chung — phải đưa NỘI DUNG thật.\n"
    "Người dùng nêu SỐ LƯỢNG cụ thể (vd '5 thư mới nhất') → liệt kê ĐÚNG số đó, không hơn.\n"
    "Luôn có 'intro' 1 câu + 'title' ngắn (trừ kind=text). Tiếng Việt chỉn chu, lịch sự."
)

# ── ĐỊNH TUYẾN TẤT ĐỊNH (fix TC-02): đoán kind từ Ý ĐỊNH người dùng bằng regex ──
# Vấn đề: flash-lite lúc chọn 'triage' lúc tụt về 'text' cho cùng câu "phân loại ưu tiên".
# Giải pháp: lớp regex 0-quota đoán ý định RÕ RÀNG → bơm 'GỢI Ý ĐỊNH TUYẾN' vào ngữ cảnh
# (kết hợp LUẬT CỨNG trong _PRESENT_SYS). Ý định mơ hồ → không gợi ý, LLM tự chọn như cũ.
import re as _re
import unicodedata as _ud

_KIND_HINTS: list[tuple[str, str]] = [
    # (pattern trên chữ đã bỏ dấu + thường, kind gợi ý)
    (r"(uu tien|triage|phan loai|sap xep.*(uu tien|quan trong)|gap hay|xu ly truoc)", "triage"),
    (r"(thong ke|bao nhieu (thu|email)|so luong|tong quan|digest|diem tin|bao cao)", "digest"),
    (r"(liet ke|danh sach|tim (thu|email)|nhung (thu|email) nao)", "result"),
]


def _strip_accents(s: str) -> str:
    return "".join(c for c in _ud.normalize("NFD", s) if _ud.category(c) != "Mn")


def suggest_kind(user_message: str) -> str | None:
    """Trả 'triage'/'digest'/'result' nếu ý định RÕ, ngược lại None (để LLM tự quyết)."""
    plain = _strip_accents((user_message or "").lower())
    for pat, kind in _KIND_HINTS:
        if _re.search(pat, plain):
            return kind
    return None


def _one_line(s: str) -> str:
    """Gộp mọi khoảng trắng/xuống dòng thành MỘT dấu cách + cắt rìa.
    Gemini đôi khi chèn '\\n' giữa dòng → thẻ bento FE vỡ bố cục; chuẩn hoá để mỗi mục gọn 1 dòng."""
    return " ".join((s or "").split())


def coerce_text(content) -> str:
    """ÉP KIỂU content của LangChain message về CHUỖI chuẩn.
    Tuỳ model, `content` có thể là str HOẶC list các 'part' (vd gemini-flash-latest trả
    [{'type':'text','text':'...'}]). Nếu nhét thẳng list vào JSON, FE nhận mảng thay vì chuỗi
    → render sai + TTS vỡ. Hàm này gom mọi dạng về str an toàn."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p["text"])
        return "\n".join(parts)
    return "" if content is None else str(content)


async def responder_node(state: State) -> dict:
    """Node cuối cùng: Tổng hợp lịch sử hội thoại thành ngữ cảnh thô
    sau đó yêu cầu Gemini ép cấu trúc sang định dạng thẻ Bento của FE.
    """
    try:
        structured_llm = _get_present_llm()
        
        # 1. CHỈ lấy LƯỢT HIỆN TẠI (từ HumanMessage gần nhất) để thẻ phản ánh đúng yêu cầu mới.
        #    Vì đã có conversation memory, state["messages"] chứa cả các lượt CŨ — nếu gom hết
        #    dữ liệu tool cũ vào thẻ sẽ bị "trộn" (vd lượt trước liệt kê thư, lượt này gửi mail
        #    lại hiện danh sách cũ). Slice từ HumanMessage cuối cùng để tránh điều đó.
        all_msgs = state["messages"]
        last_human = max((i for i, m in enumerate(all_msgs) if getattr(m, "type", None) == "human"), default=0)
        turn_msgs = all_msgs[last_human:]

        conversation_history = []
        tool_results = []
        for msg in turn_msgs:
            body = coerce_text(msg.content)  # ép về str (content có thể là list part tuỳ model)
            if msg.type == "human":
                conversation_history.append(f"Người dùng: {body}")
            elif msg.type == "ai" and body:
                conversation_history.append(f"Trợ lý: {body}")
            elif msg.type == "tool":
                tool_results.append(body)
        
        # 2. Xây dựng văn bản ngữ cảnh duy nhất (tránh lỗi trùng lặp cấu trúc tin nhắn Gemini)
        formatted_context = (
            f"=== LỊCH SỬ HỘI THOẠI ===\n"
            f"{'\n'.join(conversation_history)}\n\n"
            f"=== DỮ LIỆU EMAIL THỰC TẾ TỪ HỆ THỐNG ===\n"
            f"{'\n'.join(tool_results) if tool_results else 'Không có dữ liệu công cụ.'}"
        )

        # 2b. (fix TC-02) Ý định người dùng RÕ RÀNG → chốt kind bằng gợi ý tất định
        #     (regex, 0 quota) + luật cứng trong _PRESENT_SYS. Hết cảnh cùng câu hỏi
        #     "phân loại ưu tiên" mà lúc ra thẻ triage, lúc tụt về text.
        last_user = next((coerce_text(m.content) for m in reversed(turn_msgs)
                          if getattr(m, "type", None) == "human"), "")
        hinted = suggest_kind(last_user)
        if hinted and tool_results:
            formatted_context += f"\n\nGỢI Ý ĐỊNH TUYẾN: kind={hinted}"
        
        # 3. Gọi mô hình có cấu trúc
        pres: PresentReply = await structured_llm.ainvoke([
            SystemMessage(content=_PRESENT_SYS),
            HumanMessage(content=formatted_context)
        ])
        
        # 4. Map dữ liệu trả về chính xác cho Frontend render
        output_dict = {"kind": pres.kind, "intro": pres.intro}
        if pres.kind == "result":
            output_dict.update({"title": pres.title, "lines": [_one_line(x) for x in pres.lines]})
        elif pres.kind == "digest":
            output_dict.update({
                "title": pres.title,
                "stats": [s.model_dump() for s in pres.stats],
                "breakdown": [b.model_dump() for b in pres.breakdown],
                "highlights": [_one_line(x) for x in pres.highlights]
            })
        elif pres.kind == "triage":
            output_dict.update({
                "title": pres.title,
                "groups": [{
                    "level": g.level,
                    "label": g.label,
                    # initial do LLM sinh có thể dài/rỗng → CHUẨN HOÁ về đúng 1 chữ cái hoa
                    # (khớp khuôn MiniAvatar của FE), sender rỗng thì lấy chữ đầu người gửi.
                    "items": [{
                        **it.model_dump(),
                        "initial": ((it.initial or it.sender or "•").strip()[:1] or "•").upper(),
                    } for it in g.items],
                } for g in pres.groups]
            })
        else:
            # kind=text: model đôi khi dồn NỘI DUNG vào 'intro' mà bỏ trống 'text' — nếu chỉ lấy
            # pres.text sẽ MẤT câu trả lời (FE không đọc intro ở thẻ text). Ưu tiên text → intro.
            output_dict.update({"text": pres.text or pres.intro or "Mình đã xử lý thông tin email cho bạn."})

        return {"final_output": output_dict}

    except Exception as e:
        # Fallback an toàn nếu Gemini bị lỗi hạn ngạch (Quota) hoặc không thể parse cấu trúc.
        import logging
        logging.getLogger(__name__).error(f"Lỗi responder_node: {str(e)}")

        # Tin cuối có thể là AIMessage mang tool_calls với content RỖNG (hoặc content dạng list)
        # → quét ngược tìm câu AI có chữ thật, ép str; không có thì dùng câu generic (tránh bubble trống).
        fallback_text = ""
        for m in reversed(state.get("messages") or []):
            if getattr(m, "type", None) == "ai":
                fallback_text = coerce_text(m.content).strip()
                if fallback_text:
                    break
        return {"final_output": {"kind": "text", "text": fallback_text or "Mình đã thực hiện xong yêu cầu, nhưng phần trình bày đang gặp trục trặc nhỏ. Bạn hỏi lại giúp mình nhé."}}