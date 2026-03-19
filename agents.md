# LLM Gateway — Agent 经验手册

## 项目概述

LLM Gateway 是一个 LLM 代理网关，将客户端请求路由到 OpenAI、Anthropic 等上游提供商，提供：
- **规则路由**：基于模型名、请求头、token 用量智能路由
- **故障转移**：自动重试、熔断切换备用 Provider
- **可观测性**：全量请求日志（token 用量、延迟、费用）
- **管理后台**：Provider / 模型 / API Key / 日志的统一管理页面

## 项目结构

```
llm-gateway/
├── backend/app/
│   ├── api/
│   │   ├── admin/        # 管理接口路由（api_keys.py, models.py ...）
│   │   ├── proxy/        # 代理接口路由（openai.py, anthropic.py）
│   │   └── deps.py       # FastAPI 依赖注入（认证、限费检查）
│   ├── services/         # 业务逻辑（proxy_service, api_key_service, log_service ...）
│   ├── repositories/     # 数据访问层（接口 + sqlalchemy/ 实现）
│   ├── providers/        # 上游 LLM provider 适配器
│   ├── rules/            # 规则引擎
│   ├── domain/           # Pydantic DTO（api_key.py, log.py ...）
│   ├── db/models.py      # SQLAlchemy ORM 模型
│   └── common/           # 工具类（costs.py, errors.py, time.py ...）
├── frontend/
│   ├── src/types/        # TypeScript 类型定义
│   ├── src/components/   # React 组件
│   └── messages/         # i18n（zh.json, en.json）
├── migrations/           # 手动 SQL/Python 迁移脚本
├── healthcheck.sh        # 端到端健康验证脚本
└── docker-compose.yml
```

## 架构约定

- **分层严格**：API 路由 → Service（业务逻辑）→ Repository（数据访问），不跨层调用
- **依赖注入**：Service / Repository 通过 `deps.py` 注入，便于测试 override
- **Python**：PEP 8，所有函数签名加类型注解
- **TypeScript**：严格类型检查，遵循标准 React hooks 模式
- **数据库迁移**：本项目用手动 SQL 脚本（`migrations/`），**不用 Alembic**（GEMINI.md 里的 `alembic upgrade head` 是错的，忽略它）

## 开发工作流

### 运行测试
```bash
cd backend
python3 -m pytest                                        # 全部
python3 -m pytest tests/integration/test_xxx.py -v      # 指定文件
```
依赖安装（首次）：
```bash
pip3 install pytest pytest-asyncio sqlalchemy pydantic pydantic-settings apscheduler --break-system-packages
```

### 部署（本机 Docker）
```bash
# 正常（需要访问 Docker Hub）
sudo docker compose up -d --build

# 网络不稳定 / TLS timeout 时，用本地缓存层构建
sudo docker compose build --pull=false && sudo docker compose up -d
```

### 验证部署
```bash
bash healthcheck.sh
# 或指定 host/key：
bash healthcheck.sh http://localhost:8000 lgw-xxxxx
```
脚本验证：服务就绪 → 无效 key 返回 401 → 真实请求返回 200。

### 数据库迁移
新增字段时：
1. 在 `migrations/` 写 `.sql` 脚本
2. 对运行中容器执行：
```bash
docker exec llm-gateway-postgres-1 psql -U llm_gateway -d llm_gateway \
  -c "ALTER TABLE api_keys ADD COLUMN ..."
```

## 常见开发模式

### 新增字段完整链路（以 ApiKey 为例）
1. `db/models.py` — ORM 新增列
2. `domain/api_key.py` — Pydantic DTO 新增字段（Model / Response / Update）
3. `repositories/sqlalchemy/api_key_repo.py` — `_to_domain` 补全映射
4. `services/api_key_service.py` — `_to_response` 补全映射
5. `api/admin/api_keys.py` — 接口层赋值/透传
6. `migrations/` — SQL 迁移脚本
7. 前端：`types/` → 组件 → i18n（zh.json + en.json）

### 新增统计查询（以日志聚合为例）
1. `domain/log.py` — 新增结果 DTO
2. `repositories/log_repo.py` — 抽象接口新增方法
3. `repositories/sqlalchemy/log_repo.py` — SQLAlchemy 实现
   - 多维度统计用条件聚合 `func.sum(case(...))` 单次查询，避免多次 roundtrip
4. `services/log_service.py` — 透传方法
5. 接口层调用

### 认证与限费（deps.py: get_current_api_key）
认证流程：`service.authenticate()` → 检查 limit（查日/周/月花费）→ 超限抛 `AuthenticationError`

限费错误格式（带 `[LLM-Gateway]` 前缀，与上游 401 区分）：
```json
{"error": {"message": "[LLM-Gateway] Daily spending limit ($1.0000) exceeded", "code": "spending_limit_exceeded"}}
```

### 错误处理
- 所有业务错误继承 `AppError`，全局 handler 统一处理
- `AuthenticationError` → 401，`NotFoundError` → 404，`ConflictError` → 409
- 接口层：`except AppError as e: return JSONResponse(content=e.to_dict(), status_code=e.status_code)`

### 集成测试模式
```python
app.dependency_overrides[get_db] = lambda: db_session       # 注入内存 SQLite
app.dependency_overrides[require_admin_auth] = lambda: None  # 跳过鉴权
# ... 测试 ...
app.dependency_overrides = {}                                # 测试后清理
```

## Changelog 规则（必须遵守）

**每次完成开发任务后，必须更新 changelog，不得跳过。**

### 文件结构

```
CHANGELOG.md               ← 入口，每次追加一行摘要
docs/changes/              ← 详情文件目录
  YYYY-MM-DD-slug.md       ← 每次改动的详情文件
```

### 步骤

**1. 在 `CHANGELOG.md` 末尾追加一行：**

```markdown
| YYYY-MM-DD | feat/fix/refactor/chore | 一句话描述改动 | [详情](docs/changes/YYYY-MM-DD-slug.md) |
```

类型说明：`feat`（新功能）/ `fix`（修复）/ `refactor`（重构）/ `chore`（配置/文档/迁移等）

**2. 在 `docs/changes/` 创建详情文件 `YYYY-MM-DD-slug.md`，包含：**

```markdown
# 标题（与 CHANGELOG 描述一致）

**日期**：YYYY-MM-DD
**类型**：feat / fix / refactor / chore
**影响范围**：哪些模块/页面

## 背景
为什么要做这个改动，解决什么问题。

## 方案
采用了什么技术方案，关键设计决策。

## 改动点
按模块列出具体文件和改动内容。

## 迁移（如有）
需要执行的 SQL 或其他操作。
```

### 查阅历史

开始任务前，先快速扫一眼 `CHANGELOG.md` 了解近期改动方向，遇到相关模块时可点进详情文件了解完整背景。

## 重要注意事项

- **时间统一 UTC**：`app.common.time` 提供 `utc_now()` / `to_utc_naive()` / `ensure_utc()`，数据库存 naive datetime
- **Pydantic v2**：update 场景用 `model_dump(exclude_unset=True)` 避免覆盖未传字段
- **Cache token 语义差异**：
  - OpenAI：`cached_tokens` **包含在** `input_tokens` 里（拆分计费）
  - Anthropic：`cache_read_input_tokens` / `cache_creation_input_tokens` 是**额外叠加**的（加法计费）
- **docker build 网络超时**：加 `--pull=false` 使用本地已缓存的基础镜像层
- **前端依赖未安装时**：无法跑 `npm run build`，但 TypeScript 类型改动可通过 interface 覆盖人工审查
