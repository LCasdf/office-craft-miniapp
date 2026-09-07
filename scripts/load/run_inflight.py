#!/usr/bin/env python3
"""M1 load smoke: create N empty character_card tasks + poll until terminal or timeout.

Usage:
  API_BASE=http://127.0.0.1:8000 uv run python scripts/load/run_inflight.py --n 5

Writes JSON summary to scripts/load/reports/ (gitignored except template).
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--n", type=int, default=5, help="tasks to create")
    p.add_argument("--poll-ms", type=int, default=500)
    p.add_argument("--timeout-s", type=int, default=120)
    args = p.parse_args()

    latencies: list[float] = []
    codes: dict[str, int] = {}
    ok = 0
    fail = 0

    with httpx.Client(base_url=args.base, timeout=30.0) as client:
        created: list[str] = []
        for i in range(args.n):
            key = str(uuid.uuid4())
            t0 = time.perf_counter()
            r = client.post(
                "/v1/tasks",
                json={"type": "character_card", "inputs": [], "uploadId": f"upl_load_{i}"},
                headers={"Idempotency-Key": key},
            )
            body = r.json()
            code = str(body.get("code"))
            codes[code] = codes.get(code, 0) + 1
            if body.get("code") != 0:
                fail += 1
                continue
            created.append(body["data"]["taskId"])
            latencies.append(time.perf_counter() - t0)

        deadline = time.time() + args.timeout_s
        pending = set(created)
        while pending and time.time() < deadline:
            done = set()
            for tid in list(pending):
                body = client.get(f"/v1/tasks/{tid}").json()
                st = (body.get("data") or {}).get("status")
                if st in ("succeeded", "failed", "cancelled"):
                    done.add(tid)
                    if st == "succeeded":
                        ok += 1
                    else:
                        fail += 1
                        codes[f"terminal:{st}"] = codes.get(f"terminal:{st}", 0) + 1
            pending -= done
            if pending:
                time.sleep(args.poll_ms / 1000)

        if pending:
            fail += len(pending)
            codes["poll_timeout"] = codes.get("poll_timeout", 0) + len(pending)

    def pct(xs: list[float], q: float) -> float | None:
        if not xs:
            return None
        xs = sorted(xs)
        i = min(len(xs) - 1, max(0, int(round((len(xs) - 1) * q))))
        return round(xs[i], 4)

    report = {
        "scenario": "inflight_character_card",
        "at": datetime.now(UTC).isoformat(),
        "base": args.base,
        "n": args.n,
        "create_ok": len(created),
        "terminal_ok": ok,
        "fail": fail,
        "error_code_dist": codes,
        "create_latency_s": {
            "p50": pct(latencies, 0.50),
            "p95": pct(latencies, 0.95),
            "p99": pct(latencies, 0.99),
            "mean": round(statistics.mean(latencies), 4) if latencies else None,
        },
        "notes": "Empty character_card: create/idempotency/inflight; PDF tools need fixtures.",
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"inflight_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"wrote {out}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
