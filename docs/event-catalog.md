# 内置事件目录

| event_key | provider_key | schema | 触发条件 |
| --- | --- | ---: | --- |
| `warframe.cetus.night` | `warframe.cetus_night` | 1 | `is_night` 从 false 变为 true |
| `warframe.konzu.rotation` | `warframe.konzu_rotation` | 1 | 稳定 `rotation_id` 发生变化 |
| `warframe.ghoul.started` | `warframe.ghoul_event` | 1 | `active` 从 false 变为 true |

兼容别名 `cetus_night`、`konzu_rotation`、`ghoul_event` 仅用于迁移旧订阅；数据库新记录
统一保存规范事件键。

provider 接收 adapter 已校验后的标准化字段。2026-09-14 已用官方
WorldState 脱敏结构样本确认：

- `SyndicateMissions[Tag=CetusSyndicate]` 的 Expiry 是 Cetus 夜晚结束点，最后 3000 秒为夜晚。
- Konzu 轮换用同一记录的 `Seed + Expiry` 作为稳定身份；任务详情没有可靠直接字段时不推测。
- `Goals[Tag=InfestedPlains]` 且当前时间位于 Activation/Expiry 内、未成功结束时视为尸鬼活动。

最小相关字段 fixture 位于 `tests/fixtures/worldstate_relevant.json`，不保存完整实时 payload。
