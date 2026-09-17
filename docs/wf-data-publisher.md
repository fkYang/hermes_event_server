# wf-data Publisher（Cetus 赏金轮换监控）设计稿

> 状态：设计已确定，尚未实现。本文所有接口、事件键和配置项均为待实现，不代表已验证。
> 数据源结构为 2026-09-17 只读实测结果，不作为长期契约保证。

## 1. 目标

把 Cetus 赏金轮换作为两个独立事件接入，让不同用户各自绑定、各自选择关注的任务：

1. 当前轮次出现了关注任务。
2. 下一轮出现了关注任务，可提前通知。

## 2. 数据源

`GET http://wf-data:8080/warframe/cetus/tent-bounties`（容器内地址；宿主映射为
`192.168.1.4:18080`）。实测返回约 4 KiB，HTTP 200，顶层字段：

| 字段 | 结构 |
| --- | --- |
| `current` | `activation`、`expiry`、`tentA`、`tentB`、`tentC` |
| `konzu` | `activation`、`expiry`、`normal[]`、`steelPath[]`、`narmer[]`、`events[]` |
| `imageUrl` | 带签名的图片地址，Publisher 不使用，也不得写入事件 |
| `next` | 仅在下一轮开始前约 8 分钟内出现，结构与 `current` 一致 |

每个 `tentX` 含 `id`、`manifestTag`、`physicalNumber` 和 `jobs[]`，每个 job 为
`{id, path, nameZh}`。`konzu.*[]` 的每项为
`{tier, jobId, jobPath, nameZh, rewardPath, masteryReq, minEnemyLevel, maxEnemyLevel, xpAmounts}`。

### 2.1 扫描范围

两个事件的扫描范围不同，但共用同一份 13 项关注项目录：

| 来源 | 当前轮次事件 | 下一轮事件 | 说明 |
| --- | --- | --- | --- |
| `current` 的 `tentA` / `tentB` / `tentC` 的 `jobs[]` | 扫描 | — | 三个槽位全部任务 |
| `current` 的 `konzu.normal` 中 `tier == 5` | 扫描 | — | 只取 tier 5，tier 1–4 一律忽略 |
| `next` 的 `tentA` / `tentB` / `tentC` 的 `jobs[]` | — | 扫描 | 三个槽位全部任务 |
| `konzu.normal` 的 tier 1–4 | 否 | 否 | 不参与关注项 |
| `konzu.steelPath` | 否 | 否 | 当前不纳入；如需支持只关注钢铁之路版本，需另行评估 |
| `konzu.narmer` | 否 | 否 | 同上 |
| `konzu.events` | 否 | 否 | 实测为空数组 |

`next` **不扫描 konzu**：接口只返回当前时段的 konzu。`CetusTentBountyResponse` 的字段是
`current;next;konzu;imageUrl`——`current` 与 `next` 各是一个 `TentBountyPeriod`
（`activation;expiry;tentA;tentB;tentC`），而 `konzu` 只有一个 `KonzuBountySchedule`
（`activation;expiry;normal;steelPath;narmer;events`），属于当前时段。因此绑定
`warframe.cetus.bounty_next` 的用户只能提前收到 tent 槽位任务的预告；只出现在 konzu 的任务
要等它成为当前轮次后由 `warframe.cetus.bounty_current` 通知。两个事件的
`match_key_options` 都保留完整 13 项，避免用户看不到自己在意的任务。

扫描范围决定「什么时候可能触发」，`match_key_options` 决定「用户可以关注哪些」。两者都收窄
或放宽时，事件键、去重键和订阅语义均不受影响。

以实测快照为例，当前轮次扫描范围内去重后应为 8 项：`AssassinateBountyAss`、
`AttritionBountyLib`、`RescueBountyResc`、`ReclamationBountyCap`、`SabotageBountySab`、
`CaptureBountyCapOne`、`CaptureBountyCapTwo`、`AttritionBountyExt`（tier 5 的那条）；
同一轮的下一轮事件只取 tent 槽位，因此是 7 项（不含 `AttritionBountyExt`）。
`konzu.normal` tier 1–4 里的 `AssassinateBountyCap`、`ReclamationBountyCache` 不得出现在
任何结果中。该快照可直接作为固件。

实测轮换参数：`current.activation = 2026-09-17T11:48:51.773+08:00`，
`expiry = 14:18:50.647+08:00`，周期 150 分钟；`konzu.activation` 与 `current.activation`
完全相同，两块共用同一套轮换。

关注键取 job 的 `id`/`jobId`（如 `RescueBountyResc`）。Narmer 版本与普通版本使用同一
`jobId`、不同 `jobPath`；由于 `narmer` 当前不在扫描范围内，这一点暂不影响结果，但将来若
把 `narmer` 纳入扫描范围，就需要先决定是接受同键合并还是改用 `jobPath` 作为关注键。

## 3. 产出事件

| | 事件 1 | 事件 2 |
| --- | --- | --- |
| `event_key` | `warframe.cetus.bounty_current` | `warframe.cetus.bounty_next` |
| 触发时机 | 每次观测到新的 `current.activation` | 每次观测到新的 `next.activation` |
| `dedupe_key` | `current.activation`（UTC，秒精度） | `next.activation`（UTC，秒精度） |
| `notify_at` | 不设置，立即投递 | `next.activation − LEAD_SECONDS`（默认 300s），已过去则立即 |
| 可见性 | 全天 | 仅开轮前约 8 分钟 |

两个事件都属于 `warframe.cetus.` 命名空间，`subscribable = true`，schema_version 1。
`bounty_current` 扫描 tent 槽位与 `konzu.normal` 的 tier 5，`bounty_next` 只扫描 tent 槽位
（原因见 §2.1）；两个事件的可关注目录都是完整的 13 项。

事件 `data`：

```json
{
  "window": "current",
  "activation": "2026-09-17T03:48:51Z",
  "expiry": "2026-09-17T06:18:50Z",
  "match_keys": ["RescueBountyResc", "ReclamationBountyCap"],
  "jobs": [
    {
      "key": "RescueBountyResc",
      "name_zh": "搜索并救援",
      "source": "tentA",
      "tier": null
    }
  ]
}
```

`match_keys` 是扫描范围内出现过的任务键（去重、最多 32 个），即订阅过滤使用的维度；
`jobs[]` 保留来源与中文名，供展示和排错，不参与过滤。扫描范围之外的任务即使出现在接口返回
里，也不会进入 `match_keys`。

**Publisher 不判断「是否存在目标任务」。** 目标的定义因人而异，Publisher 只负责在每轮
产生时如实上报该轮的任务集合，是否命中完全由 EventServer 按每个订阅的关注项求交集决定。
这正是「Provider 只负责触发、EventServer 负责投递」的分工。

## 4. 订阅关注项

两个事件在目录中声明：

- `match_key_field = "match_keys"`
- `match_keys_required = true`
- `match_key_options` = 下表 13 项，两个事件使用同一份清单

| key | label |
| --- | --- |
| `AssassinateBountyAss` | 刺杀指挥官 |
| `AssassinateBountyCap` | 捕获新任 Grineer 指挥官 |
| `AttritionBountySab` | 破坏 Grineer 补给线 |
| `AttritionBountyLib` | 削弱 Grineer 据点 |
| `AttritionBountyCap` | 捕获他们的领袖 |
| `AttritionBountyExt` | 宰杀敌人 |
| `ReclamationBountyCap` | 捕获 Grineer 特工 |
| `ReclamationBountyTheft` | 取回被偷的器物 |
| `ReclamationBountyCache` | 找出遗失的器物 |
| `CaptureBountyCapOne` | 捕获 Grineer 指挥官 |
| `CaptureBountyCapTwo` | 间谍捕手 |
| `SabotageBountySab` | 破坏原型机 |
| `RescueBountyResc` | 搜索并救援 |

这份清单是受控的完整关注项目录，覆盖任何时候可能出现的任务；单个轮次只会出现其中一部分。
实测快照里有 3 项（`AttritionBountySab`、`AttritionBountyCap`、`ReclamationBountyTheft`）
没有出现，但仍必须列入目录，否则这些任务出现的轮次无法被关注。

用户侧交互：

```text
/events                                   列出两个事件
/events warframe.cetus.bounty_current     列出该事件全部可关注任务
/bind warframe.cetus.bounty_current RescueBountyResc,ReclamationBountyCap
/bindings                                 回显订阅及其关注项
```

不指定关注项时，`match_keys_required = true` 会让绑定被拒绝并提示可选值，避免用户误订成
「每轮都通知」。核心只对关注项做集合交集，不解释其含义。

## 5. 轮询与时间线

轮询间隔 `POLL_SECONDS` 默认 60 秒。以 T 表示下一轮 `activation`：

```text
T-8:00   接口开始返回 next
T-7:xx   Publisher 轮询发现 next，判定新 activation → 发布 bounty_next
         notify_at = T - LEAD_SECONDS（默认 5:00；若已过去则立即）
T-5:00   EventServer 到点，向关注命中的订阅者投递（LEAD_SECONDS=300 时）
T-0      next 变成 current，Publisher 发布 bounty_current，立即投递
```

Publisher 每轮只发布一次对应事件；同一 activation 内重复轮询由 EventServer 的
`(event_key, dedupe_key)` 唯一约束吸收，Publisher 无需保存本地状态，重启后重复发布不会
产生重复通知。

## 6. 边界与失败语义

- 首次启动会为当前窗口发布一次事件；若该 `dedupe_key` 已存在则被去重吸收。
- 用户在某轮中途才绑定，不会收到该轮的历史通知——delivery 只在发布时创建。
- Publisher 停机跨过整个 8 分钟窗口时，该轮的提前通知永久错过，用户仍会收到转为 current
  后的正常通知。
- 数据源超时、非 200、响应超过大小上限或 JSON 结构不符合预期时不发布，记录脱敏日志，
  下一轮继续。
- 提前量取配置项 `LEAD_SECONDS`（默认 300 秒），即
  `notify_at = max(now, next.activation − LEAD_SECONDS)`；与
  `DELIVERY_MAX_SCHEDULE_HORIZON_SECONDS`（默认 24 小时）共同保证 `notify_at` 落在合法范围。
- 两个事件互不去重：同一窗口同时订了两个事件的用户会收到两条消息（一条提前、一条开轮），
  这是拆成两个事件的预期行为。
- 日志按窗口而非按轮询记录：每个窗口最多一行 INFO（含扫描范围与 `match_keys` 数量），
  只有「当前轮次缺少 konzu」这类异常才额外记一条 WARNING，同样每窗口最多一次。

## 7. 部署

- 独立容器，镜像与 EventServer 无关，仅使用 Python 标准库。
- 网络：需要同时访问 wf-data 与 EventServer。实测 wf-data 只在 `db_net` 和 `my_web_net`，
  而 EventServer API 在 `db_net` 和 `hermes_net`。推荐接入 `my_web_net` + `hermes_net`；
  也可像 API 容器一样只接 `db_net`，或用宿主地址 `192.168.1.4:18080`（不推荐，耦合宿主）。
- 配置：`WF_DATA_URL`、`EVENTSERVER_URL`、`PUBLISHER_TOKEN`、`POLL_SECONDS`、
  `LEAD_SECONDS`（默认 300）、`REQUEST_TIMEOUT_SECONDS`、`MAX_RESPONSE_BYTES`、
  `DISPLAY_TIMEZONE`（默认 `Asia/Shanghai`）。提前量是部署级配置，不提供每用户或每订阅的
  提前量参数。
- 身份：`publisher_admin --publisher-key wf-data --allow-prefix warframe.cetus.`，Token 至少
  32 字符，只保存在部署机未跟踪的 `.env`。
- 外部请求必须带 User-Agent、超时、响应大小上限和有限重试。

实现位于 `publishers/wf-data/`，目录 JSON、Compose 示例和运维步骤见该目录的 README。

## 8. 测试矩阵（最低）

- 首次基线、同 activation 重复轮询、activation 变化各一次。
- `next` 出现与消失的边界；`next` 缺失时不发布第二个事件。
- `match_keys` 提取正确：当前轮次为 tent 三槽全部任务 + `konzu.normal` tier 5，下一轮仅为
  tent 三槽全部任务，两个列表都去重。
- 日志降噪：同一窗口重复轮询只产生一行 INFO，异常警告每个窗口只记一次。
- `notify_at` 计算：远期窗口延迟、已过期限立即、超上限拒绝。
- 订阅关注项：交集命中投递、无交集不投递、未指定关注项被拒绝、目录外取值被拒绝。
- 扫描范围：`konzu.normal` 只取 `tier == 5`，tier 1–4 出现在 `match_keys` 即判定为缺陷；
  `steelPath` 与 `narmer` 不得进入 `match_keys`。
- 数据源超时、非 200、超大响应、结构异常时不发布且不污染目录。
- 相同 activation 不重复投递（重启、网络重试两种路径）。
- 日志与事件 data 不出现 `imageUrl` 签名地址、Token 或完整 OpenID。

## 9. 已确定的取舍

| 取舍 | 结论 | 理由 |
| --- | --- | --- |
| 事件粒度 | 两个事件键，不做每任务一个事件键 | 用户要按任务自定义关注，事件键会组合爆炸 |
| 目标判定位置 | EventServer 按订阅关注项求交集 | Publisher 不知道用户关注什么，也不应接触用户数据 |
| 提前量 | 部署配置 `LEAD_SECONDS`（默认 300 秒），由 Publisher 声明 `notify_at`，核心不猜测 | 每用户提前偏好需要订阅参数，属于已否掉的方向 |
| 扫描范围 | 当前轮次：tent 三槽 + `konzu.normal` tier 5；下一轮：仅 tent 三槽 | wf-data 只暴露当前时段的 konzu，下一轮的 konzu 无从获取 |
| 关注项目录 | 固定 13 项，来自游戏任务全集而非单次快照 | 只按实测快照建目录会漏掉不常出现的任务 |
| 关注键 | 用 `jobId`，保留 `jobPath` 与来源在 data 中 | `jobId` 可读且稳定；`narmer` 暂不扫描，暂不涉及同键歧义 |
| 每轮是否发布 | 每轮都发布，命中与否由订阅决定 | Publisher 无法判断「目标任务」，用户定义才是准绳 |
