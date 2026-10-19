from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable, Protocol


class State(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PENDING_VERIFY = "PENDING_VERIFY"
    SUCCEEDED = "SUCCEEDED"
    RETRY_WAIT = "RETRY_WAIT"
    UNKNOWN = "UNKNOWN"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


STATE_LABELS = {
    State.PENDING: "等待执行",
    State.RUNNING: "正在执行",
    State.PENDING_VERIFY: "等待验证",
    State.SUCCEEDED: "账号已确认",
    State.RETRY_WAIT: "等待重试",
    State.UNKNOWN: "结果待核查",
    State.NEEDS_REVIEW: "需要人工处理",
    State.FAILED: "失败",
    State.CANCELLED: "已取消",
    State.SKIPPED: "已跳过",
}

TRANSITIONS = {
    State.PENDING: {State.RUNNING, State.NEEDS_REVIEW, State.CANCELLED},
    State.RETRY_WAIT: {State.RUNNING, State.NEEDS_REVIEW, State.FAILED, State.CANCELLED},
    State.RUNNING: set(State) - {State.RUNNING},
    State.PENDING_VERIFY: {State.RUNNING, State.SUCCEEDED, State.NEEDS_REVIEW, State.CANCELLED},
    State.UNKNOWN: {
        State.RUNNING,
        State.SUCCEEDED,
        State.PENDING_VERIFY,
        State.NEEDS_REVIEW,
        State.PENDING,
    },
    State.NEEDS_REVIEW: {
        State.RUNNING,
        State.SUCCEEDED,
        State.PENDING_VERIFY,
        State.PENDING,
        State.CANCELLED,
    },
    State.SUCCEEDED: {State.RUNNING},
    State.FAILED: set(),
    State.CANCELLED: set(),
    State.SKIPPED: set(),
}


@dataclass(frozen=True)
class Task:
    id: str
    batch_id: str
    user_id: str
    email: str
    display_name: str
    secret_ref: str
    mailbox_authorized: bool
    attempts: int
    phase: str
    submitted_at: float | None
    proxy_id: str | None


@dataclass(frozen=True)
class Result:
    state: State
    code: str = ""
    message: str = ""
    account_id: str = ""
    evidence: str = ""
    retry_after: float = 0
    pause: bool = False
    proxy_failed: bool = False
    retry_known: bool = False


Checkpoint = Callable[[str], Awaitable[None]]


class Adapter(Protocol):
    async def execute(self, task: Task, proxy: dict | None, checkpoint: Checkpoint) -> Result: ...

    async def close(self) -> None: ...


class StoppedBeforeSubmit(Exception):
    pass
