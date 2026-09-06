from oc_shared.constants import TASK_TIMEOUTS
from oc_shared.enums import TaskStatus, TaskType
from oc_shared.error_codes import ErrorCode


def test_task_types_cover_timeouts():
    for t in TaskType:
        assert t.value in TASK_TIMEOUTS


def test_error_code_ok():
    assert ErrorCode.OK.defn.code == 0
    assert ErrorCode.RATE_LIMITED.defn.http_status == 429


def test_task_status_values():
    assert TaskStatus.SUCCEEDED.value == "succeeded"
