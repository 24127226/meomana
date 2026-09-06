# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/repo/email_store_repo.py — ĐỌC/GHI store-of-record `emails`     ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ Đây là tầng phục vụ ĐỌC-TỪ-DB (không gọi Gmail): dựng lại schema    ║
# ║ Email từ bản ghi đã đồng bộ; và upsert khi sync kéo thư về.         ║
# ║ Thân thư (body) mã hoá khi lưu, giải mã khi đọc (privacy).          ║
# ╚══════════════════════════════════════════════════════════════════╝

import json
from datetime import datetime
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session

from app.models.email_store import StoredEmail
from app.schemas.email import Email
from app.core.crypto import encrypt_token, decrypt_token


def _parse_received(date_s: str) -> datetime | None:
    """'dd/mm/YYYY HH:MM' (giờ VN, do *_service tính) → datetime để sắp xếp. Hỏng thì None."""
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _enc_body(body: list[str] | None) -> str | None:
    if not body:
        return None
    return encrypt_token(json.dumps(body, ensure_ascii=False))


def _dec_body(body_enc: str | None) -> list[str]:
    if not body_enc:
        return []
    raw = decrypt_token(body_enc)
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else [str(val)]
    except (ValueError, TypeError):
        return [raw] if raw else []


def _row_to_email(row: StoredEmail) -> Email:
    """Bản ghi DB → schema Email (đúng hợp đồng FE). KHÔNG chạm Gmail."""
    body = _dec_body(row.body_enc) or [row.preview]
    atts = row.attachments_json or None
    return Email(
        id=row.g_id,
        sender=row.sender,
        senderEmail=row.sender_email,
        senderInitial=row.sender_initial or "?",
        to=row.to_addr,
        subject=row.subject or "(không tiêu đề)",
        preview=row.preview,
        body=body,
        time=row.time_s,
        date=row.date_s,
        unread=(not row.is_read),
        starred=row.starred,
        category=row.ai_category,          # type: ignore[arg-type]
        label=row.ai_label,
        attachments=atts,                  # type: ignore[arg-type]
        hasAttachment=bool(row.has_attachment),
        priority=row.ai_priority,          # type: ignore[arg-type]
        status=row.ai_status,              # type: ignore[arg-type]
        tldr=row.ai_tldr,
        folder=row.folder,                 # type: ignore[arg-type]
        threadId=row.thread_id,
    )


def upsert(db: Session, user_id: int, provider: str, email: Email, *,
           folder: str | None = None, full: bool = False,
           gmail_labels: list[str] | None = None, commit: bool = True) -> StoredEmail:
    """Chèn mới HOẶC cập nhật 1 email theo (user, provider, g_id).
    full=True ⇒ email.body là thân thư ĐẦY ĐỦ (từ get_message). full=False (từ list) chỉ có
    snippet ⇒ KHÔNG ghi đè body đầy đủ đã có (tránh 'mất' thân thư đã tải)."""
    row = db.scalars(
        select(StoredEmail).where(
            StoredEmail.user_id == user_id,
            StoredEmail.provider == provider,
            StoredEmail.g_id == email.id,
        )
    ).first()
    if row is None:
        row = StoredEmail(user_id=user_id, provider=provider, g_id=email.id)
        db.add(row)

    row.thread_id = email.threadId
    row.folder = folder or email.folder or "inbox"
    row.sender = email.sender
    row.sender_email = email.senderEmail
    row.sender_initial = email.senderInitial
    row.to_addr = email.to
    row.subject = email.subject
    row.preview = email.preview
    row.is_read = (not email.unread)
    row.starred = email.starred
    # PA2 §1.3.9 — ba nhãn đi qua MỘT cửa, không gán lẻ từng cột.
    row.apply_ai_labels(email.category, email.priority, email.status, label=email.label)
    if email.tldr is not None:
        row.ai_tldr = email.tldr
    row.time_s = email.time
    row.date_s = email.date
    row.received_at = _parse_received(email.date) or row.received_at
    if gmail_labels is not None:
        row.gmail_labels = gmail_labels
    if email.attachments is not None:
        row.attachments_json = [a.model_dump() for a in email.attachments]
        row.has_attachment = True
    elif email.hasAttachment:
        # Đường DANH SÁCH biết CÓ tệp nhưng không biết tên (Gmail `format=metadata`
        # không trả `parts`). Vẫn phải ghi cờ, nếu không thì thư đồng bộ từ danh sách
        # mất dấu kẹp giấy cho tới khi ai đó mở nó ra.
        row.has_attachment = True
    # Thân thư: chỉ ghi (và bật has_full) khi có bản ĐẦY ĐỦ; list chỉ cập nhật khi chưa có gì.
    if full:
        row.body_enc = _enc_body(email.body)
        row.has_full = True
    elif not row.has_full:
        row.body_enc = _enc_body(email.body)

    if commit:
        db.commit()
    return row


def get_page(db: Session, user_id: int, provider: str, *, folder: str = "inbox",
             q: str | None = None, unread: bool | None = None, starred: bool | None = None,
             attachment: bool | None = None, limit: int = 30, cursor: str | None = None
             ) -> tuple[list[Email], str | None]:
    """Trang danh sách LẤY TỪ DB (UC003/005). cursor = offset dạng chuỗi (phân trang đơn giản)."""
    offset = int(cursor) if (cursor or "").isdigit() else 0
    stmt = select(StoredEmail).where(
        StoredEmail.user_id == user_id, StoredEmail.provider == provider,
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(
            StoredEmail.subject.ilike(like), StoredEmail.sender.ilike(like),
            StoredEmail.sender_email.ilike(like), StoredEmail.preview.ilike(like),
            StoredEmail.ai_label.ilike(like),
        ))
    else:
        stmt = stmt.where(StoredEmail.folder == folder)
    if unread:
        stmt = stmt.where(StoredEmail.is_read.is_(False))
    if starred:
        stmt = stmt.where(StoredEmail.starred.is_(True))
    if attachment:
        stmt = stmt.where(StoredEmail.has_attachment.is_(True))

    stmt = stmt.order_by(StoredEmail.received_at.desc().nullslast(),
                         StoredEmail.id.desc()).offset(offset).limit(limit + 1)
    rows = list(db.scalars(stmt))
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = str(offset + limit) if has_more else None
    return [_row_to_email(r) for r in rows], next_cursor


def get_one(db: Session, user_id: int, provider: str, g_id: str) -> Email | None:
    row = db.scalars(
        select(StoredEmail).where(
            StoredEmail.user_id == user_id, StoredEmail.provider == provider,
            StoredEmail.g_id == g_id,
        )
    ).first()
    return _row_to_email(row) if row else None


def has_any(db: Session, user_id: int, provider: str) -> bool:
    """DB đã có thư nào của user chưa (để quyết định phục vụ-từ-DB hay lùi live khi 'lạnh')."""
    return db.scalar(
        select(func.count()).select_from(StoredEmail).where(
            StoredEmail.user_id == user_id, StoredEmail.provider == provider,
        )
    ) > 0


def contacts(db: Session, user_id: int, provider: str, q: str = "", limit: int = 8) -> list[dict]:
    """Danh bạ gợi ý (autocomplete người nhận): địa chỉ email suy từ sender/recipient các thư đã
    đồng bộ. Lọc theo `q` (khớp cả tên lẫn email), khử trùng, ưu tiên thư mới nhất."""
    ql = q.strip().lower()
    rows = db.scalars(
        select(StoredEmail).where(
            StoredEmail.user_id == user_id, StoredEmail.provider == provider,
        ).order_by(StoredEmail.received_at.desc().nullslast()).limit(500)
    ).all()
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        for name, addr in ((r.sender, r.sender_email), (None, r.to_addr)):
            addr = (addr or "").strip()
            if "@" not in addr or addr.lower() in seen:
                continue
            if ql and ql not in f"{addr} {name or ''}".lower():
                continue
            seen.add(addr.lower())
            out.append({"name": (name or addr), "email": addr})
            if len(out) >= limit:
                return out
    return out


def count_unread(db: Session, user_id: int, provider: str, folder: str = "inbox") -> int:
    return db.scalar(
        select(func.count()).select_from(StoredEmail).where(
            StoredEmail.user_id == user_id, StoredEmail.provider == provider,
            StoredEmail.folder == folder, StoredEmail.is_read.is_(False),
        )
    ) or 0


def ids_da_co(db: Session, user_id: int, provider: str, ids: list[str]) -> set[str]:
    """Trong `ids`, những g_id ĐÃ có sẵn trong DB.

    Dùng để phân biệt thư THẬT SỰ MỚI với thư chỉ được cập nhật (đổi nhãn, đánh dấu đã
    đọc...). Gmail history trộn chung "added" và "updated", nên không hỏi trước thì mỗi
    lần ai đó đọc một lá thư cũ cũng thành "có thư mới" — báo sai vài lần là người dùng
    thôi tin cái chuông.

    MỘT câu truy vấn cho cả lô, không hỏi từng lá: một lần đồng bộ có thể chạm hàng chục
    thư, và hỏi lẻ là hàng chục lượt đi lại CSDL cho một việc đáng lẽ chỉ tốn một.
    """
    if not ids:
        return set()
    return {
        g for (g,) in db.execute(
            select(StoredEmail.g_id).where(
                StoredEmail.user_id == user_id,
                StoredEmail.provider == provider,
                StoredEmail.g_id.in_(ids),
            )
        )
    }


# ── WRITE-THROUGH: cập nhật DB sau khi hành động đã chạy thật trên Gmail/Graph ──
def _rows(db, user_id, provider, ids):
    return db.scalars(
        select(StoredEmail).where(
            StoredEmail.user_id == user_id, StoredEmail.provider == provider,
            StoredEmail.g_id.in_(ids),
        )
    ).all()


def mark_read(db: Session, user_id: int, provider: str, ids: list[str], read: bool) -> None:
    for r in _rows(db, user_id, provider, ids):
        r.is_read = read
    db.commit()


def set_starred(db: Session, user_id: int, provider: str, ids: list[str], starred: bool) -> None:
    for r in _rows(db, user_id, provider, ids):
        r.starred = starred
    db.commit()


def move_folder(db: Session, user_id: int, provider: str, ids: list[str], folder: str) -> None:
    for r in _rows(db, user_id, provider, ids):
        r.folder = folder
    db.commit()


def set_label(db: Session, user_id: int, provider: str, ids: list[str],
              label: str | None) -> None:
    for r in _rows(db, user_id, provider, ids):
        r.ai_label = label
    db.commit()
