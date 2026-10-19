"""Real UI + real local API acceptance, using fictional resources and local scripts only."""

from __future__ import annotations

import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from agnes_provisioner.config import Settings, save_settings
from agnes_provisioner.web import WebAppController, make_handler


def main():
    root = Path(__file__).resolve().parents[1]
    evidence = Path(os.environ.get("LOCALAPPDATA", str(root / "output"))) / "Temp/opencode"
    from uuid import uuid4
    evidence = evidence / ("runtime-e2e-" + uuid4().hex[:8])
    evidence.mkdir(parents=True)
    config = evidence / "config.toml"
    save_settings(Settings(database=evidence / "runtime.db", vault=evidence / "vault.dpapi"),
                  config)
    controller = WebAppController(config)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(controller))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = {"scope": "real browser + local API; fictional resources; no external requests",
               "screenshots": [], "checks": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            page.wait_for_function("STATE.loaded")
            expect(page.locator("#startButton")).to_be_disabled()
            results["checks"].append("missing resources disables start")
            page.locator('[data-view="resources"]').click()
            page.locator("#addResourceButton").click()
            page.locator("#resourceName").fill("验收邮箱 · 虚构")
            page.locator("#mailAccounts").fill(
                "acceptance@example.com----fiction-password----fiction-client----fiction-token")
            page.locator("#resourceSubmit").click()
            expect(page.locator("#resourceDialog")).not_to_be_visible()
            expect(page.locator("#resourceList")).to_contain_text("验收邮箱")
            assert "fiction-password" not in page.locator("#resourceList").inner_text()
            page.locator("#addResourceButton").click()
            page.locator("#resourceName").fill("验收代理 · 不联网")
            page.locator("#resourceKind").select_option("proxy")
            page.locator("#proxyServer").fill("http://127.0.0.1:9")
            page.locator("#proxyUsername").fill("fiction-user")
            page.locator("#proxyPassword").fill("fiction-proxy-password")
            page.locator("#resourceSubmit").click()
            expect(page.locator("#resourceDialog")).not_to_be_visible()
            results["checks"].append("UI persists mailbox/proxy with hidden credentials")
            page.locator('[data-view="scripts"]').click()
            page.locator("#importButton").click()
            page.locator("#scriptFile").set_input_files(root / "examples/script-demo-accounts.json")
            page.locator("#importSubmit").click()
            expect(page.locator("#importDialog")).not_to_be_visible()
            page.locator('[data-view="run"]').click()
            page.locator("#scriptSelect").select_option('["demo-accounts","1.0.0"]')
            page.locator("#mailboxSelect").select_option("")
            page.locator("#proxySelect").select_option("")
            page.locator("#taskCount").fill("20")
            page.locator("#startButton").click()
            page.wait_for_function("STATE.lastTasks.summary.total===20 && "
                                   "STATE.lastTasks.summary.succeeded===17 && "
                                   "STATE.lastTasks.summary.failed===3", timeout=30000)
            batch_id = page.evaluate("STATE.batch")
            assert len(controller.runtime.store.tasks(batch_id)["tasks"]) == 20
            results["checks"].append("UI imports actual script, runs 20: 17 success / 3 failure")
            page.locator("#stateFilter").select_option("FAILED")
            expect(page.locator("#taskBody tr")).to_have_count(3)
            page.locator("#taskBody [data-task]").first.click()
            expect(page.locator("#eventList")).to_contain_text("预设失败")
            page.locator("#followLogs").uncheck()
            selected = page.evaluate("STATE.selected")
            page.evaluate("refresh()")
            assert page.evaluate("STATE.selected") == selected
            expect(page.locator("#followLogs")).not_to_be_checked()
            results["checks"].append("failure filter, per-task events, selection/follow preserved")
            page.locator("#stateFilter").select_option("")
            expect(page.locator("#taskBody tr")).to_have_count(20)
            assert "demo-password-1" not in page.locator("#taskBody").inner_text()
            page.locator("#revealResults").check()
            expect(page.locator("#taskBody")).to_contain_text("demo-password-1")
            page.locator("#revealResults").uncheck()
            page.locator("#exportButton").click()
            with page.expect_download() as download:
                page.locator("#exportSubmit").click()
            download.value.save_as(evidence / "masked.csv")
            assert "demo-password-1" not in (evidence / "masked.csv").read_text(
                encoding="utf-8-sig")
            results["checks"].append("explicit secret reveal; real CSV download defaults masked")
            page.reload()
            page.wait_for_function("STATE.loaded && STATE.tasks.length===20")
            assert page.evaluate("STATE.overview.resources.length") == 2
            results["checks"].append("page reload restores scripts, resources and batch results")
            for width in (1440, 768, 360):
                page.set_viewport_size({"width": width, "height": 1000})
                for theme in ("dark", "light"):
                    if page.locator("html").get_attribute("data-theme") != theme:
                        page.locator("#themeButton").click()
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"), width
                    expect(page.locator("#startButton")).to_be_visible()
                    filename = f"runtime-{width}-{theme}.png"
                    page.screenshot(path=str(evidence / filename), full_page=True)
                    results["screenshots"].append(filename)
            assert not errors, errors
            results["checks"].append("1440/768/360 × dark/light: no page overflow or JS errors")
            browser.close()
    finally:
        if controller._runtime and controller.runtime.worker:
            controller.runtime.worker.join(20)
        server.shutdown()
        server.server_close()
        thread.join(5)
    (evidence / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(json.dumps({"evidence": str(evidence), **results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
