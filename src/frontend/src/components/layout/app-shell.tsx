import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { NavRail } from '@/components/layout/nav-rail'
import { EmailList } from '@/components/layout/email-list'
import { EmailDetail } from '@/components/layout/email-detail'
import { ChatPanel } from '@/components/layout/chat-panel'
import { CommandPalette } from '@/components/layout/command-palette'
import { Onboarding } from '@/components/layout/onboarding'
import { WanderingCat } from '@/components/wandering-cat'
import { useTheme } from '@/components/theme-provider'
import { useToast } from '@/components/ui/toast'
import { emails as seedEmails } from '@/data/emails'
import { CommitmentsView } from '@/components/layout/commitments-view'
import { cn } from '@/lib/utils'
import { AlertOverlay } from '@/components/layout/alert-overlay'
import {
  apDungSuaLacQuan,
  ghimLenDau,
  giuChiTietDaCo,
  nenNapNgam,
  THU_MUC_DICH,
  type EmailActions,
} from '@/lib/email-actions'
import { api, apiBaseUrlDaCauHinh } from '@/lib/api'
import { trichCamKet, apLucTheoNgay } from '@/lib/cam-ket'
import { chuyenCanh } from '@/lib/chuyen-canh'
import { t } from '@/lib/ngon-ngu'

/** Layout 3 phần: nav rail trái · email list giữa · (chi tiết email | AI chat) phải */
export function AppShell() {
  // KHONG khoi tao bang du lieu mau khi da cau hinh backend that.
  //
  // Truoc day luon la `useState(seedEmails)`. O che do that, giua luc trang vua
  // mo va luc Gmail tra ve, nguoi dung nhin thay NAM LA THU BIA DAT (Giao vu
  // HCMUS, GitHub, Vercel...) trong y het that. Neu lenh goi hong — chua dang
  // nhap, phien het han, mang loi — thi `.catch(() => {})` nuot loi va man hinh
  // dung yen o do MAI MAI: khong bao loi, khong o trong, chi la mot hop thu gia
  // trong nhu that. Dem san pham di trinh bay ma gap canh do thi khong con
  // duong nao chua.
  //
  // Che do mock (chua co backend) van dung seedEmails — do la muc dich cua no.
  const [emails, setEmails] = useState(apiBaseUrlDaCauHinh ? [] : seedEmails)
  /** Loi nap thu, hien thang ra danh sach thay vi nuot im. */
  const [loiNapThu, setLoiNapThu] = useState<string | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null) // token trang kế (null = hết)
  const [loadingMore, setLoadingMore] = useState(false)
  const [refreshing, setRefreshing] = useState(false) // đang "Làm mới" (bỏ qua cache BE)
  // Ghi nhớ truy vấn hiện tại (thư mục hoặc từ khoá) để "Tải thêm" lấy đúng trang tiếp.
  const [pageQuery, setPageQuery] = useState<{ folder?: string; q?: string }>({ folder: 'inbox' })
  const [openedId, setOpenedId] = useState<string | null>(null)
  // Lệnh do nút ngữ cảnh (UC016) / Command Palette đẩy sang ChatPanel
  const [pendingCommand, setPendingCommand] = useState<string | null>(null)
  const [commandOpen, setCommandOpen] = useState(false)
  const [activeNav, setActiveNav] = useState('inbox') // thư mục đang chọn (luôn là folder thật)
  // MẶC ĐỊNH BẬT. Trước đây tắt cho "giống Gmail" — nhưng giống Gmail là hỏng:
  // danh sách thư thì Gmail cũng có, thứ Gmail KHÔNG có là trợ lý. Mở app ra mà
  // không thấy nó thì màn hình đầu tiên không kể được sản phẩm này khác chỗ nào.
  const [aiOpen, setAiOpen] = useState(true)
  const [chatFocus, setChatFocus] = useState(0)       // đếm số lần bấm tab AI Agent → focus chat
  const { theme, toggleTheme } = useTheme()
  const toast = useToast()

  // Nav trái giờ luôn là thư mục thật; nút "AI Agent" là công tắc bật/tắt panel chat.
  const folder = activeNav

  // Cache thư THEO THƯ MỤC (stale-while-revalidate): quay lại tab đã xem → hiện
  // NGAY bản cache (hết cảm giác "đang gọi API load lại"), đồng thời vẫn refetch
  // NỀN để làm tươi dữ liệu. Chỉ có tác dụng ở chế độ backend thật.
  const folderCache = useRef(new Map<string, { items: typeof seedEmails; cursor: string | null }>())

  // Thư vừa khôi phục, ghim lên đầu Hộp thư cho tới khi người dùng rời khỏi Hộp thư
  // hoặc bấm Làm mới. Không ghim thì thư cũ khôi phục xong rơi ra ngoài trang đầu và
  // coi như biến mất — xem ghi chú dài ở `restoreEmails`.
  const [vuaKhoiPhuc, setVuaKhoiPhuc] = useState<typeof seedEmails>([])

  // Chế độ backend thật: nạp thư theo THƯ MỤC đang chọn từ Gmail; đổi nav → fetch lại
  // (inbox/sent/drafts/trash/starred/archive). Mock mode bỏ qua → vẫn dùng dữ liệu mẫu.
  useEffect(() => {
    if (!apiBaseUrlDaCauHinh) return
    setPageQuery({ folder })
    const cached = folderCache.current.get(folder)
    if (cached) {
      setEmails(cached.items) // hiện tức thì từ cache trong lúc chờ bản mới
      setNextCursor(cached.cursor)
    }
    api
      .listEmails({ folder })
      .then((r) => {
        setEmails((truoc) => {
          const gop = giuChiTietDaCo(truoc, r.items)
          folderCache.current.set(folder, { items: gop, cursor: r.nextCursor ?? null })
          return gop
        })
        setNextCursor(r.nextCursor ?? null) // có cursor = còn thư để "Tải thêm"
        setLoiNapThu(null)
      })
      .catch((e) => {
        // Bao that. Mot hop thu rong kem dong bao loi thi con sua duoc; mot hop
        // thu day thu gia thi khong ai biet duong ma sua.
        setEmails([])
        setLoiNapThu(
          e?.status === 401
            ? t('sh.expired')
            : t('sh.netFail'),
        )
      })
  }, [folder])
  const selectNav = (id: string) => {
    // "AI Agent" = CÔNG TẮC hiện/ẩn panel chat (không phải một thư mục). Mở → focus ô chat.
    if (id === 'agent') {
      setAiOpen((v) => !v)
      setChatFocus((n) => n + 1)
      return
    }
    setActiveNav(id)
    // Rời Hộp thư là thôi ghim: ghim chỉ để trả lời câu "thư tôi vừa lấy lại đâu",
    // giữ mãi thì nó thành một thứ tự sai vĩnh viễn ở đầu danh sách.
    if (id !== 'inbox') setVuaKhoiPhuc([])
    /* CHỈ chuyển cảnh khi THẬT SỰ đổi cảnh.
       Bản trước bọc MỌI cú bấm thư mục trong `chuyenCanh`, mà chuyển cảnh gốc là
       một hiệu ứng TOÀN TRANG: cả trang trượt -8px và co 0.994 trong 0.34s. Nên
       bấm từ Hộp thư sang Thư rác là thanh điều hướng, danh sách và cả panel phải
       cùng nhún một cái — đúng cảm giác "giật" người dùng mô tả.

       Đổi thư mục là đổi NỘI DUNG trong cùng một cảnh, không phải đổi cảnh. Chỉ
       khi đang mở chi tiết một lá thư (một mặt phẳng khác hẳn) thì quay về danh
       sách mới đáng một chuyển cảnh. */
    if (openedId) chuyenCanh(() => setOpenedId(null))
    else setOpenedId(null)
  }
  /* ── SỐ CHƯA ĐỌC CỦA HỘP THƯ ĐẾN — phải ỔN ĐỊNH, không đổi theo chỗ đang đứng ──
     Bản trước đếm thẳng trên `emails`, mà `emails` là thư của THƯ MỤC ĐANG XEM. Nên
     con số nhảy lung tung theo nơi người dùng bấm vào, và không quy tắc nào giải
     thích được nó:
       • đang ở "Hộp thư"  → đếm đúng thư chưa đọc
       • đang ở "Gắn sao"  → thư gắn sao vẫn mang folder 'inbox', nên nó đếm số thư
                             GẮN SAO chưa đọc (vd 2) rồi dán lên icon Hộp thư
       • đang ở "Đã gửi"   → không lá nào mang folder 'inbox' → badge BIẾN MẤT
     Đúng ba triệu chứng người dùng báo, và cả ba đều từ một nguyên nhân.

     Nay: chỉ cập nhật khi ĐANG THẬT SỰ xem hộp thư đến; các thư mục khác giữ nguyên
     con số biết được lần cuối. Một con số hơi cũ vẫn có nghĩa; một con số đổi theo
     tab thì không có nghĩa gì cả. */
  const soChuaDoc = useRef(0)
  if (folder === 'inbox') {
    soChuaDoc.current = emails.filter((e) => (e.folder ?? 'inbox') === 'inbox' && e.unread).length
  }
  const inboxUnread = soChuaDoc.current

  // Áp lực 7 ngày cho dải ở thanh điều hướng. Tính Ở ĐÂY chứ không trong nav-rail
  // để nav-rail không phải biết gì về tầng lịch trình — nó còn được dùng ở chỗ
  // khác, và một thanh điều hướng tự đi lấy dữ liệu nghiệp vụ là chỗ rất dễ kẹt
  // về sau.
  const apLuc = useMemo(() => apLucTheoNgay(trichCamKet(emails), 7), [emails])

  // Mở email = chuyển panel phải sang chi tiết + đánh dấu đã đọc (UC004)
  const openEmail = (id: string) => {
    chuyenCanh(() => setOpenedId(id))
    setEmails((prev) => prev.map((e) => (e.id === id ? { ...e, unread: false } : e)))
    // Chế độ backend thật: tải nội dung ĐẦY ĐỦ của thư (thân thư + đính kèm) từ Gmail,
    // rồi trộn vào thư trong danh sách → màn chi tiết hiện đủ thay vì chỉ snippet.
    if (apiBaseUrlDaCauHinh) {
      api
        .getEmail(id)
        .then((full) => {
          if (!full) return
          // Nếu thư CHƯA có trong danh sách (vd AI trả từ thư mục khác) → THÊM vào để mở được;
          // đã có thì trộn nội dung đầy đủ. Nhờ vậy bấm mở thư từ kết quả AI luôn hiện chi tiết.
          setEmails((prev) =>
            prev.some((e) => e.id === id)
              ? prev.map((e) =>
                  // GIỮ NGUYÊN `folder` CŨ. Bản chi tiết suy thư mục từ nhãn Gmail, còn
                  // bản trong danh sách mang thư mục ĐANG XEM — hai cách suy có thể lệch
                  // nhau (thư tự gửi cho mình mang cả INBOX lẫn SENT). Để `...full` đè
                  // lên thì bấm vào thư là nó rơi khỏi bộ lọc và BIẾN MẤT trước mắt.
                  // Thư mục là thuộc tính của KHUNG ĐANG XEM, không phải của lần tải chi tiết.
                  e.id === id ? { ...e, ...full, folder: e.folder, unread: false } : e,
                )
              : [{ ...full, unread: false }, ...prev],
          )
        })
        .catch(() => {})
      // UC004: ghi "đã đọc" xuống Gmail thật (bỏ nhãn UNREAD). Lỗi thì kệ (UI vẫn đã đọc).
      api.markEmailRead(id, true).catch(() => {})
    }
  }
  const closeEmail = () => chuyenCanh(() => setOpenedId(null))

  // UC005 — Tìm kiếm trên Gmail (chỉ chế độ backend thật). Gửi từ khoá `q` sang BE,
  // BE hỏi Gmail rồi trả thư khớp → thay danh sách. Ô rỗng → quay về hộp thư đến.
  const searchEmails = (q: string) => {
    const query = q ? { q } : { folder: 'inbox' }
    setPageQuery(query)
    api
      .listEmails(query)
      .then((r) => {
        setEmails(r.items)
        setNextCursor(r.nextCursor ?? null)
      })
      .catch(() => {})
  }

  // Nút "Làm mới": nạp lại truy vấn hiện tại nhưng BỎ QUA cache backend (fresh) → thấy thư mới ngay.
  const refreshEmails = () => {
    if (!apiBaseUrlDaCauHinh) return
    setVuaKhoiPhuc([]) // "Làm mới" = xin bản thật của máy chủ, ghim tay phải nhường
    setRefreshing(true)
    api
      .listEmails({ ...pageQuery, fresh: true })
      .then((r) => {
        // "Làm mới" cũng ghi đè cache thư mục hiện tại cho lần quay lại sau
        setEmails((truoc) => {
          const gop = giuChiTietDaCo(truoc, r.items)
          if (pageQuery.folder)
            folderCache.current.set(pageQuery.folder, { items: gop, cursor: r.nextCursor ?? null })
          return gop
        })
        setNextCursor(r.nextCursor ?? null)
      })
      .catch(() => {})
      .finally(() => setRefreshing(false))
  }

  /* ── TỰ NẠP LẠI HỘP THƯ ────────────────────────────────────────────────────
     Trước đây hộp thư KHÔNG BAO GIỜ tự nạp lại: chỉ đổi thư mục hoặc bấm "Làm mới"
     mới gọi máy chủ. Nên thư về tới Gmail mà người dùng đang mở sẵn màn danh sách thì
     màn hình đứng im vĩnh viễn — ngồi chờ bao lâu cũng không có gì xảy ra. Nhìn từ
     ngoài tưởng là "đồng bộ chậm", thật ra KHÔNG có đường nào nối "thư tới" với
     "màn hình đổi".

     Vài quyết định nhỏ nhưng đáng nói:
     • `fresh: true` — bắt buộc. Gọi thường thì máy chủ phục vụ từ CSDL/cache, mà CSDL
       chỉ đổi khi có ai đó chạy đồng bộ. Poll kiểu đó là hỏi lại đúng câu trả lời cũ
       mãi mãi.
     • CHỈ khi tab đang hiện. Tab nền chạy vòng lặp là đốt hạn mức Gmail cho một màn
       hình không ai nhìn.
     • Nạp NGAY khi quay lại tab. Đó là khoảnh khắc người ta muốn thấy cái mới nhất,
       và chờ thêm 30 giây ở đúng lúc đó là dở nhất.
     • BỎ QUA khi đang tìm kiếm: đè kết quả tìm kiếm bằng hộp thư đến là cướp mất thứ
       người dùng đang xem.
     • Trần đọc là 90 lượt/phút/người; 30 giây một lần tốn 2. Không chạm tới trần.  */
  const dangNap = useRef(false)
  const idsDaBiet = useRef<Set<string> | null>(null)

  const napNgam = () => {
    if (!apiBaseUrlDaCauHinh) return
    const duocPhep = nenNapNgam({
      dangNap: dangNap.current,
      coTimKiem: !!pageQuery.q,
      hienThi: typeof document === 'undefined' || document.visibilityState === 'visible',
    })
    if (!duocPhep) return
    dangNap.current = true
    api
      .listEmails({ ...pageQuery, fresh: true })
      .then((r) => {
        const truoc = idsDaBiet.current
        const sau = new Set(r.items.map((e) => e.id))
        // Lần đầu chỉ GHI NHỚ, không báo: nếu không thì mở app lên là bị báo "có N thư
        // mới" cho toàn bộ hộp thư — đúng kiểu thông báo khiến người ta tắt thông báo.
        if (truoc) {
          const moi = r.items.filter((e) => !truoc.has(e.id))
          if (moi.length > 0)
            toast(
              moi.length === 1
                ? t('toast.newMailOne', { ten: moi[0].sender })
                : t('toast.newMail', { n: moi.length }),
              'success',
            )
        }
        idsDaBiet.current = sau
        // GIỮ phần chi tiết đã tải. Bản danh sách không có thân thư đầy đủ và không có
        // tệp đính kèm — thay thẳng vào là thư đang mở bị nghèo đi trước mắt người đọc.
        setEmails((truoc) => {
          const gop = giuChiTietDaCo(truoc, r.items)
          if (pageQuery.folder)
            folderCache.current.set(pageQuery.folder, { items: gop, cursor: r.nextCursor ?? null })
          return gop
        })
        setNextCursor(r.nextCursor ?? null)
      })
      .catch(() => {})                            // hỏng thì im lặng: đây là việc nền
      .finally(() => { dangNap.current = false })
  }

  // Đổi thư mục/truy vấn thì quên danh sách id cũ — không thì chuyển từ Thùng rác về
  // Hộp thư sẽ bị báo "có 70 thư mới".
  useEffect(() => { idsDaBiet.current = null }, [pageQuery.folder, pageQuery.q])

  // Giữ bản MỚI NHẤT của `napNgam` trong một ref, rồi mới dựng bộ đếm MỘT LẦN.
  //
  // Viết thẳng `useEffect(..., [napNgam])` hay bỏ trống mảng phụ thuộc đều hỏng, theo
  // hai kiểu ngược nhau: bỏ trống thì effect chạy lại sau MỌI lần render, tức bộ đếm
  // 30 giây bị dựng lại liên tục và không bao giờ đếm hết — tính năng trông như không
  // tồn tại. Còn `[]` với hàm gọi thẳng thì bộ đếm sống đúng một lần nhưng ôm mãi
  // `pageQuery` của lần render đầu, nên đổi thư mục xong nó vẫn nạp thư mục cũ.
  const napNgamRef = useRef(napNgam)
  napNgamRef.current = napNgam

  useEffect(() => {
    if (!apiBaseUrlDaCauHinh) return
    const goi = () => napNgamRef.current()
    const t = window.setInterval(goi, 30_000)
    const khiHien = () => { if (document.visibilityState === 'visible') goi() }
    document.addEventListener('visibilitychange', khiHien)
    window.addEventListener('focus', khiHien)
    return () => {
      window.clearInterval(t)
      document.removeEventListener('visibilitychange', khiHien)
      window.removeEventListener('focus', khiHien)
    }
  }, [])

  // UC003 — "Tải thêm": lấy TRANG KẾ (theo cursor) rồi NỐI vào danh sách hiện có.
  const loadMore = () => {
    if (!apiBaseUrlDaCauHinh || !nextCursor || loadingMore) return
    setLoadingMore(true)
    api
      .listEmails({ ...pageQuery, cursor: nextCursor })
      .then((r) => {
        setEmails((prev) => [...prev, ...r.items]) // NỐI thêm, không thay
        setNextCursor(r.nextCursor ?? null)
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false))
  }

  // Nút "đoán trước ý định" / palette: đóng chi tiết → mở canvas AI → tự gửi lệnh
  const runAgentAction = (command: string) => {
    chuyenCanh(() => setOpenedId(null))
    setPendingCommand(command)
  }

  // ⌘K / Ctrl+K mở Command Palette
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCommandOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Nếu lệnh ghi xuống Gmail THẤT BẠI (vd token thiếu quyền → 403), nạp lại thư mục
  // hiện tại để màn hình quay về ĐÚNG sự thật trên Gmail (huỷ cập nhật lạc quan vừa rồi).
  const resync = () => {
    if (!apiBaseUrlDaCauHinh) return
    api.listEmails({ folder }).then((r) => setEmails(r.items)).catch(() => {})
  }

  // Sửa lạc quan phải áp cho CẢ `folderCache`, không riêng danh sách đang hiện. Cache
  // là stale-while-revalidate: bỏ qua nó thì xoá một thư ở Hộp thư rồi quay lại Hộp thư
  // sẽ thấy thư đó HIỆN LẠI một nhịp trước khi bản mới về — người xem chỉ kịp thấy nó
  // nhấp nháy và kết luận là app xoá hụt.
  // `boCache` xoá hẳn entry của thư mục ĐÍCH: thư vừa chuyển tới không có trong bản
  // cache cũ của nó, mà đoán thêm vào thì lại là bịa — thà nạp lại cho đúng.
  const suaThu = (
    ids: string[],
    sua: (e: (typeof seedEmails)[number]) => (typeof seedEmails)[number],
    boCache?: string,
  ) => setEmails(apDungSuaLacQuan(folderCache.current, ids, sua, boCache))

  // Hành động quản lý email (UC006) — nhận mảng id để dùng được cho cả bulk.
  // CHIẾN LƯỢC "lạc quan": đổi giao diện NGAY cho mượt, rồi mới gọi backend ngầm;
  // lỗi thì resync() kéo trạng thái thật về. Mock mode (không có apiBaseUrlDaCauHinh) chỉ đổi cục bộ.
  const actions: EmailActions = {
    markRead: (ids, read) => {
      suaThu(ids, (e) => ({ ...e, unread: !read }))
      if (apiBaseUrlDaCauHinh) api.markRead(ids, read).catch(resync)
    },
    setImportant: (ids, value) => {
      suaThu(ids, (e) => ({ ...e, starred: value }))
      if (apiBaseUrlDaCauHinh) api.setImportant(ids, value).catch(resync)
    },
    applyLabel: (ids, category, label) => {
      suaThu(ids, (e) => ({ ...e, category, label }))
      if (apiBaseUrlDaCauHinh) api.applyLabel(ids, category, label).catch(resync) // tạo/gắn nhãn Gmail thật
    },
    restoreEmails: (ids) => {
      // Thư trong thùng rác VẪN nằm trong mảng `emails` — EmailList lọc theo
      // `email.folder`, đó chính là cách thư mục Thùng rác hiện ra nó. Nên khôi phục
      // là đổi `folder` về 'inbox', y như các hành động khác ở khối này. Bản trước
      // chỉ gọi máy chủ mà không đụng state: ở chế độ mock thư đứng nguyên trong
      // thùng rác trong khi toast đã báo "đã khôi phục" — báo xanh giả.
      //
      // GHIM LÊN ĐẦU HỘP THƯ. Máy chủ trả 30 thư/trang, sắp theo ngày nhận giảm dần,
      // và thư khôi phục quay về ĐÚNG vị trí thời gian cũ của nó. Thư cũ hơn 30 thư
      // mới nhất thì nằm ở trang 2 — người dùng bấm khôi phục, thấy toast báo xong,
      // nhìn Hộp thư thì không có gì mới. Đúng nghĩa đen là "khôi phục rồi nhưng
      // không thấy mail". Ghim là cách nói thật: "đây là mấy thư bạn vừa lấy lại",
      // khác hẳn việc giả vờ chúng là thư mới nhất.
      const ds = emails.filter((e) => ids.includes(e.id))
      if (ds.length) setVuaKhoiPhuc(ds.map((e) => ({ ...e, folder: THU_MUC_DICH.restore })))
      suaThu(ids, (e) => ({ ...e, folder: THU_MUC_DICH.restore }), THU_MUC_DICH.restore)
      if (apiBaseUrlDaCauHinh) api.restoreEmails(ids).then(resync).catch(resync)
    },
    markSpam: (ids, rac) => {
      // Cùng khuôn với các hành động khác: đổi thư mục lạc quan rồi gọi máy chủ.
      // `spam` là một THƯ MỤC thật trong `Email.folder`, nên thư đi đúng chỗ và
      // thư mục Thư rác ở nav hiện ra ngay, không phải chờ nạp lại.
      const dich = rac ? ('spam' as const) : ('inbox' as const)
      suaThu(ids, (e) => ({ ...e, folder: dich }), dich)
      if (openedId && ids.includes(openedId)) setOpenedId(null)
      if (apiBaseUrlDaCauHinh) {
        const xong = rac ? api.spamEmails(ids) : api.notSpamEmails(ids)
        xong.catch(resync)
      }
    },
    removeEmails: (ids, mode = 'delete') => {
      // CHUYỂN thư mục, không xoá khỏi mảng. Lọc bỏ hẳn thì thư biến mất khỏi hộp thư
      // ĐÚNG như mong muốn, nhưng cũng không bao giờ hiện ra ở Thùng rác/Lưu trữ —
      // nên vòng "xoá rồi khôi phục" đứt ngay ở giữa. Chuyển folder cho cùng một kết
      // quả ở hộp thư (EmailList lọc `e.folder === folder`) mà giữ được đường lùi.
      const dich = mode === 'archive' ? THU_MUC_DICH.archive : THU_MUC_DICH.delete
      suaThu(ids, (e) => ({ ...e, folder: dich }), dich)
      if (openedId && ids.includes(openedId)) setOpenedId(null)
      // archive → bỏ nhãn INBOX; delete → vào thùng rác. Gọi đúng endpoint theo mode.
      if (apiBaseUrlDaCauHinh) {
        const done = mode === 'archive' ? api.archiveEmails(ids) : api.deleteEmails(ids)
        done.catch(resync)
      }
    },
  }

  // Danh sách ĐEM ĐI HIỆN: thư vừa khôi phục đứng trước, phần còn lại giữ nguyên thứ
  // tự máy chủ trả. Khử trùng theo id để khi máy chủ trả về đúng thư đó (thư mới, nằm
  // trong trang đầu) thì nó không hiện hai lần.
  const emailsHienThi = useMemo(() => ghimLenDau(emails, vuaKhoiPhuc), [emails, vuaKhoiPhuc])

  const openedEmail = emailsHienThi.find((e) => e.id === openedId) ?? null

  return (
    <div className="giao-dien-app relative flex h-screen w-full overflow-hidden bg-background text-foreground">
      {/* Báo hiệu nổi trên cùng — thư cần xử lý và hạn sắp tới. */}
      <AlertOverlay emails={emailsHienThi} />
      {/* Cực quang nền — dải sáng uốn lượn như khung hình đầu trang giới thiệu.
          Nằm SAU mọi panel (các panel là khối kính nên ánh sáng vẫn thấp thoáng qua). */}
      <div aria-hidden className="aurora-stage">
        <span className="aurora-ribbon aurora-ribbon-1" />
        <span className="aurora-ribbon aurora-ribbon-2" />
        <span className="aurora-ribbon aurora-ribbon-3" />
      </div>

      {/* Ba cột nằm ở tầng trên aurora (z-10) — nếu để chung tầng, lớp nền absolute
          sẽ được vẽ ĐÈ lên các cột vì chúng không phải phần tử positioned. */}
      <div className="relative z-10 flex min-w-0 flex-1">
      <NavRail
        activeId={activeNav}
        onSelect={selectNav}
        badges={{ inbox: inboxUnread }}
        agentActive={aiOpen}
        apLuc={apLuc}
      />
      {/* "Việc của tôi" thay chỗ danh sách thư ở cột giữa — KHÔNG mở thành một
          màn riêng chiếm cả trang. Lý do: nó là một cách nhìn khác về cùng hộp
          thư đó, nên giữ nguyên khung ba cột thì người dùng vẫn bấm được vào một
          việc để nhảy thẳng sang lá thư sinh ra nó, mà không mất ngữ cảnh. */}
      {activeNav === 'viec' ? (
        <div className={cn('flex min-h-0 shrink-0 flex-col p-2', aiOpen ? 'w-[420px]' : 'flex-1')}>
          <CommitmentsView
            emails={emailsHienThi}
            onOpenEmail={(id) => {
              setActiveNav('inbox')
              openEmail(id)
            }}
          />
        </div>
      ) : (
      <EmailList
        emails={emailsHienThi}
        folder={folder}
        openedId={openedId}
        onOpen={openEmail}
        actions={actions}
        onSearch={apiBaseUrlDaCauHinh ? searchEmails : undefined}
        onLoadMore={apiBaseUrlDaCauHinh && nextCursor ? loadMore : undefined}
        loadingMore={loadingMore}
        onRefresh={apiBaseUrlDaCauHinh ? refreshEmails : undefined}
        loi={loiNapThu}
        refreshing={refreshing}
        elegant={!aiOpen}
        fill={!aiOpen && !openedEmail}
      />
      )}
      {/* Panel phải — chỉ dựng khi CẦN: đang bật AI, HOẶC đang mở 1 thư (reading pane).
          AI tắt + chưa mở thư → không dựng gì → Hộp thư fill trọn khung như Gmail. */}
      {(aiOpen || openedEmail) && (
        <div
          className="flex min-w-0 flex-1"
          style={{ ['viewTransitionName' as keyof CSSProperties]: 'rightpanel' } as CSSProperties}
        >
          {/* ChatPanel mounted khi AI bật (ẩn khi đang xem thư) → mở thư rồi quay lại KHÔNG mất phiên. */}
          {aiOpen && (
            <div className={openedEmail ? 'hidden' : 'flex min-w-0 flex-1'}>
              <ChatPanel
                emails={emailsHienThi}
                actions={actions}
                injectedCommand={pendingCommand}
                onInjectConsumed={() => setPendingCommand(null)}
                onOpenEmail={openEmail}
                focusSignal={chatFocus}
                onClose={() => setAiOpen(false)}
              />
            </div>
          )}
          {openedEmail && (
            <EmailDetail
              email={openedEmail}
              onClose={closeEmail}
              actions={actions}
              onAgentAction={runAgentAction}
            />
          )}
        </div>
      )}
      </div>

      {/* Command Palette (⌘K) */}
      <CommandPalette
        open={commandOpen}
        onOpenChange={setCommandOpen}
        onRun={runAgentAction}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {/* Onboarding coachmark — chỉ hiện lần đầu */}
      <Onboarding />

      {/* Mèo lang thang — thỉnh thoảng chạy/nhảy ngang sàn app cho có hồn 🐈 */}
      <WanderingCat />
    </div>
  )
}
