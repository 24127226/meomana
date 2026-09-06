# ╔══════════════════════════════════════════════════════════════════╗
# ║ app/api/app.py — TRÁI TIM của server (Nấc 0)                        ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║ MỤC ĐÍCH: tạo ra "ứng dụng web" và khai báo vài ROUTE đầu tiên.     ║
# ║ AI GỌI: Frontend (hoặc trình duyệt) gửi request HTTP tới đây.       ║
# ║ Ở nấc này chưa có Gmail/đăng nhập — chỉ để bạn THẤY server chạy.    ║
# ╚══════════════════════════════════════════════════════════════════╝

# Nhập lớp FastAPI từ thư viện fastapi. Đây là "bộ khung" lo hết phần
# khó của web (nhận request, parse, trả JSON, sinh tài liệu...).
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware  # cho phép FE gọi sang (xem CORS bên dưới)
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.email_service import list_emails  # logic lấy email (tầng service)

# --- Nấc 3: database (ORM) ---
from fastapi import Depends, HTTPException, status, UploadFile, File, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.db import Base, engine, get_db
from app.core.config import settings  # cờ tính năng (vd mailbox_store_enabled) dùng ở nhiều route
from app.models.user import User  # noqa: F401 — phải import để create_all "thấy" bảng users
from app.models.session import AuthSession  # noqa: F401 — để create_all tạo cả bảng sessions
from app.models.conversation import Conversation  # noqa: F401 — UC011: tạo bảng conversations
from app.models.audit import AuditLog  # noqa: F401 — tạo bảng audit_logs (accountability)
from app.models.notification import Notification  # noqa: F401 — tạo bảng notifications
from app.models.subscription import Subscription  # noqa: F401 — tạo bảng subscriptions (quota token)
from app.models.dat_cho import DonDatCho  # noqa: F401 — Giai đoạn 3: bảng don_dat_cho (chống trùng)
from app.models.session_provider import SessionProvider  # noqa: F401 — tạo bảng session_providers (Gmail/Outlook)
from app.models.email_store import StoredEmail, MailboxSync  # noqa: F401 — tạo bảng emails + mailbox_sync (store-of-record)
from app.models.mcp_token import McpToken  # noqa: F401 — tạo bảng mcp_tokens (thẻ MCP-HTTP)
from app.repo import (user_repo, conversation_repo, audit_repo, notification_repo,
                      subscription_repo, email_store_repo, confirmation_repo,
                      user_preference_repo, mcp_token_repo)
from app.core import plans  # danh mục gói + hạn mức token (một nguồn duy nhất)
from app.core import limits  # NFR-Scalability: trần tài nguyên + số liệu vận hành
from app.core.ngon_ngu import dich, dich_gia_tri
from app.core import maintenance  # dọn dữ liệu cũ định kỳ (retention)
from app.core.breaker import CircuitOpen, llm_breaker, provider_breaker
from app.core import errors  # thu thập lỗi: Sentry khi có DSN, không thì ghi log
from app.core.kv import kv   # kho key-value dùng chung (Redis khi có, không thì in-memory)
import logging
import re

# File này vốn không có `logger` cấp module — mỗi chỗ tự gọi logging.getLogger(...) tại
# chỗ. Nhưng nhánh lỗi của "Làm mới" (đồng bộ nhanh thất bại) lại gọi thẳng `logger`,
# nên nó là NameError NẰM CHỜ: đúng lúc đồng bộ hỏng thì chính khối `except` nổ, biến
# một lỗi phục hồi được thành 500 ở màn hộp thư. Chỉ lộ ra khi có sự cố — tức đúng lúc
# tệ nhất. Khai báo ở đây để nhánh đó chạy đúng ý người viết.
logger = logging.getLogger("app.api")

from app.schemas.user import UserCreate, UserOut  # noqa: E402
from app.schemas.conversation import ConversationSummary, ConversationDetail, UpdateConversationReq

# --- Nấc 4b: đăng nhập ---
from app.core.deps import get_current_user, get_current_session, get_gmail_token, get_provider
from app.services import gmail_service, mail, sync_service
from app.api import auth as auth_routes
from app.api import avatar as avatar_routes
from fastapi import BackgroundTasks  # hàng đợi nhẹ (in-process) cho webhook/sync chạy nền

# --- Nấc 6a: hành động Gmail (ghi) ---
from fastapi import Response
from app.services import gmail_actions
from app.schemas.actions import ReadReq, ImportantReq, IdsReq, ActionResult, LabelReq, ReadOneReq

# --- Nấc 6b: gửi & trả lời thư ---
from app.services import gmail_send
from app.schemas.send import SendReq, ReplyReq, SendResult

# --- Nấc 8: kho tệp đính kèm (giữ bytes để gắn vào mail) ---
from app.services import upload_store

# --- Nấc 10: thực thi sau duyệt (cầu nối agent ↔ service, KHÔNG phải LLM) ---
from app.schemas.agent import ExecutePlanReq, ExecuteResult, AutopilotApplyReq, OkResult

# ── Tạo bảng: Alembic là NGUỒN SỰ THẬT, create_all chỉ còn là lưới an toàn ──
# `create_all` chỉ TẠO BẢNG MỚI, KHÔNG sửa bảng đã có: thêm một cột vào bảng đang
# chạy là nó im lặng bỏ qua (nhóm đã gặp đúng vấn đề này và phải né bằng bảng riêng
# `session_providers`). Nên từ nay MỌI thay đổi cấu trúc đi qua Alembic:
#     uv run alembic revision --autogenerate -m "mo ta thay doi"
#     uv run alembic upgrade head
# Đặt AUTO_CREATE_TABLES=false ở môi trường thật để tắt hẳn lưới an toàn này —
# khi đó database chỉ đổi khi có người chạy di trú, không đổi lén lúc khởi động.
if settings.auto_create_tables:
    Base.metadata.create_all(bind=engine)

# ── NFR-Observability: BẬT hệ thống log có request-id + xoay file (logs/app.log) ──
# Hạ tầng này develop đã viết sẵn ở core/logging.py nhưng CHƯA từng được gọi → giờ nối vào.
# Mỗi request được gắn rid riêng (middleware bên dưới) → mọi dòng log của cùng 1 request
# mang cùng rid, tra lỗi production dễ hơn hẳn.
from app.core.logging import setup_logging, set_request_id
setup_logging()

import time as _time
_STARTED_AT = _time.time()  # mốc khởi động — /health báo uptime

# Tạo đối tượng ứng dụng. title/description/version sẽ HIỆN trên trang
# tài liệu tự sinh tại /docs — nên đặt cho rõ để dễ đọc khi demo.
app = FastAPI(
    title="MeoArc Backend (sandbox)",
    description="Server học việc — nấc 0: làm cho FastAPI chạy được.",
    version="0.1.0",
)

# ── NFR-Speed: nén GZip cho response lớn (danh sách email JSON rất "nặng chữ") ──
# minimum_size=1024: gói nhỏ khỏi nén (nén còn tốn CPU hơn tiết kiệm).
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)


# ── NFR-Observability + Security: middleware gắn request-id, đo thời gian, header an toàn ──
@app.middleware("http")
async def observability_and_security(request: Request, call_next):
    rid = set_request_id()                      # log của request này đều mang rid
    t0 = _time.perf_counter()

    # NFR-Scalability: chặn payload khổng lồ TRƯỚC khi đọc vào RAM. Không chặn thì
    # vài request 500MB đủ làm hết bộ nhớ tiến trình và kéo sập cả server.
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limits.MAX_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={"error": {"code": 413, "message": "Nội dung gửi lên quá lớn."}},
        )

    try:
        response = await call_next(request)
    except CircuitOpen as broken:
        # Dịch vụ ngoài đang sập kéo dài → từ chối NGAY, không bắt người dùng chờ
        # rồi cũng hỏng. Retry-After nói rõ khi nào đáng thử lại.
        limits.metrics.note_rejection("busy")
        limits.metrics.observe((_time.perf_counter() - t0) * 1000, 503)
        logging.getLogger("app.breaker").info("Từ chối vì mạch mở: %s", broken.name)
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": str(int(broken.retry_after) + 1), "X-Request-ID": rid},
            content={"error": {"code": 503, "message": str(broken)}},
        )
    except limits.ProviderBusy as busy:
        # Quá tải CÓ KIỂM SOÁT: hệ thống còn sống, chỉ đang hết suất gọi ra ngoài.
        # Trả 503 + Retry-After để client (và load balancer) biết mà thử lại,
        # thay vì để request treo tới lúc timeout rồi báo lỗi 500 khó hiểu.
        limits.metrics.note_rejection("busy")
        limits.metrics.observe((_time.perf_counter() - t0) * 1000, 503)
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "5", "X-Request-ID": rid},
            content={"error": {"code": 503, "message": str(busy)}},
        )

    elapsed_ms = (_time.perf_counter() - t0) * 1000
    limits.metrics.observe(elapsed_ms, response.status_code)
    # Đo được mới nói chuyện "tốc độ": FE/DevTools đọc 2 header này để soi độ trễ từng call.
    response.headers["X-Request-ID"] = rid
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.0f}"
    # Header bảo mật cơ bản (OWASP): chặn đoán MIME, chặn nhúng iframe (clickjacking),
    # hạn chế rò URL qua referrer. (HSTS chỉ bật khi chạy HTTPS thật — dev là HTTP.)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Request chậm bất thường → cảnh báo kèm rid để lần ra (agent >10s là đáng nhìn).
    if elapsed_ms > 10_000:
        import logging
        logging.getLogger("app.perf").warning(
            "SLOW %s %s took %.0fms", request.method, request.url.path, elapsed_ms)
    return response

# ── CORS — vì sao bắt buộc khi nối Frontend ──────────────────────────
# Trình duyệt có quy tắc "same-origin": một trang ở origin A
# (vd http://localhost:5173 của FE) MẶC ĐỊNH bị chặn gọi sang origin B
# (vd http://localhost:8000 của BE). Server phải KHAI BÁO origin được
# phép thì trình duyệt mới cho. Thiếu đoạn này → FE gọi sẽ lỗi CORS.
app.add_middleware(
    CORSMiddleware,
    # Máy dev lấy mặc định localhost; khi triển khai thật thì khai thêm tên miền FE
    # vào biến CORS_ORIGINS (xem app/core/config.py). Ghi cứng danh sách ở đây đồng
    # nghĩa bản deploy không gọi được API nào.
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── NFR-Reliability: /health — điểm bắt mạch cho monitor/uptime check ────────
# Chuẩn production: hệ thống giám sát (hoặc giám khảo 😄) gọi GET /health là biết ngay
# app sống không + DB nối được không, khỏi bấm mò từng tính năng. DB đứt → 503 "degraded".
@app.get("/health")
def health(db: Session = Depends(get_db)):
    from sqlalchemy import text as _sqltext
    try:
        db.execute(_sqltext("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    body = {
        "status": "ok" if db_ok else "degraded",
        "db": "up" if db_ok else "down",
        "uptime_s": int(_time.time() - _STARTED_AT),
        "version": app.version,
    }
    return body if db_ok else JSONResponse(status_code=503, content=body)


# ── UC012: màn MCP phải NÓI ĐÚNG những gì server MCP thật sự mở ra ───────────
# Màn Cài đặt → MCP trước đây ghi cứng một endpoint không có thật
# (`https://mcp.meoarc.dev/sse`), một token giả, dòng "đã kết nối · 1 client đang hoạt
# động", và bảy tên tool trong đó BỐN cái không tồn tại (`summarize`, `draft_reply`,
# `bulk_manage`, `extract_tasks`). Server thật mở 14 tool + 3 prompt + 1 resource, và
# chạy qua stdio chứ không qua HTTP.
#
# Với một màn hình chỉ để trang trí thì đó là chuyện nhỏ. Nhưng đây đúng là màn được
# mở ra để CHỨNG MINH tích hợp MCP — nên sai ở đây không phải "thiếu sót", nó là một
# lời khẳng định sai về thứ hệ thống làm được. Thà không có màn này còn hơn.
#
# Nay endpoint đọc THẲNG từ `app.mcp.server`, nên danh sách không thể lệch: thêm/bớt
# tool ở đó là màn hình đổi theo.
# ══════════════ MCP QUA HTTP — thẻ ra vào cho agent ở MÁY KHÁC ══════════════
# Gắn thẳng vào app này thay vì mở một tiến trình + cổng riêng: thừa hưởng luôn HTTPS,
# tên miền và cấu hình đã triển khai. Một cổng nữa là một bề mặt nữa phải tự bảo vệ.
_MCP_HTTP_DA_MOUNT = False
_MCP_HTTP_APP = None          # ASGI app con, giữ lại để chạy vòng đời của nó
_MCP_HTTP_STACK = None        # AsyncExitStack đang giữ vòng đời đó


def _gan_mcp_http() -> None:
    """Mount MCP lên /mcp/rpc — CHỈ khi bật cờ, và chỉ khi có TLS."""
    global _MCP_HTTP_DA_MOUNT
    if not settings.mcp_http_enabled:
        return
    # Thẻ Bearer đi qua HTTP trần là gửi chìa khoá dạng chữ thường cho bất kỳ ai trên
    # đường truyền. Thà không mở còn hơn mở một cách vô nghĩa — nên chặn ngay ở đây,
    # không trông chờ người triển khai nhớ đặt HTTPS.
    if not (settings.mcp_http_cho_phep_khong_tls or _sau_tls()):
        logger.warning("MCP-HTTP: BỎ QUA — chưa thấy HTTPS. Đặt MCP_HTTP_CHO_PHEP_KHONG_TLS=true "
                       "nếu đang chạy thử ở localhost.")
        return
    global _MCP_HTTP_APP
    try:
        from app.mcp.server import mcp as _mcp_server
        # path="/" để MCP phục vụ NGAY tại gốc chỗ mount; bỏ nó thì đường thật thành
        # /mcp/rpc/mcp và client nhận 404 mà không hiểu vì sao.
        _MCP_HTTP_APP = _mcp_server.http_app(path="/", transport="http", stateless_http=True)
        app.mount("/mcp/rpc", _MCP_HTTP_APP)
        _MCP_HTTP_DA_MOUNT = True
        logger.info("MCP-HTTP: đã mở tại /mcp/rpc (xác thực bằng thẻ Bearer)")
    except Exception:
        logger.warning("MCP-HTTP: không mount được — giữ nguyên stdio", exc_info=True)


# App con của MCP có vòng đời riêng (quản lý phiên streamable-http) và Starlette KHÔNG
# tự chạy vòng đời của app được mount. Bỏ qua thì mount xong vẫn hỏng ngay lượt gọi hợp
# lệ đầu tiên — "Task group is not initialized".
#
# Cách chính thống là truyền lifespan vào constructor của app cha, nhưng app này đang
# dùng @app.on_event(...) ở nhiều chỗ, mà đặt `lifespan=` thì FastAPI BỎ QUA hết các
# handler đó — sửa một chỗ làm hỏng lặng lẽ mấy chỗ khác. Nên nối vào đúng startup/shutdown.
@app.on_event("startup")
async def _mcp_http_khoi_dong() -> None:
    global _MCP_HTTP_STACK
    if not _MCP_HTTP_DA_MOUNT or _MCP_HTTP_APP is None:
        return
    from contextlib import AsyncExitStack
    try:
        _MCP_HTTP_STACK = AsyncExitStack()
        await _MCP_HTTP_STACK.enter_async_context(_MCP_HTTP_APP.lifespan(_MCP_HTTP_APP))
    except Exception:
        _MCP_HTTP_STACK = None
        logger.warning("MCP-HTTP: không khởi động được vòng đời", exc_info=True)


@app.on_event("shutdown")
async def _mcp_http_dung() -> None:
    global _MCP_HTTP_STACK
    if _MCP_HTTP_STACK is None:
        return
    try:
        await _MCP_HTTP_STACK.aclose()
    except Exception:
        logger.info("MCP-HTTP: lỗi khi đóng vòng đời", exc_info=True)
    finally:
        _MCP_HTTP_STACK = None


def _sau_tls() -> bool:
    """Có dấu hiệu app đang chạy sau HTTPS không (Azure/Nginx đều đặt biến này)."""
    import os as _os
    # Azure App Service dựng sẵn WEBSITE_HOSTNAME và luôn phục vụ qua HTTPS; các nền
    # tảng khác đặt FORWARDED_PROTO/X_FORWARDED_PROTO khi đứng sau proxy TLS.
    if _os.getenv("WEBSITE_HOSTNAME"):
        return True
    return (_os.getenv("FORWARDED_PROTO") or _os.getenv("X_FORWARDED_PROTO") or "") == "https"


class TaoTheReq(BaseModel):
    ten: str = Field("", max_length=80)          # "Claude Desktop máy nhà"
    so_ngay: int = Field(30, ge=1, le=365)


@app.post("/mcp/tokens")
def mcp_tao_the(req: TaoTheReq, session: AuthSession = Depends(get_current_session),
                db: Session = Depends(get_db)):
    """Phát 1 thẻ MCP cho CHÍNH người đang đăng nhập. Thẻ gốc trả về ĐÚNG MỘT LẦN.

    Không có đường nào đọc lại thẻ sau lượt này — DB chỉ giữ bản băm. Mất thì thu hồi
    và tạo cái khác; đó là đánh đổi có chủ ý để một lần lộ CSDL không thành một lần lộ
    mọi hộp thư.
    """
    row, raw = mcp_token_repo.tao(db, session.user_id, req.ten, req.so_ngay)
    _record(db, session.user_id, action="mcp_token_create", tool_name="mcp_tokens",
            ids=[], notify=f"Đã tạo thẻ MCP “{row.ten or row.tien_to}”.", notify_type="warning")
    return {
        "id": row.id, "ten": row.ten, "tien_to": row.tien_to,
        "het_han": row.expires_at.isoformat(),
        "token": raw,
        "luu_y": "Chép ngay — thẻ này không hiện lại lần nào nữa.",
    }


@app.get("/mcp/tokens")
def mcp_liet_ke_the(session: AuthSession = Depends(get_current_session),
                    db: Session = Depends(get_db)):
    """Danh sách thẻ của chính mình. KHÔNG có trường nào chứa thẻ gốc."""
    return {"items": [
        {"id": r.id, "ten": r.ten, "tien_to": r.tien_to,
         "tao_luc": r.created_at.isoformat() if r.created_at else None,
         "het_han": r.expires_at.isoformat() if r.expires_at else None,
         "da_thu_hoi": r.revoked,
         "dung_gan_nhat": r.last_used_at.isoformat() if r.last_used_at else None}
        for r in mcp_token_repo.liet_ke(db, session.user_id)
    ]}


@app.delete("/mcp/tokens/{token_id}")
def mcp_thu_hoi_the(token_id: int, session: AuthSession = Depends(get_current_session),
                    db: Session = Depends(get_db)):
    """Thu hồi NGAY. Thẻ đã thu hồi thì lượt gọi kế tiếp bị từ chối, không chờ hết hạn."""
    ok = mcp_token_repo.thu_hoi(db, session.user_id, token_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không có thẻ đó, hoặc đã thu hồi rồi.")
    _record(db, session.user_id, action="mcp_token_revoke", tool_name="mcp_tokens", ids=[],
            notify="Đã thu hồi một thẻ MCP.", notify_type="info")
    return {"ok": True}


@app.get("/mcp/thong-tin")
def mcp_thong_tin():
    """Khai báo THẬT của MCP server: transport, cách kết nối, tool/prompt đang mở."""
    try:
        from app.mcp import server as _mcp
    except Exception as exc:      # noqa: BLE001 — thiếu gói mcp thì nói thẳng, đừng 500
        return {"san_sang": False, "ly_do": f"Không nạp được MCP server: {exc}"[:200],
                "tools": [], "prompts": [], "resources": []}

    def _ten(x) -> str:
        return getattr(x, "__name__", "") or str(x)

    tools = sorted(_ten(f) for f in (
        _mcp.search_emails, _mcp.semantic_search, _mcp.categorize_emails, _mcp.get_email,
        _mcp.list_labels, _mcp.send_email, _mcp.reply_email, _mcp.apply_labels,
        _mcp.bulk_action, _mcp.liet_ke_cam_ket, _mcp.ap_luc_lich_trinh,
        _mcp.de_xuat_di_lai, _mcp.tim_chuyen_bay, _mcp.tim_khach_san,
    ))
    # Đường HTTP chỉ được coi là ĐANG MỞ khi cờ bật VÀ mount thành công. Báo "có" theo
    # mỗi biến môi trường là kiểu khai báo từng làm màn này ghi ra một URL không tồn tại.
    http_bat = bool(getattr(settings, "mcp_http_enabled", False) and _MCP_HTTP_DA_MOUNT)
    return {
        "san_sang": True,
        # stdio LUÔN có; HTTP là tuỳ chọn phải bật tay. Transport từ xa mà không xác thực
        # thì bất kỳ ai có đường dẫn cũng đọc và gửi được thư — nên đường HTTP bắt buộc
        # mang thẻ Bearer, và màn hình phải nói đúng nó đang ở trạng thái nào.
        "transport": "stdio+http" if http_bat else "stdio",
        "lenh_chay": "uv run python -m app.mcp.server",
        "cau_hinh_mau": "_claude_config_READY.json (ở gốc repo)",
        "http": {
            "dang_mo": http_bat,
            "duong_dan": "/mcp/rpc" if http_bat else None,
            "xac_thuc": "Bearer — thẻ tạo ở POST /mcp/tokens, băm khi lưu, có hạn, thu hồi được",
            "vi_sao_tat": None if http_bat else (
                "Cố ý tắt mặc định. Bật bằng MCP_HTTP_ENABLED=true, và chỉ chạy sau HTTPS."
            ),
        },
        "tools": tools,
        "prompts": ["daily_digest", "triage_inbox", "meeting_brief"],
        "resources": ["meoarc://whoami"],
        # Hai tool CỐ Ý không mở — nói ra để người xem biết đây là lựa chọn, không phải sót.
        "khong_mo": {
            "dat_cho_mo_phong": "không hoàn tác + liên quan tiền → phải bấm duyệt trên web",
            "tu_choi_ngoai_pham_vi": "chỉ có nghĩa với agent trong app",
        },
    }


# ── NFR-Scalability: /metrics — nhìn được hệ thống đang thở thế nào ──────────
# Không đo thì không biết lúc nào sắp quá tải, và khi sập cũng không biết vì sao.
# Ba con số đáng nhìn nhất: độ trễ p95 (người dùng CẢM nhận được), số suất gọi ra
# ngoài còn trống (gần 0 = đang nghẽn), và số kết nối DB đang mượn.
@app.get("/metrics")
def metrics():
    from app.core.db import engine
    snap = limits.metrics.snapshot()
    pool = getattr(engine, "pool", None)
    try:
        snap["db_pool"] = {
            "size": pool.size(), "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception:
        snap["db_pool"] = "n/a"
    snap["kv_backend"] = kv.backend_name
    snap["thread_pool"] = _thread_pool_size()
    # Bậc LLM nào đang nghỉ vì hết hạn mức. Ngày trình bày, đây là con số đáng nhìn
    # nhất mà trước giờ chỉ đoán được bằng cách hỏi thử — tức là tốn đúng cái đang đo.
    # Chỉ có tên model + số thứ tự khoá, KHÔNG có khoá (xem `_nhan_bac`).
    try:
        from app.core.llm import loi_llm_gan_nhat, trang_thai_khoa
        snap["llm_dang_nghi"] = trang_thai_khoa()
        # NGUYÊN VĂN lỗi gần nhất (đã che khoá). Người dùng chỉ thấy câu tiếng Việt đã
        # dịch sẵn, nên khi dịch SAI bệnh thì không ai có đường nào lần ra. Đây là chỗ
        # nói thật: quota hay 503 hay tên model sai.
        snap["llm_loi_gan_nhat"] = loi_llm_gan_nhat()
        # HÌNH DẠNG CHUỖI — đọc thẳng từ cấu hình, không dựng client nên rất rẻ.
        #
        # Trước đó chỉ nhìn thấy được chuỗi KHI ĐÃ CÓ LỖI (qua nhãn bậc trong
        # `llm_loi_gan_nhat`). Nghĩa là muốn kiểm "Azure đã nạp đủ khoá chưa" thì phải
        # đợi hỏng — mà lúc đang cần kiểm nhất chính là lúc VỪA sửa xong và chưa hỏng.
        # Đây là số khoá app THẬT SỰ đọc được, nên nó bắt được cả lỗi dán thiếu dấu phẩy.
        _model = [settings.model_name] + [
            t.strip() for t in (settings.model_fallbacks or "").split(",") if t.strip()
        ]
        _model = list(dict.fromkeys(_model))
        _so_khoa = len(settings.danh_sach_khoa_ai)
        snap["llm_cau_hinh"] = {
            "so_khoa": _so_khoa,
            "model": _model,
            "so_bac": len(_model) * max(1, _so_khoa),
            # Hạn mức free Gemini = 20 lượt/ngày cho mỗi PROJECT mỗi MODEL (đo được
            # 02/09/2026, quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier).
            # Con số dưới CHỈ ĐÚNG khi mỗi khoá nằm ở một project RIÊNG — nhiều khoá
            # chung project thì chúng chia nhau một hạn mức, và không có cách nào biết
            # từ phía máy chủ. Xem tên project ở https://aistudio.google.com/apikey
            "uoc_luot_moi_ngay_NEU_moi_khoa_mot_project": len(_model) * max(1, _so_khoa) * 20,
        }
    except Exception:
        snap["llm_dang_nghi"] = "n/a"
    snap["workers"] = settings.web_concurrency
    # Trạng thái ngắt mạch: 'mo' nghĩa là dịch vụ ngoài đang sập và ta đang tạm ngừng gọi.
    snap["ngat_mach"] = {
        "nha_cung_cap_thu": provider_breaker.snapshot(),
        "mo_hinh_ai": llm_breaker.snapshot(),
    }
    # Số dòng các bảng nằm ở /admin/data-size, KHÔNG gộp vào đây.
    # /metrics bị hệ thống giám sát gọi liên tục nên phải nhẹ và không chạm database;
    # gộp truy vấn đếm vào đây từng làm chính endpoint này treo cứng (đo được).
    return snap


@app.get("/admin/data-size")
def data_size(db: Session = Depends(get_db),
              session: AuthSession = Depends(get_current_session)):
    """Số dòng các bảng chỉ-thêm — nhìn được dữ liệu có đang phình không.

    Tách khỏi /metrics vì có chạm database: /metrics phải nhẹ để giám sát gọi
    liên tục, còn cái này chỉ xem khi cần.
    """
    return {"table_rows": maintenance.table_sizes(db)}


@app.get("/admin/kiem-khoa")
async def kiem_khoa(session: AuthSession = Depends(get_current_session)):
    """Từng khoá có SỐNG không, và có THẤY được các model đã cấu hình không.

    ── VÌ SAO DÙNG ListModels ──
    Đây là lời gọi SIÊU DỮ LIỆU, không tiêu hạn mức sinh nội dung. Nên hỏi được ngay
    cả khi mọi khoá đã cạn — đúng lúc cần câu trả lời nhất. Thử bằng một câu chat thật
    thì vừa tốn lượt vừa không phân biệt được "khoá hỏng" với "hết hạn mức".

    Trả lời hai câu hỏi mà nhìn thông báo lỗi không tài nào biết được:
      • Khoá có hợp lệ không, hay đã bị thu hồi / gõ thiếu ký tự khi dán vào Azure.
      • Model trong MODEL_NAME / MODEL_FALLBACKS có THẬT SỰ TỒN TẠI với khoá đó không.
        Google từng gỡ `gemini-2.5-flash` giữa ngày (xem tests/test_llm_du_phong.py).
        Tên model chết thì bậc đó chỉ là chỗ trống — cấu hình trông như có dự phòng mà
        thực tế không có, và không có triệu chứng nào nhìn ra được từ ngoài.

    KHÔNG BAO GIỜ trả về khoá, chỉ số thứ tự. Cần đăng nhập mới gọi được.
    """
    import asyncio

    import httpx

    goc = (settings.ai_base_url or "https://generativelanguage.googleapis.com").rstrip("/")
    dau = {}
    if settings.ai_base_url and settings.ai_proxy_secret:
        dau["x-meoarc-proxy"] = settings.ai_proxy_secret

    can_co = [settings.model_name] + [
        t.strip() for t in (settings.model_fallbacks or "").split(",") if t.strip()
    ]
    can_co = list(dict.fromkeys(can_co))

    async def _thu(i: int, khoa: str) -> dict:
        ra: dict = {"khoa": f"#{i}"}
        try:
            async with httpx.AsyncClient(timeout=20) as cl:
                # Khoá đi trong HEADER chứ không phải query string: chuỗi truy vấn bị
                # ghi vào log của mọi tầng trung gian, header thì không.
                r = await cl.get(f"{goc}/v1beta/models",
                                 headers={**dau, "x-goog-api-key": khoa})
            if r.status_code != 200:
                ra["ok"] = False
                ra["loi"] = f"HTTP {r.status_code}: {r.text[:200]}"
                return ra
            # CHỈ model sinh nội dung được. Danh sách thô còn có model nhúng
            # (embedding) và TTS — liệt kê hết thì người đọc phải tự lọc, rồi rất dễ
            # đặt MODEL_FALLBACKS bằng một model không chat được.
            co = {
                (m.get("name") or "").removeprefix("models/")
                for m in (r.json().get("models") or [])
                if "generateContent" in (m.get("supportedGenerationMethods") or [])
            }
            ra["ok"] = True
            ra["so_model"] = len(co)
            ra["model_thieu"] = [t for t in can_co if t not in co]
            # Tên model DÙNG ĐƯỢC, không chỉ số đếm. Biết "thiếu 1 model" mà không biết
            # thay bằng gì thì vẫn phải đi tra Google rồi đoán — đúng cái vòng lặp mà
            # bảng này sinh ra để cắt. Chỉ lấy dòng Gemini cho gọn.
            ra["model_dung_duoc"] = sorted(t for t in co if t.startswith("gemini"))
        except Exception as exc:  # noqa: BLE001 — một khoá hỏng không được làm chết cả bảng
            ra["ok"] = False
            ra["loi"] = str(exc)[:200]
        return ra

    ds = settings.danh_sach_khoa_ai
    if not ds:
        return {"so_khoa": 0, "ghi_chu": "Chưa cấu hình AI_API_KEY."}

    ket = await asyncio.gather(*(_thu(i, k) for i, k in enumerate(ds, start=1)))
    thieu = sorted({t for r in ket for t in r.get("model_thieu", [])})
    return {
        "so_khoa": len(ds),
        "model_dang_cau_hinh": can_co,
        "khoa_hong": [r["khoa"] for r in ket if not r.get("ok")],
        # Model KHÔNG khoá nào thấy = tên model sai hoặc đã bị gỡ. Đây là thứ đáng xem
        # trước tiên: nó biến một nửa chuỗi dự phòng thành chỗ trống mà không báo gì.
        "model_KHONG_KHOA_NAO_THAY": [
            t for t in thieu
            if all(t in r.get("model_thieu", []) for r in ket if r.get("ok"))
        ],
        "chi_tiet": ket,
    }


def _table_rows_once() -> dict:
    from app.core.db import SessionLocal
    db = SessionLocal()
    try:
        return maintenance.table_sizes(db)
    finally:
        db.close()


# Số luồng thực tế đã áp dụng được, GHI LẠI NGAY LÚC KHỞI ĐỘNG.
#
# Vì sao không đọc trực tiếp trong /metrics: bộ giới hạn luồng của anyio chỉ đọc
# được từ trong vòng lặp bất đồng bộ. Từng làm /metrics thành `async def` để đọc
# cho được, nhưng route async ở đây TREO CỨNG (đo được: /health `def` trả 200
# bình thường, /metrics `async` không bao giờ trả). Ghi lại lúc khởi động vừa
# đúng vừa tránh hẳn vấn đề đó.
_thread_pool_applied: int | str = "chua-ap-dung"


def _thread_pool_size() -> int | str:
    """Số luồng đang cấp cho các route đồng bộ (route `def` chạy trong pool này)."""
    return _thread_pool_applied


@app.on_event("startup")
async def _tune_runtime() -> None:
    """Nới số luồng cho các route đồng bộ.

    FastAPI chạy route `def` trong một pool mặc định 40 luồng. Route của mình chờ
    I/O rất lâu (Gmail ~2.5s, mô hình còn lâu hơn) chứ không tốn CPU, nên 40 luồng
    là nghẽn quá sớm: người thứ 41 phải xếp hàng dù server đang rảnh. Nới rộng để
    chịu được nhiều người chờ I/O cùng lúc — trần thật sự nằm ở semaphore gọi ra
    ngoài, chỗ đó mới là tài nguyên khan hiếm.
    """
    errors.setup_error_tracking()
    global _thread_pool_applied
    try:
        import anyio.to_thread
        limiter = anyio.to_thread.current_default_thread_limiter()
        limiter.total_tokens = settings.web_thread_pool
        _thread_pool_applied = limiter.total_tokens  # đọc lại để chắc đã ăn
        logging.getLogger("app.limits").info(
            "Thread pool = %s · provider slots = %s · llm slots = %s · KV = %s",
            settings.web_thread_pool, settings.max_provider_concurrency,
            settings.max_llm_concurrency, kv.backend_name,
        )
    except Exception as exc:  # noqa: BLE001 — chỉ là tinh chỉnh, hỏng thì chạy mặc định
        logging.getLogger("app.limits").warning("Không nới được thread pool: %s", exc)


_maintenance_task = None  # tham chiếu tới vòng dọn nền, để lúc tắt còn huỷ được


@app.on_event("startup")
async def _start_maintenance_loop() -> None:
    """Khởi động vòng dọn dữ liệu cũ chạy nền.

    Ba bảng sessions / audit_logs / notifications chỉ thêm mà không bao giờ bớt;
    chạy vài tháng với vài nghìn người là index phình và mọi truy vấn chậm dần.

    Chạy NHIỀU WORKER thì cả bốn tiến trình đều muốn dọn cùng lúc → dùng khoá trên
    KV để mỗi chu kỳ chỉ một tiến trình làm thật. Đặt MAINTENANCE_INTERVAL_MIN=0
    để tắt (ví dụ khi muốn dùng cron bên ngoài thay thế).
    """
    import asyncio

    every_min = settings.maintenance_interval_min
    if every_min <= 0:
        logging.getLogger("app.maintenance").info("Dọn dữ liệu tự động: TẮT")
        return

    async def loop() -> None:
        await asyncio.sleep(60)  # để app khởi động xong đã, đừng tranh việc lúc mở máy
        while True:
            try:
                if maintenance.try_acquire_lock("maintenance", every_min * 60):
                    # chạy trong luồng riêng: đây là việc DB đồng bộ, không được chẹn event loop
                    await asyncio.to_thread(_run_maintenance_once)
            except Exception as exc:  # noqa: BLE001 — dọn hỏng thì thôi, app vẫn phải sống
                logging.getLogger("app.maintenance").warning("Lượt dọn lỗi: %s", exc)
            await asyncio.sleep(every_min * 60)

    # Giữ tham chiếu để lúc tắt máy còn HUỶ được. Không giữ thì: (1) Python có thể
    # thu gom task giữa chừng, (2) quan trọng hơn — lúc tắt, vòng lặp vô hạn này
    # vẫn chạy và giữ tiến trình lại, khiến mỗi lần triển khai đều bị treo.
    global _maintenance_task
    _maintenance_task = asyncio.create_task(loop())
    logging.getLogger("app.maintenance").info(
        "Dọn dữ liệu mỗi %s phút · giữ nhật ký %s ngày · thông báo đã đọc %s ngày",
        every_min, settings.audit_retention_days, settings.notification_retention_days,
    )


def _run_maintenance_once() -> dict:
    """Một lượt dọn với session DB riêng (không dùng chung session của request)."""
    from app.core.db import SessionLocal
    db = SessionLocal()
    try:
        return maintenance.run_maintenance(db)
    finally:
        db.close()


@app.on_event("shutdown")
async def _tat_may_em() -> None:
    """Đóng tài nguyên gọn gàng khi tắt.

    Mỗi lần triển khai bản mới là một lần tắt máy. Không đóng pool kết nối thì
    Postgres còn giữ những kết nối "ma" cho tới lúc hết giờ — triển khai vài lần
    liên tiếp là cạn slot kết nối và bản mới không nối được vào database.

    (Uvicorn đã tự chờ các request đang chạy xong trước khi gọi tới đây, nên
    không cần tự đếm request dở dang.)
    """
    import asyncio

    log = logging.getLogger("app.shutdown")

    # 1) Dừng vòng dọn dữ liệu. Bỏ qua bước này thì vòng lặp vô hạn còn chạy và
    #    giữ tiến trình lại — mỗi lần triển khai bản mới sẽ treo ở khâu tắt.
    global _maintenance_task
    if _maintenance_task is not None:
        _maintenance_task.cancel()
        try:
            await _maintenance_task
        except (asyncio.CancelledError, Exception):  # noqa: B014 — tắt máy, nuốt mọi lỗi
            pass
        _maintenance_task = None
        log.info("Đã dừng vòng dọn dữ liệu")

    # 2) Trả kết nối database. Không trả thì Postgres còn giữ kết nối "ma" tới lúc
    #    hết giờ — triển khai vài lần liên tiếp là cạn slot và bản mới không nối được.
    try:
        from app.core.db import engine
        engine.dispose()
        log.info("Đã đóng pool kết nối database")
    except Exception as exc:  # noqa: BLE001 — tắt máy thì không được ném lỗi ra
        log.warning("Không đóng được pool: %s", exc)


@app.post("/admin/maintenance")
def trigger_maintenance(session: AuthSession = Depends(get_current_session)):
    """Chạy dọn ngay, không chờ tới chu kỳ — tiện khi trình bày và khi cần dọn gấp."""
    return {"purged": _run_maintenance_once()}


# ── Nấc 9 (#2): CHUẨN HOÁ định dạng lỗi ──────────────────────────────
# Hợp đồng (docs/02-API-CONTRACT) quy ước MỌI lỗi trả về dạng:
#   { "error": { "code": "...", "message": "...", "details": {} } }
# FastAPI mặc định trả { "detail": ... } → FE đọc `error.message` không thấy. Hai handler
# dưới đổi mọi lỗi sang đúng khuôn để FE hiển thị thông báo thật (vd "Token thiếu quyền…").

# Mã chữ theo HTTP status (để FE/log phân loại dễ hơn số trần).
_ERR_CODE = {
    400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
    409: "CONFLICT", 422: "VALIDATION_ERROR", 500: "INTERNAL_ERROR",
}


@app.exception_handler(StarletteHTTPException)
def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Mọi HTTPException (401/403/404...) → khuôn { error: { code, message, details } }."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {
            "code": _ERR_CODE.get(exc.status_code, "ERROR"),
            "message": exc.detail,
            "details": {},
        }},
    )


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Lỗi dữ liệu vào sai/thiếu (422) → cùng khuôn, kèm chi tiết field nào sai."""
    return JSONResponse(
        status_code=422,
        content={"error": {
            "code": "VALIDATION_ERROR",
            "message": "Dữ liệu gửi lên không hợp lệ.",
            "details": {"errors": jsonable_encoder(exc.errors())},
        }},
    )


# @app.get("/") là một DECORATOR. Đọc là:
#   "Khi có request GET tới đường dẫn '/', hãy chạy hàm ngay bên dưới."
# GET = 'lấy/đọc dữ liệu' (một trong các 'động từ' HTTP: GET/POST/PUT/DELETE).
@app.get("/")
async def root():
    # `async def` = hàm BẤT ĐỒNG BỘ. Nhờ vậy server có thể phục vụ
    # nhiều người cùng lúc mà không bị "kẹt" chờ từng việc xong.
    #
    # Trả về một dict Python bình thường. FastAPI TỰ ĐỘNG đổi nó thành
    # JSON cho trình duyệt — bạn không phải tự viết code chuyển đổi.
    return {"message": "MeoArc backend đang chạy 🎉"}


# (Route /health cũ đã GỘP vào bản NFR phía trên — thêm kiểm tra DB + uptime/version.)


# ── /emails — list theo thư mục + LỌC + TÌM + PHÂN TRANG (UC003/005) ──
# `token = Depends(get_gmail_token)` → tự lấy access_token CÒN HẠN (làm mới nếu cần, Nấc 9).
def _gom_theo_luong(items: list) -> list:
    """Gộp các thư CÙNG MỘT LUỒNG thành một dòng, như Gmail vẫn làm.

    Gmail hiển thị một cuộc trao đổi năm lượt thành MỘT dòng. MeoArc trước đây trả
    về từng thư riêng, nên cùng cuộc đó hiện thành NĂM thẻ — hộp thư trông đầy gấp
    mấy lần thật, và người dùng phải tự nhận ra "à, năm cái này là một chuyện".

    Giữ thư MỚI NHẤT làm đại diện (danh sách từ Gmail đã sắp mới→cũ, nên thư đầu
    tiên gặp trong mỗi luồng chính là thư mới nhất) và đếm số thư còn lại.

    GIỚI HẠN ĐÃ BIẾT, nói thẳng: gom trong PHẠM VI MỘT TRANG. Một luồng có thư nằm
    vắt qua hai trang thì vẫn xuất hiện ở cả hai. Muốn triệt để phải chuyển sang
    Gmail threads.list — đổi cả đường phân trang, nên để lại chứ không làm nửa vời
    ở đây. Trong thực tế thư cùng luồng gần nhau về thời gian nên hiếm khi bị tách.
    """
    ra: list = []
    vi_tri: dict[str, int] = {}
    for e in items:
        tid = getattr(e, "threadId", None)
        if not tid:
            ra.append(e)
            continue
        if tid in vi_tri:
            dai_dien = ra[vi_tri[tid]]
            dai_dien.threadCount = (dai_dien.threadCount or 1) + 1
            # Cả luồng chỉ cần MỘT thư chưa đọc là cả dòng phải hiện chưa đọc —
            # đúng cách Gmail làm, và đúng cái người dùng cần biết.
            if getattr(e, "unread", False):
                dai_dien.unread = True
            continue
        vi_tri[tid] = len(ra)
        ra.append(e)
    return ra


@app.get("/emails")
def get_emails(
    folder: str = "inbox",
    # NFR-Scalability: chặn TỪ CỬA. `limit` không giới hạn thì một request
    # ?limit=5000 sẽ bắn 5000 lệnh gọi Gmail — đủ để một người làm nghẽn cả hệ thống
    # và đốt sạch hạn ngạch chung. `q` dài vô tận cũng làm truy vấn DB phình.
    q: str | None = Query(None, max_length=limits.MAX_QUERY_LEN),
    unread: bool | None = None,      # bộ lọc nhanh: chỉ thư chưa đọc
    starred: bool | None = None,     # chỉ thư gắn sao
    attachment: bool | None = None,  # chỉ thư có đính kèm
    category: str | None = None,     # màu chip của FE — Gmail KHÔNG có khái niệm này → bỏ qua ở server
    cursor: str | None = Query(None, max_length=512),  # token trang KẾ
    limit: int = Query(30, ge=1, le=limits.MAX_PAGE_SIZE),
    fresh: bool = False,             # nút "Làm mới": bỏ qua cache 60s, ép lấy bản mới nhất
    token: str = Depends(get_gmail_token),
    provider: str = Depends(get_provider),  # 'google' | 'microsoft' → định tuyến Gmail/Outlook
    session: AuthSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    # Trần lượt đọc theo người: bảo vệ hạn ngạch nhà cung cấp khỏi tab kẹt vòng lặp.
    if limits.rate_limited("read", session.user_id, settings.read_rate_limit_per_min):
        limits.metrics.note_rejection("rate")
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Bạn đang tải thư quá nhanh. Chờ một chút rồi thử lại nhé.",
            headers={"Retry-After": "30"},
        )
    # STORE-OF-RECORD: bật cờ + DB đã có thư của user ⇒ phục vụ TỪ DB, KHÔNG gọi Gmail
    # (chống rate-limit — yêu cầu nhóm). DB còn "lạnh" (chưa sync) ⇒ lùi về live như cũ.
    if settings.mailbox_store_enabled and email_store_repo.has_any(db, session.user_id, provider):
        # ── NÚT "LÀM MỚI" PHẢI THẬT SỰ LÀM MỚI ──
        # Trước đây nhánh này BỎ QUA HẲN cờ `fresh`: bấm làm mới thì server vẫn trả
        # đúng các dòng DB cũ, nên thư vừa tới không bao giờ xuất hiện — và vì dữ
        # liệu không đổi nên lớp thông báo cũng chẳng có gì để báo. Đó là nguyên
        # nhân gốc của "bấm refresh mà không thấy thông báo nào", nằm ở backend
        # chứ không phải ở giao diện.
        #
        # Đồng bộ TĂNG DẦN chứ không tải lại cả hộp thư: Gmail history.list hỏi
        # "có gì đổi kể từ mốc X" — không đổi gì thì đúng MỘT lượt gọi API, đổi
        # thì chỉ lấy phần đổi. Rẻ hơn hẳn 31 lượt của một lần liệt kê lại.
        #
        # Lỗi đồng bộ KHÔNG được làm hỏng việc đọc thư: vẫn trả bản DB đang có.
        # Thà hiện thư hơi cũ còn hơn hiện một màn lỗi.
        if fresh:
            try:
                sync_service.incremental_sync(db, session.user_id, provider, token)
            except Exception:
                logger.info("Đồng bộ nhanh thất bại — vẫn phục vụ từ DB", exc_info=True)
                db.rollback()

        items, next_cursor = email_store_repo.get_page(
            db, session.user_id, provider, folder=folder, q=q, unread=unread,
            starred=starred, attachment=attachment, limit=limit, cursor=cursor,
        )
        return {"items": _gom_theo_luong(items), "nextCursor": next_cursor,
                "criteria": [], "source": "db"}

    items, next_cursor = mail.list_messages(
        provider, token, folder=folder, q=q, unread=unread, starred=starred,
        attachment=attachment, page_token=cursor, max_results=limit, bypass_cache=fresh,
    )
    return {"items": _gom_theo_luong(items), "nextCursor": next_cursor, "criteria": []}


# ── Nấc 5b: xem CHI TIẾT 1 thư (UC004) — thân thư đầy đủ + đính kèm ──
@app.get("/emails/{email_id}")
def get_email(email_id: str, token: str = Depends(get_gmail_token),
              provider: str = Depends(get_provider),
              session: AuthSession = Depends(get_current_session),
              db: Session = Depends(get_db)):
    # Chi tiết LUÔN lấy LIVE (có HTML gốc + mới nhất; 1 call/thư, cache 60s). Store phục vụ LIST.
    # Lỗi live (offline / thư đã xoá) → lùi về bản DB nếu có.
    try:
        live = mail.get_message(provider, token, email_id)
        if settings.mailbox_store_enabled:
            try:
                email_store_repo.upsert(db, session.user_id, provider, live,
                                        folder=live.folder or "inbox", full=True)
            except Exception:
                db.rollback()
        return live
    except Exception:
        if settings.mailbox_store_enabled:
            cached = email_store_repo.get_one(db, session.user_id, provider, email_id)
            if cached is not None:
                return cached
        raise


@app.get("/emails/{email_id}/thread")
def get_thread(email_id: str, token: str = Depends(get_gmail_token),
               provider: str = Depends(get_provider),
               session: AuthSession = Depends(get_current_session),
               db: Session = Depends(get_db)):
    """MỌI thư trong luồng của thư này, sắp CŨ → MỚI.

    Danh sách đã gộp một cuộc trao đổi năm lượt thành MỘT dòng (đúng như Gmail). Nhưng
    mở dòng đó ra thì trước đây chỉ thấy thư mới nhất — bốn lượt kia không có chỗ nào để
    xem. Gộp mà không mở ra được thì tệ hơn không gộp: người dùng còn không biết mình
    đang bị giấu thứ gì.

    Nhận vào id của MỘT thư (đúng thứ giao diện đang cầm) rồi tự suy ra luồng của nó,
    để phía giao diện không phải biết `threadId` có tồn tại hay không.
    """
    goc = mail.get_message(provider, token, email_id)
    tid = getattr(goc, "threadId", None)
    if not tid:
        return {"items": [goc]}     # thư lẻ: chính nó là cả luồng
    try:
        ds = mail.get_thread(provider, token, tid)
    except Exception:
        logger.info("Không lấy được luồng %s — trả về thư lẻ", tid, exc_info=True)
        return {"items": [goc]}     # hỏng khâu luồng thì vẫn phải đọc được thư đang mở
    return {"items": ds or [goc]}


@app.post("/emails/{email_id}/summarize")
def summarize_email(email_id: str, token: str = Depends(get_gmail_token),
                    provider: str = Depends(get_provider)):
    """UC008 — Tóm tắt 1 email bằng LLM → trả list gạch đầu dòng cho thẻ 'Tóm tắt · AI' ở
    màn chi tiết. LLM chưa cấu hình / thư rỗng / lỗi → lùi về TRÍCH đoạn đầu (fallback an toàn)."""
    import re as _re
    email = mail.get_message(provider, token, email_id)
    body = "\n".join(email.body or []).strip() or email.preview

    def _extract() -> list[str]:
        pts = [p.strip() for p in (email.body or []) if len(p.strip()) > 20][:3]
        return pts or [email.preview or "(thư rỗng)"]

    if not settings.agent_enabled or not body:
        return {"points": _extract(), "source": "extract"}
    try:
        from app.core.llm import create_llm
        from app.agent.nodes.agent_node import coerce_text
        prompt = (
            "Tóm tắt email dưới đây thành 2–4 gạch đầu dòng NGẮN GỌN bằng tiếng Việt, "
            "mỗi dòng 1 ý chính. CHỈ trả các gạch đầu dòng, không mở đầu/kết luận.\n\n"
            f"Tiêu đề: {email.subject}\nNội dung:\n{body[:4000]}"
        )
        text = coerce_text(getattr(create_llm().invoke(prompt), "content", "")) or ""
        pts = [_re.sub(r"^[\-\*•\d\.\)\s]+", "", ln).strip() for ln in text.splitlines()]
        pts = [p for p in pts if p][:5]
        return {"points": pts or _extract(), "source": "llm"}
    except Exception:
        return {"points": _extract(), "source": "extract"}


# ── Nấc 6a: HÀNH ĐỘNG Gmail (UC006) — đánh dấu đọc · sao · lưu trữ · xoá ──
# Hàm phụ dùng chung cho các endpoint ghi (viết 1 lần, tránh lặp code):

def _guard(action):
    """Chạy 1 lệnh gọi Gmail và DỊCH lỗi thiếu quyền (403) thành thông báo dễ hiểu.
    VÌ SAO: token cũ có thể thiếu quyền ghi/gửi → service ném GmailPermissionError;
    ở đây đổi thành 403 kèm hướng dẫn 'đăng nhập lại' thay vì lỗi 500 khó hiểu.
    Trả NGUYÊN giá trị của action (số thư, hay dict thư đã gửi) để nơi gọi tự xử."""
    try:
        return action()
    except gmail_actions.GmailPermissionError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Token thiếu quyền. Hãy ĐĂNG NHẬP LẠI để cấp quyền quản lý & gửi Gmail.",
        )


def _write(action) -> ActionResult:
    """Riêng cho 4 hành động nhãn: chạy qua _guard rồi gói số thư vào ActionResult."""
    return ActionResult(affected=_guard(action))


def _record(
    db: Session,
    user_id: int,
    *,
    action: str,
    ids: list[str] | None = None,
    tool_name: str = "",
    actor_type: str = "user",
    status: str = "success",
    details: dict | None = None,
    conversation_id: str | None = None,
    notify: str | None = None,
    notify_type: str = "info",
) -> None:
    """Ghi 1 dòng AuditLog (LUÔN) + sinh 1 Notification (nếu có `notify`). Gọi SAU khi
    hành động Gmail đã thành công. Nuốt mọi lỗi phụ trợ: audit/notify hỏng KHÔNG được
    làm sập response của hành động chính (accountability là 'thêm', không phải 'chặn')."""
    try:
        audit_repo.log(
            db, user_id=user_id, action=action, tool_name=tool_name, actor_type=actor_type,
            affected_email_ids=ids or [], status=status, details=details or {},
            conversation_id=conversation_id,
        )
        if notify:
            notification_repo.create(db, user_id=user_id, message=notify, type=notify_type)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def _turn_tokens(messages: list) -> int:
    """Ước lượng token đã tiêu của LƯỢT hiện tại (từ HumanMessage cuối → tránh cộng dồn lượt cũ).
    Ưu tiên usage_metadata model báo (Gemini/Groq đều có); thiếu thì ước ~4 ký tự/token."""
    last_human = max((i for i, m in enumerate(messages)
                      if getattr(m, "type", None) == "human"), default=0)
    turn = messages[last_human:]
    total, have_meta = 0, False
    for m in turn:
        if getattr(m, "type", None) != "ai":
            continue
        um = getattr(m, "usage_metadata", None)
        if isinstance(um, dict) and um.get("total_tokens"):
            total += int(um["total_tokens"])
            have_meta = True
    if have_meta:
        return total
    from app.agent.nodes.agent_node import coerce_text
    chars = sum(len(coerce_text(getattr(m, "content", "")) or "") for m in turn)
    return max(1, chars // 4)


def _wt(fn) -> None:
    """WRITE-THROUGH: cập nhật store `emails` sau khi hành động đã chạy thật trên Gmail/Graph.
    Chỉ khi bật cờ store; nuốt lỗi để KHÔNG bao giờ phá hành động chính (best-effort)."""
    if not settings.mailbox_store_enabled:
        return
    try:
        fn()
    except Exception:
        pass


@app.post("/emails/actions/read", response_model=ActionResult)
def action_read(req: ReadReq, token: str = Depends(get_gmail_token),
                provider: str = Depends(get_provider),
                session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Đánh dấu đã/chưa đọc (Gmail: nhãn UNREAD · Outlook: isRead)."""
    result = _write(lambda: mail.set_read(provider, token, req.ids, req.read))
    _wt(lambda: email_store_repo.mark_read(db, session.user_id, provider, req.ids, req.read))
    # Hành động NHẸ, đảo được → chỉ audit, KHÔNG làm phiền bằng notification.
    _record(db, session.user_id, action="mark_read" if req.read else "mark_unread",
            ids=req.ids, tool_name="bulk_action")
    return result


@app.post("/emails/actions/important", response_model=ActionResult)
def action_important(req: ImportantReq, token: str = Depends(get_gmail_token),
                     provider: str = Depends(get_provider),
                     session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Gắn/bỏ sao (Gmail: STARRED · Outlook: flag)."""
    result = _write(lambda: mail.set_flag(provider, token, req.ids, req.value))
    _wt(lambda: email_store_repo.set_starred(db, session.user_id, provider, req.ids, req.value))
    _record(db, session.user_id, action="star" if req.value else "unstar",
            ids=req.ids, tool_name="bulk_action")
    return result


@app.post("/emails/actions/archive", response_model=ActionResult)
def action_archive(req: IdsReq, token: str = Depends(get_gmail_token),
                   provider: str = Depends(get_provider),
                   session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Lưu trữ (Gmail: bỏ nhãn INBOX · Outlook: chuyển thư mục Archive)."""
    result = _write(lambda: mail.archive(provider, token, req.ids))
    _wt(lambda: email_store_repo.move_folder(db, session.user_id, provider, req.ids, "archive"))
    _record(db, session.user_id, action="archive", ids=req.ids, tool_name="bulk_action",
            notify=f"Đã lưu trữ {len(req.ids)} thư.", notify_type="info")
    return result


@app.post("/emails/actions/delete", response_model=ActionResult)
def action_delete(req: IdsReq, token: str = Depends(get_gmail_token),
                  provider: str = Depends(get_provider),
                  session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Xoá = vào THÙNG RÁC (Gmail: trash · Outlook: chuyển Deleted Items) — khôi phục được."""
    result = _write(lambda: mail.trash(provider, token, req.ids))
    _wt(lambda: email_store_repo.move_folder(db, session.user_id, provider, req.ids, "trash"))
    _record(db, session.user_id, action="delete", ids=req.ids, tool_name="bulk_action",
            notify=f"Đã chuyển {len(req.ids)} thư vào thùng rác.", notify_type="warning")
    return result


@app.post("/emails/actions/restore", response_model=ActionResult)
def action_restore(req: IdsReq, token: str = Depends(get_gmail_token),
                   provider: str = Depends(get_provider),
                   session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Đưa thư TỪ thùng rác trở lại hộp thư — đường lùi cho nút Xoá.

    Xoá vốn đã là xoá MỀM nên luôn cứu được, nhưng chỉ khi người dùng biết tự vào
    Gmail mà bới. Trợ lý xoá hộ thì phải hoàn tác hộ được, không thì "hoàn tác được"
    chỉ đúng trên giấy.

    KHÔNG cần cổng xác nhận: thao tác này chỉ THÊM thư trở lại, không mất gì. Dựng
    thêm một hàng rào ở đúng lúc người dùng đang hoảng vì lỡ tay là đặt nhầm chỗ."""
    result = _write(lambda: mail.untrash(provider, token, req.ids))
    _wt(lambda: email_store_repo.move_folder(db, session.user_id, provider, req.ids, "inbox"))
    _record(db, session.user_id, action="restore", ids=req.ids, tool_name="bulk_action",
            notify=f"Đã khôi phục {len(req.ids)} thư về hộp thư.", notify_type="success")
    return result


@app.post("/emails/actions/spam", response_model=ActionResult)
def action_spam(req: IdsReq, token: str = Depends(get_gmail_token),
                provider: str = Depends(get_provider),
                session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Đánh dấu thư rác (Gmail: thêm nhãn SPAM + bỏ INBOX · Outlook: chuyển Junk Email)."""
    result = _write(lambda: mail.spam(provider, token, req.ids))
    _wt(lambda: email_store_repo.move_folder(db, session.user_id, provider, req.ids, "spam"))
    _record(db, session.user_id, action="spam", ids=req.ids, tool_name="bulk_action",
            notify=f"Đã đánh dấu {len(req.ids)} thư là thư rác.", notify_type="info")
    return result


@app.post("/emails/actions/not-spam", response_model=ActionResult)
def action_not_spam(req: IdsReq, token: str = Depends(get_gmail_token),
                    provider: str = Depends(get_provider),
                    session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Bỏ đánh dấu thư rác, đưa thư về hộp thư.

    Chiều này mới là chiều người ta cần gấp: một lá thư quan trọng bị lọc nhầm vào Thư
    rác, và họ đang hoảng đi tìm. Có chiều đi mà không có chiều về thì chỉ làm được nửa
    việc, và là nửa ít quan trọng hơn.
    """
    result = _write(lambda: mail.not_spam(provider, token, req.ids))
    _wt(lambda: email_store_repo.move_folder(db, session.user_id, provider, req.ids, "inbox"))
    _record(db, session.user_id, action="not_spam", ids=req.ids, tool_name="bulk_action",
            notify=f"Đã đưa {len(req.ids)} thư về hộp thư.", notify_type="success")
    return result


@app.post("/emails/actions/label", response_model=ActionResult)
def action_label(req: LabelReq, token: str = Depends(get_gmail_token),
                 provider: str = Depends(get_provider),
                 session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Gắn NHÃN (Gmail: label tự tạo · Outlook: categories) cho thư (UC006)."""
    result = _write(lambda: mail.apply_label(provider, token, req.ids, req.label))
    _wt(lambda: email_store_repo.set_label(db, session.user_id, provider, req.ids, req.label))
    _record(db, session.user_id, action="apply_label", ids=req.ids, tool_name="apply_labels",
            details={"label": req.label},
            notify=f"Đã gắn nhãn “{req.label}” cho {len(req.ids)} thư.", notify_type="success")
    return result


@app.post("/emails/{email_id}/read", response_model=ActionResult)
def mark_read_one(email_id: str, req: ReadOneReq, token: str = Depends(get_gmail_token),
                  provider: str = Depends(get_provider)):
    """Đánh dấu MỘT thư đã/chưa đọc — FE gọi khi MỞ thư (UC004). Không audit (quá thường)."""
    return _write(lambda: mail.set_read(provider, token, [email_id], req.read))


@app.get("/emails/{email_id}/attachments/{name}")
def download_attachment(email_id: str, name: str, token: str = Depends(get_gmail_token)):
    """Tải 1 tệp đính kèm (UC004 — nút Download). Trả bytes kèm tên + kiểu để trình duyệt lưu."""
    data, mime, fname = gmail_service.get_attachment(token, email_id, name)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tệp đính kèm")
    # Content-Disposition: attachment → trình duyệt TẢI XUỐNG (thay vì mở trong tab).
    return Response(
        content=data,
        media_type=mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── Nấc 6b: GỬI & TRẢ LỜI thư thật (UC010) ───────────────────────────
@app.post("/emails/send", response_model=SendResult)
def send_email_route(req: SendReq, bg: BackgroundTasks, token: str = Depends(get_gmail_token),
                     provider: str = Depends(get_provider),
                     session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Soạn & gửi thư mới (kèm tệp — Gmail). Body khớp `SendEmailInput` + attachmentIds."""
    # Đổi danh sách id tệp → nội dung thật (bytes) đã cất ở /uploads.
    _xin = list(req.attachmentIds or [])
    attachments = [
        {"name": f["name"], "content": f["content"], "mime": f["mime"]}
        for fid in _xin
        if (f := upload_store.get(fid))
    ]
    # THIẾU TỆP THÌ TỪ CHỐI, KHÔNG GỬI IM LẶNG.
    # Bản trước bỏ qua id tra không ra rồi vẫn gửi — và người dùng báo đúng triệu chứng
    # sinh ra từ đó: "mail thì qua mà không có phần đính kèm", không lỗi, không dấu vết.
    # Một bức thư gửi thành công NHƯNG THIẾU thứ chính cần gửi thì tệ hơn một lỗi rõ
    # ràng: người gửi tin là xong và chỉ biết sự thật từ phía người nhận.
    if len(attachments) < len(_xin):
        raise HTTPException(
            status_code=409,
            detail=(f"{len(_xin) - len(attachments)} tệp đính kèm không còn trong kho "
                    "tạm (kho giữ 30 phút và mất khi máy chủ khởi động lại). Thư CHƯA "
                    "được gửi — bạn đính lại tệp rồi gửi giúp mình nhé."),
        )
    res = _guard(lambda: mail.send_email(
        provider, token, req.to, req.subject, req.body, cc=req.cc, bcc=req.bcc, attachments=attachments,
    ))
    new_id = res.get("id", "")
    _record(db, session.user_id, action="send_email", tool_name="send_email",
            ids=[new_id] if new_id else [], details={"to": req.to, "subject": req.subject},
            notify=f"Đã gửi email tới {req.to}.", notify_type="success")
    if settings.mailbox_store_enabled:
        bg.add_task(_bg_sync, session.user_id, provider, token)  # Sent hiện ngay
    return SendResult(id=new_id, threadId=res.get("threadId"))


@app.post("/emails/{email_id}/reply", response_model=SendResult)
def reply_email_route(email_id: str, req: ReplyReq, bg: BackgroundTasks,
                      token: str = Depends(get_gmail_token),
                      provider: str = Depends(get_provider),
                      session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Trả lời thư email_id: BE tự suy người nhận/tiêu đề/luồng từ thư gốc, chỉ cần `body`."""
    res = _guard(lambda: mail.reply_email(provider, token, email_id, req.body,
                                         reply_all=req.replyAll))
    new_id = res.get("id", "")
    _record(db, session.user_id, action="reply_email", tool_name="reply_email",
            ids=[i for i in (email_id, new_id) if i], details={"reply_to": email_id},
            notify="Đã gửi trả lời trong đúng luồng thư.", notify_type="success")
    if settings.mailbox_store_enabled:
        bg.add_task(_bg_sync, session.user_id, provider, token)  # Sent hiện ngay
    return SendResult(id=new_id, threadId=res.get("threadId"))


class ForwardReq(BaseModel):
    """POST /emails/{id}/forward — `to` BẮT BUỘC, `note` là lời nhắn đặt ở đầu."""
    to: str
    note: str = ""


@app.post("/emails/{email_id}/forward", response_model=SendResult)
def forward_email_route(email_id: str, req: ForwardReq, bg: BackgroundTasks,
                        token: str = Depends(get_gmail_token),
                        provider: str = Depends(get_provider),
                        session: AuthSession = Depends(get_current_session),
                        db: Session = Depends(get_db)):
    """Chuyển tiếp thư sang địa chỉ khác, kèm nội dung thư gốc được trích dẫn.

    Rủi ro RIÊNG của chuyển tiếp: nó đưa nội dung của NGƯỜI KHÁC cho người thứ ba. Gửi
    nhầm địa chỉ là làm lộ thư của một người không hề tham gia cuộc trao đổi — nặng hơn
    gửi nhầm thư của chính mình. Nên ghi nhật ký kèm địa chỉ nhận để còn lần ra được.
    """
    res = _guard(lambda: mail.forward_email(provider, token, email_id, req.to, req.note))
    new_id = res.get("id", "")
    _record(db, session.user_id, action="forward_email", tool_name="forward_email",
            ids=[i for i in (email_id, new_id) if i], details={"to": req.to},
            notify=f"Đã chuyển tiếp thư tới {req.to}.", notify_type="success")
    if settings.mailbox_store_enabled:
        bg.add_task(_bg_sync, session.user_id, provider, token)
    return SendResult(id=new_id, threadId=res.get("threadId"))


# ── HUMAN-IN-THE-LOOP CÓ TRẠNG THÁI (PA2 §1.3.5, FR-02.4) ───────────────────
# Trước đây việc duyệt chỉ sống ở giao diện: nút bấm gọi thẳng lệnh gửi. Máy chủ
# không biết có "yêu cầu đang chờ duyệt" nào, nên bấm hai lần là GỬI HAI LẦN.
# Giờ mỗi hành động không-hoàn-tác có một bản ghi; ràng buộc "chỉ chạy khi đang
# pending" khiến lần bấm thứ hai không thể thực thi lại.
@app.get("/confirmations")
def list_confirmations(session: AuthSession = Depends(get_current_session),
                       db: Session = Depends(get_db)):
    """Các yêu cầu còn chờ duyệt của chính người dùng."""
    return [confirmation_repo.to_dict(r) for r in confirmation_repo.list_pending(db, session.user_id)]


@app.post("/confirmations/{req_id}/approve")
async def approve_confirmation(req_id: str,
                               token: str = Depends(get_gmail_token),
                               provider: str = Depends(get_provider),
                               session: AuthSession = Depends(get_current_session),
                               db: Session = Depends(get_db)):
    """Người dùng đồng ý → CHẠY hành động đã chốt, đúng MỘT lần.

    Bấm lại lần nữa trả về kết quả của lần đầu kèm `already: true`, chứ không báo
    lỗi: bấm hai lần là chuyện thường của người dùng (mạng chậm, lỡ tay), không
    phải sự cố cần dí vào mặt họ.
    """
    req = confirmation_repo.get_owned(db, req_id, session.user_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu xác nhận")
    if req.status == confirmation_repo.REJECTED:
        raise HTTPException(status_code=409, detail="Yêu cầu này đã bị từ chối trước đó")

    # Cửa duy nhất: chỉ lần gọi chuyển được trạng thái mới được phép chạy hành động.
    if not confirmation_repo.approve(db, req):
        return {"status": req.status, "already": True, "result": req.result}

    # Import tại chỗ theo đúng lối app.py đang dùng cho RequestContext (tránh vòng import).
    from app.tools.registry import RequestContext, tool_registry
    _sub = subscription_repo.get_or_create(db, session.user_id)
    import app.tools.email_tools  # noqa: F401 — nạp để các tool tự đăng ký vào registry

    # Gỡ `_tep` ra khỏi args TRƯỚC khi gọi tool: nó là khoá nội bộ, không có trong
    # schema của tool nào. Để lẫn vào thì Pydantic sẽ từ chối cả lời gọi.
    _args = dict(req.args or {})
    _tep = [str(x) for x in (_args.pop("_tep", None) or [])]
    ctx = RequestContext(user_id=str(session.user_id), access_token=token,
                         email_provider=provider, conversation_id=req.conversation_id,
                         tier=_sub.tier, scan_days=subscription_repo.scan_days_of(_sub),
                         tep_dinh_kem=_tep)
    try:
        out = await tool_registry.call(req.action, _args, ctx)
        res = out.model_dump() if hasattr(out, "model_dump") else dict(out or {})
    except Exception as exc:                      # noqa: BLE001 — mọi lỗi tool đều phải ghi lại
        res = {"success": False, "error": str(exc)[:300]}
    confirmation_repo.save_result(db, req, res)
    _record(db, session.user_id, action=req.action, tool_name=req.action,
            ids=[], details={"confirmation_id": req.id},
            notify=req.description, notify_type="success" if res.get("success", True) else "error")
    return {"status": req.status, "already": False, "result": res}


@app.post("/confirmations/{req_id}/reject")
def reject_confirmation(req_id: str,
                        session: AuthSession = Depends(get_current_session),
                        db: Session = Depends(get_db)):
    """Người dùng từ chối → hành động KHÔNG chạy, và không ai 'cứu' lại được."""
    req = confirmation_repo.get_owned(db, req_id, session.user_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu xác nhận")
    doi = confirmation_repo.reject(db, req)
    return {"status": req.status, "already": not doi}


# ── UC010: LƯU NHÁP · GỢI Ý AI · AUTOCOMPLETE NGƯỜI NHẬN ────────────────────
@app.post("/emails/draft")
def save_draft(req: SendReq, token: str = Depends(get_gmail_token),
               provider: str = Depends(get_provider),
               session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Lưu BẢN NHÁP (không gửi) — tạo nháp trên Gmail/Outlook + upsert vào store (folder='drafts')
    để hiện NGAY ở tab Nháp dù chưa sync lại."""
    attachments = [
        {"name": f["name"], "content": f["content"], "mime": f["mime"]}
        for fid in (req.attachmentIds or []) if (f := upload_store.get(fid))
    ]
    res = _guard(lambda: mail.create_draft(provider, token, req.to, req.subject, req.body,
                                           cc=req.cc, bcc=req.bcc, attachments=attachments))
    gid = (res.get("message") or {}).get("id") or res.get("id") or ""
    try:
        if settings.mailbox_store_enabled and gid:
            from app.schemas.email import Email
            recipient = (req.to or "").strip() or "(chưa có người nhận)"
            em = Email(id=gid, sender=recipient, senderEmail=(req.to or "").strip(),
                       senderInitial=(recipient.lstrip("(")[:1].upper() or "?"), to=(req.to or ""),
                       subject=req.subject or "(không tiêu đề)", preview=(req.body or "")[:120],
                       body=[req.body or ""], time="", date="", unread=False, starred=False,
                       category="sky", label="Nháp", folder="drafts",
                       threadId=(res.get("message") or {}).get("threadId"))
            email_store_repo.upsert(db, session.user_id, provider, em, folder="drafts", full=True)
    except Exception:
        db.rollback()
    return {"id": gid}


@app.post("/emails/compose/suggest")
def compose_suggest(payload: dict,
                    session: AuthSession = Depends(get_current_session)):
    # PHẢI đăng nhập: endpoint này GỌI LLM. Để mở thì bất kỳ ai cũng đốt được hạn mức
    # Gemini của nhóm — mà gói free chỉ 20 lượt/ngày mỗi model, tức là một người lạ
    # gọi vài chục lần là buổi trình bày mất trợ lý.
    """Smart Compose — gợi ý ĐOẠN TIẾP THEO khi soạn thư, dựa trên tiêu đề + phần đang gõ.
    LLM chưa cấu hình / lỗi → trả rỗng (FE tự ẩn gợi ý)."""
    subject = (payload or {}).get("subject", "")
    body = (payload or {}).get("body", "")
    if not settings.agent_enabled:
        return {"suggestion": ""}
    try:
        from app.core.llm import create_llm
        from app.agent.nodes.agent_node import coerce_text
        prompt = (
            "Bạn là trợ lý viết email tiếng Việt. Dựa trên TIÊU ĐỀ và phần người dùng ĐANG viết, "
            "gợi ý PHẦN TIẾP THEO (nối liền mạch, tự nhiên, tối đa 1–2 câu). CHỈ trả phần nối tiếp, "
            "KHÔNG lặp lại phần đã viết, KHÔNG giải thích.\n\n"
            f"Tiêu đề: {subject}\nĐang viết:\n{body}\n\nGợi ý tiếp theo:"
        )
        text = coerce_text(getattr(create_llm().invoke(prompt), "content", "")) or ""
        return {"suggestion": text.strip()[:300]}
    except Exception:
        return {"suggestion": ""}


@app.get("/contacts")
def contacts(q: str = "", limit: int = 8, provider: str = Depends(get_provider),
             session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Autocomplete người nhận (như Gmail) — suy từ sender/recipient các thư đã đồng bộ trong store."""
    return {"items": email_store_repo.contacts(db, session.user_id, provider, q, min(max(limit, 1), 20))}


# ── ĐỒNG BỘ HỘP THƯ → DB store (chống rate-limit) ───────────────────────────
# Chiến lược: Gmail Push (Pub/Sub) đẩy thông báo khi hộp thư đổi → webhook này nhận →
# đồng bộ LŨY TIẾN (chỉ phần thay đổi) vào DB. User đọc web = đọc DB, KHÔNG gọi Gmail.

def _bg_sync(user_id: int, provider: str, token: str) -> None:
    """Đồng bộ lũy tiến ở NỀN sau hành động GHI (gửi/trả lời/agent) → Sent/Inbox trong web cập nhật
    NGAY mà không cần Pub/Sub. Mở phiên DB riêng; nuốt lỗi (không phá response chính)."""
    from app.core.db import SessionLocal
    d = SessionLocal()
    try:
        sync_service.incremental_sync(d, user_id, provider, token)
    except Exception:
        pass
    finally:
        d.close()


def _bg_pubsub(email_address: str) -> None:
    """Chạy NỀN sau khi webhook đã trả 2xx (Pub/Sub yêu cầu phản hồi nhanh). Mở phiên DB riêng."""
    from app.core.db import SessionLocal
    db = SessionLocal()
    try:
        n = sync_service.handle_pubsub(db, email_address)
        import logging
        logging.getLogger("app.sync").info("Pub/Sub sync %s: %d thư", email_address, n)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


@app.post("/gmail/push", status_code=status.HTTP_204_NO_CONTENT)
async def gmail_push(request: Request, bg: BackgroundTasks, token: str | None = None):
    """WEBHOOK Gmail Push (Pub/Sub push subscription trỏ vào đây). Giải mã thông báo lấy
    emailAddress rồi ĐẨY việc đồng bộ sang nền, trả 204 NGAY (Pub/Sub retry nếu chậm/lỗi).
    Bảo vệ tối thiểu bằng ?token= khớp PUBSUB_VERIFY_TOKEN (nếu có cấu hình)."""
    import base64 as _b64, json as _json, logging as _log
    if settings.pubsub_verify_token and token != settings.pubsub_verify_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "token webhook không hợp lệ")
    try:
        envelope = await request.json()
        data_b64 = (envelope.get("message") or {}).get("data") or ""
        payload = _json.loads(_b64.b64decode(data_b64).decode("utf-8")) if data_b64 else {}
        email_address = payload.get("emailAddress")
    except Exception as exc:
        _log.getLogger("app.sync").warning("Pub/Sub payload lỗi: %s", exc)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if email_address:
        bg.add_task(_bg_pubsub, email_address)   # HÀNG ĐỢI nhẹ: tách việc nặng khỏi phản hồi
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/sync/run")
def sync_run(bg: BackgroundTasks, background: bool = False,
             token: str = Depends(get_gmail_token), provider: str = Depends(get_provider),
             session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Đồng bộ hộp thư của PHIÊN đang đăng nhập vào DB (nút 'Đồng bộ ngay' / gọi định kỳ).
    background=true → chạy nền, trả ngay. Mặc định chạy đồng bộ và trả số thư đã cập nhật."""
    if background:
        uid, prov, tok = session.user_id, provider, token
        def _job():
            from app.core.db import SessionLocal
            d = SessionLocal()
            try:
                sync_service.incremental_sync(d, uid, prov, tok)
            finally:
                d.close()
        bg.add_task(_job)
        return {"queued": True}
    n = sync_service.incremental_sync(db, session.user_id, provider, token)
    return {"synced": n, "provider": provider}


@app.post("/gmail/watch")
def gmail_watch(token: str = Depends(get_gmail_token), provider: str = Depends(get_provider),
                session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """BẬT Gmail Push cho hộp thư này (cần GMAIL_PUBSUB_TOPIC). Lưu hạn watch để gia hạn sau.
    Chỉ Gmail — Outlook dùng Graph subscriptions (hướng nâng cấp)."""
    if provider != "google":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "watch chỉ hỗ trợ Gmail (google).")
    if not settings.gmail_pubsub_topic:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Chưa cấu hình GMAIL_PUBSUB_TOPIC trong .env.")
    res = _guard(lambda: gmail_service.watch(token, settings.gmail_pubsub_topic))
    state = sync_service._get_state(db, session.user_id, "google")
    exp = res.get("expiration")
    if exp:
        from datetime import datetime as _dt, timezone as _tz
        state.watch_expiration = _dt.fromtimestamp(int(exp) / 1000, tz=_tz.utc).replace(tzinfo=None)
    if res.get("historyId"):
        state.history_id = str(res["historyId"])
    db.commit()
    return {"watching": True, "expiration": res.get("expiration"),
            "historyId": res.get("historyId")}


# ── ACCOUNTABILITY: AuditLog + Notification ─────────────────────────────────
# AuditLog = nhật ký KỸ THUẬT "agent/user đã làm gì lên email nào" (hiện thực ý
# Toolcall_Email trong Design bằng affected_email_ids). Notification = thông báo
# hướng NGƯỜI DÙNG, sinh kèm các hành động đáng chú ý. Chỉ đọc phiên của CHÍNH user.
@app.get("/audit")
def get_audit(limit: int = 50,
              session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """N hành động gần nhất của user — để soi 'agent đã đụng gì' (accountability)."""
    rows = audit_repo.list_recent(db, session.user_id, limit=min(max(limit, 1), 200))
    return {"items": [{
        "id": r.id, "action": r.action, "toolName": r.tool_name, "actorType": r.actor_type,
        "affectedEmailIds": r.affected_email_ids, "status": r.status, "details": r.details,
        "createdAt": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


def _notif_dto(n) -> dict:
    return {"id": n.id, "type": n.type, "message": n.message, "read": n.read,
            "createdAt": n.created_at.isoformat() if n.created_at else None}


@app.get("/notifications")
def get_notifications(limit: int = 50,
                      session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    rows = notification_repo.list_for_user(db, session.user_id, limit=min(max(limit, 1), 200))
    return {"items": [_notif_dto(n) for n in rows],
            "unread": notification_repo.unread_count(db, session.user_id)}


@app.get("/notifications/unread-count")
def get_unread_count(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    return {"unread": notification_repo.unread_count(db, session.user_id)}


@app.post("/notifications/read-all")
def read_all_notifications(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    return {"marked": notification_repo.mark_all_read(db, session.user_id)}


@app.post("/notifications/{notif_id}/read")
def read_notification(notif_id: int,
                      session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    n = notification_repo.mark_read(db, session.user_id, notif_id)
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy thông báo")
    return _notif_dto(n)


# ── SUBSCRIPTION: gói + hạn mức token (freemium kiểu sản phẩm AI) ────────────
@app.get("/subscription")
def get_subscription(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Gói hiện tại + token đã dùng/còn lại (ngày & tháng) — FE hiện thanh usage."""
    sub = subscription_repo.get_or_create(db, session.user_id)
    return subscription_repo.status(db, sub)


@app.get("/subscription/plans")
def list_plans():
    """Danh mục 3 gói (Miễn phí / Pro / Pro Max) kèm hạn mức + giá hiển thị.
    FE dựng trang nâng cấp từ đây → số liệu chỉ nằm MỘT chỗ (app/core/plans.py)."""
    return {"plans": plans.public_catalog()}


@app.post("/subscription/tier")
def set_subscription_tier(payload: dict,
                          session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """Đổi gói (free/pro/max). ĐỒ ÁN: stub nâng cấp — sản phẩm thật sẽ qua cổng THANH TOÁN
    rồi mới set tier (không cho client tự nâng gói)."""
    tier = (payload or {}).get("tier", "free")
    if not plans.is_valid_tier(tier):
        raise HTTPException(status_code=400, detail=f"Gói không hợp lệ: {tier}")
    sub = subscription_repo.set_tier(db, session.user_id, tier)
    audit_repo.log(db, user_id=session.user_id, action="subscription.change_tier",
                   status="success", details={"tier": tier})
    return subscription_repo.status(db, sub)


# ── Pha 3 (tích hợp): AGENT THẬT — LangGraph + Gemini + tool Gmail ───
# FE gọi POST /agent/chat (qua api.sendAgentMessage). Giờ KHÔNG còn trả mẫu nữa:
# chạy graph agent → LLM hiểu lệnh → tự gọi tool (email_tools → service của quan).
# Vẫn trả đúng khuôn AgentReply kind "text" để FE hiện được như cũ.
_AGENT_GRAPH = None  # graph đã compile, dựng 1 lần ở request đầu rồi tái dùng (lazy singleton)

# ── NFR-Reliability: RATE LIMIT /agent/chat theo NGƯỜI (cửa sổ 60s) ──────────
# Vì sao cần: mỗi lượt chat đốt 2-3 lần gọi Gemini; quota free rất mỏng. Một người bấm
# liên tục (hoặc script lỗi lặp vô hạn) sẽ cạn quota của CẢ nhóm → chặn từ cửa, trả lời
# nhẹ nhàng TRƯỚC khi chạm LLM. Chạy trên kho KV cắm-rút: có REDIS_URL thì đếm trên
# Redis (đúng khi scale nhiều worker), không có thì in-memory như cũ.
from app.core.kv import kv as _kv


def _rate_limited(user_id: int) -> bool:
    from app.core.config import settings
    n = _kv.incr_window(f"rate:agent:{user_id}", window=60)
    return n > settings.agent_rate_limit_per_min

# ── BỘ NHỚ HỘI THOẠI (UC011 — LƯU BỀN xuống DB) ─────────────────────
# Vì sao CẦN: mỗi POST /agent/chat trước đây chạy 1 lượt RỖNG (chỉ tin nhắn mới) → agent KHÔNG
# nhớ gì. Luồng nhiều bước (vd "gửi mail cho A" → agent hỏi "xác nhận?" → user "ừ") bị ĐỨT.
# Giờ lưu lịch sử xuống bảng `conversations` theo sessionId → agent NHỚ + người dùng xem/tiếp tục
# lại phiên cũ (kể cả sau khi restart server). Xem app/models/conversation.py.
_MAX_HISTORY = 30  # giữ tối đa N tin LangChain gần nhất mỗi phiên (chặn phình token)


def _trim_history(msgs: list) -> list:
    """Cắt ngữ cảnh agent an toàn cho lượt sau:
    • Bỏ AIMessage 'mồ côi' ở cuối (có tool_calls nhưng CHƯA có ToolMessage — xảy ra khi chạm
      trần vòng lặp) để Gemini không báo lỗi 'tool_call thiếu kết quả'.
    • Giữ N tin cuối, rồi bỏ phần đầu cho tới HumanMessage đầu tiên (không mở màn bằng tool/ai mồ côi).
    """
    msgs = list(msgs)
    while msgs and getattr(msgs[-1], "type", None) == "ai" and getattr(msgs[-1], "tool_calls", None):
        msgs.pop()
    trimmed = msgs[-_MAX_HISTORY:]
    for i, m in enumerate(trimmed):
        if getattr(m, "type", None) == "human":
            return trimmed[i:]
    return trimmed


def _compact_tools(msgs: list, cap: int = 600) -> list:
    """NFR-Memory: rút gọn nội dung ToolMessage (JSON email thô — thường vài KB) khi CẤT KHO lịch sử.
    Lượt HIỆN TẠI đã dùng bản đầy đủ để trả lời + responder đã tóm tắt thành thẻ; nên bản lưu cho các
    lượt SAU chỉ cần giữ 'gợi ý' → đỡ phình token/RAM mỗi lần nạp lại phiên. Giữ nguyên tool_call_id để
    cặp AIMessage(tool_calls)↔ToolMessage không bị đứt."""
    from langchain_core.messages import ToolMessage
    out = []
    for m in msgs:
        c = getattr(m, "content", None)
        if getattr(m, "type", None) == "tool" and isinstance(c, str) and len(c) > cap:
            out.append(ToolMessage(
                content=c[:cap] + " …(đã rút gọn để tiết kiệm bộ nhớ)",
                tool_call_id=getattr(m, "tool_call_id", ""), name=getattr(m, "name", ""),
            ))
        else:
            out.append(m)
    return out


def _emails_from_search(messages: list, cap: int = 15) -> list:
    """UI/UX: rút danh sách email THẬT (id + người gửi + tiêu đề + snippet) từ kết quả search_emails
    của LƯỢT HIỆN TẠI → đính vào reply để FE vẽ thẻ BẤM ĐƯỢC (mở thẳng thư). Lấy id trực tiếp từ
    dữ liệu tool (KHÔNG nhờ LLM) nên id luôn chính xác — bấm là mở đúng thư.
    ⚠️ CHỈ xét từ HumanMessage CUỐI trở đi: vì có conversation memory, messages chứa cả lượt CŨ —
    không cắt sẽ đính nhầm danh sách thư của lượt trước vào câu trả lời mới (vd user nói 'cảm ơn'
    mà reply lại kèm chục thư cũ)."""
    import json
    last_human = max((i for i, m in enumerate(messages)
                      if getattr(m, "type", None) == "human"), default=0)
    for m in reversed(messages[last_human:]):
        # semantic_search trả CÙNG khuôn dữ liệu → thẻ bấm-được dùng chung
        # ── PHẢI XÉT CẢ `categorize_emails` ──
        # Câu "xoá các thư ưu đãi, mua sắm" không đi qua `search_emails`: agent phải
        # PHÂN LOẠI mới biết thư nào thuộc nhóm đó. Bản trước chỉ đọc hai tool tìm
        # kiếm, nên đúng những lệnh xoá theo NHÓM — loại nguy hiểm nhất — lại là loại
        # KHÔNG hiện được danh sách. Đo được trên bản triển khai: thẻ chỉ ghi "Xoá 2
        # thư", không một dòng nào cho biết hai thư đó là thư gì.
        if getattr(m, "type", None) == "tool" and getattr(m, "name", None) in (
            "search_emails", "semantic_search", "categorize_emails",
        ):
            try:
                data = json.loads(m.content)
            except Exception:
                return []
            out = []
            for e in (data.get("data") or [])[:cap]:
                if not isinstance(e, dict) or not e.get("id"):
                    continue
                sender = (e.get("sender") or "").strip()
                out.append({
                    "id": str(e["id"]),
                    "sender": sender or "(không rõ)",
                    "initial": (sender[:1].upper() if sender else "•"),
                    "subject": e.get("subject") or "(không tiêu đề)",
                    "snippet": e.get("snippet") or "",
                    "unread": not e.get("is_read", True),
                })
            return out
    return []


def _categorize_card(messages: list) -> dict | None:
    """UC009: dựng thẻ 'categorize' cho FE từ kết quả categorize_emails CỦA LƯỢT NÀY.
    Tất định (id + nhãn lấy thẳng từ tool) → không nhờ LLM nên không sai nhãn/ id.
    Trả None nếu lượt này không phân loại."""
    import json
    last_human = max((i for i, m in enumerate(messages)
                      if getattr(m, "type", None) == "human"), default=0)
    for m in reversed(messages[last_human:]):
        if getattr(m, "type", None) == "tool" and getattr(m, "name", None) == "categorize_emails":
            try:
                data = json.loads(m.content)
            except Exception:
                return None
            raw = data.get("data") or []
            items = [{
                "id": str(it["id"]), "sender": it.get("sender", ""),
                "subject": it.get("subject", "(không tiêu đề)"),
                "category": it.get("category", "cherry"),   # màu chip FE
                "label": it.get("label", "Cá nhân"),
            } for it in raw if isinstance(it, dict) and it.get("id")]
            if not items:
                return None
            summary = data.get("summary") or {}
            gist = " · ".join(f"{v} {k}" for k, v in summary.items())
            return {
                "kind": "categorize",
                "intro": "Mình đã tự phân loại giúp bạn — xem lại/sửa nhãn từng thư rồi bấm Áp dụng nhé:",
                "title": f"Đề xuất nhãn cho {len(items)} thư" + (f" ({gist})" if gist else ""),
                "items": items,
            }
    return None


def _tim_tool(messages: list, ten: str) -> dict | None:
    """Lấy `data` của tool `ten` NẾU nó được gọi trong LƯỢT NÀY. None nếu không."""
    import json
    last_human = max((i for i, m in enumerate(messages)
                      if getattr(m, "type", None) == "human"), default=0)
    for m in reversed(messages[last_human:]):
        if getattr(m, "type", None) == "tool" and getattr(m, "name", None) == ten:
            try:
                return json.loads(m.content).get("data") or None
            except Exception:
                return None
    return None


def _digest_card(messages: list, ngon: str = "vi") -> dict | None:
    """Thẻ 'digest' cho FE từ kết quả tom_tat_ngay.

    Số liệu lấy THẲNG từ tool, không nhờ mô hình đọc lại: đây là bảng thống kê, mà một
    bảng thống kê do mô hình chép tay thì mỗi lần bấm ra một con số khác — và không ai
    tin nổi một con số như thế."""
    d = _tim_tool(messages, "tom_tat_ngay")
    if not d:
        return None
    return {
        "kind": "digest",
        "intro": dich("the.digest.dan", ngon),
        # Tiêu đề thuần Việt. Giao diện lẫn Anh–Việt bắt người đọc chuyển ngữ giữa
        # chừng, và với bài bảo vệ thì đó là chi tiết người chấm nhìn ra ngay.
        "title": (dich("the.digest.tieude", ngon) + " — "
                  + (d.get("pham_vi") or dich("pham_vi.hom_nay", ngon))),
        "stats": [
            {"label": dich("the.digest.tong", ngon), "value": d.get("tong", 0)},
            {"label": dich("the.digest.chuadoc", ngon), "value": d.get("chua_doc", 0)},
            {"label": dich("the.digest.canxuly", ngon), "value": d.get("can_xu_ly", 0)},
        ],
        # Nhãn giữ giá trị tiếng Việt CHUẨN suốt đường xử lý, chỉ đổi ở đây —
        # điểm xuất ra. Xem `dich_gia_tri` để biết vì sao không đổi tận gốc.
        "breakdown": [{**x, "label": dich_gia_tri(x.get("label", ""), ngon)}
                      for x in (d.get("theo_nhan") or [])],
        "highlights": d.get("noi_bat") or [],
        # Kèm id thư để FE gắn nút MỞ THƯ cho từng dòng — liệt kê tên thư mà không mở
        # được thì người dùng vẫn phải tự đi tìm lại trong hộp thư.
        "emails": d.get("thu") or [],
    }


def _triage_card(messages: list, ngon: str = "vi") -> dict | None:
    """Thẻ 'triage' cho FE từ kết quả phan_loai_uu_tien."""
    d = _tim_tool(messages, "phan_loai_uu_tien")
    if not d or not d.get("nhom"):
        return None
    return {
        "kind": "triage",
        "intro": dich("the.triage.dan", ngon),
        "title": dich("the.triage.tieude", ngon, n=d.get("tong", 0)),
        "groups": [
            {**g,
             "label": dich_gia_tri(g.get("label", ""), ngon),
             "items": [{**i, "suggest": dich_gia_tri(i.get("suggest", ""), ngon)}
                       for i in (g.get("items") or [])]}
            for g in d["nhom"]
        ],
    }


# Thẻ nào có BỘ DỰNG TẤT ĐỊNH → tool nào phải chạy thì thẻ đó mới hợp lệ.
_THE_CAN_TOOL = {"digest": "tom_tat_ngay", "triage": "phan_loai_uu_tien"}


def ha_the_bia(out: dict, messages: list) -> dict:
    """Mô hình KHÔNG được tự bịa một loại thẻ vốn có nguồn tất định.

    `PresentReply.kind` cho phép bộ trình bày chọn 'digest' và 'triage'. Nhưng hai kiểu
    đó có bộ dựng riêng lấy số liệu THẲNG từ tool (`_digest_card`, `_triage_card`). Mô
    hình chọn chúng khi tool tương ứng KHÔNG hề chạy nghĩa là nó đang vẽ một cái vỏ
    không có ruột.

    ĐÃ ĐO ĐƯỢC 03/09/2026: câu "tìm giúp mình các thư về học phí" chỉ gọi
    `search_emails`, nhưng bộ trình bày trả về kind='triage' → người dùng nhận một
    widget "xếp theo độ ưu tiên" cho một câu hỏi TÌM KIẾM. Nguy ở chỗ nó TRÔNG CHỈN
    CHU: một thẻ vẽ đẹp nhưng sai loại còn khó phát hiện hơn một lỗi lộ liễu.

    Hạ về 'result' chứ không phải 'text': nội dung vẫn là một danh sách, chỉ là nó
    không phải bảng phân loại ưu tiên.

    ── HÀM RIÊNG, KHÔNG VIẾT THẲNG TRONG ENDPOINT ──
    Kịch bản kiểm (`scripts/thu_prompt_demo.py`) phải chạy ĐÚNG luật này. Chép luật
    sang đó là tạo ra hai bản sẽ trôi xa nhau — và đã trôi thật: bản vá đầu tiên chỉ
    nằm trong endpoint nên bộ kiểm vẫn báo lệch sau khi đã sửa xong.
    """
    ten = _THE_CAN_TOOL.get(out.get("kind"))
    if ten and not _tim_tool(messages, ten):
        logging.getLogger("app.agent").info(
            "Bộ trình bày chọn kind=%s nhưng %s không chạy → hạ về 'result'",
            out.get("kind"), ten,
        )
        return {**out, "kind": "result"}
    return out


def _lich_trinh_card(messages: list, ngon: str = "vi") -> dict | None:
    """Thẻ 'lichtrinh' — MỘT khuôn dùng chung cho ba tool lịch trình.

    ── VÌ SAO PHẢI CÓ ──
    `liet_ke_cam_ket`, `ap_luc_lich_trinh` và `de_xuat_di_lai` trước đây không có thẻ
    nào nên rơi hết vào nhánh `kind:"text"` — mô hình tự kể lại bằng lời. Hậu quả đo
    được trên bản triển khai:
      • "tuần này lịch trình tôi thế nào?" → trả về mỗi một câu hỏi ngược
        ("Bạn có muốn mình xem chi tiết thư nào không?"), KHÔNG có việc nào được liệt kê.
      • "tuần này tôi có bị quá tải không?" → một đoạn văn dài bốn dòng, người đọc phải
        tự dò ra ngày nào bận.
      • "cần đi công tác việc nào không?" → cũng một đoạn văn xuôi.
    Cả ba đều là DỮ LIỆU CÓ CẤU TRÚC bị ép thành văn xuôi, và văn xuôi thì mỗi lần một
    khác, không bấm được, không mở được thư.

    ── VÌ SAO MỘT THẺ CHỨ KHÔNG BA ──
    Ba tool khác nhau nhưng người dùng nhìn thấy cùng một thứ: "những việc tôi phải
    làm, khi nào, vì lá thư nào". Ba thẻ ba kiểu vẽ thì họ phải học ba lần, và mình
    phải bảo trì ba bộ. Thẻ này bật/tắt phần theo dữ liệu có mặt:
      `ngay` có → vẽ dải áp lực · `viec` có → vẽ danh sách việc.
    """
    ck = _tim_tool(messages, "liet_ke_cam_ket")
    ap = _tim_tool(messages, "ap_luc_lich_trinh")
    dl = _tim_tool(messages, "de_xuat_di_lai")
    if not (ck or ap or dl):
        return None

    viec: list[dict] = []
    if ck:
        viec = [
            {"noi_dung": c.get("noi_dung", ""), "han": c.get("han"),
             "nguoi_cho": c.get("nguoi_cho", ""), "email_id": c.get("email_id", ""),
             "tieu_de": c.get("tieu_de", ""), "nguoi_gui": c.get("nguoi_gui", ""),
             "muc_uu_tien": c.get("muc_uu_tien", 1),
             "uoc_luong_phut": c.get("uoc_luong_phut", 0)}
            for c in ck
        ]
    elif dl:
        # Ý ĐỊNH ĐI LẠI: cùng khuôn "việc", thêm nơi đến. `noi` có mặt thì giao diện
        # hiện thêm nút tra vé — đúng việc tiếp theo người dùng sẽ muốn làm.
        viec = [
            {"noi_dung": y.get("noi_dung", ""), "han": y.get("han"),
             "email_id": y.get("email_id", ""), "nguoi_cho": "",
             "tieu_de": "", "nguoi_gui": "",
             "noi": y.get("thanh_pho", ""), "ma_san_bay": y.get("ma_san_bay", ""),
             "tu_san_bay": y.get("tu_san_bay", ""),
             "muc_uu_tien": 2, "uoc_luong_phut": 0}
            for y in dl
        ]

    ngay = ap or []
    if not viec and ngay:
        # Chỉ hỏi áp lực: gom việc từ chính bảng ngày để danh sách không rỗng.
        _thay: dict[str, dict] = {}
        for d in ngay:
            for v in (d.get("viec") or []):
                _thay.setdefault(v.get("noi_dung", ""), {
                    "noi_dung": v.get("noi_dung", ""), "han": v.get("han"),
                    "email_id": v.get("email_id", ""), "nguoi_cho": "",
                    "tieu_de": "", "nguoi_gui": "",
                    "muc_uu_tien": v.get("muc_uu_tien", 1), "uoc_luong_phut": 0,
                })
        viec = list(_thay.values())

    if not viec and not ngay:
        return None

    if dl and not ck:
        tieu_de = dich("the.lich.tieude_dilai", ngon, n=len(viec))
        intro = dich("the.lich.dan_dilai", ngon)
    elif ngay:
        _nang = max(ngay, key=lambda d: d.get("phut", 0), default=None)
        _qt = sum(1 for d in ngay if d.get("qua_tai"))
        tieu_de = dich("the.lich.tieude_apluc", ngon, n=len(ngay))
        intro = (dich("the.lich.khong_quatai", ngon) if not _qt
                 else dich("the.lich.co_quatai", ngon, n=_qt))
        if _nang and _nang.get("so_viec"):
            intro += dich("the.lich.nang_nhat", ngon,
                          ngay=_nang["ngay"], n=_nang["so_viec"])
    else:
        tieu_de = dich("the.lich.tieude_viec", ngon, n=len(viec))
        intro = dich("the.lich.dan_viec", ngon)

    return {
        "kind": "lichtrinh",
        "intro": intro,
        "title": tieu_de,
        "ngay": ngay,
        "viec": viec[:20],
    }


def _di_lai_card(messages: list) -> dict | None:
    """Dựng thẻ 'dilai' cho FE từ kết quả tim_chuyen_bay / tim_khach_san CỦA LƯỢT NÀY.

    ── VÌ SAO PHẢI CÓ THẺ, KHÔNG ĐỂ MÔ HÌNH KỂ LẠI ──
    Trước đây kết quả tra cứu rơi vào nhánh mặc định `kind: "text"`, tức là mô hình đọc
    dữ liệu tool rồi TỰ VIẾT LẠI thành đoạn văn. Đó đúng là thứ cả tính năng này sinh ra
    để tránh: mô hình có thể chép sai số hiệu, làm rơi nhãn nguồn, hoặc thêm một con giá
    không có trong dữ liệu — ngay trên phần cần chứng minh là THẬT.
    Dựng tất định từ `data` thì thứ người dùng đọc CHÍNH LÀ thứ nhà cung cấp trả về.
    Cùng lý do với `_categorize_card` và `_confirm_card`.

    NHÃN NGUỒN lấy từ chính nhà cung cấp (không suy ra bằng cách so chuỗi ở đây), nên
    thẻ trong chat và khung "Tra cứu đi lại" luôn nói cùng một điều.
    """
    import json
    from app.services import dat_cho as _dc

    TEN_TOOL = {"tim_chuyen_bay": "bay", "tim_khach_san": "phong"}
    last_human = max((i for i, m in enumerate(messages)
                      if getattr(m, "type", None) == "human"), default=0)
    for m in reversed(messages[last_human:]):
        if getattr(m, "type", None) != "tool":
            continue
        loai = TEN_TOOL.get(getattr(m, "name", "") or "")
        if not loai:
            continue
        try:
            data = json.loads(m.content)
        except Exception:
            return None
        items = [it for it in (data.get("data") or []) if isinstance(it, dict)]
        if not items:
            # Không có kết quả thì ĐỪNG dựng thẻ rỗng — để mô hình nói bằng lời sẽ rõ
            # hơn ("không có chuyến nào ngày đó"). Thẻ rỗng trông như giao diện hỏng.
            return None

        # Nguồn nào đang phục vụ: hỏi thẳng lớp nhà cung cấp. Riêng khách sạn có thể đã
        # LUI VỀ mô phỏng dù nguồn bay là thật — nên tin `nguon` trong chính dữ liệu
        # trước, chỉ dùng nhà cung cấp để lấy câu nhãn.
        ncc = _dc.lay_nha_cung_cap()
        nguon = items[0].get("nguon") or getattr(ncc, "ten", "mo_phong")
        if nguon == getattr(ncc, "ten", None):
            nhan, la_that = getattr(ncc, "nhan", ""), getattr(ncc, "la_that", False)
        else:
            nhan, la_that = _dc.NhaCungCapMoPhong.nhan, False

        return {
            "kind": "dilai",
            "loai": loai,
            "intro": (data.get("message") or "").strip() or None,
            "title": (f"{len(items)} chuyến bay" if loai == "bay"
                      else f"{len(items)} chỗ ở"),
            "nguon": nguon, "la_that": la_that, "nhan": nhan,
            "items": items,
        }
    return None


def _confirm_card(messages: list) -> dict | None:
    """Human-in-the-loop (UC007/UC010): tool KHÔNG HOÀN TÁC bị tool_node CHẶN (payload
    needs_confirmation) → dựng thẻ CÓ NÚT DUYỆT cho FE: 'draft' (gửi/trả lời — nút
    Niêm phong & Gửi) hoặc 'plan' (hàng loạt — nút Duyệt/Từ chối). Dựng TẤT ĐỊNH từ
    args tool (không nhờ LLM) → nội dung thẻ chính là thứ sẽ thực thi, không sai lệch.
    Trả None nếu lượt này không có tool nào bị chặn."""
    import json
    last_human = max((i for i, m in enumerate(messages)
                      if getattr(m, "type", None) == "human"), default=0)
    for m in reversed(messages[last_human:]):
        if getattr(m, "type", None) != "tool":
            continue
        try:
            data = json.loads(m.content)
        except Exception:
            continue
        if not (isinstance(data, dict) and data.get("needs_confirmation")):
            continue
        args = data.get("args") or {}
        name = getattr(m, "name", "")

        if name == "send_email":
            to = args.get("to") or []
            return {
                "kind": "draft",
                "intro": "Mình đã soạn xong — bạn xem lại rồi bấm gửi nhé:",
                "to": ", ".join(to) if isinstance(to, list) else str(to),
                "subject": args.get("subject") or "(không tiêu đề)",
                "body": args.get("body") or "",
                # Chốt tool + tham số để tạo yêu cầu chờ duyệt. Hai khoá gạch dưới này
                # bị gỡ trước khi trả về FE — chúng chỉ dùng ở tầng máy chủ.
                "_tool": "send_email", "_args": dict(args),
            }
        if name == "reply_email":
            return {
                "kind": "draft",
                "intro": "Bản nháp trả lời đã sẵn sàng — bạn duyệt là mình gửi trong đúng luồng thư:",
                "to": "(người gửi thư gốc — trả lời trong luồng)",
                "subject": "Re: (thư gốc)",
                "body": args.get("instructions") or "",
                "replyToId": args.get("email_id") or "",
                "_tool": "reply_email", "_args": dict(args),
            }
        if name == "bulk_action":
            ids = [str(x) for x in (args.get("email_ids") or [])]
            act = str(args.get("action") or "").lower()
            op = None
            if "restore" in act:
                op = {"type": "restore", "ids": ids}
            elif "delete" in act:
                op = {"type": "delete", "ids": ids}
            elif "unread" in act:
                op = {"type": "markRead", "ids": ids, "read": False}
            elif "read" in act:
                op = {"type": "markRead", "ids": ids, "read": True}
            if op:
                verb = {"delete": "Xoá", "markRead": "Đánh dấu", "restore": "Khôi phục"}[op["type"]]
                # Tổng số thư tool đã soát ở lượt này — để nói thẳng phạm vi đã xem.
                # PHẢI tính trước khi dựng `card`: bản đầu tôi đặt nó xuống dưới, và
                # `card` tham chiếu một biến chưa gán → UnboundLocalError làm chết cả
                # thẻ duyệt. Test tự viết bắt được ngay.
                _tong_soat = len(_emails_from_search(messages, cap=1000))
                card = {
                    "kind": "plan",
                    "intro": "Mình đã lên kế hoạch — bạn duyệt là chạy ngay:",
                    # NÓI RÕ ĐÃ SOÁT BAO NHIÊU. "Chọn 2 thư theo yêu cầu" đọc ra
                    # thành "nhóm này có 2 thư", trong khi sự thật có thể là "2 trong
                    # số 20 thư gần nhất mình xem tới". Người dùng duyệt xong rồi mở
                    # hộp thư ra thấy còn mười lá nữa — và không hiểu vì sao.
                    "steps": [
                        (f"Chọn {len(ids)} thư theo yêu cầu"
                         + (f" (đã soát {_tong_soat} thư gần nhất)"
                            if _tong_soat > len(ids) else "")),
                        f"{verb} {len(ids)} thư",
                    ],
                    "confirmLabel": f"{verb} {len(ids)} thư",
                    "op": op,
                }
                # ── LIỆT KÊ ĐÍCH DANH THƯ SẼ BỊ ĐỤNG TỚI ──
                # Thẻ chỉ ghi "Xoá 2 thư" là bắt người dùng DUYỆT MÙ một hành động
                # không hoàn tác — đúng thứ cổng xác nhận sinh ra để ngăn. "Kiểm tra kỹ
                # trước khi duyệt" mà không cho thấy cái gì để kiểm thì chỉ là một câu
                # chữ, không phải một lớp bảo vệ.
                # Lấy từ kết quả search_emails CỦA LƯỢT NÀY (id thật, không nhờ mô hình),
                # rồi lọc đúng những id sắp bị thao tác.
                _tap = set(ids)
                _ds = [e for e in _emails_from_search(messages, cap=60) if e.get("id") in _tap]
                # LUÔN đặt khoá, kể cả rỗng. Thẻ được LƯU NGUYÊN VĂN xuống DB rồi dựng
                # lại y hệt khi mở app, nên một khoá lúc có lúc không nghĩa là dữ liệu
                # cũ và mã mới có thể lệch nhau — và lệch kiểu đó đã làm ĐEN cả giao
                # diện một lần rồi (`.map` trên `undefined`, React tháo sạch cây).
                # KHÔNG cắt bớt. Người dùng sắp BỎ TICK từng thư trên chính danh sách
                # này, nên hiện 20 mà thao tác trên 25 là để họ bỏ tick một danh sách
                # rồi hệ thống xoá một danh sách khác — tệ hơn hẳn không cho tick.
                # `email_ids` vốn đã bị chặn ở 100 nên danh sách không thể phình vô hạn.
                card["emails"] = _ds
                if op["type"] == "delete":
                    # NÓI ĐÚNG SỰ THẬT. Câu cũ ghi "không hoàn tác được" — sai kể từ
                    # khi có `bulk_action(restore)`: thư vào Thùng rác và lấy lại được.
                    # Một cảnh báo sai làm hỏng chính nó: người dùng xoá thử, thấy khôi
                    # phục được, rồi từ đó không tin bất kỳ cảnh báo nào của app nữa.
                    #
                    # Rủi ro THẬT của xoá hàng loạt không phải mất vĩnh viễn, mà là xoá
                    # nhầm mà KHÔNG BIẾT — nên câu cảnh báo phải chỉ vào đúng chỗ đó.
                    card["warn"] = ("Thư sẽ vào Thùng rác và khôi phục lại được, nhưng "
                                    "sẽ biến khỏi hộp thư — soát danh sách bên trên "
                                    "trước khi duyệt.")
                card["_tool"] = "bulk_action"
                card["_args"] = dict(args)
                return card

        if name == "dat_cho_mo_phong":
            # THẺ DỰ ĐỊNH — dựng TẤT ĐỊNH từ args, không nhờ LLM viết lại. Đây là chỗ
            # người dùng nhìn vào để quyết định tiêu tiền, nên nội dung thẻ phải CHÍNH
            # LÀ thứ sẽ chạy; để mô hình diễn đạt lại thì thẻ và hành động có thể lệch
            # nhau, và người dùng duyệt một thứ khác với thứ xảy ra.
            tien = int(args.get("so_tien_vnd") or 0)
            hoan = bool(args.get("hoan_duoc"))
            la_bay = str(args.get("loai") or "") == "chuyen_bay"
            return {
                "kind": "dudinh",
                "intro": "Mình đã tra và chọn sẵn. Đây là DỰ ĐỊNH — bạn duyệt thì mình mới làm.",
                "title": args.get("mo_ta") or "Dự định đặt chỗ",
                "buoc": [
                    {
                        "mo_ta": args.get("mo_ta") or "",
                        # Nói hậu quả bằng lời người dùng hiểu, không bằng thuật ngữ.
                        "hau_qua": ("huỷ/hoàn miễn phí" if hoan
                                    else "không đổi, không hoàn"),
                        # Cấp 3 = mất tiền thật. Đây đúng là chỗ thang rủi ro cấp 3
                        # được dành sẵn cho — và là lần đầu nó được dùng.
                        "mucRuiRo": 3 if not hoan else 2,
                        "tien": tien,
                    },
                ],
                # NÓI RÕ ĐÂY LÀ MÔ PHỎNG, ngay trên thẻ duyệt. Một xác nhận đặt chỗ
                # trông như thật mà thực ra là giả là thứ nguy hiểm nhất ở đây: người
                # dùng có thể ra sân bay với nó.
                "cho_doan": ("ĐÂY LÀ ĐẶT CHỖ MÔ PHỎNG — MeoArc chưa nối với hệ thống bán "
                             f"{'vé' if la_bay else 'phòng'} nào. Không có khoản tiền nào "
                             "được thanh toán, và bạn sẽ không nhận được "
                             f"{'vé' if la_bay else 'xác nhận phòng'} thật."),
                "_tool": "dat_cho_mo_phong", "_args": dict(args),
            }

        return None  # tool destructive khác: chưa có thẻ riêng → giữ câu trả lời của agent
    return None


def _preview_of(display_messages: list) -> str:
    """Vài chữ của TIN GẦN NHẤT (cho drawer xem lướt). Tin agent là thẻ → rút text/intro."""
    for m in reversed(display_messages or []):
        if m.get("role") == "user":
            return " ".join((m.get("text") or "").split())[:80]
        if m.get("role") == "agent":
            r = m.get("reply") or {}
            txt = r.get("text") or r.get("intro") or r.get("title") or ""
            if txt:
                return " ".join(txt.split())[:80]
    return ""


@app.post("/agent/chat")
async def agent_chat(
    payload: dict,
    bg: BackgroundTasks,                                  # sync nền sau lượt (Sent/Inbox cập nhật ngay)
    session: AuthSession = Depends(get_current_session),  # phải đăng nhập (agent đụng hộp thư thật)
    token: str = Depends(get_gmail_token),                # token còn hạn (tự refresh, đa provider)
    provider: str = Depends(get_provider),                # 'google'|'microsoft' → tool route Gmail/Outlook
    db: Session = Depends(get_db),                        # UC011: lưu/đọc lịch sử phiên
):
    from app.core.config import settings
    message = (payload or {}).get("message", "")
    incoming_id = (payload or {}).get("sessionId")  # id phiên FE gửi (None = phiên mới)
    # Tệp người dùng vừa đính kèm trong khung chat (id do POST /uploads cấp).
    # Đi theo NGỮ CẢNH chứ không qua tham số tool — xem RequestContext.tep_dinh_kem.
    tep_dinh_kem = [str(x) for x in ((payload or {}).get("attachmentIds") or [])][:5]

    # NFR-Reliability: chặn spam TRƯỚC MỌI THỨ (không tốn LLM/DB) — bảo vệ quota chung.
    if _rate_limited(session.user_id):
        return {"kind": "text", "conversationId": incoming_id,
                "text": ("🐢 Bạn đang gửi hơi nhanh — mình xin nghỉ vài giây để tiết kiệm "
                         "lượt gọi AI. Chờ chút rồi gửi lại giúp mình nhé.")}

    # NFR-Security: chặn prompt-injection NGAY (regex, không tốn LLM) trước khi vào graph.
    from app.agent.guardrails.input_guardrail import check_input
    blocked = check_input(message)
    if blocked:
        return {"kind": "text", "text": blocked, "conversationId": incoming_id}

    # FALLBACK: chưa cấu hình khoá LLM → trả lời lịch sự, KHÔNG làm sập gì.
    # Nhờ vậy app vẫn chạy đầy đủ kể cả khi chưa cắm Gemini (mọi nút bấm khác vô tư).
    if not settings.agent_enabled:
        return {
            "kind": "text",
            "text": (
                "🔑 Agent chưa được cấp khoá Gemini nên mình chưa “suy nghĩ” được.\n"
                "Thêm AI_API_KEY vào .env (lấy free ở aistudio.google.com) rồi khởi động lại "
                "là mình chạy thật ngay. Các tính năng bấm-nút khác vẫn dùng bình thường nhé."
            ),
        }

    # SUBSCRIPTION: chặn khi CHẠM trần token của gói (free/pro) — theo ngày HOẶC tháng.
    # Kiểm TRƯỚC khi gọi LLM (không đốt thêm token khi đã hết hạn mức). Chặn MỀM: báo lịch sự,
    # gợi ý nâng cấp; các nút bấm khác vẫn dùng bình thường.
    sub = subscription_repo.get_or_create(db, session.user_id)
    if subscription_repo.is_over_quota(db, sub):
        st = subscription_repo.status(db, sub)
        return {"kind": "text", "conversationId": incoming_id,
                "text": (f"🎟️ Bạn đã dùng hết hạn mức token gói “{sub.tier}” "
                         f"(ngày: {st['daily']['used']:,}/{st['daily']['limit']:,}). "
                         "Chờ sang kỳ mới hoặc nâng cấp gói để tiếp tục dùng trợ lý AI. "
                         "Các thao tác bấm-nút (đọc/gắn nhãn/gửi qua nút) vẫn dùng bình thường.")}

    # CHẠY AGENT — lazy-import bên trong + bọc try/except để lỗi LLM/tool KHÔNG thành 500,
    # mà báo nhẹ nhàng (giữ trải nghiệm mượt + an toàn).
    conv = None  # bind trước try: except cần biết phiên đã tạo chưa (trả đúng conversationId)
    try:
        from langchain_core.messages import HumanMessage, messages_to_dict, messages_from_dict
        from app.agent.graph import build_graph
        from app.agent.skills.skill_loader import load_skills
        from app.tools.registry import RequestContext

        global _AGENT_GRAPH
        if _AGENT_GRAPH is None:
            _AGENT_GRAPH = build_graph()  # dựng + compile graph 1 lần duy nhất

        # UC011: lấy/tạo phiên trong DB rồi NẠP LẠI ngữ cảnh LangChain đã lưu (agent NHỚ).
        conv = conversation_repo.get_or_create(db, incoming_id, session.user_id)
        history = messages_from_dict(conv.agent_messages) if conv.agent_messages else []

        # RequestContext = "thẻ ra vào" bơm xuống mọi tool: ai gọi + token nào để đụng Gmail.
        ctx = RequestContext(
            user_id=str(session.user_id),
            access_token=token,
            email_provider=provider,   # tool trong graph route đúng Gmail/Outlook theo phiên
            conversation_id=conv.id,
            tier=sub.tier,             # NFR-08: quyết định cửa sổ quét hộp thư của các tool
            scan_days=subscription_repo.scan_days_of(sub),   # giá trị đã chốt của người này
            tep_dinh_kem=tep_dinh_kem,
        )
        # State khởi đầu: lịch sử cũ + tin mới → agent thấy CẢ hội thoại (luồng hỏi-xác-nhận → gửi…).
        init_state = {
            "messages": [*history, HumanMessage(content=message)],
            "request_ctx": ctx,
            "skill_context": load_skills(message),  # nạp kỹ năng khớp ngữ cảnh
            # Sở thích cá nhân: tên xưng hô, giọng văn, chữ ký, dặn dò riêng.
            # Trả rỗng khi chưa đặt gì — repo tự nuốt lỗi nên không làm hỏng lượt chat.
            "user_context": user_preference_repo.prompt_context(db, session.user_id),  # noqa: E501
            "pending_confirmation": None,
            "iteration_count": 0,
            "final_output": None,
        }
        # NGÔN NGỮ NGƯỜI DÙNG — quyết định chữ trên thẻ và trong thông báo lỗi.
        # Đọc một lần ở đây rồi truyền xuống, thay vì mỗi bộ dựng thẻ tự đi hỏi lại
        # database: một lượt chat dựng nhiều thẻ, và mỗi lần hỏi lại là một truy vấn
        # thừa cho một giá trị không đổi trong suốt lượt đó.
        try:
            _ngon = user_preference_repo.get_or_create(db, session.user_id).language or "vi"
        except Exception:
            _ngon = "vi"   # đọc hỏng thì về mặc định, đừng làm hỏng cả lượt chat

        # Graph lo TỪ A-Z: agent (nghĩ) ↔ tools (chạy) → responder (ép thẻ) hoặc dừng (thuần text).
        result = await _AGENT_GRAPH.ainvoke(init_state)

        # SUBSCRIPTION: cộng token đã tiêu của lượt này vào hạn mức ngày/tháng.
        try:
            subscription_repo.add_usage(db, sub, _turn_tokens(result.get("messages") or []))
        except Exception:
            pass  # đo/ghi token hỏng KHÔNG được làm sập câu trả lời

        # Agent có thể vừa gửi/xoá/gắn nhãn → sync nền để Hộp thư/Đã gửi trong web cập nhật NGAY
        # (không chờ Pub/Sub). incremental_sync nhẹ (history.list + fetch phần đổi).
        if settings.mailbox_store_enabled:
            bg.add_task(_bg_sync, session.user_id, provider, token)

        # responder_node (khi có dữ liệu tool) đóng gói sẵn AgentReply vào final_output (thẻ FE).
        out = result.get("final_output")
        if not out:
            # Lượt thuần văn bản (graph đi thẳng END, bỏ responder để tiết kiệm) → lấy câu trả lời
            # cuối của agent làm thẻ 'text'. Chào hỏi/hỏi-xác-nhận vẫn hiện đúng, KHÔNG tốn LLM lần 2.
            from app.agent.nodes.agent_node import coerce_text
            last_ai = next((m for m in reversed(result["messages"])
                            if getattr(m, "type", None) == "ai" and getattr(m, "content", None)), None)
            # coerce_text: content có thể là LIST part (tuỳ model Gemini) → ép về chuỗi chuẩn cho FE.
            last_text = coerce_text(last_ai.content).strip() if last_ai else ""
            out = {"kind": "text", "text": last_text or "Mình đã xử lý xong."}

        out = ha_the_bia(out, result["messages"])

        # UC009: nếu lượt này có gọi categorize_emails → ÉP thành thẻ 'categorize' (widget FE cho
        # sửa nhãn từng thư rồi Áp dụng). Xây TẤT ĐỊNH từ dữ liệu tool (id + nhãn), KHÔNG nhờ LLM
        # → nhãn/ id luôn chuẩn. Đặt TRƯỚC phần đính emails để không lẫn 2 loại thẻ.
        cat_card = _categorize_card(result["messages"])
        if cat_card:
            out = cat_card

        # Tra cứu đi lại: ÉP thành thẻ 'dilai' để chat hiện ĐÚNG bảng như khung "Tra cứu
        # đi lại", thay vì để mô hình kể lại bằng lời. Xem chú thích ở _di_lai_card.
        dl_card = _di_lai_card(result["messages"])
        if dl_card:
            out = dl_card

        # Digest / Triage / Lịch trình: cùng khuôn — thẻ dựng TẤT ĐỊNH từ số liệu tool.
        for _dung in (_digest_card, _triage_card, _lich_trinh_card):
            _c = _dung(result["messages"], _ngon)
            if not _c:
                continue
            # ── THẺ LÀ BẰNG CHỨNG, CÂU TRẢ LỜI VẪN LÀ CÂU TRẢ LỜI ──
            # Thẻ dựng tất định thì đè lên `out`, và như thế là ĐÈ MẤT câu mô hình vừa
            # viết. Đo được 03/09/2026: hỏi "buổi bảo vệ đồ án mấy giờ?" thì agent tra
            # đúng chuỗi thư rồi trả về… một danh sách 18 việc kèm dòng dẫn chung chung
            # "Đây là những việc bạn đang mắc". Người hỏi một cái GIỜ mà nhận một cái
            # DANH SÁCH — và bên dưới danh sách đó thì câu trả lời thật đã bị vứt đi.
            #
            # Giữ cả hai: câu của mô hình lên làm phần dẫn, bảng số liệu nằm dưới làm
            # chỗ đối chiếu. Đó mới đúng vai của từng thứ.
            #
            # Ngưỡng 20 ký tự để bỏ qua mấy câu lấp chỗ ("Đã xong.", "Đây rồi:") — chúng
            # tệ hơn dòng dẫn mặc định vốn ít ra còn nói thẻ này là thẻ gì.
            _cau = str(out.get("text") or out.get("intro") or "").strip()
            if _cau and len(_cau) > 20:
                _c = {**_c, "intro": _cau}
            out = _c

        # HUMAN-IN-THE-LOOP: lượt này có tool không-hoàn-tác bị CHẶN chờ duyệt →
        # thẻ draft/plan CÓ NÚT thắng mọi thẻ khác (người dùng phải thấy nút duyệt,
        # không phải câu chữ của LLM).
        confirm_card = _confirm_card(result["messages"])
        if confirm_card and tep_dinh_kem:
            # HIỆN TÊN TỆP TRÊN THẺ DUYỆT. Cổng xác nhận chỉ có nghĩa khi người dùng
            # thấy ĐÚNG thứ sắp đi ra ngoài — duyệt một lá thư mà không biết nó kèm
            # tệp gì thì cái nút duyệt đó không bảo vệ được gì cả.
            from app.services import upload_store as _us
            _ten = [f["name"] for fid in tep_dinh_kem if (f := _us.get(fid))]
            if _ten:
                confirm_card["attachments"] = _ten
        if confirm_card:
            # Ghi lại yêu cầu chờ duyệt và gắn id vào thẻ. Không có bản ghi này thì
            # nút "Duyệt" lại gọi thẳng lệnh gửi như trước — bấm hai lần là gửi hai lần.
            try:
                _cr = confirmation_repo.create(
                    db, user_id=session.user_id,
                    action=confirm_card.get("_tool") or "send_email",
                    description=confirm_card.get("confirmLabel")
                    or f"Gửi thư: {confirm_card.get('subject') or ''}".strip(),
                    # `_tep` là khoá NỘI BỘ, không phải tham số tool: nó được gỡ ra ở
                    # bước duyệt rồi đưa vào ngữ cảnh. Lưu kèm ở đây vì người dùng có
                    # thể bấm Duyệt sau vài phút, lúc đó lượt chat đã kết thúc từ lâu
                    # và không còn chỗ nào biết họ đã đính tệp nào.
                    args={**(confirm_card.get("_args") or {}),
                          **({"_tep": tep_dinh_kem} if tep_dinh_kem else {})},
                    conversation_id=conv.id,
                )
                confirm_card["confirmationId"] = _cr.id
            except Exception:
                # Ghi hỏng thì vẫn hiện thẻ (người dùng không bị kẹt), chỉ mất tính
                # chống-bấm-trùng của lượt này — nên nuốt lỗi chứ không chặn luồng.
                logging.getLogger("app.confirm").warning("Không tạo được yêu cầu xác nhận", exc_info=True)
            confirm_card.pop("_tool", None)
            confirm_card.pop("_args", None)
            out = confirm_card

        # UI/UX: đính danh sách thư THẬT (bấm mở được) từ search_emails CỦA LƯỢT NÀY → FE render
        # thẻ clickable. Lưu luôn vào display_messages nên phiên cũ mở lại vẫn bấm được.
        # Chỉ đính cho kind 'text'/'result' — 2 kind FE có render danh sách này (digest/triage
        # có widget riêng, đính thêm chỉ phình payload + DB vô ích).
        ref_emails = _emails_from_search(result["messages"]) if out.get("kind") in ("text", "result") else []
        if ref_emails:
            # KHỚP số thẻ với số mục LLM ĐÃ trình bày: user xin "5 thư" → responder liệt kê 5 dòng →
            # chỉ hiện 5 thẻ (đừng đổ hết kết quả tool ra, kẻo "liệt kê 5" lại hiện 10-15).
            if out.get("kind") == "result" and out.get("lines"):
                ref_emails = ref_emails[: len(out["lines"])]
            else:
                ref_emails = ref_emails[:8]
            out = {**out, "emails": ref_emails}

        # UC011: LƯU lượt này — ngữ cảnh agent (để nghĩ tiếp) + lịch sử FE (để vẽ lại thẻ).
        # _compact_tools: cắt bớt JSON email thô trước khi cất → NFR-Memory (đỡ phình token lượt sau).
        agent_dump = messages_to_dict(_compact_tools(_trim_history(result["messages"])))
        display = list(conv.display_messages or [])
        display.append({"role": "user", "text": message})
        display.append({"role": "agent", "reply": out})
        conversation_repo.save_turn(db, conv, agent_dump, display, first_user_text=message)

        # Trả AgentReply kèm conversationId để FE biết phiên nào (nhất là khi phiên VỪA tạo).
        return {**out, "conversationId": conv.id}
    except Exception as exc:
        # Lỗi bất ngờ (mạng/LLM/tool) → vẫn trả AgentReply hợp lệ, không vỡ FE.
        # PHÂN LOẠI để báo đúng bệnh thay vì ném stack-trace khó hiểu cho người dùng:
        text = str(exc)
        low = text.lower()
        if "user location is not supported" in low or "failed_precondition" in low:
            # GOOGLE CHAN GEMINI API THEO VI TRI CUA MAY CHU GOI, khong phai vi tri
            # trinh duyet. Da kiem chung: goi tu Viet Nam -> HTTP 200; nhung ban trien
            # khai dang chay tren Azure "East Asia" = HONG KONG, va Google khong cho
            # generativelanguage.googleapis.com phuc vu Hong Kong.
            #
            # => Chay may cuc bo thi agent hoat dong, ban deploy thi KHONG BAO GIO
            #    hoat dong. Day la loai loi de tuong la "loi lac" vi no chi xuat hien
            #    o mot moi truong.
            #
            # Ba duong sua, deu can thao tac NGOAI ma nguon:
            #   1. (RE NHAT, KHUYEN DUNG) Dat AI_BASE_URL tro toi Cloudflare Worker
            #      trong `infra/cf-gemini-proxy/`. Worker day loi goi qua mot Durable
            #      Object ghim o Bac My nen loi goi DI RA tu My. Vung Azure giu nguyen
            #      => URL dang nhap giu nguyen => KHONG phai khai bao lai OAuth redirect.
            #      LUU Y: mot Worker THUONG (khong Durable Object) KHONG cuu duoc —
            #      Worker chay o PoP gan nguoi goi nhat, tuc la van Hong Kong.
            #   2. Tao lai App Service o vung Google co phuc vu (Japan East, Korea
            #      Central, Southeast Asia). Vung cua App Service KHONG doi tai cho
            #      duoc, phai tao moi roi tro lai deploy — va URL doi theo.
            #   3. Doi sang Vertex AI (MODEL_PROVIDER=google_vertexai): Vertex CHAY
            #      DUOC o Hong Kong vi no thuoc nhom san pham doanh nghiep, chinh sach
            #      vung khac han. Doi lai phai co project GCP + bat thanh toan.
            msg = ("🌏 Google không phục vụ Gemini API cho khu vực mà máy chủ này đang đặt "
                   "(Azure East Asia = Hong Kong). Đây là hạn chế theo vị trí MÁY CHỦ, không "
                   "phải lỗi tài khoản hay hết lượt — nên bản chạy máy cục bộ vẫn dùng agent "
                   "bình thường. Cách sửa nhanh nhất: dựng proxy trong infra/cf-gemini-proxy "
                   "rồi đặt AI_BASE_URL. Các thao tác bấm-nút (đọc/gắn nhãn/gửi) vẫn dùng được.")
        elif "not_found" in low or "no longer available" in low:
            # GOOGLE ĐÃ GỠ MODEL. Không phải hết lượt, không phải khoá hỏng — nên mọi
            # lời khuyên kiểu "chờ ít phút" hay "thêm khoá" đều dẫn đi sai đường.
            # Nghiệt nhất là mệnh đề "to new users": khoá cũ vẫn gọi được, khoá VỪA TẠO
            # thì 404. Nên vừa lập thêm project để có thêm hạn mức là vừa mất model
            # chính — hai việc trông không liên quan gì nhau.
            #
            # Google có nói sẵn tên thay thế trong chính thông báo; lôi nó ra để người
            # đọc không phải đi tra, vì đây là lúc họ đang kẹt giữa buổi trình bày.
            _thay = re.search(r"use\s+models/([\w.-]+)", text)
            msg = ("🚫 Model AI đang cấu hình đã bị Google gỡ (404), không phải bạn hết lượt. "
                   + (f"Google đề nghị dùng `{_thay.group(1)}` thay thế. " if _thay else "")
                   + "Sửa MODEL_NAME (hoặc MODEL_FALLBACKS) trong cấu hình rồi khởi động lại. "
                   "Xem /admin/kiem-khoa để biết khoá của bạn còn dùng được model nào.")
        # ── 503 PHẢI XÉT TRƯỚC 429 ──────────────────────────────────────────
        # Bản trước để nhánh quota lên trên, mà điều kiện của nó là `"429" in text` —
        # một phép tìm chuỗi con trên TOÀN BỘ văn bản lỗi. Lỗi 503 của Google thường
        # kéo theo cả lịch sử thử lại, và chỉ cần đâu đó trong đó có ba ký tự "429"
        # là cả cú 503 bị dán nhãn "hết quota".
        #
        # Hậu quả không phải một chữ sai: người dùng vừa nạp 10 khoá của 10 project
        # khác nhau, thấy báo "hết quota", và kết luận rằng tính năng nhiều khoá không
        # chạy — trong khi thật ra Google chỉ đang đông. Chẩn đoán sai đắt hơn lỗi gốc.
        #
        # "unavailable"/"overloaded" là dấu hiệu KHÔNG mập mờ nên xét trước; nhánh quota
        # ở dưới mới được phép dùng phép tìm chuỗi con rộng tay.
        elif "unavailable" in low or "overloaded" in low or "high demand" in low or "503" in text:
            # Google báo model quá tải NHẤT THỜI (503). Chuỗi dự phòng đã thử hết mọi bậc
            # (xem `_la_loi_qua_tai_nhat_thoi`) mà vẫn kẹt → phía Google đông thật.
            msg = ("⏳ Mô hình AI của Google đang quá tải nhất thời (lỗi 503). Trợ lý đã tự thử "
                   "lại qua toàn bộ các khoá dự phòng rồi mà vẫn kẹt, nên đây là phía Google "
                   "đông chứ KHÔNG phải bạn hết lượt. Thử lại sau vài giây là được. "
                   "Các thao tác bấm-nút vẫn dùng bình thường.")
        elif "resource_exhausted" in low or "429" in text or "quota" in low:
            # Quota Gemini free hết (theo phút hoặc theo ngày). Chuỗi dự phòng đã đi hết
            # mọi model × mọi khoá; tới đây là hết lượt thật → khuyên người dùng cách xử lý.
            msg = ("🚦 Gemini đã hết lượt miễn phí (quota) trên TẤT CẢ các khoá đã cấu hình. "
                   "Chờ ít phút rồi thử lại, hoặc thêm khoá từ một project khác — hạn mức free "
                   "tính theo project, nên nhiều khoá cùng một project vẫn chỉ là một hạn mức. "
                   "Các thao tác bấm-nút (đọc/gắn nhãn/gửi qua nút) vẫn dùng bình thường nhé.")
        elif "permission" in low or "403" in text or "invalid_grant" in low or "unauthorized" in low:
            msg = ("🔑 Phiên Gmail có thể đã hết hạn hoặc thiếu quyền. Bạn đăng xuất rồi đăng nhập "
                   "lại bằng Google để cấp quyền mới giúp mình nhé.")
        elif "tool_use_failed" in low or "failed to call a function" in low or "failed_generation" in low:
            # Model (thường Llama-trên-Groq) sinh cú gọi tool SAI cú pháp → nhà cung cấp
            # từ chối. Là lỗi CHẤT LƯỢNG MODEL, không phải hộp thư. Thử lại thường qua
            # (do lấy mẫu ngẫu nhiên); dai dẳng thì đổi model tool tốt hơn / hạ nhiệt độ.
            msg = ("🤖 Model AI vừa tạo lệnh gọi công cụ chưa đúng chuẩn (hay gặp với Llama trên "
                   "Groq). Bạn thử gửi lại — thường lần sau là được. Nếu lặp nhiều, đổi sang "
                   "model gọi-tool ổn hơn (vd llama-3.3-70b-versatile) hoặc đặt AGENT_TEMPERATURE=0.")
        else:
            msg = f"Xin lỗi, agent đang gặp trục trặc: {exc}"

        # UC011: phiên đã được tạo TRƯỚC khi graph chạy → phải trả ĐÚNG id + LƯU lượt lỗi vào
        # lịch sử. Nếu trả None như trước: FE không bám phiên → mỗi lần lỗi đẻ thêm 1 dòng
        # "Cuộc trò chuyện mới" RỖNG trong drawer, còn tin nhắn của user thì bốc hơi.
        err_reply = {"kind": "text", "text": msg}
        if conv is not None:
            try:
                display = list(conv.display_messages or [])
                display.append({"role": "user", "text": message})
                display.append({"role": "agent", "reply": err_reply})
                conversation_repo.save_turn(db, conv, list(conv.agent_messages or []),
                                            display, first_user_text=message)
            except Exception:
                pass  # lưu lỗi thất bại thì thôi — ưu tiên vẫn trả reply hợp lệ cho FE
        return {**err_reply, "conversationId": conv.id if conv is not None else incoming_id}


# ── UC011: QUẢN LÝ LỊCH SỬ HỘI THOẠI ────────────────────────────────
# Drawer lịch sử của FE đọc/sửa qua 4 endpoint dưới. Tất cả CHỈ đụng phiên của CHÍNH user
# (get_owned chặn xem chéo). Phiên được tạo ngầm khi chat (/agent/chat), nên ở đây không có POST tạo.

def _summary_of(c: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=c.id, title=c.title, pinned=c.pinned, updatedAt=c.updated_at,
        messageCount=len(c.display_messages or []),
        preview=_preview_of(c.display_messages or []),
    )


@app.get("/agent/conversations", response_model=list[ConversationSummary])
def list_conversations(
    session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)
):
    """Liệt kê phiên chat của user (ghim trước, mới-nhất-trước) cho drawer lịch sử."""
    return [_summary_of(c) for c in conversation_repo.list_for_user(db, session.user_id)]


@app.get("/agent/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(
    conv_id: str,
    session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db),
):
    """Mở 1 phiên: trả display_messages để FE vẽ lại lịch sử (Xem / Tiếp tục)."""
    c = conversation_repo.get_owned(db, conv_id, session.user_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên hội thoại.")
    return ConversationDetail(
        id=c.id, title=c.title, pinned=c.pinned,
        createdAt=c.created_at, updatedAt=c.updated_at,
        messages=c.display_messages or [],
    )


@app.patch("/agent/conversations/{conv_id}", response_model=ConversationSummary)
def update_conversation(
    conv_id: str, req: UpdateConversationReq,
    session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db),
):
    """Đổi tên và/hoặc ghim một phiên (chỉ gửi field cần đổi)."""
    c = conversation_repo.get_owned(db, conv_id, session.user_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên hội thoại.")
    if req.title is not None:
        conversation_repo.rename(db, c, req.title)
    if req.pinned is not None:
        conversation_repo.set_pinned(db, c, req.pinned)
    return _summary_of(c)


@app.delete("/agent/conversations/{conv_id}", status_code=204)
def delete_conversation(
    conv_id: str,
    session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db),
):
    """Xoá một phiên (drawer có xác nhận trước khi gọi)."""
    c = conversation_repo.get_owned(db, conv_id, session.user_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên hội thoại.")
    conversation_repo.delete(db, c)
    return Response(status_code=204)


# ── Nấc 10: THỰC THI SAU DUYỆT (cầu nối agent ↔ service) ──────────────
# Khép kín human-in-the-loop: agent trả 'plan'/'autopilot' → user Approve →
# FE gọi 2 endpoint dưới để CHẠY THẬT qua cùng lớp gmail_actions.
# KHÔNG có LLM ở đây — chỉ nhận hành động ĐÃ DUYỆT rồi thực thi (phần của BE).

@app.post("/agent/plan/execute", response_model=ExecuteResult)
def execute_plan(req: ExecutePlanReq, token: str = Depends(get_gmail_token)):
    """Chạy 1 PlanOp đã được user Approve, trả câu tóm tắt 'done' cho FE hiển thị."""
    op = req.op
    if op.type == "archive":
        n = _guard(lambda: gmail_actions.modify_labels(token, op.ids, remove=["INBOX"]))
        done = f"Đã lưu trữ {n} thư."
    elif op.type == "delete":
        n = _guard(lambda: gmail_actions.trash(token, op.ids))
        done = f"Đã chuyển {n} thư vào thùng rác."
    elif op.type == "markRead":
        if op.read:
            n = _guard(lambda: gmail_actions.modify_labels(token, op.ids, remove=["UNREAD"]))
            done = f"Đã đánh dấu {n} thư là đã đọc."
        else:
            n = _guard(lambda: gmail_actions.modify_labels(token, op.ids, add=["UNREAD"]))
            done = f"Đã đánh dấu {n} thư là chưa đọc."
    elif op.type == "label":
        n = _guard(lambda: gmail_actions.apply_label(token, op.ids, op.label))
        done = f"Đã gắn nhãn “{op.label}” cho {n} thư."
    else:  # autoLabel — mỗi thư một nhãn riêng (gán `it=it` để lambda khỏi dính biến vòng lặp)
        total = 0
        for it in op.items:
            total += _guard(lambda it=it: gmail_actions.apply_label(token, [it.id], it.label))
        done = f"Đã gắn nhãn cho {total} thư."
    return ExecuteResult(done=done)


@app.post("/agent/autopilot/apply", response_model=OkResult)
def autopilot_apply(req: AutopilotApplyReq, token: str = Depends(get_gmail_token)):
    """Áp dụng lô hành động tự-lái đã duyệt (UC017): lưu trữ + đánh dấu đọc + gắn sao."""
    if req.archive:
        _guard(lambda: gmail_actions.modify_labels(token, req.archive, remove=["INBOX"]))
    if req.markRead:
        _guard(lambda: gmail_actions.modify_labels(token, req.markRead, remove=["UNREAD"]))
    if req.flag:
        _guard(lambda: gmail_actions.modify_labels(token, req.flag, add=["STARRED"]))
    return OkResult()


# ── Nấc 3: chạm database lần đầu (DEV — để THẤY DB chạy) ──────────────
# Đây là endpoint TẠM cho việc học (chưa phải đăng nhập thật). Mục đích:
# tạo & xem User trong DB, hiểu vòng route → repo → database.
# `db: Session = Depends(get_db)` → FastAPI tự mở 1 phiên DB, đưa vào, đóng sau.
def _chi_moi_truong_dev() -> None:
    """Chặn các endpoint tiện-lợi-khi-dev ở môi trường thật.

    `/dev/users` TẠO và LIỆT KÊ người dùng mà không cần đăng nhập. Trên máy dev thì
    tiện; trên bản deploy thì bất kỳ ai cũng tạo được tài khoản trong CSDL thật, và
    GET còn trả về địa chỉ email của MỌI người đã đăng ký — lộ dữ liệu cá nhân.
    Trả 404 (không phải 403) để không xác nhận là endpoint có tồn tại."""
    if settings.app_env.strip().lower() in ("production", "prod", "staging"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")


@app.post("/dev/users", response_model=UserOut)
def dev_create_user(payload: UserCreate, db: Session = Depends(get_db),
                    _=Depends(_chi_moi_truong_dev)):
    # get_or_create: có email rồi thì lấy lại, chưa có thì tạo (mẫu khi đăng nhập).
    return user_repo.get_or_create_user(db, payload.email, payload.name, payload.initial)


@app.get("/dev/users", response_model=list[UserOut])
def dev_list_users(db: Session = Depends(get_db), _=Depends(_chi_moi_truong_dev)):
    return user_repo.list_users(db)


# ── Nấc 4b: gắn router đăng nhập + endpoint /me ──────────────────────
app.include_router(auth_routes.router)  # thêm /auth/google/start, /callback, /auth/logout
app.include_router(avatar_routes.router)  # /avatars/{ten_mien} — biểu tượng người gửi (có cache)

# /tra-cuu/* — tra cứu chuyến bay & phòng, gọi THẲNG không qua mô hình. Tách khỏi
# đường agent để phần trình bày không phụ thuộc hạn mức Gemini (20 lượt/ngày cho mỗi
# model) — một buổi bảo vệ chết vì hết lượt thì không cứu được tại chỗ.
from app.api import dat_cho_routes  # noqa: E402
app.include_router(dat_cho_routes.router)


@app.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    """Trả thông tin user của phiên hiện tại.
    `Depends(get_current_user)` = "cửa có bảo vệ": chưa đăng nhập → tự động 401."""
    return current_user


# ── Sở thích cá nhân (PA2 §1.5.2) — thứ làm trợ lý viết ra GIỌNG CỦA NGƯỜI NÀY ──
from pydantic import BaseModel, Field                    # noqa: E402
from app.models.user_preference import TONES             # noqa: E402


class PreferenceBody(BaseModel):
    """Thân yêu cầu cập nhật. Mọi trường đều tuỳ chọn — client gửi cái nào sửa cái đó,
    không phải gửi lại toàn bộ. Trần độ dài đặt ở đây vì nội dung này đi thẳng vào
    system prompt: không giới hạn thì một chữ ký dài vài nghìn từ sẽ đẩy prompt phình
    ra mỗi lượt chat, vừa tốn hạn ngạch vừa làm loãng phần chỉ dẫn quan trọng."""
    language: str | None = Field(None, max_length=8)
    display_name: str | None = Field(None, max_length=80)
    theme: str | None = Field(None, max_length=16)
    tone_preference: str | None = None
    signature_note: str | None = Field(None, max_length=500)
    custom_instruction: str | None = Field(None, max_length=1000)


def _pref_out(pref) -> dict:
    return {
        "language": pref.language,
        "displayName": pref.display_name,
        "theme": pref.theme,
        "tonePreference": pref.tone_preference,
        "signatureNote": pref.signature_note,
        "customInstruction": pref.custom_instruction,
        # Trả kèm bản kết tinh để giao diện cho người dùng XEM TRƯỚC đúng thứ mà trợ lý
        # sẽ đọc. Không có nó thì người dùng gõ vào một ô rồi đoán xem có tác dụng gì.
        "promptPreview": pref.to_prompt_context(),
        "availableTones": TONES,
    }


@app.get("/me/preferences")
def get_preferences(session: AuthSession = Depends(get_current_session),
                    db: Session = Depends(get_db)):
    return _pref_out(user_preference_repo.get_or_create(db, session.user_id))


@app.patch("/me/preferences")
def update_preferences(body: PreferenceBody,
                       session: AuthSession = Depends(get_current_session),
                       db: Session = Depends(get_db)):
    if body.tone_preference is not None and body.tone_preference not in TONES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Giọng văn không hợp lệ. Chọn một trong: {', '.join(TONES)}")

    # exclude_unset: chỉ lấy trường client THẬT SỰ gửi. Thiếu nó thì mọi trường không
    # gửi sẽ về None và xoá sạch thiết lập cũ của người dùng — mất dữ liệu âm thầm.
    pref, da_doi = user_preference_repo.update(
        db, session.user_id, body.model_dump(exclude_unset=True))

    if da_doi:
        audit_repo.log(db, user_id=session.user_id, action="update_preferences",
                       actor_type="user", details={"fields": da_doi})
    return _pref_out(pref)


# ── Gửi tệp đính kèm: nhận FILE upload từ frontend (multipart/form-data) ──
# `file: UploadFile = File(...)` → FastAPI đọc tệp từ form-data (cần python-multipart).
# Nấc 8: GIỮ CẢ BYTES trong upload_store → khi bấm Gửi sẽ lấy ra đính vào email.
@app.post("/uploads")
async def upload_file(
    file: UploadFile = File(...),
    session: AuthSession = Depends(get_current_session),  # cần đăng nhập mới được upload
):
    content = await file.read()  # đọc toàn bộ nội dung tệp (dạng bytes)
    # NFR-Memory/Security: chặn tệp quá trần — không giới hạn thì 1 tệp 2GB = 2GB RAM (DoS).
    from app.core.config import settings
    if len(content) > settings.upload_max_mb * 1024 * 1024:
        raise HTTPException(status_code=413,
                            detail=f"Tệp vượt quá {settings.upload_max_mb}MB cho phép.")
    # Cất vào kho tạm; trả {id, name, size} để FE GIỮ `id` rồi gửi kèm khi soạn xong.
    return upload_store.save(file.filename or "tep", content, file.content_type)


# ── Gộp frontend (tuỳ chọn) — PHẢI đặt CUỐI FILE ────────────────────────────
# Starlette duyệt route theo đúng thứ tự đăng ký, nên bộ bắt-tất-cả của SPA phải
# nằm sau mọi route API. Đặt nhầm lên trên là API bị nuốt sạch.
#
# Không có thư mục build thì hàm này lặng lẽ bỏ qua — backend chạy y như trước.
# Nhờ vậy Vercel vẫn là đường chính (đúng sơ đồ PA2 §1.1), còn đây là đường dự
# phòng khi cần một URL duy nhất.
from app.api.spa import gan_frontend  # noqa: E402

# MCP-HTTP mount TRƯỚC bộ bắt-tất-cả của SPA, cùng lý do như trên: đăng ký sau thì
# /mcp/rpc bị SPA nuốt và trả về trang HTML thay vì giao thức MCP.
_gan_mcp_http()

gan_frontend(app, settings.frontend_dist or None)
