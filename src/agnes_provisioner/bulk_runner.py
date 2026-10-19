"""Single-process execution with durable safety gates and a long-lived public cache."""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import ipaddress
import os
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx

from .agnes import AgnesAdapter
from .bulk_excel import write_bulk_excel
from .bulk_relay import MeteredRelay
from .bulk_store import BulkStore
from .domain import Result, State
from .lock import RunLock
from .mailbox import MailboxError, OutlookMailbox
from .models import Job, User
from .storage import Storage, StorageError
from .vault import Vault


async def mailbox_ready(vault, task, *, factory=OutlookMailbox, delay=3):
    mailbox = factory(vault, task.secret_ref)
    for attempt in range(2):
        try:
            return (mailbox, await asyncio.to_thread(mailbox.baseline)), None
        except MailboxError as error:
            if error.code == "MAILBOX_TOKEN_INVALID":
                return None, Result(State.SKIPPED, error.code, "邮箱令牌已失效；未提交注册")
            if error.code in {
                "MAILBOX_NETWORK", "MAILBOX_IMAP", "MAILBOX_RESPONSE", "MAILBOX_GRAPH"
            }:
                if attempt == 0:
                    await asyncio.sleep(delay)
                    continue
                return None, Result(
                    State.SKIPPED, error.code, "邮箱连接失败；退避复查一次仍失败，未提交注册"
                )
            return None, Result(
                State.NEEDS_REVIEW,
                error.code,
                "邮箱共享配置或授权异常，暂停并交回 Astra",
                pause=True,
            )


def claim_next(storage, bulk, *, allow_new=True):
    """All submitted work goes directly to normal-login recovery, never execute(register)."""
    rows = bulk.rows()
    eligible = [
        r
        for r in rows
        if not r["reason"]
        and r["state"] not in ("SKIPPED", "CANCELLED", "FAILED", "RUNNING")
        and not bulk.confirmed(r)
        and (
            allow_new
            or r["submitted_at"] is not None
            or r["state"] not in {"PENDING", "RETRY_WAIT"}
        )
        and not (r["error_code"] == "IP_REGISTRATION_LIMIT" and r["phase"] == "EMAIL_REQUESTED")
        and not (r["submitted_at"] is None and r["state"] == "NEEDS_REVIEW")
    ]
    eligible.sort(key=lambda r: (r["submitted_at"] is None, r["line"]))
    if not eligible:
        return None, False
    row = eligible[0]
    with bulk.connection() as db:
        reg_submitted = db.execute(
            "SELECT 1 FROM bulk_requests WHERE job_id=? "
            "AND kind IN ('REGISTRATION_SUBMITTED','KEY_REQUESTED')",
            (row["job_id"],),
        ).fetchone()
    only_email_requested = (
        row["phase"] == "EMAIL_REQUESTED"
        and row["state"] != "SUCCEEDED"
        and not reg_submitted
    )
    if only_email_requested:
        with bulk.connection(write=True) as db:
            db.execute(
                "UPDATE bulk_requests SET job_id=? WHERE job_id=? AND kind='EMAIL_REQUESTED'",
                (f"{row['job_id']}#retry-{int(time.time() * 1000)}", row["job_id"]),
            )
    with storage.session.begin() as session:
        job = session.get(Job, row["job_id"])
        if job.state == State.RUNNING:
            raise StorageError("RECOVERY_REQUIRED")
        if only_email_requested:
            job.phase = "PREPARE"
            job.submitted_at = None
            review = False
        else:
            review = job.submitted_at is not None or job.state not in {
                State.PENDING,
                State.RETRY_WAIT,
            }
        old = job.state
        job.state, job.started_at, job.finished_at = State.RUNNING, time.time(), None
        job.attempts += 1
        storage._event(session, job, old, "BULK_REVIEW" if review else "BULK_STARTED")
        return storage._task(job, session.get(User, job.user_id)), review


class ProxySlot:
    """One sticky egress session; clipboard and cookies stay inside its browser context."""

    def __init__(self):
        self.ip_session = None
        self.current_ip = ""


_SLOT = contextvars.ContextVar("agnes-proxy-slot", default=None)


class BulkRunner:
    def __init__(self, settings, root: Path):
        self.settings, self.root = settings, root
        self.bulk = BulkStore(settings.database)
        self.storage = Storage(settings.database)
        self.vault = Vault(settings.vault)
        self.adapter = AgnesAdapter(settings, self.vault)
        self.run_id = uuid4().hex
        self.current_task = None
        self.current_ip = ""
        self.current_started = 0
        self.ip_session = None
        self.fault = ""

    def meter(self, sent, received):
        self.bulk.traffic(self.run_id, sent, received)
        ctl = self.bulk.control()
        if (
            self.settings.concurrency == 1
            and sent + received - self.current_started > 10_000_000
            and self.current_task
        ):
            self.fault = "ACCOUNT_TRAFFIC_HIGH"
        if ctl["used_bytes"] >= ctl["budget_bytes"]:
            self.fault = "TRAFFIC_BUDGET"
        remaining = self.bulk.supplier_remaining(ctl)
        if remaining is not None and remaining <= ctl["finish_reserve_bytes"]:
            self.fault = "SUPPLIER_BALANCE_LOW"
        if self.fault:
            self.bulk.update(action="PAUSED", reason=self.fault)

    async def heartbeat(self):
        while True:
            now = time.time()
            # Keep the run alive while this process is actively supervising.
            self.bulk.update(heartbeat=now, supervisor_at=now)
            ctl = self.bulk.control()
            if ctl["action"] == "RUNNING":
                if time.time() - ctl["progress_at"] > 300:
                    self.fault = "NO_PROGRESS"
                if self.fault:
                    self.bulk.update(action="PAUSED", reason=self.fault)
            await asyncio.sleep(15)

    async def check_ip(self, relay, record):
        async with httpx.AsyncClient(
            proxy=httpx.Proxy(relay.url, auth=(record["username"], record["password"])),
            trust_env=False,
            timeout=25,
        ) as client:
            response = await client.get("https://ipinfo.io/ip")
            if response.status_code != 200:
                raise StorageError("EGRESS_CHECK_FAILED")
            try:
                return str(ipaddress.ip_address(response.text.strip()))
            except ValueError:
                raise StorageError("EGRESS_CHECK_FAILED") from None

    def _slot(self, slot=None):
        return slot or _SLOT.get() or self

    async def session(self, relay, base, *, review=False, slot=None):
        # Only fresh work may use a planned next allocation. Rejection stops the run.
        slot = self._slot(slot)
        if slot.ip_session and not review:
            # A session without an egress_ip was created but check_ip failed;
            # treat it as expired and allocate a fresh one.
            existing_ip = slot.ip_session.get("egress_ip")
            if existing_ip:
                with self.bulk.connection() as db:
                    sends = db.execute(
                        "SELECT count(*) FROM bulk_requests WHERE ip=? AND kind='EMAIL_REQUESTED'",
                        (existing_ip,),
                    ).fetchone()[0]
                if sends >= 2 or time.time() - slot.ip_session["created_at"] > 25 * 60:
                    slot.ip_session = None
            else:
                slot.ip_session = None
        if slot.ip_session is None:
            record = dict(base)
            record["session_id"] = uuid4().hex[:8]
            record["username"] += "-session-" + record["session_id"] + "-time-30"
            record["created_at"] = time.time()
            slot.ip_session = record
        record = slot.ip_session
        if time.time() - record["created_at"] > 29 * 60:
            raise StorageError("PROXY_SESSION_EXPIRED")
        ip = await self.check_ip(relay, record)
        if record.get("egress_ip") and record["egress_ip"] != ip:
            raise StorageError("EGRESS_CHANGED")
        record["egress_ip"] = ip
        slot.current_ip = ip
        if slot is self:
            self.current_ip = ip
        with self.bulk.connection() as db:
            blocked = db.execute(
                "SELECT 1 FROM bulk_blocks WHERE scope='ip' AND subject=? AND released_at IS NULL",
                (ip,),
            ).fetchone()
            sends = db.execute(
                "SELECT count(*) FROM bulk_requests WHERE ip=? AND kind='EMAIL_REQUESTED'", (ip,)
            ).fetchone()[0]
        if blocked or (not review and sends >= 2):
            raise StorageError("EGRESS_BLOCKED_OR_EXHAUSTED")
        self.vault.set("bulk-proxy-session-" + self.run_id, record)
        self.vault.set("bulk-proxy-session-" + self.run_id + "-" + record["session_id"], record)
        return {"server": relay.url, "username": record["username"], "password": record["password"]}

    async def checkpoint(self, task, phase, slot=None):
        slot = self._slot(slot)
        if time.time() - slot.ip_session["created_at"] >= 29 * 60:
            raise StorageError("PROXY_SESSION_EXPIRED")
        while True:
            delay = self.bulk.reserve(task.id, phase, slot.current_ip, self.settings.per_minute)
            if not delay:
                break
            await asyncio.sleep(min(delay, 1))
        self.storage.checkpoint(task.id, phase)

    async def authenticate(self, task, result, relay, proxy):
        record = self.vault.get(task.secret_ref)
        if result.state != State.SUCCEEDED or not record.get("api_key") or not result.evidence:
            return result
        identity = (
            record.get("activated") and record.get("email", "").casefold() == task.email.casefold()
        )
        with self.bulk.connection() as db:
            auth = db.execute(
                "SELECT key_sha256 FROM bulk_auth WHERE user_id=? AND http_status=200",
                (task.user_id,),
            ).fetchone()
        if auth and identity and auth[0] == hashlib.sha256(record["api_key"].encode()).hexdigest():
            return result
        async with httpx.AsyncClient(
            proxy=httpx.Proxy(relay.url, auth=(proxy["username"], proxy["password"])),
            trust_env=False,
            timeout=25,
        ) as client:
            response = await client.get(
                "https://apihub.agnes-ai.com/v1/models",
                headers={"Authorization": "Bearer " + record["api_key"]},
            )
        if response.status_code != 200 or not identity:
            return Result(
                State.NEEDS_REVIEW, "KEY_AUTH_FAILED", "已保存密钥，但认证未通过", pause=True
            )
        self.bulk.authenticate(task.user_id, record["api_key"], identity)
        return result

    async def execute_one(self, task, review, relay, base, slot=None):
        slot = self._slot(slot)
        prepared = None
        if not review:
            self.bulk.update(phase="MAILBOX_CHECK", progress_at=time.time())
            prepared, rejected = await mailbox_ready(self.vault, task)
            if rejected:
                return rejected, False
        self.bulk.gate(new_account=not review)
        proxy = await self.session(relay, base, review=review)

        # The first session check doubles as this account's start-IP check.
        async def checkpoint(phase):
            await self.checkpoint(task, phase)

        if review:
            result = await self.adapter.reconcile(task, proxy, checkpoint)
        else:
            result = await self.adapter.execute(task, proxy, checkpoint, prepared_mailbox=prepared)
        with self.bulk.connection() as db:
            kinds = {
                row[0]
                for row in db.execute(
                    "SELECT kind FROM bulk_requests WHERE job_id=?", (task.id,)
                )
            }
        submitted = "REGISTRATION_SUBMITTED" in kinds or "KEY_REQUESTED" in kinds
        if not submitted and result.code in {"VERIFY_TIMEOUT", "MAILBOX_TOKEN_INVALID"}:
            result = replace(result, state=State.SKIPPED, pause=False)
        if result.code in {
            "IP_REGISTRATION_LIMIT",
            "RATE_LIMIT",
            "SECURITY_CHECK",
            "EMAIL_DOMAIN_BLOCKED",
        }:
            self.bulk.block(
                result.code,
                scope="ip" if result.code == "IP_REGISTRATION_LIMIT" else "global",
                subject=slot.current_ip
                if result.code == "IP_REGISTRATION_LIMIT"
                else "registration",
                retry_at=time.time() + result.retry_after if result.retry_known else None,
                evidence="平台响应；详细恢复窗口须核对",
                pause=result.code != "IP_REGISTRATION_LIMIT" or self.settings.concurrency == 1,
            )
            slot.ip_session = None
            slot.current_ip = ""
            if result.code == "IP_REGISTRATION_LIMIT" and self.settings.concurrency > 1:
                result = replace(result, pause=False)
            else:
                result = replace(result, pause=True)
        result = await self.authenticate(task, result, relay, proxy)
        try:
            after = await self.check_ip(relay, slot.ip_session) if slot.ip_session else ""
        except (StorageError, httpx.HTTPError):
            after = ""
        stable = bool(after) and after == slot.current_ip
        if not stable:
            slot.ip_session = None
            slot.current_ip = ""
            if result.state == State.SUCCEEDED and result.code == "ACTIVATED_WITH_KEY":
                pass
            elif not result.pause:
                result = replace(
                    result,
                    state=State.UNKNOWN if submitted else State.PENDING,
                    code="EGRESS_CHANGED",
                    pause=False,
                )
        if not submitted and result.state in {State.PENDING, State.RETRY_WAIT, State.UNKNOWN}:
            if "EMAIL_REQUESTED" in kinds:
                with self.bulk.connection(write=True) as db:
                    db.execute(
                        "UPDATE bulk_requests SET job_id=? "
                        "WHERE job_id=? AND kind='EMAIL_REQUESTED'",
                        (f"{task.id}#retry-{int(time.time() * 1000)}", task.id),
                    )
            with self.storage.session.begin() as session:
                job = session.get(Job, task.id)
                if job:
                    job.phase = "PREPARE"
                    job.submitted_at = None
            result = replace(result, state=State.PENDING, pause=False)
        if result.code in {"EGRESS_CHANGED", "KEY_PENDING"}:
            result = replace(result, pause=False)
        elif result.code == "LOGIN_REJECTED" and not submitted:
            result = replace(result, pause=False)
        elif result.code in {
            "SECURITY_CHECK",
            "RATE_LIMIT",
            "EMAIL_DOMAIN_BLOCKED",
            "MAILBOX_OAUTH_CONFIG",
            "KEY_AUTH_FAILED",
        }:
            result = replace(result, pause=True)
        elif (
            self.settings.concurrency == 1
            and result.state in {State.UNKNOWN, State.PENDING_VERIFY, State.NEEDS_REVIEW}
        ):
            result = replace(result, pause=True)
        verified = (
            result.state == State.SUCCEEDED
            and result.code == "ACTIVATED_WITH_KEY"
            and not result.pause
        )
        return result, verified

    async def _finish_task(self, task, result, relay, started, verified, processed, index, slot):
        actual = self.storage.complete(task.id, result, max_attempts=1)
        result = replace(result, state=actual)
        spent = relay.sent_bytes + relay.received_bytes - started
        warning = self.bulk.result(task, result, slot.current_ip, spent, verified)
        if (
            warning
            in {
                "ACCOUNT_TRAFFIC_HIGH",
                "TRAFFIC_AVERAGE_HIGH",
                "REPEATED_FAILURE",
                "FAILURE_RATIO_HIGH",
            }
            and self.settings.concurrency > 1
        ):
            warning = ""
        if warning or result.pause or self.fault:
            self.bulk.incident(
                self.root / "output/production",
                self.fault or warning or result.code,
                task,
                slot.current_ip,
            )
            return True
        if (processed + index + 1) % 50 == 0:
            self._export()
        return False

    def _export(self):
        try:
            write_bulk_excel(
                self.root / "outputs/production/Agnes开户结果.xlsx", self.bulk, self.vault
            )
        except StorageError as error:
            self.bulk.incident(
                self.root / "output/production", str(error), self.current_task, self.current_ip
            )

    async def _run_claimed(self, task, review, relay, base, slot, processed, index):
        self.current_task = task
        self.current_ip = slot.current_ip
        started = relay.sent_bytes + relay.received_bytes
        if self.settings.concurrency == 1:
            self.current_started = started
        verified = False
        try:
            token = _SLOT.set(slot)
            try:
                result, verified = await self.execute_one(task, review, relay, base)
            finally:
                _SLOT.reset(token)
        except asyncio.CancelledError:
            result = Result(
                State.UNKNOWN,
                "INTERRUPTED",
                "任务已中断，先核查既有结果",
                pause=True,
            )
            self.storage.complete(task.id, result)
            raise
        except (StorageError, httpx.HTTPError) as error:
            code = str(error) if isinstance(error, StorageError) else "NETWORK_ERROR"
            slot.ip_session = None
            slot.current_ip = ""
            with self.bulk.connection() as db:
                submitted_reg = db.execute(
                    "SELECT 1 FROM bulk_requests WHERE job_id=? "
                    "AND kind IN ('REGISTRATION_SUBMITTED','KEY_REQUESTED')",
                    (task.id,),
                ).fetchone()
                email_only = db.execute(
                    "SELECT 1 FROM bulk_requests WHERE job_id=? AND kind='EMAIL_REQUESTED'",
                    (task.id,),
                ).fetchone()
            # Pre-registration network failures are transient proxy noise;
            # retry them without pausing the whole batch.
            if submitted_reg:
                state = State.UNKNOWN
                message = "提交后网络异常，保留待核查"
                pause = self.settings.concurrency == 1
            else:
                if email_only:
                    with self.bulk.connection(write=True) as db:
                        db.execute(
                            "UPDATE bulk_requests SET job_id=? "
                            "WHERE job_id=? AND kind='EMAIL_REQUESTED'",
                            (f"{task.id}#retry-{int(time.time() * 1000)}", task.id),
                        )
                with self.storage.session.begin() as session:
                    job = session.get(Job, task.id)
                    if job:
                        job.phase = "PREPARE"
                        job.submitted_at = None
                state = State.PENDING
                message = "提交前网络失败，下次执行重试"
                pause = False
            result = Result(state, code, message, pause=pause)
        except Exception as error:
            import traceback
            from pathlib import Path
            trace_path = Path(self.root / "output/production" / "latest-internal-traceback.txt")
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(traceback.format_exc(), encoding="utf-8")
            result = Result(
                State.NEEDS_REVIEW,
                "INTERNAL_" + type(error).__name__,
                "程序异常，已停止新提交",
                pause=True,
            )
        stopped = await self._finish_task(
            task, result, relay, started, verified, processed, index, slot
        )
        self.current_task = None
        return stopped

    async def run(self, limit):
        if not 1 <= self.settings.concurrency <= self.settings.approval.concurrency:
            raise StorageError("生产并发必须在授权范围内。")
        with RunLock(self.settings.database):
            self.bulk.gate(new_account=True)
            with self.bulk.connection() as db:
                processed = db.execute(
                    "SELECT count(DISTINCT job_id) FROM bulk_results"
                ).fetchone()[0]
            accepted = self.bulk.control()["accepted_count"]
            ceiling = 2 if accepted < 2 else processed + limit
            new_allowance = max(0, ceiling - processed)
            upstream = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
            if not upstream:
                raise StorageError("EXISTING_LOCAL_UPSTREAM_REQUIRED")
            base = Vault(self.root / "data/proxy-image-20261014.dpapi").get("screenshot_proxy")
            self.bulk.start_run(self.run_id)
            heartbeat = asyncio.create_task(self.heartbeat())
            remaining = {"limit": limit, "allowance": new_allowance, "index": 0}
            try:
                async with MeteredRelay(upstream, base["server"], self.meter) as relay:

                    async def worker():
                        slot = ProxySlot()
                        while remaining["limit"] > 0 and not self.fault:
                            try:
                                self.bulk.gate(new_account=True)
                            except StorageError:
                                return
                            task, review = claim_next(
                                self.storage, self.bulk, allow_new=remaining["allowance"] > 0
                            )
                            if task is None:
                                return
                            remaining["limit"] -= 1
                            if not review:
                                remaining["allowance"] -= 1
                            index = remaining["index"]
                            remaining["index"] += 1
                            stopped = await self._run_claimed(
                                task, review, relay, base, slot, processed, index
                            )
                            if stopped or self.fault:
                                return

                    await asyncio.gather(
                        *[worker() for _ in range(min(self.settings.concurrency, limit))]
                    )
            except StorageError as error:
                self.bulk.incident(
                    self.root / "output/production", str(error), self.current_task, self.current_ip
                )
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                await self.adapter.close()
                self.bulk.finish_run(self.run_id)
                self._export()
                self.storage.close()
        return self.bulk.status()
