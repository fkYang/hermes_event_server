# AutoQQ EventServer Contract

> 本文定义 EventServer 的核心边界、事件模型、数据库不变量、内部 API 和投递契约。
> 部署、配置、迁移、首管理员、升级和故障排查见 `README.md`；provider 实现细节见
> `docs/provider-development.md`；事件清单见 `docs/event-catalog.md`。

## 1. 范围与边界

EventServer 是通用事件采集、判定、发布和投递服务，负责：

- 用户、角色、账号状态、`chat`/`command` 权限和订阅。
- 事件类型、schema、别名和受控 Publisher 注册。
- 受控 Publisher 的可信内部发布接入。
- 事件与 delivery 幂等持久化。
- delivery 领取租约、成功或失败回写、有限重试和 dead 状态。
- 内部 API、健康检查、指标、审计和 Publisher 故障隔离。

EventServer 不负责：

- 直接调用 Hermes、腾讯 QQ API 或 LLM。
- 保存 QQ AppID、QQ Secret 或 LLM Key。
- 允许普通用户提交任意 URL、脚本、SQL 或模板表达式。
- 将某个 Publisher 的领域字段泄漏到核心鉴权、订阅或 outbox。

EventServer 是权限、订阅、事件和投递状态的唯一事实来源，也是唯一允许访问 MySQL 的
项目。

## 2. 核心分层

```text
外部数据源 / 内部系统
              |
              v
独立 Publisher（采集、规范化、判定）
              |
              v
  受控内部发布 API（鉴权、命名空间、schema）
              |
              v
       Event Store + Subscription
              |
              v
          Delivery Outbox
              |
       claim / lease / ack / fail
              |
              v
       Hermes AutoQQ Plugin
              |
              v
         QQ 用户私聊
```

核心模块只能依赖通用契约：

- `publisher`：在核心镜像外取得原始数据、完成判定并提交消息，不访问 MySQL。
- `catalog`：由部署管理员管理 event schema，不执行模板或表达式。
- `subscription`：根据稳定 `event_key` 查找有效订阅者。
- `outbox`：创建、领取、回写和重试 delivery。
- `channel consumer`：由 Plugin 实现，EventServer 不包含 QQ 发送代码。

新增事件必须作为独立 Publisher 和目录配置接入，不得修改权限、订阅、outbox 或 Plugin 核心逻辑。

## 3. 事件标识与版本

事件键采用：

```text
<domain>.<resource>.<event>
```

规则：

- `event_key` 一经发布不得改变含义。
- 语义变化时创建新键或提升 `schema_version`。
- 显示名称、描述和模板可以修改，但不能作为订阅主键。
- Publisher 实现版本与事件 schema 版本分开管理。
- 旧键下线前先标记 deprecated，提供迁移映射和观察期。
- 迁移期可以使用别名；数据库最终只保存规范键。

## 4. 核心数据契约

### 4.1 Observation

normalizer 输出：

```json
{
  "provider_key": "warframe.cetus_night",
  "schema_version": 1,
  "identity": "stable-source-identity",
  "observed_at": "ISO-8601 UTC",
  "effective_at": "ISO-8601 UTC",
  "expires_at": "ISO-8601 UTC or null",
  "state": {},
  "source_metadata": {
    "source": "warframe-worldstate"
  }
}
```

要求：

- `identity` 必须稳定且可复现。
- `state` 必须符合 provider 的版本化 schema。
- 时间必须带时区并统一转为 UTC。
- `source_metadata` 不得包含 Token 或大体积原始响应。

### 4.2 DomainEvent

trigger 产生：

```json
{
  "event_id": "deterministic-or-server-generated-id",
  "event_key": "warframe.cetus.night",
  "schema_version": 1,
  "dedupe_key": "stable-deduplication-key",
  "occurred_at": "ISO-8601 UTC",
  "subject": {
    "type": "location",
    "id": "cetus"
  },
  "data": {},
  "metadata": {
    "provider_key": "warframe.cetus_night"
  }
}
```

核心层只依赖 `event_key`、`schema_version`、`dedupe_key`、时间和通用 envelope。领域字段
全部位于 `subject` 和 `data`。

### 4.3 DeliveryMessage

renderer 输出渠道无关的消息：

```json
{
  "title": "事件提醒",
  "text": "希图斯已进入夜晚",
  "data": {},
  "template_key": "warframe.cetus.night.default",
  "template_version": 1
}
```

第一版以纯文本为主。Plugin 负责验证渠道限制和安全分段；EventServer 不硬编码 QQ API 参数，
也不执行模板。

## 5. 数据库模型与不变量

最低数据模型：

| 表 | 主键或唯一约束 | 用途 |
| --- | --- | --- |
| `users` | PK `(platform, openid)` | 用户、角色和 `active/blocked` 状态 |
| `user_permissions` | PK `(platform, openid, permission_key)` | 独立保存 `chat`、`command` |
| `event_types` | PK `event_key` | 事件目录、schema 和启停状态 |
| `event_publishers` | PK `publisher_key` | Publisher Token 哈希、命名空间前缀和启停状态 |
| `event_aliases` | PK `alias_key` | 旧键迁移映射 |
| `provider_instances` | PK `provider_instance_id` | provider 类型、配置和调度 |
| `provider_checkpoints` | PK `provider_instance_id` | 游标、状态哈希和调度租约 |
| `observations` | PK `observation_id`; UNIQUE `(provider_instance_id, identity)` | 标准化观察历史 |
| `event_occurrences` | PK `event_id`; UNIQUE `(event_key, dedupe_key)` | 已发布事件 |
| `subscriptions` | PK `(platform, openid, event_key)` | 用户订阅、关注项过滤与投递资格 |
| `deliveries` | PK `delivery_id`; UNIQUE `(event_id, platform, openid)` | 投递、租约和重试 |
| `pairing_codes` | PK `code_hash` | 一次性授权码 |
| `audit_logs` | PK `audit_id` | 管理与配置审计 |
| `webhook_receipts` | PK `receipt_id`; UNIQUE `(source_key, external_id)` | Webhook 防重放 |

数据库要求：

- 使用 MySQL 8、InnoDB 和 `utf8mb4`。
- 时间统一存储为 UTC。
- 账号状态与具体权限分离。
- `blocked` 优先于所有权限；删除权限不能代替封禁。
- JSON payload、schema 和配置使用 MySQL `JSON`。
- 敏感配置只保存 Secret 引用，不保存明文。
- 事件和 delivery 使用唯一约束保证幂等。
- `deliveries` 至少包含 `status`、`attempts`、`next_attempt_at`、`lease_owner`、
  `lease_token_hash`、`lease_until`、`last_error_code` 和更新时间。
- 迁移由 Alembic 管理；应用启动不得静默修改生产表结构。
- 多实例领取使用事务、行级锁和 `SKIP LOCKED`，不使用 Redis 分布式锁。

## 6. 内部 API

第一版对 Plugin 提供：

```text
GET    /health
GET    /ready
GET    /v1/events

GET    /v1/users/{openid}/permission
POST   /v1/users/{openid}/grant
POST   /v1/users/{openid}/revoke
POST   /v1/users/{openid}/role

GET    /v1/users/{openid}/subscriptions
POST   /v1/users/{openid}/subscriptions
DELETE /v1/users/{openid}/subscriptions/{event_key}

POST   /v1/pairing-codes
POST   /v1/pairing-codes/{code}/approve

POST   /v1/deliveries/claim
POST   /v1/deliveries/{delivery_id}/ack
POST   /v1/deliveries/{delivery_id}/fail

POST   /v1/publish/events
```

统一错误响应：

```json
{
  "code": "EVENT_NOT_FOUND",
  "message": "不支持该事件",
  "request_id": "..."
}
```

API 要求：

- 除健康检查外，所有接口校验服务身份。
- 内部 API 只绑定容器或内网接口，不直接暴露公网。
- 管理员写操作再次校验操作者为 `active + command=true + role=admin`。
- `grant`、`revoke` 必须显式指定 `permissions: ["chat"]`、`["command"]` 或两者。
- 权限查询分别返回账号状态、角色、`chat` 和 `command`。
- 重复订阅、取消订阅、授权和撤销保持幂等。
- 管理员不能移除最后一个有效管理员。
- `ack`、`fail` 只有匹配当前有效租约时才能更新状态。
- 所有发布、配置和管理员操作写入审计。
- `/v1/publish/events` 仅接受独立 Publisher Token；Token 使用哈希保存，且每个 Publisher 只能
  发布其被授予前缀下、已启用且 schema 版本一致的事件。

权限响应：

```json
{
  "platform": "qqbot",
  "openid": "CURRENT_USER_OPENID",
  "account_status": "active",
  "role": "user",
  "permissions": {
    "chat": false,
    "command": true
  }
}
```

语义：

- `chat=true` 只允许普通消息进入 LLM。
- `command=true` 只允许 `authorized` 命令、订阅管理和事件通知。
- `role=admin` 还必须同时满足 `active` 和 `command=true`。
- 角色修改不隐式修改权限。
- 不存在用户返回明确的 unknown 状态，不能与服务错误混淆。
- `blocked` 拒绝所有操作，包括 `public` 命令。
- 撤销 `command` 后保留订阅但暂停 delivery；恢复后不补发停权期间事件。

## 7. 事件处理与发布

```text
独立 Publisher 采集并判定
  -> 提交 DomainEvent envelope 与 locale 消息
  -> 核心校验 Publisher、命名空间和 payload schema
  -> 以 event_key + dedupe_key 幂等写入 event_occurrences
  -> 查找 active + command=true 的有效订阅者
  -> renderer 生成 DeliveryMessage
  -> 同一事务创建唯一 deliveries
  -> Plugin 领取并发送
  -> Plugin 回写 ack/fail
```

规则：

- 基线、状态变化、定时和数据源失败语义属于 Publisher；核心只接收完成判定的事件。
- 事件记录和 delivery 创建必须可恢复、可审计。
- Publisher 重试与 delivery 重试相互独立。
- renderer 失败不得破坏已经发布的 DomainEvent。
- 订阅只能指向已注册、可订阅且启用的事件类型。
- `chat` 不影响订阅和通知；通知资格只依赖 `command`。

### 7.1 订阅关注项过滤

事件目录可以为一个事件声明匹配维度，让用户只关注该事件下的部分内容，而不需要为每个可关注
项单独建事件键：

- `event_types.match_key_field`：可空字符串，指向事件 `data` 中承载匹配键数组的字段名。
- `event_types.match_key_options`：受控的 `[{key, label}]` 列表，用于 `/events` 展示可选项，
  也是校验订阅关注项的唯一依据。声明了 `match_key_field` 就必须同时声明非空的
  `match_key_options`，否则订阅无法表达任何关注项。
- `event_types.match_keys_required`：布尔值，缺省 false。为 true 时订阅必须显式指定至少一个
  关注项，避免「不指定就等于订阅全部」在轮换类事件上产生误订阅。
- `subscriptions.match_keys`：JSON 字符串数组，可为空。空表示关注该事件的全部内容；目录声明
  `match_keys_required = true` 时，空值必须被拒绝。

投递规则：事件目录声明了 `match_key_field`，且订阅的 `match_keys` 非空时，只有当
`data[match_key_field]` 与订阅的 `match_keys` 有交集才创建 delivery。核心只做集合交集，
不解释键的含义；键的取值范围由目录声明限定，普通用户无法写入目录之外的任意值。

订阅关注项可以在创建订阅时一并提交。重复提交同一 `event_key` 时 `match_keys` 以最后一次
为准（幂等 upsert），并写入审计。

### 7.2 计划投递时间

`POST /v1/publish/events` 可以携带可选字段 `notify_at`（带时区的 ISO-8601）：

- EventServer 用它设置该次发布所产生 delivery 的 `next_attempt_at`，取 `max(now, notify_at)`。
- `notify_at` 在未来时，delivery 保持 `pending` 且在到点前不可被领取，领取逻辑无需修改。
- `notify_at` 早于当前时间时按当前时间处理，即立刻可投递。
- 超过部署配置上限（默认 24 小时）的未来时间被拒绝，避免长期悬挂的 pending 记录。
- Publisher 用它表达「提前通知」；核心不猜测提前量，也不按订阅保存每用户的提前偏好。

## 8. Delivery 契约

Plugin 调用 `POST /v1/deliveries/claim`。EventServer：

- 只领取 `pending` 或到达 `next_attempt_at` 的 `retry`。
- 将过期 `leased` 恢复为可领取，但不影响有效租约。
- 在同一事务中锁定候选记录并更新为 `leased`。
- 返回 `delivery_id`、一次性租约 Token、目标、通知内容、尝试次数和通用事件标识。
- 不暴露 Publisher 私有配置、数据库内部字段或原始数据源响应。

Plugin 成功后调用 `ack`，失败后调用 `fail` 并报告脱敏错误码及是否可重试。EventServer
校验租约后更新为 `sent`、`retry` 或 `dead`。达到最大次数、明确不可重试或消息非法时
进入 `dead`，不得无限重发。

投递语义是至少一次。Plugin 发送成功但在 `ack` 前崩溃时可能重复发送。支持幂等键时
统一使用稳定 `delivery_id`；不支持时必须在运维文档中说明限制。

## 9. Publisher 契约

Publisher 自主实现采集、规范化、判定和消息生成；核心不加载其代码，也不启动其 scheduler。

约束：

- Publisher 不得读写用户、订阅或 delivery 表。
- Publisher 不得直接发送 QQ 消息或调用 LLM。
- 外部 HTTP 客户端必须设置超时、响应大小上限、User-Agent、有限重试和 SSRF 防护。
- Publisher 的事件 data 必须通过核心受限 JSON Schema 校验后才能进入事件存储。
- Publisher 异常只能影响自身，不得阻塞核心 API。
- Publisher 的地址、Token、配置和部署只能来自管理员受控配置。

接入模式、接口签名、测试要求和最低交付物见 `docs/provider-development.md`。

## 10. 故障隔离与可观测性

- 单个 Publisher 连续失败不得阻塞权限 API 或 delivery API。
- 日志包含 `request_id`、`publisher_key`、`event_id` 或 `delivery_id`。
- OpenID、pairing code、租约 Token 和外部 payload 必须脱敏。
- 指标至少覆盖 Publisher 调用失败、事件数、delivery 积压、租约过期、retry 和 dead。
- `/health` 表示进程存活；`/ready` 表示依赖就绪。
- 非关键 Publisher 故障不应使整个服务失去存活状态。
- 对异常积压、连续 Publisher 失败、Webhook 验签失败和 dead delivery 建立告警。

## 11. 安全与兼容性

- 数据库口令、内部 Token、Webhook Secret 和真实 OpenID 不进入 Git、日志或 fixture。
- Webhook 必须验签、校验时间戳并防重放。
- 内部 API 不直接暴露公网。
- 普通用户不能配置 URL、脚本、SQL、模板表达式或 Publisher 代码。
- 跨项目接口变更必须先更新版本化契约和双方契约测试。
- 不兼容的 Publisher、消息或事件结构变更必须提升 schema 版本。

## 12. 合规要求

实现和变更必须覆盖：

- Publisher 的首次基线、无变化、变化、超时和无效响应。
- `dedupe_key` 和 delivery 唯一约束。
- 多实例并发领取、租约过期、`ack/fail` 校验和有限重试。
- EventServer 和 Plugin 重启恢复。
- 权限四种组合、blocked 优先级和管理员约束。
- 撤销 `command` 后暂停 delivery，恢复后不补发。
- 敏感信息不进入日志。
- 新 Publisher 不修改权限、订阅、outbox 或 Plugin 核心代码。
- 迁移、备份、恢复、回退和 Publisher 下线流程具备可执行文档。
