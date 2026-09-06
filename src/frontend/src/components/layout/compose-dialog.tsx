import { useEffect, useRef, useState } from 'react'
import {
  PenSquare,
  Palette,
  RemoveFormatting,
  Send,
  CheckCircle2,
  ArrowLeft,
  Paperclip,
  X,
  Sparkles,
  Bold,
  Italic,
  Underline,
  List,
  Link2,
  Trash2,
  Files,
  UploadCloud,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { t } from '@/lib/ngon-ngu'
import { api, apiBaseUrlDaCauHinh } from '@/lib/api'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

// id = mã tệp BE trả khi upload (http mode). Mock mode không có id (gửi giả).
/** `loi` = tải lên máy chủ hỏng. Giữ lại để người dùng THẤY, và chặn nút Gửi —
 *  chứ không im lặng loại ra lúc gửi như bản trước. */
type Attachment = { id?: string; name: string; size: string; loi?: boolean }

const fieldCls =
  'w-full bg-transparent text-sm text-popover-foreground outline-none placeholder:text-popover-foreground/40'

/** Một nút định dạng cho ô soạn thư.
 *
 *  ── TRƯỚC ĐÂY NĂM NÚT NÀY KHÔNG LÀM GÌ CẢ ──
 *  Thanh định dạng đã có sẵn từ bản dựng giao diện, nhưng `ToolbarBtn` không hề có
 *  `onClick` — bấm vào là không có chuyện gì xảy ra. Nút có mà bấm không ăn còn tệ hơn
 *  không có nút: người dùng thử vài lần rồi kết luận cả ứng dụng hỏng.
 *
 *  Dùng `document.execCommand`. Nó đã bị đánh dấu deprecated nhưng KHÔNG có thứ thay
 *  thế được chuẩn hoá, và mọi trình duyệt hiện tại vẫn chạy. Lựa chọn còn lại là kéo về
 *  một thư viện soạn thảo — thêm vài trăm KB và một phụ thuộc mới cho năm cái nút, vài
 *  ngày trước buổi bảo vệ. Đánh đổi có chủ ý.
 */
function ToolbarBtn({
  icon: Icon,
  nhan,
  lenh,
  gtri,
  onXong,
}: {
  icon: React.ElementType
  nhan: string
  lenh: string
  gtri?: string
  onXong: () => void
}) {
  return (
    <button
      type="button"
      title={nhan}
      aria-label={nhan}
      // Bấm nút KHÔNG được cướp con trỏ khỏi ô soạn — mất vùng đang bôi đen thì lệnh
      // định dạng chẳng áp vào đâu cả.
      onMouseDown={(e) => e.preventDefault()}
      onClick={() => {
        if (lenh === 'createLink') {
          const url = window.prompt(t('cmp.linkPrompt'))
          if (!url) return
          document.execCommand('createLink', false, url)
        } else {
          document.execCommand(lenh, false, gtri)
        }
        onXong()
      }}
      className="flex size-8 items-center justify-center rounded-lg text-popover-foreground/60 transition-colors hover:bg-popover-foreground/10 hover:text-popover-foreground"
    >
      <Icon className="size-4" />
    </button>
  )
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

/** UC010 — Soạn & gửi email (Gmail+): To/Cc/Bcc, định dạng, đính kèm file, xác nhận gửi. */
export function ComposeDialog() {
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState<'compose' | 'confirm' | 'sent'>('compose')
  const [to, setTo] = useState('')
  const [cc, setCc] = useState('')
  const [bcc, setBcc] = useState('')
  const [showCc, setShowCc] = useState(false)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [html, setHtml] = useState('')
  /* CHẾ ĐỘ TRẢ LỜI. Cùng một form, chỉ khác đích đến khi bấm Gửi:
     có `replyToId` thì gửi qua /emails/{id}/reply để Gmail xếp ĐÚNG LUỒNG hội thoại;
     không có thì là thư mới. Dựng một form riêng cho trả lời là chép lại toàn bộ phần
     đính kèm, CC/BCC, gợi ý địa chỉ — rồi hai bên lệch nhau dần. */
  const [replyToId, setReplyToId] = useState<string | null>(null)
  const [replyAll, setReplyAll] = useState(false)
  const [files, setFiles] = useState<Attachment[]>([])
  const [dragging, setDragging] = useState(false)
  const [justDropped, setJustDropped] = useState(false) // bật vệt sáng chạy viền sau khi thả
  const [sending, setSending] = useState(false) // đang gọi backend gửi thư (khoá nút, chống gửi 2 lần)
  const [sendError, setSendError] = useState<string | null>(null) // báo lỗi nếu Gmail từ chối
  const fileRef = useRef<HTMLInputElement>(null)
  const oRef = useRef<HTMLDivElement>(null)
  const toast = useToast()
  // #3 — autocomplete người nhận (như Gmail)
  const [toSuggest, setToSuggest] = useState<{ name: string; email: string }[]>([])
  const toTimer = useRef<number | null>(null)
  // #2 — Smart Compose: gợi ý đoạn tiếp theo (Tab để chèn)
  const [ghost, setGhost] = useState('')
  const ghostTimer = useRef<number | null>(null)

  // #2 — phím tắt "c" mở soạn thư (khi không đang gõ ở ô nào)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || open) return
      const el = document.activeElement as HTMLElement | null
      const typing =
        !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
      if (e.key === 'c' && !typing) {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  /* Mở từ nút "Trả lời" ở màn chi tiết. Dùng sự kiện window thay vì luồn prop qua
     email-list → EmailDetail: hộp thoại này vốn tự quản trạng thái mở, và luồn prop
     qua hai tầng chỉ để bật một cờ là thêm hai chỗ có thể quên truyền. */
  useEffect(() => {
    const onMo = (e: Event) => {
      const d = (e as CustomEvent).detail || {}
      setReplyToId(d.replyToId || null)
      setReplyAll(!!d.replyAll)
      setTo(d.to || '')
      setSubject(d.subject || '')
      setBody('')
      setHtml('')
      setFiles([])
      setStep('compose')
      setSendError(null)
      setOpen(true)
    }
    window.addEventListener('meoarc:soan-tra-loi', onMo)
    return () => window.removeEventListener('meoarc:soan-tra-loi', onMo)
  }, [])

  // #9 — "Soạn với AI": stream chữ kiểu typewriter + ghost text + con trỏ bokeh
  const [aiTyping, setAiTyping] = useState(false)
  const [aiTarget, setAiTarget] = useState('')
  const [aiTyped, setAiTyped] = useState(0)
  const aiTimer = useRef<number | null>(null)
  const stopAi = () => {
    if (aiTimer.current) {
      clearInterval(aiTimer.current)
      aiTimer.current = null
    }
  }
  useEffect(() => () => stopAi(), [])
  // Khi gõ xong → chốt nội dung vào ô soạn
  useEffect(() => {
    if (aiTyping && aiTarget && aiTyped >= aiTarget.length) {
      stopAi()
      setBody(aiTarget)
      setAiTyping(false)
    }
  }, [aiTyped, aiTyping, aiTarget])

  const reset = () => {
    stopAi()
    setAiTyping(false)
    setAiTarget('')
    setAiTyped(0)
    setStep('compose')
    setTo('')
    setCc('')
    setBcc('')
    setShowCc(false)
    setSubject('')
    setBody('')
    setFiles([])
    setSending(false)
    setSendError(null)
    setGhost('')
    setToSuggest([])
    if (ghostTimer.current) window.clearTimeout(ghostTimer.current)
    if (toTimer.current) window.clearTimeout(toTimer.current)
  }

  // Thêm tệp: chế độ backend thật → UPLOAD lên server rồi lấy metadata trả về;
  // chế độ mock → chỉ thêm cục bộ như cũ.
  const addFiles = async (list: FileList | null) => {
    if (!list) return
    const arr = Array.from(list)
    if (apiBaseUrlDaCauHinh) {
      for (const f of arr) {
        try {
          const r = await api.uploadFile(f)
          // GIỮ r.id để lúc gửi còn biết đính tệp nào (BE tra bytes theo id).
          setFiles((prev) => [...prev, { id: r.id, name: r.name, size: r.size }])
        } catch {
          // KHÔNG âm thầm thêm tệp "không có id".
          //
          // Bản trước làm đúng thế: tải lên hỏng thì vẫn thêm chip vào danh sách, chỉ
          // là thiếu `id`. Lúc gửi, `.filter(x => !!x)` lặng lẽ loại nó ra — nên người
          // dùng NHÌN THẤY tệp trên màn hình, bấm Gửi, nhận báo "đã gửi", và bức thư
          // đi ra không có tệp nào. Họ chỉ biết sự thật từ người nhận.
          //
          // Nay đánh dấu `loi` để hiện đỏ và CHẶN nút Gửi (xem `canSend`). Một lỗi rõ
          // ràng luôn tốt hơn một thành công giả.
          setFiles((prev) => [...prev, { name: f.name, size: formatBytes(f.size), loi: true }])
        }
      }
    } else {
      setFiles((prev) => [...prev, ...arr.map((f) => ({ name: f.name, size: formatBytes(f.size) }))])
    }
  }

  // Khi THẢ tệp vào khung: bật vệt sáng chạy viền (~1.2s) rồi thêm tệp.
  const handleDrop = (list: FileList | null) => {
    setJustDropped(false)
    requestAnimationFrame(() => setJustDropped(true))
    window.setTimeout(() => setJustDropped(false), 1200)
    void addFiles(list)
  }

  const aiCompose = () => {
    // Đang gõ → bấm lần nữa để chốt ngay
    if (aiTyping) {
      stopAi()
      setBody(aiTarget)
      setAiTyping(false)
      return
    }
    const target = t('cmp.aiDraft', { cd: subject || '...' })
    stopAi()
    setBody('')
    setAiTarget(target)
    setAiTyped(0)
    setAiTyping(true)
    aiTimer.current = window.setInterval(() => {
      setAiTyped((n) => Math.min(target.length, n + 2))
    }, 18)
  }

  // Có tệp tải lên hỏng thì KHÔNG cho gửi. Gửi lúc này là gửi một bức thư thiếu
  // đúng thứ người dùng muốn gửi, mà họ vẫn nhận được thông báo 'đã gửi'.
  const coTepHong = files.some((f) => f.loi)
  const canSend = to.trim() && subject.trim() && !coTepHong

  // Một ô Cc/Bcc có thể chứa NHIỀU email ngăn bởi dấu phẩy → tách thành mảng cho backend.
  const splitAddrs = (s: string): string[] | undefined => {
    const arr = s.split(',').map((x) => x.trim()).filter(Boolean)
    return arr.length ? arr : undefined // rỗng → undefined để khỏi gửi field thừa
  }

  // #3 — gõ ô "Tới": debounce gọi danh bạ theo TOKEN CUỐI (hỗ trợ nhiều người nhận).
  const onToChange = (v: string) => {
    setTo(v)
    if (toTimer.current) window.clearTimeout(toTimer.current)
    const tok = v.split(',').pop()?.trim() ?? ''
    if (!tok) {
      setToSuggest([])
      return
    }
    toTimer.current = window.setTimeout(() => {
      api.contacts(tok).then(setToSuggest).catch(() => setToSuggest([]))
    }, 180)
  }
  const pickContact = (email: string) => {
    const parts = to.split(',')
    parts[parts.length - 1] = ` ${email}`
    setTo(parts.join(',').replace(/^\s+/, ''))
    setToSuggest([])
  }

  // #2 — gõ nội dung: debounce gọi LLM gợi ý đoạn tiếp (dựa trên tiêu đề). Tab để chèn.
  const onBodyChange = (v: string) => {
    setBody(v)
    setGhost('')
    if (ghostTimer.current) window.clearTimeout(ghostTimer.current)
    if (!apiBaseUrlDaCauHinh || !subject.trim() || v.trim().length < 4) return
    ghostTimer.current = window.setTimeout(() => {
      api.suggestCompose(subject, v).then((s) => setGhost(s.trim())).catch(() => setGhost(''))
    }, 900)
  }
  /* Ô soạn là contentEditable nên React KHÔNG tự vẽ lại nội dung theo state. Những
     chỗ đặt `body` từ bên ngoài (nhờ AI soạn, chèn gợi ý bằng Tab) sẽ đổi state mà màn
     hình đứng yên — người dùng bấm "Nhờ AI viết" rồi không thấy gì.

     Chỉ ghi khi chữ trong ô KHÁC `body`: lúc đang gõ thì hai bên luôn bằng nhau, nên
     effect không chạm vào và con trỏ không bị nhảy về đầu. */
  useEffect(() => {
    const el = oRef.current
    if (!el || el.innerText === body) return
    el.textContent = body
    setHtml(el.innerHTML)
  }, [body])

  /** Đọc lại ô soạn sau mỗi lệnh định dạng — giữ `body` (chữ thuần) và `html` khớp DOM. */
  const dongBoHtml = () => {
    const el = oRef.current
    if (!el) return
    setBody(el.innerText)
    setHtml(el.innerHTML)
  }

  const acceptGhost = () => {
    if (!ghost) return
    setBody((b) => (b && !/[\s\n]$/.test(b) ? b + ' ' : b) + ghost)
    setGhost('')
  }

  // #1 — thoát compose mà CÒN nội dung → LƯU NHÁP (không chặn việc đóng). Bấm "Bỏ nháp" thì reset trước.
  const handleOpenChange = (o: boolean) => {
    if (!o && step === 'compose' && (to.trim() || subject.trim() || body.trim()) && apiBaseUrlDaCauHinh) {
      api
        .saveDraft({
          to: to.trim(), cc: splitAddrs(cc), bcc: splitAddrs(bcc), subject, body,
          attachmentIds: files.map((f) => f.id).filter((x): x is string => !!x),
        })
        .then(() => toast('Đã lưu vào Nháp', 'success'))
        .catch(() => {})
    }
    setOpen(o)
    if (!o) setTimeout(reset, 150)
  }

  // Bấm "Xác nhận gửi": chế độ backend thật → GỬI qua Gmail rồi mới sang bước 'sent';
  // chế độ mock → chỉ chuyển bước như demo cũ. Lỗi (vd token thiếu quyền) → hiện thông báo.
  const doSend = async () => {
    if (!apiBaseUrlDaCauHinh) {
      setStep('sent')
      return
    }
    setSending(true)
    setSendError(null)
    try {
      // Danh sách tệp ĐÃ upload thành công (có id) — dùng chung cho cả hai đường gửi.
      const tepIds = files.map((f) => f.id).filter((x): x is string => !!x)
      if (replyToId) {
        // Trả lời: BE tự suy người nhận/tiêu đề/luồng từ thư gốc.
        // `tepIds` là chỗ bản trước THIẾU: tệp lên tới máy chủ, chip hiện ra bình
        // thường, mà thư trả lời đi ra không mang gì cả.
        await api.replyEmail(replyToId, body, replyAll, html, tepIds)
      } else {
        await api.sendEmail({
          to: to.trim(),
          cc: splitAddrs(cc),
          bcc: splitAddrs(bcc),
          subject,
          body,
          html,
          attachmentIds: tepIds,
        })
      }
      setStep('sent')
    } catch (e) {
      setSendError(e instanceof Error ? e.message : t('cmp.sendFail'))
    } finally {
      setSending(false)
    }
  }


  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <button
          title={t('act.compose')}
          className="flex size-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <PenSquare className="size-4" />
        </button>
      </DialogTrigger>

      <DialogContent className="max-w-2xl">
        {step === 'compose' && (
          <>
            <DialogHeader>
              {/* Tiêu đề nói đúng việc đang làm. Để "Soạn thư mới" khi đang trả lời thì
                  người dùng tưởng mình bấm nhầm, và không chắc thư có vào đúng luồng không. */}
              <DialogTitle>
                {t(replyToId ? (replyAll ? 'det.replyAll' : 'det.replySelf') : 'act.compose')}
              </DialogTitle>
            </DialogHeader>

            {/* Vùng form (chặn trình duyệt tự mở file nếu lỡ thả trượt ra ngoài khung) */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => e.preventDefault()}
              className="relative overflow-hidden rounded-xl border border-border/40"
            >

              {/* Người gửi */}
              <div className="flex items-center gap-2 border-b border-border/30 px-3.5 py-2 text-xs text-popover-foreground/60">
                <span className="text-popover-foreground/80">{t('mail.from')}</span>
                Anh Quân &lt;quanpta.meoarc@gmail.com&gt;
              </div>

              {/* Tới + Cc/Bcc toggle + autocomplete người nhận (như Gmail) */}
              <div className="relative">
                <div className="flex items-center gap-2 border-b border-border/30 px-3.5 py-2">
                  <span className="w-7 shrink-0 text-xs text-popover-foreground/60">{t('mail.to')}</span>
                  <input
                    className={fieldCls}
                    placeholder={t('mail.toPlaceholder')}
                    value={to}
                    onChange={(e) => onToChange(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Escape') setToSuggest([])
                    }}
                    onBlur={() => window.setTimeout(() => setToSuggest([]), 150)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowCc((v) => !v)}
                    className="shrink-0 rounded-md px-1.5 text-xs font-medium text-popover-foreground/60 hover:text-popover-foreground"
                  >
                    Cc/Bcc
                  </button>
                </div>
                {toSuggest.length > 0 && (
                  <div className="absolute left-9 right-3 top-full z-30 mt-1 overflow-hidden rounded-xl border border-border/50 bg-popover shadow-float">
                    {toSuggest.map((ct) => (
                      <button
                        key={ct.email}
                        type="button"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => pickContact(ct.email)}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-secondary"
                      >
                        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-active/20 text-[10px] font-semibold text-active">
                          {(ct.name || ct.email).charAt(0).toUpperCase()}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-popover-foreground">
                          {ct.name}
                          {ct.name !== ct.email && (
                            <span className="ml-1.5 text-xs text-muted-foreground">{ct.email}</span>
                          )}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {showCc && (
                <>
                  <div className="flex items-center gap-2 border-b border-border/30 px-3.5 py-2">
                    <span className="w-7 shrink-0 text-xs text-popover-foreground/60">Cc</span>
                    <input className={fieldCls} value={cc} onChange={(e) => setCc(e.target.value)} />
                  </div>
                  <div className="flex items-center gap-2 border-b border-border/30 px-3.5 py-2">
                    <span className="w-7 shrink-0 text-xs text-popover-foreground/60">Bcc</span>
                    <input className={fieldCls} value={bcc} onChange={(e) => setBcc(e.target.value)} />
                  </div>
                </>
              )}

              {/* Chủ đề */}
              <div className="border-b border-border/30 px-3.5 py-2">
                <input
                  className={`${fieldCls} font-medium`}
                  placeholder={t('mail.subject')}
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                />
              </div>

              {/* Thanh định dạng */}
              <div className="flex items-center gap-0.5 border-b border-border/30 px-2 py-1">
                <ToolbarBtn icon={Bold} nhan={t('cmp.bold')} lenh="bold" onXong={dongBoHtml} />
                <ToolbarBtn icon={Italic} nhan={t('cmp.italic')} lenh="italic" onXong={dongBoHtml} />
                <ToolbarBtn icon={Underline} nhan={t('cmp.underline')} lenh="underline" onXong={dongBoHtml} />
                <span className="mx-1 h-5 w-px bg-border/40" />
                <ToolbarBtn icon={List} nhan={t('cmp.bullets')} lenh="insertUnorderedList" onXong={dongBoHtml} />
                <ToolbarBtn icon={Link2} nhan={t('cmp.link')} lenh="createLink" onXong={dongBoHtml} />
                {/* Màu chữ dùng ô chọn màu của trình duyệt — không tự dựng bảng màu,
                    và người dùng đã quen cái này ở mọi ứng dụng khác. */}
                <label
                  title={t('cmp.color')}
                  className="flex size-8 cursor-pointer items-center justify-center rounded-lg text-popover-foreground/60 transition-colors hover:bg-popover-foreground/10 hover:text-popover-foreground"
                >
                  <Palette className="size-4" />
                  <input
                    type="color"
                    className="sr-only"
                    onMouseDown={(e) => e.preventDefault()}
                    onChange={(e) => {
                      document.execCommand('foreColor', false, e.target.value)
                      dongBoHtml()
                    }}
                  />
                </label>
                <ToolbarBtn icon={RemoveFormatting} nhan={t('cmp.clearFormat')} lenh="removeFormat" onXong={dongBoHtml} />
                <button
                  type="button"
                  onClick={aiCompose}
                  className={cn(
                    'ml-auto flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium text-popover-foreground transition-colors',
                    aiTyping ? 'bg-active/30' : 'bg-active/20 hover:bg-active/30',
                  )}
                >
                  <Sparkles className={cn('size-3.5 text-active', aiTyping && 'animate-pulse')} />
                  {t(aiTyping ? 'cmp.aiTyping' : 'cmp.aiWrite')}
                </button>
              </div>

              {/* Nội dung — khi AI đang soạn: hiện chữ gõ dần + ghost text + con trỏ bokeh */}
              {aiTyping ? (
                <div
                  className={`${fieldCls} min-h-44 whitespace-pre-wrap px-3.5 py-3 leading-relaxed`}
                  aria-live="polite"
                >
                  <span>{aiTarget.slice(0, aiTyped)}</span>
                  <span
                    className="mx-px inline-block h-4 w-0.5 -translate-y-0.5 animate-pulse rounded-full bg-active align-middle"
                    style={{ boxShadow: '0 0 8px 1px var(--active)' }}
                  />
                  <span className="text-popover-foreground/30">{aiTarget.slice(aiTyped)}</span>
                </div>
              ) : (
                <div>
                  <div
                    ref={oRef}
                    contentEditable
                    suppressContentEditableWarning
                    role="textbox"
                    aria-multiline="true"
                    aria-label={t('mail.bodyPlaceholder')}
                    data-rong={body.length === 0 || undefined}
                    className={`${fieldCls} o-soan min-h-44 px-3.5 py-3 leading-relaxed`}
                    onInput={(e) => {
                      const el = e.currentTarget
                      // Giữ HAI bản song song: `body` là chữ thuần (Smart Compose và
                      // gợi ý đều làm việc trên chữ), `html` là bản có định dạng để gửi.
                      onBodyChange(el.innerText)
                      setHtml(el.innerHTML)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Tab' && ghost) {
                        e.preventDefault()
                        acceptGhost()
                      }
                    }}
                  />
                </div>
              )}

              {/* #2 — Smart Compose: gợi ý đoạn tiếp theo (bấm hoặc nhấn Tab để chèn) */}
              {ghost && !aiTyping && (
                <button
                  type="button"
                  onClick={acceptGhost}
                  className="flex w-full items-start gap-2 border-t border-border/30 px-3.5 py-2 text-left transition-colors hover:bg-secondary/40"
                >
                  <Sparkles className="mt-0.5 size-3.5 shrink-0 text-active" />
                  <span className="min-w-0 flex-1 text-xs">
                    <span className="italic text-popover-foreground/70">{ghost}</span>
                    <span className="ml-1.5 whitespace-nowrap text-[10px] uppercase tracking-wide text-muted-foreground/60">
                      — Tab để chèn
                    </span>
                  </span>
                </button>
              )}

              {/* Tệp đính kèm */}
              {files.length > 0 && (
                <div className="flex flex-wrap gap-2 border-t border-border/30 px-3.5 py-2.5">
                  {files.map((f, i) => (
                    <span
                      key={i}
                      title={f.loi ? t('cmp.uploadFail') : undefined}
                      className={cn(
                        'flex items-center gap-2 rounded-lg py-1 pl-2 pr-1 text-xs text-popover-foreground',
                        // Tệp hỏng phải TRÔNG KHÁC. Bản trước nó giống hệt tệp thành công,
                        // nên người dùng không có cách nào biết nó sẽ không đi kèm thư.
                        f.loi
                          ? 'bg-destructive/15 ring-1 ring-destructive/50'
                          : 'bg-popover-foreground/10',
                      )}
                    >
                      <span className={cn(
                        'rounded px-1 text-[9px] font-bold uppercase text-popover-foreground',
                        f.loi ? 'bg-destructive/40' : 'bg-active/20',
                      )}>
                        {f.loi ? 'lỗi' : f.name.split('.').pop()}
                      </span>
                      <span className="max-w-[160px] truncate">{f.name}</span>
                      <span className="text-popover-foreground/50">
                        {f.loi ? t('cmp.notUploaded') : f.size}
                      </span>
                      <button
                        type="button"
                        onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                        className="flex size-5 items-center justify-center rounded text-popover-foreground/50 hover:bg-popover-foreground/10 hover:text-popover-foreground"
                      >
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Khung kéo–thả tệp "xịn": glow khi rê vào · viền chạy sáng khi thả */}
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  fileRef.current?.click()
                }
              }}
              onDragOver={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setDragging(true)
              }}
              onDragLeave={(e) => {
                e.preventDefault()
                setDragging(false)
              }}
              onDrop={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setDragging(false)
                handleDrop(e.dataTransfer.files)
              }}
              className={cn('drop-zone', dragging && 'is-dragging', justDropped && 'border-run')}
            >
              <UploadCloud className={cn('dz-icon size-7', dragging && 'text-active')} />
              <span className="text-sm font-medium">
                {t(dragging ? 'cmp.dropNow' : 'cmp.dropHere')}
              </span>
              <span className="text-xs text-muted-foreground">{t('mail.orBrowse')}</span>
            </div>

            <input
              ref={fileRef}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
            />

            <DialogFooter className="sm:justify-between">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  title={t('act.attach')}
                  className="flex size-9 items-center justify-center rounded-xl text-popover-foreground/60 transition-colors hover:bg-popover-foreground/10 hover:text-popover-foreground"
                >
                  <Paperclip className="size-4" />
                </button>
                {files.length > 0 && (
                  <span className="flex items-center gap-1 text-xs text-popover-foreground/60">
                    <Files className="size-3.5" />
                    {files.length}
                  </span>
                )}
                <button
                  type="button"
                  onClick={reset}
                  title={t('act.discardDraft')}
                  className="flex size-9 items-center justify-center rounded-xl text-popover-foreground/60 transition-colors hover:bg-popover-foreground/10 hover:text-popover-foreground"
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
              <Button variant="primary" disabled={!canSend} onClick={() => setStep('confirm')}>
                <Send className="size-4" />
                Gửi
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'confirm' && (
          <>
            <DialogHeader>
              <DialogTitle>{t('mail.confirmSend')}</DialogTitle>
            </DialogHeader>
            <div className="space-y-2 rounded-xl bg-popover-foreground/5 p-3.5 text-sm text-popover-foreground">
              <p>
                <span className="text-popover-foreground/60">{t('mail.toLabel')}</span> {to}
              </p>
              {cc && (
                <p>
                  <span className="text-popover-foreground/60">Cc:</span> {cc}
                </p>
              )}
              <p>
                <span className="text-popover-foreground/60">{t('mail.subjectLabel')}</span> {subject}
              </p>
              <p className="flex items-center gap-1.5 text-popover-foreground/70">
                <Paperclip className="size-3.5" />
                {files.length} tệp đính kèm
              </p>
            </div>
            {sendError && (
              <p className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {sendError}
              </p>
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setStep('compose')} disabled={sending}>
                <ArrowLeft className="size-4" />
                Quay lại
              </Button>
              <Button variant="primary" onClick={doSend} disabled={sending}>
                <Send className="size-4" />
                {t(sending ? 'cmp.sending' : 'cmp.confirmSend')}
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'sent' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckCircle2 className="size-5 text-success" />
                Đã gửi thư
              </DialogTitle>
            </DialogHeader>
            {/* Hiệu ứng gửi: máy bay giấy bay đi + gợn sóng xác nhận */}
            <div className="relative mx-auto my-1 flex size-16 items-center justify-center">
              <span className="send-ripple absolute inset-0 rounded-full" />
              <Send className="send-plane size-7 text-active" />
            </div>
            <p className={cn('text-sm text-popover-foreground/75')}>
              {t('cmp.sentTo', {
                ai: to,
                kem: files.length ? t('cmp.withFiles', { n: files.length }) : '',
              })}
            </p>
            <DialogFooter>
              <Button variant="primary" onClick={() => setOpen(false)}>
                Đóng
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
