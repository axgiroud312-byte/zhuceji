# 给外部 AI 的网站脚本编写说明

本产品是本机 Python 脚本运行台。网站逻辑、验证码匹配、注册提交、结果提取由脚本负责；框架负责邮箱与代理资源、固定任务数、互斥、事件、持久化和导出。

## 可直接使用的包格式

输出 UTF-8 `.json` 文件，结构与 [账号示例](../examples/script-demo-accounts.json)、[Token 示例](../examples/script-demo-tokens.json) 相同。不要生成节点图、选择器配置向导或安装脚本。

`manifest.api_version` 必须是 `1`；`id` 是脚本身份，`site_id` 是网站身份。同脚本升级保留这两个值并更改 `version`。`entrypoint` 对应源码中的 `async def run(ctx)`；可提供 `async def close(ctx)`，成功、失败、超时均尝试调用它。

第一版是单文件 Python 源码，支持标准库及当前环境已安装的模块（包括 httpx、playwright、pydantic）。`dependencies` 写顶层 Python 模块名，不是 pip 表达式。导入只解析声明、AST、入口签名和依赖，不执行顶层源码，不自动安装系统依赖。包被持久保存在 SQLite；相同版本不能覆盖，更新失败不影响旧版。

## 上下文

```python
from agnes_provisioner.script_contract import ScriptFailure

async def run(ctx):
    # index 从 1 开始；task_id / batch_id 可用于关联日志。
    ctx.log('准备请求', stage='prepare')
    # 参数来自 manifest.parameters 默认值与启动时输入的合并快照。
    # 若声明需要邮箱，框架会分配 ctx.mailbox。
    mailbox = ctx.mailbox
    if mailbox:
        mailbox.configure(sender_domain='example.com', code_pattern=r'\d{6}')
        baseline = await mailbox.baseline()
        email = mailbox.email
    # ctx.proxy 为 Playwright 支持的代理 dict；必需代理缺失不会降级直连。
    # 新生成的敏感值必须先注册脱敏，再用于日志/错误/网页请求。
    token = '示例中的虚构值'
    ctx.register_secret(token)
    if ctx.cancelled:
        raise ScriptFailure('STOPPED', '停止前未提交')
    # 在可能创建账号的请求之前，先持久化提交边界。
    ctx.mark_submitted()
    # 这里由脚本执行一次真实注册、等待验证并提取结果；不要自己维护任务池。
    return {'token': token}

async def close(ctx):
    # 关闭自己创建的 httpx client / browser / context 等资源。
    ctx.log('清理完成', stage='cleanup')
```

实际编写时返回值必须对应自己的 `result_fields`。支持 `string / number / integer / boolean`；必需字段缺失、类型不符、额外未声明字段都会失败。可选字段缺失就是缺失，框架不会编造值。敏感字段设置 `sensitive: true`，保存在 Windows DPAPI Vault；默认界面与 CSV 隐藏，用户显式显示或导出才解密。敏感邮箱、密码、Token、Key 都应声明敏感。

`ctx.log(message, stage='run', level='info', details='')` 产生结构化事件；可用级别 info/warning/error。错误使用 `ScriptFailure(code, message)`，message 应为用户能理解的原因，不包含响应正文、请求认证或凭证。未处理异常只显示错误类型，避免任意异常文本泄露凭证。注册新敏感值必须在写日志前调用 `ctx.register_secret`；框架无法推断第三方源码中尚未声明的任意秘密。

## 运行和失败边界

输入 N 创建 N 个任务，各调用入口一次。不得在脚本中把失败任务重新注册，也不得自行启动额外注册。只读收信轮询可以重复；产生账号的提交不可隐式重试。提交前异常为 FAILED；调用提交边界后异常为 UNKNOWN（结果待核查），不自动重新执行。

并发默认 1，最多 50。停止后不再领取待执行任务，已运行任务可完成；提交之前检查取消。单任务异步超时 600 秒，清理 15 秒。新任务使用新版本，已启动任务和历史使用原版本、字段和资源快照。

第一版在服务进程中执行受信任本机脚本，每任务独立 globals、参数和浏览器上下文；**不是安全沙箱**。只导入自己审阅/信任的源码。异步超时是协作式的，脚本不得用无限同步循环或阻塞 I/O 卡住事件循环；这类脚本需要手动结束服务进程，重启后中断记录保留且不重放。脚本不要修改数据库、Vault、全局设置或其他脚本状态。

## 本地验证

先导入两个示例。账号示例运行 20 个会故意在第 3、8、16 个失败，结果应为 17 成功、3 失败、总数始终 20；Token 示例输出另一组字段，两者都不访问外部网站。真实注册必须独立验证网站、邮箱、代理与结果，示例成功不能代表真实服务成功。
