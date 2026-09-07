# M1 压测报告模板

| 项 | 填写 |
|----|------|
| 日期 | |
| 环境 | local / staging |
| 机器规格 | CPU / RAM / Docker 与否 |
| 分支 / commit | |
| 场景 | inflight 空任务 / pdf_compress / pdf_merge |

## 结果摘要

| 指标 | 目标 | 实测 | 过？ |
|------|------|------|------|
| P95 端到端（限制内） | ≤ 60s | | |
| 成功率（排除用户错误） | 可接受 | | |
| inflight 超额 | 返回 `40005` | | |
| 错误码分布 | 可归因 | | |

## 原始数据

- 脚本：`scripts/load/run_inflight.py`
- 产物：`scripts/load/reports/inflight_*.json`

## 结论

- [ ] 过 G1 压测门禁
- [ ] 不过 — 阻塞项：
