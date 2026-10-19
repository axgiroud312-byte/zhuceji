import time

import pytest

from agnes_provisioner.agnes import AgnesAdapter
from agnes_provisioner.browser import BrowserManager
from agnes_provisioner.config import KeyFlow, Settings
from agnes_provisioner.domain import Task
from agnes_provisioner.models import Proxy, User
from agnes_provisioner.proxy import ProxyManager
from agnes_provisioner.storage import Storage
from agnes_provisioner.vault import Vault


def test_domain_rejection_holds_related_tasks_and_revoked_consent_is_not_claimed(tmp_path):
    storage = Storage(tmp_path / "test.db")
    storage.initialize()
    with storage.session.begin() as session:
        session.add_all(
            [
                User(
                    id="a",
                    email="a@example.com",
                    consent=True,
                    consent_reference="test",
                    created_at=time.time(),
                ),
                User(
                    id="b",
                    email="b@example.com",
                    consent=True,
                    consent_reference="test",
                    created_at=time.time(),
                ),
                User(
                    id="c",
                    email="c@example.org",
                    consent=True,
                    consent_reference="test",
                    created_at=time.time(),
                ),
            ]
        )
    storage.create_batch("batch", "mock")
    assert storage.hold_domain("batch", "example.com", "provider refused domain") == 2
    assert storage.batch("batch").action == "PAUSED"
    with storage.session.begin() as session:
        session.get(User, "c").consent = False
    storage.control("batch", "RUNNING")
    assert storage.claim("batch", 3) is None
    assert storage.summary("batch")["states"] == {"CANCELLED": 1, "NEEDS_REVIEW": 2}
    storage.close()


def test_proxy_lease_is_exclusive_and_failure_does_not_release_other_users(tmp_path):
    storage = Storage(tmp_path / "proxies.db")
    storage.initialize()
    with storage.session.begin() as session:
        session.add_all(
            [
                Proxy(id="one", server="http://127.0.0.1:8001", status="HEALTHY"),
                Proxy(id="two", server="http://127.0.0.1:8002", status="HEALTHY"),
            ]
        )
    manager = ProxyManager(storage)
    one = manager.acquire("job-a")
    two = manager.acquire("job-b")
    assert one[0] != two[0]
    assert manager.acquire("job-c") is None
    manager.release(one[0], "job-b", failed=True)
    assert all(row["leased"] for row in manager.list())
    manager.release(one[0], "job-a", failed=True)
    assert manager.acquire("job-c", bound_id=one[0]) is None
    second = next(row for row in manager.list() if row["id"] == two[0])
    assert second["leased"] and second["status"] == "HEALTHY"
    storage.close()


@pytest.mark.asyncio
async def test_browser_isolation_and_redirect_alone_never_prove_identity(tmp_path):
    settings = Settings(
        headless=True, account_identity_selector="#identity", authenticated_selector="#logout"
    )
    manager = BrowserManager(settings)
    adapter = AgnesAdapter(settings, Vault(tmp_path / "unused.dpapi"))
    task = Task(
        "job",
        "batch",
        "user",
        "user@example.com",
        "",
        "user",
        False,
        1,
        "REGISTRATION_SUBMITTED",
        time.time(),
        None,
    )
    html = '<div id="identity">user@example.com</div><button id="logout">退出登录</button>'
    try:
        async with manager.page() as first, manager.page() as second:

            async def route(interception):
                await interception.fulfill(body=html, content_type="text/html")

            await first.route("**/*", route)
            await second.route("**/*", route)
            await first.goto("https://platform.agnes-ai.com/dashboard")
            await first.context.add_cookies(
                [
                    {
                        "name": "session",
                        "value": "first-only",
                        "domain": "platform.agnes-ai.com",
                        "path": "/",
                    }
                ]
            )
            await first.evaluate("localStorage.setItem('user', 'first-only')")
            await second.goto("https://platform.agnes-ai.com/dashboard")
            assert await second.context.cookies() == []
            assert await second.evaluate("localStorage.getItem('user')") is None
            assert await adapter._identity_confirmed(first, task)
            await first.locator("#identity").evaluate("e => e.textContent='other@example.com'")
            assert not await adapter._identity_confirmed(first, task)
            await first.goto("https://platform.agnes-ai.com/login/error")
            assert not await adapter._identity_confirmed(first, task)
            await first.set_content("<div>Registration is not allowed for this email domain</div>")
            error = await adapter._business_error(first)
            assert error.code == "EMAIL_DOMAIN_BLOCKED" and error.pause
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_full_key_is_copied_without_recreating_a_pending_key():
    full_key = "sk-" + "ExampleOnly" * 4
    settings = Settings(
        headless=True,
        key_flow=KeyFlow(
            enabled=True,
            navigation_selector="#navigation",
            value_selector="#masked",
            copy_selector="#copy",
            create_selector="#create",
        ),
    )

    class MemoryVault:
        def get(self, _):
            return {"api_key_creation_started": True}

    adapter = AgnesAdapter(settings, MemoryVault())
    task = Task(
        "job",
        "batch",
        "user",
        "user@example.com",
        "",
        "user",
        False,
        1,
        "KEY_REQUESTED",
        time.time(),
        None,
    )
    phases = []

    async def checkpoint(phase):
        phases.append(phase)

    html = (
        '<button id="navigation">API 密钥</button><div id="masked">sk-Example…Only</div>'
        '<button id="copy" onclick="navigator.clipboard.writeText(\''
        + full_key
        + "')\">复制</button>"
        '<button id="create" onclick="window.created=true">创建</button>'
    )
    try:
        async with adapter.browser.page() as page:

            async def route(interception):
                await interception.fulfill(body=html, content_type="text/html")

            await page.route("**/*", route)
            await page.goto("https://platform.agnes-ai.com/settings/apiKeys")
            await page.evaluate("() => { navigator.clipboard.readText = async () => ''; }")
            assert await adapter.collect_key(task, page, checkpoint) == full_key
            assert phases == []
            assert not await page.evaluate("Boolean(window.created)")
            assert await page.evaluate("navigator.clipboard.readText()") == ""
    finally:
        await adapter.close()


async def test_delayed_registration_interactivity_retries_before_any_mutation(tmp_path):
    settings = Settings(headless=True, browser_timeout_ms=1000)
    adapter = AgnesAdapter(settings, Vault(tmp_path / "unused.dpapi"))
    requests = []
    html = '''<a href="#" onclick="window.clicks=(window.clicks||0)+1;
      if(window.clicks===2){const input=document.createElement('input');
      input.placeholder='请再次输入密码';document.body.append(input);}return false;">注册</a>'''
    try:
        async with adapter.browser.page() as page:
            async def route(request):
                requests.append(request.request.method)
                await request.fulfill(body=html, content_type="text/html; charset=utf-8")

            await page.route("**/*", route)
            assert await adapter._open_registration(page, []) is None
            assert await page.evaluate("window.clicks") == 2
            assert all(method == "GET" for method in requests)
    finally:
        await adapter.close()


async def test_registration_form_accepts_confirm_label_and_enables_send(tmp_path):
    settings = Settings(headless=True, browser_timeout_ms=3000)
    adapter = AgnesAdapter(settings, Vault(tmp_path / "unused.dpapi"))
    html = """
    <a href="#" onclick="document.getElementById('form').hidden=false;return false;">注册</a>
    <form id="form" hidden>
      <input id="email" placeholder="邮箱">
      <input placeholder="密码">
      <input placeholder="请确认您的密码">
      <img alt="send" id="send">
    </form>
    <script>
    document.getElementById('email').addEventListener('blur', (event) => {
      if ((event.target.value || '').includes('@')) {
        document.getElementById('send').alt = 'can send';
      }
    });
    </script>
    """
    try:
        async with adapter.browser.page() as page:
            async def route(request):
                await request.fulfill(body=html, content_type="text/html; charset=utf-8")

            await page.route("**/*", route)
            await page.goto("https://platform.agnes-ai.com/login")
            assert await adapter._open_registration(page, []) is None
            send = await adapter._fill_registration_form(
                page, "probe@example.com", "ExamplePass1"
            )
            assert await send.get_attribute("alt") == "can send"
    finally:
        await adapter.close()
