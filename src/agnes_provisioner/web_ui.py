# ruff: noqa: E501
from __future__ import annotations

WEB_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Agnes 注册机可视化控制台 — 流程编排 · 智能导号 · 代理池轮换</title>
<style>
  :root[data-theme="dark"] {
    --bg: #090d16;
    --bg-sidebar: #0f172a;
    --bg-card: #151f32;
    --bg-card-hover: #1e293b;
    --bg-input: #0b1120;
    --border: #26334d;
    --border-focus: #3b82f6;
    --text: #f8fafc;
    --text-secondary: #cbd5e1;
    --text-muted: #8b9bb4;
    --primary: #3b82f6;
    --primary-hover: #2563eb;
    --primary-soft: rgba(59, 130, 246, 0.14);
    --success: #10b981;
    --success-soft: rgba(16, 185, 129, 0.15);
    --warning: #f59e0b;
    --warning-soft: rgba(245, 158, 11, 0.15);
    --danger: #ef4444;
    --danger-soft: rgba(239, 68, 68, 0.15);
    --purple: #8b5cf6;
    --purple-soft: rgba(139, 92, 246, 0.15);
    --shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
  }
  :root[data-theme="light"] {
    --bg: #f1f5f9;
    --bg-sidebar: #ffffff;
    --bg-card: #ffffff;
    --bg-card-hover: #f8fafc;
    --bg-input: #f8fafc;
    --border: #e2e8f0;
    --border-focus: #2563eb;
    --text: #0f172a;
    --text-secondary: #334155;
    --text-muted: #64748b;
    --primary: #2563eb;
    --primary-hover: #1d4ed8;
    --primary-soft: rgba(37, 99, 235, 0.1);
    --success: #059669;
    --success-soft: rgba(5, 150, 105, 0.12);
    --warning: #d97706;
    --warning-soft: rgba(217, 119, 6, 0.12);
    --danger: #dc2626;
    --danger-soft: rgba(220, 38, 38, 0.12);
    --purple: #7c3aed;
    --purple-soft: rgba(124, 58, 237, 0.12);
    --shadow: 0 10px 25px rgba(15, 23, 42, 0.08);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    display: flex;
    min-height: 100vh;
  }

  /* Sidebar */
  .sidebar {
    width: 230px;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 100;
    padding: 18px 14px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 8px 18px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 14px;
  }
  .brand-logo {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    color: #fff;
    font-weight: 800;
    font-size: 19px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .brand-title {
    font-size: 15.5px;
    font-weight: 800;
    line-height: 1.25;
  }
  .brand-sub {
    font-size: 11.5px;
    color: var(--text-muted);
  }
  .nav-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
  }
  .nav-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 11px 13px;
    border-radius: 10px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-secondary);
    font-size: 12.5px;
    font-weight: 600;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s;
  }
  .nav-item:hover {
    background: var(--bg-card-hover);
    color: var(--text);
  }
  .nav-item.active {
    background: var(--primary-soft);
    color: var(--primary);
    border-color: rgba(59, 130, 246, 0.3);
  }
  .nav-badge {
    font-size: 11.5px;
    padding: 2px 7px;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.16);
    color: var(--text-secondary);
    font-family: Consolas, monospace;
    flex-shrink: 0;
    white-space: nowrap;
  }
  .sidebar-footer {
    padding-top: 14px;
    border-top: 1px solid var(--border);
    font-size: 11.5px;
    color: var(--text-muted);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  /* Main Area */
  .main-shell {
    margin-left: 230px;
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding-bottom: 90px;
  }

  /* Sticky Topbar */
  .topbar {
    position: sticky;
    top: 0;
    z-index: 90;
    background: var(--bg-sidebar);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .topbar-left, .topbar-right {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 13px;
    border-radius: 999px;
    font-size: 12.5px;
    font-weight: 700;
    background: var(--success-soft);
    color: var(--success);
    border: 1px solid rgba(16, 185, 129, 0.3);
  }
  .status-pill.idle {
    background: rgba(148, 163, 184, 0.12);
    color: var(--text-muted);
    border-color: var(--border);
  }
  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
  }
  .status-pill.running .status-dot {
    animation: pulse 1.1s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.35; transform: scale(1.3); }
  }
  .ip-capsule {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 12.5px;
    font-weight: 600;
    background: var(--purple-soft);
    color: var(--purple);
    border: 1px solid rgba(139, 92, 246, 0.28);
    cursor: pointer;
  }

  .content-area {
    padding: 20px 24px;
    max-width: 1400px;
    width: 100%;
    margin: 0 auto;
  }

  /* Summary Cards */
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
    margin-bottom: 18px;
  }
  .stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 15px 18px;
  }
  .stat-label {
    font-size: 12.5px;
    color: var(--text-muted);
    margin-bottom: 4px;
  }
  .stat-val {
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.5px;
  }
  .stat-sub {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 4px;
  }

  /* Multi-segment Progress Bar */
  .progress-track {
    height: 10px;
    background: var(--bg-input);
    border-radius: 999px;
    overflow: hidden;
    display: flex;
    border: 1px solid var(--border);
    margin: 10px 0 6px;
  }
  .progress-seg {
    height: 100%;
    transition: width 0.3s ease;
  }

  /* Panels & Cards */
  .tab-panel { display: none; }
  .tab-panel.active { display: block; }
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 18px;
  }
  .card-title {
    margin: 0 0 6px;
    font-size: 16.5px;
    font-weight: 700;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .card-desc {
    margin: 0 0 16px;
    font-size: 13px;
    color: var(--text-muted);
  }
  .grid-2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
    gap: 16px;
  }
  .grid-3 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: 14px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin-bottom: 12px;
  }
  .field label {
    font-size: 12.5px;
    font-weight: 600;
    color: var(--text-secondary);
  }
  .field small {
    font-size: 11.5px;
    color: var(--text-muted);
  }
  input[type="text"],
  input[type="number"],
  input[type="password"],
  select,
  textarea {
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 11px;
    color: var(--text);
    font-size: 13.5px;
    font-family: inherit;
    outline: none;
  }
  textarea {
    font-family: "JetBrains Mono", Consolas, monospace;
    font-size: 12.5px;
    resize: vertical;
  }
  input:focus, select:focus, textarea:focus {
    border-color: var(--border-focus);
  }
  .checkbox-row {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 13.5px;
    cursor: pointer;
    user-select: none;
  }

  /* Choice Cards (Radio Cards) */
  .choice-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 12px;
    margin-bottom: 14px;
  }
  .choice-card {
    background: var(--bg-input);
    border: 2px solid var(--border);
    border-radius: 10px;
    padding: 13px 15px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .choice-card:hover {
    border-color: var(--text-muted);
  }
  .choice-card.selected {
    border-color: var(--primary);
    background: var(--primary-soft);
  }
  .choice-card h4 {
    margin: 0 0 4px;
    font-size: 14px;
    font-weight: 700;
  }
  .choice-card p {
    margin: 0;
    font-size: 12px;
    color: var(--text-muted);
  }

  /* Pipeline Step Cards (Automa / n8n style) */
  .pipeline {
    display: flex;
    flex-direction: column;
    gap: 12px;
    position: relative;
  }
  .pipe-step {
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    transition: border-color 0.15s;
  }
  .pipe-step:hover {
    border-color: var(--primary);
  }
  .pipe-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
  }
  .pipe-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 6px;
    background: var(--primary);
    color: #fff;
    font-size: 12px;
    font-weight: 800;
    margin-right: 8px;
  }
  .pipe-title {
    font-weight: 700;
    font-size: 14px;
  }
  .pipe-summary {
    font-family: Consolas, monospace;
    font-size: 12px;
    color: var(--primary);
    background: var(--primary-soft);
    padding: 2px 8px;
    border-radius: 6px;
  }

  /* Buttons */
  .btn-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .btn {
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid transparent;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary { background: var(--primary); color: #fff; }
  .btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
  .btn-success { background: var(--success); color: #fff; }
  .btn-warning { background: var(--warning); color: #090d16; }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-secondary {
    background: var(--bg-card-hover);
    border-color: var(--border);
    color: var(--text);
  }
  .btn-secondary:hover:not(:disabled) { border-color: var(--text-muted); }
  .btn-sm { padding: 4px 9px; font-size: 12px; border-radius: 6px; }

  /* Filter Pills */
  .filter-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .filter-pill {
    padding: 5px 11px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg-input);
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  .filter-pill.active {
    background: var(--primary);
    border-color: var(--primary);
    color: #fff;
  }

  /* Tables */
  .table-wrap {
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: 10px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th, td {
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }
  th {
    background: var(--bg-input);
    color: var(--text-muted);
    font-weight: 600;
    white-space: nowrap;
  }
  tr:hover td {
    background: rgba(59, 130, 246, 0.03);
  }
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11.5px;
    font-weight: 600;
    white-space: nowrap;
  }
  .badge-success { background: var(--success-soft); color: var(--success); }
  .badge-pending { background: var(--primary-soft); color: var(--primary); }
  .badge-warn { background: var(--warning-soft); color: var(--warning); }
  .badge-danger { background: var(--danger-soft); color: var(--danger); }
  .badge-muted { background: rgba(148, 163, 184, 0.16); color: var(--text-secondary); }

  .mono { font-family: "JetBrains Mono", Consolas, monospace; font-size: 12.5px; }
  .copy-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 7px;
    border-radius: 5px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    cursor: pointer;
    font-size: 11.5px;
    color: var(--text-secondary);
  }
  .copy-chip:hover { border-color: var(--primary); color: var(--primary); }

  /* Floating Bulk Action Bar */
  .floating-bulk-bar {
    position: fixed;
    bottom: 20px;
    left: calc(50% + 115px);
    transform: translateX(-50%);
    background: var(--bg-sidebar);
    border: 1px solid var(--primary);
    border-radius: 12px;
    padding: 10px 18px;
    box-shadow: var(--shadow);
    z-index: 500;
    display: none;
    align-items: center;
    gap: 12px;
    width: min(1100px, calc(100% - 270px));
    flex-wrap: wrap;
  }
  .floating-bulk-bar > span { white-space: nowrap; flex-shrink: 0; }

  /* Right Slide-over Drawer */
  .drawer-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.55);
    z-index: 800;
    display: none;
  }
  .drawer {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 460px;
    max-width: 92vw;
    background: var(--bg-sidebar);
    border-left: 1px solid var(--border);
    box-shadow: var(--shadow);
    z-index: 810;
    padding: 20px;
    overflow-y: auto;
    transform: translateX(100%);
    transition: transform 0.22s ease;
  }
  .drawer.open {
    transform: translateX(0);
  }
  .timeline-item {
    position: relative;
    padding-left: 18px;
    padding-bottom: 14px;
    border-left: 2px solid var(--border);
  }
  .timeline-item::before {
    content: "";
    position: absolute;
    left: -5px;
    top: 4px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--primary);
  }

  .step-box {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px;
    margin-bottom: 8px;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    align-items: center;
  }
  @media (max-width: 980px) {
    .sidebar { position: static; width: 100%; height: auto; border-right: none; border-bottom: 1px solid var(--border); }
    body { flex-direction: column; }
    .main-shell { margin-left: 0; }
    .floating-bulk-bar { left: 50%; width: calc(100% - 24px); }
    .step-box { grid-template-columns: 1fr; }
  }
  .log-box {
    background: #060911;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 11px;
    font-family: Consolas, monospace;
    font-size: 12px;
    max-height: 170px;
    overflow-y: auto;
    color: #93c5fd;
    white-space: pre-wrap;
  }
  .callout {
    background: var(--primary-soft);
    border-left: 4px solid var(--primary);
    padding: 11px 15px;
    border-radius: 6px;
    font-size: 13px;
    margin-bottom: 16px;
  }
  .toast {
    position: fixed;
    top: 20px;
    right: 24px;
    padding: 11px 18px;
    border-radius: 10px;
    background: var(--bg-sidebar);
    border: 1px solid var(--primary);
    color: var(--text);
    font-size: 13.5px;
    font-weight: 600;
    box-shadow: var(--shadow);
    z-index: 9999;
    display: none;
  }
  input, select, textarea { min-width: 0; max-width: 100%; }
  button:focus-visible, [tabindex]:focus-visible { outline: 2px solid var(--primary); outline-offset: 3px; }
  .pipe-head { cursor: pointer; }
  .pipe-step.collapsed > :not(.pipe-head) { display: none; }
  .pipe-step.collapsed .pipe-head { margin-bottom: 0; }
  .pipe-step + .insert-zone { margin: 0 0 10px 14px; padding-left: 16px; border-left: 2px solid var(--primary); }
  .smart-selector-control { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
  .smart-selector-control input { flex: 1; }
  .log-error { color: var(--danger); } .log-warn { color: var(--warning); }
  .log-success { color: var(--success); }
  .drop-zone { padding: 16px; background: var(--primary-soft); border-radius: 10px; margin-bottom: 12px; }
  .drop-zone.dragging { outline: 2px dashed var(--primary); }
  .secret-cell { max-width: 210px; word-break: break-all; }
  .selected-row { background: var(--primary-soft); }
  .step-box.disabled-step { opacity: .55; }
  .step-box input[type=text], .step-box select { width: 100%; }
  .running-badge { color: var(--primary); font-size: 11px; }
  @media (max-width: 650px) {
    .grid-2, .grid-3, .choice-grid { grid-template-columns: minmax(0, 1fr); }
    .grid-2 > *, .grid-3 > * { grid-column: auto !important; min-width: 0; }
    .content-area { padding: 14px 12px; } .topbar { padding: 12px; }
    .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .stat-card { padding: 12px; } .stat-val { font-size: 23px; }
    .floating-bulk-bar { flex-wrap: wrap; width: calc(100% - 24px); bottom: 8px; gap: 8px; padding: 12px; }
    .toast { left: 12px; right: 12px; top: 12px; }
    .card { padding: 14px; } .drawer { max-width: 100vw; }
    .topbar-left, .topbar-right { width: 100%; } .ip-capsule { max-width: 100%; overflow-wrap: anywhere; }
  }
</style>
</head>
<body>

<!-- Left Sidebar Navigation (ISS-001) -->
<aside class="sidebar">
  <div class="brand">
    <div class="brand-logo">A</div>
    <div>
      <div class="brand-title">Agnes 工作台</div>
      <div class="brand-sub">可视化流程 · 导号 · 代理池</div>
    </div>
  </div>

  <div class="nav-list">
    <button class="nav-item active" id="nav-dashboard" onclick="switchTab('dashboard', this)">
      <span>🚀 任务监控大盘</span>
      <span class="nav-badge" id="navBadgeTotal">0</span>
    </button>
    <button class="nav-item" id="nav-import" onclick="switchTab('import', this)">
      <span>📥 账号导入与核验</span>
      <span class="nav-badge">预览向导</span>
    </button>
    <button class="nav-item" id="nav-flows" onclick="switchTab('flows', this)">
      <span>⛓️ 可视化流程编排</span>
      <span class="nav-badge">步骤流</span>
    </button>
    <button class="nav-item" id="nav-proxies" onclick="switchTab('proxies', this)">
      <span>🌐 代理池与换IP策略</span>
      <span class="nav-badge" id="navBadgeProxies">0</span>
    </button>
    <button class="nav-item" id="nav-delivery" onclick="switchTab('delivery', this)">
      <span>📦 交付导出与备份</span><span class="nav-badge">本地</span>
    </button>
  </div>

  <div class="sidebar-footer">
    <div id="configPathText" style="word-break: break-all;">正在加载配置...</div>
    <div class="btn-row" style="justify-content: space-between;">
      <button class="btn btn-secondary btn-sm" onclick="toggleTheme()">🌓 切换深浅主题</button>
      <button class="btn btn-secondary btn-sm" onclick="refreshAll()">🔄 刷新</button>
    </div>
  </div>
</aside>

<!-- Main Content Shell -->
<div class="main-shell">
  <!-- Persistent Top Control Bar (ISS-001) -->
  <header class="topbar">
    <div class="topbar-left">
      <div id="runnerStatusPill" class="status-pill idle">
        <span class="status-dot"></span>
        <span id="runnerStatusText">空闲待命</span>
      </div>
      <select id="batchSelect" aria-label="当前批次" onchange="onBatchChange()" style="min-width: 190px; font-weight: 600;"></select>
      <input type="number" id="runLimitInput" placeholder="执行数量(留空=全部)" min="1" style="width: 155px;" />
      <button class="btn btn-success" onclick="controlBatch('run')">▶ 开始/继续注册</button>
      <button class="btn btn-primary" onclick="controlBatch('verify_batch')">🔐 批量验登录&拿结果</button>
       <button class="btn btn-warning btn-sm" onclick="controlBatch('pause')">⏸ 暂停</button>
       <button class="btn btn-secondary btn-sm" onclick="controlBatch('resume')">▷ 恢复</button>
      <button class="btn btn-danger btn-sm" onclick="controlBatch('stop')">⏹ 停止</button>
      <button class="btn btn-secondary btn-sm" onclick="controlBatch('recover')">🛠 恢复中断</button>
    </div>
    <div class="topbar-right">
      <div class="ip-capsule" onclick="switchTab('proxies', document.getElementById('nav-proxies'))" title="点击进入代理池与自动换IP面板">
        <span>🌐</span>
        <span id="topIpCapsuleText">代理池: 未启用</span>
      </div>
      <button class="btn btn-primary btn-sm" onclick="exportData('xlsx')">📥 导出 Excel</button>
      <button class="btn btn-secondary btn-sm" onclick="exportData('csv')">📄 导出 CSV</button>
    </div>
  </header>

  <main class="content-area">
    <!-- Top Summary Cards -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">总任务账号数</div>
        <div class="stat-val" id="statTotal">0</div>
        <div class="stat-sub" id="statBatchCount">共 0 个批次</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已达成目标结果 (含Key/已激活)</div>
        <div class="stat-val" style="color: var(--success)" id="statSucceeded">0</div>
        <div class="stat-sub" id="statWithKey">其中已提取最终结果: 0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">等待执行 / 正在运行</div>
        <div class="stat-val" style="color: var(--primary)" id="statPending">0</div>
        <div class="stat-sub" id="statRunning">正在运行: 0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">待登录验证 / 需人工处理</div>
        <div class="stat-val" style="color: var(--warning)" id="statReview">0</div>
        <div class="stat-sub" id="statFailed">失败/跳过: 0</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">代理池 & 自动换 IP 进度</div>
        <div class="stat-val" style="color: var(--purple); font-size: 19px;" id="statProxySummary">直连模式</div>
        <div class="stat-sub" id="statProxyRotation">每达成 1 次结果换 IP</div>
      </div>
    </div>

    <!-- ==================== TAB 1: DASHBOARD & DATA TABLE (ISS-001) ==================== -->
    <div id="tab-dashboard" class="tab-panel active">
      <div class="card">
        <div class="card-title">
          <span>实时执行进度与运行终端</span>
          <span style="font-size: 12px; color: var(--text-muted);" id="progressPercentText">完成率 0%</span>
        </div>
        <div class="progress-track">
          <div class="progress-seg" id="progSuccess" style="width: 0%; background: var(--success);" title="已完成"></div>
          <div class="progress-seg" id="progNoKey" style="width: 0%; background: var(--purple);" title="已登录待拿结果"></div>
          <div class="progress-seg" id="progRunning" style="width: 0%; background: var(--primary);" title="正在运行"></div>
          <div class="progress-seg" id="progReview" style="width: 0%; background: var(--warning);" title="待验证/待核查"></div>
          <div class="progress-seg" id="progFailed" style="width: 0%; background: var(--danger);" title="失败/跳过"></div>
          <div class="progress-seg" id="progPending" style="width: 0%; background: var(--text-muted);" title="待处理"></div>
        </div>
        <div id="runnerSlots" class="mono" style="margin:8px 0;color:var(--text-muted)"></div>
        <div class="btn-row">
          <label class="checkbox-row"><input id="logAutoScroll" type="checkbox" checked />自动滚动</label>
          <button class="btn btn-secondary btn-sm" onclick="clearLogs()">清空当前日志视图</button>
          <span class="stat-sub">绿：完成 · 紫：已登录待拿结果 · 蓝：运行 · 黄：待核验 · 红：异常 · 灰：待处理</span>
        </div>
        <div class="log-box" id="runnerLogsBox" style="margin-top: 10px;">等待任务启动...</div>
      </div>

      <div class="card">
        <div class="card-title">
          <div class="filter-pills" id="stateFilterPills">
            <button class="filter-pill active" onclick="setStateFilter('', this)">全部</button>
            <button class="filter-pill" onclick="setStateFilter('SUCCEEDED', this)">✅ 已完成</button>
            <button class="filter-pill" onclick="setStateFilter('PENDING', this)">⏳ 等待执行</button>
            <button class="filter-pill" onclick="setStateFilter('PENDING_VERIFY', this)">🔐 待登录验证</button>
            <button class="filter-pill" onclick="setStateFilter('NEEDS_REVIEW', this)">⚠️ 需人工处理</button>
            <button class="filter-pill" onclick="setStateFilter('UNKNOWN', this)">❓ 结果待核查</button>
            <button class="filter-pill" onclick="setStateFilter('FAILED', this)">❌ 失败</button>
          </div>
          <div class="btn-row">
            <label class="checkbox-row" style="font-size: 12.5px;">
              <input type="checkbox" id="revealSecretsToggle" onchange="onRevealChange()" />
              显示明文密码与提取结果
            </label>
              <input type="text" id="jobSearchInput" aria-label="搜索任务" placeholder="🔍 搜索邮箱 / 用户ID / 错误码..." oninput="onJobSearch()" style="width: 220px;" />
          </div>
        </div>

        <div class="table-wrap" style="margin-top: 12px;">
          <table>
            <thead>
              <tr>
                <th style="width:36px;"><input type="checkbox" id="selectAllJobs" onchange="toggleSelectAllJobs(this)" /></th>
                <th>邮箱账号 (点击复制)</th>
                <th>状态</th>
                <th>执行阶段</th>
                <th>平台登录密码</th>
                <th>最终提取结果 (API Key / Token)</th>
                <th>代理节点</th>
                <th>状态说明 / 错误码</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="jobsTableBody">
              <tr><td colspan="9" style="text-align:center; color: var(--text-muted); padding: 24px;">正在加载任务列表...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ==================== TAB 2: SMART IMPORT WIZARD & VERIFY (ISS-003) ==================== -->
    <div id="tab-import" class="tab-panel">
      <div class="callout">
        💡 <b>实时分列预览向导：</b>把账号粘贴到下方（或拖入 <code>.txt/.csv</code> 文件），底下会<b>立刻实时显示分列预览结果</b>，哪一列是邮箱、哪一列是密码、哪一行格式写错了当场标红！确认无误后点导入即可。
      </div>

      <div class="card">
        <h3 class="card-title">第一步：选择这批账号要执行的任务模式</h3>
        <div class="choice-grid">
          <div class="choice-card selected" id="modeCardRegister" onclick="selectImportMode('register')">
            <h4>🆕 模式 A：新账号批量注册</h4>
            <p>按设定的「注册流程 ➔ 接收验证码 ➔ 提取最终结果」完整走完新开户流程。</p>
          </div>
          <div class="choice-card" id="modeCardExisting" onclick="selectImportMode('existing_login')">
            <h4>🔐 模式 B：已有平台账号（直接验证登录 & 拿结果）</h4>
            <p>跳过注册！直接用导入的账号密码登录平台，验证账号是否有效并把 API Key / 目标结果提出来。</p>
          </div>
        </div>
        <input type="hidden" id="importMode" value="register" />

        <div class="grid-3">
          <div class="field">
            <label>账号数据格式</label>
            <select id="importFormat" onchange="updateImportPreview()">
              <option value="auto">✨ 自动识别格式（支持 1~5 段及 CSV）</option>
              <option value="four_part">四段式：邮箱----邮箱密码----ClientID----RefreshToken</option>
              <option value="three_part">三段式：邮箱----邮箱密码----平台登录密码</option>
              <option value="two_part">两段式：邮箱----密码</option>
              <option value="email_only">单列纯邮箱（自动生成强密码）</option>
              <option value="csv">标准 CSV 格式</option>
            </select>
          </div>
          <div class="field">
            <label>字段分隔符</label>
            <select id="importDelimiter" onchange="updateImportPreview()">
              <option value="auto">自动检测 (---- / : / , / | / Tab)</option>
              <option value="----">四横线 (----)</option>
              <option value=":">冒号 (:)</option>
              <option value=",">逗号 (,)</option>
              <option value="|">竖线 (|)</option>
              <option value="\t">制表符 (Tab)</option>
            </select>
          </div>
          <div class="field">
            <label>两段式“邮箱----密码”中密码用途</label>
            <select id="importPasswordRole" onchange="updateImportPreview()">
              <option value="both">同时作为邮箱密码 & 平台登录密码</option>
              <option value="agnes_only">仅作为平台登录密码（已有账号验号常用）</option>
              <option value="mailbox_only">仅作为邮箱密码（平台密码自动生成）</option>
            </select>
          </div>
          <div class="field">
            <label>自动加入批次名称</label>
            <input type="text" id="importBatchId" value="batch-main" placeholder="例如：batch-main" />
          </div>
          <div class="field">
            <label>邮箱自动收码协议</label>
            <select id="importMailboxTransport">
              <option value="graph">Microsoft Graph API（四段式推荐）</option>
              <option value="imap">Outlook IMAP XOAUTH2</option>
              <option value="imap_password">标准 IMAP 账号密码登录</option>
            </select>
          </div>
          <div class="field">
            <label>选择本地文件导入 (.txt / .csv)</label>
            <input type="file" id="importFilePicker" accept=".txt,.csv" onchange="loadImportFile(this)" />
          </div>
        </div>

        <div class="field">
          <label>粘贴账号数据（每行一条，支持实时分列预览）</label>
          <div id="importDropZone" class="drop-zone">拖入 .txt / .csv 文件到这里，或在下方粘贴。文件仅在本机解析。</div>
          <textarea id="importAccountsText" aria-label="账号导入内容" rows="6" oninput="updateImportPreview()" placeholder="在此粘贴账号，下方将实时生成分列预览表：&#10;user1@example.com----MailPass123----client-id-xxx----example-refresh-token&#10;user2@example.com----MyPlatformPass123&#10;user3@example.com"></textarea>
        </div>

        <!-- Live Parse Preview Table (ISS-003) -->
        <div style="margin: 12px 0;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span style="font-size:13px; font-weight:700;">🔍 实时分列解析预览（导入前自动校验）</span>
            <span id="importPreviewSummary" class="badge badge-muted">等待输入数据...</span>
          </div>
          <div class="table-wrap" style="max-height: 220px; overflow-y: auto;">
            <table>
              <thead>
                <tr>
                  <th>行号</th>
                  <th>校验状态</th>
                  <th>识别类型</th>
                  <th>邮箱账号</th>
                  <th>邮箱密码</th>
                  <th>平台登录密码</th>
                  <th>OAuth ClientID</th><th>RefreshToken</th>
                </tr>
              </thead>
              <tbody id="importPreviewBody">
                <tr><td colspan="8" style="text-align:center; color:var(--text-muted);">在上方粘贴账号后，此处将实时展示每一行的分列结果</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="btn-row">
          <button class="btn btn-primary" id="importSubmit" onclick="submitImportAccounts()">🚀 确认无误，立即批量导入账号</button>
          <span id="importResultBox" style="font-size: 13px; color: var(--success); font-weight: 600;"></span>
        </div>
      </div>

      <!-- Verification Mode Cards (ISS-003) -->
      <div class="card">
        <h3 class="card-title">第二步：设置验证码获取方式 & 登录成功核验标准</h3>
        <p class="card-desc">选择注册时如何获取邮箱验证码，以及验证账号登录时如何判断登录成功。</p>
        <label style="font-size:13px; font-weight:700; display:block; margin-bottom:8px;">📬 注册验证码获取模式 (`verification.mode`)</label>
        <div class="choice-grid">
          <div class="choice-card selected" id="vCardAuto" onclick="selectVerifyMode('auto_mailbox')">
            <h4>📬 自动从邮箱读取验证码</h4>
            <p>通过 Microsoft Graph 或 IMAP 自动连接收件箱/垃圾箱提取验证码。</p>
          </div>
          <div class="choice-card" id="vCardManual" onclick="selectVerifyMode('manual')">
            <h4>👀 弹出浏览器人工输入</h4>
            <p>自动打开可见浏览器窗口，停在验证码框等待你手动输入 6 位验证码。</p>
          </div>
          <div class="choice-card" id="vCardNone" onclick="selectVerifyMode('none')">
            <h4>⚡ 无需邮箱验证码</h4>
            <p>目标注册页不需要邮箱验证码，填完账号密码后直接点击提交按钮。</p>
          </div>
        </div>
        <input type="hidden" id="cfgVerifyMode" value="auto_mailbox" />
        <div class="field"><label>账号登录成功核验标准</label><select id="importLoginVerifyMode" onchange="selectLoginVerifyMode(this.value)"><option value="strict_identity">严格匹配页面邮箱 + 已登录标志（推荐）</option><option value="selector_only">仅检查已登录元素</option><option value="url_or_token">跳出登录页与 LocalStorage Token</option></select><small>与流程编排中的登录核验设置同步保存。</small></div>

        <div class="grid-3">
          <div class="field">
            <label>验证码发件人域名过滤 (`sender_domain`)</label>
            <input type="text" id="cfgSenderDomain" placeholder="agnes-ai.com (填 * 不限域名)" />
          </div>
          <div class="field">
            <label>验证码提取正则 (`code_pattern`)</label>
            <input type="text" id="cfgCodePattern" class="mono" placeholder="(?<!\d)\d{6}(?!\d)" />
          </div>
          <div class="field">
            <label>IMAP 服务器 / 等待超时(秒)</label>
            <div style="display:flex; gap:6px;">
              <input type="text" id="cfgImapHost" placeholder="outlook.office365.com" style="flex:1;" />
              <input type="number" id="cfgVerifyTimeout" min="5" max="900" style="width:85px;" title="验证码超时秒数" />
            </div>
          </div>
        </div>

        <button class="btn btn-primary" onclick="saveAllConfig()">💾 保存验证设置</button>
      </div>
    </div>

    <!-- ==================== TAB 3: VISUAL FLOW BUILDER (ISS-002) ==================== -->
    <div id="tab-flows" class="tab-panel">
      <div class="callout">
        💡 <b>可视化步骤流编排器（参考 Automa / n8n）：</b>整个流程按执行先后顺序排列成步骤卡片。你可以用<b>「定位助手」</b>（按按钮文字 / 按输入框提示词）自动生成选择器，在任意阶段点 <b>「+ 插入自定义步骤」</b> 并上下调整顺序，还能在最下方<b>实时测试结果正则表达式</b>！
      </div>

      <div class="card">
        <div class="card-title">
          <span>🌐 全局运行参数 & 目标网站设置</span>
          <div class="btn-row">
            <button class="btn btn-secondary btn-sm" onclick="resetFlowDefaults()">🔄 一键恢复 Agnes 官方默认流程</button>
            <button class="btn btn-primary btn-sm" onclick="saveAllConfig()">💾 保存全部流程修改</button>
          </div>
        </div>
        <div class="grid-3">
          <div class="field">
            <label>目标平台根网址 (`base_url`)</label>
            <input type="text" id="cfgBaseUrl" class="mono" placeholder="https://platform.agnes-ai.com" />
          </div>
          <div class="field">
            <label>运行模式 (`mode`)</label>
            <select id="cfgMode">
              <option value="agnes">🌐 真实浏览器执行 (agnes)</option>
              <option value="mock">🧪 本地模拟演练 (mock)</option>
            </select>
          </div>
          <div class="field">
            <label>浏览器窗口模式 (`headless`)</label>
            <select id="cfgHeadless">
              <option value="false">🖥 显示浏览器窗口 (方便观察与调试)</option>
              <option value="true">👻 后台静默无头运行 (Headless)</option>
            </select>
          </div>
          <div class="field">
            <label>同时并发窗口数 (`concurrency`)</label>
            <input type="number" id="cfgConcurrency" min="1" max="50" />
          </div>
          <div class="field">
            <label>每分钟最大提交数 (`per_minute`)</label>
            <input type="number" id="cfgPerMinute" min="0.1" step="0.5" />
          </div>
          <div class="field">
            <label>失败最大重试次数 (`max_attempts`)</label>
            <input type="number" id="cfgMaxAttempts" min="1" max="10" />
          </div>
        </div>
      </div>

      <!-- Visual Pipeline Stage 1: Registration -->
      <div class="card">
        <h3 class="card-title">阶段一：打开与填写注册流程 (`registration_flow`)</h3>
        <div class="pipeline">
          <div class="pipe-step">
            <div class="pipe-head">
              <div><span class="pipe-num">1</span><span class="pipe-title">访问入口页面 & 切换到注册表单</span></div>
              <span class="pipe-summary">PUBLIC_LOGIN_LOAD ➔ REGISTRATION_LINK</span>
            </div>
            <div class="grid-3">
              <div class="field">
                <label>入口路径 (`entry_path`)</label>
                <input type="text" id="regEntryPath" class="mono" placeholder="/login" />
              </div>
              <div class="field">
                <label>定位助手：怎么找“切换注册”按钮？</label>
                <select onchange="applySmartSelector(this, 'regOpenSelector', '注册')">
                  <option value="">-- 快速生成定位器 --</option>
                  <option value="default">使用 Agnes 默认 (role=link[name="注册"])</option>
                  <option value="text">按按钮/链接上的文字定位</option>
                  <option value="none">入口直接就是注册页（无需点击，填 none）</option>
                </select>
              </div>
              <div class="field">
                <label>切换注册选择器 (`open_register_selector`)</label>
                <input type="text" id="regOpenSelector" class="mono" placeholder='留空默认：role=link[name="注册"]' />
              </div>
            </div>
          </div>

          <div class="pipe-step">
            <div class="pipe-head">
              <div><span class="pipe-num">2</span><span class="pipe-title">填写邮箱、密码与确认密码</span></div>
              <span class="pipe-summary">REGISTRATION_FIELDS</span>
            </div>
            <div class="grid-3">
              <div class="field">
                <label>邮箱输入框选择器 (`email_selector`)</label>
                <div style="display:flex; gap:6px;">
                  <input type="text" id="regEmailSelector" class="mono" placeholder='默认：role=textbox[name="邮箱"]' style="flex:1;" />
                  <button class="btn btn-secondary btn-sm" onclick="promptPlaceholder('regEmailSelector', '邮箱')">按提示词</button>
                </div>
              </div>
              <div class="field">
                <label>密码输入框选择器 (`password_selector`)</label>
                <div style="display:flex; gap:6px;">
                  <input type="text" id="regPasswordSelector" class="mono" placeholder='默认：role=textbox[name="密码"]' style="flex:1;" />
                  <button class="btn btn-secondary btn-sm" onclick="promptPlaceholder('regPasswordSelector', '密码')">按提示词</button>
                </div>
              </div>
              <div class="field">
                <label>确认密码框选择器 (`confirm_password_selector`)</label>
                <div style="display:flex; gap:6px;">
                  <input type="text" id="regConfirmSelector" class="mono" placeholder='默认匹配确认密码（无此框填 none）' style="flex:1;" />
                  <button class="btn btn-secondary btn-sm" onclick="document.getElementById('regConfirmSelector').value='none'">无确认框</button>
                </div>
              </div>
            </div>
          </div>

          <div class="pipe-step">
            <div class="pipe-head">
              <div><span class="pipe-num">3</span><span class="pipe-title">发送验证码、填写验证码并点击提交</span></div>
              <span class="pipe-summary">EMAIL_REQUESTED ➔ REGISTRATION_SUBMITTED</span>
            </div>
            <div class="grid-2">
              <div class="field">
                <label>发码按钮就绪选择器 (`send_code_ready_selector`)</label>
                <input type="text" id="regSendReadySelector" class="mono" placeholder='默认：img[alt="can send"]' />
              </div>
              <div class="field">
                <label>点击发码选择器 (`send_code_click_selector`，留空同左)</label>
                <input type="text" id="regSendClickSelector" class="mono" placeholder="留空则直接点击就绪元素" />
              </div>
              <div class="field">
                <label>验证码输入框选择器 (`code_input_selector`)</label>
                <input type="text" id="regCodeInputSelector" class="mono" placeholder='默认：role=textbox[name="验证码"]' />
              </div>
              <div class="field">
                <label>提交注册按钮选择器 (`submit_button_selector`)</label>
                <div style="display:flex; gap:6px;">
                  <input type="text" id="regSubmitSelector" class="mono" placeholder='默认：button:has-text("继续")' style="flex:1;" />
                  <button class="btn btn-secondary btn-sm" onclick="promptTextSelector('regSubmitSelector', '立即注册')">按按钮文字</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div style="margin-top: 14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <label style="font-size:13.5px; font-weight:700;">➕ 注册阶段插入自定义步骤（支持 ↑↓ 调整顺序，可用变量 `{email}` `{password}` `{user_id}` `{code}`）</label>
            <button class="btn btn-primary btn-sm" onclick="addCustomStep('reg')">+ 插入注册自定义步骤</button>
          </div>
          <div id="regCustomStepsContainer"></div>
        </div>
      </div>

      <!-- Visual Pipeline Stage 2: Login & Identity Verification -->
      <div class="card">
        <h3 class="card-title">阶段二：登录核验与身份确认流程 (`login_flow`)</h3>
        <div class="choice-grid">
          <div class="choice-card selected" id="lCardStrict" onclick="selectLoginVerifyMode('strict_identity')">
            <h4>🛡 严格核验模式 (strict_identity)</h4>
            <p>确认页面显示当前用户的完整邮箱 + 出现已登录标志元素（最安全，防串号）。</p>
          </div>
          <div class="choice-card" id="lCardSelector" onclick="selectLoginVerifyMode('selector_only')">
            <h4>🎯 元素核验模式 (selector_only)</h4>
            <p>只要登录后页面出现指定的“已登录标志元素”即判定登录成功。</p>
          </div>
          <div class="choice-card" id="lCardToken" onclick="selectLoginVerifyMode('url_or_token')">
            <h4>⚡ 快速 Token 模式 (url_or_token)</h4>
              <p>必须同时满足：可信站点内离开登录页 + 非空 LocalStorage Token。严格身份核验更适合正式交付。</p>
          </div>
        </div>
        <input type="hidden" id="cfgLoginVerifyMode" value="strict_identity" />

        <div class="grid-3">
          <div class="field">
            <label>登录页路径 (`login_path`)</label>
            <input type="text" id="loginPath" class="mono" placeholder="/login" />
          </div>
          <div class="field">
            <label>登录邮箱框选择器 (`email_selector`)</label>
            <input type="text" id="loginEmailSelector" class="mono" placeholder='默认：role=textbox[name="邮箱"]' />
          </div>
          <div class="field">
            <label>登录密码框选择器 (`password_selector`)</label>
            <input type="text" id="loginPasswordSelector" class="mono" placeholder='默认：input[placeholder="请输入密码"]' />
          </div>
          <div class="field">
            <label>登录提交按钮选择器 (`submit_selector`)</label>
            <input type="text" id="loginSubmitSelector" class="mono" placeholder='默认：button:has-text("登录")' />
          </div>
          <div class="field">
            <label>登录接口校验路径 (`login_api_path`，不拦截填 none)</label>
            <input type="text" id="loginApiPath" class="mono" placeholder="/api/user/login" />
          </div>
          <div class="field">
            <label>登录后跳转路径 (`post_login_path`)</label>
            <input type="text" id="loginPostPath" class="mono" placeholder="/settings/apiKeys" />
          </div>
          <div class="field"><label>登录令牌 LocalStorage 键名</label><input id="loginTokenKey" type="text" value="token" /></div>
          <div class="field">
            <label>个人资料导航选择器 (`identity_navigation_selector`)</label>
            <input type="text" id="cfgIdentityNav" class="mono" placeholder='text="个人资料"' />
          </div>
          <div class="field">
            <label>已登录标志选择器 (`authenticated_selector`)</label>
            <input type="text" id="cfgAuthSelector" class="mono" placeholder='img[alt="user"]' />
          </div>
          <div class="field">
            <label>页面邮箱元素选择器 (`account_identity_selector`)</label>
            <input type="text" id="cfgAccountIdentitySelector" class="mono" placeholder="留空默认全文匹配邮箱文字" />
          </div>
        </div>
        <div class="insert-zone"><button class="btn btn-primary btn-sm" onclick="addCustomStep('login')">+ 插入登录自定义动作</button><div id="loginCustomStepsContainer"></div></div>
      </div>

      <!-- Visual Pipeline Stage 3: Final Result / Key Flow + Live Regex Tester -->
      <div class="card">
        <h3 class="card-title">阶段三：获得最终想要结果的流程 (`key_flow` / Result Flow)</h3>
        <div class="btn-row" style="margin-bottom: 14px; gap: 24px;">
          <label class="checkbox-row">
            <input type="checkbox" id="keyFlowEnabled" checked />
            <b>启用最终结果提取流程 (`key_flow.enabled`)</b>
          </label>
          <label class="checkbox-row">
            <input type="checkbox" id="keyFlowRequireKey" checked />
            <b>必须提取到最终结果才算任务完成 (`require_key`)</b>
          </label>
        </div>

        <div class="pipeline">
          <div class="pipe-step">
            <div class="pipe-head">
              <div><span class="pipe-num">1</span><span class="pipe-title">进入最终结果所在页面 & 触发创建动作</span></div>
              <span class="pipe-summary">KEY_REQUESTED</span>
            </div>
            <div class="grid-3">
              <div class="field">
                <label>点击进入结果页选择器 (`navigation_selector`)</label>
                <input type="text" id="keyNavSelector" class="mono" placeholder='text="API 密钥"' />
              </div>
              <div class="field">
                <label>或直接跳转结果页 URL (`target_url`)</label>
                <input type="text" id="keyTargetUrl" class="mono" placeholder="例如：/settings/apiKeys" />
              </div>
              <div class="field">
                <label>点击“创建新密钥/目标”按钮 (`create_selector`)</label>
                <input type="text" id="keyCreateSelector" class="mono" placeholder='button:has-text("创建新的密钥") >> nth=0' />
              </div>
              <div class="field">
                <label>名称输入框选择器 (`name_selector`)</label>
                <input type="text" id="keyNameSelector" class="mono" placeholder="#keyName" />
              </div>
              <div class="field">
                <label>填写的名称模板 (`name_template`)</label>
                <input type="text" id="keyNameTemplate" class="mono" placeholder="Agnes Provisioner {user_id}" />
              </div>
              <div class="field">
                <label>弹窗确认创建按钮 (`confirm_selector`)</label>
                <input type="text" id="keyConfirmSelector" class="mono" placeholder=".ant-modal .ant-btn-primary" />
              </div>
            </div>
          </div>

          <div class="pipe-step">
            <div class="pipe-head">
              <div><span class="pipe-num">2</span><span class="pipe-title">提取最终想要的结果 (DOM / 接口JSON / 剪贴板 / LocalStorage)</span></div>
              <span class="pipe-summary">ACTIVATED_WITH_KEY</span>
            </div>
            <div class="grid-3">
              <div class="field">
                <label>结果提取渠道 (`extract_mode`)</label>
                <select id="keyExtractMode">
                  <option value="auto">✨ 全能自动提取 (DOM + 接口JSON + 剪贴板复制)</option>
                  <option value="dom_regex">📄 仅从页面元素文本正则提取 (DOM Regex)</option>
                  <option value="network_json">🌐 仅从接口返回 JSON 自动抓取 (Network JSON)</option>
                  <option value="clipboard_copy">📋 仅点击复制按钮拦截剪贴板</option>
                  <option value="local_storage">🗄 从浏览器 LocalStorage 读取指定键</option>
                </select>
              </div>
              <div class="field">
                <label>结果文本容器选择器 (`value_selector`)</label>
                <input type="text" id="keyValueSelector" class="mono" placeholder=".ant-modal, .ant-table-tbody" />
              </div>
              <div class="field">
                <label>复制按钮选择器 (`copy_selector`)</label>
                <input type="text" id="keyCopySelector" class="mono" placeholder='tr:has-text("Agnes Provisioner {user_id}") img[alt="复制"]' />
              </div>
              <div class="field">
                <label>LocalStorage 键名 (`storage_key`，可选)</label>
                <input type="text" id="keyStorageKey" class="mono" placeholder="例如：token" />
              </div>
              <div class="field" style="grid-column: span 2;">
                <label>最终结果正则匹配规则 (`pattern`) —— 点击右侧模板可快速填入：</label>
                <input type="text" id="keyPattern" class="mono" oninput="runRegexTester()" placeholder="sk-[A-Za-z0-9_-]{16,}" />
                <div class="btn-row" style="margin-top:4px;">
                  <button class="btn btn-secondary btn-sm" onclick="setKeyPattern('sk-[A-Za-z0-9_-]{16,}')">sk- API密钥</button>
                  <button class="btn btn-secondary btn-sm" onclick="setKeyPattern('eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+')">JWT Token</button>
                  <button class="btn btn-secondary btn-sm" onclick="setKeyPattern('[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')">UUID格式</button>
                   <button class="btn btn-secondary btn-sm" onclick="setKeyPattern('.+')">任意非空内容</button>
                   <button class="btn btn-secondary btn-sm" onclick="setKeyPattern('(?&lt;!\\d)\\d{6}(?!\\d)')">6 位数字码</button>
                </div>
              </div>
            </div>

            <!-- Live Regex Tester (ISS-002) -->
            <div style="margin-top: 10px; padding: 12px; background: var(--bg-card); border: 1px dashed var(--border); border-radius: 8px;">
              <div style="font-size: 12.5px; font-weight: 700; margin-bottom: 6px;">🧪 正则表达式实时测试器（粘贴示例网页文字或 JSON，立即验证能否提取出想要的结果）</div>
              <div class="grid-2" style="align-items: center;">
                <input type="text" id="regexSampleInput" class="mono" oninput="runRegexTester()" value='{"code":200,"data":{"apiKey":"sk-AbCdEf1234567890"}}' placeholder="在此粘贴包含目标结果的示例文本..." />
                <div id="regexTestResult" class="mono" style="font-size: 13px; color: var(--success); font-weight: 700;"></div>
              </div>
            </div>
          </div>
        </div>

        <div style="margin-top: 14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <label style="font-size:13.5px; font-weight:700;">➕ 结果阶段自定义步骤（支持 ↑↓ 调整顺序）</label>
            <button class="btn btn-primary btn-sm" onclick="addCustomStep('key')">+ 插入结果流程步骤</button>
          </div>
          <div id="keyCustomStepsContainer"></div>
        </div>

        <div class="btn-row" style="margin-top: 16px;">
          <button class="btn btn-primary" onclick="saveAllConfig()">💾 保存全部流程修改并写入配置文件</button>
        </div>
      </div>
    </div>

    <!-- ==================== TAB 4: PROXY POOL & AUTO IP ROTATION (ISS-004) ==================== -->
    <div id="tab-proxies" class="tab-panel">
      <!-- Active Proxy & Rotation Progress Banner (ISS-004) -->
      <div class="card" style="border-color: rgba(139, 92, 246, 0.4);">
        <div class="card-title">
          <span>🌐 当前激活代理 & 自动换 IP 实时进度监控</span>
          <div class="btn-row">
            <button class="btn btn-secondary btn-sm" onclick="proxyAction('rotate_now')">⏭ 立即手动切换到下一个 IP</button>
            <button class="btn btn-secondary btn-sm" onclick="proxyAction('reset_rotation')">♻️ 重置所有计数与状态</button>
          </div>
        </div>
        <div class="grid-3" style="align-items: center; margin-top: 8px;">
          <div>
            <div style="font-size: 12px; color: var(--text-muted);">当前顺位首选代理节点</div>
            <div style="font-size: 18px; font-weight: 800; color: var(--purple);" class="mono" id="activeProxyNodeTitle">本机直连 (未导入代理)</div>
            <div style="font-size: 12px; color: var(--text-muted);" id="activeProxyServerSub">-</div>
          </div>
          <div style="grid-column: span 2;">
            <div style="display:flex; justify-content:space-between; font-size:12.5px; font-weight:600; margin-bottom:4px;">
              <span id="activeProxyWindowLabel">本轮换 IP 进度：0 / 1 次</span>
              <span id="activeProxyCountdownLabel" style="color: var(--success);">完成设定次数后自动切换下一节点</span>
            </div>
            <div class="progress-track" style="height: 12px;">
              <div class="progress-seg" id="activeProxyProgressBar" style="width: 0%; background: linear-gradient(90deg, #3b82f6, #8b5cf6);"></div>
            </div>
          </div>
        </div>
      </div>

      <div class="grid-2">
        <!-- Rotation Policy Configuration -->
        <div class="card">
          <h3 class="card-title">🔄 满 X 次自动换 IP 策略设置 (`proxy_pool`)</h3>
          <p class="card-desc">选择按“达成想要的结果次数”还是“执行注册流程次数”触发换 IP。</p>

          <div class="choice-grid" style="grid-template-columns: 1fr;">
            <div class="choice-card selected" id="pModeResult" onclick="selectProxyRotateMode('result_reached')">
              <h4>🎯 模式 1：每达到 X 次【最终想要的结果】就换 IP（推荐）</h4>
              <p>只有成功完成注册并拿到最终结果（如 API Key）才计入次数，满 X 次立即换下一个代理 IP。</p>
            </div>
            <div class="choice-card" id="pModeExec" onclick="selectProxyRotateMode('execution_count')">
              <h4>🔢 模式 2：每执行 X 次【注册流程】就换 IP</h4>
              <p>无论成功或失败，只要用当前代理跑满 X 次流程就立即切换下一个代理 IP。</p>
            </div>
            <div class="choice-card" id="pModeBoth" onclick="selectProxyRotateMode('both')">
              <h4>⚡ 模式 3：达成 X 次目标结果 【或】 执行满 Y 次流程就换 IP</h4>
              <p>双重兜底：拿到 X 个结果换 IP；如果一直没成功，最多执行 Y 次也强制换 IP。</p>
            </div>
          </div>
          <input type="hidden" id="cfgProxyRotateMode" value="result_reached" />

          <div class="grid-2">
            <div class="field">
              <label>触发换 IP 的次数阈值 (`rotate_every` = X)</label>
              <input type="number" id="cfgProxyRotateEvery" min="1" max="10000" value="2" />
            </div>
            <div class="field">
              <label>单 IP 最大执行次数兜底 (`rotate_executions_limit` = Y)</label>
              <input type="number" id="cfgProxyExecLimit" min="1" max="10000" value="3" />
            </div>
          </div>

          <div class="field">
            <label class="checkbox-row">
              <input type="checkbox" id="cfgAutoSwitchIpLimit" checked />
              <b>遇到平台提示“当前 IP 注册过多”时自动熔断并切换下一个 IP</b>
            </label>
          </div>
          <div class="field">
            <label class="checkbox-row">
              <input type="checkbox" id="cfgEnableSessionStickiness" />
              <b>动态隧道代理模式：换 IP 时自动给用户名追加新 `-session-随机ID`</b>
            </label>
          </div>
          <div class="field">
            <label class="checkbox-row">
              <input type="checkbox" id="cfgProxyRequired" />
              <b>强制要求代理 (`proxy_required`：无可用代理时暂停保护，不走本机直连)</b>
            </label>
          </div>
          <div class="field">
            <label>动态隧道会话后缀模板 (`session_suffix_template`)</label>
            <input type="text" id="cfgSessionSuffix" class="mono" placeholder="-session-{session}-time-30" />
          </div>

          <button class="btn btn-primary" onclick="saveAllConfig()">💾 保存换 IP 策略设置</button>
        </div>

        <!-- Batch Proxy Import with Live Preview -->
        <div class="card">
          <h3 class="card-title">➕ 批量导入代理池（支持实时解析预览）</h3>
          <p class="card-desc">直接粘贴 HTTP / HTTPS / SOCKS5 代理列表，支持固定 IP 池或带 `{session}` 的动态隧道代理。</p>
          <div class="grid-2">
            <div class="field">
              <label>导入后初始状态</label>
              <select id="proxyInitialStatus">
                <option value="HEALTHY">✅ 直接设为可用 (HEALTHY，立即可跑)</option>
                <option value="UNCHECKED">🔍 设为待检测 (需先点检测连通性)</option>
              </select>
            </div>
            <div class="field">
              <label>代理类型预设</label>
              <select id="proxySessionMode">
                <option value="false">📋 静态/独立 IP 代理池（多节点轮换）</option>
                <option value="true">🌪 动态会话隧道代理（自动刷新 Session 换 IP）</option>
              </select>
            </div>
          </div>

          <div class="field">
            <label>粘贴代理地址（每行一条）</label>
            <textarea id="importProxiesText" rows="5" oninput="updateProxyPreview()" placeholder="支持以下任意格式：&#10;http://user:pass@1.2.3.4:8080&#10;1.2.3.4:8080:user:pass&#10;http://user-{session}:pass@gate.example.com:3128&#10;socks5://127.0.0.1:10808"></textarea>
          </div>

          <div style="margin-bottom: 12px;">
            <div style="display:flex; justify-content:space-between; font-size:12.5px; font-weight:700; margin-bottom:6px;">
              <span>🔍 代理格式实时解析预览</span>
              <span id="proxyPreviewCount" class="badge badge-muted">0 条</span>
            </div>
            <div class="table-wrap" style="max-height: 150px; overflow-y: auto;">
              <table>
                <thead>
                   <tr><th>行</th><th>协议 / 主机 / 端口</th><th>账密认证</th><th>会话换IP模式 / 错误</th></tr>
                </thead>
                <tbody id="proxyPreviewBody">
                  <tr><td colspan="4" style="text-align:center; color:var(--text-muted);">粘贴代理后自动预览解析结果</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="btn-row">
            <label class="checkbox-row" style="font-size:12.5px;">
              <input type="checkbox" id="proxyClearExisting" />
              导入前清空旧代理池
            </label>
            <button class="btn btn-primary" onclick="submitImportProxies()">🌐 确认导入代理池</button>
            <button class="btn btn-success" onclick="checkAllProxies()">⚡ 并发测速 & 查出口IP</button>
            <button class="btn btn-danger btn-sm" onclick="proxyAction('clear_all')">🗑 清空</button>
          </div>
          <div id="proxyImportMsg" style="margin-top: 8px; font-size: 13px; color: var(--success);"></div>
        </div>
      </div>

      <!-- Proxy Pool Nodes Table -->
      <div class="card">
        <div class="card-title">
          <span>代理池节点矩阵与本轮换 IP 进度</span>
          <span style="font-size: 12.5px; color: var(--text-muted);">调度器始终优先分配【轮换轮次最小】的可用代理，满 X 次后自动切入下一节点</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>代理 ID</th>
                <th>代理服务器地址</th>
                <th>实测出口 IP / 延迟</th>
                <th>状态</th>
                <th>当前轮次</th>
                <th>本轮换 IP 进度</th>
                <th>累计达成结果 / 累计执行</th>
                <th>当前会话后缀</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="proxiesTableBody">
              <tr><td colspan="9" style="text-align:center; color: var(--text-muted); padding: 20px;">暂无代理节点</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div id="tab-delivery" class="tab-panel">
      <div class="card"><h3 class="card-title">交付导出</h3>
        <p class="card-desc">导出顶部选中的批次；选择“全部批次汇总”则导出所有记录。默认隐藏邮箱和凭证。</p>
        <label class="checkbox-row"><input id="exportIncludeSecrets" type="checkbox" />我需要包含明文账号密码与最终结果的交付文件</label>
        <div class="btn-row" style="margin-top:16px"><button class="btn btn-primary" onclick="exportData('xlsx')">导出 Excel</button><button class="btn btn-secondary" onclick="exportData('csv')">导出 CSV</button></div>
      </div>
      <div class="card"><h3 class="card-title">数据库与加密凭证备份</h3><p class="card-desc">停止执行器后备份。备份保存在配置目录的 outputs/backups 下；DPAPI 凭证只能由保存时的 Windows 用户解密，不会写入明文密码。</p><button class="btn btn-secondary" onclick="createBackup()">创建本地一致性备份</button><p id="backupResult" class="mono"></p></div>
    </div>
  </main>
</div>

<!-- Floating Bulk Action Bar (ISS-001) -->
<div id="floatingBulkBar" class="floating-bulk-bar">
  <span style="font-weight: 700; font-size: 13.5px;">已勾选 <b id="selectedCountText" style="color: var(--primary);">0</b> 个账号</span>
  <button class="btn btn-primary btn-sm" onclick="batchSelectedAction('verify')">🔐 批量验证登录 & 拿结果</button>
  <button class="btn btn-secondary btn-sm" onclick="batchSelectedAction('check_mailbox')">📬 测试邮箱连接</button>
  <button class="btn btn-secondary btn-sm" onclick="batchSelectedAction('requeue_login')">🔄 设为已有账号(仅登录拿结果)</button>
  <button class="btn btn-secondary btn-sm" onclick="batchSelectedAction('requeue')">♻️ 重置为重新注册</button>
  <button class="btn btn-danger btn-sm" onclick="batchSelectedAction('delete')">🗑 批量删除</button>
  <button class="btn btn-secondary btn-sm" onclick="clearJobSelection()">✖ 取消选择</button>
</div>

<!-- Right Slide-over Drawer for Single Job Details & Password Edit (ISS-001) -->
<div id="drawerBackdrop" class="drawer-backdrop" onclick="closeJobDrawer()"></div>
<aside id="jobDrawer" class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawerEmailTitle" aria-hidden="true" inert>
  <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:12px; margin-bottom:16px;">
    <div>
      <div style="font-size:16px; font-weight:800;" id="drawerEmailTitle">账号详情</div>
      <div style="font-size:12px; color:var(--text-muted);" class="mono" id="drawerSubMeta"></div>
    </div>
    <button class="btn btn-secondary btn-sm" onclick="closeJobDrawer()">✕ 关闭 (ESC)</button>
  </div>

  <div id="drawerQuickActions" class="btn-row" style="margin-bottom: 16px;"></div>

  <div class="card" style="padding: 14px; margin-bottom: 16px;">
    <div style="font-size: 13.5px; font-weight: 700; margin-bottom: 10px;">🔑 账号加密凭证与最终提取结果</div>
    <div class="field">
      <label>已提取的最终结果 (`api_key` / Token)</label>
      <div style="display:flex; gap:6px;">
        <input type="password" id="drawerApiKey" class="mono" readonly style="flex:1; color: var(--success);" />
        <button class="btn btn-secondary btn-sm" onclick="copyJobField(STATE.activeDrawerJobId, 'api_key')">📋 复制</button>
      </div>
    </div>
    <div class="grid-2">
      <div class="field" style="margin-bottom:0;">
        <label>平台登录密码 (`agnes_password`)</label>
        <input type="password" id="drawerAgnesPwd" autocomplete="new-password" class="mono" placeholder="输入新平台登录密码（留空不改）" />
      </div>
      <div class="field" style="margin-bottom:0;">
        <label>邮箱密码 (`mailbox_password`)</label>
        <input type="password" id="drawerMailboxPwd" autocomplete="new-password" class="mono" placeholder="输入新邮箱密码（留空不改）" />
      </div>
    </div>
    <div class="btn-row" style="margin-top: 10px;">
      <button class="btn btn-primary btn-sm" onclick="saveDrawerPassword()">💾 保存修改后的密码到加密库</button>
      <button class="btn btn-secondary btn-sm" onclick="copyJobField(STATE.activeDrawerJobId, 'agnes_password')">📋 复制平台密码</button>
      <button id="drawerReveal" class="btn btn-secondary btn-sm" onclick="toggleDrawerSecrets()">显示当前凭证</button>
    </div>
  </div>

  <div>
    <div style="font-size: 13.5px; font-weight: 700; margin-bottom: 12px;">⏱ 状态变更与执行时间线 (`job_events`)</div>
    <div id="drawerTimelineBox"></div>
  </div>
</aside>

<div id="toast" class="toast" role="status" aria-live="polite"></div>

<script>
let STATE = {
  overview: null,
  jobs: [],
  stateFilter: '',
  regSteps: [],
  keySteps: [],
  loginSteps: [],
  selected: new Set(),
  revealedRows: new Set(),
  secrets: new Map(),
  logCutoff: 0,
  refreshBusy: false,
  jobPage: 0,
  searchMatches: null,
  configLoaded: false,
  activeDrawerJobId: null,
};

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const post = (path, data) => api(path, {method: 'POST', body: JSON.stringify(data)});

function showToast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = isError ? 'var(--danger)' : 'var(--primary)';
  el.style.display = 'block';
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => { el.style.display = 'none'; }, 3200);
}

function toggleTheme() {
  const root = document.documentElement;
  const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  root.setAttribute('data-theme', next);
  localStorage.setItem('agnes-theme', next);
}

async function copyText(text, label = '内容') {
  if (!text) {
    showToast(`没有可复制的${label}`, true);
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast(`📋 已复制${label}到剪贴板！`);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const copied = document.execCommand('copy');
    ta.remove();
    showToast(copied ? `📋 已复制${label}到剪贴板！` : '浏览器未允许复制，请手动复制。', !copied);
  }
}

async function api(path, options = {}) {
  const opts = Object.assign({ headers: { 'Content-Type': 'application/json' } }, options);
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok || data.error) {
    throw new Error(data.error || ('请求失败: ' + res.status));
  }
  return data;
}

function switchTab(name, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if (btn) btn.classList.add('active');
}

function stateBadge(state, label) {
  const map = {
    SUCCEEDED: 'badge-success',
    RUNNING: 'badge-pending',
    PENDING: 'badge-muted',
    PENDING_VERIFY: 'badge-warn',
    RETRY_WAIT: 'badge-warn',
    NEEDS_REVIEW: 'badge-danger',
    UNKNOWN: 'badge-warn',
    FAILED: 'badge-danger',
    SKIPPED: 'badge-muted',
    CANCELLED: 'badge-muted',
  };
  return `<span class="badge ${map[state] || 'badge-muted'}">${esc(label || state)}</span>`;
}

async function loadOverview(populateForm = false) {
  try {
    const chosenBatch = document.getElementById('batchSelect').value;
    const data = await api('/api/overview?batch=' + encodeURIComponent(chosenBatch));
    STATE.overview = data;
    document.getElementById('configPathText').textContent = `配置: ${data.config_path}`;

    const s = data.summary;
    const total = s.total || 0;
    const succ = s.states.SUCCEEDED || 0;
    const running = s.states.RUNNING || 0;
    const pending = (s.states.PENDING || 0) + (s.states.RETRY_WAIT || 0);
    const review = (s.states.NEEDS_REVIEW || 0) + (s.states.PENDING_VERIFY || 0) + (s.states.UNKNOWN || 0);
    const failed = (s.states.FAILED || 0) + (s.states.SKIPPED || 0);

    document.getElementById('navBadgeTotal').textContent = `${pending + review}/${running}`;
    document.getElementById('navBadgeTotal').title=`${pending + review} 待办，${running} 运行中`;
    document.getElementById('navBadgeProxies').textContent = data.proxy_summary.total || 0;
    document.getElementById('statTotal').textContent = total;
    document.getElementById('statBatchCount').textContent = `共 ${data.batches.length} 个批次`;
    const completed = s.succeeded_with_key || 0;
    document.getElementById('statSucceeded').textContent = completed;
    document.getElementById('statWithKey').textContent = `其中已提取最终结果: ${s.succeeded_with_key || 0}`;
    document.getElementById('statPending').textContent = pending;
    document.getElementById('statRunning').textContent = `正在运行: ${running}`;
    document.getElementById('statReview').textContent = review;
    document.getElementById('statFailed').textContent = `失败/跳过: ${failed}`;

    // Progress bar
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
    document.getElementById('progressPercentText').textContent = `含结果完成率 ${pct}% (${completed}/${total})`;
    document.getElementById('progSuccess').style.width = total ? `${(completed / total) * 100}%` : '0%';
    document.getElementById('progNoKey').style.width = total ? `${((succ - completed) / total) * 100}%` : '0%';
    document.getElementById('progPending').style.width = total ? `${(pending / total) * 100}%` : '0%';
    document.getElementById('progRunning').style.width = total ? `${(running / total) * 100}%` : '0%';
    document.getElementById('progReview').style.width = total ? `${(review / total) * 100}%` : '0%';
    document.getElementById('progFailed').style.width = total ? `${(failed / total) * 100}%` : '0%';

    // Proxy & rotation summary
    const p = data.proxy_summary;
    const poolCfg = data.settings.proxy_pool || {};
    const every = poolCfg.rotate_every || 1;
    const np = p.active_proxy || p.next_proxy;
    if (p.total === 0) {
      document.getElementById('statProxySummary').textContent = '直连 (0 节点)';
      document.getElementById('topIpCapsuleText').textContent = '本机直连 (无代理池)';
      document.getElementById('activeProxyNodeTitle').textContent = '本机直连 (未导入代理)';
      document.getElementById('activeProxyServerSub').textContent = '前往下方粘贴导入代理即可启用自动换 IP';
      document.getElementById('activeProxyProgressBar').style.width = '0%';
    } else {
      const rotation = rotationProgress(np, poolCfg);
      const ipText = np ? (np.last_ip || np.server) : '无可用健康代理';
      document.getElementById('statProxySummary').textContent = `${p.healthy}/${p.total} 可用`;
      document.getElementById('topIpCapsuleText').textContent = np
        ? `${np.id} (${ipText}) · ${rotation.label}`
        : `代理池 0/${p.total} 可用`;
      if (np) {
        document.getElementById('activeProxyNodeTitle').textContent = `${np.id} ${np.last_ip ? ('[' + np.last_ip + ']') : ''}`;
        document.getElementById('activeProxyServerSub').textContent = `地址: ${np.server} · 当前第 ${np.generation} 轮`;
        document.getElementById('activeProxyWindowLabel').textContent = `本轮进度：${rotation.label}`;
        document.getElementById('activeProxyCountdownLabel').textContent = rotation.remaining;
        document.getElementById('activeProxyProgressBar').style.width = `${rotation.percent}%`;
      } else {
        document.getElementById('activeProxyNodeTitle').textContent = '没有可用健康节点';
        document.getElementById('activeProxyServerSub').textContent = '请启用节点或先检测连通性';
        document.getElementById('activeProxyProgressBar').style.width = '0%';
      }
    }
    const modeLabel = poolCfg.rotate_mode === 'execution_count'
      ? `每执行 ${every} 次流程换 IP`
      : (poolCfg.rotate_mode === 'both'
          ? `每达成 ${every} 次结果或执行 ${poolCfg.rotate_executions_limit} 次换 IP`
          : `每达成 ${every} 次目标结果换 IP`);
    document.getElementById('statProxyRotation').textContent = modeLabel;

    // Runner status
    const pill = document.getElementById('runnerStatusPill');
    const rText = document.getElementById('runnerStatusText');
    if (data.runner.running) {
      const active = data.batches.find(b => b.id === data.runner.active_batch);
      const paused = active && active.action === 'PAUSED';
      pill.className = paused ? 'status-pill idle' : 'status-pill running';
      rText.textContent = `${paused ? '已暂停' : (active && active.action === 'STOPPING' ? '正在停止' : '运行中')}: ${data.runner.active_batch}`;
    } else {
      pill.className = 'status-pill idle';
      rText.textContent = '空闲待命';
    }
    document.getElementById('runnerSlots').textContent = `运行槽位 ${(data.runner.slots || []).length}/${data.settings.concurrency} · ` + (data.runner.slots || []).map(j => `${j.user_id}: ${j.phase}`).join(' · ');
    renderLogs(data.runner);

    // Batch select
    const sel = document.getElementById('batchSelect');
    const prevBatch = sel.value;
    sel.innerHTML = '<option value="">全部批次汇总</option>';
    data.batches.forEach(b => {
      const opt = document.createElement('option');
      opt.value = b.id;
      opt.textContent = `${b.id} [${b.action}] (${b.total}条)` + (b.pause_reason ? ` - ${b.pause_reason}` : '');
      sel.appendChild(opt);
    });
    if (prevBatch && data.batches.some(b => b.id === prevBatch)) {
      sel.value = prevBatch;
    }

    renderProxiesTable(data.proxies, poolCfg);

    if (populateForm || !STATE.configLoaded) {
      populateSettingsForm(data.settings);
      STATE.configLoaded = true;
      runRegexTester();
    }
  } catch (err) {
    showToast(err.message, true);
  }
}

function selectImportMode(mode) {
  document.getElementById('importMode').value = mode;
  document.getElementById('modeCardRegister').classList.toggle('selected', mode === 'register');
  document.getElementById('modeCardExisting').classList.toggle('selected', mode === 'existing_login');
  updateImportPreview();
}

function selectVerifyMode(mode) {
  document.getElementById('cfgVerifyMode').value = mode;
  document.getElementById('vCardAuto').classList.toggle('selected', mode === 'auto_mailbox');
  document.getElementById('vCardManual').classList.toggle('selected', mode === 'manual');
  document.getElementById('vCardNone').classList.toggle('selected', mode === 'none');
  if (mode === 'manual') document.getElementById('cfgHeadless').value = 'false';
}

function selectLoginVerifyMode(mode) {
  document.getElementById('cfgLoginVerifyMode').value = mode;
  document.getElementById('lCardStrict').classList.toggle('selected', mode === 'strict_identity');
  document.getElementById('lCardSelector').classList.toggle('selected', mode === 'selector_only');
  document.getElementById('lCardToken').classList.toggle('selected', mode === 'url_or_token');
  document.getElementById('importLoginVerifyMode').value=mode;
}

function selectProxyRotateMode(mode) {
  document.getElementById('cfgProxyRotateMode').value = mode;
  document.getElementById('pModeResult').classList.toggle('selected', mode === 'result_reached');
  document.getElementById('pModeExec').classList.toggle('selected', mode === 'execution_count');
  document.getElementById('pModeBoth').classList.toggle('selected', mode === 'both');
}

function populateSettingsForm(cfg) {
  document.getElementById('cfgBaseUrl').value = cfg.base_url || '';
  document.getElementById('cfgMode').value = cfg.mode || 'agnes';
  document.getElementById('cfgHeadless').value = String(Boolean(cfg.headless));
  document.getElementById('cfgConcurrency').value = cfg.concurrency || 1;
  document.getElementById('cfgPerMinute').value = cfg.per_minute || 1;
  document.getElementById('cfgMaxAttempts').value = cfg.max_attempts || 3;
  document.getElementById('cfgVerifyTimeout').value = cfg.verification_timeout_seconds || 90;

  const v = cfg.verification || {};
  selectVerifyMode(cfg.manual_verification ? 'manual' : (v.mode || 'auto_mailbox'));
  document.getElementById('cfgSenderDomain').value = v.sender_domain ?? 'agnes-ai.com';
  document.getElementById('cfgCodePattern').value = v.code_pattern || '(?<!\\d)\\d{6}(?!\\d)';
  document.getElementById('cfgImapHost').value = v.imap_host || 'outlook.office365.com';

  document.getElementById('cfgIdentityNav').value = cfg.identity_navigation_selector || '';
  document.getElementById('cfgAuthSelector').value = cfg.authenticated_selector || '';
  document.getElementById('cfgAccountIdentitySelector').value = cfg.account_identity_selector || '';

  const reg = cfg.registration_flow || {};
  document.getElementById('regEntryPath').value = reg.entry_path || '/login';
  document.getElementById('regOpenSelector').value = reg.open_register_selector || '';
  document.getElementById('regEmailSelector').value = reg.email_selector || '';
  document.getElementById('regPasswordSelector').value = reg.password_selector || '';
  document.getElementById('regConfirmSelector').value = reg.confirm_password_selector || '';
  document.getElementById('regSendReadySelector').value = reg.send_code_ready_selector || '';
  document.getElementById('regSendClickSelector').value = reg.send_code_click_selector || '';
  document.getElementById('regCodeInputSelector').value = reg.code_input_selector || '';
  document.getElementById('regSubmitSelector').value = reg.submit_button_selector || '';
  STATE.regSteps = (reg.custom_steps || []).map(s => Object.assign({}, s));
  renderCustomSteps('reg');

  const lf = cfg.login_flow || {};
  selectLoginVerifyMode(lf.verify_mode || 'strict_identity');
  document.getElementById('loginPath').value = lf.login_path || '/login';
  document.getElementById('loginEmailSelector').value = lf.email_selector || '';
  document.getElementById('loginPasswordSelector').value = lf.password_selector || '';
  document.getElementById('loginSubmitSelector').value = lf.submit_selector || '';
  document.getElementById('loginApiPath').value = lf.login_api_path ?? '/api/user/login';
  document.getElementById('loginPostPath').value = lf.post_login_path ?? '/settings/apiKeys';
  document.getElementById('loginTokenKey').value = lf.token_storage_key || 'token';
  STATE.loginSteps = (lf.custom_steps || []).map(s => ({...s}));
  renderCustomSteps('login');

  const kf = cfg.key_flow || {};
  document.getElementById('keyFlowEnabled').checked = Boolean(kf.enabled);
  document.getElementById('keyFlowRequireKey').checked = kf.require_key !== false;
  document.getElementById('keyExtractMode').value = kf.extract_mode || 'auto';
  document.getElementById('keyPattern').value = kf.pattern || 'sk-[A-Za-z0-9_-]{16,}';
  document.getElementById('keyNavSelector').value = kf.navigation_selector || '';
  document.getElementById('keyTargetUrl').value = kf.target_url || '';
  document.getElementById('keyCreateSelector').value = kf.create_selector || '';
  document.getElementById('keyNameSelector').value = kf.name_selector || '';
  document.getElementById('keyNameTemplate').value = kf.name_template || 'Agnes Provisioner {user_id}';
  document.getElementById('keyConfirmSelector').value = kf.confirm_selector || '';
  document.getElementById('keyValueSelector').value = kf.value_selector || '';
  document.getElementById('keyCopySelector').value = kf.copy_selector || '';
  document.getElementById('keyStorageKey').value = kf.storage_key || '';
  STATE.keySteps = (kf.custom_steps || []).map(s => Object.assign({}, s));
  renderCustomSteps('key');

  const pp = cfg.proxy_pool || {};
  document.getElementById('cfgProxyRequired').checked = Boolean(cfg.proxy_required);
  selectProxyRotateMode(pp.rotate_mode || 'result_reached');
  document.getElementById('cfgProxyRotateEvery').value = pp.rotate_every || 1;
  document.getElementById('cfgProxyExecLimit').value = pp.rotate_executions_limit || 3;
  document.getElementById('cfgAutoSwitchIpLimit').checked = pp.auto_switch_on_ip_limit !== false;
  document.getElementById('cfgEnableSessionStickiness').checked = Boolean(pp.enable_session_stickiness);
  document.getElementById('cfgSessionSuffix').value = pp.session_suffix_template || '-session-{session}-time-30';
  syncSelectorHelpers();
}

/* Smart Selector Helpers & Regex Tester (ISS-002) */
function applySmartSelector(selEl, targetInputId, defaultText) {
  const mode = selEl.value;
  const input = document.getElementById(targetInputId);
  if (mode === 'default') input.value = '';
  else if (mode === 'none') input.value = 'none';
  else if (mode === 'text') {
    const txt = prompt('请输入页面上该按钮或链接显示的文字：', defaultText);
    if (txt) input.value = `text="${txt.trim()}"`;
  }
  selEl.value = '';
}

function promptPlaceholder(targetInputId, defaultHint) {
  const txt = prompt('请输入该输入框里的灰色提示文字 (Placeholder)：', defaultHint);
  if (txt) {
    document.getElementById(targetInputId).value = `input[placeholder*="${txt.trim()}"]`;
  }
}

function promptTextSelector(targetInputId, defaultText) {
  const txt = prompt('请输入按钮上的文字：', defaultText);
  if (txt) {
    document.getElementById(targetInputId).value = `button:has-text("${txt.trim()}")`;
  }
}

function setKeyPattern(pat) {
  document.getElementById('keyPattern').value = pat;
  runRegexTester();
}

function runRegexTester() {
  const pat = document.getElementById('keyPattern').value.trim();
  const sample = document.getElementById('regexSampleInput').value;
  const out = document.getElementById('regexTestResult');
  if (!pat) {
    out.style.color = 'var(--warning)';
    out.textContent = '⚠️ 请输入正则表达式';
    return;
  }
  try {
    const re = new RegExp(pat);
    if(re.test('')) {out.style.color='var(--danger)';out.textContent='❌ 正则不能匹配空文本，请改用 .+ 或具体的结果格式。';return;}
    const m = re.exec(sample);
    if (m) {
      out.style.color = 'var(--success)';
      out.innerHTML = `✅ 匹配成功 ➔ <mark>${esc(m[0])}</mark><div style="margin-top:6px;color:var(--text-muted)">${esc(sample.slice(0,m.index))}<mark>${esc(m[0])}</mark>${esc(sample.slice(m.index+m[0].length))}</div>`;
    } else {
      out.style.color = 'var(--danger)';
      out.textContent = '❌ 在示例文本中未匹配到结果';
    }
  } catch (e) {
    out.style.color = 'var(--danger)';
    out.textContent = `❌ 正则语法错误: ${e.message}`;
  }
}

function renderCustomSteps(kind) {
  const list = stepsFor(kind);
  const container = document.getElementById(kind + 'CustomStepsContainer');
  const stageOptions = kind === 'reg'
    ? [
        ['before_open', '打开入口页后'],
        ['before_fill', '点开注册表单后'],
        ['before_code', '填完账密后(发码前)'],
        ['before_submit', '填完验证码后(提交前)'],
        ['after_submit', '点击注册提交后'],
      ]
     : kind === 'login' ? [['before_open','打开登录页后'],['before_fill','填登录账密前'],['before_submit','提交登录前'],['after_submit','完成登录提交后']] : [
        ['before_navigate', '进入结果页前'],
        ['before_extract', '进入结果页后(提取前)'],
        ['after_create', '点击创建确认后'],
        ['extract', '自定义提取结果'],
      ];
  const actionOptions = [
    ['click', '点击元素 (click)'],
    ['check', '勾选复选框 (check)'],
    ['fill', '填写输入框 (fill)'],
    ['wait_selector', '等待元素出现 (wait)'],
    ['wait_ms', '等待毫秒数 (wait_ms)'],
    ['goto', '跳转网址 (goto)'],
    ['press', '键盘按键 (press)'],
    ['extract_text', '提取元素文本为结果'],
    ['extract_storage', '提取LocalStorage为结果'],
    ['evaluate_js', '执行JS表达式'],
  ];

  const stepHtml = (step, idx) => `
    <div class="step-box ${step.enabled === false ? 'disabled-step' : ''}" data-step-index="${idx}">
      <select aria-label="执行位置" onchange="updateStep('${kind}', ${idx}, 'stage', this.value); renderCustomSteps('${kind}')">
        ${stageOptions.map(([v, l]) => `<option value="${v}" ${step.stage === v ? 'selected' : ''}>${l}</option>`).join('')}
      </select>
      <select aria-label="动作类型" onchange="updateStep('${kind}', ${idx}, 'action', this.value)">
        ${actionOptions.map(([v, l]) => `<option value="${v}" ${step.action === v ? 'selected' : ''}>${l}</option>`).join('')}
      </select>
      <input type="text" aria-label="动作选择器" class="mono" placeholder="元素选择器 (如 #agree)" value="${esc(step.selector)}" oninput="updateStep('${kind}', ${idx}, 'selector', this.value)" />
      <input type="text" aria-label="动作值" class="mono" placeholder="值 / 网址 / 毫秒数 (支持 {email} {user_id})" value="${esc(step.value)}" oninput="updateStep('${kind}', ${idx}, 'value', this.value)" />
      <label class="checkbox-row"><input type="checkbox" aria-label="启用步骤" ${step.enabled !== false ? 'checked' : ''} onchange="updateStep('${kind}', ${idx}, 'enabled', this.checked);renderCustomSteps('${kind}')" />启用步骤</label>
      <label class="checkbox-row" style="font-size:12px;">
        <input type="checkbox" ${step.optional !== false ? 'checked' : ''} onchange="updateStep('${kind}', ${idx}, 'optional', this.checked)" />
        可选
      </label>
      <div class="btn-row">
        <button class="btn btn-secondary btn-sm" onclick="moveCustomStep('${kind}', ${idx}, -1)" ${!list.slice(0,idx).some(s=>s.stage===step.stage) ? 'disabled' : ''} title="在本阶段上移">↑</button>
        <button class="btn btn-secondary btn-sm" onclick="moveCustomStep('${kind}', ${idx}, 1)" ${!list.slice(idx+1).some(s=>s.stage===step.stage) ? 'disabled' : ''} title="在本阶段下移">↓</button>
      </div>
      <button class="btn btn-danger btn-sm" onclick="removeCustomStep('${kind}', ${idx})">删除</button>
    </div>`;
  const zones = document.querySelectorAll(`[data-custom-kind="${kind}"]`);
  if (zones.length) {
    zones.forEach(zone => {
      zone.innerHTML = list.map((step, idx) => step.stage === zone.dataset.customStage ? stepHtml(step, idx) : '').join('');
    });
    container.innerHTML = list.map((step, idx) => !Array.from(zones).some(z=>z.dataset.customStage===step.stage) ? stepHtml(step,idx) : '').join('');
  } else container.innerHTML = list.map(stepHtml).join('');
}

function stepsFor(kind) { return kind === 'reg' ? STATE.regSteps : (kind === 'login' ? STATE.loginSteps : STATE.keySteps); }

function addCustomStep(kind, stage) {
  const list = stepsFor(kind);
  list.push({
    stage: stage || (kind === 'reg' ? 'before_code' : (kind === 'login' ? 'before_submit' : 'before_extract')),
    action: 'click',
    selector: '',
    value: '',
    optional: true,
    enabled: true,
    note: '',
  });
  renderCustomSteps(kind);
}

function moveCustomStep(kind, idx, dir) {
  const list = stepsFor(kind);
  let target = idx + dir;
  while(target>=0 && target<list.length && list[target].stage!==list[idx].stage) target+=dir;
  if (target < 0 || target >= list.length) return;
  const tmp = list[idx];
  list[idx] = list[target];
  list[target] = tmp;
  renderCustomSteps(kind);
}

function updateStep(kind, idx, field, val) {
  const list = stepsFor(kind);
  if (list[idx]) list[idx][field] = val;
}

function removeCustomStep(kind, idx) {
  const list = stepsFor(kind);
  list.splice(idx, 1);
  renderCustomSteps(kind);
}

/* Live Parse Preview for Account Import (ISS-003) */
function splitAccountLineClient(line, delimiter) {
  if (delimiter && delimiter !== 'auto') {
    const sep = delimiter === '\\t' ? '\t' : delimiter;
    return line.split(sep).map(s => s.trim());
  }
  for (const cand of ['----', '\t', '|', ';', ',', ':']) {
    if (line.includes(cand)) return line.split(cand).map(s => s.trim());
  }
  return [line.trim()];
}

function updateImportPreview() {
  const raw = (document.getElementById('importAccountsText').value || '').replace(/^\uFEFF/,'');
  const delimiter = document.getElementById('importDelimiter').value;
  const pwdRole = document.getElementById('importPasswordRole').value;
  const format = document.getElementById('importFormat').value;
  const tbody = document.getElementById('importPreviewBody');
  const summaryBadge = document.getElementById('importPreviewSummary');
  const rows = [];
  let validCount = 0;
  let errorCount = 0;
  let records = [];
  try {
    const first = raw.split(/\r?\n/).find(l=>l.trim()) || '';
    const csv = format === 'csv' || (format === 'auto' && first.split(',').map(s=>s.trim().replace(/^"|"$/g,'')).includes('email'));
    if (csv) {
      const parsed = parseCSV(raw);
      while(parsed.length && !parsed[0].values.some(x=>x.trim())) parsed.shift();
      const fields = (parsed.shift()?.values || []).map(x=>x.trim());
      const allowed = ['user_id','email','consent','consent_reference','display_name','mailbox_authorized','secret_ref','mailbox_password','agnes_password','password','client_id','refresh_token'];
      if (!fields.includes('email') || new Set(fields).size !== fields.length || fields.some(f=>!allowed.includes(f))) throw new Error('CSV 需要唯一的 email 列；请检查是否有重复或未知列名。');
      records = parsed.filter(r=>r.values.some(Boolean)).map(r=>({lineNo:r.lineNo,data:Object.fromEntries(fields.map((f,i)=>[f,(r.values[i]||'').trim()])),error:r.values.length===fields.length?'':'CSV 列数与表头不一致',csv:true}));
    } else {
      raw.split(/\r?\n/).forEach((line,i)=>{
        line=line.trim();
        if (line && !line.startsWith('#') && !['email','卡密导出'].includes(line)) records.push({lineNo:i+1,parts:splitAccountLineClient(line,delimiter)});
      });
    }
    records.forEach(record=>{
      const parts=record.parts || [], count=parts.length, data=record.data || {};
      let error=record.error || '', mbPwd=data.mailbox_password||'', agPwd=data.agnes_password||'', cid=data.client_id||'', token=data.refresh_token||'';
      const email=record.csv ? data.email||'' : parts[0]||'';
      const kind=record.csv?'CSV':({1:'纯邮箱',2:'两段式账密',3:'三段式双密码',4:'四段式OAuth',5:'五段式全凭证'}[count]||'格式错误');
      const expected={four_part:4,three_part:3,two_part:2,email_only:1}[format];
      if (!record.csv && (count>5 || (expected && expected!==count))) error='字段数量与所选格式不一致（支持 1 至 5 段）';
      if (count===3) [mbPwd,agPwd]=parts.slice(1);
      if (count===4) [mbPwd,cid,token]=parts.slice(1);
      if (count===5) [mbPwd,agPwd,cid,token]=parts.slice(1);
      const pwd=record.csv?data.password:(count===2?parts[1]:'');
      if (pwd && pwdRole!=='agnes_only') mbPwd=mbPwd||pwd;
      if (pwd && pwdRole!=='mailbox_only') agPwd=agPwd||pwd;
      if (Boolean(cid)!==Boolean(token)||(!record.csv&&[4,5].includes(count)&&(!cid||!token))) error='OAuth ClientID 与 RefreshToken 需要同时提供';
      if (record.csv && data.consent && !['true','1','yes'].includes(data.consent.toLowerCase())) error='缺少用户开户授权';
      if (!/^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/.test(email)) error='未识别到有效邮箱地址';
      if (error) errorCount++; else validCount++;
      rows.push({...record,email,kind,mbPwd,agPwd,cid,token,error,ok:!error});
    });
  } catch (err) { errorCount++; rows.push({lineNo:1,ok:false,error:err.message,kind:'CSV格式错误'}); }

  summaryBadge.textContent = `共识别 ${rows.length} 行 · ✅ 有效 ${validCount} 条 · ❌ 异常 ${errorCount} 条`;
  summaryBadge.className = 'badge ' + (errorCount > 0 ? 'badge-danger' : (validCount > 0 ? 'badge-success' : 'badge-muted'));
  STATE.importPreview = {validCount,errorCount};
  document.getElementById('importSubmit').disabled = !validCount || errorCount > 0;

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted);">在上方粘贴账号后，此处将实时展示每一行的分列结果</td></tr>';
    return;
  }

  tbody.innerHTML = rows.slice(0, 20).map(r => `
    <tr style="${r.ok ? '' : 'background: var(--danger-soft);'}">
      <td class="mono">#${r.lineNo}</td>
      <td>${r.ok ? '<span class="badge badge-success">有效</span>' : `<span class="badge badge-danger">第 ${r.lineNo} 行：${esc(r.error)}</span>`}</td>
      <td><span class="badge badge-muted">${esc(r.kind)}</span></td>
      <td class="mono">${esc(r.email)}</td>
      <td class="mono">${r.mbPwd ? '••••••（已识别）' : '—'}</td>
      <td class="mono">${r.agPwd ? '••••••（已识别）' : (document.getElementById('importMode').value==='existing_login' ? '使用本地已保存密码' : '自动生成强密码')}</td>
      <td class="mono">${esc(r.cid || '—')}</td>
      <td class="mono">${r.token ? '••••••（已识别）' : '—'}</td>
    </tr>
  `).join('');
}

function parseCSV(text) {
  const rows=[]; let values=[], field='', quoted=false, lineNo=1, start=1;
  for(let i=0;i<text.length;i++) {
    const c=text[i];
    if(c==='"') {
      if(quoted && text[i+1]==='"') {field+='"';i++;} else quoted=!quoted;
    } else if(c===',' && !quoted) {values.push(field);field='';}
    else if(c==='\n') {
      if(quoted) field+='\n'; else {values.push(field.replace(/\r$/,''));rows.push({lineNo:start,values});values=[];field='';start=lineNo+1;}
      lineNo++;
    } else field+=c;
  }
  if(quoted) throw new Error(`CSV 第 ${start} 行引号未闭合`);
  if(field || values.length) {values.push(field.replace(/\r$/,''));rows.push({lineNo:start,values});}
  return rows;
}

/* Live Proxy Import Preview (ISS-004) */
function updateProxyPreview() {
  const raw = document.getElementById('importProxiesText').value || '';
  const tbody = document.getElementById('proxyPreviewBody');
  const badge = document.getElementById('proxyPreviewCount');
  const lines = raw.split(/\r?\n/).map(s => s.trim()).filter(s => s && !s.startsWith('#'));
  let valid=0;
  if (!lines.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">粘贴代理后自动预览解析结果</td></tr>';
    badge.textContent='0 条';return;
  }
  tbody.innerHTML = lines.slice(0, 20).map((line, idx) => {
    const parsed = parseProxyPreview(line);
    if(parsed.ok) valid++;
    return `
      <tr style="${parsed.ok ? '' : 'background:var(--danger-soft)'}">
        <td class="mono">#${idx + 1}</td>
        <td class="mono">${esc(parsed.server || '格式错误')}</td>
        <td>${parsed.hasAuth ? '<span class="badge badge-success">含账密（已隐藏）</span>' : '<span class="badge badge-muted">免密</span>'}</td>
        <td>${!parsed.ok ? `<span class="badge badge-danger">${esc(parsed.error)}</span>` : (parsed.hasSession ? '<span class="badge badge-pending">动态Session换IP</span>' : '<span class="badge badge-muted">标准节点</span>')}</td>
      </tr>
    `;
  }).join('');
  const all=lines.map(parseProxyPreview);STATE.proxyPreviewValid=all.every(p=>p.ok);
  badge.textContent=`${lines.length} 条 · 有效 ${all.filter(p=>p.ok).length}`;
}

function parseProxyPreview(line) {
  try {
    let value=line.includes('|')?line.split('|').slice(1).join('|'):line;
    if(!value.includes('://')) {
      const p=value.split(value.includes('----')?'----':':');
      value=p.length>=4?`http://${encodeURIComponent(p[2])}:${encodeURIComponent(p.slice(3).join(':'))}@${p[0]}:${p[1]}`:`http://${value}`;
    }
    const u=new URL(value), hasAuth=Boolean(u.username||u.password);
    const explicitPort=value.match(/:(\d+)(?:\/)?$/)?.[1];
    const port=u.port||explicitPort;
    if(!['http:','https:','socks5:'].includes(u.protocol)||!u.hostname||!port) throw new Error('需要 http/https/socks5 主机与有效端口');
    if(u.protocol==='socks5:'&&hasAuth) throw new Error('Chromium 不支持带账密的 SOCKS5');
    if(u.pathname!=='/'||u.search||u.hash) throw new Error('代理地址不能包含路径或查询参数');
    return {ok:true,server:`${u.protocol}//${u.hostname}:${port}`,hasAuth,hasSession:line.includes('{session}')||document.getElementById('proxySessionMode').value==='true'};
  } catch(err) {return {ok:false,error:err.message};}
}

async function saveAllConfig() {
  try {
    const verifyMode = document.getElementById('cfgVerifyMode').value;
    const payload = {
      base_url: document.getElementById('cfgBaseUrl').value.trim(),
      mode: document.getElementById('cfgMode').value,
      headless: document.getElementById('cfgHeadless').value === 'true',
      concurrency: Number(document.getElementById('cfgConcurrency').value) || 1,
      per_minute: Number(document.getElementById('cfgPerMinute').value) || 1,
      max_attempts: Number(document.getElementById('cfgMaxAttempts').value) || 3,
      verification_timeout_seconds: Number(document.getElementById('cfgVerifyTimeout').value) || 90,
      manual_verification: verifyMode === 'manual',
      identity_navigation_selector: document.getElementById('cfgIdentityNav').value.trim(),
      authenticated_selector: document.getElementById('cfgAuthSelector').value.trim(),
      account_identity_selector: document.getElementById('cfgAccountIdentitySelector').value.trim(),
      proxy_required: document.getElementById('cfgProxyRequired').checked,
      verification: {
        mode: verifyMode,
        sender_domain: document.getElementById('cfgSenderDomain').value.trim(),
        code_pattern: document.getElementById('cfgCodePattern').value.trim() || '(?<!\\d)\\d{6}(?!\\d)',
        imap_host: document.getElementById('cfgImapHost').value.trim() || 'outlook.office365.com',
      },
      registration_flow: {
        entry_path: document.getElementById('regEntryPath').value.trim() || '/login',
        open_register_selector: document.getElementById('regOpenSelector').value.trim(),
        email_selector: document.getElementById('regEmailSelector').value.trim(),
        password_selector: document.getElementById('regPasswordSelector').value.trim(),
        confirm_password_selector: document.getElementById('regConfirmSelector').value.trim(),
        send_code_ready_selector: document.getElementById('regSendReadySelector').value.trim(),
        send_code_click_selector: document.getElementById('regSendClickSelector').value.trim(),
        code_input_selector: document.getElementById('regCodeInputSelector').value.trim(),
        submit_button_selector: document.getElementById('regSubmitSelector').value.trim(),
        custom_steps: STATE.regSteps,
      },
      login_flow: {
        verify_mode: document.getElementById('cfgLoginVerifyMode').value,
        login_path: document.getElementById('loginPath').value.trim() || '/login',
        email_selector: document.getElementById('loginEmailSelector').value.trim(),
        password_selector: document.getElementById('loginPasswordSelector').value.trim(),
        submit_selector: document.getElementById('loginSubmitSelector').value.trim(),
        login_api_path: document.getElementById('loginApiPath').value.trim(),
        post_login_path: document.getElementById('loginPostPath').value.trim(),
        token_storage_key: document.getElementById('loginTokenKey').value.trim(),
        custom_steps: STATE.loginSteps,
      },
      key_flow: {
        enabled: document.getElementById('keyFlowEnabled').checked,
        require_key: document.getElementById('keyFlowRequireKey').checked,
        extract_mode: document.getElementById('keyExtractMode').value,
        pattern: document.getElementById('keyPattern').value.trim() || 'sk-[A-Za-z0-9_-]{16,}',
        navigation_selector: document.getElementById('keyNavSelector').value.trim(),
        target_url: document.getElementById('keyTargetUrl').value.trim(),
        create_selector: document.getElementById('keyCreateSelector').value.trim(),
        name_selector: document.getElementById('keyNameSelector').value.trim(),
        name_template: document.getElementById('keyNameTemplate').value.trim() || 'Agnes Provisioner {user_id}',
        confirm_selector: document.getElementById('keyConfirmSelector').value.trim(),
        value_selector: document.getElementById('keyValueSelector').value.trim(),
        copy_selector: document.getElementById('keyCopySelector').value.trim(),
        storage_key: document.getElementById('keyStorageKey').value.trim(),
        custom_steps: STATE.keySteps,
      },
      proxy_pool: {
        rotate_mode: document.getElementById('cfgProxyRotateMode').value,
        rotate_every: Number(document.getElementById('cfgProxyRotateEvery').value) || 1,
        rotate_executions_limit: Number(document.getElementById('cfgProxyExecLimit').value) || 3,
        auto_switch_on_ip_limit: document.getElementById('cfgAutoSwitchIpLimit').checked,
        enable_session_stickiness: document.getElementById('cfgEnableSessionStickiness').checked,
        session_suffix_template: document.getElementById('cfgSessionSuffix').value.trim() || '-session-{session}-time-30',
      },
    };
    await api('/api/config', { method: 'POST', body: JSON.stringify(payload) });
    showToast('✅ 配置已保存，下次启动任务使用新流程。');
    await loadOverview(true);
  } catch (err) {
    showToast(err.message, true);
  }
}

async function resetFlowDefaults() {
  if (!confirm('恢复官方流程会覆盖尚未保存的流程修改，确定恢复吗？')) return;
  try {
    await api('/api/config/reset-defaults', { method: 'POST', body: '{}' });
    showToast('✅ 已恢复 Agnes 官方默认流程！');
    await loadOverview(true);
  } catch (err) {
    showToast(err.message, true);
  }
}

function setStateFilter(st, btn) {
  STATE.stateFilter = st;
  STATE.jobPage=0;
  document.querySelectorAll('#stateFilterPills .filter-pill').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  loadJobs();
}

async function loadJobs() {
  try {
    const batch = document.getElementById('batchSelect').value;
    const reveal = document.getElementById('revealSecretsToggle').checked ? '1' : '0';
    const data = await api(`/api/jobs?batch=${encodeURIComponent(batch)}&reveal_secrets=${reveal}`);
    if (document.getElementById('batchSelect').value !== batch) return;
    STATE.jobs = data.jobs || [];
    if (reveal === '1') STATE.jobs.forEach(j=>STATE.secrets.set(j.job_id,j));
    else await Promise.all(Array.from(STATE.revealedRows).map(async id=>{
      const result=await api(`/api/jobs?job_id=${encodeURIComponent(id)}&reveal_secrets=1`);
      if(result.jobs[0]) STATE.secrets.set(id,result.jobs[0]);
    }));
    const available = new Set(STATE.jobs.map(j=>j.job_id));
    STATE.selected.forEach(id=>{if(!available.has(id)) STATE.selected.delete(id);});
    renderJobsTable();
    updateFloatingBulkBar();
  } catch (err) {
    showToast(err.message, true);
  }
}

function renderJobsTable() {
  const tbody = document.getElementById('jobsTableBody');
  const q = (document.getElementById('jobSearchInput').value || '').trim().toLowerCase();
  const filtered = STATE.jobs.filter(j => {
    if (STATE.stateFilter && j.state !== STATE.stateFilter) return false;
    if (!q) return true;
    if (STATE.searchMatches) return STATE.searchMatches.has(j.job_id);
    return (j.email || '').toLowerCase().includes(q)
      || (j.user_id || '').toLowerCase().includes(q)
      || (j.error_code || '').toLowerCase().includes(q)
      || (j.message || '').toLowerCase().includes(q);
  });

  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color: var(--text-muted); padding: 26px;">当前筛选下暂无账号记录（可点击左侧“2. 批量导号与核验”导入账号）</td></tr>';
    document.getElementById('jobsPagination').textContent='没有匹配的任务';updateFloatingBulkBar();return;
  }

  const size=100,pages=Math.ceil(filtered.length/size);
  STATE.jobPage=Math.min(STATE.jobPage,pages-1);
  document.getElementById('jobsPagination').innerHTML=`<span>匹配 ${filtered.length} 条 · 第 ${STATE.jobPage+1}/${pages} 页（每页 ${size} 条）</span><button class="btn btn-secondary btn-sm" onclick="STATE.jobPage--;renderJobsTable()" ${STATE.jobPage===0?'disabled':''}>上一页</button><button class="btn btn-secondary btn-sm" onclick="STATE.jobPage++;renderJobsTable()" ${STATE.jobPage>=pages-1?'disabled':''}>下一页</button>`;
  tbody.innerHTML = filtered.slice(STATE.jobPage*size, (STATE.jobPage+1)*size).map(j => {
    const show = document.getElementById('revealSecretsToggle').checked || STATE.revealedRows.has(j.job_id);
    const secret = STATE.secrets.get(j.job_id) || j;
    return `
    <tr data-job-id="${esc(j.job_id)}" class="${STATE.selected.has(j.job_id)?'selected-row':''}">
      <td><input type="checkbox" aria-label="选择 ${esc(j.user_id)}" class="job-check" value="${esc(j.job_id)}" ${STATE.selected.has(j.job_id)?'checked':''} onchange="selectJob(this)" /></td>
      <td class="mono">
        <div style="display:flex; align-items:center; gap:6px;">
          <span>${esc(show ? secret.email : j.email)}</span>
          <button class="copy-chip" data-copy="email" aria-label="复制邮箱">📋</button>
        </div>
        <div style="font-size:11px; color:var(--text-muted);">${esc(j.user_id)} · ${esc(j.batch)}</div>
      </td>
      <td>${stateBadge(j.state, j.state_label)}</td>
      <td class="mono" style="font-size:12px;">${esc(j.phase)} (尝试:${j.attempts})</td>
      <td class="mono secret-cell">
        <button class="copy-chip" data-copy="agnes_password" aria-label="复制平台密码">${show ? esc(secret.agnes_password || '未设置') : '••••••'} 📋</button>
      </td>
      <td class="mono secret-cell">
        ${j.has_key ? `<button class="copy-chip" data-copy="api_key" aria-label="复制最终结果">${show ? esc(secret.api_key || '结果已确认') : '••••••（已获取）'} 📋</button>` : '<span style="color:var(--text-muted)">未获取</span>'}
      </td>
      <td class="mono" style="font-size:12px;">${esc(j.proxy_id || '-')}</td>
      <td style="max-width:220px;">
        <div style="font-weight:600; font-size:12px;">${esc(j.error_code || '-')}</div>
        <div style="font-size:11.5px; color:var(--text-muted);">${esc(j.message)}</div>
      </td>
      <td>
        <div class="btn-row">
          <button class="btn btn-primary btn-sm" data-job-action="verify">验证登录</button>
          <button class="btn btn-secondary btn-sm" data-reveal-row>${show ? '隐藏' : '显示'}</button>
          <button class="btn btn-secondary btn-sm" data-details>详情 / 改密</button>
        </div>
      </td>
    </tr>
  `;
  }).join('');
  updateFloatingBulkBar();
}

function onJobSearch() {
  STATE.jobPage=0;STATE.searchMatches=null;renderJobsTable();
  clearTimeout(STATE.searchTimer);
  const q=document.getElementById('jobSearchInput').value.trim(), batch=document.getElementById('batchSelect').value;
  if(!q) return;
  STATE.searchTimer=setTimeout(async()=>{
    try {
      const data=await api(`/api/jobs?batch=${encodeURIComponent(batch)}&search=${encodeURIComponent(q)}`);
      if(document.getElementById('jobSearchInput').value.trim()!==q||document.getElementById('batchSelect').value!==batch) return;
      STATE.searchMatches=new Set(data.jobs.map(j=>j.job_id));renderJobsTable();
    } catch(err){showToast(err.message,true);}
  },150);
}

function toggleSelectAllJobs(master) {
  document.querySelectorAll('.job-check').forEach(cb => { cb.checked = master.checked; if(cb.checked) STATE.selected.add(cb.value); else STATE.selected.delete(cb.value); });
  updateFloatingBulkBar();
}

function getSelectedJobIds() {
  return Array.from(STATE.selected);
}

function selectJob(cb) { if(cb.checked) STATE.selected.add(cb.value); else STATE.selected.delete(cb.value); updateFloatingBulkBar(); }

function updateFloatingBulkBar() {
  const ids = getSelectedJobIds();
  const bar = document.getElementById('floatingBulkBar');
  document.getElementById('selectedCountText').textContent = ids.length;
  bar.style.display = ids.length > 0 ? 'flex' : 'none';
  const boxes = Array.from(document.querySelectorAll('.job-check'));
  const master = document.getElementById('selectAllJobs');
  const checked = boxes.filter(cb=>STATE.selected.has(cb.value)).length;
  master.checked = boxes.length > 0 && checked === boxes.length;
  master.indeterminate = checked > 0 && checked < boxes.length;
}

function clearJobSelection() {
  STATE.selected.clear();
  document.getElementById('selectAllJobs').checked = false;
  document.querySelectorAll('.job-check').forEach(cb => { cb.checked = false; });
  updateFloatingBulkBar();
}

async function batchSelectedAction(action) {
  const ids = getSelectedJobIds();
  if (!ids.length) return;
  if (['delete','requeue'].includes(action) && !confirm(action==='delete' ? `将删除所选 ${ids.length} 个账号的本地任务和加密凭证，不能撤销。确定吗？` : '请确认这些账号尚未创建。重新注册可能产生重复提交，确定重置吗？')) return;
  try {
    if (action === 'verify') {
      const batches = new Set(STATE.jobs.filter(j=>ids.includes(j.job_id)).map(j=>j.batch));
      if (batches.size !== 1) throw new Error('请先选择一个批次，再批量验证该批次的账号。');
      const batch = Array.from(batches)[0];
      await api('/api/batches/control', {
        method: 'POST',
        body: JSON.stringify({ action: 'verify_batch', batch_id: batch, job_ids: ids }),
      });
      showToast(`🔐 已启动 ${ids.length} 个选中账号的批量登录验证！`);
    } else {
      await api('/api/jobs/action', {
        method: 'POST',
        body: JSON.stringify({
          action: action === 'requeue_login' ? 'requeue' : action,
          login_only: action === 'requeue_login',
          job_ids: ids,
          confirmed_not_created: action === 'requeue',
        }),
      });
      showToast(`✅ 已完成 ${ids.length} 个选中账号的批量操作！`);
    }
    clearJobSelection();
    await refreshAll();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function jobAction(jobId, action) {
  if (action === 'requeue' && !confirm('请确认账号尚未创建，确定重置为重新注册吗？')) return;
  try {
    showToast('正在执行操作...');
    const res = await api('/api/jobs/action', {
      method: 'POST',
      body: JSON.stringify({ action, job_id: jobId, confirmed_not_created: action === 'requeue' }),
    });
    showToast(res.message || '✅ 操作完成！');
    await refreshAll();
    if (STATE.activeDrawerJobId === jobId) {
      await openJobDrawer(jobId);
    }
  } catch (err) {
    showToast(err.message, true);
  }
}

/* Right Slide-over Drawer (ISS-001) */
async function openJobDrawer(jobId) {
  const job = STATE.jobs.find(j => j.job_id === jobId);
  if (!job) return;
  STATE.activeDrawerJobId = jobId;
  STATE.drawerReturnFocus = document.activeElement;
  STATE.drawerRevealed = false;
  document.getElementById('drawerEmailTitle').textContent = job.email;
  document.getElementById('drawerSubMeta').textContent = `用户ID: ${job.user_id} · 批次: ${job.batch} · 代理: ${job.proxy_id || '直连'}`;
  document.getElementById('drawerApiKey').value = job.has_key ? '••••••' : '';
  document.getElementById('drawerAgnesPwd').value = '';
  document.getElementById('drawerMailboxPwd').value = '';
  document.getElementById('drawerReveal').textContent = '显示当前凭证';
  ['drawerApiKey','drawerAgnesPwd','drawerMailboxPwd'].forEach(id=>document.getElementById(id).type='password');

  document.getElementById('drawerQuickActions').innerHTML = `
    <button class="btn btn-primary btn-sm" onclick="jobAction('${jobId}', 'verify')">🔐 立即验证此账号登录 & 拿结果</button>
    <button class="btn btn-secondary btn-sm" onclick="jobAction('${jobId}', 'check_mailbox')">📬 测试邮箱收码连接</button>
    <button class="btn btn-secondary btn-sm" onclick="jobAction('${jobId}', 'requeue')">♻️ 重置为重新注册</button>
  `;

  document.getElementById('drawerBackdrop').style.display = 'block';
  document.getElementById('jobDrawer').classList.add('open');
  document.getElementById('jobDrawer').inert = false;
  document.getElementById('jobDrawer').setAttribute('aria-hidden','false');
  document.getElementById('jobDrawer').querySelector('button').focus();

  const timelineBox = document.getElementById('drawerTimelineBox');
  timelineBox.innerHTML = '<div style="color:var(--text-muted); font-size:12.5px;">正在加载事件历史...</div>';
  try {
    const res = await api(`/api/jobs/${encodeURIComponent(jobId)}/events`);
    if (STATE.activeDrawerJobId !== jobId) return;
    if (!res.events || !res.events.length) {
      timelineBox.innerHTML = '<div style="color:var(--text-muted); font-size:12.5px;">暂无事件记录</div>';
    } else {
      timelineBox.innerHTML = res.events.slice().reverse().map(e => {
        const dt = new Date(e.at * 1000).toLocaleString();
        return `
          <div class="timeline-item">
            <div style="font-size:11.5px; color:var(--text-muted);">${dt}</div>
            <div style="font-size:13px; font-weight:700;">${esc(e.from || 'INIT')} ➔ ${esc(e.to)} <span class="badge badge-muted">${esc(e.code)}</span></div>
            <div style="font-size:12px; color:var(--text-secondary); margin-top:2px;">${esc(e.message)}</div>
          </div>
        `;
      }).join('');
    }
  } catch (err) {
    timelineBox.textContent = err.message;
  }
}

function closeJobDrawer() {
  STATE.activeDrawerJobId = null;
  document.getElementById('jobDrawer').classList.remove('open');
  document.getElementById('drawerBackdrop').style.display = 'none';
  document.getElementById('jobDrawer').inert = true;
  document.getElementById('jobDrawer').setAttribute('aria-hidden','true');
  ['drawerApiKey','drawerAgnesPwd','drawerMailboxPwd'].forEach(id=>document.getElementById(id).value='');
  STATE.drawerReturnFocus?.focus();
}

async function saveDrawerPassword() {
  if (!STATE.activeDrawerJobId) return;
  try {
    const res = await api('/api/jobs/action', {
      method: 'POST',
      body: JSON.stringify({
        action: 'set_password',
        job_id: STATE.activeDrawerJobId,
        agnes_password: document.getElementById('drawerAgnesPwd').value,
        mailbox_password: document.getElementById('drawerMailboxPwd').value,
      }),
    });
    showToast(res.message || '✅ 密码已更新！');
    STATE.secrets.delete(STATE.activeDrawerJobId);
    document.getElementById('drawerAgnesPwd').value='';
    document.getElementById('drawerMailboxPwd').value='';
    await loadJobs();
  } catch (err) {
    showToast(err.message, true);
  }
}

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeJobDrawer();
  if (e.key === 'Tab' && STATE.activeDrawerJobId) {
    const controls=Array.from(document.getElementById('jobDrawer').querySelectorAll('button,input')).filter(el=>!el.disabled);
    const first=controls[0], last=controls.at(-1);
    if (e.shiftKey && document.activeElement===first) {e.preventDefault();last.focus();}
    else if(!e.shiftKey && document.activeElement===last) {e.preventDefault();first.focus();}
  }
});

async function onBatchChange() {
  clearJobSelection();
  STATE.jobPage=0;
  STATE.searchMatches=null;
  STATE.secrets.clear();STATE.revealedRows.clear();
  await refreshAll();
}

async function controlBatch(action) {
  try {
    const sel = document.getElementById('batchSelect');
    const targetBatch = sel.value;
    if (!targetBatch) {
      const hasBatches=STATE.overview && STATE.overview.batches.length;
      showToast(hasBatches?'请在顶部选择要操作的批次；汇总视图不会运行所有账号。':'请先前往「2. 批量导号与核验」导入账号并自动创建批次！', true);
      if(!hasBatches) switchTab('import', document.getElementById('nav-import'));
      return;
    }
    const limitVal = document.getElementById('runLimitInput').value.trim();
    const res = await api('/api/batches/control', {
      method: 'POST',
      body: JSON.stringify({
        action,
        batch_id: targetBatch,
        limit: limitVal ? Number(limitVal) : null,
      }),
    });
    showToast(res.message || `✅ 指令已发送: ${action}`);
    await refreshAll();
  } catch (err) {
    showToast(err.message, true);
  }
}

function loadImportFile(input) {
  const file = input.files && input.files[0];
  readImportFile(file);
}

function readImportFile(file) {
  if (!file) return;
  if(!/\.(txt|csv)$/i.test(file.name)) {showToast('请选择 .txt 或 .csv 文件。',true);return;}
  if(file.size>8*1024*1024) {showToast('文件超过 8MB，请拆分后导入。',true);return;}
  const reader = new FileReader();
  reader.onload = () => {
    document.getElementById('importAccountsText').value = reader.result || '';
    updateImportPreview();
    showToast(`📄 已读取文件: ${file.name}`);
  };
  reader.onerror=()=>showToast('文件读取失败，请重新选择。',true);
  reader.readAsText(file, 'utf-8');
}

async function submitImportAccounts() {
  try {
    const text = document.getElementById('importAccountsText').value;
    if (!text.trim()) {
      showToast('请先粘贴或选择要导入的账号数据！', true);
      return;
    }
    updateImportPreview();
    if(STATE.importPreview.errorCount) throw new Error('请先修正预览中的异常行，再导入整批账号。');
    const payload = {
      content: text,
      format_hint: document.getElementById('importFormat').value,
      delimiter: document.getElementById('importDelimiter').value,
      import_mode: document.getElementById('importMode').value,
      password_role: document.getElementById('importPasswordRole').value,
      batch_id: document.getElementById('importBatchId').value.trim() || 'batch-main',
      mailbox_transport: document.getElementById('importMailboxTransport').value,
    };
    const res = await api('/api/accounts/import', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const r = res.report;
    const msg = `导入完成：新增 ${r.imported}，更新 ${r.updated}，重复 ${r.duplicates}，拒绝 ${r.rejected}` + (r.batch ? `，批次【${r.batch.batch}】` : '') + (r.errors.length ? '；'+r.errors.map(e=>`第 ${e.row} 行：${e.reason}`).join('；') : '');
    document.getElementById('importResultBox').textContent = msg;
    showToast(msg);
    await refreshAll();
    if(r.batch && !r.rejected) {
      document.getElementById('batchSelect').value=r.batch.batch;
      document.getElementById('importAccountsText').value='';
      document.getElementById('importFilePicker').value='';
      updateImportPreview();
      await onBatchChange();
      switchTab('dashboard',document.getElementById('nav-dashboard'));
    }
  } catch (err) {
    showToast(err.message, true);
  }
}

function renderProxiesTable(proxies, poolCfg) {
  const tbody = document.getElementById('proxiesTableBody');
  if (!proxies || !proxies.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color: var(--text-muted); padding: 22px;">代理池为空（当前使用本机直连），可在上方批量粘贴导入代理</td></tr>';
    return;
  }
  tbody.innerHTML = proxies.map(p => {
    const statusMap = {
      HEALTHY: 'badge-success',
      UNCHECKED: 'badge-warn',
      UNHEALTHY: 'badge-danger',
      BLOCKED: 'badge-danger',
    };
    const rotation=rotationProgress(p,poolCfg);
    return `
      <tr data-proxy-id="${esc(p.id)}">
        <td class="mono" style="font-weight:700;">${esc(p.id)}</td>
        <td class="mono">${esc(p.server)} ${p.has_auth ? '<span class="badge badge-muted">含账密</span>' : ''}</td>
        <td class="mono" style="color:var(--primary); font-weight:700;">${esc(p.last_ip || '待检测')}<div>${p.latency_ms != null ? esc(p.latency_ms)+' ms' : '未测速'}</div></td>
        <td>
          <span class="badge ${statusMap[p.status] || 'badge-muted'}">${esc(p.status)}</span>
          ${p.leased ? `<span class="badge badge-pending">${p.checking?'检测中':'使用中'}</span>` : ''}
          ${p.binding_preserved ? '<span class="badge badge-warn">保留提交后绑定</span>' : ''}
          ${!p.enabled ? '<span class="badge badge-danger">已停用</span>' : ''}
        </td>
        <td class="mono">第 ${p.generation} 轮</td>
        <td style="min-width:150px;">
          <div style="font-size:11.5px;" class="mono">${esc(rotation.label)}</div>
          <div class="progress-track" style="height:6px; margin:4px 0 0;">
            <div class="progress-seg" style="width:${rotation.percent}%; background:var(--purple);"></div>
          </div>
        </td>
        <td class="mono">成功 ${p.total_results} / 共 ${p.total_executions}</td>
        <td class="mono">${esc(p.session_mode ? p.session_sticky_id : '-')}</td>
        <td>
          <div class="btn-row">
            <button class="btn btn-secondary btn-sm" data-proxy-action="check" ${p.leased||p.binding_preserved?'disabled':''}>测速&查IP</button>
            <button class="btn btn-secondary btn-sm" data-proxy-action="rotate_now" ${p.leased||p.binding_preserved?'disabled':''}>换下一轮</button>
            <button class="btn btn-secondary btn-sm" data-proxy-action="toggle_enable" data-enabled="${!p.enabled}" ${p.leased||p.binding_preserved?'disabled':''}>${p.enabled ? '停用' : '启用'}</button>
            <button class="btn btn-danger btn-sm" data-proxy-action="delete" ${p.leased||p.binding_preserved?'disabled':''}>删除</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

async function submitImportProxies() {
  try {
    const text = document.getElementById('importProxiesText').value;
    if (!text.trim()) {
      showToast('请先粘贴要导入的代理地址！', true);
      return;
    }
    updateProxyPreview();
    if(!STATE.proxyPreviewValid) throw new Error('请先修正代理预览中的格式错误。');
    if(document.getElementById('proxyClearExisting').checked && !confirm('将清空旧代理池再导入，确定替换吗？')) return;
    const payload = {
      content: text,
      initial_status: document.getElementById('proxyInitialStatus').value,
      session_mode: document.getElementById('proxySessionMode').value === 'true',
      clear_existing: document.getElementById('proxyClearExisting').checked,
    };
    const res = await api('/api/proxies/import', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const msg = `✅ 成功导入 ${res.imported} 条代理节点！`;
    document.getElementById('proxyImportMsg').textContent = msg;
    showToast(msg);
    await refreshAll();
    document.getElementById('importProxiesText').value='';updateProxyPreview();
  } catch (err) {
    showToast(err.message, true);
  }
}

async function checkSingleProxy(proxyId) {
  try {
    showToast(`正在检测代理 ${proxyId}...`);
    const res = await api('/api/proxies/check', {
      method: 'POST',
      body: JSON.stringify({ proxy_id: proxyId }),
    });
    const item = res.results[0] || {};
    const lat = item.latency_ms ? ` · ${item.latency_ms}ms` : '';
    showToast(`代理 ${proxyId}: ${item.status} ${item.ip ? ('(出口IP: ' + item.ip + ')') : ''}${lat}`);
    await loadOverview(false);
  } catch (err) {
    showToast(err.message, true);
  }
}

async function checkAllProxies() {
  try {
    showToast('⚡ 正在并发检测所有代理连通性与真实出口 IP...');
    const res = await api('/api/proxies/check', {
      method: 'POST',
      body: JSON.stringify({ proxy_id: 'all' }),
    });
    const healthy = (res.results || []).filter(r => r.status === 'HEALTHY').length;
    showToast(`✅ 检测完成：${healthy} / ${(res.results || []).length} 条代理可用！`);
    await loadOverview(false);
  } catch (err) {
    showToast(err.message, true);
  }
}

async function proxyAction(action, proxyId = null, enabled = true) {
  if(['clear_all','delete','reset_rotation'].includes(action) && !confirm(action==='reset_rotation'?'重置健康状态不代表实际检测通过，确定重置所有代理吗？':'此操作不能撤销，确定删除代理吗？')) return;
  try {
    await api('/api/proxies/action', {
      method: 'POST',
      body: JSON.stringify({ action, proxy_id: proxyId, enabled }),
    });
    showToast('✅ 代理池操作已生效！');
    await loadOverview(false);
  } catch (err) {
    showToast(err.message, true);
  }
}

function exportData(format) {
  const batch = document.getElementById('batchSelect').value;
  const secrets=document.getElementById('exportIncludeSecrets').checked;
  if(secrets&&!confirm('交付文件将包含明文密码和最终结果，请妥善保管，确定导出吗？')) return;
  window.open(`/api/export?format=${encodeURIComponent(format)}&batch=${encodeURIComponent(batch)}&include_secrets=${secrets?'1':'0'}`, '_blank');
}

async function refreshAll() {
  if(STATE.refreshBusy) return;
  STATE.refreshBusy=true;
  try {await loadOverview(false);await loadJobs();} finally {STATE.refreshBusy=false;}
}

async function createBackup() {
  try {const result=await post('/api/backup',{});document.getElementById('backupResult').textContent=result.directory;showToast(result.message);}
  catch(err){showToast(err.message,true);}
}

function rotationProgress(p,cfg={}) {
  const r=p?.window_results||0, x=p?.window_executions||0, every=cfg.rotate_every||1, max=cfg.rotate_executions_limit||3;
  if(cfg.rotate_mode==='execution_count') return {label:`执行 ${x}/${every}`,remaining:`再执行 ${Math.max(0,every-x)} 次切换`,percent:Math.min(100,x/every*100)};
  if(cfg.rotate_mode==='both') return {label:`结果 ${r}/${every} 或执行 ${x}/${max}`,remaining:`再达成 ${Math.max(0,every-r)} 次结果或执行 ${Math.max(0,max-x)} 次切换`,percent:Math.min(100,Math.max(r/every,x/max)*100)};
  return {label:`结果 ${r}/${every}`,remaining:`再达成 ${Math.max(0,every-r)} 次结果切换`,percent:Math.min(100,r/every*100)};
}

function clearLogs() {
  STATE.logCutoff=Date.now()/1000;
  STATE.ignoredLogs=new Set(STATE.overview?.runner.logs || []);
  document.getElementById('runnerLogsBox').textContent='当前日志视图已清空；审计时间线仍保留。';
}

function renderLogs(runner) {
  const lines=(runner.logs||[]).filter(line=>!STATE.ignoredLogs?.has(line));
  const events=(runner.events||[]).filter(e=>e.at>STATE.logCutoff).sort((a,b)=>a.at-b.at).slice(-35);
  events.forEach(e=>lines.push(`[${new Date(e.at*1000).toLocaleTimeString()}] ${e.user_id} · ${e.code} · ${e.message}`));
  const box=document.getElementById('runnerLogsBox'), previous=box.scrollTop;
  box.innerHTML=lines.map(line=>`<div class="${/失败|异常|错误|❌/.test(line)?'log-error':/等待|暂停|重试/.test(line)?'log-warn':/完成|通过|成功/.test(line)?'log-success':''}">${esc(line)}</div>`).join('')||'等待新的执行日志…';
  box.scrollTop=document.getElementById('logAutoScroll').checked?box.scrollHeight:previous;
}

async function getJobSecrets(jobId) {
  if(STATE.secrets.has(jobId)) return STATE.secrets.get(jobId);
  const result=await api(`/api/jobs?job_id=${encodeURIComponent(jobId)}&reveal_secrets=1`);
  const job=result.jobs[0];if(!job) throw new Error('账号已不存在，请刷新后重试。');
  STATE.secrets.set(jobId,job);return job;
}

async function copyJobField(jobId,field) {
  try {const job=await getJobSecrets(jobId);await copyText(job[field],{email:'邮箱',agnes_password:'平台密码',api_key:'最终结果'}[field]||'凭证');}
  catch(err){showToast(err.message,true);}
}

async function onRevealChange() {
  if(!document.getElementById('revealSecretsToggle').checked) {STATE.secrets.clear();STATE.revealedRows.clear();}
  await loadJobs();
}

async function toggleDrawerSecrets() {
  try {
    STATE.drawerRevealed=!STATE.drawerRevealed;
    const job=STATE.drawerRevealed?await getJobSecrets(STATE.activeDrawerJobId):null;
    document.getElementById('drawerApiKey').value=job?.api_key || '';
    ['drawerApiKey','drawerAgnesPwd','drawerMailboxPwd'].forEach(id=>document.getElementById(id).type=STATE.drawerRevealed?'text':'password');
    document.getElementById('drawerReveal').textContent=STATE.drawerRevealed?'隐藏当前凭证':'显示当前凭证';
    if(job) {document.getElementById('drawerAgnesPwd').value=job.agnes_password||'';document.getElementById('drawerMailboxPwd').value=job.mailbox_password||'';}
    else {document.getElementById('drawerAgnesPwd').value='';document.getElementById('drawerMailboxPwd').value='';}
  } catch(err){showToast(err.message,true);}
}

function initSelectorHelpers() {
  const ids=['regOpenSelector','regEmailSelector','regPasswordSelector','regConfirmSelector','regSendReadySelector','regSendClickSelector','regCodeInputSelector','regSubmitSelector','loginEmailSelector','loginPasswordSelector','loginSubmitSelector','cfgIdentityNav','cfgAuthSelector','cfgAccountIdentitySelector','keyNavSelector','keyCreateSelector','keyNameSelector','keyConfirmSelector','keyValueSelector','keyCopySelector'];
  ids.forEach(id=>{
    const input=document.getElementById(id), box=document.createElement('div');
    box.className='smart-selector-control';box.dataset.target=id;
    box.innerHTML='<select aria-label="定位方式"><option value="default">官方默认</option><option value="text">按按钮/链接文字</option><option value="placeholder">按输入框提示词</option><option value="css">高级 CSS / Playwright</option><option value="none">跳过此步</option></select><input type="text" aria-label="定位内容" placeholder="输入按钮文字、提示词或 CSS" />';
    input.closest('.field').appendChild(box);
    const select=box.querySelector('select'), value=box.querySelector('input');
    const update=()=>{input.value=select.value==='none'?'none':select.value==='default'?'':select.value==='text'?'text='+JSON.stringify(value.value):select.value==='placeholder'?'input[placeholder*='+JSON.stringify(value.value)+']':value.value;value.disabled=['none','default'].includes(select.value);};
    select.addEventListener('change',update);value.addEventListener('input',update);
    input.addEventListener('input',()=>{select.value='css';value.disabled=false;value.value=input.value;});
    input.closest('.field').querySelectorAll('button, select:not(.smart-selector-control select)').forEach(el=>{if(!box.contains(el)) el.hidden=true;});
    input.setAttribute('aria-label',input.closest('.field').querySelector('label')?.textContent || id);
  });
}

function syncSelectorHelpers() {
  document.querySelectorAll('.smart-selector-control').forEach(box=>{
    const input=document.getElementById(box.dataset.target), select=box.querySelector('select'), value=box.querySelector('input');
    select.value=input.value==='none'?'none':input.value?'css':'default';
    value.value=input.value==='none'?'':input.value;value.disabled=['none','default'].includes(select.value);
  });
}

function initPipeline() {
  const original=Array.from(document.querySelectorAll('#tab-flows .pipeline'));
  const makeStep=(number,title,fields)=>{
    const step=document.createElement('div');step.className='pipe-step';
    step.innerHTML=`<div class="pipe-head"><div><span class="pipe-num">${number}</span><span class="pipe-title">${title}</span></div><span class="pipe-summary">点击配置 ▾</span></div>`;
    const grid=document.createElement('div');grid.className='grid-3';
    fields.forEach(id=>grid.appendChild(document.getElementById(id).closest('.field')));
    step.appendChild(grid);return step;
  };
  const registration=[
    makeStep(1,'访问注册入口页',['regEntryPath']),
    makeStep(2,'点击切换注册',['regOpenSelector']),
    makeStep(3,'填写邮箱与密码',['regEmailSelector','regPasswordSelector','regConfirmSelector']),
    makeStep(4,'发送并填写验证码',['regSendReadySelector','regSendClickSelector','regCodeInputSelector']),
    makeStep(5,'点击提交注册',['regSubmitSelector']),
  ];
  original[0].replaceChildren(...registration);original[0].dataset.flowKind='reg';
  const extraction=original[1].querySelectorAll('.pipe-step')[1];
  extraction.querySelector('.pipe-num').textContent='9';extraction.querySelector('.pipe-title').textContent='提取并保存最终结果';
  const result=[makeStep(7,'进入最终结果页面',['keyNavSelector','keyTargetUrl']),makeStep(8,'触发创建目标项',['keyCreateSelector','keyNameSelector','keyNameTemplate','keyConfirmSelector']),extraction];
  original[1].replaceChildren(...result);original[1].dataset.flowKind='key';
  const loginGrid=document.getElementById('loginPath').closest('.grid-3');
  const loginPipe=document.createElement('div');loginPipe.className='pipeline';loginPipe.dataset.flowKind='login';
  const loginStep=document.createElement('div');loginStep.className='pipe-step';
  loginStep.innerHTML='<div class="pipe-head"><div><span class="pipe-num">6</span><span class="pipe-title">登录账号与确认身份</span></div><span class="pipe-summary">点击配置 ▾</span></div>';
  loginGrid.before(loginPipe);loginStep.appendChild(loginGrid);loginPipe.appendChild(loginStep);
  const pipelines=Array.from(document.querySelectorAll('#tab-flows .pipeline'));
  pipelines.forEach(pipeline=>{
    const kind=pipeline.dataset.flowKind, stages=kind==='reg'?['before_open','before_fill','before_code','before_submit','after_submit']:kind==='login'?['before_submit']:['before_extract','after_create','extract'];
    Array.from(pipeline.querySelectorAll('.pipe-step')).forEach((step,i)=>{
      step.classList.add('collapsed');
      const head=step.querySelector('.pipe-head');head.tabIndex=0;head.setAttribute('role','button');head.setAttribute('aria-expanded','false');
      const toggle=()=>{step.classList.toggle('collapsed');head.setAttribute('aria-expanded',String(!step.classList.contains('collapsed')));};
      head.addEventListener('click',toggle);head.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggle();}});
      const zone=document.createElement('div');zone.className='insert-zone';
      zone.innerHTML=`<button class="btn btn-secondary btn-sm" onclick="addCustomStep('${kind}','${stages[i]}')">+ 在此插入自定义动作</button><div data-custom-kind="${kind}" data-custom-stage="${stages[i]}"></div>`;
      step.after(zone);
    });
  });
}

window.addEventListener('DOMContentLoaded', async () => {
  const savedTheme=localStorage.getItem('agnes-theme');if(['dark','light'].includes(savedTheme)) document.documentElement.dataset.theme=savedTheme;
  initSelectorHelpers();initPipeline();updateImportPreview();
  const pager=document.createElement('div');pager.id='jobsPagination';pager.className='btn-row';pager.style.marginTop='12px';document.getElementById('jobsTableBody').closest('.table-wrap').after(pager);
  const drop=document.getElementById('importDropZone');
  drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragging');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));
  drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragging');readImportFile(e.dataTransfer.files[0]);});
  document.getElementById('proxySessionMode').addEventListener('change',updateProxyPreview);
  document.getElementById('jobsTableBody').addEventListener('click',async e=>{
    const row=e.target.closest('[data-job-id]');if(!row||e.target.closest('input')) return;
    const id=row.dataset.jobId, button=e.target.closest('button');
    if(!button){openJobDrawer(id);return;}
    if(button.dataset.copy) await copyJobField(id,button.dataset.copy);
    else if(button.hasAttribute('data-reveal-row')) {
      try {if(STATE.revealedRows.has(id)){STATE.revealedRows.delete(id);STATE.secrets.delete(id);}else{await getJobSecrets(id);STATE.revealedRows.add(id);}renderJobsTable();}
      catch(err){showToast(err.message,true);}
    } else if(button.dataset.jobAction) jobAction(id,button.dataset.jobAction);
    else if(button.hasAttribute('data-details')) openJobDrawer(id);
  });
  document.getElementById('proxiesTableBody').addEventListener('click',e=>{
    const button=e.target.closest('[data-proxy-action]'), row=e.target.closest('[data-proxy-id]');if(!button||!row) return;
    if(button.dataset.proxyAction==='check') checkSingleProxy(row.dataset.proxyId);
    else proxyAction(button.dataset.proxyAction,row.dataset.proxyId,button.dataset.enabled==='true');
  });
  await loadOverview(true);
  await loadJobs();
  setInterval(refreshAll, 3000);
});
</script>
</body>
</html>
"""
