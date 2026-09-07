# Office Craft / 文匠工具

微信小程序：文件转换、PDF 压缩/合并、PPT / 小说 / 角色卡生成。

**后端已锁定：** Python 3.11+ / FastAPI + Celery（Redis）+ MySQL。

## 文档

| 文档 | 说明 |
|------|------|
| [项目蓝图](./docs/01-项目蓝图.md) | 定位、功能、架构、里程碑、风险 |
| [开发规范](./docs/02-开发规范.md) | 目录边界、API/任务/Git/安全约定 |
| [接口契约](./docs/03-API契约.md) | REST 接口 Markdown + OpenAPI 3.0 初稿 |
| [数据模型与 DDL](./docs/04-数据模型.md) | MySQL 表结构、3NF、建表脚本 |
| [启动步骤](./docs/05-启动步骤.md) | 本地环境、依赖、API/Worker/Beat/小程序启动 |
| [排期与测试](./docs/06-排期与测试.md) | 里程碑、DoD、门禁、测试与压测 |
| [项目进度](./docs/07-项目进度.md) | 里程碑完成状态、Gate、已知缺口与下一步 |
| [PPT POC Go/No-Go](./docs/known-issues/ppt-poc-go-nogo.md) | M2b 模板路线结论（条件 Go） |
| [ADR-0001 后端栈](./docs/adr/0001-python-fastapi-celery.md) | FastAPI + Celery 决策记录 |

## 仓库结构

```
apps/api          FastAPI
apps/worker       Celery worker + beat（tools / maintenance）
apps/miniapp      微信小程序（工具页 + 任务中心）
packages/oc_shared  枚举 / 错误码 / DTO
packages/oc_core    领域 / SQLAlchemy / MinIO / 转换器 / 额度
configs/          任务超时等配置
alembic/          迁移
scripts/load      M1 压测脚本与报告模板
scripts/ppt_poc   PPT 模板填充 POC
docs/             产品与技术文档
```

## 本地启动

完整步骤见 **[docs/05-启动步骤.md](./docs/05-启动步骤.md)**。摘要：

```bash
cp .env.example .env && uv sync
docker compose up -d mysql redis minio
uv run alembic upgrade head
uv run uvicorn oc_api.main:app --reload --port 8000
# 另开终端
uv run celery -A oc_worker.celery_app:celery_app worker -l INFO -Q q.tools,q.ai
# 建议再开 Beat（TTL / 超时 sweep / 告警）
uv run celery -A oc_worker.celery_app:celery_app beat -l INFO
```

小程序：微信开发者工具打开 `apps/miniapp`（勾选「不校验合法域名」）。

## 自检

```bash
bash scripts/dev_check.sh
# 或（CI 另卡覆盖率地板 60%；G1 目标行 80% / 分支 70%）
uv run pytest -q --cov=oc_core --cov=oc_api --cov-fail-under=60
curl -s localhost:8000/healthz
```

> **当前进度（见 [docs/07](./docs/07-项目进度.md)）：** M0 完成（G0）；M1 进行中——四条工具 + 任务中心（重试/下载/过期）+ 额度/幂等/inflight + 清理告警已通；**G1 未过**（正式压测报告与覆盖率目标未达标）。PPT POC = **条件 Go**。
