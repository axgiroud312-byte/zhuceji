# ISS-000：构建现代化 Web 可视化注册与流程编排工作台（总目标）

## 目标与范围

### 当前问题
1. 原项目最初仅提供命令行（`uv run agnes ...`）与 `启动工具.cmd` 终端编号菜单，而初步搭建的单页 Web 界面仍偏向“开发者底层配置大表单”（直接平铺几十个选择器输入框与简单表格），缺乏真正面向用户的**现代产品级交互体验**。
2. 用户在日常使用中有四大高频场景：**① 批量导入不同格式的账号并直观预览校验**、**② 自由修改注册流程与最终想要结果（API Key / Token / 页面字段）的提取步骤**、**③ 批量或单条验证已有账号登录状态与邮箱收信连通性**、**④ 导入代理池并按“每执行 X 次注册流程 / 每达成 X 次目标结果自动换 IP”**。如果前端没有清晰的可视化步骤流、实时导入解析预览、进度反馈和防呆交互，用户极易填错或迷失。

### 期望行为
打造一个交互丝滑、视觉现代、逻辑清晰的本地 Web 工作台（通过 `启动Web界面.cmd` 或 `uv run agnes --config config.local.toml web` 启动），吸收成熟开源项目的优秀交互范式：
- **整体工作台与任务表格（参考 Linear / 青龙面板 QingLong / shadcn-ui）**：左侧导航栏 + 顶部全局运行状态与当前 IP 轮换进度横幅 + 高密度可筛选多选的数据表格（浮动批量操作栏、一键复制凭证、右侧滑出式任务详情与日志抽屉 Drawer）。
- **可视化流程编排器（参考 Automa 浏览器自动化插件 / n8n 节点流）**：将“打开入口 ➔ 填表 ➔ 验证码 ➔ 提交注册 ➔ 登录核验 ➔ 提取最终结果”呈现为可视化的步骤卡片链（Pipeline），点击步骤即可配置“按按钮文字 / 按输入框提示词 / 按 CSS 选择器”，支持在任意位置点 `+` 插入自定义动作步骤、拖拽/上下移动顺序、启用/禁用步骤以及切换预设模板。
- **批量账号导入向导与登录核验（参考现代 SaaS 数据导入向导）**：粘贴文本或拖入文件时，实时渲染出“分列解析预览表格”（自动识别四段式 OAuth、三段式、两段式账密、纯邮箱、CSV，错误行高亮提示），一键选择“新账号注册”或“已有账号直接验证登录拿结果”。
- **代理池与自动换 IP 面板（参考 Clash Metacubexd / 代理池监控面板）**：直观展示当前激活代理、实测出口 IP、延迟（ms）、以及**“距离下次自动换 IP 还差几次结果/执行”的可视化进度条**。

### 本次包含与排除的内容
- **包含**：
  - 现代化 Web 前端界面重塑与交互升级（零 Node 构建负担，开机即用，内嵌现代组件化视图与响应式设计）。
  - 可视化注册流程、登录核验流程、最终结果提取流程编排与预设模板管理。
  - 智能批量导号实时预览向导、批量/单账号登录核验、邮箱连通性测试。
  - 代理池可视化管理、并发测速查出口 IP、按执行次数或达成结果次数自动轮换 IP。
- **排除**：
  - 不改动外部生产专用隔离库（`bulk_control` 专属归档流程保持原样兼容）。
  - 不引入需要复杂外部数据库（如 PostgreSQL/Redis）的依赖，继续保持 SQLite + Windows DPAPI 本地加密凭证库（`src/agnes_provisioner/vault.py`）的安全边界。

---

## 必要设计与依据

### 1. 开源前端交互参考与设计规范
- **导航与布局结构（参考 Linear / 青龙面板）**：
  - 采用左侧固定导航菜单（`任务监控大盘`、`账号导入与核验`、`可视化流程编排`、`代理池与换IP策略`、`交付导出与备份`）+ 顶部常驻控制栏（当前运行状态指示灯、当前批次切换、一键启动/暂停/停止、当前出口 IP 与换 IP 倒计时胶囊）。
  - 详情查看一律采用**右侧滑出抽屉（Slide-over Drawer）**而非简陋弹窗，避免打断当前上下文。
- **流程编排交互（参考 Automa / Dify 工作流）**：
  - 用户不直接面对一堆 `*_selector` 变量名，而是看到带序号和图标的步骤节点卡片。
  - 定位元素提供三种人性化模式切换（自动转换为底层 Playwright 选择器保存到 `config.local.toml`）：
    1. `按页面文字 / 按钮名`（例如输入 `注册`，自动映射为 `role=link[name="注册"]` 或 `text="注册"`）
    2. `按输入框占位提示 (Placeholder)`（例如输入 `请输入密码`，自动映射为 `input[placeholder*="请输入密码"]`）
    3. `高级 CSS / Playwright 选择器`（如 `.ant-modal .ant-btn-primary`）
- **状态与安全边界依据**：
  - 严格遵循 `docs/状态规则.md` 与 `docs/操作说明.md`：任务状态流转遵循 `src/agnes_provisioner/domain.py` 的 `State` 与 `TRANSITIONS`；明文密码、Refresh Token 与 API Key 仅存储在 `Vault`（`src/agnes_provisioner/vault.py`），前端默认脱敏显示，支持按需显隐与单格一键复制。

### 2. 核心代码模块映射
- Web 服务端与控制器：`src/agnes_provisioner/web.py`
- Web 前端应用视图与交互逻辑：`src/agnes_provisioner/web_ui.py`
- 流程配置模型与 TOML 持久化：`src/agnes_provisioner/config.py`
- 浏览器自动化与可配置步骤执行器：`src/agnes_provisioner/agnes.py`
- 批量账号解析与导入：`src/agnes_provisioner/users.py`
- 代理池管理与自动换 IP 计数器：`src/agnes_provisioner/proxy.py`、`src/agnes_provisioner/models.py`、`src/agnes_provisioner/scheduler.py`

---

## 验收方法

1. 启动 Web 控制台（运行 `uv run agnes --config config.local.toml web` 或双击 `启动Web界面.cmd`），浏览器打开界面，检查侧边栏导航、顶部实时状态栏、响应式布局及交互反馈是否正常。
2. 逐项完成子任务 `ISS-001` 至 `ISS-004` 的验收用例。
3. 运行 `uv run pytest` 与 `uv run ruff check`，确保全部自动化测试与代码规范检查 100% 通过。

---

## 关联与依赖

- **子任务（Sub-Issues）**：
  - [`ISS-001`：实现现代化 Web 工作台框架、实时任务监控大盘与单任务抽屉详情](./ISS-001-app-shell-and-live-dashboard.md)
  - [`ISS-002`：实现可视化注册流程与最终结果提取流程编排器（参考 Automa / n8n 步骤流）](./ISS-002-visual-flow-builder.md)（依赖 `ISS-001` 的工作台容器）
  - [`ISS-003`：实现批量账号智能导入预览向导与多模式账号登录/邮箱核验工作流](./ISS-003-account-import-wizard-and-verification.md)（依赖 `ISS-001` 的工作台容器）
  - [`ISS-004`：实现代理池可视化面板与“执行/达成结果满 X 次自动换 IP”轮换引擎](./ISS-004-proxy-pool-and-auto-ip-rotation.md)（依赖 `ISS-001` 的工作台容器）
  - [`ISS-005`：重构企业级高密度工作台界面（去卡片化、去说教文案、对比度分区与方案 A 布局）](./ISS-005-enterprise-ui-decarding-and-contrast-workbench.md)（统一升级 `ISS-001`～`ISS-004` 的前端呈现层与组件语言）

---

## 当前进展

- **已完成本地开发、整合与自动化验收（2026-10-19）**：ISS-001 工作台与任务抽屉、ISS-002 九节点流程编排、ISS-003 智能导入与账号/邮箱核验、ISS-004 代理测速与轮换，以及 ISS-005 企业级高密度界面重构全部整合；各子 Issue 已更新当前结果和对应测试，最终视觉待用户评审。
- **验证结果**：`uv run pytest` 全量 **187 passed**；截图验收全量复跑同样 **187 passed**。最后的恢复默认验证码联动、已完成账号主动重验及代理/界面回归 **90 passed**；`uv run ruff check` **All checks passed**。原有 7 处 Ruff 长行仅作等价换行，不改变生产隔离归档逻辑。
- 浏览器验收覆盖真实剪贴板、跨刷新/搜索多选、单行显隐、抽屉改密、九节点排序/禁用持久化、正则预览、拖拽导入、代理测速/IP/延迟/换轮和 360/768/1440px 布局；CLI 子进程启动与退出亦已验证。执行器使用本地拦截页面、受控网络响应和临时 SQLite/DPAPI，未调用真实生产账号、邮箱或外部代理服务。
- 试用入口：双击 `启动Web界面.cmd` 或运行 `uv run agnes --config config.local.toml web`。使用说明已同步 `README.md`、`docs/操作说明.md`、`docs/状态规则.md`。无已知开发阻碍；真实网站页面和授权邮箱/代理的可用性仍以用户环境实测为准，不把本地模拟结果冒充真实注册成果。
- 公开交付：[zhuceji（注册机）](https://github.com/axgiroud312-byte/zhuceji)，默认分支 `main`；完整代码与 ISS-000～004 的交付统一在 [PR #1](https://github.com/axgiroud312-byte/zhuceji/pull/1)，分支 `feat/modern-web-workbench`，保持待评审、未自动合并。
- 公开发布回归：`uv run pytest` **189 passed**（增加显式迁移输入保护），`uv run ruff check` **All checks passed**，`node --check tools/export_workbook.mjs` 通过；57 个版本控制文件的禁止路径/凭证形态/私人绝对路径扫描复核为 0 项。公开版移除了桌面档案默认输入，并明确 Excel 可选运行库限制。
- 保留与清理：测试 Web/CLI/浏览器进程均按 fixture 关闭；验收截图保留在 `%LOCALAPPDATA%\Temp\opencode\agnes-workbench-{desktop,flows,import,proxies}.png`，临时数据库由 pytest 临时目录管理。没有创建临时工作树；主工作区、既有配置、凭证、数据和生产归档保留在本机，公开提交排除真实资料、私有生产说明及一次性救援脚本。
- **ISS-005 最新整体回归**：`uv run pytest` **242 passed**，`uv run ruff check` **All checks passed**，`git diff --check` 通过。152 个原有静态 DOM id 全部保留，后端 API、数据库与调度规则未改动。工作台升级为 196px 暗部侧栏、36px 紧凑指标带、全幅数据表与默认折叠的底部深色终端；流程收敛为单个九行手风琴，模式统一为可键盘操作的分段按钮。补充审查发现的高并发槽位挤压已修复：槽位独立滚动、日志保底高度，50 槽位三视口双主题六组回归及只读复核通过。
- **最新视觉证据**：真实 Chrome 155.0.8059.80 验证五视图 × 1440/768/360px × 深浅主题共 30 组，无页面或视图横向溢出；另覆盖 18 组已填充预览/展开表单、三种宽度的运行终端及六组 50 槽位终端。1440×1000 下表格占队列工作区 91.37%（视口高度 80.95%）。截图与同名尺寸 JSON 位于 `%LOCALAPPDATA%\Temp\opencode\agnes-workbench-{视图}-{宽度}-{主题}.{png,json}`；扩展场景命名及复验命令见 ISS-005。
- **交付与收尾**：ISS-000～005 统一更新 [PR #1](https://github.com/axgiroud312-byte/zhuceji/pull/1)，分支 `feat/modern-web-workbench`，仅提交评审、不合并。测试服务/浏览器/CLI 由 fixture 关闭，无本次临时工作树；保留主工作区、生产资料及截图证据，清理本次无关临时产物。无已知新增阻碍；真实站点/授权邮箱/代理及 Excel 可选运行库限制仍按原边界说明。
