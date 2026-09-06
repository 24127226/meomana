from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Annotated, Any, Literal

from app.core.van_ban import sua_xuong_dong


# =========================================================
# =                     Shared Enum                       =
# =========================================================

class EmailCategory(str, Enum):
    SPAM = "Spam"
    SCHOOL = "School"
    FINANCE = "Finance"
    CAREER = "Career"
    PERSONAL = "Personal"

class EmailPriority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class EmailStatus(str, Enum):
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    DONE = "Done"

class BulkAction(str, Enum):
    # (SỬA BUG) Trước đây DELETE = "Delete" (viết hoa) trong khi 4 giá trị kia thường và
    # chính description của field ghi 'delete' → LLM truyền "delete" là ValidationError,
    # lệnh xoá hàng loạt KHÔNG chạy được. Chuẩn hoá về thường; BulkActionInput có validator
    # case-insensitive nên "Delete"/"DELETE" kiểu cũ vẫn được nhận.
    DELETE = "delete"
    MARK_READ = "mark_read"
    MARK_UNMARKED = "mark_unread"
    APPLY_LABEL = "apply_label"
    REMOVE_LABEL = "remove_label"
    # Xoá đã là xoá MỀM (vào thùng rác) nên luôn cứu được — nhưng chỉ khi người dùng
    # tự vào Gmail bới. Trợ lý xoá hộ thì phải hoàn tác hộ được, nếu không thì
    # "hoàn tác được" chỉ đúng trên giấy.
    RESTORE = "restore"
    # Thư rác: hai chiều, và CẢ HAI đều đảo ngược được nên không cần cổng xác nhận.
    # Gắn nhầm rác còn gỡ ra được; dựng thêm một hàng rào ở đây chỉ làm người dùng
    # quen bấm-cho-qua, rồi tới lúc gặp cổng THẬT (gửi/xoá) họ cũng bấm-cho-qua.
    SPAM = "spam"
    NOT_SPAM = "not_spam"


# =========================================================
# =               Shared Output Primitives                =
# =========================================================

class EmailSummary(BaseModel):
    """Lightweight email representation
    - Dùng trong list result, không kéo full body email
    """
    id: str
    thread_id: str
    sender: str
    subject: str
    recipient: list[str]
    date: datetime
    snippet: str        # Xem trước 200 từ
    is_read: bool
    labels: list[str] = []
    category: EmailCategory | None = None
    priority: EmailPriority | None = None
    status: EmailStatus | None = None

class EmailDetail(BaseModel):
    """Full Email
    - Dùng khi agent cần đọc nội dung để summarize hoặc reply
    """
    body_text: str
    body_html: str | None = None
    attachments: list[str] = []
    cc: list[str] = []
    bcc: list[str] = []

class ToolResult(BaseModel):
    """Base wrapper cho mọi tool output
    - Giúp tool_node serialize nhất quán
    """
    success: bool
    message: str = ""   # Human-readable summary cho LLM evaluate
    data: Any = None    # Payload thật



# =========================================================
# =                   READ tools I/O                      =
# =========================================================

class SearchEmailsInput(BaseModel):
    """Input for search_emails tool
    LLM điền các field này dựa vào user request
    """
    query: Annotated[str, Field(
        description="Natural language or Gmail search syntax query. "
                    "Examples: 'emails from boss this week', 'from:hr@company.com subject:offer'"
    )] = ""

    category: Annotated[EmailCategory | None, Field(
        description="Filter by auto-classified category. "
                    "Use when user mentions 'spam', 'school emails', 'finance', etc.",
    )] = None

    is_read: Annotated[bool | None, Field(
        description="True = read only, False = unread only, None = both.",
    )] = None

    limit: Annotated[int, Field(
        ge=1, le=50,
        description="Max number of emails to return. Default 10. "
                    "Use higher values for bulk operations.",
    )] = 10

    date_from: Annotated[datetime | None, Field(
        description="Start date filter (inclusive). ISO 8601 format.",
    )] = None

    date_to: Annotated[datetime | None, Field(
        description="End date filter (inclusive). ISO 8601 format.",
    )] = None

    @model_validator(mode="after")
    def validate_date_range(self) -> SearchEmailsInput:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before date_to")
        return self


class SemanticSearchInput(BaseModel):
    """Input for semantic_search tool — tìm theo Ý NGHĨA (embedding re-rank),
    dùng khi người dùng mô tả CHỦ ĐỀ mơ hồ thay vì từ khoá chính xác
    (vd 'thư về tiền nong', 'liên quan bảo mật tài khoản')."""

    query: Annotated[str, Field(
        min_length=2,
        description="Mô tả điều cần tìm bằng ngôn ngữ tự nhiên (tiếng Việt hoặc Anh đều được).",
    )]

    limit: Annotated[int, Field(
        ge=1, le=20,
        description="Số thư khớp nhất muốn lấy. Mặc định 5.",
    )] = 5

    pool: Annotated[int, Field(
        ge=5, le=50,
        description="Số thư GẦN NHẤT đem ra so nghĩa (ứng viên). Mặc định 30.",
    )] = 30


class SearchEmailsOutput(ToolResult):
    data: list[EmailSummary] = []
    total_found: int = 0


class CategorizeEmailsInput(BaseModel):
    """Input for categorize_emails — tự ĐỀ XUẤT nhãn cho các thư gần nhất (UC009).
    KHÔNG áp nhãn ngay: chỉ trả đề xuất để người dùng duyệt (human-in-the-loop)."""

    limit: Annotated[int, Field(
        ge=1, le=100,
        # Trần cũ là 50. Người dùng nói "xoá các thư Cá nhân" thì họ muốn nói CẢ NHÓM,
        # nhưng tool chỉ soát 20 thư gần nhất nên thẻ hiện ra "Xoá 2 thư" — và họ tưởng
        # nhóm đó chỉ có 2. Đo trên hộp thư 68 thư: nhóm Cá nhân có 12, thẻ báo 2.
        # Mặc định vẫn 20 cho câu hỏi thường (rẻ, nhanh); thao tác trên CẢ NHÓM thì
        # agent được dặn nâng lên — xem mục tương ứng trong system prompt.
        description="Số thư gần nhất cần phân loại. Mặc định 20. Khi người dùng muốn "
                    "thao tác trên CẢ MỘT NHÓM (vd 'xoá các thư Cá nhân'), đặt 100 "
                    "để không bỏ sót.",
    )] = 20

    query: Annotated[str, Field(
        description="Lọc trước bằng cú pháp Gmail (rỗng = hộp thư đến gần nhất).",
    )] = ""


class CategorizedItem(BaseModel):
    id: str
    thread_id: str
    sender: str
    subject: str
    label: str          # tên nhãn ĐỀ XUẤT (chính là tên nhãn sẽ áp lên Gmail)
    category: str       # màu chip FE: moss/sea/sun/cherry/sky/terra/wine/jade
    confidence: str     # high | medium | low
    reason: str         # vì sao đề xuất nhãn này (để người dùng tin/sửa)


class CategorizeEmailsOutput(ToolResult):
    data: list[CategorizedItem] = []
    summary: dict[str, int] = {}   # đếm số thư theo từng nhãn


class GetEmailInput(BaseModel):
    email_id: Annotated[str, Field(
        description="Gmail message ID or Outlook message ID. "
                    "Get this from search_emails results.",
    )]


class GetEmailOutput(ToolResult):
    data: EmailDetail | None = None


class SummarizeEmailInput(BaseModel):
    email_id: Annotated[str, Field(
        description="ID of the email to summarize.",
    )]

    focus: Annotated[str, Field(
        description="What to focus on in the summary. "
                    "Examples: 'action items', 'deadlines', 'key decisions', 'tone and intent'",
    )] = "key points and action items"


class SummarizeEmailOutput(ToolResult):
    data: str | None = None   # The summary text


class ListLabelsInput(BaseModel):
    """No required params — trả về toàn bộ labels của user's mailbox."""
    pass


class ListLabelsOutput(ToolResult):
    data: list[str] = []



# =========================================================
# =                   WRITE tools I/O                     =
# =========================================================

class DraftEmailInput(BaseModel):
    """
    Tạo email draft — lưu vào Drafts folder, chưa gửi.
    Dùng cho: (1) email mới hoàn toàn, (2) draft reply để review trước khi send.
    Để send ngay lập tức, dùng send_email hoặc reply_email thay thế.
    """

    # ── Context: new mail hay reply/forward? ──────────────────────────────────
    # Ba trường này xác định "loại" draft. Agent phải điền đúng case.

    reply_to_id: Annotated[str | None, Field(
        description="Email ID being replied to. When set, 'to' field is optional — "
                    "recipients are inherited from the original thread. "
                    "Set reply_all=True to include all original recipients in To/Cc.",
    )] = None

    reply_all: Annotated[bool, Field(
        description="Only relevant when reply_to_id is set. "
                    "True = reply to all original recipients (To + Cc). "
                    "False = reply to sender only.",
    )] = False

    forward_from_id: Annotated[str | None, Field(
        description="Email ID being forwarded. When set, original email body is "
                    "quoted and attachments are included automatically. "
                    "Mutually exclusive with reply_to_id.",
    )] = None

    # ── Recipients ────────────────────────────────────────────────────────────

    to: Annotated[list[str], Field(
        description="Primary recipient email addresses. "
                    "REQUIRED for new emails. "
                    "OPTIONAL when reply_to_id is set — leave empty to use original sender. "
                    "Use when adding extra recipients beyond the original thread.",
    )] = []

    cc: Annotated[list[str], Field(
        description="Carbon copy recipients — receive the email but are not the primary audience. "
                    "Use when someone needs to be kept in the loop (e.g., a manager, a team). "
                    "LLM should infer from context: 'keep my manager in the loop' → add manager to cc.",
    )] = []

    bcc: Annotated[list[str], Field(
        description="Blind carbon copy — recipients hidden from each other and from To/Cc recipients. "
                    "Use for: mass emails, privacy-sensitive sends, or when user explicitly requests bcc.",
    )] = []

    # ── Content ───────────────────────────────────────────────────────────────

    subject: Annotated[str, Field(
        description="Email subject line. "
                    "REQUIRED for new emails. "
                    "OPTIONAL when reply_to_id or forward_from_id is set — "
                    "defaults to 'Re: <original subject>' or 'Fwd: <original subject>'.",
    )] = ""

    instructions: Annotated[str, Field(
        description="What the email should say. Bullet points, rough notes, or full prose. "
                    "Agent expands and polishes this into the final body.",
        min_length=1,
    )]

    tone: Annotated[str, Field(
        description="Desired tone: 'formal', 'casual', 'assertive', 'empathetic'. "
                    "Infer from context if not stated — academic/work context defaults to 'formal'.",
    )] = "formal"

    language: Annotated[str, Field(
        description="Language for the email body. 'vi' for Vietnamese, 'en' for English. "
                    "Infer from the language the user is writing in.",
    )] = "en"

    attachment_filenames: Annotated[list[str], Field(
        description="Filenames the user mentioned attaching. "
                    "Actual file content is resolved by email_service. "
                    "Example: ['Q3_report.pdf', 'invoice_oct.xlsx']",
    )] = []

    # ── Validators ────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_draft_context(self) -> DraftEmailInput:
        is_reply = self.reply_to_id is not None
        is_forward = self.forward_from_id is not None

        # Mutually exclusive
        if is_reply and is_forward:
            raise ValueError("reply_to_id and forward_from_id are mutually exclusive")

        # New email phải có `to`
        if not is_reply and not is_forward and not self.to:
            raise ValueError(
                "to is required for new emails. "
                "Only omit 'to' when reply_to_id is set."
            )

        # New email phải có subject
        if not is_reply and not is_forward and not self.subject:
            raise ValueError(
                "subject is required for new emails. "
                "Only omit subject when reply_to_id or forward_from_id is set."
            )

        # reply_all chỉ có nghĩa khi có reply_to_id
        if self.reply_all and not is_reply:
            raise ValueError("reply_all=True requires reply_to_id to be set")

        return self

    @field_validator("to", "cc", "bcc", mode="before")
    @classmethod
    def normalize_addresses(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v


class DraftEmailOutput(ToolResult):
    data: dict[str, Any] | None = None  # {subject, body, to, cc, bcc}


class SendEmailInput(BaseModel):
    to: Annotated[list[str], Field(
        description="Recipient email addresses.",
        min_length=1,
    )]

    subject: Annotated[str, Field(min_length=1)]

    body: Annotated[str, Field(
        description="Final email body to send. Must be the confirmed, polished version.",
        min_length=1,
    )]

    cc: list[str] = []
    bcc: list[str] = []

    @field_validator("to", "cc", "bcc", mode="before")
    @classmethod
    def normalize_addresses(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v

    # Mô hình hay viết ra HAI KÝ TỰ `\` và `n` thay vì xuống dòng thật khi phải đặt
    # một chuỗi nhiều dòng vào tham số JSON. Thư gửi đi rồi thì không rút lại được,
    # nên chặn ở đây chứ không chỉ dặn thêm trong prompt. Xem `core/van_ban.py`.
    _go_thoat_body = field_validator("body", mode="before")(sua_xuong_dong)


class SendEmailOutput(ToolResult):
    data: dict[str, str] | None = None  # {message_id, thread_id}


class ReplyEmailInput(BaseModel):
    email_id: Annotated[str, Field(
        description="ID of the email being replied to. Thread context is preserved automatically.",
    )]

    instructions: Annotated[str, Field(
        description="What the reply should say. Agent will generate full reply from this.",
    )]

    tone: str = "formal"
    reply_all: Annotated[bool, Field(
        description="True to reply-all, False to reply only to sender.",
    )] = False

    # `instructions` được gửi đi NGUYÊN VĂN làm thân thư trả lời (xem docstring của
    # tool `reply_email`), nên chịu đúng lỗi chuỗi thoát như `SendEmailInput.body`.
    _go_thoat_instructions = field_validator("instructions", mode="before")(sua_xuong_dong)


class ForwardEmailInput(BaseModel):
    """Chuyển tiếp một thư sang địa chỉ khác.

    KHÁC `reply_email` ở chỗ căn bản: trả lời là nói tiếp với NGƯỜI ĐÃ VIẾT cho mình,
    còn chuyển tiếp là đưa nội dung đó cho NGƯỜI THỨ BA. Nên `to` là bắt buộc và không
    suy ra được từ thư gốc — đoán bừa người nhận ở đây là gửi thư của người khác cho
    một người không liên quan.
    """

    email_id: Annotated[str, Field(description="ID of the email to forward.")]
    to: Annotated[str, Field(
        description="Recipient email address. REQUIRED — never guess it from the original "
                    "email; ask the user if unknown.",
    )]
    note: Annotated[str, Field(
        description="Optional short note placed above the forwarded content.",
    )] = ""

    _go_thoat_note = field_validator("note", mode="before")(sua_xuong_dong)


class ForwardEmailOutput(ToolResult):
    data: dict[str, str] | None = None  # {message_id, thread_id}


class ReplyEmailOutput(ToolResult):
    data: dict[str, str] | None = None  # {message_id, thread_id}



# =========================================================
# =                 MANAGEMENT tools I/O                  =
# =========================================================

class ApplyLabelsInput(BaseModel):
    email_ids: Annotated[list[str], Field(
        description="List of email IDs to apply labels to.",
        min_length=1,
    )]

    labels_to_add: Annotated[list[str], Field(
        description="Label names to add. For category labels use: 'Spam', 'School', 'Career', "
                    "'Finance', 'Personal'. Can also use custom labels.",
    )] = []

    labels_to_remove: Annotated[list[str], Field(
        description="Label names to remove. Use exact label name as it appears "
                    "in the mailbox. Use list_labels to check available labels first.",
    )] = []

    @model_validator(mode="after")
    def at_least_one_action(self) -> ApplyLabelsInput:
        if not self.labels_to_add and not self.labels_to_remove:
            raise ValueError("Must specify at least one label to add or remove")
        return self


class ApplyLabelsOutput(ToolResult):
    data: dict[str, Any] | None = None  # {modified_count, failed_ids}


class BulkActionInput(BaseModel):
    email_ids: Annotated[list[str], Field(
        description="List of email IDs to perform the action on.",
        min_length=1,
        max_length=100,   # Hard limit — tránh LLM hallucinate xóa cả mailbox
    )]

    action: Annotated[BulkAction, Field(
        description="Action to perform: 'delete', 'restore', 'mark_read', 'mark_unread', "
                    "'apply_label', 'remove_label'. Use 'restore' to bring messages "
                    "back from Trash after a delete.",
    )]

    label_name: Annotated[str | None, Field(
        description="Required when action is 'apply_label' or 'remove_label'. "
                    "Use list_labels to verify label exists before bulk operations.",
    )] = None

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, v: Any) -> Any:
        """LLM hay viết hoa tuỳ hứng ('Delete'/'DELETE') → hạ về thường cho khớp enum."""
        return v.lower() if isinstance(v, str) else v

    @model_validator(mode="after")
    def validate_label_required(self) -> BulkActionInput:
        if self.action in (BulkAction.APPLY_LABEL, BulkAction.REMOVE_LABEL) and not self.label_name:
            raise ValueError(f"label_name is required when action is '{self.action.value}'")
        return self


class BulkActionOutput(ToolResult):
    data: dict[str, Any] | None = None  # {success_count, failed_count, failed_ids}



# =========================================================
# =                  SYSTEM tools I/O                     =
# =========================================================

class ClarificationQuestion(BaseModel):
    """Một câu hỏi đơn lẻ trong một lần clarification."""
    question: Annotated[str, Field(
        description="The clarifying question. Be specific about what is needed and why.",
    )]

    options: Annotated[list[str], Field(
        description="Suggested quick-reply options. Empty for open-ended questions.",
    )] = []

    required: Annotated[bool, Field(
        description="True if this question must be answered before proceeding. "
                    "False if agent can make a reasonable default assumption.",
    )] = True


class AskClarificationInput(BaseModel):
    questions: Annotated[list[ClarificationQuestion], Field(
        description="One or more clarifying questions to ask the user in a single round-trip. "
                    "Batch all missing information into one call instead of asking "
                    "one question at a time.",
        min_length=1,
        max_length=5,
    )]

    context: Annotated[str, Field(
        description="Brief explanation of why clarification is needed. "
                    "Shown to user as preamble before the questions. "
                    "Example: 'I need a few details before drafting this email.'",
    )] = ""


class AskClarificationOutput(ToolResult):
    """Frontend renders question + options, waits for user reply."""
    data: dict[str, Any] | None = None  # {question, options}


class RequestConfirmationInput(BaseModel):
    action_summary: Annotated[str, Field(
        description="Human-readable summary of what will happen if user confirms. "
                    "Be explicit about scope and irreversibility. "
                    "Example: 'Delete 47 emails matching spam filter. This cannot be undone.'",
    )]

    affected_items: Annotated[list[str], Field(
        description="List of email IDs or descriptions of items affected by this action.",
    )]

    action_type: Annotated[str, Field(
        description="Type of action: 'delete', 'send', 'reply', 'bulk_delete', etc.",
    )]


class RequestConfirmationOutput(ToolResult):
    """
    Frontend renders confirmation dialog.
    Agent pauses — user response (yes/no) comes back as next chat message.
    """
    data: dict[str, Any] | None = None  # {action_summary, affected_items, action_type}

# =========================================================
# =            RANH GIỚI NĂNG LỰC (Chặn 01)               =
# =========================================================

class NgoaiPhamViInput(BaseModel):
    """Tham số cho `tu_choi_ngoai_pham_vi`."""

    viec_nguoi_dung_muon: Annotated[str, Field(
        description="Điều người dùng thực sự yêu cầu, viết lại bằng một câu ngắn. "
                    "Ví dụ: 'đặt vé máy bay SGN đi Đà Nẵng ngày 12/9'.",
    )]

    vi_sao_khong_lam_duoc: Annotated[str, Field(
        description="Lý do CỤ THỂ, nói theo góc nhìn người dùng. "
                    "Ví dụ: 'MeoArc chưa kết nối với hệ thống bán vé nào'. "
                    "Đừng nói chung chung kiểu 'tôi không thể'.",
    )]

    viec_gan_nhat_lam_duoc: Annotated[str | None, Field(
        default=None,
        description="Việc gần nhất MeoArc LÀM ĐƯỢC và có ích cho ý định đó. "
                    "Ví dụ: 'tìm trong hộp thư các thư xác nhận vé đã đặt trước đó'. "
                    "Để trống nếu thật sự không có gì liên quan — đừng bịa cho có.",
    )]


class NgoaiPhamViOutput(ToolResult):
    data: dict[str, Any] | None = None


# =========================================================
# =              LỊCH TRÌNH / CAM KẾT (Chặn 02)           =
# =========================================================

class LietKeCamKetInput(BaseModel):
    """Tham số cho `liet_ke_cam_ket`."""

    so_ngay_toi: Annotated[int, Field(
        default=14,
        ge=1, le=90,
        description="Chỉ lấy việc có hạn trong bao nhiêu ngày tới. Mặc định 14.",
    )]

    chi_con_han: Annotated[bool, Field(
        default=True,
        description="True = bỏ qua việc đã xong và việc đã quá hạn. "
                    "False = lấy hết, kể cả việc đã trễ.",
    )]


class CamKetItem(BaseModel):
    noi_dung: str
    han: str | None = None
    bat_dau: str | None = None
    han_suy_ra: bool = False
    nguoi_cho: str = ""
    email_id: str = ""
    # Tiêu đề + người gửi của LÁ THƯ SINH RA việc này. Chỉ có `email_id` thì giao diện
    # vẽ được một cái nút không có chữ — người dùng phải bấm mới biết mình sắp mở gì.
    tieu_de: str = ""
    nguoi_gui: str = ""
    uoc_luong_phut: int = 0
    muc_uu_tien: int = 1
    do_tin_cay: float = 0.9


class LietKeCamKetOutput(ToolResult):
    data: list[CamKetItem] = []


class ApLucLichTrinhInput(BaseModel):
    """Tham số cho `ap_luc_lich_trinh`."""

    # ── "TUẦN NÀY" KHÔNG PHẢI "7 NGÀY TỚI" ──
    # Hai khái niệm khác hẳn nhau và người dùng phân biệt rất rõ. Hỏi hôm thứ Tư mà
    # trả lời tới thứ Ba tuần sau là trả lời một câu KHÁC với câu được hỏi — và người
    # dùng không có cách nào biết mình vừa nhận thông tin của một khoảng khác.
    pham_vi: Annotated[
        Literal["tuan_nay", "tuan_sau", "n_ngay"],
        Field(
            default="n_ngay",
            description=(
                "'tuan_nay' = TỪ HÔM NAY ĐẾN HẾT CHỦ NHẬT tuần này — dùng khi người "
                "dùng nói 'tuần này'. 'tuan_sau' = trọn thứ Hai→Chủ nhật tuần kế. "
                "'n_ngay' = cửa sổ trượt `so_ngay` ngày tới, dùng khi họ nói 'mấy ngày "
                "tới', 'sắp tới', hoặc không nói rõ."
            ),
        ),
    ] = "n_ngay"

    so_ngay: Annotated[int, Field(
        default=7, ge=1, le=30,
        description="Chỉ dùng khi pham_vi='n_ngay'. Số ngày tới. Mặc định 7.",
    )]


class ApLucLichTrinhOutput(ToolResult):
    data: list[dict[str, Any]] = []


# =========================================================
# =            Ý ĐỊNH ĐI LẠI (Giai đoạn 1)                =
# =========================================================

class DeXuatDiLaiInput(BaseModel):
    """Tham số cho `de_xuat_di_lai`."""

    so_ngay_toi: Annotated[int, Field(
        default=30, ge=1, le=90,
        description="Chỉ xét việc có hạn trong bao nhiêu ngày tới. Mặc định 30.",
    )]

    tu_thanh_pho: Annotated[str, Field(
        default="SGN",
        description="Mã sân bay nơi người dùng khởi hành. Mặc định SGN (TP.HCM).",
    )]


class DeXuatDiLaiOutput(ToolResult):
    data: list[dict[str, Any]] = []


# =========================================================
# =        TRA CỨU CHUYẾN BAY / PHÒNG (Giai đoạn 2)       =
# =========================================================

class TimChuyenBayInput(BaseModel):
    """Tham số cho `tim_chuyen_bay`. CHỈ TRA CỨU — không đặt."""

    tu: Annotated[str, Field(
        description="Mã sân bay đi, 3 chữ in hoa. VD: SGN (TP.HCM), HAN (Hà Nội).",
        min_length=3, max_length=3,
    )]
    den: Annotated[str, Field(
        description="Mã sân bay đến, 3 chữ in hoa. VD: DAD (Đà Nẵng).",
        min_length=3, max_length=3,
    )]
    ngay: Annotated[str, Field(
        description="Ngày bay dạng dd/mm/yyyy. VD: 16/09/2026.",
    )]
    so_ket_qua: Annotated[int, Field(default=3, ge=1, le=10)]


class TimChuyenBayOutput(ToolResult):
    data: list[dict[str, Any]] = []


class TimKhachSanInput(BaseModel):
    """Tham số cho `tim_khach_san`. CHỈ TRA CỨU — không đặt."""

    thanh_pho: Annotated[str, Field(description="Tên thành phố. VD: Đà Nẵng.")]
    nhan_phong: Annotated[str, Field(description="Ngày nhận phòng dd/mm/yyyy.")]
    tra_phong: Annotated[str, Field(description="Ngày trả phòng dd/mm/yyyy.")]
    so_ket_qua: Annotated[int, Field(default=3, ge=1, le=10)]


class TimKhachSanOutput(ToolResult):
    data: list[dict[str, Any]] = []


# =========================================================
# =      ĐẶT CHỖ MÔ PHỎNG — đi qua CỔNG TIỀN (GĐ 3)       =
# =========================================================

class DatChoMoPhongInput(BaseModel):
    """Tham số cho `dat_cho_mo_phong`. Đi qua cổng xác nhận và cổng tiền."""

    loai: Annotated[str, Field(
        description="'chuyen_bay' hoặc 'khach_san'.",
    )]
    mo_ta: Annotated[str, Field(
        description="Một câu người đọc hiểu, đủ để duyệt mà không cần mở gì khác. "
                    "VD: 'VN123 SGN→DAD 16/09 06:20, 1 khách'.",
    )]
    so_tien_vnd: Annotated[int, Field(
        ge=1,
        description="Tổng tiền, đồng. Vượt trần thì cổng tiền từ chối.",
    )]
    ma_lua_chon: Annotated[str, Field(
        description="Mã chuyến bay / mã khách sạn lấy từ kết quả tra cứu. "
                    "Đây là thứ phân biệt đơn này với đơn khác, nên PHẢI chính xác.",
    )]
    ngay: Annotated[str, Field(description="Ngày dd/mm/yyyy.")]
    hoan_duoc: Annotated[bool, Field(
        default=False,
        description="Lựa chọn này có hoàn/huỷ miễn phí không. Không chắc thì để False — "
                    "nói 'hoàn được' mà thật ra không hoàn là dẫn người dùng tới quyết "
                    "định tiền bạc dựa trên thông tin bịa.",
    )]


class DatChoMoPhongOutput(ToolResult):
    data: dict[str, Any] | None = None


# =========================================================
# =   TÓM TẮT NGÀY & PHÂN LOẠI ƯU TIÊN — TẤT ĐỊNH, 0 LLM   =
# =========================================================
# Hai tính năng này TỪNG chỉ tồn tại ở giao diện mock: `DigestWidget` và
# `TriageWidget` có sẵn, nhưng backend thật KHÔNG có tool nào sinh ra chúng. Nên bấm
# "Digest hôm nay" / "Triage hộp thư" thì agent không có gì để gọi và rơi về
# categorize_emails — đúng triệu chứng "bấm Triage mà nó lại phân loại thư".
#
# Cả hai dựng bằng LUẬT (app/core/labeling.analyze), KHÔNG gọi model: chúng chỉ là
# đếm và nhóm trên dữ liệu đã có. Gọi model ở đây vừa tốn hạn mức vừa cho kết quả
# kém ổn định hơn — cùng một hộp thư mà mỗi lần bấm ra một con số khác thì không ai
# tin nổi bảng thống kê đó.

class TomTatNgayInput(BaseModel):
    """Tham số cho `tom_tat_ngay` (Daily Digest)."""

    so_ngay: Annotated[int, Field(default=1, ge=1, le=30,
                                  description="Tính thư trong bao nhiêu ngày gần đây. Mặc định 1 (hôm nay).")]
    limit: Annotated[int, Field(default=60, ge=5, le=200)]


class TomTatNgayOutput(ToolResult):
    data: dict[str, Any] = {}


class PhanLoaiUuTienInput(BaseModel):
    """Tham số cho `phan_loai_uu_tien` (Triage Inbox)."""

    chi_chua_doc: Annotated[bool, Field(default=True,
                                        description="Chỉ xét thư CHƯA ĐỌC. Mặc định true.")]
    limit: Annotated[int, Field(default=40, ge=5, le=100)]


class PhanLoaiUuTienOutput(ToolResult):
    data: dict[str, Any] = {}
