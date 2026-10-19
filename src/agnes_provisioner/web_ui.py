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
    color-scheme: dark;
    --bg-canvas: #090a0f;
    --bg-surface: #11131a;
    --bg-elevated: #171a24;
    --bg-terminal: #06070b;
    --border-subtle: rgba(255, 255, 255, 0.07);
    --bg: var(--bg-canvas);
    --bg-sidebar: var(--bg-canvas);
    --bg-input: var(--bg-elevated);
    --border: var(--border-subtle);
    --border-focus: #3b82f6;
    --text: #eceef4;
    --text-secondary: #b6bbca;
    --text-muted: #8d94a6;
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
    color-scheme: light;
    --bg-canvas: #f3f4f6;
    --bg-surface: #ffffff;
    --bg-elevated: #f8fafc;
    --bg-terminal: #06070b;
    --border-subtle: #e5e7eb;
    --bg: var(--bg-canvas);
    --bg-sidebar: var(--bg-canvas);
    --bg-input: var(--bg-elevated);
    --border: var(--border-subtle);
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
  :root { --sidebar-width: 196px; --terminal-height: 34px; }
  [hidden] { display: none !important; }
  html { height: 100%; }
  body {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
    line-height: 1.5;
    display: flex;
    height: 100dvh;
    overflow: hidden;
  }
  button, input, select, textarea { font: inherit; }
  button { touch-action: manipulation; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }

  /* Sidebar */
  .sidebar {
    width: var(--sidebar-width);
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 100;
    padding: 16px 10px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 8px 24px;
  }
  .brand-logo {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    background: var(--bg-elevated);
    color: var(--text);
    font-weight: 700;
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .brand-title {
    font-size: 14px;
    font-weight: 650;
    line-height: 1.25;
  }
  .brand-sub {
    font-size: 10px;
    color: var(--text-muted);
  }
  .nav-list {
    display: flex;
    flex-direction: column;
    gap: 3px;
    flex: 1;
  }
  .nav-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 8px 10px;
    border-radius: 5px;
    border: 0;
    background: transparent;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s;
  }
  .nav-item:hover {
    background: var(--bg-elevated);
    color: var(--text);
  }
  .nav-item.active {
    background: var(--bg-elevated);
    color: var(--text);
    box-shadow: inset 2px 0 var(--primary);
  }
  .nav-badge {
    font-size: 10px;
    color: var(--text-muted);
    font-family: Consolas, monospace;
    flex-shrink: 0;
    white-space: nowrap;
  }
  .sidebar-footer {
    padding-top: 12px;
    border-top: 1px solid var(--border);
    font-size: 10px;
    color: var(--text-muted);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  /* Main Area */
  .main-shell {
    margin-left: var(--sidebar-width);
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    height: 100dvh;
    padding-bottom: var(--terminal-height);
  }

  /* Sticky Topbar */
  .topbar {
    z-index: 90;
    background: var(--bg-sidebar);
    border-bottom: 1px solid var(--border);
    padding: 7px 12px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    min-height: 44px;
    flex-shrink: 0;
  }
  .topbar-left, .topbar-right {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 5px;
    min-width: 0;
  }
  .topbar-left { flex: 1; }
  #batchSelect { width: 150px; font-size: 11px; }
  #runLimitInput { width: 66px; font-size: 11px; }
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 0 4px 0 0;
    font-size: 11px;
    font-weight: 500;
    color: var(--success);
    max-width: 140px;
  }
  #runnerStatusText { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .status-pill.idle {
    color: var(--text-muted);
  }
  .status-dot {
    width: 6px;
    height: 6px;
    flex-shrink: 0;
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
    padding: 4px 6px;
    border: 0;
    background: transparent;
    font-size: 11px;
    color: var(--text-muted);
    cursor: pointer;
    max-width: 155px;
  }
  #topIpCapsuleText { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .content-area {
    padding: 0;
    width: 100%;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg-surface);
  }

  /* One telemetry strip; the queue remains the primary surface. */
  .telemetry-strip { display: flex; position: relative; align-items: center; gap: 24px; min-height: 36px; padding: 6px 14px 8px; border-bottom: 1px solid var(--border); background: var(--bg-canvas); flex-shrink: 0; }
  .telemetry-item { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
  .stat-label { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
  .stat-val { font: 600 14px Consolas, monospace; white-space: nowrap; }
  .telemetry-percent { margin-left: auto; font: 11px Consolas, monospace; color: var(--text-muted); white-space: nowrap; }
  .stat-sub { font-size: 11px; color: var(--text-muted); }

  /* Multi-segment Progress Bar */
  .progress-track {
    height: 3px;
    background: var(--bg-input);
    border-radius: 0;
    overflow: hidden;
    display: flex;
    margin: 6px 0;
  }
  .telemetry-strip > .progress-track { position: absolute; bottom: 0; left: 0; width: 100%; height: 2px; margin: 0; }
  .progress-seg {
    height: 100%;
    transition: width 0.3s ease;
  }

  /* Continuous workspace sections, separated only by hairlines. */
  .tab-panel { display: none; min-width: 0; min-height: 0; overflow-y: auto; flex: 1; }
  .tab-panel.active { display: block; }
  #tab-dashboard.active { display: flex; flex-direction: column; overflow: hidden; }
  .surface-section { padding: 16px; border-bottom: 1px solid var(--border); min-width: 0; }
  .section-title {
    margin: 0 0 12px;
    font-size: 13px;
    font-weight: 600;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .section-title h2 { font: inherit; margin: 0; }
  .queue-toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 12px; border-bottom: 1px solid var(--border); }
  #jobSearchInput { width: 185px; }
  .grid-2 {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }
  .grid-3 {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }
  .grid-2 > *, .grid-3 > * { min-width: 0; }
  .field {
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin-bottom: 10px;
    min-width: 0;
  }
  .field label {
    font-size: 11px;
    font-weight: 500;
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
    border-radius: 4px;
    padding: 5px 8px;
    color: var(--text);
    font-size: 12px;
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
    font-size: 11px;
    cursor: pointer;
    user-select: none;
  }

  /* Native buttons retain keyboard access and expose selection via aria-pressed. */
  .segmented { display: inline-flex; flex-wrap: wrap; gap: 2px; padding: 3px; border-radius: 5px; background: var(--bg-canvas); max-width: 100%; }
  .segment { border: 0; border-radius: 3px; background: transparent; color: var(--text-muted); font-size: 11px; padding: 5px 10px; cursor: pointer; }
  .segment:hover { color: var(--text); }
  .segment.selected { background: var(--bg-elevated); color: var(--text); box-shadow: 0 1px 3px #0001; }
  :root[data-theme=light] .segment.selected { background: var(--bg-surface); box-shadow: 0 1px 3px #0002; }
  .mode-field { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 12px; }

  /* Nine connected accordion rows. */
  .pipeline {
    display: flex;
    flex-direction: column;
    gap: 0;
    position: relative;
  }
  .pipe-step {
    background: var(--bg-surface);
    border-top: 1px solid var(--border);
    min-width: 0;
  }
  .pipe-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 9px 16px;
  }
  .pipe-head:hover { background: var(--bg-elevated); }
  .pipe-head > div { display: flex; align-items: center; min-width: 0; }
  .pipe-step > .grid-3, .pipe-step > .pipe-body { padding: 8px 16px 12px 54px; }
  .pipe-body > .grid-3 { margin-top: 12px; }
  .pipe-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    flex-shrink: 0;
    color: var(--text-muted);
    font: 11px Consolas, monospace;
    margin-right: 16px;
  }
  .pipe-title {
    font-weight: 500;
    font-size: 12px;
  }
  .pipe-summary {
    font-size: 10px;
    color: var(--text-muted);
    white-space: nowrap;
  }
  .pipe-head::after { content: '−'; color: var(--text-muted); }
  .collapsed > .pipe-head::after { content: '+'; }
  .pipe-summary { margin-left: auto; margin-right: 60px; }
  .regex-tester { padding-top: 12px; margin-top: 8px; border-top: 1px solid var(--border); }

  /* Buttons */
  .btn-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .btn {
    padding: 5px 10px;
    border-radius: 4px;
    border: 1px solid transparent;
    font-size: 11px;
    font-weight: 500;
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
  .btn-danger { background: transparent; color: var(--danger); }
  .btn-danger:hover:not(:disabled) { background: var(--danger-soft); }
  .btn-secondary {
    background: transparent;
    border-color: var(--border);
    color: var(--text);
  }
  .btn-secondary:hover:not(:disabled), .btn-ghost:hover:not(:disabled) { background: var(--bg-elevated); }
  .btn-ghost { background: transparent; color: var(--text-secondary); }
  .btn-sm { padding: 3px 7px; font-size: 11px; }
  .topbar .btn { padding: 4px 7px; }

  /* Flat filter tabs */
  .filter-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
  }
  .filter-pill {
    padding: 5px 8px;
    border-radius: 0;
    border: 0;
    background: transparent;
    color: var(--text-secondary);
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
  }
  .filter-pill.active {
    box-shadow: inset 0 -2px var(--primary);
    color: var(--text);
  }

  /* Tables */
  .table-wrap {
    overflow: auto;
    min-width: 0;
    max-width: 100%;
  }
  .jobs-table-wrap { flex: 1; min-height: 0; }
  .jobs-table-wrap table { min-width: 1160px; }
  #jobsPagination { min-height: 30px; padding: 4px 12px; border-top: 1px solid var(--border); color: var(--text-muted); font-size: 11px; flex-shrink: 0; }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  th, td {
    padding: 7px 10px;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }
  th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--bg-surface);
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
  }
  tr:hover td {
    background: rgba(59, 130, 246, 0.03);
  }
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    white-space: nowrap;
  }
  .badge-success { background: var(--success-soft); color: var(--success); }
  .badge-pending { background: var(--primary-soft); color: var(--primary); }
  .badge-warn { background: var(--warning-soft); color: var(--warning); }
  .badge-danger { background: var(--danger-soft); color: var(--danger); }
  .badge-muted { background: rgba(148, 163, 184, 0.16); color: var(--text-secondary); }

  .mono { font-family: "JetBrains Mono", Consolas, monospace; font-size: 11px; }
  .copy-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 7px;
    border-radius: 3px;
    background: var(--bg-elevated);
    border: 0;
    cursor: pointer;
    font-size: 11px;
    color: var(--text-secondary);
  }
  .copy-chip:hover { border-color: var(--primary); color: var(--primary); }

  /* Floating Bulk Action Bar */
  .floating-bulk-bar {
    position: fixed;
    bottom: calc(var(--terminal-height) + 12px);
    left: calc(50% + var(--sidebar-width) / 2);
    transform: translateX(-50%);
    background: var(--bg-sidebar);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    box-shadow: var(--shadow);
    z-index: 500;
    display: none;
    align-items: center;
    gap: 8px;
    width: min(1040px, calc(100% - var(--sidebar-width) - 24px));
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
    background: var(--bg-surface);
    border-left: 1px solid var(--border);
    box-shadow: var(--shadow);
    z-index: 810;
    padding: 20px;
    overflow-y: auto;
    transform: translateX(100%);
    visibility: hidden;
    transition: transform 0.22s ease;
  }
  .drawer.open {
    transform: translateX(0);
    visibility: visible;
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
    background: var(--bg-elevated);
    padding: 8px;
    margin-top: 6px;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    align-items: center;
  }
  /* The terminal docks outside the scrollable views, collapsed by default. */
  .terminal-dock { --danger: #f87171; --warning: #fbbf24; --success: #34d399; position: fixed; bottom: 0; left: var(--sidebar-width); right: 0; z-index: 110; color-scheme: dark; background: var(--bg-terminal); color: #aeb7ca; border-top: 1px solid #ffffff12; }
  .terminal-toggle { display: flex; gap: 10px; align-items: center; width: 100%; height: 33px; padding: 0 14px; background: transparent; border: 0; color: inherit; cursor: pointer; text-align: left; font-size: 11px; }
  .terminal-toggle::before { content: '>_'; color: #6f7e99; font-family: Consolas, monospace; }
  .terminal-toggle::after { content: '展开 ↑'; margin-left: auto; color: #6f7e99; font-size: 10px; }
  .terminal-toggle[aria-expanded=true]::after { content: '收起 ↓'; }
  .terminal-body { padding: 0 14px 12px; height: 232px; display: flex; flex-direction: column; }
  .terminal-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; border-top: 1px solid #ffffff12; padding: 8px 0; }
  .terminal-toolbar .btn { color: #aeb7ca; }
  #runnerSlots { margin-right: auto; overflow-wrap: anywhere; }
  .log-box {
    background: var(--bg-terminal);
    padding: 6px 0;
    font-family: Consolas, monospace;
    font-size: 12px;
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    color: #93c5fd;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .toast {
    position: fixed;
    top: 20px;
    right: 24px;
    padding: 11px 18px;
    border-radius: 6px;
    background: var(--bg-sidebar);
    border: 1px solid var(--primary);
    color: var(--text);
    font-size: 12px;
    font-weight: 600;
    box-shadow: var(--shadow);
    z-index: 9999;
    display: none;
  }
  input, select, textarea { min-width: 0; max-width: 100%; }
  input[type=checkbox] { accent-color: var(--primary); margin: 0; flex-shrink: 0; }
  button:focus-visible, [tabindex]:focus-visible { outline: 2px solid var(--primary); outline-offset: 3px; }
  .pipe-head { cursor: pointer; }
  .pipe-step.collapsed > :not(.pipe-head) { display: none; }
  .pipe-step.collapsed .pipe-head { margin-bottom: 0; }
  .pipe-step + .insert-zone { position: relative; min-width: 0; }
  .pipe-step + .insert-zone:has(.step-box) { padding: 0 16px 8px 54px; }
  .insert-zone > .btn { position: absolute; right: 42px; top: -32px; padding: 3px 6px; font-size: 10px; color: var(--text-muted); }
  .smart-selector-control { display: flex; flex-wrap: wrap; gap: 5px; }
  .smart-selector-control select { flex: 1; font-size: 11px; }
  .smart-selector-control input { flex: 1; min-width: 100px; }
  .log-error { color: var(--danger); } .log-warn { color: var(--warning); }
  .log-success { color: var(--success); }
  .drop-zone { background: var(--bg-elevated); border-radius: 4px; padding: 8px; }
  .drop-zone textarea { display: block; width: 100%; border: 0; background: transparent; padding: 4px; }
  .drop-label { display: flex; justify-content: space-between; gap: 6px; margin-bottom: 6px; font-size: 11px; color: var(--text-muted); }
  .drop-zone.dragging { outline: 2px dashed var(--primary); }
  .secret-cell { max-width: 210px; word-break: break-all; }
  .selected-row { background: var(--primary-soft); }
  .step-box.disabled-step { opacity: .55; }
  .step-box input[type=text], .step-box select { width: 100%; }
  .running-badge { color: var(--primary); font-size: 11px; }
  .proxy-status { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
  .proxy-identity { min-width: 0; flex: 1; }
  #activeProxyNodeTitle { font-weight: 600; overflow-wrap: anywhere; }
  #activeProxyServerSub { font-size: 10px; color: var(--text-muted); overflow-wrap: anywhere; }
  .proxy-progress { flex: 1; min-width: 150px; font-size: 10px; color: var(--text-muted); }
  .proxy-columns { gap: 0; }
  .proxy-columns > :first-child { border-right: 1px solid var(--border); }
  .security-note { color: var(--text-muted); font-size: 11px; margin: 12px 0 0; }
  #backupResult, #regexTestResult { overflow-wrap: anywhere; }
  @media (max-width: 1250px) and (min-width: 1101px) {
    .topbar-right { width: 100%; justify-content: flex-end; }
  }
  @media (max-width: 1100px) {
    :root { --sidebar-width: 0px; }
    body { flex-direction: column; }
    .sidebar { position: static; width: 100%; flex-shrink: 0; padding: 6px 10px 0; border-right: 0; border-bottom: 1px solid var(--border); display: grid; grid-template-columns: 1fr auto; }
    .brand { padding: 0 0 6px; gap: 8px; }
    .brand-sub, #configPathText { display: none; }
    .brand-logo { width: 22px; height: 22px; font-size: 13px; }
    .brand-title { font-size: 12px; }
    .sidebar-footer { grid-column: 2; grid-row: 1; border: 0; padding: 0 0 6px; }
    .nav-list { grid-column: 1 / -1; flex-direction: row; overflow-x: auto; min-width: 0; gap: 2px; }
    .nav-item { padding: 7px 10px; flex-shrink: 0; border-radius: 0; }
    .nav-item.active { box-shadow: inset 0 -2px var(--primary); }
    .main-shell { height: auto; flex: 1; min-height: 0; }
    .telemetry-strip { gap: 18px; }
    .floating-bulk-bar { left: 50%; width: calc(100% - 24px); }
  }
  @media (max-width: 650px) {
    .grid-2, .grid-3 { grid-template-columns: minmax(0, 1fr); }
    .grid-2 > *, .grid-3 > * { grid-column: auto !important; min-width: 0; }
    .topbar { padding: 6px 8px; gap: 6px; }
    .topbar-left, .topbar-right { width: 100%; flex: auto; }
    .topbar-right { justify-content: flex-end; }
    .ip-capsule { margin-right: auto; max-width: 210px; }
    .topbar-left .status-pill { max-width: 105px; }
    #batchSelect { flex: 1 1 145px; width: 145px; }
    .telemetry-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); padding: 6px 10px 8px; gap: 4px; }
    .telemetry-item { flex-direction: column; gap: 0; }
    .stat-label { font-size: 10px; }
    .stat-val { font-size: 12px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
    .telemetry-percent, .pipe-summary { display: none; }
    .queue-toolbar { padding: 6px 8px; }
    .queue-toolbar > .btn-row { width: 100%; justify-content: space-between; }
    #jobSearchInput { width: 190px; }
    .filter-pill { padding: 4px 7px; font-size: 10px; }
    .surface-section { padding: 12px; }
    .section-title { align-items: flex-start; }
    .segment { padding: 5px 8px; }
    .pipe-head { padding: 9px 12px; }
    .pipe-num { margin-right: 8px; }
    .pipe-step > .grid-3, .pipe-step > .pipe-body { padding: 6px 12px 12px; }
    .pipe-step + .insert-zone:has(.step-box) { padding-left: 12px; }
    .step-box { grid-template-columns: 1fr; }
    .proxy-columns > :first-child { border-right: 0; }
    .proxy-status { display: grid; grid-template-columns: minmax(0, 1fr); }
    .proxy-progress { min-width: 0; }
    .proxy-status > .btn-row { justify-content: flex-end; }
    .floating-bulk-bar { max-height: 40dvh; overflow-y: auto; gap: 6px; padding: 8px; }
    .toast { left: 12px; right: 12px; top: 12px; }
    .drawer { max-width: 100vw; padding: 14px; }
    .terminal-body { height: 260px; }
    .terminal-toolbar { gap: 8px; }
    #runnerSlots { width: 100%; }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
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
      <div class="brand-sub">LOCAL WORKBENCH</div>
    </div>
  </div>

  <nav class="nav-list" aria-label="工作台导航">
    <button class="nav-item active" id="nav-dashboard" onclick="switchTab('dashboard', this)">
      <span>任务队列</span>
      <span class="nav-badge" id="navBadgeTotal">0</span>
    </button>
    <button class="nav-item" id="nav-import" onclick="switchTab('import', this)">
      <span>账号导入</span>
    </button>
    <button class="nav-item" id="nav-flows" onclick="switchTab('flows', this)">
      <span>流程编排</span>
    </button>
    <button class="nav-item" id="nav-proxies" onclick="switchTab('proxies', this)">
      <span>代理池</span>
      <span class="nav-badge" id="navBadgeProxies">0</span>
    </button>
    <button class="nav-item" id="nav-delivery" onclick="switchTab('delivery', this)">
      <span>导出与备份</span>
    </button>
  </nav>

  <div class="sidebar-footer">
    <div id="configPathText" style="word-break: break-all;">正在加载配置...</div>
    <div class="btn-row" style="justify-content: space-between;">
      <button class="btn btn-ghost btn-sm" onclick="toggleTheme()" aria-label="🌓 切换深浅主题">切换主题</button>
      <button class="btn btn-ghost btn-sm" onclick="refreshAll()">刷新</button>
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
      <select id="batchSelect" aria-label="当前批次" onchange="onBatchChange()"></select>
      <input type="number" id="runLimitInput" aria-label="执行数量" placeholder="全部" title="执行数量，留空为全部" min="1" />
      <button class="btn btn-primary" onclick="controlBatch('run')" aria-label="▶ 开始/继续注册">开始执行</button>
      <button class="btn btn-secondary" onclick="controlBatch('verify_batch')" aria-label="🔐 批量验登录&拿结果">批量核验</button>
      <button class="btn btn-ghost btn-sm" onclick="controlBatch('pause')">暂停</button>
      <button class="btn btn-ghost btn-sm" onclick="controlBatch('resume')">恢复</button>
      <button class="btn btn-danger btn-sm" onclick="controlBatch('stop')">停止</button>
      <button class="btn btn-ghost btn-sm" onclick="controlBatch('recover')">恢复中断</button>
    </div>
    <div class="topbar-right">
      <button class="ip-capsule" onclick="switchTab('proxies', document.getElementById('nav-proxies'))" title="代理池与换 IP 策略">
        <span id="topIpCapsuleText">代理池: 未启用</span>
      </button>
      <button class="btn btn-ghost btn-sm" onclick="exportData('xlsx')" aria-label="📥 导出 Excel">Excel</button>
      <button class="btn btn-ghost btn-sm" onclick="exportData('csv')" aria-label="📄 导出 CSV">CSV</button>
    </div>
  </header>

  <section id="telemetryStrip" class="telemetry-strip" aria-label="任务指标">
    <div class="telemetry-item"><span class="stat-label">总计</span><span class="stat-val" id="statTotal">0</span><span class="sr-only" id="statBatchCount">共 0 个批次</span></div>
    <div class="telemetry-item"><span class="stat-label">已拿结果</span><span class="stat-val" style="color:var(--success)" id="statSucceeded">0</span><span class="sr-only" id="statWithKey"></span></div>
    <div class="telemetry-item"><span class="stat-label">运行中</span><span class="stat-val" id="statRunning">0</span><span class="sr-only" id="statPending">待执行 0</span></div>
    <div class="telemetry-item"><span class="stat-label">待核验</span><span class="stat-val" id="statReview">0</span><span class="sr-only" id="statFailed"></span></div>
    <div class="telemetry-item"><span class="stat-label">代理池</span><span class="stat-val" id="statProxySummary">直连</span><span class="sr-only" id="statProxyRotation"></span></div>
    <span class="telemetry-percent" id="progressPercentText">完成率 0%</span>
    <div class="progress-track" aria-label="任务状态分布">
      <div class="progress-seg" id="progSuccess" style="width:0%;background:var(--success)" title="已完成"></div>
      <div class="progress-seg" id="progNoKey" style="width:0%;background:var(--purple)" title="已登录待拿结果"></div>
      <div class="progress-seg" id="progRunning" style="width:0%;background:var(--primary)" title="正在运行"></div>
      <div class="progress-seg" id="progReview" style="width:0%;background:var(--warning)" title="待核验"></div>
      <div class="progress-seg" id="progFailed" style="width:0%;background:var(--danger)" title="失败或跳过"></div>
      <div class="progress-seg" id="progPending" style="width:0%;background:var(--text-muted)" title="待执行"></div>
    </div>
  </section>

  <main class="content-area">

    <!-- ==================== TAB 1: DASHBOARD & DATA TABLE (ISS-001) ==================== -->
    <div id="tab-dashboard" class="tab-panel active">
        <div class="queue-toolbar">
          <div class="filter-pills" id="stateFilterPills" role="group" aria-label="任务状态筛选">
            <button class="filter-pill active" onclick="setStateFilter('', this)">全部</button>
            <button class="filter-pill" onclick="setStateFilter('SUCCEEDED', this)">已完成</button>
            <button class="filter-pill" onclick="setStateFilter('PENDING', this)">待执行</button>
            <button class="filter-pill" onclick="setStateFilter('PENDING_VERIFY', this)">待核验</button>
            <button class="filter-pill" onclick="setStateFilter('NEEDS_REVIEW', this)">人工处理</button>
            <button class="filter-pill" onclick="setStateFilter('UNKNOWN', this)">待核查</button>
            <button class="filter-pill" onclick="setStateFilter('FAILED', this)">失败</button>
          </div>
          <div class="btn-row">
            <label class="checkbox-row">
              <input type="checkbox" id="revealSecretsToggle" onchange="onRevealChange()" />
              显示明文
            </label>
              <input type="text" id="jobSearchInput" aria-label="搜索任务" placeholder="搜索邮箱、用户或错误码" oninput="onJobSearch()" />
          </div>
        </div>

        <div class="table-wrap jobs-table-wrap" tabindex="0" role="region" aria-label="任务数据表">
          <table aria-label="任务队列">
            <thead>
              <tr>
                <th style="width:36px;"><input type="checkbox" id="selectAllJobs" aria-label="选择当前页全部任务" onchange="toggleSelectAllJobs(this)" /></th>
                <th>邮箱账号</th>
                <th>状态</th>
                <th>执行阶段</th>
                <th>登录密码</th>
                <th>提取结果</th>
                <th>代理节点</th>
                <th>状态说明</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="jobsTableBody">
              <tr><td colspan="9" style="text-align:center; color: var(--text-muted); padding: 24px;">正在加载任务列表...</td></tr>
            </tbody>
          </table>
        </div>
    </div>

    <!-- ==================== TAB 2: SMART IMPORT WIZARD & VERIFY (ISS-003) ==================== -->
    <div id="tab-import" class="tab-panel">
      <section class="surface-section">
        <div class="section-title">
          <h2>账号导入</h2>
          <div class="segmented" role="group" aria-label="导入任务模式">
            <button class="segment selected" id="modeCardRegister" aria-pressed="true" onclick="selectImportMode('register')">新账号注册</button>
            <button class="segment" id="modeCardExisting" aria-pressed="false" onclick="selectImportMode('existing_login')">已有账号验号</button>
          </div>
        </div>
        <input type="hidden" id="importMode" value="register" />

        <div class="grid-3">
          <div class="field">
            <label for="importFormat">数据格式</label>
            <select id="importFormat" onchange="updateImportPreview()">
              <option value="auto">自动识别（1～5 段 / CSV）</option>
              <option value="four_part">四段式 OAuth</option>
              <option value="three_part">三段式双密码</option>
              <option value="two_part">两段式账密</option>
              <option value="email_only">纯邮箱</option>
              <option value="csv">CSV</option>
            </select>
          </div>
          <div class="field">
            <label for="importDelimiter">分隔符</label>
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
            <label for="importPasswordRole">两段式密码用途</label>
            <select id="importPasswordRole" onchange="updateImportPreview()">
              <option value="both">邮箱与平台通用</option>
              <option value="agnes_only">仅平台登录</option>
              <option value="mailbox_only">仅邮箱收信</option>
            </select>
          </div>
          <div class="field">
            <label for="importBatchId">批次名称</label>
            <input type="text" id="importBatchId" value="batch-main" placeholder="例如：batch-main" />
          </div>
          <div class="field">
            <label for="importMailboxTransport">收码协议</label>
            <select id="importMailboxTransport">
              <option value="graph">Microsoft Graph</option>
              <option value="imap">Outlook IMAP XOAUTH2</option>
              <option value="imap_password">IMAP 账密</option>
            </select>
          </div>
          <div class="field">
            <label for="importFilePicker">本地文件</label>
            <input type="file" id="importFilePicker" accept=".txt,.csv" onchange="loadImportFile(this)" />
          </div>
        </div>

        <div id="importDropZone" class="drop-zone">
          <div class="drop-label"><label for="importAccountsText">账号数据</label><span>粘贴或拖入 TXT / CSV · 仅本机解析</span></div>
          <textarea id="importAccountsText" aria-label="账号导入内容" rows="4" oninput="updateImportPreview()" placeholder="每行一条账号&#10;user@example.com----password&#10;user@example.com----mail-password----client-id----refresh-token"></textarea>
        </div>

        <!-- Live Parse Preview Table (ISS-003) -->
        <div style="margin: 12px 0;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <span style="font-size:12px; font-weight:600;">解析预览</span>
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
                <tr><td colspan="8" style="text-align:center; color:var(--text-muted);">暂无数据</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="btn-row">
          <button class="btn btn-primary" id="importSubmit" onclick="submitImportAccounts()" aria-label="🚀 确认无误，立即批量导入账号">导入账号</button>
          <span id="importResultBox" style="font-size: 13px; color: var(--success); font-weight: 600;"></span>
        </div>
      </section>

      <section class="surface-section">
        <div class="section-title"><h2>验证设置</h2><button class="btn btn-primary" onclick="saveAllConfig()" aria-label="💾 保存验证设置">保存设置</button></div>
        <div class="mode-field"><span class="stat-label">验证码</span>
          <div class="segmented" role="group" aria-label="验证码获取模式">
            <button class="segment selected" id="vCardAuto" aria-pressed="true" onclick="selectVerifyMode('auto_mailbox')">自动收码</button>
            <button class="segment" id="vCardManual" aria-pressed="false" onclick="selectVerifyMode('manual')">人工输入</button>
            <button class="segment" id="vCardNone" aria-pressed="false" onclick="selectVerifyMode('none')">无需验证码</button>
          </div>
        </div>
        <input type="hidden" id="cfgVerifyMode" value="auto_mailbox" />
        <div class="mode-field"><span class="stat-label">登录核验</span>
          <div class="segmented" role="group" aria-label="导入登录核验标准">
            <button class="segment selected" id="iLoginStrict" aria-pressed="true" onclick="selectLoginVerifyMode('strict_identity')">严格身份</button>
            <button class="segment" id="iLoginSelector" aria-pressed="false" onclick="selectLoginVerifyMode('selector_only')">已登录元素</button>
            <button class="segment" id="iLoginToken" aria-pressed="false" onclick="selectLoginVerifyMode('url_or_token')">跳转与令牌</button>
          </div>
        </div>
        <select id="importLoginVerifyMode" aria-label="账号登录成功核验标准" onchange="selectLoginVerifyMode(this.value)" hidden><option value="strict_identity">严格身份</option><option value="selector_only">已登录元素</option><option value="url_or_token">跳转与令牌</option></select>

        <div class="grid-3">
          <div class="field">
            <label for="cfgSenderDomain">发件域名</label>
            <input type="text" id="cfgSenderDomain" placeholder="agnes-ai.com (填 * 不限域名)" />
          </div>
          <div class="field">
            <label for="cfgCodePattern">验证码正则</label>
            <input type="text" id="cfgCodePattern" class="mono" placeholder="(?<!\d)\d{6}(?!\d)" />
          </div>
          <div class="field">
            <label for="cfgImapHost">IMAP 服务器 / 超时（秒）</label>
            <div style="display:flex; gap:6px;">
              <input type="text" id="cfgImapHost" placeholder="outlook.office365.com" style="flex:1;" />
              <input type="number" id="cfgVerifyTimeout" aria-label="验证码超时秒数" min="5" max="900" style="width:65px;" />
            </div>
          </div>
        </div>

      </section>
    </div>

    <!-- ==================== TAB 3: VISUAL FLOW BUILDER (ISS-002) ==================== -->
    <div id="tab-flows" class="tab-panel">
      <section class="surface-section">
        <div class="section-title">
          <h2>流程编排</h2>
          <div class="btn-row">
            <button class="btn btn-ghost btn-sm" onclick="resetFlowDefaults()" aria-label="🔄 一键恢复 Agnes 官方默认流程">恢复默认</button>
            <button class="btn btn-primary btn-sm" onclick="saveAllConfig()" aria-label="💾 保存全部流程修改">保存配置</button>
          </div>
        </div>
        <div class="grid-3">
          <div class="field">
            <label for="cfgBaseUrl">目标地址</label>
            <input type="text" id="cfgBaseUrl" class="mono" placeholder="https://platform.agnes-ai.com" />
          </div>
          <div class="field">
            <label for="cfgMode">运行模式</label>
            <select id="cfgMode">
              <option value="agnes">真实浏览器</option>
              <option value="mock">本地模拟</option>
            </select>
          </div>
          <div class="field">
            <label for="cfgHeadless">浏览器窗口</label>
            <select id="cfgHeadless">
              <option value="false">显示窗口</option>
              <option value="true">后台运行</option>
            </select>
          </div>
          <div class="field">
            <label for="cfgConcurrency">并发窗口</label>
            <input type="number" id="cfgConcurrency" min="1" max="50" />
          </div>
          <div class="field">
            <label for="cfgPerMinute">每分钟提交上限</label>
            <input type="number" id="cfgPerMinute" min="0.1" step="0.5" />
          </div>
          <div class="field">
            <label for="cfgMaxAttempts">最大重试次数</label>
            <input type="number" id="cfgMaxAttempts" min="1" max="10" />
          </div>
        </div>
      </section>

      <div id="flowPipeline" class="pipeline" aria-label="执行流程">
        <div class="pipe-step" data-flow-kind="reg" data-stage="before_open">
          <div class="pipe-head"><div><span class="pipe-num">1</span><span class="pipe-title">访问注册入口页</span></div><span class="pipe-summary">注册</span></div>
          <div class="grid-3"><div class="field"><label for="regEntryPath">入口路径</label><input id="regEntryPath" type="text" class="mono" placeholder="/login" /></div></div>
        </div>
        <div class="pipe-step" data-flow-kind="reg" data-stage="before_fill">
          <div class="pipe-head"><div><span class="pipe-num">2</span><span class="pipe-title">点击切换注册</span></div><span class="pipe-summary">注册</span></div>
          <div class="grid-3"><div class="field"><label for="regOpenSelector">切换注册按钮</label><input id="regOpenSelector" type="text" class="mono" placeholder='role=link[name="注册"]' /></div></div>
        </div>
        <div class="pipe-step" data-flow-kind="reg" data-stage="before_code">
          <div class="pipe-head"><div><span class="pipe-num">3</span><span class="pipe-title">填写邮箱与密码</span></div><span class="pipe-summary">注册</span></div>
          <div class="grid-3">
            <div class="field"><label for="regEmailSelector">邮箱输入框</label><input id="regEmailSelector" type="text" class="mono" placeholder='role=textbox[name="邮箱"]' /></div>
            <div class="field"><label for="regPasswordSelector">密码输入框</label><input id="regPasswordSelector" type="text" class="mono" placeholder='role=textbox[name="密码"]' /></div>
            <div class="field"><label for="regConfirmSelector">确认密码框</label><input id="regConfirmSelector" type="text" class="mono" placeholder="无确认框时选择跳过" /></div>
          </div>
        </div>
        <div class="pipe-step" data-flow-kind="reg" data-stage="before_submit">
          <div class="pipe-head"><div><span class="pipe-num">4</span><span class="pipe-title">发送并填写验证码</span></div><span class="pipe-summary">注册</span></div>
          <div class="grid-3">
            <div class="field"><label for="regSendReadySelector">发码就绪标志</label><input id="regSendReadySelector" type="text" class="mono" placeholder='img[alt="can send"]' /></div>
            <div class="field"><label for="regSendClickSelector">发码按钮</label><input id="regSendClickSelector" type="text" class="mono" placeholder="留空使用就绪元素" /></div>
            <div class="field"><label for="regCodeInputSelector">验证码输入框</label><input id="regCodeInputSelector" type="text" class="mono" placeholder='role=textbox[name="验证码"]' /></div>
          </div>
        </div>
        <div class="pipe-step" data-flow-kind="reg" data-stage="after_submit">
          <div class="pipe-head"><div><span class="pipe-num">5</span><span class="pipe-title">点击提交注册</span></div><span class="pipe-summary">注册</span></div>
          <div class="pipe-body"><div class="field"><label for="regSubmitSelector">注册提交按钮</label><input id="regSubmitSelector" type="text" class="mono" placeholder='button:has-text("继续")' /></div><div id="regCustomStepsContainer"></div></div>
        </div>
        <div class="pipe-step" data-flow-kind="login" data-stage="before_submit">
          <div class="pipe-head"><div><span class="pipe-num">6</span><span class="pipe-title">登录账号与确认身份</span></div><span class="pipe-summary">登录核验</span></div>
          <div class="pipe-body">
            <div class="segmented" role="group" aria-label="流程登录核验标准">
              <button class="segment selected" id="lCardStrict" aria-pressed="true" onclick="selectLoginVerifyMode('strict_identity')">严格身份</button>
              <button class="segment" id="lCardSelector" aria-pressed="false" onclick="selectLoginVerifyMode('selector_only')">已登录元素</button>
              <button class="segment" id="lCardToken" aria-pressed="false" onclick="selectLoginVerifyMode('url_or_token')">跳转与令牌</button>
            </div>
            <input type="hidden" id="cfgLoginVerifyMode" value="strict_identity" />
            <div class="grid-3">
              <div class="field"><label for="loginPath">登录路径</label><input id="loginPath" type="text" class="mono" placeholder="/login" /></div>
              <div class="field"><label for="loginEmailSelector">登录邮箱框</label><input id="loginEmailSelector" type="text" class="mono" placeholder='role=textbox[name="邮箱"]' /></div>
              <div class="field"><label for="loginPasswordSelector">登录密码框</label><input id="loginPasswordSelector" type="text" class="mono" placeholder='input[placeholder="请输入密码"]' /></div>
              <div class="field"><label for="loginSubmitSelector">登录提交按钮</label><input id="loginSubmitSelector" type="text" class="mono" placeholder='button:has-text("登录")' /></div>
              <div class="field"><label for="loginApiPath">登录接口路径</label><input id="loginApiPath" type="text" class="mono" placeholder="/api/user/login（none 跳过）" /></div>
              <div class="field"><label for="loginPostPath">登录后跳转</label><input id="loginPostPath" type="text" class="mono" placeholder="/settings/apiKeys" /></div>
              <div class="field"><label for="loginTokenKey">本地登录令牌键名</label><input id="loginTokenKey" type="text" class="mono" value="token" /></div>
              <div class="field"><label for="cfgIdentityNav">个人资料导航</label><input id="cfgIdentityNav" type="text" class="mono" placeholder='text="个人资料"' /></div>
              <div class="field"><label for="cfgAuthSelector">已登录标志</label><input id="cfgAuthSelector" type="text" class="mono" placeholder='img[alt="user"]' /></div>
              <div class="field"><label for="cfgAccountIdentitySelector">页面邮箱元素</label><input id="cfgAccountIdentitySelector" type="text" class="mono" placeholder="留空匹配页面邮箱" /></div>
            </div>
            <button class="btn btn-ghost btn-sm" onclick="addCustomStep('login')">+ 插入登录自定义动作</button><div id="loginCustomStepsContainer"></div>
          </div>
        </div>
        <div class="pipe-step" data-flow-kind="key" data-stage="before_extract">
          <div class="pipe-head"><div><span class="pipe-num">7</span><span class="pipe-title">进入最终结果页面</span></div><span class="pipe-summary">结果提取</span></div>
          <div class="grid-3">
            <div class="field"><label for="keyNavSelector">结果页导航</label><input id="keyNavSelector" type="text" class="mono" placeholder='text="API 密钥"' /></div>
            <div class="field"><label for="keyTargetUrl">结果页地址</label><input id="keyTargetUrl" type="text" class="mono" placeholder="/settings/apiKeys" /></div>
          </div>
        </div>
        <div class="pipe-step" data-flow-kind="key" data-stage="after_create">
          <div class="pipe-head"><div><span class="pipe-num">8</span><span class="pipe-title">触发创建目标项</span></div><span class="pipe-summary">结果提取</span></div>
          <div class="grid-3">
            <div class="field"><label for="keyCreateSelector">创建按钮</label><input id="keyCreateSelector" type="text" class="mono" placeholder='button:has-text("创建新的密钥")' /></div>
            <div class="field"><label for="keyNameSelector">名称输入框</label><input id="keyNameSelector" type="text" class="mono" placeholder="#keyName" /></div>
            <div class="field"><label for="keyNameTemplate">名称模板</label><input id="keyNameTemplate" type="text" class="mono" placeholder="Agnes Provisioner {user_id}" /></div>
            <div class="field"><label for="keyConfirmSelector">确认创建按钮</label><input id="keyConfirmSelector" type="text" class="mono" placeholder=".ant-modal .ant-btn-primary" /></div>
          </div>
        </div>
        <div class="pipe-step" data-flow-kind="key" data-stage="extract">
          <div class="pipe-head"><div><span class="pipe-num">9</span><span class="pipe-title">提取并保存最终结果</span></div><span class="pipe-summary">结果提取</span></div>
          <div class="pipe-body">
            <div class="btn-row"><label class="checkbox-row"><input id="keyFlowEnabled" type="checkbox" checked />启用结果提取</label><label class="checkbox-row"><input id="keyFlowRequireKey" type="checkbox" checked />拿到结果才算完成</label></div>
            <div class="grid-3">
              <div class="field"><label for="keyExtractMode">提取渠道</label><select id="keyExtractMode"><option value="auto">自动提取</option><option value="dom_regex">页面文本正则</option><option value="network_json">接口 JSON</option><option value="clipboard_copy">复制按钮</option><option value="local_storage">本地存储</option></select></div>
              <div class="field"><label for="keyValueSelector">结果文本容器</label><input id="keyValueSelector" type="text" class="mono" placeholder=".ant-modal, .ant-table-tbody" /></div>
              <div class="field"><label for="keyCopySelector">复制按钮</label><input id="keyCopySelector" type="text" class="mono" placeholder='img[alt="复制"]' /></div>
              <div class="field"><label for="keyStorageKey">本地存储键名</label><input id="keyStorageKey" type="text" class="mono" placeholder="token" /></div>
              <div class="field" style="grid-column:span 2"><label for="keyPattern">结果正则</label><input id="keyPattern" type="text" class="mono" oninput="runRegexTester()" placeholder="sk-[A-Za-z0-9_-]{16,}" />
                <div class="btn-row">
                  <button class="btn btn-ghost btn-sm" onclick="setKeyPattern('sk-[A-Za-z0-9_-]{16,}')">API Key</button>
                  <button class="btn btn-ghost btn-sm" onclick="setKeyPattern('eyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+')">JWT</button>
                  <button class="btn btn-ghost btn-sm" onclick="setKeyPattern('[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')">UUID</button>
                  <button class="btn btn-ghost btn-sm" onclick="setKeyPattern('.+')">非空文本</button>
                  <button class="btn btn-ghost btn-sm" onclick="setKeyPattern('(?&lt;!\\d)\\d{6}(?!\\d)')">6 位数字</button>
                </div>
              </div>
            </div>
            <div class="regex-tester"><label class="stat-label" for="regexSampleInput">正则预览</label><div class="grid-2"><input id="regexSampleInput" type="text" class="mono" oninput="runRegexTester()" value='{"data":{"apiKey":"sk-AbCdEf1234567890"}}' placeholder="示例文本或 JSON" /><div id="regexTestResult" class="mono"></div></div></div>
            <button class="btn btn-ghost btn-sm" onclick="addCustomStep('key')">+ 插入结果流程步骤</button><div id="keyCustomStepsContainer"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== TAB 4: PROXY POOL & AUTO IP ROTATION (ISS-004) ==================== -->
    <div id="tab-proxies" class="tab-panel">
      <div class="proxy-status">
        <div class="proxy-identity">
          <div class="stat-label">当前节点</div>
          <div class="mono" id="activeProxyNodeTitle">本机直连</div>
          <div id="activeProxyServerSub">未启用代理池</div>
        </div>
        <div class="proxy-progress">
          <div id="activeProxyWindowLabel">本轮进度：0 / 1</div>
          <div class="progress-track">
            <div class="progress-seg" id="activeProxyProgressBar" style="width:0%;background:var(--primary)"></div>
          </div>
          <div id="activeProxyCountdownLabel">未启用轮换</div>
        </div>
        <div class="btn-row">
          <button class="btn btn-secondary btn-sm" onclick="proxyAction('rotate_now')" aria-label="⏭ 立即手动切换到下一个 IP">切换节点</button>
          <button class="btn btn-ghost btn-sm" onclick="proxyAction('reset_rotation')" aria-label="♻️ 重置所有计数与状态">重置计数</button>
        </div>
      </div>

      <div class="grid-2 proxy-columns">
        <!-- Rotation Policy Configuration -->
        <section class="surface-section">
          <div class="section-title"><h2>轮换策略</h2><button class="btn btn-primary btn-sm" onclick="saveAllConfig()" aria-label="💾 保存换 IP 策略设置">保存策略</button></div>
          <div class="mode-field"><div class="segmented" role="group" aria-label="换 IP 策略">
            <button class="segment selected" id="pModeResult" aria-pressed="true" onclick="selectProxyRotateMode('result_reached')">按结果</button>
            <button class="segment" id="pModeExec" aria-pressed="false" onclick="selectProxyRotateMode('execution_count')">按执行</button>
            <button class="segment" id="pModeBoth" aria-pressed="false" onclick="selectProxyRotateMode('both')">双阈值</button>
          </div>
          </div>
          <input type="hidden" id="cfgProxyRotateMode" value="result_reached" />

          <div class="grid-2">
            <div class="field">
              <label for="cfgProxyRotateEvery" id="proxyThresholdLabel">结果阈值</label>
              <input type="number" id="cfgProxyRotateEvery" min="1" max="10000" value="2" />
            </div>
            <div class="field">
              <label for="cfgProxyExecLimit">执行兜底上限</label>
              <input type="number" id="cfgProxyExecLimit" min="1" max="10000" value="3" />
            </div>
          </div>

          <div class="field">
            <label class="checkbox-row">
              <input type="checkbox" id="cfgAutoSwitchIpLimit" checked />
              IP 注册受限时自动切换
            </label>
          </div>
          <div class="field">
            <label class="checkbox-row">
              <input type="checkbox" id="cfgEnableSessionStickiness" />
              动态隧道会话轮换
            </label>
          </div>
          <div class="field">
            <label class="checkbox-row">
              <input type="checkbox" id="cfgProxyRequired" />
              强制代理（无可用节点时暂停）
            </label>
          </div>
          <div class="field">
            <label for="cfgSessionSuffix">会话后缀模板</label>
            <input type="text" id="cfgSessionSuffix" class="mono" placeholder="-session-{session}-time-30" />
          </div>

        </section>

        <!-- Batch Proxy Import with Live Preview -->
        <section class="surface-section">
          <h2 class="section-title">导入代理</h2>
          <div class="grid-2">
            <div class="field">
              <label for="proxyInitialStatus">初始状态</label>
              <select id="proxyInitialStatus">
                <option value="HEALTHY">可用</option>
                <option value="UNCHECKED">待检测</option>
              </select>
            </div>
            <div class="field">
              <label for="proxySessionMode">代理类型</label>
              <select id="proxySessionMode">
                <option value="false">静态节点</option>
                <option value="true">动态会话隧道</option>
              </select>
            </div>
          </div>

          <div class="field">
            <label for="importProxiesText">代理地址</label>
            <textarea id="importProxiesText" rows="3" oninput="updateProxyPreview()" placeholder="每行一个 HTTP / HTTPS / SOCKS5 节点&#10;http://user:pass@127.0.0.1:8080"></textarea>
          </div>

          <div style="margin-bottom: 12px;">
            <div style="display:flex; justify-content:space-between; font-size:12.5px; font-weight:700; margin-bottom:6px;">
              <span>解析预览</span>
              <span id="proxyPreviewCount" class="badge badge-muted">0 条</span>
            </div>
            <div class="table-wrap" style="max-height: 150px; overflow-y: auto;">
              <table>
                <thead>
                   <tr><th>行</th><th>协议 / 主机 / 端口</th><th>账密认证</th><th>会话换IP模式 / 错误</th></tr>
                </thead>
                <tbody id="proxyPreviewBody">
                  <tr><td colspan="4" style="text-align:center; color:var(--text-muted);">暂无数据</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="btn-row">
            <label class="checkbox-row">
              <input type="checkbox" id="proxyClearExisting" />
              替换旧代理池
            </label>
            <button class="btn btn-primary" onclick="submitImportProxies()" aria-label="🌐 确认导入代理池">导入代理</button>
            <button class="btn btn-secondary" onclick="checkAllProxies()" aria-label="⚡ 并发测速 & 查出口IP">测速与出口 IP</button>
            <button class="btn btn-danger btn-sm" onclick="proxyAction('clear_all')">清空</button>
          </div>
          <div id="proxyImportMsg" style="margin-top: 8px; font-size: 13px; color: var(--success);"></div>
        </section>
      </div>

      <!-- Proxy Pool Nodes Table -->
      <section class="surface-section">
        <div class="section-title">
          <h2>代理节点</h2>
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
      </section>
    </div>
    <div id="tab-delivery" class="tab-panel">
      <section class="surface-section"><h2 class="section-title">交付导出</h2>
        <label class="checkbox-row"><input id="exportIncludeSecrets" type="checkbox" />包含明文凭证与提取结果</label>
        <div class="btn-row" style="margin-top:12px"><button class="btn btn-primary" onclick="exportData('xlsx')">导出 Excel</button><button class="btn btn-secondary" onclick="exportData('csv')">导出 CSV</button></div>
        <p class="security-note">范围：当前批次 · 默认脱敏 · 明文导出需确认</p>
      </section>
      <section class="surface-section"><h2 class="section-title">加密备份</h2><button class="btn btn-secondary" onclick="createBackup()">创建本地一致性备份</button><p class="security-note">执行器停止后可用 · 凭证仅限当前 Windows 用户解密</p><p id="backupResult" class="mono"></p></section>
    </div>
  </main>
  <section id="terminalDock" class="terminal-dock" aria-label="运行终端">
    <button id="terminalToggle" class="terminal-toggle" aria-label="运行终端" aria-expanded="false" aria-controls="terminalBody" onclick="toggleTerminal()">运行终端<span id="terminalSlotSummary" class="mono">0 个运行槽位</span></button>
    <div id="terminalBody" class="terminal-body" hidden>
      <div class="terminal-toolbar">
        <span id="runnerSlots" class="mono"></span>
        <label class="checkbox-row"><input id="logAutoScroll" type="checkbox" checked />自动滚动</label>
        <button class="btn btn-ghost btn-sm" onclick="clearLogs()" aria-label="清空当前日志视图">清空日志</button>
      </div>
      <div class="log-box" id="runnerLogsBox" role="log" aria-label="实时运行日志" aria-live="off" tabindex="0">等待任务启动…</div>
    </div>
  </section>
</div>

<!-- Floating Bulk Action Bar (ISS-001) -->
<div id="floatingBulkBar" class="floating-bulk-bar">
  <span style="font-weight: 700; font-size: 13.5px;">已勾选 <b id="selectedCountText" style="color: var(--primary);">0</b> 个账号</span>
  <button class="btn btn-primary btn-sm" onclick="batchSelectedAction('verify')">核验所选</button>
  <button class="btn btn-secondary btn-sm" onclick="batchSelectedAction('check_mailbox')">测试邮箱</button>
  <button class="btn btn-ghost btn-sm" onclick="batchSelectedAction('requeue_login')">设为仅登录</button>
  <button class="btn btn-ghost btn-sm" onclick="batchSelectedAction('requeue')">重新注册</button>
  <button class="btn btn-danger btn-sm" onclick="batchSelectedAction('delete')">删除</button>
  <button class="btn btn-ghost btn-sm" onclick="clearJobSelection()">取消选择</button>
</div>

<!-- Right Slide-over Drawer for Single Job Details & Password Edit (ISS-001) -->
<div id="drawerBackdrop" class="drawer-backdrop" onclick="closeJobDrawer()"></div>
<aside id="jobDrawer" class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawerEmailTitle" aria-hidden="true" inert>
  <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:12px; margin-bottom:16px;">
    <div>
      <div style="font-size:16px; font-weight:800;" id="drawerEmailTitle">账号详情</div>
      <div style="font-size:12px; color:var(--text-muted);" class="mono" id="drawerSubMeta"></div>
    </div>
    <button class="btn btn-ghost btn-sm" onclick="closeJobDrawer()">关闭 · Esc</button>
  </div>

  <div id="drawerQuickActions" class="btn-row" style="margin-bottom: 16px;"></div>

  <div class="surface-section" style="padding:0 0 16px; margin-bottom:16px;">
    <div class="section-title">加密凭证</div>
    <div class="field">
      <label for="drawerApiKey">提取结果</label>
      <div style="display:flex; gap:6px;">
        <input type="password" id="drawerApiKey" class="mono" readonly style="flex:1; color: var(--success);" />
        <button class="btn btn-secondary btn-sm" onclick="copyJobField(STATE.activeDrawerJobId, 'api_key')">复制</button>
      </div>
    </div>
    <div class="grid-2">
      <div class="field" style="margin-bottom:0;">
        <label for="drawerAgnesPwd">平台密码</label>
        <input type="password" id="drawerAgnesPwd" autocomplete="new-password" class="mono" placeholder="输入新平台登录密码（留空不改）" />
      </div>
      <div class="field" style="margin-bottom:0;">
        <label for="drawerMailboxPwd">邮箱密码</label>
        <input type="password" id="drawerMailboxPwd" autocomplete="new-password" class="mono" placeholder="输入新邮箱密码（留空不改）" />
      </div>
    </div>
    <div class="btn-row" style="margin-top: 10px;">
      <button class="btn btn-primary btn-sm" onclick="saveDrawerPassword()" aria-label="💾 保存修改后的密码到加密库">保存密码</button>
      <button class="btn btn-secondary btn-sm" onclick="copyJobField(STATE.activeDrawerJobId, 'agnes_password')">复制平台密码</button>
      <button id="drawerReveal" class="btn btn-secondary btn-sm" onclick="toggleDrawerSecrets()">显示当前凭证</button>
    </div>
  </div>

  <div>
    <div class="section-title">执行时间线</div>
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

function toggleTerminal() {
  const button = document.getElementById('terminalToggle');
  const body = document.getElementById('terminalBody');
  const expanded = button.getAttribute('aria-expanded') !== 'true';
  button.setAttribute('aria-expanded', String(expanded));
  body.hidden = !expanded;
  localStorage.setItem('agnes-terminal-open', String(expanded));
  syncTerminalHeight();
  if (expanded && document.getElementById('logAutoScroll').checked) {
    const logs = document.getElementById('runnerLogsBox');
    logs.scrollTop = logs.scrollHeight;
  }
}

function syncTerminalHeight() {
  document.documentElement.style.setProperty('--terminal-height', document.getElementById('terminalDock').offsetHeight + 'px');
}

async function copyText(text, label = '内容') {
  if (!text) {
    showToast(`没有可复制的${label}`, true);
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    showToast(`已复制${label}到剪贴板`);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const copied = document.execCommand('copy');
    ta.remove();
    showToast(copied ? `已复制${label}到剪贴板` : '浏览器未允许复制，请手动复制。', !copied);
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
  document.querySelectorAll('.nav-item').forEach(b => b.removeAttribute('aria-current'));
  if (btn) { btn.classList.add('active'); btn.setAttribute('aria-current', 'page'); }
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
    document.getElementById('statPending').textContent = `待执行 ${pending}`;
    document.getElementById('statRunning').textContent = running;
    document.getElementById('statReview').textContent = review;
    document.getElementById('statFailed').textContent = `失败/跳过: ${failed}`;

    // Progress bar
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
    document.getElementById('progressPercentText').textContent = `完成率 ${pct}%`;
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
      document.getElementById('statProxySummary').textContent = '直连';
      document.getElementById('topIpCapsuleText').textContent = '本机直连';
      document.getElementById('activeProxyNodeTitle').textContent = '本机直连';
      document.getElementById('activeProxyServerSub').textContent = '未启用代理池';
      document.getElementById('activeProxyWindowLabel').textContent = '本轮进度：—';
      document.getElementById('activeProxyCountdownLabel').textContent = '未启用轮换';
      document.getElementById('activeProxyProgressBar').style.width = '0%';
    } else {
      const rotation = rotationProgress(np, poolCfg);
      const ipText = np ? (np.last_ip || np.server) : '无可用健康代理';
      document.getElementById('statProxySummary').textContent = `${p.healthy}/${p.total}`;
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
    const slots = data.runner.slots || [];
    document.getElementById('terminalSlotSummary').textContent = `${slots.length}/${data.settings.concurrency} 槽位`;
    document.getElementById('runnerSlots').textContent = `运行槽位 ${slots.length}/${data.settings.concurrency}` + (slots.length ? ' · ' + slots.map(j => `${j.user_id}: ${j.phase}`).join(' · ') : ' · 空闲');
    [['statTotal','statBatchCount'],['statSucceeded','statWithKey'],['statRunning','statPending'],['statReview','statFailed'],['statProxySummary','statProxyRotation']].forEach(([value, detail]) => {
      document.getElementById(value).closest('.telemetry-item').title = document.getElementById(detail).textContent;
    });
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

function setSegments(options, selected) {
  Object.entries(options).forEach(([id, value]) => {
    const button = document.getElementById(id);
    button.classList.toggle('selected', value === selected);
    button.setAttribute('aria-pressed', String(value === selected));
  });
}

function selectImportMode(mode) {
  document.getElementById('importMode').value = mode;
  setSegments({modeCardRegister: 'register', modeCardExisting: 'existing_login'}, mode);
  updateImportPreview();
}

function selectVerifyMode(mode) {
  document.getElementById('cfgVerifyMode').value = mode;
  setSegments({vCardAuto: 'auto_mailbox', vCardManual: 'manual', vCardNone: 'none'}, mode);
  if (mode === 'manual') document.getElementById('cfgHeadless').value = 'false';
}

function selectLoginVerifyMode(mode) {
  document.getElementById('cfgLoginVerifyMode').value = mode;
  setSegments({lCardStrict: 'strict_identity', lCardSelector: 'selector_only', lCardToken: 'url_or_token', iLoginStrict: 'strict_identity', iLoginSelector: 'selector_only', iLoginToken: 'url_or_token'}, mode);
  document.getElementById('importLoginVerifyMode').value=mode;
}

function selectProxyRotateMode(mode) {
  document.getElementById('cfgProxyRotateMode').value = mode;
  setSegments({pModeResult: 'result_reached', pModeExec: 'execution_count', pModeBoth: 'both'}, mode);
  document.getElementById('proxyThresholdLabel').textContent = mode === 'execution_count' ? '执行阈值' : '结果阈值';
  document.getElementById('cfgProxyExecLimit').disabled = mode !== 'both';
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
    out.textContent = '请输入正则表达式';
    return;
  }
  try {
    const re = new RegExp(pat);
    if(re.test('')) {out.style.color='var(--danger)';out.textContent='正则不能匹配空文本';return;}
    const m = re.exec(sample);
    if (m) {
      out.style.color = 'var(--success)';
      out.innerHTML = `匹配成功 · <mark>${esc(m[0])}</mark><div style="margin-top:6px;color:var(--text-muted)">${esc(sample.slice(0,m.index))}<mark>${esc(m[0])}</mark>${esc(sample.slice(m.index+m[0].length))}</div>`;
    } else {
      out.style.color = 'var(--danger)';
      out.textContent = '未匹配到结果';
    }
  } catch (e) {
    out.style.color = 'var(--danger)';
    out.textContent = `正则语法错误: ${e.message}`;
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
    ['click', '点击元素'],
    ['check', '勾选复选框'],
    ['fill', '填写输入框'],
    ['wait_selector', '等待元素'],
    ['wait_ms', '等待毫秒'],
    ['goto', '跳转网址'],
    ['press', '键盘按键'],
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

  summaryBadge.textContent = `${rows.length} 行 · 有效 ${validCount} 条 · 异常 ${errorCount} 条`;
  summaryBadge.className = 'badge ' + (errorCount > 0 ? 'badge-danger' : (validCount > 0 ? 'badge-success' : 'badge-muted'));
  STATE.importPreview = {validCount,errorCount};
  document.getElementById('importSubmit').disabled = !validCount || errorCount > 0;

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted);">暂无数据</td></tr>';
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
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">暂无数据</td></tr>';
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
    showToast('配置已保存，下次启动任务使用新流程。');
    await loadOverview(true);
  } catch (err) {
    showToast(err.message, true);
  }
}

async function resetFlowDefaults() {
  if (!confirm('恢复官方流程会覆盖尚未保存的流程修改，确定恢复吗？')) return;
  try {
    await api('/api/config/reset-defaults', { method: 'POST', body: '{}' });
    showToast('已恢复 Agnes 官方默认流程');
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
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--text-muted);padding:40px;">暂无匹配任务 <button class="btn btn-secondary btn-sm" onclick="switchTab(\'import\',document.getElementById(\'nav-import\'))">导入账号</button></td></tr>';
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
          <button class="copy-chip" data-copy="email" aria-label="复制邮箱">复制</button>
        </div>
        <div style="font-size:11px; color:var(--text-muted);">${esc(j.user_id)} · ${esc(j.batch)}</div>
      </td>
      <td>${stateBadge(j.state, j.state_label)}</td>
      <td class="mono" style="font-size:12px;">${esc(j.phase)} (尝试:${j.attempts})</td>
      <td class="mono secret-cell">
        <button class="copy-chip" data-copy="agnes_password" aria-label="复制平台密码">${show ? esc(secret.agnes_password || '未设置') : '••••••'}</button>
      </td>
      <td class="mono secret-cell">
        ${j.has_key ? `<button class="copy-chip" data-copy="api_key" aria-label="复制最终结果">${show ? esc(secret.api_key || '结果已确认') : '••••••（已获取）'}</button>` : '<span style="color:var(--text-muted)">未获取</span>'}
      </td>
      <td class="mono" style="font-size:12px;">${esc(j.proxy_id || '-')}</td>
      <td style="max-width:220px;">
        <div style="font-weight:600; font-size:12px;">${esc(j.error_code || '-')}</div>
        <div style="font-size:11.5px; color:var(--text-muted);">${esc(j.message)}</div>
      </td>
      <td>
        <div class="btn-row">
          <button class="btn btn-ghost btn-sm" data-job-action="verify">核验</button>
          <button class="btn btn-secondary btn-sm" data-reveal-row>${show ? '隐藏' : '显示'}</button>
          <button class="btn btn-ghost btn-sm" data-details>详情</button>
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
      showToast(`已启动 ${ids.length} 个选中账号的登录核验`);
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
      showToast(`已完成 ${ids.length} 个账号的批量操作`);
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
    showToast(res.message || '操作完成');
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
    <button class="btn btn-secondary btn-sm" onclick="jobAction('${jobId}', 'verify')">核验账号</button>
    <button class="btn btn-secondary btn-sm" onclick="jobAction('${jobId}', 'check_mailbox')">测试邮箱连接</button>
    <button class="btn btn-ghost btn-sm" onclick="jobAction('${jobId}', 'requeue')">重新注册</button>
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
    showToast(res.message || '密码已更新');
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
    showToast(res.message || '指令已发送');
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
    showToast(`已读取文件: ${file.name}`);
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
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:22px;">暂无代理节点 · 本机直连</td></tr>';
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
    const msg = `成功导入 ${res.imported} 条代理节点`;
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
    showToast('正在检测代理连通性与出口 IP…');
    const res = await api('/api/proxies/check', {
      method: 'POST',
      body: JSON.stringify({ proxy_id: 'all' }),
    });
    const healthy = (res.results || []).filter(r => r.status === 'HEALTHY').length;
    showToast(`检测完成：${healthy} / ${(res.results || []).length} 条代理可用`);
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
    showToast('代理池操作已生效');
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
    input.hidden=true;
    const label=input.closest('.field').querySelector('label');
    value.id=id+'Editor';
    if(label) label.htmlFor=value.id;
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
  document.querySelectorAll('#flowPipeline > .pipe-step').forEach((step,i)=>{
    const kind=step.dataset.flowKind, stage=step.dataset.stage;
    step.classList.add('collapsed');
    const head=step.querySelector('.pipe-head'), body=step.children[1];
    body.id='flowStepBody'+i;
    head.tabIndex=0;head.setAttribute('role','button');head.setAttribute('aria-expanded','false');head.setAttribute('aria-controls',body.id);
    const toggle=()=>{step.classList.toggle('collapsed');head.setAttribute('aria-expanded',String(!step.classList.contains('collapsed')));};
    head.addEventListener('click',toggle);head.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggle();}});
    const zone=document.createElement('div');zone.className='insert-zone';
    zone.innerHTML=`<button class="btn btn-ghost btn-sm" aria-label="+ 在此插入自定义动作" title="在此插入自定义动作" onclick="addCustomStep('${kind}','${stage}')">+ 动作</button><div data-custom-kind="${kind}" data-custom-stage="${stage}"></div>`;
    step.after(zone);
  });
}

function initSegmentedControls() {
  document.querySelectorAll('.segmented').forEach(group=>{
    group.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      const buttons=Array.from(group.querySelectorAll('button'));
      const current=buttons.indexOf(document.activeElement);
      if(current<0) return;
      event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(current+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;
      buttons[next].focus();buttons[next].click();
    });
  });
}

window.addEventListener('DOMContentLoaded', async () => {
  const savedTheme=localStorage.getItem('agnes-theme');if(['dark','light'].includes(savedTheme)) document.documentElement.dataset.theme=savedTheme;
  initSelectorHelpers();initPipeline();initSegmentedControls();updateImportPreview();
  if(localStorage.getItem('agnes-terminal-open')==='true') toggleTerminal();
  document.getElementById('nav-dashboard').setAttribute('aria-current','page');
  new ResizeObserver(syncTerminalHeight).observe(document.getElementById('terminalDock'));
  syncTerminalHeight();
  const pager=document.createElement('div');pager.id='jobsPagination';pager.className='btn-row';document.getElementById('jobsTableBody').closest('.table-wrap').after(pager);
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
