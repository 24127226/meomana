import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ChevronLeft, ChevronRight, Clock, Mail,
  MessageSquare, Sparkles, Plane,
} from 'lucide-react'
import { emails as seedEmails, type Email } from '@/data/emails'
import { api, apiBaseUrlDaCauHinh } from '@/lib/api'
import {
  trichCamKet, gomTheoNgay, luoiThang, khoaNgay, TRAN_MOI_NGAY,
  xepDoanTheoTuan, thangNenMo, phutMoiNgay, type CamKet, type DoanThe,
} from '@/lib/cam-ket'
import { ChatPanel } from '@/components/layout/chat-panel'
import { EmailDetail } from '@/components/layout/email-detail'
import type { EmailActions } from '@/lib/email-actions'
import { AlertOverlay } from '@/components/layout/alert-overlay'
import { LogoMark } from '@/components/logo'
import { cn } from '@/lib/utils'
import { t } from '@/lib/ngon-ngu'
import { chuyenCanh } from '@/lib/chuyen-canh'
import { TraCuuPanel } from '@/components/layout/tra-cuu-panel'

/**
 * SchedulePage — trang lịch trình.
 *
 * ── BỐ CỤC: HAI KHUNG, KHÔNG PHẢI MỘT KHUNG RỒI CUỘN ──
 * Bản trước là một cuốn lịch to rồi bên dưới là phần tóm tắt — nghĩa là muốn xem
 * đủ thì phải cuộn, mà cuộn trong một trang lịch là hỏng: người ta mở lịch để
 * NHÌN THẤY CẢ BỨC TRANH, không phải để đọc lần lượt.
 *
 * Nay chia đôi theo chiều ngang: cột trái là lịch nhỏ + danh sách sắp tới (phần
 * tóm tắt), cột phải là khung lớn chứa các thẻ lịch trình. Hai thứ nằm cạnh nhau
 * nên thấy cùng lúc, không phải cuộn.
 *
 * ── VÌ SAO THẺ, KHÔNG PHẢI CHẤM ──
 * Một hạn nộp thứ Sáu KHÔNG phải một việc của thứ Sáu: nếu nó cần sáu tiếng thì
 * nó là việc của cả thứ Tư và thứ Năm. Cuốn lịch thường vẽ nó thành một chấm ở
 * thứ Sáu, và đó chính là lý do người ta hay vỡ kế hoạch — họ nhìn thấy một chấm,
 * không nhìn thấy khối lượng. Thẻ TRẢI DÀI qua đúng số ngày cần làm.
 *
 * ── XẾP LỚP KHI NHIỀU ──
 * Một ngày có bốn việc mà vẽ bốn thẻ đầy đủ thì ô đó cao gấp bốn ô khác và cả
 * lưới méo. Xếp chồng lệch vài pixel thì vẫn thấy "ở đây có nhiều việc", vẫn giữ
 * lưới đều, và thẻ ƯU TIÊN CAO NHẤT nằm trên cùng — thứ người ta cần thấy trước.
 * Rê chuột thì cả chồng xoè ra.
 */
export function SchedulePage() {
  const dieuHuong = useNavigate()
  const [emails, setEmails] = useState<Email[]>(apiBaseUrlDaCauHinh ? [] : seedEmails)
  const homNay = useMemo(() => new Date(), [])
  const [thang, setThang] = useState(() => new Date(homNay.getFullYear(), homNay.getMonth(), 1))
  const [lenh, setLenh] = useState<string | null>(null)
  // Bối cảnh "đang nói về việc này" — KHÔNG tự gửi câu hỏi nào. Xem `hoiAI`.
  const [boiCanh, setBoiCanh] = useState<{ tieuDe: string; mo_ta: string } | null>(null)
  const [chatMo, setChatMo] = useState(false)
  /** Thẻ vừa bấm → hiện khung hỏi "xem thư hay hỏi AI". */
  /** Thẻ đang rê chuột → thanh hành động xổ ra ngay dưới nó.
   *  Giữ HÌNH CHỮ NHẬT của thẻ chứ không giữ toạ độ chuột: thanh phải bám vào
   *  MÉP DƯỚI của thẻ, không phải chỗ con trỏ tình cờ dừng lại. */
  const [dangHoi, setDangHoi] = useState<{ ck: CamKet; hcn: DOMRect } | null>(null)
  /** Thư đang mở toàn màn — bấm quay lại là về đúng lịch, không mất chỗ. */
  const [thuMo, setThuMo] = useState<string | null>(null)
  /** Ngày đang mở bảng liệt kê đầy đủ — lối thoát cho các việc không đủ làn. */
  const [ngayMo, setNgayMo] = useState<{ ngay: Date; hcn: DOMRect } | null>(null)
  /** Khung tra cứu chỗ đi lại — gọi thẳng backend, không qua trợ lý (xem TraCuuPanel). */
  const [traCuuMo, setTraCuuMo] = useState(false)
  /** Tải thư hỏng — phải NÓI RA. Lịch rỗng vì lỗi và lịch rỗng vì rảnh trông
   *  giống hệt nhau, và đó chính là thứ làm lần gỡ lỗi trước mất nhiều giờ. */
  const [loiTai, setLoiTai] = useState(false)

  useEffect(() => {
    if (!apiBaseUrlDaCauHinh) return
    // XIN ĐÚNG SỐ THƯ AGENT QUÉT. Mặc định của API là 30, còn các tool lịch trình quét
    // nhiều hơn — nên trợ lý tìm ra cam kết trong lá thứ 45 mà cuốn lịch chưa bao giờ
    // tải về. Người dùng thấy AI nhắc một việc rồi mở lịch không có nó.
    //
    // ⚠️ 50 chứ KHÔNG PHẢI 60: API chặn `limit` ở MAX_PAGE_SIZE=50. Xin 60 thì FastAPI
    // trả 422, `.catch` bên dưới nuốt lỗi, và cuốn lịch TRỐNG TRƠN — im lặng hoàn toàn.
    // Đã vấp đúng lỗi đó. Hằng số dùng chung nằm ở backend: limits.QUET_LICH_TRINH.
    api.listEmails({ folder: 'inbox', limit: 50 })
      .then((r) => setEmails(r.items))
      // KHÔNG nuốt lỗi trong im lặng nữa: lịch rỗng vì hỏng và lịch rỗng vì không có
      // việc trông y hệt nhau, nên lần trước mất rất lâu mới lần ra.
      .catch((e) => {
        console.error('[lịch] không tải được thư:', e)
        setLoiTai(true)
      })
  }, [])

  const camKet = useMemo(() => trichCamKet(emails), [emails])
  const theoNgay = useMemo(() => gomTheoNgay(camKet), [camKet])

  // MỞ RA Ở CHỖ CÓ VIỆC. Đo thật ngày 29/08: mọi cam kết rơi vào tháng 9, nên lịch
  // mở ra là một tháng 8 trống trơn, còn nội dung thật thì nằm ở hàng "ngoài tháng"
  // và bị làm mờ — vừa trống vừa giấu mất thứ đáng xem.
  //
  // Chỉ nhảy MỘT LẦN, lúc dữ liệu về. Chạy lại mỗi lần `camKet` đổi thì người dùng
  // bấm sang tháng khác sẽ bị kéo ngược về, và đó là kiểu bực nhất: giao diện tự ý
  // huỷ thao tác của mình mà không nói gì.
  const daNhay = useRef(false)
  useEffect(() => {
    if (daNhay.current || camKet.length === 0) return
    daNhay.current = true
    setThang(thangNenMo(camKet, homNay))
  }, [camKet, homNay])
  const o = useMemo(() => luoiThang(thang.getFullYear(), thang.getMonth()), [thang])
  /* "SẮP TỚI" = SÁU VIỆC GẦN HẠN NHẤT — không phải sáu việc đầu danh sách.
     Bản trước là `slice(0, 6)` trên thứ tự trích, tức thứ tự thư trong hộp thư.
     Nó TÌNH CỜ gần đúng vì thư thường tới theo thời gian, nhưng chỉ cần một lá
     thư cũ nhắc hạn xa là danh sách sai — và không có cách nào nhìn ra tại sao
     một việc lại nằm đó. Một khối tên là "Sắp tới" mà không sắp theo hạn thì
     người dùng không thể tin nó, cũng không đoán được nó.

     Việc KHÔNG CÓ HẠN xuống cuối: chúng vẫn cần theo dõi (thư đã gửi đang chờ
     hồi âm) nhưng không tranh chỗ với thứ có mốc thật. */
  const sapToi = useMemo(
    () =>
      camKet
        .filter((c) => c.trangThai !== 'xong')
        .sort((a, b) => (a.han?.getTime() ?? Infinity) - (b.han?.getTime() ?? Infinity))
        .slice(0, 6),
    [camKet],
  )
  const emailDangMo = thuMo ? emails.find((e) => e.id === thuMo) : null

  /* ── RÊ CHUỘT CÓ CHỦ ĐÍCH ──────────────────────────────────────────────────
     Hai vấn đề người dùng gặp, cùng một gốc: bảng chi tiết đổi/biến mất ngay theo
     từng lần chuột lướt qua.

     • Đi từ thanh XUỐNG bảng thì con trỏ quét qua các thanh ở làn dưới. Mỗi thanh
       lại tự mở bảng của nó, nên bảng "nhảy" đi chỗ khác — người dùng thấy như nó
       biến mất, và phải BẤM vào thanh rồi mới với tới được nút.
     • Lướt ngang qua lưới cũng bật/tắt bảng liên tục, nhấp nháy.

     Chữa bằng độ trễ hai chiều: mở phải DỪNG LẠI một nhịp (140ms) mới tính là có
     ý định; đóng cũng chờ (260ms) để kịp đưa chuột sang bảng. Vào bảng thì huỷ
     hẹn đóng. Đây là mẫu "hover intent" quen thuộc, và nó là thứ duy nhất làm
     đường đi từ thanh sang nút trở nên tự nhiên. */
  const henMo = useRef<number | null>(null)
  const henDong = useRef<number | null>(null)
  const huyHen = () => {
    if (henMo.current) { clearTimeout(henMo.current); henMo.current = null }
    if (henDong.current) { clearTimeout(henDong.current); henDong.current = null }
  }
  const moThe = (v: { ck: CamKet; hcn: DOMRect }) => {
    huyHen()
    // Đang mở đúng thẻ đó rồi thì không đặt hẹn lại — nếu không, mỗi lần chuột
    // nhích trong cùng một thanh là một lần dựng lại bảng.
    if (dangHoi?.ck.id === v.ck.id) return
    henMo.current = window.setTimeout(() => setDangHoi(v), 140)
  }
  const dongThe = () => {
    if (henMo.current) { clearTimeout(henMo.current); henMo.current = null }
    henDong.current = window.setTimeout(() => setDangHoi(null), 260)
  }
  // Dọn hẹn khi rời trang — timer còn sống sau unmount là rò rỉ, và nó sẽ gọi
  // setState trên component đã chết.
  useEffect(() => huyHen, [])

  const hoiAI = (ck: CamKet) => {
    chuyenCanh(() => {
      setDangHoi(null)
      setChatMo(true)
    })
    // GHIM BỐI CẢNH, KHÔNG TỰ GỬI CÂU HỎI.
    //
    // Bản trước dựng sẵn một câu hỏi ("nên bắt đầu ngày nào, chia mấy buổi…") rồi gửi
    // NGAY khi bấm. Ngữ cảnh thì đủ, nhưng nó đoán luôn người dùng muốn hỏi gì — mà
    // phần lớn lúc bấm vào một việc, họ định hỏi chuyện khác: "tìm vé máy bay đi dự
    // sự kiện này". Khi đó câu hỏi dựng sẵn bị vứt đi CÙNG VỚI một lượt gọi model đã
    // trả tiền, và hạn mức gói free chỉ có 20 lượt/ngày.
    //
    // Nay chỉ ghim "đang nói về việc này" rồi chờ. Không gõ thì không tốn lượt nào,
    // và gõ gì cũng được — trợ lý vẫn biết đang bàn về việc nào.
    const han = ck.han
      ? `${ck.han.getDate()}/${ck.han.getMonth() + 1} lúc ${gioPhut(ck.han)}`
      : t('sc.noDue')
    const gio = Math.round(ck.uocLuongPhut / 6) / 10
    setBoiCanh({
      tieuDe: ck.noiDung,
      mo_ta:
        t('sc.dueAt', { han }) + (ck.hanSuyRa ? t('sc.inferred') : '')
        + t('sc.waitingEst', { ai: ck.nguoiCho, gio }),
    })
  }

  // Thư mở toàn màn: che hẳn lịch. Quay lại là về đúng chỗ cũ vì lịch không
  // bị unmount — state tháng, thẻ, chat đều còn nguyên.
  if (emailDangMo) {
    return (
      <div className="giao-dien-app flex h-screen w-full overflow-hidden bg-background text-foreground">
        <EmailDetail
          email={emailDangMo}
          onClose={() => chuyenCanh(() => setThuMo(null))}
          actions={KHONG_LAM_GI}
          onAgentAction={(c) => { chuyenCanh(() => { setThuMo(null); setChatMo(true) }); setLenh(c) }}
        />
      </div>
    )
  }

  return (
    <div className="giao-dien-app relative flex h-screen w-full overflow-hidden bg-background text-foreground">
      <AlertOverlay emails={emails} />

      {/* ══ CỘT TRÁI — lịch nhỏ + sắp tới. Đây là phần "tóm tắt" ══ */}
      {/* Mở chat → cột này GIÃN RA và cột giữa BIẾN MẤT. Trước đó cả hai cùng
          liệt kê lịch trình, tức là hai chỗ nói cùng một thứ trên một màn hình —
          thừa, và làm loãng chính thứ đang muốn nhấn. Mở chat thì màn hình chỉ
          còn đúng hai khối: lịch và cuộc trò chuyện. */}
      {/* Mở chat → cột này HẸP LẠI, không giãn ra. Bản trước cho nó `flex-1` nên nó
          chiếm 1022px để hiện một danh sách, còn cuộc trò chuyện — thứ người dùng vừa
          chủ động mở — chỉ được 400px cố định. Tỉ lệ ngược hẳn với ý định của họ.
          Đo trên khung 1422px: cột trái 1022 / chat 400. */}
      <aside className={cn(
        'den-noi-phai flex shrink-0 flex-col overflow-hidden',
        chatMo ? 'w-[340px]' : 'w-[268px]',
      )}>
        <div className="flex items-center gap-3 px-4 py-4">
          {/* Chặn điều hướng mặc định của Link để bọc được chuyển cảnh. Vẫn giữ
              thẻ <a> (có href thật) nên mở tab mới / bàn phím vẫn chạy đúng. */}
          <Link
            to="/app"
            onClick={(e) => {
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
              e.preventDefault()
              chuyenCanh(() => dieuHuong('/app'))
            }}
            className="o-icon size-8 shrink-0"
            aria-label={t('nav.backInbox')}
          >
            <ArrowLeft className="size-4" />
          </Link>
          <span className="text-[15px] font-semibold tracking-tight">{t('nav.schedule')}</span>
          <LogoMark className="ml-auto size-5 text-foreground/35" />
        </div>

        <LichNho thang={thang} homNay={homNay} theoNgay={theoNgay} onDoiThang={setThang} />

        {/* Chat mở → cột này là khối chính, nên hiện DANH SÁCH ĐẦY ĐỦ.
            Chat đóng → nó chỉ là phần tóm tắt bên cạnh lưới thẻ, nên rút gọn còn
            6 mục sắp tới. Cùng một chỗ, hai vai khác nhau tuỳ ngữ cảnh. */}
        {/* Khung bọc danh sách PHẢI là flex container. `DanhSachViec` dùng
            `flex-1 min-h-0 overflow-y-auto` để tự cuộn, nhưng hai lớp đó chỉ có
            tác dụng khi CHA là flex — bản trước khung bọc chỉ có `overflow-hidden`,
            nên danh sách cao tự nhiên, tràn ra rồi bị CẮT CỤT và không cuộn được. */}
        {chatMo ? (
          <div className="fade-y mt-1 flex min-h-0 flex-1 flex-col overflow-hidden">
            <DanhSachViec camKet={camKet} homNay={homNay} onBamThe={moThe} />
          </div>
        ) : (
        <div className="mt-1 flex min-h-0 flex-1 flex-col overflow-y-auto scrollbar-thin px-3 pb-3">
          <p className="px-1 py-2 font-mono text-[9.5px] uppercase tracking-[0.2em] text-muted-foreground/60">
            Sắp tới
            <span className="ml-1.5 normal-case tracking-normal text-muted-foreground/45">
              · 6 việc gần hạn nhất
            </span>
          </p>
          {loiTai ? (
            /* NÓI RA khi hỏng. "Chưa có việc nào" cho một lần tải thất bại là nói dối
               người dùng, và họ sẽ đi tìm lỗi ở chỗ khác — hoặc tin là mình rảnh. */
            <p className="rounded-lg bg-destructive/12 px-2 py-2 text-[12.5px] text-foreground ring-1 ring-destructive/40">
              Không tải được thư nên chưa dựng được lịch. Bạn thử tải lại trang giúp mình nhé.
            </p>
          ) : sapToi.length === 0 ? (
            <p className="px-1 text-[12.5px] text-muted-foreground">{t('st.noTasks')}</p>
          ) : (
            sapToi.map((c) => (
              <button
                key={c.id}
                onClick={(e) => moThe({ ck: c, hcn: e.currentTarget.getBoundingClientRect() })}
                className="group flex items-start gap-2.5 rounded-lg px-1 py-2 text-left transition-colors hover:bg-foreground/[0.04]"
              >
                <span className={cn('cham-rr mt-1.5', `c${c.mucRuiRo}`)} aria-hidden />
                <span className="flex min-w-0 flex-col gap-0.5">
                  {/* HAI DÒNG, không cắt cụt một dòng. Cột chỉ rộng 268px nên
                      `truncate` biến mọi tiêu đề thành "Xác nhận dự chung kết
                      Hackathon …" — người dùng phải rê chuột từng cái mới biết
                      việc gì. Đây là khối TÓM TẮT, thứ duy nhất nó phải làm được
                      là đọc lướt ra tên việc. */}
                  <span className="line-clamp-2 text-[12.5px] font-medium leading-snug">
                    {c.noiDung}
                  </span>
                  <span className="truncate text-[11px] text-muted-foreground">
                    {c.han ? nhanNgay(c.han, homNay) : t('sc.noDueShort')} · {c.nguoiCho}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
        )}
      </aside>

      {/* ══ KHUNG LỚN — lịch thẻ. ẨN HẲN khi chat mở. ══ */}
      {!chatMo && (
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="den-noi-duoi flex shrink-0 items-center gap-3 px-5 py-3.5">
          <h2 className="text-[17px] font-semibold tracking-tight">
            Tháng {thang.getMonth() + 1}/{thang.getFullYear()}
          </h2>
          <span className="font-mono text-[11px] tabular-nums text-[var(--spark)]">
            {String(camKet.filter((c) => c.trangThai !== 'xong').length).padStart(2, '0')} việc
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            <button onClick={() => setThang((t) => new Date(t.getFullYear(), t.getMonth() - 1, 1))}
              className="o-icon size-8" aria-label={t('cal.prev')}><ChevronLeft className="size-4" /></button>
            <button onClick={() => setThang(new Date(homNay.getFullYear(), homNay.getMonth(), 1))}
              className="nut-ky-thuat px-3 py-1.5 text-[11.5px] font-medium">{t('cal.today')}</button>
            {/* Đặt cạnh điều hướng tháng vì nó thuộc cùng câu chuyện: nhìn lịch thấy
                phải đi đâu đó, rồi tra ngay chỗ đi lại. */}
            <button onClick={() => setTraCuuMo(true)}
              className="nut-ky-thuat flex items-center gap-1.5 px-3 py-1.5 text-[11.5px] font-medium">
              <Plane className="size-3.5" /> Tra cứu đi lại
            </button>
            <button onClick={() => setThang((t) => new Date(t.getFullYear(), t.getMonth() + 1, 1))}
              className="o-icon size-8" aria-label={t('cal.next')}><ChevronRight className="size-4" /></button>
          </div>
        </header>

        {/* Chat mở → lịch NHỎ LẠI và ưu tiên danh sách. Người dùng vừa mở chat là
            họ đang muốn BÀN về lịch, không phải ngắm lưới tháng. */}
        <LuoiThe o={o} thang={thang} homNay={homNay} theoNgay={theoNgay} camKet={camKet}
          onBamThe={moThe} onRoiThe={dongThe} dangReId={dangHoi?.ck.id ?? null}
          onMoNgay={setNgayMo} />
      </main>
      )}

      {/* ══ CHAT — nút tượng trưng góc dưới phải, bấm mới hiện ══ */}
      {chatMo ? (
        <div className="den-noi-trai flex min-w-0 flex-1 flex-col">
          <ChatPanel
            emails={emails}
            actions={KHONG_LAM_GI}
            injectedCommand={lenh}
            onInjectConsumed={() => setLenh(null)}
            boiCanh={boiCanh}
            onBoBoiCanh={() => setBoiCanh(null)}
            onClose={() => setChatMo(false)}
          />
        </div>
      ) : (
        <button
          onClick={() => setChatMo(true)}
          aria-label={t('nav.openAssistant')}
          // `position` ghi NỘI TUYẾN: `.goc-cat` đặt position:relative và nó thắng
          // tiện ích `fixed` của Tailwind (CSS tự viết nằm ngoài @layer). Dùng class
          // thì nút rơi lên góc trên phải — đã dính đúng vậy.
          style={{ position: 'fixed', bottom: 24, right: 24 }}
          className="den-vien-chon goc-cat z-40 flex size-14 items-center justify-center
                     bg-[var(--elevated)]/92 backdrop-blur-md transition-transform
                     hover:scale-105 active:scale-95"
        >
          <Sparkles className="size-6 text-[var(--spark)]" />
        </button>
      )}

      {/* ══ KHUNG HỎI khi bấm một thẻ ══ */}
      {dangHoi && (
        <ThanhViec
          ck={dangHoi.ck} hcn={dangHoi.hcn}
          onGiuMo={huyHen}
          onDong={dongThe}
          onXemThu={() => chuyenCanh(() => { setThuMo(dangHoi.ck.emailId); setDangHoi(null) })}
          onHoiAI={() => hoiAI(dangHoi.ck)}
        />
      )}

      {traCuuMo && <TraCuuPanel onDong={() => setTraCuuMo(false)} />}

      {/* ══ BẢNG NGÀY — lối thoát cho các việc không đủ làn trong ô ══ */}
      {ngayMo && (
        <BangNgay
          ngay={ngayMo.ngay}
          hcn={ngayMo.hcn}
          viec={theoNgay.get(khoaNgay(ngayMo.ngay)) ?? []}
          onDong={() => setNgayMo(null)}
          onXemThu={(ck) => chuyenCanh(() => { setThuMo(ck.emailId); setNgayMo(null) })}
          onHoiAI={(ck) => { setNgayMo(null); hoiAI(ck) }}
        />
      )}
    </div>
  )
}

/* ── BẢNG MỘT NGÀY ────────────────────────────────────────────────────────────
   VÌ SAO CẦN. Ô ngày chỉ vẽ được 3 làn. Một ngày 7 việc thì 4 cái còn lại chỉ
   hiện thành chữ "+4" — mà chữ đó trước đây là chữ CHẾT: người dùng biết có thứ
   đang bị giấu nhưng không có cách nào xem. Thế còn tệ hơn không hiện gì.

   VÌ SAO KHÔNG NỚI SỐ LÀN. Cho ô cao thêm để chứa đủ 7 việc thì hàng tuần đó cao
   gấp đôi các hàng khác, lưới méo, và mất luôn khả năng so ngày này với ngày kia
   bằng mắt — thứ mà một cuốn lịch tồn tại để làm. Ô ngày phải giữ kích thước cố
   định; phần tràn cần một MẶT PHẲNG KHÁC, không phải nhiều chỗ hơn trên cùng mặt.

   Nên: lưới nói "ngày này nặng" (3 thanh + số +N + vạch tải), bảng này nói "nặng
   những gì". Cùng nguyên tắc đã dùng cho bảng chi tiết khi rê chuột. */
function BangNgay({
  ngay, hcn, viec, onDong, onXemThu, onHoiAI,
}: {
  ngay: Date
  hcn: DOMRect
  viec: CamKet[]
  onDong: () => void
  onXemThu: (ck: CamKet) => void
  onHoiAI: (ck: CamKet) => void
}) {
  const W = 320
  const xep = useMemo(
    () => [...viec].sort((a, b) =>
      b.mucUuTien - a.mucUuTien ||
      (a.han?.getTime() ?? 0) - (b.han?.getTime() ?? 0)),
    [viec],
  )
  const phut = viec.reduce((s, c) => s + phutMoiNgay(c), 0)
  const quaTai = phut > TRAN_MOI_NGAY

  // Kẹp trong màn hình theo CẢ HAI trục. Ô ngày ở cột Chủ nhật hay ở hàng cuối
  // đều đẩy bảng ra ngoài nếu chỉ căn theo ô.
  const left = Math.min(Math.max(8, hcn.left - 8), window.innerWidth - W - 8)
  const CAO_TOI_DA = Math.min(360, window.innerHeight - 24)
  const duoi = hcn.bottom + 6
  const lat = duoi + CAO_TOI_DA > window.innerHeight - 8
  const top = lat
    ? Math.max(12, Math.min(hcn.top - 6 - CAO_TOI_DA, window.innerHeight - CAO_TOI_DA - 12))
    : duoi

  return (
    <>
      {/* Nền bắt cú bấm ra ngoài. Bảng này mở bằng CÚ BẤM (khác bảng rê chuột),
          nên phải đóng bằng cú bấm — rời chuột là đóng thì không đọc kịp. */}
      <div className="fixed inset-0 z-40" onClick={onDong} aria-hidden />
      <div
        role="dialog"
        aria-label={t('sc.dayTasks', { ngay: `${ngay.getDate()}/${ngay.getMonth() + 1}` })}
        // `position` NỘI TUYẾN — `.goc-cat` đặt position:relative và thắng `fixed`
        // của Tailwind. Cái bẫy này đã dính hai lần trong file này.
        style={{ position: 'fixed', left, top, width: W, maxHeight: CAO_TOI_DA }}
        className="goc-cat goc-cat-nho den-vien-chon z-50 flex flex-col
                   bg-[var(--nen-2,var(--elevated))]/97 backdrop-blur-md
                   shadow-[0_14px_40px_-10px_rgba(0,0,0,0.65)]"
      >
        <div className="flex shrink-0 items-baseline gap-2 border-b border-border/20 px-3 py-2.5">
          <span className="font-mono text-[15px] font-bold tabular-nums text-foreground">
            {ngay.getDate()}/{ngay.getMonth() + 1}
          </span>
          <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground/60">
            {THU[ngay.getDay()]} · {viec.length} việc
          </span>
          <span className={cn(
            'ml-auto font-mono text-[9.5px] tabular-nums',
            quaTai ? 'font-bold text-[var(--ut-gap)]' : 'text-muted-foreground',
          )}>
            {t('sc.hours', { n: Math.round(phut / 6) / 10 })}
            {quaTai ? t('sc.overloaded') : ''}
          </span>
        </div>

        {/* Cuộn được: bảng này KHÔNG có trần số việc, khác hẳn ô ngày. Đây là chỗ
            duy nhất trong màn lịch được phép cuộn, vì nó là mặt phẳng phụ chứ
            không phải bức tranh tổng thể. */}
        {/* `fade-y` làm mờ dần hai mép vùng cuộn. Không có nó thì dòng cuối bị cắt
            ngang thân chữ trông như lỗi render, chứ không đọc ra là "còn nữa". */}
        <div className="fade-y min-h-0 flex-1 overflow-y-auto scrollbar-thin">
          {xep.map((c) => (
            <div key={c.id} className="border-b border-border/10 px-3 py-2 last:border-b-0">
              <div className="flex items-start gap-2">
                <span
                  className={cn(
                    'mt-1 h-3 w-[3px] shrink-0',
                    c.mucUuTien === 3 ? 'uu-tien-3' : c.mucUuTien === 2 ? 'uu-tien-2' : 'uu-tien-1',
                  )}
                  style={{ background: 'var(--ut)' }}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  {/* Tiêu đề ĐẦY ĐỦ, không cắt — đúng lý do bảng này tồn tại. */}
                  <p className="text-[12px] font-medium leading-snug text-foreground">
                    {c.noiDung}
                  </p>
                  <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                    {c.nguoiCho}
                    {c.han ? t('sc.dueSuffix', { gio: gioPhut(c.han) }) : ''}
                    {c.batDau && khoaNgay(c.batDau) !== khoaNgay(c.han ?? c.batDau)
                      ? t('sc.multiDay') : ''}
                  </p>
                </div>
                <div className="flex shrink-0 gap-0.5">
                  <button
                    onClick={() => onXemThu(c)}
                    title={t('mail.viewOriginal')}
                    className="o-icon size-6"
                  >
                    <Mail className="size-3" />
                  </button>
                  <button
                    onClick={() => onHoiAI(c)}
                    title={t('mail.askAssistant')}
                    className="o-icon size-6"
                  >
                    <MessageSquare className="size-3" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}

/** Trang lịch KHÔNG thao tác trên thư — người dùng ở đây đang nghĩ về thời gian. */
const KHONG_LAM_GI: EmailActions = {
  markRead: () => {},
  setImportant: () => {},
  applyLabel: () => {},
  removeEmails: () => {}, restoreEmails: () => {}, markSpam: () => {},
}

/* ── Lịch nhỏ ở cột trái ─────────────────────────────────────────────────── */
function LichNho({
  thang, homNay, theoNgay, onDoiThang,
}: {
  thang: Date
  homNay: Date
  theoNgay: Map<string, CamKet[]>
  onDoiThang: (d: Date) => void
}) {
  const o = useMemo(() => luoiThang(thang.getFullYear(), thang.getMonth()), [thang])
  return (
    <div className="shrink-0 px-3">
      <div className="mb-1.5 flex items-center justify-between px-1">
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
          Th {thang.getMonth() + 1}/{thang.getFullYear()}
        </span>
        <span className="flex gap-0.5">
          <button onClick={() => onDoiThang(new Date(thang.getFullYear(), thang.getMonth() - 1, 1))}
            className="o-icon size-6" aria-label={t('cal.prev')}><ChevronLeft className="size-3" /></button>
          <button onClick={() => onDoiThang(new Date(thang.getFullYear(), thang.getMonth() + 1, 1))}
            className="o-icon size-6" aria-label={t('cal.next')}><ChevronRight className="size-3" /></button>
        </span>
      </div>
      <div className="grid grid-cols-7 gap-px">
        {['2', '3', '4', '5', '6', '7', 'C'].map((t) => (
          <span key={t} className="pb-1 text-center font-mono text-[9px] text-muted-foreground/50">{t}</span>
        ))}
        {o.map((d) => {
          const co = (theoNgay.get(khoaNgay(d)) ?? []).length
          return (
            <span key={d.toISOString()}
              className={cn(
                'relative flex h-7 items-center justify-center font-mono text-[10.5px] tabular-nums',
                d.getMonth() === thang.getMonth() ? 'text-foreground/75' : 'text-foreground/20',
                khoaNgay(d) === khoaNgay(homNay) && 'font-bold text-[var(--spark)]',
              )}
            >
              {d.getDate()}
              {co > 0 && (
                <i className="absolute bottom-0.5 size-1 rounded-full bg-[var(--rr-hoan)]" />
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
}

/* ── Lưới tháng với THẺ ──────────────────────────────────────────────────── */
function LuoiThe({
  o, thang, homNay, theoNgay, camKet, onBamThe, onRoiThe, dangReId, onMoNgay,
}: {
  o: Date[]
  thang: Date
  homNay: Date
  theoNgay: Map<string, CamKet[]>
  camKet: CamKet[]
  onBamThe: (v: { ck: CamKet; hcn: DOMRect }) => void
  onRoiThe: () => void
  /** Id cam kết đang được rê chuột — MỌI đoạn của nó đều sáng, kể cả ở hàng khác. */
  dangReId: string | null
  onMoNgay: (v: { ngay: Date; hcn: DOMRect }) => void
}) {
  const tuan = useMemo(() => xepDoanTheoTuan(camKet, o), [camKet, o])

  // CẮT HÀNG TUẦN RỖNG Ở ĐÁY. Lưới tháng luôn là 6 hàng, nhưng phần lớn tháng chỉ
  // cần 5 — hàng thừa nằm hoàn toàn ngoài tháng và trống trơn. Giữ nó lại là ăn
  // mất 1/6 chiều cao để không nói gì, mà chiều cao đó chính là thứ các hàng còn
  // lại đang thiếu (thẻ bị cắt chữ vì ô quá thấp).
  const soTuan = useMemo(() => {
    for (let w = 5; w >= 0; w--) {
      const trongThang = o.slice(w * 7, w * 7 + 7).some((d) => d.getMonth() === thang.getMonth())
      if (trongThang || tuan[w].doan.length > 0) return w + 1
    }
    return 6
  }, [o, thang, tuan])

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1 p-3">
      <div className="grid shrink-0 grid-cols-7 gap-1">
        {['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'].map((t) => (
          <div key={t} className="pb-0.5 text-center font-mono text-[9.5px] uppercase tracking-[0.16em] text-muted-foreground/55">
            {t}
          </div>
        ))}
      </div>
      {tuan.slice(0, soTuan).map((tt, w) => (
        <HangTuan
          key={o[w * 7].toISOString()}
          ngay={o.slice(w * 7, w * 7 + 7)}
          thang={thang}
          homNay={homNay}
          theoNgay={theoNgay}
          doan={tt.doan}
          dot={tt.dot}
          du={tt.du}
          onBamThe={onBamThe}
          onRoiThe={onRoiThe}
          dangReId={dangReId}
          onMoNgay={onMoNgay}
        />
      ))}
    </div>
  )
}

/* ── MỘT HÀNG TUẦN = ô ngày ở dưới + LỚP THANH phủ lên trên ──────────────────
   Bản trước để mỗi ô ngày tự vẽ phần thẻ của mình rồi trông chờ các mảnh cạnh
   nhau trông như một thanh liền. Chúng không liền — giữa hai ô có khe lưới, có
   viền, có padding — nên một việc ba ngày hiện ra ba viên rời rạc và mắt đọc ra
   ba việc. Mà cả lý do tồn tại của màn này là cho thấy việc DÀI tới đâu.

   Nay thanh là MỘT phần tử trải ngang qua nhiều cột. Lớp thanh dùng lại đúng
   `grid-cols-7 gap-1` của lớp ô bên dưới, nên nó tự khớp cột — không phải tính
   phần trăm bằng tay, và không lệch khi đổi khoảng cách lưới.

   Mỗi làn là MỘT HÀNG của lưới con (`grid-rows-[repeat(3,17px)]`), nên hai việc
   trùng ngày nằm đúng hai làn mà không cần cộng trừ vị trí. */
function HangTuan({
  ngay, thang, homNay, theoNgay, doan, dot, du, onBamThe, onRoiThe, dangReId, onMoNgay,
}: {
  ngay: Date[]
  thang: Date
  homNay: Date
  theoNgay: Map<string, CamKet[]>
  doan: DoanThe[]
  /** Đợt dài — vẽ ở DẢI RIÊNG dưới đáy, không tranh làn với việc trong ngày. */
  dot: DoanThe[]
  du: Map<string, number>
  onBamThe: (v: { ck: CamKet; hcn: DOMRect }) => void
  onRoiThe: () => void
  dangReId: string | null
  onMoNgay: (v: { ngay: Date; hcn: DOMRect }) => void
}) {
  return (
    <div className="relative min-h-0 flex-1">
      <div className="grid h-full grid-cols-7 gap-1">
        {ngay.map((d) => (
          <ONgay
            key={d.toISOString()}
            ngay={d}
            trongThang={d.getMonth() === thang.getMonth()}
            laHomNay={khoaNgay(d) === khoaNgay(homNay)}
            viec={theoNgay.get(khoaNgay(d)) ?? []}
            con={du.get(khoaNgay(d)) ?? 0}
            onMoNgay={(hcn) => onMoNgay({ ngay: d, hcn })}
          />
        ))}
      </div>

      {/* `top-[26px]` chừa chỗ cho số ngày; `pointer-events-none` để khoảng trống
          giữa các thanh không nuốt cú rê chuột vào ô ngày bên dưới. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-1 top-[26px] grid grid-cols-7 grid-rows-[repeat(3,17px)] content-start gap-x-1 gap-y-[3px] px-1">
        {doan.map((dt) => (
          <ThanhCamKet
            key={dt.ck.id + '-' + dt.cot}
            doan={dt}
            mo={dt.ck.han ? dt.ck.han.getMonth() !== thang.getMonth() : false}
            dangRe={dangReId === dt.ck.id}
            onBam={(e) => onBamThe({ ck: dt.ck, hcn: e.currentTarget.getBoundingClientRect() })}
            onRoi={onRoiThe}
          />
        ))}
      </div>

      {/* ── DẢI ĐỢT DÀI — không gian RIÊNG ở đáy ──
          Mỏng hơn thanh việc (11px so với 17px) và nằm dưới cùng, ngay trên vạch
          tải. Hình dáng đó nói đúng vai trò: đây là NỀN của tuần, không phải việc
          phải làm hôm nay. Trước đây chúng dùng chung ba làn với việc ngắn, và một
          ngày sáu việc chỉ vẽ được một vì hai đợt dài đã chiếm hai làn. */}
      {dot.length > 0 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-[9px] grid grid-cols-7
                        grid-rows-[repeat(2,11px)] content-end gap-x-1 gap-y-[2px] px-1">
          {dot.map((dt) => (
            <ThanhCamKet
              key={dt.ck.id + '-dot-' + dt.cot}
              doan={dt}
              mo={dt.ck.han ? dt.ck.han.getMonth() !== thang.getMonth() : false}
              dangRe={dangReId === dt.ck.id}
              laDot
              onBam={(e) => onBamThe({ ck: dt.ck, hcn: e.currentTarget.getBoundingClientRect() })}
              onRoi={onRoiThe}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** Ô một ngày — giờ chỉ còn NỀN: số ngày, vạch tải, và "+N" khi hết làn.
 *  Việc vẽ thẻ đã chuyển hẳn lên lớp thanh của `HangTuan`. */
function ONgay({
  ngay, trongThang, laHomNay, viec, con, onMoNgay,
}: {
  ngay: Date
  trongThang: boolean
  laHomNay: boolean
  viec: CamKet[]
  con: number
  onMoNgay: (hcn: DOMRect) => void
}) {
  // Chia đều phút theo số ngày việc trải qua. Cộng thẳng `uocLuongPhut` cho mọi
  // ngày như bản trước thì một việc 6 tiếng trải 3 ngày bị tính thành 18 tiếng,
  // và ngày nào cũng "quá tải" — cảnh báo lúc nào cũng bật thì hết là cảnh báo.
  const phut = viec.reduce((s, c) => s + phutMoiNgay(c), 0)
  const ty = Math.min(1, phut / TRAN_MOI_NGAY)
  const quaTai = phut > TRAN_MOI_NGAY

  return (
    <div
      className={cn(
        'goc-cat-nho goc-cat relative flex min-h-0 flex-col p-1.5',
        laHomNay ? 'den-vien-chon' : 'den-vien',
        // 30% là quá mờ — nội dung thật rơi vào hàng ngoài tháng thì gần như biến
        // mất. 55% vẫn đọc được mà vẫn lùi ra sau tháng đang xem.
        !trongThang && 'opacity-55',
      )}
    >
      {/* Số ngày là NÚT khi ngày đó có việc. Bấm vào mở bảng liệt kê đầy đủ.
          Bấm vào con số của ngày là thao tác người ta làm theo bản năng ở mọi
          cuốn lịch, nên gắn hành động vào đó không phải học gì thêm. */}
      <span className="flex shrink-0 items-center justify-between">
        {viec.length > 0 ? (
          <button
            onClick={(e) => onMoNgay(e.currentTarget.getBoundingClientRect())}
            title={t('sc.nTasksOn', { n: viec.length, ngay: `${ngay.getDate()}/${ngay.getMonth() + 1}` })}
            className={cn(
              'nhay-bat -mx-0.5 rounded px-0.5 font-mono text-[11px] tabular-nums',
              'transition-colors hover:bg-foreground/10',
              laHomNay ? 'font-bold text-[var(--spark)]' : 'text-foreground/70',
            )}
          >
            {ngay.getDate()}
          </button>
        ) : (
          <span className={cn(
            'font-mono text-[11px] tabular-nums',
            laHomNay ? 'font-bold text-[var(--spark)]' : 'text-foreground/70',
          )}>
            {ngay.getDate()}
          </span>
        )}

        {/* "+N" PHẢI BẤM ĐƯỢC. Trước đây nó là một dòng chữ chết: người dùng biết
            còn 4 việc nữa mà không có cách nào xem chúng — tệ hơn cả không hiện
            gì, vì nó nói rằng có thứ đang bị giấu rồi bỏ mặc ở đó. */}
        {con > 0 && (
          <button
            onClick={(e) => onMoNgay(e.currentTarget.getBoundingClientRect())}
            title={t('sc.seeRest', { n: con })}
            className="nhay-bat rounded px-1 font-mono text-[9px] font-semibold
                       text-[var(--ut-gap)] transition-colors hover:bg-foreground/10"
          >
            +{con}
          </button>
        )}
      </span>

      {/* VẠCH TẢI ở đáy ô — trả lời câu hỏi thật của người dùng: không phải "ngày
          này có việc không" mà "ngày này nặng tới đâu". Nhờ nó mà một ô không có
          thẻ nào vẫn khác một ô kín việc, và cả tháng đọc ra được bằng một cái
          liếc thay vì phải đếm từng thanh. */}
      {phut > 0 && (
        <span
          className="absolute inset-x-1.5 bottom-1 h-[2px] overflow-hidden rounded-full bg-foreground/8"
          title={t('sc.hours', { n: Math.round(phut / 6) / 10 })}
        >
          <span
            className={cn(
              'block h-full rounded-full transition-[width] duration-300 ease-soft',
              quaTai ? 'bg-[var(--rr-khong)]' : 'bg-[var(--spark)]/70',
            )}
            style={{ width: `${Math.max(8, ty * 100)}%` }}
          />
        </span>
      )}
    </div>
  )
}

/** Một THANH cam kết trải ngang qua các cột của hàng tuần.
 *
 *  Ba mức ưu tiên phải đọc được mà KHÔNG cần so sánh cạnh nhau, nên mỗi mức khác
 *  nhau ở ba thứ cùng lúc: hình (▲ ● ▪), độ dày vạch trái, và cường độ quầng
 *  sáng. Chỉ đổi màu là không đủ — người mù màu không thấy gì, và ngay cả mắt
 *  thường cũng khó xếp hạng ba màu nếu chúng không đứng cạnh nhau. */
function ThanhCamKet({
  doan, mo, dangRe, laDot, onBam, onRoi,
}: {
  doan: DoanThe
  /** Hạn nằm ngoài tháng đang xem → lùi lại một bậc cho khỏi tranh chỗ. */
  mo: boolean
  /** MỌI đoạn của cùng một đợt cùng sáng, kể cả đoạn ở hàng tuần khác.
   *
   *  Trước đây chỉ đoạn dưới con trỏ sáng lên, vì hiệu ứng nằm ở lớp `hover:` của
   *  Tailwind — thứ chỉ biết đến đúng phần tử đang bị rê. Nhưng một đợt ba tuần là
   *  MỘT việc; sáng lẻ một khúc thì mắt không nối được ba khúc lại với nhau, và cả
   *  lý do vẽ thanh trải dài (cho thấy việc kéo dài tới đâu) mất tác dụng ngay lúc
   *  người dùng đang tìm hiểu nó. Nên trạng thái rê phải nằm ở TRÊN, theo id cam
   *  kết, chứ không nằm ở CSS của từng đoạn. */
  dangRe: boolean
  /** Là ĐỢT DÀI (vẽ ở dải đáy) — mỏng hơn, chữ nhỏ hơn, mờ hơn một bậc.
   *  Khác biệt về hình dáng là thứ giúp mắt phân biệt "nền của tuần" với "việc
   *  hôm nay" mà không cần đọc chữ. */
  laDot?: boolean
  onBam: (e: { currentTarget: HTMLElement }) => void
  onRoi: () => void
}) {
  const { ck, cot, rong, lan, moDau, ketThuc } = doan
  const ut = ck.mucUuTien
  // Ba mức phải đọc được KHÔNG CẦN so sánh cạnh nhau, nên mỗi mức khác ở BỐN thứ
  // cùng lúc: hình, độ dày vạch, cường độ quầng, và độ đậm chữ. Chỉ đổi màu thì
  // người mù màu không thấy gì, mà mắt thường cũng khó xếp hạng ba màu khi chúng
  // nằm rải rác trên lưới chứ không đứng cạnh nhau.
  const dau = ut === 3 ? '▲' : ut === 2 ? '◆' : '▪'
  return (
    <button
      // RÊ CHUỘT là đủ để xổ bảng chi tiết — không tốn một cú bấm chỉ để biết có
      // gì. Giữ onClick cho bàn phím/cảm ứng, nơi không có "rê chuột".
      onMouseEnter={onBam}
      onMouseLeave={onRoi}
      onFocus={onBam}
      onBlur={onRoi}
      onClick={onBam}
      style={{ gridColumn: `${cot + 1} / span ${rong}`, gridRow: lan + 1 }}
      title={ck.noiDung}
      className={cn(
        'nhay-bat pointer-events-auto relative flex items-center gap-1 overflow-hidden pr-1 text-left',
        // Đợt dài MỎNG HƠN và chữ nhỏ hơn: hình dáng phải nói được vai trò, để mắt
        // phân biệt "nền của tuần" với "việc hôm nay" mà không cần đọc chữ.
        laDot ? 'h-[11px] text-[8.5px] opacity-80' : 'h-[17px]',
        'transition-[box-shadow,transform] duration-150 ease-soft hover:z-30 hover:scale-[1.012]',
        ut === 3 ? 'uu-tien-3' : ut === 2 ? 'uu-tien-2' : 'uu-tien-1',
        'bg-[var(--elevated)]/90 backdrop-blur-sm',
        ut === 3
          // Nhịp thở nhẹ chỉ dành cho việc SÁT HẠN — thứ duy nhất đáng kéo mắt
          // người dùng về khi họ đang nhìn chỗ khác trên lưới.
          ? 'tho-gap'
          : ut === 2
            ? 'shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--ut)_60%,transparent),0_0_10px_-5px_var(--ut)]'
            : 'shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--ut)_26%,transparent)]',
        'hover:shadow-[inset_0_0_0_1px_var(--ut),0_0_20px_-2px_var(--ut)]',
        // Cả đợt cùng sáng. Ghi SAU các lớp bóng mặc định để nó thắng, và dùng cùng
        // cường độ với `hover:` để đoạn dưới con trỏ không nổi hơn các đoạn kia —
        // chúng là một việc, phải trông như một việc.
        dangRe && 'z-20 shadow-[inset_0_0_0_1px_var(--ut),0_0_20px_-2px_var(--ut)]',
        // Bo góc CHỈ ở hai đầu THẬT của đợt. Đoạn bị tuần cắt để vuông, nên nhìn
        // sang hàng dưới vẫn đọc ra là "còn tiếp".
        moDau && 'rounded-l-[4px]',
        ketThuc && 'rounded-r-[4px]',
        mo && 'opacity-70',
      )}
    >
      {/* Vạch ưu tiên bên trái: cấp 3 dày 4px, cấp 2 dày 3px, cấp 1 mảnh 2px. */}
      {moDau ? (
        <span
          className="h-full shrink-0 bg-[var(--ut)]"
          style={{ width: ut === 3 ? 4 : ut === 2 ? 3 : 2 }}
          aria-hidden
        />
      ) : (
        // Đoạn nối tiếp từ tuần trước — mũi nhọn thay cho vạch, để không đọc nhầm
        // thành một việc mới bắt đầu.
        <span className="shrink-0 pl-1 font-mono text-[9px] leading-none text-[var(--ut)]" aria-hidden>‹</span>
      )}

      {moDau && (
        <span className="shrink-0 text-[8px] leading-none text-[var(--ut)]" aria-hidden>{dau}</span>
      )}

      <span className={cn(
        'truncate text-[10px] leading-none',
        ut === 3 ? 'font-semibold text-foreground' : ut === 2 ? 'font-medium text-foreground/90' : 'text-foreground/75',
      )}>
        {ck.noiDung}
      </span>

      {/* Dấu hạn chỉ đặt ở ĐÚNG ngày hạn, và chỉ khi thanh đủ rộng để không đè chữ. */}
      {ketThuc && rong >= 2 && ck.han && (
        <span className="ml-auto shrink-0 font-mono text-[8.5px] tabular-nums text-muted-foreground">
          {gioPhut(ck.han)}
        </span>
      )}
    </button>
  )
}

/* ── Danh sách việc (khi chat mở, lịch nhường chỗ) ───────────────────────── */
function DanhSachViec({
  camKet, homNay, onBamThe,
}: {
  camKet: CamKet[]
  homNay: Date
  onBamThe: (v: { ck: CamKet; hcn: DOMRect }) => void
}) {
  const con = camKet.filter((c) => c.trangThai !== 'xong')
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-thin p-3">
      {con.map((c) => (
        <button
          key={c.id}
          onClick={(e) => onBamThe({ ck: c, hcn: e.currentTarget.getBoundingClientRect() })}
          className={cn(
            'goc-cat flex items-start gap-3 p-3 text-left transition-transform hover:-translate-y-px',
            c.mucRuiRo === 3 ? 'rui-ro-3' : c.mucRuiRo === 2 ? 'rui-ro-2' : 'rui-ro-1',
          )}
        >
          <span className={cn('cham-rr mt-1.5', `c${c.mucRuiRo}`)} aria-hidden />
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="truncate text-[13.5px] font-medium">{c.noiDung}</span>
            <span className="flex flex-wrap items-center gap-x-2 text-[11.5px] text-muted-foreground">
              <span className="inline-flex items-center gap-1"><Mail className="size-3" />{c.nguoiCho}</span>
              {c.uocLuongPhut > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Clock className="size-3" />
                  {c.uocLuongPhut >= 60
                    ? t('ck.hours', { n: c.uocLuongPhut / 60 })
                    : t('ck.minutes', { n: c.uocLuongPhut })}
                </span>
              )}
            </span>
          </span>
          <span className="shrink-0 font-mono text-[10.5px] tabular-nums text-muted-foreground">
            {c.han ? nhanNgay(c.han, homNay) : '—'}
          </span>
        </button>
      ))}
    </div>
  )
}

/* ── Khung hỏi: xem thư hay hỏi AI ───────────────────────────────────────── */
/**
 * ThanhViec — thanh hành động xổ ra NGAY DƯỚI thẻ khi rê chuột.
 *
 * ── VÌ SAO KHÔNG DÙNG HỘP THOẠI NHƯ BẢN TRƯỚC ──
 * Bản trước bấm vào thẻ mới mở một hộp có hai dòng chữ. Hai vấn đề: nó tốn một
 * cú bấm chỉ để BIẾT có những lựa chọn gì, và nó là một hộp chữ đặt đè lên lịch
 * — nặng nề so với việc nó chỉ đang hỏi "xem thư hay hỏi trợ lý".
 *
 * Xổ ra khi rê chuột thì lựa chọn tự lộ, không tốn cú bấm nào; và hai icon thì
 * nhận ra nhanh hơn hai dòng chữ.
 *
 * ── VÌ SAO ĐỊNH VỊ `fixed` CHỨ KHÔNG ĐẶT TRONG THẺ ──
 * Ô ngày mang `clip-path` (góc cắt), mà clip-path CẮT CẢ CON. Đặt thanh này bên
 * trong thẻ thì nó bị xén mất ngay khi tràn khỏi ô. Nên tính toạ độ từ hình chữ
 * nhật của thẻ rồi vẽ ở tầng trên cùng.
 */
function ThanhViec({
  ck, hcn, onGiuMo, onDong, onXemThu, onHoiAI,
}: {
  ck: CamKet
  hcn: DOMRect
  /** Chuột vào bảng → HUỶ hẹn đóng. Thiếu cái này thì độ trễ chỉ hoãn được vấn đề:
   *  bảng vẫn tự đóng đúng lúc người dùng đang với tay tới nút. */
  onGiuMo: () => void
  onDong: () => void
  onXemThu: () => void
  onHoiAI: () => void
}) {
  // Rộng hơn hẳn bản trước (188 → 300). Thanh trong lưới chỉ cao 17px và rộng
  // bằng một ô ngày, nên tiêu đề LUÔN bị cắt — đó là giới hạn của lưới tháng,
  // không phải lỗi sửa được bằng cách chỉnh cỡ chữ. Chỗ đọc đủ phải là ĐÂY.
  //
  // Chia vai rõ: lưới là BẢN ĐỒ (ở đâu, dài bao lâu, gấp cỡ nào), bảng này là
  // CHI TIẾT (việc gì, ai chờ, hạn lúc nào, tốn bao lâu).
  const W = 300
  const left = Math.min(Math.max(8, hcn.left + hcn.width / 2 - W / 2), window.innerWidth - W - 8)
  // Bảng cao hơn nên phải tự lật LÊN TRÊN khi thẻ nằm sát đáy màn hình — không
  // thì nó tràn ra ngoài và người dùng không đọc được gì.
  const CAO = 150
  // KHÔNG chừa khe giữa thanh và bảng. Khe hở là chỗ con trỏ "rơi ra ngoài" giữa
  // đường, và mỗi lần rơi là một lần hẹn đóng chạy. Dán sát mép dưới thanh thì
  // đường đi từ thanh sang nút liền một mạch.
  const duoi = hcn.bottom
  const lat = duoi + CAO > window.innerHeight - 8
  const top = lat ? Math.max(8, hcn.top - CAO) : duoi

  const ut = ck.mucUuTien
  const nhanUuTien = t(ut === 3 ? 'sc.prio3' : ut === 2 ? 'sc.prio2' : 'sc.prio1')
  const gio = Math.round(ck.uocLuongPhut / 6) / 10

  return (
    <div
      onMouseEnter={onGiuMo}
      onMouseLeave={onDong}
      // `position` PHẢI ghi nội tuyến. `.goc-cat` đặt `position: relative`, và vì
      // nó là CSS tự viết nằm ngoài @layer nên nó THẮNG tiện ích `fixed` của
      // Tailwind. Dùng class thì thanh này thành `relative`, rơi vào dòng chảy
      // bình thường ở cuối DOM và văng ra ngoài màn hình — đã đo được: left 2260,
      // top 1017 trên khung 1440×900.
      //
      // Đúng cái bẫy đã ghi chú cho nút trợ lý ở trên, và tôi vẫn giẫm lại. Ghi
      // ở CẢ HAI chỗ để lần sau ai đọc file này cũng vấp thấy.
      style={{ position: 'fixed', left, top, width: W }}
      className={cn(
        'nhay-bat goc-cat-nho goc-cat z-50 flex flex-col gap-2 p-2.5 backdrop-blur-md',
        ut === 3 ? 'uu-tien-3' : ut === 2 ? 'uu-tien-2' : 'uu-tien-1',
        'border border-[color-mix(in_srgb,var(--ut)_60%,transparent)]',
        'bg-[var(--nen-2,var(--elevated))]/97',
        'shadow-[0_10px_30px_-8px_rgba(0,0,0,0.6)]',
      )}
    >
      {/* Hàng nhãn: mức ưu tiên + hạn. Hai thứ quyết định "có làm ngay không". */}
      <div className="flex items-center gap-2">
        <span className={cn(
          'shrink-0 px-1.5 py-0.5 font-mono text-[8.5px] uppercase tracking-[0.14em]',
          'border border-[color-mix(in_srgb,var(--ut)_55%,transparent)] text-[var(--ut)]',
        )}>
          {nhanUuTien}
        </span>
        {ck.han && (
          <span className="truncate font-mono text-[9.5px] tabular-nums text-muted-foreground">
            {ck.han.getDate()}/{ck.han.getMonth() + 1} · {gioPhut(ck.han)}
          </span>
        )}
        {/* Hạn SUY RA phải nói rõ là suy ra. Trình bày một phỏng đoán như một sự
            thật là cách nhanh nhất làm người dùng mất tin vào cả tính năng. */}
        {ck.hanSuyRa && (
          <span className="ml-auto shrink-0 font-mono text-[8.5px] uppercase tracking-wider text-muted-foreground/60">
            ước tính
          </span>
        )}
      </div>

      {/* TIÊU ĐỀ ĐẦY ĐỦ — không cắt. Đây là lý do bảng này tồn tại. */}
      <p className="text-[12.5px] font-medium leading-snug text-foreground">
        {ck.noiDung}
      </p>

      <p className="flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
        <Clock className="size-3 shrink-0" />
        {ck.nguoiCho} đang chờ · ~{gio} giờ
      </p>

      <div className="flex items-center gap-1 border-t border-border/15 pt-2">
        <button
          onClick={onXemThu}
          title={t('mail.viewOriginal')}
          className="nut-ky-thuat flex flex-1 items-center justify-center gap-1.5 px-2 py-1.5
                     text-[11px] font-medium text-foreground"
        >
          <Mail className="size-3.5" />
          Thư gốc
        </button>
        <button
          onClick={onHoiAI}
          title={t('sc.askAbout', { viec: ck.noiDung })}
          className="nut-ky-thuat flex flex-1 items-center justify-center gap-1.5 px-2 py-1.5
                     text-[11px] font-medium text-foreground"
          style={{ ['--tint' as string]: 'var(--spark)' }}
        >
          <MessageSquare className="size-3.5" />
          Hỏi trợ lý
        </button>
      </div>
    </div>
  )
}


const THU = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']

function nhanNgay(d: Date, homNay: Date): string {
  const a = new Date(homNay); a.setHours(0, 0, 0, 0)
  const b = new Date(d); b.setHours(0, 0, 0, 0)
  const cach = Math.round((b.getTime() - a.getTime()) / 86400000)
  if (cach === 0) return `Nay ${gioPhut(d)}`
  if (cach === 1) return `Mai ${gioPhut(d)}`
  if (cach < 0) return t('sc.lateDays', { n: -cach })
  if (cach < 7) return `${THU[d.getDay()]} ${gioPhut(d)}`
  return `${d.getDate()}/${d.getMonth() + 1}`
}
function gioPhut(d: Date): string {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
