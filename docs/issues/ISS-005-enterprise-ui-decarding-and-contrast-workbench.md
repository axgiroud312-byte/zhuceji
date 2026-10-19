# ISS-005：重构企业级高密度工作台界面（去卡片化、去说教文案、对比度分区与方案 A 布局）

## 目标与范围

### 当前问题
1. **过度卡片化（Card Spam）**：页面所有层级（顶部 5 个统计块、进度与日志块、表格容器、模式选择块、流程步骤块、提示横幅）全部使用带边框与圆角的独立 `.card` / `.choice-card`。满屏方框割裂了视线，导致没有真正的视觉中心。
2. **界面在“讲解自己”，像教程页而非专业工具**：
   - 大量 `.callout` 蓝色教学横幅（如“💡 实时分列预览向导：把账号粘贴到下方……”）。
   - 标题充斥“第一步：……”“第二步：……”“阶段一：……”等向导式说教。
   - 每个选项卡片下都跟着两行口语化解释说明，且标题直接暴露内部配置字段名（如 `registration_flow`、`sender_domain`、`rotate_every = X`）与过多装饰性 Emoji。
3. **信息主次颠倒，缺乏视觉锚点与对比度分区**：
   - 首页最核心的“任务数据表”被 5 张大统计卡和一块常驻日志卡片挤到屏幕下半部。
   - 背景、侧边栏、卡片、输入框之间缺乏清晰的表面明暗层级（Surface Contrast），顶部操作栏堆满红、绿、蓝、黄实心按钮，所有元素都在抢注意力。
4. **控件形态复古（NPC 感）**：二选一/三选一模式切换使用肥胖的大号卡片（`.choice-card`），状态筛选使用圆胖胶囊，缺乏现代企业软件（Linear / Vercel / Datadog 风格）克制、紧凑、高密度的工业工具感。

### 期望行为
采用已确认的 **方案 A（全幅数据台 + 底部折叠终端）** 与**表面对比度分区（Surface Contrast Zoning）**重构 `src/agnes_provisioner/web_ui.py`：
1. **三级对比度分区与清晰视觉锚点（方案 A 布局）**：
   - **背景暗部区（Canvas / Recessed Zone）**：左侧紧凑导航栏（`180px`～`200px`）、顶部单行指令栏、底部可折叠深色运行终端。采用低对比度退后视觉，不抢主视野。
   - **顶部紧凑指标带（Telemetry Strip）**：取消 5 张独立统计大卡片，合并为紧贴指令栏下方的一条高密度横向数据带（`总计` · `已拿结果` · `运行中` · `待核验` · `代理池`），底部内嵌 `2px`～`3px` 极细多段进度流。
   - **第一视觉锚点（Primary Workspace Surface）**：任务表格（`#tab-dashboard`）与各功能主面板采用抬升的纯平面板（Elevated Surface）铺满工作区，区域内部仅用 `1px` 极细分割线（Hairline Divider）划分，彻底取消卡片套卡片。
   - **底部可折叠实时终端（Bottom Docked Console）**：将运行槽位与实时日志（`#runnerLogsBox`）沉入工作台底部深色终端栏，支持一键折叠/展开、自动滚动与清空，把首屏 80% 以上面积还给任务表格。
2. **“不讲解自己”的界面语言**：
   - 删除所有 `.callout` 教程提示框、删除“第一步 / 第二步 / 阶段一”等教学前缀、删除冗余的 `.card-desc` 解释段落。
   - 清除界面标题与标签中的代码变量名（如 `(`registration_flow`)`、`(`sender_domain`)`）及多余装饰性 Emoji，统一为简练专业的产品术语（如 `目标地址`、`发件域名`、`轮换阈值`）。
3. **现代高密度组件替换（去 NPC 化）**：
   - **Segmented Control（分段切换器）**：将所有肥胖的 `.choice-card`（导入模式二选一、验证码模式三选一、登录核验标准三选一、换 IP 策略三选一）统一替换为紧凑的横向分段控制器或单行平铺切换条。
   - **按钮主次收敛**：每个视图同一区域最多保留 1 个高对比度主按钮（Primary Action，如 `开始执行`、`导入账号`、`保存配置`），其余次要动作统一收敛为低噪幽灵/描边按钮（Ghost / Secondary），危险操作仅在悬停或文字色上体现。
   - **紧凑流水线列表**：将流程编排的 9 个节点从松散大卡片改为紧凑的连续步骤列表行（Accordion List），展开时内嵌网格表单，与整体无卡片风格保持一致。

### 本次包含与排除的内容
- **包含**：
  - `src/agnes_provisioner/web_ui.py` 全局 CSS 设计令牌（Dark / Light 双主题表面对比度色板）、HTML 布局结构、文案精简与控件形态升级。
  - `tests/test_workbench_acceptance.py` 与相关前端验收测试同步验证（保持既有 DOM ID 与功能钩子兼容，若有按钮文案精简则同步更新或通过 `aria-label` 保持无障碍定位）。
- **排除**：
  - 不修改后端数据库 Schema、DPAPI 加密存储、调度算法及 Web API 路由契约。

---

## 必要设计与依据

### 1. 视觉层级与对比度令牌规范
- **Dark 主题表面对比度**：
  - `--bg-canvas: #090a0f`（侧边栏、顶部栏、底部背景，向后退）
  - `--bg-surface: #11131a`（主工作台面、主数据表，向前浮现成为视觉锚点）
  - `--bg-elevated: #171a24`（输入框、分段控制器选中滑块、抽屉浮层）
  - `--bg-terminal: #06070b`（底部内凹日志终端）
  - `--border-subtle: rgba(255, 255, 255, 0.07)`（区域之间的 `1px` 分割线，替代卡片边框）
- **Light 主题表面对比度**：
  - `--bg-canvas: #f3f4f6`（侧边栏与背景灰底层）
  - `--bg-surface: #ffffff`（主工作台纯白面）
  - `--bg-elevated: #f8fafc`（控件背景）
  - `--border-subtle: #e5e7eb`（极细分割线）

### 2. 各视图去卡片化与控件重构细则
- **全局导航与指令栏**：
  - 左侧导航去除多彩 Emoji 与花哨胶囊，仅用清晰文字 + 右侧等宽数字角标（`#navBadgeTotal`、`#navBadgeProxies`）。
  - 顶部指令栏：左侧为状态指示点（`#runnerStatusPill`）+ 批次选择器（`#batchSelect`）+ 数量限制（`#runLimitInput`）+ 主操作按钮；右侧为代理状态指示（`#topIpCapsuleText`）与导出入口。
- **任务队列主视图（`#tab-dashboard`，方案 A）**：
  - 上方为单行紧凑状态筛选 Tab（`#stateFilterPills`）+ 明文开关 + 搜索框（`#jobSearchInput`）。
  - 中间全幅展示高密度任务表格（`#jobsTableBody`），表头固定，行高紧凑，密码与 API Key 单元格采用内联等宽可复制标签。
  - 底部停靠可折叠运行终端（包含 `#runnerSlots`、`#logAutoScroll`、清空按钮与 `#runnerLogsBox`）。
- **账号导入与验证页（`#tab-import`）**：
  - 移除顶部蓝色教学横幅与“第一步/第二步”卡片。
  - 顶部栏右侧直接使用 **Segmented Control** 切换 `新账号注册`（`#modeCardRegister`）与 `已有账号验号`（`#modeCardExisting`）。
  - 参数行（格式、分隔符、密码用途、批次名、收码协议、文件选择）单行/双行紧凑网格排布，紧接拖拽粘贴合一输入区（`#importDropZone` + `#importAccountsText`）与下方实时解析表（`#importPreviewBody`）。
  - 验证设置作为同一连续面板的下半区，用 Segmented Control 切换验证码模式（`#vCardAuto`、`#vCardManual`、`#vCardNone`）。
- **流程编排页（`#tab-flows`）**：
  - 移除顶部教学横幅；顶部工具条展示目标网址与运行参数，右侧放置恢复默认与保存按钮。
  - 三大阶段合并为连续的 9 步紧凑手风琴列表（保留 `.pipeline`、`.pipe-step`、`.pipe-head` 结构钩子，但去除卡片间距与厚重外框，改为上下相连的 `1px` 分割列表）。
- **代理池页（`#tab-proxies`）**：
  - 顶部用一条紧凑的当前激活节点与换 IP 进度横条替代紫色大卡片。
  - 中部采用左右分栏（左栏：分段切换器选择换 IP 策略 `#pModeResult` / `#pModeExec` / `#pModeBoth` 及阈值；右栏：粘贴导入与实时预览表），底部直接平铺代理节点矩阵表（`#proxiesTableBody`）。

### 3. 自动化测试与 DOM 契约兼容要求
- 必须保留现有 JS 逻辑与测试依赖的核心 DOM `id`、`data-*` 属性与 class（如 `#batchSelect`、`#floatingBulkBar`、`#jobDrawer`、`.pipe-head`、`[data-target=...]`、`#importPreviewSummary`、`#proxiesTableBody` 等）。
- 页面 `<title>` 保留 `Agnes 注册机可视化控制台`，侧边栏保留 `Agnes 工作台` 字样，或同步更新对应断言。
- 对精简了 Emoji 或冗长文案的按钮，使用 `aria-label` 或同步更新 `tests/test_workbench_acceptance.py` 中的 `get_by_role("button", name=...)`，确保 `uv run pytest` 全量通过。

---

## 验收方法

1. **视觉与布局验收（Playwright 截图核验）**：
   - 在 `1440px`、`768px`、`360px` 视口下启动真实 Chrome，并生成 `dashboard`、`import`、`flows`、`proxies`、`delivery` 五个视图的深浅双主题截图。
   - 检查确认：无 `.callout` 教程框、无“第一步/第二步”标题、无满屏嵌套卡片；任务主表占据首屏核心位置，5 项统计已收敛为顶部紧凑指标带，实时日志位于底部可折叠终端；所有二选一/三选一模式均已呈现为紧凑分段控制器（Segmented Control）。
   - 检查任意视口下 `document.documentElement.scrollWidth <= innerWidth`，无横向溢出。
2. **交互与功能回归验收**：
   - 运行 `uv run pytest` 与 `uv run ruff check`，确保全部 189+ 项单元测试与 Playwright 端到端验收测试 100% 通过。

---

## 关联与依赖

- **所属总目标**：[`ISS-000`：构建现代化 Web 可视化注册与流程编排工作台](./ISS-000-modern-web-workbench-epic.md)
- **更新既有任务视觉规范**：收敛并升级 [`ISS-001`](./ISS-001-app-shell-and-live-dashboard.md)、[`ISS-002`](./ISS-002-visual-flow-builder.md)、[`ISS-003`](./ISS-003-account-import-wizard-and-verification.md)、[`ISS-004`](./ISS-004-proxy-pool-and-auto-ip-rotation.md) 的前端呈现层。

---

## 当前进展

- **已完成开发、整合与自动化验收（2026-10-19）**，按方案 A 交付至 `feat/modern-web-workbench`，整体关联 [PR #1](https://github.com/axgiroud312-byte/zhuceji/pull/1)，保持待评审、不自动合并；最终产品视觉由用户评审。
- **布局**：196px 侧栏、单行指令栏、36px 五指标带与 2px 多段进度线；抬升的全幅任务表为主面，深浅主题分别使用独立表面对比度令牌。1440×1000 实测表格滚动区为 809.5px，占队列工作区 **91.37%**、视口高度 **80.95%**。表头固定、长表仅在表格内部横向滚动。
- **终端**：槽位与日志统一停靠底部，默认折叠为 34px；展开状态在切换视图、轮询和刷新后保留。自动跟随、暂停滚动、清空视图均回归；清空不会删除后端日志或审计时间线。批量操作栏随终端高度避让。
- **组件与文案**：删除教程横幅、卡片描述、教学前缀及标题/标签中的底层字段名；清除装饰性 Emoji，旧按钮无障碍名称保持兼容。导入模式、验证码、两处同步登录核验标准、代理策略统一为五组原生按钮分段控制器，支持鼠标、Tab、空格、Enter、方向键与 Home/End。流程直接维护一个连续的九节点手风琴列表，保留节点插入、定位助手、动作排序/禁用及正则预览。
- **兼容与边界**：原有静态 DOM id **152/152 保留**，既有选择器与 `data-*` 操作钩子继续可用；登录标准兼容旧 select 并双向同步。未改动数据库 Schema、DPAPI、调度器或 Web API 契约，未读取真实账号、生产库或外部邮箱/代理。
- **验证**：`uv run pytest` **236 passed**；`uv run ruff check` **All checks passed**；`git diff --check` 通过。`tests/test_workbench_acceptance.py` 共 **58 项**，其中 ISS-005 新增 **47 项**，包含五视图 × 三视口 × 双主题的 30 组布局，另有填充预览/展开节点、分段键盘操作、登录标准持久化与终端回归。浏览器为 **Chrome 155.0.8059.80**，各视图均满足 `scrollWidth <= innerWidth`，同时检查面板边界与内部滚动，避免只隐藏页面溢出。
- **截图证据**：保留于 `%LOCALAPPDATA%\Temp\opencode\`，30 张主矩阵截图命名 `agnes-workbench-{dashboard,import,flows,proxies,delivery}-{1440,768,360}-{dark,light}.png`；另有 18 张 `agnes-workbench-{import,proxies,flows}-expanded-{宽度}-{主题}.png` 和 3 张 `agnes-workbench-terminal-{宽度}-dark.png`。同名 JSON 保存 Chrome 版本、视口及实际尺寸；截图遮蔽本机配置路径，数据全部虚构。
- **复验**：PowerShell 设置 `$env:AGNES_UI_SCREENSHOT='1'` 后运行 `uv run pytest tests/test_workbench_acceptance.py`，即在上述目录更新截图与尺寸证据；日常启动仍为双击 `启动Web界面.cmd` 或 `uv run agnes --config config.local.toml web`。
- **收尾**：测试 HTTP 服务、Chrome 上下文/进程与 CLI 子进程均由 fixture 关闭；没有新建临时工作树或常驻服务。保留主工作区、原有本地配置/数据库/凭证及验收截图，不上传真实资料。无已知开发阻碍；既有 Excel 本机可选运行库限制与真实网站可用性边界不变。
