# Publisher 开发说明

Publisher 是与 EventServer 核心独立部署的事件源适配器。它可以轮询固定数据源、执行定时任务
或接收已验签的上游 Webhook，但不得连接 EventServer MySQL、直接发送 QQ 消息或调用 LLM。

```text
受控数据源 -> 独立 Publisher -> POST /v1/publish/events -> EventServer outbox -> Hermes Plugin
```

## Publisher 职责

- 使用固定、受控且可审计的数据源地址；HTTP 客户端必须设置超时、响应大小上限、有限重试和
  明确 User-Agent。
- 规范化来源数据，完成状态比较、时间计算和业务判定。
- 为每个事件生成稳定的 `dedupe_key`，并提供带时区的 `occurred_at`。
- 提供渠道无关的 `DeliveryMessage`；至少包含 `default` locale，可按 locale 提供额外消息。
- 用只属于自己的 Bearer Token 调用 EventServer 内网地址。

## 核心强制执行的边界

每个 Publisher 在数据库中有一个不可共享的身份：

- Token 只保存 SHA-256 哈希；原始 Token 只通过部署 Secret/环境变量交给 Publisher。
- Publisher 只能发布其 `allowed_event_prefixes` 中的 `<domain>.` 命名空间。
- 事件必须已在目录中注册、启用，且 schema 版本精确一致。
- `data` 必须符合目录中受限的结构化 JSON Schema。
- EventServer 使用 `(event_key, dedupe_key)` 去重，并只为当时具有 `active + command=true`
  的订阅者创建 delivery。

Publisher 不能创建事件目录、授权用户、读取订阅、领取 delivery，或绕过 EventServer 直接访问
QQ/Hermes 凭据。

## 发布请求

```http
POST /v1/publish/events
Authorization: Bearer <PUBLISHER_TOKEN>
Content-Type: application/json
```

```json
{
  "event_key": "example.sample.available",
  "schema_version": 1,
  "dedupe_key": "stable-source-window",
  "occurred_at": "2026-09-16T12:00:00Z",
  "notify_at": "2026-09-16T12:55:00Z",
  "subject": {"type": "resource", "id": "stable-id"},
  "data": {"state": "available", "match_keys": ["example-target"]},
  "messages": {
    "default": {
      "title": "事件提醒",
      "text": "事件已触发",
      "data": {},
      "template_key": "example.sample.available.default",
      "template_version": 1
    }
  }
}
```

`event_id` 由 EventServer 生成。重复提交相同事件键和去重键会返回既有 ID 并且不再创建
delivery。响应与日志不得包含 Token、完整外部 payload 或完整 OpenID。

两个可选字段值得注意：

- `notify_at`（带时区的 ISO-8601）：把这次发布产生的 delivery 推迟到该时刻，值是
  `max(now, notify_at)`；已过去按立即投递处理，超过 `DELIVERY_MAX_SCHEDULE_HORIZON_SECONDS`
  （默认 24 小时）会被拒绝。用于「提前 N 分钟通知」这类场景，核心不猜测提前量。
- `data` 里由目录声明的匹配键数组（`match_key_field` 指向的字段）：订阅方可以只关注其中
  一部分值，只有与该订阅的 `match_keys` 有交集时才会为该用户创建 delivery。声明了
  `match_keys_required` 的事件，用户绑定时必须至少给出一项。键的取值范围由目录的
  `match_key_options` 限定，普通用户不能写入目录之外的任意值。

完整的目录字段与投递语义见 [EventServer Contract](../CONTRACT.md) 的 §7.1 与 §7.2。

## 上线步骤

1. 设计稳定事件键、schema、`dedupe_key` 和异常/超时策略。
2. 用 `eventserver.publisher_admin` 创建或轮换 Publisher Token，并限定最小命名空间前缀。
3. 用 `eventserver.catalog_admin` 从受控 JSON 文件注册事件目录。
4. 部署 Publisher；它与 EventServer 分别构建、发布和回滚。
5. 以无订阅或测试订阅观察请求、schema、去重和失败隔离后再开放订阅。

新增 Publisher 或事件配置不得修改 EventServer 镜像、权限、订阅、outbox 或 Plugin 核心代码。
