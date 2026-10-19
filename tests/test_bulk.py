import json
import time

import pytest

from agnes_provisioner.bulk import recover
from agnes_provisioner.bulk_excel import write_bulk_excel
from agnes_provisioner.bulk_prepare import prepare
from agnes_provisioner.bulk_runner import BulkRunner, claim_next, mailbox_ready
from agnes_provisioner.bulk_store import BulkStore
from agnes_provisioner.config import Approval, Settings
from agnes_provisioner.domain import Result, State
from agnes_provisioner.lock import RunLock
from agnes_provisioner.mailbox import MailboxError
from agnes_provisioner.models import User
from agnes_provisioner.scheduler import Scheduler
from agnes_provisioner.storage import Storage, StorageError
from agnes_provisioner.vault import Vault


@pytest.fixture
def production(tmp_path):
    sample = tmp_path / "sample"
    storage = Storage(sample / "jobs.db")
    storage.initialize()
    with storage.session.begin() as session:
        session.add(
            User(
                id="P-existing",
                email="one@example.com",
                consent=True,
                consent_reference="test",
                mailbox_authorized=True,
                secret_ref="P-existing",
                created_at=time.time(),
            )
        )
    storage.create_batch("sample", "agnes-api")
    storage.control("sample", "RUNNING")
    task = storage.claim("sample", 1)
    storage.checkpoint(task.id, "REGISTRATION_SUBMITTED")
    storage.complete(
        task.id, Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY", evidence="test identity")
    )
    storage.control("sample", "PAUSED", "IP_REGISTRATION_LIMIT")
    Vault(sample / "credentials.dpapi").set(
        "P-existing",
        {
            "email": "one@example.com",
            "agnes_password": "=literal-secret",
            "mailbox_password": "@literal-mail",
            "client_id": "client-one",
            "refresh_token": "rotated-new-token",
            "api_key": "sk-test-full-key-only",
            "activated": True,
            "api_key_creation_started": True,
        },
    )
    storage.close()
    source = tmp_path / "source.txt"
    source.write_text(
        "卡密导出\nONE@example.com----old-mail----client-one----stale-token\n"
        "two@example.com----mail-two----client-two----token-two\n"
        "three@example.com----mail-three----client-three----token-three\n",
        encoding="utf-8",
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "status": "PAUSED_PLATFORM_IP_LIMIT",
                "finished_at": time.time(),
                "groups": [
                    {
                        "batch": "sample",
                        "egress_ip": "192.0.2.1",
                        "status": "IP_LIMIT_OBSERVED",
                        "accounts": [
                            {
                                "user_id": "P-existing",
                                "key_authenticated": True,
                                "key_auth_status": 200,
                                "account_activated": True,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        mode="agnes",
        database=tmp_path / "production/jobs.db",
        vault=tmp_path / "production/credentials.dpapi",
        approval=Approval(reference="test", proxies_allowed=True),
    )
    imported = prepare(settings, source, sample, report)
    return settings, BulkStore(settings.database), source, sample, report, imported


def unblock_for_test(bulk):
    with bulk.connection(write=True) as db:
        db.execute("UPDATE bulk_blocks SET released_at=?", (time.time(),))
    bulk.update(
        action="RUNNING",
        reason="",
        supplier_remaining=1_000_000_000,
        balance_at=time.time(),
        supervisor_at=time.time(),
        progress_at=time.time(),
    )


def test_repeat_import_preserves_ids_tokens_jobs_and_authenticated_key(production):
    settings, bulk, source, sample, report, imported = production
    assert imported["imported"] == 2 and imported["duplicates"] == 1
    before = bulk.rows()
    vault = Vault(settings.vault)
    record = vault.get("P-existing")
    assert record["refresh_token"] == "rotated-new-token"
    record["refresh_token"] = "even-newer-token"
    vault.set("P-existing", record)
    assert prepare(settings, source, sample, report)["imported"] == 0
    assert vault.get("P-existing")["refresh_token"] == "even-newer-token"
    assert bulk.rows() == before
    assert bulk.status()["succeeded_authenticated"] == 1
    assert bulk.status()["pause_reason"] == "IP_REGISTRATION_LIMIT"
    with bulk.connection() as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 3
        assert (
            db.execute("SELECT pause_reason FROM batches WHERE id='sample'").fetchone()[0]
            == "IP_REGISTRATION_LIMIT"
        )


def test_reservation_and_rate_survive_restart_and_ip_quota_is_real_ip(production):
    settings, bulk, *_ = production
    unblock_for_test(bulk)
    assert bulk.reserve("a", "EMAIL_REQUESTED", "192.0.2.2", 600) == 0
    reopened = BulkStore(settings.database)
    assert reopened.reserve("b", "EMAIL_REQUESTED", "192.0.2.2", 600) > 0
    with pytest.raises(StorageError, match="ALREADY_RESERVED"):
        reopened.reserve("a", "EMAIL_REQUESTED", "192.0.2.2", 600)
    with bulk.connection(write=True) as db:
        db.execute("UPDATE bulk_requests SET at=0 WHERE job_id='a'")
    assert reopened.reserve("b", "EMAIL_REQUESTED", "192.0.2.2", 600) == 0
    with pytest.raises(StorageError, match="IP_SEND_BUDGET"):
        reopened.reserve("c", "EMAIL_REQUESTED", "192.0.2.2", 600)
    assert reopened.reserve("b", "REGISTRATION_SUBMITTED", "192.0.2.2", 600) == 0


def test_crash_between_reservation_and_checkpoint_goes_to_reconciliation(production):
    settings, bulk, *_ = production
    unblock_for_test(bulk)
    storage = Storage(settings.database)
    try:
        task, review = claim_next(storage, bulk)
        assert not review
        assert bulk.reserve(task.id, "REGISTRATION_SUBMITTED", "192.0.2.3", 1_000_000) == 0
        # Simulate process death before the generic checkpoint; durable reservation wins.
        assert recover(bulk)["recovered"] == 1
        again, review = claim_next(storage, bulk)
        assert again.id == task.id and review and again.phase == "REGISTRATION_SUBMITTED"
        assert again.submitted_at is not None
        storage.complete(again.id, Result(State.NEEDS_REVIEW, "LOGIN_REJECTED"))
    finally:
        storage.close()


async def test_bad_mailbox_skips_once_and_shared_config_pauses(production):
    settings, bulk, *_ = production
    storage = Storage(settings.database)
    task, _ = claim_next(storage, bulk)
    calls = []

    class Mailbox:
        code = "MAILBOX_TOKEN_INVALID"

        def __init__(self, *_):
            pass

        def baseline(self):
            calls.append(self.code)
            raise MailboxError(self.code, "test")

    try:
        _, result = await mailbox_ready(None, task, factory=Mailbox, delay=0)
        assert result.state == State.SKIPPED and len(calls) == 1
        storage.complete(task.id, result)
        next_task, _ = claim_next(storage, bulk)
        assert next_task.id != task.id
        Mailbox.code = "MAILBOX_OAUTH_CONFIG"
        _, result = await mailbox_ready(None, next_task, factory=Mailbox, delay=0)
        assert result.state == State.NEEDS_REVIEW and result.pause and len(calls) == 2
        Mailbox.code = "MAILBOX_NETWORK"
        _, result = await mailbox_ready(None, next_task, factory=Mailbox, delay=0)
        assert result.state == State.SKIPPED and len(calls) == 4
    finally:
        storage.close()


def test_budget_and_heartbeat_fail_closed_and_usage_is_persistent(production):
    settings, bulk, *_ = production
    unblock_for_test(bulk)
    bulk.start_run("test")
    bulk.traffic("test", 100, 1000)
    bulk.traffic("test", 100, 1000)
    assert BulkStore(settings.database).control()["used_bytes"] == 1100
    bulk.update(supervisor_at=0)
    with pytest.raises(StorageError, match="SUPERVISOR_LOST"):
        bulk.gate()
    bulk.update(supervisor_at=time.time(), budget_bytes=1100)
    with pytest.raises(StorageError, match="TRAFFIC_BUDGET"):
        bulk.gate()
    bulk.update(budget_bytes=50_000_000, action="PAUSED", reason="IP_REGISTRATION_LIMIT")
    with pytest.raises(StorageError, match="IP_REGISTRATION_LIMIT"):
        bulk.gate()
    bulk.finish_run("test")
    assert bulk.control()["used_bytes"] == 1100


def test_workbook_checks_every_credential_and_detects_changed_key(production, tmp_path):
    settings, bulk, *_ = production
    result = write_bulk_excel(tmp_path / "result.xlsx", bulk, Vault(settings.vault))
    assert result["rows"] == 3 and result["states"] == {"已完成": 1, "未处理": 2}
    assert result["unique_keys"] == 1 and result["exact_readback"]
    vault = Vault(settings.vault)
    record = vault.get("P-existing")
    record["api_key"] = "sk-changed-unverified"
    vault.set("P-existing", record)
    result = write_bulk_excel(tmp_path / "result.xlsx", bulk, vault)
    assert result["states"] == {"待核查": 1, "未处理": 2}


async def test_legacy_run_cannot_clear_paused_batch_and_bulk_lock_is_exclusive(production):
    settings, bulk, *_ = production
    storage = Storage(settings.database)

    class Never:
        async def execute(self, *_):
            pytest.fail("paused batch executed")

    try:
        with pytest.raises(StorageError, match="暂停"):
            await Scheduler(storage, settings, Never()).run("sample")
        assert storage.batch("sample").pause_reason == "IP_REGISTRATION_LIMIT"
        with RunLock(settings.database), pytest.raises(StorageError), RunLock(settings.database):
            pass
    finally:
        storage.close()


def test_success_without_auth_is_not_completed(production):
    settings, bulk, *_ = production
    storage = Storage(settings.database)
    try:
        task, _ = claim_next(storage, bulk)
        storage.complete(task.id, Result(State.SUCCEEDED, "KEY_PENDING", evidence="identity only"))
        assert bulk.status()["succeeded_authenticated"] == 1
        again, review = claim_next(storage, bulk)
        assert again.id == task.id and review
    finally:
        storage.close()


def test_running_job_is_not_claimed_by_another_worker(production):
    settings, bulk, *_ = production
    storage = Storage(settings.database)
    try:
        first, _ = claim_next(storage, bulk)
        second, _ = claim_next(storage, bulk)
        assert second.id != first.id
    finally:
        storage.close()


def test_unsubmitted_selector_failure_is_not_claimed_until_requeued(production):
    settings, bulk, *_ = production
    storage = Storage(settings.database)
    try:
        first, review = claim_next(storage, bulk)
        assert not review
        storage.complete(
            first.id,
            Result(State.NEEDS_REVIEW, "SELECTOR_CHANGED", "页面步骤超时：SEND_CODE_READY"),
        )
        second, _ = claim_next(storage, bulk)
        assert second.id != first.id
    finally:
        storage.close()


def test_scoped_ip_block_preserved_while_fresh_ip_is_usable(production):
    _, bulk, *_ = production
    with bulk.connection(write=True) as db:
        db.execute(
            "UPDATE bulk_blocks SET released_at=?,release_evidence='scope correction' "
            "WHERE scope='global'",
            (time.time(),),
        )
    bulk.update(
        action="RUNNING",
        reason="",
        supervisor_at=time.time(),
        progress_at=time.time(),
        balance_at=time.time(),
        supplier_remaining=3_000_000_000,
        budget_basis="user_declared_ceiling",
        finish_reserve_bytes=1_000_000,
    )
    bulk.gate(new_account=True)
    with pytest.raises(StorageError, match="PLATFORM_BLOCK_UNRESOLVED"):
        bulk.reserve("blocked", "EMAIL_REQUESTED", "192.0.2.1", 1e6)
    assert bulk.reserve("fresh", "EMAIL_REQUESTED", "192.0.2.99", 1e6) == 0
    assert not bulk.status()["supplier_balance_verified"]
    assert len(bulk.status()["active_blocks"]) == 1


async def test_two_sends_allocate_next_session_but_reused_ip_is_not_accepted(production, tmp_path):
    settings, bulk, *_ = production
    unblock_for_test(bulk)
    runner = BulkRunner(settings, tmp_path)
    base = {"username": "test", "password": "fixture", "server": "http://127.0.0.1:2"}
    ips = iter(["192.0.2.2", "192.0.2.2", "192.0.2.3", "192.0.2.2"])

    async def ip(*_):
        return next(ips)

    runner.check_ip = ip

    class LocalRelay:
        url = "http://127.0.0.1:1"

    relay = LocalRelay()
    try:
        await runner.session(relay, base)
        original = runner.ip_session["session_id"]
        assert bulk.reserve("first", "EMAIL_REQUESTED", "192.0.2.2", 1e6) == 0
        await runner.session(relay, base)
        assert runner.ip_session["session_id"] == original
        assert bulk.reserve("second", "EMAIL_REQUESTED", "192.0.2.2", 1e6) == 0
        await runner.session(relay, base)
        assert runner.ip_session["session_id"] != original
        assert runner.current_ip == "192.0.2.3"
        runner.ip_session = None
        with pytest.raises(StorageError, match="EXHAUSTED"):
            await runner.session(relay, base)
    finally:
        runner.storage.close()


async def test_runner_pause_releases_lock_and_capped_batch_can_reconcile(
    production, tmp_path, monkeypatch
):
    settings, bulk, *_ = production
    runner = BulkRunner(settings, tmp_path)
    with pytest.raises(StorageError, match="IP_REGISTRATION_LIMIT"):
        await runner.run(100)
    with RunLock(settings.database):
        pass
    unblock_for_test(bulk)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    Vault(tmp_path / "data/proxy-image-20261014.dpapi").set(
        "screenshot_proxy", {"server": "http://127.0.0.1:2"}
    )

    class LocalRelay:
        def __init__(self, *args):
            self.sent_bytes = self.received_bytes = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr("agnes_provisioner.bulk_runner.MeteredRelay", LocalRelay)
    calls, closed = [], []

    async def close():
        closed.append(True)

    async def execute(task, review, relay, base):
        calls.append((task.id, review, id(runner.adapter.browser.public_cache)))
        assert bulk.reserve(task.id, "REGISTRATION_SUBMITTED", "192.0.2.4", 1e6) == 0
        runner.storage.checkpoint(task.id, "REGISTRATION_SUBMITTED")
        if len(calls) == 2:
            return Result(State.UNKNOWN, "TIMEOUT", "test interrupt", pause=True), False
        record = runner.vault.get(task.secret_ref)
        record.update(api_key="sk-test-" + task.id, activated=True)
        runner.vault.set(task.secret_ref, record)
        bulk.authenticate(task.user_id, record["api_key"], True)
        return Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY", evidence="test identity"), True

    runner.execute_one, runner.adapter.close = execute, close
    status = await runner.run(50)
    assert len(calls) == 2 and calls[0][2] == calls[1][2] and closed == [True]
    assert status["succeeded_authenticated"] == 2 and status["needs_review"] == 1
    assert status["pid"] is None and status["action"] == "PAUSED"
    with RunLock(settings.database):
        pass
    bulk.update(action="RUNNING", reason="", progress_at=time.time())
    second = BulkRunner(settings, tmp_path)

    async def reconcile_only(task, review, *_):
        assert review and task.id == calls[1][0]
        record = second.vault.get(task.secret_ref)
        record.update(api_key="sk-test-" + task.id, activated=True)
        second.vault.set(task.secret_ref, record)
        bulk.authenticate(task.user_id, record["api_key"], True)
        return Result(State.SUCCEEDED, "ACTIVATED_WITH_KEY", evidence="test login"), True

    second.execute_one = reconcile_only
    assert (await second.run(2))["succeeded_authenticated"] == 3
    with bulk.connection() as db:
        assert (
            db.execute("SELECT count(*) FROM bulk_requests WHERE historical=0").fetchone()[0] == 2
        )
