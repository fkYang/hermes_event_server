# wf-data Publisher

独立的事件发布服务：轮询 wf-data 的 Cetus 赏金接口，把每一轮出现的任务集合发布给
EventServer，由 EventServer 决定谁会收到通知。

它不连接 MySQL，不保存用户或订阅数据，不发送 QQ 消息；只持有一个受命名空间限制的
Publisher Token。源码、构建和运行全部自包含在本目录。

## 1. 目录内容

```text
wf-data/
├── Dockerfile
├── pyproject.toml
├── compose.example.yml      # 独立运行时的 compose 定义
├── config/                  # 两个事件的目录 JSON
└── src/wfdata_publisher/
```

## 2. 构建镜像

```bash
docker build -t autoqq-wfdata-publisher:0.1.1 .
```

运行期只依赖 Python 标准库；除基础镜像外，构建过程不需要下载依赖。

镜像分发二选一：

```bash
# 推送到 registry
docker tag autoqq-wfdata-publisher:0.1.1 <registry>/autoqq-wfdata-publisher:0.1.1
docker push <registry>/autoqq-wfdata-publisher:0.1.1

# 或直接传到目标主机
docker save autoqq-wfdata-publisher:0.1.1 | gzip -1 \
  | ssh <host> 'gunzip | /usr/local/bin/docker load'
```

## 3. 配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WF_DATA_URL` | 必填 | wf-data 的 Cetus 赏金接口，例如 `http://wf-data:8080/warframe/cetus/tent-bounties` |
| `EVENTSERVER_URL` | 必填 | EventServer 地址，例如 `http://autoqq-eventserver-api:8080` |
| `PUBLISHER_TOKEN` | 必填 | 至少 32 字符，与 EventServer 中注册的 Publisher 身份一致 |
| `POLL_SECONDS` | `60` | 轮询间隔；`next` 只在一轮开始前约 10 分钟可见，间隔不宜过大 |
| `LEAD_SECONDS` | `300` | 下一轮事件的提前通知秒数 |
| `REQUEST_TIMEOUT_SECONDS` | `10` | 两个 HTTP 调用的超时 |
| `MAX_RESPONSE_BYTES` | `262144` | wf-data 响应大小上限 |
| `DISPLAY_TIMEZONE` | `Asia/Shanghai` | 通知正文中展示的时区 |

## 4. 运行

容器需要同时能够访问 wf-data 与 EventServer。若两者在同一 Docker 主机，把它加入对应网络；
若 wf-data 与 EventServer 不在同一网络，则同时加入两个（示例见 `compose.example.yml`）。

```bash
docker run -d --name autoqq-wfdata-publisher \
  --restart unless-stopped \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --network hermes_net \
  -e WF_DATA_URL=http://wf-data:8080/warframe/cetus/tent-bounties \
  -e EVENTSERVER_URL=http://autoqq-eventserver-api:8080 \
  -e PUBLISHER_TOKEN=<至少 32 字符> \
  autoqq-wfdata-publisher:0.1.1
```

或用 Compose：

```bash
cp .env.example .env && chmod 600 .env    # 填写 WFDATA_PUBLISHER_TOKEN
docker compose --env-file .env -f compose.example.yml up -d
```

## 5. 发布的事件

| event_key | 触发 | `dedupe_key` | 投递时间 |
| --- | --- | --- | --- |
| `warframe.cetus.bounty_current` | 观测到新的 `current.activation` | `current.activation`（UTC 秒） | 立即 |
| `warframe.cetus.bounty_next` | 观测到新的 `next.activation` | `next.activation`（UTC 秒） | `activation − LEAD_SECONDS` |

同一 activation 在进程内只发布一次；进程重启后重复发布会由 EventServer 的
`(event_key, dedupe_key)` 唯一约束吸收，因此本服务不需要保存任何本地状态。

扫描范围按事件区分：

| 事件 | 扫描 | 不扫描 |
| --- | --- | --- |
| `bounty_current` | `current` 的三个 tent 槽位全部任务 + `konzu.normal` 中 `tier == 5` 的那条 | `normal` 的 tier 1–4、`steelPath`、`narmer` |
| `bounty_next` | `next` 的三个 tent 槽位全部任务 | 所有 konzu 分组 |

`next` 不扫描 konzu，因为 wf-data 只返回当前时段的 konzu（`CetusTentBountyResponse` 的字段是
`current;next;konzu;imageUrl`，其中只有一个 `konzu`）。两个事件的可关注目录都是完整的 13 项，
所以只出现在 konzu 的任务要等它成为当前轮次后，由 `bounty_current` 通知。

## 6. 事件数据

```json
{
  "window": "current",
  "activation": "2026-09-17T03:48:51Z",
  "expiry": "2026-09-17T06:18:50Z",
  "match_keys": ["RescueBountyResc", "ReclamationBountyCap"],
  "jobs": [
    {"key": "RescueBountyResc", "name_zh": "搜索并救援", "source": "tentA", "tier": null}
  ]
}
```

`match_keys` 是订阅过滤使用的维度，`jobs[]` 保留来源与中文名供展示和排错。

## 7. 上线前置条件

EventServer 侧需要先具备两件事，否则本服务发布时会被拒绝（403/422）：

1. 事件目录里已启用 `warframe.cetus.bounty_current` 与 `warframe.cetus.bounty_next`，
   schema 版本为 1 —— `config/` 下的两个 JSON 就是对应的目录定义。
2. 存在一个只允许 `warframe.cetus.` 前缀的 Publisher 身份，其 Token 与本服务的
   `PUBLISHER_TOKEN` 一致。

这两步属于 EventServer 的部署操作，命令见
[Provider 开发说明](../../docs/provider-development.md) 与
[wf-data Publisher 设计稿](../../docs/wf-data-publisher.md)。

## 8. 验证

```bash
docker logs --since 30m autoqq-wfdata-publisher
```

正常形态是每个轮换窗口一行 INFO，含扫描范围与任务数量：

```text
INFO published warframe.cetus.bounty_current with dedupe key 2026-09-17T11:18:48Z (tent+konzu, 7 match keys)
INFO published warframe.cetus.bounty_next with dedupe key 2026-09-17T13:48:47Z (tent-only, 7 match keys)
```

同一窗口内重复轮询不再重复记录；只有「当前轮次从源里消失」或「当前轮次缺少 konzu」这类
异常才会额外出现一条 WARNING，且每个窗口最多一次。

## 9. 本地测试

```bash
python -m pytest
```

测试使用仓库内的样例响应固件，不访问真实 wf-data，也不连接 EventServer。
