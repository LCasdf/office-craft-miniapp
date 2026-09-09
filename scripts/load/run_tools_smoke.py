#!/usr/bin/env python3
"""G1 tool latency smoke: local merge (+ optional compress) P50/P95.

Does not need API/Worker — measures converter path used by Worker.
Optional: --api to also hit create/poll against a running API.

Usage:
  uv run python scripts/load/run_tools_smoke.py --rounds 20
  uv run python scripts/load/run_tools_smoke.py --rounds 10 --api --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"


def _blank(path: Path, pages: int = 2) -> Path:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=280)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        w.write(f)
    return path


def _pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round((len(xs) - 1) * q))))
    return round(xs[i], 4)


def run_local(rounds: int) -> dict:
    from oc_core.converters.pdf import compress_pdf, find_gs, merge_pdfs

    merge_lat: list[float] = []
    compress_lat: list[float] = []
    with tempfile.TemporaryDirectory(prefix="oc_load_") as tmp:
        tmp_path = Path(tmp)
        a = _blank(tmp_path / "a.pdf", 3)
        b = _blank(tmp_path / "b.pdf", 3)
        for i in range(rounds):
            t0 = time.perf_counter()
            merge_pdfs([a, b], tmp_path / f"m_{i}.pdf")
            merge_lat.append(time.perf_counter() - t0)
            if find_gs():
                t1 = time.perf_counter()
                compress_pdf(a, tmp_path / f"c_{i}.pdf", quality="standard", timeout_sec=60)
                compress_lat.append(time.perf_counter() - t1)
    return {
        "merge": {
            "n": len(merge_lat),
            "p50": _pct(merge_lat, 0.5),
            "p95": _pct(merge_lat, 0.95),
            "mean": round(statistics.mean(merge_lat), 4) if merge_lat else None,
            "gate_p95_le_60s": bool(merge_lat) and (_pct(merge_lat, 0.95) or 99) <= 60,
        },
        "compress": {
            "n": len(compress_lat),
            "p50": _pct(compress_lat, 0.5),
            "p95": _pct(compress_lat, 0.95),
            "mean": round(statistics.mean(compress_lat), 4) if compress_lat else None,
            "skipped": not compress_lat,
            "gate_p95_le_60s": (not compress_lat)
            or bool(compress_lat and (_pct(compress_lat, 0.95) or 99) <= 60),
        },
    }


def run_api(base: str, n: int) -> dict:
    import httpx

    codes: dict[str, int] = {}
    ok = fail = 0
    with httpx.Client(base_url=base, timeout=30.0) as client:
        for i in range(n):
            r = client.post(
                "/v1/tasks",
                json={"type": "character_card", "inputs": [], "uploadId": f"upl_g1_{i}"},
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            body = r.json()
            code = str(body.get("code"))
            codes[code] = codes.get(code, 0) + 1
            if body.get("code") == 0:
                ok += 1
            else:
                fail += 1
    return {"create_ok": ok, "fail": fail, "error_code_dist": codes}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rounds", type=int, default=20)
    p.add_argument("--api", action="store_true")
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--api-n", type=int, default=5)
    args = p.parse_args()

    report = {
        "scenario": "g1_tools_smoke",
        "at": datetime.now(UTC).isoformat(),
        "machine": "local",
        "local_converters": run_local(args.rounds),
    }
    if args.api:
        try:
            report["api_inflight"] = run_api(args.base, args.api_n)
        except Exception as e:
            report["api_inflight"] = {"error": str(e)}

    gate_ok = (
        report["local_converters"]["merge"]["gate_p95_le_60s"]
        and report["local_converters"]["compress"]["gate_p95_le_60s"]
    )
    report["g1_latency_gate"] = gate_ok

    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_json = REPORTS / f"tools_smoke_{stamp}.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    md = REPORTS / f"G1_REPORT_{stamp}.md"
    md.write_text(
        "\n".join(
            [
                "# M1 / G1 压测报告（自动生成）",
                "",
                f"- 时间：{report['at']}",
                f"- 场景：本地转换器 merge/compress × {args.rounds}",
                f"- merge P95：{report['local_converters']['merge']['p95']}s",
                f"- compress P95：{report['local_converters']['compress']['p95']}s"
                f"（skipped={report['local_converters']['compress']['skipped']}）",
                f"- 门禁 P95≤60s：{'通过' if gate_ok else '未通过'}",
                f"- 原始 JSON：`{out_json.name}`",
                "",
            ]
        )
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"wrote {out_json}")
    print(f"wrote {md}")
    return 0 if gate_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
