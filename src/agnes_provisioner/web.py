from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .agnes import AgnesAdapter
from .cli import export_rows, write_csv
from .config import (
    KeyFlow,
    LoginFlow,
    RegistrationFlow,
    Settings,
    VerificationFlow,
    load_settings,
    save_settings,
)
from .domain import STATE_LABELS, State
from .excel import write_excel
from .lock import RunLock
from .mailbox import MailboxError, OutlookMailbox
from .mock import MockAdapter
from .privacy import mask_email, redact
from .proxy import ProxyManager
from .scheduler import Scheduler
from .storage import Storage, StorageError
from .users import import_accounts_flexible
from .vault import Vault, VaultError
from .web_ui import WEB_HTML


class WebAppController:
    """Manages state, background runner, config, accounts, and proxy pool for the Web UI."""

    def __init__(self, config_path: Path | None = None):
        root = Path(__file__).resolve().parents[2]
        if config_path is None:
            local_cfg = root / "config.local.toml"
            example_cfg = root / "config.example.toml"
            config_path = local_cfg if local_cfg.exists() else example_cfg
        self.config_path = Path(config_path).resolve()
        self.root = self.config_path.parent
        self.lock = threading.RLock()
        self.runner_running = False
        self.active_batch = ""
        self.task_type = ""
        self.started_at: float | None = None
        self.last_error = ""
        self.last_report: dict = {}
        self.logs: list[str] = ["[系统] Web 控制台已就绪。"]

        # Ensure database is initialized
        settings = self.get_settings()
        storage = Storage(settings.database)
        try:
            storage.initialize()
        finally:
            storage.close()

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        with self.lock:
            self.logs.append(f"[{stamp}] {redact(message)}")
            if len(self.logs) > 150:
                self.logs = self.logs[-150:]

    def get_settings(self) -> Settings:
        if self.config_path.exists():
            return load_settings(self.config_path)
        return Settings()

    def overview(self, batch: str = "") -> dict:
        settings = self.get_settings()
        storage = Storage(settings.database)
        vault = Vault(settings.vault)
        try:
            proxies = ProxyManager(storage).list()
            batches = storage.batches()
            summary = storage.summary(batch or None)
            all_jobs = storage.jobs(batch or None)
            vault_snap = vault.snapshot()
            with_key = 0
            for j in all_jobs:
                rec = vault_snap.get(j["secret_ref"], {})
                if j["state"] == State.SUCCEEDED and (
                    rec.get("api_key") or (
                        j["provider"] == "mock" and j["error_code"] == "ACTIVATED_WITH_KEY"
                    )
                ):
                    with_key += 1
            summary["succeeded_with_key"] = with_key

            healthy_proxies = [
                p for p in proxies if p["status"] == "HEALTHY" and p.get("enabled", True)
            ]
            healthy_proxies.sort(key=lambda p: (p["generation"], p["failures"], p["id"]))
            available_proxies = [p for p in healthy_proxies if p.get("available", not p["leased"])]
            next_proxy = available_proxies[0] if available_proxies else None
            active_proxy = next((p for p in proxies if p["leased"] and not p.get("checking")), None)
            next_proxy_id = next_proxy["id"] if next_proxy else ""

            settings_dict = json.loads(settings.model_dump_json())
            return {
                "config_path": str(self.config_path),
                "settings": settings_dict,
                "batches": batches,
                "summary": summary,
                "proxies": proxies,
                "proxy_summary": {
                    "total": len(proxies),
                    "healthy": len(healthy_proxies),
                    "leased": sum(1 for p in proxies if p["leased"]),
                    "next_proxy_id": next_proxy_id,
                    "next_proxy": next_proxy,
                    "active_proxy": active_proxy,
                    "available": len(available_proxies),
                },
                "runner": {
                    "running": self.runner_running,
                    "active_batch": self.active_batch,
                    "task_type": self.task_type,
                    "started_at": self.started_at,
                    "last_error": self.last_error,
                    "last_report": self.last_report,
                    "logs": list(self.logs[-50:]),
                    "slots": [
                        {"job_id": j["job_id"], "user_id": j["user_id"], "phase": j["phase"]}
                        for j in all_jobs if j["state"] == State.RUNNING
                    ],
                    "events": [
                        dict(event, job_id=j["job_id"], user_id=j["user_id"])
                        for j in all_jobs[-20:] for event in storage.events(j["job_id"])[-5:]
                    ],
                },
            }
        finally:
            storage.close()

    def list_jobs(
        self, batch: str = "", state: str = "", reveal_secrets: bool = False,
        job_id: str = "", search: str = "",
    ) -> dict:
        settings = self.get_settings()
        storage = Storage(settings.database)
        vault = Vault(settings.vault)
        try:
            rows = storage.jobs(batch or None)
            snap = vault.snapshot()
            result = []
            for j in rows:
                if job_id and j["job_id"] != job_id:
                    continue
                if state and j["state"] != state:
                    continue
                if search and not any(search.casefold() in str(j[k]).casefold()
                                      for k in ("email", "user_id", "error_code", "message")):
                    continue
                rec = snap.get(j["secret_ref"], {})
                has_key = bool(rec.get("api_key") or (
                    j["provider"] == "mock" and j["error_code"] == "ACTIVATED_WITH_KEY"
                ))
                label = STATE_LABELS.get(State(j["state"]), j["state"])
                if j["state"] == State.SUCCEEDED and has_key:
                    label = "已完成 (含结果)"
                elif j["state"] == State.SUCCEEDED:
                    label = "已登录 (待拿结果)"
                result.append(
                    {
                        "job_id": j["job_id"],
                        "batch": j["batch"],
                        "user_id": j["user_id"],
                        "email": j["email"] if reveal_secrets else mask_email(j["email"]),
                        "raw_email": j["email"] if reveal_secrets else "",
                        "state": j["state"],
                        "state_label": label,
                        "phase": j["phase"],
                        "attempts": j["attempts"],
                        "proxy_id": j["proxy_id"],
                        "error_code": j["error_code"],
                        "message": j["message"],
                        "has_key": has_key,
                        "activated": bool(rec.get("activated")),
                        "agnes_password": rec.get("agnes_password", "") if reveal_secrets else "",
                        "mailbox_password": rec.get("mailbox_password", "")
                        if reveal_secrets
                        else "",
                        "api_key": rec.get("api_key", "") if reveal_secrets else "",
                        "has_password": bool(rec.get("agnes_password")),
                    }
                )
            return {"jobs": result}
        finally:
            storage.close()

    def job_events(self, job_id: str) -> dict:
        settings = self.get_settings()
        storage = Storage(settings.database)
        try:
            return {"events": storage.events(job_id)}
        finally:
            storage.close()

    def update_config(self, payload: dict) -> dict:
        if self.runner_running:
            raise StorageError("请等待执行结束后再保存配置，避免运行中切换数据库或流程。")
        current = self.get_settings()
        merged = current.model_dump()

        for k, v in payload.items():
            if k in {
                "approval", "key_flow", "registration_flow", "verification", "login_flow",
                "proxy_pool",
            } and not isinstance(v, dict):
                raise StorageError(f"{k} 配置必须是对象。")
            if k in (
                "approval",
                "key_flow",
                "registration_flow",
                "verification",
                "login_flow",
                "proxy_pool",
            ) and isinstance(v, dict):
                merged[k] = {**(merged.get(k) or {}), **v}
            elif v is not None:
                merged[k] = v

        # Auto-align approval & custom base_url so user edits in Web UI never trip approval limits
        if merged.get("manual_verification") or (
            merged.get("verification", {}).get("mode") == "manual"
        ):
            merged["headless"] = False

        base_url = str(merged.get("base_url") or "https://platform.agnes-ai.com").rstrip("/")
        merged["base_url"] = base_url
        if base_url != "https://platform.agnes-ai.com":
            merged["allow_custom_base_url"] = True

        approval = merged.setdefault("approval", {})
        if not str(approval.get("reference") or "").strip():
            approval["reference"] = "Web 控制台用户配置授权"
        approval["concurrency"] = max(
            int(approval.get("concurrency") or 1), int(merged.get("concurrency") or 1)
        )
        approval["per_minute"] = max(
            float(approval.get("per_minute") or 1), float(merged.get("per_minute") or 1)
        )
        if merged.get("proxy_required"):
            approval["proxies_allowed"] = True

        new_settings = Settings.model_validate(merged)
        save_settings(new_settings, self.config_path)
        self.log(f"已更新并保存流程与全局配置 -> {self.config_path.name}")
        return {"saved": True, "config_path": str(self.config_path)}

    def reset_flow_defaults(self) -> dict:
        if self.runner_running:
            raise StorageError("请等待执行结束后再恢复流程。")
        current = self.get_settings()
        current.base_url = "https://platform.agnes-ai.com"
        current.allow_custom_base_url = False
        current.identity_navigation_selector = 'text="个人资料"'
        current.authenticated_selector = 'img[alt="user"]'
        current.account_identity_selector = ""
        current.registration_flow = RegistrationFlow()
        current.verification = VerificationFlow()
        current.manual_verification = False
        current.login_flow = LoginFlow()
        current.key_flow = KeyFlow(
            enabled=True,
            require_key=True,
            navigation_selector='text="API 密钥"',
            create_selector='button:has-text("创建新的密钥") >> nth=0',
            name_selector="#keyName",
            confirm_selector=".ant-modal .ant-btn-primary",
            value_selector=".ant-modal, .ant-table-tbody",
            copy_selector='tr:has-text("Agnes Provisioner {user_id}") img[alt="复制"]',
            pattern=r"sk-[A-Za-z0-9_-]{16,}",
        )
        save_settings(current, self.config_path)
        self.log("已将注册流程、登录核验流程与结果提取流程恢复为 Agnes 官方默认配置。")
        return {"reset": True}

    def import_accounts(self, payload: dict) -> dict:
        if self.runner_running:
            raise StorageError("请等待执行结束后再导入或更新账号凭证。")
        if not isinstance(payload.get("content", ""), str):
            raise StorageError("账号导入内容必须是文本。")
        settings = self.get_settings()
        storage = Storage(settings.database)
        vault = Vault(settings.vault)
        try:
            storage.initialize()
            provider = "mock" if settings.mode == "mock" else "agnes-api"
            report = import_accounts_flexible(
                storage,
                vault,
                payload.get("content", ""),
                format_hint=payload.get("format_hint", "auto"),
                delimiter=payload.get("delimiter", "auto"),
                password_role=payload.get("password_role", "both"),
                mailbox_transport=payload.get("mailbox_transport", "graph"),
                consent_reference=payload.get("consent_reference") or "Web控制台批量导入授权",
                batch_id=payload.get("batch_id") or "batch-main",
                provider=provider,
                import_mode=payload.get("import_mode", "register"),
                update_existing=True,
            )
            batch_name = payload.get("batch_id") or "batch-main"
            self.log(
                f"批量导入账号完成：新增 {report['imported']}，更新 {report['updated']}，"
                f"重复 {report['duplicates']}，批次 {batch_name}。"
            )
            return {"report": report}
        finally:
            storage.close()

    def import_proxies(self, payload: dict) -> dict:
        if not isinstance(payload.get("content", ""), str):
            raise StorageError("代理导入内容必须是文本。")
        settings = self.get_settings()
        if not settings.approval.proxies_allowed:
            settings.approval.proxies_allowed = True
            save_settings(settings, self.config_path)
        storage = Storage(settings.database)
        try:
            storage.initialize()
            mgr = ProxyManager(storage)
            res = mgr.import_text(
                payload.get("content", ""),
                initial_status=payload.get("initial_status", "HEALTHY"),
                session_mode=bool(payload.get("session_mode", False)),
                clear_existing=bool(payload.get("clear_existing", False)),
            )
            self.log(f"代理池导入完成：成功导入 {res['imported']} 条代理节点。")
            return res
        finally:
            storage.close()

    def check_proxies(self, payload: dict) -> dict:
        settings = self.get_settings()
        storage = Storage(settings.database)
        try:
            mgr = ProxyManager(storage)
            target = payload.get("proxy_id") or "all"
            if target == "all":
                ids = [p["id"] for p in mgr.list()
                       if not p["leased"] and not p.get("binding_preserved")]
            else:
                ids = [target]

            async def _run_checks():
                semaphore = asyncio.Semaphore(8)

                async def check_one(pid):
                    async with semaphore:
                        return await mgr.check(
                            pid, settings.proxy_check_url,
                            session_suffix_template=settings.proxy_pool.session_suffix_template,
                            enable_session_stickiness=settings.proxy_pool.enable_session_stickiness,
                        )

                tasks = [check_one(pid) for pid in ids]
                return await asyncio.gather(*tasks, return_exceptions=True)

            raw_results = asyncio.run(_run_checks()) if ids else []
            results = []
            for pid, item in zip(ids, raw_results):
                if isinstance(item, Exception):
                    results.append({"proxy_id": pid, "status": "UNHEALTHY", "error": str(item)})
                else:
                    results.append(item)
            self.log(f"完成 {len(results)} 条代理健康与出口 IP 检测。")
            return {"results": results}
        finally:
            storage.close()

    def proxy_action(self, payload: dict) -> dict:
        settings = self.get_settings()
        storage = Storage(settings.database)
        try:
            mgr = ProxyManager(storage)
            action = payload.get("action")
            proxy_id = payload.get("proxy_id")
            if action == "rotate_now":
                res = mgr.rotate_now(proxy_id)
                self.log(f"手动触发换 IP：已切换 {res['rotated']} 个代理节点到下一轮会话。")
                return res
            if action == "reset_rotation":
                res = mgr.reset_rotation()
                self.log("已重置所有代理节点的轮换计数并将状态恢复为 HEALTHY。")
                return res
            if action == "toggle_enable":
                res = mgr.set_enabled(proxy_id, bool(payload.get("enabled", True)))
                self.log(f"代理 {proxy_id} 已{'启用' if res['enabled'] else '停用'}。")
                return res
            if action == "delete":
                res = mgr.delete_proxy(proxy_id)
                self.log(f"已删除代理节点 {proxy_id}。")
                return res
            if action == "clear_all":
                res = mgr.clear_all()
                self.log("已清空全部代理池节点。")
                return res
            raise StorageError(f"未知代理操作: {action}")
        finally:
            storage.close()

    def job_action(self, payload: dict) -> dict:
        settings = self.get_settings()
        storage = Storage(settings.database)
        vault = Vault(settings.vault)
        try:
            action = payload.get("action")
            job_id = payload.get("job_id")
            job_ids = payload.get("job_ids") or ([job_id] if job_id else [])

            if action == "requeue":
                if not job_ids:
                    raise StorageError("请至少选择一个账号。")
                if self.runner_running:
                    raise StorageError("请先停止执行器，结束后再重置任务。")
                if not payload.get("login_only") and not payload.get("confirmed_not_created"):
                    raise StorageError("重新注册前请确认这些账号尚未创建，避免重复提交。")
                targets = {j["job_id"]: j for j in storage.jobs()}
                if any(jid not in targets for jid in job_ids):
                    raise StorageError("所选任务已不存在，请刷新后重试。")
                if not payload.get("login_only") and any(
                    targets[jid]["state"] == State.SUCCEEDED for jid in job_ids
                ):
                    raise StorageError("已确认的账号不能重新注册，请使用验证登录与提取结果。")
                login_only = bool(payload.get("login_only", False))
                for jid in job_ids:
                    storage.requeue_job(
                        jid,
                        "Web控制台设为登录验证" if login_only else "Web控制台手动重排",
                        login_only=login_only,
                    )
                mode_str = "待登录验证(已有账号)" if login_only else "待重新注册"
                self.log(f"已将 {len(job_ids)} 个任务状态重置为【{mode_str}】。")
                return {"message": f"已将 {len(job_ids)} 个任务设为{mode_str}"}

            if action == "check_mailbox":
                if len(job_ids) > 1:
                    jobs = {j["job_id"]: j for j in storage.jobs()}
                    if any(jid not in jobs for jid in job_ids):
                        raise StorageError("所选账号中有不存在的任务。")
                    self._start_background_task(
                        jobs[job_ids[0]]["batch"], "mailbox_check", job_ids=job_ids
                    )
                    return {"message": f"已在后台测试 {len(job_ids)} 个邮箱连接。"}
                target_job = next((j for j in storage.jobs() if j["job_id"] == job_id), None)
                if not target_job:
                    raise StorageError("找不到该任务。")
                v = settings.verification
                mb = OutlookMailbox(
                    vault,
                    target_job["secret_ref"],
                    sender_domain=v.sender_domain,
                    code_pattern=v.code_pattern,
                    imap_host=v.imap_host,
                    imap_port=v.imap_port,
                )
                baseline = mb.baseline()
                transport = baseline.get("transport", "imap")
                self.log(f"邮箱连接测试通过：{target_job['email']} ({transport})")
                return {"message": f"✅ 邮箱连接正常 ({transport})，可正常接收验证码！"}

            if action == "verify":
                if self.runner_running:
                    raise StorageError("当前已有批次正在后台运行，请等待或先暂停。")
                target_job = next((j for j in storage.jobs() if j["job_id"] == job_id), None)
                if not target_job:
                    raise StorageError("找不到该任务。")
                self._start_background_task(
                    target_job["batch"], "verify_single", job_ids=[job_id]
                )
                msg = f"🔐 已在后台启动账号 {target_job['email']} 的登录验证与提取结果！"
                return {"message": msg}

            if action == "set_password":
                if self.runner_running:
                    raise StorageError("请等待执行结束后再修改密码。")
                target_job = next((j for j in storage.jobs() if j["job_id"] == job_id), None)
                if not target_job:
                    raise StorageError("找不到该任务。")
                rec = vault.get(target_job["secret_ref"])
                ag_pwd = payload.get("agnes_password") or ""
                mb_pwd = payload.get("mailbox_password") or ""
                if not isinstance(ag_pwd, str) or not isinstance(mb_pwd, str):
                    raise StorageError("密码必须为文本。")
                if not ag_pwd and not mb_pwd:
                    raise StorageError("请至少输入一个新密码；留空表示保持原值。")
                if ag_pwd:
                    rec["agnes_password"] = ag_pwd
                if mb_pwd:
                    rec["mailbox_password"] = mb_pwd
                vault.set(target_job["secret_ref"], rec)
                self.log(f"已更新账号 {target_job['email']} 的本地加密凭证密码。")
                return {"message": "✅ 密码已加密保存至本地凭证库！"}

            if action == "delete":
                deleted = 0
                all_jobs = {j["job_id"]: j for j in storage.jobs()}
                for jid in job_ids:
                    j = all_jobs.get(jid)
                    if not j:
                        continue
                    storage.delete_user(j["user_id"])
                    vault.delete(j["secret_ref"])
                    deleted += 1
                self.log(f"已删除 {deleted} 个账号及其本地凭证。")
                return {"message": f"🗑 已删除 {deleted} 个账号记录"}

            raise StorageError(f"未知的任务操作: {action}")
        finally:
            storage.close()

    def control_batch(self, payload: dict) -> dict:
        action = payload.get("action")
        if not isinstance(payload.get("batch_id", ""), str):
            raise StorageError("批次名称必须是文本。")
        batch_id = (payload.get("batch_id") or "").strip()
        if not batch_id:
            raise StorageError("请先选择或填写批次名称。")
        limit = payload.get("limit")
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            raise StorageError("执行数量必须是大于 0 的整数；留空表示全部。")
        settings = self.get_settings()
        storage = Storage(settings.database)
        try:
            batch = storage.batch(batch_id)
            if action in ("pause", "resume", "stop"):
                mapped = {"pause": "PAUSED", "resume": "RUNNING", "stop": "STOPPING"}[action]
                storage.control(batch_id, mapped)
                self.log(f"批次 {batch_id} 状态已切换为 {mapped}。")
                return {"message": f"批次 {batch_id} 已设为 {mapped}"}
            if action == "recover":
                if self.runner_running:
                    raise StorageError("请等待执行器停止后再恢复中断任务。")
                with RunLock(settings.database):
                    rep = storage.recover(batch_id)
                self.log(f"批次 {batch_id} 中断恢复完成：{rep}")
                return {"message": f"已恢复中断任务：{rep}"}
            if action == "run":
                if self.runner_running:
                    raise StorageError("已有任务正在运行中，请勿重复启动。")
                batch = storage.batch(batch_id)
                if batch.action == "PAUSED":
                    storage.control(batch_id, "RUNNING", "")
                limit = payload.get("limit")
                self._start_background_task(batch_id, "run", limit=limit)
                return {"message": f"🚀 批次 {batch_id} 已开始在后台执行！"}
            if action == "verify_batch":
                if self.runner_running:
                    raise StorageError("已有任务正在运行中，请勿重复启动。")
                job_ids = payload.get("job_ids")
                if job_ids is not None:
                    available = {j["job_id"] for j in storage.jobs(batch_id)}
                    if not job_ids or any(jid not in available for jid in job_ids):
                        raise StorageError("请选择同一批次中的有效账号进行核验。")
                limit = payload.get("limit")
                self._start_background_task(
                    batch_id, "verify_batch", limit=limit, job_ids=job_ids
                )
                return {"message": f"🔐 批次 {batch_id} 批量账号登录核验已启动！"}
            raise StorageError(f"未知的批次指令: {action}")
        finally:
            storage.close()

    def _start_background_task(
        self,
        batch_id: str,
        task_type: str,
        *,
        limit: int | None = None,
        job_ids: list[str] | None = None,
    ) -> None:
        with self.lock:
            if self.runner_running:
                raise StorageError("后台执行器正在运行中。")
            self.runner_running = True
            self.active_batch = batch_id
            self.task_type = task_type
            self.started_at = time.time()
            self.last_error = ""

        def _worker():
            storage = None
            try:
                settings = self.get_settings()
                storage = Storage(settings.database)
                vault = Vault(settings.vault)
                if task_type == "mailbox_check":
                    results = []
                    jobs = {j["job_id"]: j for j in storage.jobs()}
                    for jid in job_ids or []:
                        try:
                            v = settings.verification
                            mb = OutlookMailbox(
                                vault, jobs[jid]["secret_ref"], sender_domain=v.sender_domain,
                                code_pattern=v.code_pattern, imap_host=v.imap_host,
                                imap_port=v.imap_port,
                            )
                            mb.baseline()
                            results.append({"job_id": jid, "ok": True})
                            self.log(f"邮箱连接通过：{jobs[jid]['user_id']}")
                        except (MailboxError, VaultError, OSError) as err:
                            results.append({"job_id": jid, "ok": False, "error": redact(str(err))})
                            self.log(f"邮箱连接失败：{jobs[jid]['user_id']} · {err}")
                    self.last_report = {"mailboxes": results}
                    return
                proxies = ProxyManager(storage).list()
                if proxies and not settings.approval.proxies_allowed:
                    settings.approval.proxies_allowed = True
                adapter = (
                    MockAdapter()
                    if settings.mode == "mock"
                    else AgnesAdapter(settings, vault)
                )
                scheduler = Scheduler(storage, settings, adapter)
                rot = settings.proxy_pool
                self.log(
                    f"开始执行 [{task_type}] 批次={batch_id} 模式={settings.mode} "
                    f"并发={settings.concurrency} 换IP={rot.rotate_mode}(每{rot.rotate_every}次)"
                )
                if task_type == "run":
                    rep = asyncio.run(scheduler.run(batch_id, limit))
                elif task_type == "verify_single" and job_ids:
                    rep = asyncio.run(scheduler.verify_batch(batch_id, job_ids=job_ids, limit=1))
                else:
                    rep = asyncio.run(
                        scheduler.verify_batch(batch_id, job_ids=job_ids, limit=limit)
                    )
                self.last_report = rep
                self.log(f"执行完成 [{task_type}] 批次={batch_id} 统计={rep.get('states', rep)}")
            except Exception as err:
                self.last_error = redact(str(err))
                self.log(f"❌ 执行异常：{err}")
            finally:
                if storage is not None:
                    storage.close()
                with self.lock:
                    self.runner_running = False
                    self.active_batch = ""
                    self.task_type = ""

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def backup(self) -> dict:
        if self.runner_running:
            raise StorageError("请等待任务停止后再备份，确保数据库与凭证一致。")
        settings = self.get_settings()
        with RunLock(settings.database):
            folder = self.root / "outputs" / "backups" / time.strftime("%Y%m%d-%H%M%S")
            folder.mkdir(parents=True, exist_ok=False)
            with sqlite3.connect(settings.database) as source:
                with sqlite3.connect(folder / "agnes.db") as target:
                    source.backup(target)
            with Vault(settings.vault).lock:
                if settings.vault.exists():
                    shutil.copy2(settings.vault, folder / "credentials.dpapi")
            self.log("已保存数据库与加密凭证的一致性备份。")
            return {
                "directory": str(folder),
                "message": "备份成功；凭证仅可由当前 Windows 用户解密。",
            }

    def export_file(
        self, fmt: str = "xlsx", batch: str = "", include_secrets: bool = False
    ) -> Path:
        settings = self.get_settings()
        storage = Storage(settings.database)
        vault = Vault(settings.vault)
        try:
            rows = export_rows(storage, vault, batch or None, include_secrets)
            if not rows:
                raise StorageError("当前还没有可导出的任务记录，请先导入账号并创建批次。")
            out_dir = self.root / "outputs"
            out_dir.mkdir(parents=True, exist_ok=True)
            suffix = ".csv" if fmt.lower() == "csv" else ".xlsx"
            safe_batch = hashlib.sha256(batch.encode()).hexdigest()[:10] if batch else "全部"
            filename = f"Agnes开户结果_{safe_batch}{suffix}"
            target_path = out_dir / filename
            if suffix == ".csv":
                write_csv(target_path, rows)
            else:
                write_excel(target_path, rows)
            self.log(f"已导出结果文件：{target_path}")
            return target_path
        finally:
            storage.close()


def make_handler(controller: WebAppController):
    class RequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _send_json(self, data: dict, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 10 * 1024 * 1024:
                raise ValueError("请求过大，请将导入文件拆分为 10MB 以下。")
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("请求内容必须为 JSON 对象。")
            return payload

        def _valid_host(self) -> bool:
            bound_host = self.server.server_address[0]
            if bound_host not in {"127.0.0.1", "::1", "localhost"}:
                return True
            try:
                host = urlsplit("http://" + self.headers.get("Host", "")).hostname
            except ValueError:
                host = ""
            if host not in {"127.0.0.1", "::1", "localhost"}:
                self._send_json({"error": "本地工作台拒绝非本机 Host。"}, status=403)
                return False
            return True

        def do_GET(self):
            if not self._valid_host():
                return
            parsed = urlsplit(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            try:
                if path in ("/", "/index.html"):
                    body = WEB_HTML.encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if path == "/api/overview":
                    self._send_json(controller.overview((query.get("batch") or [""])[0]))
                    return
                if path == "/api/jobs":
                    batch = (query.get("batch") or [""])[0]
                    state = (query.get("state") or [""])[0]
                    reveal = (query.get("reveal_secrets") or ["0"])[0] == "1"
                    job_id = (query.get("job_id") or [""])[0]
                    search = (query.get("search") or [""])[0]
                    self._send_json(controller.list_jobs(batch, state, reveal, job_id, search))
                    return
                if path.startswith("/api/jobs/") and path.endswith("/events"):
                    job_id = path.split("/")[3]
                    self._send_json(controller.job_events(job_id))
                    return
                if path == "/api/export":
                    fmt = (query.get("format") or ["xlsx"])[0]
                    batch = (query.get("batch") or [""])[0]
                    secrets = (query.get("include_secrets") or ["0"])[0] == "1"
                    file_path = controller.export_file(fmt, batch, secrets)
                    content = file_path.read_bytes()
                    ctype = (
                        "text/csv; charset=utf-8"
                        if file_path.suffix.lower() == ".csv"
                        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("Cache-Control", "no-store")
                    fname = urlsplit(file_path.as_uri()).path.rsplit("/", 1)[-1]
                    self.send_header(
                        "Content-Disposition",
                        f"attachment; filename*=UTF-8''{fname}",
                    )
                    self.end_headers()
                    self.wfile.write(content)
                    return
                self._send_json({"error": "Not Found"}, status=404)
            except (StorageError, VaultError, MailboxError, ValueError, OSError) as err:
                self._send_json({"error": str(err)}, status=400)

        def do_POST(self):
            with controller.lock:
                self._dispatch_post()

        def _dispatch_post(self):
            if not self._valid_host():
                return
            parsed = urlsplit(self.path)
            path = parsed.path
            try:
                origin = self.headers.get("Origin")
                if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                    self._send_json({"error": "已拒绝来自其他网站的操作。"}, status=403)
                    return
                if "application/json" not in self.headers.get("Content-Type", ""):
                    self._send_json({"error": "请使用 JSON 格式提交操作。"}, status=415)
                    return
                payload = self._read_json()
                if path == "/api/backup":
                    self._send_json(controller.backup())
                    return
                if path == "/api/config":
                    self._send_json(controller.update_config(payload))
                    return
                if path == "/api/config/reset-defaults":
                    self._send_json(controller.reset_flow_defaults())
                    return
                if path == "/api/accounts/import":
                    self._send_json(controller.import_accounts(payload))
                    return
                if path == "/api/proxies/import":
                    self._send_json(controller.import_proxies(payload))
                    return
                if path == "/api/proxies/check":
                    self._send_json(controller.check_proxies(payload))
                    return
                if path == "/api/proxies/action":
                    self._send_json(controller.proxy_action(payload))
                    return
                if path == "/api/jobs/action":
                    self._send_json(controller.job_action(payload))
                    return
                if path == "/api/batches/control":
                    self._send_json(controller.control_batch(payload))
                    return
                self._send_json({"error": "Not Found"}, status=404)
            except (StorageError, VaultError, MailboxError, ValueError, OSError) as err:
                self._send_json({"error": str(err)}, status=400)

    return RequestHandler


def serve_web(
    config_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    controller = WebAppController(config_path)
    server = ThreadingHTTPServer((host, port), make_handler(controller))
    url = f"http://{host}:{port}"
    print(f"Agnes Web 控制台已启动：{url}", flush=True)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWeb 控制台已关闭。")
    finally:
        server.server_close()
