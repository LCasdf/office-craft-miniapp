# ADR-0001：后端采用 FastAPI + Celery

- 状态：已采纳
- 日期：2026-09-05
- 最后同步：2026-09-07（对齐蓝图 v0.8、开发规范 v0.7、进度 docs/07）
- 决策人：项目组（用户确认）

## 背景

小程序后端需要同时提供 HTTP API（鉴权、额度、建任务、AI 编排）与重文件处理 Worker（PDF 压缩/合并、转换、PPT、出图）。此前候选包括 NestJS、Go，以及「API 与 Worker 分语言」。

## 决策

**API 与 Worker 均使用 Python 3.11+：**

| 层级 | 选型 |
|------|------|
| API | **FastAPI** + Pydantic v2 + uvicorn |
| ORM / 迁移 | SQLAlchemy 2.x + Alembic；库 **MySQL 8**（DDL 见 `docs/04-数据模型.md`） |
| 队列 / Worker | **Celery + Redis**（默认）；分队列 `q.tools` / `q.ai` |
| 共享 | `packages/oc_shared`（DTO、错误码、`error_codes.py`） |
| 领域 | `packages/oc_core`（模型与领域服务；**禁止** import fastapi/celery） |
| AI | 统一 **`AIClient`** 适配层（多供应商、记 token） |
| 日志 / 监控 | structlog JSON；Prometheus + Grafana（或云监控） |

不采用 NestJS / Go 作为本阶段默认栈。**ARQ 不作为 MVP 默认**（可作未来备选）。  
一期倾向 **自建 FastAPI**，不以微信云函数为主路径。

## 理由

1. Worker 强依赖 Python 生态（Ghostscript、pypdf/pikepdf、python-pptx、Pillow 等）。
2. 全 Python 降低双语言仓库、重复 DTO、发布耦合成本。
3. FastAPI 原生 OpenAPI，对齐 `docs/03-API契约.md` 与小程序生成类型。
4. Celery 对超时、重试、prefork、路由队列、DLQ 更成熟，适合 CPU/子进程型任务。

## 后果

**正向**

- 一套类型与错误码，API/Worker 共用 `oc_shared`。
- 本地 `docker-compose` 易对齐（MySQL + Redis + api + **worker 容器含 gs**）。

**代价与约束（须遵守现行开发规范）**

- API 进程禁止重转换 / 外部命令 / 长耗时 AI 阻塞；预估 >1s、文件 IO、gs/soffice、AI 一律 Celery 入队。
- 消息 schema 版本化（`schemaVersion`）；按 `taskId` **幂等**消费；Celery 自动重试 ≤2 且**不得重复扣额度**。
- 配置：分类型超时（默认 180s，见蓝图 §4.3）、硬 `task_time_limit`、`acks_late`、失败进 **DLQ**、Worker `/healthz`。
- **额度预占/转正/回滚仅 API**；Worker 只回写 `tasks` / `assets`，禁止改 `quotas` / `users`。
- `oc_core` 保持纯领域逻辑，**禁止**依赖 FastAPI / Celery 框架模块。
- 小程序类型以 OpenAPI 生成物为准；改 `oc_shared` 须全链路同步（规范 §2.3）。

## 备选方案（未采纳）

| 方案 | 未采纳原因 |
|------|------------|
| NestJS/Go API + Python Worker | 契约与部署复杂度更高，团队收益不足 |
| FastAPI + ARQ（默认） | 对重文件/子进程隔离与生态成熟度弱于 Celery |
| 微信云开发云函数为主 | 长时文件任务与自定义二进制（gs）受限 |

## 文档锚点

| 文档 | 相关章节 |
|------|----------|
| [01 项目蓝图](../01-项目蓝图.md) | §4.1 技术栈、§4.2 仓库、§4.12 Worker、§9 已决策 |
| [02 开发规范](../02-开发规范.md) | §2 边界、§5–6 任务/Celery、§8 AIClient、§11 可观测 |
| [03 API 契约](../03-API契约.md) | OpenAPI 与包络 |
| [04 数据模型](../04-数据模型.md) | MySQL DDL |

## 后续动作

- [x] 蓝图 §4.1 / §4.2 / §9 同步本决策  
- [x] 开发规范锁定 FastAPI + Celery 约束（含分队列、额度归属、DLQ）  
- [x] M0 脚手架按本 ADR 初始化（`uv` 工作区、compose、空任务链路）  
- [x] CI：lint / 单测 / `pip-audit`（见规范 §9.5；类型检查待后续补齐）  
