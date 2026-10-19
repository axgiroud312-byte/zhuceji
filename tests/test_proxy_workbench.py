from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import inspect, select

from agnes_provisioner.config import Approval, KeyFlow, ProxyPoolConfig, Settings
from agnes_provisioner.domain import Result, State
from agnes_provisioner.lock import RunLock
from agnes_provisioner.models import Job, Proxy, ProxyMeta, User
from agnes_provisioner.proxy import ProxyManager, parse_proxy_line, preview_proxy_text
from agnes_provisioner.scheduler import Scheduler
from agnes_provisioner.storage import Storage, StorageError
from agnes_provisioner.vault import VaultError


@pytest.fixture
def storage(tmp_path):
    value = Storage(tmp_path / "proxy-workbench.db")
    value.initialize()
    yield value
    value.close()


def seed(storage, count=1, *, provider="mock", batch="batch"):
    with storage.session.begin() as session:
        for index in range(count):
            session.add(User(
                id=f"{batch}-u{index}", email=f"{batch}-u{index}@example.com",
                consent=True, consent_reference="isolated-test", created_at=time.time(),
            ))
    storage.create_batch(batch, provider)
    return [job["job_id"] for job in storage.jobs(batch)]


def pool(storage, count=2, *, dynamic=False):
    manager = ProxyManager(storage)
    auth = "test-{session}:dummy-password@" if dynamic else ""
    manager.import_text("\n".join(
        f"p{index}|http://{auth}127.0.0.1:{8100 + index}"
        for index in range(1, count + 1)
    ))
    return manager


def settings(storage, **kwargs):
    return Settings(
        database=storage.path, per_minute=1000000, retry_delay_seconds=0, **kwargs
    )


def rows_by_id(manager):
    return {row["id"]: row for row in manager.list()}


@pytest.mark.parametrize(("line", "server", "username", "password", "dynamic"), [
    ("http://u1:p1@127.0.0.1:8001", "http://127.0.0.1:8001", "u1", "p1", False),
    ("127.0.0.1:8002:u2:p2", "http://127.0.0.1:8002", "u2", "p2", False),
    ("http://u3-{session}:p3@127.0.0.1:8003", "http://127.0.0.1:8003",
     "u3-{session}", "p3", True),
    ("socks5://127.0.0.1:8004", "socks5://127.0.0.1:8004", "", "", False),
    ("http://u%40example:p%3Ass@127.0.0.1:8005", "http://127.0.0.1:8005",
     "u@example", "p:ss", False),
    ("127.0.0.1:8006:user:pass:with:colon", "http://127.0.0.1:8006",
     "user", "pass:with:colon", False),
    ("https://[2001:db8::1]:8007", "https://[2001:db8::1]:8007", "", "", False),
    ("[::1]:8008:user:pass", "http://[::1]:8008", "user", "pass", False),
    ("127.0.0.1----8009----user----pass", "http://127.0.0.1:8009",
     "user", "pass", False),
])
def test_common_proxy_formats(line, server, username, password, dynamic):
    parsed = parse_proxy_line(line, 1)
    assert (parsed["server"], parsed["username"], parsed["password"], parsed["session_mode"]) == (
        server, username, password, dynamic
    )


@pytest.mark.parametrize("line", [
    "http://private-user:private-password@127.0.0.1:bad",
    "http://private-user:private-password@127.0.0.1:65536",
    "http://private-user:private-password@127.0.0.1:8000/private-password",
    "http://private-user:private-password@127.0.0.1:8000?private-password",
    "http://private-user:private-password@127.0.0.1:8000#private-password",
    "ftp://private-user:private-password@127.0.0.1:8000",
    "socks5://private-user:private-password@127.0.0.1:8000",
    "127.0.0.1:private-password:private-user:private-password",
    "http://private-user%0A:private-password@127.0.0.1:8000",
    "http://private-user%XX:private-password@127.0.0.1:8000",
    "http://private-user:private-password@[not-an-ip]:8000",
])
def test_invalid_inputs_and_preview_never_echo_credentials(storage, line):
    with pytest.raises(StorageError) as error:
        parse_proxy_line(line, 7)
    assert "private-user" not in str(error.value)
    assert "private-password" not in str(error.value)
    preview = preview_proxy_text(line)
    assert preview["invalid"] == 1 and preview["valid"] == 0
    assert "private-user" not in json.dumps(preview)
    assert "private-password" not in json.dumps(preview)
    with pytest.raises(StorageError):
        ProxyManager(storage).import_text("127.0.0.1:8100\n" + line)
    assert ProxyManager(storage).list() == []


def test_preview_is_pure_redacted_and_marks_templates():
    preview = preview_proxy_text(
        "# comment\nhttp://private-user:private-password@127.0.0.1:8001\n"
        "127.0.0.1:8002:second-user:second-password\n"
        "http://dynamic-{session}:third-password@127.0.0.1:8003\n"
        "socks5://127.0.0.1:8004"
    )
    assert preview["valid"] == 4 and preview["invalid"] == 0
    assert [row["has_auth"] for row in preview["rows"]] == [True, True, True, False]
    assert [row["session_mode"] for row in preview["rows"]] == [False, False, True, False]
    assert preview["rows"][0]["line"] == 2
    assert preview["rows"][-1]["scheme"] == "socks5"
    for secret in ["private-user", "private-password", "second-user", "third-password"]:
        assert secret not in json.dumps(preview)


def test_toml_preview_and_import_errors_are_redacted(storage):
    content = '''[[proxies]]
id = "node"
server = "http://127.0.0.1:8001"
username_env = "TEST_PROXY_USER"
password_env = "TEST_PROXY_PASSWORD"
'''
    preview = preview_proxy_text(content)
    assert preview["valid"] == 1 and preview["rows"][0]["has_auth"]
    assert "TEST_PROXY_PASSWORD" not in json.dumps(preview)
    bad = content.replace("http://127.0.0.1:8001", "http://private-user:private-password@host:bad")
    with pytest.raises(StorageError) as error:
        ProxyManager(storage).import_text(bad)
    assert "private-password" not in str(error.value)
    assert "private-password" not in json.dumps(preview_proxy_text(bad))


def test_import_deduplicates_and_does_not_overwrite_different_auth(storage):
    manager = ProxyManager(storage)
    text = "http://first-user:dummy-password@127.0.0.1:8001"
    result = manager.import_text(text + "\n" + text)
    assert result["imported"] == 1 and result["duplicates"] == 1
    assert preview_proxy_text(text + "\n" + text)["duplicates"] == 1
    manager.import_text(text.replace("first-user", "second-user"))
    assert len(manager.list()) == 2
    assert "dummy-password" not in json.dumps(manager.list())
    with pytest.raises(StorageError):
        manager.import_text("same|127.0.0.1:8100\nsame|127.0.0.1:8101")


def test_inline_credentials_are_dpapi_encrypted_not_written_as_plaintext(storage):
    manager = ProxyManager(storage)
    username = "ISS004-Private-Proxy-Username-For-Isolated-Test"
    password = "ISS004-Private-Proxy-Password-For-Isolated-Test"
    content = f"safe|http://{username}:{password}@127.0.0.1:8100"
    manager.import_text(content)
    with storage.session() as session:
        meta = session.get(ProxyMeta, "safe")
        assert meta.inline_username.startswith("dpapi:v1:")
        assert meta.inline_password.startswith("dpapi:v1:")
        assert meta.inline_username != username and meta.inline_password != password
    lease = manager.acquire("job")
    assert lease[1]["username"] == username and lease[1]["password"] == password
    for output in [manager.list(), preview_proxy_text(content)]:
        assert username not in json.dumps(output) and password not in json.dumps(output)
    with storage.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    for file in storage.path.parent.glob(storage.path.name + "*"):
        contents = file.read_bytes()
        assert username.encode() not in contents and password.encode() not in contents


def test_legacy_plaintext_is_read_only_until_explicit_reimport(storage):
    manager = pool(storage, count=1)
    username = "ISS004-Legacy-Username"
    password = "ISS004-Legacy-Password"
    with storage.session.begin() as session:
        meta = session.get(ProxyMeta, "p1")
        meta.inline_username = username
        meta.inline_password = password
    manager.list()
    lease = manager.acquire("legacy-job")
    assert lease[1]["password"] == password
    manager.release("p1", "legacy-job")
    with storage.session() as session:
        assert session.get(ProxyMeta, "p1").inline_password == password
    manager.import_text(f"p1|http://{username}:{password}@127.0.0.1:8101")
    with storage.session() as session:
        assert session.get(ProxyMeta, "p1").inline_password.startswith("dpapi:v1:")
    with storage.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    for file in storage.path.parent.glob(storage.path.name + "*"):
        assert password.encode() not in file.read_bytes()


def test_encryption_failure_never_falls_back_to_plaintext(storage, monkeypatch):
    def denied(*args):
        raise VaultError("ISS004-private-password-from-failed-encryption")

    monkeypatch.setattr("agnes_provisioner.proxy._transform", denied)
    manager = ProxyManager(storage)
    with pytest.raises(StorageError) as error:
        manager.import_text("p1|http://private-user:private-password@127.0.0.1:8101")
    assert "private-password" not in str(error.value)
    assert manager.list() == []


def test_latency_migration_preserves_existing_pool_bindings_and_secrets(storage):
    ids = seed(storage)
    manager = pool(storage, dynamic=True)
    with storage.session.begin() as session:
        meta = session.get(ProxyMeta, "p1")
        meta.generation = 17
        meta.total_results = 4
        meta.last_ip = "203.0.113.20"
        job = session.get(Job, ids[0])
        job.state = State.UNKNOWN
        job.submitted_at = time.time()
        job.proxy_id = "p1"
        protected_username, protected_password = meta.inline_username, meta.inline_password
    # Reconstruct the existing 0001 schema only in this temporary database.
    with storage.engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE proxy_meta DROP COLUMN latency_ms")
        connection.exec_driver_sql("UPDATE alembic_version SET version_num = '0001'")
    storage.initialize()
    storage.initialize()  # idempotent, including a fresh 0001 metadata-created column
    latency = next(
        column for column in inspect(storage.engine).get_columns("proxy_meta")
        if column["name"] == "latency_ms"
    )
    assert latency["nullable"]
    with storage.session() as session:
        meta = session.get(ProxyMeta, "p1")
        assert meta.latency_ms is None and meta.generation == 17 and meta.total_results == 4
        assert meta.last_ip == "203.0.113.20"
        assert (meta.inline_username, meta.inline_password) == (
            protected_username, protected_password
        )
        assert session.get(Job, ids[0]).proxy_id == "p1"
    assert rows_by_id(manager)["p1"]["binding_preserved"]


@pytest.mark.parametrize(("mode", "threshold", "exec_limit", "results", "rotations"), [
    ("result_reached", 2, 3, [False, True, True], [False, False, True]),
    ("execution_count", 2, 3, [False, False], [False, True]),
    ("both", 2, 3, [False, False, False], [False, False, True]),
    ("both", 2, 4, [True, True], [False, True]),
])
def test_all_rotation_thresholds(storage, mode, threshold, exec_limit, results, rotations):
    manager = pool(storage)
    for index, (achieved, expected_rotation) in enumerate(zip(results, rotations)):
        lease = manager.acquire(f"job-{index}")
        assert lease[0] == "p1"
        result = manager.release(
            lease[0], f"job-{index}", result_achieved=achieved, rotate_mode=mode,
            rotate_every=threshold, rotate_executions_limit=exec_limit,
        )
        assert result["rotated"] is expected_rotation
    rows = rows_by_id(manager)
    assert rows["p1"]["total_executions"] == len(results)
    assert rows["p1"]["total_results"] == sum(results)
    assert rows["p1"]["window_results"] == rows["p1"]["window_executions"] == 0
    assert manager.acquire("next")[0] == "p2"


@pytest.mark.parametrize("manual", [True, False])
def test_rotation_really_moves_past_unequal_generations(storage, manual):
    manager = pool(storage)
    with storage.session.begin() as session:
        session.get(ProxyMeta, "p2").generation = 50
    if manual:
        result = manager.rotate_now()
        assert result["rotated"] == 1 and result["next_proxy_id"] == "p2"
    else:
        assert manager.acquire("job")[0] == "p1"
        manager.release("p1", "job", result_achieved=True)
    rows = rows_by_id(manager)
    assert rows["p1"]["generation"] > rows["p2"]["generation"] == 50
    assert manager.acquire("next")[0] == "p2"


def test_leased_node_cannot_be_modified_rotated_reset_or_deleted(storage):
    manager = pool(storage)
    manager.acquire("owner", "p1")
    for action in [
        lambda: manager.rotate_now("p1"), manager.reset_rotation,
        lambda: manager.delete_proxy("p1"), manager.clear_all,
        lambda: manager.set_enabled("p1", False),
        lambda: manager.import_text("p1|127.0.0.1:8101"),
    ]:
        with pytest.raises(StorageError):
            action()
    assert manager.release("p1", "someone-else", failed=True)["released"] is False
    assert rows_by_id(manager)["p1"]["leased_job_id"] == "owner"
    assert rows_by_id(manager)["p1"]["generation"] == 0


def test_acquisition_is_atomic_across_threads_and_storage_instances(storage):
    pool(storage, count=1)
    barrier = threading.Barrier(12)

    def acquire(index):
        other_storage = Storage(storage.path)
        try:
            barrier.wait(timeout=10)
            return ProxyManager(other_storage).acquire(f"parallel-{index}")
        finally:
            other_storage.close()

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(acquire, range(12)))
    assert sum(result is not None for result in results) == 1
    assert ProxyManager(storage).list()[0]["leased"]


def test_one_job_cannot_acquire_multiple_nodes(storage):
    manager = pool(storage)
    assert manager.acquire("same-job") is not None
    assert manager.acquire("same-job") is None
    assert sum(row["leased"] for row in manager.list()) == 1


def test_unconfigured_auth_does_not_prevent_acquiring_another_healthy_node(storage, monkeypatch):
    manager = pool(storage)
    monkeypatch.delenv("ISS004_MISSING_PROXY_USER", raising=False)
    monkeypatch.delenv("ISS004_MISSING_PROXY_PASSWORD", raising=False)
    with storage.session.begin() as session:
        proxy = session.get(Proxy, "p1")
        proxy.username_env = "ISS004_MISSING_PROXY_USER"
        proxy.password_env = "ISS004_MISSING_PROXY_PASSWORD"
    assert manager.acquire("job")[0] == "p2"
    assert rows_by_id(manager)["p1"]["status"] == "UNHEALTHY"


def test_reset_clears_all_counts_health_and_stale_ip(storage):
    manager = pool(storage)
    with storage.session.begin() as session:
        for index, proxy in enumerate(session.scalars(select(Proxy))):
            proxy.status = ["HEALTHY", "BLOCKED"][index]
            proxy.failures = 4
            proxy.successes = 7
            proxy.last_checked = time.time()
            meta = session.get(ProxyMeta, proxy.id)
            meta.generation = 9
            meta.window_executions = meta.total_executions = 8
            meta.window_results = meta.total_results = 3
            meta.last_ip = "203.0.113.1"
            meta.last_rotated_at = time.time()
    manager.reset_rotation()
    for row in manager.list():
        assert row["status"] == "HEALTHY"
        for field in ["generation", "window_executions", "window_results", "total_executions",
                      "total_results", "failures", "successes"]:
            assert row[field] == 0
        assert row["last_ip"] == "" and row["last_checked"] is None
        assert row["last_rotated_at"] is None


def test_submitted_binding_reserves_original_session_and_prevents_mutation(storage):
    seed(storage)
    manager = pool(storage, dynamic=True)
    storage.control("batch", "RUNNING")
    task = storage.claim("batch", 3)
    first = manager.acquire(task.id)
    storage.set_proxy(task.id, first[0])
    storage.checkpoint(task.id, "SUBMITTED")
    storage.complete(task.id, Result(State.UNKNOWN, "RESULT_UNKNOWN"))
    released = manager.release("p1", task.id, force_rotate=True)
    assert released["binding_preserved"] and not released["rotated"]
    assert manager.acquire("unrelated")[0] == "p2"
    assert manager.acquire("not-the-bound-job", "p1") is None
    assert manager.acquire(task.id, "p2") is None
    for action in [
        lambda: manager.rotate_now("p1"), lambda: manager.delete_proxy("p1"),
        manager.clear_all, manager.reset_rotation,
        lambda: manager.import_text("p1|http://test-{session}:dummy-password@127.0.0.1:8101"),
    ]:
        with pytest.raises(StorageError):
            action()
    restored = manager.acquire(task.id)
    assert restored[0] == "p1" and restored[1]["username"] == first[1]["username"]


class FakeClient:
    requests = []
    ip_text = "203.0.113.10"
    response_status = 200
    error = None
    active = 0
    peak = 0

    def __init__(self, **kwargs):
        assert kwargs["trust_env"] is False

    async def __aenter__(self):
        type(self).active += 1
        type(self).peak = max(type(self).peak, type(self).active)
        return self

    async def __aexit__(self, *args):
        type(self).active -= 1

    async def get(self, url, **kwargs):
        type(self).requests.append(url)
        await asyncio.sleep(0.01)
        if self.error:
            raise self.error
        return httpx.Response(
            200 if url == "https://ipinfo.io/ip" else self.response_status,
            text=self.ip_text if url == "https://ipinfo.io/ip" else "mock reachable page",
        )


@pytest.fixture
def fake_client(monkeypatch):
    class IsolatedClient(FakeClient):
        requests = []
        active = 0
        peak = 0
    monkeypatch.setattr("agnes_provisioner.proxy.httpx.AsyncClient", IsolatedClient)
    return IsolatedClient


async def test_health_checks_measure_ip_and_latency_concurrently(storage, fake_client):
    manager = pool(storage, count=4)
    results = await asyncio.gather(*[
        manager.check(row["id"], "https://target.invalid/login") for row in manager.list()
    ])
    assert fake_client.peak == 4
    assert all(result["status"] == "HEALTHY" for result in results)
    assert all(result["ip"] == "203.0.113.10" for result in results)
    assert all(result["latency_ms"] >= 0 for result in results)
    assert all(row["last_ip"] == "203.0.113.10" and not row["leased"] for row in manager.list())
    other_storage = Storage(storage.path)
    try:
        persisted = ProxyManager(other_storage).list()
        assert [row["latency_ms"] for row in persisted] == [row["latency_ms"] for row in results]
    finally:
        other_storage.close()


@pytest.mark.parametrize("ip_text", ["<script>bad()</script>", "203.0.113.1\n203.0.113.2", "n/a"])
async def test_exit_ip_is_validated_and_stale_measurements_cleared(storage, fake_client, ip_text):
    manager = pool(storage, count=1)
    fake_client.ip_text = ip_text
    with storage.session.begin() as session:
        session.get(ProxyMeta, "p1").last_ip = "203.0.113.99"
    result = await manager.check("p1", "https://target.invalid/login")
    assert result["status"] == "HEALTHY" and result["ip"] == ""
    assert manager.list()[0]["last_ip"] == ""


async def test_health_failure_is_safe_and_http_block_is_distinct(storage, fake_client):
    manager = pool(storage, count=1)
    await manager.check("p1", "https://target.invalid/login")
    assert manager.list()[0]["latency_ms"] is not None
    fake_client.error = httpx.ConnectError("http://private-user:private-password@proxy.invalid")
    failed = await manager.check("p1", "https://target.invalid/login")
    assert failed["status"] == "UNHEALTHY" and failed["latency_ms"] is None
    assert manager.list()[0]["latency_ms"] is None and manager.list()[0]["last_ip"] == ""
    assert "private-password" not in json.dumps(failed)
    fake_client.error = None
    fake_client.response_status = 403
    fake_client.requests = []
    blocked = await manager.check("p1", "https://target.invalid/login")
    assert blocked["status"] == "BLOCKED" and blocked["http_status"] == 403
    assert manager.list()[0]["latency_ms"] is None
    assert "https://ipinfo.io/ip" not in fake_client.requests


async def test_inflight_check_reserves_node_and_cancellation_releases_it(storage, monkeypatch):
    manager = pool(storage, count=1)
    entered = asyncio.Event()

    class WaitingClient(FakeClient):
        async def get(self, url, **kwargs):
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr("agnes_provisioner.proxy.httpx.AsyncClient", WaitingClient)
    checking = asyncio.create_task(manager.check("p1", "https://target.invalid/login"))
    await asyncio.wait_for(entered.wait(), timeout=3)
    assert manager.list()[0]["checking"] and manager.acquire("worker") is None
    assert manager.list()[0]["leased_job_id"] == ""
    for action in [lambda: manager.delete_proxy("p1"), lambda: manager.rotate_now("p1"),
                   lambda: manager.set_enabled("p1", False), manager.reset_rotation]:
        with pytest.raises(StorageError):
            action()
    with pytest.raises(StorageError):
        await manager.check("p1", "https://target.invalid/login")
    checking.cancel()
    with pytest.raises(asyncio.CancelledError):
        await checking
    assert manager.list()[0]["available"] and not manager.list()[0]["leased"]


@pytest.mark.parametrize("action", ["manual", "automatic", "reset", "reimport"])
async def test_rotation_and_explicit_updates_clear_persisted_probe_values(
    storage, fake_client, action
):
    manager = pool(storage)
    await manager.check("p1", "https://target.invalid/login")
    assert rows_by_id(manager)["p1"]["latency_ms"] is not None
    if action == "manual":
        manager.rotate_now("p1")
    elif action == "automatic":
        manager.acquire("job", "p1")
        manager.release("p1", "job", result_achieved=True)
    elif action == "reset":
        manager.reset_rotation()
    else:
        manager.import_text("p1|127.0.0.1:8101")
    row = rows_by_id(manager)["p1"]
    assert row["latency_ms"] is None and row["last_ip"] == "" and row["last_checked"] is None


def test_abandoned_health_check_lease_expires_without_reusing_stale_measurements(storage):
    manager = pool(storage, count=1)
    with storage.session.begin() as session:
        proxy = session.get(Proxy, "p1")
        proxy.leased_job_id = f"health-check:{time.time() - 100}:abandoned"
        meta = session.get(ProxyMeta, "p1")
        meta.latency_ms = 123
        meta.last_ip = "203.0.113.20"
    row = manager.list()[0]
    assert not row["checking"] and not row["leased"] and row["status"] == "UNHEALTHY"
    assert row["latency_ms"] is None and row["last_ip"] == ""


async def test_health_check_hard_timeout_releases_lease_and_clears_old_values(storage, monkeypatch):
    manager = pool(storage, count=1)
    with storage.session.begin() as session:
        session.get(ProxyMeta, "p1").latency_ms = 123

    class NeverReturns(FakeClient):
        async def get(self, url, **kwargs):
            await asyncio.Event().wait()

    monkeypatch.setattr("agnes_provisioner.proxy.httpx.AsyncClient", NeverReturns)
    monkeypatch.setattr("agnes_provisioner.proxy._CHECK_TIMEOUT_SECONDS", 0.02)
    result = await asyncio.wait_for(manager.check("p1", "https://target.invalid/login"), timeout=2)
    assert result["status"] == "UNHEALTHY" and result["latency_ms"] is None
    assert manager.list()[0]["latency_ms"] is None and not manager.list()[0]["leased"]


class RecordingAdapter:
    def __init__(self):
        self.calls = []
        self.closed = False

    async def execute(self, task, proxy, checkpoint):
        self.calls.append((task, proxy))
        return Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY", evidence="mock identity confirmed")

    async def close(self):
        self.closed = True


async def test_worker_start_does_not_recover_away_an_inflight_health_lease(storage, monkeypatch):
    seed(storage)
    manager = pool(storage, count=1)
    entered = asyncio.Event()
    ready = asyncio.Event()

    class ControlledClient(FakeClient):
        async def get(self, url, **kwargs):
            entered.set()
            await ready.wait()
            return httpx.Response(200, text="203.0.113.10")

    monkeypatch.setattr("agnes_provisioner.proxy.httpx.AsyncClient", ControlledClient)
    checking = asyncio.create_task(manager.check("p1", "https://target.invalid/login"))
    await asyncio.wait_for(entered.wait(), timeout=3)
    adapter = RecordingAdapter()
    running = asyncio.create_task(Scheduler(storage, settings(storage), adapter).run("batch"))
    try:
        await asyncio.sleep(0.1)
        assert adapter.calls == [] and manager.list()[0]["checking"]
    finally:
        ready.set()
        _, result = await asyncio.wait_for(asyncio.gather(checking, running), timeout=3)
    assert result["states"] == {"SUCCEEDED": 1} and len(adapter.calls) == 1


@pytest.mark.parametrize("code", ["IP_REGISTRATION_LIMIT", "NETWORK", "THROWN_NETWORK"])
async def test_pre_submit_error_switches_proxy_and_continues_same_task(storage, code):
    seed(storage)
    manager = pool(storage)

    class BeforeSubmit(RecordingAdapter):
        async def execute(self, task, proxy, checkpoint):
            self.calls.append((task, proxy))
            if len(self.calls) == 1:
                if code == "THROWN_NETWORK":
                    raise httpx.ConnectError("private-password must not leak")
                return Result(State.NEEDS_REVIEW, code, pause=True)
            await checkpoint("SUBMITTED")
            return Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY", evidence="mock identity confirmed")

    adapter = BeforeSubmit()
    result = await Scheduler(storage, settings(storage), adapter).run("batch")
    assert [proxy["server"] for _, proxy in adapter.calls] == [
        "http://127.0.0.1:8101", "http://127.0.0.1:8102"
    ]
    assert result["states"] == {"SUCCEEDED": 1} and result["action"] == "STOPPED"
    assert storage.jobs("batch")[0]["attempts"] == 2
    assert rows_by_id(manager)["p1"]["status"] == (
        "BLOCKED" if code == "IP_REGISTRATION_LIMIT" else "UNHEALTHY"
    )
    assert "private-password" not in json.dumps(storage.events(adapter.calls[0][0].id))


@pytest.mark.parametrize(("dynamic", "auto_switch", "should_continue"), [
    (True, True, True), (False, True, False), (True, False, False),
])
async def test_single_dynamic_session_can_switch_but_static_or_disabled_cannot(
    storage, dynamic, auto_switch, should_continue
):
    seed(storage)
    pool(storage, count=1, dynamic=dynamic)

    class LimitedOnce(RecordingAdapter):
        async def execute(self, task, proxy, checkpoint):
            self.calls.append((task, proxy))
            if len(self.calls) == 1:
                return Result(State.NEEDS_REVIEW, "IP_REGISTRATION_LIMIT", pause=True)
            return Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY", evidence="mock identity confirmed")

    adapter = LimitedOnce()
    result = await Scheduler(
        storage, settings(storage, proxy_pool=ProxyPoolConfig(auto_switch_on_ip_limit=auto_switch)),
        adapter,
    ).run("batch")
    assert len(adapter.calls) == (2 if should_continue else 1)
    assert result["states"] == ({"SUCCEEDED": 1} if should_continue else {"NEEDS_REVIEW": 1})
    if should_continue:
        assert adapter.calls[0][1]["username"] != adapter.calls[1][1]["username"]
    else:
        assert result["action"] == "PAUSED"


@pytest.mark.parametrize("code", ["IP_REGISTRATION_LIMIT", "NETWORK"])
async def test_checkpointed_error_keeps_binding_and_never_automatically_resubmits(storage, code):
    seed(storage)
    manager = pool(storage, dynamic=True)
    sticky_id = rows_by_id(manager)["p1"]["session_sticky_id"]

    class AfterSubmit(RecordingAdapter):
        async def execute(self, task, proxy, checkpoint):
            self.calls.append((task, proxy))
            assert task.submitted_at is None  # claim-time snapshot must not decide retry safety
            await checkpoint("SUBMITTED")
            return Result(State.RETRY_WAIT, code, proxy_failed=code == "NETWORK")

    adapter = AfterSubmit()
    result = await Scheduler(storage, settings(storage), adapter).run("batch")
    assert len(adapter.calls) == 1
    assert result["states"] == {"UNKNOWN": 1} and result["action"] == "PAUSED"
    job = storage.jobs("batch")[0]
    assert job["proxy_id"] == "p1" and job["attempts"] == 1
    row = rows_by_id(manager)["p1"]
    assert row["generation"] == 0 and row["session_sticky_id"] == sticky_id
    assert row["binding_preserved"] and not row["leased"]


async def test_unavailable_submitted_binding_never_falls_back_even_at_threshold_one(storage):
    ids = seed(storage)
    manager = pool(storage, dynamic=True)
    with storage.session.begin() as session:
        job = session.get(Job, ids[0])
        job.state = State.UNKNOWN
        job.phase = "REGISTRATION_SUBMITTED"
        job.submitted_at = time.time()
        job.proxy_id = "p1"
        session.get(Proxy, "p1").status = "UNHEALTHY"
    adapter = RecordingAdapter()
    result = await Scheduler(storage, settings(storage), adapter).verify_job(ids[0])
    assert adapter.calls == [] and result["verified_started"] == 1
    assert storage.jobs("batch")[0]["proxy_id"] == "p1"
    assert not rows_by_id(manager)["p2"]["leased"]
    assert rows_by_id(manager)["p2"]["total_executions"] == 0


async def test_incomplete_submitted_result_keeps_session_despite_execution_threshold(storage):
    ids = seed(storage)
    manager = pool(storage, dynamic=True)
    sticky_id = rows_by_id(manager)["p1"]["session_sticky_id"]

    class PendingVerification(RecordingAdapter):
        async def execute(self, task, proxy, checkpoint):
            await checkpoint("SUBMITTED")
            return Result(State.PENDING_VERIFY, "VERIFY_REQUIRED")

    cfg = settings(
        storage, proxy_pool=ProxyPoolConfig(rotate_mode="execution_count", rotate_every=1)
    )
    await Scheduler(storage, cfg, PendingVerification()).run("batch")
    assert rows_by_id(manager)["p1"]["session_sticky_id"] == sticky_id
    assert manager.acquire("new-task")[0] == "p2"
    adapter = RecordingAdapter()
    await Scheduler(storage, cfg, adapter).verify_job(ids[0])
    assert adapter.calls[0][1]["username"] == "test-" + sticky_id


async def test_pool_smaller_than_concurrency_waits_without_pausing_or_burning_attempts(storage):
    seed(storage, count=4)
    pool(storage, count=1)

    class SlowAdapter(RecordingAdapter):
        active = 0
        peak = 0

        async def execute(self, task, proxy, checkpoint):
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0.02)
                await checkpoint("SUBMITTED")
                return await super().execute(task, proxy, checkpoint)
            finally:
                self.active -= 1

    adapter = SlowAdapter()
    result = await Scheduler(storage, settings(storage, concurrency=4), adapter).run("batch")
    assert result["states"] == {"SUCCEEDED": 4} and result["started"] == 4
    assert adapter.peak == 1
    assert all(job["attempts"] == 1 for job in storage.jobs("batch"))


async def test_proxy_switch_retries_still_respect_max_attempts(storage):
    seed(storage)
    pool(storage, count=3)

    class Offline(RecordingAdapter):
        async def execute(self, task, proxy, checkpoint):
            self.calls.append((task, proxy))
            return Result(State.RETRY_WAIT, "NETWORK", proxy_failed=True)

    adapter = Offline()
    result = await Scheduler(storage, settings(storage, max_attempts=2), adapter).run("batch")
    assert result["states"] == {"FAILED": 1} and len(adapter.calls) == 2


@pytest.mark.parametrize(("require_key", "code", "expected_results"), [
    (True, "KEY_PENDING", 0), (False, "KEY_PENDING", 1),
    (True, "ACTIVATED_WITH_KEY", 1),
])
async def test_result_counter_counts_only_the_configured_final_result(
    storage, require_key, code, expected_results
):
    seed(storage)
    manager = pool(storage)

    class FinalResult(RecordingAdapter):
        async def execute(self, task, proxy, checkpoint):
            return Result(State.SUCCEEDED, code, evidence="mock identity confirmed")

    await Scheduler(
        storage, settings(storage, key_flow=KeyFlow(require_key=require_key)), FinalResult()
    ).run("batch")
    assert rows_by_id(manager)["p1"]["total_results"] == expected_results
    assert rows_by_id(manager)["p1"]["generation"] == expected_results


@pytest.mark.parametrize("single", [False, True])
async def test_mock_verification_only_runs_exact_selected_job(storage, single):
    ids = seed(storage, count=3)
    adapter = RecordingAdapter()
    scheduler = Scheduler(storage, settings(storage), adapter)
    result = await (
        scheduler.verify_job(ids[1]) if single
        else scheduler.verify_batch("batch", job_ids=[ids[1], ids[1]])
    )
    assert result["verified_started"] == 1
    assert [task.id for task, _ in adapter.calls] == [ids[1]]
    assert adapter.calls[0][0].phase == "REGISTRATION_SUBMITTED"
    assert adapter.calls[0][0].submitted_at is not None
    assert storage.jobs("batch")[0]["state"] == State.PENDING
    assert storage.jobs("batch")[2]["state"] == State.PENDING
    assert storage.batch("batch").action == "READY" and adapter.closed


@pytest.mark.parametrize(("job_ids", "limit"), [([], None), (None, 0)])
async def test_empty_verification_selection_is_not_all(storage, job_ids, limit):
    ids = seed(storage)
    with storage.session.begin() as session:
        session.get(Job, ids[0]).state = State.NEEDS_REVIEW
    previous_events = storage.events(ids[0])
    adapter = RecordingAdapter()
    result = await Scheduler(storage, settings(storage), adapter).verify_batch(
        "batch", job_ids=job_ids, limit=limit
    )
    assert result["verified_started"] == 0 and adapter.calls == []
    assert storage.events(ids[0]) == previous_events
    assert storage.batch("batch").action == "READY"


@pytest.mark.parametrize("single", [True, False])
@pytest.mark.parametrize(("mode", "provider"), [("mock", "agnes-api"), ("agnes", "mock")])
async def test_verification_provider_is_checked_before_any_claim_or_requeue(
    storage, single, mode, provider
):
    ids = seed(storage, provider=provider)
    previous_events = storage.events(ids[0])
    adapter = RecordingAdapter()
    config = settings(storage, mode=mode, approval=Approval(
        reference="isolated-mock-only-test", per_minute=1000000,
    ))
    scheduler = Scheduler(storage, config, adapter)
    with pytest.raises(StorageError, match="执行模式不同"):
        if single:
            await scheduler.verify_job(ids[0])
        else:
            await scheduler.verify_batch("batch", job_ids=ids)
    assert adapter.calls == []
    assert storage.events(ids[0]) == previous_events
    assert storage.jobs("batch")[0]["state"] == State.PENDING


async def test_verification_lock_is_acquired_before_requeue(storage):
    ids = seed(storage)
    previous_events = storage.events(ids[0])
    adapter = RecordingAdapter()
    with RunLock(storage.path):
        with pytest.raises(StorageError):
            await Scheduler(storage, settings(storage), adapter).verify_batch("batch", job_ids=ids)
    assert storage.events(ids[0]) == previous_events
    assert storage.jobs("batch")[0]["state"] == State.PENDING
    assert adapter.calls == []


async def test_verification_rejects_jobs_from_other_batches_atomically(storage):
    first = seed(storage)
    other = seed(storage, batch="other")
    previous_events = storage.events(first[0])
    with pytest.raises(StorageError, match="不在当前批次"):
        await Scheduler(storage, settings(storage), RecordingAdapter()).verify_batch(
            "batch", job_ids=first + other
        )
    assert storage.events(first[0]) == previous_events
    assert all(job["state"] == State.PENDING for job in storage.jobs())


async def test_verification_calls_reconcile_not_registration_and_keeps_submit_boundary(storage):
    ids = seed(storage, count=2)
    submitted_at = time.time() - 20
    with storage.session.begin() as session:
        job = session.get(Job, ids[1])
        job.state = State.UNKNOWN
        job.submitted_at = submitted_at
        job.phase = "EMAIL_REQUESTED"

    class LoginOnly(RecordingAdapter):
        async def execute(self, *args):
            pytest.fail("Verification must never enter registration")

        async def reconcile(self, task, proxy, checkpoint):
            self.calls.append((task, proxy))
            return Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY", evidence="mock login identity")

    adapter = LoginOnly()
    result = await Scheduler(storage, settings(storage), adapter).verify_batch("batch")
    assert result["verified_started"] == 1
    assert [task.id for task, _ in adapter.calls] == [ids[1]]
    with storage.session() as session:
        job = session.get(Job, ids[1])
        assert job.submitted_at == submitted_at and job.phase == "EMAIL_REQUESTED"
    assert not any(event["code"] == "LOGIN_VERIFY_QUEUED" for event in storage.events(ids[1]))


async def test_delivered_key_skipped_automatically_but_explicit_login_is_allowed(storage):
    ids = seed(storage)
    with storage.session.begin() as session:
        job = session.get(Job, ids[0])
        job.state = State.SUCCEEDED
        job.error_code = "ACTIVATED_WITH_KEY"
        job.submitted_at = time.time()
    adapter = RecordingAdapter()
    result = await Scheduler(storage, settings(storage), adapter).verify_batch("batch")
    assert result["verified_started"] == 0 and adapter.calls == []

    class ExplicitLogin(RecordingAdapter):
        async def execute(self, *args):
            pytest.fail("An explicit login check must not register again")

        async def reconcile(self, task, proxy, checkpoint):
            self.calls.append((task, proxy))
            return Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY", evidence="identity reconfirmed")

    explicit = ExplicitLogin()
    result = await Scheduler(storage, settings(storage), explicit).verify_batch(
        "batch", job_ids=ids
    )
    assert result["verified_started"] == 1
    assert [task.id for task, _ in explicit.calls] == ids
