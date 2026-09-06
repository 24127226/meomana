import type { Category } from '@/data/emails'

/** Tập hành động quản lý email (UC006) — dùng chung cho list (bulk) và detail (đơn). */
export type EmailActions = {
  markRead: (ids: string[], read: boolean) => void
  setImportant: (ids: string[], value: boolean) => void
  applyLabel: (ids: string[], category: Category, label: string) => void
  /** Gỡ thư khỏi danh sách. `mode` phân biệt hệ quả trên Gmail:
   *  'archive' = bỏ nhãn INBOX (thư vẫn còn); 'delete' = chuyển vào thùng rác.
   *  Mặc định 'delete' để các nút Xoá cũ vẫn đúng nếu chưa truyền mode. */
  removeEmails: (ids: string[], mode?: 'archive' | 'delete') => void
  /** Đưa thư từ thùng rác trở lại hộp thư — đường lùi cho `removeEmails('delete')`. */
  restoreEmails: (ids: string[]) => void
  /** Đánh dấu thư rác (`rac=true`) hoặc trả về hộp thư (`rac=false`).
   *  MỘT hàm hai chiều thay vì hai hàm: chúng luôn đi cùng nhau, và tách ra là mở đường
   *  cho một bên được cập nhật còn bên kia bị bỏ quên. */
  markSpam: (ids: string[], rac: boolean) => void
}

/** Một mục cache thư mục (stale-while-revalidate) — chỉ cần `items` để suy luận. */
type MucCache<T> = { items: T[]; cursor: string | null }

/**
 * Áp một sửa đổi lạc quan lên CẢ danh sách đang hiện LẪN mọi mục `folderCache`.
 *
 * Vì sao phải đụng tới cache: cache trả bản cũ ra màn hình ngay khi đổi thư mục rồi
 * mới nạp bản mới đè lên. Nếu chỉ sửa danh sách đang hiện thì xoá một thư ở Hộp thư,
 * bấm sang Thùng rác rồi bấm về Hộp thư sẽ thấy thư vừa xoá HIỆN LẠI một nhịp — đủ
 * lâu để người xem tin là app xoá hụt. Lỗi này KHÔNG lộ ở chế độ mock (không có
 * cache) nên chỉ bộ test này giữ được nó.
 *
 * `boCache` xoá hẳn mục của thư mục ĐÍCH khi thư chuyển chỗ: thư mới tới không nằm
 * trong bản cache cũ của thư mục đó, và tự chèn vào là đoán — thà nạp lại cho thật.
 */
export function apDungSuaLacQuan<T extends { id: string }>(
  cache: Map<string, MucCache<T>>,
  ids: string[],
  sua: (e: T) => T,
  boCache?: string,
): (ds: T[]) => T[] {
  const bien = (ds: T[]) => ds.map((e) => (ids.includes(e.id) ? sua(e) : e))
  for (const [k, v] of cache) cache.set(k, { ...v, items: bien(v.items) })
  if (boCache) cache.delete(boCache)
  return bien
}

/**
 * Ghim `ghim` lên đầu `ds`, khử trùng theo id.
 *
 * Vì sao cần: máy chủ trả 30 thư/trang sắp theo ngày nhận giảm dần, và thư khôi phục
 * quay về ĐÚNG vị trí thời gian cũ của nó. Thư cũ hơn 30 thư mới nhất thì nằm ở trang
 * 2 — người dùng bấm khôi phục, thấy toast báo xong, nhìn Hộp thư không thấy gì mới.
 * Ghim là cách trả lời thẳng "thư bạn vừa lấy lại đây"; nó KHÔNG giả vờ thư đó mới,
 * và bị dọn ngay khi người dùng rời Hộp thư hoặc bấm Làm mới.
 *
 * Khử trùng theo id là bắt buộc: thư khôi phục đủ mới thì máy chủ CŨNG trả nó trong
 * trang đầu, và không khử thì nó hiện hai lần.
 */
export function ghimLenDau<T extends { id: string }>(ds: T[], ghim: T[]): T[] {
  if (!ghim.length) return ds
  const id = new Set(ghim.map((e) => e.id))
  return [...ghim, ...ds.filter((e) => !id.has(e.id))]
}

/**
 * Có nên nạp lại hộp thư ngầm lúc này không.
 *
 * Tách ra khỏi component vì đây là phần DUY NHẤT của việc tự-nạp-lại có thể sai thầm
 * lặng: vòng lặp vẫn chạy, không lỗi, chỉ là gọi sai lúc. Ba điều kiện, mỗi cái chặn
 * một kiểu hỏng khác nhau:
 *  • `dangNap` — hai lượt gọi chồng nhau thì lượt về sau có thể là bản CŨ hơn, và
 *    danh sách nhảy ngược về trạng thái trước đó.
 *  • `coTimKiem` — đè kết quả tìm kiếm bằng hộp thư đến là cướp mất thứ đang xem.
 *  • `hienThi` — tab nền chạy vòng lặp là đốt hạn mức Gmail cho màn hình không ai nhìn.
 */
export function nenNapNgam(dk: {
  dangNap: boolean
  coTimKiem: boolean
  hienThi: boolean
}): boolean {
  return !dk.dangNap && !dk.coTimKiem && dk.hienThi
}

/** Các trường CHỈ có ở bản chi tiết, không có ở bản danh sách. */
type ChiTiet = {
  body?: string[]
  html?: string | null
  attachments?: unknown[] | null
  hasAttachment?: boolean
}

/**
 * Trộn danh sách MỚI từ máy chủ mà KHÔNG làm nghèo đi thứ đã biết.
 *
 * ── VÌ SAO CẦN ──
 * Danh sách và chi tiết là hai lần gọi khác nhau, trả về hai độ chi tiết khác nhau:
 * danh sách chỉ có snippet, KHÔNG có thân thư đầy đủ, KHÔNG có tệp đính kèm (Gmail ở
 * `format=metadata` không trả `payload.parts`). Nên mỗi lần thay cả mảng bằng bản danh
 * sách là xoá sạch phần chi tiết đã tải.
 *
 * Trước khi có tự-nạp-lại-30-giây thì không ai thấy: danh sách chỉ được thay khi đổi
 * thư mục, mà đổi thư mục thì đóng luôn thư đang mở. Thêm vòng nạp nền vào là lỗi lộ
 * ra ngay — đang đọc một lá thư, chưa tới nửa phút thì tệp đính kèm và thân thư biến
 * mất trước mắt, không lỗi, không dấu hiệu gì.
 *
 * Luật: bản mới THẮNG ở mọi trường nó có (đã đọc/chưa, gắn sao, nhãn, thư mục — đó là
 * lý do ta nạp lại). Nhưng trường nào bản mới KHÔNG BIẾT thì giữ lại thứ đã biết,
 * chứ không ghi đè bằng khoảng trống.
 */
export function giuChiTietDaCo<T extends { id: string } & ChiTiet>(cu: T[], moi: T[]): T[] {
  if (!cu.length) return moi
  const theoId = new Map(cu.map((e) => [e.id, e]))
  return moi.map((m) => {
    const c = theoId.get(m.id)
    if (!c) return m
    const gop: T = { ...m }
    if (m.html == null && c.html != null) gop.html = c.html
    if (m.attachments == null && c.attachments != null) gop.attachments = c.attachments
    // Thân thư: bản danh sách chỉ có MỘT đoạn (snippet). Giữ bản dài hơn — nhưng chỉ
    // khi bản mới đúng là bản rút gọn, để nội dung thật sự đổi vẫn được cập nhật.
    if ((c.body?.length ?? 0) > (m.body?.length ?? 0)) gop.body = c.body
    if (!m.hasAttachment && c.hasAttachment) gop.hasAttachment = true
    return gop
  })
}

/** Thư mục thư sẽ tới sau mỗi hành động — nguồn sự thật DUY NHẤT cho vòng lùi. */
export const THU_MUC_DICH = {
  archive: 'archive',
  delete: 'trash',
  restore: 'inbox',
} as const
