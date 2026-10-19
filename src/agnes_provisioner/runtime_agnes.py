"""Agnes is one importable site script; resource ownership stays in the runtime."""

from __future__ import annotations

import asyncio
import time

from .agnes import AgnesAdapter
from .domain import State, Task
from .runtime_resources import ResourceError
from .vault import Vault

AGNES_PACKAGE = {
    "manifest": {
        "api_version": 1,
        "id": "agnes",
        "site_id": "agnes",
        "name": "Agnes 注册与 API Key",
        "version": "1.0.0",
        "entrypoint": "run",
        "resources": {"mailbox": True, "proxy": True},
        "parameters": {},
        "result_fields": [
            {"key": "email", "label": "邮箱", "type": "string", "required": True,
             "sensitive": False},
            {"key": "password", "label": "密码", "type": "string", "required": True,
             "sensitive": True},
            {"key": "api_key", "label": "API Key", "type": "string", "required": True,
             "sensitive": True},
        ],
        "dependencies": ["agnes_provisioner"],
    },
    "source": (
        "from agnes_provisioner.runtime_agnes import run_agnes\n\n"
        "async def run(ctx):\n"
        "    return await run_agnes(ctx)\n"
    ),
}


def _failure(code, message):
    # Lazy import keeps the builtin package available during script registry initialization.
    from .script_contract import ScriptFailure

    return ScriptFailure(code, message)


async def run_agnes(ctx) -> dict:
    """Exactly one adapter execute; the adapter's reconciliation only logs in.

    EMAIL_REQUESTED sends a verification message, not a registration. Only the
    registration/key checkpoint crosses the runtime's irreversible boundary.
    No RETRY_WAIT/PENDING result is rescheduled by this wrapper.
    """
    mailbox = ctx.mailbox
    if mailbox is None:
        raise _failure("MAILBOX_REQUIRED", "Agnes 脚本需要框架分配的邮箱。")
    if ctx.proxy is None:
        raise _failure("PROXY_REQUIRED", "Agnes 脚本需要绑定代理；不能降级直连。")
    vault = Vault(ctx.settings.vault)
    record = vault.get(mailbox.secret_ref)
    if record.get("email", "").casefold() != mailbox.email.casefold():
        raise _failure("CREDENTIALS_MISSING", "邮箱与本地凭证引用不匹配。")
    # These markers are task-local Vault data, never a second resource pool.
    if record.get("runtime_agnes_submitted") or record.get("activated") or record.get("api_key"):
        ctx.mark_submitted()
        raise _failure("AGNES_ALREADY_SUBMITTED", "已有 Agnes 提交记录；禁止重新注册，请核查结果。")
    if record.get("runtime_agnes_started"):
        raise _failure("AGNES_TASK_REPLAY", "此 Agnes 任务已执行过，不能重复注册。")
    if ctx.cancelled:
        raise _failure("CANCELLED", "任务已停止，未提交注册。")
    record["runtime_agnes_started"] = True
    vault.set(mailbox.secret_ref, record)
    password = vault.ensure_account_password(mailbox.secret_ref)
    for value in (password, record.get("mailbox_password"), record.get("refresh_token"),
                  record.get("client_id"), ctx.proxy.get("username"), ctx.proxy.get("password")):
        if value:
            ctx.register_secret(value)
    task = Task(
        id=ctx.task_id, batch_id=ctx.batch_id, user_id=ctx.task_id,
        email=mailbox.email, display_name="", secret_ref=mailbox.secret_ref,
        mailbox_authorized=bool(record.get("mailbox_authorized")), attempts=1,
        phase="PREPARE", submitted_at=None, proxy_id=None,
    )
    submitted = False

    async def checkpoint(phase):
        nonlocal submitted
        if phase in {"REGISTRATION_SUBMITTED", "KEY_REQUESTED"}:
            try:
                await ctx.lease.validate_proxy()
            except ResourceError as error:
                raise _failure(error.code, str(error)) from None
            # Durable framework marker BEFORE any mutating browser click.
            if not submitted:
                ctx.mark_submitted()
                submitted = True
                saved = vault.get(mailbox.secret_ref)
                saved["runtime_agnes_submitted"] = time.time()
                vault.set(mailbox.secret_ref, saved)
        ctx.log("Agnes 执行阶段", stage=phase)

    adapter = AgnesAdapter(ctx.settings, vault)
    try:
        ctx.log("开始 Agnes 注册", stage="PREPARE")
        result = await adapter.execute(task, ctx.proxy, checkpoint)
        saved = vault.get(mailbox.secret_ref)
        for value in (saved.get("agnes_password"), saved.get("api_key"),
                      saved.get("refresh_token")):
            if value:
                ctx.register_secret(value)
        if (result.state != State.SUCCEEDED or result.code != "ACTIVATED_WITH_KEY"
                or not saved.get("activated") or not saved.get("api_key")):
            # The runtime makes submitted failures UNKNOWN, pre-submit failures FAILED.
            # KEY_PENDING is not success when the manifest promises an API key.
            raise _failure(result.code or "AGNES_RESULT_UNCONFIRMED",
                           result.message or "Agnes 注册结果未确认。")
        if not submitted:
            # Defensive handling for an adapter that observes an existing activated account.
            ctx.mark_submitted()
        return {"email": mailbox.email, "password": saved["agnes_password"],
                "api_key": saved["api_key"]}
    finally:
        # Browser cleanup also runs on cancellation/timeout; it must not trigger a retry.
        cleanup = asyncio.create_task(adapter.close())
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            await cleanup
            raise
