"""Hai chỗ TRỐNG mà agent bị mù, tìm ra bằng cách gieo thư THẬT rồi hỏi lại.

Cả hai không phải lỗi crash. Chúng là chỗ trống trả về giá trị hợp lệ nhưng SAI:

  1. `EmailDetail.cc` ghi cứng `[]`. Gmail có header Cc đầy đủ (đã kiểm trên thư
     thật gửi đi trong lúc dựng bộ demo), nhưng qua tầng tool thì nó biến mất. Agent
     đọc một lá thư "gửi chung cả nhóm" và tin rằng đó là thư riêng — rồi chọn trả
     lời riêng, và ba người còn lại không bao giờ biết.

  2. `EmailSummary` không có cờ đính kèm. Nên khi agent đọc CẢ MỘT LUỒNG, nó không
     biết tệp nằm ở lượt nào; muốn biết phải gọi `get_email` cho từng lượt. Câu hỏi
     "file bạn gửi hôm trước nằm ở đâu trong đoạn này" là câu rất thật, và nó tốn n
     lời gọi Gmail thay vì không tốn lời gọi nào.

VÌ SAO KHÔNG BỘ TEST NÀO BẮT ĐƯỢC: mọi thư trong các bộ demo trước đều tự gửi cho
chính mình, không Cc ai, và không lá nào có tệp. Dữ liệu không có thì chỗ trống
không lộ. Đây là lý do bộ làm giàu vòng hai gieo đúng hai thứ đó.
"""

from __future__ import annotations

import asyncio

from app.schemas.email import Email
from app.tools.email_tools import _to_summary, get_email
from app.tools.registry import RequestContext


def _thu(**kw) -> Email:
    goc = dict(
        id="m1", sender="GVHD", senderEmail="gv@hcmus.edu.vn", senderInitial="G",
        to="quan@example.com", subject="Góp ý slide", preview="", body=["thân thư"],
        time="", date="2026-09-07 09:50", unread=True, starred=False, category="sea",
    )
    goc.update(kw)
    return Email(**goc)


# ── 1. Cc phải đi tới được agent ────────────────────────────────────────────

def test_get_email_tra_ve_Cc_that(monkeypatch):
    """Thư có ba người đồng gửi → `EmailDetail.cc` phải có đủ ba, không phải rỗng."""
    thu = _thu(cc="tai@x.com, tien@x.com, thien@x.com")
    monkeypatch.setattr("app.tools.email_tools.mail.get_message",
                        lambda *a, **k: thu)

    ra = asyncio.run(get_email(_dau_vao("m1"), _ctx()))
    assert ra.data.cc == ["tai@x.com", "tien@x.com", "thien@x.com"]


def test_get_email_khong_co_Cc_thi_rong(monkeypatch):
    """Thư riêng thì rỗng — nếu không, agent lại tưởng mọi thư đều gửi cả nhóm."""
    monkeypatch.setattr("app.tools.email_tools.mail.get_message",
                        lambda *a, **k: _thu(cc=None))
    ra = asyncio.run(get_email(_dau_vao("m1"), _ctx()))
    assert ra.data.cc == []


def test_Cc_co_dau_phay_thua_khong_sinh_phan_tu_rong(monkeypatch):
    """Header thật hay có dấu phẩy cuối. Không lọc thì danh sách có một chuỗi rỗng,
    và agent sẽ nói "thư gửi cho 4 người" trong khi chỉ có 3."""
    monkeypatch.setattr("app.tools.email_tools.mail.get_message",
                        lambda *a, **k: _thu(cc="a@x.com, b@x.com,"))
    ra = asyncio.run(get_email(_dau_vao("m1"), _ctx()))
    assert ra.data.cc == ["a@x.com", "b@x.com"]


def test_bcc_van_rong_va_do_la_DUNG(monkeypatch):
    """BCC KHÔNG được lộ cho người nhận — đó là toàn bộ ý nghĩa của BCC. Rỗng ở đây
    là sự thật, không phải chỗ trống bỏ quên như `cc`."""
    monkeypatch.setattr("app.tools.email_tools.mail.get_message",
                        lambda *a, **k: _thu(cc="a@x.com"))
    ra = asyncio.run(get_email(_dau_vao("m1"), _ctx()))
    assert ra.data.bcc == []


# ── 2. Cờ đính kèm phải đi theo mỗi lượt trong luồng ────────────────────────

def test_summary_mang_co_dinh_kem():
    assert _to_summary(_thu(hasAttachment=True)).has_attachment is True


def test_summary_khong_co_tep_thi_False():
    assert _to_summary(_thu(hasAttachment=False)).has_attachment is False


def test_hasAttachment_None_hieu_la_KHONG_CO():
    """`None` = nguồn không nói được (thư lấy từ store cũ), KHÔNG phải "có tệp".

    Chọn False vì hai kiểu sai không ngang nhau: bỏ sót một tệp thì người dùng hỏi
    lại, còn khẳng định có tệp mà không có thì họ đi tìm một thứ không tồn tại."""
    assert _to_summary(_thu(hasAttachment=None)).has_attachment is False


def test_luong_chi_ra_dung_LUOT_NAO_giu_tep():
    """Hình dạng đúng của lỗi đã gặp: tệp ở lượt ĐẦU, hai lượt sau không có.

    Đây là thứ khiến câu "file nằm ở đâu trong đoạn chat này" trả lời được mà không
    phải mở từng lượt ra xem."""
    luong = [
        _thu(id="l1", subject="Đặc tả tool MCP — bản 1", hasAttachment=True),
        _thu(id="l2", subject="Re: Đặc tả tool MCP — bản 1", hasAttachment=False),
        _thu(id="l3", subject="Re: Đặc tả tool MCP — bản 1", hasAttachment=False),
    ]
    co = [s.id for s in map(_to_summary, luong) if s.has_attachment]
    assert co == ["l1"]


# ── phụ trợ ─────────────────────────────────────────────────────────────────

def _dau_vao(mid: str):
    from app.tools.schemas import GetEmailInput
    return GetEmailInput(email_id=mid)


def _ctx() -> RequestContext:
    return RequestContext(user_id="1", access_token="tok", email_provider="gmail")


# ── 3. Chuyển tiếp KHÔNG mang tệp — và phải NÓI RA ──────────────────────────
#
# Giới hạn này có thật và đã được ghi trong tài liệu, nhưng nó nằm ở chỗ không ai
# đọc: docstring của tầng service. Mô hình đọc docstring của TOOL, còn người dùng
# đọc câu báo kết quả — cả hai chỗ trước đây đều im lặng. Nên luồng thật là: người
# dùng nhờ chuyển tiếp một thư có tệp, thấy "Đã chuyển tiếp thư", và bên nhận không
# có tệp. Đúng loại hỏng đã gặp một lần với thư trả lời.

def test_chuyen_tiep_thu_co_tep_thi_bao_ro_la_tep_KHONG_di(monkeypatch):
    from app.tools.email_tools import forward_email
    from app.tools.schemas import ForwardEmailInput

    monkeypatch.setattr(
        "app.tools.email_tools.mail.forward_email",
        lambda *a, **k: {"id": "x", "threadId": "t",
                         "tep_bo_lai": ["bao-cao.pdf", "bang-diem.csv"]})
    ra = asyncio.run(forward_email(
        ForwardEmailInput(email_id="m1", to="ai@do.com", note=""), _ctx()))

    assert "bao-cao.pdf" in ra.message and "bang-diem.csv" in ra.message
    assert "KHÔNG đi kèm" in ra.message


def test_chuyen_tiep_thu_KHONG_co_tep_thi_khong_doa_nguoi_dung(monkeypatch):
    """Cảnh báo phải ĐÚNG LÚC. Dán vào mọi lần chuyển tiếp thì nó thành tiếng ồn,
    và tiếng ồn thì người ta học được cách bỏ qua — kể cả lúc nó nói thật."""
    from app.tools.email_tools import forward_email
    from app.tools.schemas import ForwardEmailInput

    monkeypatch.setattr("app.tools.email_tools.mail.forward_email",
                        lambda *a, **k: {"id": "x", "threadId": "t", "tep_bo_lai": []})
    ra = asyncio.run(forward_email(
        ForwardEmailInput(email_id="m1", to="ai@do.com", note=""), _ctx()))
    assert "LƯU Ý" not in ra.message


def test_mo_ta_tool_forward_co_noi_ve_tep():
    """Mô hình quyết định TRƯỚC khi gọi, và nó chỉ có docstring để dựa vào. Cảnh báo
    chỉ nằm ở câu trả kết quả là quá muộn — lúc đó thư đã đi rồi."""
    from app.tools.registry import tool_registry
    mo_ta = tool_registry.get_spec("forward_email").description
    assert "KHÔNG MANG THEO TỆP ĐÍNH KÈM" in mo_ta
