"""Error code catalog — single source of truth (dev spec §5.4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class ErrorDef:
    code: int
    message: str
    user_msg: str
    http_status: int


class ErrorCode(Enum):
    OK = ErrorDef(0, "ok", "ok", 200)
    PARAM_INVALID = ErrorDef(40001, "param_invalid", "参数有误，请检查后重试", 400)
    FILE_TOO_LARGE = ErrorDef(40002, "file_too_large", "文件过大，请压缩后再上传", 400)
    QUOTA_EXHAUSTED = ErrorDef(40003, "quota_exhausted", "今日额度已用完，明天再来或开通会员", 400)
    PDF_ENCRYPTED = ErrorDef(40004, "pdf_encrypted", "含加密 PDF，请先解除保护", 400)
    TOO_MANY_INFLIGHT = ErrorDef(
        40005, "too_many_inflight_tasks", "进行中的任务已满（最多3个），请先到任务中心查看", 400
    )
    IDEMPOTENCY_CONFLICT = ErrorDef(
        40007,
        "idempotency_key_conflict",
        "重复提交的内容与首次不一致，请勿复用同一幂等键",
        400,
    )
    IDEMPOTENCY_REQUIRED = ErrorDef(40008, "idempotency_key_required", "缺少幂等键，请重试", 400)
    TASK_NOT_FOUND = ErrorDef(40009, "task_not_found", "任务不存在或无权访问", 404)
    TASK_NOT_RETRYABLE = ErrorDef(40010, "task_not_retryable", "当前任务不可重试", 400)
    TASK_NOT_CANCELLABLE = ErrorDef(40011, "task_not_cancellable", "任务已结束，无法取消", 400)
    OUTLINE_VERSION_MISMATCH = ErrorDef(
        40012, "outline_version_mismatch", "大纲已变更，请重新确认后再生成", 400
    )
    INPUT_TOO_LONG = ErrorDef(40013, "input_too_long", "设定过长，请精简后再试", 400)
    CHAPTER_LIMIT = ErrorDef(40014, "chapter_limit_exceeded", "章节数量已达上限", 400)
    PROJECT_VERSION_MISMATCH = ErrorDef(
        40015, "project_version_mismatch", "作品已更新，请刷新后重试", 400
    )
    RESULT_EXPIRED = ErrorDef(40016, "result_expired", "已过期，请重新处理", 400)
    RESULT_NOT_READY = ErrorDef(40017, "result_not_ready", "任务未完成，暂不可下载", 400)
    QUEUE_OVERLOADED = ErrorDef(40018, "queue_overloaded", "系统繁忙，请稍后再试", 503)
    RATE_LIMITED = ErrorDef(40029, "rate_limited", "请求过于频繁，请稍后再试", 429)
    UNAUTHORIZED = ErrorDef(41001, "unauthorized", "登录已失效，请重新登录", 401)
    WX_LOGIN_FAILED = ErrorDef(41002, "wx_login_failed", "登录失败，请稍后重试", 401)
    CONTENT_BLOCKED = ErrorDef(42001, "content_blocked", "内容未通过安全审核，请修改后重试", 400)
    INTERNAL_ERROR = ErrorDef(50001, "internal_error", "服务繁忙，请稍后重试", 500)
    QUEUE_WAIT_TIMEOUT = ErrorDef(
        50002, "queue_wait_timeout", "排队超时，额度已返还，请稍后重试", 500
    )
    AI_UPSTREAM_FAILED = ErrorDef(52001, "ai_upstream_failed", "AI 服务暂不可用，请稍后重试", 502)
    TASK_TIMEOUT = ErrorDef(53001, "task_timeout", "处理超时，额度已返还，请稍后重试", 500)

    @property
    def defn(self) -> ErrorDef:
        return self.value


_BY_CODE: dict[int, ErrorCode] = {e.value.code: e for e in ErrorCode}


def get_error(code: int) -> ErrorCode | None:
    return _BY_CODE.get(code)
