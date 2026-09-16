# AutoQQ EventServer

AutoQQ EventServer 是面向 Hermes/QQBot 的通用事件发布与投递服务。它统一管理用户权限、事件
订阅、provider 状态和待发送消息；Hermes Plugin 通过内部 HTTP API 查询权限并领取通知。

Warframe 是当前内置的首批 provider，但 EventServer 的权限、订阅和投递能力不依赖具体事件
领域，后续事件通过独立 provider 接入。

## 服务能力

- 管理用户状态、`chat`/`command` 权限和管理员角色。
- 提供事件目录、订阅、取消订阅和 pairing code。
- 轮询 provider，规范化观察结果并按确定性规则发布事件。
- 通过 MySQL 唯一约束保证事件和 delivery 幂等。
- 通过数据库租约提供 `claim`、`ack`、`fail`、过期恢复和有限重试。
- API 与 scheduler 故障隔离；单个 provider 失败不会阻塞权限和 delivery API。
- 提供 `/health`、`/ready`、受保护的 `/metrics` 和结构化日志。
- 支持本地一次性首管理员引导，不需要预先知道完整 QQ OpenID。

EventServer 不直接调用 Hermes 或腾讯 QQ API，也不保存 QQ AppID、QQ Secret 或 LLM Key。

```text
外部事件源 -> EventServer scheduler -> MySQL 事件与 delivery
                                          |
Hermes Plugin <- claim/ack/fail -----------+
      |
      +-> Hermes QQBot 主动私聊用户
```

## 部署拓扑

推荐部署两个 EventServer 容器：

| 服务 | 作用 | 网络 |
| --- | --- | --- |
| `autoqq-eventserver-api` | 权限、订阅、事件目录和 delivery API | MySQL 网络 + Hermes 网络 |
| `autoqq-eventserver-scheduler` | provider 轮询、基线、事件发布 | MySQL 网络 |

两者使用同一个镜像和同一个 `autoqq` MySQL 数据库。API 不需要发布宿主机端口，Hermes
Plugin 通过共享 Docker 网络访问 `http://autoqq-eventserver-api:8080`。

MySQL 容器必须加入 MySQL 外部网络；Hermes Gateway 必须加入 Hermes 外部网络。仅创建网络但
没有把对应服务接入网络，仍然无法通过上述容器 DNS 名称通信。

MVP 不需要 Redis。权限、订阅、事件、delivery 和租约始终以 MySQL 为事实来源。

## 部署前提

- Docker Engine 与 Docker Compose v2。
- MySQL 8，字符集 `utf8mb4`，数据库时间统一使用 UTC。
- 已存在一个连接 MySQL 的外部 Docker 网络。
- 已存在一个连接 Hermes Gateway 的外部 Docker 网络。
- 已拉取包含当前功能的 EventServer 镜像，例如 `fkyang/autoqq-eventserver:latest`。
- 一个至少 32 个随机字符的 `INTERNAL_API_TOKEN`，并与 Plugin 保持一致。

生产环境建议将镜像固定到发布 tag 或 digest，不长期依赖 `latest`。

## 使用 Docker Compose 部署

以下流程面向全新正式部署，直接使用 `autoqq` 数据库；不会创建或使用 `_test` 后缀数据库。

### 1. 创建数据库与专用账号

以下 SQL 是模板，应由数据库管理员确认账号来源范围和密码策略后执行：

```sql
CREATE DATABASE autoqq
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER 'autoqq'@'%' IDENTIFIED BY '<从Secret注入的随机密码>';
GRANT ALL PRIVILEGES ON autoqq.* TO 'autoqq'@'%';
```

当前版本迁移和运行使用同一账号，因此该账号需要对 `autoqq.*` 执行迁移和读写，但不应拥有
其他数据库权限。不要让 EventServer 长期使用 MySQL `root`。

### 2. 准备部署目录

```bash
mkdir -p autoqq-eventserver
cd autoqq-eventserver
```

创建 `.env`：

```dotenv
COMPOSE_PROJECT_NAME=autoqq
EVENTSERVER_IMAGE=fkyang/autoqq-eventserver:latest
MYSQL_DOCKER_NETWORK=infra_mysql_backend
HERMES_DOCKER_NETWORK=my_web_net

MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=autoqq
MYSQL_USER=autoqq
MYSQL_PASSWORD=<数据库密码>
MYSQL_CHARSET=utf8mb4

INTERNAL_API_TOKEN=<至少32个随机字符并与Plugin一致>
INITIAL_ADMIN_OPENIDS=

DEFAULT_TIMEZONE=Asia/Shanghai
ENABLED_PROVIDERS=warframe.cetus_night,warframe.konzu_rotation,warframe.ghoul_event
DELIVERY_MAX_ATTEMPTS=5
DELIVERY_DEFAULT_LEASE_SECONDS=60
PROVIDER_DEFAULT_TIMEOUT_SECONDS=10
PROVIDER_SCHEDULER_TICK_SECONDS=5
```

生成内部 Token：

```bash
openssl rand -hex 32
chmod 600 .env
```

如果通过宿主机地址访问 MySQL，可把 `MYSQL_HOST`、`MYSQL_PORT` 改为实际地址和映射端口；
如果共用 Docker 网络，应使用 MySQL service/alias 和容器端口 `3306`。

创建 `compose.yml`：

```yaml
name: ${COMPOSE_PROJECT_NAME:-autoqq}

x-eventserver-common: &eventserver-common
  image: ${EVENTSERVER_IMAGE:?Set EVENTSERVER_IMAGE in .env}
  env_file:
    - ./.env
  environment:
    MYSQL_PASSWORD: ${MYSQL_PASSWORD:?Set MYSQL_PASSWORD in .env}
    INTERNAL_API_TOKEN: ${INTERNAL_API_TOKEN:?Set INTERNAL_API_TOKEN in .env}
  init: true
  restart: unless-stopped
  security_opt:
    - no-new-privileges:true
  cap_drop:
    - ALL
  stop_grace_period: 30s

services:
  autoqq-eventserver-api:
    <<: *eventserver-common
    command:
      - uvicorn
      - eventserver.main:app
      - --host
      - 0.0.0.0
      - --port
      - "8080"
      - --no-access-log
    networks:
      - mysql_backend
      - hermes_net
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import urllib.request;
          urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=2).read()
      interval: 10s
      timeout: 3s
      retries: 6
      start_period: 10s

  autoqq-eventserver-scheduler:
    <<: *eventserver-common
    command:
      - python
      - -m
      - eventserver.providers.warframe.runner
    depends_on:
      autoqq-eventserver-api:
        condition: service_healthy
    networks:
      - mysql_backend

networks:
  mysql_backend:
    external: true
    name: ${MYSQL_DOCKER_NETWORK:-infra_mysql_backend}
  hermes_net:
    external: true
    name: ${HERMES_DOCKER_NETWORK:-my_web_net}
```

确认镜像和网络存在：

```bash
docker pull fkyang/autoqq-eventserver:latest
docker image inspect fkyang/autoqq-eventserver:latest
docker network inspect infra_mysql_backend
docker network inspect my_web_net
docker compose --env-file .env -f compose.yml config --quiet
```

不要输出完整 `docker compose config` 到日志，因为展开结果可能包含 Secret。

### 3. 迁移和初始化

应用启动不会自动修改数据库结构。首次启动前显式执行：

```bash
docker compose --env-file .env -f compose.yml run --rm \
  autoqq-eventserver-api alembic upgrade head

docker compose --env-file .env -f compose.yml run --rm \
  autoqq-eventserver-api python -m eventserver.bootstrap
```

第二条命令会幂等注册事件目录、别名和启用的 provider。正式 `autoqq` 库不要运行
`scripts/prepare_test_database.py`、`alembic downgrade base` 或带
`RUN_MYSQL_INTEGRATION=1` 的测试套件。

### 4. 启动服务

```bash
docker compose --env-file .env -f compose.yml up -d
docker compose --env-file .env -f compose.yml ps
```

期望 API 为 `healthy`，scheduler 为 `running`。

## 初始化首管理员

### 已知 OpenID

通过可信渠道取得管理员稳定 QQ OpenID 后，在首次 bootstrap 前配置：

```dotenv
INITIAL_ADMIN_OPENIDS=<稳定QQ OpenID>
```

bootstrap 会将该账号初始化为：

```text
active + admin + chat=true + command=true
```

成功后清空 `INITIAL_ADMIN_OPENIDS`，并重新创建容器，避免 OpenID 长期留在容器环境配置中。

### 不知道 OpenID

1. 保持 `INITIAL_ADMIN_OPENIDS=`。
2. 完成 EventServer 和 Hermes Plugin 启动。
3. 预定管理员向机器人发送消息并取得 pairing code。
4. 在 EventServer 部署主机交互执行：

```bash
docker compose --env-file .env -f compose.yml run --rm \
  autoqq-eventserver-api python -m eventserver.bootstrap_admin
```

命令隐藏读取 pairing code，不接受明文 code 参数。它仅在不存在
`active + admin + command=true` 用户时生效，并在单个事务中消费配对码、授予权限、设置角色
和写入脱敏审计。显式封禁用户不会被该命令解封。

## 连接 Hermes Plugin

Plugin 至少配置：

```dotenv
EVENT_SERVER_URL=http://autoqq-eventserver-api:8080
INTERNAL_API_TOKEN=<与EventServer完全相同>
DELIVERY_WORKER_ID=hermes-main
DELIVERY_POLL_ENABLED=true
```

Hermes Gateway 必须加入 Compose 中 `HERMES_DOCKER_NETWORK` 指向的同一外部网络。Plugin 不应
获得任何 MySQL 配置。

## 使用服务

### 内部 API

除 `/health` 和 `/ready` 外，内部 API 与 `/metrics` 都要求：

```http
Authorization: Bearer <INTERNAL_API_TOKEN>
```

主要能力：

| API 组 | 用途 |
| --- | --- |
| `/v1/events` | 查询可用事件目录 |
| `/v1/users/...` | 查询权限、授权、撤权和角色管理 |
| `/v1/users/.../subscriptions` | 查询、添加和取消订阅 |
| `/v1/pairing-codes` | 创建并由管理员批准一次性授权码 |
| `/v1/deliveries/claim` | Plugin 领取待发送通知 |
| `/v1/deliveries/{id}/ack` | Plugin 确认发送成功 |
| `/v1/deliveries/{id}/fail` | Plugin 回写发送失败 |

普通用户不直接调用这些 API，而是通过 Plugin 的 `/events`、`/bind`、`/grant` 等命令操作。

### 内置事件

| event_key | 说明 |
| --- | --- |
| `warframe.cetus.night` | 希图斯进入夜晚 |
| `warframe.konzu.rotation` | Konzu 赏金轮换 |
| `warframe.ghoul.started` | 尸鬼活动开始 |

provider 首次成功观察默认只建立基线，不会把当前状态当成新事件补发。只有后续确定性状态变化
才发布事件并创建 delivery。

### 接入新事件

1. 定义稳定的 `<domain>.<resource>.<event>` 事件键和 payload schema 版本。
2. 按 provider 契约接入数据源、规范化、触发判断和消息渲染。
3. 覆盖首次基线、无变化、状态变化、重复输入、超时和无效响应测试。
4. 将 provider 注册到发布镜像，并加入 `ENABLED_PROVIDERS`。
5. 重新执行幂等 bootstrap 和 Compose 重建。
6. 先观察基线、去重和故障隔离，再向用户开放订阅。

接入规则与验收要求参见 [Provider 开发说明](docs/provider-development.md) 和
[内置事件目录](docs/event-catalog.md)。新增 provider 不应修改权限、订阅、outbox 或 Plugin。

## 健康检查与运维

API 不发布宿主机端口时，可在容器内检查：

```bash
docker compose --env-file .env -f compose.yml exec -T \
  autoqq-eventserver-api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).read().decode())"

docker compose --env-file .env -f compose.yml exec -T \
  autoqq-eventserver-api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=2).read().decode())"
```

- `/health` 返回 `alive`：进程存活。
- `/ready` 返回 `ready`：数据库连接可用。

查看日志：

```bash
docker compose --env-file .env -f compose.yml logs --since 10m \
  autoqq-eventserver-api autoqq-eventserver-scheduler
```

重点监控 provider 最近成功时间、待投递积压、租约过期、retry/dead、API 5xx 和数据库连接。
日志不得包含数据库密码、内部 Token、完整 OpenID、pairing code 或租约 Token。

## 更新与回退

更新流程：

1. 备份 `autoqq` 数据库并验证备份可读。
2. 拉取新镜像并把 `EVENTSERVER_IMAGE` 固定到新 tag 或 digest。
3. 停止 scheduler，避免升级期间发布新事件。
4. 使用新镜像执行 `alembic upgrade head`。
5. 执行幂等 bootstrap。
6. `docker compose up -d --force-recreate`。
7. 验证 `/ready`、scheduler、Plugin claim 和日志。

回退前必须确认旧镜像可以读取当前 schema。不能只回退容器而忽略数据库迁移；不可逆迁移需要
单独审批和恢复方案。

## 投递与安全边界

- delivery 为至少一次投递；发送成功但 `ack` 前崩溃可能造成重复通知。
- Plugin 不在本地无限重试；重试次数、时间和 `dead` 状态由 EventServer 决定。
- 并发 Plugin 不能领取同一有效租约，`ack`/`fail` 必须匹配当前租约 Token。
- EventServer 内部 API 不应直接暴露公网。
- 外部 Webhook 接入需要独立网关、签名、时间戳校验和防重放策略。
- 普通用户不能配置任意 URL、脚本、SQL、模板表达式或 provider 代码。

## 常见问题

| 现象 | 检查项 |
| --- | --- |
| API healthy 但功能不可用 | `/health` 只表示进程存活，应检查 `/ready`、MySQL 网络和迁移版本 |
| scheduler 没有立即发布事件 | 首次观察只建立基线；等待后续确定性状态变化 |
| Plugin 返回 401/403 | 确认两端 `INTERNAL_API_TOKEN` 完全一致且没有空格或换行 |
| Plugin 一直 claim 不到消息 | 检查用户 `command` 权限、订阅、delivery 状态和 worker 配置 |
| delivery 持续 retry/dead | 查看脱敏错误码、Hermes QQBot 状态和消息长度限制 |
| Compose 找不到网络 | 先创建或修正 `MYSQL_DOCKER_NETWORK`、`HERMES_DOCKER_NETWORK` |
| 首管理员命令拒绝执行 | 系统可能已有有效管理员，或 pairing code 已过期、已消费、目标被封禁 |

## 参考文档

- [详细操作、权限和投递契约](操作指南.md)
- [Provider 开发说明](docs/provider-development.md)
- [内置事件目录](docs/event-catalog.md)
- [AutoQQ Hermes Plugin](https://github.com/fkYang/hermes_qqbot_plugin)
