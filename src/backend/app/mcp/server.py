# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/mcp/server.py — MCP SERVER (Pha 4: "agent-native", tiêu chí 10đ)║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ MCP (Model Context Protocol) = "ổ cắm chuẩn" để AGENT BÊN NGOÀI    ║
# ║ (Claude Desktop, Codex...) cắm vào và GỌI TOOL của app mình.       ║
# ║ Khác /agent/chat (LLM nằm TRONG app), ở đây LLM nằm Ở NGOÀI: user  ║
# ║ dùng agent của họ → agent gọi MCP → MCP chạy tool → thao tác Gmail.║
# ║                                                                    ║
# ║ THEO ĐÚNG Q&A CỦA THẦY (tiêu chí "LLM as main program" = 10đ):     ║
# ║  • Phơi TOOL HẠT MỊN (search/get/send/label/bulk...) để agent      ║
# ║    ngoài TỰ SUY LUẬN — KHÔNG phơi tool to kiểu summarize_and_      ║
# ║    process (suy luận vẫn của app → chỉ 9đ).                        ║
# ║  • Mỗi tool là VỎ MỎNG: gọi cùng tool_registry.call(...) mà        ║
# ║    /agent/chat dùng → MỘT bộ tool lõi, BA khách: UI web, Gemini    ║
# ║    nội bộ, agent ngoài qua MCP.                                    ║
# ║                                                                    ║
# ║ Điểm riêng của MeoArc (vượt yêu cầu tối thiểu):                    ║
# ║  1. CONFIRM-GATE: hành động KHÔNG HOÀN TÁC (gửi/xoá) bị chặn ở      ║
# ║     TẦNG TOOL — lần gọi đầu chỉ trả BẢN XEM TRƯỚC + yêu cầu agent   ║
# ║     hỏi người dùng, phải gọi lại với confirm=true mới chạy thật.   ║
# ║     → human-in-the-loop được CƯỠNG CHẾ cả với agent ngoài (UC010), ║
# ║     không trông chờ thiện chí của LLM.                             ║
# ║  2. MCP PROMPTS: 3 kỹ năng (digest/triage/meeting-brief) phơi ra    ║
# ║     menu Claude Desktop — 1 click là agent ngoài chạy đúng quy      ║
# ║     trình dùng tool hạt mịn (cùng "thư viện kỹ năng" với agent     ║
# ║     trong app).                                                    ║
# ║  3. RESOURCE meoarc://whoami — agent ngoài tự biết đang thao tác    ║
# ║     hộp thư của ai.                                                ║
# ╚══════════════════════════════════════════════════════════════════╝

import logging
import os
import time
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.labeling import ALL_CATEGORIES
from app.tools.schemas import BulkAction
from app.models.session import AuthSession
from app.repo import session_repo, audit_repo, subscription_repo, connected_account_repo
from app.services import auth_service, auth_service_ms
from app.tools.registry import tool_registry, RequestContext
import app.tools.email_tools  # noqa: F401 — import ĐỂ các tool tự đăng ký vào registry

logger = logging.getLogger("app.mcp")

# Cửa xác thực chỉ có tác dụng trên đường HTTP — FastMCP không hỏi Bearer khi chạy stdio.
# Nên gắn sẵn không làm hỏng lối stdio đang dùng, mà lại bảo đảm KHÔNG có cách nào bật
# HTTP lên mà quên cắm xác thực: cùng một đối tượng `mcp` phục vụ cả hai đường.
from app.mcp.xac_thuc import XacThucBangThe  # noqa: E402  (đặt sau logger cho dễ đọc)

mcp = FastMCP("MeoArc", auth=XacThucBangThe())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── NFR-Speed: CACHE "thẻ ra vào" (agent ngoài thường gọi 3-10 tool liên tiếp; ─────
# không cache thì MỖI tool = 1 lần mở DB + có thể 1 lần refresh token → chậm vô ích).
# TTL 45s < biên làm mới token (60s) nên không bao giờ dùng token sắp chết.
# Cache PHẢI khoá theo NGƯỜI DÙNG. Bản trước là một ô nhớ duy nhất, đúng khi cả tiến
# trình chỉ phục vụ một người qua stdio — nhưng qua HTTP thì hai người gọi gần nhau sẽ
# dùng chung ô đó, và người thứ hai thao tác hộp thư của người thứ nhất. Đây là loại lỗi
# không bao giờ lộ ra lúc tự thử một mình.
_CTX_CACHE: dict[str, tuple[RequestContext, float]] = {}
_CTX_TTL = 45.0

# Ngữ cảnh của ĐÚNG lượt gọi đang chạy. `_audit_mcp` trước đây đọc ô cache toàn cục để
# biết ghi nhật ký cho ai — dưới HTTP đồng thời thì nó ghi nhầm người, tức nhật ký kiểm
# toán nói dối, mà nhật ký nói dối còn tệ hơn không có nhật ký. ContextVar đi theo từng
# tác vụ async nên không lẫn giữa các lượt.
_CTX_HIEN_TAI: ContextVar[RequestContext | None] = ContextVar("meoarc_mcp_ctx", default=None)


def _uid_tu_http() -> int | None:
    """user_id của thẻ Bearer đang gọi, hoặc None nếu đang chạy stdio (không có HTTP)."""
    try:
        at = get_access_token()
    except Exception:
        return None
    sub = getattr(at, "subject", None) if at else None
    return int(sub) if sub and str(sub).isdigit() else None


def _resolve_ctx() -> RequestContext:
    """Lấy 'thẻ ra vào' (access_token Gmail) cho agent ngoài — có cache 45s theo người.

    HAI ĐƯỜNG VÀO, HAI LUẬT KHÁC HẲN NHAU:
    • Qua HTTP: thẻ Bearer đã được `XacThucBangThe` kiểm và cho biết user_id. Phục vụ
      ĐÚNG người đó, không ai khác.
    • Qua stdio: agent chạy cùng máy với backend nên ai chạy được tiến trình thì vốn đã
      có quyền trên máy. Giữ nguyên lối cũ — env MEOARC_ACCESS_TOKEN, hoặc phiên đăng
      nhập mới nhất trong DB.
    """
    uid = _uid_tu_http()

    # Lối tắt env CHỈ dành cho stdio. Qua HTTP mà vẫn nhận nó thì đặt một biến môi trường
    # là mọi người mang thẻ khác nhau đều rơi vào chung một hộp thư — biến cả lớp xác
    # thực vừa dựng thành hình thức.
    env_token = os.getenv("MEOARC_ACCESS_TOKEN")
    if env_token and uid is None:
        # Demo env: cho ép provider qua MEOARC_PROVIDER ('microsoft' để test Outlook), mặc định google.
        ctx = RequestContext(user_id="env", access_token=env_token,
                             email_provider=os.getenv("MEOARC_PROVIDER", "google"))
        _CTX_HIEN_TAI.set(ctx)
        return ctx

    khoa = str(uid) if uid is not None else "stdio:moi-nhat"
    now = time.monotonic()
    da_co = _CTX_CACHE.get(khoa)
    if da_co is not None and now - da_co[1] < _CTX_TTL:
        _CTX_HIEN_TAI.set(da_co[0])
        return da_co[0]

    db = SessionLocal()
    try:
        dk = select(AuthSession).where(AuthSession.google_access_token.isnot(None))
        if uid is not None:
            dk = dk.where(AuthSession.user_id == uid)
        s = db.scalars(dk.order_by(AuthSession.expires_at.desc())).first()
        if s is None:
            raise RuntimeError("Chưa có phiên đăng nhập nào — hãy đăng nhập trên web trước đã.")
        # Lấy token từ KẾT NỐI hộp thư — cùng nguồn với web (deps.get_gmail_token).
        # Hai đường đọc hai nơi thì mỗi bên tự làm mới một bản token, lệch nhau, và lỗi
        # chỉ lộ ra sau vài giờ khi một bên hết hạn.
        acc = connected_account_repo.primary_for(db, s.user_id)
        if acc is not None:
            provider, token = acc.provider, acc.access_token
            han, refresh = acc.token_expiry, acc.refresh_token
        else:
            provider = session_repo.get_provider(db, s.token)
            token, han, refresh = s.google_access_token, s.google_token_expiry, s.google_refresh_token

        if han and han <= _utcnow() + timedelta(seconds=60) and refresh:
            if provider == "microsoft":
                token, expires_in = auth_service_ms.refresh_access_token(refresh)
            else:
                token, expires_in = auth_service.refresh_access_token(refresh)
            if acc is not None:
                connected_account_repo.update_access_token(
                    db, acc, token, _utcnow() + timedelta(seconds=int(expires_in or 3600)))
            else:
                session_repo.update_access_token(db, s, token, expires_in)
        # Agent NGOÀI (Claude Desktop…) chịu đúng cửa sổ quét của gói như người dùng web —
        # nếu không thì đi cửa MCP là lách được giới hạn.
        _sub = subscription_repo.get_or_create(db, s.user_id)
        ctx = RequestContext(user_id=str(s.user_id), access_token=token,
                             email_provider=provider, tier=_sub.tier,
                             scan_days=subscription_repo.scan_days_of(_sub))
        _CTX_CACHE[khoa] = (ctx, now)
        _CTX_HIEN_TAI.set(ctx)
        return ctx
    finally:
        db.close()


def _ok(res) -> bool:
    """Tool coi là THÀNH CÔNG trừ khi trả dict có success=False (nhánh lỗi của _call/registry)."""
    return not (isinstance(res, dict) and res.get("success") is False)


def _audit_mcp(action: str, tool_name: str, ids: list[str] | None, res,
               details: dict | None = None) -> None:
    """Ghi 1 dòng AuditLog actor_type='mcp' cho hành động GHI do agent NGOÀI gọi qua MCP
    (accountability đồng nhất với web/agent nội bộ). Chỉ ghi khi biết user_id thật của phiên
    (bỏ qua demo env token vì user_id='env' không phải FK users.id). Nuốt mọi lỗi phụ trợ."""
    ctx = _CTX_HIEN_TAI.get()
    uid = getattr(ctx, "user_id", None) if ctx else None
    if not (uid and str(uid).isdigit()):
        return
    db = SessionLocal()
    try:
        audit_repo.log(
            db, user_id=int(uid), action=action, tool_name=tool_name, actor_type="mcp",
            affected_email_ids=ids or [], status="success" if _ok(res) else "failed",
            details=details or {}, conversation_id=None,
        )
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


async def _call(name: str, args: dict) -> dict:
    """Chạy 1 tool qua registry (tự validate input bằng Pydantic) → dict cho MCP trả về.
    Lỗi KHÔNG ném ra ngoài (agent ngoài xử lý JSON lỗi tốt hơn exception giao thức):
    trả {"success": false, "error": ...} để agent tự đọc và nói lại với người dùng."""
    t0 = time.perf_counter()
    try:
        res = await tool_registry.call(name, args, _resolve_ctx())
        out = res.model_dump() if hasattr(res, "model_dump") else res
        logger.info("MCP tool %s OK (%.0fms)", name, (time.perf_counter() - t0) * 1000)
        return out
    except Exception as exc:
        # Token có thể là thủ phạm → bỏ cache CỦA ĐÚNG NGƯỜI này, lần sau lấy tươi.
        # Xoá sạch cả bảng thì một người gặp lỗi làm chậm lây sang mọi người còn lại.
        _uid = _uid_tu_http()
        _CTX_CACHE.pop(str(_uid) if _uid is not None else "stdio:moi-nhat", None)
        logger.warning("MCP tool %s FAILED: %s", name, exc)
        return {"success": False, "error": str(exc),
                "hint": "Đọc 'error' và giải thích cho người dùng; thử sửa tham số rồi gọi lại."}


# Hậu quả THẬT của từng hành động, nói đúng mức — không nói quá, không nói giảm.
#
# Trước đây mọi hành động dùng chung một câu "HÀNH ĐỘNG KHÔNG HOÀN TÁC". Câu đó ĐÚNG
# với gửi/trả lời (người nhận đã đọc rồi, không rút lại được) nhưng SAI với xoá: xoá là
# chuyển vào Thùng rác và đã có `restore` lấy về. Nói quá cũng hỏng như nói giảm — agent
# ngoài đọc chỉ dẫn này để soạn câu hỏi cho người dùng, nên một cảnh báo thổi phồng sẽ
# được nó chuyển nguyên văn tới người dùng, và người dùng học được rằng cảnh báo của
# MeoArc nói quá. Đúng tinh thần thang rủi ro: hoàn tác được / người khác đã thấy.
_HAU_QUA = {
    "bulk_action:delete": ("Thư sẽ vào THÙNG RÁC và khôi phục lại được (tool `bulk_action` "
                           "không khôi phục — người dùng lấy lại từ giao diện MeoArc hoặc "
                           "Gmail), nhưng sẽ biến khỏi hộp thư."),
    "send_email": "KHÔNG HOÀN TÁC — thư gửi đi rồi thì người nhận đã thấy, không rút lại được.",
    "forward_email": ("KHÔNG HOÀN TÁC, và nó đưa nội dung của NGƯỜI KHÁC cho người thứ ba — "
                      "soát kỹ địa chỉ nhận trước khi duyệt."),
    "reply_email": "KHÔNG HOÀN TÁC — thư trả lời gửi đi rồi thì người nhận đã thấy.",
}


def _needs_confirm(action: str, preview: dict) -> dict:
    """CONFIRM-GATE (UC010 cho agent ngoài): lần gọi đầu KHÔNG thực thi — trả bản xem
    trước + chỉ dẫn. Agent phải đưa preview cho NGƯỜI DÙNG duyệt rồi gọi lại confirm=true."""
    hau_qua = _HAU_QUA.get(action, "Hành động có rủi ro — chưa thực thi.")
    return {
        "success": False,
        "needs_confirmation": True,
        "action": action,
        "preview": preview,
        "instruction": (f"{hau_qua} CHƯA THỰC THI. Hãy hiển thị 'preview' cho người dùng và "
                        "HỎI XÁC NHẬN. Người dùng đồng ý thì gọi lại tool này với chính các "
                        "tham số đó kèm confirm=true."),
    }


# ══════════════ TOOL HẠT MỊN (đúng tiêu chí thầy — agent ngoài tự suy luận) ══════════════

async def search_emails(query: str = "", limit: int = 10, is_read: bool | None = None,
                        date_from: str | None = None, date_to: str | None = None) -> dict:
    """Tìm email theo từ khoá hoặc cú pháp Gmail (from:, subject:, has:attachment, newer_than:7d...).
    is_read: true=đã đọc, false=chưa đọc, bỏ trống=tất cả. date_from/date_to: ISO 8601 (2026-07-01).
    Trả danh sách tóm tắt {id, sender, subject, snippet, date, is_read} — dùng id cho các tool khác."""
    args: dict = {"query": query, "limit": limit, "is_read": is_read}
    if date_from:
        args["date_from"] = date_from
    if date_to:
        args["date_to"] = date_to
    return await _call("search_emails", args)


async def semantic_search(query: str, limit: int = 5, pool: int = 30) -> dict:
    """Tìm email theo Ý NGHĨA (embedding) — khớp cả khi thư KHÔNG chứa đúng từ khoá.
    Dùng khi chủ đề mơ hồ ('thư về tiền nong', 'liên quan bảo mật'); từ khoá chính xác
    thì dùng search_emails. pool = số thư gần nhất đem so nghĩa."""
    return await _call("semantic_search", {"query": query, "limit": limit, "pool": pool})


async def categorize_emails(limit: int = 20, query: str = "") -> dict:
    # Docstring được LẮP Ở DƯỚI từ `ALL_CATEGORIES` — xem ghi chú ở đó.
    return await _call("categorize_emails", {"limit": limit, "query": query})


# ── DANH SÁCH NHÃN PHẢI SINH RA, KHÔNG CHÉP TAY ──
# Docstring của tool chính là thứ agent NGOÀI đọc để biết app có những nhãn nào. Chép
# tay thì nó trôi: nhãn thứ 8 "Đi lại" đã được thêm vào `labeling.py` mà dòng này vẫn
# liệt kê 7 — tức Claude Desktop được cho một bảng phân loại SAI, và sai ở đúng chỗ
# không ai nhìn thấy vì nó không phải giao diện. Lắp từ nguồn sự thật thì hết trôi.
categorize_emails.__doc__ = (
    "Tự ĐỀ XUẤT nhãn cho các thư gần nhất ("
    + "/".join(c.label for c in ALL_CATEGORIES)
    + ") theo người gửi + nội dung. CHỈ đề xuất — trả {id, label, reason}; muốn ÁP thì "
      "gọi apply_labels với các id + label đó SAU KHI người dùng duyệt."
)


async def get_email(email_id: str) -> dict:
    """Lấy nội dung ĐẦY ĐỦ (thân thư + tên tệp đính kèm) của 1 email theo id (lấy id từ search_emails)."""
    return await _call("get_email", {"email_id": email_id})


async def list_labels() -> dict:
    """Liệt kê tên mọi nhãn trong hộp thư (gọi trước khi gắn/bỏ nhãn để dùng đúng tên)."""
    return await _call("list_labels", {})


async def send_email(to: list[str], subject: str, body: str,
                     cc: list[str] | None = None, bcc: list[str] | None = None,
                     confirm: bool = False) -> dict:
    """GỬI email mới — KHÔNG HOÀN TÁC. Lần đầu gọi với confirm=false (mặc định) sẽ trả
    bản xem trước để bạn hỏi người dùng; được đồng ý mới gọi lại với confirm=true."""
    if not confirm:
        return _needs_confirm("send_email", {
            "to": to, "cc": cc or [], "bcc": bcc or [], "subject": subject,
            "body_preview": body[:300] + ("…" if len(body) > 300 else ""),
        })
    res = await _call("send_email", {"to": to, "subject": subject, "body": body,
                                     "cc": cc or [], "bcc": bcc or []})
    _audit_mcp("send_email", "send_email", [], res, {"to": to, "subject": subject})
    return res


async def reply_email(email_id: str, reply_body: str, reply_all: bool = False,
                      confirm: bool = False) -> dict:
    """TRẢ LỜI 1 email (tự giữ đúng luồng/thread) — KHÔNG HOÀN TÁC, cần confirm=true
    sau khi người dùng đã duyệt nội dung reply_body.
    reply_all=True gửi cho CẢ những người có mặt trong thư gốc (To + Cc), trừ chính mình —
    nói rõ điều đó trong bản xem trước, vì số người nhận là thứ người dùng cần biết TRƯỚC
    khi duyệt."""
    if not confirm:
        return _needs_confirm("reply_email", {
            "email_id": email_id,
            "reply_all": reply_all,
            "pham_vi": "tất cả người trong thư gốc" if reply_all else "chỉ người gửi",
            "reply_preview": reply_body[:300] + ("…" if len(reply_body) > 300 else ""),
        })
    res = await _call("reply_email", {"email_id": email_id, "instructions": reply_body,
                                      "reply_all": reply_all})
    _audit_mcp("reply_email", "reply_email", [email_id], res,
               {"email_id": email_id, "reply_all": reply_all})
    return res


async def apply_labels(email_ids: list[str], labels_to_add: list[str] | None = None,
                       labels_to_remove: list[str] | None = None) -> dict:
    """Thêm/bớt nhãn cho các email (đảo ngược được nên không cần confirm)."""
    res = await _call("apply_labels", {"email_ids": email_ids,
                                       "labels_to_add": labels_to_add or [],
                                       "labels_to_remove": labels_to_remove or []})
    _audit_mcp("apply_label", "apply_labels", email_ids, res,
               {"add": labels_to_add or [], "remove": labels_to_remove or []})
    return res


async def forward_email(email_id: str, to: str, note: str = "", confirm: bool = False) -> dict:
    """CHUYỂN TIẾP một thư sang địa chỉ khác — KHÔNG HOÀN TÁC, cần confirm=true.
    `to` BẮT BUỘC và không được đoán từ thư gốc: chuyển tiếp là đưa nội dung của NGƯỜI
    KHÁC cho người thứ ba, gửi nhầm địa chỉ là làm lộ thư của người không liên quan.
    Lần đầu gọi (confirm=false) trả bản xem trước để hỏi người dùng."""
    if not confirm:
        return _needs_confirm("forward_email", {"email_id": email_id, "to": to, "note": note})
    res = await _call("forward_email", {"email_id": email_id, "to": to, "note": note})
    _audit_mcp("forward_email", "forward_email", [email_id], res, {"to": to})
    return res


async def bulk_action(email_ids: list[str], action: str, label_name: str | None = None,
                      confirm: bool = False) -> dict:
    # Docstring lắp ở dưới từ enum `BulkAction` — xem ghi chú ở đó.
    if action.strip().lower() == "delete" and not confirm:
        return _needs_confirm("bulk_action:delete", {
            "action": "delete", "so_thu": len(email_ids),
            "email_ids_dau": email_ids[:5], "con_lai": max(0, len(email_ids) - 5),
        })
    res = await _call("bulk_action", {"email_ids": email_ids, "action": action,
                                      "label_name": label_name})
    _audit_mcp(f"bulk_{action.strip().lower()}", "bulk_action", email_ids, res,
               {"action": action, "count": len(email_ids), "label_name": label_name})
    return res


# ── DANH SÁCH HÀNH ĐỘNG PHẢI SINH RA, KHÔNG CHÉP TAY ──
# Dòng này ĐÃ trôi một lần: 'restore' thêm vào enum từ lâu mà docstring vẫn liệt kê
# năm hành động cũ, nên agent ngoài không biết là khôi phục được thư. Cùng một lỗi với
# danh sách nhãn ở `categorize_emails`. Lắp từ enum thì hết trôi.
bulk_action.__doc__ = (
    "Thao tác HÀNG LOẠT. action ∈ {"
    + ",".join(f"'{a.value}'" for a in BulkAction)
    + "} (chữ thường). 'delete' = chuyển thùng rác (khôi phục được bằng 'restore'); "
      "'spam'/'not_spam' = đánh dấu / bỏ đánh dấu thư rác. Tối đa 100 thư/lần. "
      "Riêng 'delete' cần confirm=true sau khi người dùng duyệt danh sách."
)


# ══════════════ LỊCH TRÌNH & ĐI LẠI — phần LÀM NÊN MeoArc ══════════════
# Chín tool trên là thao tác hộp thư: agent nào nối vào Gmail cũng làm được. Bốn tool
# dưới mới là thứ MeoArc có mà Gmail không có — đọc CAM KẾT ra khỏi thư, biết ai đang
# chờ, biết ngày nào quá tải.
#
# Trước đây chúng chỉ chạy được TRONG app. Nghĩa là agent ngoài nối vào MeoArc vẫn chỉ
# đọc được thư — đúng thứ nó tự làm được — còn phần đáng giá nhất thì không với tới.
# Mở kênh mà giữ lại phần hay nhất cho riêng mình thì kênh đó chưa hoàn chỉnh.

async def liet_ke_cam_ket(limit: int = 30) -> dict:
    """Trích CAM KẾT từ hộp thư — không phải "sự kiện", mà là việc BẠN đã hứa hoặc
    người khác đang chờ ở bạn. Mỗi cam kết kèm: nội dung, hạn, người đang chờ, ước
    lượng thời lượng, độ tin cậy, và id lá thư sinh ra nó.
    Chỉ nhận khi thư có CẢ động từ cam kết LẪN mốc thời gian — nên thư quảng cáo có
    ngày tháng ("Sale 9/9") bị bỏ qua. Độ tin cậy dưới 0.6 nghĩa là suy ra, nên HỎI
    LẠI người dùng thay vì khẳng định."""
    return await _call("liet_ke_cam_ket", {"limit": limit})


async def ap_luc_lich_trinh(so_ngay: int = 7) -> dict:
    """Ước lượng KHỐI LƯỢNG công việc mỗi ngày trong N ngày tới, tính từ các cam kết.
    Thời lượng được CHIA ĐỀU cho số ngày việc đó trải qua — một việc 6 tiếng hạn thứ
    Sáu là việc của cả thứ Tư và thứ Năm, không phải một chấm ở thứ Sáu.
    Dùng để trả lời "tuần này tôi có quá tải không", "nên bắt đầu việc X ngày nào"."""
    return await _call("ap_luc_lich_trinh", {"so_ngay": so_ngay})


async def de_xuat_di_lai(limit: int = 30) -> dict:
    """Tìm các cam kết CẦN ĐI LẠI (họp/sự kiện ở thành phố khác) và gợi ý chặng + ngày.
    Chỉ ĐỀ XUẤT — không tra vé, không đặt. Có chặng rồi thì gọi tim_chuyen_bay."""
    return await _call("de_xuat_di_lai", {"limit": limit})


async def tim_chuyen_bay(tu: str, den: str, ngay: str, so_ket_qua: int = 5) -> dict:
    """TRA CỨU chuyến bay. `tu`/`den` nhận TÊN THÀNH PHỐ ("Hà Nội", "Đà Nẵng") hoặc mã
    IATA; `ngay` dạng dd/mm/yyyy.
    Mỗi kết quả mang `nguon` + `la_that`: nguồn thật cho hãng/số hiệu/giờ/máy bay/nhà
    ga THẬT nhưng KHÔNG có giá (`co_gia`=false, `gia_vnd`=0) — đừng trình bày số 0 đó
    như một mức giá. `nguon`="mo_phong" nghĩa là SỐ BỊA, phải nói rõ cho người dùng.
    CHỈ TRA CỨU — không giữ chỗ, không đặt, không thanh toán."""
    return await _call("tim_chuyen_bay",
                       {"tu": tu, "den": den, "ngay": ngay, "so_ket_qua": so_ket_qua})


async def tim_khach_san(thanh_pho: str, nhan_phong: str, tra_phong: str,
                        so_ket_qua: int = 5) -> dict:
    """TRA CỨU chỗ ở. Ngày dạng dd/mm/yyyy. Kết quả sắp SAO CAO TRƯỚC.
    `ten_that`=true nghĩa là tên/hạng sao/vị trí là của cơ sở CÓ THẬT, nhưng GIÁ vẫn
    là số mô phỏng — nói đúng phần nào thật, đừng gộp thành "dữ liệu thật".
    CHỈ TRA CỨU — không giữ chỗ, không đặt, không thanh toán."""
    return await _call("tim_khach_san",
                       {"thanh_pho": thanh_pho, "nhan_phong": nhan_phong,
                        "tra_phong": tra_phong, "so_ket_qua": so_ket_qua})


# Đăng ký tool với MCP — giữ hàm gốc ở module-level để test gọi thẳng được.
#
# `tu_choi_ngoai_pham_vi` CỐ Ý KHÔNG mở ra đây: nó dạy agent TRONG app biết ranh giới
# năng lực của chính app. Agent ngoài đã có ranh giới riêng của nó, và một tool "hãy
# từ chối" trong danh sách chỉ làm nó bối rối.
#
# `dat_cho_mo_phong` cũng KHÔNG mở: đó là tool KHÔNG HOÀN TÁC, phải đi qua cổng xác
# nhận + cổng tiền. Cổng đó gắn với phiên người dùng trên web; phơi qua stdio là mở
# đường vòng qua chính lớp bảo vệ đó. Đặt chỗ vẫn phải bấm duyệt trên web.
for _fn in (search_emails, semantic_search, categorize_emails, get_email, list_labels,
            send_email, reply_email, forward_email, apply_labels, bulk_action,
            liet_ke_cam_ket, ap_luc_lich_trinh, de_xuat_di_lai,
            tim_chuyen_bay, tim_khach_san):
    mcp.tool()(_fn)


# ══════════════ MCP PROMPTS — kỹ năng 1-click trên menu Claude Desktop ══════════════
# Cùng "thư viện kỹ năng" tinh thần với agent trong app (skills/library) — nhưng ở đây
# quy trình được GIAO cho agent ngoài tự thực thi bằng tool hạt mịn (đúng agent-native).

@mcp.prompt()
def daily_digest() -> str:
    """Điểm tin hộp thư hôm nay (UC014)."""
    return ("Hãy làm báo cáo điểm tin hộp thư MeoArc: (1) search_emails với query "
            "'newer_than:1d' limit 20; (2) đếm tổng/chưa đọc; (3) nhóm theo người gửi; "
            "(4) nêu 3-5 thư đáng chú ý nhất kèm lý do; (5) đề xuất hành động cho từng thư "
            "đáng chú ý (trả lời/lưu trữ/bỏ qua). Trình bày gọn bằng tiếng Việt.")


@mcp.prompt()
def triage_inbox() -> str:
    """Phân loại hộp thư theo mức ưu tiên (UC015)."""
    return ("Hãy triage hộp thư MeoArc: (1) search_emails is_read=false limit 20; "
            "(2) chia 2 nhóm ƯU TIÊN CAO (cần hành động/deadline/người thật hỏi) và "
            "BÌNH THƯỜNG (bản tin, thông báo máy); (3) với mỗi thư nêu 1 gợi ý xử lý ngắn; "
            "(4) hỏi tôi có muốn đánh dấu đã đọc nhóm bình thường không — nếu có thì dùng "
            "bulk_action mark_read. Tiếng Việt, gọn.")


@mcp.prompt()
def meeting_brief() -> str:
    """Chuẩn bị brief cuộc họp từ email liên quan (UC016)."""
    return ("Hãy chuẩn bị meeting brief từ hộp thư MeoArc: (1) hỏi tôi chủ đề/từ khoá cuộc họp; "
            "(2) search_emails theo từ khoá đó; (3) get_email các thư liên quan nhất; "
            "(4) tổng hợp: điểm chính, action items (ai—việc—hạn), câu hỏi còn mở. Tiếng Việt.")


# ══════════════ RESOURCE — agent ngoài tự biết bối cảnh ══════════════

@mcp.resource("meoarc://whoami")
def whoami() -> str:
    """Đang thao tác trên hộp thư của ai.

    ── CHỖ NÀY TỪNG BỊ SÓT ──
    Khi mở đường HTTP, `_resolve_ctx` đã được sửa để đi theo user_id của thẻ Bearer.
    Nhưng resource này vẫn giữ nguyên lối stdio cũ: "lấy phiên đăng nhập MỚI NHẤT trong
    CSDL", không lọc theo ai. Qua HTTP thì nó trả về email + user_id của NGƯỜI KHÁC —
    người vừa đăng nhập web — cho bất kỳ ai có một thẻ hợp lệ của chính mình.

    Hai hậu quả, và cái thứ hai mới là cái tệ:
    1. Rò rỉ email và user_id nội bộ của người dùng khác.
    2. Các tool thì được phân quyền ĐÚNG (thao tác trên hộp thư của người gọi), nên
       resource này nói với agent một danh tính khác hẳn hộp thư nó đang đụng vào. Agent
       ký tên, xưng danh, hay suy luận "địa chỉ của tôi" đều dựa trên người thứ ba.
       Một câu trả lời sai còn nguy hơn không trả lời.

    Nên nó dùng CHUNG `_uid_tu_http()` với `_resolve_ctx` — một nguồn xác định người dùng
    duy nhất, để lần sau không lệch được nữa.
    """
    uid = _uid_tu_http()
    db = SessionLocal()
    try:
        from app.models.user import User
        if uid is None:
            # stdio: agent chạy cùng máy, giữ nguyên lối cũ.
            s = db.scalars(select(AuthSession).order_by(AuthSession.expires_at.desc())).first()
            uid = s.user_id if s else None
        if uid is None:
            return "Chưa ai đăng nhập web MeoArc."
        u = db.get(User, uid)
        return f"Hộp thư đang thao tác: {u.email if u else '?'} (user_id={uid})."
    finally:
        db.close()


# Chạy server: `uv run python -m app.mcp.server` (stdio — đúng kiểu Claude Desktop/Codex
# kết nối MCP server cục bộ; cấu hình trong _claude_config_READY.json ở gốc repo).
if __name__ == "__main__":
    mcp.run()
