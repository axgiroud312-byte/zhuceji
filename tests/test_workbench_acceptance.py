from __future__ import annotations

import os
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


@pytest.fixture
def workbench(tmp_path):
    config = tmp_path / "config.local.toml"
    save_settings(
        Settings(database=tmp_path / "jobs.db", vault=tmp_path / "vault.dpapi",
                 per_minute=100000, retry_delay_seconds=0), config
    )
    controller = WebAppController(config)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(controller))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    with httpx.Client(base_url=base, trust_env=False, timeout=15) as client:
        yield controller, client, base
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture
def browser_page(workbench):
    _, _, base = workbench
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            permissions=["clipboard-read", "clipboard-write"],
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base)
        page.wait_for_function("STATE.configLoaded")
        yield page
        context.close()
        browser.close()
        assert errors == []


def import_demo(controller, batch="demo", content=None):
    controller.import_accounts({
        "content": content or "alice@example.com----Pass1!\nbob@example.com----Pass2!",
        "batch_id": batch,
    })
    return controller.list_jobs(batch, reveal_secrets=True)["jobs"]


def capture_workbench(page, name):
    destination = os.environ.get("AGNES_UI_SCREENSHOT")
    if destination:
        page.locator("#toast").evaluate("element => element.style.display = 'none'")
        page.screenshot(path=Path(destination).with_name(f"agnes-workbench-{name}.png"),
                        full_page=True)


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
