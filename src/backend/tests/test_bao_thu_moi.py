"""ĐỒNG BỘ PHẢI BÁO CÓ THƯ MỚI — và chỉ báo khi thư THẬT SỰ mới.

Người dùng ngồi mở sẵn màn danh sách rồi tự gửi một lá thư sang hộp thư MeoArc để xem
thông báo hiện ra thế nào. Chờ rất lâu, không có gì xảy ra cả.

Lý do không phải "đồng bộ chậm": chuông hỏi máy chủ 25 giây một lần, nhưng `sync_service`
CHƯA BAO GIỜ tạo ra một dòng thông báo nào. Không có đường nào nối "thư tới" với "màn
hình đổi", nên chờ bao lâu cũng thế.

Chỗ dễ sai khi vá: Gmail history trộn chung "added" và "updated". Đếm cả hai là mỗi lần
ai đó mở một lá thư cũ (đổi nhãn UNREAD) cũng thành "có thư mới" — báo sai vài lần là
người dùng thôi tin cái chuông, và lúc đó tính năng còn tệ hơn lúc chưa có.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.schemas.email import Email

USER = 1
PROVIDER = "google"


def _mem_db():
    from app.core.db import Base
    import app.models.user  # noqa: F401
    import app.models.email_store  # noqa: F401
    import app.models.notification  # noqa: F401

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _thu(mid: str, nguoi="Ai Đó", chu_de="Chào bạn", folder="inbox") -> Email:
    return Email(
        id=mid, threadId=mid, sender=nguoi, senderEmail="x@example.com",
        senderInitial="A", to="meoarc.hcmus@gmail.com", subject=chu_de,
        preview="...", body=["..."], time="10:05", date="06/09",
        unread=True, starred=False, folder=folder, category="cherry", label=None,
    )


@pytest.fixture()
def db():
    from app.models.user import User

    d = _mem_db()
    d.add(User(id=USER, email="u@x.vn", name="U", initial="U"))
    d.commit()
    return d


def _chay(db, monkeypatch, ids: list[str], thu_theo_id: dict):
    """Chạy `_apply_gmail_changes` với Gmail giả trả đúng các thư mình dựng."""
    from app.services import sync_service as S

    monkeypatch.setattr(S.gmail_service, "get_message", lambda tok, mid: thu_theo_id[mid])
    return S._apply_gmail_changes(db, USER, "tok", {"added": ids, "updated": []})


def test_thu_moi_sinh_thong_bao(db, monkeypatch):
    from app.repo import notification_repo
    from app.services import sync_service as S

    n, thu_moi = _chay(db, monkeypatch, ["m1"], {"m1": _thu("m1", "Quân", "V/V xin số")})
    assert n == 1 and len(thu_moi) == 1
    S._bao_thu_moi(db, USER, thu_moi)

    tin = notification_repo.list_for_user(db, USER)
    assert len(tin) == 1
    assert "Quân" in tin[0].message and "V/V xin số" in tin[0].message


def test_thu_DA_CO_roi_thi_KHONG_bao_lai(db, monkeypatch):
    """Đây là cái bẫy chính: đọc một lá thư cũ cũng đi qua history dưới dạng 'updated'."""
    from app.services import sync_service as S

    thu = {"m1": _thu("m1")}
    _chay(db, monkeypatch, ["m1"], thu)          # lần đầu — mới
    _, lan_hai = _chay(db, monkeypatch, ["m1"], thu)  # lần hai — đã có trong DB
    assert lan_hai == [], "thư đã có trong CSDL thì không phải thư mới"


def test_thu_KHONG_vao_hop_thu_den_thi_khong_bao(db, monkeypatch):
    """Thư mình vừa GỬI cũng đi qua history. Báo 'có thư mới' cho chính thư mình vừa
    bấm Gửi là vô nghĩa."""
    from app.services import sync_service as S

    _, thu_moi = _chay(db, monkeypatch, ["s1"], {"s1": _thu("s1", folder="sent")})
    assert thu_moi == []


def test_nhieu_thu_thi_GOP_thanh_MOT_dong(db, monkeypatch):
    """Nhập hai chục thư mà đổ hai chục dòng thì chuông thành chỗ không ai buồn mở."""
    from app.repo import notification_repo
    from app.services import sync_service as S

    ids = [f"m{i}" for i in range(5)]
    _, thu_moi = _chay(db, monkeypatch, ids, {i: _thu(i) for i in ids})
    assert len(thu_moi) == 5
    S._bao_thu_moi(db, USER, thu_moi)

    tin = notification_repo.list_for_user(db, USER)
    assert len(tin) == 1, "một đợt = một thông báo"
    assert "5" in tin[0].message


def test_khong_co_thu_moi_thi_KHONG_tao_dong_nao(db):
    from app.repo import notification_repo
    from app.services import sync_service as S

    S._bao_thu_moi(db, USER, [])
    assert notification_repo.list_for_user(db, USER) == []


def test_hong_khau_thong_bao_KHONG_lam_hong_dong_bo(db, monkeypatch):
    """Thông báo là phần PHỤ. Mất một dòng chuông rẻ hơn nhiều so với mất thư."""
    from app.repo import notification_repo
    from app.services import sync_service as S

    monkeypatch.setattr(notification_repo, "create",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CSDL sập")))
    S._bao_thu_moi(db, USER, [("Ai Đó", "Chào")])   # không được ném ra ngoài


def test_ids_da_co_tra_dung_tap_hop(db, monkeypatch):
    from app.repo import email_store_repo
    from app.services import sync_service as S

    _chay(db, monkeypatch, ["m1", "m2"], {"m1": _thu("m1"), "m2": _thu("m2")})
    ra = email_store_repo.ids_da_co(db, USER, PROVIDER, ["m1", "m3"])
    assert ra == {"m1"}
    assert email_store_repo.ids_da_co(db, USER, PROVIDER, []) == set()


def test_KHONG_thay_thu_cua_nguoi_khac(db, monkeypatch):
    """`ids_da_co` phải lọc theo người — nếu không thì thư người này che thư người kia."""
    from app.repo import email_store_repo
    from app.models.user import User

    db.add(User(id=2, email="v@x.vn", name="V", initial="V"))
    db.commit()
    _chay(db, monkeypatch, ["m1"], {"m1": _thu("m1")})     # của user 1
    assert email_store_repo.ids_da_co(db, 2, PROVIDER, ["m1"]) == set()
