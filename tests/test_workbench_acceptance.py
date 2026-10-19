from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

from agnes_provisioner.config import Settings, load_settings, save_settings
from agnes_provisioner.proxy import ProxyManager
from agnes_provisioner.storage import Storage
from agnes_provisioner.users import import_accounts_flexible, parse_accounts_text
from agnes_provisioner.vault import Vault
from agnes_provisioner.web import WebAppController, make_handler

WORKBENCH_TABS = ("dashboard", "import", "flows", "proxies", "delivery")
UI_ARTIFACT_DIRECTORY = Path.home() / "AppData" / "Local" / "Temp" / "opencode"
LOGIN_VALUES = ("strict_identity", "selector_only", "url_or_token")
IMPORT_LOGIN_BUTTONS = ("iLoginStrict", "iLoginSelector", "iLoginToken")
FLOW_LOGIN_BUTTONS = ("lCardStrict", "lCardSelector", "lCardToken")


@pytest.fixture
def workbench(tmp_path):
    config = tmp_path / "config.local.toml"
    save_settings(
        Settings(mode="mock", database=tmp_path / "jobs.db", vault=tmp_path / "vault.dpapi",
                 per_minute=100000, retry_delay_seconds=0), config
    )
    controller = WebAppController(config)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(controller))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with httpx.Client(base_url=base, trust_env=False, timeout=15) as client:
            yield controller, client, base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def chrome_browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def browser_page(workbench, chrome_browser):
    _, _, base = workbench
    context = chrome_browser.new_context(
        viewport={"width": 1440, "height": 1000},
        permissions=["clipboard-read", "clipboard-write"],
        service_workers="block",
    )
    external_requests = []

    def local_requests_only(route):
        if route.request.url.startswith(base + "/"):
            route.continue_()
        else:
            external_requests.append(route.request.url)
            route.abort()

    context.route("**/*", local_requests_only)
    errors = []
    try:
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base)
        page.wait_for_function("STATE.configLoaded")
        yield page
    finally:
        context.close()
        assert errors == []
        assert external_requests == [], "The acceptance browser must stay on its local test server"


def import_demo(controller, batch="demo", content=None):
    controller.import_accounts({
        "content": content or "alice@example.com----Pass1!\nbob@example.com----Pass2!",
        "batch_id": batch,
    })
    return controller.list_jobs(batch, reveal_secrets=True)["jobs"]


def capture_workbench(page, name, measurements=None):
    """Opt-in evidence, always outside the checkout; never serialize config or real paths."""
    enabled = os.environ.get("AGNES_UI_SCREENSHOT", "").strip().lower()
    if enabled in {"", "0", "false", "off", "no"}:
        return
    UI_ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    theme = page.locator("html").get_attribute("data-theme")
    viewport = page.viewport_size
    stem = f"agnes-workbench-{name}-{viewport['width']}-{theme}"
    page.screenshot(
        path=UI_ARTIFACT_DIRECTORY / f"{stem}.png",
        full_page=True,
        animations="disabled",
        style="""
          #toast { visibility: hidden !important; }
          #configPathText { font-size: 0 !important; }
          #configPathText::after { content: '本地测试配置'; font-size: 11px; }
        """,
    )
    evidence = {
        "schema": "agnes-workbench-acceptance-v1",
        "browser": "chrome",
        "browser_version": page.context.browser.version,
        "view": page.locator(".tab-panel.active").get_attribute("id").removeprefix("tab-"),
        "theme": theme,
        "viewport": viewport,
        "measurements": measurements or {},
    }
    (UI_ARTIFACT_DIRECTORY / f"{stem}.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def refresh_workbench(page):
    page.wait_for_function("!STATE.refreshBusy")
    page.evaluate("refreshAll()")
    page.wait_for_function("!STATE.refreshBusy")


def expect_segment_selection(page, button_ids, values, selected):
    for button_id, value in zip(button_ids, values, strict=True):
        expect(page.locator("#" + button_id)).to_have_attribute(
            "aria-pressed", "true" if value == selected else "false"
        )


def expect_login_selection(page, selected):
    expect(page.locator("#cfgLoginVerifyMode")).to_have_value(selected)
    expect(page.locator("#importLoginVerifyMode")).to_have_value(selected)
    expect_segment_selection(page, IMPORT_LOGIN_BUTTONS, LOGIN_VALUES, selected)
    expect_segment_selection(page, FLOW_LOGIN_BUTTONS, LOGIN_VALUES, selected)


def expect_terminal_state(page, expanded):
    expect(page.locator("#terminalToggle")).to_have_attribute(
        "aria-expanded", "true" if expanded else "false"
    )
    body = page.locator("#terminalBody")
    assert body.evaluate("element => element.hidden") == (not expanded)
    if expanded:
        expect(body).to_be_visible()
    else:
        expect(body).to_be_hidden()


def workbench_measurements(page):
    return page.evaluate("""() => {
      const rect = element => {
        const r = element.getBoundingClientRect();
        return {left:r.left, right:r.right, top:r.top, bottom:r.bottom,
                width:r.width, height:r.height};
      };
      const content = rect(document.querySelector('.content-area'));
      const telemetry = rect(document.getElementById('telemetryStrip'));
      const dock = rect(document.getElementById('terminalDock'));
      const active = document.querySelector('.tab-panel.active');
      const dashboard = document.getElementById('tab-dashboard');
      const table = document.getElementById('jobsTableBody').closest('.table-wrap');
      const workspaceTop = Math.max(content.top, telemetry.bottom);
      const workspaceBottom = Math.min(innerHeight, content.bottom, dock.top);
      const availableHeight = Math.max(0, workspaceBottom - workspaceTop);
      const panels = Array.from(document.querySelectorAll(
        '.main-shell, .topbar, .content-area, #telemetryStrip, #terminalDock, '
        + '.tab-panel.active, .tab-panel.active > *, .tab-panel.active .segmented, '
        + '.tab-panel.active .pipeline, .tab-panel.active .table-wrap'
      )).filter(element => element.getClientRects().length).map(element => ({
        hook:element.id || element.classList[0] || element.tagName.toLowerCase(), ...rect(element)
      }));
      const scrollers = Array.from(active.querySelectorAll('.table-wrap')).map(element => ({
        width:element.clientWidth, contentWidth:element.scrollWidth,
        overflow:getComputedStyle(element).overflowX
      }));
      const dashboardRect = rect(dashboard), tableRect = rect(table);
      const dashboardVisibleHeight = Math.max(0,
        Math.min(dashboardRect.bottom, workspaceBottom)
        - Math.max(dashboardRect.top, workspaceTop));
      return {
        rootWidth:document.documentElement.scrollWidth, viewportWidth:innerWidth,
        panels, scrollers, telemetryHeight:telemetry.height,
        workspaceTop, workspaceBottom, availableHeight, dashboard:dashboardRect, table:tableRect,
        dashboardWorkspaceRatio:availableHeight ? dashboardVisibleHeight / availableHeight : 0,
        tableDashboardRatio:dashboardRect.height ? tableRect.height / dashboardRect.height : 0
      };
    }""")


def test_api_privacy_validation_and_consistent_backup(workbench):
    controller, client, _ = workbench
    jobs = import_demo(controller)
    job_id = jobs[0]["job_id"]
    masked = client.get("/api/jobs").json()["jobs"][0]
    assert masked["raw_email"] == masked["agnes_password"] == masked["api_key"] == ""
    assert "Pass1!" not in client.get("/api/overview").text
    search = client.get("/api/jobs?search=alice@example.com").json()["jobs"]
    assert len(search) == 1 and search[0]["raw_email"] == ""
    assert client.post("/api/batches/control", json={"action": "run"}).status_code == 400
    assert client.post("/api/batches/control", json={
        "action": "run", "batch_id": "missing"
    }).status_code == 400
    assert client.post("/api/batches/control", json={
        "action": "run", "batch_id": "demo", "limit": -1
    }).status_code == 400
    password = '  Pa\'ss"<>&!  '
    response = client.post("/api/jobs/action", json={
        "action": "set_password", "job_id": job_id, "agnes_password": password,
    })
    assert response.status_code == 200
    revealed = client.get(f"/api/jobs?job_id={job_id}&reveal_secrets=1").json()["jobs"]
    assert len(revealed) == 1 and revealed[0]["agnes_password"] == password
    raw_db = controller.get_settings().database.read_bytes()
    assert password.encode() not in raw_db
    assert client.post("/api/jobs/action", json={
        "action": "requeue", "job_ids": [job_id]
    }).status_code == 400
    assert client.post("/api/config", json={"key_flow": {"pattern": "["}}).status_code == 400
    assert client.post("/api/config", json=[], headers={
        "Origin": "https://untrusted.example"
    }).status_code == 403
    assert client.post("/api/config", json=[]).status_code == 400
    assert client.post("/api/config", json={"approval": "invalid"}).status_code == 400
    assert client.post("/api/accounts/import", json={"content": None}).status_code == 400
    assert client.get("/api/overview", headers={"Host": "malicious.example"}).status_code == 403
    export = client.get("/api/export?format=csv&batch=demo")
    assert export.status_code == 200 and password not in export.text
    backup = client.post("/api/backup", json={}).json()
    folder = Path(backup["directory"])
    assert (folder / "credentials.dpapi").exists()
    with sqlite3.connect(folder / "agnes.db") as db:
        assert db.execute("SELECT count(*) FROM registration_jobs").fetchone()[0] == 2


def test_csv_retains_credentials_and_source_row_errors(tmp_path):
    text = ('\ufeffuser_id,email,mailbox_password,agnes_password,client_id,refresh_token\n'
            'csv-user,alice@example.com,"mail,pass","platform""pass",client,token\n'
            'bad,not-email,secret,secret,,\n')
    parsed = parse_accounts_text(text)
    assert parsed[0]["mailbox_password"] == "mail,pass"
    assert parsed[0]["agnes_password"] == 'platform"pass'
    assert parsed[1]["row"] == 3 and parsed[1]["error"]
    storage = Storage(tmp_path / "csv.db")
    storage.initialize()
    vault = Vault(tmp_path / "csv.dpapi")
    try:
        report = import_accounts_flexible(storage, vault, text, batch_id="verify-only-batch",
                                         provider="mock", import_mode="existing_login")
        assert report["imported"] == 1 and report["rejected"] == 1
        job = storage.jobs()[0]
        assert job["state"] == "PENDING_VERIFY"
        assert job["phase"] == "REGISTRATION_SUBMITTED"
        record = vault.get(job["secret_ref"])
        assert record["agnes_password"] == 'platform"pass'
        assert record["refresh_token"] == "token"
        assert storage.events(job["job_id"])[-1]["code"] == "EXISTING_ACCOUNT_IMPORT"
        assert parse_accounts_text("a@example.com----p", format_hint="four_part")[0]["error"]
        assert parse_accounts_text("a@example.com----p--------")[0]["error"]
        combined = import_accounts_flexible(
            storage, vault,
            "duplicate@example.com----mail----client----refresh\n"
            "duplicate@example.com----platform", provider="mock",
        )
        assert combined["imported"] == combined["updated"] == 1
        merged = vault.get(combined["user_ids"][0])
        assert merged["refresh_token"] == "refresh" and merged["agnes_password"] == "platform"
    finally:
        storage.close()


def test_iss001_dashboard_selection_copy_drawer_and_responsive(workbench, browser_page):
    controller, _, _ = workbench
    jobs = import_demo(controller)
    page = browser_page
    page.evaluate("refreshAll()")
    page.locator("#batchSelect").select_option("demo")
    page.wait_for_function("STATE.jobs.length === 2")
    page.locator(".job-check").nth(0).check()
    page.locator(".job-check").nth(1).check()
    expect(page.locator("#floatingBulkBar")).to_be_visible()
    expect(page.locator("#selectedCountText")).to_have_text("2")
    page.evaluate("refreshAll()")
    assert page.locator(".job-check:checked").count() == 2
    page.locator("#jobSearchInput").fill(jobs[0]["user_id"])
    page.locator("#jobSearchInput").fill("")
    assert page.locator(".job-check:checked").count() == 2
    page.locator("#jobSearchInput").fill(jobs[0]["email"])
    expect(page.locator(".job-check")).to_have_count(1)
    page.locator("#jobSearchInput").fill("")
    page.locator("[data-copy='agnes_password']").first.click()
    expect(page.locator("#toast")).to_contain_text("已复制")
    assert page.evaluate("navigator.clipboard.readText()") == jobs[0]["agnes_password"]
    assert jobs[0]["agnes_password"] not in page.locator("#jobsTableBody").inner_text()
    page.locator("[data-reveal-row]").first.click()
    expect(page.locator("#jobsTableBody")).to_contain_text(jobs[0]["agnes_password"])
    page.locator("[data-details]").first.click()
    expect(page.locator("#jobDrawer")).to_have_class("drawer open")
    expect(page.locator("#drawerTimelineBox")).to_contain_text("CREATED")
    page.locator("#drawerAgnesPwd").fill('  new"Pass!  ')
    page.get_by_role("button", name="💾 保存修改后的密码到加密库").click()
    expect(page.locator("#toast")).to_contain_text("密码已加密保存")
    page.locator("#drawerReveal").click()
    expect(page.locator("#drawerAgnesPwd")).to_have_value('  new"Pass!  ')
    page.keyboard.press("Escape")
    expect(page.locator("#jobDrawer")).not_to_have_class("drawer open")
    for tab in ["import", "flows", "proxies", "delivery", "dashboard"]:
        page.locator("#nav-" + tab).click()
        expect(page.locator("#tab-" + tab)).to_be_visible()
    page.locator("#terminalToggle").click()
    expect_terminal_state(page, True)
    page.locator("#logAutoScroll").uncheck()
    page.get_by_role("button", name="清空当前日志视图").click()
    expect(page.locator("#runnerLogsBox")).to_contain_text("已清空")
    for width in [360, 768, 1440]:
        page.set_viewport_size({"width": width, "height": 1000})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    capture_workbench(page, "desktop")


def test_iss001_empty_batch_guidance(browser_page):
    page = browser_page
    page.get_by_role("button", name="▶ 开始/继续注册").click()
    expect(page.locator("#toast")).to_contain_text("导入账号")
    expect(page.locator("#tab-import")).to_be_visible()


def test_iss002_pipeline_selector_steps_regex_and_reset(workbench, browser_page):
    controller, _, _ = workbench
    page = browser_page
    page.locator("#nav-flows").click()
    expect(page.locator(".pipe-head")).to_have_count(9)
    page.locator(".pipe-head").filter(has_text="点击切换注册").click()
    helper = page.locator('[data-target="regOpenSelector"]')
    helper.locator("select").select_option("text")
    helper.locator("input").fill('立即 "注册"')
    expect(page.locator("#regOpenSelector")).to_have_value('text="立即 \\"注册\\""')
    insert = page.get_by_role("button", name="+ 在此插入自定义动作")
    insert.nth(2).click()
    first = page.locator('[data-custom-stage="before_code"] .step-box').first
    first.get_by_label("动作类型").select_option("check")
    first.get_by_label("动作选择器").fill("#agree-tos")
    insert.nth(2).click()
    second = page.locator('[data-custom-stage="before_code"] .step-box').nth(1)
    second.get_by_label("动作类型").select_option("wait_ms")
    second.get_by_label("动作值").fill("500")
    second.get_by_role("button", name="↑", exact=True).click()
    page.locator('[data-custom-stage="before_code"] .step-box').first.get_by_label(
        "启用步骤"
    ).uncheck()
    page.locator("#flowPipeline .pipe-head").nth(5).click()
    page.get_by_role("button", name="+ 插入登录自定义动作", exact=True).click()
    login_step = page.locator('[data-custom-kind="login"] .step-box')
    login_step.get_by_label("动作类型").select_option("fill")
    login_step.get_by_label("动作选择器").fill("#alias")
    login_step.get_by_label("动作值").fill("{email}")
    page.get_by_role("button", name="💾 保存全部流程修改", exact=True).click()
    expect(page.locator("#toast")).to_contain_text("配置已保存")
    page.reload()
    page.wait_for_function("STATE.configLoaded")
    cfg = load_settings(controller.config_path)
    steps = cfg.registration_flow.custom_steps
    assert [s.action for s in steps] == ["wait_ms", "check"]
    assert steps[0].value == "500" and not steps[0].enabled
    assert steps[1].selector == "#agree-tos"
    assert cfg.login_flow.custom_steps[0].stage == "before_submit"
    assert cfg.login_flow.custom_steps[0].value == "{email}"
    page.locator("#nav-flows").click()
    page.locator(".pipe-head").last.click()
    page.locator("#keyPattern").fill("sk-[A-Za-z0-9_-]{16,}")
    page.locator("#regexSampleInput").fill('{"data":{"key":"sk-AbCdEf1234567890"}}')
    expect(page.locator("#regexTestResult mark").first).to_have_text("sk-AbCdEf1234567890")
    capture_workbench(page, "flows")
    page.locator("#keyPattern").fill("[")
    expect(page.locator("#regexTestResult")).to_contain_text("语法错误")
    controller.update_config({"manual_verification": True, "verification": {"mode": "manual"}})
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="🔄 一键恢复 Agnes 官方默认流程").click()
    expect(page.locator("#toast")).to_contain_text("恢复 Agnes")
    page.wait_for_function("STATE.regSteps.length === 0")
    assert load_settings(controller.config_path).key_flow.enabled
    assert not load_settings(controller.config_path).manual_verification
    assert load_settings(controller.config_path).verification.mode == "auto_mailbox"


def test_iss003_live_import_existing_login_manual_and_file_drop(workbench, browser_page):
    controller, _, _ = workbench
    page = browser_page
    page.locator("#nav-import").click()
    page.locator("#importAccountsText").fill(
        "oauth@example.com----mail-pass----cid----refresh\n"
        "login@example.com----platform-pass\nnot-an-email"
    )
    expect(page.locator("#importPreviewSummary")).to_contain_text("有效 2")
    expect(page.locator("#importPreviewBody")).to_contain_text("第 3 行")
    expect(page.locator("#importSubmit")).to_be_disabled()
    assert "mail-pass" not in page.locator("#importPreviewBody").inner_text()
    capture_workbench(page, "import")
    page.evaluate("""() => {
      const transfer=new DataTransfer();
      transfer.items.add(new File(['login@example.com----platform-pass'], 'accounts.txt',
                                  {type:'text/plain'}));
      document.getElementById('importDropZone').dispatchEvent(
        new DragEvent('drop',{bubbles:true,dataTransfer:transfer}));
    }""")
    expect(page.locator("#importPreviewSummary")).to_contain_text("有效 1")
    page.locator("#modeCardExisting").click()
    page.locator("#importPasswordRole").select_option("agnes_only")
    page.locator("#importBatchId").fill("verify-only-batch")
    page.locator("#importSubmit").click()
    expect(page.locator("#tab-dashboard")).to_be_visible()
    jobs = controller.list_jobs("verify-only-batch")["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["state"] == "PENDING_VERIFY"
    assert jobs[0]["phase"] == "REGISTRATION_SUBMITTED"
    page.locator("#nav-import").click()
    page.locator("#vCardManual").click()
    expect(page.locator("#cfgHeadless")).to_have_value("false")
    page.get_by_role("button", name="💾 保存验证设置").click()
    expect(page.locator("#toast")).to_contain_text("配置已保存")
    assert not load_settings(controller.config_path).headless
    assert load_settings(controller.config_path).verification.mode == "manual"


def test_iss004_proxy_preview_import_policy_rotate_reset(workbench, browser_page, monkeypatch):
    controller, _, _ = workbench
    page = browser_page

    class LocalProbe:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            return httpx.Response(200, text="203.0.113.10" if "ipinfo" in url else "ok")

    monkeypatch.setattr("agnes_provisioner.proxy.httpx.AsyncClient", LocalProbe)
    page.locator("#nav-proxies").click()
    page.locator("#importProxiesText").fill(
        "http://u1:p1@127.0.0.1:8001\n127.0.0.1:8002:u2:p2\n"
        "http://u3-{session}:p3@127.0.0.1:8003"
    )
    expect(page.locator("#proxyPreviewCount")).to_contain_text("有效 3")
    expect(page.locator("#proxyPreviewBody")).to_contain_text("动态Session换IP")
    assert "p1@" not in page.locator("#proxyPreviewBody").inner_text()
    page.get_by_role("button", name="🌐 确认导入代理池").click()
    expect(page.locator("#proxiesTableBody tr")).to_have_count(3)
    page.get_by_role("button", name="⚡ 并发测速 & 查出口IP").click()
    expect(page.locator("#proxiesTableBody")).to_contain_text("203.0.113.10")
    expect(page.locator("#proxiesTableBody")).to_contain_text("ms")
    capture_workbench(page, "proxies")
    page.locator("#cfgProxyRotateEvery").fill("2")
    page.get_by_role("button", name="💾 保存换 IP 策略设置").click()
    expect(page.locator("#toast")).to_contain_text("配置已保存")
    original = controller.overview()["proxy_summary"]["next_proxy_id"]
    page.get_by_role("button", name="⏭ 立即手动切换到下一个 IP").click()
    page.wait_for_function("STATE.overview.proxies.some(p=>p.generation>0)")
    assert controller.overview()["proxy_summary"]["next_proxy_id"] != original
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="♻️ 重置所有计数与状态").click()
    page.wait_for_function("STATE.overview.proxies.every(p=>p.generation===0)")
    assert all(p["status"] == "HEALTHY" for p in controller.overview()["proxies"])


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("width", [1440, 768, 360])
@pytest.mark.parametrize("tab", WORKBENCH_TABS)
def test_iss005_five_view_responsive_theme_acceptance(workbench, browser_page, tab, width, theme):
    controller, _, _ = workbench
    import_demo(controller, "ui-acceptance", "\n".join(
        f"ui{index:02d}@example.com----DemoPass{index:02d}!" for index in range(1, 13)
    ))
    controller.import_proxies({
        "content": "http://127.0.0.1:8101\nhttp://127.0.0.1:8102\nhttp://127.0.0.1:8103",
    })
    page = browser_page
    if page.locator("html").get_attribute("data-theme") != theme:
        page.get_by_role("button", name="🌓 切换深浅主题", exact=True).click()
    page.set_viewport_size({"width": width, "height": 1000})
    page.reload()
    page.wait_for_function("STATE.configLoaded")
    expect(page.locator("html")).to_have_attribute("data-theme", theme)
    page.locator("#batchSelect").select_option("ui-acceptance")
    page.wait_for_function("STATE.jobs.length === 12")
    page.locator("#nav-" + tab).click()
    expect(page.locator("#tab-" + tab)).to_be_visible()

    measurements = workbench_measurements(page)
    capture_workbench(page, tab, measurements)
    assert measurements["rootWidth"] <= width, measurements
    assert page.locator("#tab-" + tab).evaluate(
        "element => element.scrollWidth <= element.clientWidth"
    ), "Only data tables may scroll horizontally, not the view itself"
    assert measurements["panels"]
    for panel in measurements["panels"]:
        assert panel["left"] >= -1 and panel["right"] <= width + 1, panel
        assert panel["width"] > 0, panel
    for scroller in measurements["scrollers"]:
        if scroller["contentWidth"] > scroller["width"] + 1:
            assert scroller["overflow"] in {"auto", "scroll"}, scroller

    expect(page.locator(".callout, .card-desc, .choice-card")).to_have_count(0)
    titles = page.locator(
        "h1, h2, h3, h4, .card-title, .section-title, .panel-title, .pipe-title, label"
    ).all_text_contents()
    tutorial_or_field_name = re.compile(
        r"第[一二三四五六七八九十0-9]+步|阶段[一二三四五六七八九十0-9]+"
        r"|模式\s*[ABC123]\s*[:：]|`|[a-z][a-z0-9]*(?:_[a-z0-9]+)+"
    )
    assert not [text.strip() for text in titles if tutorial_or_field_name.search(text)]
    expect(page.locator(".segmented[role='group']")).to_have_count(5)
    expect(page.locator(".segment:not(button)")).to_have_count(0)
    for group in page.locator(".segmented").all():
        segments = group.locator("button.segment")
        assert segments.count() in {2, 3}
        expect(group.locator("button.segment[aria-pressed='true']")).to_have_count(1)
        expect(group.locator("button.segment[aria-pressed='false']")).to_have_count(
            segments.count() - 1
        )

    expect(page.locator("#telemetryStrip")).to_be_visible()
    for metric in ("statTotal", "statSucceeded", "statRunning", "statReview", "statProxySummary"):
        expect(page.locator("#telemetryStrip #" + metric)).to_be_visible()
    expect(page.locator("#terminalDock")).to_be_visible()
    assert page.locator("#terminalDock").evaluate("element => !element.closest('.tab-panel')")
    expect_terminal_state(page, False)
    if width == 360:
        assert page.locator("#batchSelect").bounding_box()["width"] >= 140
        if tab == "proxies":
            assert page.locator(".proxy-identity").bounding_box()["width"] >= 300
    if tab == "flows":
        expect(page.locator("#tab-flows .pipeline")).to_have_count(1)
        expect(page.locator("#flowPipeline .pipe-step.collapsed")).to_have_count(9)
    if tab == "dashboard" and width == 1440:
        assert measurements["telemetryHeight"] <= 80
        assert measurements["availableHeight"] > 0
        assert measurements["dashboardWorkspaceRatio"] >= .8, measurements
        assert measurements["tableDashboardRatio"] >= .8, measurements
        assert measurements["dashboard"]["top"] >= measurements["workspaceTop"] - 1
        assert measurements["dashboard"]["bottom"] <= measurements["workspaceBottom"] + 1
        assert measurements["table"]["bottom"] <= measurements["dashboard"]["bottom"] + 1


@pytest.mark.parametrize(("tab", "button_ids", "values", "value_id"), [
    pytest.param("import", ("modeCardRegister", "modeCardExisting"),
                 ("register", "existing_login"), "importMode", id="import-mode"),
    pytest.param("import", ("vCardAuto", "vCardManual", "vCardNone"),
                 ("auto_mailbox", "manual", "none"), "cfgVerifyMode", id="verification-mode"),
    pytest.param("import", IMPORT_LOGIN_BUTTONS, LOGIN_VALUES,
                 "cfgLoginVerifyMode", id="import-login-standard"),
    pytest.param("flows", FLOW_LOGIN_BUTTONS, LOGIN_VALUES,
                 "cfgLoginVerifyMode", id="flow-login-standard"),
    pytest.param("proxies", ("pModeResult", "pModeExec", "pModeBoth"),
                 ("result_reached", "execution_count", "both"),
                 "cfgProxyRotateMode", id="proxy-rotation-mode"),
])
def test_iss005_all_segment_groups_support_mouse_tab_space_and_enter(
    browser_page, tab, button_ids, values, value_id,
):
    page = browser_page
    page.locator("#nav-" + tab).click()
    if tab == "flows":
        page.locator("#flowPipeline .pipe-head").nth(5).click()
    group = page.locator(".segmented").filter(has=page.locator("#" + button_ids[0]))
    expect(group).to_have_count(1)
    expect(group).to_have_attribute("role", "group")
    expect(group.locator("button.segment")).to_have_count(len(button_ids))
    for button_id in button_ids:
        button = page.locator("#" + button_id)
        assert button.evaluate("element => element.tagName === 'BUTTON' && element.tabIndex >= 0")
        expect(button).to_be_visible()
        expect(button).to_be_enabled()

    page.locator("#" + button_ids[-1]).click()
    expect(page.locator("#" + value_id)).to_have_value(values[-1])
    expect_segment_selection(page, button_ids, values, values[-1])
    page.locator("#" + button_ids[0]).focus()
    page.keyboard.press("Tab")
    expect(page.locator("#" + button_ids[1])).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(page.locator("#" + button_ids[0])).to_be_focused()

    for key in ("Space", "Enter"):
        for button_id, value in zip(button_ids, values, strict=True):
            page.locator("#" + button_id).focus()
            page.keyboard.press(key)
            expect(page.locator("#" + value_id)).to_have_value(value)
            expect_segment_selection(page, button_ids, values, value)
            if value_id == "cfgLoginVerifyMode":
                expect_login_selection(page, value)
            if value == "manual":
                expect(page.locator("#cfgHeadless")).to_have_value("false")

    page.locator("#" + button_ids[0]).focus()
    for key, index in (("ArrowRight", 1), ("End", -1), ("Home", 0), ("ArrowLeft", -1)):
        page.keyboard.press(key)
        expect(page.locator("#" + button_ids[index])).to_be_focused()
        expect(page.locator("#" + value_id)).to_have_value(values[index])


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("width", [1440, 768, 360])
def test_iss005_populated_previews_and_expanded_forms_stay_inside_workspace(
    workbench, browser_page, width, theme,
):
    controller, _, _ = workbench
    controller.import_proxies({"content": "http://127.0.0.1:8101"})
    page = browser_page
    page.set_viewport_size({"width": width, "height": 1000})
    if page.locator("html").get_attribute("data-theme") != theme:
        page.get_by_role("button", name="🌓 切换深浅主题", exact=True).click()
    refresh_workbench(page)
    for tab in ("import", "proxies", "flows"):
        page.locator("#nav-" + tab).click()
        if tab == "import":
            page.locator("#importAccountsText").fill(
                "oauth@example.com----mail-pass----client-id----example-refresh\n"
                "login@example.com----platform-pass\ninvalid-email"
            )
            expect(page.locator("#importPreviewSummary")).to_contain_text("有效 2")
            expect(page.locator("#importSubmit")).to_be_disabled()
        elif tab == "proxies":
            page.locator("#importProxiesText").fill(
                "http://user-{session}:pass@127.0.0.1:8101\ninvalid-proxy"
            )
            expect(page.locator("#proxyPreviewCount")).to_contain_text("有效 1")
        else:
            for head in page.locator("#flowPipeline .pipe-head").all():
                head.click()
            page.locator("#keyPattern").fill(".+")
            page.locator("#regexSampleInput").fill("long-example-" + "x" * 500)
            expect(page.locator("#regexTestResult")).to_contain_text("匹配成功")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator("#tab-" + tab).evaluate(
            "element => element.scrollWidth <= element.clientWidth"
        )
        for panel in workbench_measurements(page)["panels"]:
            assert panel["left"] >= -1 and panel["right"] <= width + 1, panel
        capture_workbench(page, tab + "-expanded", workbench_measurements(page))


def test_iss005_login_standard_syncs_both_views_legacy_select_and_saved_config(
    workbench, browser_page,
):
    controller, _, _ = workbench
    page = browser_page
    page.locator("#nav-import").click()
    page.locator("#iLoginSelector").press("Space")
    expect_login_selection(page, "selector_only")
    page.locator("#nav-flows").click()
    page.locator("#flowPipeline .pipe-head").nth(5).click()
    page.locator("#lCardToken").press("Enter")
    expect_login_selection(page, "url_or_token")
    page.get_by_role("button", name="💾 保存全部流程修改", exact=True).click()
    expect(page.locator("#toast")).to_contain_text("配置已保存")
    assert load_settings(controller.config_path).login_flow.verify_mode == "url_or_token"
    page.reload()
    page.wait_for_function("STATE.configLoaded")
    expect_login_selection(page, "url_or_token")

    page.locator("#nav-import").click()
    page.locator("#importLoginVerifyMode").select_option("strict_identity", force=True)
    expect_login_selection(page, "strict_identity")
    page.get_by_role("button", name="💾 保存验证设置", exact=True).click()
    expect(page.locator("#toast")).to_contain_text("配置已保存")
    page.reload()
    page.wait_for_function("STATE.configLoaded")
    expect_login_selection(page, "strict_identity")
    assert load_settings(controller.config_path).login_flow.verify_mode == "strict_identity"


def test_iss005_single_nine_node_pipeline_keyboard_and_visible_insert_hooks(browser_page):
    page = browser_page
    page.locator("#nav-flows").click()
    expect(page.locator("#tab-flows .pipeline")).to_have_count(1)
    pipeline = page.locator("#flowPipeline.pipeline")
    steps = pipeline.locator(":scope > .pipe-step")
    expect(steps).to_have_count(9)
    expect(pipeline.locator(".pipe-num")).to_have_text([str(index) for index in range(1, 10)])
    expect(pipeline.locator(".pipe-step.collapsed")).to_have_count(9)
    expect(pipeline.get_by_role("button", name="+ 在此插入自定义动作", exact=True)).to_have_count(9)
    expected_stages = (
        ("reg", "before_open"), ("reg", "before_fill"), ("reg", "before_code"),
        ("reg", "before_submit"), ("reg", "after_submit"), ("login", "before_submit"),
        ("key", "before_extract"), ("key", "after_create"), ("key", "extract"),
    )
    for index, (kind, stage) in enumerate(expected_stages):
        step = steps.nth(index)
        head = step.locator(".pipe-head")
        expect(head).to_have_attribute("role", "button")
        expect(head).to_have_attribute("aria-expanded", "false")
        expect(head).to_have_attribute("tabindex", "0")
        insertion = step.locator("xpath=following-sibling::*[1]")
        expect(insertion.get_by_role(
            "button", name="+ 在此插入自定义动作", exact=True,
        )).to_be_visible()
        expect(insertion.locator(
            f'[data-custom-kind="{kind}"][data-custom-stage="{stage}"]'
        )).to_have_count(1)
        head.press("Enter")
        expect(head).to_have_attribute("aria-expanded", "true")
        expect(step).not_to_have_class(re.compile(r"\bcollapsed\b"))
        head.press("Space")
        expect(head).to_have_attribute("aria-expanded", "false")
        expect(step).to_have_class(re.compile(r"\bcollapsed\b"))
    expect(page.locator("#keyPattern")).to_be_hidden()
    steps.last.locator(".pipe-head").press("Enter")
    expect(page.locator("#keyPattern")).to_be_visible()
    steps.nth(5).locator(".pipe-head").press("Space")
    expect(page.get_by_role(
        "button", name="+ 插入登录自定义动作", exact=True,
    )).to_be_visible()


def test_iss005_global_terminal_state_survives_navigation_polling_and_reload(browser_page):
    page = browser_page
    toggle = page.get_by_role("button", name="运行终端", exact=True)
    expect(toggle).to_have_attribute("id", "terminalToggle")
    expect(toggle).to_have_attribute("aria-controls", "terminalBody")
    assert toggle.evaluate("element => element.tagName === 'BUTTON'")
    expect_terminal_state(page, False)
    refresh_workbench(page)
    expect_terminal_state(page, False)
    page.reload()
    page.wait_for_function("STATE.configLoaded")
    expect_terminal_state(page, False)

    toggle.press("Enter")
    expect_terminal_state(page, True)
    for control in ("runnerSlots", "logAutoScroll", "runnerLogsBox"):
        expect(page.locator("#terminalDock #terminalBody #" + control)).to_be_visible()
    for tab in WORKBENCH_TABS:
        page.locator("#nav-" + tab).click()
        expect(page.locator("#terminalDock")).to_be_visible()
        expect_terminal_state(page, True)
        refresh_workbench(page)
        expect_terminal_state(page, True)
    page.reload()
    page.wait_for_function("STATE.configLoaded")
    expect_terminal_state(page, True)

    toggle.press("Space")
    expect_terminal_state(page, False)
    refresh_workbench(page)
    expect_terminal_state(page, False)
    page.reload()
    page.wait_for_function("STATE.configLoaded")
    expect_terminal_state(page, False)


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("width", [1440, 768, 360])
def test_iss005_fifty_running_slots_keep_logs_and_controls_accessible(
    workbench, browser_page, width, theme,
):
    controller, _, _ = workbench
    controller.update_config({"concurrency": 50})
    import_demo(controller, "terminal-busy", "\n".join(
        f"busy{index:02d}@example.com----DemoPass{index:02d}!" for index in range(50)
    ))
    # Simulate active slots in this fixture's database, without launching real workers.
    with sqlite3.connect(controller.get_settings().database) as db:
        db.execute("UPDATE registration_jobs SET state='RUNNING', phase='EMAIL_REQUESTED'")
    for index in range(50):
        controller.log(f"并发验收日志 {index:02d}")
    page = browser_page
    page.set_viewport_size({"width": width, "height": 1000})
    if page.locator("html").get_attribute("data-theme") != theme:
        page.get_by_role("button", name="🌓 切换深浅主题", exact=True).click()
    refresh_workbench(page)
    page.wait_for_function("STATE.overview.runner.slots.length === 50")
    page.locator("#terminalToggle").click()
    expect(page.locator("#terminalSlotSummary")).to_have_text("50/50 槽位")
    capture_workbench(page, "terminal-busy", workbench_measurements(page))
    logs = page.locator("#runnerLogsBox")
    assert logs.evaluate("element => element.clientHeight") >= 80
    slots = page.locator("#runnerSlots")
    assert slots.evaluate("element => element.scrollHeight > element.clientHeight")
    assert slots.evaluate("element => getComputedStyle(element).overflowY") == "auto"
    slots.press("End")
    page.wait_for_function("document.getElementById('runnerSlots').scrollTop > 0")
    terminal = page.locator("#terminalBody").bounding_box()
    for control in (page.locator("#logAutoScroll"), page.get_by_role(
        "button", name="清空当前日志视图", exact=True,
    ), logs):
        rect = control.bounding_box()
        assert terminal["y"] <= rect["y"]
        assert rect["y"] + rect["height"] <= terminal["y"] + terminal["height"]
    page.locator("#logAutoScroll").uncheck()
    page.get_by_role("button", name="清空当前日志视图", exact=True).click()
    expect(logs).to_contain_text("已清空")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator("#terminalToggle").click()
    expect_terminal_state(page, False)


@pytest.mark.parametrize("width", [1440, 768, 360])
def test_iss005_terminal_real_logs_pause_follow_clear_and_keep_audit(
    workbench, browser_page, width,
):
    controller, _, _ = workbench
    import_demo(controller, "terminal-acceptance")
    page = browser_page
    page.set_viewport_size({"width": width, "height": 1000})
    page.locator("#terminalToggle").click()
    expect_terminal_state(page, True)
    auto_scroll = page.locator("#logAutoScroll")
    box = page.locator("#runnerLogsBox")
    expect(auto_scroll).to_be_checked()
    for index in range(50):
        controller.log(f"验收日志 {index:03d} · 已完成本地模拟步骤")
    refresh_workbench(page)
    expect(box).to_contain_text("验收日志 049")
    assert box.evaluate("element => element.scrollHeight > element.clientHeight")
    page.wait_for_function("""() => {
      const box = document.getElementById('runnerLogsBox');
      return box.scrollHeight - box.clientHeight - box.scrollTop <= 1;
    }""")

    auto_scroll.uncheck()
    box.evaluate("element => { element.scrollTop = 0; }")
    controller.log("终端滚动暂停标记")
    refresh_workbench(page)
    expect(box).to_contain_text("终端滚动暂停标记")
    assert box.evaluate("element => element.scrollTop") == 0
    auto_scroll.check()
    controller.log("终端自动跟随标记")
    refresh_workbench(page)
    expect(box).to_contain_text("终端自动跟随标记")
    page.wait_for_function("""() => {
      const box = document.getElementById('runnerLogsBox');
      return box.scrollHeight - box.clientHeight - box.scrollTop <= 1;
    }""")

    before = controller.overview()
    page.get_by_role("button", name="清空当前日志视图", exact=True).click()
    expect(box).to_contain_text("已清空")
    after = controller.overview()
    assert before["runner"]["logs"] == after["runner"]["logs"]
    assert before["runner"]["events"] == after["runner"]["events"]
    assert before["runner"]["events"], "The audit-preservation check needs actual account events"
    refresh_workbench(page)
    expect(box).not_to_contain_text("终端自动跟随标记")
    expect(box).not_to_contain_text("验收日志 049")
    controller.log("清空后的新日志")
    refresh_workbench(page)
    expect(box).to_contain_text("清空后的新日志")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    capture_workbench(page, "terminal", workbench_measurements(page))
    page.locator("#terminalToggle").click()
    expect_terminal_state(page, False)


def test_recovery_does_not_clear_health_checks_or_other_batches(workbench):
    controller, _, _ = workbench
    first_jobs = import_demo(controller, "one")
    second_jobs = import_demo(controller, "two", "c@example.com----Pass3!")
    storage = Storage(controller.get_settings().database)
    manager = ProxyManager(storage)
    try:
        manager.import_text("one|127.0.0.1:8101\ntwo|127.0.0.1:8102\ncheck|127.0.0.1:8103")
        assert manager.acquire(first_jobs[0]["job_id"], "one")
        assert manager.acquire(second_jobs[0]["job_id"], "two")
        assert manager.acquire(f"health-check:{time.time():.6f}:fixture", "check")
        storage.recover("one")
        rows = {p["id"]: p for p in manager.list()}
        assert not rows["one"]["leased"]
        assert rows["two"]["leased"] and rows["check"]["leased"]
        overview = controller.overview()
        assert overview["proxy_summary"]["next_proxy_id"] == "one"
        assert controller.overview("two")["summary"]["total"] == 1
    finally:
        storage.close()


def test_preview_xss_and_quoted_csv_credentials_are_safe(workbench, browser_page):
    controller, _, _ = workbench
    page = browser_page
    page.locator("#nav-import").click()
    password = '<img src=x onerror="window.previewPwned=true">'
    content = ('email,mailbox_password,agnes_password,client_id,refresh_token\n'
               f'alice@example.com,"mail,pass","{password.replace(chr(34), chr(34) * 2)}",c,t')
    page.locator("#importAccountsText").fill(content)
    expect(page.locator("#importPreviewSummary")).to_contain_text("有效 1")
    assert page.locator("#importPreviewBody img").count() == 0
    assert page.evaluate("window.previewPwned") is None
    page.locator("#importSubmit").click()
    expect(page.locator("#tab-dashboard")).to_be_visible()
    job = controller.list_jobs("batch-main", reveal_secrets=True)["jobs"][0]
    assert job["agnes_password"] == password
    page.locator("[data-reveal-row]").click()
    expect(page.locator("#jobsTableBody")).to_contain_text(password)
    assert page.locator("#jobsTableBody img").count() == 0
    assert page.evaluate("window.previewPwned") is None


def test_selected_mock_verification_runs_only_selected_account(workbench):
    controller, client, _ = workbench
    jobs = import_demo(controller)
    response = client.post("/api/jobs/action", json={
        "action": "verify", "job_id": jobs[1]["job_id"]
    })
    assert response.status_code == 200
    deadline = time.monotonic() + 10
    while controller.runner_running and time.monotonic() < deadline:
        time.sleep(.05)
    assert not controller.runner_running and not controller.last_error
    final = controller.list_jobs("demo")["jobs"]
    assert final[0]["state"] == "PENDING"
    assert final[1]["state"] != "PENDING"


def test_web_cli_startup_is_ready_and_shuts_down(tmp_path):
    config = tmp_path / "config.local.toml"
    save_settings(Settings(database=tmp_path / "jobs.db", vault=tmp_path / "vault.dpapi"), config)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-c", "from agnes_provisioner.cli import main;main()",
         "--config", str(config), "web", "--port", str(port), "--no-browser"],
        cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
            deadline = time.monotonic() + 15
            while True:
                try:
                    response = client.get("/api/overview")
                    break
                except httpx.ConnectError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise AssertionError("Web CLI did not become ready") from None
                    time.sleep(.05)
            assert response.status_code == 200
            assert response.json()["summary"]["total"] == 0
            assert "Agnes 工作台" in client.get("/").text
    finally:
        process.terminate()
        process.communicate(timeout=10)
        assert process.poll() is not None
