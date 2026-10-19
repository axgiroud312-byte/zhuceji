"""The production CLI. All write commands except control/heartbeat hold the run lock."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from .bulk_excel import write_bulk_excel
from .bulk_prepare import prepare
from .bulk_store import BulkStore
from .config import load_settings
from .lock import RunLock
from .storage import StorageError
from .vault import Vault

ROOT = Path(__file__).resolve().parents[2]


def add_parser(commands):
    root = commands.add_parser("bulk", help="生产入口：隔离导入、状态、节流执行与动态导出")
    sub = root.add_subparsers(dest="bulk_command", required=True)
    prep = sub.add_parser("prepare", help="离线复制样本并按邮箱去重导入，保留暂停原因")
    prep.add_argument("--source", type=Path, required=True, help="明确授权的账号源文件")
    prep.add_argument("--sample", type=Path, required=True, help="离线样本库目录")
    prep.add_argument("--report", type=Path, required=True, help="本地代理实测报告 JSON")
    prep.add_argument("--legacy", type=Path, help="可选的旧账号数据库（只读识别）")
    sub.add_parser("status", help="只读摘要，不访问网络，不修改数据库")
    sub.add_parser("ip-ledger", help="只读查看各实际 IP 的请求、成果及阻塞账本")
    run = sub.add_parser("run", help="执行已恢复的生产任务；不会清除暂停")
    run.add_argument("--limit", type=int, default=2, help="最大处理数；小批次门槛仍然生效")
    pause = sub.add_parser("pause", help="停止新提交，让当前任务落盘后退出并释放锁")
    pause.add_argument("--reason", default="OPERATOR_PAUSE")
    stop = sub.add_parser("stop", help="优雅停止，已提交任务保留供恢复")
    stop.add_argument("--reason", default="OPERATOR_STOP")
    for name, help_text in (
        ("resume", "修复验收后显式放行；有未解决平台阻塞时拒绝"),
        ("resolve-block", "按平台证据解除一条阻塞，不自动启动"),
        ("budget", "登记当前供应商余额及累计预算，已用流量不会归零"),
        ("accept", "核对完整 2/20 个结果、流量和导出，记录小批次验收"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--evidence", type=Path, required=True, help="本地 JSON 证据文件")
    sub.add_parser("heartbeat", help="监督者明确发出一次心跳；与进度读取分开")
    sub.add_parser("recover", help="执行进程退出后恢复中断状态；有预留请求的任务先核查")
    requeue = sub.add_parser("requeue-unsubmitted", help="修复后仅重新排队没有任何发送记录的任务")
    requeue.add_argument("job_id")
    requeue.add_argument("--evidence", type=Path, required=True)
    export = sub.add_parser("export", help="导出所有源记录并逐格核对凭证，包含未处理结论")
    export.add_argument(
        "path", type=Path, nargs="?", default=ROOT / "outputs/production/Agnes开户结果.xlsx"
    )
    backup = sub.add_parser("backup", help="锁内一致性备份数据库与加密凭证")
    backup.add_argument("directory", type=Path)


def code_digest():
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def evidence(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("reason") or not data.get("verification"):
        raise StorageError("证据需要 reason 与 verification；只填写脱敏核查结论。")
    return data, f"{path.resolve()}#sha256={hashlib.sha256(path.read_bytes()).hexdigest()}"


def record_repair(bulk, reason, ref):
    with bulk.connection(write=True) as db:
        db.execute(
            "INSERT INTO bulk_repairs(at,reason,evidence,code_sha256) VALUES(?,?,?,?)",
            (time.time(), reason, ref, code_digest()),
        )


def recover(bulk):
    recovered = 0
    with bulk.connection(write=True) as db:
        for job in list(
            db.execute(
                "SELECT id,state,phase,submitted_at FROM registration_jobs WHERE state='RUNNING'"
            )
        ):
            reserved = db.execute(
                "SELECT kind,at FROM bulk_requests WHERE job_id=? ORDER BY at DESC LIMIT 1",
                (job["id"],),
            ).fetchone()
            submitted = job["submitted_at"] or (reserved[1] if reserved else None)
            state = "UNKNOWN" if submitted else "PENDING"
            phase = reserved[0] if reserved else job["phase"]
            db.execute(
                """UPDATE registration_jobs SET state=?,phase=?,submitted_at=?,
                       error_code='INTERRUPTED_RECOVERY',message='中断恢复；已预留请求先核查'
                       WHERE id=?""",
                (state, phase, submitted, job["id"]),
            )
            db.execute(
                """INSERT INTO job_events(job_id,at,from_state,to_state,code,message)
                       VALUES(?,?,'RUNNING',?,'INTERRUPTED_RECOVERY','保留持久提交边界')""",
                (job["id"], time.time(), state),
            )
            recovered += 1
        db.execute("UPDATE proxies SET leased_job_id=NULL")
        db.execute("UPDATE bulk_runs SET finished_at=? WHERE finished_at IS NULL", (time.time(),))
        db.execute("UPDATE bulk_control SET pid=NULL WHERE id=1")
    return {"recovered": recovered, "reregistered": 0}


def handle(args):
    settings = load_settings(args.config or ROOT / "config.production.toml")
    if settings.mode != "agnes":
        raise StorageError("生产入口需要独立 Agnes 配置。")
    bulk = BulkStore(settings.database)
    cmd = args.bulk_command
    if cmd == "prepare":
        return prepare(
            settings,
            args.source.resolve(),
            args.sample.resolve(),
            args.report.resolve(),
            args.legacy.resolve() if args.legacy else None,
        )
    if cmd == "status":
        return bulk.status(Vault(settings.vault).snapshot())
    if cmd == "ip-ledger":
        return bulk.ip_ledger()
    if cmd in {"pause", "stop"}:
        current_reason = bulk.control()["reason"]
        bulk.update(
            action="PAUSED" if cmd == "pause" else "STOPPING", reason=current_reason or args.reason
        )
        return bulk.status()
    if cmd == "heartbeat":
        bulk.update(supervisor_at=time.time())
        return {"supervisor_at": bulk.control()["supervisor_at"]}
    if cmd == "run":
        if args.limit <= 0:
            raise StorageError("--limit 必须大于零。")
        from .bulk_runner import BulkRunner

        return asyncio.run(BulkRunner(settings, ROOT).run(args.limit))
    with RunLock(settings.database):
        bulk.initialize()
        if cmd == "recover":
            return recover(bulk)
        if cmd == "export":
            if args.path.suffix.lower() != ".xlsx":
                raise StorageError("生产交付文件使用 .xlsx。")
            return write_bulk_excel(args.path, bulk, Vault(settings.vault))
        if cmd == "backup":
            args.directory.mkdir(parents=True, exist_ok=False)
            with (
                bulk.connection() as source,
                closing(sqlite3.connect(args.directory / "jobs.db")) as target,
            ):
                source.backup(target)
            shutil.copy2(settings.vault, args.directory / "credentials.dpapi")
            return {"backup": str(args.directory.resolve()), "consistent": True}
        data, ref = evidence(args.evidence)
        if cmd == "requeue-unsubmitted":
            with bulk.connection(write=True) as db:
                job = db.execute(
                    "SELECT * FROM registration_jobs WHERE id=?", (args.job_id,)
                ).fetchone()
                reserved = db.execute(
                    "SELECT 1 FROM bulk_requests WHERE job_id=?", (args.job_id,)
                ).fetchone()
                if (not job or reserved or job["submitted_at"] is not None
                        or job["phase"] != "PREPARE" or job["state"] != "NEEDS_REVIEW"
                        or job["error_code"] != "SELECTOR_CHANGED"):
                    raise StorageError("TASK_NOT_PROVABLY_UNSUBMITTED")
                if db.execute("SELECT 1 FROM accounts WHERE user_id=? AND provider='agnes-api'",
                              (job["user_id"],)).fetchone():
                    raise StorageError("EXISTING_ACCOUNT_REQUIRES_RECONCILIATION")
                db.execute("UPDATE registration_jobs SET state='PENDING',finished_at=NULL,"
                           "error_code='REPAIR_CONFIRMED_UNSUBMITTED',message=? WHERE id=?",
                           (ref, args.job_id))
                db.execute("""INSERT INTO job_events(job_id,at,from_state,to_state,code,message)
                    VALUES(?,?,'NEEDS_REVIEW','PENDING','REPAIR_CONFIRMED_UNSUBMITTED',?)""",
                           (args.job_id, time.time(), ref))
        elif cmd == "resolve-block":
            with bulk.connection(write=True) as db:
                block = db.execute(
                    "SELECT * FROM bulk_blocks WHERE id=? AND released_at IS NULL",
                    (data.get("block_id"),),
                ).fetchone()
                if (
                    not block
                    or data.get("scope") != block["scope"]
                    or data.get("subject") != block["subject"]
                ):
                    raise StorageError("BLOCK_SCOPE_MISMATCH")
                condition = data.get("condition")
                if condition == "retry_after_elapsed":
                    if block["retry_at"] is None or time.time() < block["retry_at"]:
                        raise StorageError("PLATFORM_WAIT_NOT_ESTABLISHED")
                elif condition == "platform_rule_confirmed":
                    if not data.get("platform_reference") or not data.get("recovery_condition"):
                        raise StorageError("PLATFORM_RULE_EVIDENCE_REQUIRED")
                    if data.get("not_before", time.time() + 1) > time.time():
                        raise StorageError("PLATFORM_WAIT_NOT_FINISHED")
                elif condition == "scope_corrected_to_ip":
                    if (
                        block["scope"] != "global"
                        or block["code"] != "IP_REGISTRATION_LIMIT"
                        or not data.get("platform_reference")
                        or not db.execute(
                            "SELECT 1 FROM bulk_blocks WHERE scope='ip' AND code=? "
                            "AND released_at IS NULL",
                            (block["code"],),
                        ).fetchone()
                    ):
                        raise StorageError("SPECIFIC_IP_BLOCK_EVIDENCE_REQUIRED")
                else:
                    raise StorageError("PLATFORM_RECOVERY_CONDITION_REQUIRED")
                db.execute(
                    "UPDATE bulk_blocks SET released_at=?,release_evidence=? WHERE id=?",
                    (time.time(), ref, block["id"]),
                )
        elif cmd == "budget":
            remaining, observed = data.get("remaining_bytes"), data.get("observed_at")
            basis = data.get("budget_basis", "supplier_observation")
            if (
                not isinstance(remaining, int)
                or remaining <= 0
                or not isinstance(observed, (int, float))
                or not 0 <= time.time() - observed < 86400
                or not data.get("supplier_reference")
                or basis not in {"supplier_observation", "user_declared_ceiling"}
            ):
                raise StorageError("CURRENT_SUPPLIER_BALANCE_EVIDENCE_REQUIRED")
            ctl = bulk.control()
            budget = data.get("budget_bytes", 50_000_000)
            if not isinstance(budget, int) or budget <= ctl["used_bytes"]:
                raise StorageError("BUDGET_MUST_EXCEED_PERSISTED_USAGE")
            if ctl["accepted_count"] < 2 and budget > 50_000_000:
                raise StorageError("DIAGNOSTIC_BUDGET_MAX_50MB")
            reserve = data.get("finish_reserve_bytes", max(100_000_000, int(remaining * 0.1)))
            if not isinstance(reserve, int) or not 0 <= reserve < remaining:
                raise StorageError("FINISH_RESERVE_INVALID")
            bulk.update(
                supplier_remaining=remaining,
                balance_at=observed,
                balance_used=ctl["used_bytes"],
                balance_evidence=ref,
                budget_bytes=budget,
                budget_basis=basis,
                finish_reserve_bytes=reserve,
            )
        elif cmd == "resume":
            with bulk.connection() as db:
                if db.execute(
                    "SELECT 1 FROM bulk_blocks WHERE released_at IS NULL AND scope='global'"
                ).fetchone():
                    raise StorageError("PLATFORM_BLOCK_UNRESOLVED：先核实恢复条件，暂停原因保留。")
                if db.execute("SELECT 1 FROM registration_jobs WHERE state='RUNNING'").fetchone():
                    raise StorageError("RECOVERY_REQUIRED")
            # Gate validates the prospective state; restore the pause on any failure.
            previous = bulk.control()
            bulk.update(action="RUNNING", reason="", progress_at=time.time())
            try:
                bulk.gate(new_account=True)
            except StorageError:
                bulk.update(action=previous["action"], reason=previous["reason"])
                raise
        elif cmd == "accept":
            with bulk.connection() as db:
                results = list(
                    db.execute("""SELECT r.* FROM bulk_results r WHERE r.id IN
                    (SELECT max(id) FROM bulk_results GROUP BY job_id)""")
                )
            count = len(results)
            required = 2 if bulk.control()["accepted_count"] < 2 else 20
            if count < required or any(r["state"] not in {"SUCCEEDED", "SKIPPED"} for r in results):
                raise StorageError("SMALL_BATCH_RESULTS_INCOMPLETE")
            if not any(r["flow_verified"] for r in results) or any(
                r["state"] == "SUCCEEDED" and not r["flow_verified"] for r in results
            ):
                raise StorageError("FULL_REGISTRATION_FLOW_NOT_VERIFIED")
            export = write_bulk_excel(
                ROOT / "outputs/production/Agnes开户结果.xlsx", bulk, Vault(settings.vault)
            )
            if not export["exact_readback"]:
                raise StorageError("EXPORT_NOT_VERIFIED")
            bulk.update(
                accepted_count=required, baseline_bytes=bulk.control()["used_bytes"] / count
            )
        else:
            raise StorageError("UNKNOWN_BULK_COMMAND")
        record_repair(bulk, data["reason"], ref)
        return bulk.status()
