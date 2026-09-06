# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/services/sync_service.py — BỘ ĐỒNG BỘ hộp thư → DB store        ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ Hiện thực chiến lược "DB làm trung tâm, không sợ rate-limit":       ║
# ║  • initial_sync : kéo N thư gần nhất mỗi thư mục về DB (1 lần khi    ║
# ║    đăng nhập / DB còn lạnh) + ghim historyId gốc.                   ║
# ║  • incremental_sync : chỉ lấy các thư ĐỔI kể từ historyId cũ         ║
# ║    (Gmail history.list) → fetch đúng những thư đó → upsert. KHÔNG    ║
# ║    quét lại toàn hộp thư.                                           ║
# ║  • handle_pubsub : điểm vào cho Gmail Push (webhook) — nhận thông    ║
# ║    báo → tìm user → incremental_sync (chạy nền, không polling).     ║
# ║                                                                    ║
# ║ Outlook: v1 dùng re-list inbox có giới hạn (Graph delta để nâng cấp).║
# ╚══════════════════════════════════════════════════════════════════╝

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.email_store import MailboxSync
from app.models.session import AuthSession
from app.models.user import User
from app.repo import email_store_repo, session_repo
from app.services import mail, gmail_service, auth_service, auth_service_ms

logger = logging.getLogger("app.sync")

_FOLDERS = ("inbox", "sent", "drafts", "archive", "trash")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_state(db: Session, user_id: int, provider: str) -> MailboxSync:
    row = db.scalars(
        select(MailboxSync).where(
            MailboxSync.user_id == user_id, MailboxSync.provider == provider,
        )
    ).first()
    if row is None:
        row = MailboxSync(user_id=user_id, provider=provider)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def initial_sync(db: Session, user_id: int, provider: str, token: str, *,
                 max_per_folder: int = 500) -> int:
    """Kéo TOÀN BỘ thư MỖI thư mục về DB (phân trang tới hết; trần `max_per_folder` để không
    chạy vô hạn với hộp thư khổng lồ). Ghim historyId gốc để lần sau chỉ lấy phần thay đổi.
    Trả tổng số thư đã upsert."""
    total = 0
    for folder in _FOLDERS:
        cursor, pulled = None, 0
        while True:
            try:
                emails, cursor = mail.list_messages(
                    provider, token, folder=folder, max_results=100,
                    page_token=cursor, bypass_cache=True,
                )
            except Exception as exc:
                logger.warning("initial_sync bỏ qua thư mục %s: %s", folder, exc)
                break
            for em in emails:
                email_store_repo.upsert(db, user_id, provider, em, folder=folder,
                                        full=False, commit=False)
                total += 1
                pulled += 1
            db.commit()
            if not cursor or pulled >= max_per_folder:
                break

    state = _get_state(db, user_id, provider)
    if provider == "google":
        try:
            state.history_id = gmail_service.get_profile_history_id(token)
        except Exception as exc:
            logger.warning("initial_sync không lấy được historyId: %s", exc)
    state.last_synced_at = _utcnow()
    db.commit()
    logger.info("initial_sync user=%s provider=%s: %d thư", user_id, provider, total)
    return total


def _bao_thu_moi(db: Session, user_id: int, thu_moi: list) -> None:
    """Sinh MỘT thông báo cho đợt thư mới vừa đồng bộ.

    ── VÌ SAO CẦN ──
    Chuông thông báo hỏi máy chủ 25 giây một lần, nhưng đồng bộ chưa bao giờ tạo ra dòng
    thông báo nào — nên thư về tới Gmail mà màn hình MeoArc đứng im vĩnh viễn. Nhìn từ
    phía người dùng thì đó là "đồng bộ chậm"; thật ra không có đường nào nối "thư tới"
    với "màn hình đổi" cả.

    MỘT thông báo cho cả đợt, không phải mỗi thư một dòng: nhập hai chục thư một lúc
    (đồng bộ lần đầu, hoặc mở máy sau kỳ nghỉ) mà đổ hai chục dòng thì chuông thành chỗ
    không ai buồn mở, và đúng lúc có tin đáng đọc thì nó đã bị bỏ qua.

    Nuốt lỗi: thông báo là phần PHỤ. Hỏng khâu này mà làm hỏng cả lượt đồng bộ thì mất
    thư — đắt hơn nhiều so với mất một dòng chuông.
    """
    if not thu_moi:
        return
    try:
        from app.repo import notification_repo
        if len(thu_moi) == 1:
            nguoi, chu_de = thu_moi[0]
            tin = f"Thư mới từ {nguoi}: {chu_de}" if chu_de else f"Thư mới từ {nguoi}"
        else:
            tin = f"Có {len(thu_moi)} thư mới trong hộp thư."
        notification_repo.create(db, user_id=user_id, message=tin[:300], type="info")
    except Exception:
        logger.info("Không tạo được thông báo thư mới", exc_info=True)
        db.rollback()


def _apply_gmail_changes(db: Session, user_id: int, token: str, changes: dict) -> tuple[int, list]:
    """added/updated → fetch full rồi upsert; deleted → chuyển thư mục 'trash' trong DB.

    Trả thêm danh sách thư THẬT SỰ MỚI (chưa từng có trong DB, vào hộp thư đến) để tầng
    trên báo chuông. Gmail history trộn chung added/updated, nên phải hỏi DB trước khi
    ghi — không thì mỗi lần ai đó đọc một lá thư cũ cũng bị tính là "thư mới".
    """
    ids = list(changes.get("added", [])) + list(changes.get("updated", []))
    da_co = email_store_repo.ids_da_co(db, user_id, "google", ids)

    n = 0
    thu_moi: list = []
    for mid in ids:
        try:
            em = gmail_service.get_message(token, mid)
        except Exception as exc:
            logger.warning("history: bỏ qua %s (%s)", mid, exc)
            continue
        thu_muc = em.folder or "inbox"
        email_store_repo.upsert(db, user_id, "google", em, folder=thu_muc,
                                full=True, commit=False)
        n += 1
        # Chỉ báo thư ĐẾN hộp thư đến: thư mình vừa gửi cũng đi qua history, và báo
        # "có thư mới" cho chính thư mình vừa bấm Gửi là vô nghĩa.
        if mid not in da_co and thu_muc == "inbox":
            thu_moi.append((em.sender or em.senderEmail or "ai đó", em.subject or ""))
    deleted = changes.get("deleted", [])
    if deleted:
        email_store_repo.move_folder(db, user_id, "google", deleted, "trash")
    db.commit()
    return n, thu_moi


def incremental_sync(db: Session, user_id: int, provider: str, token: str) -> int:
    """Đồng bộ PHẦN THAY ĐỔI kể từ lần trước. DB lạnh/không có mốc → initial_sync."""
    state = _get_state(db, user_id, provider)

    if provider == "google":
        if not state.history_id or not email_store_repo.has_any(db, user_id, provider):
            return initial_sync(db, user_id, provider, token)
        try:
            changes = gmail_service.list_history(token, state.history_id)
        except gmail_service.HistoryExpired:
            logger.info("historyId hết hạn user=%s → resync đầy đủ", user_id)
            return initial_sync(db, user_id, provider, token)
        n, thu_moi = _apply_gmail_changes(db, user_id, token, changes)
        state.history_id = changes.get("history_id") or state.history_id
        state.last_synced_at = _utcnow()
        db.commit()
        _bao_thu_moi(db, user_id, thu_moi)
        return n

    # Microsoft (v1): re-list inbox có giới hạn (Graph delta là hướng nâng cấp).
    if not email_store_repo.has_any(db, user_id, provider):
        return initial_sync(db, user_id, provider, token)
    try:
        emails, _ = mail.list_messages(provider, token, folder="inbox",
                                       max_results=25, bypass_cache=True)
    except Exception as exc:
        logger.warning("incremental_sync outlook lỗi: %s", exc)
        return 0
    da_co = email_store_repo.ids_da_co(db, user_id, provider, [e.id for e in emails])
    thu_moi = [(e.sender or e.senderEmail or "ai đó", e.subject or "")
               for e in emails if e.id not in da_co]
    for em in emails:
        email_store_repo.upsert(db, user_id, provider, em, folder="inbox",
                                full=False, commit=False)
    state.last_synced_at = _utcnow()
    db.commit()
    _bao_thu_moi(db, user_id, thu_moi)
    return len(emails)


# ── Điểm vào cho Gmail Push (webhook /gmail/push) ─────────────────────
def _token_for_user(db: Session, user_id: int) -> tuple[str, str] | None:
    """(token còn hạn, provider) của user từ phiên MỚI NHẤT — tự refresh nếu sắp hết hạn.
    None nếu user chưa có phiên đăng nhập nào."""
    s = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == user_id,
               AuthSession.google_access_token.isnot(None))
        .order_by(AuthSession.expires_at.desc())
    ).first()
    if s is None:
        return None
    provider = session_repo.get_provider(db, s.token)
    token = s.google_access_token
    if (s.google_token_expiry
            and s.google_token_expiry <= _utcnow() + timedelta(seconds=60)
            and s.google_refresh_token):
        if provider == "microsoft":
            token, exp = auth_service_ms.refresh_access_token(s.google_refresh_token)
        else:
            token, exp = auth_service.refresh_access_token(s.google_refresh_token)
        session_repo.update_access_token(db, s, token, exp)
    return token, provider


def handle_pubsub(db: Session, email_address: str) -> int:
    """Nhận thông báo Gmail Push (đã giải mã ra emailAddress) → đồng bộ lũy tiến hộp thư đó.
    Trả số thư đã cập nhật (0 nếu không map được user/phiên)."""
    user = db.scalars(select(User).where(User.email == email_address)).first()
    if user is None:
        logger.warning("Pub/Sub: không có user %s", email_address)
        return 0
    tp = _token_for_user(db, user.id)
    if tp is None:
        logger.warning("Pub/Sub: user %s chưa có phiên → bỏ qua", email_address)
        return 0
    token, provider = tp
    return incremental_sync(db, user.id, provider, token)


def sync_for_session(db: Session, session: AuthSession, token: str, provider: str) -> int:
    """Tiện ích cho endpoint /sync/run: đồng bộ hộp thư của phiên đang đăng nhập."""
    return incremental_sync(db, session.user_id, provider, token)


# ── GIA HẠN Gmail watch (hết hạn ~7 ngày) ────────────────────────────
def renew_watches(db: Session) -> int:
    """Gọi lại gmail.watch() cho MỌI hộp thư đang bật Push → dời hạn thêm ~7 ngày.
    Worker pull gọi hàm này mỗi ngày → watch không bao giờ chết mà không phải làm tay.
    Bỏ qua nếu chưa cấu hình topic. Trả số hộp thư đã gia hạn."""
    if not settings.gmail_pubsub_topic:
        return 0
    rows = db.scalars(
        select(MailboxSync).where(
            MailboxSync.provider == "google",
            MailboxSync.watch_expiration.isnot(None),
        )
    ).all()
    n = 0
    for row in rows:
        tp = _token_for_user(db, row.user_id)
        if tp is None:
            continue
        token, provider = tp
        if provider != "google":
            continue
        try:
            res = gmail_service.watch(token, settings.gmail_pubsub_topic)
        except Exception as exc:
            logger.warning("Gia hạn watch user=%s lỗi: %s", row.user_id, exc)
            continue
        if res.get("historyId"):
            row.history_id = str(res["historyId"])
        exp = res.get("expiration")
        if exp:
            row.watch_expiration = datetime.fromtimestamp(
                int(exp) / 1000, tz=timezone.utc).replace(tzinfo=None)
        n += 1
    db.commit()
    return n
