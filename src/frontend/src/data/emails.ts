// Thư demo cho màn Lịch trình. `demo-lich.ts` chỉ nhập KIỂU từ file này, mà nhập
// kiểu bị xoá lúc biên dịch — nên vòng phụ thuộc này không tồn tại khi chạy.
import { DEMO_LICH } from '@/data/demo-lich'
import { DEMO_QUA_TAI } from '@/data/demo-qua-tai'

/** Category màu của inbox — tên màu lấy từ palette "Provence Meadow".
 *  Bảng màu cụ thể nằm ở email-list.tsx (CATEGORY) để giữ một nguồn duy nhất. */
export type Category = 'moss' | 'sea' | 'sun' | 'cherry' | 'sky' | 'terra' | 'wine' | 'jade'

export type Attachment = { name: string; size: string }

/** Ba trục nhãn AI theo PA1 §4.2.9. Priority và Status CHỈ có với thư mang tính
 *  công việc; thư còn lại để `null` — `null` nghĩa là KHÔNG PHẢI việc, khác hẳn
 *  'Low'/'Done' (đã xét rồi kết luận việc nhẹ / đã xong). */
export type Priority = 'High' | 'Medium' | 'Low'
export type TaskStatus = 'Todo' | 'Waiting' | 'Done'

export type Email = {
  id: string
  sender: string
  senderEmail: string
  senderInitial: string
  to: string
  /** ĐỒNG GỬI. Quyết định "Trả lời tất cả" có nghĩa hay không: một thư `to` chỉ mình
   *  mình nhưng `cc` ba người thì đó là thư gửi cả nhóm, và trả lời riêng là sai. */
  cc?: string | null
  subject: string
  preview: string
  body: string[]
  time: string
  date: string
  unread: boolean
  starred: boolean
  category: Category
  label?: string
  /** Thân thư HTML gốc (render đúng chuẩn Gmail ở màn chi tiết) — thiếu thì dùng body text. */
  html?: string | null
  attachments?: Attachment[]
  /** CÓ tệp đính kèm hay không. Tách khỏi `attachments` vì danh sách thư biết CÓ nhưng
   *  KHÔNG biết tên (Gmail `format=metadata` không trả `parts`). */
  hasAttachment?: boolean
  /** AI Triage (UC015): action=cần bạn xử lý · waiting=đang đợi · fyi=để biết */
  priority?: Priority | null
  status?: TaskStatus | null
  /** Tóm tắt 1 dòng do AI quét sẵn (UC008) — TL;DR cho card & smart card. */
  tldr?: string
  /** Thư mục (mặc định inbox) — cho nav trái lọc thật. */
  /** Thư mục. `spam` được thêm cùng nút "Thư rác" ở nav — thư mục người ta cần
   *  nhất khi một lá thư quan trọng "biến mất", và đó là lúc họ hoảng nhất. */
  folder?: 'inbox' | 'sent' | 'drafts' | 'archive' | 'trash' | 'spam' 
}

const ME = 'Anh Quân <meoarc.hcmus@gmail.com>'

const EMAILS_GOC: Email[] = [
  {
    id: '1',
    sender: 'Giáo vụ HCMUS',
    senderEmail: 'giaovu@fit.hcmus.edu.vn',
    senderInitial: 'G',
    to: ME,
    subject: 'Nhắc nộp báo cáo SRS — Nhóm 7',
    preview: 'Các nhóm vui lòng nộp bản SRS hoàn chỉnh trước 23:59 thứ Sáu tuần này...',
    body: [
      'Chào các em,',
      'Các nhóm vui lòng nộp bản SRS hoàn chỉnh (PDF + bản Word) lên hệ thống Moodle trước 23:59 thứ Sáu tuần này. Lưu ý đặt tên file theo định dạng Nhom07_SRS_v1.pdf.',
      'Bản nộp cần đầy đủ: danh sách Use Case, đặc tả Main/Alternative Scenario, sơ đồ Use Case, và mockup giao diện minh hoạ.',
      'Trân trọng,\nPhòng Giáo vụ — Khoa CNTT, HCMUS',
    ],
    time: '08:42',
    date: 'Hôm nay, 08:42',
    unread: true,
    starred: true,
    category: 'moss',
    label: 'Học tập',
    priority: 'Medium',
    status: 'Todo',
    tldr: 'Hạn nộp SRS hoàn chỉnh: 23:59 thứ Sáu, đặt tên Nhom07_SRS_v1.pdf.',
    attachments: [
      { name: 'Mau_SRS_Intro2SE.docx', size: '248 KB' },
      { name: 'Lich_nop_baocao.pdf', size: '96 KB' },
    ],
  },
  /* ── MỘT CUỘC TRAO ĐỔI BA LƯỢT ─────────────────────────────────────────────
     Bộ mock trước đây KHÔNG có luồng nào: mọi thư đều đứng lẻ. Nên phần gộp luồng
     và màn xem cả cuộc trao đổi không bao giờ chạy khi xem thử — mà không thấy chạy
     thì cũng không biết nó đúng hay sai. Ba lượt dưới đây dùng chung tiêu đề (khác
     nhau tiền tố "Re:") để đúng cơ chế gom luồng của mock. */
  {
    id: '1b',
    sender: 'Anh Quân',
    senderEmail: 'meoarc.hcmus@gmail.com',
    senderInitial: 'Q',
    to: 'Phòng Giáo vụ <giaovu@fit.hcmus.edu.vn>',
    subject: 'Re: Nhắc nộp báo cáo SRS — Nhóm 7',
    preview: 'Dạ em xin xác nhận nhóm 7 sẽ nộp đúng hạn ạ...',
    body: [
      'Dạ em chào thầy/cô,',
      'Em xin xác nhận Nhóm 7 sẽ nộp đúng hạn ạ. Cho em hỏi phần mockup giao diện có cần xuất riêng ra PDF không, hay để trong file Word là được ạ?',
      'Em cảm ơn ạ.\nPhạm Trần Anh Quân — 24127226',
    ],
    time: '09:15',
    date: 'Hôm nay, 09:15',
    unread: false,
    starred: false,
    category: 'moss',
    label: 'Học tập',
    folder: 'sent',
    // Tệp nằm ở LƯỢT THỨ HAI của cuộc trao đổi — đúng chỗ người ta hay đính kèm nhất,
    // và đúng chỗ bản đầu KHÔNG vẽ gì cả.
    attachments: [{ name: 'Nhom07_SRS_v1_draft.pdf', size: '1.2 MB' }],
  },
  {
    id: '1c',
    sender: 'Phòng Giáo vụ',
    senderEmail: 'giaovu@fit.hcmus.edu.vn',
    senderInitial: 'G',
    // HAI người nhận — để "Trả lời tất cả" có nghĩa (nút chỉ hiện khi thư thật sự
    // có nhiều người). Cũng sát thực tế hơn: giáo vụ trả lời thì Cc cả nhóm.
    to: `${ME}, Nhóm 7 <nhom7@fit.hcmus.edu.vn>`,
    subject: 'Re: Nhắc nộp báo cáo SRS — Nhóm 7',
    preview: 'Để trong file Word là được em nhé...',
    body: [
      'Chào em,',
      'Để trong file Word là được em nhé, không cần xuất riêng. Nhớ đánh số hình và có chú thích bên dưới mỗi mockup.',
      'Trân trọng,\nPhòng Giáo vụ — Khoa CNTT, HCMUS',
    ],
    time: '09:40',
    date: 'Hôm nay, 09:40',
    unread: true,
    starred: false,
    category: 'moss',
    label: 'Học tập',
    priority: 'Medium',
    status: 'Todo',
  },
  {
    id: '2',
    sender: 'GitHub',
    senderEmail: 'notifications@github.com',
    senderInitial: 'G',
    to: ME,
    subject: '[meoarc-frontend] PR #12 đã được review',
    preview: 'quanpta đã yêu cầu thay đổi trên pull request: "feat: add chat canvas"...',
    body: [
      'quanpta đã review pull request #12 — "feat: add chat canvas".',
      'Trạng thái: Changes requested. 2 bình luận mới ở src/components/layout/chat-panel.tsx.',
      'Mở pull request trên GitHub để xem chi tiết và phản hồi.',
    ],
    time: '08:10',
    date: 'Hôm nay, 08:10',
    unread: true,
    starred: false,
    category: 'sea',
    label: 'Công việc',
    priority: 'Medium',
    status: 'Todo',
    tldr: 'PR #12 bị "Changes requested" — 2 bình luận cần bạn xử lý.',
  },
  {
    id: '3',
    sender: 'Google Cloud',
    senderEmail: 'cloud-noreply@google.com',
    senderInitial: 'C',
    to: ME,
    subject: 'Gemini API — hạn mức tháng này',
    preview: 'Dự án của bạn đã dùng 64% hạn mức request. Xem chi tiết sử dụng...',
    body: [
      'Xin chào,',
      'Dự án meoarc-prod đã sử dụng 64% hạn mức request của Gemini API trong chu kỳ thanh toán này.',
      'Bạn có thể xem chi tiết mức sử dụng theo từng model và thiết lập cảnh báo ngân sách trong Google Cloud Console.',
    ],
    time: 'Hôm qua',
    date: 'Hôm qua, 19:20',
    unread: false,
    starred: false,
    category: 'sun',
    label: 'Cập nhật & Hệ thống',
    tldr: 'Đã dùng 64% hạn mức Gemini API tháng này — chưa cần hành động.',
  },
  {
    id: '4',
    sender: 'Trần Minh Khoa',
    senderEmail: 'khoa.tran@gmail.com',
    senderInitial: 'K',
    to: ME,
    subject: 'Re: Phân chia use case backend',
    preview: 'Ok bạn, mình nhận UC005 với UC006 nhé. Còn phần MCP để cuối tuần họp...',
    body: [
      'Ok bạn,',
      'Mình nhận UC005 (Search & Filter) với UC006 (Manage Emails) nhé. Phần MCP (UC012) để cuối tuần họp rồi chia tiếp.',
      'Tối nay mình push nhánh feat/search, bạn review giúp nha.',
    ],
    time: 'Hôm qua',
    date: 'Hôm qua, 16:05',
    unread: false,
    starred: true,
    category: 'cherry',
    label: 'Cá nhân',
    priority: 'Medium',
    status: 'Waiting',
    tldr: 'Khoa nhận UC005/UC006; tối nay push nhánh feat/search chờ bạn review. Có hẹn cuối tuần họp chia phần MCP.',
  },
  {
    id: '5',
    sender: 'Vercel',
    senderEmail: 'noreply@vercel.com',
    senderInitial: 'V',
    to: ME,
    subject: 'Deployment sẵn sàng để preview',
    preview: 'Bản preview cho nhánh main đã build thành công và sẵn sàng xem thử...',
    body: [
      'Deployment cho meoarc-frontend đã hoàn tất.',
      'Nhánh: main · Trạng thái: Ready · Thời gian build: 38s.',
      'Mở bản preview để kiểm tra trước khi promote lên production.',
    ],
    time: 'T4',
    date: 'Thứ 4, 11:48',
    unread: false,
    starred: false,
    category: 'sun',
    label: 'Cập nhật & Hệ thống',
    tldr: 'Preview nhánh main build xong (38s) — sẵn sàng kiểm tra trước khi promote.',
  },
  {
    id: '6',
    sender: 'Newsletter UX',
    senderEmail: 'hello@uxweekly.com',
    senderInitial: 'N',
    to: ME,
    subject: 'Xu hướng thiết kế "quiet luxury" 2026',
    preview: 'Tuần này: bảng màu ấm, typography serif, và sự trở lại của old-money...',
    body: [
      'Chào bạn,',
      'Số tuần này: bảng màu ấm, typography serif có trọng lượng, và sự trở lại của thẩm mỹ "old-money" trong sản phẩm số.',
      'Đọc bản đầy đủ trên web để xem các case study kèm ảnh minh hoạ.',
    ],
    time: 'T3',
    date: 'Thứ 3, 09:15',
    unread: false,
    starred: false,
    category: 'sun',
    label: 'Cập nhật & Hệ thống',
    tldr: 'Bản tin UX: màu ấm, serif có trọng lượng, thẩm mỹ "old-money" lên ngôi 2026.',
  },

  /* ----- Đã gửi ----- */
  {
    id: 's1',
    sender: 'Giáo vụ HCMUS',
    senderEmail: 'giaovu@fit.hcmus.edu.vn',
    senderInitial: 'G',
    to: 'giaovu@fit.hcmus.edu.vn',
    subject: 'Re: Nhắc nộp báo cáo SRS — Nhóm 7',
    preview: 'Dạ em chào thầy/cô, nhóm 7 sẽ nộp bản SRS đúng hạn ạ...',
    body: [
      'Dạ em chào thầy/cô,',
      'Nhóm 7 đã nắm thông tin và sẽ nộp bản SRS hoàn chỉnh trước hạn. Em cảm ơn ạ.',
      'Trân trọng,\nAnh Quân',
    ],
    time: '09:02',
    date: 'Hôm nay, 09:02',
    unread: false,
    starred: false,
    category: 'moss',
    label: 'Học tập',
    folder: 'sent',
  },
  {
    id: 's2',
    sender: 'Trần Minh Khoa',
    senderEmail: 'khoa.tran@gmail.com',
    senderInitial: 'K',
    to: 'khoa.tran@gmail.com',
    subject: 'Re: Phân chia use case backend',
    preview: 'Ok bạn, mình review nhánh feat/search tối nay nhé...',
    body: ['Ok bạn,', 'Mình review nhánh feat/search tối nay nhé. Cảm ơn!', 'Quân'],
    time: 'Hôm qua',
    date: 'Hôm qua, 17:10',
    unread: false,
    starred: false,
    category: 'cherry',
    label: 'Cá nhân',
    folder: 'sent',
  },

  /* ----- Nháp ----- */
  {
    id: 'd1',
    sender: 'Nháp',
    senderEmail: '',
    senderInitial: '✎',
    to: 'cloud-noreply@google.com',
    subject: 'Hỏi về hạn mức Gemini API',
    preview: 'Dạ cho em hỏi về cách nâng hạn mức request...',
    body: ['Dạ cho em hỏi về cách nâng hạn mức request cho dự án meoarc-prod ạ.', '(đang soạn…)'],
    time: 'Hôm qua',
    date: 'Hôm qua, 20:05',
    unread: false,
    starred: false,
    category: 'sun',
    folder: 'drafts',
  },

  /* ----- Thư rác -----
     THIẾU HẲN ở bản trước: `folder: 'spam'` không xuất hiện lần nào trong toàn bộ
     dữ liệu mẫu, nên bấm "Thư rác" ra một danh sách rỗng và trông như tính năng
     hỏng. Nút có mà bấm vào không có gì thì tệ hơn là không có nút.
     Ba lá đủ để thấy bộ lọc chạy: một lừa đảo trắng trợn, một giả danh ngân hàng,
     một quảng cáo. Lá giả danh ngân hàng CÓ CHỦ Ý — đó là loại thư người dùng
     phải tự nhận ra, và là lý do thư mục này đáng được nhìn tới. */
  {
    id: 'sp1',
    sender: 'Trúng thưởng Quốc tế',
    senderEmail: 'winner@lottery-intl.top',
    senderInitial: 'T',
    to: ME,
    subject: 'CHÚC MỪNG! Bạn đã trúng 500.000.000đ',
    preview: 'Bạn là người may mắn được chọn. Gửi thông tin tài khoản để nhận...',
    body: [
      'CHÚC MỪNG QUÝ KHÁCH!',
      'Bạn là người may mắn được chọn trong đợt quay số quốc tế. Giải thưởng 500.000.000đ đang chờ.',
      'Vui lòng gửi số tài khoản ngân hàng và ảnh CCCD để chúng tôi chuyển tiền ngay hôm nay.',
    ],
    time: '03:14',
    date: 'Hôm nay, 03:14',
    unread: true,
    starred: false,
    category: 'terra',
    label: 'Thư rác',
    folder: 'spam',
  },
  {
    id: 'sp2',
    sender: 'Vietcombank Security',
    senderEmail: 'security@vietcombank-verify.info',
    senderInitial: 'V',
    to: ME,
    subject: 'Tài khoản của bạn sẽ bị khoá trong 24 giờ',
    preview: 'Xác minh ngay để tránh bị khoá. Nhấn vào liên kết bên dưới...',
    body: [
      'Kính gửi Quý khách,',
      'Hệ thống ghi nhận hoạt động bất thường. Tài khoản sẽ bị khoá trong 24 giờ nếu không xác minh.',
      'Nhấn vào liên kết bên dưới và đăng nhập để xác minh danh tính.',
    ],
    time: '01:52',
    date: 'Hôm nay, 01:52',
    unread: true,
    starred: false,
    category: 'wine',
    label: 'Thư rác',
    folder: 'spam',
  },
  {
    id: 'sp3',
    sender: 'Khoá học online',
    senderEmail: 'promo@edu-deals.biz',
    senderInitial: 'K',
    to: ME,
    subject: 'Giảm 90% toàn bộ khoá học — chỉ hôm nay',
    preview: 'Cơ hội cuối cùng! Đăng ký ngay kẻo lỡ...',
    body: ['Cơ hội cuối cùng! Giảm 90% toàn bộ khoá học lập trình. Đăng ký ngay kẻo lỡ.'],
    time: 'Hôm qua',
    date: 'Hôm qua, 22:40',
    unread: false,
    starred: false,
    category: 'sun',
    label: 'Thư rác',
    folder: 'spam',
  },

  /* ----- Thùng rác ----- */
  {
    id: 't1',
    sender: 'Promo Shopee',
    senderEmail: 'no-reply@shopee.vn',
    senderInitial: 'S',
    to: ME,
    subject: 'Sale 12.12 — giảm đến 50%',
    preview: 'Săn deal khủng ngày đôi, mã freeship toàn sàn...',
    body: ['Săn deal khủng ngày đôi!', 'Mã freeship toàn sàn, áp dụng hôm nay.'],
    time: 'T2',
    date: 'Thứ 2, 08:00',
    unread: false,
    starred: false,
    category: 'terra',
    label: 'Mua sắm & Ưu đãi',
    folder: 'trash',
  },
]

/** Hop thu demo = bo goc + thu lich trinh thang 8-9 + bo THU DAY de xem man
 *  Lich trinh duoi tai that (xem data/demo-qua-tai.ts, tat bang co `BAT`).
 *  Tach lam ba de xoa tung bo chi can bo dung mot dong. */
export const emails: Email[] = [...EMAILS_GOC, ...DEMO_LICH, ...DEMO_QUA_TAI]
