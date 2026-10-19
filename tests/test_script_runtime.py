from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agnes_provisioner.config import Settings
from agnes_provisioner.lock import RunLock
from agnes_provisioner.proxy import ProxyManager
from agnes_provisioner.runtime_migration import migrate_legacy
from agnes_provisioner.runtime_store import RuntimeStore
from agnes_provisioner.script_contract import ScriptFailure, validate_package, validate_results
from agnes_provisioner.script_runtime import ScriptRuntime
from agnes_provisioner.storage import Storage, StorageError
from agnes_provisioner.vault import Vault

ROOT = Path(__file__).resolve().parents[1]


class NoResources:
    def __init__(self):
        self.released = []
        self.submissions = []

    def list(self):
        return []

    def recover(self):
        pass

    def snapshot(self, bindings, requirements, count, site_id):
        return {}

    async def acquire(self, snapshot, site_id, task_id):
        return SimpleNamespace(mailbox=None, proxy=None, task_id=task_id)

    def mark_submitted(self, lease):
        self.submissions.append(lease.task_id)

    async def release(self, lease, *, submitted, succeeded):
        self.released.append((lease.task_id, submitted, succeeded))


@pytest.fixture
def settings(tmp_path):
    return Settings(database=tmp_path / "test.db", vault=tmp_path / "test.dpapi")


@pytest.fixture
def runtime(settings):
    return ScriptRuntime(settings, resources=NoResources())


def package(name="accounts"):
    return json.loads((ROOT / f"examples/script-demo-{name}.json").read_text(encoding="utf-8"))


def start(runtime, pkg=None, **kwargs):
    pkg = pkg or package()
    if not any(m["id"] == pkg["manifest"]["id"] and m["version"] == pkg["manifest"]["version"]
               for m in runtime.store.scripts()):
        runtime.store.import_package(pkg)
    return runtime.start({"script_id": pkg["manifest"]["id"],
                          "version": pkg["manifest"]["version"], "count": 20,
                          "concurrency": 4, "request_id": uuid4().hex, **kwargs})["batch"]


def wait(runtime):
    runtime.worker.join(20)
    assert not runtime.worker.is_alive()


def test_twenty_means_twenty_no_retries_and_persistent_results(runtime, settings):
    batch = start(runtime)
    wait(runtime)
    result = runtime.store.tasks(batch["id"], reveal=True)
    assert result["summary"] == {"total": 20, "succeeded": 17, "failed": 3,
                                 "running": 0, "pending": 0, "unknown": 0, "cancelled": 0}
    assert len(runtime.resources.released) == 20
    assert len(set(x[0] for x in runtime.resources.released)) == 20
    assert len(runtime.resources.submissions) == 17
    reopened = ScriptRuntime(settings, resources=NoResources())
    assert len(reopened.store.scripts()) >= 2
    assert reopened.store.tasks(batch["id"], reveal=True) == result
    assert reopened.store.tasks(batch["id"])["tasks"][0]["results"]["password"] == "••••••"
    assert b"demo-password-1" not in settings.database.read_bytes()
    assert b"demo-password-1" not in settings.vault.read_bytes()
    events = runtime.store.events(batch["id"], limit=500)["events"]
    assert "demo-password" not in json.dumps(events)
    assert any(e["stage"] == "cleanup" for e in events)


def test_two_sites_mutual_exclusion_idempotency_stop_and_lock_release(runtime, settings):
    request_id = uuid4().hex
    batch = start(runtime, count=20, concurrency=1, request_id=request_id,
                  parameters={"delay": 0.2, "fail_indices": []})
    duplicate = runtime.start({"request_id": request_id})
    assert duplicate["batch"]["id"] == batch["id"]
    another = ScriptRuntime(settings, resources=NoResources())
    assert another.overview()["active"]["id"] == batch["id"]
    with pytest.raises(StorageError):
        start(another, package("tokens"), count=1)
    runtime.stop(batch["id"])
    wait(runtime)
    tasks = runtime.store.tasks(batch["id"])
    assert tasks["summary"]["total"] == 20
    assert tasks["summary"]["cancelled"] > 0
    assert tasks["batch"]["state"] == "STOPPED"
    second = start(another, package("tokens"), count=1)
    wait(another)
    assert another.store.tasks(second["id"])["summary"]["succeeded"] == 1


def test_invalid_package_never_executes_and_failed_update_preserves_old(runtime, tmp_path):
    pkg = package()
    target = tmp_path / "import-side-effect.txt"
    pkg["source"] = f"open({str(target)!r}, 'w').write('bad')\n" + pkg["source"]
    runtime.store.import_package(pkg)
    assert not target.exists()
    invalid = package()
    invalid["manifest"]["version"] = "2.0.0"
    invalid["source"] = "def run(ctx): return {}"
    with pytest.raises(ValueError, match="async def"):
        runtime.store.import_package(invalid)
    assert runtime.store.script("demo-accounts", "1.0.0")[1] == pkg["source"]
    with pytest.raises(ValueError, match="已经存在"):
        runtime.store.import_package(pkg)
    invalid["source"] = "import nonexistent_runtime_dependency\nasync def run(ctx): return {}"
    with pytest.raises(ValueError, match="缺少依赖"):
        validate_package(invalid)
    invalid["manifest"]["api_version"] = 2
    with pytest.raises(ValueError, match="接口版本"):
        validate_package(invalid)


def test_update_pins_running_and_historical_version(runtime):
    old = package("tokens")
    old["source"] = "import asyncio\n" + old["source"].replace(
        "async def run(ctx):", "async def run(ctx):\n    await asyncio.sleep(0.1)")
    batch = start(runtime, old, count=2, concurrency=1)
    new = package("tokens")
    new["manifest"]["version"] = "2.0.0"
    new["manifest"]["result_fields"][2]["label"] = "新版额度"
    new["source"] = new["source"].replace("12.5", "99.0")
    runtime.store.import_package(new)
    wait(runtime)
    assert runtime.store.tasks(batch["id"])["tasks"][0]["results"]["credits"] == 12.5
    later = start(runtime, new, count=1)
    wait(runtime)
    assert runtime.store.tasks(later["id"])["tasks"][0]["results"]["credits"] == 99
    assert runtime.store.tasks(batch["id"])["fields"][2]["label"] == "额度"


def test_submission_exception_unknown_and_cleanup(runtime):
    pkg = package("tokens")
    pkg["source"] = """
async def run(ctx):
    ctx.register_secret('very-secret-token')
    ctx.mark_submitted()
    raise RuntimeError('very-secret-token')
async def close(ctx):
    ctx.log('cleanup called')
"""
    batch = start(runtime, pkg, count=1)
    wait(runtime)
    task = runtime.store.tasks(batch["id"])["tasks"][0]
    assert task["state"] == "UNKNOWN"
    assert len(runtime.resources.submissions) == 1
    assert runtime.resources.released[0][1:3] == (True, False)
    events = json.dumps(runtime.store.events(batch["id"]))
    assert "cleanup called" in events and "very-secret-token" not in events


def test_crash_recovery_never_requeues(settings):
    store = RuntimeStore(settings.database, Vault(settings.vault))
    manifest, _ = validate_package(package())
    store.create_batch("crashed", uuid4().hex, manifest.model_dump(), 3, {}, {})
    store.task_state("crashed-0001", "RUNNING")
    store.submitted("crashed-0001")
    store.task_state("crashed-0002", "RUNNING")
    reopened = ScriptRuntime(settings, resources=NoResources())
    tasks = reopened.store.tasks("crashed")
    assert [t["state"] for t in tasks["tasks"]] == ["UNKNOWN", "CANCELLED", "CANCELLED"]
    assert tasks["batch"]["state"] == "INTERRUPTED"
    with RunLock(settings.database):
        pass


def test_task_marker_failure_after_resource_marker_is_unknown(runtime, monkeypatch):
    def fail(_):
        raise OSError("simulated task-store failure")

    monkeypatch.setattr(runtime.store, "submitted", fail)
    batch = start(runtime, count=1, parameters={"fail_indices": [], "delay": 0})
    wait(runtime)
    assert runtime.store.tasks(batch["id"])["tasks"][0]["state"] == "UNKNOWN"
    assert runtime.resources.released[0][1] is True


@pytest.mark.parametrize("value", [True, "7", float("nan"), float("inf")])
def test_result_type_validation(value):
    with pytest.raises(ScriptFailure):
        validate_results([{"key": "number", "type": "number", "required": True}],
                         {"number": value})


def test_missing_and_undeclared_fields_and_csv(runtime):
    fields = [{"key": "x", "type": "string", "required": False}]
    assert validate_results(fields, {}) == {}
    with pytest.raises(ScriptFailure):
        validate_results(fields, {"y": "bad"})
    with pytest.raises(ScriptFailure):
        validate_results([{**fields[0], "required": True}], {})
    pkg = package("tokens")
    pkg["source"] = pkg["source"].replace("demo-token-", 'secret,quote\\"\\n')
    batch = start(runtime, pkg, count=1)
    wait(runtime)
    hidden = runtime.store.export_csv(batch["id"]).decode("utf-8-sig")
    assert "secret," not in hidden
    data = list(csv.DictReader(io.StringIO(
        runtime.store.export_csv(batch["id"], True).decode("utf-8-sig"))))
    assert data[0]["token"] == 'secret,quote"\n1'
    assert data[0]["credits"] == "12.5"


def test_legacy_migration_backup_rollback_idempotency_and_originals(settings):
    storage = Storage(settings.database)
    storage.initialize()
    ProxyManager(storage).import_text("http://fiction-user:fiction-pass@127.0.0.1:8089")
    storage.close()
    vault = Vault(settings.vault)
    vault.set("old-user", {"agnes_password": "old-password", "api_key": "old-key"})
    with sqlite3.connect(settings.database) as db:
        db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
                   ("u", "old@example.com", "Old", 1, "test", 1, "old-user", time.time()))
        db.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)",
                   ("old-batch", "agnes", "READY", "", 0, time.time()))
        db.execute("INSERT INTO registration_jobs "
                   "(id,batch_id,user_id,provider,state,phase,attempts,next_attempt_at,error_code,"
                   "message,created_at,submitted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   ("old-job", "old-batch", "u", "agnes", "SUCCEEDED", "DONE", 1, 0, "", "",
                    time.time(), time.time()))
        db.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?,?,?)",
                   ("account-1", "u", "agnes", "remote-1", "ACTIVE", "fixture", time.time(),
                    "old-user"))
        for number, submitted in ((2, time.time()), (3, None)):
            db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
                       (f"u{number}", f"old{number}@example.com", "Old", 1, "test", 1,
                        "old-user", time.time()))
            db.execute("INSERT INTO registration_jobs "
                       "(id,batch_id,user_id,provider,state,phase,attempts,next_attempt_at,"
                       "error_code,message,created_at,submitted_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (f"old-job-{number}", "old-batch", f"u{number}", "agnes", "RUNNING",
                        "REGISTER", 1, 0, "", "", time.time(), submitted))
        original = {table: db.execute(f"SELECT * FROM {table}").fetchall() for table in
                    ("users", "batches", "registration_jobs", "accounts", "proxies", "proxy_meta")}
    store = RuntimeStore(settings.database, vault)
    with pytest.raises(RuntimeError, match="MIGRATION_FAILURE"):
        migrate_legacy(store, fail_after=1)
    assert store.batches() == []
    assert vault.get("old-user")["api_key"] == "old-key"
    result = migrate_legacy(store)
    assert result["imported"] == 3 and Path(result["backup"]).exists()
    assert migrate_legacy(store)["imported"] == 0
    batch = store.batches()[0]
    assert batch["state"] == "ARCHIVED"
    assert store.tasks(batch["id"], reveal=True)["tasks"][0]["results"]["api_key"] == "old-key"
    assert [t["state"] for t in store.tasks(batch["id"])["tasks"]] == [
        "SUCCEEDED", "UNKNOWN", "CANCELLED"]
    with sqlite3.connect(settings.database) as db:
        for table, rows in original.items():
            assert db.execute(f"SELECT * FROM {table}").fetchall() == rows
    with sqlite3.connect(result["backup"]) as backup:
        assert backup.execute("SELECT COUNT(*) FROM registration_jobs").fetchone()[0] == 3


def test_structured_event_incremental_cursor_and_task_filter(runtime):
    batch = start(runtime, count=2)
    wait(runtime)
    task_id = f"{batch['id']}-0001"
    first = runtime.store.events(batch["id"], task_id, limit=1)
    second = runtime.store.events(batch["id"], task_id, after=first["cursor"], limit=500)
    assert len(first["events"]) == 1
    assert all(e["task_id"] == task_id and e["id"] > first["cursor"] for e in second["events"])


def test_resource_failure_does_not_silently_fallback(runtime):
    async def broken(*_):
        raise StorageError("邮箱资源已耗尽。")
    runtime.resources.acquire = broken
    batch = start(runtime, count=1)
    wait(runtime)
    task = runtime.store.tasks(batch["id"])["tasks"][0]
    assert task["state"] == "FAILED" and "耗尽" in task["message"]
    assert runtime.resources.submissions == []


def test_scripts_with_invalid_result_are_not_successful(runtime):
    pkg = package("tokens")
    pkg["source"] = "async def run(ctx):\n    return {'credits': 'wrong'}\n"
    batch = start(runtime, pkg, count=1)
    wait(runtime)
    assert runtime.store.tasks(batch["id"])["summary"]["failed"] == 1


def test_params_and_mutable_globals_isolated(runtime):
    pkg = package("tokens")
    pkg["manifest"]["parameters"] = {"items": []}
    pkg["source"] = """
counter = 0
async def run(ctx):
    global counter
    counter += 1
    ctx.parameters['items'].append(counter)
    return {'token':'private', 'url':'https://example.com', 'credits':len(ctx.parameters['items'])}
"""
    batch = start(runtime, pkg, count=3)
    wait(runtime)
    assert [r["results"]["credits"] for r in runtime.store.tasks(batch["id"])["tasks"]] == [1, 1, 1]
