from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from oc_core.alerts import evaluate_alerts, incr, render_prometheus
from oc_core.cleanup import group_upload_prefixes


def test_group_upload_prefixes():
    now = datetime.now(UTC)
    objs = [
        {
            "key": "local/0/uploads/upl_abc/0_a.pdf",
            "last_modified": now - timedelta(hours=7),
            "size": 10,
        },
        {
            "key": "local/0/uploads/upl_abc/1_b.pdf",
            "last_modified": now - timedelta(hours=1),
            "size": 10,
        },
        {
            "key": "local/0/results/tsk/result.pdf",
            "last_modified": now,
            "size": 10,
        },
    ]
    groups = group_upload_prefixes("local", objs)
    assert "upl_abc" in groups
    assert groups["upl_abc"]["prefix"] == "local/0/uploads/upl_abc/"
    assert groups["upl_abc"]["last_modified"] == now - timedelta(hours=1)
    assert len(groups["upl_abc"]["keys"]) == 2


def test_render_prometheus_contains_counters():
    incr("upload_orphan_cleanup_total", 2)
    text = render_prometheus()
    assert "oc_upload_orphan_cleanup_total" in text
    assert "oc_queue_depth" in text


def test_evaluate_alerts_success_rate(monkeypatch):
    session = MagicMock()

    def fake_stats(session, *, window_seconds):
        return {"succeeded": 1, "failed": 9, "cancelled": 0, "total": 10}

    monkeypatch.setattr("oc_core.alerts.task_stats_window", fake_stats)
    monkeypatch.setattr("oc_core.alerts.queue_depth", lambda q: 0)
    fired = evaluate_alerts(session)
    assert any(a["name"] == "task_success_rate_low" for a in fired)


def test_evaluate_alerts_queue_depth(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(
        "oc_core.alerts.task_stats_window",
        lambda *a, **k: {"succeeded": 10, "failed": 0, "cancelled": 0, "total": 10},
    )
    monkeypatch.setattr("oc_core.alerts.queue_depth", lambda q: 999 if q == "q.tools" else 0)
    fired = evaluate_alerts(session)
    assert any(a["name"] == "queue_depth_high" for a in fired)
