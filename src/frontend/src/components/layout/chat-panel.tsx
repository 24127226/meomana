import { Fragment, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sparkles,
  Check,
  X,
  Send,
  Paperclip,
  ListChecks,
  Mail,
  AlertTriangle,
  CheckCircle2,
  FileText,
  History,
  SquarePen,
  Search,
  Loader2,
  CalendarClock,
  Users,
  CheckSquare,
  Square,
  Clock,
  BarChart3,
  Pin,
  PinOff,
  Pencil,
  Trash2,
  Mic,
  Volume2,
  VolumeX,
  ArrowUpRight,
  Plane,
  Hotel,
  ShieldCheck,
  FlaskConical,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { t } from '@/lib/ngon-ngu'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { MeoMascot } from '@/components/meo-mascot'
import { LogoMark } from '@/components/logo'
import { useTheme } from '@/components/theme-provider'
import { VoiceMode } from '@/components/layout/voice-mode'
import { ChatAmbience } from '@/components/layout/chat-ambience'
import { KinhKhucXa, KinhKhucXaDefs } from '@/components/layout/glass-refraction'
// Dùng LẠI thành phần vẽ của khung "Tra cứu đi lại" — không vẽ bản thứ hai. Vẽ hai lần
// thì hai chỗ sẽ trôi xa nhau và cùng một chuyến bay hiện hai kiểu.
import { DongBay, DongPhong } from '@/components/layout/tra-cuu-panel'
import { type AgentReply, type PlanOp, type EmailRef } from '@/lib/agent'
import { AutopilotWidget, type AutopilotResult } from '@/components/layout/autopilot-widget'
import { api, apiBaseUrlDaCauHinh, type StoredMessage } from '@/lib/api'
import { useSubscription, isOutOfTokens } from '@/lib/subscription'
import { TokenMeter, QuotaBanner } from '@/components/layout/token-meter'
import { PricingScreen } from '@/components/layout/pricing-screen'
import { normalize } from '@/lib/search'
import { VanBanDep } from '@/lib/van-ban'
import { doDieuHuong } from '@/lib/dieu-huong-chat'
import { chuyenCanh } from '@/lib/chuyen-canh'
import type { EmailActions } from '@/lib/email-actions'
import type { Category, Email } from '@/data/emails'
import { CATEGORY, CATEGORY_OPTIONS } from '@/data/categories'

type Message =
  | { id: string; role: 'user'; text: string }
  | { id: string; role: 'agent'; reply: AgentReply; resolved?: boolean }

/** Một phiên hội thoại đã lưu (UC011).
 *  `backendId` = id phiên trong DB (có khi đã lưu xuống backend); dùng để gọi API
 *  list/get/rename/delete + gửi kèm chat. Phiên mới chưa gửi thì chưa có backendId. */
type Session = {
  id: string
  title: string
  time: string
  messages: Message[]
  pinned?: boolean
  backendId?: string
}

const RENAME_MAX = 60

let counter = 0
const uid = () => `m${++counter}`

/** Cuộc trò chuyện đang mở, nhớ qua localStorage.
 *
 *  ── VÌ SAO PHẢI NHỚ Ở NGOÀI COMPONENT ──
 *  Hộp thư và trang Lịch trình mỗi bên dựng MỘT ChatPanel riêng. Đổi trang là
 *  component cũ bị gỡ, component mới mount và bắt đầu từ một phiên trắng — nên đi
 *  Lịch trình rồi quay lại Hộp thư là mất mạch trò chuyện, dù vẫn đang ở trong cùng
 *  một ứng dụng và cùng một người dùng.
 *  Gộp hai ChatPanel làm một ở tầng trên thì sạch hơn, nhưng phải dựng lại bố cục cả
 *  hai trang; nhớ id ở đây đạt cùng kết quả mà không đụng tới bố cục nào. */
const KHOA_CHAT = 'meoarc:chatHienTai'

const doc = (k: string): string | null => {
  // Chế độ riêng tư / chặn cookie làm localStorage NÉM LỖI chứ không trả null — không
  // bọc thì cả khung chat trắng màn hình vì một tiện ích nhớ-chỗ-đang-đọc.
  try { return localStorage.getItem(k) } catch { return null }
}
const ghi = (k: string, v: string) => {
  try { localStorage.setItem(k, v) } catch { /* không nhớ được thì thôi, đừng vỡ */ }
}

const WELCOME =
  'Chào Quân 👋 Mình là trợ lý MeoArc. Cứ nhắn bằng lời thường — mình giúp tóm tắt, dọn, phân loại hay soạn thư. Việc quan trọng mình luôn hỏi bạn duyệt trước.'

function initSessions(): Session[] {
  return [
    {
      id: 's0',
      title: 'Cuộc trò chuyện mới',
      time: t('tm.now'),
      messages: [{ id: uid(), role: 'agent', reply: { kind: 'text', text: WELCOME } }],
    },
    {
      id: 'past1',
      title: 'Dọn thư bản tin tuần này',
      time: 'Hôm qua',
      messages: [
        { id: uid(), role: 'user', text: 'lưu trữ thư bản tin' },
        { id: uid(), role: 'agent', reply: { kind: 'done', text: 'Đã lưu trữ 1 thư. Hộp thư gọn hơn rồi ✨' } },
      ],
    },
    {
      id: 'past2',
      title: 'Tóm tắt hộp thư sáng nay',
      time: 'Thứ 4',
      messages: [
        { id: uid(), role: 'user', text: 'tóm tắt thư chưa đọc' },
        {
          id: uid(),
          role: 'agent',
          reply: {
            kind: 'result',
            title: 'Tóm tắt 2 thư chưa đọc',
            intro: 'Mình đã rút gọn:',
            lines: ['Giáo vụ HCMUS — Nhắc nộp báo cáo SRS', 'GitHub — PR #12 đã được review'],
          },
        },
      ],
    },
  ]
}

/* Gợi ý chip KHÔNG còn tĩnh — sinh theo ngữ cảnh hộp thư thật, xem memo
   `suggestions` trong ChatPanel (web "tư duy" đúng thời điểm). */

/** Kỹ năng AI (UC014/015/016/009) — gợi ý nổi bật trên canvas. */
// NHÃN thuần Việt, PROMPT giữ nguyên từ khoá cũ.
// Hai thứ này phục vụ hai đối tượng khác nhau: nhãn là cho người đọc, prompt là cho
// mô hình. Dịch luôn cả prompt thì phải chỉnh lại phần nhận diện ý định ở backend —
// một thay đổi không ai yêu cầu, và là đúng kiểu "sửa cái này hỏng cái kia".
const dsSkills = () => [
  { label: t('skill.autopilot'), prompt: 'tự lái hộp thư' },
  { label: t('skill.digest'), prompt: 'digest hôm nay' },
  { label: t('skill.triage'), prompt: 'triage hộp thư' },
  { label: t('skill.brief'), prompt: 'brief cuộc họp' },
  { label: t('skill.autolabel'), prompt: 'phân loại tự động toàn bộ' },
]

/** GỢI Ý CÂU TIẾP THEO — suy từ THỂ LOẠI câu trả lời vừa rồi.
 *
 *  ── VÌ SAO KHÔNG NHỜ MÔ HÌNH NGHĨ HỘ ──
 *  Cách thường thấy là gọi model lần nữa để đoán "người dùng sẽ hỏi gì tiếp". Ở đây
 *  làm vậy là hỏng: gói Gemini free chỉ 20 lượt/NGÀY mỗi model, nên mỗi câu trả lời
 *  lại đốt thêm một lượt CHỈ ĐỂ VẼ VÀI CÁI NÚT — mà phần lớn nút đó không ai bấm.
 *  Người dùng sẽ hết lượt hỏi thật vì những gợi ý họ không dùng.
 *
 *  Suy từ thể loại trả lời thì tốn 0 lượt, ra ngay lập tức, và không bao giờ gợi ý
 *  một việc trợ lý không làm được — điều mà model đoán rất hay mắc.
 *
 *  Đổi lại: gợi ý KHÔNG bám nội dung cụ thể. Chấp nhận, vì bước tiếp theo hợp lý sau
 *  một bảng chuyến bay gần như luôn là "tìm chỗ ở", bất kể chặng nào. */
/** Một chip gợi ý: NHÃN là thứ người đọc, LỆNH là thứ gửi cho agent.
 *  Hai thứ này PHẢI tách nhau. Câu lệnh bám đúng bộ đọc ý định (`lib/agent.ts`),
 *  vốn khớp bằng từ khoá tiếng Việt — dịch nó là chip bấm vào không chạy nữa. */
type ChipGoiY = { nhan: string; lenh: string }
const chip = (khoa: string, lenh: string): ChipGoiY => ({ nhan: t(khoa), lenh })

function goiYTiepTheo(reply: AgentReply): ChipGoiY[] {
  switch (reply.kind) {
    case 'dilai':
      return reply.loai === 'bay'
        ? [chip('gy.stayNear', 'Tìm chỗ ở gần đó'), chip('gy.morningFlight', 'Chuyến nào bay buổi sáng?'), chip('gy.remindBefore', 'Đặt lịch nhắc trước ngày bay')]
        : [chip('gy.flightThere', 'Tìm chuyến bay tới đó'), chip('gy.nearCentre', 'Chỗ nào gần trung tâm nhất?')]
    case 'digest':
      return [chip('gy.whichFirst', 'Thư nào cần xử lý trước?'), chip('gy.categorise', 'Phân loại giúp mình'), chip('gy.archiveNews', 'Lưu trữ hết bản tin')]
    case 'triage':
      return [chip('gy.replyUrgent', 'Soạn trả lời thư gấp nhất'), chip('gy.overloaded', 'Tuần này mình có quá tải không?')]
    case 'categorize':
      return [chip('gy.digestToday', 'Tóm tắt hộp thư hôm nay'), chip('gy.waitingOnMe', 'Thư nào đang chờ mình phản hồi?')]
    case 'brief':
      return [chip('gy.confirmAttend', 'Soạn thư xác nhận tham dự'), chip('gy.flightToMeeting', 'Tìm chuyến bay tới cuộc họp này')]
    case 'draft':
      return [chip('gy.shorter', 'Viết ngắn gọn hơn'), chip('gy.formal', 'Đổi sang giọng trang trọng')]
    case 'done':
      return [chip('gy.digestToday', 'Tóm tắt hộp thư hôm nay'), chip('gy.whichFirst', 'Thư nào cần xử lý trước?')]
    default:
      // 'text' và các loại còn lại: câu trả lời tự do, không đoán được bước sau —
      // để trống còn hơn gợi ý bừa rồi người dùng bấm vào một ngõ cụt.
      return []
  }
}

/** Khuôn tin BE (StoredMessage) → Message của FE (thêm id cục bộ để React render). */
function toLocalMsg(m: StoredMessage): Message {
  // DÙNG LẠI mã của máy chủ, không sinh mã mới. Sinh mới thì sau khi tải lại, mã cục
  // bộ không còn khớp với gì cả và không đánh dấu duyệt lên máy chủ được nữa.
  // `resolved` phải mang theo: thiếu nó thì mở lại hội thoại là mọi thẻ quay về CHỜ
  // DUYỆT, kể cả thẻ xoá đã chạy xong — và người dùng bấm duyệt lần hai.
  return m.role === 'user'
    ? { id: m.id || uid(), role: 'user', text: m.text }
    : { id: m.id || uid(), role: 'agent', reply: m.reply, resolved: m.resolved }
}

/** ISO time (BE) → nhãn 'time' mà drawer hiểu (timeBucket đọc 'Hôm nay'/'Hôm qua'). */
function relTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const y = new Date(now)
  y.setDate(now.getDate() - 1)
  const hhmm = d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
  if (d.toDateString() === now.toDateString()) return t('tm.todayAt', { gio: hhmm })
  if (d.toDateString() === y.toDateString()) return t('tm.yesterday')
  return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' })
}

/** Dòng preview ngắn của 1 phiên (lấy tin cuối). */
function previewOf(s: Session): string {
  const last = s.messages[s.messages.length - 1]
  if (!last) return ''
  if (last.role === 'user') return last.text
  return 'text' in last.reply ? last.reply.text : t('ch.resultShort')
}

/** Gom toàn bộ chữ của 1 phiên để tìm kiếm. */
function searchTextOf(s: Session): string {
  return [s.title, ...s.messages.map((m) => (m.role === 'user' ? m.text : 'text' in m.reply ? m.reply.text : ''))]
    .join(' ')
    .toLowerCase()
}

/** Nhóm phiên theo mốc thời gian.
 *
 *  Nhóm theo KHOÁ, không theo chữ đã dịch. Trường `time` vừa là thứ hiện ra vừa là
 *  thứ đem đi phân tích — nên khi nhãn đổi sang 'Today 13:03' thì phép so khớp
 *  'hôm nay' trượt hết và MỌI phiên rơi vào "Trước đó". So khớp phải hỏi chính lớp
 *  dịch xem hôm nay/hôm qua đang được viết thế nào, chứ không đoán một thứ tiếng. */
const TIME_ORDER = ['tm.today', 'tm.yesterday', 'tm.earlier'] as const
function timeBucket(nhan: string): (typeof TIME_ORDER)[number] {
  const low = nhan.toLowerCase()
  const co = (khoa: string) => low.includes(t(khoa).toLowerCase())
  if (co('tm.now') || co('tm.today')) return 'tm.today'
  if (co('tm.yesterday')) return 'tm.yesterday'
  return 'tm.earlier'
}

function doneText(op: PlanOp): string {
  switch (op.type) {
    case 'archive':
      return t('ch.doneArchive', { n: op.ids.length })
    case 'delete':
      return t('ch.doneDelete', { n: op.ids.length })
    case 'restore':
      return t('ch.doneRestore', { n: op.ids.length })
    case 'markRead':
      return t('ch.doneRead', { n: op.ids.length })
    case 'label':
      return t('ch.doneLabel', { nhan: op.label, n: op.ids.length })
    case 'autoLabel':
      return t('ch.doneAuto', { n: op.items.length })
  }
}

/** Câu ngắn để TTS đọc cho từng loại phản hồi.
 *
 *  `intro` của thẻ 'dilai' có thể vắng (nhà cung cấp không kèm câu mô tả), nên phải
 *  lui về `title` — thiếu bước này thì máy đọc thành tiếng chữ "null". */
function replyToSpeech(reply: AgentReply): string {
  if ('text' in reply) return reply.text
  if ('intro' in reply && reply.intro) return reply.intro
  if ('title' in reply && reply.title) return reply.title
  return ''
}

/* ---------- Mảnh hiển thị ---------- */

function UserBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex justify-end">
      <div className="gloss max-w-[85%] whitespace-pre-line break-words rounded-2xl rounded-tr-md bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-soft">
        {children}
      </div>
    </div>
  )
}

function AgentRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5">
      <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-emphasis text-emphasis-foreground shadow-subtle">
        <Sparkles className="size-3.5" />
      </div>
      <div className="min-w-0 flex-1 space-y-2.5">{children}</div>
    </div>
  )
}

/* (#3) Chữ "giải mã": ký tự random rồi định hình dần về câu thật.
   Tốc độ co theo độ dài (câu dài vẫn xong ~1.4s). Reduced-motion → hiện thẳng. */
const SCRAMBLE_CH = 'ABCDEF#@%&*0123456789▓▒░'
function scrambleAll(t: string): string {
  let out = ''
  for (const c of t) out += c === ' ' || c === '\n' ? c : SCRAMBLE_CH[(Math.random() * SCRAMBLE_CH.length) | 0]
  return out
}
function ScrambleText({ text }: { text: string }) {
  const reduce =
    typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [display, setDisplay] = useState(() => (reduce ? text : scrambleAll(text)))
  useEffect(() => {
    if (reduce) {
      setDisplay(text)
      return
    }
    let i = 0
    const step = Math.max(0.5, text.length / 22) // câu dài → lộ nhanh hơn để khỏi lê thê
    const id = window.setInterval(() => {
      let out = ''
      for (let k = 0; k < text.length; k++) {
        const c = text[k]
        out += c === ' ' || c === '\n' || k < i ? c : SCRAMBLE_CH[(Math.random() * SCRAMBLE_CH.length) | 0]
      }
      setDisplay(out)
      i += step
      if (i >= text.length) {
        window.clearInterval(id)
        setDisplay(text) // chốt câu thật, sạch sẽ
      }
    }, 32)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text])
  return <>{display}</>
}

function AgentText({ children }: { children: React.ReactNode }) {
  // Mô hình VỐN ĐÃ viết Markdown (**đậm**, - gạch đầu dòng, ### tiêu đề) — đó là thói
  // quen mặc định của mọi LLM. Bản trước chỉ `whitespace-pre-line` nên giữ được dấu
  // xuống dòng mà VỨT BỎ phần cấu trúc: dấu sao và dấu thăng hiện nguyên ra màn hình.
  // Đọc lại cấu trúc đó KHÔNG tốn thêm token nào — cùng một câu trả lời, cùng một chi
  // phí, chỉ khác ở chỗ nó được vẽ đúng hình dạng mô hình đã định. Xem lib/van-ban.tsx.
  const chu = typeof children === 'string' ? children : null
  // Câu ngắn một dòng thì hiệu ứng "giải mã" ăn tiền hơn; câu dài có cấu trúc thì bố
  // cục ăn tiền hơn. Ngưỡng thô nhưng phân biệt đúng hai loại đó.
  const coCauTruc = !!chu && (chu.includes('\n') || /\*\*|^#{1,4}\s|\[[^\]]+\]\(/m.test(chu))

  return (
    <div className="max-w-[88%] break-words rounded-2xl rounded-tl-md px-4 py-2.5 text-sm leading-relaxed text-foreground shadow-soft edge-light rose-glass">
      {chu === null ? children
        : coCauTruc ? <VanBanDep text={chu} />
        : <ScrambleText text={chu} />}
    </div>
  )
}

/* ── DÒNG TRẠNG THÁI KHI ĐANG CHỜ ─────────────────────────────────────────────
   Đo được: p99 của /agent/chat là 115 GIÂY. Suốt chừng đó chỉ có ba chấm nhấp nháy,
   nên người dùng không phân biệt được "đang chạy" với "đã treo" — và phần lớn sẽ bấm
   lại, tốn thêm một lượt gọi mô hình cho đúng câu vừa hỏi.

   ⚠️ ĐÂY LÀ ƯỚC LƯỢNG THEO THỜI GIAN, KHÔNG PHẢI TRẠNG THÁI THẬT.
   Backend chưa phát sự kiện từng bước (xem kế hoạch Giai đoạn B), nên frontend không
   biết agent đang gọi tool nào. Vì thế câu chữ ở đây cố ý viết theo kiểu MÔ TẢ CHUNG
   ("đang tra hộp thư") chứ không khẳng định cụ thể ("đang gọi search_emails") — nói
   một điều mình không biết là sai, kể cả khi đoán đúng phần lớn lần.

   Mốc thời gian lấy từ số đo thật: p50 ≈ 2–5s, câu có tool ≈ 10–25s, và trên 45s thì
   gần như chắc chắn chuỗi dự phòng đang xoay model. Nên mốc cuối nói thẳng là bất
   thường thay vì trấn an — trấn an sai chỗ làm người dùng chờ lâu hơn mức đáng chờ. */
const GIAI_DOAN: { tu: number; chu: string }[] = [
  { tu: 0, chu: t('ch.st1') },
  { tu: 3, chu: t('ch.st2') },
  { tu: 9, chu: t('ch.st3') },
  { tu: 20, chu: t('ch.st4') },
  { tu: 45, chu: t('ch.st5') },
]

function DongTrangThai() {
  const [giay, setGiay] = useState(0)
  useEffect(() => {
    const t = window.setInterval(() => setGiay((g) => g + 1), 1000)
    return () => window.clearInterval(t)
  }, [])
  const chu = [...GIAI_DOAN].reverse().find((g) => giay >= g.tu)?.chu ?? GIAI_DOAN[0].chu
  return (
    <p className="mt-1.5 flex items-center gap-2 px-1 text-[11.5px] text-muted-foreground">
      <span>{chu}</span>
      {/* Số giây là số ĐO ĐƯỢC, khác với câu chữ ở trên vốn chỉ là ước lượng. Chỉ hiện
          từ giây thứ 10 — hiện sớm quá thì mọi câu trả lời nhanh cũng trông như chậm. */}
      {giay >= 10 && <span className="tabular-nums opacity-60">{giay}s</span>}
    </p>
  )
}

function ThinkingDots() {
  return (
    <div className="flex items-start gap-2.5">
      <MeoMascot thinking className="size-9 shrink-0" />
      <div className="min-w-0 flex-1 space-y-2.5">
        <div className="inline-flex items-center gap-1 rounded-2xl rounded-tl-md px-4 py-3 shadow-soft glass">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="size-1.5 animate-bounce rounded-full bg-foreground/60"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
        <DongTrangThai />
        {/* Skeleton morphing — khung kết quả đang hình thành */}
        <div className="max-w-[88%] space-y-2.5 rounded-2xl p-3.5 shadow-soft glass">
          <div className="skeleton h-3 w-1/3 rounded" />
          <div className="grid grid-cols-2 gap-2">
            <div className="skeleton h-12 rounded-lg" />
            <div className="skeleton h-12 rounded-lg" />
          </div>
          <div className="skeleton h-2.5 w-3/4 rounded" />
          <div className="skeleton h-2.5 w-1/2 rounded" />
        </div>
      </div>
    </div>
  )
}

/* ---------- Generative widgets (UC014/015/016) ---------- */

/** Nút hành động nhỏ trên mỗi phiên lịch sử (Pin/Rename/Delete). */
function HistAction({
  icon: Icon,
  title,
  onClick,
  danger,
}: {
  icon: React.ElementType
  title: string
  onClick: () => void
  danger?: boolean
}) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      title={title}
      aria-label={title}
      className={cn(
        'flex size-7 items-center justify-center rounded-md text-popover-foreground/60 transition-colors active:scale-90',
        danger
          ? 'hover:bg-destructive hover:text-destructive-foreground'
          : 'hover:bg-popover-foreground/10 hover:text-popover-foreground',
      )}
    >
      <Icon className="size-3.5" />
    </button>
  )
}

/** Avatar tròn nhỏ với chữ cái đầu. */
function MiniAvatar({ initial }: { initial: string }) {
  return (
    <span className="gloss flex size-7 shrink-0 items-center justify-center rounded-full bg-emphasis font-serif text-xs font-semibold text-emphasis-foreground ring-1 ring-inset ring-accent/40">
      {initial}
    </span>
  )
}

/** Danh sách thư THẬT (bấm để mở thẳng thư) — dùng dưới kết quả AI. UI/UX: mỗi thư 1 hàng
 *  avatar + người gửi + tiêu đề + snippet + chấm chưa đọc; bấm → onOpen(id) mở chi tiết. */
function EmailRefList({ emails, onOpen }: { emails: EmailRef[]; onOpen?: (id: string) => void }) {
  return (
    <div className="mt-2 space-y-1.5">
      {emails.map((e) => (
        <button
          key={e.id}
          type="button"
          onClick={() => onOpen?.(e.id)}
          disabled={!onOpen}
          className="group/mail flex w-full items-center gap-2.5 rounded-xl bg-[#452216]/5 dark:bg-white/5 p-2 text-left transition-colors hover:bg-[#452216]/10 dark:hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        >
          <MiniAvatar initial={e.initial} />
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1.5 truncate text-sm font-medium text-foreground">
              {e.unread && <span className="size-1.5 shrink-0 rounded-full cherry-dot" />}
              <span className="truncate">{e.sender}</span>
            </p>
            <p className="truncate text-xs text-muted-foreground">{e.subject}</p>
            {e.snippet && (
              <p className="truncate text-[11px] text-muted-foreground/70">{e.snippet}</p>
            )}
          </div>
          {onOpen && (
            <ArrowUpRight className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover/mail:opacity-100" />
          )}
        </button>
      ))}
    </div>
  )
}

/** Tóm lược cuộc họp — bento: thời gian/deadline · người tham gia · checklist · điểm chính. */
/** Kết quả tra cứu đi lại, hiện NGAY TRONG CHAT.
 *
 *  Dùng lại đúng `DongBay`/`DongPhong` của khung "Tra cứu đi lại" — không vẽ lại một
 *  bản riêng. Vẽ hai lần thì hai chỗ sẽ TRÔI XA NHAU: sửa cột giá ở khung mà quên
 *  trong chat là cùng một chuyến bay hiện hai kiểu, và không ai biết bên nào đúng.
 *
 *  Nhãn nguồn giữ nguyên kiểu của khung (xanh = thật, hổ phách = mô phỏng) để người
 *  xem nhận ra ngay là CÙNG MỘT THỨ, dù tới bằng hai đường khác nhau. */
function DiLaiWidget({ reply }: { reply: Extract<AgentReply, { kind: 'dilai' }> }) {
  return (
    <Card className="rose-glass shadow-float">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {reply.loai === 'bay' ? (
            <Plane className="size-4 text-primary" />
          ) : (
            <Hotel className="size-4 text-primary" />
          )}
          {reply.title}
          <span
            className={cn(
              'flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1',
              'font-mono text-[10px] font-semibold uppercase tracking-[0.08em]',
              reply.la_that
                ? 'bg-[var(--rr-hoan,#0E8F63)]/15 text-[var(--rr-hoan,#0E8F63)]'
                : 'bg-[var(--ut-gap,#B45309)]/15 text-[var(--ut-gap,#B45309)]',
            )}
          >
            {reply.la_that ? <ShieldCheck className="size-3" /> : <FlaskConical className="size-3" />}
            {reply.nhan}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-2">
        <div className="flex flex-col gap-1.5">
          {(reply.items ?? []).map((k, i) => (
            <div key={i} className="goc-cat-nho goc-cat den-vien flex items-center gap-3 px-3 py-2">
              {reply.loai === 'bay' ? <DongBay k={k} /> : <DongPhong k={k} />}
            </div>
          ))}
        </div>
        <p className="mt-2.5 text-[11px] text-muted-foreground/80">
          Chỉ tra cứu — không đặt, không thanh toán.
        </p>
      </CardContent>
    </Card>
  )
}

function BriefWidget({ reply }: { reply: Extract<AgentReply, { kind: 'brief' }> }) {
  const [done, setDone] = useState<Set<number>>(new Set())
  const toggle = (i: number) =>
    setDone((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  return (
    <Card className="overflow-hidden rose-glass shadow-float">
      <CardHeader>
        <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <CalendarClock className="size-4 text-primary" />
          {reply.title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pt-2">
        {/* Hàng bento: thời gian · người tham gia */}
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-xl bg-[#452216]/5 dark:bg-white/5 p-3">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <Clock className="size-3.5" />
              Thời gian
            </p>
            <p className="mt-1 text-sm font-medium text-foreground">{reply.when}</p>
            {reply.deadline && (
              <p className="mt-1 inline-flex rounded-full bg-spark/20 px-2 py-0.5 text-[11px] font-semibold text-foreground">
                {reply.deadline}
              </p>
            )}
          </div>
          <div className="rounded-xl bg-[#452216]/5 dark:bg-white/5 p-3">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <Users className="size-3.5" />
              Tham gia
            </p>
            <div className="mt-1.5 space-y-1.5">
              {(reply.attendees ?? []).map((a) => (
                <div key={a.name} className="flex items-center gap-2">
                  <MiniAvatar initial={a.initial} />
                  <span className="truncate text-xs text-foreground">{a.name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Checklist action items (tick được) */}
        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Việc cần làm · {done.size}/{(reply.actions ?? []).length}
          </p>
          <div className="space-y-1">
            {(reply.actions ?? []).map((a, i) => {
              const checked = done.has(i)
              return (
                <button
                  key={i}
                  onClick={() => toggle(i)}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-sm transition-colors ease-spring hover:bg-popover-foreground/5 active:scale-[0.99]"
                >
                  <span
                    className={cn(
                      'flex size-5 shrink-0 items-center justify-center rounded-md ring-1 ring-inset transition-colors',
                      checked
                        ? 'ripe-pulse bg-success text-success-foreground ring-transparent'
                        : 'text-transparent ring-border',
                    )}
                  >
                    <Check className="size-3.5" />
                  </span>
                  <span
                    className={cn(
                      'min-w-0 flex-1',
                      checked ? 'text-muted-foreground line-through' : 'text-foreground',
                    )}
                  >
                    {a}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Điểm chính */}
        <div className="space-y-1 border-t border-border/40 pt-2.5">
          {(reply.points ?? []).map((p, i) => (
            <div key={i} className="flex gap-2 text-sm text-foreground/90">
              <span className="mt-1 size-1.5 shrink-0 rounded-full bg-active" />
              <span className="min-w-0">{p}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/** Phân loại hộp thư — nhóm theo ưu tiên, mỗi thư có gợi ý hành động + nút "đã xử lý".
 *
 *  ── Ô TICK PHẢI LÀM MỘT VIỆC THẬT ──
 *  Bản trước nó chỉ làm mờ dòng đó, và trạng thái mất khi đóng chat. Người dùng hỏi
 *  thẳng: "ô tick đó có tác dụng gì?" — câu hỏi đúng, vì một nút không để lại dấu vết
 *  nào ở đâu cả thì tệ hơn không có nút: nó hứa một việc rồi không làm.
 *  Nay tick = ĐÁNH DẤU ĐÃ ĐỌC thật trên hộp thư (đảo lại được, rủi ro thấp nhất trong
 *  các thao tác thư), nên lần sau mở lại vẫn đúng. */
function TriageWidget({
  reply, onOpenEmail, onDaXuLy,
}: {
  reply: Extract<AgentReply, { kind: 'triage' }>
  onOpenEmail?: (id: string) => void
  onDaXuLy?: (emailId: string) => void
}) {
  const [done, setDone] = useState<Set<string>>(new Set())
  const toggle = (k: string, id?: string) =>
    setDone((prev) => {
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else {
        next.add(k)
        // Chỉ đánh dấu đã đọc khi TICK VÀO. Bỏ tick không "đánh dấu chưa đọc" lại:
        // đó là một hành động khác, và tự ý làm thay người dùng thì bất ngờ.
        if (id) onDaXuLy?.(id)
      }
      return next
    })
  return (
    <Card className="overflow-hidden rose-glass shadow-float">
      <CardHeader>
        <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <ListChecks className="size-4 text-primary" />
          {reply.title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pt-2">
        {(reply.groups ?? []).map((g) => (
          <div key={g.label}>
            <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <span
                className={cn(
                  'size-2 rounded-full',
                  g.level === 'high' ? 'cherry-dot' : 'bg-muted-foreground/50',
                )}
              />
              {g.label} · {(g.items ?? []).length}
            </p>
            <div className="space-y-1.5">
              {(g.items ?? []).map((it, i) => {
                const key = `${g.label}-${i}`
                const checked = done.has(key)
                return (
                  <div
                    key={key}
                    className={cn(
                      'flex items-center gap-2.5 rounded-xl bg-popover-foreground/5 p-2 transition-opacity',
                      checked && 'opacity-50',
                    )}
                  >
                    <MiniAvatar initial={it.initial} />
                    {/* CẢ KHỐI CHỮ LÀ NÚT MỞ THƯ. Liệt kê thư mà không mở được thì
                        người dùng vẫn phải tự đi tìm lại trong hộp thư — bảng phân
                        loại dừng ở "biết có gì" mà không đi tiếp được. */}
                    <button
                      type="button"
                      disabled={!it.id || !onOpenEmail}
                      onClick={() => it.id && onOpenEmail?.(it.id)}
                      title={it.id ? 'Mở lá thư này' : undefined}
                      className="min-w-0 flex-1 text-left disabled:cursor-default"
                    >
                      <p
                        className={cn(
                          'truncate text-sm font-medium text-foreground',
                          checked && 'line-through',
                        )}
                      >
                        {it.sender}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">{it.subject}</p>
                    </button>
                    <span className="hidden shrink-0 rounded-full bg-active/15 px-2 py-0.5 text-[10px] font-semibold text-foreground sm:inline">
                      {it.suggest}
                    </span>
                    <button
                      onClick={() => toggle(key, it.id)}
                      title={checked ? t('ch.unmark') : t('ch.markHandled')}
                      className="flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-popover-foreground/10 hover:text-foreground active:scale-90"
                    >
                      {checked ? (
                        <CheckSquare className="size-4 text-success" />
                      ) : (
                        <Square className="size-4" />
                      )}
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

/** Tóm tắt hộp thư — bento số liệu + phân bổ theo nhãn (mini-bar) + nổi bật. */
function DigestWidget({ reply, onOpenEmail }: {
  reply: Extract<AgentReply, { kind: 'digest' }>
  onOpenEmail?: (id: string) => void
}) {
  const max = Math.max(1, ...(reply.breakdown ?? []).map((b) => b.count))
  return (
    <Card className="overflow-hidden rose-glass shadow-float">
      <CardHeader>
        <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <BarChart3 className="size-4 text-primary" />
          {reply.title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pt-2">
        {/* Tiles số liệu */}
        <div className="grid grid-cols-3 gap-2">
          {(reply.stats ?? []).map((s) => (
            <div
              key={s.label}
              className="ripe rounded-xl bg-popover-foreground/5 p-2.5 text-center"
              style={{ ['--tint' as string]: 'var(--spark)' }}
            >
              <p className="font-serif text-2xl font-semibold text-foreground">{s.value}</p>
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{s.label}</p>
            </div>
          ))}
        </div>
        {/* Phân bổ theo nhãn */}
        {(reply.breakdown ?? []).length > 0 && (
          <div className="space-y-1.5">
            {(reply.breakdown ?? []).map((b) => (
              <div key={b.label} className="flex items-center gap-2 text-xs">
                <span className="w-20 shrink-0 truncate text-muted-foreground">{b.label}</span>
                <span className="h-2 flex-1 overflow-hidden rounded-full bg-popover-foreground/10">
                  <span
                    className="block h-full rounded-full bg-active transition-all"
                    style={{ width: `${(b.count / max) * 100}%` }}
                  />
                </span>
                <span className="w-4 shrink-0 text-right font-semibold text-foreground">
                  {b.count}
                </span>
              </div>
            ))}
          </div>
        )}
        {/* Nổi bật */}
        {(reply.highlights ?? []).length > 0 && (
          <div className="space-y-1 border-t border-border/40 pt-2.5">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Nổi bật
            </p>
            {(reply.highlights ?? []).map((h, i) => (
              <div key={i} className="flex gap-2 text-sm text-foreground/90">
                <span className="mt-1 size-1.5 shrink-0 cherry-dot rounded-full" />
                <span className="min-w-0 truncate">{h}</span>
              </div>
            ))}
          </div>
        )}
        {/* MỞ THẲNG TỪNG THƯ. Báo cáo chỉ liệt kê tên thư thì đọc xong người dùng vẫn
            phải tự đi tìm lại trong hộp thư — tức là bản báo cáo dừng ở chỗ "biết có
            gì" mà không đi tiếp tới "làm gì với nó". */}
        {reply.emails && reply.emails.length > 0 && onOpenEmail && (
          <div className="space-y-1 border-t border-border/40 pt-2.5">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Mở nhanh
            </p>
            {(reply.emails ?? []).map((e) => (
              <button
                key={e.id}
                onClick={() => onOpenEmail(e.id)}
                className="flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-sm transition-colors hover:bg-foreground/5"
              >
                <span className="min-w-0 flex-1 truncate">
                  <span className="text-muted-foreground">{e.sender}: </span>
                  <span className="text-foreground/90">{e.subject}</span>
                </span>
                <ArrowUpRight className="size-3.5 shrink-0 text-[var(--spark)]" />
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}


/* ── LỊCH TRÌNH ────────────────────────────────────────────────────────────────
   Một khuôn cho ba câu hỏi: "tuần này tôi có gì", "tôi có quá tải không", "cần đi
   công tác việc nào". Trước đây cả ba rơi vào `kind:'text'` nên mô hình kể lại bằng
   lời — và câu "tuần này lịch trình tôi thế nào?" từng trả về ĐÚNG MỘT câu hỏi ngược,
   không liệt kê nổi một việc.

   Ba quyết định vẽ, mỗi cái sửa một lỗi đo được:
   1. DẢI ÁP LỰC vẽ CỘT, không viết số. "4 việc, 120 phút" bắt người đọc tự so sánh
      bảy con số trong đầu; bảy cái cột thì mắt so xong trong một nhịp.
   2. MỖI VIỆC LÀ MỘT NÚT mở thẳng lá thư sinh ra nó. Liệt kê tên việc rồi bỏ đó thì
      người dùng vẫn phải tự đi tìm lại trong hộp thư.
   3. NÚT "TRẢ LỜI" ngay tại chỗ. Đọc xong "tôi đang nợ ai cái gì" thì việc kế tiếp
      luôn là trả lời — không nên bắt đi vòng. */
function LichTrinhWidget({
  reply, onOpenEmail, onTraLoiThu,
}: {
  reply: Extract<AgentReply, { kind: 'lichtrinh' }>
  onOpenEmail?: (id: string) => void
  onTraLoiThu?: (emailId: string, tieuDe: string) => void
}) {
  const ngay = reply.ngay ?? []
  const viec = reply.viec ?? []
  // Thang TUYỆT ĐỐI theo ngày nặng nhất, tối thiểu 240 phút. Co thang theo dữ liệu thì
  // một tuần rảnh trông y hệt một tuần kín — cột nào cũng cao gần bằng nhau.
  const tran = Math.max(240, ...ngay.map((d) => d.phut))
  const thuVN = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']

  return (
    <Card className="mt-2 overflow-hidden">
      <CardContent className="space-y-3 p-3.5">
        <p className="text-[13px] font-semibold text-foreground">{reply.title}</p>

        {ngay.length > 0 && (
          <div className="flex items-end gap-1.5 border-b border-border/40 pb-3">
            {ngay.map((d) => {
              const cao = Math.max(4, Math.round((d.phut / tran) * 52))
              const dt = new Date(d.ngay)
              return (
                <div key={d.ngay} className="flex flex-1 flex-col items-center gap-1">
                  <span className="text-[9px] tabular-nums text-muted-foreground/70">
                    {d.so_viec > 0 ? d.so_viec : ''}
                  </span>
                  <div
                    style={{ height: `${cao}px` }}
                    title={`${d.so_viec} việc · ${d.phut} phút`}
                    className={cn(
                      'w-full rounded-sm transition-colors',
                      d.qua_tai ? 'bg-destructive/70' : d.phut > 0 ? 'bg-[var(--spark)]/60' : 'bg-foreground/10',
                    )}
                  />
                  <span className="text-[9px] text-muted-foreground/70">
                    {thuVN[dt.getDay()]}
                  </span>
                  <span className="text-[9px] tabular-nums text-muted-foreground/50">
                    {dt.getDate()}/{dt.getMonth() + 1}
                  </span>
                </div>
              )
            })}
          </div>
        )}

        {viec.length === 0 ? (
          <p className="text-[12.5px] text-muted-foreground">{t('st.noTasksRange')}</p>
        ) : (
          <div className="space-y-1">
            {viec.map((v, i) => (
              <div
                key={`${v.email_id || 'x'}-${i}`}
                className="group flex items-start gap-2 rounded-lg px-1.5 py-1.5 transition-colors hover:bg-foreground/5"
              >
                <span
                  aria-hidden
                  className={cn(
                    'mt-1.5 size-1.5 shrink-0 rounded-full',
                    (v.muc_uu_tien ?? 1) >= 3
                      ? 'bg-destructive'
                      : (v.muc_uu_tien ?? 1) === 2
                        ? 'bg-[var(--accent)]'
                        : 'bg-foreground/30',
                  )}
                />
                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    disabled={!v.email_id || !onOpenEmail}
                    onClick={() => v.email_id && onOpenEmail?.(v.email_id)}
                    className="block w-full text-left text-[13px] leading-snug text-foreground/90 disabled:cursor-default hover:enabled:underline"
                  >
                    {v.noi_dung}
                  </button>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                    {v.han && <span className="tabular-nums">Hạn {v.han}</span>}
                    {v.noi && <span>Đi {v.noi}{v.ma_san_bay ? ` (${v.ma_san_bay})` : ''}</span>}
                    {v.nguoi_cho && <span>Đang chờ {v.nguoi_cho}</span>}
                    {v.tieu_de && <span className="truncate">Từ thư: {v.tieu_de}</span>}
                  </p>
                </div>
                {v.email_id && (
                  <span className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                    {onTraLoiThu && (
                      <button
                        type="button"
                        title={t('mail.replyThis')}
                        onClick={() => onTraLoiThu(v.email_id!, v.tieu_de || v.noi_dung)}
                        className="rounded-md px-1.5 py-0.5 text-[11px] text-[var(--spark)] hover:bg-foreground/10"
                      >
                        Trả lời
                      </button>
                    )}
                    {onOpenEmail && (
                      <button
                        type="button"
                        title={t('mail.openThis')}
                        onClick={() => onOpenEmail(v.email_id!)}
                        className="rounded-md p-1 text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
                      >
                        <ArrowUpRight className="size-3.5" />
                      </button>
                    )}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ---------- Panel ---------- */

/* ĐÃ XOÁ hai thành phần MeltingWave (sơn tan chảy) và WaterDivider (mặt hồ
   gợn sóng) cùng dữ liệu đi kèm. Xem giải thích ở chỗ chúng từng được gắn.
   Lịch sử vẫn còn trong git nếu cần dựng lại. */

/** Đoạn phim nền — MỖI THEME MỘT ĐOẠN, và đây không phải chuyện thẩm mỹ.
 *
 *  Phép hoà trộn quyết định đoạn phim nào dùng được ở đâu:
 *
 *  TỐI  → `screen` (lấy giá trị sáng hơn). Đoạn phim phải có NỀN ĐEN thì vùng
 *         nền mới triệt tiêu hoàn toàn và chỉ còn lại vật thể phát sáng. Bông
 *         hoa thuỷ tinh đúng như vậy: nền đen tuyền, hoa rực ngũ sắc. Nhờ nó
 *         mà bản tối không còn phải ghì brightness xuống 0.38 như đoạn bong
 *         bóng trước — cái đó là chữa cháy cho một đoạn phim sai nền.
 *
 *  SÁNG → `multiply` (lấy giá trị tối hơn). Ở đây cần ngược lại: nền phải SÁNG
 *         thì mới triệt tiêu, còn vật thể sẫm hơn mới hiện ra. Bong bóng xà
 *         phòng trên nền studio trắng đúng vai này. Bê bông hoa nền đen sang
 *         đây thì cả khung hoá đen kịt.
 *
 *  Cùng một nguyên tắc phát xạ/tán sắc đã dùng cho toàn bộ giao diện, lần này
 *  quyết định luôn cả việc CHỌN TỆP.
 *
 *  Cả hai đều đã chuyển mã cho web: H.264, không tiếng, +faststart. Bản gốc của
 *  bông hoa là 30.9 MB (2888x2160, 19.9 Mbit/s) — bản dùng thật 1.28 MB.
 */
const PHIM_TOI = '/landing/space-bubble.mp4'   // nền đen  → dùng với screen
const PHIM_SANG = '/landing/soap-bubble.mp4'   // nền trắng → dùng với multiply

/**
 * TheDuDinh — agent xin phép TRƯỚC khi làm việc có hậu quả ra ngoài hộp thư.
 *
 * Đây là màn quan trọng nhất khi MeoArc gọi MCP đi đặt vé, đặt phòng — và cũng
 * là chỗ dễ làm sai nhất. Ba quyết định thiết kế, mỗi cái chữa một cách hỏng:
 *
 * 1. MỖI BƯỚC MỘT MỨC RỦI RO RIÊNG, không gộp thành một cục "đặt chuyến đi".
 *    Gộp lại thì người dùng không thấy được bước nào rút lại được, bước nào
 *    không — và họ sẽ duyệt cả cụm mà không biết mình vừa duyệt cái gì.
 *
 * 2. NÚT GIỮA LÀ NÚT QUAN TRỌNG NHẤT. "Chỉ thêm vào lịch" cho phép lấy phần an
 *    toàn và bỏ phần tốn tiền. Thiếu nó thì người dùng chỉ có duyệt tất hoặc bỏ
 *    tất — và khi phải chọn giữa hai cực đó, họ sẽ bỏ tất.
 *
 * 3. AGENT NÓI RA CHỖ NÓ ĐOÁN. Không giấu phần suy đoán đi. Một trợ lý nói rõ
 *    chỗ mình không chắc thì đáng tin hơn hẳn một trợ lý lúc nào cũng quả quyết.
 *
 * Mức rủi ro CAO NHẤT trong các bước quyết định độ sáng của cả thẻ — vì đó mới
 * là thứ người dùng đang thật sự đánh cược khi bấm duyệt.
 */
function TheDuDinh({
  reply,
  resolved,
  dangChay,
  onDuyet,
  onBoQua,
}: {
  reply: Extract<AgentReply, { kind: 'dudinh' }>
  resolved?: boolean
  /** Đang gọi backend — khoá nút để một cú bấm không thành hai đơn. */
  dangChay?: boolean
  onDuyet: () => void
  onBoQua: () => void
}) {
  const capCao = Math.max(1, ...(reply.buoc ?? []).map((b) => b.mucRuiRo)) as 1 | 2 | 3
  const tong = (reply.buoc ?? []).reduce((s, b) => s + (b.tien ?? 0), 0)
  const coTienThat = (reply.buoc ?? []).some((b) => b.mucRuiRo === 3)

  return (
    <div
      className={cn(
        // NỀN ĐỤC, không để trong suốt. Panel trợ lý có đoạn phim chạy phía sau;
        // thẻ này chứa SỐ TIỀN và các bước không hoàn tác được, nên nó là chỗ
        // cuối cùng được phép hy sinh độ đọc để lấy hiệu ứng. Vẫn giữ backdrop-blur
        // để nó còn thuộc về khung kính chung.
        'goc-cat mt-2 flex flex-col gap-3.5 bg-[var(--elevated)]/92 p-4 backdrop-blur-md',
        capCao === 3 ? 'rui-ro-3' : capCao === 2 ? 'rui-ro-2' : 'rui-ro-1',
        resolved && 'opacity-60',
      )}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.16em]"
          style={{ color: 'var(--rr)' }}>
          {coTienThat ? t('ch.noUndoMoney') : t('ch.needApproval')}
        </span>
        <span className="font-mono text-[11px] tabular-nums" style={{ color: 'var(--rr)' }}>
          {(reply.buoc ?? []).length} bước
        </span>
      </div>

      <h3 className="text-[15px] font-semibold leading-snug text-foreground">{reply.title}</h3>

      <div className="flex flex-col">
        {(reply.buoc ?? []).map((b, i) => (
          <div key={i}
            className="grid grid-cols-[14px_1fr_auto] items-center gap-2.5 border-t border-foreground/[0.07] py-2.5 first:border-t-0">
            <span className={cn('cham-rr', `c${b.mucRuiRo}`)} aria-hidden />
            <span className="min-w-0 text-[13px] text-foreground">
              {b.mo_ta}{' '}
              <span className="text-muted-foreground">· {b.hau_qua}</span>
            </span>
            <span className="font-mono text-[12px] tabular-nums"
              style={{ color: b.tien ? `var(--rr-${b.mucRuiRo === 3 ? 'khong' : b.mucRuiRo === 2 ? 'can' : 'hoan'})` : undefined }}>
              {b.tien ? `${b.tien.toLocaleString('vi-VN')} ₫` : '—'}
            </span>
          </div>
        ))}
      </div>

      {tong > 0 && (
        <div className="flex items-baseline justify-between border-t border-foreground/[0.07] pt-2.5">
          <span className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-muted-foreground">
            Tổng chi
          </span>
          <span className="font-mono text-[15px] font-bold tabular-nums" style={{ color: 'var(--rr)' }}>
            {tong.toLocaleString('vi-VN')} ₫
          </span>
        </div>
      )}

      {reply.cho_doan && (
        <p className="border-l-2 py-2 pl-3 pr-2 text-[12.5px] leading-relaxed text-muted-foreground"
          style={{ borderColor: 'var(--rr)', background: 'color-mix(in srgb, var(--rr) 5%, transparent)' }}>
          {reply.cho_doan}
        </p>
      )}

      {/* Ba nút này TỪNG KHÔNG GẮN HÀNH ĐỘNG NÀO — thẻ chỉ để nhìn. Và một trong ba
          ("Chỉ thêm vào lịch") hứa việc MeoArc không làm được: nó không ghi được vào
          Google Calendar. Một nút hứa sai còn tệ hơn không có nút, vì người dùng bấm
          rồi tưởng đã xong. Đã bỏ nút đó và nối hai nút còn lại vào đường thật. */}
      {!resolved && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onDuyet}
            disabled={dangChay}
            className="nut-ky-thuat px-4 py-2 text-[12.5px] font-semibold text-white disabled:opacity-60"
            style={{ ['--tint' as string]: 'var(--rr)', background: 'var(--rr)' }}>
            {dangChay ? 'Đang xử lý…' : coTienThat ? 'Duyệt & đặt' : 'Duyệt'}
          </button>
          <button
            onClick={onBoQua}
            disabled={dangChay}
            className="nut-ky-thuat px-4 py-2 text-[12.5px] font-medium text-muted-foreground disabled:opacity-60">
            Bỏ qua
          </button>
        </div>
      )}
    </div>
  )
}

export function ChatPanel({
  emails,
  actions,
  injectedCommand,
  onInjectConsumed,
  boiCanh,
  onBoBoiCanh,
  onOpenEmail,
  focusSignal,
  onClose,
}: {
  emails: Email[]
  actions: EmailActions
  injectedCommand?: string | null
  onInjectConsumed?: () => void
  /** BỐI CẢNH — "đang nói về việc này", KHÔNG tự gửi câu hỏi nào.
   *
   *  Khác `injectedCommand` ở đúng một điểm, và điểm đó tốn tiền: `injectedCommand`
   *  GỬI NGAY một câu hỏi dựng sẵn, nên bấm nút là mất một lượt gọi model dù người
   *  dùng chưa kịp nói mình muốn gì. Phần lớn lúc họ bấm vào một việc là để hỏi
   *  chuyện khác ("tìm vé máy bay đi dự sự kiện này") — câu hỏi dựng sẵn về "nên bắt
   *  đầu ngày nào, chia mấy buổi" bị vứt đi cùng với lượt gọi đã trả tiền.
   *
   *  Bối cảnh thì chỉ ĐÍNH KÈM vào câu người dùng thật sự gõ. Không gõ thì không gọi. */
  boiCanh?: { tieuDe: string; mo_ta: string } | null
  onBoBoiCanh?: () => void
  /** Mở 1 thư (chuyển panel phải sang chi tiết) — dùng khi bấm thư trong kết quả AI. */
  onOpenEmail?: (id: string) => void
  /** Tăng lên mỗi khi bấm tab "AI Agent" ở nav → bung composer + focus ô chat. */
  focusSignal?: number
  /** Đóng panel AI → trả Hộp thư về full-width (nút X trên header + tab AI Agent). */
  onClose?: () => void
}) {
  const [sessions, setSessions] = useState<Session[]>(initSessions)
  const [currentId, setCurrentId] = useState('s0')
  // Điều hướng trong app khi người dùng bảo "mở lịch trình" — xem lib/dieu-huong-chat.
  const dieuHuong = useNavigate()
  const [input, setInput] = useState('')
  /** Ô nhập TỰ GIÃN theo nội dung.
   *
   *  `rows={1}` + `resize-none` giữ ô luôn cao đúng một dòng, nên gõ quá một dòng là
   *  chữ cuộn trong một khe cao ~24px: không đọc lại được thứ mình vừa viết, và cũng
   *  không biết mình đã viết tới đâu. Với một ô mà người dùng được khuyến khích mô tả
   *  bằng lời thì đó là rào cản thẳng vào tính năng chính.
   *
   *  Đo lại chiều cao mỗi lần nội dung đổi: đặt `height='auto'` trước để `scrollHeight`
   *  co lại được khi xoá bớt chữ — thiếu bước đó thì ô chỉ phình ra mà không bao giờ
   *  nhỏ lại. Trần do CSS (`max-h-56`) lo, sau đó nội dung tự cuộn. */
  /** Tệp người dùng đính kèm cho LƯỢT SẮP GỬI.
   *
   *  Nút kẹp giấy trước đây KHÔNG có `onClick` — thuần hình vẽ. Một nút bấm không làm
   *  gì còn tệ hơn không có nút: người dùng thử, không thấy phản hồi, và kết luận là
   *  ứng dụng hỏng chứ không kết luận là tính năng chưa có.
   *
   *  Id do POST /uploads cấp, gửi kèm lượt chat. Mô hình KHÔNG chọn được tệp — nó chỉ
   *  quyết định có gửi thư hay không, còn gửi cái gì thì do người dùng đã tự tay chọn. */
  const [tepDinhKem, setTepDinhKem] = useState<{ id: string; name: string }[]>([])
  const [dangTaiTep, setDangTaiTep] = useState(false)
  const oChonTep = useRef<HTMLInputElement>(null)

  const chonTep = async (fs: FileList | null) => {
    if (!fs?.length) return
    setDangTaiTep(true)
    try {
      for (const f of Array.from(fs).slice(0, 3)) {
        const r = await api.uploadFile(f)
        setTepDinhKem((t) => (t.some((x) => x.id === r.id) ? t : [...t, { id: r.id, name: r.name }]))
      }
    } catch {
      // Tải hỏng (quá trần dung lượng chẳng hạn) thì báo ngay trong khung chat, chứ
      // không im lặng — im lặng ở đây khiến người dùng tưởng đã đính được rồi gửi đi
      // một lá thư thiếu tệp.
      push({ id: uid(), role: 'agent',
             reply: { kind: 'text', text: t('ch.uploadFail') } })
    } finally {
      setDangTaiTep(false)
      if (oChonTep.current) oChonTep.current.value = ''
    }
  }

  const oNhap = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = oNhap.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])
  // Composer THU GỌN: mặc định chỉ là 1 nút; bấm mới bung ô nhập + gợi ý (chừa chỗ cho
  // khung chat). Bấm ra ngoài (khi ô rỗng) → tự co lại. composerRef để phát hiện click ngoài.
  const [composerOpen, setComposerOpen] = useState(false)
  const composerRef = useRef<HTMLDivElement>(null)
  const [thinking, setThinking] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyQuery, setHistoryQuery] = useState('')
  const [voiceOpen, setVoiceOpen] = useState(false)
  // Gói + hạn mức token: hiện cạnh ô nhập, chặn gửi khi cạn, mở trang nâng cấp.
  const { status: sub, refresh: refreshSub, setStatus: setSub } = useSubscription()
  const [pricingOpen, setPricingOpen] = useState(false)
  /** Đoạn phim nền + cờ báo hỏng để rơi về bong bóng dựng bằng CSS. */
  const videoNenRef = useRef<HTMLVideoElement>(null)
  const [phimHong, setPhimHong] = useState(false)
  const { theme } = useTheme()
  const phimNen = theme === 'dark' ? PHIM_TOI : PHIM_SANG
  const [ttsOn, setTtsOn] = useState(true) // đọc lại câu trả lời khi dùng voice
  const [speaking, setSpeaking] = useState(false) // agent đang đọc → nút loa nhấp nháy
  // UC011 — đổi tên / xoá phiên
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deletingId, setDeletingId] = useState<string | null>(null)
  // #7 — tiến trình thực thi plan: { id phiên message, số bước đã xong }
  const [exec, setExec] = useState<{ id: string; current: number } | null>(null)
  const [executedIds, setExecutedIds] = useState<Set<string>>(new Set())
  // #3 — luồng sáng viền panel khi vừa hoàn tất tác vụ
  const [flash, setFlash] = useState(false)
  const flashTimer = useRef<number | null>(null)
  const triggerFlash = () => {
    setFlash(false)
    window.requestAnimationFrame(() => setFlash(true))
    if (flashTimer.current) clearTimeout(flashTimer.current)
    flashTimer.current = window.setTimeout(() => setFlash(false), 1100)
  }
  const scrollRef = useRef<HTMLDivElement>(null)

  const messages = useMemo(
    () => sessions.find((s) => s.id === currentId)?.messages ?? [],
    [sessions, currentId],
  )

  /** Gợi ý bước tiếp theo, lấy từ TIN CUỐI của trợ lý. Ẩn khi đang nghĩ — chìa ra
   *  một câu hỏi mới trong lúc câu trước chưa xong là mời người dùng bấm rồi mất lượt. */
  const buocTiepTheo = useMemo(() => {
    if (thinking) return []
    const cuoi = [...messages].reverse().find((m) => m.role === 'agent')
    return cuoi && 'reply' in cuoi && cuoi.reply ? goiYTiepTheo(cuoi.reply) : []
  }, [messages, thinking])

  // (#AI-native) GỢI Ý THEO NGỮ CẢNH — web "tư duy" từ tình trạng hộp thư thật:
  // thư quan trọng chưa đọc → gợi ý trả lời ĐÍCH DANH người gửi; có thư chưa đọc
  // → tóm tắt đúng số lượng; có thư khuyến mãi → gợi ý dọn; nhiều thư chưa nhãn
  // → gợi ý phân loại. Câu chữ bám đúng intent parser (lib/agent.ts) để bấm phát
  // là agent hiểu và chạy đúng việc. Tối đa 3 chip, ưu tiên việc gấp trước.
  const suggestions = useMemo(() => {
    const inbox = emails.filter((e) => (e.folder ?? 'inbox') === 'inbox')
    const out: ChipGoiY[] = []
    const urgent = inbox.find((e) => e.unread && e.status === 'Todo')
    if (urgent)
      out.push({ nhan: t('gy.replyTo', { ai: urgent.sender }), lenh: `Soạn trả lời ${urgent.sender}` })
    const unread = inbox.filter((e) => e.unread).length
    if (unread > 0)
      out.push({ nhan: t('gy.sumUnread', { n: unread }), lenh: `Tóm tắt ${unread} thư chưa đọc` })
    const promo = inbox.filter((e) => e.category === 'terra').length
    if (promo > 0)
      out.push({ nhan: t('gy.cleanPromo', { n: promo }), lenh: `Dọn ${promo} thư khuyến mãi` })
    if (out.length < 3) {
      const unlabeled = inbox.filter((e) => !e.label).length
      if (unlabeled >= 2) out.push(chip('gy.autoLabel', 'Phân loại tự động thư chưa nhãn'))
    }
    if (out.length < 3) {
      const waiting = inbox.find((e) => e.status === 'Waiting')
      if (waiting)
        out.push({ nhan: t('gy.sumFrom', { ai: waiting.sender }), lenh: `Tóm tắt thư của ${waiting.sender}` })
    }
    if (out.length === 0) out.push(chip('gy.digestToday', 'Tóm tắt hộp thư hôm nay'))
    return out.slice(0, 3)
  }, [emails])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, thinking])

  // Composer vừa bung → focus ô nhập ngay cho gõ liền.
  useEffect(() => {
    if (composerOpen) document.getElementById('meoarc-composer-input')?.focus()
  }, [composerOpen])

  // Bấm RA NGOÀI composer (khi ô đang RỖNG) → tự co lại thành nút → chừa chỗ cho khung chat.
  // Còn chữ trong ô thì KHÔNG co (khỏi mất bản nháp đang gõ dở).
  useEffect(() => {
    if (!composerOpen) return
    const onDown = (e: PointerEvent) => {
      if (composerRef.current?.contains(e.target as Node)) return
      if (input.trim()) return
      setComposerOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [composerOpen, input])

  // Esc để đóng drawer lịch sử
  useEffect(() => {
    if (!historyOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setHistoryOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [historyOpen])

  // Lọc + nhóm lịch sử: phiên đã ghim lên đầu, phần còn lại theo mốc thời gian (UC011)
  const historyGroups = useMemo(() => {
    const q = historyQuery.trim().toLowerCase()
    const filtered = q ? sessions.filter((s) => searchTextOf(s).includes(q)) : sessions
    const pinned = filtered.filter((s) => s.pinned)
    const rest = filtered.filter((s) => !s.pinned)
    const map = new Map<string, Session[]>()
    rest.forEach((s) => {
      const b = timeBucket(s.time)
      if (!map.has(b)) map.set(b, [])
      map.get(b)!.push(s)
    })
    const groups: { label: string; items: Session[]; pinned?: boolean }[] = []
    if (pinned.length) groups.push({ label: t('st.pinned'), items: pinned, pinned: true })
    TIME_ORDER.filter((o) => map.has(o)).forEach((o) => groups.push({ label: t(o), items: map.get(o)! }))
    return groups
  }, [sessions, historyQuery])

  // Cập nhật messages của phiên hiện tại
  const updateMessages = (fn: (m: Message[]) => Message[]) =>
    setSessions((prev) =>
      prev.map((s) => (s.id === currentId ? { ...s, messages: fn(s.messages) } : s)),
    )
  const push = (m: Message) => updateMessages((prev) => [...prev, m])

  const freshSession = (): Session => ({
    id: uid(),
    title: 'Cuộc trò chuyện mới',
    time: t('tm.now'),
    messages: [{ id: uid(), role: 'agent', reply: { kind: 'text', text: WELCOME } }],
  })

  const newChat = () => {
    const s = freshSession()
    setSessions((prev) => [s, ...prev])
    setCurrentId(s.id)
  }

  /* UC011: nạp lịch sử phiên ĐÃ LƯU từ backend (chế độ HTTP).
     Phiên tải về chỉ có metadata (messages rỗng) — mở phiên nào thì mới getConversation.

     ── LỖI ĐÃ SỬA: CÂU HỎI BỐC HƠI SAU VÀI GIÂY ──
     Bản trước, khi lời gọi này trả về nó chạy `setSessions([fresh, ...loaded])` rồi
     `setCurrentId(fresh.id)` — tức THAY SẠCH phiên đang mở bằng một phiên TRỐNG.

     Trên máy nhà, lời gọi về trong vài chục mili-giây nên không ai thấy. Trên bản
     chạy thật nó mất vài giây, và trong khoảng đó người dùng đã kịp bấm "Hỏi trợ lý"
     từ trang Lịch trình: câu hỏi hiện lên, agent bắt đầu nghĩ, rồi lịch sử về và
     XOÁ luôn phiên chứa câu hỏi đó. Màn hình quay về lời chào, câu trả lời đang tới
     thì rơi vào một phiên không còn được hiển thị.

     Triệu chứng người dùng mô tả: "hỏi xong khoảng 10 mấy giây thì AI bị refresh và
     hiện lại đoạn Chào Quân". Đúng là refresh — do chính đoạn mã này.

     Nay: GIỮ NGUYÊN phiên đang mở, chỉ ghép lịch sử vào SAU nó, và KHÔNG đụng tới
     `currentId`. Người dùng đang đứng ở đâu thì ở nguyên đó. */
  const currentIdRef = useRef(currentId)
  useEffect(() => { currentIdRef.current = currentId }, [currentId])
  // Cần đọc `sessions` bên trong effect chạy MỘT LẦN mà không đưa nó vào deps (đưa
  // vào thì effect chạy lại mỗi lượt chat và nạp lại lịch sử liên tục).
  const sessionsRef = useRef(sessions)
  useEffect(() => { sessionsRef.current = sessions }, [sessions])

  /** GHI NHỚ cuộc trò chuyện đang mở, để mọi màn nối lại đúng nó.
   *  Ghi mỗi khi phiên hiện tại có backendId — tức là ngay khi backend cấp id ở lượt
   *  đầu, và mỗi lần người dùng tự đổi phiên. */
  useEffect(() => {
    const bid = sessions.find((s) => s.id === currentId)?.backendId
    if (bid) ghi(KHOA_CHAT, bid)
  }, [sessions, currentId])

  useEffect(() => {
    let alive = true
    api
      .listConversations()
      .then((list) => {
        if (!alive || list.length === 0) return
        const loaded: Session[] = list.map((c) => ({
          id: c.id,
          backendId: c.id,
          title: c.title,
          time: relTime(c.updatedAt),
          pinned: c.pinned,
          messages: [],
        }))
        setSessions((prev) => {
          const dangMo = prev.find((s) => s.id === currentIdRef.current) ?? prev[0]
          // Bỏ bản trùng: phiên đang mở có thể đã được lưu xuống backend rồi.
          const conLai = loaded.filter((c) => c.id !== dangMo?.backendId)
          return dangMo ? [dangMo, ...conLai] : [freshSession(), ...loaded]
        })
        // KHÔNG setCurrentId khi phiên đang mở ĐÃ CÓ tin nhắn — đổi phiên dưới chân
        // người dùng là cách chắc chắn nhất làm mất câu hỏi họ vừa gửi.
        //
        // ── NỐI LẠI ĐÚNG CUỘC TRÒ CHUYỆN ĐANG DỞ ──
        // Nhưng nếu phiên đang mở còn TRẮNG (vừa mount, mới chỉ có lời chào) thì nối
        // lại cuộc đang dở. Trước đây mỗi lần đổi trang là một ChatPanel mới mount và
        // bắt đầu từ 's0' trắng, nên đi Lịch trình rồi quay về Hộp thư là mất mạch:
        // hai màn cùng một ứng dụng mà hoá ra hai cuộc trò chuyện khác nhau.
        const dangTrong = !sessionsRef.current
          .find((s) => s.id === currentIdRef.current)
          ?.messages.some((m) => m.role === 'user')
        const idLuu = doc(KHOA_CHAT)
        if (dangTrong && idLuu && loaded.some((s) => s.id === idLuu)) {
          // PHẢI TẢI NỘI DUNG TRƯỚC KHI CHUYỂN SANG.
          // Danh sách hội thoại chỉ mang metadata (`messages: []`), nội dung tải lười
          // khi mở từ drawer. Chuyển `currentId` sang một phiên rỗng thì khung chat
          // trắng trơn — không tin nhắn cũ, mà cũng mất luôn lời chào (lời chào nằm
          // trong phiên 's0' vừa bị bỏ lại). Người dùng thấy đúng một khoảng trắng.
          api
            .getConversation(idLuu)
            .then((detail) => {
              if (!alive) return
              setSessions((prev) =>
                prev.map((x) =>
                  x.id === idLuu ? { ...x, messages: detail.messages.map(toLocalMsg) } : x,
                ),
              )
              setCurrentId(idLuu)
            })
            // Tải hỏng (phiên đã bị xoá ở máy khác chẳng hạn) thì Ở NGUYÊN phiên chào
            // hiện tại. Thà bắt đầu lại còn hơn nhìn một khung trắng không lối thoát.
            .catch(() => {})
        }
      })
      .catch(() => {}) // lỗi mạng/chưa đăng nhập → cứ giữ initSessions, không vỡ UI
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---- UC011: Mở / Pin / Rename / Delete (đều LƯU xuống backend nếu phiên đã có backendId) ----
  // Mở 1 phiên ở drawer: chuyển sang phiên đó; nếu mới có metadata (messages rỗng) thì tải đầy đủ.
  const openSession = (s: Session) => {
    setCurrentId(s.id)
    setHistoryOpen(false)
    if (s.backendId && s.messages.length === 0) {
      api
        .getConversation(s.backendId)
        .then((detail) => {
          setSessions((prev) =>
            prev.map((x) => (x.id === s.id ? { ...x, messages: detail.messages.map(toLocalMsg) } : x)),
          )
        })
        .catch(() => {})
    }
  }

  const togglePin = (id: string) => {
    const s = sessions.find((x) => x.id === id)
    const next = !s?.pinned
    setSessions((prev) => prev.map((x) => (x.id === id ? { ...x, pinned: next } : x)))
    if (s?.backendId) api.updateConversation(s.backendId, { pinned: next }).catch(() => {})
  }

  const startRename = (s: Session) => {
    setRenamingId(s.id)
    setRenameValue(s.title)
  }
  const commitRename = () => {
    const title = renameValue.trim()
    if (!title || title.length > RENAME_MAX) return // A4 — rename không hợp lệ: giữ ô mở
    const s = sessions.find((x) => x.id === renamingId)
    setSessions((prev) => prev.map((x) => (x.id === renamingId ? { ...x, title } : x)))
    if (s?.backendId) api.updateConversation(s.backendId, { title }).catch(() => {})
    setRenamingId(null)
  }

  const deleteSession = (id: string) => {
    const s = sessions.find((x) => x.id === id)
    if (s?.backendId) api.deleteConversation(s.backendId).catch(() => {})
    const next = sessions.filter((x) => x.id !== id)
    if (next.length === 0) {
      const fresh = freshSession()
      setSessions([fresh])
      setCurrentId(fresh.id)
    } else {
      setSessions(next)
      if (id === currentId) setCurrentId(next[0].id)
    }
    setDeletingId(null)
  }

  // Đọc to câu trả lời (SpeechSynthesis, vi-VN) — dùng khi tương tác bằng giọng nói
  const speak = (txt: string) => {
    if (!ttsOn || !txt || typeof window === 'undefined' || !('speechSynthesis' in window)) return
    try {
      window.speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(txt)
      u.lang = 'vi-VN'
      u.rate = 1.02
      u.onstart = () => setSpeaking(true)
      u.onend = () => setSpeaking(false)
      u.onerror = () => setSpeaking(false)
      window.speechSynthesis.speak(u)
    } catch {
      /* noop */
    }
  }

  const send = (raw: string, viaVoice = false) => {
    const text = raw.trim()
    if (!text || thinking) return

    // ── ĐI LẠI TRONG APP: xử lý TẠI CHỖ, KHÔNG gọi model ──
    // "cho tôi xem lịch trình" là một lệnh đi lại, không phải một câu hỏi. Đẩy nó qua
    // agent thì tốn một lượt trong hạn mức 20 lượt/ngày cho việc mà một biểu thức
    // chính quy làm được — và người dùng phải ngồi chờ "đang nghĩ" cho một cú bấm.
    // Ở đây phản hồi tức thì, tốn 0 lượt, và vẫn chạy khi đã hết quota.
    // Luật khớp cố ý chặt tay; nghi ngờ thì nhường cho agent (xem lib/dieu-huong-chat).
    const dich = doDieuHuong(text)
    if (dich) {
      push({ id: uid(), role: 'user', text })
      push({ id: uid(), role: 'agent',
             reply: { kind: 'done', text: t('ch.opening', { ten: dich.ten }) } })
      setInput('')
      chuyenCanh(() => dieuHuong(dich.duong_dan))
      return
    }
    // BỐI CẢNH đính vào câu người dùng gõ, chỉ ở lượt đầu sau khi bấm vào một việc.
    // Hiện trong bong bóng là ĐÚNG câu họ gõ (biến `text`), còn bản gửi lên agent mới
    // kèm ngữ cảnh — người dùng không phải đọc lại một khối dữ liệu họ vừa bấm vào.
    const guiDi = boiCanh
      ? `[Đang nói về: ${boiCanh.tieuDe} — ${boiCanh.mo_ta}]\n\n${text}`
      : text
    // Cạn hạn mức token → chặn ngay ở client, khỏi gọi backend chỉ để nhận lỗi.
    if (isOutOfTokens(sub)) {
      setPricingOpen(true)
      return
    }
    // Thêm tin user + đặt tiêu đề phiên nếu là tin đầu tiên
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id !== currentId) return s
        const firstUser = !s.messages.some((m) => m.role === 'user')
        return {
          ...s,
          time: t('tm.now'),
          title: firstUser ? (text.length > 40 ? text.slice(0, 40) + '…' : text) : s.title,
          messages: [...s.messages, { id: uid(), role: 'user', text }],
        }
      }),
    )
    setInput('')
    setThinking(true)
    // Bối cảnh chỉ dùng cho MỘT lượt: gửi xong là gỡ chip. Giữ mãi thì mọi câu sau đó
    // đều bị gắn thêm một việc mà người dùng đã chuyển chủ đề từ lâu.
    onBoBoiCanh?.()
    // Tệp chỉ đi theo MỘT lượt: gửi xong là gỡ. Giữ lại thì lượt sau vô tình đính lại
    // đúng tệp đó, và người dùng không hề biết mình vừa gửi nó lần thứ hai.
    setTepDinhKem([])
    // Gửi kèm backendId của phiên hiện tại (nếu đã lưu) để agent NHỚ đúng cuộc trò chuyện (UC011).
    const sid = currentId
    const backendId = sessions.find((s) => s.id === sid)?.backendId
    // Qua lớp adapter (UC007): mock trả interpretCommand; backend thật gọi POST /agent/chat.
    api
      .sendAgentMessage(guiDi, { emails },
                        { viaVoice, sessionId: backendId,
                          attachmentIds: tepDinhKem.map((t) => t.id) })
      .then((reply) => {
        setThinking(false)
        // Lần đầu của phiên mới: BE trả conversationId → gắn vào phiên để các lượt sau bám đúng.
        if (reply.conversationId) {
          setSessions((prev) =>
            prev.map((s) => (s.id === sid ? { ...s, backendId: reply.conversationId } : s)),
          )
        }
        push({ id: uid(), role: 'agent', reply })
        if (viaVoice) speak(replyToSpeech(reply))
        void refreshSub() // lượt vừa rồi đã tiêu token → cập nhật lại đồng hồ
      })
      .catch(() => {
        setThinking(false)
        push({
          id: uid(),
          role: 'agent',
          reply: { kind: 'text', text: t('ch.error') },
        })
      })
  }

  // Lệnh từ nút ngữ cảnh (UC016) — tự gửi khi app-shell đẩy vào.
  //
  // CỜ CHỐNG GỬI HAI LẦN. React StrictMode gọi effect hai lượt khi mount, và cả hai
  // lượt đều chạy TRƯỚC khi cha kịp xoá lệnh — nên một lần bấm "Hỏi trợ lý" cho ra
  // HAI câu hỏi và HAI thẻ trả lời giống hệt nhau. Đã chụp được đúng vậy.
  //
  // Cờ tự đặt lại khi `injectedCommand` về null (tức cha đã tiêu thụ xong), nên bấm
  // lại đúng việc đó lần nữa vẫn gửi được. Nếu chỉ so sánh nội dung lệnh thì lần bấm
  // thứ hai vào CÙNG một việc sẽ bị nuốt — một cách sửa tưởng đúng mà lại chặn nhầm
  // thao tác hợp lệ.
  const dangGuiLenh = useRef(false)
  useEffect(() => {
    if (!injectedCommand) { dangGuiLenh.current = false; return }
    if (dangGuiLenh.current) return
    dangGuiLenh.current = true
    send(injectedCommand)
    onInjectConsumed?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [injectedCommand])

  // Bấm tab "AI Agent" ở nav → bung ô nhập (nếu đang thu gọn) + focus con trỏ vào chat
  // + cuộn xuống cuối. Nhờ vậy nút không còn "vô tác dụng" khi chat đã hiển thị sẵn.
  useEffect(() => {
    if (!focusSignal) return
    setComposerOpen(true)
    const t = window.setTimeout(() => {
      const el = document.getElementById('meoarc-composer-input') as HTMLTextAreaElement | null
      el?.focus()
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }, 60)
    return () => window.clearTimeout(t)
  }, [focusSignal])

  const markResolved = (id: string) => {
    updateMessages((prev) =>
      prev.map((m) => (m.id === id && m.role === 'agent' ? { ...m, resolved: true } : m)),
    )
    // GHI XUỐNG MÁY CHỦ. Chỉ đổi ở bộ nhớ trình duyệt thì tải lại trang là mất, và thẻ
    // xoá đã duyệt lại mọc ra nút "Duyệt". Lỗi im lặng: hỏng thì thẻ vẫn đúng trong
    // phiên đang mở, chỉ mất sau khi tải lại — không đáng làm phiền người dùng giữa
    // lúc họ vừa duyệt xong một việc.
    const bid = sessions.find((s) => s.id === currentId)?.backendId
    if (apiBaseUrlDaCauHinh && bid) api.resolveMessage(bid, id).catch(() => {})
  }

  const execOp = (op: PlanOp) => {
    if (op.type === 'archive' || op.type === 'delete') actions.removeEmails(op.ids, op.type)
    else if (op.type === 'restore') actions.restoreEmails(op.ids)
    else if (op.type === 'markRead') actions.markRead(op.ids, op.read)
    else if (op.type === 'label') actions.applyLabel(op.ids, op.category, op.label)
    else if (op.type === 'autoLabel')
      op.items.forEach((it) => actions.applyLabel([it.id], it.category, it.label))
  }

  // #7 — duyệt plan: chạy từng bước (skeleton → ripe-pulse) rồi mới thực thi
  const approvePlan = (id: string, op: PlanOp, stepCount: number) => {
    const total = Math.max(1, stepCount)
    setExec({ id, current: 0 })
    let i = 0
    const tick = () => {
      i += 1
      if (i < total) {
        setExec({ id, current: i })
        window.setTimeout(tick, 550)
      } else {
        setExec(null)
        setExecutedIds((prev) => new Set(prev).add(id))
        execOp(op)
        markResolved(id)
        push({ id: uid(), role: 'agent', reply: { kind: 'done', text: doneText(op) } })
        triggerFlash()
      }
    }
    window.setTimeout(tick, 550)
  }

  /* ── DUYỆT THẺ DỰ ĐỊNH ────────────────────────────────────────────────────
     Đây là mắt xích cuối để cả ý tưởng chạy được đầu-cuối: agent đề xuất → người
     bấm → hệ thống thực thi qua cổng tiền.

     Đi qua `/confirmations/{id}/approve` — đường TẤT ĐỊNH, KHÔNG qua mô hình. Mô
     hình đã làm xong phần việc của nó (đề xuất) trước khi thẻ hiện ra; để nó tham
     gia lần nữa lúc thực thi thì thứ chạy có thể khác thứ người dùng vừa duyệt.

     Chế độ mock không có `confirmationId`. Vẫn cho duyệt, nhưng nói THẲNG là mô
     phỏng — im lặng để người dùng tưởng đã đặt thật là kiểu nói dối tệ nhất ở đây. */
  const [dangDuyetId, setDangDuyetId] = useState<string | null>(null)

  const onDuyetDuDinh = async (
    id: string,
    reply: Extract<AgentReply, { kind: 'dudinh' }>,
  ) => {
    if (dangDuyetId) return          // khoá: một cú bấm không được thành hai đơn
    setDangDuyetId(id)
    const tong = (reply.buoc ?? []).reduce((s, b) => s + (b.tien ?? 0), 0)
    try {
      let ma = ''
      if (reply.confirmationId) {
        const ra = await api.approveConfirmation(reply.confirmationId)
        const d = (ra?.result ?? {}) as { data?: { ma_dat_cho?: string }; message?: string }
        ma = d.data?.ma_dat_cho ?? ''
      }
      markResolved(id)
      push({
        id: uid(),
        role: 'agent',
        reply: {
          kind: 'result',
          title: ma ? t('ch.bookedSim', { ma }) : t('ch.approvedSim'),
          intro: t('ch.readLastLine'),
          lines: [
            reply.title,
            tong > 0 ? t('ch.totalSpent', { tien: tong.toLocaleString('vi-VN') }) : t('ch.noCost'),
            t('ch.simWarn1')
            + t('ch.simWarn2'),
          ],
        },
      })
      triggerFlash()
    } catch (e) {
      markResolved(id)
      push({
        id: uid(),
        role: 'agent',
        reply: { kind: 'text', text: t('ch.approveFail', { loi: String(e).slice(0, 140) }) },
      })
    } finally {
      setDangDuyetId(null)
    }
  }

  const onBoQuaDuDinh = (id: string) => {
    markResolved(id)
    push({
      id: uid(),
      role: 'agent',
      reply: { kind: 'text', text: t('ch.skipped') },
    })
  }

  const rejectPlan = (id: string) => {
    markResolved(id)
    push({
      id: uid(),
      role: 'agent',
      reply: { kind: 'text', text: t('ch.cancelled') },
    })
  }

  // UC010 — GỬI THẬT bản nháp sau khi user duyệt trên DraftCard (human-in-the-loop):
  // draft thường → POST /emails/send; draft TRẢ LỜI (replyToId) → POST /emails/{id}/reply
  // (giữ đúng luồng thư). Mock mode: adapter giả trả ok — UX như cũ. Trả true/false để
  // DraftCard biết đóng thẻ hay GIỮ LẠI cho user sửa/bấm gửi lại khi lỗi. Nhờ gửi qua
  // endpoint tất định (không qua LLM) nên "Đã gửi ✓" = thư THẬT SỰ đã đi.
  const sendDraft = async (
    id: string,
    draft: { to: string; subject: string; body: string; replyToId?: string; confirmationId?: string },
  ): Promise<boolean> => {
    try {
      if (draft.confirmationId) {
        // Đường CHUẨN: máy chủ giữ trạng thái yêu cầu duyệt, nên bấm hai lần vẫn chỉ
        // gửi một lần (PA2 §1.3.5). Trước đây nút này gọi thẳng lệnh gửi — mở lại hội
        // thoại cũ rồi bấm lại là thư đi lần nữa.
        await api.approveConfirmation(draft.confirmationId)
      } else if (draft.replyToId) {
        await api.replyEmail(draft.replyToId, draft.body)
      } else {
        // "Tên <email>" → chỉ gửi phần địa chỉ cho backend
        const addr = (draft.to.match(/<([^>]+)>/)?.[1] ?? draft.to).trim()
        await api.sendEmail({ to: addr, subject: draft.subject, body: draft.body })
      }
      markResolved(id)
      push({
        id: uid(),
        role: 'agent',
        reply: {
          kind: 'done',
          text: draft.replyToId
            ? t('ch.replySent')
            : `Đã gửi email tới ${draft.to.split('<')[0].trim()}.`,
        },
      })
      triggerFlash()
      return true
    } catch {
      push({
        id: uid(),
        role: 'agent',
        reply: {
          kind: 'text',
          text: t('ch.sendFail'),
        },
      })
      return false
    }
  }

  // UC010 — "Viết lại": nhờ AGENT soạn lại ĐÚNG bản nháp này (giữ người nhận + chủ đề),
  // KHÔNG tạo email mới. Neo theo chủ đề/người nhận để agent không lạc đề (fix bug rewrite
  // ra email khác hẳn). Agent trả về 1 thẻ nháp mới đã viết lại.
  const rewriteDraft = (
    draft: { to: string; subject: string; body: string; replyToId?: string; confirmationId?: string },
    instruction: string,
  ) => {
    const instr = instruction.trim()
    send(
      `Viết lại bản nháp email vừa rồi (chủ đề “${draft.subject}”, gửi ${draft.to})` +
        `${instr ? ` theo yêu cầu: “${instr}”` : ''}. ` +
        `Giữ NGUYÊN người nhận và chủ đề, chỉ đổi cách hành văn — tuyệt đối không đổi chủ đề.`,
    )
  }

  // UC017 — áp dụng kết quả tự lái vào hộp thư thật
  const applyAutopilot = (id: string, r: AutopilotResult) => {
    if (r.archive.length) actions.removeEmails(r.archive, 'archive')
    if (r.markRead.length) actions.markRead(r.markRead, true)
    if (r.flag.length) actions.setImportant(r.flag, true)
    markResolved(id)
    const parts: string[] = []
    if (r.counts.archive) parts.push(t('ch.autoArchive', { n: r.counts.archive }))
    if (r.counts.markRead) parts.push(t('ch.autoRead', { n: r.counts.markRead }))
    if (r.counts.flag) parts.push(t('ch.autoFlag', { n: r.counts.flag }))
    if (r.counts.replied) parts.push(t('ch.autoReplied', { n: r.counts.replied }))
    const summary = parts.length ? parts.join(', ') : t('ch.autoNothing')
    push({
      id: uid(),
      role: 'agent',
      reply: { kind: 'done', text: t('ch.autoDone', { tt: summary }) },
    })
    triggerFlash()
  }

  // UC009 — áp dụng nhãn sau khi user chỉnh checklist
  /** Soạn trả lời cho một lá thư ngay từ thẻ lịch trình.
   *
   *  Gửi thẳng một câu vào chính khung chat thay vì mở hộp thoại riêng: nó đi qua
   *  đúng luồng agent (có cổng xác nhận trước khi gửi thật), và người dùng THẤY được
   *  yêu cầu mình vừa đặt nằm trong dòng hội thoại — không có gì xảy ra sau lưng. */
  const traLoiThu = (emailId: string, tieuDe: string) => {
    send(`soạn trả lời cho thư ${emailId}${tieuDe ? ` ("${tieuDe}")` : ''}`)
  }

  const applyCategorize = (
    id: string,
    items: { id: string; category: Category; label: string }[],
  ) => {
    items.forEach((it) => actions.applyLabel([it.id], it.category, it.label))
    markResolved(id)
    push({
      id: uid(),
      role: 'agent',
      reply: { kind: 'done', text: t('ch.categorised', { n: items.length }) },
    })
    triggerFlash()
  }

  // #8 — phát hiện confirmation đang chờ (plan/draft cuối chưa xử lý) để spotlight
  const lastMsg = messages[messages.length - 1]
  const pendingConfirmId =
    lastMsg &&
    lastMsg.role === 'agent' &&
    !lastMsg.resolved &&
    !exec &&
    (lastMsg.reply.kind === 'plan' || lastMsg.reply.kind === 'draft')
      ? lastMsg.id
      : null

  return (
    <aside className="ai-panel-bg den-noi-trai relative z-10 flex h-full flex-1 flex-col overflow-hidden shadow-soft duration-300 animate-in fade-in">
      {/* ĐOẠN PHIM NỀN — nguồn để khối kính khúc xạ, và nó PHẢI ĂN NHẬP VỚI NỀN, KHÔNG PHẢI DÁN LÊN NỀN.
          Bản thô là một bong bóng TRẮNG LOÁ trên nền studio sáng. Đặt nguyên nó
          lên nền #05060D thì nó không thuộc về căn phòng ấy — nó là một tấm ảnh
          dán lên tường tối, và mắt đọc ra ngay.

          Thử `mix-blend-mode: screen` trước và nó KHÔNG ăn thua, vì một lý do đáng
          ghi lại: screen lấy giá trị sáng hơn của hai lớp, mà nền ở đây là #05060D
          — gần như đen tuyệt đối. Screen với đen chính là phép đồng nhất, nên nó
          không đổi được gì cả. Vẫn giữ screen vì ở những chỗ nền không thuần đen
          nó có tác dụng, nhưng nó không phải đòn bẩy.

          Đòn bẩy là `filter`. Ghì brightness xuống 0.38 để nền studio trắng của
          đoạn phim tụt xuống ngang tầm nền tối của mình, rồi đẩy contrast và
          saturate lên bù lại — làm thế thì chỉ những vân ngũ sắc rực nhất mới
          sống sót, đúng những thứ đáng giữ. hue-rotate kéo phổ về phía tím/hồng
          của thương hiệu để đoạn phim không mang một hệ màu riêng.

          Bản gốc dặn "không phủ lớp làm tối nào lên phim" — vẫn giữ đúng: đây
          không phải lớp phủ, đây là cách chính đoạn phim hoà vào nền. Riêng
          phần mờ dần về đáy thì cần, vì dưới đó là chip gợi ý và ô nhập, chữ
          phải đọc được. */}
      <video
        ref={videoNenRef}
        className="phim-nen"
        aria-hidden
        autoPlay muted loop playsInline preload="auto"
        key={phimNen}
        src={phimNen}
        onError={() => setPhimHong(true)}
      />
      {/* Định nghĩa bộ lọc khúc xạ — gắn một lần, các khối kính trỏ tới bằng id */}
      <KinhKhucXaDefs />
      {/* Bong bóng dựng bằng CSS: nền dự phòng khi đoạn phim không tải được
          (mạng chặn, CDN hỏng). Không có nó thì panel thành một mảng đen trơn. */}
      {phimHong && <ChatAmbience />}
      {/* CHỮ "MEOARC" LÀM NỀN ĐÃ GỠ HẲN, cùng toàn bộ khối <style> đi kèm.
          Nó từng là chữ ký của khung này, rồi bị hạ xuống 12% để thôi tranh chỗ
          với hội thoại. Nhưng hạ độ mờ chỉ chữa triệu chứng: nền panel giờ đã có
          một VẬT THẬT — bông hoa thuỷ tinh — nên chồng thêm một dòng chữ khổng lồ
          sau nó là hai thứ cùng đòi làm hình nền. Bỏ hẳn thì bông hoa mới có chỗ. */}
      {/* Luồng sáng viền khi hoàn tất tác vụ (#3) */}
      {flash && <span aria-hidden className="panel-flash pointer-events-none absolute inset-0 z-30" />}
      {/* Voice mode (mở rộng UC007) — nói → STT → gửi cho agent */}
      <VoiceMode open={voiceOpen} onClose={() => setVoiceOpen(false)} onResult={(t) => send(t, true)} />

      {/* Trang chọn gói — chiếm trọn khung hình */}
      <PricingScreen
        open={pricingOpen}
        onClose={() => setPricingOpen(false)}
        status={sub}
        onChanged={setSub}
      />
      
      {/* [HAUTE COUTURE] Khung tiêu đề Hollywood với thanh phân cách dập rãnh cơ khí 3D tách khối tuyệt đối */}
      {/* Khung tiêu đề: nền KÍNH SỌC (fluted glass).
          Kính sọc là tấm kính đúc thành nhiều gân bán trụ dọc; mỗi gân là một
          thấu kính trụ nên ảnh phía sau bị nén ngang và vỡ thành dải — thấy có
          gì đó ở sau nhưng không đọc được là gì. Đúng vai của một thanh tiêu đề:
          phải tách khỏi nội dung bên dưới, nhưng không được là một mảng đặc chặn
          hết mọi thứ. Bong bóng phía sau vẫn thấp thoáng qua các gân. */}
      {/* Thanh tiêu đề: ĐÈN NEON CHIẾU VÀO, không phải một bề mặt được trang trí.
          Ống đèn nằm ở mép trên, chùm sáng đổ xuống, và thứ nhìn thấy là chùm ấy
          chạm vào không khí trong khối. Khác hẳn kính sọc trước đó — sọc là hoa
          văn nên mắt luôn thấy nó và nó tranh chỗ với nội dung; ánh sáng thì
          không có hoa văn nào để nhìn, nó chỉ làm khối này sáng lên.

          CHỮ ĐÃ BỎ, thay bằng dấu hiệu thương hiệu. Dòng "Trợ lý MeoArc" không
          nói thêm được gì: người dùng vừa tự tay mở khung này, họ biết thừa nó
          là gì. Một chữ ở chỗ trang trọng nhất mà không mang thông tin thì chỉ
          là chỗ trống được lấp. Dấu hiệu thì nhận ra tức thì, không phải đọc, và
          nó chừa lại khoảng thở cho chùm sáng. */}
      <header data-cat-perch="bottom" className="den-neon relative z-20 shrink-0 overflow-hidden px-6 pb-5 pt-5">
        
        {/* THANH PHÂN CÁCH CƠ KHÍ 3D (RECESSED GROOVE): Tạo khe hở ánh sáng và bóng lún tách lớp */}
        <div className="absolute bottom-0 left-0 right-0 pointer-events-none z-10 flex flex-col">
          {/* Đường hairline trắng gắt giả lập ánh sáng khúc xạ qua khe cắt kính */}
          <div className="w-full h-[1px] bg-background/50 border-t border-white/[0.08]" />
          {/* Rãnh cắt tối dập chìm, hắt bóng xuống lòng khung chat bên dưới */}
          <div className="w-full h-[1px] bg-[#000000]/40 shadow-[0_1px_3px_rgba(0,0,0,0.4)]" />
        </div>

        {/* Lưới mảnh + vệt sáng: ngôn ngữ bảng điều khiển, thay cho dải sơn huy hiệu Pháp.
            Dải cũ (navy/trắng/đỏ + serif + "Maison de L'intellect") nói về thư quán thế kỷ 19,
            trong khi thứ đang chạy bên dưới là một agent. Hai câu chuyện chỏi nhau ngay trên
            cùng một màn hình, và người xem cảm nhận được dù không gọi tên ra được. */}
        {/* Lưới mảnh ĐÃ BỎ: gân kính đã lo phần "cấu trúc nền", chồng thêm một
            lưới nữa thì hai hoa văn đánh nhau. */}

        {/* BỐ CỤC NỘI DUNG: CHỮ HOLLYWOOD DI SẢN CĂN GIỮA TUYỆT ĐỐI */}
        <div className="relative flex items-center justify-between w-full z-10">
          {/* Logo mèo đã BỎ — linh hồn mèo giờ là WanderingCat chạy rong khắp app;
              giữ khối đệm trống cho tiêu đề căn giữa cân với nút bên phải */}
          <div className="size-9 shrink-0 ml-12" />

          {/* VIÊN KÍNH KHÚC XẠ — hẹp so với đoạn phim, và đó là điều kiện bắt buộc.
              Bản gốc ghi rõ một hiện tượng cố hữu của bộ lọc: khi khối kính rộng
              gần bằng nguồn, mép của nó rơi vào vùng mặt nạ 45px và lộ ra dải
              tách kênh màu gắt chạy dọc cạnh. Thanh tiêu đề tràn viền rơi đúng
              vào bẫy đó — đã thử và đúng là bị. Thu lại thành viên nổi hẹp thì
              mép ra khỏi vùng ấy, chỉ còn lại phần khúc xạ sạch.
              Tiện thể nó cũng đúng hơn về mặt hình: một tấm kính có bốn cạnh
              nhìn thấy được thì mới đọc ra là VẬT đặt lên trên đoạn phim; tràn
              viền thì chỉ đọc là một mảng nền. */}
          <KinhKhucXa
            videoRef={videoNenRef}
            co="nho"
            className="kkx pointer-events-none absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 select-none items-center justify-center overflow-hidden rounded-full border border-white/[0.16] p-3.5">
            {/* Dấu hiệu, không phải chữ. Phát sáng bằng drop-shadow theo đúng màu
                đèn đang rọi — cùng một nguồn sáng thì mọi vật trong khối phải
                nhận cùng một màu, nếu không khối mất tính nhất quán. */}
            <LogoMark className="relative size-6 text-foreground drop-shadow-[0_0_10px_var(--den)]" />
            <span className="sr-only">{t('chat.title')}</span>
          </KinhKhucXa>

          <div className="flex items-center gap-1 shrink-0 mr-12">
            <button
              onClick={() => setHistoryOpen((v) => !v)}
              title={t('mail.enableKeys')}
              className={cn(
                "o-icon size-9 bg-background/50 backdrop-blur-md transition-all duration-300 active:scale-90",
                historyOpen && "bg-foreground text-background border-transparent scale-95 rotate-90"
              )}
            >
              <Sparkles className="size-4" />
            </button>
            {onClose && (
              <button
                onClick={onClose}
                title={t('nav.closeToInbox')}
                aria-label={t('nav.closeAssistant')}
                className="o-icon size-9 bg-background/50 backdrop-blur-md transition-all duration-300 active:scale-90 [--tint:var(--destructive)]"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
        </div>

        {/* KHAY CHỨA NÚT CƠ KHÍ: Trượt lướt mượt mà khi được kích hoạt */}
        <div 
          className={cn(
            "relative z-10 flex items-center justify-center gap-4 w-full border-t border-foreground/[0.04] bg-foreground/[0.01] mt-4 pt-3 transition-all duration-500 ease-soft",
            historyOpen 
              ? "max-h-12 opacity-100 translate-y-0" 
              : "max-h-0 opacity-0 -translate-y-4 pointer-events-none overflow-hidden mt-0 pt-0 border-t-0"
          )}
        >
          <div className="den-vien goc-cat-nho goc-cat flex items-center gap-2 px-4 py-1 bg-background/60 backdrop-blur-md">
            <kbd className="hidden items-center gap-0.5 rounded-md border border-foreground/[0.08] bg-background px-1.5 py-0.5 text-[9px] font-mono font-medium text-muted-foreground/70 lg:flex">
              ⌘K
            </kbd>

            <button
              onClick={() => {
                setTtsOn((v) => {
                  if (v && 'speechSynthesis' in window) window.speechSynthesis.cancel()
                  setSpeaking(false)
                  return !v
                })
              }}
              title={t(ttsOn ? 'ch.ttsOff' : 'ch.ttsOn')}
              className={cn(
                'flex size-8 items-center justify-center rounded-lg transition-colors',
                ttsOn ? 'text-active bg-background shadow-sm' : 'text-muted-foreground hover:bg-background/40 hover:text-foreground',
                speaking && 'animate-pulse', // agent đang đọc → loa nhấp nháy thay mèo mấp máy
              )}
            >
              {ttsOn ? <Volume2 className="size-3.5" /> : <VolumeX className="size-3.5" />}
            </button>

            <button
              onClick={newChat}
              title={t('chat.new')}
              className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-background/40 hover:text-foreground"
            >
              <SquarePen className="size-3.5" />
            </button>
          </div>
        </div>
      </header>

      {/* ĐÃ GỠ dải sơn nhớt (navy/trắng ngà/đỏ mận) tan chảy tràn mép header.
          Nó là một mảng công phu và đẹp, nhưng nó kể sai chuyện: sơn chảy là ẩn dụ
          của chất lỏng, của thủ công, của thứ diễn ra chậm. Bên dưới nó là một
          agent đọc vài trăm lá thư trong vài giây. Hai câu chuyện chỏi nhau ngay
          trên cùng một màn hình.
          Thay bằng một VẠCH SÁNG mảnh có tán sắc — cùng vai trò phân cách, nhưng
          nói bằng ngôn ngữ ánh sáng. */}
      <div aria-hidden className="relative z-10 h-px shrink-0">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[var(--spark)] to-transparent opacity-80" />
        <div className="absolute inset-x-0 top-0 h-px translate-y-[0.5px] bg-gradient-to-r from-transparent via-[#F042FF] to-transparent opacity-40 blur-[1.5px]" />
      </div>

      {/* Canvas hội thoại */}
      <div
        ref={scrollRef}
        className="scrollbar-thin fade-y relative z-[1] flex-1 space-y-5 overflow-y-auto px-6 py-6"
      >
        {messages.map((m) => {
          return (
            <div key={m.id} className="msg-pop">
              {m.role === 'user' ? (
                <UserBubble>{m.text}</UserBubble>
              ) : (
                <AgentMessage
                  message={m}
                  hopThu={emails}
                  exec={exec}
                  executed={executedIds.has(m.id)}
                  spotlight={pendingConfirmId === m.id}
                  onApprove={approvePlan}
                  onReject={rejectPlan}
                  onSendDraft={sendDraft}
                  onRewrite={rewriteDraft}
                  onResolve={markResolved}
                  onApplyCategorize={applyCategorize}
                  onAutopilotApply={applyAutopilot}
                  onOpenEmail={onOpenEmail}
                  onTraLoiThu={traLoiThu}
                  onDanhDauDaDoc={(id) => actions.markRead([id], true)}
                  duyetDuDinhId={dangDuyetId}
                  onDuyetDuDinh={onDuyetDuDinh}
                  onBoQuaDuDinh={onBoQuaDuDinh}
                />
              )}
            </div>
          )
        })}
        {thinking && (
          <div className="duration-300 animate-in fade-in slide-in-from-bottom-2">
            <ThinkingDots />
          </div>
        )}
      </div>

      {/* Khu nhập liệu — .roof-ledge = dải phân cách "mặt hồ" (WaterDivider) nơi giọt
          sơn đáp xuống; mèo lang thang đậu được (data-cat-perch). THU GỌN được:
          mặc định là 1 nút, bấm mới bung; bấm ra ngoài (ô rỗng) tự co → chừa chỗ chat.
          composer co/giãn thì --roof-y tự đo lại (ResizeObserver) → mặt hồ + giọt vẫn khớp. */}
      <div
        ref={composerRef}
        data-cat-perch="top"
        className="roof-ledge relative px-6 py-4"
      >
        {/* ĐÃ GỠ mặt hồ gợn sóng champagne. Sóng nước là đường cong hữu cơ, mềm —
            đúng thứ khiến cả panel đọc ra là "mặt phẳng mượt". Thay bằng một
            đường chân trời phát sáng: cùng nhiệm vụ ngăn khung chat với ô nhập,
            nhưng là một CẠNH sắc, thứ mà ánh sáng bám được vào. */}
        <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0">
          <div className="h-px w-full bg-gradient-to-r from-transparent via-[var(--active)] to-transparent" />
          <div className="h-px w-full -translate-y-px bg-gradient-to-r from-transparent via-[var(--spark)] to-transparent opacity-70 blur-[2px]" />
          {/* Quầng hắt lên từ đường kẻ — cho biết nó phát sáng chứ không phải một nét vẽ */}
          <div className="h-10 w-full bg-[radial-gradient(60%_100%_at_50%_0%,color-mix(in_srgb,var(--active)_22%,transparent),transparent_72%)]" />
        </div>

        {/* Cạn hạn mức → nói rõ lý do trợ lý ngừng trả lời + lối nâng cấp */}
        <QuotaBanner status={sub} onUpgrade={() => setPricingOpen(true)} />

        {/* Kỹ năng AI — LUÔN hiện (không thu gọn) */}
        <div className="mb-2 flex flex-wrap gap-2">
          {dsSkills().map((s) => (
            <button
              key={s.label}
              onClick={() => send(s.prompt)}
              className="flex items-center gap-1.5 rounded-full bg-active/20 px-3 py-1.5 text-xs font-medium text-foreground shadow-subtle transition-all duration-200 ease-spring hover:-translate-y-0.5 active:scale-95"
            >
              <Sparkles className="size-3.5 text-active" />
              {s.label}
            </button>
          ))}
        </div>
        {/* BƯỚC TIẾP THEO — suy từ thể loại câu trả lời vừa rồi, 0 lượt gọi model.
            Đặt TRƯỚC nhóm gợi ý theo hộp thư vì nó bám sát thứ người dùng vừa xem,
            nên khả năng bấm cao hơn hẳn. */}
        {buocTiepTheo.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {buocTiepTheo.map((g) => (
              <button
                key={g.nhan}
                onClick={() => send(g.lenh)}
                className="flex items-center gap-1.5 rounded-full border border-[var(--spark)]/35 bg-[var(--spark)]/10 px-3 py-1.5 text-xs font-medium text-foreground shadow-subtle transition-all duration-200 ease-spring hover:-translate-y-0.5 active:scale-95"
              >
                <ArrowUpRight className="size-3.5 text-[var(--spark)]" />
                {g.nhan}
              </button>
            ))}
          </div>
        )}
        {/* Gợi ý theo ngữ cảnh — LUÔN hiện */}
        <div className="mb-3 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s.nhan}
              onClick={() => send(s.lenh)}
              className="rounded-full px-3.5 py-1.5 text-xs text-foreground/80 shadow-subtle transition-all duration-200 ease-spring glass hover:-translate-y-0.5 hover:text-foreground active:scale-95"
            >
              {s.nhan}
            </button>
          ))}
        </div>

        {/* CHỈ Ô NHẬP LIỆU thu gọn: mặc định là 1 nút, bấm mới bung; bấm ra ngoài
            (ô rỗng) tự co lại → chừa chỗ cho khung chat. Tag phía trên GIỮ NGUYÊN. */}
        {composerOpen ? (
          <div className="duration-200 animate-in fade-in slide-in-from-bottom-1">
            {/* CHIP BỐI CẢNH — "đang nói về việc này". Cố ý KHÔNG tự gửi câu hỏi nào:
                bấm vào một việc rồi hỏi chuyện khác (vé máy bay đi dự sự kiện đó) là
                trường hợp thường gặp, mà câu hỏi dựng sẵn thì bị vứt đi cùng với lượt
                gọi model đã trả tiền. Ở đây chỉ ghim ngữ cảnh rồi CHỜ người dùng gõ. */}
            {/* TỆP ĐÃ ĐÍNH — hiện ra để người dùng thấy mình sắp gửi gì. Đính kèm mà
                không thấy gì đổi trên màn hình thì không ai dám bấm gửi. */}
            {tepDinhKem.length > 0 && (
              <div className="mb-1.5 flex flex-wrap gap-1.5">
                {tepDinhKem.map((tep) => (
                  <span key={tep.id}
                        className="flex items-center gap-1.5 rounded-lg border border-border/50 bg-background/60 px-2 py-1 text-[11.5px]">
                    <Paperclip className="size-3 shrink-0 text-muted-foreground" />
                    <span className="max-w-[160px] truncate">{tep.name}</span>
                    <button
                      onClick={() => setTepDinhKem((v) => v.filter((x) => x.id !== tep.id))}
                      aria-label={t('ch.removeCtx', { ten: tep.name })}
                      className="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
                    >
                      <X className="size-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            {boiCanh && (
              <div className="mb-1.5 flex items-center gap-2 rounded-xl border border-[var(--spark)]/30 bg-[var(--spark)]/10 px-3 py-1.5">
                <CalendarClock className="size-3.5 shrink-0 text-[var(--spark)]" />
                <span className="min-w-0 flex-1 truncate text-[12px]">
                  <span className="text-muted-foreground">{t('st.askingAbout')} </span>
                  <span className="font-medium">{boiCanh.tieuDe}</span>
                </span>
                <button
                  onClick={onBoBoiCanh}
                  aria-label={t('chat.clearCtx')}
                  className="shrink-0 rounded-md p-0.5 text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            )}
            <div className="flex items-end gap-2 rounded-2xl p-2.5 shadow-soft transition-shadow glass focus-within:shadow-float focus-within:ring-2 focus-within:ring-ring/40">
              <input
                ref={oChonTep}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => void chonTep(e.target.files)}
              />
              <button
                onClick={() => oChonTep.current?.click()}
                disabled={dangTaiTep}
                title={t('chat.attachHint')}
                aria-label={t('act.attach')}
                className="flex size-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
              >
                {dangTaiTep ? <Loader2 className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
              </button>
              <button
                onClick={() => setVoiceOpen(true)}
                title={t('voice.speak')}
                aria-label={t('voice.on')}
                className="flex size-9 items-center justify-center rounded-xl text-muted-foreground transition-colors ease-spring hover:bg-secondary hover:text-foreground active:scale-90"
              >
                <Mic className="size-4" />
              </button>
              <Textarea
                id="meoarc-composer-input"
                rows={1}
                ref={oNhap}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    send(input)
                  } else if (e.key === 'Escape' && !input.trim()) {
                    setComposerOpen(false)
                  }
                }}
                placeholder={
                  isOutOfTokens(sub)
                    ? t('ch.outOfTokens')
                    : t('ch.phExample')
                }
                disabled={isOutOfTokens(sub)}
                className="max-h-56 min-h-0 flex-1 resize-none overflow-y-auto border-0 bg-transparent py-1.5 shadow-none focus-visible:ring-0 disabled:opacity-60"
              />
              {/* Đồng hồ token — luôn nằm cạnh ô nhập như các trợ lý AI khác */}
              <TokenMeter status={sub} onUpgrade={() => setPricingOpen(true)} />
              <Button
                size="icon"
                variant="primary"
                className="rounded-xl"
                disabled={isOutOfTokens(sub)}
                onClick={() => send(input)}
              >
                <Send className="size-4" />
              </Button>
            </div>
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              Mọi hành động không thể hoàn tác đều cần bạn xác nhận trước.
            </p>
          </div>
        ) : (
          /* Ô nhập THU GỌN — pill mời gõ, bấm là bung ô nhập đầy đủ */
          <button
            onClick={() => setComposerOpen(true)}
            className="gloss gloss-sweep flex w-full items-center gap-3 rounded-2xl px-3.5 py-2.5 text-left shadow-soft transition-all duration-200 ease-spring glass hover:-translate-y-0.5 hover:shadow-float active:scale-[0.99]"
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-emphasis text-emphasis-foreground shadow-subtle">
              <Sparkles className="size-4" />
            </span>
            <span className="flex-1 truncate text-sm text-muted-foreground">{t('chat.placeholder')}</span>
            <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <Send className="size-4" />
            </span>
          </button>
        )}
      </div>

      {/* Lịch sử trò chuyện (UC011) — drawer trượt từ phải */}
      <div
        aria-hidden
        onClick={() => setHistoryOpen(false)}
        className={cn(
          'fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity duration-300',
          historyOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
      />
      <div
        role="dialog"
        aria-label={t('nav.history')}
        aria-modal={historyOpen || undefined}
        aria-hidden={!historyOpen}
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex w-[min(360px,92vw)] flex-col border-l border-accent/30 bg-popover text-popover-foreground shadow-float transition-transform duration-300 ease-out',
          historyOpen ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        <div className="flex items-center gap-3 border-b border-border/40 px-5 py-4">
          <span className="bokeh flex size-9 shrink-0 items-center justify-center rounded-xl bg-emphasis text-emphasis-foreground shadow-subtle">
            <History className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="font-serif text-base font-semibold text-popover-foreground">
              Lịch sử trò chuyện
            </h3>
            <p className="truncate text-xs text-popover-foreground/55">
              {sessions.length} cuộc trò chuyện đã lưu
            </p>
          </div>
          <button
            onClick={() => setHistoryOpen(false)}
            title={t('act.close')}
            aria-label={t('act.close')}
            className="flex size-8 shrink-0 items-center justify-center rounded-lg text-popover-foreground/60 transition-colors hover:bg-popover-foreground/10 hover:text-popover-foreground active:scale-95"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-2.5 px-5 py-3">
          <button
            onClick={() => {
              newChat()
              setHistoryOpen(false)
            }}
            className="gloss gloss-sweep flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-float active:scale-[0.98]"
          >
            <SquarePen className="size-4" />
            Cuộc trò chuyện mới
          </button>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-popover-foreground/45" />
            <input
              value={historyQuery}
              onChange={(e) => setHistoryQuery(e.target.value)}
              placeholder={t('chat.searchHistory')}
              className="w-full rounded-xl border border-border/40 bg-popover-foreground/5 py-2 pl-9 pr-3 text-sm text-popover-foreground outline-none transition-shadow placeholder:text-popover-foreground/40 focus-visible:ring-2 focus-visible:ring-ring/40"
            />
          </div>
        </div>

        <div className="scrollbar-thin flex-1 overflow-y-auto px-3 pb-4">
          {historyGroups.length === 0 ? (
            <div className="mt-14 flex flex-col items-center gap-3 px-6 text-center">
              <span className="bokeh flex size-16 items-center justify-center">
                <MeoMascot className="size-14" />
              </span>
              <p className="text-sm font-medium text-popover-foreground/80">
                Không có cuộc trò chuyện nào khớp
              </p>
              <p className="text-xs text-popover-foreground/50">{t('st.tryOtherKeyword')}</p>
            </div>
          ) : (
            historyGroups.map((g) => (
              <div key={g.label} className="mb-1">
                <p className="px-2 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-popover-foreground/40">
                  {g.label}
                </p>
                <div className="space-y-1">
                  {g.items.map((s) => {
                    const active = s.id === currentId
                    const renaming = renamingId === s.id

                    if (deletingId === s.id) {
                      return (
                        <div
                          key={s.id}
                          className="rounded-xl bg-destructive/10 px-3 py-2.5 ring-1 ring-destructive/30"
                        >
                          <p className="text-xs text-popover-foreground/80">
                            Xoá phiên “{s.title}”? Không thể hoàn tác.
                          </p>
                          <div className="mt-2 flex justify-end gap-1.5">
                            <button
                              onClick={() => setDeletingId(null)}
                              className="rounded-lg px-2.5 py-1 text-xs text-popover-foreground/70 transition-colors hover:bg-popover-foreground/10"
                            >
                              Huỷ
                            </button>
                            <button
                              onClick={() => deleteSession(s.id)}
                              className="flex items-center gap-1 rounded-lg bg-destructive px-2.5 py-1 text-xs font-semibold text-destructive-foreground transition-transform active:scale-95"
                            >
                              <Trash2 className="size-3.5" />
                              Xoá
                            </button>
                          </div>
                        </div>
                      )
                    }

                    return (
                      <div
                        key={s.id}
                        className={cn(
                          'group relative flex items-start gap-3 overflow-hidden rounded-xl py-2.5 pl-4 pr-3 transition-colors',
                          active ? 'bg-popover-foreground/10' : 'hover:bg-popover-foreground/[0.06]',
                        )}
                      >
                        {active && (
                          <span className="absolute inset-y-1.5 left-0 w-1 rounded-r-full bg-active" />
                        )}
                        <span className="mt-1 flex size-2 shrink-0 items-center justify-center">
                          {s.pinned ? (
                            <Pin className="size-3 text-active" />
                          ) : (
                            <span
                              className={cn(
                                'block size-2 rounded-full',
                                active ? 'cherry-dot' : 'bg-popover-foreground/25',
                              )}
                            />
                          )}
                        </span>

                        <div className="min-w-0 flex-1">
                          {renaming ? (
                            <input
                              autoFocus
                              value={renameValue}
                              maxLength={RENAME_MAX}
                              onChange={(e) => setRenameValue(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault()
                                  commitRename()
                                } else if (e.key === 'Escape') {
                                  setRenamingId(null)
                                }
                              }}
                              onBlur={commitRename}
                              className="w-full rounded-md border border-border/50 bg-popover-foreground/5 px-2 py-1 text-sm text-popover-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                            />
                          ) : (
                            <button
                              onClick={() => openSession(s)}
                              className="block w-full text-left"
                            >
                              <span className="flex items-center gap-2">
                                <span className="min-w-0 flex-1 truncate text-sm font-medium text-popover-foreground">
                                  {s.title}
                                </span>
                                <span className="shrink-0 text-[11px] text-popover-foreground/45 transition-opacity group-hover:opacity-0">
                                  {s.time}
                                </span>
                              </span>
                              <span className="mt-0.5 block truncate text-xs text-popover-foreground/55">
                                {previewOf(s)}
                              </span>
                            </button>
                          )}
                        </div>

                        {!renaming && (
                          <div className="absolute right-2 top-1.5 hidden items-center gap-0.5 rounded-lg bg-popover/90 px-0.5 shadow-subtle backdrop-blur-sm group-hover:flex">
                            <HistAction
                              icon={s.pinned ? PinOff : Pin}
                              title={s.pinned ? t('ch.unpin') : 'Ghim'}
                              onClick={() => togglePin(s.id)}
                            />
                            <HistAction icon={Pencil} title={t('act.rename')} onClick={() => startRename(s)} />
                            <HistAction
                              icon={Trash2}
                              title={t('act.delete')}
                              danger
                              onClick={() => setDeletingId(s.id)}
                            />
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </aside>
  )
}

// MOCK viết lại (chỉ dùng khi CHƯA nối backend). Nguyên tắc: GIỮ nội dung/chủ đề gốc,
// chỉ khoác văn phong theo yêu cầu — KHÔNG trả email mẫu cứng lạc đề. Bản thật do agent viết lại.
function rewriteVariant(base: string, instr: string): string {
  const body = base.trim()
  const i = normalize(instr)
  if (/(trang trong|formal|lich su)/.test(i))
    return `Kính gửi anh/chị,\n\n${body}\n\nEm xin chân thành cảm ơn.\nTrân trọng.`
  if (/(than thien|friendly|gan gui)/.test(i))
    return `Chào anh/chị,\n\n${body}\n\nCảm ơn anh/chị nhiều nhé!`
  if (/(ngan|short|gon|suc tich)/.test(i)) {
    const lines = body.split(/\n+/).map((s) => s.trim()).filter(Boolean)
    return lines.slice(0, 2).join('\n\n')
  }
  return instr ? `${body}\n\n(Đã điều chỉnh theo: “${instr}”.)` : `${body}\n\n(Đã viết lại.)`
}

function DraftCard({
  reply,
  resolved,
  spotCls,
  id,
  onSendDraft,
  onRewrite,
  onResolve,
}: {
  reply: Extract<AgentReply, { kind: 'draft' }>
  resolved?: boolean
  spotCls: string
  id: string
  onSendDraft: (
    id: string,
    draft: { to: string; subject: string; body: string; replyToId?: string; confirmationId?: string },
  ) => Promise<boolean>
  onRewrite?: (draft: { to: string; subject: string; body: string; replyToId?: string }, instruction: string) => void
  onResolve: (id: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [rwOpen, setRwOpen] = useState(false)
  const [rwText, setRwText] = useState('')
  const [rewriting, setRewriting] = useState(false)
  const [to, setTo] = useState(reply.to)
  const [subject, setSubject] = useState(reply.subject)
  const [body, setBody] = useState(reply.body)
  const [done, setDone] = useState<null | 'sent' | 'cancelled'>(null)
  const [sendingNow, setSendingNow] = useState(false) // đang gọi API gửi thật

  const fieldCls =
    'w-full rounded-lg border border-border/50 bg-popover-foreground/5 px-2.5 py-1.5 text-sm text-popover-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/40'

  const doRewrite = () => {
    const instr = rwText.trim()
    setRwOpen(false)
    // Backend thật: nhờ AGENT viết lại đúng bản nháp này (giữ chủ đề + người nhận).
    // Mock/demo (chưa nối backend): biến thể cục bộ GIỮ nội dung gốc, không lạc đề.
    if (apiBaseUrlDaCauHinh && onRewrite) {
      onRewrite({ to, subject, body, replyToId: reply.replyToId }, instr)
      setRwText('')
      return
    }
    setRewriting(true)
    window.setTimeout(() => {
      setBody((b) => rewriteVariant(b, instr))
      setRwText('')
      setRewriting(false)
    }, 650)
  }

  if (done || resolved) {
    return (
      <Card className="rose-glass shadow-float overflow-hidden relative">
        {done === 'sent' && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2 flex size-12 items-center justify-center rounded-full bg-active text-active-foreground font-serif font-bold text-lg border-2 border-accent/40 shadow-md rotate-[-12deg] opacity-85 animate-in fade-in zoom-in duration-500">
            M
            <div className="absolute inset-0.5 rounded-full border border-dashed border-active-foreground/30" />
          </div>
        )}
        <CardHeader>
          <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Mail className="size-4 text-primary" />
            Bản nháp trả lời
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-2 pr-20">
          <span className="text-xs font-serif font-semibold uppercase tracking-wider text-foreground/80">
            {done === 'cancelled' ? t('ch.mailCancelled') : t('ch.mailSealed')}
          </span>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn('rose-glass shadow-float transition-all overflow-hidden', spotCls)}>
      <CardHeader>
        <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Mail className="size-4 text-primary" />
          {t(editing ? 'ch.editDraft' : 'ch.replyDraft')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5 pt-2 text-sm">
        {editing ? (
          <div className="space-y-1.5">
            <input className={fieldCls} value={to} onChange={(e) => setTo(e.target.value)} />
            <input
              className={fieldCls}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
            <textarea
              className={cn(fieldCls, 'min-h-28 resize-none font-serif leading-relaxed bg-elevated text-foreground shadow-inner')}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
        ) : (
          <>
            <p className="text-muted-foreground text-xs">
              <span className="text-foreground font-medium">{t('mail.toLabel')}</span> {to}
            </p>
            <p className="text-muted-foreground text-xs">
              <span className="text-foreground font-medium">{t('mail.subjectLabel')}</span> {subject}
            </p>
            {rewriting ? (
              <div className="mt-2 space-y-2 rounded-xl bg-popover px-3.5 py-3 shadow-subtle">
                <div className="skeleton h-3 w-3/4 rounded" />
                <div className="skeleton h-3 w-full rounded" />
                <div className="skeleton h-3 w-2/3 rounded" />
              </div>
            ) : (
              /* Bản nháp thư. Trước đây khối này là NỀN KEM #f7ebd9 + MỰC NÂU
                 #3e1717 + viền ngà — tức là giả một tờ giấy da. Đây là thứ "cổ
                 điển" lộ liễu nhất trong toàn ứng dụng, lại nằm đúng chỗ người
                 dùng nhìn lâu nhất: lúc đọc lại thư trước khi bấm gửi.

                 Hai màu đó còn được ghi cứng nên ở theme tối chúng đứng im —
                 một mảng kem chói giữa nền gần đen.

                 Giờ là một khối kính có viền phát sáng, chữ dùng token nên theo
                 theme. Vẫn tách khỏi nền để biết "đây là nội dung thư", nhưng
                 tách bằng ÁNH SÁNG chứ không bằng cách giả vật liệu giấy. */
              <div className="neon-edge mt-2 whitespace-pre-line rounded-xl bg-elevated/70 px-4 py-3.5 text-[14px] leading-relaxed text-foreground backdrop-blur-sm"
                style={{ ['--tint' as string]: 'var(--spark)' }}>
                {body}
              </div>
            )}
            {/* TỆP ĐÍNH KÈM trên thẻ duyệt. Cổng xác nhận chỉ có nghĩa khi người dùng
                thấy ĐÚNG thứ sắp đi ra ngoài — duyệt một lá thư mà không biết nó kèm
                tệp gì thì cái nút duyệt đó không bảo vệ được gì cả. */}
            {reply.attachments && reply.attachments.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(reply.attachments ?? []).map((ten) => (
                  <span key={ten}
                        className="flex items-center gap-1.5 rounded-lg border border-[var(--spark)]/35 bg-[var(--spark)]/10 px-2 py-1 text-[11.5px]">
                    <Paperclip className="size-3 shrink-0 text-[var(--spark)]" />
                    <span className="max-w-[180px] truncate">{ten}</span>
                  </span>
                ))}
              </div>
            )}
          </>
        )}

        {rwOpen && (
          <div className="flex items-center gap-1.5 pt-1">
            <input
              autoFocus
              value={rwText}
              onChange={(e) => setRwText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doRewrite()}
              placeholder={t('chat.rewriteHint')}
              className={fieldCls}
            />
            <Button size="sm" variant="accent" onClick={doRewrite}>
              Tạo lại
            </Button>
          </div>
        )}
      </CardContent>
      <CardFooter className="flex-wrap gap-2 border-t border-border/10 pt-3 mt-2">
        <Button
          variant="primary"
          size="sm"
          disabled={rewriting || sendingNow}
          onClick={async () => {
            // GỬI THẬT rồi mới đóng thẻ — thất bại thì giữ thẻ cho user sửa/gửi lại
            setSendingNow(true)
            const ok = await onSendDraft(id, { to, subject, body, replyToId: reply.replyToId, confirmationId: reply.confirmationId })
            setSendingNow(false)
            if (ok) setDone('sent')
          }}
          className="relative overflow-hidden group/btn"
        >
          {sendingNow ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Đang gửi…
            </>
          ) : (
            <>
              <Send className="size-4 transition-transform group-hover/btn:translate-x-0.5 group-hover/btn:-translate-y-0.5" />
              Niêm phong &amp; Gửi
            </>
          )}
        </Button>
        <Button variant="outline" size="sm" onClick={() => setEditing((v) => !v)}>
          <Pencil className="size-4" />
          {editing ? 'Xong' : 'Chỉnh sửa'}
        </Button>
        <Button variant="outline" size="sm" disabled={rewriting} onClick={() => setRwOpen((v) => !v)}>
          <Sparkles className="size-4" />
          Viết lại
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setDone('cancelled')
            onResolve(id)
          }}
        >
          Huỷ
        </Button>
      </CardFooter>
    </Card>
  )
}

function CategorizeWidget({
  reply,
  resolved,
  spotCls,
  id,
  onApply,
  onReject,
}: {
  reply: Extract<AgentReply, { kind: 'categorize' }>
  resolved?: boolean
  spotCls: string
  id: string
  onApply: (id: string, items: { id: string; category: Category; label: string }[]) => void
  onReject: (id: string) => void
}) {
  const [rows, setRows] = useState((reply.items ?? []).map((it) => ({ ...it })))
  const [excluded, setExcluded] = useState<Set<string>>(new Set())

  const cycleLabel = (rid: string) =>
    setRows((prev) =>
      prev.map((r) => {
        if (r.id !== rid) return r
        const idx = CATEGORY_OPTIONS.findIndex((o) => o.key === r.category)
        const next = CATEGORY_OPTIONS[(idx + 1) % CATEGORY_OPTIONS.length]
        return { ...r, category: next.key, label: next.label }
      }),
    )
  const toggle = (rid: string) =>
    setExcluded((prev) => {
      const n = new Set(prev)
      if (n.has(rid)) n.delete(rid)
      else n.add(rid)
      return n
    })

  const included = rows.filter((r) => !excluded.has(r.id))

  return (
    <Card className={cn('overflow-hidden rose-glass shadow-float transition-all', spotCls)}>
      <CardHeader>
        <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <ListChecks className="size-4 text-primary" />
          {reply.title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5 pt-2">
        {rows.map((r) => {
          const c = CATEGORY[r.category]
          const off = excluded.has(r.id)
          return (
            <div
              key={r.id}
              className={cn(
                'flex items-center gap-2.5 rounded-xl bg-popover-foreground/5 p-2 transition-opacity',
                off && 'opacity-45',
              )}
            >
              <button
                onClick={() => toggle(r.id)}
                title={t(off ? 'ch.includeAgain' : 'ch.skipThis')}
                className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-popover-foreground/10 active:scale-90"
              >
                {off ? <Square className="size-4" /> : <CheckSquare className="size-4 text-success" />}
              </button>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{r.sender}</p>
                <p className="truncate text-xs text-muted-foreground">{r.subject}</p>
              </div>
              <button
                onClick={() => cycleLabel(r.id)}
                disabled={resolved || off}
                title={t('mail.tapChangeLabel')}
                className="flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold text-[#1b1b2c] dark:text-[#E6E8F5] ring-1 ring-inset transition-transform active:scale-95 disabled:opacity-60"
                style={
                  {
                    // Pha màu nhãn với nền của theme hiện tại để chip không bị đục
                    backgroundColor: `color-mix(in srgb, ${c.bar} 70%, var(--background))`,
                    ['--tw-ring-color']: c.bar, // Viền đặc màu nhãn không loãng
                  } as CSSProperties
                }
              >
                <span className="size-1.5 rounded-full" style={{ backgroundColor: c.bar }} />
                {r.label}
              </button>
            </div>
          )
        })}
      </CardContent>
      <CardFooter>
        {resolved ? (
          <span className="text-xs font-medium text-muted-foreground">{t('st.handled')}</span>
        ) : (
          <>
            <Button
              variant="primary"
              size="sm"
              disabled={included.length === 0}
              onClick={() =>
                onApply(
                  id,
                  included.map((r) => ({ id: r.id, category: r.category, label: r.label })),
                )
              }
            >
              <Check className="size-4" />
              Áp dụng ({included.length})
            </Button>
            <Button variant="outline" size="sm" onClick={() => onReject(id)}>
              <X className="size-4" />
              Từ chối
            </Button>
          </>
        )}
      </CardFooter>
    </Card>
  )
}

/* ---------- Render 1 phản hồi agent ---------- */

function AgentMessage({
  message,
  hopThu,
  exec,
  executed,
  spotlight,
  onApprove,
  onReject,
  onSendDraft,
  onRewrite,
  onResolve,
  onApplyCategorize,
  onAutopilotApply,
  onOpenEmail,
  onTraLoiThu,
  onDanhDauDaDoc,
  duyetDuDinhId,
  onDuyetDuDinh,
  onBoQuaDuDinh,
}: {
  message: Extract<Message, { role: 'agent' }>
  /** Hộp thư đang mở — để dựng lại danh sách thư khi backend không đính kèm được. */
  hopThu: Email[]
  exec: { id: string; current: number } | null
  executed: boolean
  spotlight: boolean
  onApprove: (id: string, op: PlanOp, stepCount: number) => void
  onReject: (id: string) => void
  onSendDraft: (
    id: string,
    draft: { to: string; subject: string; body: string; replyToId?: string; confirmationId?: string },
  ) => Promise<boolean>
  onRewrite: (draft: { to: string; subject: string; body: string; replyToId?: string }, instruction: string) => void
  onResolve: (id: string) => void
  onApplyCategorize: (id: string, items: { id: string; category: Category; label: string }[]) => void
  /** Soạn trả lời cho một lá thư ngay từ trong thẻ. Người dùng đọc "tôi đang nợ ai"
   *  xong thì việc kế tiếp LUÔN là trả lời — bắt họ đi tìm lại lá thư đó trong hộp
   *  thư là chèn thêm một đoạn đường không cần thiết. */
  onTraLoiThu?: (emailId: string, tieuDe: string) => void
  /** Tick "đã xử lý" ở bảng phân loại → đánh dấu ĐÃ ĐỌC thật trên hộp thư.
   *  Trước đây ô tick chỉ làm mờ dòng rồi mất khi đóng chat: người dùng tick xong
   *  không biết mình vừa làm gì, và lần sau mở lại thấy y như cũ. Một nút không để
   *  lại dấu vết nào thì tệ hơn không có nút. */
  onDanhDauDaDoc?: (emailId: string) => void
  onAutopilotApply: (id: string, result: AutopilotResult) => void
  onOpenEmail?: (id: string) => void
  /* THẺ DỰ ĐỊNH. Ba prop này TỪNG THIẾU: `AgentMessage` gọi thẳng `dangDuyetId`,
     `onDuyetDuDinh`, `onBoQuaDuDinh` — vốn là biến trong component CHA. Thẻ dự định
     chưa bao giờ được render thật (chỉ là mockup) nên không ai vấp; vừa render lần
     đầu là ReferenceError làm TRẮNG CẢ APP.
     TypeScript CÓ bắt được (5 lỗi), nhưng chúng bị che bởi bộ nhớ đệm
     `node_modules/.tmp/tsconfig.app.tsbuildinfo` — tsc coi file không đổi nên dùng
     lại kết quả cũ. Xoá cache là lộ ra ngay. */
  duyetDuDinhId: string | null
  onDuyetDuDinh: (id: string, reply: Extract<AgentReply, { kind: 'dudinh' }>) => void
  onBoQuaDuDinh: (id: string) => void
}) {
  const { reply, resolved } = message
  const running = exec?.id === message.id
  const spotCls = spotlight ? 'ring-2 ring-spark/50 shadow-float' : ''

  /* ── THƯ NÀO SẼ BỊ ĐỤNG TỚI — CHỌN SẴN HẾT, BỎ TICK ĐƯỢC ──────────────────
     `null` = người dùng chưa đụng vào, tức đang chọn HẾT. Giữ `null` thay vì
     dựng sẵn một Set từ props để không phải đồng bộ state với props mỗi lần thẻ
     vẽ lại — đồng bộ kiểu đó là chỗ lệch âm thầm quen thuộc.

     Hook phải nằm ở ĐẦU component: bên dưới toàn `if (reply.kind === …) return`,
     đặt hook trong nhánh là vi phạm quy tắc hook và React sẽ vỡ khi loại thẻ đổi. */
  const [boChon, setBoChon] = useState<Set<string> | null>(null)

  if (reply.kind === 'text') {
    return (
      <AgentRow>
        <AgentText>{reply.text}</AgentText>
        {reply.emails && reply.emails.length > 0 && (
          <EmailRefList emails={reply.emails} onOpen={onOpenEmail} />
        )}
      </AgentRow>
    )
  }

  if (reply.kind === 'done') {
    return (
      <AgentRow>
        <div className="ripe-pulse flex items-center gap-2.5 rounded-2xl rounded-tl-md px-4 py-3 text-sm font-medium text-foreground shadow-soft edge-light glass">
          <CheckCircle2 className="size-5 shrink-0 text-success" />
          {reply.text}
        </div>
      </AgentRow>
    )
  }

  if (reply.kind === 'result') {
    return (
      <AgentRow>
        <AgentText>{reply.intro}</AgentText>
        <Card className="rose-glass shadow-float">
          <CardHeader>
            <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <FileText className="size-4 text-primary" />
              {reply.title}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-2">
            {reply.emails && reply.emails.length > 0 ? (
              <EmailRefList emails={reply.emails} onOpen={onOpenEmail} />
            ) : (
              <div className="space-y-2">
                {(reply.lines ?? []).map((l, i) => (
                  <div key={i} className="flex min-w-0 gap-2 text-sm text-foreground">
                    <span className="text-muted-foreground">•</span>
                    <span className="min-w-0 break-words">{l}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </AgentRow>
    )
  }

  if (reply.kind === 'dilai') {
    return (
      <AgentRow>
        {reply.intro && <AgentText>{reply.intro}</AgentText>}
        <DiLaiWidget reply={reply} />
      </AgentRow>
    )
  }

  if (reply.kind === 'brief') {
    return (
      <AgentRow>
        <AgentText>{reply.intro}</AgentText>
        <BriefWidget reply={reply} />
      </AgentRow>
    )
  }

  if (reply.kind === 'triage') {
    return (
      <AgentRow>
        <AgentText>{reply.intro}</AgentText>
        <TriageWidget reply={reply} onOpenEmail={onOpenEmail} onDaXuLy={onDanhDauDaDoc} />
      </AgentRow>
    )
  }

  if (reply.kind === 'digest') {
    return (
      <AgentRow>
        <AgentText>{reply.intro}</AgentText>
        <DigestWidget reply={reply} onOpenEmail={onOpenEmail} />
      </AgentRow>
    )
  }

  if (reply.kind === 'lichtrinh') {
    return (
      <AgentRow>
        <AgentText>{reply.intro}</AgentText>
        <LichTrinhWidget reply={reply} onOpenEmail={onOpenEmail} onTraLoiThu={onTraLoiThu} />
      </AgentRow>
    )
  }

  if (reply.kind === 'categorize') {
    return (
      <AgentRow>
        <AgentText>{reply.intro}</AgentText>
        <CategorizeWidget
          reply={reply}
          resolved={resolved}
          spotCls={spotCls}
          id={message.id}
          onApply={onApplyCategorize}
          onReject={onReject}
        />
      </AgentRow>
    )
  }

  if (reply.kind === 'dudinh') {
    return (
      <AgentRow>
        <AgentText>{reply.intro}</AgentText>
        <TheDuDinh
          reply={reply}
          resolved={resolved}
          dangChay={duyetDuDinhId === message.id}
          onDuyet={() => onDuyetDuDinh(message.id, reply)}
          onBoQua={() => onBoQuaDuDinh(message.id)}
        />
      </AgentRow>
    )
  }

  if (reply.kind === 'autopilot') {
    return (
      <AgentRow>
        <AgentText>{reply.intro}</AgentText>
        <AutopilotWidget
          reply={reply}
          resolved={resolved}
          id={message.id}
          onApply={onAutopilotApply}
        />
      </AgentRow>
    )
  }

  if (reply.kind === 'plan') {
    /* ── DANH SÁCH THƯ: BACKEND ĐÍNH KÈM, THIẾU THÌ TỰ TRA ────────────────────
       Backend chỉ rút được danh sách từ kết quả của vài tool. Câu "xoá các thư ưu
       đãi, mua sắm" đi qua `categorize_emails`, và trước khi sửa thì thẻ hiện ra
       trống trơn: "Xoá 2 thư" mà không nói hai thư nào — tức là vẫn bắt duyệt mù,
       đúng thứ cả thẻ này sinh ra để chống.
       Sửa ở backend là chữa đúng ca đó. Lưới này chữa MỌI ca còn lại: id đã nằm sẵn
       trong `op`, và hộp thư thì trình duyệt đang giữ — không việc gì phải hỏi lại
       máy chủ để biết một lá thư mình vừa hiển thị tên. */
    const dsThu: EmailRef[] =
      reply.emails && reply.emails.length > 0
        ? reply.emails
        : 'ids' in reply.op
          ? reply.op.ids
              .map((id) => hopThu.find((e) => e.id === id))
              .filter((e): e is Email => !!e)
              .map((e) => ({
                id: e.id, sender: e.sender, initial: e.senderInitial,
                subject: e.subject, snippet: e.preview, unread: e.unread,
              }))
          : []
    // `null` = chưa đụng vào = chọn HẾT. Đây là mặc định đúng: người dùng vừa nói
    // "xoá thư từ X" nên ý định của họ là cả nhóm; ô tick sinh ra để LOẠI TRỪ, không
    // phải để bắt họ chọn lại từ đầu thứ mình vừa yêu cầu.
    const daChon = boChon ?? new Set(dsThu.map((e) => e.id))
    const stepStatus = (i: number): 'done' | 'running' | 'pending' => {
      if (running) {
        if (i < exec!.current) return 'done'
        if (i === exec!.current) return 'running'
        return 'pending'
      }
      return executed ? 'done' : 'pending'
    }
    return (
      <AgentRow>
        <AgentText>{reply.intro}</AgentText>
        <Card className={cn('rose-glass shadow-float transition-all', spotCls)}>
          <CardHeader>
            <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <ListChecks className="size-4 text-primary" />
              {t(running ? 'ch.executing' : 'ch.planProposed')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 pt-2">
            {(reply.steps ?? []).length > 1 && (
              <div className="flex items-center px-1 pb-1">
                {(reply.steps ?? []).map((_s, i) => {
                  const st = stepStatus(i)
                  return (
                    <Fragment key={i}>
                      <span
                        className={cn(
                          'flex size-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ring-1 ring-inset transition-colors',
                          st === 'done'
                            ? 'ripe-pulse bg-success text-success-foreground ring-transparent'
                            : st === 'running'
                              ? 'bg-active text-active-foreground ring-transparent'
                              : 'bg-transparent text-muted-foreground ring-border',
                        )}
                      >
                        {st === 'done' ? (
                          <Check className="size-3" />
                        ) : st === 'running' ? (
                          <Loader2 className="size-3 animate-spin" />
                        ) : (
                          i + 1
                        )}
                      </span>
                      {i < (reply.steps ?? []).length - 1 && (
                        <span
                          className={cn(
                            'h-px flex-1 border-t border-dashed transition-colors',
                            stepStatus(i) === 'done' ? 'border-success/60' : 'border-border/60',
                          )}
                        />
                      )}
                    </Fragment>
                  )
                })}
              </div>
            )}
            <ol className="space-y-2">
              {(reply.steps ?? []).map((s, i) => {
                const st = stepStatus(i)
                return (
                  <li key={i} className="flex items-start gap-2.5 text-sm text-foreground">
                    <span
                      className={cn(
                        'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold transition-colors',
                        st === 'done'
                          ? 'ripe-pulse bg-success text-success-foreground'
                          : st === 'running'
                            ? 'bg-active text-active-foreground'
                            : 'bg-accent text-accent-foreground',
                      )}
                    >
                      {st === 'done' ? (
                        <Check className="size-3" />
                      ) : st === 'running' ? (
                        <Loader2 className="size-3 animate-spin" />
                      ) : (
                        i + 1
                      )}
                    </span>
                    <span className={cn('min-w-0', st === 'running' && 'text-foreground')}>
                      {st === 'running' ? (
                        <span className="skeleton inline-block w-full rounded text-transparent">
                          {s}
                        </span>
                      ) : (
                        s
                      )}
                    </span>
                  </li>
                )
              })}
            </ol>
            {/* ĐÍCH DANH THƯ SẼ BỊ ĐỤNG TỚI.
                Thẻ chỉ ghi "Xoá 2 thư" là bắt người dùng DUYỆT MÙ một hành động không
                hoàn tác. Câu cảnh báo "kiểm tra kỹ trước khi duyệt" mà không cho thấy
                cái gì để kiểm thì chỉ là chữ, không phải một lớp bảo vệ. */}
            {dsThu.length > 0 && !running && (
              <div className="space-y-1.5 rounded-2xl bg-popover-foreground/5 p-2.5">
                <div className="flex items-center justify-between px-0.5">
                  <p className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-muted-foreground">
                    {daChon.size}/{dsThu.length} thư sẽ bị đụng tới
                  </p>
                  <button
                    onClick={() =>
                      setBoChon(daChon.size === dsThu.length ? new Set() : new Set(dsThu.map((e) => e.id)))
                    }
                    className="rounded-md px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.16em] text-active transition-colors hover:bg-active/10"
                  >
                    {daChon.size === dsThu.length ? t('mail.deselectAll') : t('mail.selectAll')}
                  </button>
                </div>
                {/* Cuộn được: danh sách không còn bị cắt ở 20, mà một thẻ cao mãi thì
                    nút Duyệt bị đẩy khỏi tầm mắt — người dùng cuộn tìm nút thay vì đọc
                    danh sách, tức là mất đúng thứ danh sách này sinh ra để làm. */}
                <div className="fade-y max-h-64 space-y-1 overflow-y-auto pr-0.5">
                  {dsThu.map((e) => {
                    const chon = daChon.has(e.id)
                    return (
                      <label
                        key={e.id}
                        className={cn(
                          'flex cursor-pointer items-center gap-2.5 rounded-xl bg-popover-foreground/5 p-2 transition-all',
                          'hover:bg-popover-foreground/10',
                          !chon && 'opacity-40',
                        )}
                      >
                        {/* Ô TICK — mặc định chọn hết. Bỏ tick là LOẠI thư đó khỏi thao
                            tác, không phải chỉ làm mờ: `ids` gửi đi được lọc theo đúng
                            tập này ở nút Duyệt bên dưới.
                            Bọc trong <label> để bấm cả hàng cũng tick được — ô 14px là
                            đích quá nhỏ, nhất là trên máy có màn cảm ứng. */}
                        <input
                          type="checkbox"
                          checked={chon}
                          onChange={() => {
                            const n = new Set(daChon)
                            if (n.has(e.id)) n.delete(e.id)
                            else n.add(e.id)
                            setBoChon(n)
                          }}
                          className="size-4 shrink-0 accent-[var(--active)]"
                        />
                        <MiniAvatar initial={e.initial} />
                        {/* MỞ ĐƯỢC THƯ. Bắt duyệt một danh sách mà không cho đọc từng lá
                            là vẫn duyệt mù — tiêu đề thôi không đủ để biết có nên xoá.
                            `stopPropagation` để bấm mở thư KHÔNG kéo theo tick/bỏ tick. */}
                        <button
                          type="button"
                          disabled={!onOpenEmail}
                          onClick={(ev) => {
                            ev.preventDefault()
                            ev.stopPropagation()
                            onOpenEmail?.(e.id)
                          }}
                          title={onOpenEmail ? t('mail.openThis') : undefined}
                          className="min-w-0 flex-1 text-left disabled:cursor-default"
                        >
                          <p className="truncate text-sm font-medium text-foreground">{e.sender}</p>
                          <p className="truncate text-xs text-muted-foreground">{e.subject}</p>
                        </button>
                        {onOpenEmail && (
                          <ArrowUpRight className="size-3.5 shrink-0 text-[var(--spark)] opacity-60" />
                        )}
                      </label>
                    )
                  })}
                </div>
              </div>
            )}
            {reply.warn && !running && (
              <div className="flex items-start gap-2 rounded-xl bg-accent px-3 py-2 text-xs text-accent-foreground">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                {reply.warn}
              </div>
            )}
          </CardContent>
          <CardFooter>
            {running ? (
              <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" />
                Agent đang xử lý từng bước…
              </span>
            ) : resolved ? (
              <span className="text-xs font-medium text-muted-foreground">{t('st.handled')}</span>
            ) : (
              <>
                <Button
                  variant="primary"
                  size="sm"
                  // Bỏ tick sạch thì KHÔNG cho duyệt. Chạy một thao tác trên danh sách
                  // rỗng rồi báo "đã xoá 0 thư" là một câu trả lời vô nghĩa cho một cú
                  // bấm có chủ đích — thà chặn nút và để người dùng thấy vì sao.
                  disabled={dsThu.length > 0 && daChon.size === 0}
                  onClick={() =>
                    onApprove(
                      message.id,
                      // Gửi đi ĐÚNG tập đã tick. `autoLabel` không có `ids` (nó dùng
                      // `items`) nên để nguyên — lọc bừa vào đó là làm hỏng thẻ khác.
                      'ids' in reply.op ? { ...reply.op, ids: [...daChon] } : reply.op,
                      (reply.steps ?? []).length,
                    )
                  }
                >
                  <Check className="size-4" />
                  {/* Nhãn phải theo số thư CÒN TICK, không theo số ban đầu. Bỏ tick 3
                      trong 5 mà nút vẫn ghi "Xoá 5 thư" thì nút đang nói dối. */}
                  {dsThu.length > 0 && daChon.size !== dsThu.length
                    ? `${reply.confirmLabel.replace(/\d+/, String(daChon.size))}`
                    : reply.confirmLabel}
                </Button>
                <Button variant="outline" size="sm" onClick={() => onReject(message.id)}>
                  <X className="size-4" />
                  Từ chối
                </Button>
              </>
            )}
          </CardFooter>
        </Card>
      </AgentRow>
    )
  }

  return (
    <AgentRow>
      <AgentText>{reply.intro}</AgentText>
      <DraftCard
        reply={reply}
        resolved={resolved}
        spotCls={spotCls}
        id={message.id}
        onSendDraft={onSendDraft}
        onRewrite={onRewrite}
        onResolve={onResolve}
      />
    </AgentRow>
  )
}