# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/repo/conversation_repo.py — TRUY VẤN bảng conversations (UC011)║
# ╚══════════════════════════════════════════════════════════════════╝

import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.models.conversation import Conversation


def _utcnow() -> datetime:
    """Giờ UTC 'naive' — đồng nhất với cách so sánh thời gian ở session_repo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    return uuid.uuid4().hex


def list_for_user(db: Session, user_id: int) -> list[Conversation]:
    """Danh sách phiên của user: ghim lên đầu, rồi mới-nhất-trước."""
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.pinned.desc(), Conversation.updated_at.desc())
        .all()
    )


def get_owned(db: Session, conv_id: str, user_id: int) -> Conversation | None:
    """Lấy 1 phiên NHƯNG chỉ khi đúng chủ — chặn user A đọc phiên user B."""
    c = db.get(Conversation, conv_id)
    if c is None or c.user_id != user_id:
        return None
    return c


def get_or_create(db: Session, conv_id: str | None, user_id: int) -> Conversation:
    """Lấy phiên đang có (đúng chủ) hoặc TẠO mới. conv_id None/lạ → tạo mới với id sinh ra.
    Trả về phiên CHƯA commit phần nội dung — gọi save_turn để ghi sau khi chạy agent."""
    if conv_id:
        c = db.get(Conversation, conv_id)
        if c is not None and c.user_id == user_id:
            return c
    now = _utcnow()
    c = Conversation(
        id=conv_id or new_id(),
        user_id=user_id,
        title="Cuộc trò chuyện mới",
        pinned=False,
        created_at=now,
        updated_at=now,
        agent_messages=[],
        display_messages=[],
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _auto_title(text: str) -> str:
    """Đặt tiêu đề từ câu hỏi đầu: gọn 1 dòng, tối đa ~48 ký tự."""
    t = " ".join((text or "").split())
    return (t[:48] + "…") if len(t) > 48 else (t or "Cuộc trò chuyện mới")


def save_turn(
    db: Session,
    conv: Conversation,
    agent_messages: list,
    display_messages: list,
    first_user_text: str | None = None,
) -> Conversation:
    """Ghi lại sau MỘT lượt chat: cập nhật 2 khuôn dữ liệu + dời updated_at.
    Nếu phiên còn tiêu đề mặc định và có câu user đầu → tự đặt tiêu đề cho dễ tìm."""
    conv.agent_messages = agent_messages
    conv.display_messages = display_messages
    conv.updated_at = _utcnow()
    if first_user_text and conv.title == "Cuộc trò chuyện mới":
        conv.title = _auto_title(first_user_text)
    db.commit()
    db.refresh(conv)
    return conv


def set_display_messages(db: Session, conv: Conversation, display_messages: list) -> Conversation:
    """Ghi lại RIÊNG phần lịch sử hiển thị, KHÔNG đụng `agent_messages`.

    Dùng khi chỉ đổi trạng thái hiển thị (đánh dấu một thẻ đã duyệt, cấp mã cho tin nhắn
    cũ). Gọi `save_turn` cho việc này thì phải truyền cả `agent_messages` — và truyền
    nhầm một lần là xoá sạch ngữ cảnh agent của cả phiên.

    KHÔNG dời `updated_at`: đánh dấu một thẻ không phải một lượt trò chuyện mới, mà
    danh sách phiên xếp theo mốc đó — dời thì phiên nhảy lên đầu vì một cú bấm nút.
    """
    conv.display_messages = display_messages
    # SQLAlchemy không tự phát hiện thay đổi BÊN TRONG cột JSON (mutate tại chỗ), nên
    # phải báo rõ. Thiếu dòng này thì commit đi qua trong im lặng và không ghi được gì.
    flag_modified(conv, "display_messages")
    db.commit()
    db.refresh(conv)
    return conv


def rename(db: Session, conv: Conversation, title: str) -> Conversation:
    conv.title = (title or "").strip()[:60] or "Cuộc trò chuyện mới"
    db.commit()
    db.refresh(conv)
    return conv


def set_pinned(db: Session, conv: Conversation, pinned: bool) -> Conversation:
    conv.pinned = pinned
    db.commit()
    db.refresh(conv)
    return conv


def delete(db: Session, conv: Conversation) -> None:
    db.delete(conv)
    db.commit()
