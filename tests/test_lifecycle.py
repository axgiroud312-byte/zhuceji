import asyncio
import csv
import time

import pytest
from sqlalchemy import select

from agnes_provisioner.config import Settings
from agnes_provisioner.domain import Result, State
from agnes_provisioner.lock import RunLock
from agnes_provisioner.mock import MockAdapter
from agnes_provisioner.models import JobEvent, User
from agnes_provisioner.scheduler import Scheduler
from agnes_provisioner.storage import Storage, StorageError
from agnes_provisioner.users import import_users


@pytest.fixture
def storage(tmp_path):
    value = Storage(tmp_path / "jobs.db")
    value.initialize()
    yield value
    value.close()


def seed(storage, count, cases=None):
    with storage.session.begin() as session:
        for i in range(count):
            session.add(
                User(
                    id=f"u{i}",
                    email=f"u{i}@example.com",
                    consent=True,
                    consent_reference="test",
                    display_name=(cases or {}).get(i, ""),
                    created_at=time.time(),
                )
            )
    storage.create_batch("test", "mock")


def test_import_normalizes_duplicates_and_rejects_unapproved(storage, tmp_path):
    path = tmp_path / "users.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["user_id", "email", "consent", "consent_reference"])
        writer.writerows(
            [
                ["a", "First@EXAMPLE.com", True, "test"],
                ["a", "first@example.com", True, "test"],
                ["b", "first@example.com", True, "test"],
                ["c", "third@example.com", False, "test"],
            ]
        )
    report = import_users(storage, path)
    assert (report["imported"], report["duplicates"], report["rejected"]) == (1, 1, 2)
    assert "third@example.com" not in str(report)
    assert import_users(storage, path)["imported"] == 0
    first = storage.create_batch("first", "mock")
    second = storage.create_batch("second", "mock")
    assert first["created"] == 1 and second["created"] == 0


def test_crash_recovery_distinguishes_submission(storage):
    seed(storage, 2)
    storage.control("test", "RUNNING")
    submitted = storage.claim("test", 3)
    storage.checkpoint(submitted.id, "EMAIL_REQUESTED")
    unsubmitted = storage.claim("test", 3)
    report = storage.recover("test")
    assert report == {"UNKNOWN": 1, "PENDING": 1}
    claimed = storage.claim("test", 3)
    assert claimed.id == unsubmitted.id
    assert storage.claim("test", 3) is None
    assert storage.events(submitted.id)[-1]["code"] == "INTERRUPTED_AFTER_SUBMIT"


def test_submitted_task_cannot_be_automatically_retried(storage):
    seed(storage, 1)
    storage.control("test", "RUNNING")
    task = storage.claim("test", 3)
    storage.checkpoint(task.id, "SUBMITTED")
    actual = storage.complete(task.id, Result(State.RETRY_WAIT, "NETWORK", "lost connection"))
    assert actual == State.UNKNOWN
    assert storage.claim("test", 3) is None
    with pytest.raises(StorageError):
        storage.complete(task.id, Result(State.SUCCEEDED))


async def test_retry_unknown_and_verification_remain_distinct(storage):
    seed(storage, 20, {0: "network", 1: "unknown", 2: "verify"})
    settings = Settings(
        database=storage.path, concurrency=3, per_minute=1000000, retry_delay_seconds=0
    )
    adapter = MockAdapter()
    result = await Scheduler(storage, settings, adapter).run("test")
    assert result["states"] == {"PENDING_VERIFY": 1, "SUCCEEDED": 18, "UNKNOWN": 1}
    assert adapter.peak <= 3
    assert all(count == 1 for count in adapter.submissions.values())
    repeated = await Scheduler(storage, settings, adapter).run("test")
    assert repeated["started"] == 0
    assert sum(adapter.submissions.values()) == 20


async def test_submission_rate_is_shared_and_persistent(storage):
    seed(storage, 4)
    settings = Settings(database=storage.path, concurrency=3, per_minute=600, retry_delay_seconds=0)
    await Scheduler(storage, settings, MockAdapter()).run("test", limit=2)
    await Scheduler(storage, settings, MockAdapter()).run("test")
    with storage.session() as session:
        times = list(
            session.scalars(
                select(JobEvent.at)
                .where(JobEvent.code == "CHECKPOINT_SUBMITTED")
                .order_by(JobEvent.id)
            )
        )
    assert len(times) == 4
    assert all(b - a >= 0.095 for a, b in zip(times, times[1:]))


async def test_pause_prevents_submission_and_lock_prevents_second_runner(storage):
    seed(storage, 1)
    entered = asyncio.Event()
    ready = asyncio.Event()

    class ControlledAdapter:
        async def execute(self, task, proxy, checkpoint):
            entered.set()
            await ready.wait()
            await checkpoint("SUBMITTED")
            return Result(State.SUCCEEDED, evidence="test activation")

        async def close(self):
            pass

    settings = Settings(database=storage.path)
    running = asyncio.create_task(Scheduler(storage, settings, ControlledAdapter()).run("test"))
    await entered.wait()
    with pytest.raises(StorageError), RunLock(storage.path):
        pass
    storage.control("test", "PAUSED")
    ready.set()
    await asyncio.sleep(0.15)
    assert storage.jobs("test")[0]["phase"] == "PREPARE"
    storage.control("test", "RUNNING")
    assert (await running)["states"] == {"SUCCEEDED": 1}


async def test_retries_are_finite(storage):
    seed(storage, 1)

    class Offline:
        async def execute(self, *args):
            return Result(State.RETRY_WAIT, "NETWORK", "offline")

        async def close(self):
            pass

    settings = Settings(database=storage.path, retry_delay_seconds=0, max_attempts=2)
    report = await Scheduler(storage, settings, Offline()).run("test")
    assert report["states"] == {"FAILED": 1}
    assert storage.jobs("test")[0]["attempts"] == 2
