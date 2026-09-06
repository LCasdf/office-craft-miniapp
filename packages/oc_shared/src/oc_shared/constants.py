"""Cross-cutting constants (no framework imports)."""

AI_TEXT_MAX_CHARS = 2000
DEFAULT_TASK_TIMEOUT_SECONDS = 180
MAX_INFLIGHT_TASKS_PER_USER = 3
UPLOAD_CREDENTIAL_TTL_SECONDS = 900
DOWNLOAD_URL_TTL_SECONDS = 900
IDEMPOTENCY_WINDOW_HOURS = 24

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
