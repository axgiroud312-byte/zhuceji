"""Real Chrome interactions against a controlled runtime HTTP contract mock.

These verify the UI, not backend execution, persistence, mailbox or proxy services.
The integration owner separately exercises the same UI against the real runtime API.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from agnes_provisioner.web_ui import WEB_HTML

ARTIFACTS = Path.home() / "AppData/Local/Temp/opencode"
SCRIPT = {
    "api_version": 1, "id": "example", "site_id": "example.test", "name": "本地示例",
    "version": "1.0.0", "entrypoint": "run", "resources": {"mailbox": True, "proxy": True},
    "parameters": {"timeout": 30, "nickname": "demo", "enabled": True},
    "result_fields": [
        {"key": "email", "label": "邮箱", "type": "string", "sensitive": False},
        {"key": "token", "label": "访问凭证", "type": "string", "sensitive": True},
        {"key": "credits", "label": "额度", "type": "integer", "sensitive": False},
    ], "dependencies": [],
}
SECRET = "test-only-private-token"
XSS = '<img src=x onerror="window.pwned=true">'


class RuntimeMock:
    def __init__(self):
        self.scripts = []
        self.resources = []
        self.batches = []
        self.active = None
        self.tasks = {}
        self.events = {}
        self.calls = []
        self.start_error = None
        self.fail_start_response = False

    def ready(self):
        self.scripts = [copy.deepcopy(SCRIPT)]
        self.resources = [
            {"id": "mail", "kind": "mailbox", "name": "Outlook 主邮箱", "status": "READY",
             "summary": "可用邮箱 80"},
            {"id": "proxy", "kind": "proxy", "name": "动态代理", "status": "READY",
             "summary": "已检查 · 动态会话"},
        ]

    def batch(self, batch_id="batch-001", count=52, state="COMPLETED"):
        batch = {"id": batch_id, "site_id": SCRIPT["site_id"], "script_id": SCRIPT["id"],
                 "version": "1.0.0", "state": state, "count": count,
                 "created_at": "2026-10-19T14:30:00+08:00"}
        self.batches.insert(0, batch)
        self.tasks[batch_id] = [
            {"id": f"{batch_id}-task-{i}", "index": i,
             "state": "FAILED" if i in (3, 7, 13) else "SUCCEEDED",
             "stage": "verify" if i in (3, 7, 13) else "complete",
             "message": "验证码等待超时" if i in (3, 7, 13) else "结果已保存",
             "results": {"email": f"user{i}@example.com", "token": SECRET, "credits": i}}
            for i in range(1, count + 1)
        ]
        self.events[batch_id] = [
            {"id": i, "at": "2026-10-19T14:32:08+08:00",
             "task_id": f"{batch_id}-task-{1 if i < 210 else 3}", "stage": "verify",
             "level": "info" if i < 210 else "error", "message": f"事件 {i} · {XSS}",
             "details": "检查邮件响应：" + "technical details " * 35}
            for i in range(1, 221)
        ]
        if state == "RUNNING":
            self.active = batch
        return batch

    def handle(self, route):
        request = route.request
        url = urlsplit(request.url)
        if url.path == "/":
            route.fulfill(content_type="text/html; charset=utf-8", body=WEB_HTML)
            return
        assert url.path.startswith("/api/runtime/"), request.url
        path = url.path.removeprefix("/api/runtime/")
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        body = request.post_data_json if request.method == "POST" else None
        self.calls.append((path, query, body))
        data, status = {}, 200
        if path == "overview":
            data = {"scripts": self.scripts, "resources": self.resources,
                    "batches": self.batches, "active": self.active}
        elif path == "scripts/import":
            if any(s["id"] == body["manifest"]["id"] and
                   s["version"] == body["manifest"]["version"] for s in self.scripts):
                data, status = {"error": "相同 ID / 版本已存在"}, 400
            else:
                self.scripts.append(body["manifest"])
                data = {"script": body["manifest"]}
        elif path == "resources/save":
            resource = {"id": body.get("id", f"resource-{len(self.resources)}"),
                        "name": body["name"], "kind": body["kind"], "status": "UNCHECKED",
                        "summary": "配置已保存"}
            self.resources = [r for r in self.resources if r["id"] != resource["id"]]
            self.resources.append(resource)
            data = {"resource": resource}
        elif path == "resources/check":
            resource = next(r for r in self.resources if r["id"] == body["id"])
            resource["status"] = "READY"
            resource["summary"] = "检查通过"
            data = {"resource": resource}
        elif path == "start":
            if self.start_error:
                data, status = {"error": self.start_error}, 409
            elif self.fail_start_response:
                self.fail_start_response = False
                route.abort("failed")
                return
            else:
                data = {"batch": self.batch(count=body["count"], state="RUNNING")}
        elif path == "stop":
            self.active["state"] = "STOPPING"
            data = {"ok": True}
        elif path == "tasks":
            batch = next(b for b in self.batches if b["id"] == query["batch"])
            all_tasks = self.tasks[batch["id"]]
            tasks = [t for t in all_tasks if
                     (not query.get("state") or t["state"] == query["state"]) and
                     (not query.get("search") or query["search"] in json.dumps(t))]
            summary = {key.lower(): sum(t["state"] == key for t in all_tasks)
                       for key in ("SUCCEEDED", "FAILED", "RUNNING", "PENDING", "UNKNOWN",
                                   "CANCELLED")}
            summary["total"] = len(all_tasks)
            offset, limit = int(query["offset"]), int(query["limit"])
            rows = copy.deepcopy(tasks[offset:offset + limit])
            if query.get("reveal") != "1":
                for task in rows:
                    task["results"]["token"] = "••••••••"
            data = {"tasks": rows, "total": len(tasks), "fields": SCRIPT["result_fields"],
                    "summary": summary, "batch": batch}
        elif path == "events":
            events = [e for e in self.events.get(query["batch"], []) if
                      e["id"] > int(query["after"]) and
                      (not query.get("task") or e["task_id"] == query["task"])][:100]
            data = {"events": events, "cursor": events[-1]["id"] if events else
                    int(query["after"])}
        elif path == "export":
            token = SECRET if query.get("include_secrets") == "1" else "[hidden]"
            route.fulfill(content_type="text/csv", body=f"email,token\na@example.com,{token}\n")
            return
        else:
            raise AssertionError(f"Unexpected runtime endpoint: {path}")
        route.fulfill(status=status, content_type="application/json",
                      body=json.dumps(data, ensure_ascii=False))


@pytest.fixture(scope="module")
def chrome_browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        yield browser
        browser.close()


@pytest.fixture
def runtime_page(chrome_browser):
    context = chrome_browser.new_context(viewport={"width": 1440, "height": 1000},
                                         service_workers="block")
    page = context.new_page()
    mock = RuntimeMock()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("**/*", mock.handle)
    yield page, mock
    context.close()
    assert not errors


def visit(page):
    page.goto("http://127.0.0.1:9876/")
    page.wait_for_function("STATE.loaded")


def upload_script(page, manifest=None):
    page.locator("#scriptFile").set_input_files({
        "name": "example.json", "mimeType": "application/json",
        "buffer": json.dumps({"manifest": manifest or SCRIPT,
                              "source": "async def run(ctx): return {}"}).encode(),
    })
    page.locator("#importSubmit").click()


def test_legacy_config_import_form_sends_path_without_credentials(runtime_page):
    page, mock = runtime_page
    visit(page)
    page.locator('[data-view="resources"]').click()
    page.locator("#addResourceButton").click()
    page.locator("#resourceName").fill("旧配置邮箱")
    page.locator("#resourceSource").select_option("legacy")
    page.locator("#legacyConfigPath").fill("config.production.toml")
    page.locator("#resourceSubmit").click()
    expect(page.locator("#resourceDialog")).not_to_be_visible()
    payload = next(body for path, _, body in mock.calls if path == "resources/save")
    assert payload["config"] == {"source": "legacy", "config_path": "config.production.toml"}


def test_runtime_onboarding_resources_import_parameters_start_stop(runtime_page):
    page, mock = runtime_page
    visit(page)
    expect(page.locator("#emptyTitle")).to_have_text("开始你的第一个批次")
    expect(page.locator("#startButton")).to_be_disabled()
    page.locator('[data-view="scripts"]').click()
    page.locator("#importButton").click()
    upload_script(page)
    expect(page.locator("#scriptList")).to_contain_text("本地示例")
    imported = next(body for path, _, body in mock.calls if path == "scripts/import")
    assert imported["manifest"] == SCRIPT and "source" in imported
    page.reload()
    page.wait_for_function("STATE.loaded")
    expect(page.locator("#scriptSelect")).to_contain_text("本地示例")
    page.locator('[data-view="resources"]').click()
    page.locator("#addResourceButton").click()
    page.locator("#resourceName").fill("测试邮箱")
    page.locator("#mailAccounts").fill("a@example.com----mail-pass----client----refresh")
    page.locator("#mailTransport").select_option("imap_oauth")
    expect(page.locator("#imapFields")).to_be_visible()
    page.locator("#resourceSubmit").click()
    expect(page.locator("#resourceList")).to_contain_text("测试邮箱")
    mailbox = next(body for path, _, body in mock.calls if path == "resources/save")
    assert mailbox["config"]["transport"] == "imap_oauth"
    assert mailbox["config"]["imap_port"] == 993
    assert "refresh" not in page.locator("#resourceList").inner_text()
    page.locator("[data-check-resource]").click()
    expect(page.locator("#resourceList")).to_contain_text("检查通过")
    page.locator("#addResourceButton").click()
    page.locator("#resourceName").fill("测试动态代理")
    page.locator("#resourceKind").select_option("proxy")
    page.locator("#proxyServer").fill("http://proxy.example:8000")
    page.locator("#proxyUsername").fill("user")
    page.locator("#proxyPassword").fill("proxy-pass")
    page.locator("#resourceSubmit").click()
    expect(page.locator("#resourceList")).to_contain_text("测试动态代理")
    page.locator('[data-view="run"]').click()
    expect(page.locator("#startButton")).to_be_enabled()
    page.locator("#parametersButton").click()
    page.locator('[data-key="timeout"]').fill("45")
    page.locator('[data-key="enabled"]').uncheck()
    page.locator('#parametersForm button.primary').click()
    page.locator("#taskCount").fill("20")
    page.locator("#startButton").click()
    expect(page.locator("#stopButton")).to_be_visible()
    expect(page.locator("#taskBody tr")).to_have_count(20)
    start = next(body for path, _, body in mock.calls if path == "start")
    assert start["count"] == 20 and start["concurrency"] == 1
    assert start["parameters"] == {"timeout": 45, "nickname": "demo", "enabled": False}
    assert set(start["bindings"]) == {"mailbox", "proxy"}
    expect(page.locator("#scriptSelect")).to_be_disabled()
    expect(page.locator("#taskCount")).to_be_disabled()
    page.locator("#stopButton").click()
    expect(page.locator("#stopButton")).to_have_text("正在收尾…")
    expect(page.locator("#stopButton")).to_be_disabled()
    assert sum(path == "start" for path, _, _ in mock.calls) == 1


def test_runtime_results_filter_pagination_reveal_export_history_and_logs(runtime_page):
    page, mock = runtime_page
    mock.ready()
    mock.batch("history", count=20)
    mock.batch("current", state="RUNNING")
    # Runtime-store timestamps use Python time.time() seconds, not JS milliseconds.
    mock.events["history"][0]["at"] = 1792391528.125
    mock.batches[1]["created_at"] = 1792391528.125
    visit(page)
    expect(page.locator("#taskBody tr")).to_have_count(25)
    expect(page.locator("#taskHead")).to_contain_text("额度")
    assert SECRET not in page.locator("body").inner_text()
    page.locator("#nextPage").click()
    expect(page.locator("#pageInfo")).to_have_text("显示 26–50，共 52 个任务")
    page.locator("#stateFilter").select_option("FAILED")
    expect(page.locator("#taskBody tr")).to_have_count(3)
    page.locator("#taskSearch").fill("user13")
    expect(page.locator("#taskBody tr")).to_have_count(1)
    page.locator("#taskBody [data-task]").first.click()
    expect(page.locator("#detailTitle")).to_have_text("任务 #13")
    page.locator("#revealResults").check()
    expect(page.locator("#taskBody")).to_contain_text(SECRET)
    expect(page.locator("#resultDetail")).to_contain_text(SECRET)
    page.locator("#revealResults").uncheck()
    expect(page.locator("#taskBody")).not_to_contain_text(SECRET)
    expect(page.locator("#resultDetail")).not_to_contain_text(SECRET)
    for reveal in (False, True):
        page.locator("#exportButton").click()
        expect(page.locator("#exportSecrets")).not_to_be_checked()
        if reveal:
            page.locator("#exportSecrets").check()
        with page.expect_download() as download_info:
            page.locator("#exportSubmit").click()
        content = Path(download_info.value.path()).read_text()
        assert (SECRET in content) is reveal
    page.locator("#batchSelect").select_option("history")
    expect(page.locator("#batchState")).to_contain_text("history")
    expect(page.locator("#liveButton")).to_be_visible()
    expect(page.locator("#scriptSelect")).to_be_disabled()
    page.evaluate("refresh()")
    assert page.locator("#batchSelect").input_value() == "history"
    assert page.locator("#taskSearch").input_value() == "user13"
    page.locator("#taskSearch").fill("")
    page.locator("#stateFilter").select_option("")
    expect(page.locator("#taskBody tr")).to_have_count(20)
    page.locator("#taskBody [data-task]").first.click()
    expect(page.locator("#eventList .event")).to_have_count(100)
    assert "2026" in page.locator("#eventList time").first.get_attribute("title")
    assert page.evaluate("asDate('2026-10-19T14:32:08+08:00').getFullYear()") == 2026
    assert page.locator("#eventList img").count() == 0
    assert page.evaluate("window.pwned") is None
    page.locator("#eventList details").first.locator("summary").click()
    page.locator("#followLogs").uncheck()
    page.locator("#eventList").evaluate("e=>e.scrollTop=0")
    page.locator("#moreLogs").click()
    expect(page.locator("#eventList .event")).to_have_count(200)
    assert page.locator("#eventList").evaluate("e=>e.scrollTop") == 0
    assert page.locator("#eventList details").first.get_attribute("open") is not None
    page.evaluate("refresh()")
    assert page.locator("#detailTitle").inner_text() == "任务 #1"
    assert all(q.get("task") == "history-task-1" for path, q, _ in mock.calls
               if path == "events" and q["batch"] == "history")
    page.locator("#liveButton").click()
    expect(page.locator("#batchSelect")).to_have_value("current")


def test_runtime_errors_idempotency_import_update_and_untrusted_text(runtime_page):
    page, mock = runtime_page
    mock.ready()
    mock.scripts[0]["name"] = XSS
    mock.resources[0]["summary"] = XSS
    mock.start_error = "另一个网站正在运行"
    visit(page)
    page.locator("#startButton").click()
    expect(page.locator("#noticeText")).to_have_text("另一个网站正在运行")
    mock.start_error = None
    mock.fail_start_response = True
    page.locator("#startButton").click()
    expect(page.locator("#noticeText")).to_contain_text("fetch")
    page.locator("#startButton").click()
    expect(page.locator("#stopButton")).to_be_visible()
    ids = [body["request_id"] for path, _, body in mock.calls if path == "start"]
    assert len(set(ids)) == 1
    page.locator('[data-view="scripts"]').click()
    assert page.locator("#scriptList img").count() == 0
    page.locator("#importButton").click()
    upload_script(page)
    expect(page.locator("#importError")).to_contain_text("相同 ID / 版本已存在")
    updated = copy.deepcopy(SCRIPT)
    updated["version"] = "2.0.0"
    upload_script(page, updated)
    expect(page.locator("#scriptList .catalog-item")).to_have_count(2)
    assert mock.active["version"] == "1.0.0"
    assert page.locator("#scriptSelect").input_value() == '["example","1.0.0"]'
    page.locator('[data-view="resources"]').click()
    assert page.locator("#resourceList img").count() == 0
    assert page.evaluate("window.pwned") is None


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("width", [1440, 768, 360])
def test_runtime_three_views_responsive_theme_keyboard(runtime_page, width, theme):
    page, mock = runtime_page
    mock.ready()
    mock.batch()
    page.set_viewport_size({"width": width, "height": 900})
    visit(page)
    if theme == "light":
        page.locator("#themeButton").focus()
        page.keyboard.press("Enter")
    assert page.locator("html").get_attribute("data-theme") == theme
    page.locator("#taskBody [data-task]").first.focus()
    page.evaluate("refresh()")
    expect(page.locator("#taskBody [data-task]").first).to_be_focused()
    for view in ("run", "scripts", "resources"):
        page.locator(f'[data-view="{view}"]').focus()
        page.keyboard.press("Space")
        expect(page.locator(f"#view-{view}")).to_be_visible()
        measurements = page.evaluate("""() => ({
          viewport: innerWidth, body: document.documentElement.scrollWidth,
          violations: [...document.querySelectorAll('button,input,select')].filter(el => {
            const r=el.getBoundingClientRect();
            return r.width && r.height && !el.closest('.table-wrap') &&
              (r.left < 0 || r.right > innerWidth+1);
          }).map(el=>el.id || el.textContent)
        })""")
        assert measurements["body"] <= width, measurements
        assert measurements["violations"] == [], measurements
        page.screenshot(path=str(ARTIFACTS / f"runtime-mock-{view}-{width}-{theme}.png"),
                        full_page=True)
    page.locator("#addResourceButton").click()
    expect(page.locator("#resourceDialog")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#resourceDialog")).not_to_be_visible()
    expect(page.locator("#addResourceButton")).to_be_focused()
    page.reload()
    page.wait_for_function("STATE.loaded")
    assert page.locator("html").get_attribute("data-theme") == theme
    assert page.locator('[data-view="flows"]').count() == 0
