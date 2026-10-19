# 网站脚本运行台

导入外部 AI 编写的网站注册脚本，选择已保存的邮箱/动态代理资源，填写任务数量，运行并查看结果。脚本决定注册逻辑和结果字段；框架负责资源、调度、状态、日志、保存与导出。

## 打开工具

双击 **`启动Web界面.cmd`**，或运行：

```powershell
uv sync --python 3.12
if (-not (Test-Path config.local.toml)) { Copy-Item config.example.toml config.local.toml }
uv run agnes --config config.local.toml web
```

入口：**http://127.0.0.1:8765**。需要 Windows、Python 3.12、uv、Chrome；使用 Playwright Chromium 时设置 `browser_channel = "chromium"` 并运行 `uv run playwright install chromium`。前端不依赖 Node 或远程 CDN。

## 使用

在 **资源设置** 保存命名邮箱与代理。此前 Agnes 实际路径是 Outlook Graph 收信，以及通过本地 HTTP 上游连接动态代理网关；支持相同连接方式，凭证加密保存，连接未检查不会显示为健康。配置可以长期复用；旧 users 和原代理 Vault 提供显式导入入口，外部生产隔离档案不自动扫描或改写。

在 **脚本库** 导入 JSON 脚本包；同一脚本新版本更新不覆盖历史版本。内置 Agnes 也是网站脚本，框架没有固定 API Key 结果列。可先导入 `examples/script-demo-accounts.json` 或 `examples/script-demo-tokens.json` 试用，无外部请求。

回到 **运行台** 选择脚本、邮箱、代理、数量后启动。**填 20 就创建 20 个任务**，失败保存原因，不补数量、不隐式重新注册。账号示例故意失败 3 条，用来检查 17 成功 / 3 失败。服务端保证同一时间一个运行批次，重复点击不会生成重复任务。停止后待执行任务取消，进行中任务完成或超时；提交后结果不明时标为“待核查”。

结果列按脚本声明显示。选择任务查看它的结构化日志，技术详情按需展开；历史批次和结果重启后可读取。默认隐藏敏感字段，显式显示/导出才解密。CSV 可直接下载；旧命令行 Excel 导出依赖可选本机 Excel 适配器，非普通安装必备能力。

脚本是受信任的本机 Python 程序，不是沙箱；只导入已审阅的包，不自动安装依赖。编写接口见 [外部 AI 脚本说明](docs/script-authoring.md)。

## 旧数据与凭证

升级首次打开运行台时，将当前配置数据库里的旧任务复制成只读历史，不重新排队；原账号、批次、代理、凭证引用和旧流程配置保留。迁移前在数据库旁的 `runtime-backups/` 保存 SQLite 与 DPAPI 恢复副本，迁移可重复执行。旧自定义流程不自动转换成通用脚本；请保留原配置，按新接口重新编写。

凭证仍由当前 Windows 用户 DPAPI 保护。迁移恢复需要同时保留数据库、Vault 和原配置，不能只复制 SQLite。公开仓库不包含真实账号、本地配置、代理认证、数据库、截图中的凭证或交付文件。

## 验证与说明

```powershell
uv run pytest
uv run ruff check
git diff --check
```

当前产品依据：[ISS-006](docs/issues/ISS-006-script-runtime-workbench-epic.md) 及 ISS-007～012。旧 ISS-000～005 是历史记录；流程编排、录制和选择器编辑已退出当前产品。

- [操作说明](docs/操作说明.md)
- [脚本编写接口](docs/script-authoring.md)
- [状态与持久化](docs/状态规则.md)
- [本轮验收证据](docs/runtime-acceptance.md)

工作台是本机工具，没有远程账号系统，请保持默认 `127.0.0.1`。旧 CLI 和生产隔离工具保留兼容用途，其旧重试/流程配置不代表新脚本运行台语义。
