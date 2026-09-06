/**
 * MeoArc API adapter — LỚP HỢP ĐỒNG FE ↔ BE.
 *
 * Đây là điểm chạm DUY NHẤT giữa giao diện và "thế giới bên ngoài". Mọi màn nên
 * gọi qua `api.*` thay vì dùng trực tiếp dữ liệu/logic mock. Nhờ vậy khi backend
 * thật sẵn sàng, chỉ cần đặt biến môi trường `VITE_API_BASE_URL` là chuyển sang
 * HTTP — KHÔNG phải sửa component nào.
 *
 * - Bỏ trống `VITE_API_BASE_URL`  → dùng `createMockApi()` (chạy hoàn toàn offline cho demo/SRS).
 * - Đặt `VITE_API_BASE_URL=...`   → dùng `createHttpApi()` (gọi REST/SSE thật).
 *
 * Interface `MeoArcApi` bám sát docs/02-API-CONTRACT.md. Kiểu dữ liệu: docs/01-DATA-MODEL.md.
 */
import { interpretCommand, type AgentReply, type PlanOp } from '@/lib/agent'
import { emailHaystack, interpretNL, matchText } from '@/lib/search'
import { emails as seedEmails, type Category, type Email } from '@/data/emails'
import type { User } from '@/auth/auth-context'
import type { AutopilotResult } from '@/components/layout/autopilot-widget'

/* ----------------------------- Kiểu I/O hợp đồng ----------------------------- */

export type EmailQuery = {
  folder?: string
  category?: Category | 'all'
  unread?: boolean
  starred?: boolean
  attachment?: boolean
  /** Từ khoá hoặc câu ngôn ngữ tự nhiên (khi nl=true). */
  q?: string
  nl?: boolean
  /** Phân trang: token trang kế (lấy từ nextCursor lần trước) + số thư mỗi trang. */
  cursor?: string
  limit?: number
  /** Nút "Làm mới": bỏ qua cache backend, ép lấy bản mới nhất từ Gmail. */
  fresh?: boolean
}

export type EmailListResult = {
  items: Email[]
  nextCursor?: string | null
  /** Khi nl=true: các tiêu chí BE/mock đã "hiểu" (để hiển thị "Đã hiểu: …"). */
  criteria?: string[]
}

export type SendEmailInput = {
  to: string
  cc?: string[]
  bcc?: string[]
  subject: string
  body: string
  /** Bản CÓ ĐỊNH DẠNG. Gửi KÈM `body` chứ không thay — chỗ nào đọc được HTML thì
   *  hiện đậm/nghiêng/màu, chỗ nào không thì vẫn còn chữ thuần để đọc. */
  html?: string
  /** id các tệp đã upload qua `uploadFile` → BE lấy bytes đính vào thư. */
  attachmentIds?: string[]
}

/* --- UC011: lịch sử hội thoại ------------------------------------------------ */
/** AgentReply kèm id phiên do BE trả về (để FE bám đúng cuộc trò chuyện). */
/** AgentReply kèm hai mã máy chủ cấp cho lượt này.
 *  `messageId` là mã CỦA MÁY CHỦ cho đúng thẻ vừa nhận — phải dùng nó làm id cục bộ,
 *  không tự sinh mã mới, nếu không thì không đánh dấu "đã duyệt" lên máy chủ được. */
export type AgentReplyWithId = AgentReply & { conversationId?: string; messageId?: string }

/** 1 tin trong lịch sử đã lưu (khuôn BE: user text HOẶC thẻ agent). */
export type StoredMessage =
  | { id?: string; role: 'user'; text: string; resolved?: boolean }
  | { id?: string; role: 'agent'; reply: AgentReply; resolved?: boolean }

/** 1 dòng ở drawer lịch sử (danh sách, không kèm toàn bộ tin nhắn). */
export type ConversationSummary = {
  id: string
  title: string
  pinned: boolean
  updatedAt: string
  messageCount: number
  preview: string
}

/** Mở 1 phiên: kèm messages để vẽ lại / tiếp tục. */
export type ConversationDetail = {
  id: string
  title: string
  pinned: boolean
  createdAt: string
  updatedAt: string
  messages: StoredMessage[]
}

/* --- Accountability: Notifications (chuông + panel) ------------------------- */
/** 1 thông báo (khớp _notif_dto backend). type: 'info' | 'success' | 'warning'. */
export type NotificationItem = {
  id: number
  type: string
  message: string
  read: boolean
  createdAt: string | null
}
export type NotificationList = { items: NotificationItem[]; unread: number }

/** Một mức hạn mức token (ngày hoặc tháng). */
export type TokenBucket = { used: number; limit: number; remaining: number }

/** Gói hiện tại + mức tiêu thụ token — nguồn cho thanh usage và trang nâng cấp. */
export type SubscriptionStatus = {
  tier: string
  tierLabel: string
  isActive: boolean
  /** FR-02.7 — số ngày thư gần nhất mà trợ lý được phép quét, theo gói (NFR-08). */
  scanDays: number
  daily: TokenBucket
  monthly: TokenBucket
}

/** Một gói trong danh mục (backend là nguồn duy nhất của số liệu). */
export type Plan = {
  id: string
  label: string
  tagline: string
  priceVnd: number
  /** Cửa sổ quét hộp thư của gói này (ngày). */
  scanDays: number
  dailyTokens: number
  monthlyTokens: number
  features: string[]
}

/** Toàn bộ năng lực backend mà FE cần. Mỗi nhóm map 1-1 với docs/02-API-CONTRACT.md. */
/* ------------------------- Cá nhân hoá — PA2 §1.5.2 ------------------------- */

/** Các trường người dùng sửa được. Tách riêng khỏi `Preferences` vì hai thứ do hai
 *  phía sở hữu: cái này client gửi lên, `promptPreview`/`availableTones` do máy chủ trả. */
export interface PreferenceFields {
  language: string
  displayName: string | null
  theme: string
  tonePreference: string
  signatureNote: string | null
  customInstruction: string | null
}

export interface Preferences extends PreferenceFields {
  /** Đoạn văn kết tinh mà trợ lý thật sự đọc. Cho người dùng XEM TRƯỚC thay vì
   *  gõ vào ô rồi đoán xem có tác dụng gì. */
  promptPreview: string
  /** { khoá: mô tả } — danh sách giọng văn do máy chủ định nghĩa, client không tự bịa. */
  availableTones: Record<string, string>
}

export interface MeoArcApi {
  // Auth — UC001/002
  me(): Promise<User | null>
  loginWithGoogle(): Promise<User>
  loginWithOutlook(): Promise<User>  // đa provider — điều hướng sang đăng nhập Microsoft
  logout(): Promise<void>
  revokeAccess(): Promise<void>

  // Đọc & tìm — UC003/004/005
  listEmails(query?: EmailQuery): Promise<EmailListResult>
  /** Đánh dấu MỘT thẻ duyệt là đã xử lý, và ghi xuống máy chủ.
   *  Không lưu thì mở lại hội thoại là thẻ quay về "chờ duyệt" — kể cả thẻ xoá đã chạy. */
  resolveMessage(convId: string, msgId: string): Promise<void>
  getEmail(id: string): Promise<Email | null>
  /** MỌI thư trong luồng của thư này, sắp CŨ → MỚI (UC004 — xem cả cuộc trao đổi). */
  getThread(id: string): Promise<Email[]>
  markEmailRead(id: string, read: boolean): Promise<void>
  /** UC008 — tóm tắt 1 email bằng LLM → list gạch đầu dòng (thẻ 'Tóm tắt · AI'). Mock trả []. */
  summarizeEmail(id: string): Promise<string[]>

  // Quản lý — UC006 (nhận mảng id cho cả 1 thư lẫn hàng loạt)
  markRead(ids: string[], read: boolean): Promise<void>
  setImportant(ids: string[], value: boolean): Promise<void>
  applyLabel(ids: string[], category: Category, label: string): Promise<void>
  archiveEmails(ids: string[]): Promise<void>
  /** Đánh dấu / bỏ đánh dấu thư rác — cả hai chiều đều đảo ngược được. */
  spamEmails(ids: string[]): Promise<void>
  notSpamEmails(ids: string[]): Promise<void>
  deleteEmails(ids: string[]): Promise<void>
  /** Khôi phục thư từ thùng rác về hộp thư. */
  restoreEmails(ids: string[]): Promise<void>

  // Soạn & gửi — UC010
  sendEmail(input: SendEmailInput): Promise<{ id: string }>
  /** Trả lời 1 thư — BE tự suy người nhận/tiêu đề từ thư gốc, giữ đúng luồng. */
  replyEmail(id: string, body: string, replyAll?: boolean, html?: string): Promise<{ id: string }>
  /** Chuyển tiếp thư sang địa chỉ khác, kèm lời nhắn. */
  forwardEmail(id: string, to: string, note?: string): Promise<{ id: string }>
  /** Upload 1 tệp đính kèm lên backend → trả metadata { id, name, size }. */
  uploadFile(file: File): Promise<{ id: string; name: string; size: string }>
  /** UC010 — lưu bản nháp (không gửi) lên Gmail/Outlook + hiện ở tab Nháp. */
  saveDraft(input: SendEmailInput): Promise<{ id: string }>
  /** UC010 — gợi ý đoạn tiếp theo khi soạn (Smart Compose) dựa trên tiêu đề + phần đang gõ. */
  suggestCompose(subject: string, body: string): Promise<string>
  /** Autocomplete người nhận (như Gmail) — địa chỉ suy từ thư đã đồng bộ. */
  contacts(q: string): Promise<{ name: string; email: string }[]>

  // Gói dịch vụ & hạn mức token (freemium)
  /** Gói hiện tại + token đã dùng/còn lại theo ngày & tháng. */
  subscription(): Promise<SubscriptionStatus>
  /** Danh mục 3 gói để dựng trang nâng cấp (số liệu lấy từ backend). */
  plans(): Promise<Plan[]>
  /** Đổi gói. Đồ án: không nối cổng thanh toán, đổi thẳng để trình bày luồng. */
  setTier(tier: string): Promise<SubscriptionStatus>

  // Cá nhân hoá — PA2 §1.5.2
  /** Sở thích hiện tại + `promptPreview` = đúng đoạn văn trợ lý sẽ đọc. */
  preferences(): Promise<Preferences>
  /** Cập nhật CÓ CHỌN LỌC: chỉ gửi trường muốn đổi. Gửi cả object là xoá sạch phần còn lại. */
  updatePreferences(patch: Partial<PreferenceFields>): Promise<Preferences>

  // Human-in-the-loop có trạng thái (PA2 §1.3.5)
  /** Duyệt một hành động không hoàn tác. Gọi lại lần nữa KHÔNG chạy lại — máy chủ
   *  trả về kết quả của lần đầu kèm `already: true`. */
  approveConfirmation(id: string): Promise<{ status: string; already: boolean; result?: unknown }>
  /** Từ chối — hành động không được chạy. */
  rejectConfirmation(id: string): Promise<{ status: string; already: boolean }>

  // Agent — UC007 + mọi AI skill (008/009/014/015/016/017)
  sendAgentMessage(
    message: string,
    ctx: { emails: Email[] },
    opts?: { sessionId?: string; viaVoice?: boolean
             /** Id tệp đã tải lên qua `uploadFile` — BE đính vào thư khi agent gửi.
              *  Đi kèm LƯỢT CHAT chứ không phải tham số tool: mô hình quyết định
              *  GỬI HAY KHÔNG, không quyết định GỬI CÁI GÌ. */
             attachmentIds?: string[] },
  ): Promise<AgentReplyWithId>
  /** Thực thi 1 PlanOp sau khi user Approve (UC006/007). */
  executePlan(op: PlanOp): Promise<void>
  /** Áp dụng kết quả tự lái vào hộp thư (UC017). */
  applyAutopilot(result: AutopilotResult): Promise<void>

  // Lịch sử hội thoại — UC011
  /** Danh sách phiên đã lưu (ghim trước, mới nhất trước). */
  listConversations(): Promise<ConversationSummary[]>
  /** Mở 1 phiên (kèm messages) để xem lại / tiếp tục. */
  getConversation(id: string): Promise<ConversationDetail>
  /** Đổi tên và/hoặc ghim 1 phiên. */
  updateConversation(id: string, patch: { title?: string; pinned?: boolean }): Promise<void>
  /** Xoá 1 phiên. */
  deleteConversation(id: string): Promise<void>

  // Thông báo — accountability (chuông + badge + panel)
  /** Danh sách thông báo (mới nhất trước) + số chưa đọc. */
  listNotifications(limit?: number): Promise<NotificationList>
  /** Chỉ số chưa đọc (badge chuông poll định kỳ). */
  unreadCount(): Promise<number>
  /** Đánh dấu 1 thông báo đã đọc. */
  markNotificationRead(id: number): Promise<void>
  /** Đánh dấu tất cả đã đọc. */
  markAllNotificationsRead(): Promise<void>
}

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

/* --------------------------------- MOCK API --------------------------------- */
/* Tái dùng đúng logic đang chạy (interpretCommand, interpretNL, matchText) để
   bản demo hành xử y hệt, đồng thời đóng vai "tham chiếu" cho backend thật. */

const STORAGE_KEY = 'meoarc-auth'
const DEMO_USER: User = {
  name: 'Phạm Trần Anh Quân',
  email: 'quanpta.meoarc@gmail.com',
  initial: 'Q',
}

/** Thông báo mẫu cho bản demo/SRS (chế độ mock). Backend thật trả từ bảng notifications. */
const _iso = (minAgo: number) => new Date(Date.now() - minAgo * 60_000).toISOString()
let mockNotifs: NotificationItem[] = [
  { id: 3, type: 'success', message: 'Đã gửi email tới thầy Sơn (nộp báo cáo SE).', read: false, createdAt: _iso(4) },
  { id: 2, type: 'warning', message: 'Đã chuyển 3 thư quảng cáo vào thùng rác.', read: false, createdAt: _iso(72) },
  { id: 1, type: 'success', message: 'Đã gắn nhãn “Học tập” cho 5 thư.', read: true, createdAt: _iso(1500) },
]

/** Lọc giống EmailList: folder → category → quick/nl → từ khoá. */
function filterEmails(all: Email[], q: EmailQuery): EmailListResult {
  const folder = q.folder ?? 'inbox'
  const byFolder = all.filter((e) => {
    const f = e.folder ?? 'inbox'
    if (folder === 'starred') return e.starred && f !== 'trash'
    return f === folder
  })
  const nl = q.nl && q.q?.trim() ? interpretNL(q.q) : null
  const text = nl ? nl.text : (q.q ?? '')
  const unread = q.unread || nl?.unread
  const starred = q.starred || nl?.starred
  const attachment = q.attachment || nl?.attachment
  const items = byFolder.filter((e) => {
    if (q.category && q.category !== 'all' && e.category !== q.category) return false
    if (unread && !e.unread) return false
    if (starred && !e.starred) return false
    if (attachment && !e.attachments?.length) return false
    if (text.trim() && !matchText(emailHaystack(e), text)) return false
    return true
  })
  return { items, nextCursor: null, criteria: nl?.criteria }
}

/* Danh mục gói cho chế độ mock — khớp app/core/plans.py bên backend. */
const MOCK_PLANS: Plan[] = [
  {
    id: 'free', label: 'Miễn phí', tagline: 'Đủ dùng cho việc học và hộp thư cá nhân',
    priceVnd: 0, scanDays: 90, dailyTokens: 100_000, monthlyTokens: 2_000_000,
    features: [
      'Trợ lý quét 90 ngày thư gần nhất',
      'Khoảng 20–40 lượt hỏi trợ lý mỗi ngày',
      'Tóm tắt, phân loại 7 nhóm, soạn thư',
      'Kết nối 1 hộp thư (Gmail hoặc Outlook)',
    ],
  },
  {
    id: 'pro', label: 'Pro', tagline: 'Cho người dùng thư nhiều mỗi ngày',
    priceVnd: 99_000, scanDays: 180, dailyTokens: 2_000_000, monthlyTokens: 40_000_000,
    features: [
      'Trợ lý quét 180 ngày thư gần nhất',
      'Gấp 20 lần hạn mức Miễn phí',
      'Kết nối đồng thời Gmail và Outlook',
      'Kỹ năng nâng cao: Digest, Triage, Brief cuộc họp',
      'Đồng bộ hộp thư ưu tiên',
    ],
  },
  {
    id: 'max', label: 'Pro Max', tagline: 'Dùng thoải mái, cho khối lượng công việc lớn',
    priceVnd: 299_000, scanDays: 365, dailyTokens: 10_000_000, monthlyTokens: 200_000_000,
    features: [
      'Gấp 100 lần hạn mức Miễn phí',
      'Không giới hạn số hộp thư kết nối',
      'Truy cập MCP cho trợ lý ngoài (Claude Desktop, Codex…)',
      'Tự động hoá theo lịch + ưu tiên xử lý',
    ],
  },
]

const mockApproved = new Set<string>()   // id đã duyệt/từ chối — chặn bấm trùng ở mock

let mockSub: SubscriptionStatus = {
  tier: 'free', tierLabel: 'Miễn phí', isActive: true, scanDays: 90,
  daily: { used: 34_500, limit: 100_000, remaining: 65_500 },
  monthly: { used: 612_000, limit: 2_000_000, remaining: 1_388_000 },
}

/* Cá nhân hoá — trạng thái mock. Giữ ngoài hàm để sống qua nhiều lần gọi trong 1 phiên. */
const MOCK_TONES: Record<string, string> = {
  formal: 'trang trọng, giữ khoảng cách, xưng hô đầy đủ chức danh',
  friendly: 'thân thiện, gần gũi nhưng vẫn lịch sự',
  concise: 'ngắn gọn, đi thẳng vào việc, không rào đón',
  warm: 'ấm áp, quan tâm tới người nhận',
}

let mockPrefs: PreferenceFields = {
  language: 'vi',
  displayName: null,
  theme: 'system',
  tonePreference: 'friendly',
  signatureNote: null,
  customInstruction: null,
}

/** Dựng lại đúng logic của backend (`to_prompt_context`) để bản mock xem trước cũng thật. */
function mockPromptPreview(): string {
  const d: string[] = []
  if (mockPrefs.displayName) d.push(`- Người dùng tên là ${mockPrefs.displayName}. Xưng hô cho đúng.`)
  if (mockPrefs.tonePreference && mockPrefs.tonePreference !== 'friendly') {
    const t = MOCK_TONES[mockPrefs.tonePreference]
    if (t) d.push(`- Khi soạn thư, giữ giọng ${t}.`)
  }
  if (mockPrefs.signatureNote)
    d.push(`- Kết thư bằng đúng chữ ký sau, giữ nguyên từng dòng, KHÔNG tự chế thêm:\n${mockPrefs.signatureNote.trim()}`)
  if (mockPrefs.customInstruction)
    d.push(`- Dặn riêng của người dùng: ${mockPrefs.customInstruction.trim()}`)
  return d.join('\n')
}

export function createMockApi(): MeoArcApi {
  return {
    async me() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY)
        return raw ? (JSON.parse(raw) as User) : null
      } catch {
        return null
      }
    },
    async loginWithGoogle() {
      await delay(1100) // giả lập redirect OAuth
      localStorage.setItem(STORAGE_KEY, JSON.stringify(DEMO_USER))
      return DEMO_USER
    },
    async loginWithOutlook() {
      await delay(1100)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(DEMO_USER))
      return DEMO_USER
    },
    async logout() {
      localStorage.removeItem(STORAGE_KEY)
    },
    async revokeAccess() {
      localStorage.removeItem(STORAGE_KEY)
    },

    async listEmails(query = {}) {
      await delay(120)
      return filterEmails(seedEmails, query)
    },
    async resolveMessage() {},
    async getEmail(id) {
      return seedEmails.find((e) => e.id === id) ?? null
    },
    async getThread(id) {
      // Mock gom luồng theo TIÊU ĐỀ đã bỏ tiền tố "Re:/Fwd:" — backend thật dùng
      // threadId của nhà cung cấp, nhưng dữ liệu mẫu không có nên đây là cách gần
      // đúng nhất mà vẫn cho thấy màn luồng chạy thật.
      const goc = seedEmails.find((e) => e.id === id)
      if (!goc) return []
      const chuan = (x: string) => x.replace(/^((re|fwd|fw)\s*:\s*)+/i, '').trim().toLowerCase()
      const khoa = chuan(goc.subject)
      return seedEmails.filter((e) => chuan(e.subject) === khoa)
    },
    async summarizeEmail() {
      return [] // mock: để email-detail tự dùng tóm tắt trích cục bộ
    },
    async markEmailRead() {
      /* mock: trạng thái do app-shell quản lý cục bộ */
    },

    async markRead() {},
    async setImportant() {},
    async applyLabel() {},
    async archiveEmails() {},
    async spamEmails() {},
    async notSpamEmails() {},
    async deleteEmails() {},
    async restoreEmails() {},

    async sendEmail() {
      await delay(300)
      return { id: `mock-${Date.now()}` }
    },
    async forwardEmail() {
      await delay(250)
      return { id: `mock-fwd-${Date.now()}` }
    },
    async replyEmail() {
      await delay(300)
      return { id: `mock-${Date.now()}` }
    },
    async uploadFile(file) {
      await delay(250) // mock: không upload thật, chỉ trả metadata
      const kb = Math.max(1, Math.round(file.size / 1024))
      return { id: `mock-${Date.now()}`, name: file.name, size: `${kb} KB` }
    },
    async saveDraft() {
      await delay(200)
      return { id: `mock-${Date.now()}` }
    },
    async suggestCompose() {
      return '' // mock: không gọi LLM
    },
    // Mock: giữ gói + mức dùng trong bộ nhớ để xem giao diện khi chưa có backend.
    async subscription() {
      return mockSub
    },
    // Mock mô phỏng ĐÚNG hành vi chống bấm trùng, nếu không thì bản mock lại che
    // mất chính cái lỗi mà tính năng này sinh ra để vá.
    async approveConfirmation(id: string) {
      if (mockApproved.has(id)) return { status: 'approved', already: true, result: { success: true } }
      mockApproved.add(id)
      await delay(300)
      return { status: 'approved', already: false, result: { success: true } }
    },
    async rejectConfirmation(id: string) {
      const moi = !mockApproved.has(id)
      mockApproved.add(id)
      return { status: 'rejected', already: !moi }
    },
    async plans() {
      return MOCK_PLANS
    },
    async setTier(tier) {
      const p = MOCK_PLANS.find((x) => x.id === tier) ?? MOCK_PLANS[0]
      mockSub = {
        ...mockSub,
        tier: p.id,
        tierLabel: p.label,
        scanDays: p.scanDays,
        daily: { ...mockSub.daily, limit: p.dailyTokens, remaining: Math.max(0, p.dailyTokens - mockSub.daily.used) },
        monthly: { ...mockSub.monthly, limit: p.monthlyTokens, remaining: Math.max(0, p.monthlyTokens - mockSub.monthly.used) },
      }
      return mockSub
    },
    async contacts(q) {
      const seen = new Map<string, string>()
      for (const e of seedEmails) {
        if (e.senderEmail?.includes('@') && !seen.has(e.senderEmail))
          seen.set(e.senderEmail, e.sender)
      }
      const ql = q.trim().toLowerCase()
      return [...seen]
        .filter(([addr, name]) => !ql || `${addr} ${name}`.toLowerCase().includes(ql))
        .slice(0, 8)
        .map(([email, name]) => ({ name, email }))
    },

    async sendAgentMessage(message, ctx) {
      await delay(700) // giả lập "đang nghĩ"
      return interpretCommand(message, ctx.emails)
    },
    async executePlan() {},
    async applyAutopilot() {},

    // UC011 (mock): để FE tự quản lịch sử cục bộ (demo SRS). Trả rỗng → ChatPanel giữ initSessions.
    async listConversations() {
      return []
    },
    async getConversation(id) {
      return { id, title: '', pinned: false, createdAt: '', updatedAt: '', messages: [] }
    },
    async updateConversation() {},
    async deleteConversation() {},

    async listNotifications() {
      await delay(120)
      return { items: mockNotifs, unread: mockNotifs.filter((n) => !n.read).length }
    },
    async unreadCount() {
      return mockNotifs.filter((n) => !n.read).length
    },
    async markNotificationRead(id) {
      mockNotifs = mockNotifs.map((n) => (n.id === id ? { ...n, read: true } : n))
    },
    async markAllNotificationsRead() {
      mockNotifs = mockNotifs.map((n) => ({ ...n, read: true }))
    },

    // Cá nhân hoá — bản mock giữ trong RAM, đủ để dựng và xem giao diện không cần backend
    async preferences() {
      return { ...mockPrefs, promptPreview: mockPromptPreview(), availableTones: MOCK_TONES }
    },
    async updatePreferences(patch) {
      mockPrefs = { ...mockPrefs, ...patch }
      return { ...mockPrefs, promptPreview: mockPromptPreview(), availableTones: MOCK_TONES }
    },
  }
}

/* --------------------------------- HTTP API --------------------------------- */
/* Khung gọi REST/SSE thật theo docs/02-API-CONTRACT.md. Bật khi có VITE_API_BASE_URL. */

export function createHttpApi(baseUrl: string): MeoArcApi {
  const base = baseUrl.replace(/\/$/, '')
  const req = async <T>(path: string, init?: RequestInit): Promise<T> => {
    const res = await fetch(`${base}${path}`, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      ...init,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body?.error?.message ?? `HTTP ${res.status}`)
    }
    return (res.status === 204 ? undefined : await res.json()) as T
  }
  const post = <T>(path: string, body?: unknown) =>
    req<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

  const qs = (q: EmailQuery) => {
    const p = new URLSearchParams()
    Object.entries(q).forEach(([k, v]) => v != null && v !== '' && p.set(k, String(v)))
    const s = p.toString()
    return s ? `?${s}` : ''
  }

  return {
    me: async () => {
      try {
        return await req<User>('/me')
      } catch {
        return null // /me trả 401 = chưa đăng nhập
      }
    },
    loginWithGoogle: async () => {
      // Đăng nhập THẬT = điều hướng cả trang tới backend → backend đẩy sang Google.
      window.location.href = `${base}/auth/google/start`
      return new Promise<User>(() => {}) // trang sẽ rời đi, không resolve
    },
    loginWithOutlook: async () => {
      window.location.href = `${base}/auth/outlook/start`  // backend đẩy sang Microsoft
      return new Promise<User>(() => {})
    },
    logout: () => post<void>('/auth/logout'),
    revokeAccess: () => post<void>('/auth/revoke'),

    listEmails: (query = {}) => req<EmailListResult>(`/emails${qs(query)}`),
    resolveMessage: (convId, msgId) =>
      post<void>(`/agent/conversations/${convId}/messages/${msgId}/resolved`, {}),
    getEmail: (id) => req<Email | null>(`/emails/${id}`),
    getThread: (id) =>
      req<{ items: Email[] }>(`/emails/${id}/thread`).then((r) => r?.items ?? []),
    summarizeEmail: async (id) =>
      (await post<{ points: string[] }>(`/emails/${id}/summarize`)).points,
    markEmailRead: (id, read) => post<void>(`/emails/${id}/read`, { read }),

    markRead: (ids, read) => post<void>('/emails/actions/read', { ids, read }),
    setImportant: (ids, value) => post<void>('/emails/actions/important', { ids, value }),
    applyLabel: (ids, category, label) =>
      post<void>('/emails/actions/label', { ids, category, label }),
    archiveEmails: (ids) => post<void>('/emails/actions/archive', { ids }),
    spamEmails: (ids) => post<void>('/emails/actions/spam', { ids }),
    notSpamEmails: (ids) => post<void>('/emails/actions/not-spam', { ids }),
    deleteEmails: (ids) => post<void>('/emails/actions/delete', { ids }),
    restoreEmails: (ids) => post<void>('/emails/actions/restore', { ids }),

    sendEmail: (input) => post<{ id: string }>('/emails/send', input),

    replyEmail: (id, body, replyAll = false, html = '') =>
      post<{ id: string }>(`/emails/${id}/reply`, { body, replyAll, html }),
    forwardEmail: (id, to, note = '') =>
      post<{ id: string }>(`/emails/${id}/forward`, { to, note }),

    // Upload tệp = multipart/form-data (KHÔNG đặt Content-Type để trình duyệt tự thêm boundary).
    uploadFile: async (file) => {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch(`${base}/uploads`, {
        method: 'POST',
        credentials: 'include',
        body: form,
      })
      if (!res.ok) throw new Error('upload failed')
      return res.json()
    },
    saveDraft: (input) => post<{ id: string }>('/emails/draft', input),
    suggestCompose: async (subject, body) =>
      (await post<{ suggestion: string }>('/emails/compose/suggest', { subject, body })).suggestion,
    contacts: async (q) =>
      (await req<{ items: { name: string; email: string }[] }>(`/contacts?q=${encodeURIComponent(q)}`))
        .items,

    subscription: () => req<SubscriptionStatus>('/subscription'),
    approveConfirmation: (id: string) =>
      req<{ status: string; already: boolean; result?: unknown }>(`/confirmations/${id}/approve`, { method: 'POST' }),
    rejectConfirmation: (id: string) =>
      req<{ status: string; already: boolean }>(`/confirmations/${id}/reject`, { method: 'POST' }),
    plans: async () => (await req<{ plans: Plan[] }>('/subscription/plans')).plans,
    setTier: (tier) => post<SubscriptionStatus>('/subscription/tier', { tier }),

    // Cá nhân hoá — PA2 §1.5.2. PATCH chứ không PUT: chỉ gửi trường muốn đổi, nên
    // đổi giọng văn không làm mất chữ ký đã lưu.
    preferences: () => req<Preferences>('/me/preferences'),
    updatePreferences: (patch) =>
      req<Preferences>('/me/preferences', { method: 'PATCH', body: JSON.stringify(patch) }),

    // Production nên dùng SSE (text/event-stream); ở đây nhận reply cuối dạng JSON cho gọn.
    sendAgentMessage: (message, _ctx, opts) =>
      post<AgentReplyWithId>('/agent/chat', { message, ...opts }),
    executePlan: (op) => post<void>('/agent/plan/execute', { op }),
    applyAutopilot: (result) =>
      post<void>('/agent/autopilot/apply', {
        archive: result.archive,
        markRead: result.markRead,
        flag: result.flag,
      }),

    // Lịch sử hội thoại — UC011
    listConversations: () => req<ConversationSummary[]>('/agent/conversations'),
    getConversation: (id) => req<ConversationDetail>(`/agent/conversations/${id}`),
    updateConversation: (id, patch) =>
      req<void>(`/agent/conversations/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      }),
    deleteConversation: (id) => req<void>(`/agent/conversations/${id}`, { method: 'DELETE' }),

    // Thông báo — accountability
    listNotifications: (limit = 50) => req<NotificationList>(`/notifications?limit=${limit}`),
    unreadCount: async () =>
      (await req<{ unread: number }>('/notifications/unread-count')).unread,
    markNotificationRead: (id) => post<void>(`/notifications/${id}/read`),
    markAllNotificationsRead: () => post<void>('/notifications/read-all'),
  }
}

/* --------------------------------- Singleton -------------------------------- */

const BASE = import.meta.env.VITE_API_BASE_URL

/** Có cấu hình backend thật không? (auth-context dùng để biết chế độ mock/thật.)
 *
 *  ĐÃ CẮT gạch chéo cuối. Chỗ này từng gây một lỗi rất khó lần: ở chế độ gộp,
 *  `VITE_API_BASE_URL` là `"/"`, nên nơi nào ghép `` `${apiBaseUrl}/auth/...` ``
 *  sẽ ra `"//auth/..."`. Hai gạch chéo đầu là cú pháp URL-không-kèm-giao-thức —
 *  trình duyệt hiểu `auth` là TÊN MÁY CHỦ và điều hướng sang `https://auth/...`,
 *  một địa chỉ không tồn tại. Kết quả: bấm nút xong ra trang trắng/đen, không
 *  báo lỗi gì, và mọi thứ khác vẫn chạy bình thường.
 *
 *  Cắt xong thì `"/"` thành `""`, và `"" + "/auth/..."` ra đúng đường dẫn tương đối.
 *  Lưu ý `""` vẫn là giá trị FALSY — nhưng `USE_BACKEND` phải phân biệt được
 *  "gộp cùng origin" với "chưa cấu hình backend", nên xem `apiBaseUrlDaCauHinh`.
 */
const goc = (BASE ?? '').replace(/\/$/, '')

/** Ghép một đường dẫn API. DÙNG HÀM NÀY thay vì tự nối chuỗi.
 *
 *  Vì sao không còn xuất thẳng `apiBaseUrl` nữa: ở chế độ gộp giá trị đúng của
 *  nó là chuỗi RỖNG — mà chuỗi rỗng là FALSY. Ai vô tình viết `if (apiBaseUrl)`
 *  thì ở bản triển khai gộp điều kiện đó luôn SAI, nên khối lệnh bên trong không
 *  bao giờ chạy. Đã dính đúng lỗi này: `if (!apiBaseUrl) return` chặn mất lệnh
 *  nạp thư, khiến bản deploy hiển thị vĩnh viễn dữ liệu mẫu — mà không báo gì.
 *
 *  Nay chỉ còn một hàm (luôn truthy) và một cờ boolean rõ nghĩa, nên viết nhầm
 *  kiểu đó không còn khả năng xảy ra. */
export function duongDanApi(duong_dan: string): string {
  return goc + (duong_dan.startsWith('/') ? duong_dan : '/' + duong_dan)
}

/** Có khai VITE_API_BASE_URL hay không — dùng để chọn chế độ mock ↔ thật.
 *  Tách khỏi `apiBaseUrl` vì ở chế độ gộp, đường dẫn đúng là chuỗi RỖNG mà vẫn
 *  phải gọi backend thật. Dựa vào `!!apiBaseUrl` thì chế độ gộp bị hiểu nhầm
 *  thành "chưa có backend" và ứng dụng lặng lẽ chạy bằng dữ liệu giả. */
export const apiBaseUrlDaCauHinh = BASE != null && BASE !== ''

/** Dùng ở mọi nơi: `import { api } from '@/lib/api'`. Tự chọn mock ↔ http. */
export const api: MeoArcApi = apiBaseUrlDaCauHinh
  ? createHttpApi(goc)
  : createMockApi()
