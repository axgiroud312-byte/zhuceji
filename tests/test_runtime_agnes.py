from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import pytest

from agnes_provisioner import script_contract
from agnes_provisioner.config import KeyFlow, RegistrationFlow, Settings, VerificationFlow
from agnes_provisioner.domain import Result, State
from agnes_provisioner.runtime_agnes import AGNES_PACKAGE, run_agnes
from agnes_provisioner.runtime_resources import ResourceError, ResourceManager
from agnes_provisioner.vault import Vault

ScriptFailure = script_contract.ScriptFailure
validate_package = script_contract.validate_package
validate_results = script_contract.validate_results


class Context:
    def __init__(self, settings, lease, manager=None):
        self.settings, self.lease = settings, lease
        self.mailbox, self.proxy = lease.mailbox, lease.proxy
        self.task_id, self.batch_id, self.index = "test-task", "test-batch", 1
        self.parameters, self.cancelled = {}, False
        self.submitted, self.secrets, self.events = False, [], []
        self.manager = manager

    def mark_submitted(self):
        if self.manager:
            self.manager.mark_submitted(self.lease)
        self.submitted = True
        self.events.append("marked")

    def register_secret(self, value):
        self.secrets.append(value)

    def log(self, message, **kwargs):
        self.events.append(kwargs.get("stage", "run"))


@pytest.fixture
def context(tmp_path):
    settings = Settings(vault=tmp_path / "vault.dpapi", database=tmp_path / "jobs.db")
    vault = Vault(settings.vault)
    vault.set("test-ref", {"email": "fake@example.com", "mailbox_authorized": True,
                           "mailbox_password": "fake-mail-pass", "client_id": "fake-client",
                           "refresh_token": "fake-refresh", "mailbox_transport": "graph"})

    async def validate_proxy():
        ctx.events.append("proxy-validated")

    lease = SimpleNamespace(
        mailbox=SimpleNamespace(email="fake@example.com", secret_ref="test-ref"),
        proxy={"server": "http://127.0.0.1:9999", "username": "fake-user",
               "password": "fake-proxy-pass"}, validate_proxy=validate_proxy,
    )
    ctx = Context(settings, lease)
    return ctx


def test_builtin_is_valid_importable_json_package():
    package = json.loads(json.dumps(AGNES_PACKAGE))
    manifest, source = validate_package(package)
    assert [f.key for f in manifest.result_fields] == ["email", "password", "api_key"]
    assert manifest.resources.mailbox and manifest.resources.proxy
    assert "async def run(ctx)" in source


@pytest.mark.asyncio
async def test_agnes_success_uses_adapter_once_marks_before_request_and_closes(
    context, monkeypatch,
):
    calls = []

    class Adapter:
        def __init__(self, settings, vault):
            self.vault = vault

        async def execute(self, task, proxy, checkpoint):
            calls.append((task, proxy))
            await checkpoint("EMAIL_REQUESTED")
            assert not context.submitted
            await checkpoint("REGISTRATION_SUBMITTED")
            assert context.submitted
            assert context.events.index("proxy-validated") < context.events.index("marked")
            record = self.vault.get(task.secret_ref)
            assert record["runtime_agnes_submitted"]
            record.update(activated=True, api_key="sk-fake-success123456")
            self.vault.set(task.secret_ref, record)
            return Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY")

        async def close(self):
            context.events.append("closed")

    monkeypatch.setattr("agnes_provisioner.runtime_agnes.AgnesAdapter", Adapter)
    namespace = {}
    exec(AGNES_PACKAGE["source"], namespace)
    results = await namespace["run"](context)
    assert validate_results(AGNES_PACKAGE["manifest"]["result_fields"], results) == results
    assert results["email"] == "fake@example.com"
    assert results["password"] in context.secrets
    assert results["api_key"] in context.secrets
    assert "fake-proxy-pass" in context.secrets
    assert context.events[-1] == "closed"
    with pytest.raises(ScriptFailure) as failure:
        await run_agnes(context)
    assert failure.value.code == "AGNES_ALREADY_SUBMITTED"
    assert len(calls) == 1


@pytest.mark.parametrize("phase,state,code", [
    ("EMAIL_REQUESTED", State.RETRY_WAIT, "RATE_LIMIT"),
    ("REGISTRATION_SUBMITTED", State.UNKNOWN, "NETWORK"),
    ("REGISTRATION_SUBMITTED", State.SUCCEEDED, "KEY_PENDING"),
])
@pytest.mark.asyncio
async def test_failure_has_correct_submission_boundary_and_no_retry(
    context, monkeypatch, phase, state, code,
):
    calls = []

    class Adapter:
        def __init__(self, *_):
            pass

        async def execute(self, task, proxy, checkpoint):
            calls.append(task)
            await checkpoint(phase)
            return Result(state, code, "受控失败")

        async def close(self):
            context.events.append("closed")

    monkeypatch.setattr("agnes_provisioner.runtime_agnes.AgnesAdapter", Adapter)
    with pytest.raises(ScriptFailure) as failure:
        await run_agnes(context)
    assert failure.value.code == code
    assert context.submitted == (phase == "REGISTRATION_SUBMITTED")
    assert context.events[-1] == "closed"
    assert len(calls) == 1
    with pytest.raises(ScriptFailure):
        await run_agnes(context)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_proxy_change_stops_before_mutating_registration(context, monkeypatch):
    async def changed():
        raise ResourceError("EGRESS_CHANGED", "changed")

    context.lease.validate_proxy = changed

    class Adapter:
        def __init__(self, *_):
            pass

        async def execute(self, task, proxy, checkpoint):
            await checkpoint("REGISTRATION_SUBMITTED")
            pytest.fail("registration must not happen")

        async def close(self):
            context.events.append("closed")

    monkeypatch.setattr("agnes_provisioner.runtime_agnes.AgnesAdapter", Adapter)
    with pytest.raises(ScriptFailure) as failure:
        await run_agnes(context)
    assert failure.value.code == "EGRESS_CHANGED"
    assert not context.submitted
    assert context.events[-1] == "closed"


@pytest.mark.asyncio
async def test_adapter_cleanup_on_cancellation(context, monkeypatch):
    started = asyncio.Event()

    class Adapter:
        def __init__(self, *_):
            pass

        async def execute(self, task, proxy, checkpoint):
            await checkpoint("REGISTRATION_SUBMITTED")
            started.set()
            await asyncio.Future()

        async def close(self):
            await asyncio.sleep(0)
            context.events.append("closed")

    monkeypatch.setattr("agnes_provisioner.runtime_agnes.AgnesAdapter", Adapter)
    task = asyncio.create_task(run_agnes(context))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert context.submitted
    assert context.events[-1] == "closed"


@pytest.mark.asyncio
@pytest.mark.parametrize("via_runtime", [False, True])
async def test_real_browser_agnes_graph_and_http_proxy_closed_loop(tmp_path, monkeypatch,
                                                                  via_runtime):
    """Actual Chromium + HTTP proxy, controlled Graph responses; zero external service calls."""
    state = {"email_requested": False, "registrations": [], "proxy_checks": 0, "graph_reads": 0}
    email = "browser-test@example.com"
    result_key = "sk-ControlledBrowserResult123456"
    manager = None
    writers = set()
    handlers = set()

    async def serve(reader, writer):
        task = asyncio.current_task()
        handlers.add(task)
        writers.add(writer)
        try:
            headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            lines = headers.decode().split("\r\n")
            method, target, _ = lines[0].split(" ")
            length = next((int(line.split(":", 1)[1]) for line in lines[1:]
                           if line.lower().startswith("content-length:")), 0)
            body = await reader.readexactly(length) if length else b""
            path = urlsplit(target).path
            content_type = "text/html; charset=utf-8"
            if method == "CONNECT":
                status, response = 502, "No external connections in this test"
            elif path == "/ip":
                state["proxy_checks"] += 1
                status, response = 200, "203.0.113.9"
            elif path == "/login":
                status, response = 200, """
                    <!doctype html><html><body>
                    <input id="email"><input id="password" type="password">
                    <input id="confirm" type="password"><input id="code">
                    <button id="send" onclick="fetch('/verify',{method:'POST'})">Send</button>
                    <button id="register" onclick="register()">Register</button>
                    <script>
                    async function register(){
                      const payload={email:document.querySelector('#email').value,
                        code:document.querySelector('#code').value};
                      const r=await fetch('/register',{method:'POST',body:JSON.stringify(payload)});
                      if(r.ok)location.href='/dashboard';
                    }
                    </script></body></html>
                """
            elif path == "/verify":
                state["email_requested"] = True
                status, response = 200, '{}'
                content_type = "application/json"
            elif path == "/register":
                payload = json.loads(body)
                with manager._connection() as db:
                    marked = db.execute("SELECT submitted FROM resource_leases "
                                        "WHERE email=? ORDER BY created_at DESC LIMIT 1",
                                        (email,)).fetchone()[0]
                    if via_runtime:
                        marked = marked and db.execute(
                            "SELECT submitted FROM rt_tasks LIMIT 1").fetchone()[0]
                state["registrations"].append({**payload, "marked_before_request": bool(marked)})
                status = 200 if payload == {"email": email, "code": "314159"} and marked else 400
                response, content_type = '{"code":200}', "application/json"
            elif path == "/dashboard":
                status, response = 200, (f'<div id="identity">{email}</div>'
                                         '<button id="logout">Log out</button>'
                                         f'<div id="key">{result_key}</div>')
            else:
                status, response = 404, "Not found"
            data = response.encode()
            writer.write((f"HTTP/1.1 {status} Test\r\nContent-Length: {len(data)}\r\n"
                          f"Content-Type: {content_type}\r\nConnection: close\r\n\r\n").encode()
                         + data)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, TimeoutError):
            pass
        finally:
            writer.close()
            writers.discard(writer)
            handlers.discard(task)

    def graph(request):
        assert request.url.host in {"login.microsoftonline.com", "graph.microsoft.com"}
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "controlled-access",
                                             "refresh_token": "controlled-rotated-refresh"})
        state["graph_reads"] += 1
        if request.url.path.endswith("/messages/test-message"):
            return httpx.Response(200, json={"body": {"content": "Your code is 314159"}})
        messages = []
        if state["email_requested"] and "inbox" in request.url.path:
            messages = [{"id": "test-message", "from": {
                "emailAddress": {"address": "verify@agnes-ai.com"}},
                "toRecipients": [{"emailAddress": {"address": email}}]}]
        return httpx.Response(200, json={"value": messages})

    actual_client = httpx.Client
    monkeypatch.setattr(
        "agnes_provisioner.mailbox.httpx.Client",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(graph), **kwargs),
    )
    settings = Settings(
        database=tmp_path / "runtime.db", vault=tmp_path / "vault.dpapi", headless=True,
        base_url="http://runtime-browser.test", allow_custom_base_url=True,
        browser_timeout_ms=3000, verification_timeout_seconds=5,
        cache_public_assets=False, block_analytics=False,
        registration_flow=RegistrationFlow(
            open_register_selector="none", email_selector="#email", password_selector="#password",
            confirm_password_selector="#confirm", send_code_ready_selector="#send",
            send_code_click_selector="#send", code_input_selector="#code",
            submit_button_selector="#register",
        ),
        verification=VerificationFlow(sender_domain="agnes-ai.com"),
        key_flow=KeyFlow(enabled=True, extract_mode="dom_regex", value_selector="#key"),
        account_identity_selector="#identity", authenticated_selector="#logout",
    )
    manager = ResourceManager(settings)
    mailbox = manager.save({"name": "受控 Graph", "kind": "mailbox", "config": {
        "source": "outlook", "accounts": f"{email}----fake-password----fake-client----fake-refresh",
    }})
    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    lease = None
    try:
        proxy = manager.save({"name": "受控 HTTP 代理", "kind": "proxy", "config": {
            "source": "dynamic", "server": f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}",
            "check_url": "http://runtime-browser.test/ip",
        }})
        if via_runtime:
            from agnes_provisioner.script_runtime import ScriptRuntime

            runtime = ScriptRuntime(settings, resources=manager)
            batch = runtime.start({"script_id": "agnes", "version": "1.0.0", "count": 1,
                                   "request_id": "agnes-real-runtime-test",
                                   "bindings": {"mailbox": mailbox["id"], "proxy": proxy["id"]}
                                   })["batch"]
            await asyncio.to_thread(runtime.worker.join, 30)
            assert not runtime.worker.is_alive()
            task = runtime.store.tasks(batch["id"], reveal=True)["tasks"][0]
            assert task["state"] == "SUCCEEDED", task["message"]
            result = task["results"]
            assert result_key not in json.dumps(runtime.store.events(batch["id"]))
            assert result_key.encode() not in settings.database.read_bytes()
            assert runtime.store.tasks(batch["id"])["tasks"][0]["results"]["api_key"] == "••••••"
        else:
            snapshot = manager.snapshot({"mailbox": mailbox["id"], "proxy": proxy["id"]},
                                        {"mailbox": True, "proxy": True}, 1, "agnes")
            lease = await manager.acquire(snapshot, "agnes", "test-task")
            ctx = Context(settings, lease, manager)
            result = await run_agnes(ctx)
            assert result["password"] in ctx.secrets
        assert result["email"] == email
        assert result["api_key"] == result_key
        assert state["registrations"] == [{"email": email, "code": "314159",
                                            "marked_before_request": True}]
        assert state["proxy_checks"] >= 2 and state["graph_reads"] >= 5
        if not via_runtime:
            with pytest.raises(ScriptFailure) as error:
                await run_agnes(ctx)
            assert error.value.code == "AGNES_ALREADY_SUBMITTED"
            await manager.release(lease, submitted=ctx.submitted, succeeded=True)
        assert len(state["registrations"]) == 1
        with pytest.raises(ResourceError) as error:
            manager.snapshot({"mailbox": mailbox["id"]}, {"mailbox": True}, 1, "agnes")
        assert error.value.code == "MAILBOX_EXHAUSTED"
    finally:
        if lease:
            await manager.release(lease, submitted=False, succeeded=False)
        server.close()
        await server.wait_closed()
        for writer in list(writers):
            writer.close()
        for task in list(handlers):
            task.cancel()
        await asyncio.gather(*list(handlers), return_exceptions=True)
