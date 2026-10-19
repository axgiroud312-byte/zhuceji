from __future__ import annotations

import asyncio

from .domain import Checkpoint, Result, State, Task


class MockAdapter:
    def __init__(self, delay: float = 0.002):
        self.delay = delay
        self.active = 0
        self.peak = 0
        self.submissions: dict[str, int] = {}

    async def execute(self, task: Task, proxy: dict | None, checkpoint: Checkpoint) -> Result:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
            case = task.display_name
            if case == "network" and task.attempts == 1:
                return Result(State.RETRY_WAIT, "NETWORK", "模拟提交前网络中断")
            if case == "captcha":
                return Result(State.NEEDS_REVIEW, "SECURITY_CHECK", "模拟人工安全校验", pause=True)
            if case == "selector":
                return Result(State.NEEDS_REVIEW, "SELECTOR_CHANGED", "模拟页面变化", pause=True)
            if case == "rate" and task.attempts == 1:
                return Result(State.RETRY_WAIT, "RATE_LIMIT", "模拟限流", retry_after=0.01)
            await checkpoint("SUBMITTED")
            self.submissions[task.user_id] = self.submissions.get(task.user_id, 0) + 1
            await asyncio.sleep(self.delay)
            if case == "unknown":
                return Result(State.UNKNOWN, "RESULT_UNKNOWN", "模拟提交后连接中断")
            if case == "verify":
                return Result(State.PENDING_VERIFY, "VERIFY_REQUIRED", "模拟等待用户验证")
            return Result(
                State.SUCCEEDED,
                account_id="mock-" + task.user_id,
                evidence="模拟注册服务确认账号激活",
            )
        finally:
            self.active -= 1

    async def close(self) -> None:
        pass
