"""XEM CẢ CUỘC TRAO ĐỔI, không chỉ thư mới nhất.

Danh sách đã gộp một luồng nhiều lượt thành MỘT dòng (`_gom_theo_luong`), đúng như
Gmail. Nhưng mở dòng đó ra thì trước đây chỉ thấy thư mới nhất — các lượt trước không
có chỗ nào để xem. Gộp mà không mở ra được thì TỆ HƠN không gộp: người dùng còn không
biết mình đang bị giấu thứ gì.

Phần đáng test không phải "gọi Gmail có chạy không" (đó là việc của nhà cung cấp), mà
là hai đường LÙI: thư không có luồng, và khâu lấy luồng hỏng. Cả hai đều phải để người
dùng đọc được lá thư họ vừa bấm vào — một tính năng phụ hỏng không được kéo theo thứ
chính.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.app import app
from app.core.deps import get_current_session, get_db, get_gmail_token, get_provider
from app.schemas.email import Email


class _Phien:
    user_id = 1
    provider = "google"
    google_access_token = "tok"


def _thu(mid: str, tid: str | None, chu_de: str) -> Email:
    return Email(
        id=mid, threadId=tid, sender="Ai Đó", senderEmail="x@example.com",
        senderInitial="A", to="me@example.com", subject=chu_de, preview="...",
        body=["..."], time="09:00", date="06/09", unread=False, starred=False,
        category="moss", label=None, folder="inbox",
    )


@pytest.fixture()
def khach(monkeypatch):
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_session] = lambda: _Phien()
    app.dependency_overrides[get_gmail_token] = lambda: "tok"
    app.dependency_overrides[get_provider] = lambda: "google"
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_tra_ve_CA_luong_sap_cu_den_moi(khach, monkeypatch):
    from app.services import mail

    ds = [_thu("m1", "t1", "Hỏi"), _thu("m2", "t1", "Re: Hỏi"), _thu("m3", "t1", "Re: Hỏi")]
    monkeypatch.setattr(mail, "get_message", lambda p, t, i: ds[2])
    monkeypatch.setattr(mail, "get_thread", lambda p, t, tid: ds)

    r = khach.get("/emails/m3/thread")
    assert r.status_code == 200
    assert [e["id"] for e in r.json()["items"]] == ["m1", "m2", "m3"]


def test_thu_KHONG_co_luong_thi_tra_chinh_no(khach, monkeypatch):
    from app.services import mail

    monkeypatch.setattr(mail, "get_message", lambda p, t, i: _thu("le", None, "Thư lẻ"))
    def _khong_duoc_goi(*a, **k):
        raise AssertionError("không có threadId thì đừng hỏi nhà cung cấp làm gì")
    monkeypatch.setattr(mail, "get_thread", _khong_duoc_goi)

    assert [e["id"] for e in khach.get("/emails/le/thread").json()["items"]] == ["le"]


def test_lay_luong_HONG_thi_van_doc_duoc_thu_dang_mo(khach, monkeypatch):
    """Đây là điều quan trọng nhất: khâu phụ hỏng không được che mất thứ người dùng
    vừa bấm vào. Trả 500 ở đây nghĩa là mở thư ra thấy màn lỗi."""
    from app.services import mail

    monkeypatch.setattr(mail, "get_message", lambda p, t, i: _thu("m1", "t1", "Hỏi"))
    monkeypatch.setattr(mail, "get_thread",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Gmail sập")))

    r = khach.get("/emails/m1/thread")
    assert r.status_code == 200
    assert [e["id"] for e in r.json()["items"]] == ["m1"]


def test_luong_RONG_cung_lui_ve_thu_dang_mo(khach, monkeypatch):
    from app.services import mail

    monkeypatch.setattr(mail, "get_message", lambda p, t, i: _thu("m1", "t1", "Hỏi"))
    monkeypatch.setattr(mail, "get_thread", lambda *a, **k: [])
    assert [e["id"] for e in khach.get("/emails/m1/thread").json()["items"]] == ["m1"]
