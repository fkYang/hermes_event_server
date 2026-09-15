# AutoQQ EventServer

通用事件采集、判定、发布与投递服务。Warframe 是首批 provider；核心层不包含
Warframe、Hermes 或 QQ 领域逻辑。

## 当前实现范围

- 通用 `Observation`、`DomainEvent`、`DeliveryMessage` 和 provider 协议。
- MySQL 8 数据模型及 Alembic 迁移入口。
- 用户状态、`chat`/`command` 权限、角色、订阅、事件目录和 pairing code API。
- 幂等事件发布与 delivery outbox。
- 基于数据库租约的 `claim`、`ack`、`fail`、过期恢复和有限重试。
- Cetus 夜晚、Konzu 轮换、尸鬼活动的 WorldState adapter、触发与渲染逻辑。
- 基于 MySQL 租约的 Warframe 轮询 runner，同批次只请求一次 WorldState，各 provider 独立处理成败。

WorldState 映射已用脱敏结构样本和一次真实基线请求验证；默认测试仍只使用
fixture，不会请求外网或 MySQL。2026-09-15 已在隔离 MySQL 8.4 数据库和 Hermes Agent
`v0.21.2` 环境完成 Plugin `claim -> QQBot 私聊 -> ack` 真实联调。Webhook 网关、生产指标
告警和备份恢复演练仍属于后续阶段。完整部署顺序见仓库根目录
[README](../README.md)。

## 本地开发

要求 Python 3.12。以下命令只安装本项目依赖并运行离线测试：

```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
```

复制 `.env.example` 为不跟踪的 `.env`，填入本地 Secret。数据库密码、内部 Token 和真实
OpenID 不得提交。应用不会在启动时创建或修改表结构。

## 迁移与初始化

在测试数据库先执行升级、降级、再升级。不要直接以目标生产数据库作为首次验证环境。
准备脚本要求 `MYSQL_DATABASE` 是以 `_test` 结尾的隔离库，例如 `autoqq_test`。

```bash
uv run python scripts/prepare_test_database.py --probe
uv run python scripts/prepare_test_database.py --create
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
uv run python -m eventserver.bootstrap
```

`bootstrap` 注册内置事件和兼容别名，并把 `INITIAL_ADMIN_OPENIDS` 中的账号显式初始化为
`active + admin + chat=true + command=true`，同时注册已启用的 provider 实例。重复执行保持幂等。
`prepare_test_database.py` 只允许操作名称以 `_test` 结尾的数据库。

显式执行 MySQL 集成测试：

```bash
RUN_MYSQL_INTEGRATION=1 uv run pytest tests/integration/test_mysql_outbox.py
```

## 启动

```bash
uv run uvicorn eventserver.main:app --host 127.0.0.1 --port 8080 --no-access-log
uv run python -m eventserver.providers.warframe.runner
```

API 和 provider scheduler 是两个独立进程。本地或部署验证可用 `--once` 只执行一个
到期批次；长运行模式会响应 `SIGINT`/`SIGTERM` 并优雅停止。

生产部署应绑定容器或内网接口。`/health` 只表示进程存活，`/ready` 会检查数据库；其余
接口需要 `Authorization: Bearer ...`。`/metrics` 也需要服务 Token。关闭 Uvicorn 原生
access log 是为了避免 URL 中的完整 OpenID 落盘；应用只记录路由模板和脱敏结构化字段。
EventServer 不直接调用 Hermes/QQ，Plugin 通过
`/v1/deliveries/claim` 领取通知并以租约 Token 回写 `ack` 或 `fail`。

## 可靠性边界

投递为至少一次。若 Plugin 已发送但在 `ack` 前崩溃，租约到期后可能再次领取。平台若
支持幂等键，应使用稳定 `delivery_id`；否则需接受极低概率的重复通知。

新增 provider 见 [provider 开发说明](docs/provider-development.md)，内置事件见
[事件目录](docs/event-catalog.md)。
