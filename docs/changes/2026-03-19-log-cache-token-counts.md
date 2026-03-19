# 日志列表增加 cache read/creation token 数量展示

**日期**：2026-03-19
**类型**：feat
**影响范围**：request_logs 表、日志列表接口、前端日志列表页

## 背景

日志列表已展示 in/out token 数量，但 Anthropic cache_read_input_tokens 和 cache_creation_input_tokens 只存在 usage_details JSON 里，没有独立列，无法直接展示和统计。

## 方案

在 `request_logs` 表新增两个独立整数列，写入时从 usage_details 同步存储，前端列表在 in/out token 行下追加展示（有值才显示，用不同颜色区分：cache-read 蓝色，cache-creation 橙色）。

## 改动点

### 后端
- `app/db/models.py` — `RequestLog` 新增 `cache_read_tokens` / `cache_creation_tokens`
- `app/domain/log.py` — `RequestLogCreate` / `RequestLogSummary` / `RequestLogResponse` 补全字段
- `app/services/proxy_service.py` — 非流式和流式日志写入时传入两个字段
- `migrations/add_cache_token_counts.sql` — 迁移脚本

### 前端
- `src/types/log.ts` — `RequestLog` 补全字段
- `src/components/logs/LogList.tsx` — token 列追加 cache read/creation 行（有值才显示）
- `messages/zh.json` / `messages/en.json` — 新增 i18n key

## 迁移

```sql
ALTER TABLE request_logs ADD COLUMN cache_read_tokens INTEGER NULL;
ALTER TABLE request_logs ADD COLUMN cache_creation_tokens INTEGER NULL;
```
