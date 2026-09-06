"""THƯ CÓ TỆP MÀ HỘP THƯ KHÔNG BÁO GÌ.

Người dùng gửi một tệp sang hộp thư MeoArc rồi nhìn danh sách — không thấy dấu hiệu
nào, và kết luận là app làm mất tệp. Thật ra tệp vẫn ở đó và tải xuống được: màn chi
tiết hiện đủ tên tệp lẫn nút tải. Thiếu là thiếu ở DANH SÁCH.

── VÌ SAO KHÔNG CHỈ DÙNG `attachments` ──
Đã ĐO trên thư thật: Gmail ở `format=metadata` (dạng danh sách dùng) KHÔNG trả
`payload.parts`, nên không có cách nào biết TÊN tệp mà không tải thêm một lượt cho MỖI
thư — nhân đôi số lượt gọi Gmail chỉ để vẽ một cái kẹp giấy. Nên tách riêng một lá cờ
CÓ/KHÔNG: nói đúng thứ mình biết, không bịa tên và cũng không im lặng coi như không có.
"""

from __future__ import annotations

from app.services.gmail_service import _co_dinh_kem


def test_multipart_mixed_la_co_tep():
    assert _co_dinh_kem({"payload": {"mimeType": "multipart/mixed"}}) is True


def test_cac_khuon_KHAC_khong_phai_tep_dinh_kem():
    """Thư text+HTML là `multipart/alternative`, thư có ảnh nhúng là `multipart/related`.
    Nhận nhầm chúng thì gần như THƯ NÀO cũng đeo kẹp giấy, và cái kẹp hết nghĩa."""
    for kieu in ("multipart/alternative", "multipart/related", "text/plain", "text/html", ""):
        assert _co_dinh_kem({"payload": {"mimeType": kieu}}) is False, kieu


def test_khong_co_payload_thi_khong_vo():
    assert _co_dinh_kem({}) is False
    assert _co_dinh_kem({"payload": {}}) is False


def test_chi_tiet_BIET_CHAC_chu_khong_suy_doan(monkeypatch):
    """Màn chi tiết lấy `format=full` nên đọc được tệp thật — cờ phải theo tệp thật,
    không theo mimeType."""
    from app.services import gmail_service as G

    monkeypatch.setattr(G, "_extract_body",
                        lambda payload: ("chào", "", [{"name": "a.pdf", "size": "10 KB"}]))
    monkeypatch.setattr(G, "_nhan_nguoi_dung_dat", lambda *a, **k: None)
    msg = {"id": "m1", "threadId": "t1", "labelIds": [], "snippet": "…",
           "payload": {"mimeType": "text/plain", "headers": []}}
    e = G._to_email_day_du(msg, {})
    assert e.hasAttachment is True, "có tệp thật thì phải True dù mimeType không phải mixed"
    assert [a.name for a in e.attachments] == ["a.pdf"]

    monkeypatch.setattr(G, "_extract_body", lambda payload: ("chào", "", []))
    assert G._to_email_day_du(msg, {}).hasAttachment is False


def test_kho_DB_giu_duoc_co(monkeypatch):
    """Đường đồng bộ ghi thư từ DANH SÁCH — biết CÓ tệp nhưng không biết tên. Không ghi
    cờ thì thư mất dấu kẹp giấy cho tới khi ai đó mở nó ra."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.core.db import Base
    import app.models.user  # noqa: F401
    import app.models.email_store  # noqa: F401
    from app.models.user import User
    from app.repo import email_store_repo
    from app.schemas.email import Email

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng)()
    db.add(User(id=1, email="u@x.vn", name="U", initial="U"))
    db.commit()

    thu = Email(id="m1", sender="A", senderEmail="a@x.vn", senderInitial="A", to="me@x.vn",
                subject="Có tệp", preview="...", body=["..."], time="10:00", date="06/09",
                unread=True, starred=False, category="moss", label=None,
                attachments=None, hasAttachment=True)
    email_store_repo.upsert(db, 1, "google", thu, folder="inbox")
    ra = email_store_repo.get_one(db, 1, "google", "m1")
    assert ra.hasAttachment is True, "cờ phải sống sót qua CSDL"


def test_outlook_doc_thang_tu_Graph():
    """Graph nói thẳng `hasAttachments`, khỏi phải suy từ mimeType."""
    from app.services.outlook_service import _to_email

    m = {"id": "o1", "subject": "X", "from": {"emailAddress": {"name": "A", "address": "a@x.vn"}},
         "toRecipients": [], "receivedDateTime": "2026-09-06T03:00:00Z",
         "bodyPreview": "…", "isRead": True, "hasAttachments": True}
    assert _to_email(m, "inbox").hasAttachment is True
    m["hasAttachments"] = False
    assert _to_email(m, "inbox").hasAttachment is False
