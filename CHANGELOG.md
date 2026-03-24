# Changelog

每次改动在此追加一行，格式：`日期 | 类型 | 简要描述 | 详情`
详情文件位于 `docs/changes/`。

---

| 日期 | 类型 | 描述 | 详情 |
|------|------|------|------|
| 2026-03-25 | feat | Provider 列表每行展示熔断状态切换按钮（CLOSED/OPEN/HALF-OPEN），支持手动切换；status 徽章可点击切换启用禁用 | — |
| 2026-03-24 | feat | 模型详情页新增「重置熔断状态」按钮，支持一键清除所有 provider 熔断状态 | — |
| 2026-03-24 | feat | 新增 POST /api/admin/circuit-breaker/reset 接口重置熔断器 | — |
| 2026-03-24 | feat | 日志详情页新增对话预览 box，展示最新一轮 user 消息与 assistant 响应 | — |
| 2026-03-24 | fix | 流式异常路径补全熔断 is_open 检查，熔断触发后不再继续 except 分支重试 | — |
| 2026-03-23 | fix | 熔断触发后立即切换 provider，不再继续无效重试 | — |
| 2026-03-23 | feat | 日志列表新增耗时列（TTFB / 总响应时间） | — |
| 2026-03-20 | feat | 模型测试支持批量测试全部供应商或指定供应商 | — |
| 2026-03-19 | feat | 引入 Provider 熔断器实现智能快速切换 | — |
| 2026-03-19 | fix | 导入导出补全 cache 相关字段 | — |
| 2026-03-19 | fix | request_logs 补全 cache_creation_cost 写入 | — |
| 2026-03-19 | fix | 对齐 cache 计费字段与 UI label 语义 | — |
| 2026-03-19 | feat | 日志列表和详情页展示缓存费用明细 | — |
| 2026-03-19 | feat | API Key 增加日/周/月消费统计与限费拦截 | [详情](docs/changes/2026-03-19-api-key-spending-limits.md) |
| 2026-03-19 | feat | 日志列表增加 cache read/creation token 数量展示 | [详情](docs/changes/2026-03-19-log-cache-token-counts.md) |
| 2026-03-19 | fix | 日志列表 API 补全 cache token 字段映射（log_service / log_repo） | — |
