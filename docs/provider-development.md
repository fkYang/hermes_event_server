# Provider 开发说明

Provider 只能依赖 `eventserver.core` 中的通用契约，不得访问用户、订阅、delivery、QQ、
Hermes 或 LLM。新增 provider 不应修改鉴权、订阅、outbox 或 Plugin。

## 公共能力

每个 provider 按需要实现以下能力，实际函数签名以代码契约为准：

```text
metadata() -> ProviderMetadata
validate_config(config) -> ValidatedConfig
normalize(raw) -> Observation
evaluate(previous, current) -> list[DomainEvent]
render(event, locale) -> DeliveryMessage
health() -> ProviderHealth
```

按接入模式声明 capability：

```text
# polling capability
collect(context, checkpoint) -> RawObservation | NoChange

# scheduled capability
on_schedule(context, scheduled_at) -> Observation | DomainEvent

# webhook capability
verify_webhook(headers, body) -> VerifiedWebhook
ingest_webhook(verified) -> Observation | DomainEvent

# trusted publisher capability
validate_published_event(identity, payload, dedupe_key) -> DomainEvent
```

Provider 不得强迫所有事件源实现轮询，也不得让核心调度依赖具体领域字段。

## 接入模式

### 轮询型

适用于状态 API 等定期采集来源。scheduler 按 provider 配置调度，使用租约避免多个实例
重复轮询。失败时保留旧状态，不得把请求失败误判为状态变化。

### 定时型

适用于固定日程、周期提醒和内部计划任务。时间计算统一使用 UTC，展示时再转换时区。
同一时间窗口必须生成稳定 `dedupe_key`。

### Webhook 型

适用于外部系统主动推送。每个来源使用独立路径、签名密钥、时间戳校验和重放保护。
请求先持久化最小接收记录，再异步规范化；不得在 Webhook 请求线程中发送通知。

### 可信内部发布

发布者只能发布被授权的事件命名空间。payload 必须符合已注册 schema，并提供幂等键。
不得提供匿名或普通用户可调用的任意事件发布接口。

## 通用约束

- 选择稳定的 `<domain>.<resource>.<event>` 事件键和独立 schema 版本。
- `identity` 必须稳定、可复现。
- 时间必须带时区并统一转为 UTC。
- `evaluate(None, current)` 默认只建立基线，只有 metadata 明确允许时才发布初始事件。
- `dedupe_key` 必须稳定、可复现，并与事件语义窗口一致。
- Provider 不得读写用户、订阅或 delivery 表。
- Provider 不得直接发送消息或调用 LLM。
- Provider 返回的数据必须经过 schema 校验后才能进入核心事件存储。
- Provider 异常只能影响自身调度，不得阻塞其他 provider 或内部 API。
- 每个 provider 有独立的并发上限、速率限制、熔断状态和最近成功时间。
- Provider 配置只能来自管理员配置或受控部署，不接受普通用户提供的 URL、代码、SQL 或
  模板表达式。

轮询 provider 的 HTTP 客户端必须使用受控固定地址、连接和读取超时、响应大小上限、
有限重试、明确 User-Agent 和 SSRF 防护。网络失败保留旧 checkpoint，不能产生状态变化
事件。

## 注册与测试

最低步骤：

1. 选择稳定的 `<domain>.<resource>.<event>` 事件键和独立 schema 版本。
2. 实现 `metadata`、`validate_config`、`normalize`、`evaluate`、`render`、`health`。
3. 在应用组合层 `eventserver.providers.build_registry` 显式注册。
4. 增加首次基线、无变化、变化、异常、重复输入和 renderer 快照测试。
5. 在测试环境先观察而不开放订阅，验证去重、模板、速率限制与故障隔离后再启用。

每个 provider 的最低交付物：

- `ProviderMetadata` 和配置 schema。
- Observation、DomainEvent payload schema 和示例。
- 正常、无变化、异常、超时和重复数据 fixture。
- trigger 幂等测试和 renderer 快照测试。
- 数据源使用限制、负责人和故障处理说明。
- 指标：调用次数、耗时、失败数、最近成功时间、发布事件数。
