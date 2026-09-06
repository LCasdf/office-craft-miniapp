from enum import StrEnum


class TaskType(StrEnum):
    IMAGE_TO_PDF = "image_to_pdf"
    PDF_COMPRESS = "pdf_compress"
    PDF_MERGE = "pdf_merge"
    OFFICE_TO_PDF = "office_to_pdf"
    PPT_GENERATE = "ppt_generate"
    NOVEL_CHAPTER = "novel_chapter"
    CHARACTER_CARD = "character_card"


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorClass(StrEnum):
    USER = "user"
    SYSTEM = "system"
    TIMEOUT = "timeout"
    SAFETY = "safety"


class QuotaSettled(StrEnum):
    """Stored as tinyint in DB; string names for clarity in code."""

    FROZEN = "0"
    CHARGED = "1"
    REFUNDED = "2"
