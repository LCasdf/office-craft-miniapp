"""Cross-cutting constants (no framework imports)."""

AI_TEXT_MAX_CHARS = 2000
DEFAULT_TASK_TIMEOUT_SECONDS = 180
MAX_INFLIGHT_TASKS_PER_USER = 3
UPLOAD_CREDENTIAL_TTL_SECONDS = 900
DOWNLOAD_URL_TTL_SECONDS = 900
IDEMPOTENCY_WINDOW_HOURS = 24
INPUT_TTL_SECONDS = 6 * 3600
OUTPUT_TTL_SECONDS = 24 * 3600

IMAGE_TO_PDF_MAX_COUNT = 20
IMAGE_TO_PDF_MAX_BYTES = 10 * 1024 * 1024
IMAGE_TO_PDF_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
OFFICE_TO_PDF_EXTS = frozenset({".doc", ".docx", ".odt", ".rtf"})
PDF_EXTS = frozenset({".pdf"})
PDF_COMPRESS_MAX_BYTES = 50 * 1024 * 1024
PDF_COMPRESS_QUALITIES = frozenset({"high", "standard", "extreme"})
PDF_MERGE_MIN_COUNT = 2
PDF_MERGE_MAX_COUNT = 10
PDF_MERGE_MAX_FILE_BYTES = 30 * 1024 * 1024
PDF_MERGE_MAX_TOTAL_BYTES = 50 * 1024 * 1024
PDF_MERGE_MAX_PAGES = 200

# Per-type processing timeouts (seconds), aligned with blueprint §4.3
TASK_TIMEOUTS: dict[str, int] = {
    "image_to_pdf": 60,
    "pdf_compress": 60,
    "pdf_merge": 120,
    "office_to_pdf": 180,
    "character_card": 120,
    "ppt_generate": 120,
    "novel_chapter": 120,
}

# Default quota costs
TASK_COST_QUOTA: dict[str, int] = {
    "image_to_pdf": 1,
    "pdf_compress": 1,
    "pdf_merge": 2,
    "office_to_pdf": 2,
    "character_card": 3,
    "ppt_generate": 5,
    "novel_chapter": 4,
}

QUEUE_TOOLS = "q.tools"
QUEUE_AI = "q.ai"
