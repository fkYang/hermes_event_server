# demo-reminder Publisher（演示用一次性提醒）

最小的「定时」Publisher：调用方给一个延迟参数（`5m`、`10min`、`90s`、`1h`）或一个绝对
时间，它就把这次请求发布成一次事件，并把提醒时刻写成 `notify_at`。EventServer 到点后才让
该 delivery 可领取，Plugin 再私聊订阅者。

它不连接 MySQL，不保存用户或订阅数据，不发送 QQ 消息，只持有一个受命名空间限制的
Publisher Token。源码、构建和运行全部自包含在本目录，与 EventServer 核心各自发布。

```text
调用方（curl / CLI） -> demo-reminder -> POST /v1/publish/events (notify_at) -> EventServer outbox -> Hermes Plugin
```

## 1. 目录内容

```text
demo-reminder/
├── Dockerfile
├── pyproject.toml
├── compose.example.yml      # 独立运行时的 compose 定义
├── config/                  # 事件目录 JSON
└── src/demo_reminder/
```

## 2. 构建镜像

```bash
docker build -t autoqq-demo-reminder:0.1.0 .
```

运行期只依赖 Python 标准库；除基础镜像外，构建过程不需要下载依赖。

镜像分发二选一：

```bash
# 推送到 registry
docker tag autoqq-demo-reminder:0.1.0 <registry>/autoqq-demo-reminder:0.1.0
docker push <registry>/autoqq-demo-reminder:0.1.0

# 或直接传到目标主机
docker save autoqq-demo-reminder:0.1.0 | gzip -1 \
  | ssh <host> 'gunzip | /usr/local/bin/docker load'
```

## 3. 配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `EVENTSERVER_URL` | 必填 | EventServer 地址，例如 `http://autoqq-eventserver-api:8080` |
| `PUBLISHER_TOKEN` | 必填 | 至少 32 字符，与 EventServer 中注册的 Publisher 身份一致 |
| `INGRESS_TOKEN` | 必填（HTTP 模式） | 演示入口的 Bearer Token，至少 16 字符；缺失时容器拒绝启动 |
| `HTTP_HOST` / `HTTP_PORT` | `0.0.0.0` / `8080` | 演示入口监听地址 |
| `DEFAULT_DELAY_SECONDS` | `300` | 请求没给延迟时使用的默认值 |
| `MAX_DELAY_SECONDS` | `3600` | 允许的最大延迟；超过返回 400 |
| `REQUEST_TIMEOUT_SECONDS` | `10` | 调用 EventServer 的超时 |
| `MAX_BODY_BYTES` | `16384` | 演示入口的请求体上限 |
| `DISPLAY_TIMEZONE` | `Asia/Shanghai` | 通知正文里展示的时区 |

## 4. 运行

```bash
docker run -d --name autoqq-demo-reminder \
  --restart unless-stopped \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --network hermes_net \
  -p 18090:8080 \
  -e EVENTSERVER_URL=http://autoqq-eventserver-api:8080 \
  -e PUBLISHER_TOKEN=<至少 32 字符> \
  -e INGRESS_TOKEN=<至少 16 字符> \
  autoqq-demo-reminder:0.1.0
```

或用 Compose：

```bash
cp .env.example .env && chmod 600 .env    # 填写 PUBLISHER_TOKEN 与 INGRESS_TOKEN
docker compose --env-file .env -f compose.example.yml up -d
```

## 5. 演示入口

```http
POST /v1/reminders
Authorization: Bearer <INGRESS_TOKEN>
Content-Type: application/json
```

```json
{"delay": "5m", "text": "5 分钟后提醒我一下"}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `text` | 是 | 提醒内容，1–500 字符 |
| `title` | 否 | 标题，默认「演示提醒」 |
| `delay` | 否 | `5m` / `10min` / `90s` / `1h`；纯数字按**分钟**解释，缺省用 `DEFAULT_DELAY_SECONDS` |
| `delay_seconds` | 否 | 直接给秒数，与 `delay`、`at` 互斥 |
| `at` | 否 | 绝对时间（ISO-8601，必须带时区），与 `delay`、`delay_seconds` 互斥 |
| `dedupe_key` | 否 | 显式去重键；同一个 key 重复提交只发布一次。缺省每次请求各自生成 |

示例：

```bash
# 5 分钟后提醒
curl -sS -X POST http://192.168.1.4:18090/v1/reminders \
  -H "Authorization: Bearer $INGRESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"delay":"5m","text":"5 分钟后提醒我一下"}'

# 10 分钟后提醒，带自定义标题
curl -sS -X POST http://192.168.1.4:18090/v1/reminders \
  -H "Authorization: Bearer $INGRESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"delay":"10min","title":"演示提醒","text":"10 分钟到了"}'

# 健康检查与用法（不需要 Token）
curl -sS http://192.168.1.4:18090/health
curl -sS http://192.168.1.4:18090/v1/reminders
```

响应：

```json
{
  "event_id": "1a2b...",
  "created": true,
  "deliveries_created": 1,
  "notify_at": "2026-09-17T12:05:00Z"
}
```

`created=false` 表示 `(event_key, dedupe_key)` 已存在，本次不会重复投递；
`deliveries_created=0` 表示当时没有有效订阅者。

## 6. 命令行一次性发布

不想开入口时，可以直接在容器里跑一次（同样只需要 `EVENTSERVER_URL` 与 `PUBLISHER_TOKEN`）：

```bash
docker run --rm --network hermes_net \
  -e EVENTSERVER_URL=http://autoqq-eventserver-api:8080 \
  -e PUBLISHER_TOKEN=<至少 32 字符> \
  autoqq-demo-reminder:0.1.0 \
  python -m demo_reminder.cli --delay 5m --text "5 分钟后提醒我一下"
```

## 7. 发布的事件

| event_key | 触发 | `dedupe_key` | 投递时间 |
| --- | --- | --- | --- |
| `demo.reminder.scheduled` | 每次接受一个提醒请求 | 请求的 `dedupe_key`，缺省为随机值 | 请求的 `notify_at`（`now + delay` 或 `at`），由 EventServer 调度 |

事件数据：

```json
{
  "request_id": "0f4c...",
  "delay_seconds": 300,
  "notify_at": "2026-09-17T12:05:00Z"
}
```

通知正文形如：

```text
5 分钟后提醒我一下
提醒时间：09-17 20:05（UTC+08:00，5 分钟后）
```

事件没有关注项（`match_keys`），绑定该事件即接收全部演示提醒；同一时刻只投递一次，
不会因为提前量而重复触发。

## 8. 上线前置条件

EventServer 侧需要两件事，否则本服务发布时会被拒绝（403/422）：

1. 事件目录里已启用 `demo.reminder.scheduled`，schema 版本为 1 —— `config/event-catalog.json`
   就是对应的目录定义；
2. 存在一个只允许 `demo.` 前缀的 Publisher 身份，其 Token 与本服务的 `PUBLISHER_TOKEN` 一致。

```bash
# 在 EventServer 主机上（容器或本机虚拟环境）
python -m eventserver.catalog_admin register --file config/event-catalog.json
PUBLISHER_TOKEN='<至少 32 字符>' \
  python -m eventserver.publisher_admin \
  --publisher-key demo-reminder --token-env PUBLISHER_TOKEN --allow-prefix demo. \
  --description "演示用一次性定时提醒"
```

## 9. 与 QQ 侧联调

1. 用户私聊机器人执行 `/events`，确认能看到「演示定时提醒」；
2. `/bind demo.reminder.scheduled` 完成绑定（该事件没有关注项，无需额外参数）；
3. 用第 5 节的 curl 发一条 `5m` 的提醒；
4. 约 5 分钟后收到私聊消息，即整条链路（Publisher → EventServer outbox → Plugin → QQ）打通。

> 投递由 Plugin 轮询领取，实际到达时间取决于 Plugin 的轮询间隔与租约，通常在本时刻之后
> 的一个轮询周期内。

## 10. 验证

```bash
docker logs --since 30m autoqq-demo-reminder
```

正常形态是每次接受一条提醒就一行 INFO：

```text
INFO accepted reminder event_id=1a2b... created=True deliveries_created=1 notify_at=2026-09-17T12:05:00Z
```

请求参数错误返回 400，EventServer 拒绝发布返回 502，日志里不记录提醒正文。

## 11. 本地测试

```bash
../../.venv/bin/python -m pytest -q
```

测试使用假 Publisher 与临时端口，不访问真实 EventServer，也不发送 QQ 消息。
（HTTP 用例需要在本机回环地址上监听临时端口。）
