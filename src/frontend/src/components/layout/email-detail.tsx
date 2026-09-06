import { useState, useEffect, useRef, useMemo, type CSSProperties } from 'react'
import {
  ArrowLeft,
  Archive,
  Trash2,
  Tag,
  Star,
  Mail,
  Paperclip,
  Download,
  Reply,
  Sparkles,
  CalendarClock,
  ListChecks,
  FileText,
  ChevronDown,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { t } from '@/lib/ngon-ngu'
import { api, apiBaseUrlDaCauHinh, duongDanApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { LabelDialog } from '@/components/layout/label-dialog'
import { useToast } from '@/components/ui/toast'
import { useTheme } from '@/components/theme-provider'
import { SenderAvatar } from '@/components/layout/sender-avatar'
import { CATEGORY } from '@/data/categories'
import type { Email } from '@/data/emails'
import type { EmailActions } from '@/lib/email-actions'

/** Nút hành động "đoán trước ý định" theo nội dung thư (UC016 + UC007). */
type ContextAction = { label: string; icon: React.ElementType; command: string }
function contextActions(email: Email): ContextAction[] {
  const text = `${email.subject} ${email.body.join(' ')}`.toLowerCase()
  const first = email.sender.split(' ').slice(-1)[0] || email.sender
  const acts: ContextAction[] = []
  if (/(họp|meeting|lịch|cuộc họp|\bhẹn\b)/.test(text)) {
    acts.push({ label: t('sug.brief'), icon: CalendarClock, command: 'brief cuộc họp' })
  }
  if (/(deadline|hạn|nộp|trước \d|submit|báo cáo)/.test(text)) {
    acts.push({ label: t('sug.tasks'), icon: ListChecks, command: 'triage hộp thư' })
  }
  acts.push({ label: t('sug.summarize'), icon: FileText, command: `tóm tắt thư từ ${first}` })
  acts.push({ label: t('act.replyDraft'), icon: Reply, command: `soạn trả lời ${first}` })
  return acts.slice(0, 3)
}

// Cache tóm tắt LLM theo email id → mở lại thư khỏi gọi LLM lần nữa (đỡ quota).
const summaryCache = new Map<string, string[]>()

export function EmailDetail({
  email,
  onClose,
  actions,
  onAgentAction,
}: {
  email: Email
  onClose: () => void
  actions: EmailActions
  onAgentAction?: (command: string) => void
}) {
  const c = CATEGORY[email.category]
  const { theme } = useTheme()

  /* ── LUỒNG HỘI THOẠI ──────────────────────────────────────────────────────
     Nạp theo id thư đang mở; máy chủ tự suy ra luồng nên phía này không cần biết
     `threadId` có tồn tại hay không. Hỏng thì để danh sách rỗng — khối luồng biến
     mất, còn thư đang mở vẫn đọc được bình thường. Một tính năng phụ hỏng không
     được kéo theo thứ người dùng vừa bấm vào. */
  const [luong, setLuong] = useState<Email[]>([])
  const [daMo, setDaMo] = useState<Set<string>>(new Set())
  useEffect(() => {
    let huy = false
    setLuong([])
    setDaMo(new Set())          // đổi thư thì đóng hết, không giữ trạng thái thư cũ
    api.getThread(email.id).then((ds) => { if (!huy) setLuong(ds ?? []) }).catch(() => {})
    return () => { huy = true }
  }, [email.id])
  // Bỏ chính thư đang mở ra khỏi danh sách "các lượt trước".
  const truocDo = useMemo(() => luong.filter((m) => m.id !== email.id), [luong, email.id])
  const [labelOpen, setLabelOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [showSummary, setShowSummary] = useState(true)
  const id = email.id
  const toast = useToast()
  const actionsList = contextActions(email)

  // UC008 — thẻ tóm tắt gọi LLM THẬT (backend). Lazy khi mở thẻ + cache theo email (đỡ quota);
  // lỗi/quota/mock → lùi về tóm tắt trích cục bộ (aiSummary). KHÔNG bao giờ chặn UI.
  const [llmSummary, setLlmSummary] = useState<string[] | null>(() => summaryCache.get(id) ?? null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  useEffect(() => {
    if (!apiBaseUrlDaCauHinh || !showSummary) return
    const cached = summaryCache.get(email.id)
    if (cached) {
      setLlmSummary(cached)
      return
    }
    let cancelled = false
    setSummaryLoading(true)
    setLlmSummary(null)
    api
      .summarizeEmail(email.id)
      .then((pts) => {
        if (cancelled || !pts?.length) return
        summaryCache.set(email.id, pts)
        setLlmSummary(pts)
      })
      .catch(() => {})
      .finally(() => !cancelled && setSummaryLoading(false))
    return () => {
      cancelled = true
    }
  }, [email.id, showSummary])
  const points = llmSummary ?? aiSummary(email)

  /* TÓM TẮT CHỈ HIỆN KHI NÓ THỰC SỰ RÚT GỌN.
     `aiSummary` (bản lùi khi chưa có LLM) chỉ lấy ba đoạn đầu của thân thư rồi
     cắt bớt — với một lá thư ba đoạn thì đó là BẢN SAO NGUYÊN VĂN, không phải
     tóm tắt. Ảnh chụp cho thấy đúng vậy: ba gạch đầu dòng trùng khít ba đoạn
     ngay bên dưới. Người đọc mất một khối màn hình để đọc lại thứ họ sắp đọc.

     Nên: có tóm tắt THẬT từ mô hình thì luôn hiện; còn bản lùi cục bộ chỉ hiện
     khi thư đủ dài để việc rút gọn có nghĩa. Thư ngắn thì bỏ hẳn khối này —
     không có gì để tóm tắt thì đừng giả vờ là có. */
  const soChu = email.body.join(' ').trim().split(/\s+/).length
  const phutDoc = Math.max(1, Math.round(soChu / 200))
  const dangThucSuTomTat = llmSummary != null || soChu > 140

  return (
    <aside className="ai-panel-bg relative z-10 flex h-full flex-1 flex-col overflow-hidden border-l border-accent/30 shadow-soft duration-300 animate-in fade-in slide-in-from-right-4">
      {/* Adaptive accent — panel nhuốm sắc theo category của thư đang đọc */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-44"
        style={{
          background: `linear-gradient(to bottom, color-mix(in srgb, ${c.bar} 22%, transparent), transparent)`,
        }}
      />
      {/* Thanh hành động trên cùng */}
      <header className="flex items-center gap-1 border-b border-border/50 px-4 py-3">
        <button
          onClick={onClose}
          title={t('nav.backAssistant')}
          className="flex items-center gap-2 rounded-xl px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Quay lại
        </button>
        <div className="ml-auto flex items-center gap-0.5">
          <ActionBtn
            icon={Mail}
            label={t('act.markUnread')}
            onClick={() => {
              actions.markRead([id], false)
              toast(t('toast.markedUnreadOne'), 'success')
            }}
          />
          <ActionBtn
            icon={Archive}
            label={t('act.archive')}
            onClick={() => {
              actions.removeEmails([id], 'archive') // bỏ nhãn INBOX
              toast(t('toast.archived'), 'success')
            }}
          />
          <ActionBtn icon={Tag} label={t('act.label')} onClick={() => setLabelOpen(true)} />
          <ActionBtn icon={Trash2} label={t('act.delete')} onClick={() => setConfirmDelete(true)} />
          <button
            onClick={() => {
              actions.setImportant([id], !email.starred)
              toast(email.starred ? 'Đã bỏ quan trọng' : 'Đã đánh dấu quan trọng', 'success')
            }}
            aria-label={t(email.starred ? 'det.unstar' : 'det.star')}
            title={t(email.starred ? 'det.unstar' : 'det.star')}
            className="flex size-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <Star className="size-4" style={email.starred ? { fill: c.bar, color: c.bar } : undefined} />
          </button>
        </div>
      </header>

      {/* Nội dung */}
      <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto px-5 py-5">
        {/* TÓM TẮT — bản trước bị chê "chữ không à", và đúng: nó là một cái hộp
            chứa vài dòng chữ, không có gì để mắt bám vào ngoài chữ.

            Bản này cho nó CẤU TRÚC trước khi cho nó chữ: một hàng số liệu (trạng
            thái xử lý · số chữ · phút đọc) rồi mới tới các ý chính. Hàng số liệu
            trả lời được câu hỏi đầu tiên người ta hỏi khi mở một lá thư — "cái
            này có cần tôi làm gì không, và có dài không" — mà không cần đọc chữ nào.

            Cũng bỏ `.ripe` (bề mặt mọng thời cũ) và dùng đèn viền cho khớp phần
            còn lại của giao diện. */}
        {dangThucSuTomTat && (
        <div
          style={{ ['--tint' as string]: c.bar }}
          className="den-vien goc-cat overflow-hidden"
        >
          <button
            onClick={() => setShowSummary((v) => !v)}
            className="flex w-full items-center gap-2.5 px-4 py-3 text-left"
          >
            <span className="o-icon size-7 shrink-0">
              <Sparkles className="size-3.5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[10px] font-semibold uppercase tracking-[0.18em] text-foreground/70">
                Tóm tắt · AI
              </span>
              {!showSummary && (
                <span className="block truncate text-xs text-muted-foreground">
                  {email.tldr ?? points[0]}
                </span>
              )}
            </span>
            <ChevronDown
              className={cn(
                'size-4 shrink-0 text-muted-foreground transition-transform',
                showSummary && 'rotate-180',
              )}
            />
          </button>

          {showSummary && (
            <div className="px-4 pb-4">
              {/* HÀNG SỐ LIỆU — thứ đọc được bằng liếc mắt, không phải bằng đọc */}
              <div className="mb-3 grid grid-cols-3 gap-2">
                {[
                  { nhan: t('det.status'), gtri: t(TRANG_THAI[email.priority ?? 'fyi']) },
                  { nhan: t('det.length'), gtri: t('det.words', { n: soChu }) },
                  { nhan: t('det.readTime'), gtri: t('det.minutes', { n: phutDoc }) },
                ].map((o) => (
                  <div key={o.nhan} className="den-vien goc-cat-nho goc-cat px-2.5 py-2">
                    <p className="text-[8.5px] font-medium uppercase tracking-[0.16em] text-muted-foreground/70">
                      {o.nhan}
                    </p>
                    <p className="mt-1 font-mono text-[12px] font-semibold tabular-nums text-foreground">
                      {o.gtri}
                    </p>
                  </div>
                ))}
              </div>

              {email.tldr && (
                <p className="mb-2.5 text-sm font-medium leading-relaxed text-foreground">{email.tldr}</p>
              )}
              {summaryLoading && !llmSummary ? (
                <div className="space-y-2">
                  <div className="skeleton h-3 w-3/4 rounded" />
                  <div className="skeleton h-3 w-full rounded" />
                  <div className="skeleton h-3 w-2/3 rounded" />
                </div>
              ) : (
                <ul className="space-y-1.5">
                  {points.map((s, i) => (
                    <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-foreground/90">
                      <span className="mt-[7px] size-1.5 shrink-0 rounded-full"
                        style={{ background: c.bar, boxShadow: `0 0 8px ${c.bar}` }} />
                      <span className="min-w-0">{s}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
        )}

        {/* Contextual Agent Actions (UC016) — nút "đoán trước ý định" */}
        {onAgentAction && (
          <div className="flex flex-wrap gap-2">
            {actionsList.map((a) => {
              const Icon = a.icon
              return (
                <button
                  key={a.label}
                  onClick={() => onAgentAction(a.command)}
                  className="nut-ky-thuat group flex items-center gap-2 px-3.5 py-2 text-xs font-semibold text-foreground glass"
                >
                  <Icon className="size-4 text-spark" />
                  {a.label}
                </button>
              )
            })}
          </div>
        )}

        {/* THÂN THƯ KHÔNG CÒN NẰM TRONG MỘT CÁI THẺ.
            Trước đây cả lá thư bị bọc trong `rounded-2xl p-5 glass` — một khối
            kính bo góc, đổ bóng, có viền. Nhìn ra là "một mẩu nội dung đặt trong
            một ô", và ô đó lại nằm trong một cột đang cuộn: đọc một lá thư dài
            thành ra cuộn trong ô, trong cột.

            Gmail không làm vậy vì lá thư KHÔNG PHẢI một mẩu nội dung trong màn
            hình — nó LÀ màn hình. Nên bỏ hết khung: chỉ còn khoảng đệm rộng và
            một mặt phẳng để đọc. */}
        <div className="px-1 pb-2">
          {/* Eyebrow: nhãn + thời gian (micro uppercase) */}
          <div className="mb-2.5 flex flex-wrap items-center gap-2 text-[10px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
            {email.label && (
              <span className="inline-flex items-center gap-1.5 text-foreground">
                <span className="size-1.5 rounded-full" style={{ backgroundColor: c.bar }} />
                {email.label}
              </span>
            )}
            {email.label && <span className="text-muted-foreground/50">/</span>}
            <span>{email.date}</span>
          </div>

          {/* Subject lớn editorial */}
          <h1 className="font-serif text-[28px] font-semibold leading-[1.12] text-foreground">
            {email.subject}
          </h1>

          {/* Người gửi */}
          <div className="mt-5 flex items-center gap-3">
            <SenderAvatar
              email={email.senderEmail}
              initial={email.senderInitial}
              className="gloss size-11 shrink-0 rounded-full font-mono text-base font-semibold ring-1 ring-inset"
              style={
                {
                  backgroundColor: 'rgba(251, 240, 226, 0.92)',
                  color: c.ink,
                  ['--tw-ring-color' as string]: c.bar,
                } as CSSProperties
              }
            />
            <div className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-foreground">
                {email.sender}
              </span>
              <p className="truncate text-xs text-muted-foreground">&lt;{email.senderEmail}&gt;</p>
            </div>
          </div>

          {/* Người nhận */}
          <p className="mt-3 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            <span className="text-foreground/75">{t('mail.to')}</span> · {email.to}
          </p>

          {/* ── CÁC LƯỢT TRƯỚC ĐÓ TRONG CÙNG CUỘC TRAO ĐỔI ──────────────────
              Danh sách đã gộp một cuộc trao đổi nhiều lượt thành MỘT dòng, đúng như
              Gmail. Nhưng mở ra thì trước đây chỉ thấy thư MỚI NHẤT — các lượt trước
              không có chỗ nào để xem. Gộp mà không mở ra được thì tệ hơn không gộp:
              người dùng còn không biết mình đang bị giấu thứ gì.

              Thu gọn sẵn, không bung hết: mở một thư ra mà phải cuộn qua sáu lượt cũ
              để tới nội dung mới nhất là đặt sai thứ tự ưu tiên — thứ người ta vừa
              bấm vào phải nằm ngay trước mắt. */}
          {truocDo.length > 0 && (
            <div className="mt-4 space-y-1.5">
              <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                {t('det.threadEarlier', { n: truocDo.length })}
              </p>
              {truocDo.map((m) => {
                const mo = daMo.has(m.id)
                return (
                  <div key={m.id} className="goc-cat den-vien overflow-hidden" style={{ position: 'relative' }}>
                    <button
                      type="button"
                      onClick={() =>
                        setDaMo((tr) => {
                          const s = new Set(tr)
                          if (s.has(m.id)) s.delete(m.id)
                          else s.add(m.id)
                          return s
                        })
                      }
                      aria-expanded={mo}
                      className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-foreground/[0.04]"
                    >
                      <SenderAvatar name={m.sender} email={m.senderEmail} size={22} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium text-foreground">
                          {m.sender}
                        </span>
                        {!mo && (
                          <span className="block truncate text-[12px] text-muted-foreground">
                            {m.preview}
                          </span>
                        )}
                      </span>
                      <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">
                        {m.time}
                      </span>
                      <ChevronDown
                        className={cn('size-3.5 shrink-0 text-muted-foreground transition-transform',
                          mo && 'rotate-180')}
                      />
                    </button>
                    {mo && (
                      <div className="space-y-3 border-t border-border/60 px-3 py-3 text-[14px] leading-[1.7] text-foreground/90 [overflow-wrap:anywhere]">
                        {cleanParagraphs(m.body).map((p, i) => (
                          <p key={i} className="whitespace-pre-line">{renderRich(p)}</p>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* Vạch ngăn */}
          <div className="my-4 h-px bg-border/60" />

          {/* Body — HTML GỐC (đúng chuẩn Gmail, iframe sandbox) nếu có; không thì text sạch đã tinh chỉnh */}
          {email.html ? (
            <EmailHtmlBody html={email.html} dark={theme === 'dark'} />
          ) : (
            <div className="max-w-[68ch] space-y-4 text-[15px] leading-[1.75] text-foreground/90 [overflow-wrap:anywhere]">
              {cleanParagraphs(email.body).map((p, i) => (
                <p key={i} className="whitespace-pre-line">
                  {renderRich(p)}
                </p>
              ))}
            </div>
          )}

          {/* Tệp đính kèm */}
          {email.attachments && email.attachments.length > 0 && (
            <div className="mt-5">
              <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <Paperclip className="size-3.5" />
                {email.attachments.length} tệp đính kèm
              </div>
              <div className="flex flex-wrap gap-2">
                {email.attachments.map((a) => (
                  <button
                    key={a.name}
                    onClick={() => {
                      // Chế độ backend thật: mở URL tải đính kèm (cookie phiên tự đính kèm
                      // → backend xác thực). Mock mode: chưa có tệp thật → bỏ qua.
                      if (apiBaseUrlDaCauHinh)
                        window.open(
                          duongDanApi(`/emails/${id}/attachments/${encodeURIComponent(a.name)}`),
                          '_blank',
                        )
                    }}
                    className="group flex items-center gap-2.5 rounded-xl bg-popover px-3 py-2 text-left shadow-subtle transition-all hover:-translate-y-0.5 hover:shadow-soft"
                  >
                    <span
                      className="flex size-8 items-center justify-center rounded-lg text-[10px] font-bold uppercase"
                      style={{ backgroundColor: c.soft, color: c.ink }}
                    >
                      {a.name.split('.').pop()}
                    </span>
                    <span className="min-w-0">
                      <span className="block max-w-[160px] truncate text-xs font-medium text-popover-foreground">
                        {a.name}
                      </span>
                      <span className="block text-[11px] text-popover-foreground/60">{a.size}</span>
                    </span>
                    <Download className="size-4 text-popover-foreground/50 transition-colors group-hover:text-popover-foreground" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Chân — trả lời */}
      <div className="flex items-center gap-2.5 border-t border-border/50 px-5 py-4">
        <Button
          variant="primary"
          onClick={() => onAgentAction?.(`soạn trả lời ${email.sender.split(' ').slice(-1)[0]}`)}
        >
          <Reply className="size-4" />
          Trả lời
        </Button>
        <Button variant="outline" onClick={() => setShowSummary((v) => !v)}>
          <Sparkles className="size-4" />
          {t(showSummary ? 'det.hideSummary' : 'det.aiSummary')}
        </Button>
      </div>

      {/* Dialog gắn nhãn */}
      <LabelDialog
        open={labelOpen}
        onOpenChange={setLabelOpen}
        count={1}
        onPick={(category, label) => {
          actions.applyLabel([id], category, label)
          toast(t('toast.labelledOne', { nhan: label }), 'success')
        }}
      />

      {/* Dialog xác nhận xoá */}
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Trash2 className="size-5 text-destructive" />
              {t('det.delTitle')}
            </DialogTitle>
            <DialogDescription>
              {t('det.delDesc', { tieuDe: email.subject })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              {t('act.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConfirmDelete(false)
                actions.removeEmails([id], 'delete') // vào thùng rác
                toast(t('toast.deleted', { n: 1 }), 'destructive')
              }}
            >
              <Trash2 className="size-4" />
              {t('act.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  )
}

// Nhận diện URL trong text đã strip-HTML → biến thành LINK RÚT GỌN (tránh chuỗi tracking dài
// cả trăm ký tự làm vỡ bố cục). Đọc êm & gọn như Gmail.
const URL_RE = /(https?:\/\/[^\s<>()]+)/g
function renderRich(text: string) {
  return text.split(URL_RE).map((part, i) => {
    if (i % 2 === 0) return <span key={i}>{part}</span>
    let label = part.replace(/^https?:\/\/(www\.)?/, '')
    if (label.length > 42) label = label.slice(0, 42) + '…'
    return (
      <a
        key={i}
        href={part}
        target="_blank"
        rel="noopener noreferrer"
        className="break-all font-medium text-active underline decoration-active/40 underline-offset-2 hover:decoration-active"
      >
        {label}
      </a>
    )
  })
}

// Dọn đoạn văn: gộp khoảng trắng/dòng trống thừa, bỏ đoạn rỗng → hết cảm giác "lộn xộn".
function cleanParagraphs(body: string[]): string[] {
  return body
    .map((p) => p.replace(/[ \t]{2,}/g, ' ').replace(/\n{3,}/g, '\n\n').trim())
    .filter(Boolean)
}

// Dọn HTML email trước khi render (phòng thủ nhiều lớp — iframe sandbox KHÔNG cho chạy script
// đã chặn XSS, nhưng vẫn cắt <script>/<iframe>/handler on*/javascript: cho chắc).
function sanitizeHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, '')
    .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(/(href|src)\s*=\s*(["'])\s*javascript:[^"']*\2/gi, '$1="#"')
}

/** Render HTML GỐC của email đúng chuẩn Gmail — trong iframe SANDBOX (không cho JS chạy),
 *  tự canh chiều cao theo nội dung, link mở tab mới, ảnh co vừa khung, hỗ trợ dark mode. */
/**
 * EmailHtmlBody — dựng thư HTML gốc trong iframe sandbox, cao ĐÚNG bằng nội dung.
 *
 * ── VÌ SAO BẢN TRƯỚC HỎNG ──
 * Bản trước đo `body.scrollHeight` ở đúng ba mốc: 0ms, 300ms, 1200ms. Nguyên
 * nhân nằm ở chỗ đó — KHÔNG phải ở phép đo, mà ở việc ĐOÁN KHI NÀO ĐO.
 *
 * Thư quảng cáo dựng bằng ảnh banner tải từ CDN, và thường không khai `width`/
 * `height` trên thẻ `img`. Trước khi ảnh về, thẻ ảnh chiếm 0px, nên cả ba lần đo
 * đều ra một con số bé tí. Ảnh về sau giây thứ hai thì không còn ai đo lại nữa:
 * iframe đứng ở chiều cao cũ, nội dung cao gấp mười, và trình duyệt mọc thanh
 * cuộn riêng bên trong. Đúng triệu chứng đã bị chỉ ra hai lần.
 *
 * Đã dựng lại đúng tình huống này để kiểm chứng: bản cũ đo được 53px ở cả ba
 * mốc, trong khi nội dung thật sau đó là 721px.
 *
 * (Giả thuyết đầu tiên của tôi — thư đặt `html{height:100%}` làm `scrollHeight`
 * trả về chiều cao khung nhìn và tạo vòng khoá cứng — đã thử và KHÔNG tái hiện
 * được: Chrome vẫn báo đúng chiều cao nội dung. Vẫn giữ phần ép `height:auto`
 * bên dưới vì nó vô hại và chặn được lớp lỗi đó ở trình duyệt khác, nhưng nó
 * không phải thứ chữa được lỗi này.)
 *
 * ── CÁCH CHỮA ──
 * 1. ResizeObserver thay cho hẹn giờ: thôi đoán, chỉ phản ứng. Bố cục đổi lúc
 *    nào thì đo lại lúc đó — ảnh về muộn, phông web tải xong, khối gập mở, đổi
 *    bề rộng cột. Đây là thứ thật sự chữa lỗi.
 * 2. Nghe thêm sự kiện `load` của từng ảnh — thừa một chút so với (1), nhưng
 *    ResizeObserver chỉ bắn khi kích thước ĐÃ đổi, còn cách này bắt đúng thời
 *    điểm ảnh sẵn sàng.
 * 3. Đo bằng GIÁ TRỊ LỚN NHẤT trong bốn phép đo: thư dùng float hoặc position
 *    tuyệt đối thì `body.scrollHeight` có thể nhỏ hơn thực tế trong khi
 *    `documentElement.scrollHeight` lại đúng — và ngược lại.
 */
function EmailHtmlBody({ html, dark }: { html: string; dark: boolean }) {
  const ref = useRef<HTMLIFrameElement>(null)
  const srcDoc = useMemo(() => {
    const base =
      // Ép tài liệu KHÔNG được cao bằng khung nhìn và KHÔNG được tự cuộn.
      // `!important` là bắt buộc: ta đang ghi đè CSS của người gửi.
      `html,body{height:auto!important;min-height:0!important;max-height:none!important;` +
      `overflow:hidden!important;margin:0;padding:0;background:transparent;` +
      `font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;` +
      `font-size:15px;line-height:1.65;overflow-wrap:anywhere;word-break:break-word}` +
      `img{max-width:100%!important;height:auto}*{max-width:100%}` +
      `table{max-width:100%!important;width:auto!important}` +
      `blockquote{margin:0 0 0 .8em;padding-left:.8em;border-left:2px solid #ccc;color:#777}`
    // NHẬP GIA TÙY TỤC: DARK → đảo màu để hoà vào nền tối MeoArc (bố cục & nội dung GIỮ NGUYÊN),
    // rồi đảo NGƯỢC ảnh/video/nền-ảnh để chúng vẫn đúng màu. LIGHT → giữ tự nhiên trên nền sáng.
    const themed = dark
      ? `html{filter:invert(0.9) hue-rotate(180deg)}` +
        `img,picture,video,svg,image,[style*="background-image"]{filter:invert(1) hue-rotate(180deg)}` +
        `body{color:#1a1a1a}`
      : `body{color:#14141f}a{color:#6D5BE0}`
    return (
      `<!doctype html><html><head><meta charset="utf-8"><base target="_blank">` +
      `<style>${base}${themed}</style></head><body>${sanitizeHtml(html)}</body></html>`
    )
  }, [html, dark])

  useEffect(() => {
    const f = ref.current
    if (!f) return
    let quanSat: ResizeObserver | null = null

    const doLai = () => {
      const d = f.contentDocument
      const b = d?.body
      const e = d?.documentElement
      if (!b || !e) return
      const cao = Math.max(b.scrollHeight, b.offsetHeight, e.scrollHeight, e.offsetHeight)
      if (cao > 0) f.style.height = `${cao + 16}px`
    }

    const gan = () => {
      const d = f.contentDocument
      if (!d?.body) return
      doLai()
      quanSat?.disconnect()
      quanSat = new ResizeObserver(doLai)
      quanSat.observe(d.body)
      quanSat.observe(d.documentElement)
      // Ảnh trong thư có thể tải xong SAU khi bố cục đã ổn định một lần;
      // ResizeObserver bắt được, nhưng gắn thêm listener cho chắc.
      d.querySelectorAll('img').forEach((img) => img.addEventListener('load', doLai))
    }

    f.addEventListener('load', gan)
    if (f.contentDocument?.readyState === 'complete') gan()
    return () => {
      f.removeEventListener('load', gan)
      quanSat?.disconnect()
    }
  }, [srcDoc])

  return (
    <iframe
      ref={ref}
      title={t('mail.body')}
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      srcDoc={srcDoc}
      scrolling="no"
      className="w-full border-0"
      style={{ minHeight: 120, display: 'block' }}
    />
  )
}

/** Tóm tắt mock từ nội dung email (UC008) — backend thật dùng LLM. */
/** Nhãn trạng thái xử lý — cùng bộ với badge triage ở danh sách thư. */
const TRANG_THAI: Record<string, string> = {
  action: 'flt.action',
  waiting: 'flt.waiting',
  fyi: 'det.fyi',
}

/** Một đoạn có phải CÂU THẬT không, hay là rác mã hoá?
 *
 *  Thư quảng cáo (Groq, Mailchimp, Sendgrid…) nhét vào phần văn bản thuần đủ
 *  thứ không phải văn bản: liên kết theo dõi dài hàng trăm ký tự, khối base64,
 *  chuỗi mã hoá quoted-printable. Bản trước không lọc gì, nên khối "Tóm tắt"
 *  hiện ra nguyên một dòng ký tự vô nghĩa — người dùng đã nhìn thấy đúng cảnh đó.
 *
 *  Ba dấu hiệu nhận rác, và cần cả ba vì mỗi thứ bắt một kiểu:
 *    1. Từ dài bất thường (>40 ký tự không khoảng trắng) — base64, token, URL.
 *    2. Tỉ lệ chữ cái thấp so với tổng ký tự — chuỗi lẫn nhiều số và dấu.
 *    3. Không có khoảng trắng nào ở đoạn đủ dài — câu thật luôn có khoảng trắng.
 */
function laCauThat(t: string): boolean {
  const s = t.trim()
  if (s.length < 24) return false
  if (/https?:\/\/\S{40,}/.test(s)) return false
  if (/\S{45,}/.test(s)) return false
  const chuCai = (s.match(/[\p{L}]/gu) ?? []).length
  if (chuCai / s.length < 0.55) return false
  const tu = s.split(/\s+/)
  if (tu.length < 4) return false
  return true
}

function aiSummary(email: Email): string[] {
  const core = email.body
    .map((p) => p.replace(/\s+/g, ' ').trim())
    .filter(laCauThat)
    .slice(0, 3)
    .map((p) => (p.length > 160 ? p.slice(0, 160).trimEnd() + '…' : p))
  if (core.length) return core
  // Không đoạn nào là câu thật (thư toàn HTML/mã) → dùng dòng xem trước, và nếu
  // dòng đó cũng là rác thì thà nói thẳng còn hơn hiện một dòng ký tự vô nghĩa.
  return laCauThat(email.preview) ? [email.preview] : [t('det.htmlNote')]
}

function ActionBtn({
  icon: Icon,
  label,
  onClick,
}: {
  icon: React.ElementType
  label: string
  onClick: () => void
}) {
  return (
    <button
      title={label}
      onClick={onClick}
      className="flex size-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
    >
      <Icon className="size-4" />
    </button>
  )
}
