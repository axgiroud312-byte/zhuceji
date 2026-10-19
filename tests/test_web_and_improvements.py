from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

import httpx
import pytest

from agnes_provisioner.agnes import AgnesAdapter
from agnes_provisioner.config import (
    Approval,
    FlowStep,
    KeyFlow,
    ProxyPoolConfig,
    RegistrationFlow,
    Settings,
    VerificationFlow,
    load_settings,
)
from agnes_provisioner.domain import Result, State, Task
from agnes_provisioner.proxy import ProxyManager
from agnes_provisioner.scheduler import Scheduler
from agnes_provisioner.storage import Storage
from agnes_provisioner.vault import Vault
from agnes_provisioner.web import WebAppController, make_handler


def test_proxy_pool_text_import_and_rotate_after_x_results(tmp_path):
    storage = Storage(tmp_path / "pool.db")
    storage.initialize()
    mgr = ProxyManager(storage)

    raw_proxies = """
    p1|http://user1:pass1@127.0.0.1:9001
    p2|127.0.0.1:9002:user2:pass2
    p3|http://dynuser-{session}:dynpass@127.0.0.1:9003
    """
    res = mgr.import_text(raw_proxies, initial_status="HEALTHY")
    assert res["imported"] == 3

    # Rotate every 2 target results (rotate_mode = "result_reached")
    # 1st execution on p1: result achieved (1/2) -> should NOT rotate yet
    lease1 = mgr.acquire("job-1")
    assert lease1[0] == "p1"
    assert lease1[1]["username"] == "user1"
    rel1 = mgr.release(
        "p1",
        "job-1",
        failed=False,
        result_achieved=True,
        rotate_every=2,
        rotate_mode="result_reached",
    )
    assert not rel1["rotated"] and rel1["window_results"] == 1

    # Next task still picks p1 because p1 has not reached 2 target results yet
    lease2 = mgr.acquire("job-2")
    assert lease2[0] == "p1"
    # Suppose job-2 did NOT achieve result (e.g. pending verify) -> window_results still 1/2
    rel2 = mgr.release(
        "p1",
        "job-2",
        failed=False,
        result_achieved=False,
        rotate_every=2,
        rotate_mode="result_reached",
    )
    assert not rel2["rotated"] and rel2["window_results"] == 1

    # 3rd task still uses p1 and now achieves the 2nd target result (2/2) -> triggers IP rotation!
    lease3 = mgr.acquire("job-3")
    assert lease3[0] == "p1"
    rel3 = mgr.release(
        "p1",
        "job-3",
        failed=False,
        result_achieved=True,
        rotate_every=2,
        rotate_mode="result_reached",
    )
    assert rel3["rotated"] and rel3["generation"] == 1 and rel3["window_results"] == 0

    # 4th task automatically switches to p2!
    lease4 = mgr.acquire("job-4")
    assert lease4[0] == "p2"
    assert lease4[1]["server"] == "http://127.0.0.1:9002"
    assert lease4[1]["username"] == "user2"
    mgr.release(
        "p2",
        "job-4",
        failed=False,
        result_achieved=True,
        rotate_every=1,
        rotate_mode="result_reached",
    )

    # 5th task switches to p3 (which has {session} template)
    lease5 = mgr.acquire("job-5")
    assert lease5[0] == "p3"
    first_session_user = lease5[1]["username"]
    assert first_session_user.startswith("dynuser-") and "{session}" not in first_session_user
    mgr.release(
        "p3",
        "job-5",
        failed=False,
        result_achieved=True,
        rotate_every=1,
        rotate_mode="result_reached",
    )

    # Force rotate p3 again and verify session ID changed (new exit IP)
    mgr.rotate_now("p3")
    lease6 = mgr.acquire("job-6", bound_id="p3")
    assert lease6[1]["username"] != first_session_user
    mgr.release("p3", "job-6")
    storage.close()


@pytest.mark.asyncio
async def test_scheduler_rotates_ip_every_x_results(tmp_path):
    db_path = tmp_path / "sched.db"
    vault_path = tmp_path / "sched.dpapi"
    settings = Settings(
        database=db_path,
        vault=vault_path,
        mode="mock",
        concurrency=1,
        per_minute=100000,
        retry_delay_seconds=0,
        proxy_pool=ProxyPoolConfig(rotate_every=2, rotate_mode="result_reached"),
    )
    storage = Storage(db_path)
    storage.initialize()
    vault = Vault(vault_path)

    from agnes_provisioner.users import import_accounts_flexible

    import_accounts_flexible(
        storage,
        vault,
        "u1@example.com----pass1\nu2@example.com----pass2\nu3@example.com----pass3\nu4@example.com----pass4",
        batch_id="b1",
        provider="mock",
    )
    ProxyManager(storage).import_text(
        "ip1|http://127.0.0.1:8101\nip2|http://127.0.0.1:8102", initial_status="HEALTHY"
    )

    used_proxies = []

    class RecordingAdapter:
        async def execute(self, task, proxy, checkpoint):
            used_proxies.append(proxy["server"])
            await checkpoint("SUBMITTED")
            return Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY", evidence="ok")

        async def close(self):
            pass

    await Scheduler(storage, settings, RecordingAdapter()).run("b1")
    # First 2 tasks use ip1 (8101), then auto-rotates to ip2 (8102) for next 2 tasks!
    assert used_proxies == [
        "http://127.0.0.1:8101",
        "http://127.0.0.1:8101",
        "http://127.0.0.1:8102",
        "http://127.0.0.1:8102",
    ]
    storage.close()


@pytest.mark.asyncio
async def test_custom_registration_and_result_flow_in_browser(tmp_path):
    settings = Settings(
        headless=True,
        browser_timeout_ms=5000,
        verification=VerificationFlow(mode="none"),
        registration_flow=RegistrationFlow(
            entry_path="/signup",
            open_register_selector="none",
            email_selector="#custom-email",
            password_selector="#custom-pass",
            confirm_password_selector="none",
            submit_button_selector="#custom-submit",
            custom_steps=[
                FlowStep(
                    stage="before_code",
                    action="check",
                    selector="#agree-tos",
                    optional=False,
                )
            ],
        ),
        key_flow=KeyFlow(
            enabled=True,
            target_url="/tokens",
            value_selector="#my-token",
            pattern=r"tok_[A-Za-z0-9]{10,}",
            custom_steps=[
                FlowStep(
                    stage="before_extract",
                    action="click",
                    selector="#reveal-btn",
                    optional=False,
                )
            ],
        ),
    )
    vault = Vault(tmp_path / "custom.dpapi")
    vault.set("u1", {"email": "custom@example.com", "agnes_password": "CustomPassword123!"})
    adapter = AgnesAdapter(settings, vault)

    signup_html = """
    <form>
      <input id="custom-email" />
      <input id="custom-pass" type="password" />
      <input id="agree-tos" type="checkbox" />
      <button id="custom-submit" type="button" onclick="
        if(document.getElementById('agree-tos').checked) {
          window.agreed = true;
        }
      ">立即开户</button>
    </form>
    """
    tokens_html = """
    <div>custom@example.com</div>
    <button>退出登录</button>
    <button id="reveal-btn"
      onclick="document.getElementById('my-token').textContent='tok_SuperSecretResult999'">
      显示令牌
    </button>
    <div id="my-token">hidden</div>
    """
    task = Task(
        "j1", "b1", "u1", "custom@example.com", "", "u1", False, 1, "PREPARE", None, None
    )
    try:
        async with adapter.browser.page() as page:

            async def route(interception):
                url = interception.request.url
                body = tokens_html if "/tokens" in url else signup_html
                await interception.fulfill(body=body, content_type="text/html; charset=utf-8")

            await page.route("**/*", route)
            assert await adapter._open_registration(page, [], task=task) is None
            await adapter._fill_registration_form(page, task.email, "CustomPassword123!", task=task)
            assert await page.locator("#agree-tos").is_checked()

            extracted = await adapter.collect_key(task, page, lambda _: None)
            assert extracted == "tok_SuperSecretResult999"
    finally:
        await adapter.close()


def test_web_api_end_to_end(tmp_path):
    cfg_path = tmp_path / "config.local.toml"
    settings = Settings(
        mode="mock",
        database=tmp_path / "data/web.db",
        vault=tmp_path / "data/web.dpapi",
        approval=Approval(reference="web-test", proxies_allowed=True),
    )
    from agnes_provisioner.config import save_settings

    save_settings(settings, cfg_path)
    controller = WebAppController(cfg_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(controller))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=base, timeout=10, trust_env=False) as client:
            # 1. Load Web HTML
            html_res = client.get("/")
            assert html_res.status_code == 200
            assert "Runtime · 脚本运行工作台" in html_res.text

            # 2. Update flow & proxy rotation config via Web API
            cfg_res = client.post(
                "/api/config",
                json={
                    "concurrency": 2,
                    "per_minute": 120,
                    "proxy_pool": {
                        "rotate_every": 3,
                        "rotate_mode": "result_reached",
                    },
                    "registration_flow": {
                        "entry_path": "/custom-signup",
                    },
                },
            )
            assert cfg_res.status_code == 200
            reloaded = load_settings(cfg_path)
            assert reloaded.proxy_pool.rotate_every == 3
            assert reloaded.registration_flow.entry_path == "/custom-signup"

            # 3. Batch import accounts via Web API
            imp_res = client.post(
                "/api/accounts/import",
                json={
                    "content": "a1@example.com----pass1----cid1----tok1\na2@example.com----pass2",
                    "batch_id": "web-batch",
                    "import_mode": "register",
                },
            )
            assert imp_res.status_code == 200
            assert imp_res.json()["report"]["imported"] == 2

            # 4. Batch import proxies via Web API
            prx_res = client.post(
                "/api/proxies/import",
                json={
                    "content": "http://u:p@127.0.0.1:8080\n127.0.0.1:8081:u2:p2",
                    "initial_status": "HEALTHY",
                },
            )
            assert prx_res.status_code == 200
            assert prx_res.json()["imported"] == 2

            # 5. Check overview and jobs
            ov = client.get("/api/overview").json()
            assert ov["summary"]["total"] == 2
            assert ov["proxy_summary"]["total"] == 2
            jobs = client.get("/api/jobs?batch=web-batch&reveal_secrets=1").json()["jobs"]
            assert len(jobs) == 2
            assert jobs[0]["email"] == "a1@example.com"

            # 6. Export CSV via Web API
            exp = client.get("/api/export?format=csv&batch=web-batch&include_secrets=1")
            assert exp.status_code == 200
            assert "a1@example.com" in exp.text
    finally:
        server.shutdown()
        server.server_close()
