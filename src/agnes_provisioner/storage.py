from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, event, func, select
from sqlalchemy.orm import sessionmaker

from .domain import TRANSITIONS, Result, State, Task
from .models import Account, Base, Batch, Job, JobEvent, Proxy, User
from .privacy import redact


class StorageError(RuntimeError):
    pass


class Storage:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            "sqlite:///" + self.path.as_posix(), connect_args={"timeout": 15}
        )

        @event.listens_for(self.engine, "connect")
        def sqlite_options(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=15000")

        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            Base.metadata.create_all(bind=connection)

    @staticmethod
    def _event(session, job: Job, old: str, code: str = "", message: str = "") -> None:
        session.add(
            JobEvent(
                job_id=job.id,
                at=time.time(),
                from_state=old,
                to_state=job.state,
                code=code,
                message=redact(message)[:256],
            )
        )

    def create_batch(self, batch_id: str, provider: str, users: list[str] | None = None) -> dict:
        if not batch_id or len(batch_id) > 80:
            raise StorageError("批次名称应为 1 至 80 个字符。")
        with self.session.begin() as session:
            batch = session.get(Batch, batch_id)
            if batch and batch.provider != provider:
                raise StorageError("此批次属于另一个执行模式，请使用新的批次名称。")
            if not batch:
                session.add(Batch(id=batch_id, provider=provider, created_at=time.time()))
                session.flush()
            query = select(User).where(User.consent.is_(True))
            if users is not None:
                found = set(session.scalars(select(User.id).where(User.id.in_(users))))
                if set(users) - found:
                    raise StorageError("指定的用户尚未导入。")
                query = query.where(User.id.in_(users))
            existing = set(session.scalars(select(Job.user_id).where(Job.provider == provider)))
            count = skipped = 0
            for user in session.scalars(query):
                if user.id in existing:
                    skipped += 1
                    continue
                job = Job(
                    id=str(uuid4()),
                    batch_id=batch_id,
                    user_id=user.id,
                    provider=provider,
                    state=State.PENDING,
                    created_at=time.time(),
                )
                session.add(job)
                session.flush()
                self._event(session, job, "", "CREATED", "开户任务已创建")
                count += 1
            return {"batch": batch_id, "created": count, "duplicates": skipped}

    def batch(self, batch_id: str) -> Batch:
        with self.session() as session:
            batch = session.get(Batch, batch_id)
            if not batch:
                raise StorageError("找不到此批次，请先创建批次。")
            return batch

    def control(self, batch_id: str, action: str, reason: str = "") -> None:
        with self.session.begin() as session:
            batch = session.get(Batch, batch_id)
            if not batch:
                raise StorageError("找不到此批次。")
            batch.action = action
            batch.pause_reason = redact(reason)[:256]

    def block(self, batch_id: str, seconds: float) -> None:
        with self.session.begin() as session:
            batch = session.get(Batch, batch_id)
            batch.blocked_until = max(batch.blocked_until, time.time() + max(seconds, 1))

    @staticmethod
    def _task(job: Job, user: User) -> Task:
        return Task(
            job.id,
            job.batch_id,
            user.id,
            user.email,
            user.display_name,
            user.secret_ref,
            user.mailbox_authorized,
            job.attempts,
            job.phase,
            job.submitted_at,
            job.proxy_id,
        )

    def claim(self, batch_id: str, max_attempts: int) -> Task | None:
        with self.session.begin() as session:
            batch = session.get(Batch, batch_id)
            if batch.action != "RUNNING" or batch.blocked_until > time.time():
                return None
            job = session.scalar(
                select(Job)
                .where(
                    Job.batch_id == batch_id,
                    Job.state.in_([State.PENDING, State.RETRY_WAIT]),
                    Job.next_attempt_at <= time.time(),
                )
                .order_by(Job.created_at, Job.id)
                .limit(1)
            )
            if not job:
                return None
            user = session.get(User, job.user_id)
            if not user.consent:
                old = job.state
                job.state = State.CANCELLED
                job.error_code = "CONSENT_REVOKED"
                job.finished_at = time.time()
                self._event(session, job, old, job.error_code, "此用户的开户授权已撤销")
                return None
            if job.submitted_at is not None:
                old = job.state
                job.state = State.UNKNOWN
                job.error_code = "SUBMISSION_ALREADY_STARTED"
                self._event(session, job, old, job.error_code, "先核查已提交任务")
                return None
            if job.attempts >= max_attempts:
                old = job.state
                job.state = State.FAILED
                job.error_code = "ATTEMPTS_EXHAUSTED"
                job.finished_at = time.time()
                self._event(session, job, old, job.error_code, "已达到重试次数上限")
                return None
            old = job.state
            job.state = State.RUNNING
            job.attempts += 1
            job.started_at = time.time()
            job.finished_at = None
            self._event(session, job, old, "STARTED", "开始执行")
            return self._task(job, user)

    def checkpoint(self, job_id: str, phase: str) -> None:
        with self.session.begin() as session:
            job = session.get(Job, job_id)
            if not job or job.state != State.RUNNING:
                raise StorageError("任务已不在执行中，不能提交。")
            job.phase = phase
            job.submitted_at = time.time()
            self._event(session, job, job.state, "CHECKPOINT_" + phase, "提交边界已持久保存")

    def last_submission(self, provider: str) -> float:
        with self.session() as session:
            return (
                session.scalar(
                    select(func.max(JobEvent.at))
                    .join(Job)
                    .where(
                        Job.provider == provider,
                        JobEvent.code.in_(
                            ["CHECKPOINT_SUBMITTED", "CHECKPOINT_REGISTRATION_SUBMITTED"]
                        ),
                    )
                )
                or 0
            )

    def set_proxy(self, job_id: str, proxy_id: str | None) -> None:
        with self.session.begin() as session:
            session.get(Job, job_id).proxy_id = proxy_id

    def complete(
        self, job_id: str, result: Result, *, max_attempts: int = 3, retry_delay: float = 5
    ) -> State:
        with self.session.begin() as session:
            job = session.get(Job, job_id)
            if not job:
                raise StorageError("找不到此任务。")
            state = result.state
            if state in {State.RETRY_WAIT, State.PENDING} and job.submitted_at is not None:
                state = State.UNKNOWN
            if state == State.SUCCEEDED and not result.evidence:
                raise StorageError("确认成功需要激活或登录核验证据。")
            if state == State.RETRY_WAIT and job.attempts >= max_attempts:
                state = State.FAILED
            old = State(job.state)
            if state not in TRANSITIONS[old]:
                raise StorageError(f"不允许从 {old} 变更为 {state}。")
            job.state = state
            job.error_code = result.code
            job.message = redact(result.message)[:256]
            if state == State.RETRY_WAIT:
                job.next_attempt_at = time.time() + max(result.retry_after, retry_delay)
            if state not in {State.PENDING, State.RETRY_WAIT}:
                job.finished_at = time.time()
            self._event(session, job, old, result.code, result.message)
            if state in {State.SUCCEEDED, State.PENDING_VERIFY}:
                account = session.scalar(
                    select(Account).where(
                        Account.user_id == job.user_id, Account.provider == job.provider
                    )
                )
                if not account:
                    account = Account(id=str(uuid4()), user_id=job.user_id, provider=job.provider)
                    session.add(account)
                account.status = state
                account.remote_id = result.account_id
                account.evidence = redact(result.evidence)[:256]
                if state == State.SUCCEEDED:
                    account.activated_at = time.time()
                    account.api_key_ref = job.user_id if result.code == "ACTIVATED_WITH_KEY" else ""
            return state

    def recover(self, batch_id: str) -> dict:
        recovered = Counter()
        with self.session.begin() as session:
            jobs = list(
                session.scalars(
                    select(Job).where(Job.batch_id == batch_id, Job.state == State.RUNNING)
                )
            )
            for job in jobs:
                old = job.state
                job.state = State.UNKNOWN if job.submitted_at is not None else State.PENDING
                job.error_code = "INTERRUPTED_AFTER_SUBMIT" if job.submitted_at else "INTERRUPTED"
                job.message = "执行中断；已提交的任务需要核查"
                self._event(session, job, old, job.error_code, job.message)
                recovered[job.state] += 1
            batch_jobs = select(Job.id).where(Job.batch_id == batch_id)
            for proxy in session.scalars(select(Proxy).where(
                Proxy.leased_job_id.in_(batch_jobs),
                ~Proxy.leased_job_id.startswith("health-check:"),
            )):
                proxy.leased_job_id = None
        return dict(recovered)

    def work_remaining(self, batch_id: str) -> bool:
        with self.session() as session:
            return bool(
                session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(
                        Job.batch_id == batch_id, Job.state.in_([State.PENDING, State.RETRY_WAIT])
                    )
                )
            )

    def hold_domain(self, batch_id: str, domain: str, reason: str) -> int:
        count = 0
        with self.session.begin() as session:
            query = (
                select(Job)
                .join(User)
                .where(
                    Job.batch_id == batch_id,
                    User.email.like("%@" + domain.casefold()),
                    Job.state.in_([State.PENDING, State.RETRY_WAIT, State.PENDING_VERIFY]),
                )
            )
            for job in session.scalars(query):
                old = job.state
                job.state = State.NEEDS_REVIEW
                job.error_code = "EMAIL_DOMAIN_BLOCKED"
                job.message = redact(reason)[:256]
                job.finished_at = time.time()
                self._event(session, job, old, job.error_code, reason)
                count += 1
        self.control(batch_id, "PAUSED", reason)
        return count

    def claim_verification(self, job_id: str) -> Task:
        with self.session.begin() as session:
            job = session.get(Job, job_id)
            if not job or job.state not in {
                State.PENDING_VERIFY,
                State.UNKNOWN,
                State.NEEDS_REVIEW,
                State.SUCCEEDED,
            }:
                raise StorageError("仅能核验待验证、结果未知、人工处理或缺少 API Key 的任务。")
            if job.state == State.SUCCEEDED:
                account = session.scalar(
                    select(Account).where(
                        Account.user_id == job.user_id, Account.provider == job.provider
                    )
                )
                if account and account.api_key_ref:
                    raise StorageError("此账号已经交付 API Key，无需重复创建。")
            if not session.get(User, job.user_id).consent:
                raise StorageError("此用户的开户授权已撤销，不能继续访问账号。")
            old = job.state
            job.state = State.RUNNING
            job.started_at = time.time()
            job.finished_at = None
            self._event(session, job, old, "VERIFY_STARTED", "开始核查既有注册结果")
            return self._task(job, session.get(User, job.user_id))

    def summary(self, batch_id: str | None = None) -> dict:
        with self.session() as session:
            query = select(Job.state, func.count()).group_by(Job.state)
            if batch_id:
                self.batch(batch_id)
                query = query.where(Job.batch_id == batch_id)
            counts = dict(session.execute(query).all())
            return {"total": sum(counts.values()), "states": counts}

    def jobs(self, batch_id: str | None = None) -> list[dict]:
        with self.session() as session:
            query = select(Job, User).join(User).order_by(Job.created_at, Job.user_id)
            if batch_id:
                query = query.where(Job.batch_id == batch_id)
            return [
                {
                    "job_id": j.id,
                    "batch": j.batch_id,
                    "user_id": u.id,
                    "email": u.email,
                    "provider": j.provider,
                    "secret_ref": u.secret_ref,
                    "state": j.state,
                    "phase": j.phase,
                    "attempts": j.attempts,
                    "proxy_id": j.proxy_id or "",
                    "error_code": j.error_code,
                    "message": j.message,
                    "started_at": j.started_at,
                    "finished_at": j.finished_at,
                }
                for j, u in session.execute(query)
            ]

    def events(self, job_id: str) -> list[dict]:
        with self.session() as session:
            return [
                {
                    "at": e.at,
                    "from": e.from_state,
                    "to": e.to_state,
                    "code": e.code,
                    "message": e.message,
                }
                for e in session.scalars(
                    select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.id)
                )
            ]

    def batches(self) -> list[dict]:
        with self.session() as session:
            rows = list(session.scalars(select(Batch).order_by(Batch.created_at.desc(), Batch.id)))
            result = []
            for b in rows:
                counts = dict(
                    session.execute(
                        select(Job.state, func.count())
                        .where(Job.batch_id == b.id)
                        .group_by(Job.state)
                    ).all()
                )
                result.append(
                    {
                        "id": b.id,
                        "provider": b.provider,
                        "action": b.action,
                        "pause_reason": b.pause_reason,
                        "blocked_until": b.blocked_until,
                        "created_at": b.created_at,
                        "total": sum(counts.values()),
                        "states": counts,
                    }
                )
            return result

    def requeue_job(
        self, job_id: str, reason: str = "手动重置重排", *, login_only: bool = False
    ) -> dict:
        with self.session.begin() as session:
            job = session.get(Job, job_id)
            if not job:
                raise StorageError("找不到此任务。")
            if job.state == State.RUNNING:
                raise StorageError("任务正在执行中，请先暂停或停止批次。")
            old = job.state
            if login_only:
                job.state = State.PENDING_VERIFY
                job.phase = "REGISTRATION_SUBMITTED"
                job.submitted_at = job.submitted_at or time.time()
                job.error_code = "LOGIN_VERIFY_QUEUED"
                job.message = redact(reason or "排队等待账号登录核验与提取结果")[:256]
            else:
                job.state = State.PENDING
                job.phase = "PREPARE"
                job.submitted_at = None
                job.next_attempt_at = 0
                job.attempts = 0
                job.error_code = "MANUAL_REQUEUE"
                job.message = redact(reason or "手动重新排队等待注册")[:256]
                job.finished_at = None
            self._event(session, job, old, job.error_code, job.message)
            return {"job_id": job.id, "state": job.state, "phase": job.phase}

    def review_not_created(self, job_id: str, evidence: str) -> None:
        if not evidence.strip():
            raise StorageError("重新排队需要填写核查记录。")
        with self.session.begin() as session:
            job = session.get(Job, job_id)
            if not job or job.state not in {State.UNKNOWN, State.NEEDS_REVIEW}:
                raise StorageError("仅能重新排队结果待核查或人工处理的任务。")
            old = job.state
            job.state = State.PENDING
            job.phase = "PREPARE"
            job.submitted_at = None
            job.next_attempt_at = 0
            job.attempts = 0
            job.error_code = "REVIEW_CONFIRMED_NOT_CREATED"
            job.message = redact(evidence)[:256]
            self._event(session, job, old, job.error_code, job.message)

    def secret_reference(self, user_id: str) -> str:
        with self.session() as session:
            user = session.get(User, user_id)
            if not user:
                raise StorageError("找不到此用户。")
            return user.secret_ref

    def delete_user(self, user_id: str) -> None:
        with self.session.begin() as session:
            if session.scalar(
                select(Job.id).where(Job.user_id == user_id, Job.state == State.RUNNING)
            ):
                raise StorageError("此用户有执行中的任务，请先停止批次。")
            if not session.get(User, user_id):
                raise StorageError("找不到此用户。")
            session.execute(delete(User).where(User.id == user_id))

    def close(self) -> None:
        self.engine.dispose()
