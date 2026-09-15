# Provider 开发说明

Provider 只能依赖 `eventserver.core` 中的通用契约，不得访问用户、订阅、delivery、QQ、
Hermes 或 LLM。新增 provider 不应修改鉴权、订阅和 outbox。

最低步骤：

1. 选择稳定的 `<domain>.<resource>.<event>` 事件键和独立 schema 版本。
2. 实现 `metadata`、`validate_config`、`normalize`、`evaluate`、`render`、`health`。
3. 在应用组合层 `eventserver.providers.build_registry` 显式注册。
4. 增加首次基线、无变化、变化、异常、重复输入和 renderer 快照测试。
5. 在测试环境先观察而不开放订阅，验证去重、模板、速率限制与故障隔离后再启用。

轮询 provider 的 HTTP 客户端必须使用受控固定地址、连接/读取超时、响应大小上限、
有限重试和明确 User-Agent。网络失败保留旧 checkpoint，不能产生状态变化事件。普通用户
不能通过 API 提供 URL、代码、SQL 或模板表达式。

`normalize` 返回的时间必须带时区并统一转为 UTC。`evaluate(None, current)` 默认只建立
基线；只有 metadata 明确允许时才发布初始事件。`dedupe_key` 必须稳定、可复现，并与
事件语义窗口一致。
