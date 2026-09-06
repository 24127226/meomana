"""BA TÍNH NĂNG BỔ SUNG — và luật "thêm gì thì LLM cũng phải làm được".

Soát lại MeoArc so với Gmail, ba thứ thiếu thật: chuyển tiếp, đánh dấu thư rác, và
trả lời tất cả. Mỗi cái phải đi ĐỦ BỐN TẦNG chứ không chỉ mọc thêm một cái nút:
nhà cung cấp → tool cho agent trong app → MCP cho agent ngoài → giao diện.

Một nút bấm mà agent không gọi được thì phá đúng luận điểm của MeoArc: "mở hộp thư ra
cho agent điều khiển". Bộ test này chốt đúng điều đó.
"""

from __future__ import annotations

import pytest

from app.services.gmail_send import cc_tra_loi_tat_ca


# ── TRẢ LỜI TẤT CẢ: đúng người, không thừa, không thiếu ──────────────────────

def test_cc_gom_moi_nguoi_trong_thu_goc():
    ra = cc_tra_loi_tat_ca("a@x.vn, b@x.vn", "c@x.vn", "sep@x.vn", "toi@x.vn")
    assert ra == ["a@x.vn", "b@x.vn", "c@x.vn"]


def test_cc_LOAI_chinh_minh():
    """Không loại thì mỗi lần trả lời tất cả là tự gửi cho mình một bản."""
    ra = cc_tra_loi_tat_ca("a@x.vn, toi@x.vn", "", "sep@x.vn", "toi@x.vn")
    assert ra == ["a@x.vn"]


def test_cc_LOAI_nguoi_gui():
    """Người gửi đã nằm ở To rồi — để cả hai chỗ thì họ nhận hai bản."""
    ra = cc_tra_loi_tat_ca("sep@x.vn, a@x.vn", "", "Sếp <sep@x.vn>", "toi@x.vn")
    assert ra == ["a@x.vn"]


def test_cc_KHU_TRUNG():
    ra = cc_tra_loi_tat_ca("a@x.vn", "a@x.vn, A@X.VN", "sep@x.vn", "toi@x.vn")
    assert ra == ["a@x.vn"]


def test_cc_khong_con_ai_thi_tra_None():
    """None chứ không phải [] — `_build_raw` bỏ qua Cc rỗng, trả None cho đúng ý."""
    assert cc_tra_loi_tat_ca("toi@x.vn", "", "sep@x.vn", "toi@x.vn") is None
    assert cc_tra_loi_tat_ca("", "", "sep@x.vn", "toi@x.vn") is None


def test_cc_doc_duoc_dang_co_ten_hien_thi():
    ra = cc_tra_loi_tat_ca('"Trần A" <a@x.vn>, B <b@x.vn>', "", "sep@x.vn", "toi@x.vn")
    assert ra == ["a@x.vn", "b@x.vn"]


def test_header_To_Cc_duoc_XIN_khi_lay_thu_goc():
    """Chỗ hỏng LẶNG NHẤT của tính năng này: Gmail chỉ trả header nào mình xin. Quên xin
    To/Cc thì danh sách Cc dựng ra rỗng và 'trả lời tất cả' im lặng thành trả lời thường
    — không lỗi, không cảnh báo, chỉ là mấy người kia không nhận được."""
    import inspect
    from app.services import gmail_send

    ma = inspect.getsource(gmail_send.reply_email)
    assert '"To"' in ma and '"Cc"' in ma


# ── LLM PHẢI DÙNG ĐƯỢC: đủ bốn tầng cho cả ba tính năng ─────────────────────

def test_tool_reply_email_TRUYEN_reply_all_xuong_duoi():
    """`reply_all` từng chỉ là một trường trong schema mà KHÔNG tầng nào dùng tới — LLM
    đặt cờ đó thì chẳng có gì xảy ra. Nói dối trong im lặng còn tệ hơn thiếu hẳn."""
    import inspect
    from app.tools import email_tools

    assert "inp.reply_all" in inspect.getsource(email_tools.reply_email)


def test_agent_trong_app_goi_duoc_ca_ba():
    from app.tools.registry import tool_registry
    from app.tools.schemas import BulkAction
    import app.tools.email_tools  # noqa: F401 — để tool tự đăng ký

    assert "forward_email" in tool_registry._tools, "agent phải chuyển tiếp được"
    assert BulkAction.SPAM.value == "spam"
    assert BulkAction.NOT_SPAM.value == "not_spam"


def test_agent_NGOAI_goi_duoc_ca_ba_qua_MCP():
    from app.mcp import server as S

    assert callable(S.forward_email), "MCP phải phơi chuyển tiếp"
    assert "reply_all" in S.reply_email.__doc__, "MCP phải nói rõ có trả lời tất cả"
    for v in ("spam", "not_spam"):
        assert f"'{v}'" in S.bulk_action.__doc__, f"MCP phải liệt kê '{v}'"


def test_chuyen_tiep_di_qua_CONG_XAC_NHAN():
    """Chuyển tiếp đưa nội dung của NGƯỜI KHÁC cho người thứ ba — gửi nhầm địa chỉ là
    làm lộ thư của người không hề tham gia cuộc trao đổi."""
    from app.mcp.server import _needs_confirm

    ra = _needs_confirm("forward_email", {"to": "ai@do.vn"})
    assert ra["success"] is False and ra["needs_confirmation"] is True
    assert "NGƯỜI KHÁC" in ra["instruction"]


@pytest.mark.asyncio
async def test_thu_rac_KHONG_bi_cong_xac_nhan_chan(monkeypatch):
    """Cả hai chiều đều đảo ngược được nên KHÔNG cần cổng. Dựng thêm hàng rào ở đây chỉ
    làm người dùng quen bấm-cho-qua, rồi tới cổng THẬT (gửi/xoá) họ cũng bấm-cho-qua.

    Kiểm bằng cách gọi thật tool MCP: 'spam' phải CHẠY THẲNG, còn 'delete' vẫn phải bị
    chặn — nếu không thì bản sửa này đã vô tình phá luôn cổng đang có."""
    from app.mcp import server as S

    da_goi = []
    async def _gia(name, args):
        da_goi.append(args["action"])
        return {"success": True}
    monkeypatch.setattr(S, "_call", _gia)
    monkeypatch.setattr(S, "_audit_mcp", lambda *a, **k: None)

    for hd in ("spam", "not_spam"):
        ra = await S.bulk_action(["m1"], hd)
        assert ra.get("needs_confirmation") is not True, f"'{hd}' đảo ngược được, đừng chặn"
    assert da_goi == ["spam", "not_spam"]

    chan = await S.bulk_action(["m1"], "delete")
    assert chan["needs_confirmation"] is True, "cổng cho 'delete' phải còn nguyên"
    assert da_goi == ["spam", "not_spam"], "'delete' KHÔNG được chạy khi chưa duyệt"


# ── Định tuyến nhà cung cấp ─────────────────────────────────────────────────

def test_spam_gmail_them_SPAM_va_BO_INBOX(monkeypatch):
    """Thiếu vế bỏ INBOX thì thư nằm ở CẢ hai chỗ — người dùng thấy thứ mình vừa vứt đi
    vẫn còn trong hộp thư."""
    from app.services import mail, gmail_actions

    goi = {}
    monkeypatch.setattr(gmail_actions, "modify_labels",
                        lambda tok, ids, add=None, remove=None: goi.update(add=add, remove=remove) or 1)
    mail.spam("google", "tok", ["m1"])
    assert goi["add"] == ["SPAM"] and goi["remove"] == ["INBOX"]

    goi.clear()
    mail.not_spam("google", "tok", ["m1"])
    assert goi["add"] == ["INBOX"] and goi["remove"] == ["SPAM"]


def test_outlook_di_dung_thu_muc(monkeypatch):
    from app.services import mail, outlook_service

    dich = []
    monkeypatch.setattr(outlook_service, "_move", lambda tok, ids, d: dich.append(d) or 1)
    mail.spam("microsoft", "tok", ["m1"])
    mail.not_spam("microsoft", "tok", ["m1"])
    assert dich == ["junkemail", "inbox"]
