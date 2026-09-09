# M1 / G1 压测报告

| 项 | 填写 |
|----|------|
| 日期 | 2026-09-08 |
| 环境 | local（macOS，本机 gs 已装） |
| 机器规格 | 开发机；转换器本地直跑（Worker 同路径） |
| 分支 / commit | main（G1 收口） |
| 场景 | `scripts/load/run_tools_smoke.py --rounds 20` |

## 结果摘要

| 指标 | 目标 | 实测 | 过？ |
|------|------|------|------|
| merge P95 | ≤ 60s | **0.0016s** | 是 |
| compress P95 | ≤ 60s | **0.0312s** | 是 |
| 成功率（转换器） | 可接受 | 20/20 | 是 |
| inflight≤3 / `40005` | 有 | 单测覆盖 | 是 |
| 队列过载拒绝 | 有 | `40018`（深度≥`ALERT_QUEUE_DEPTH_MAX`） | 是 |

## 原始数据

- 脚本：`scripts/load/run_tools_smoke.py`、`scripts/load/run_inflight.py`
- 产物示例：`scripts/load/reports/tools_smoke_*.json`（json 默认 gitignore）

## 结论

- [x] 过 G1 压测门禁（本地转换器 P95）
- [x] 加密 PDF / 用户错误 → 释预占不扣费（单测）
- [x] 覆盖率行 ≥ 80%（CI `--cov-fail-under=80`）
