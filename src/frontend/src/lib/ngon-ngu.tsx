/* ── LỚP DỊCH TỐI GIẢN ────────────────────────────────────────────────────────
   Nút "English" ở màn Cài đặt trước đây chỉ ghi vào localStorage và đặt thuộc tính
   `lang` của thẻ <html> — KHÔNG có chỗ nào đọc nó, nên bấm xong giao diện không đổi
   một chữ. Một nút hứa một việc rồi không làm thì tệ hơn không có nút.

   ── VÌ SAO TỰ VIẾT, KHÔNG DÙNG THƯ VIỆN ──
   `react-i18next` kéo theo ~40KB, một hệ thống namespace, và cách nạp bất đồng bộ —
   toàn thứ đáng giá khi có hàng nghìn chuỗi và nhiều người dịch. Ở đây phạm vi là vài
   chục chuỗi KHUNG (thanh điều hướng, tiêu đề cột, nút chính). Một `Record` phẳng cộng
   một hook đọc hết trong ba mươi giây, và không ai phải học gì để thêm chuỗi mới.

   ── PHẠM VI: DỊCH NHÃN, KHÔNG DỊCH DỮ LIỆU VÀ KHÔNG DỊCH ĐẦU VÀO CỦA MÁY ──
   484 khoá, phủ toàn bộ giao diện ứng dụng: khung, toast, thông báo lỗi, ô nhập,
   nhãn ngày giờ. Ba thứ CỐ Ý để nguyên tiếng Việt:

   1. DỮ LIỆU THẬT — tên người gửi, tiêu đề thư, tên thành phố/sân bay. Dịch chúng là
      bịa dữ liệu: người dùng đối chiếu với Gmail sẽ thấy hai thứ khác nhau.
   2. CÂU LỆNH GỬI CHO AGENT — chip gợi ý gửi đi 'lưu trữ thư bản tin' chứ không gửi
      'Archive newsletters'. Bộ đọc ý định (`lib/agent.ts`) khớp bằng từ khoá tiếng
      Việt, nên dịch câu lệnh là chip bấm vào không chạy nữa. Vì vậy chip có HAI
      trường tách nhau: `nhan` để đọc, `lenh` để gửi.
   3. TRANG GIỚI THIỆU (`landing.tsx`) — trang tiếp thị xem một lần trước khi đăng
      nhập, không phải khung làm việc.

   Ngôn ngữ TRẢ LỜI của trợ lý cũng đổi thật (xem `user_preference.to_prompt_context`),
   và thẻ kết quả đổi ở backend (`app/core/ngon_ngu.py`).

   ── MỘT CÁI BẪY, ĐÃ VẤP THẬT ──
   `t()` gọi ở TẦNG MODULE thì chạy MỘT LẦN lúc nạp module, không phải lúc vẽ — nên
   `const CHIP = [{ label: t('...') }]` đông cứng ở thứ tiếng lúc mở trang, và bấm
   English xong nó vẫn nguyên tiếng Việt. tsc và build đều xanh; chỉ mở trình duyệt
   mới thấy. Mọi bảng nhãn ở tầng module vì thế là HÀM (`dsFilters()`), hoặc giữ
   KHOÁ rồi mới dịch ở chỗ vẽ.

   Thiếu khoá thì trả về CHÍNH KHOÁ đó chứ không phải chuỗi rỗng: một nhãn hiện ra
   "nav.inbox" là lỗi nhìn thấy ngay và sửa được, còn một nhãn trống thì trông như
   giao diện hỏng và không ai đoán ra thiếu gì. */

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Ngon = 'vi' | 'en'

const KHOA_LUU = 'meoarc-lang'

/** Từ điển. Khoá đặt theo `khu-vuc.ten` để tìm bằng mắt được. */
const TU_DIEN: Record<string, { vi: string; en: string }> = {
  // Thanh điều hướng
  'nav.inbox': { vi: 'Hộp thư', en: 'Inbox' },
  'nav.schedule': { vi: 'Lịch trình', en: 'Schedule' },
  'nav.assistant': { vi: 'Trợ lý', en: 'Assistant' },
  'nav.starred': { vi: 'Gắn sao', en: 'Starred' },
  'nav.sent': { vi: 'Đã gửi', en: 'Sent' },
  'nav.drafts': { vi: 'Nháp', en: 'Drafts' },
  'nav.archive': { vi: 'Lưu trữ', en: 'Archive' },
  'nav.spam': { vi: 'Thư rác', en: 'Spam' },
  'nav.trash': { vi: 'Thùng rác', en: 'Trash' },
  'nav.settings': { vi: 'Cài đặt', en: 'Settings' },
  'nav.notifications': { vi: 'Thông báo', en: 'Notifications' },

  // Cột thư
  'mail.title': { vi: 'Hộp thư', en: 'Inbox' },
  'mail.searchTitle': { vi: 'Tìm kiếm', en: 'Search' },
  'mail.colTitle': { vi: 'Thư', en: 'Mail' },
  'mail.search': { vi: 'Tìm trong thư…', en: 'Search mail…' },
  'mail.compose': { vi: 'Soạn thư', en: 'Compose' },
  'mail.refresh': { vi: 'Làm mới', en: 'Refresh' },
  'mail.unread': { vi: 'chưa đọc', en: 'unread' },
  'mail.empty': { vi: 'Không có thư nào.', en: 'No messages.' },

  // Khung trợ lý
  'chat.title': { vi: 'Trợ lý MeoArc', en: 'MeoArc Assistant' },
  'chat.placeholder': { vi: 'Nhắn cho trợ lý…', en: 'Message the assistant…' },
  'chat.send': { vi: 'Gửi', en: 'Send' },
  'chat.approve': { vi: 'Duyệt', en: 'Approve' },
  'chat.reject': { vi: 'Từ chối', en: 'Reject' },
  'chat.openMail': { vi: 'Mở thư', en: 'Open' },
  'chat.reply': { vi: 'Trả lời', en: 'Reply' },

  // Cài đặt
  'settings.title': { vi: 'Cài đặt', en: 'Settings' },
  'settings.appearance': { vi: 'Giao diện', en: 'Appearance' },
  'settings.personal': { vi: 'Cá nhân hoá', en: 'Personalisation' },
  'settings.theme': { vi: 'Chủ đề', en: 'Theme' },
  'settings.language': { vi: 'Ngôn ngữ', en: 'Language' },
  'act.approveSend': { vi: 'Duyệt & gửi', en: 'Approve & send' },
  'act.archive': { vi: 'Lưu trữ', en: 'Archive' },
  'act.attach': { vi: 'Đính kèm tệp', en: 'Attach file' },
  'act.clear': { vi: 'Bỏ chọn', en: 'Clear selection' },
  'act.close': { vi: 'Đóng', en: 'Close' },
  'act.compose': { vi: 'Soạn thư mới', en: 'New message' },
  'act.copy': { vi: 'Sao chép', en: 'Copy' },
  'act.delete': { vi: 'Xoá', en: 'Delete' },
  'act.discardDraft': { vi: 'Bỏ bản nháp', en: 'Discard draft' },
  'act.filter': { vi: 'Bộ lọc theo tiêu chí', en: 'Filter by criteria' },
  'act.important': { vi: 'Quan trọng', en: 'Important' },
  'act.label': { vi: 'Gắn nhãn', en: 'Label' },
  'act.markImportant': { vi: 'Đánh dấu quan trọng', en: 'Mark as important' },
  'act.markRead': { vi: 'Đánh dấu đã đọc', en: 'Mark as read' },
  'act.markUnread': { vi: 'Đánh dấu chưa đọc', en: 'Mark as unread' },
  'act.refresh': { vi: 'Làm mới', en: 'Refresh' },
  'act.rename': { vi: 'Đổi tên', en: 'Rename' },
  'act.restore': { vi: 'Khôi phục về hộp thư', en: 'Restore to inbox' },
  'act.rerun': { vi: 'Chạy lại', en: 'Run again' },
  'act.skip': { vi: 'Bỏ qua', en: 'Skip' },
  'auth.login': { vi: 'Đăng nhập MeoArc', en: 'Sign in to MeoArc' },
  'auth.retry': { vi: 'Thử lại, hoặc dùng tài khoản Google.', en: 'Try again, or use a Google account.' },
  'auth.scope': { vi: 'đọc &amp; quản lý thư', en: 'read &amp; manage mail' },
  'cal.day': { vi: 'NGÀY', en: 'DAY' },
  'cal.month': { vi: 'THÁNG', en: 'MONTH' },
  'cal.next': { vi: 'Tháng sau', en: 'Next month' },
  'cal.prev': { vi: 'Tháng trước', en: 'Previous month' },
  'cal.today': { vi: 'Hôm nay', en: 'Today' },
  'chat.attachHint': { vi: 'Đính kèm tệp để trợ lý gửi đi', en: 'Attach a file for the assistant to send' },
  'chat.clearCtx': { vi: 'Bỏ bối cảnh', en: 'Clear context' },
  'chat.new': { vi: 'Cuộc trò chuyện mới', en: 'New conversation' },
  'mail.askAssistant': { vi: 'Hỏi trợ lý về việc này', en: 'Ask the assistant about this' },
  'mail.body': { vi: 'Nội dung email', en: 'Email body' },
  'mail.confirmSend': { vi: 'Xác nhận gửi?', en: 'Confirm send?' },
  'mail.dragWidth': { vi: 'Kéo để chỉnh độ rộng dải hộp thư', en: 'Drag to resize the mail column' },
  'mail.dragWidthLong': { vi: 'Kéo để chỉnh độ rộng · double-click để khôi phục', en: 'Drag to resize · double-click to reset' },
  'mail.enableKeys': { vi: 'Kích hoạt dải phím thao tác', en: 'Enable shortcut bar' },
  'mail.openThis': { vi: 'Mở lá thư này', en: 'Open this message' },
  'mail.refreshBox': { vi: 'Làm mới hộp thư', en: 'Refresh mailbox' },
  'mail.replyThis': { vi: 'Soạn trả lời thư này', en: 'Draft a reply' },
  'mail.subjectLabel': { vi: 'Chủ đề:', en: 'Subject:' },
  'mail.tapChangeLabel': { vi: 'Bấm để đổi nhãn', en: 'Tap to change label' },
  'mail.toggleSearch': { vi: 'Bật/tắt ô tìm kiếm', en: 'Toggle search box' },
  'mail.viewOriginal': { vi: 'Xem thư gốc', en: 'View original' },
  'nav.account': { vi: 'Tài khoản', en: 'Account' },
  'nav.backAssistant': { vi: 'Quay lại trợ lý', en: 'Back to assistant' },
  'nav.backInbox': { vi: 'Về hộp thư', en: 'Back to inbox' },
  'nav.closeAssistant': { vi: 'Đóng trợ lý AI', en: 'Close AI assistant' },
  'nav.closeToInbox': { vi: 'Đóng trợ lý — về Hộp thư', en: 'Close assistant — back to Inbox' },
  'nav.history': { vi: 'Lịch sử trò chuyện', en: 'Chat history' },
  'nav.openAssistant': { vi: 'Mở trợ lý MeoArc', en: 'Open MeoArc Assistant' },
  'nav.palette': { vi: 'Bảng lệnh', en: 'Command palette' },
  'nav.travel': { vi: 'Tra cứu chỗ đi lại', en: 'Travel lookup' },
  'nav.travelLong': { vi: 'Tra cứu chuyến bay và phòng', en: 'Look up flights and rooms' },
  'notif.close': { vi: 'Đóng thông báo', en: 'Dismiss notification' },
  'onb.welcome': { vi: 'Chào mừng đến MeoArc', en: 'Welcome to MeoArc' },
  'plan.close': { vi: 'Đóng trang nâng cấp', en: 'Close upgrade page' },
  'plan.perDay': { vi: 'lượt hỏi / ngày', en: 'questions / day' },
  'plan.perMonth': { vi: '/tháng', en: '/month' },
  'pref.callYou': { vi: 'Trợ lý gọi bạn là', en: 'The assistant calls you' },
  'pref.instruction': { vi: 'Dặn riêng cho trợ lý', en: 'Custom instruction' },
  'pref.session': { vi: 'Phiên đăng nhập Google hiện tại của bạn.', en: 'Your current Google session.' },
  'pref.signature': { vi: 'Chữ ký cuối thư', en: 'Email signature' },
  'pref.tone': { vi: 'Giọng văn khi soạn thư', en: 'Writing tone' },
  'st.arrowSelect': { vi: '↑↓ chọn', en: '↑↓ select' },
  'st.askingAbout': { vi: 'Đang hỏi về:', en: 'Asking about:' },
  'st.enterRun': { vi: '↵ chạy', en: '↵ run' },
  'st.escClose': { vi: 'esc đóng', en: 'esc to close' },
  'st.handled': { vi: 'Đã xử lý ✓', en: 'Handled ✓' },
  'st.inferredDue': { vi: 'hạn tự tính', en: 'inferred due date' },
  'st.loading': { vi: 'Đang tải…', en: 'Loading…' },
  'st.multiSelect': { vi: 'Được chọn nhiều', en: 'Multi-select' },
  'st.noBooking': { vi: 'không đặt chỗ', en: 'no booking' },
  'st.noNotif': { vi: 'Chưa có thông báo', en: 'No notifications' },
  'st.noTasks': { vi: 'Chưa có việc nào.', en: 'No tasks yet.' },
  'st.noTasksRange': { vi: 'Không có việc nào trong khoảng này.', en: 'No tasks in this range.' },
  'st.on': { vi: 'đang bật', en: 'on' },
  'st.tryOtherKeyword': { vi: 'Thử từ khoá khác nhé.', en: 'Try another keyword.' },
  'travel.clearFilter': { vi: 'Bỏ lọc', en: 'Clear filters' },
  'travel.googleDetail': { vi: 'Xem chi tiết chuyến bay này trên Google', en: 'See this flight on Google' },
  'travel.hotelNote': { vi: 'Tên, hạng sao và vị trí là thật — giá phòng là số mô phỏng', en: 'Name, star rating and location are real — the price is simulated' },
  'travel.noPrice': { vi: 'Nguồn này cung cấp lịch bay, không bán vé nên không có giá', en: 'This source provides schedules, not tickets — so no price' },
  'travel.real': { vi: 'thật', en: 'real' },
  'travel.viewFlight': { vi: 'Xem chuyến bay', en: 'View flight' },
  'voice.off': { vi: 'Đóng voice mode', en: 'Close voice mode' },
  'voice.on': { vi: 'Bật voice mode', en: 'Start voice mode' },
  'voice.speak': { vi: 'Nói với trợ lý (voice mode)', en: 'Talk to the assistant (voice mode)' },

  'act.keep': { vi: 'Giữ lại', en: 'Keep' },
  'act.replyDraft': { vi: 'Soạn trả lời', en: 'Draft a reply' },
  'act.star': { vi: 'Gắn sao', en: 'Star' },
  'auto.read': { vi: 'Đã đọc', en: 'Read' },
  'auto.replay': { vi: '— bấm để tua lại', en: '— click to replay' },
  'auto.sent': { vi: 'Đã gửi', en: 'Sent' },
  'chat.rewriteHint': { vi: 'Gợi ý: ngắn gọn hơn, trang trọng hơn…', en: 'Try: shorter, more formal…' },
  'chat.searchHistory': { vi: 'Tìm trong lịch sử…', en: 'Search history…' },
  'cmd.archiveHint': { vi: 'Dọn hộp thư', en: 'Tidy the inbox' },
  'cmd.archiveNews': { vi: 'Lưu trữ thư bản tin', en: 'Archive newsletters' },
  'cmd.autolabelHint': { vi: 'Gắn nhãn toàn bộ', en: 'Label everything' },
  'cmd.briefHint': { vi: 'Tóm tắt cuộc họp', en: 'Summarize the meeting' },
  'cmd.digest': { vi: 'Digest hôm nay', en: "Today's digest" },
  'cmd.digestHint': { vi: 'Báo cáo nhanh hộp thư', en: 'Quick inbox report' },
  'cmd.placeholder': { vi: 'Gõ lệnh hoặc hỏi trợ lý…', en: 'Type a command or ask…' },
  'cmd.sendToMeoarc': { vi: 'Gửi cho MeoArc xử lý', en: 'Send to MeoArc' },
  'cmd.summarize': { vi: 'Tóm tắt thư chưa đọc', en: 'Summarize unread' },
  'cmd.summarizeHint': { vi: 'Rút gọn nội dung', en: 'Condense the content' },
  'cmd.theme': { vi: 'Đổi theme', en: 'Switch theme' },
  'cmd.triage': { vi: 'Triage hộp thư', en: 'Triage inbox' },
  'cmd.triageHint': { vi: 'Phân loại theo ưu tiên', en: 'Sort by priority' },
  'flt.action': { vi: 'Cần xử lý', en: 'Needs action' },
  'flt.all': { vi: 'Tất cả', en: 'All' },
  'flt.attach': { vi: 'Đính kèm', en: 'Attachment' },
  'flt.done': { vi: 'Xong', en: 'Done' },
  'flt.unread': { vi: 'Chưa đọc', en: 'Unread' },
  'flt.waiting': { vi: 'Đang đợi', en: 'Waiting' },
  'mail.bodyPlaceholder': { vi: 'Nội dung email…', en: 'Email body…' },
  'mail.from': { vi: 'Từ', en: 'From' },
  'mail.orBrowse': { vi: 'hoặc bấm để chọn từ máy', en: 'or click to browse' },
  'mail.subject': { vi: 'Chủ đề', en: 'Subject' },
  'mail.to': { vi: 'Tới', en: 'To' },
  'mail.toLabel': { vi: 'Tới:', en: 'To:' },
  'mail.toPlaceholder': { vi: 'email người nhận', en: 'recipient email' },
  'nav.faq': { vi: 'Giải đáp', en: 'FAQ' },
  'nav.features': { vi: 'Tính năng', en: 'Features' },
  'nav.how': { vi: 'Cách vận hành', en: 'How it works' },
  'nav.pricing': { vi: 'Gói dịch vụ', en: 'Pricing' },
  'onb.d2': { vi: 'Cứ nhắn lời thường: “tóm tắt thư chưa đọc”, “lưu trữ thư bản tin”, “brief cuộc họp”…', en: 'Just talk normally: “summarize unread”, “archive newsletters”, “brief the meeting”…' },
  'onb.d4': { vi: '⌘K mở bảng lệnh · / tìm kiếm · j/k duyệt thư · Enter mở · c soạn thư.', en: '⌘K command palette · / search · j/k browse · Enter open · c compose.' },
  'onb.d1': { vi: 'Điều hướng trái · danh sách thư giữa · trợ lý AI phải. Kéo mép phải để chỉnh rộng.', en: 'Navigation left · mail list centre · AI assistant right. Drag the edge to resize.' },
  'onb.d3': { vi: 'Bấm mic để nói — trợ lý nghe, hiểu và đọc lại câu trả lời cho bạn.', en: 'Tap the mic and speak — the assistant listens, understands and reads its answer back.' },
  'onb.t1': { vi: 'Giao diện 3 cột', en: 'Three-column layout' },
  'onb.t2': { vi: 'Trợ lý ngôn ngữ tự nhiên', en: 'Natural-language assistant' },
  'onb.t3': { vi: 'Ra lệnh bằng giọng nói', en: 'Voice commands' },
  'onb.t4': { vi: 'Phím tắt nhanh', en: 'Keyboard shortcuts' },
  'plan.choose': { vi: 'Chọn gói', en: 'Choose a plan' },
  'pref.namePlaceholder': { vi: 'Anh Quân', en: 'e.g. Alex' },
  'scope.modify': { vi: 'Quản lý thư (modify/label/archive)', en: 'Manage mail (modify/label/archive)' },
  'scope.read': { vi: 'Đọc thư (read)', en: 'Read mail (read)' },
  'scope.send': { vi: 'Soạn & gửi (send)', en: 'Compose & send (send)' },
  'skill.autolabel': { vi: 'Phân loại tự động', en: 'Auto-label' },
  'skill.autopilot': { vi: 'Hộp thư tự lái', en: 'Autopilot inbox' },
  'skill.brief': { vi: 'Tóm lược cuộc họp', en: 'Meeting brief' },
  'skill.digest': { vi: 'Tóm tắt hôm nay', en: "Today's digest" },
  'skill.triage': { vi: 'Phân loại ưu tiên', en: 'Prioritize' },
  'st.pinned': { vi: 'Đã ghim', en: 'Pinned' },
  'sub.thisMonth': { vi: 'Tháng này', en: 'This month' },
  'sug.brief': { vi: 'Tạo Meeting Brief', en: 'Create a meeting brief' },
  'sug.cleanNews': { vi: 'Dọn thư bản tin tuần này', en: "Clear this week's newsletters" },
  'sug.digestAm': { vi: 'Tóm tắt hộp thư sáng nay', en: "Summarize this morning's inbox" },
  'sug.summarize': { vi: 'Tóm tắt thư này', en: 'Summarize this message' },
  'sug.tasks': { vi: 'Trích việc & deadline', en: 'Extract tasks & deadlines' },
  'theme.dark': { vi: 'Tối', en: 'Dark' },
  'theme.light': { vi: 'Sáng', en: 'Light' },

  'acct.switchTo': { vi: 'Chuyển sang', en: 'Switch to' },
  'acct.addAnother': { vi: 'Thêm tài khoản khác', en: 'Add another account' },
  'acct.logoutThis': { vi: 'Đăng xuất tài khoản này', en: 'Sign out of this account' },
  'acct.revoke': { vi: 'Thu hồi quyền Gmail', en: 'Revoke Gmail access' },
  'acct.revokeAsk': { vi: 'Thu hồi quyền Gmail?', en: 'Revoke Gmail access?' },
  'acct.revokeWarn': { vi: 'MeoArc sẽ mất toàn bộ quyền đọc & quản lý thư trên Gmail của bạn và bạn sẽ bị đăng xuất. Lần sau muốn dùng lại phải cấp quyền từ đầu.', en: 'MeoArc will lose all read & manage access to your Gmail and you will be signed out. Using it again means granting access from scratch.' },
  'acct.revokeGo': { vi: 'Thu hồi & đăng xuất', en: 'Revoke & sign out' },
  'act.cancel': { vi: 'Huỷ', en: 'Cancel' },

  'pref.instrPlaceholder': { vi: "Đừng dùng từ 'trân trọng'. Luôn hỏi lại trước khi hứa deadline.", en: "Don't use the word 'sincerely'. Always check with me before promising a deadline." },
  'voice.example': { vi: 'vd: “tóm tắt thư chưa đọc”', en: 'e.g. “summarize unread”' },

  'fld.inbox': { vi: 'Hộp thư', en: 'Inbox' },
  'fld.starred': { vi: 'Gắn sao', en: 'Starred' },
  'fld.sent': { vi: 'Đã gửi', en: 'Sent' },
  'fld.drafts': { vi: 'Nháp', en: 'Drafts' },
  'fld.archive': { vi: 'Lưu trữ', en: 'Archive' },
  'fld.trash': { vi: 'Thùng rác', en: 'Trash' },
  'toast.unstarred': { vi: 'Đã bỏ quan trọng', en: 'Removed from important' },
  // Nói rõ thư ĐANG Ở ĐÂU. Thư khôi phục quay về đúng vị trí thời gian cũ, nên thư cũ
  // rơi ra ngoài trang đầu và người dùng kết luận là khôi phục hụt. Câu này cùng với
  // việc ghim lên đầu Hộp thư trả lời thẳng câu "thế mail đâu".
  'toast.newMailOne': { vi: 'Thư mới từ {ten}', en: 'New message from {ten}' },
  'toast.newMail': { vi: 'Có {n} thư mới', en: '{n} new messages' },
  'toast.restored': {
    vi: 'Đã khôi phục {n} thư — đang ghim ở đầu Hộp thư',
    en: 'Restored {n} messages — pinned at the top of your inbox',
  },
  'toast.restoredOne': {
    vi: 'Đã khôi phục thư — đang ghim ở đầu Hộp thư',
    en: 'Message restored — pinned at the top of your inbox',
  },
  'toast.starred': { vi: 'Đã đánh dấu quan trọng', en: 'Marked important' },
  'toast.markedRead': { vi: 'Đã đánh dấu {n} thư là đã đọc', en: 'Marked {n} messages as read' },
  'toast.markedUnread': { vi: 'Đã đánh dấu {n} thư là chưa đọc', en: 'Marked {n} messages as unread' },
  'toast.markedImportant': { vi: 'Đã đánh dấu {n} thư là quan trọng', en: 'Marked {n} messages as important' },
  'toast.deleted': { vi: 'Đã xoá {n} thư', en: 'Deleted {n} messages' },
  'toast.labelled': { vi: 'Đã gắn nhãn “{nhan}” cho {n} thư', en: 'Labelled {n} messages “{nhan}”' },
  'toast.labelledOne': { vi: 'Đã gắn nhãn “{nhan}”', en: 'Labelled “{nhan}”' },
  'toast.archived': { vi: 'Đã lưu trữ thư', en: 'Message archived' },
  'toast.markedUnreadOne': { vi: 'Đã đánh dấu chưa đọc', en: 'Marked as unread' },
  'mail.closeSearch': { vi: 'Đóng tìm kiếm', en: 'Close search' },
  'mail.unreadCount': { vi: '{n} thư chưa đọc', en: '{n} unread' },
  'mail.allRead': { vi: 'Đã đọc hết', en: 'All read' },
  'mail.phGmail': { vi: 'Tìm trên Gmail (vd: from:github, has:attachment)…', en: 'Search Gmail (e.g. from:github, has:attachment)…' },
  'mail.phNl': { vi: 'Hỏi: "thư chưa đọc có đính kèm"…', en: 'Ask: "unread with attachments"…' },
  'mail.phPlain': { vi: 'Tìm (phím / để focus)…', en: 'Search (press / to focus)…' },
  'mail.nlOff': { vi: 'Tắt tìm theo ngôn ngữ tự nhiên', en: 'Turn off natural-language search' },
  'mail.nlOn': { vi: 'Tìm bằng ngôn ngữ tự nhiên', en: 'Search in natural language' },
  'mail.tagsCollapse': { vi: 'Thu gọn nhãn', en: 'Collapse labels' },
  'mail.tagsExpand': { vi: 'Hiện đủ nhãn phân loại', en: 'Show all labels' },
  'mail.deselectAll': { vi: 'Bỏ chọn tất cả', en: 'Deselect all' },
  'mail.selectAll': { vi: 'Chọn tất cả', en: 'Select all' },
  'mail.loadMore': { vi: 'Tải thêm thư', en: 'Load more' },
  'mail.noResult': { vi: 'Không tìm thấy thư nào', en: 'No messages found' },
  'mail.folderEmpty': { vi: 'Mục “{ten}” đang trống', en: '“{ten}” is empty' },
  'mail.tryOther': { vi: 'Thử đổi từ khoá hoặc bỏ bớt bộ lọc đang áp dụng.', en: 'Try another keyword or drop a filter.' },
  'mail.nothingHere': { vi: 'Chưa có thư nào ở đây.', en: 'Nothing here yet.' },
  'mail.clearFilter': { vi: 'Xoá bộ lọc', en: 'Clear filters' },
  'mail.delTitle': { vi: 'Xoá {n} thư?', en: 'Delete {n} messages?' },
  // Câu cũ ghi "Bạn không thể hoàn tác thao tác này" — SAI kể từ khi có nút Khôi phục
  // ở Thùng rác. Một cảnh báo sai làm hỏng mọi cảnh báo còn lại: người dùng học được
  // rằng chữ đỏ nói quá, rồi bỏ qua đúng lúc nó nói thật.
  'mail.delDescOne': {
    vi: 'Thư sẽ vào Thùng rác — vẫn khôi phục lại được, nhưng sẽ biến khỏi hộp thư.',
    en: 'The message goes to Trash — still restorable, but it leaves your inbox.',
  },
  'mail.delDescMany': {
    vi: 'Các thư sẽ vào Thùng rác — vẫn khôi phục lại được, nhưng sẽ biến khỏi hộp thư.',
    en: 'The messages go to Trash — still restorable, but they leave your inbox.',
  },
  'det.delTitle': { vi: 'Xoá thư này?', en: 'Delete this message?' },
  'det.delDesc': {
    vi: 'Thư “{tieuDe}” sẽ vào Thùng rác — vẫn khôi phục lại được, nhưng sẽ biến khỏi hộp thư.',
    en: '“{tieuDe}” goes to Trash — still restorable, but it leaves your inbox.',
  },
  'mail.prioTitle': { vi: 'Độ ưu tiên: {muc}', en: 'Priority: {muc}' },
  'mail.hasAttachment': { vi: 'Có tệp đính kèm', en: 'Has attachment' },
  'act.spam': { vi: 'Đánh dấu thư rác', en: 'Report spam' },
  'act.notSpam': { vi: 'Không phải thư rác', en: 'Not spam' },
  'toast.spam': { vi: 'Đã chuyển vào Thư rác', en: 'Moved to Spam' },
  'toast.notSpam': { vi: 'Đã đưa về Hộp thư', en: 'Moved back to Inbox' },
  'det.replySelf': { vi: 'Trả lời', en: 'Reply' },
  'det.replyAi': { vi: 'Nhờ AI trả lời', en: 'Let AI reply' },
  'det.replyAiHint': {
    vi: 'Trợ lý soạn sẵn bản nháp, bạn duyệt rồi mới gửi',
    en: 'The assistant drafts it; you approve before it sends',
  },
  'det.replyAiWrite': { vi: 'Nhờ AI viết', en: 'Let AI write it' },
  'det.replyTo': { vi: 'Trả lời {ten}', en: 'Reply to {ten}' },
  'det.replyAllTo': { vi: 'Trả lời tất cả — {ten} và những người khác', en: 'Reply all — {ten} and others' },
  'det.replyPlaceholder': { vi: 'Viết câu trả lời của bạn…', en: 'Write your reply…' },
  'det.replySend': { vi: 'Gửi', en: 'Send' },
  'det.replySending': { vi: 'Đang gửi…', en: 'Sending…' },
  'toast.replySent': { vi: 'Đã gửi trả lời', en: 'Reply sent' },
  'toast.replyFailed': { vi: 'Chưa gửi được — thư CHƯA đi', en: 'Not sent — the message did NOT go out' },
  'det.replyAll': { vi: 'Trả lời tất cả', en: 'Reply all' },
  'det.forward': { vi: 'Chuyển tiếp', en: 'Forward' },
  'det.forwardHint': { vi: 'Gửi thư này cho người khác', en: 'Send this message to someone else' },
  'det.forwardTitle': { vi: 'Chuyển tiếp thư', en: 'Forward message' },
  'det.forwardDesc': {
    vi: 'Nội dung thư gốc được trích dẫn kèm theo. Tệp đính kèm KHÔNG đi cùng.',
    en: 'The original message is quoted below. Attachments are not included.',
  },
  'det.forwardTo': { vi: 'Gửi tới', en: 'To' },
  'det.forwardNote': { vi: 'Lời nhắn (không bắt buộc)', en: 'Note (optional)' },
  'det.forwardDo': { vi: 'Chuyển tiếp', en: 'Forward' },
  'det.forwardSending': { vi: 'Đang gửi…', en: 'Sending…' },
  'toast.forwarded': { vi: 'Đã chuyển tiếp tới {ten}', en: 'Forwarded to {ten}' },
  'toast.forwardFailed': { vi: 'Chưa gửi được — thư CHƯA đi', en: 'Not sent — the message did NOT go out' },
  'det.threadEarlier': { vi: '{n} lượt trước đó trong cuộc trao đổi', en: '{n} earlier in this conversation' },
  'det.unstar': { vi: 'Bỏ quan trọng', en: 'Unmark important' },
  'det.star': { vi: 'Đánh dấu quan trọng', en: 'Mark important' },
  'det.status': { vi: 'Trạng thái', en: 'Status' },
  'det.length': { vi: 'Độ dài', en: 'Length' },
  'det.words': { vi: '{n} chữ', en: '{n} words' },
  'det.readTime': { vi: 'Thời gian đọc', en: 'Reading time' },
  'det.minutes': { vi: '{n} phút', en: '{n} min' },
  'det.hideSummary': { vi: 'Ẩn tóm tắt', en: 'Hide summary' },
  'det.aiSummary': { vi: 'Tóm tắt với AI', en: 'Summarize with AI' },
  'det.fyi': { vi: 'Để biết', en: 'FYI' },
  'det.htmlNote': { vi: 'Thư này chủ yếu là nội dung HTML — xem bản đầy đủ bên dưới.', en: 'This message is mostly HTML — see the full version below.' },
  'nav.weekEmpty': { vi: 'tuần này trống', en: 'nothing this week' },
  'nav.readyShort': { vi: 'Trợ lý sẵn sàng', en: 'Assistant ready' },
  'nav.ready': { vi: 'Trợ lý sẵn sàng · {gio}', en: 'Assistant ready · {gio}' },
  'nav.expand': { vi: 'Mở rộng thanh điều hướng', en: 'Expand navigation' },
  'nav.collapse': { vi: 'Thu gọn thanh điều hướng', en: 'Collapse navigation' },
  'nav.dayLoad': { vi: '{thu} — {n} việc, {gio} giờ', en: '{thu} — {n} tasks, {gio} h' },
  'sh.refresh': { vi: 'Làm mới', en: 'Refresh' },
  'sh.loadMore': { vi: 'Tải thêm', en: 'Load more' },
  'sh.expired': { vi: 'Phiên đăng nhập đã hết hạn. Đăng nhập lại để xem thư.', en: 'Your session has expired. Sign in again to see your mail.' },
  'sh.netFail': { vi: 'Không nạp được thư từ máy chủ. Kiểm tra kết nối rồi thử lại.', en: 'Could not load mail from the server. Check your connection and try again.' },
  'sh.syncing': { vi: 'Hộp thư đang đồng bộ', en: 'Mailbox syncing' },
  'al.hoursLeft': { vi: 'Còn {n} giờ · {ai} đang chờ', en: '{n} h left · {ai} is waiting' },
  'al.new': { vi: 'mới', en: 'new' },
  'al.newMail': { vi: '{ai} · thư mới', en: '{ai} · new message' },
  'ck.hours': { vi: '{n} giờ', en: '{n} h' },
  'ck.minutes': { vi: '{n} phút', en: '{n} min' },
  'ck.urgent': { vi: 'Gấp', en: 'Urgent' },
  'ck.todo': { vi: 'Chưa làm', en: 'To do' },
  'sub.viewPlans': { vi: 'Xem gói', en: 'View plans' },
  'sub.upgrade': { vi: 'Nâng cấp', en: 'Upgrade' },
  'tok.clickPlans': { vi: 'Bấm để xem các gói.', en: 'Click to see plans.' },
  'tok.out': { vi: 'Hết token', en: 'Out of tokens' },
  'tok.left': { vi: '{n} lượt', en: '{n} left' },
  'tok.today': { vi: 'hôm nay', en: 'today' },
  'tok.month': { vi: 'tháng này', en: 'this month' },
  'tok.dayGone': { vi: 'Hạn mức {n} token/ngày đã cạn. Chờ sang ngày mai hoặc nâng gói để hỏi tiếp.', en: 'The {n} tokens/day limit is used up. Wait until tomorrow or upgrade to keep asking.' },
  'tok.monthGone': { vi: 'Hạn mức {n} token/tháng đã cạn. Nâng gói để tiếp tục.', en: 'The {n} tokens/month limit is used up. Upgrade to continue.' },

  'tok.title': { vi: 'Gói {goi} — đã dùng {dung} / {tran} token hôm nay.\nTrợ lý đọc {ngay} ngày thư gần nhất; thư cũ hơn vẫn tìm được bằng từ khoá.\nBấm để xem các gói.', en: '{goi} plan — {dung} / {tran} tokens used today.\nThe assistant reads the last {ngay} days of mail; older mail is still searchable by keyword.\nClick to see plans.' },
  'tok.usedUp': { vi: 'Đã dùng hết token {khi} của gói {goi}', en: 'Out of {khi} tokens on the {goi} plan' },

  'auto.done': { vi: 'Mèo đã lái xong hộp thư', en: 'The cat finished driving your inbox' },
  'auto.driving': { vi: 'Mèo đang tự lái hộp thư', en: 'The cat is driving your inbox' },
  'auto.reviewing': { vi: 'đang xem lại', en: 'reviewing' },
  'auto.running': { vi: 'đang chạy', en: 'running' },
  'auto.paused': { vi: 'tạm dừng', en: 'paused' },
  'auto.finished': { vi: 'hoàn tất', en: 'finished' },
  'auto.pause': { vi: 'Tạm dừng', en: 'Pause' },
  'auto.resume': { vi: 'Tiếp tục', en: 'Resume' },
  'auto.keptByYou': { vi: 'Bạn đã hoàn tác — giữ lại thư này', en: 'You undid this — the message stays' },
  'auto.rewindTo': { vi: 'Tua về {ai}', en: 'Rewind to {ai}' },
  'auto.restoreSuggest': { vi: 'Khôi phục đề xuất', en: 'Restore suggestion' },
  'auto.undo': { vi: 'Hoàn tác', en: 'Undo' },
  'auto.restore': { vi: 'Khôi phục', en: 'Restore' },
  'auto.msgCount': { vi: '{d}/{n} thư', en: '{d}/{n} messages' },
  'tm.justNow': { vi: 'vừa xong', en: 'just now' },
  'tm.minAgo': { vi: '{n} phút trước', en: '{n} min ago' },
  'tm.hourAgo': { vi: '{n} giờ trước', en: '{n} h ago' },
  'tm.dayAgo': { vi: '{n} ngày trước', en: '{n} d ago' },
  'notif.desktopTitle': { vi: 'MeoArc — thông báo', en: 'MeoArc — notification' },
  'notif.withUnread': { vi: 'Thông báo ({n} chưa đọc)', en: 'Notifications ({n} unread)' },
  'notif.unreadCount': { vi: '{n} chưa đọc', en: '{n} unread' },
  'notif.allSeen': { vi: 'Đã xem hết', en: 'All caught up' },
  'cmp.sendFail': { vi: 'Gửi thất bại, thử lại sau.', en: 'Send failed, try again later.' },
  'cmp.aiTyping': { vi: 'Đang soạn… (bấm để chốt)', en: 'Writing… (click to finish)' },
  'cmp.aiWrite': { vi: 'Soạn với AI', en: 'Write with AI' },
  'cmp.uploadFail': { vi: 'Tải tệp này lên máy chủ không thành công — gỡ ra hoặc thử lại', en: 'Uploading this file failed — remove it or try again' },
  'cmp.notUploaded': { vi: 'chưa tải lên được', en: 'not uploaded' },
  'cmp.dropNow': { vi: 'Thả ra để đính kèm ✨', en: 'Drop to attach ✨' },
  'cmp.dropHere': { vi: 'Kéo & thả tệp vào đây', en: 'Drag & drop files here' },
  'cmp.sentTo': { vi: 'Email tới {ai} đã được gửi thành công{kem}.', en: 'Your email to {ai} was sent{kem}.' },
  'cmp.sending': { vi: 'Đang gửi…', en: 'Sending…' },
  'cmp.confirmSend': { vi: 'Xác nhận gửi', en: 'Confirm send' },
  'cmp.withFiles': { vi: ' kèm {n} tệp', en: ' with {n} file(s)' },
  'cmp.aiDraft': { vi: 'Dạ em chào anh/chị,\n\nEm viết email này về việc "{cd}". Em xin trình bày ngắn gọn như sau:\n- ...\n- ...\n\nEm cảm ơn anh/chị đã dành thời gian. Mong sớm nhận phản hồi ạ.\n\nTrân trọng,\nAnh Quân', en: 'Hello,\n\nI am writing about "{cd}". In short:\n- ...\n- ...\n\nThank you for your time. I look forward to your reply.\n\nBest regards,' },
  'vo.micDenied': { vi: 'Micro bị từ chối — hãy cấp quyền micro cho trang.', en: 'Microphone denied — please allow microphone access for this page.' },
  'vo.micNoAccess': { vi: 'Không truy cập được micro — hãy cấp quyền micro cho trang.', en: 'Cannot reach the microphone — please allow microphone access for this page.' },
  'vo.micMissing': { vi: 'Không tìm thấy micro. Kiểm tra thiết bị thu âm rồi thử lại.', en: 'No microphone found. Check your input device and try again.' },
  'vo.needNet': { vi: 'Nhận diện giọng nói cần mạng — kiểm tra kết nối rồi thử lại.', en: 'Speech recognition needs a network — check your connection and try again.' },
  'vo.noVi': { vi: 'Trình duyệt chưa hỗ trợ nhận diện tiếng Việt. Hãy dùng Chrome mới nhất.', en: 'This browser cannot recognise Vietnamese speech. Please use the latest Chrome.' },
  'vo.stopped': { vi: 'Nhận diện giọng nói dừng lại ({ma}). Bạn thử lại nhé.', en: 'Speech recognition stopped ({ma}). Please try again.' },
  'vo.unknownReason': { vi: 'không rõ lý do', en: 'reason unknown' },
  'vo.unsupported': { vi: 'Trình duyệt chưa hỗ trợ nhận diện giọng nói (hãy dùng Chrome hoặc Edge).', en: 'This browser does not support speech recognition (please use Chrome or Edge).' },
  'vo.listening': { vi: 'Đang nghe…', en: 'Listening…' },
  'vo.sayIt': { vi: 'Hãy nói yêu cầu của bạn', en: 'Say what you need' },
  'cmd.toLight': { vi: 'Chuyển sang giao diện sáng', en: 'Switch to light theme' },
  'cmd.toDark': { vi: 'Chuyển sang giao diện tối', en: 'Switch to dark theme' },
  'cmd.askAssistant': { vi: 'Hỏi trợ lý: “{q}”', en: 'Ask the assistant: “{q}”' },
  'tone.formal': { vi: 'Trang trọng', en: 'Formal' },
  'tone.friendly': { vi: 'Thân thiện', en: 'Friendly' },
  'tone.concise': { vi: 'Ngắn gọn', en: 'Concise' },
  'tone.warm': { vi: 'Ấm áp', en: 'Warm' },
  'set.loadFail': { vi: 'Không tải được thiết lập.', en: 'Could not load your settings.' },
  'set.saveFail': { vi: 'Chưa lưu được. Thử lại nhé.', en: 'Could not save. Please try again.' },
  'set.saving': { vi: 'Đang lưu…', en: 'Saving…' },
  'set.autosave': { vi: 'Tự lưu khi bạn rời khỏi ô.', en: 'Saved automatically when you leave the field.' },

  'sc.noDue': { vi: 'chưa rõ hạn', en: 'no clear due date' },
  'sc.dueAt': { vi: 'hạn {han}', en: 'due {han}' },
  'sc.inferred': { vi: ' (suy ra, chưa chắc)', en: ' (inferred, not certain)' },
  'sc.waitingEst': { vi: ', {ai} đang chờ, ước tính {gio} giờ', en: ', {ai} is waiting, about {gio} h' },
  'sc.noDueShort': { vi: 'Không có hạn', en: 'No due date' },
  'sc.dateAt': { vi: '{ngay} lúc {gio}', en: '{ngay} at {gio}' },
  'sc.dayTasks': { vi: 'Việc ngày {ngay}', en: 'Tasks on {ngay}' },
  'sc.overloaded': { vi: ' · quá tải', en: ' · overloaded' },
  'sc.dueSuffix': { vi: ' · hạn {gio}', en: ' · due {gio}' },
  'sc.multiDay': { vi: ' · đợt nhiều ngày', en: ' · multi-day stretch' },
  'sc.nTasksOn': { vi: '{n} việc ngày {ngay}', en: '{n} tasks on {ngay}' },
  'sc.seeRest': { vi: 'Xem {n} việc còn lại', en: 'See {n} more' },
  'sc.hours': { vi: '{n} giờ', en: '{n} h' },
  'sc.prio3': { vi: 'Gấp', en: 'Urgent' },
  'sc.prio2': { vi: 'Quan trọng', en: 'Important' },
  'sc.prio1': { vi: 'Thường', en: 'Normal' },
  'sc.askAbout': { vi: 'Hỏi trợ lý về: {viec}', en: 'Ask the assistant about: {viec}' },
  'sc.lateDays': { vi: 'Trễ {n} ngày', en: '{n} days late' },
  'auth.errExchange': { vi: 'Không đổi được mã uỷ quyền lấy token', en: 'Could not exchange the authorisation code for a token' },
  'auth.errProfile': { vi: 'Không lấy được hồ sơ tài khoản Microsoft', en: 'Could not fetch the Microsoft account profile' },
  'auth.errRefused': { vi: 'Microsoft từ chối yêu cầu đăng nhập', en: 'Microsoft refused the sign-in request' },
  'auth.errNoCode': { vi: 'Microsoft không gửi mã uỷ quyền', en: 'Microsoft did not return an authorisation code' },
  'auth.errUnknown': { vi: 'Lỗi không lường trước', en: 'Unexpected error' },
  'auth.failed': { vi: 'Đăng nhập không thành công', en: 'Sign-in failed' },
  'auth.noAutoSend': { vi: 'Không tự ý gửi thư', en: 'Never sends mail on its own' },
  'auth.revokeAny': { vi: 'Thu hồi quyền bất cứ lúc nào', en: 'Revoke access at any time' },
  'plan.free': { vi: 'Miễn phí', en: 'Free' },
  'plan.switched': { vi: 'Đã chuyển sang gói {goi}', en: 'Switched to the {goi} plan' },
  'plan.pickSpeed': { vi: 'Chọn tốc độ', en: 'Pick a speed' },
  'plan.forYourCat': { vi: 'cho chú mèo của bạn', en: 'for your cat' },
  'plan.current': { vi: 'Gói hiện tại', en: 'Current plan' },
  'plan.backToFree': { vi: 'Về Miễn phí', en: 'Back to Free' },
  'plan.upgradeTo': { vi: 'Nâng cấp {goi}', en: 'Upgrade to {goi}' },

  'gy.stayNear': { vi: 'Tìm chỗ ở gần đó', en: 'Find a place to stay nearby' },
  'gy.morningFlight': { vi: 'Chuyến nào bay buổi sáng?', en: 'Which flights leave in the morning?' },
  'gy.remindBefore': { vi: 'Đặt lịch nhắc trước ngày bay', en: 'Remind me before the flight' },
  'gy.flightThere': { vi: 'Tìm chuyến bay tới đó', en: 'Find flights there' },
  'gy.nearCentre': { vi: 'Chỗ nào gần trung tâm nhất?', en: 'Which one is closest to the centre?' },
  'gy.whichFirst': { vi: 'Thư nào cần xử lý trước?', en: 'Which message needs me first?' },
  'gy.categorise': { vi: 'Phân loại giúp mình', en: 'Categorise them for me' },
  'gy.archiveNews': { vi: 'Lưu trữ hết bản tin', en: 'Archive every newsletter' },
  'gy.replyUrgent': { vi: 'Soạn trả lời thư gấp nhất', en: 'Draft a reply to the most urgent one' },
  'gy.overloaded': { vi: 'Tuần này mình có quá tải không?', en: 'Am I overloaded this week?' },
  'gy.digestToday': { vi: 'Tóm tắt hộp thư hôm nay', en: "Summarize today's inbox" },
  'gy.waitingOnMe': { vi: 'Thư nào đang chờ mình phản hồi?', en: 'Which messages are waiting on me?' },
  'gy.confirmAttend': { vi: 'Soạn thư xác nhận tham dự', en: 'Draft an acceptance email' },
  'gy.flightToMeeting': { vi: 'Tìm chuyến bay tới cuộc họp này', en: 'Find flights to this meeting' },
  'gy.shorter': { vi: 'Viết ngắn gọn hơn', en: 'Make it shorter' },
  'gy.formal': { vi: 'Đổi sang giọng trang trọng', en: 'Switch to a formal tone' },
  'gy.replyTo': { vi: 'Soạn trả lời {ai}', en: 'Draft a reply to {ai}' },
  'gy.sumUnread': { vi: 'Tóm tắt {n} thư chưa đọc', en: 'Summarize {n} unread' },
  'gy.cleanPromo': { vi: 'Dọn {n} thư khuyến mãi', en: 'Clear {n} promotional messages' },
  'gy.autoLabel': { vi: 'Phân loại tự động thư chưa nhãn', en: 'Auto-label the unlabelled mail' },
  'gy.sumFrom': { vi: 'Tóm tắt thư của {ai}', en: 'Summarize mail from {ai}' },
  'tm.todayAt': { vi: 'Hôm nay {gio}', en: 'Today {gio}' },
  'tm.yesterday': { vi: 'Hôm qua', en: 'Yesterday' },
  'tm.today': { vi: 'Hôm nay', en: 'Today' },
  'tm.earlier': { vi: 'Trước đó', en: 'Earlier' },
  'tm.now': { vi: 'Bây giờ', en: 'Now' },
  'ch.resultShort': { vi: 'Kết quả…', en: 'Result…' },
  'ch.doneArchive': { vi: 'Đã lưu trữ {n} thư. Hộp thư gọn hơn rồi ✨', en: 'Archived {n} messages. Tidier already ✨' },
  'ch.doneRestore': { vi: 'Đã khôi phục {n} thư về hộp thư.', en: 'Restored {n} messages to the inbox.' },
  'ch.doneDelete': { vi: 'Đã xoá {n} thư.', en: 'Deleted {n} messages.' },
  'ch.doneRead': { vi: 'Đã đánh dấu đã đọc {n} thư.', en: 'Marked {n} messages as read.' },
  'ch.doneLabel': { vi: 'Đã gắn nhãn “{nhan}” cho {n} thư.', en: 'Labelled {n} messages “{nhan}”.' },
  'ch.doneAuto': { vi: 'Đã phân loại {n} thư theo nội dung.', en: 'Sorted {n} messages by content.' },
  'ch.st1': { vi: 'Đang đọc yêu cầu…', en: 'Reading your request…' },
  'ch.st2': { vi: 'Đang tra hộp thư…', en: 'Searching your mailbox…' },
  'ch.st3': { vi: 'Đang tổng hợp kết quả…', en: 'Putting the results together…' },
  'ch.st4': { vi: 'Câu này cần nhiều bước — vẫn đang chạy…', en: 'This one takes several steps — still going…' },
  'ch.st5': { vi: 'Lâu hơn thường lệ. Có thể mô hình đang bận, chờ thêm chút nhé.', en: 'Longer than usual. The model may be busy — hang on a moment.' },
  'ch.unmark': { vi: 'Bỏ đánh dấu', en: 'Unmark' },
  'ch.markHandled': { vi: 'Đánh dấu đã xử lý (thư sẽ thành đã đọc)', en: 'Mark as handled (marks the message read)' },
  'ch.noUndoMoney': { vi: 'Không hoàn tác · tiêu tiền thật', en: 'Cannot be undone · spends real money' },
  'ch.needApproval': { vi: 'Cần bạn duyệt', en: 'Needs your approval' },
  'ch.calendarOnly': { vi: 'Chỉ thêm vào lịch', en: 'Calendar only' },
  'ch.working': { vi: 'Đang xử lý…', en: 'Working…' },
  'ch.approveBook': { vi: 'Duyệt & đặt', en: 'Approve & book' },
  'ch.approve': { vi: 'Duyệt', en: 'Approve' },
  'ch.uploadFail': { vi: 'Mình không tải được tệp đó lên. Bạn thử tệp nhỏ hơn nhé.', en: 'I could not upload that file. Try a smaller one.' },
  'ch.newChat': { vi: 'Cuộc trò chuyện mới', en: 'New conversation' },
  'ch.askAssistant': { vi: 'Hỏi trợ lý', en: 'Ask the assistant' },
  'ch.opening': { vi: 'Đang mở {ten}…', en: 'Opening {ten}…' },
  'ch.error': { vi: 'Có lỗi khi xử lý yêu cầu. Bạn thử lại giúp mình nhé.', en: 'Something went wrong handling that. Please try again.' },
  'ch.bookedSim': { vi: 'Đã đặt (mô phỏng) · {ma}', en: 'Booked (simulated) · {ma}' },
  'ch.approvedSim': { vi: 'Đã duyệt (mô phỏng)', en: 'Approved (simulated)' },
  'ch.readLastLine': { vi: 'Xong rồi — nhưng đọc kỹ dòng cuối nhé:', en: 'Done — but please read the last line:' },
  'ch.totalSpent': { vi: 'Tổng chi ghi nhận: {tien} ₫', en: 'Total recorded: {tien} ₫' },
  'ch.noCost': { vi: 'Không phát sinh chi phí.', en: 'No charges were made.' },
  'ch.simWarn1': { vi: 'ĐÂY LÀ ĐẶT CHỖ MÔ PHỎNG — MeoArc chưa nối với hệ thống bán vé hay phòng nào. ', en: 'THIS IS A SIMULATED BOOKING — MeoArc is not connected to any ticket or hotel system. ' },
  'ch.simWarn2': { vi: 'Không có khoản tiền nào được thanh toán, và bạn sẽ KHÔNG nhận được vé thật.', en: 'No money was charged, and you will NOT receive a real ticket.' },
  'ch.approveFail': { vi: 'Chưa duyệt được: {loi}. Bạn thử lại giúp mình nhé.', en: 'Could not approve: {loi}. Please try again.' },
  'ch.skipped': { vi: 'Đã bỏ qua dự định này — mình chưa làm gì cả. Bạn muốn đổi phương án nào?', en: 'Skipped this plan — nothing was done. What would you like instead?' },
  'ch.cancelled': { vi: 'Đã huỷ kế hoạch. Bạn muốn điều chỉnh lại thế nào?', en: 'Plan cancelled. How would you like to adjust it?' },
  'ch.replySent': { vi: 'Đã gửi trả lời trong đúng luồng thư ✓', en: 'Reply sent in the same thread ✓' },
  'ch.sendFail': { vi: 'Gửi KHÔNG thành công (mạng hoặc quyền Gmail). Thư CHƯA được gửi — bạn kiểm tra lại người nhận rồi bấm gửi lần nữa nhé.', en: 'Send FAILED (network or Gmail permission). The message was NOT sent — check the recipient and press send again.' },
  'ch.autoArchive': { vi: 'lưu trữ {n}', en: 'archived {n}' },
  'ch.autoRead': { vi: 'đánh dấu đã đọc {n}', en: 'marked {n} read' },
  'ch.autoFlag': { vi: 'gắn sao {n}', en: 'starred {n}' },
  'ch.autoReplied': { vi: 'gửi {n} trả lời', en: 'sent {n} replies' },
  'ch.autoNothing': { vi: 'không thay đổi gì', en: 'changed nothing' },
  'ch.autoDone': { vi: 'Mèo đã tự lái xong: {tt}. Hộp thư gọn hơn rồi ✨', en: 'The cat finished driving: {tt}. Tidier already ✨' },
  'ch.categorised': { vi: 'Đã phân loại {n} thư theo nhãn bạn chọn.', en: 'Sorted {n} messages into the labels you chose.' },
  'ch.ttsOff': { vi: 'Tắt đọc câu trả lời', en: 'Turn off reading answers aloud' },
  'ch.ttsOn': { vi: 'Bật đọc câu trả lời', en: 'Read answers aloud' },
  'ch.aboutThis': { vi: 'đang nói về việc này', en: 'talking about this' },
  'ch.removeCtx': { vi: 'Bỏ {ten}', en: 'Remove {ten}' },
  'ch.outOfTokens': { vi: 'Đã hết token — nâng gói để hỏi tiếp…', en: 'Out of tokens — upgrade to keep asking…' },
  'ch.phExample': { vi: "Nhắn cho trợ lý... vd: 'lưu trữ thư bản tin'", en: "Message the assistant… e.g. 'archive newsletters'" },
  'ch.unpin': { vi: 'Bỏ ghim', en: 'Unpin' },
  'ch.mailCancelled': { vi: 'Đã huỷ thư', en: 'Message discarded' },
  'ch.mailSealed': { vi: 'Đã niêm phong mật thư ✓', en: 'Message sealed ✓' },
  'ch.editDraft': { vi: 'Chỉnh sửa bản nháp', en: 'Edit the draft' },
  'ch.replyDraft': { vi: 'Bản nháp trả lời', en: 'Draft reply' },
  'ch.edit': { vi: 'Chỉnh sửa', en: 'Edit' },
  'ch.includeAgain': { vi: 'Bao gồm lại', en: 'Include again' },
  'ch.skipThis': { vi: 'Bỏ qua thư này', en: 'Skip this message' },
  'ch.executing': { vi: 'Đang thực thi…', en: 'Executing…' },
  'ch.planProposed': { vi: 'Kế hoạch đề xuất', en: 'Proposed plan' },
  'ch.checkBefore': { vi: 'kiểm tra kỹ trước khi duyệt', en: 'check carefully before approving' },
  'ch.title': { vi: 'Trợ lý MeoArc', en: 'MeoArc Assistant' },

  'tv.depTime': { vi: 'Giờ bay', en: 'Departure' },
  'tv.airline': { vi: 'Hãng', en: 'Airline' },
  'tv.aircraft': { vi: 'Máy bay', en: 'Aircraft' },
  'tv.terminal': { vi: 'Nhà ga', en: 'Terminal' },
  'tv.status': { vi: 'Trạng thái', en: 'Status' },
  'tv.serverSaid': { vi: 'Máy chủ trả về {ma}', en: 'Server returned {ma}' },
  'tv.noServer': { vi: 'Không gọi được máy chủ: {loi}', en: 'Could not reach the server: {loi}' },
  'tv.asking': { vi: 'đang hỏi máy chủ…', en: 'asking the server…' },
  'tv.flights': { vi: 'Chuyến bay', en: 'Flights' },
  'tv.hotels': { vi: 'Khách sạn', en: 'Hotels' },
  'tv.from': { vi: 'Từ', en: 'From' },
  'tv.to': { vi: 'Đến', en: 'To' },
  'tv.flightDate': { vi: 'Ngày bay', en: 'Date' },
  'tv.city': { vi: 'Thành phố', en: 'City' },
  'tv.checkIn': { vi: 'Nhận phòng', en: 'Check-in' },
  'tv.checkOut': { vi: 'Trả phòng', en: 'Check-out' },
  'tv.searching': { vi: 'Đang hỏi…', en: 'Searching…' },
  'tv.search': { vi: 'Tra cứu', en: 'Look up' },
  'tv.filtered': { vi: '{d}/{n} chuyến · đang lọc', en: '{d}/{n} flights · filtered' },
  'tv.results': { vi: '{n} kết quả', en: '{n} results' },
  'tv.queriedAt': { vi: ' · truy vấn lúc ', en: ' · queried at ' },
  'tv.hideRaw': { vi: 'Ẩn phản hồi gốc', en: 'Hide raw response' },
  'tv.showRaw': { vi: 'Xem phản hồi gốc từ máy chủ', en: 'View the raw server response' },
  'tv.hasRealHotel': { vi: '{tp} · có khách sạn thật', en: '{tp} · has real hotels' },
  'tv.terminalIs': { vi: 'nhà ga {n}', en: 'terminal {n}' },
  'tv.nonstop': { vi: 'bay thẳng', en: 'non-stop' },
  'tv.stops': { vi: '{n} điểm dừng', en: '{n} stop(s)' },
  'tv.refundable': { vi: 'hoàn được', en: 'refundable' },
  'tv.nonRefundable': { vi: 'không hoàn', en: 'non-refundable' },
  'tv.viewFlight': { vi: 'Xem chuyến bay', en: 'View flight' },
  'tv.viewPrice': { vi: 'Xem giá', en: 'View price' },
  'tv.freeCancel': { vi: 'huỷ miễn phí', en: 'free cancellation' },
  'tv.noCancel': { vi: 'không huỷ được', en: 'non-cancellable' },
  'tv.detail': { vi: 'Chi tiết', en: 'Details' },

  'nav.pressure7': { vi: 'Áp lực 7 ngày', en: '7-day load' },
  'nav.online': { vi: 'Trực tuyến', en: 'Online' },
  'nav.folders': { vi: 'Thư mục', en: 'Folders' },
  'nav.overloadDays': { vi: '{n} ngày quá tải · {gio} giờ', en: '{n} overloaded days · {gio} h' },
  'nav.busyDays': { vi: '{n} ngày có việc · {gio} giờ', en: '{n} days with tasks · {gio} h' },

  'settings.langNote': {
    vi: 'Đổi ngôn ngữ khung giao diện và ngôn ngữ trợ lý trả lời. Một số phần (thẻ kết quả, thông báo lỗi) hiện vẫn là tiếng Việt.',
    en: 'Changes the interface chrome and the language the assistant replies in. Some parts (result cards, error messages) are still in Vietnamese.',
  },
}

/* ── VÌ SAO CÓ `t()` Ở TẦNG MODULE, KHÔNG CHỈ HOOK ──────────────────────────
   `useT()` là hook nên chỉ gọi được TRONG component. Nhưng chuỗi cần dịch nằm rải
   rác ở những chỗ hook với tới không được: mảng hằng số ở đầu file (`SKILLS`,
   `NAV_ITEMS`), component con lồng sâu chưa nhận context, hàm tiện ích thuần.
   Ép mọi chỗ đó thành component chỉ để gọi hook được là bẻ cong cấu trúc mã vì một
   giới hạn kỹ thuật — cái giá trả bằng khả năng đọc, cho một thứ không ai thấy.

   Nên giữ MỘT biến ở tầng module, và cho `t()` đọc nó. Đổi ngôn ngữ thì provider vừa
   cập nhật biến vừa gắn `key` mới cho cây con → React dựng lại toàn bộ, và mọi `t()`
   chạy lại với giá trị mới. Dựng lại làm mất state cục bộ (ô đang gõ dở, tab đang
   mở) — chấp nhận được, vì đổi ngôn ngữ là việc hiếm và người dùng cũng mong đợi
   màn hình vẽ lại. */
let _ngonHienTai: Ngon = 'vi'

/** Dịch ở BẤT KỲ đâu, kể cả ngoài component.
 *
 *  `thay` điền vào chỗ `{ten}` trong câu. Phải có nó vì rất nhiều câu là câu ghép
 *  ("Đã xoá 3 thư") mà TRẬT TỰ TỪ giữa hai thứ tiếng không giống nhau — nối chuỗi
 *  bằng `+` ở nơi gọi thì bản tiếng Anh mãi mãi kẹt theo trật tự tiếng Việt.
 *  Thiếu biến thì để nguyên `{ten}`: một chỗ trống nhìn thấy được thì sửa được,
 *  còn ném lỗi ở đây là làm vỡ cả màn hình chỉ vì một dòng chữ. */
export function t(khoa: string, thay?: Record<string, string | number>): string {
  const cau = TU_DIEN[khoa]?.[_ngonHienTai] ?? khoa
  if (!thay) return cau
  return cau.replace(/\{(\w+)\}/g, (nguyen, ten) =>
    ten in thay ? String(thay[ten]) : nguyen,
  )
}

const Boi = createContext<{ ngon: Ngon; datNgon: (n: Ngon) => void }>({
  ngon: 'vi',
  datNgon: () => {},
})

export function NhaCungCapNgonNgu({ children }: { children: ReactNode }) {
  const [ngon, setNgon] = useState<Ngon>(() => {
    try {
      return (localStorage.getItem(KHOA_LUU) as Ngon) || 'vi'
    } catch {
      // Cửa sổ ẩn danh hoặc trình duyệt chặn lưu trữ: về mặc định, đừng để vỡ app.
      return 'vi'
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(KHOA_LUU, ngon)
    } catch {
      /* không lưu được thì thôi — lần sau mở lại về tiếng Việt, không phải lỗi chặn dùng */
    }
    document.documentElement.lang = ngon
  }, [ngon])

  // Cập nhật biến module TRƯỚC khi vẽ, để `t()` trong lần vẽ này đã đúng ngôn ngữ.
  _ngonHienTai = ngon

  return (
    <Boi.Provider value={{ ngon, datNgon: setNgon }}>
      {/* `key` đổi → React dựng lại cả cây. Không có nó thì `children` giữ nguyên
          tham chiếu nên React bỏ qua, và mọi `t()` ở tầng module vẫn trả chữ cũ. */}
      <div key={ngon} className="contents">
        {children}
      </div>
    </Boi.Provider>
  )
}

/** `const t = useT()` rồi `t('nav.inbox')`. */
export function useT() {
  const { ngon } = useContext(Boi)
  return (khoa: string, thay?: Record<string, string | number>): string => {
    const cau = TU_DIEN[khoa]?.[ngon] ?? khoa
    if (!thay) return cau
    return cau.replace(/\{(\w+)\}/g, (nguyen, ten) =>
      ten in thay ? String(thay[ten]) : nguyen,
    )
  }
}

/** Đọc/đổi ngôn ngữ hiện tại (dùng ở màn Cài đặt). */
export function useNgonNgu() {
  return useContext(Boi)
}
