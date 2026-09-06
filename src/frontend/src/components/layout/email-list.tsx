import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import {
  Search,
  Star,
  Paperclip,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  X,
  SearchX,
  Check,
  MailOpen,
  Mail,
  Tag,
  Trash2,
  CheckSquare,
  Square,
  Archive,
  ChevronDown,
  ChevronUp,
  Inbox,
  Send,
  SquarePen,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { t } from '@/lib/ngon-ngu'
import { Input } from '@/components/ui/input'
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
import { ComposeDialog } from '@/components/layout/compose-dialog'
import { MailboxChrome } from '@/components/layout/mailbox-chrome'
import { SenderAvatar } from '@/components/layout/sender-avatar'
import { MeoMascot } from '@/components/meo-mascot'
import { useToast } from '@/components/ui/toast'
import { emailHaystack, interpretNL, matchText } from '@/lib/search'
import type { EmailActions } from '@/lib/email-actions'
import { CATEGORY, CATEGORY_OPTIONS } from '@/data/categories'
import type { Category, Email, TaskStatus } from '@/data/emails'

/** Thanh tag danh mục = 'Tất cả' + ĐỦ 7 nhãn (nguồn duy nhất: CATEGORY_OPTIONS).
 *  Render dạng flex-wrap 2 hàng → thấy hết tag ngay, không phải kéo ngang tìm. */
const dsFilters = (): { key: Category | 'all'; label: string }[] => [
  { key: 'all', label: t('flt.all') },
  ...CATEGORY_OPTIONS,
]

/* Chip trạng thái việc (PA1 §4.2.9: Todo / Waiting / Done).
   Hiển thị theo STATUS chứ không theo priority: người dùng cần biết "phải làm gì"
   trước khi cần biết "gấp cỡ nào". Độ gấp thể hiện bằng sắc thái chip bên dưới. */
const chipTrangThai = (): Record<TaskStatus, { label: string; cls: string; dot: string }> => ({
  Todo: { label: t('flt.action'), cls: 'bg-spark/20 text-foreground', dot: 'cherry-dot' },
  Waiting: { label: t('flt.waiting'), cls: 'bg-active/20 text-foreground', dot: 'bg-active' },
  Done: { label: t('flt.done'), cls: 'bg-muted/40 text-muted-foreground', dot: 'bg-muted-foreground/60' },
})

/* Ưu tiên Cao được nhấn thêm; Medium/Low giữ nguyên nền chip để danh sách không
   biến thành một bức tường màu đỏ. */
const HIGH_RING = 'ring-1 ring-spark/50'

const dsQuick = () => [
  { key: 'unread', label: t('flt.unread') },
  { key: 'starred', label: t('act.star') },
  { key: 'attachment', label: t('flt.attach') },
] as const
type QuickKey = ReturnType<typeof dsQuick>[number]['key']

function CardAction({
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
    <span
      role="button"
      tabIndex={-1}
      title={title}
      aria-label={title}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className={cn(
        'flex size-7 cursor-pointer items-center justify-center rounded-lg text-muted-foreground transition-colors active:scale-90',
        danger
          ? 'hover:bg-destructive hover:text-destructive-foreground'
          : 'hover:bg-secondary hover:text-foreground',
      )}
    >
      <Icon className="size-3.5" />
    </span>
  )
}

function IconBtn({
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
      title={title}
      onClick={onClick}
      className={cn(
        'flex size-9 items-center justify-center rounded-xl transition-colors',
        danger
          ? 'text-muted-foreground hover:bg-destructive hover:text-destructive-foreground'
          : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
      )}
    >
      <Icon className="size-4" />
    </button>
  )
}

function EmailCard({
  email,
  selected,
  checked,
  selectionActive,
  kbActive,
  index,
  onSelect,
  onToggleCheck,
  onArchive,
  onStar,
  onDelete,
  onRestore,
  trongThungRac,
}: {
  email: Email
  selected: boolean
  checked: boolean
  selectionActive: boolean
  kbActive: boolean
  index: number
  onSelect: () => void
  onToggleCheck: () => void
  onArchive: () => void
  onStar: () => void
  onDelete: () => void
  /** Đang ở Thùng rác → đổi bộ nút nhanh. "Xoá" ở đây vô nghĩa (thư đã ở thùng rác
   *  rồi) còn thứ người ta cần là lấy lại — mà trước đây KHÔNG có nút nào làm được. */
  onRestore?: () => void
  trongThungRac?: boolean
}) {
  const c = CATEGORY[email.category]
  // Nền thẻ HẠ RẤT SÂU (từ 35 ≈ 21% xuống 14 ≈ 8%).
  // Nền tô đậm biến thẻ thành khối kẹo pastel: nó HÚT ánh sáng. Neon cần ngược lại —
  // ruột gần như tối, còn màu dồn hết ra viền và vạch bên trái để PHÁT ra.
  const cardStyle: CSSProperties = {
    backgroundImage: `linear-gradient(135deg, ${c.bar}14, transparent 62%)`,
  }
  ;(cardStyle as Record<string, string>)['--tint'] = c.bar

  return (
    <button
      onClick={onSelect}
      data-idx={index}
      style={cardStyle}
      className={cn(
        // ĐÃ BỎ `ripe` và `bloom-hover`. `ripe` là lớp "bề mặt mọng" thời cũ
        // (specular gắt + ánh đỏ thấu từ trong) — chính nó khiến thẻ thư trông
        // như kẹo mềm ở bản sáng. `bloom-hover` thì thừa: `neon-edge` khi rê
        // chuột đã lo phần quầng sáng, mà nó lại chiếm `::before` — chỗ mà viền
        // ngũ sắc bên dưới cần dùng.
        'goc-cat group relative w-full overflow-hidden p-4 pl-5 text-left transition-all duration-300 ease-soft glass active:scale-[0.99]',
        // VIỀN NGŨ SẮC CHO THƯ CHƯA ĐỌC. Vừa là chữ ký thị giác, vừa mang thông
        // tin: dải phổ chạy vòng quanh thẻ = thư còn "sống", chưa ai đụng tới.
        // Chỉ gắn cho thư chưa đọc nên số thẻ chạy animation luôn nhỏ — nếu rải
        // cho mọi thẻ thì vừa mất nghĩa vừa nặng máy.
        email.unread && 'vien-ngu-sac',
        selected
          ? 'shadow-[inset_0_4px_12px_rgba(0,0,0,0.35)] bg-black/20 border-t border-black/30 border-b border-white/5 scale-[0.995]'
          : kbActive
            // Đang chọn bằng bàn phím = cấp 3, sáng nhất. Chỉ MỘT thẻ tại một
            // thời điểm — đó là lý do cấp này được phép rực đến vậy.
            ? 'den-vien-chon'
            // NGHỈ giờ là CẤP 1, không còn `border-white/[0.04]` gần như tàng hình.
            // Thẻ thư là đơn vị nội dung chính của cả ứng dụng; để nó không có
            // cạnh nào bắt sáng thì mọi thứ khác phát sáng cũng vô nghĩa — mắt
            // không có gì để so. Rê chuột lên cấp 2: sáng thêm và bắt đầu toả.
            : 'den-vien hover:-translate-y-0.5',
      )}
    >
      <span
        aria-hidden
        className="absolute inset-y-0 left-0 w-1 rounded-r-full"
        style={{
          backgroundColor: c.bar,
          backgroundImage: 'linear-gradient(180deg, rgba(255,255,255,0.45), transparent 45%)',
        }}
      />

      {!selectionActive && (
        <span className="absolute right-2 top-2 z-10 hidden items-center gap-0.5 rounded-lg bg-popover/85 p-0.5 shadow-subtle backdrop-blur-sm group-hover:flex">
          {trongThungRac ? (
            /* Trong Thùng rác thì chỉ còn một việc đáng làm: lấy thư về. */
            <CardAction icon={RotateCcw} title={t('act.restore')} onClick={() => onRestore?.()} />
          ) : (
            <>
              <CardAction icon={Archive} title={t('act.archive')} onClick={onArchive} />
              <CardAction icon={Star} title={t('act.important')} onClick={onStar} />
              <CardAction icon={Trash2} title={t('act.delete')} danger onClick={onDelete} />
            </>
          )}
        </span>
      )}

      <div className="flex items-start gap-3.5">
        <div className="relative size-9 shrink-0">
          <SenderAvatar
            email={email.senderEmail}
            initial={email.senderInitial}
            className="gloss size-9 shrink-0 rounded-full font-mono text-sm font-semibold ring-1 ring-inset"
            style={
              {
                backgroundColor: 'rgba(251, 240, 226, 0.92)',
                color: c.ink,
                ['--tw-ring-color' as string]: c.bar,
              } as CSSProperties
            }
          />
          <span
            role="checkbox"
            aria-checked={checked}
            onClick={(e) => {
              e.stopPropagation()
              onToggleCheck()
            }}
            className={cn(
              'absolute inset-0 flex cursor-pointer items-center justify-center rounded-full transition-opacity',
              checked || selectionActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
            )}
          >
            <span
              className={cn(
                'flex size-9 items-center justify-center rounded-full ring-1 ring-inset',
                checked
                  ? 'bg-active text-active-foreground ring-transparent'
                  : 'bg-popover/80 text-transparent ring-border backdrop-blur-sm',
              )}
            >
              <Check className="size-4" />
            </span>
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                'truncate font-serif tracking-wide text-[14.5px]',
                email.unread ? 'font-bold text-foreground' : 'font-medium text-foreground/80',
              )}
            >
              {email.sender}
            </span>
            <span className="ml-auto shrink-0 text-xs font-mono text-muted-foreground/70">{email.time}</span>
          </div>

          <div className="mt-1 flex items-center gap-1.5">
            {email.unread && <span className="cherry-dot size-1.5 shrink-0 rounded-full" />}
            <span
              className={cn(
                'truncate text-sm tracking-tight',
                email.unread ? 'font-medium text-foreground' : 'text-muted-foreground',
              )}
            >
              {email.subject}
            </span>
            {/* Kẹp giấy — dấu hiệu DUY NHẤT cho biết thư có tệp mà không phải mở ra.
                Thiếu nó thì người gửi bảo "mình gửi file rồi" mà nhìn hộp thư không
                thấy gì, và người nhận kết luận là app làm mất tệp. */}
            {(email.hasAttachment || (email.attachments?.length ?? 0) > 0) && (
              <Paperclip
                className="ml-auto size-3.5 shrink-0 text-muted-foreground"
                aria-label={t('mail.hasAttachment')}
              />
            )}
            {email.starred && (
              <Star
                className={cn('size-3.5 shrink-0', !(email.hasAttachment || email.attachments?.length) && 'ml-auto')}
                style={{ fill: c.bar, color: c.bar }}
              />
            )}
          </div>

          <p className="mt-1 truncate text-xs text-muted-foreground/80 leading-relaxed">{email.preview}</p>

          {(email.label || email.status) && (
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              {email.status && (
                <span
                  title={email.priority ? t('mail.prioTitle', { muc: email.priority }) : undefined}
                  className={cn(
                    'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                    chipTrangThai()[email.status].cls,
                    email.priority === 'High' && HIGH_RING,
                  )}
                >
                  <span className={cn('size-1.5 rounded-full', chipTrangThai()[email.status].dot)} />
                  {chipTrangThai()[email.status].label}
                </span>
              )}
              {email.label && (
                <span
                  className="inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
                  style={{ backgroundColor: `color-mix(in srgb, ${c.soft} 40%, transparent)`, color: c.ink }}
                >
                  {email.label}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </button>
  )
}

const MIN_W = 300
const MAX_W = 560
const DEFAULT_W = 384
const WIDTH_KEY = 'meoarc:listWidth'
const clampW = (n: number) => Math.min(MAX_W, Math.max(MIN_W, Math.round(n)))

/** Icon đại diện thư mục — chữ "Hộp" trong "Hộp thư" được THAY bằng icon
 *  trong lockup thương hiệu (icon × serif), các folder khác đổi icon theo. */
const FOLDER_ICONS: Record<string, React.ElementType> = {
  inbox: Inbox,
  starred: Star,
  sent: Send,
  drafts: SquarePen,
  archive: Archive,
  trash: Trash2,
}

const FOLDER_TITLES: Record<string, string> = {
  inbox: 'fld.inbox',
  starred: 'fld.starred',
  sent: 'fld.sent',
  drafts: 'fld.drafts',
  archive: 'fld.archive',
  trash: 'fld.trash',
}

export function EmailList({
  emails,
  folder = 'inbox',
  openedId,
  onOpen,
  actions,
  onSearch,
  onLoadMore,
  loadingMore,
  onRefresh,
  refreshing,
  elegant = false,
  fill = false,
  loi,
}: {
  emails: Email[]
  folder?: string
  openedId: string | null
  onOpen: (id: string) => void
  actions: EmailActions
  onSearch?: (q: string) => void
  onLoadMore?: () => void
  loadingMore?: boolean
  onRefresh?: () => void
  refreshing?: boolean
  /** AI tắt → dùng khung header thanh lịch (dải sơn + "HỘP THƯ") thay poster Desert Rose. */
  elegant?: boolean
  /** Chiếm trọn bề ngang (flex-1) thay vì cột cố định — khi AI tắt và chưa mở thư. */
  fill?: boolean
  /** Lỗi nạp thư. Có giá trị = hiện thẳng ra thay vì để danh sách trống không lời giải thích. */
  loi?: string | null
}) {
  const [filter, setFilter] = useState<Category | 'all'>('all')
  const [query, setQuery] = useState('')
  const [nlMode, setNlMode] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  // Thanh tag RÚT GỌN (chip overflow): mặc định chỉ 3 chip + chip "+N" búng ra đủ 8.
  const [tagsOpen, setTagsOpen] = useState(false)
  // Ô tìm kiếm THU GỌN: mặc định chỉ là nút icon, bấm mới bung field → header gọn.
  const [searchOpen, setSearchOpen] = useState(false)
  const [quick, setQuick] = useState<Record<QuickKey, boolean>>({
    unread: false,
    starred: false,
    attachment: false,
  })

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [labelOpen, setLabelOpen] = useState(false)
  const [deleteIds, setDeleteIds] = useState<string[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [kbActive, setKbActive] = useState(-1)
  const listRef = useRef<HTMLDivElement>(null)
  const toast = useToast()

  const sectionRef = useRef<HTMLElement>(null)
  const dragging = useRef(false)
  const [width, setWidth] = useState<number>(() => {
    const saved = Number(localStorage.getItem(WIDTH_KEY))
    return Number.isFinite(saved) && saved >= MIN_W && saved <= MAX_W ? saved : DEFAULT_W
  })
  useEffect(() => {
    localStorage.setItem(WIDTH_KEY, String(width))
  }, [width])

  const startDrag = (e: React.PointerEvent) => {
    dragging.current = true
    e.currentTarget.setPointerCapture(e.pointerId)
    document.body.style.userSelect = 'none'
  }
  const onDrag = (e: React.PointerEvent) => {
    if (!dragging.current || !sectionRef.current) return
    const left = sectionRef.current.getBoundingClientRect().left
    setWidth(clampW(e.clientX - left))
  }
  const endDrag = (e: React.PointerEvent) => {
    dragging.current = false
    e.currentTarget.releasePointerCapture?.(e.pointerId)
    document.body.style.userSelect = ''
  }

  const refresh = () => {
    if (onRefresh) {
      onRefresh()
      return
    }
    setLoading(true)
    window.setTimeout(() => setLoading(false), 700)
  }

  // Mở/đóng ô tìm kiếm. Đóng thì XOÁ luôn từ khoá để không còn "lọc ẩn" khi field
  // đã thu lại (tránh user tưởng đang xem full hộp thư mà thực ra vẫn đang lọc).
  const toggleSearch = () => {
    if (searchOpen) {
      setSearchOpen(false)
      setQuery('')
    } else {
      setSearchOpen(true)
    }
  }
  // Field vừa bung → focus ngay cho gõ liền (element mount có điều kiện nên focus
  // trong effect sau khi DOM cập nhật).
  useEffect(() => {
    if (searchOpen) document.getElementById('meoarc-search')?.focus()
  }, [searchOpen])

  const serverMode = !!onSearch
  const FolderIcon = FOLDER_ICONS[folder] ?? Inbox
  // Màu 2 khung (header "Thư" + khung dưới danh sách mail) — PHẲNG, không hiệu ứng.
  // Lấy từ token --sc-base để đổi theo theme, không hardcode màu nữa.
  const frameColor = 'var(--sc-base)'
  const nl = nlMode && query.trim() ? interpretNL(query) : null

  const firstSearch = useRef(true)
  useEffect(() => {
    if (!serverMode) return
    if (firstSearch.current) {
      firstSearch.current = false
      return
    }
    const t = window.setTimeout(() => onSearch?.(query.trim()), 450)
    return () => window.clearTimeout(t)
  }, [query, serverMode])

  const folderEmails = useMemo(
    () =>
      emails.filter((e) => {
        const f = e.folder ?? 'inbox'
        if (folder === 'starred') return e.starred && f !== 'trash'
        return f === folder
      }),
    [emails, folder],
  )

  /** Số thư chưa đọc trong thư mục hiện tại — thay cho dòng "MEOARC MAIL" cũ. */
  const soChuaDoc = useMemo(() => emails.filter((e) => e.unread).length, [emails])

  const results = useMemo(() => {
    const text = nl ? nl.text : query
    return folderEmails.filter((e) => {
      if (filter !== 'all' && e.category !== filter) return false
      if ((quick.unread || nl?.unread) && !e.unread) return false
      if ((quick.starred || nl?.starred) && !e.starred) return false
      if ((quick.attachment || nl?.attachment) && !e.attachments?.length) return false
      if (!serverMode && text.trim() && !matchText(emailHaystack(e), text)) return false
      return true
    })
  }, [folderEmails, filter, query, nlMode, quick])


  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const el = document.activeElement as HTMLElement | null
      const typing =
        !!el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
      if (e.key === '/' && !typing) {
        e.preventDefault()
        setSearchOpen(true) // mở field nếu đang thu gọn
        requestAnimationFrame(() => document.getElementById('meoarc-search')?.focus())
        return
      }
      if (typing) return
      if (e.key === 'j') {
        e.preventDefault()
        setKbActive((i) => Math.min(results.length - 1, i + 1))
      } else if (e.key === 'k') {
        e.preventDefault()
        setKbActive((i) => Math.max(0, (i < 0 ? 0 : i) - 1))
      } else if (e.key === 'Enter') {
        if (kbActive >= 0 && results[kbActive]) onOpen(results[kbActive].id)
      } else if (e.key === 'Escape') {
        setKbActive(-1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [results, kbActive, onOpen])

  useEffect(() => {
    if (kbActive >= results.length) setKbActive(results.length ? results.length - 1 : -1)
  }, [results.length, kbActive])
  useEffect(() => {
    if (kbActive < 0) return
    const node = listRef.current?.querySelector(`[data-idx="${kbActive}"]`) as HTMLElement | null
    node?.scrollIntoView({ block: 'nearest' })
  }, [kbActive])

  const quickRestore = (id: string) => {
    actions.restoreEmails([id])
    toast(t('toast.restoredOne'), 'success')
  }
  const quickArchive = (id: string) => {
    actions.removeEmails([id], 'archive')
    toast('Đã lưu trữ thư', 'success')
  }
  const quickStar = (e: Email) => {
    actions.setImportant([e.id], !e.starred)
    toast(t(e.starred ? 'toast.unstarred' : 'toast.starred'), 'success')
  }

  const isFiltering =
    !!query.trim() || filter !== 'all' || quick.unread || quick.starred || quick.attachment

  // Chip hiển thị khi THU GỌN: 3 chip đầu; nếu tag đang chọn nằm trong nhóm ẩn
  // thì trồi nó lên thay chip cuối → không bao giờ "mất dấu" filter đang áp.
  const COLLAPSED_TAGS = 3
  const shownFilters = useMemo(() => {
    const FILTERS = dsFilters()
    if (tagsOpen) return FILTERS
    const base = FILTERS.slice(0, COLLAPSED_TAGS)
    if (base.some((f) => f.key === filter)) return base
    const active = FILTERS.find((f) => f.key === filter)
    return active ? [...FILTERS.slice(0, COLLAPSED_TAGS - 1), active] : base
  }, [tagsOpen, filter])

  const clearAll = () => {
    setQuery('')
    setFilter('all')
    setQuick({ unread: false, starred: false, attachment: false })
  }

  const ids = Array.from(selected)
  const clearSel = () => setSelected(new Set())
  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const allSelected = results.length > 0 && results.every((e) => selected.has(e.id))
  const toggleSelectAll = () =>
    setSelected(allSelected ? new Set() : new Set(results.map((e) => e.id)))

  const doMarkRead = (read: boolean) => {
    actions.markRead(ids, read)
    toast(t(read ? 'toast.markedRead' : 'toast.markedUnread', { n: ids.length }), 'success')
    clearSel()
  }
  const doImportant = () => {
    actions.setImportant(ids, true)
    toast(t('toast.markedImportant', { n: ids.length }), 'success')
    clearSel()
  }
  const doDelete = () => {
    if (!deleteIds) return
    const n = deleteIds.length
    actions.removeEmails(deleteIds, 'delete')
    setDeleteIds(null)
    toast(t('toast.deleted', { n }), 'destructive')
    clearSel()
  }

  // Tiêu đề khung thanh lịch (AI tắt) + khay công cụ dùng CHUNG cho 2 kiểu header.
  const elegantTitle = t(folder === 'inbox' ? 'fld.inbox' : (FOLDER_TITLES[folder] ?? 'fld.inbox'))
  const renderToolbar = (tone: 'poster' | 'elegant') => {
    const base = 'flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors'
    const on = tone === 'poster' ? 'bg-[var(--sc-ink)] text-[var(--sc-base)]' : 'bg-foreground text-background'
    const off =
      tone === 'poster'
        ? 'text-[var(--sc-ink)]/60 hover:bg-foreground/[0.07] hover:text-[var(--sc-ink)]'
        : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
    return (
      <div className="flex items-center gap-0.5">
        <button
          title={t(searchOpen ? 'mail.closeSearch' : 'mail.searchTitle')}
          aria-label={t('mail.toggleSearch')}
          onClick={toggleSearch}
          className={cn(base, searchOpen || query ? on : off)}
        >
          <Search className="size-3.5" />
        </button>
        <ComposeDialog />
        <button
          title={t('act.refresh')}
          aria-label={t('mail.refreshBox')}
          onClick={refresh}
          className={cn(base, off)}
        >
          <RefreshCw className={cn('size-3.5', (loading || refreshing) && 'animate-spin')} />
        </button>
        <button
          title={t('act.filter')}
          onClick={() => setShowFilters((v) => !v)}
          className={cn(base, showFilters ? on : off)}
        >
          <SlidersHorizontal className="size-3.5" />
        </button>
      </div>
    )
  }

  return (
    <section
      ref={sectionRef}
      style={fill ? { backgroundColor: frameColor } : { width, backgroundColor: frameColor }}
      className={cn(
        'relative z-10 flex h-full flex-col transition-all duration-300',
        fill ? 'min-w-0 flex-1' : 'shrink-0',
      )}
    >
      {/* [OLD MONEY FIX] Đã xóa bỏ hoàn toàn dải sơn chảy rớt cờ Pháp để tránh tranh chấp visual */}

      {/* Header "Hộp thư" — poster editorial: nền và chữ lấy từ token --sc-base/--sc-ink
          nên tự đổi theo theme (tím đêm ở dark, trời lam tím ở light).
          CÔNG CỤ dồn hết lên hàng đầu (search + soạn/làm
          mới/lọc), tag bên dưới; wordmark "Hộp thư" giờ chạy DỌC theo line phân
          tách với panel chat (khối riêng ngay dưới header). Mèo lang thang đậu
          được lên mép dưới (data-cat-perch). */}
      {/* Header TRONG SUỐT — hiện màu phẳng của <section> (frameColor), KHÔNG hiệu
          ứng. Header và khung dưới danh sách mail đồng màu; chỉ khối mail inset
          giữ màu riêng. */}
      {/* AI TẮT → khung header thanh lịch "HỘP THƯ" (dải sơn polygon) thay poster Desert Rose. */}
      {elegant && <MailboxChrome title={elegantTitle} right={renderToolbar('elegant')} />}
      <header
        data-cat-perch="bottom"
        className={cn('relative flex flex-col gap-3.5 px-6 pb-4', elegant ? 'pt-4' : 'pt-5')}
      >
        {/* Thanh đầu cột Hộp thư — CHỈ khi AI đang bật (Hộp thư ở cột giữa).
            Bản cũ là "lockup poster": ô vuông đặc đổ bóng nặng + tiêu đề serif 26px
            + dòng "MEOARC MAIL" bên dưới — ngôn ngữ của bìa tạp chí. Đẹp, nhưng nó
            là thứ đầu tiên trong cột và nó nói sai về sản phẩm.

            Bản này nói đúng thứ đang chạy: nhãn kỹ thuật + SỐ THƯ CHƯA ĐỌC dạng
            monospace (số là thông tin, "MEOARC MAIL" thì không — người dùng biết
            thừa họ đang ở đâu) + chấm nhịp báo hệ thống còn sống. */}
        {!elegant && (
          <div className="flex items-center justify-between">
            <div className="flex min-w-0 items-center gap-2.5">
              <span className="neon-edge flex size-9 shrink-0 items-center justify-center rounded-xl text-[var(--spark)]"
                style={{ ['--tint' as string]: 'var(--spark)' }}>
                <FolderIcon className="size-[17px]" strokeWidth={2} />
              </span>
              <div className="min-w-0 leading-none">
                <div className="flex items-baseline gap-2">
                  <p className="truncate text-[19px] font-semibold leading-none tracking-tight text-foreground">
                    {folder === 'inbox' ? t('mail.colTitle') : t(FOLDER_TITLES[folder] ?? 'mail.colTitle')}
                  </p>
                  {soChuaDoc > 0 && (
                    <span className="font-mono text-[12px] tabular-nums text-[var(--spark)]">
                      {String(soChuaDoc).padStart(2, '0')}
                    </span>
                  )}
                </div>
                <p className="mt-1.5 flex items-center gap-1.5 text-[9px] font-medium uppercase tracking-[0.22em] text-muted-foreground/60">
                  <span className="pulse-dot" aria-hidden />
                  {soChuaDoc > 0 ? t('mail.unreadCount', { n: soChuaDoc }) : t('mail.allRead')}
                </p>
              </div>
            </div>
            {renderToolbar('poster')}
          </div>
        )}

        {/* Khung tìm kiếm pha lê — THU GỌN: chỉ hiện khi bấm nút search (làm gọn
            header). Bung có animation; Esc trong ô để đóng nhanh. */}
        {searchOpen && (
        <div className="relative duration-200 animate-in fade-in slide-in-from-top-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 z-10 size-4 -translate-y-1/2 text-foreground/40" />
          <Input
            id="meoarc-search"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') toggleSearch()
            }}
            placeholder={
              serverMode
                ? t('mail.phGmail')
                : nlMode
                  ? t('mail.phNl')
                  : t('mail.phPlain')
            }
            className="den-vien bg-gradient-to-b from-foreground/[0.06] to-foreground/[0.02] pl-9 pr-10 text-foreground rounded-xl placeholder:text-foreground/40 backdrop-blur-xl focus-visible:den-vien-cham"
          />
          <button
            onClick={() => setNlMode((v) => !v)}
            title={t(nlMode ? 'mail.nlOff' : 'mail.nlOn')}
            className={cn(
              'absolute right-2 top-1/2 z-10 flex size-7 -translate-y-1/2 items-center justify-center rounded-lg transition-colors',
              nlMode ? 'bg-active text-active-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Sparkles className="size-4" />
          </button>
        </div>
        )}

        {/* Tag danh mục — pattern "chip overflow" gọn không gian: 1 hàng 3 chip +
            chip "+N" viền đứt búng ra đủ 8, bấm lại thu gọn (msg-pop khi mở). */}
        <div className={cn('flex flex-wrap items-center gap-1.5', tagsOpen && 'duration-300 animate-in fade-in slide-in-from-top-1')}>
          {shownFilters.map((f) => {
            const active = filter === f.key
            // Chip mang MÀU CATEGORY thật (nguồn: CATEGORY[].bar): nền tint mờ +
            // viền cùng màu; đang chọn → tint đậm hơn + viền đặc + đổ bóng.
            // Chữ luôn dùng --foreground (kem) vì tint trên nền mận vẫn tối đủ.
            const c = f.key === 'all' ? null : CATEGORY[f.key]
            return (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className={cn(
                  'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-serif tracking-wide transition-all duration-300 active:scale-95',
                  c
                    ? active
                      ? 'font-semibold text-foreground shadow-md'
                      : 'text-foreground/80 hover:text-foreground hover:brightness-125'
                    : active
                      ? 'border-transparent bg-foreground font-semibold text-background shadow-md'
                      : 'border-foreground/[0.05] bg-foreground/[0.03] text-foreground/70 hover:border-gold/30 hover:bg-foreground/[0.08] hover:text-foreground',
                )}
                style={
                  c
                    ? {
                        backgroundColor: `color-mix(in srgb, ${c.bar} ${active ? 34 : 14}%, transparent)`,
                        borderColor: active ? c.bar : `color-mix(in srgb, ${c.bar} 45%, transparent)`,
                      }
                    : undefined
                }
              >
                {f.label}
              </button>
            )
          })}
          <button
            onClick={() => setTagsOpen((v) => !v)}
            title={t(tagsOpen ? 'mail.tagsCollapse' : 'mail.tagsExpand')}
            className="flex items-center gap-1 rounded-lg border border-dashed border-foreground/[0.16] px-2.5 py-1.5 text-[11px] font-serif tracking-wide text-foreground/60 transition-all duration-300 hover:border-gold/40 hover:bg-foreground/[0.05] hover:text-foreground active:scale-95"
          >
            {tagsOpen ? (
              <>
                <ChevronUp className="size-3" />
                Thu gọn
              </>
            ) : (
              <>
                +{dsFilters().length - shownFilters.length}
                <ChevronDown className="size-3" />
              </>
            )}
          </button>
        </div>

        {showFilters && (
          <div className="flex flex-wrap gap-2">
            {dsQuick().map((q) => {
              const active = quick[q.key]
              return (
                <button
                  key={q.key}
                  onClick={() => setQuick((s) => ({ ...s, [q.key]: !s[q.key] }))}
                  className={cn(
                    'flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-serif transition-all duration-200',
                    active
                      ? 'bg-accent text-accent-foreground'
                      : 'bg-foreground/[0.03] text-foreground/70 hover:bg-foreground/[0.08]',
                  )}
                >
                  {q.label}
                </button>
              )
            })}
          </div>
        )}

      </header>

      {selected.size > 0 && (
        <div className="flex items-center gap-2 border-y border-foreground/[0.04] bg-foreground/[0.01] px-4 py-2.5">
          <button
            onClick={toggleSelectAll}
            title={t(allSelected ? 'mail.deselectAll' : 'mail.selectAll')}
            className="flex size-8 items-center justify-center rounded-lg text-active transition-colors hover:bg-foreground/[0.04]"
          >
            {allSelected ? <CheckSquare className="size-5" /> : <Square className="size-5" />}
          </button>
          <span className="text-sm font-semibold text-foreground">{selected.size} đã chọn</span>
          <div className="ml-auto flex items-center gap-0.5">
            <IconBtn icon={MailOpen} title={t('act.markRead')} onClick={() => doMarkRead(true)} />
            <IconBtn icon={Mail} title={t('act.markUnread')} onClick={() => doMarkRead(false)} />
            <IconBtn icon={Star} title={t('act.markImportant')} onClick={doImportant} />
            <IconBtn icon={Tag} title={t('act.label')} onClick={() => setLabelOpen(true)} />
            {folder === 'trash' ? (
              <IconBtn
                icon={RotateCcw}
                title={t('act.restore')}
                onClick={() => {
                  actions.restoreEmails(ids)
                  toast(t('toast.restored', { n: ids.length }), 'success')
                  clearSel()
                }}
              />
            ) : (
              <IconBtn icon={Trash2} title={t('act.delete')} onClick={() => setDeleteIds(ids)} danger />
            )}
            <IconBtn icon={X} title={t('act.clear')} onClick={clearSel} />
          </div>
        </div>
      )}

      {/* HỐC VẢI LỤA SATIN - Tích hợp cấu trúc dệt gân nổi thẳng đứng (Bespoke Ribbed Knit) từ image_73098b.jpg */}
      <div className="px-3 pb-3 flex-1 min-h-0">
        <div 
          ref={listRef} 
          /* BA LỚP KẺ SỌC ĐÃ BỎ (hai đường kẻ dọc + một dải lặp 28px giả vân
             giấy dệt). Chúng là hoa văn: lặp lại, có nhịp, nên mắt luôn thấy —
             mà đây là nền NẰM NGAY SAU danh sách thư, thứ người dùng phải đọc.
             Thay bằng kính mờ, lớp duy nhất trong dự án không có hoa văn nào để
             nhìn. Giữ lại bóng lún phía trong để cột vẫn có chiều sâu. */
          style={{ backgroundColor: 'var(--list)' }}
          className="kinh-mo den-vien w-full h-full rounded-2xl p-4 overflow-y-auto space-y-3.5 scrollbar-thin"
        >
          {loading ? (
            [0, 1, 2, 3].map((i) => (
              <div key={i} className="rounded-xl glass p-4 pl-5 shadow-soft">
                <div className="flex items-start gap-3.5">
                  <div className="skeleton size-9 shrink-0 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <div className="skeleton h-3.5 w-2/5 rounded" />
                    <div className="skeleton h-3 w-4/5 rounded" />
                    <div className="skeleton h-2.5 w-3/5 rounded" />
                  </div>
                </div>
              </div>
            ))
          ) : loi ? (
            /* Bao loi THAY CHO danh sach. Truoc day loi bi nuot va man hinh giu
               nguyen nam la thu mau — trong y het that, nen khong ai biet la hong. */
            <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
              <span className="neon-edge flex size-12 items-center justify-center rounded-2xl text-[var(--warn,#FF6FB5)]"
                style={{ ['--tint' as string]: '#FF6FB5' }}>
                <AlertTriangle className="size-5" />
              </span>
              <p className="max-w-[260px] text-[13px] leading-relaxed text-muted-foreground">{loi}</p>
              {onRefresh && (
                <button onClick={onRefresh}
                  className="neon-chip mt-1 px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.14em]">
                  Thử lại
                </button>
              )}
            </div>
          ) : results.length > 0 ? (
            <>
              {results.map((email, i) => (
                <EmailCard
                  key={email.id}
                  email={email}
                  index={i}
                  selected={openedId === email.id}
                  checked={selected.has(email.id)}
                  selectionActive={selected.size > 0}
                  kbActive={kbActive === i}
                  onSelect={() => onOpen(email.id)}
                  onToggleCheck={() => toggleOne(email.id)}
                  trongThungRac={folder === 'trash'}
                  onRestore={() => quickRestore(email.id)}
                  onArchive={() => quickArchive(email.id)}
                  onStar={() => quickStar(email)}
                  onDelete={() => setDeleteIds([email.id])}
                />
              ))}
              {onLoadMore && (
                <button
                  onClick={onLoadMore}
                  disabled={loadingMore}
                  className="mt-1 w-full rounded-xl glass py-2.5 text-xs font-medium text-foreground shadow-subtle transition-all hover:-translate-y-0.5 disabled:opacity-60"
                >
                  {t(loadingMore ? 'st.loading' : 'mail.loadMore')}
                </button>
              )}
            </>
          ) : (
            <div className="mt-14 flex flex-col items-center gap-3 px-6 text-center">
              <div className="relative flex size-20 items-center justify-center">
                <span className="bokeh flex size-16 items-center justify-center">
                  <MeoMascot className="size-16" />
                </span>
                <span className="absolute bottom-0 right-0 flex size-7 items-center justify-center rounded-full glass text-muted-foreground shadow-subtle">
                  <SearchX className="size-3.5" />
                </span>
              </div>
              <p className="text-sm font-medium text-foreground">
                {isFiltering
                  ? t('mail.noResult')
                  : t('mail.folderEmpty', { ten: t(FOLDER_TITLES[folder] ?? 'fld.inbox') })}
              </p>
              <p className="text-xs text-muted-foreground/60">
                {isFiltering
                  ? t('mail.tryOther')
                  : t('mail.nothingHere')}
              </p>
              {isFiltering && (
                <button
                  onClick={clearAll}
                  className="mt-1 flex items-center gap-1.5 rounded-full glass px-3 py-1 text-xs font-medium text-foreground shadow-subtle hover:-translate-y-0.5"
                >
                  <X className="size-3.5" />
                  {t('mail.clearFilter')}
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      <LabelDialog
        open={labelOpen}
        onOpenChange={setLabelOpen}
        count={selected.size}
        onPick={(category, label) => {
          actions.applyLabel(ids, category, label)
          toast(t('toast.labelled', { nhan: label, n: ids.length }), 'success')
          clearSel()
        }}
      />

      <Dialog open={deleteIds !== null} onOpenChange={(o) => !o && setDeleteIds(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Trash2 className="size-5 text-destructive" />
              {t('mail.delTitle', { n: deleteIds?.length ?? 0 })}
            </DialogTitle>
            <DialogDescription>
              {t((deleteIds?.length ?? 0) > 1 ? 'mail.delDescMany' : 'mail.delDescOne')}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteIds(null)}>
              {t('act.cancel')}
            </Button>
            <Button variant="destructive" onClick={doDelete}>
              <Trash2 className="size-4" />
              {t('act.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {!fill && (
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label={t('mail.dragWidth')}
        aria-valuenow={width}
        aria-valuemin={MIN_W}
        aria-valuemax={MAX_W}
        tabIndex={0}
        onPointerDown={startDrag}
        onPointerMove={onDrag}
        onPointerUp={endDrag}
        onDoubleClick={() => setWidth(DEFAULT_W)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') {
            e.preventDefault()
            setWidth((w) => clampW(w - 16))
          } else if (e.key === 'ArrowRight') {
            e.preventDefault()
          }
        }}
        title={t('mail.dragWidthLong')}
        className="group absolute inset-y-0 -right-2 z-30 flex w-4 cursor-col-resize touch-none items-center justify-center"
      >
        <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border/20 transition-colors group-hover:bg-active group-focus-visible:bg-active" />
        <span className="cherry-dot relative h-10 w-1.5 rounded-full opacity-0 shadow-subtle transition-opacity duration-200 group-hover:opacity-100 group-focus-visible:opacity-100" />
      </div>
      )}
    </section>
  )
}