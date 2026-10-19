from __future__ import annotations

import asyncio
import time
from dataclasses import replace

import httpx

from .config import Settings
from .domain import Adapter, Result, State, StoppedBeforeSubmit, Task
from .lock import RunLock
from .models import Job
from .proxy import ProxyManager
from .storage import Storage, StorageError


class Scheduler:
    def __init__(self, storage: Storage, settings: Settings, adapter: Adapter):
        self.storage = storage
        self.settings = settings
        self.adapter = adapter
        self.proxies = ProxyManager(storage)
        self.submission_lock = asyncio.Lock()
        self.halt = False
        self.peak = 0

    async def _gate(self, batch_id: str) -> None:
        while True:
            batch = self.storage.batch(batch_id)
            if self.halt or batch.action in {"STOPPING", "STOPPED"}:
                raise StoppedBeforeSubmit()
            if batch.action == "RUNNING" and batch.blocked_until <= time.time():
                return
            await asyncio.sleep(0.1)

    async def _checkpoint(self, task: Task, phase: str) -> None:
        rate_limited = phase in {"SUBMITTED", "REGISTRATION_SUBMITTED"}
        if not rate_limited:
            await self._gate(task.batch_id)
            self.storage.checkpoint(task.id, phase)
            return
        async with self.submission_lock:
            while True:
                await self._gate(task.batch_id)
                previous = self.storage.last_submission(self.storage.batch(task.batch_id).provider)
                remaining = previous + 60 / self.settings.per_minute - time.time()
                if remaining <= 0:
                    self.storage.checkpoint(task.id, phase)
                    return
                await asyncio.sleep(min(remaining, 0.1))

    async def _acquire_proxy(self, task: Task, bound: str | None):
        pool_cfg = self.settings.proxy_pool
        while True:
            await self._gate(task.batch_id)
            lease = self.proxies.acquire(
                task.id,
                bound,
                session_suffix_template=pool_cfg.session_suffix_template,
                enable_session_stickiness=pool_cfg.enable_session_stickiness,
            )
            if lease:
                return lease
            nodes = self.proxies.list()
            # An occupied pool is not an unavailable pool. Wait without burning
            # another task attempt or pausing other workers.
            busy = any(
                (not bound or node["id"] == bound)
                and (bound or node["enabled"])
                and (node["checking"] or (node["status"] == "HEALTHY" and node["leased"]))
                for node in nodes
            )
            if not busy:
                return None
            await asyncio.sleep(0.05)

    async def _execute(self, task: Task, use_proxy: bool, *, verification: bool = False) -> None:
        lease = None
        execution_started = False
        result = Result(State.UNKNOWN, "INTERRUPTED", "任务执行中断")
        pool_cfg = self.settings.proxy_pool
        try:
            if use_proxy:
                bound = task.proxy_id if task.submitted_at is not None else None
                if task.submitted_at is not None and not bound:
                    if self.settings.proxy_required:
                        result = Result(
                            State.NEEDS_REVIEW, "PROXY_BINDING_MISSING",
                            "已提交任务缺少原代理绑定，需要人工核查", pause=True,
                        )
                    else:
                        # Existing direct connections stay direct during login
                        # verification, even if a pool was imported afterwards.
                        use_proxy = False
                else:
                    lease = await self._acquire_proxy(task, bound)
                if not lease:
                    if use_proxy and result.code != "PROXY_BINDING_MISSING":
                        result = Result(
                            State.NEEDS_REVIEW,
                            "PROXY_UNAVAILABLE",
                            "原绑定代理不可用，请人工核查；不会切换已提交任务的代理"
                            if bound else "没有可用代理，请检查代理健康状态",
                            pause=True,
                        )
                else:
                    self.storage.set_proxy(task.id, lease[0])
            if not use_proxy or lease:
                execution_started = True
                reconcile = getattr(self.adapter, "reconcile", None) if verification else None
                operation = reconcile if callable(reconcile) else self.adapter.execute
                result = await operation(
                    task,
                    lease[1] if lease else None,
                    lambda phase: self._checkpoint(task, phase),
                )
        except StoppedBeforeSubmit:
            result = Result(State.PENDING, "STOPPED", "已停止后续提交")
        except asyncio.CancelledError:
            result = Result(State.PENDING, "INTERRUPTED", "程序中断；未提交任务可恢复")
            raise
        except (httpx.TransportError, ConnectionError, TimeoutError):
            result = Result(
                State.RETRY_WAIT, "NETWORK", "网络连接中断；已提交任务需先核查",
                proxy_failed=lease is not None,
            )
        except Exception as error:
            result = Result(
                State.RETRY_WAIT,
                "INTERNAL_" + type(error).__name__,
                "执行异常；已提交任务将进入核查",
            )
        finally:
            # Task is an immutable claim-time snapshot. Checkpoints written by
            # the adapter must be read back before deciding whether retry is safe.
            with self.storage.session() as session:
                job = session.get(Job, task.id)
                submitted = bool(job and job.submitted_at is not None)
            result_achieved = result.state == State.SUCCEEDED and bool(result.evidence) and (
                not self.settings.key_flow.require_key
                or result.code == "ACTIVATED_WITH_KEY"
            )
            ip_limit_hit = result.code == "IP_REGISTRATION_LIMIT"
            network_failed = result.proxy_failed or result.code in {"NETWORK", "NETWORK_ERROR"}
            if lease:
                self.proxies.release(
                    lease[0],
                    task.id,
                    network_failed,
                    result_achieved=result_achieved,
                    force_rotate=ip_limit_hit and pool_cfg.auto_switch_on_ip_limit,
                    rotate_every=pool_cfg.rotate_every,
                    rotate_mode=pool_cfg.rotate_mode,
                    rotate_executions_limit=pool_cfg.rotate_executions_limit,
                    blocked=ip_limit_hit,
                    preserve_binding=submitted and not result_achieved,
                    enable_session_stickiness=pool_cfg.enable_session_stickiness,
                    execution_started=execution_started,
                )
                if ip_limit_hit or network_failed:
                    alternatives = [
                        node for node in self.proxies.list()
                        if node["enabled"] and (
                            node["available"] or node["checking"]
                            or (node["status"] == "HEALTHY" and node["leased"])
                        )
                    ]
                    if not submitted and pool_cfg.auto_switch_on_ip_limit and alternatives:
                        result = replace(
                            result,
                            state=State.RETRY_WAIT,
                            message="提交前代理受限或断连，未提交任务将使用下一个健康代理或新会话继续",
                            pause=False,
                        )
                    elif submitted:
                        result = replace(
                            result,
                            state=State.UNKNOWN if result.state in {
                                State.RETRY_WAIT, State.PENDING
                            } else result.state,
                            message="提交后代理受限或断连，已保留原代理和会话绑定；需核查，禁止自动重提",
                            pause=True,
                        )
                    else:
                        result = replace(
                            result, state=State.NEEDS_REVIEW, pause=True,
                            message="代理受限或断连；自动切换未开启或没有其他健康代理，请检查代理池",
                        )
            state = self.storage.complete(
                task.id,
                result,
                max_attempts=self.settings.max_attempts,
                retry_delay=self.settings.retry_delay_seconds,
            )
            if result.code == "RATE_LIMIT":
                self.storage.block(task.batch_id, max(result.retry_after, 60))
            if result.code == "EMAIL_DOMAIN_BLOCKED":
                self.storage.hold_domain(
                    task.batch_id, task.email.rpartition("@")[2], result.message
                )
            if result.pause:
                self.halt = True
                self.storage.control(task.batch_id, "PAUSED", result.message)
            if state == State.UNKNOWN and result.state == State.RETRY_WAIT:
                self.halt = True
                self.storage.control(task.batch_id, "PAUSED", "已提交任务出现异常，需要核查")

    async def verify_job(self, job_id: str) -> dict:
        with self.storage.session() as session:
            job = session.get(Job, job_id)
            if not job:
                raise StorageError("找不到此任务。")
            batch_id = job.batch_id
        return await self.verify_batch(batch_id, job_ids=[job_id])

    async def verify_batch(
        self, batch_id: str, job_ids: list[str] | None = None, limit: int | None = None
    ) -> dict:
        if limit is not None and limit < 0:
            raise StorageError("核验数量不能小于零。")
        verified_count = 0
        with RunLock(self.storage.path):
            batch = self.storage.batch(batch_id)
            expected = "mock" if self.settings.mode == "mock" else "agnes-api"
            if batch.provider != expected:
                raise StorageError("核验配置与批次的执行模式不同；未修改任何任务。")
            all_jobs = {job["job_id"]: job for job in self.storage.jobs(batch_id)}
            if job_ids is None:
                selected = list(all_jobs)
            else:
                selected = list(dict.fromkeys(job_ids))
                if set(selected) - set(all_jobs):
                    raise StorageError("选中的任务不在当前批次中；未修改任何任务。")
            candidates = []
            for job_id in selected:
                job = all_jobs[job_id]
                if (
                    job_ids is None and job["state"] == State.SUCCEEDED
                    and job["error_code"] == "ACTIVATED_WITH_KEY"
                ):
                    continue
                if job["state"] in {
                    State.PENDING_VERIFY, State.UNKNOWN, State.NEEDS_REVIEW, State.SUCCEEDED
                }:
                    candidates.append(job_id)
                elif job_ids is not None and job["state"] in {State.PENDING, State.RETRY_WAIT}:
                    candidates.append(job_id)
            if limit is not None:
                candidates = candidates[:limit]
            if not candidates:
                return dict(self.storage.summary(batch_id), verified_started=0)
            nodes = self.proxies.list()
            use_proxy = self.settings.proxy_required or bool(nodes)
            if (
                self.settings.mode == "agnes"
                and (use_proxy or any(all_jobs[jid]["proxy_id"] for jid in candidates))
                and not self.settings.approval.proxies_allowed
            ):
                raise StorageError("核验配置尚未允许代理，请核对 approval.proxies_allowed。")
            previous_action = batch.action
            previous_reason = batch.pause_reason
            self.storage.control(batch_id, "RUNNING")
            try:
                for jid in candidates:
                    cur_action = self.storage.batch(batch_id).action
                    if self.halt or cur_action in {"STOPPING", "STOPPED", "PAUSED"}:
                        break
                    if all_jobs[jid]["state"] in {State.PENDING, State.RETRY_WAIT}:
                        # An explicit login request may promote an unsubmitted
                        # task, but never clears a persisted submit boundary.
                        self.storage.requeue_job(
                            jid, "手动选择登录核验（不重新注册）", login_only=True
                        )
                    try:
                        task = self.storage.claim_verification(jid)
                    except StorageError:
                        continue
                    if task.phase in {"PREPARE", "EMAIL_REQUESTED"}:
                        # Execute-only adapters also receive a login-only task.
                        # The original persisted phase remains available in the audit.
                        task = replace(task, phase="REGISTRATION_SUBMITTED")
                    await self._execute(
                        task, use_proxy or task.proxy_id is not None, verification=True
                    )
                    verified_count += 1
            finally:
                await self.adapter.close()
                if not self.halt:
                    self.storage.control(batch_id, previous_action, previous_reason)
        return dict(self.storage.summary(batch_id), verified_started=verified_count)

    async def run(self, batch_id: str, limit: int | None = None) -> dict:
        provider = "mock" if self.settings.mode == "mock" else "agnes-api"
        if self.storage.batch(batch_id).provider != provider:
            raise StorageError("批次与执行模式不同。模拟任务请使用模拟配置。")
        nodes = self.proxies.list()
        use_proxy = self.settings.proxy_required or bool(nodes)
        if (
            self.settings.mode == "agnes"
            and use_proxy
            and not self.settings.approval.proxies_allowed
        ):
            raise StorageError("此授权配置未允许代理，请核对 approval.proxies_allowed。")
        tasks = set()
        started = 0
        with RunLock(self.storage.path):
            if self.storage.batch(batch_id).action == "PAUSED":
                raise StorageError("批次已暂停；请核查暂停原因并显式恢复，run 不会清除暂停。")
            self.storage.recover(batch_id)
            self.storage.control(batch_id, "RUNNING")
            try:
                while True:
                    batch = self.storage.batch(batch_id)
                    if batch.action in {"STOPPING", "STOPPED"}:
                        self.halt = True
                    while (
                        not self.halt
                        and batch.action == "RUNNING"
                        and len(tasks) < self.settings.concurrency
                        and (limit is None or started < limit)
                    ):
                        task = self.storage.claim(batch_id, self.settings.max_attempts)
                        if not task:
                            break
                        tasks.add(asyncio.create_task(self._execute(task, use_proxy)))
                        started += 1
                        self.peak = max(self.peak, len(tasks))
                    if not tasks and (
                        self.halt
                        or not self.storage.work_remaining(batch_id)
                        or (limit is not None and started >= limit)
                    ):
                        break
                    if tasks:
                        done, tasks = await asyncio.wait(
                            tasks, timeout=0.1, return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in done:
                            task.result()
                    else:
                        await asyncio.sleep(0.1)
            finally:
                if tasks:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                await self.adapter.close()
                if self.storage.batch(batch_id).action != "PAUSED":
                    self.storage.control(batch_id, "STOPPED")
        return dict(
            self.storage.summary(batch_id),
            started=started,
            peak_concurrency=self.peak,
            action=self.storage.batch(batch_id).action,
        )
