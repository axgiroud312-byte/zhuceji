# Script Runtime v1 · 共享实施契约

ISS-006 是当前产品依据。旧数据库表只读兼容，新表使用 `rt_` / `resource_` 前缀；同一数据库的 RunLock 与旧 CLI 共用。第一版运行受信任的本机 Python 脚本，不是代码沙箱，不自动安装依赖。

## 脚本包

UTF-8 JSON：`{"manifest": {...}, "source": "Python source"}`。manifest 包含 `api_version: 1`、`id`、`site_id`、`name`、`version`、`entrypoint: "run"`、`resources: {"mailbox": false, "proxy": false}`、`parameters: {}`（运行参数默认值）、`result_fields: [{"key": "token", "label": "Token", "type": "string", "required": true, "sensitive": true}]`、`dependencies: []`。字段支持 string/number/integer/boolean；缺失的非必需字段保留为空，未声明字段拒绝。

入口 `async def run(ctx) -> dict`，返回声明的结果；失败抛出 `ScriptFailure(code, message)`。可选 `async def close(ctx)` 在 finally 执行。导入只做 AST/结构/依赖验证，不执行源码；相同 id/version 不可覆盖，启动固定版本、资源快照及字段声明。

ctx 提供 `task_id, batch_id, index`（1 起）、`parameters`、`mailbox`、`proxy`（Playwright dict 或 None）、`log(message, stage="run", level="info", details="")`（同步）、`mark_submitted()`（同步，注册请求之前调用）、`cancelled`（只读）、`register_secret(value)`（同步，加入日志脱敏）、`settings`（内置 Agnes 兼容用）。框架调用一次入口，无隐式重试；提交后异常为 UNKNOWN，提交前异常为 FAILED。停止取消待执行任务，进行中任务完成或超时；进程崩溃任务不自动重放。

## 资源实现边界

`runtime_resources.py` 提供 `ResourceManager(settings)`；使用原 Settings.database/vault。

- `list() -> list[dict]`：id/name/kind/status/summary（公开摘要，不含凭证）。
- `save(payload) -> dict`：命名资源；payload `{id?, name, kind: "mailbox"|"proxy", config: {...}}`。返回公开摘要。
- `check(resource_id) -> dict`：显式检查、保存状态。
- `snapshot(bindings: dict, requirements: dict, count: int, site_id: str) -> dict`：验证数量/资源，返回仅内部使用且可 JSON 持久化的不可变引用快照。敏感配置只保存 Vault 引用。
- `async acquire(snapshot, site_id, task_id) -> ResourceLease`：原子领取邮箱/代理，失败明确报错，不降级直连。
- `async release(lease, *, submitted: bool, succeeded: bool) -> None`。
- `recover() -> None`：仅持有全局 RunLock 后调用，释放崩溃租约，保留已提交邮箱占用。
- lease 属性 `mailbox, proxy`。mailbox 至少提供 `email, secret_ref, baseline(), find_code(baseline)`，后两者异步；匹配通过 `configure(sender_domain=..., code_pattern=...)`。内置 Agnes 可使用 secret_ref + 原 Vault/OutlookMailbox，脚本不维护资源池。

资源保存和检查通过服务端 RunLock 串行，避免设置修改改变运行绑定。同网站提交过的邮箱不能重分配；跨网站可复用，进行中邮箱不能重占。来源调查记录到资源说明，不写真实凭证。

## Web API / 前端契约

所有端点 `/api/runtime/`；成功 JSON 对象，失败 `{error: "可读原因"}` + 4xx。

- GET `overview` → `{scripts: [manifest], resources: [...], batches: [{id,site_id,script_id,version,state,count,created_at}], active: batch|null}`。
- GET `tasks?batch=...&state=...&search=...&offset=0&limit=50&reveal=0` → `{tasks: [{id,index,state,stage,message,results:{},...}], total, fields:[...], summary:{total,succeeded,failed,running,pending,unknown,cancelled}, batch:{...}}`。
- GET `events?batch=...&task=...&after=0&limit=100` → `{events:[{id,at,task_id,stage,level,message,details}], cursor}`。
- POST `scripts/import` body JSON 包 → `{script: manifest}`。
- POST `resources/save` body 如上 → `{resource: summary}`。
- POST `resources/check` `{id}` → `{resource: summary}`。
- POST `start` `{script_id,version,count,concurrency:1,bindings:{mailbox:resource_id,proxy:resource_id},parameters:{},request_id:uuid}` → `{batch: batch}`；重复 request_id 返回同批次，不创建重复任务。
- POST `stop` `{batch}` → `{ok:true}`。
- GET `export?batch=...&include_secrets=0` → CSV 下载（默认隐藏敏感字段）。

前端只依赖以上接口，旧路由保留兼容但不展示旧流程编排。主页/脚本库/资源设置三视图，结果表主工作区，历史批次及任务日志可查询；声明字段动态渲染。

## 文件所有权

主 Agent：`script_runtime.py`、`script_contract.py`、`runtime_store.py`、`web.py`、运行测试、集成文档。
资源/Agnes Agent：`runtime_resources.py`、`runtime_agnes.py`、对应新测试、资源调查文档；不修改共享旧模块。
UI Agent：`web_ui.py`、新的浏览器验收工具；不修改 web.py 或后端。
