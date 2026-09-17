# Scheduled Reminder Publisher

独立的定时提醒 Publisher。它不连接 MySQL；只在到点时通过受控的
`POST /v1/publish/events` 向 EventServer 发布 `reminder.scheduled.triggered`。

## 支持的规则

`weekly` 规则可选择一个或多个星期和多个时间点。星期使用英文小写名称；例如每周日 09:00
和 18:30：

```json
{
  "id": "sunday-status",
  "kind": "weekly",
  "timezone": "Asia/Shanghai",
  "weekdays": ["sunday"],
  "times": ["09:00", "18:30"],
  "title": "周日提醒",
  "text": "这是本周设定的提醒。"
}
```

`interval` 规则从带时区的 `anchor_at` 开始，每 `every_minutes` 分钟一次：

```json
{
  "id": "two-hour-review",
  "kind": "interval",
  "timezone": "Asia/Shanghai",
  "anchor_at": "2026-09-16T09:00:00+08:00",
  "every_minutes": 120,
  "title": "定时回顾",
  "text": "请进行一次简短回顾。"
}
```

同一配置可包含任意多个规则；空 `reminders: []` 是有效的停用状态，适合先部署服务再配置真实
提醒。完整示例见 [reminders.example.json](config/reminders.example.json)。
每次触发的 `dedupe_key` 是 `<提醒 ID>:<计划 UTC 时间>`；Publisher 重启或网络失败后的重试不
会由 EventServer 产生重复 delivery。首次启动只从当前时间开始观察，不追溯补发旧提醒。

## 配置与上线

1. 将示例配置复制到部署机受控目录，例如 `config/reminders.json`；不得放入 Token。
2. 先在 EventServer 注册事件目录：

   ```bash
   docker compose --env-file .env -f compose.yml run --rm \
     autoqq-eventserver-api python -m eventserver.catalog_admin register \
       --file /受控路径/event-catalog.json
   ```

3. 使用至少 32 个字符的 Secret 创建 Publisher 身份，最小权限前缀为 `reminder.`：

   ```bash
   docker compose --env-file .env -f compose.yml run --rm \
     -e SCHEDULED_REMINDER_PUBLISHER_TOKEN \
     autoqq-eventserver-api python -m eventserver.publisher_admin \
       --publisher-key scheduled-reminder \
       --token-env SCHEDULED_REMINDER_PUBLISHER_TOKEN \
       --allow-prefix reminder. \
       --description 'Scheduled reminder publisher'
   ```

4. 以独立 Compose 项目构建和启动该服务：

   ```bash
   docker build -t autoqq-scheduled-reminder-publisher:0.1.0 .
   docker compose --env-file .env -f compose.example.yml up -d
   ```

它与 EventServer API 使用同一内网 Docker 网络，但不共享镜像、数据库账号或内部服务 Token。
