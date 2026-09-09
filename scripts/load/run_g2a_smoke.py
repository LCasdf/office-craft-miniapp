#!/usr/bin/env python3
"""G2a character-card smoke against a running API (+ Worker for render).

Covers:
  - Demo path: POST /imagine → PNG URL downloadable
  - Server path: generate → put conflict → render → poll succeeded
  - Moderation: generate / imagine → 42001, quota unchanged
  - Render blocked before reserve → quota unchanged

Usage:
  uv run python scripts/load/run_g2a_smoke.py
  uv run python scripts/load/run_g2a_smoke.py --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"


def api(base: str, method: str, path: str, body=None, headers=None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}", data=data, headers=h, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return json.loads(raw)
        except Exception:
            raise RuntimeError(f"HTTP {e.code}: {raw[:300]}") from e


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    args = p.parse_args()
    base = args.base
    checks: list[tuple[str, bool, str]] = []

    def ok(name: str, cond: bool, detail: str = "") -> None:
        checks.append((name, cond, detail))
        print(("PASS" if cond else "FAIL"), name, detail)

    hz = api(base, "GET", "/healthz")
    ok("healthz", hz.get("code") == 0, hz.get("message", ""))

    # --- demo: imagine ---
    im = api(
        base,
        "POST",
        "/v1/ai/character-card/imagine",
        {
            "prompt": "银发法师，月下图书馆",
            "name": "埃兰",
            "title": "月档案馆主",
        },
    )
    url = (im.get("data") or {}).get("imageUrl")
    ok("imagine", im.get("code") == 0 and bool(url), im.get("user_msg", ""))
    if url:
        png = download(url)
        ok("imagine_png", png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 2000, str(len(png)))

    q0 = api(base, "GET", "/v1/me/quota")["data"]["available"]
    blk = api(
        base,
        "POST",
        "/v1/ai/character-card/imagine",
        {"prompt": "内容含违禁词请拦截"},
    )
    q1 = api(base, "GET", "/v1/me/quota")["data"]["available"]
    ok(
        "imagine_blocked",
        blk.get("code") == 42001 and q1 == q0,
        f"{blk.get('user_msg')} quota={q0}->{q1}",
    )

    # --- server: generate → put → render ---
    key = str(uuid.uuid4())
    g = api(
        base,
        "POST",
        "/v1/ai/character-card/generate",
        {"premise": "江南雨巷卖纸鸢的少年"},
        {"Idempotency-Key": key},
    )
    ok("generate_free", g.get("code") == 0 and g["data"].get("costQuota") == 0)
    card_id = g["data"]["cardId"]
    ver = g["data"]["version"]
    payload = dict(g["data"]["payload"])
    payload["name"] = "纸鸢少年"

    bad = api(
        base,
        "PUT",
        f"/v1/ai/character-card/{card_id}",
        {"version": ver + 99, "payload": payload},
        {"If-Match": str(ver + 99)},
    )
    ok("put_conflict", bad.get("code") == 40015, bad.get("user_msg", ""))

    put = api(
        base,
        "PUT",
        f"/v1/ai/character-card/{card_id}",
        {"version": ver, "payload": payload},
        {"If-Match": str(ver)},
    )
    ok("put_ok", put.get("code") == 0 and put["data"]["version"] == ver + 1)

    q_before = api(base, "GET", "/v1/me/quota")["data"]["available"]
    rend = api(
        base,
        "POST",
        f"/v1/ai/character-card/{card_id}/render",
        {},
        {"Idempotency-Key": str(uuid.uuid4())},
    )
    ok(
        "render_reserve",
        rend.get("code") == 0 and rend["data"].get("costQuota") == 3,
        rend.get("user_msg", ""),
    )
    tid = (rend.get("data") or {}).get("renderTaskId")
    q_after = api(base, "GET", "/v1/me/quota")["data"]["available"]
    ok("render_quota", q_after == q_before - 3, f"{q_before}->{q_after}")

    status = None
    task = {}
    for _ in range(40):
        task = api(base, "GET", f"/v1/tasks/{tid}")
        status = (task.get("data") or {}).get("status")
        if status in ("succeeded", "failed", "canceled"):
            break
        time.sleep(0.5)
    ok("render_succeeded", status == "succeeded", f"task={tid} status={status}")

    g_blk = api(
        base,
        "POST",
        "/v1/ai/character-card/generate",
        {"premise": "内容含违禁词请拦截"},
        {"Idempotency-Key": str(uuid.uuid4())},
    )
    q2 = api(base, "GET", "/v1/me/quota")["data"]["available"]
    ok(
        "generate_blocked",
        g_blk.get("code") == 42001 and q2 == q_after,
        g_blk.get("user_msg", ""),
    )

    passed = all(c[1] for c in checks)
    report = {
        "gate": "G2a",
        "at": datetime.now(UTC).isoformat(),
        "base": base,
        "passed": passed,
        "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = REPORTS / f"G2A_REPORT_{stamp}.md"
    lines = [
        "# G2a Smoke Report",
        "",
        f"- at: `{report['at']}`",
        f"- base: `{base}`",
        f"- passed: **{passed}**",
        "",
        "| check | ok | detail |",
        "|-------|----|--------|",
    ]
    for n, o, d in checks:
        lines.append(f"| {n} | {'yes' if o else 'NO'} | {d} |")
    lines += [
        "",
        "## Demo checklist (miniapp)",
        "",
        "1. 首页 → 角色卡集 → 新建",
        "2. 填写描述 →「根据文字生成角色图片」→ 预览 PNG",
        "3.「保存到角色卡集」→ 列表显示已出图",
        "4. 可选：AI 填充人设文字；编辑后再次出图",
        "5. 违禁词提示 `内容未通过安全审核，请修改后重试`",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    latest = ROOT / "G2A_REPORT.md"
    latest.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    print("wrote", out)
    print("wrote", latest)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
