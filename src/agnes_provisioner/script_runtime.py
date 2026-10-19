"""Fixed-cardinality execution with an OS-backed, cross-process run lock."""

from __future__ import annotations

import asyncio
import json
import threading
from uuid import uuid4

from .lock import RunLock
from .privacy import redact
from .runtime_migration import migrate_legacy
from .runtime_store import RuntimeStore
from .script_contract import ScriptFailure
from .storage import StorageError
from .vault import Vault


class ScriptContext:
    def __init__(self, runtime, batch, task_id, index, parameters, lease):
        self.runtime = runtime
        self.task_id, self.batch_id, self.index = task_id, batch["id"], index
        self.parameters = parameters
        self.settings = runtime.settings.model_copy(deep=True)
        self.mailbox, self.proxy = lease.mailbox, lease.proxy
        self.lease = lease
        self.submitted = False
        self.secrets: set[str] = set()
        self._collect_secrets(parameters)
        if self.mailbox and getattr(self.mailbox, "secret_ref", None):
            self._collect_secrets(runtime.vault.get(self.mailbox.secret_ref))
        self._collect_secrets(self.proxy or {})

    def _collect_secrets(self, value):
        if isinstance(value, dict):
            for item in value.values():
                self._collect_secrets(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self._collect_secrets(item)
        elif isinstance(value, str):
            self.register_secret(value)

    @property
    def cancelled(self):
        return bool(self.runtime.store.batch(self.batch_id)["stop"])

    def register_secret(self, value):
        if isinstance(value, str) and value:
            self.secrets.add(value)

    def clean(self, value):
        text = str(value)
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, "[已隐藏]")
        return redact(text)

    def log(self, message, stage="run", level="info", details=""):
        self.runtime.store.event(self.batch_id, self.task_id, self.clean(stage),
                                 level if level in {"info", "warning", "error"} else "info",
                                 self.clean(message), self.clean(details))

    def mark_submitted(self):
        if not self.submitted:
            if self.cancelled:
                raise ScriptFailure("STOPPED", "已停止，未提交注册。")
            # Resource marker first: a crash between writes must never free a submitted mailbox.
            self.runtime.resources.mark_submitted(self.lease)
            self.submitted = True
            self.runtime.store.submitted(self.task_id)
            self.log("注册请求即将提交；此任务不会自动重试。", "submitted")


class ScriptRuntime:
    def __init__(self, settings, resources=None):
        from .runtime_resources import ResourceManager

        self.settings = settings
        self.vault = Vault(settings.vault)
        self.store = RuntimeStore(settings.database, self.vault)
        self.resources = resources or ResourceManager(settings)
        self.mutex = threading.RLock()
        self.worker: threading.Thread | None = None
        # A second controller may open while another process runs: don't recover its jobs.
        try:
            with RunLock(settings.database):
                self.store.recover()
                self.resources.recover()
                migrate_legacy(self.store)
        except StorageError:
            pass
        self._install_builtin()

    def _install_builtin(self):
        from .runtime_agnes import AGNES_PACKAGE

        package = AGNES_PACKAGE
        try:
            self.store.script(package["manifest"]["id"], package["manifest"]["version"])
        except ValueError:
            try:
                self.store.import_package(package)
            except ValueError:
                # Another server can initialize the exact same immutable package concurrently.
                self.store.script(package["manifest"]["id"], package["manifest"]["version"])

    def overview(self):
        batches = self.store.batches()
        active = next((b for b in batches if b["state"] in {"RUNNING", "STOPPING"}), None)
        return {"scripts": self.store.scripts(), "resources": self.resources.list(),
                "batches": batches, "active": active}

    def save_resource(self, payload):
        with RunLock(self.settings.database):
            return {"resource": self.resources.save(payload)}

    def check_resource(self, resource_id):
        with RunLock(self.settings.database):
            return {"resource": self.resources.check(resource_id)}

    def start(self, payload):
        request_id = payload.get("request_id")
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 120:
            raise ValueError("启动需要唯一 request_id（8～120 字符）。")
        with self.mutex:
            previous = self.store.request_batch(request_id)
            if previous:
                return {"batch": previous}
            count, concurrency = payload.get("count"), payload.get("concurrency", 1)
            if type(count) is not int or not 1 <= count <= 10000:
                raise ValueError("任务数量必须是 1～10000 的整数。")
            if type(concurrency) is not int or not 1 <= concurrency <= 50:
                raise ValueError("并发必须是 1～50 的整数，默认 1。")
            manifest, source = self.store.script(payload.get("script_id"), payload.get("version"))
            parameters = payload.get("parameters", {})
            if not isinstance(parameters, dict):
                raise ValueError("脚本参数必须是 JSON 对象。")
            parameters = {**manifest["parameters"], **parameters}
            json.dumps(parameters, allow_nan=False)
            bindings = payload.get("bindings", {})
            if not isinstance(bindings, dict):
                raise ValueError("资源绑定必须是对象。")
            run_lock = RunLock(self.settings.database)
            run_lock.__enter__()
            try:
                previous = self.store.request_batch(request_id)
                if previous:
                    run_lock.__exit__()
                    return {"batch": previous}
                self.store.recover()
                self.resources.recover()
                migrate_legacy(self.store)
                snapshot = self.resources.snapshot(bindings, manifest["resources"], count,
                                                   manifest["site_id"])
                batch_id = "run-" + uuid4().hex[:16]
                self.store.create_batch(batch_id, request_id, manifest, count, snapshot, parameters)
                self.worker = threading.Thread(
                    target=self._thread, args=(batch_id, manifest, source, snapshot,
                                               parameters, concurrency, run_lock), daemon=True,
                )
                self.worker.start()
                return {"batch": self.store.public_batch(self.store.batch(batch_id))}
            except BaseException:
                run_lock.__exit__()
                raise

    def _thread(self, batch_id, manifest, source, snapshot, parameters, concurrency, run_lock):
        try:
            asyncio.run(self._run(batch_id, manifest, source, snapshot, parameters, concurrency))
        except BaseException as error:
            self.store.event(batch_id, "", "interrupted", "error",
                             f"运行中断（{type(error).__name__}），任务不会自动重放。")
            self.store.recover()
            self.resources.recover()
        finally:
            run_lock.__exit__()

    async def _run(self, batch_id, manifest, source, snapshot, parameters, concurrency):
        batch = self.store.batch(batch_id)
        queue = asyncio.Queue()
        for index in range(1, batch["count"] + 1):
            queue.put_nowait(index)

        async def worker():
            while not queue.empty():
                index = queue.get_nowait()
                task_id = f"{batch_id}-{index:04d}"
                if self.store.batch(batch_id)["stop"]:
                    self.store.task_state(task_id, "CANCELLED", "停止后未启动此任务。")
                    continue
                await self._task(batch, task_id, index, manifest, source, snapshot, parameters)

        await asyncio.gather(*(worker() for _ in range(min(concurrency, batch["count"]))))
        self.store.finish(batch_id)
        self.store.event(batch_id, "", "complete", "info", "批次已结束；未创建补跑任务。")

    async def _task(self, batch, task_id, index, manifest, source, snapshot, parameters):
        self.store.task_state(task_id, "RUNNING")
        lease, ctx = None, None
        namespace = {"__name__": "site_script_" + task_id.replace("-", "_"),
                     "ScriptFailure": ScriptFailure}
        state, message = "FAILED", ""
        try:
            lease = await self.resources.acquire(snapshot, manifest["site_id"], task_id)
            if callable(getattr(lease, "validate_proxy", None)):
                await lease.validate_proxy()
            # Isolate mutable arguments and globals between tasks.
            ctx = ScriptContext(self, batch, task_id, index,
                                json.loads(json.dumps(parameters)), lease)
            ctx.log("开始执行脚本。", "prepare")
            exec(compile(source, f"<{manifest['id']}@{manifest['version']}>", "exec"), namespace)
            values = await asyncio.wait_for(namespace[manifest["entrypoint"]](ctx), timeout=600)
            if isinstance(values, dict):
                for field in manifest["result_fields"]:
                    if field["sensitive"]:
                        ctx.register_secret(values.get(field["key"]))
            self.store.save_results(task_id, manifest["result_fields"], values)
            state, message = "SUCCEEDED", "执行完成，结果已保存。"
        except asyncio.CancelledError:
            state = "UNKNOWN" if ctx and ctx.submitted else "CANCELLED"
            message = "执行被中断；已提交结果待核查，不会自动重新执行。" if state == "UNKNOWN" \
                else "执行被取消，未提交注册。"
            raise
        except ScriptFailure as error:
            state = "UNKNOWN" if ctx and ctx.submitted else "FAILED"
            message = ctx.clean(str(error)) if ctx else "资源或脚本准备失败。"
        except asyncio.TimeoutError:
            state = "UNKNOWN" if ctx and ctx.submitted else "FAILED"
            message = "脚本超过 600 秒时限；未自动重试。"
        except Exception as error:
            state = "UNKNOWN" if ctx and ctx.submitted else "FAILED"
            message = (f"脚本或资源执行失败（{type(error).__name__}）；"
                       "请检查资源连接及脚本，未自动重试。")
            if isinstance(error, (StorageError, ValueError)) and ctx is None:
                message = redact(str(error))
        finally:
            if ctx:
                try:
                    if callable(namespace.get("close")):
                        await asyncio.wait_for(namespace["close"](ctx), timeout=15)
                except (Exception, asyncio.CancelledError):
                    ctx.log("脚本清理异常，框架将释放资源。", "cleanup", "warning")
            if lease:
                try:
                    await self.resources.release(lease, submitted=bool(ctx and ctx.submitted),
                                                 succeeded=state == "SUCCEEDED")
                except (Exception, asyncio.CancelledError):
                    # Keep task outcome, preserve durable submission markers and recover leases.
                    self.store.event(batch["id"], task_id, "cleanup", "warning",
                                     "资源释放异常，将在下次启动前恢复租约。")
            self.store.task_state(task_id, state, message)
            self.store.event(batch["id"], task_id, "complete", "info" if state == "SUCCEEDED"
                             else "error", message)

    def stop(self, batch_id):
        self.store.stop(batch_id)
        return {"ok": True}
