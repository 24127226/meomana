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

/** Thư mục thư sẽ tới sau mỗi hành động — nguồn sự thật DUY NHẤT cho vòng lùi. */
export const THU_MUC_DICH = {
  archive: 'archive',
  delete: 'trash',
  restore: 'inbox',
} as const
