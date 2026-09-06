"""Office Craft shared package: enums, errors, schemas."""

from oc_shared.constants import AI_TEXT_MAX_CHARS, DEFAULT_TASK_TIMEOUT_SECONDS
from oc_shared.enums import ErrorClass, QuotaSettled, TaskStatus, TaskType
from oc_shared.error_codes import ErrorCode, get_error

__all__ = [
    "AI_TEXT_MAX_CHARS",
    "DEFAULT_TASK_TIMEOUT_SECONDS",
    "ErrorClass",
    "ErrorCode",
    "QuotaSettled",
    "TaskStatus",
    "TaskType",
    "get_error",
]
