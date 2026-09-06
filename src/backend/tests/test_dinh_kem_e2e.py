"""ĐÍNH KÈM — ĐO Ở TẦNG HTTP, ĐÚNG ĐƯỜNG NGƯỜI DÙNG ĐI.

`test_dinh_kem.py` đã kiểm tool `send_email` rất kỹ và tất cả đều xanh. Nhưng người
dùng báo: "mail thì qua mà không có phần đính kèm". Nghĩa là chỗ hỏng KHÔNG nằm trong
tool — nó nằm ở một trong các mối nối mà không test nào chạm tới:

    POST /uploads  →  id tệp  →  args._tep của bản ghi chờ duyệt  →  POST
    /confirmations/{id}/approve  →  RequestContext.tep_dinh_kem  →  gmail_send

Mỗi mối nối đều "đúng" khi đọc riêng lẻ. Bộ test này nối chúng lại và đi hết một
lượt, vì đó là thứ duy nhất chứng minh được cả chuỗi.

── VÌ SAO LOẠI HỎNG NÀY IM LẶNG ──
`_lay_tep` cố ý BỎ QUA id không tra được, để một tệp hết hạn không làm hỏng cả lượt
gửi. Quyết định đó đúng, nhưng nó khiến MỌI đứt gãy trên chuỗi trên đều ra cùng một
triệu chứng: thư đi bình thường, không lỗi, chỉ thiếu tệp. Không có gì để lần.
"""

from __future__ import annotations

import types

import pytest


@pytest.fixture()
def app_client(monkeypatch):
    """App thật + phiên đăng nhập giả. KHÔNG chặn tool_registry.call — ở đây phải để
    tool chạy thật thì mới thấy tệp có đi tới lớp gửi hay không."""
    try:
        from fastapi.testclient import TestClient

        from app.api.app import app
        from app.core import deps
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Không import được app (DB tắt?): {exc}")

    fake = types.SimpleNamespace(user_id=616161, token="qa")
    app.dependency_overrides[deps.get_current_session] = lambda: fake
    app.dependency_overrides[deps.get_gmail_token] = lambda: "fake-token"

    import app.api.app as app_mod
    monkeypatch.setattr(app_mod, "_record", lambda *a, **k: None)

    from app.services import upload_store
    upload_store._UPLOADS.clear()

    with TestClient(app) as c:
        yield c, fake
    app.dependency_overrides.clear()
    upload_store._UPLOADS.clear()


def _bat_gmail(monkeypatch) -> dict:
    """Chặn ĐÚNG lớp cuối cùng (`mail.send_email`) và ghi lại những gì tới nơi.

    Chặn ở đây chứ không ở tool: mọi mối nối phía trên phải chạy thật thì phép đo mới
    có nghĩa."""
    ghi: dict = {}

    # `**_` để bản giả không vỡ mỗi khi hàm thật thêm tham số (vd `html`). Phép thử này
    # kiểm ĐÍNH KÈM, không kiểm chữ ký hàm — bắt nó khai đủ tham số là biến nó thành
    # một cái bẫy đỏ mỗi lần mở rộng tính năng, không liên quan gì tới thứ nó bảo vệ.
    def gia(provider, token, to, subject, body, cc=None, bcc=None, attachments=None, **_):
        ghi.update(to=to, subject=subject, attachments=attachments)
        return {"id": "m1", "threadId": "t1"}

    from app.tools import email_tools as T
    monkeypatch.setattr(T.mail, "send_email", gia)
    return ghi


def _tao_yeu_cau(user_id: int, tep_ids: list[str]):
    """Bản ghi chờ duyệt ĐÚNG như /agent/chat tạo ra khi có tệp đính kèm — kể cả khoá
    nội bộ `_tep` nằm lẫn trong args (xem app.py, nhánh `confirm_card`)."""
    from app.core.db import SessionLocal
    from app.models.user import User
    from app.repo import confirmation_repo

    db = SessionLocal()
    try:
        if db.get(User, user_id) is None:
            db.add(User(id=user_id, email=f"qa{user_id}@example.test",
                        name="QA", initial="Q"))
            db.commit()
        r = confirmation_repo.create(
            db, user_id=user_id, action="send_email",
            description="Gửi thư kèm tệp?",
            args={"to": ["ai_do@example.com"], "subject": "Chào",
                  "body": "Nội dung", "_tep": tep_ids},
        )
        return r.id
    finally:
        db.close()


# ── Mối nối 1: /uploads có thật sự cất được bytes không ──────────────────────

def test_uploads_tra_ve_id_tra_lai_duoc_bytes(app_client):
    c, _ = app_client
    r = c.post("/uploads", files={"file": ("bao-cao.pdf", b"%PDF-1.4 noi dung that",
                                           "application/pdf")})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]

    from app.services import upload_store
    f = upload_store.get(fid)
    assert f is not None, "id vừa cấp mà tra không ra thì mọi thứ phía sau đều vô nghĩa"
    assert f["content"] == b"%PDF-1.4 noi dung that"
    assert f["name"] == "bao-cao.pdf"


# ── Cả chuỗi: upload → chờ duyệt → Duyệt → tệp tới lớp gửi ───────────────────

def test_TU_UPLOAD_TOI_GMAIL_tep_di_duoc_het_chuoi(app_client, monkeypatch):
    """Phép kiểm quan trọng nhất của file này. Đây đúng là việc người dùng làm:
    kẹp tệp trong khung chat, nhờ trợ lý gửi, rồi bấm Duyệt."""
    c, fake = app_client
    ghi = _bat_gmail(monkeypatch)

    fid = c.post("/uploads", files={"file": ("ke-hoach.docx", b"noi dung docx",
                                             "application/vnd.openxmlformats")}).json()["id"]
    rid = _tao_yeu_cau(fake.user_id, [fid])

    r = c.post(f"/confirmations/{rid}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["result"]["success"] is True

    assert ghi.get("attachments"), "THƯ ĐI MÀ KHÔNG CÓ TỆP — đúng lỗi người dùng báo"
    assert len(ghi["attachments"]) == 1
    assert ghi["attachments"][0]["name"] == "ke-hoach.docx"
    assert ghi["attachments"][0]["content"] == b"noi dung docx"


def test_khoa_noi_bo__tep__KHONG_lot_vao_tham_so_tool(app_client, monkeypatch):
    """`_tep` phải được gỡ khỏi args trước khi gọi tool: nó không có trong schema nào,
    để lẫn vào là Pydantic từ chối cả lời gọi và thư không đi được."""
    c, fake = app_client
    ghi = _bat_gmail(monkeypatch)

    fid = c.post("/uploads", files={"file": ("a.txt", b"x", "text/plain")}).json()["id"]
    rid = _tao_yeu_cau(fake.user_id, [fid])

    r = c.post(f"/confirmations/{rid}/approve")
    assert r.json()["result"]["success"] is True
    assert ghi["to"] == "ai_do@example.com"


def test_khong_co_tep_thi_van_gui_binh_thuong(app_client, monkeypatch):
    """Đường phổ biến nhất không được vì tính năng này mà đổi hành vi."""
    c, fake = app_client
    ghi = _bat_gmail(monkeypatch)
    rid = _tao_yeu_cau(fake.user_id, [])
    assert c.post(f"/confirmations/{rid}/approve").json()["result"]["success"] is True
    assert not ghi.get("attachments")


# ── /emails/send: đường của hộp thoại Soạn thư (không qua trợ lý) ────────────

def test_hop_thoai_soan_thu_cung_dinh_duoc_tep(app_client, monkeypatch):
    """Hai đường gửi hoàn toàn tách biệt (trợ lý và nút Soạn thư), nên phải đo cả hai.
    Sửa đúng một đường rồi tưởng xong là lỗi rất dễ mắc."""
    c, _ = app_client
    ghi: dict = {}

    def gia(provider, token, to, subject, body, cc=None, bcc=None, attachments=None, **_):
        ghi.update(to=to, attachments=attachments)
        return {"id": "m1", "threadId": "t1"}

    import app.api.app as app_mod
    monkeypatch.setattr(app_mod.mail, "send_email", gia)

    fid = c.post("/uploads", files={"file": ("anh.png", b"\x89PNG fake",
                                             "image/png")}).json()["id"]
    r = c.post("/emails/send", json={"to": "ai_do@example.com", "subject": "S",
                                     "body": "B", "attachmentIds": [fid]})
    assert r.status_code == 200, r.text
    assert ghi.get("attachments"), "Soạn thư gửi đi mà không kèm tệp"
    assert ghi["attachments"][0]["name"] == "anh.png"


# ── /emails/{id}/reply: đường TRẢ LỜI — chỗ vừa hỏng ─────────────────────────

def test_TRA_LOI_cung_dinh_duoc_tep(app_client, monkeypatch):
    """Người dùng báo: đính tệp vào thư trả lời thì chip hiện bình thường mà bên nhận
    không có gì.

    Đúng vậy: đường trả lời KHÔNG hề mang tệp. Giao diện không gửi `attachmentIds`,
    `ReplyReq` không có trường đó, và `gmail_send.reply_email` không nhận tham số nào
    cho tệp. Tệp lên tới máy chủ rồi nằm im trong kho tạm.

    Đây đúng là lỗi mà chú thích đầu file này đã cảnh báo — "sửa đúng một đường rồi
    tưởng xong" — chỉ là lần này ở đường trả lời.
    """
    c, _ = app_client
    ghi: dict = {}

    def gia(provider, token, msg_id, body, **kw):
        ghi.update(msg_id=msg_id, body=body, attachments=kw.get("attachments"))
        return {"id": "m9", "threadId": "t9"}

    import app.api.app as app_mod
    monkeypatch.setattr(app_mod.mail, "reply_email", gia)

    fid = c.post("/uploads", files={"file": ("bang-diem.pdf", b"%PDF diem",
                                             "application/pdf")}).json()["id"]
    r = c.post("/emails/goc123/reply",
               json={"body": "Dạ em gửi ạ", "attachmentIds": [fid]})
    assert r.status_code == 200, r.text
    assert ghi.get("attachments"), "THƯ TRẢ LỜI ĐI MÀ KHÔNG CÓ TỆP — đúng lỗi được báo"
    assert ghi["attachments"][0]["name"] == "bang-diem.pdf"
    assert ghi["attachments"][0]["content"] == b"%PDF diem"


def test_TRA_LOI_thieu_tep_thi_TU_CHOI_chu_khong_gui_im_lang(app_client, monkeypatch):
    """Luật này vốn chỉ có ở đường gửi thư mới. Tách ra dùng chung nên trả lời cũng
    phải theo: thư gửi thành công NHƯNG THIẾU thứ chính cần gửi thì tệ hơn một lỗi rõ
    ràng — người gửi tin là xong và chỉ biết sự thật từ phía người nhận."""
    c, _ = app_client
    da_goi = []

    import app.api.app as app_mod
    monkeypatch.setattr(app_mod.mail, "reply_email",
                        lambda *a, **k: da_goi.append(1) or {"id": "x", "threadId": "y"})

    r = c.post("/emails/goc123/reply",
               json={"body": "Gửi kèm nhé", "attachmentIds": ["id-khong-ton-tai"]})
    assert r.status_code == 409
    assert da_goi == [], "phải TỪ CHỐI, tuyệt đối không gửi một bức thư thiếu tệp"


def test_TRA_LOI_khong_co_tep_thi_van_binh_thuong(app_client, monkeypatch):
    """Đường phổ biến nhất không được vì tính năng này mà đổi hành vi."""
    c, _ = app_client
    ghi: dict = {}

    import app.api.app as app_mod
    monkeypatch.setattr(app_mod.mail, "reply_email",
                        lambda p, t, i, b, **kw: ghi.update(attachments=kw.get("attachments"))
                        or {"id": "m1", "threadId": "t1"})

    assert c.post("/emails/goc123/reply", json={"body": "ok"}).status_code == 200
    assert not ghi.get("attachments")
