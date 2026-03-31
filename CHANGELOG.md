# Changelog

每次改动在此追加一行，格式：`日期 | 类型 | 简要描述 | 详情`
详情文件位于 `docs/changes/`。

---

| 日期 | 类型 | 描述 | 详情 |
|------|------|------|------|
| 2026-03-31 | fix | in_progress 日志写入时同步记录 provider/target_model/matched_provider_count，列表页不再显示空值 | — |
| 2026-03-27 | feat | 日志详情页展示 thinking 内容：实时输出与对话预览均支持 thinking 块，可折叠展示 | — |
| 2026-03-27 | feat | 模型测试对话框新增自定义提示词输入框，留空使用默认 "hello" | — |
| 2026-03-27 | fix | 模型测试对话框：强制指定非激活 provider 时绕过 is_active 过滤，允许测试任意 provider | — |
| 2026-03-27 | feat | 请求实时追踪：请求开始即写入 in_progress 日志，流式输出通过 Redis 实时同步到详情页，支持实时预览与进行中状态徽章 | — |
| 2026-03-27 | feat | 流式空响应：buffer 至首个内容 chunk，无内容则拦截发送 error SSE event 替代空 framing | — |
| 2026-03-27 | feat | proxy 检测空响应（无文本无工具调用）返回 520/EMPTY_UPSTREAM_RESPONSE 错误，不触发熔断计数 | — |
| 2026-03-25 | fix | 修复 provider extra_query_params 保存后丢失的 bug（repo 及 service 响应映射遗漏字段） | — |
| 2026-03-25 | feat | Provider 配置新增自定义 URL Query 参数（extra_query_params），支持如 /v1/messages?beta=true 场景 | — |
| 2026-03-25 | fix | 模型测试 provider 下拉框放开未激活供应商，可选测试（未激活有灰色标注） | — |
| 2026-03-25 | feat | 日志页新增自动刷新（默认视图每3秒拉取），可手动切换开关，与筛选状态联动 | — |
| 2026-03-25 | feat | 模型详情页 Provider 列表支持拖拽排序（priority 策略下），拖拽后自动批量更新优先级 | — |
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
