"""THẺ ĐÃ DUYỆT PHẢI Ở YÊN LÀ ĐÃ DUYỆT.

Người dùng bấm Duyệt cho một thẻ xoá thư, lệnh chạy xong. Mở lại đoạn chat thì thẻ đó
lại hiện nút "Duyệt" như chưa từng bấm — và bấm lần nữa là lệnh CHẠY LẦN HAI.

Nguyên nhân: trạng thái "đã duyệt" chỉ sống trong bộ nhớ trình duyệt. `StoredMessage`
không có trường nào cho nó, và `toLocalMsg` dựng lại tin nhắn thì luôn ra trạng thái
chờ duyệt.

Lưu ý phạm vi: đây là trạng thái HIỂN THỊ, không phải cổng chặn thực thi. Cổng thật
nằm ở tầng tool (`_needs_confirm`) và bảng `confirmation_requests`. Nhưng một giao diện
mời người ta bấm lại một việc đã làm thì tự nó đã là lỗi.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.app import app
from app.core.deps import get_current_session, get_db


class _Phien:
    user_id = 1
    provider = "google"
    google_access_token = "tok"


def _mem_db():
    from app.core.db import Base
    import app.models.user  # noqa: F401
    import app.models.conversation  # noqa: F401

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


@pytest.fixture()
def bo(monkeypatch):
    from app.models.conversation import Conversation
    from app.models.user import User
    from app.repo import conversation_repo

    db = _mem_db()
    db.add(User(id=1, email="a@x.vn", name="A", initial="A"))
    db.add(User(id=2, email="b@x.vn", name="B", initial="B"))
    db.commit()

    conv = Conversation(
        id="c1", user_id=1, title="Dọn thư", pinned=False,
        created_at=datetime(2026, 9, 1, 8, 0), updated_at=datetime(2026, 9, 1, 8, 0),
        agent_messages=[{"nguyen": "ven"}],
        display_messages=[
            {"id": "m1", "role": "user", "text": "xoá hết thư quảng cáo"},
            {"id": "m2", "role": "agent", "reply": {"kind": "plan", "title": "Xoá 8 thư"}},
        ],
    )
    db.add(conv)
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_session] = lambda: _Phien()
    yield TestClient(app), db, conversation_repo
    app.dependency_overrides.clear()


def test_danh_dau_roi_thi_LUU_XUONG_va_mo_lai_van_con(bo):
    c, db, _ = bo
    assert c.post("/agent/conversations/c1/messages/m2/resolved").status_code == 200

    ds = c.get("/agent/conversations/c1").json()["messages"]
    the = next(m for m in ds if m["id"] == "m2")
    assert the["resolved"] is True, "mở lại phải thấy thẻ ĐÃ duyệt, không phải chờ duyệt"


def test_chi_danh_dau_DUNG_the_do(bo):
    c, _, _ = bo
    c.post("/agent/conversations/c1/messages/m2/resolved")
    ds = c.get("/agent/conversations/c1").json()["messages"]
    assert ds[0].get("resolved") is not True, "tin nhắn khác không được đụng tới"


def test_ma_tin_nhan_LA_gi_thi_404(bo):
    c, _, _ = bo
    assert c.post("/agent/conversations/c1/messages/khong-co/resolved").status_code == 404


def test_KHONG_danh_dau_duoc_phien_cua_NGUOI_KHAC(bo, monkeypatch):
    """`get_owned` lọc theo chủ; thiếu thì đoán id phiên là sửa được hội thoại người khác."""
    c, _, _ = bo

    class _Nguoi2:
        user_id = 2
        provider = "google"
        google_access_token = "tok"

    app.dependency_overrides[get_current_session] = lambda: _Nguoi2()
    assert c.post("/agent/conversations/c1/messages/m2/resolved").status_code == 404


def test_phien_CU_chua_co_ma_thi_duoc_cap_ma_luc_mo(bo):
    """Phiên lưu trước khi có `id` vẫn phải đánh dấu duyệt được — nếu không thì lỗi cũ
    còn nguyên ở đúng những phiên người dùng hay mở lại nhất."""
    c, db, _ = bo
    from app.models.conversation import Conversation

    cu = Conversation(id="c2", user_id=1, title="Cũ", pinned=False, agent_messages=[],
                      created_at=datetime(2026, 9, 1, 8, 0), updated_at=datetime(2026, 9, 1, 8, 0),
                      display_messages=[{"role": "agent", "reply": {"kind": "plan"}}])
    db.add(cu)
    db.commit()

    ds = c.get("/agent/conversations/c2").json()["messages"]
    ma = ds[0].get("id")
    assert ma, "mở phiên cũ phải cấp mã cho tin nhắn"
    assert c.post(f"/agent/conversations/c2/messages/{ma}/resolved").status_code == 200
    assert c.get("/agent/conversations/c2").json()["messages"][0]["resolved"] is True


def test_danh_dau_KHONG_dung_toi_ngu_canh_agent_va_KHONG_doi_updated_at(bo):
    """Ghi nhầm `agent_messages` là xoá sạch trí nhớ của cả phiên. Và dời `updated_at`
    thì phiên nhảy lên đầu danh sách chỉ vì một cú bấm nút."""
    c, db, _ = bo
    from app.models.conversation import Conversation

    truoc = db.get(Conversation, "c1").updated_at
    c.post("/agent/conversations/c1/messages/m2/resolved")
    sau = db.get(Conversation, "c1")
    assert sau.agent_messages == [{"nguyen": "ven"}]
    assert sau.updated_at == truoc


def test_ma_may_chu_TRA_RA_phai_TRUNG_ma_da_luu():
    """Mắt xích thiếu của lần sửa trước — và là lý do bản vá đầu không chạy.

    Giao diện tự gắn một mã cục bộ cho thẻ vừa nhận, còn máy chủ lưu bằng mã của nó.
    Hai mã không bao giờ khớp, nên lệnh "đánh dấu đã duyệt" trỏ vào mã không tồn tại,
    trả 404, và bị nuốt im lặng — bấm Duyệt xong tải lại trang là nút Duyệt mọc lại.

    Không gọi cả `/agent/chat` (cần mô hình + Gmail thật) mà đọc thẳng mã nguồn: chốt
    rằng máy chủ CÓ trả `messageId`, và mã đó là ĐÚNG mã nó vừa gắn vào tin nhắn agent,
    không phải một mã sinh riêng cho phản hồi.
    """
    import inspect
    from app.api import app as A

    ma = inspect.getsource(A.agent_chat)
    assert '"messageId": ma_agent' in ma, "phải trả về mã máy chủ vừa cấp"
    assert '"id": ma_agent, "role": "agent"' in ma, "và đó phải là mã ĐÃ LƯU, không phải mã khác"
