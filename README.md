# 注册机 · Agnes Web 工作台

管理 Agnes 开发者平台的用户清单、浏览器开户任务和 Excel 交付结果。任务状态保存在本地数据库，账号凭证保存在当前 Windows 用户的加密凭证库。

## 打开工具

- **方式一（最推荐）：双击根目录的 `启动Web界面.cmd`**（或运行 `uv run agnes --config config.local.toml web`），浏览器会自动打开可视化 Web 控制台 `http://127.0.0.1:8765`。在网页里可以直接批量粘贴导入账号、修改注册与拿结果流程、导入代理池并设置“每达成 X 次结果自动换 IP”。
- **方式二：双击根目录的 `启动工具.cmd`**，输入 `W` 打开 Web 界面，或按菜单编号 `1-11` 操作。

首次准备环境：需要 Windows、Python 3.12、uv 和 Chrome。在本目录打开 PowerShell：

```powershell
uv sync --python 3.12
if (-not (Test-Path config.local.toml)) { Copy-Item config.example.toml config.local.toml }
```

示例配置默认是本地模拟模式，不访问真实平台注册账号。若改用 Playwright 自带 Chromium，将配置中的 `browser_channel` 设置为 `"chromium"`，并执行 `uv run playwright install chromium`。

### Web 工作台

工作台包含任务大盘、账号导入与核验、九节点流程编排、代理池与交付备份五个视图，不需要安装 Node 或联网加载前端组件。

导入时先看分列预览，再选择“新账号注册”或“已有账号登录核验”。顶部选择一个批次后才能启动，汇总视图不会误运行全部账号。任务勾选会在定时刷新、搜索及翻页时保留；点击账号行打开右侧详情、审计时间线与本地密码编辑。

密码和结果默认隐藏，可单行显示或直接复制完整值。导出也默认隐藏凭证；需要完整交付文件时，在“交付导出与备份”中显式勾选包含明文。更改本地密码不会修改远端平台密码。运行中不允许更改流程、账号密码或恢复中断任务。

测试与验收见 [工作台总任务](docs/issues/ISS-000-modern-web-workbench-epic.md) 及其四个子任务。工作台没有远程登录认证，请保持默认 `127.0.0.1`，不要直接暴露到公网。

检查本地调度器：

```powershell
uv run agnes demo --count 1000
```

模拟任务使用 `output/demo/demo.db`，不访问 Agnes。查看 `output/demo/report.json` 中的实际并发、任务数和重复提交统计。

## 开始真实开户

公开仓库只包含示例配置，不包含真实账号、本地配置、代理认证、凭证库或生产交付文件。仅对你拥有明确授权的账号执行操作，并遵守目标平台规则。

1. 将 `config.example.toml` 复制为 `config.local.toml`，设置 `mode = "agnes"`，记录本次授权范围和运行限制。
2. 先确认邮箱域名可以在 [Agnes 开发者平台](https://platform.agnes-ai.com/login) 注册。
3. 按 [用户资料格式](docs/操作说明.md#导入用户)准备用户 CSV。密码和 OAuth 令牌通过加密导入或隐藏输入保存。
4. 为新用户创建一个批次，先执行一条任务，检查验证方式、登录身份和 API Key 页面。
5. 单账号完整核验后，再继续处理同一批次的其余任务。

```powershell
uv run agnes --config config.local.toml import-users data/users.csv
uv run agnes --config config.local.toml create-batch first-batch
uv run agnes --config config.local.toml run first-batch --limit 1
uv run agnes --config config.local.toml status first-batch
```

示例文件中的邮箱用于说明格式。真实开户时请替换为获准使用的真实邮箱。

## 导出 Excel 与本地归档

通过“交付导出与备份”页面导出，或使用命令行：

```powershell
# 单批次完整交付；省略 --include-secrets 则隐藏凭证
uv run agnes --config config.local.toml export outputs/开户结果.xlsx --batch first-batch --include-secrets
```

Excel 包含邮箱账号、邮箱密码、已确认账号的 Agnes 登录密码、API Key、状态和原因。已完成账号优先展示；混合批次的未完成记录另放一页。没有取得的 API Key 留空。CSV 导出使用 `.csv` 后缀。

含凭证的导出文件使用 `--include-secrets`；省略此选项时隐藏邮箱和凭证。

`data/`、`output/`、`outputs/`、本地/生产配置、数据库、DPAPI 文件和导出文件均由 `.gitignore` 排除。请不要用 `git add -f` 提交这些资料；加密凭证也不应上传公共仓库。示例账号仅为虚构测试数据。

Excel 导出沿用可选的 Codex 本机 Excel 适配器，需要额外的本机运行库；该运行库不随公开仓库分发，也不属于 Web 前端依赖。普通安装可以使用 CSV 导出，账号管理、流程编排和备份不依赖该适配器。

生产隔离迁移入口 `bulk prepare` 不会自动读取桌面档案，必须显式指定 `--source`、`--sample`、`--report`；如需识别旧库账号，另传 `--legacy`。真实生产档案说明和一次性救援脚本只保留在本机，不随仓库发布。

## 查看说明

- [导入、代理、暂停恢复及核验](docs/操作说明.md)
- [状态与持久化规则](docs/状态规则.md)

配置字段以 `src/agnes_provisioner/config.py` 中的 `Settings`、`Approval` 和 `KeyFlow` 为准。平台页面变化时，先用一个账号核对配置，再继续整个批次。
