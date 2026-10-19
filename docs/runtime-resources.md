# 可复用资源与 Agnes 内置脚本

对应 ISS-008、ISS-012 的资源及 Agnes 适配部分。接口依据 `runtime-contract.md`。

## 来源调查：实际使用的是哪条路径

2026-10-19 只读检查原工作区配置、SQLite、DPAPI 记录结构及原有文档，未修改真实数据、刷新真实令牌或调用真实网站。调查输出只含计数、协议类型和字段名，不包含邮箱地址、密码、令牌、代理用户名或供应商地址。

- `config.production.toml` 指向独立的生产 `jobs.db` / `credentials.dpapi`，并要求代理。开发配置另指向空开发库，二者不是同一资源池。
- 生产库有 2,000 个用户；其对应邮箱记录的 `mailbox_transport` 全部为 `graph`。`bulk_prepare.source_rows/prepare` 从四段式清单读取邮箱、邮箱密码、OAuth client ID、refresh token，明确写入 `graph`。本地生产执行说明也记载 Graph、2,000 邮箱和固定会话。
- 真实运行链路是 `BulkRunner.execute_one → mailbox_ready → OutlookMailbox.baseline`，随后 `AgnesAdapter.execute(..., prepared_mailbox=...)`。因此沿用 **Microsoft Graph OAuth 收件箱/垃圾箱只读收码**，不能仅因 `OutlookMailbox` 支持 IMAP 就推断原生产使用 IMAP。
- 生产库中虽然存在 3 条 `proxies` 记录，`BulkRunner.run` 实际并不从 `ProxyManager` 领取它们。它读取独立代理 DPAPI 中的 `screenshot_proxy`，再使用现有 `HTTPS_PROXY` / `HTTP_PROXY` 本地 HTTP 上游，通过 `MeteredRelay` 建立“本地上游 CONNECT → 供应商网关 → 目标站点”的双层链路。
- Bulk 会给供应商用户名追加 `-session-<id>-time-30`，检查出口 IP，保持进行中任务的会话。新资源实现复用 `MeteredRelay` 和 `ProxyManager.credentials`，每个新任务分配独立会话，进行中不轮换或改为直连。
- 普通旧导入仍有 Graph、IMAP OAuth、IMAP 密码三种接入。新设置支持这些已有方式，不添加其他邮箱供应商。旧值 `imap` 兼容规范化为 `imap_oauth`。

生产专属计费预算、人工恢复、供应商余额和历史阻断规则仍属于 Bulk 管理流程；通用资源层不把这些记录改写成新运行策略。

## 设置 API schema

`ResourceManager(settings)` 使用当前 `Settings.database` 和 `Settings.vault`。保存：

```json
{
  "name": "Outlook 邮箱",
  "kind": "mailbox",
  "config": {
    "source": "outlook",
    "transport": "graph",
    "accounts": "alice@example.com----邮箱密码----client-id----refresh-token",
    "imap_host": "outlook.office365.com",
    "imap_port": 993
  }
}
```

- 更新时增加已有资源的 `id`；完整替换配置，创建新版本。不能改变 `kind`。
- `transport` 默认 `graph`，可选 `imap_oauth`、`imap_password`。密码方式允许每行 `邮箱----密码`；OAuth 方式需要 client ID 和 refresh token。
- `accounts` 可为多行文本，也可为对象数组，字段为 `email`、`mailbox_password`、`client_id`、`refresh_token`，可带 `mailbox_transport`、`imap_host`、`imap_port`。邮箱忽略大小写，单份资源拒绝重复邮箱。
- `config: {"source":"legacy"}` 显式从**当前配置数据库与 Vault**复制旧 users 对应邮箱。可增加 `config_path: "config.production.toml"`，从指定旧配置定位数据库和 Vault，**只读复制**邮箱及已提交排除记录到当前资源库；不修改源数据或源凭证。界面有相应路径输入，无需重新粘贴凭证。不会自动扫描外部生产库。

动态代理：

```json
{
  "name": "动态代理",
  "kind": "proxy",
  "config": {
    "source": "dynamic",
    "server": "http://gateway.example.com:8000",
    "username": "provider-account",
    "password": "provider-password",
    "upstream": "http://127.0.0.1:7890",
    "session_suffix_template": "-session-{session}-time-30",
    "check_url": "https://ipinfo.io/ip"
  }
}
```

- `server` 只接受 HTTP/HTTPS 无内嵌凭证的代理地址；用户名、密码成对填写。无认证的受控 HTTP 代理也可使用。
- `upstream` 可省略或为空，表示直接连接**指定代理网关**，不是目标站点直连。需要原 Bulk 双层链路时显式填入既有本地 HTTP 上游；不会动态读取环境变量偷偷改变绑定。双层链路只支持 HTTP 供应商网关。
- 用户名已有 `{session}` 时替换该占位符，否则追加 `session_suffix_template`。模板必须包含 `{session}`，默认 30 分钟供应商语法；本机按 29 分钟保守截止。
- `check_url` 必须返回 HTTP 200 和纯文本 IP，默认 `https://ipinfo.io/ip`。普通网站登录页不能当作 IP 检查地址。
- 旧 Bulk 代理显式导入：`source: "legacy_bulk"`，提供 `vault_path`、`secret_ref: "screenshot_proxy"` 和所需 `upstream`；可提供检查 URL 和会话模板。只读取源 DPAPI，复制网关凭证到当前 Vault。

### 返回与检查

保存、列表、检查返回 `id/name/kind/status/summary/checked_at/error_code`。不会返回原配置、邮箱清单、Vault 引用或凭证。

- 新保存状态是 `UNKNOWN`，不能当作健康。邮箱摘要包含 `total/healthy/unknown/unavailable/in_use/supply`；代理摘要为 `supply/via_upstream`。
- `check(id)` 是**同步**方法，Web 异步处理器应放入 `asyncio.to_thread`。邮箱显式检查每一条配置，包含真实 OAuth 刷新及收件箱只读访问；大清单检查时间与邮箱数相关。代理检查真实代理链路与出口 IP。
- 检查后为 `HEALTHY`、`UNHEALTHY` 或邮箱部分成功的 `DEGRADED`，并保存不含凭证的错误码，例如 `MAILBOX_TOKEN_INVALID`、`MAILBOX_OAUTH_CONFIG`、`PROXY_UNAVAILABLE`。
- `UNKNOWN` 可形成待运行快照，但领取时必须通过连接检查才返回租约。检查失败的邮箱不参与候选，检查失败的代理阻止新快照。不会用下一邮箱替换本次已领取失败的任务，也不会隐式重试。
- 摘要数量不是“对每个网站都可用”的数量；网站提交历史、占用和固定任务数在 `snapshot` 中一起校验。

## 绑定、领取与释放

1. 保存生成独立资源 revision 和新 Vault 引用。敏感配置和任务级邮箱凭证都在 DPAPI；SQLite 仅存引用及资源/租约元数据。
2. `snapshot(bindings, requirements, count, site_id)` 校验必需资源、网站及邮箱数量，返回可 JSON 持久化的引用快照，并在 `resource_snapshots` 保存规范副本。之后修改资源设置不影响此快照；篡改快照、替换资源版本或换网站会被拒绝。
3. `acquire` 通过 `BEGIN IMMEDIATE` 和邮箱活动租约唯一索引原子领取。同一邮箱即使存在于多个命名资源，也不能被并发重复领取；每个 task ID 只领取一次，快照总领取数不得超过固定数量。
4. 邮箱的 `secret_ref` 指向任务级 Vault 记录；脚本得到 `email/secret_ref/configure/baseline/find_code`。后两者为异步，底层继续使用原 OutlookMailbox。每个任务的网站密码、会话、API key 不写回共享邮箱凭证。只有更新后的 OAuth refresh token 在释放或恢复时返回原 revision。
5. 代理为 Playwright 字典，只存在于内存租约。每个租约有固定供应商 session；`await lease.validate_proxy()` 检查出口稳定和 TTL，不做重连换号、自动轮换或直连兜底。释放关闭该租约的中继及连接。
6. **新增必要接口：`ResourceManager.mark_submitted(lease)` 为同步方法。**框架 `ctx.mark_submitted()` 必须先调用它，再记录任务已提交，最后才发送网站注册请求。这样在任何一步崩溃，已消耗邮箱仍有 durable 标记。
7. `release(lease, submitted=..., succeeded=...)` 幂等释放活动占用；已提交或成功邮箱永久排除当前网站，失败/未知结果也不重新入池。提交前失败可供新任务使用。换网站可以复用，但必须先释放正在执行的租约。
8. `recover()` 只在取得全局 RunLock 后调用。释放遗留活动租约、保留已提交记录、归还已刷新令牌；不会重放旧任务。

旧数据排除依据同时覆盖旧 `registration_jobs.submitted_at`、成功状态、注册/建 Key 阶段、`bulk_requests` 注册/建 Key 记录及 users 对应 Vault 的激活/API key 证据。`agnes`、`agnes-api`、`agnes-ai` 统一映射到同一网站。旧 `submitted_at` 可能包含仅发送验证码的记录，此类也保守排除，避免升级误发起重复注册。旧表仅查询；反复导入排除项不会重复创建。

## Agnes 内置包

`runtime_agnes.AGNES_PACKAGE` 是可直接 JSON 序列化、导入的 `{manifest, source}`：

- id/site_id：`agnes`；版本：`1.0.0`；邮箱、代理均为必需资源。
- `async run(ctx)` 调用 `async run_agnes(ctx)`，复用 `AgnesAdapter` 和框架分配的 mailbox.secret_ref。脚本不创建或维护资源池。
- 声明结果为 `email`、`password`、`api_key`，三者都是敏感必需字段。
- 仅调用一次 `AgnesAdapter.execute`；适配器自己的 reconcile 是正常登录核查，不再次注册。`EMAIL_REQUESTED` 不等同于账号提交；`REGISTRATION_SUBMITTED` 和 `KEY_REQUESTED` 之前先校验固定代理，再调用 `ctx.mark_submitted()`。
- 失败统一抛 `ScriptFailure(code,message)`：框架按提交边界判为 FAILED/UNKNOWN，不能据旧 RETRY_WAIT 等状态自动重试。`KEY_PENDING` 不伪装成已完成；必须确认激活且取得 API key。
- Vault 保存任务执行/提交标记，直接再次调用同一任务也拒绝重复注册。密码、邮箱令牌、代理认证、结果 Key 注册到框架日志脱敏集合。所有返回、异常、取消路径都会关闭浏览器。

框架需提供 `ctx.settings` 的设置副本和 `ctx.lease`；后者用于提交前 `validate_proxy()`。原自定义流程资料仍由原 Settings 表达，不能宣称任意旧流程可自动转换成独立网站脚本。

## 本轮验证证据与边界

新增测试：`tests/test_runtime_resources.py`、`tests/test_runtime_agnes.py`。

本轮资源/适配专项结果：**30 passed**；四个新增 Python 文件 `ruff check` 通过。隔离工作树测试仅借用主工作区已实现的 `script_contract` 模块作契约集成，其余被测资源、适配和测试均来自本工作树；没有复制或编辑主工作区文件。

- 使用临时 SQLite 和真实 Windows DPAPI；测试保存/重启、凭证不进入公开响应和 SQLite、版本绑定、数量限制、同邮箱跨资源互斥、跨网站复用、提交前释放、崩溃恢复、旧库只读导入及故障不覆盖旧绑定。
- 真实本地 HTTP 代理检查认证及固定 session；真实本地上游 CONNECT + 原 `MeteredRelay` 验证 Bulk 双层链路，释放关闭中继；覆盖代理拒绝、出口变化和过期。
- **真实 Chromium 闭环**：框架领取 → 受控 Graph OAuth/邮箱响应 → 通过本地 HTTP 代理打开注册页 → 收码 → 标记提交 → 注册一次 → 身份确认 → API key 提取 → 释放。HTTP 注册端检查提交标记先于请求落库；再次调用不会再次注册。
- OAuth 刷新取消测试确保线程结束后才释放邮箱，避免后台刷新与下一任务重占并行。
- 真实外部 Agnes、微软邮箱、供应商代理本轮没有调用；真实服务的长期稳定性、额度和当前凭证有效性不属于受控测试结论。

整体运行存储、Web API、UI、批次及旧结果展示迁移由主 Agent 集成验收；资源与脚本测试不是整套产品验收的替代品。
