# 事件目录状态

EventServer 不再在镜像中硬编码业务事件。事件目录由部署管理员通过
`eventserver.catalog_admin register --file <受控 JSON 文件>` 管理；新事件的 Publisher 与
EventServer 核心独立发布。

当前没有启用的内置事件。下面的旧事件会在执行新版本 bootstrap 后标记为 `disabled` 和
`deprecated`，但历史 occurrence、subscription 和 delivery 不删除：

| 历史 event_key | 原 Provider | 状态 |
| --- | --- | --- |
| `warframe.cetus.night` | `warframe.cetus_night` | 停用、保留审计记录 |
| `warframe.konzu.rotation` | `warframe.konzu_rotation` | 停用、保留审计记录 |
| `warframe.ghoul.started` | `warframe.ghoul_event` | 停用、保留审计记录 |

每个新目录项必须包含稳定的 `event_key`、显示信息、`schema_version` 和可选受限 JSON Schema。
语义不兼容时使用新事件键或显式迁移；不得把事件定义、源 URL、Token、脚本或模板表达式交给
普通用户配置。

## 已注册的目录项

两个 Cetus 事件由内部部署的 wf-data Publisher 发布：源码、目录 JSON 与部署说明只在仓库的
`wfdata` 分支维护，不随 `main` 发布。它们启用订阅关注项过滤（`match_key_field = "match_keys"`，
`match_keys_required = true`），用户绑定时必须至少指定一个关注任务；演示提醒事件没有关注项，
绑定即接收全部演示提醒，目录 JSON 见 `publishers/demo-reminder/config/`。

| event_key | 来源 | 可订阅 | 关注项 | 说明 |
| --- | --- | --- | --- | --- |
| `warframe.cetus.bounty_current` | wf-data Publisher（内部部署） | 是 | 任务 `jobId`（13 项） | 当前轮次：tent 三槽 + `konzu.normal` tier 5；命中关注项时立即投递 |
| `warframe.cetus.bounty_next` | wf-data Publisher（内部部署） | 是 | 任务 `jobId`（13 项） | 下一轮：仅 tent 三槽；`notify_at = activation − LEAD_SECONDS` 提前投递 |
| `demo.reminder.scheduled` | demo-reminder Publisher | 是 | 无 | 调用方用 `delay`（`5m`、`10min`…）或 `at` 指定时刻；`notify_at = requested_at + delay`，由 EventServer 调度投递 |

## 已废弃的目录项

| event_key | 来源 | 状态 |
| --- | --- | --- |
| `reminder.scheduled.triggered` | scheduled-reminder Publisher（已下线） | 停用+弃用，用户不再可见；订阅与历史 delivery 保留 |

恢复方式：把该 Publisher 加回 Compose、用 `catalog_admin register` 重新注册目录（`register`
会清除弃用标记），再启动服务。

演示提醒事件的完整说明见 `publishers/demo-reminder/README.md`；两个 Cetus 事件的关注项清单与
扫描范围随 `wfdata` 分支的 Publisher README 一起维护。
