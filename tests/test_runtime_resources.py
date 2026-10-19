from __future__ import annotations

import asyncio
import base64
import copy
import json
import sqlite3
import threading
import time
from contextlib import asynccontextmanager

import pytest

from agnes_provisioner.config import Settings
from agnes_provisioner.mailbox import MailboxError
from agnes_provisioner.runtime_resources import ResourceError, ResourceManager
from agnes_provisioner.vault import Vault


@pytest.fixture
def manager(tmp_path, monkeypatch):
    class Mailbox:
        def __init__(self, vault, ref):
            self.vault, self.ref = vault, ref

        def baseline(self):
            record = self.vault.get(self.ref)
            if record["refresh_token"] == "expired":
                raise MailboxError("MAILBOX_TOKEN_INVALID", "invalid token (hidden)")
            return {"transport": "graph", "seen": []}

        def find_code(self, baseline):
            return "123456" if self.sender_domain == "second.example" else None

    monkeypatch.setattr("agnes_provisioner.runtime_resources.OutlookMailbox", Mailbox)
    return ResourceManager(Settings(
        database=tmp_path / "runtime.db", vault=tmp_path / "vault.dpapi",
    ))


def mailbox_payload(*emails, token="fake-refresh", **kwargs):
    return {"name": "测试邮箱", "kind": "mailbox", "config": {
        "source": "outlook", "transport": "graph", "accounts": "\n".join(
            f"{email}----fake-mail-password----fake-client----{token}" for email in emails
        ),
    }, **kwargs}


def bind(manager, resource, count=1, site="site-a"):
    return manager.snapshot({"mailbox": resource["id"]}, {"mailbox": True}, count, site)


def test_named_resource_restart_and_encrypted_config(manager):
    saved = manager.save(mailbox_payload("a@example.com", "b@example.com"))
    assert saved["status"] == "UNKNOWN"
    assert saved["summary"]["healthy"] == 0
    assert saved["summary"]["unknown"] == 2
    assert ResourceManager(manager.settings).list() == [saved]
    snapshot = bind(manager, saved, count=2)
    serialized = json.dumps([saved, snapshot])
    db_bytes = manager.settings.database.read_bytes()
    vault_bytes = manager.settings.vault.read_bytes()
    for secret in ("fake-refresh", "fake-mail-password", "fake-client"):
        assert secret not in serialized
        assert secret.encode() not in db_bytes
        assert secret.encode() not in vault_bytes
    assert manager.check(saved["id"])["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_parallel_claim_exclusion_release_and_cross_site_reuse(manager):
    saved = manager.save(mailbox_payload("a@example.com", "b@example.com"))
    snapshot = bind(manager, saved, count=2)
    one, two = await asyncio.gather(
        manager.acquire(snapshot, "site-a", "one"),
        ResourceManager(manager.settings).acquire(snapshot, "site-a", "two"),
    )
    assert one.mailbox.email != two.mailbox.email
    with pytest.raises(ResourceError, match="不足"):
        bind(manager, saved, site="site-b")
    manager.mark_submitted(one)
    await manager.release(one, submitted=False, succeeded=False)
    await manager.release(two, submitted=False, succeeded=False)
    same_site = bind(manager, saved)
    next_lease = await manager.acquire(same_site, "site-a", "three")
    assert next_lease.mailbox.email == two.mailbox.email
    await manager.release(next_lease, submitted=True, succeeded=True)
    with pytest.raises(ResourceError, match="不足"):
        bind(manager, saved)
    other_site = bind(manager, saved, count=2, site="site-b")
    reused = await manager.acquire(other_site, "site-b", "four")
    assert reused.mailbox.email == one.mailbox.email
    await manager.release(reused, submitted=False, succeeded=False)


@pytest.mark.asyncio
async def test_duplicate_email_across_named_pools_is_globally_exclusive(manager):
    first = manager.save(mailbox_payload("same@example.com"))
    second = manager.save(mailbox_payload("SAME@example.com"))
    a, b = bind(manager, first), bind(manager, second, site="site-b")
    leased = await manager.acquire(a, "site-a", "one")
    with pytest.raises(ResourceError, match="耗尽"):
        await manager.acquire(b, "site-b", "two")
    manager.mark_submitted(leased)
    await manager.release(leased, submitted=True, succeeded=False)
    with pytest.raises(ResourceError, match="不足"):
        bind(manager, second)
    reused = await manager.acquire(b, "site-b", "two")
    await manager.release(reused, submitted=False, succeeded=False)


@pytest.mark.asyncio
async def test_immutable_revision_and_tampered_snapshot_are_rejected(manager):
    saved = manager.save(mailbox_payload("before@example.com"))
    before = bind(manager, saved)
    manager.save(mailbox_payload("after@example.com", id=saved["id"], token="updated-token"))
    after = bind(manager, saved)
    assert before != after
    tampered = copy.deepcopy(before)
    tampered["bindings"] = after["bindings"]
    with pytest.raises(ResourceError, match="快照"):
        await manager.acquire(tampered, "site-a", "bad")
    lease = await manager.acquire(before, "site-a", "old")
    assert lease.mailbox.email == "before@example.com"
    assert manager.vault.get(lease.mailbox.secret_ref)["refresh_token"] == "fake-refresh"
    await manager.release(lease, submitted=False, succeeded=False)
    new = await manager.acquire(after, "site-a", "new")
    assert new.mailbox.email == "after@example.com"
    await manager.release(new, submitted=False, succeeded=False)


@pytest.mark.asyncio
async def test_crash_recovery_keeps_submissions_and_never_replays_task(manager):
    saved = manager.save(mailbox_payload("a@example.com", "b@example.com"))
    snapshot = bind(manager, saved, count=2)
    a = await manager.acquire(snapshot, "site-a", "a")
    b = await manager.acquire(snapshot, "site-a", "b")
    manager.mark_submitted(a)
    restarted = ResourceManager(manager.settings)
    restarted.recover()
    restarted.recover()
    with pytest.raises(ResourceError, match="重复执行"):
        await restarted.acquire(snapshot, "site-a", "a")
    next_snapshot = bind(restarted, saved)
    c = await restarted.acquire(next_snapshot, "site-a", "c")
    assert c.mailbox.email == b.mailbox.email
    await restarted.release(c, submitted=False, succeeded=False)


@pytest.mark.asyncio
async def test_bad_credentials_fail_before_submission_and_refresh_is_returned(manager):
    invalid = manager.save(mailbox_payload("bad@example.com", token="expired"))
    snapshot = bind(manager, invalid)
    with pytest.raises(ResourceError) as failed:
        await manager.acquire(snapshot, "site-a", "bad")
    assert failed.value.code == "MAILBOX_TOKEN_INVALID"
    assert manager.list()[0]["status"] == "UNHEALTHY"
    with manager._connection() as db:
        assert db.execute("SELECT released FROM resource_leases").fetchone()[0] == 1
        assert not list(db.execute("SELECT * FROM resource_submissions"))
    with pytest.raises(ResourceError, match="不足"):
        bind(manager, invalid)
    healthy = manager.save(mailbox_payload("good@example.com"))
    lease = await manager.acquire(bind(manager, healthy), "site-a", "good")
    record = manager.vault.get(lease.mailbox.secret_ref)
    record.update(refresh_token="rotated-token", api_key="site-key")
    manager.vault.set(lease.mailbox.secret_ref, record)
    await manager.release(lease, submitted=False, succeeded=False)
    next_lease = await manager.acquire(bind(manager, healthy), "site-a", "next")
    new_record = manager.vault.get(next_lease.mailbox.secret_ref)
    assert new_record["refresh_token"] == "rotated-token"
    assert "api_key" not in new_record
    await manager.release(next_lease, submitted=False, succeeded=False)


@pytest.mark.asyncio
async def test_mailbox_async_matching_is_script_configurable(manager):
    saved = manager.save(mailbox_payload("a@example.com"))
    lease = await manager.acquire(bind(manager, saved), "site-a", "one")
    lease.mailbox.configure(sender_domain="second.example", code_pattern=r"\d{6}")
    assert await lease.mailbox.find_code(await lease.mailbox.baseline()) == "123456"
    with pytest.raises(ResourceError):
        lease.mailbox.configure(sender_domain="*", code_pattern=".*")
    await manager.release(lease, submitted=False, succeeded=False)


def legacy_fixture(manager):
    with manager._connection(write=True) as db:
        db.executescript("""
            CREATE TABLE users(id TEXT,email TEXT,secret_ref TEXT);
            CREATE TABLE registration_jobs(id TEXT,user_id TEXT,state TEXT,phase TEXT,
                submitted_at REAL,created_at REAL,provider TEXT DEFAULT 'agnes-api');
            CREATE TABLE bulk_requests(job_id TEXT,kind TEXT,at REAL);
        """)
        for index in range(4):
            email, ref = f"old{index}@example.com", f"legacy-{index}"
            manager.vault.set(ref, {"email": email, "client_id": "old-client",
                                   "refresh_token": "old-refresh", "mailbox_transport": "graph",
                                   "activated": index == 2, "mailbox_authorized": True})
            db.execute("INSERT INTO users VALUES(?,?,?)", (ref, email, ref))
            db.execute("INSERT INTO registration_jobs "
                       "VALUES(?,?,'PENDING','PREPARE',?,?,'agnes-api')",
                       (ref, ref, 1 if index == 0 else None, time.time()))
        db.execute("INSERT INTO bulk_requests VALUES('legacy-1','REGISTRATION_SUBMITTED',1)")


@pytest.mark.asyncio
async def test_legacy_import_is_non_destructive_and_excludes_database_and_vault_evidence(manager):
    legacy_fixture(manager)
    original_vault = manager.vault.snapshot()
    with manager._connection() as db:
        before = {table: [tuple(r) for r in db.execute(f"SELECT * FROM {table}")]
                  for table in ("users", "registration_jobs", "bulk_requests")}
    saved = manager.save({"name": "旧邮箱", "kind": "mailbox", "config": {"source": "legacy"}})
    manager.save({"id": saved["id"], "name": "旧邮箱", "kind": "mailbox",
                  "config": {"source": "legacy"}})
    snapshot = bind(manager, saved, site="agnes")
    lease = await manager.acquire(snapshot, "agnes-api", "fresh")
    assert lease.mailbox.email == "old3@example.com"
    with manager._connection() as db:
        assert db.execute("SELECT count(*) FROM resource_submissions").fetchone()[0] == 3
        assert before == {table: [tuple(r) for r in db.execute(f"SELECT * FROM {table}")]
                          for table in before}
    assert all(manager.vault.get(k) == v for k, v in original_vault.items())
    await manager.release(lease, submitted=False, succeeded=False)


def test_failed_vault_write_preserves_old_binding(manager, monkeypatch):
    saved = manager.save(mailbox_payload("old@example.com"))
    before = manager.list()

    def fail(*_):
        raise OSError("write refused")

    monkeypatch.setattr(manager.vault, "set_many", fail)
    with pytest.raises(OSError):
        manager.save(mailbox_payload("new@example.com", id=saved["id"]))
    assert manager.list() == before


@pytest.mark.asyncio
async def test_external_legacy_config_readonly_copy_preserves_sources_and_exclusions(manager,
                                                                                   tmp_path):
    from agnes_provisioner.config import Settings, save_settings

    source_settings = Settings(database=tmp_path / "archive/source.db",
                               vault=tmp_path / "archive/source.dpapi")
    source = ResourceManager(source_settings)
    legacy_fixture(source)
    config_path = tmp_path / "archive/source.toml"
    save_settings(source_settings, config_path)
    before = {p: p.read_bytes() for p in
              (source_settings.database, source_settings.vault, config_path)}
    saved = manager.save({"name": "从旧配置复制", "kind": "mailbox",
                          "config": {"source": "legacy", "config_path": str(config_path)}})
    snapshot = bind(manager, saved, site="agnes")
    lease = await manager.acquire(snapshot, "agnes", "copied-task")
    assert lease.mailbox.email == "old3@example.com"
    await manager.release(lease, submitted=False, succeeded=False)
    assert {p: p.read_bytes() for p in before} == before
    assert saved["summary"]["total"] == 4


@pytest.mark.asyncio
async def test_mock_legacy_success_does_not_consume_real_agnes_mailbox(manager):
    legacy_fixture(manager)
    with manager._connection(write=True) as db:
        db.execute("UPDATE registration_jobs SET provider='mock',state='SUCCEEDED' "
                   "WHERE id='legacy-3'")
    saved = manager.save({"name": "旧资源", "kind": "mailbox", "config": {"source": "legacy"}})
    lease = await manager.acquire(bind(manager, saved, site="agnes"), "agnes", "real-after-mock")
    assert lease.mailbox.email == "old3@example.com"
    await manager.release(lease, submitted=False, succeeded=False)


@pytest.mark.parametrize("configuration", [
    {"source": "outlook", "accounts": "bad-secret"},
    {"source": "outlook", "accounts": "a@example.com----bad-secret"},
    {"source": "outlook", "transport": "unknown", "accounts": "a@example.com----bad-secret"},
    {"source": "outlook", "accounts": [], "password": "bad-secret"},
])
def test_invalid_config_does_not_echo_credentials(manager, configuration):
    with pytest.raises(ResourceError) as failed:
        manager.save({"name": "mail", "kind": "mailbox", "config": configuration})
    assert "bad-secret" not in str(failed.value)
    assert manager.list() == []


@asynccontextmanager
async def fake_gateway(*, ip="203.0.113.9", status=200):
    requests = []
    writers = set()

    async def handle(reader, writer):
        writers.add(writer)
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
            requests.append(header.decode())
            body = ip.encode()
            writer.write(f"HTTP/1.1 {status} Test\r\nContent-Length: {len(body)}\r\n"
                         "Connection: close\r\n\r\n".encode() + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            writers.discard(writer)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    try:
        yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}", requests
    finally:
        server.close()
        await server.wait_closed()
        for writer in list(writers):
            writer.close()


def proxy_payload(server, **extra):
    return {"name": "动态代理", "kind": "proxy", "config": {
        "source": "dynamic", "server": server, "username": "test-provider",
        "password": "fake-proxy-password", "check_url": "http://ip.test/ip", **extra,
    }}


@pytest.mark.asyncio
async def test_actual_http_proxy_check_pinned_session_and_rotation(manager):
    async with fake_gateway() as (server, requests):
        saved = manager.save(proxy_payload(server))
        checked = await asyncio.to_thread(manager.check, saved["id"])
        assert checked["status"] == "HEALTHY"
        snapshot = manager.snapshot({"proxy": saved["id"]}, {"proxy": True}, 2, "site")
        one = await manager.acquire(snapshot, "site", "one")
        original = dict(one.proxy)
        manager.save({**proxy_payload("http://127.0.0.1:1"), "id": saved["id"]})
        await one.validate_proxy()
        assert one.proxy == original
        assert one.egress_ip == "203.0.113.9"
        await manager.release(one, submitted=False, succeeded=True)
        two = await manager.acquire(snapshot, "site", "two")
        assert one.proxy["username"] != two.proxy["username"]
        assert two.proxy["server"] == server
        await manager.release(two, submitted=False, succeeded=False)
        assert len(requests) == 4
        encoded = base64.b64encode(
            f"{one.proxy['username']}:fake-proxy-password".encode(),
        ).decode()
        assert "Proxy-Authorization: Basic " + encoded in requests[1]
        assert requests[1].startswith("GET http://ip.test/ip HTTP/1.1")


@pytest.mark.asyncio
async def test_failed_proxy_never_falls_back_or_leaves_mailbox_leased(manager):
    mail = manager.save(mailbox_payload("a@example.com"))
    async with fake_gateway(status=407) as (server, requests):
        proxy = manager.save(proxy_payload(server))
        snapshot = manager.snapshot({"mailbox": mail["id"], "proxy": proxy["id"]},
                                    {"mailbox": True, "proxy": True}, 1, "site")
        with pytest.raises(ResourceError, match="直连"):
            await manager.acquire(snapshot, "site", "one")
        assert requests
        assert next(r for r in manager.list() if r["id"] == proxy["id"])["status"] == "UNHEALTHY"
        with manager._connection() as db:
            assert db.execute("SELECT released FROM resource_leases").fetchone()[0] == 1
        with pytest.raises(ResourceError, match="代理检查失败"):
            manager.snapshot({"proxy": proxy["id"]}, {"proxy": True}, 1, "site")


@pytest.mark.asyncio
async def test_legacy_bulk_proxy_uses_existing_local_upstream_relay(manager, tmp_path):
    connections = []
    async with fake_gateway() as (gateway, requests):
        port = int(gateway.rsplit(":", 1)[1])

        async def upstream(reader, writer):
            remote_writer = None
            children = []
            try:
                header = await reader.readuntil(b"\r\n\r\n")
                connections.append(header.decode().splitlines()[0])
                remote_reader, remote_writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(b"HTTP/1.1 200 Connected\r\n\r\n")
                await writer.drain()

                async def pipe(source, destination):
                    while chunk := await source.read(65536):
                        destination.write(chunk)
                        await destination.drain()

                children = [asyncio.create_task(pipe(reader, remote_writer)),
                            asyncio.create_task(pipe(remote_reader, writer))]
                await asyncio.wait(children, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for child in children:
                    child.cancel()
                await asyncio.gather(*children, return_exceptions=True)
                writer.close()
                if remote_writer:
                    remote_writer.close()

        server = await asyncio.start_server(upstream, "127.0.0.1", 0)
        old_vault = Vault(tmp_path / "old-proxy.dpapi")
        old_vault.set("screenshot_proxy", {"server": gateway, "username": "bulk-provider",
                                           "password": "bulk-fake-password"})
        original = old_vault.path.read_bytes()
        try:
            saved = manager.save({"name": "旧代理", "kind": "proxy", "config": {
                "source": "legacy_bulk", "vault_path": str(old_vault.path),
                "secret_ref": "screenshot_proxy", "check_url": "http://ip.test/ip",
                "upstream": f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}",
            }})
            snapshot = manager.snapshot({"proxy": saved["id"]}, {"proxy": True}, 1, "site")
            lease = await manager.acquire(snapshot, "site", "one")
            assert lease.proxy["server"] != gateway
            assert lease.proxy["username"].startswith("bulk-provider-session-")
            assert connections == [f"CONNECT 127.0.0.1:{port} HTTP/1.1"]
            assert requests
            await manager.release(lease, submitted=False, succeeded=False)
            assert lease._relay is None
            assert old_vault.path.read_bytes() == original
        finally:
            server.close()
            await server.wait_closed()


def test_snapshot_requires_resources_and_rejects_insufficient_count(manager):
    with pytest.raises(ResourceError) as error:
        manager.snapshot({}, {"mailbox": True}, 1, "site")
    assert error.value.code == "RESOURCE_REQUIRED"
    saved = manager.save(mailbox_payload("a@example.com"))
    with pytest.raises(ResourceError) as error:
        bind(manager, saved, count=2)
    assert error.value.code == "MAILBOX_EXHAUSTED"


def test_partial_mailbox_check_keeps_failure_reason_visible(manager):
    saved = manager.save({"name": "mixed", "kind": "mailbox", "config": {"accounts": [
        {"email": "a@example.com", "client_id": "client", "refresh_token": "expired"},
        {"email": "z@example.com", "client_id": "client", "refresh_token": "valid"},
    ]}})
    checked = manager.check(saved["id"])
    assert checked["status"] == "DEGRADED"
    assert checked["error_code"] == "MAILBOX_TOKEN_INVALID"
    assert checked["summary"]["healthy"] == checked["summary"]["unavailable"] == 1


@pytest.mark.asyncio
async def test_snapshot_count_is_a_hard_cap_even_after_pre_submit_release(manager):
    saved = manager.save(mailbox_payload("a@example.com"))
    snapshot = bind(manager, saved)
    lease = await manager.acquire(snapshot, "site-a", "one")
    await manager.release(lease, submitted=False, succeeded=False)
    with pytest.raises(ResourceError) as failed:
        await manager.acquire(snapshot, "site-a", "two")
    assert failed.value.code == "RESOURCE_COUNT"


@pytest.mark.asyncio
async def test_proxy_egress_change_and_expiry_do_not_rotate_session(manager, monkeypatch):
    async with fake_gateway() as (server, _):
        saved = manager.save(proxy_payload(server))
        snapshot = manager.snapshot({"proxy": saved["id"]}, {"proxy": True}, 1, "site")
        lease = await manager.acquire(snapshot, "site", "one")
        pinned = dict(lease.proxy)

        async def changed(*_):
            return "203.0.113.10"

        monkeypatch.setattr("agnes_provisioner.runtime_resources._probe_proxy", changed)
        with pytest.raises(ResourceError) as failed:
            await lease.validate_proxy()
        assert failed.value.code == "EGRESS_CHANGED"
        lease.created_at -= 30 * 60
        with pytest.raises(ResourceError) as failed:
            await lease.validate_proxy()
        assert failed.value.code == "PROXY_SESSION_EXPIRED"
        assert lease.proxy == pinned
        await manager.release(lease, submitted=False, succeeded=False)


@pytest.mark.asyncio
async def test_cancelled_mailbox_refresh_finishes_before_releasing_lease(manager, monkeypatch):
    saved = manager.save(mailbox_payload("a@example.com"))
    snapshot = bind(manager, saved)
    started, finish = threading.Event(), threading.Event()

    def slow_baseline(client):
        started.set()
        assert finish.wait(timeout=5)
        record = client.vault.get(client.ref)
        record["refresh_token"] = "last-rotated-token"
        client.vault.set(client.ref, record)
        return {}

    from agnes_provisioner import runtime_resources

    monkeypatch.setattr(runtime_resources.OutlookMailbox, "baseline", slow_baseline)
    task = asyncio.create_task(manager.acquire(snapshot, "site-a", "one"))
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    await asyncio.sleep(0.01)
    with manager._connection() as db:
        assert db.execute("SELECT released FROM resource_leases").fetchone()[0] == 0
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    with manager._connection() as db:
        row = db.execute("SELECT * FROM resource_leases").fetchone()
        assert row["released"]
        assert manager.vault.get(row["origin_ref"])["refresh_token"] == "last-rotated-token"


@pytest.mark.asyncio
async def test_sqlite_claim_is_exclusive_between_threads(manager):
    saved = manager.save(mailbox_payload("same@example.com"))
    a, b = bind(manager, saved), bind(manager, saved, site="site-b")

    def claim(snapshot, site, task):
        return asyncio.run(ResourceManager(manager.settings).acquire(snapshot, site, task))

    results = await asyncio.gather(asyncio.to_thread(claim, a, "site-a", "a"),
                                   asyncio.to_thread(claim, b, "site-b", "b"),
                                   return_exceptions=True)
    assert sum(isinstance(result, ResourceError) for result in results) == 1
    winner = next(result for result in results if not isinstance(result, Exception))
    await manager.release(winner, submitted=False, succeeded=False)
    with sqlite3.connect(manager.settings.database) as db:
        active = db.execute("SELECT count(*) FROM resource_leases WHERE released=0").fetchone()[0]
        assert active == 0
