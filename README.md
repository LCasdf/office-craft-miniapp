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
| [ADR-0001 后端栈](./docs/adr/0001-python-fastapi-celery.md) | FastAPI + Celery 决策记录 |

## 仓库结构（M0）

```
apps/api          FastAPI
apps/worker       Celery worker
apps/miniapp      微信小程序骨架
packages/oc_shared  枚举 / 错误码 / DTO
packages/oc_core    领域 / SQLAlchemy / AIClient（无 FastAPI/Celery）
configs/          任务超时等配置
alembic/          迁移
docs/             产品与技术文档
```

## 本地启动

```bash
# 1. 依赖
cp .env.example .env
uv sync

# 2. 基础设施
docker compose up -d mysql redis minio

# 3. 迁移（MySQL healthy 后）
uv run alembic upgrade head

# 4. API
uv run uvicorn oc_api.main:app --app-dir apps/api/src --reload --port 8000

# 5. Worker（另开终端）
uv run celery -A oc_worker.celery_app:celery_app worker -l INFO -Q q.tools,q.ai \
  --workdir apps/worker \
  # 或 PYTHONPATH=apps/worker/src:...
```

更简单：在已 `uv sync` 的 venv 中，因包已 editable 安装：

```bash
uv run uvicorn oc_api.main:app --reload --port 8000
uv run celery -A oc_worker.celery_app:celery_app worker -l INFO -Q q.tools,q.ai
```

小程序：用微信开发者工具打开 `apps/miniapp`。

## 自检

```bash
bash scripts/dev_check.sh
# 或
uv run pytest -q
curl -s localhost:8000/healthz
```

> M0：登录/任务多为 stub；空 Celery `ping_task` 用于验证入队。业务能力按里程碑推进。
