# API Key 增加日/周/月消费统计与限费拦截

**日期**：2026-03-19
**类型**：feat
**影响范围**：后端 API Key 模型、日志统计、认证流程；前端 API Key 列表与编辑表单

## 背景

原有 API Key 只展示本月累计消费，缺少更细粒度的周/日维度统计，也没有消费限额功能，无法对 key 的使用成本做精细控制。

## 方案

- 在 `api_keys` 表新增三个可选限额字段（`daily_cost_limit` / `weekly_cost_limit` / `monthly_cost_limit`）
- 新增 `get_api_key_period_costs` 查询，用条件聚合（`func.sum(case(...))`）单次 SQL 返回日/周/月三个维度消费，避免多次查询
- 在 `deps.py` 的 `get_current_api_key` 认证通过后立即检查限额，超限抛 `AuthenticationError`
- 错误 message 加 `[LLM-Gateway]` 前缀，与上游 401 区分
- 前端列表新增今日/本周列，支持"消费 / 限额"格式展示；编辑表单新增三个限额输入框

## 改动点

### 后端
- `app/db/models.py` — `ApiKey` 新增 `daily_cost_limit` / `weekly_cost_limit` / `monthly_cost_limit`
- `app/domain/log.py` — 新增 `ApiKeyPeriodCosts` DTO
- `app/domain/api_key.py` — `ApiKeyModel` / `ApiKeyResponse` / `ApiKeyUpdate` 补全字段
- `app/repositories/log_repo.py` — 抽象接口新增 `get_api_key_period_costs`
- `app/repositories/sqlalchemy/log_repo.py` — 实现 `get_api_key_period_costs`（条件聚合）
- `app/repositories/sqlalchemy/api_key_repo.py` — `_to_domain` 补全 limit 字段映射
- `app/services/log_service.py` — 新增 `get_api_key_period_costs`
- `app/services/api_key_service.py` — `_to_response` 补全 limit 字段
- `app/api/admin/api_keys.py` — list 接口改用 `get_api_key_period_costs`，返回日/周/月费用
- `app/api/deps.py` — `get_current_api_key` 增加限费检查逻辑
- `migrations/add_api_key_cost_limits.sql` — 新建迁移脚本

### 前端
- `src/types/api-key.ts` — `ApiKey` / `ApiKeyUpdate` 补全字段
- `src/components/api-keys/ApiKeyList.tsx` — 新增今日/本周消费列，显示"消费 / 限额"
- `src/components/api-keys/ApiKeyForm.tsx` — 编辑模式新增日/周/月限额输入框
- `messages/zh.json` / `messages/en.json` — 新增 i18n key

### 测试
- `tests/integration/test_api_key_spending_limits.py` — 7 个集成测试，覆盖超限拦截、未超限放行、旧日志不计入当前窗口、列表字段正确性

## 迁移

```sql
ALTER TABLE api_keys ADD COLUMN daily_cost_limit NUMERIC(10, 6) NULL;
ALTER TABLE api_keys ADD COLUMN weekly_cost_limit NUMERIC(10, 6) NULL;
ALTER TABLE api_keys ADD COLUMN monthly_cost_limit NUMERIC(10, 6) NULL;
```
