"""Offline, repeatable migration of the source inventory and existing results."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from email_validator import EmailNotValidError, validate_email

from .bulk_store import BulkStore
from .lock import RunLock
from .storage import StorageError
from .vault import Vault


def source_rows(path):
    rows = []
    seen = set()
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or (number == 1 and line.strip() == "卡密导出"):
            continue
        fields = line.strip().split("----")
        email = fields[0].strip().casefold()
        reason = ""
        if len(fields) != 4 or not all(fields) or email.count("@") != 1:
            reason = "SOURCE_INVALID_FIELDS"
        elif email in seen:
            reason = "SOURCE_DUPLICATE_EMAIL"
        else:
            try:
                validate_email(email, check_deliverability=False)
            except EmailNotValidError:
                reason = "SOURCE_INVALID_FIELDS"
        seen.add(email)
        rows.append((number, email, fields, reason))
    return rows


def prepare(settings, source: Path, sample: Path, report_path: Path, legacy: Path | None = None):
    if settings.database.resolve() == (sample / "jobs.db").resolve():
        raise StorageError("生产库必须与样本库分离。")
    parsed = source_rows(source)
    fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    destination = settings.database
    destination.parent.mkdir(parents=True, exist_ok=True)
    with RunLock(sample / "jobs.db"), RunLock(destination):
        if not destination.exists():
            temporary = destination.with_suffix(".initializing")
            with closing(
                sqlite3.connect((sample / "jobs.db").as_uri() + "?mode=ro", uri=True)
            ) as src:
                with closing(sqlite3.connect(temporary)) as dst:
                    src.backup(dst)
            temporary_vault = settings.vault.with_suffix(".initializing")
            shutil.copy2(sample / "credentials.dpapi", temporary_vault)
            os.replace(temporary_vault, settings.vault)
            os.replace(temporary, destination)
        if not settings.vault.exists():
            raise StorageError("生产凭证库缺失；停止迁移，保留数据库待核查。")
        bulk = BulkStore(destination)
        bulk.initialize()
        ctl = bulk.control()
        if ctl["source_sha256"] and ctl["source_sha256"] != fingerprint:
            raise StorageError("源文件与已登记清单不同；没有覆盖生产状态。")
        vault = Vault(settings.vault)
        originals = Vault(sample / "credentials.dpapi").snapshot()
        records = vault.snapshot()
        # A repeated prepare only verifies the inventory. Never overwrite rotated tokens.
        if ctl["prepared_at"]:
            if len(bulk.rows()) != len(parsed):
                raise StorageError("生产源清单行数不一致。")
            return {
                "imported": 0,
                "duplicates": len(parsed),
                "source_records": len(parsed),
                "preserved_existing": True,
                "network_requests": 0,
            }
        with bulk.connection() as db:
            users = {r["email"].casefold(): dict(r) for r in db.execute("SELECT * FROM users")}
        for user in users.values():
            if (
                user["secret_ref"] in originals
                and records.get(user["secret_ref"]) != originals[user["secret_ref"]]
            ):
                raise StorageError("首次迁移的凭证副本不一致；停止并保留现场。")
        legacy_emails = set()
        if legacy and legacy.exists():
            with closing(sqlite3.connect(legacy.as_uri() + "?mode=ro", uri=True)) as db:
                legacy_emails = {r[0].casefold() for r in db.execute("SELECT email FROM users")}
        imported = duplicates = invalid = 0
        additions = {}
        with bulk.connection(write=True) as db:
            db.execute(
                """INSERT OR IGNORE INTO batches
                (id,provider,action,pause_reason,blocked_until,created_at)
                VALUES('production-20261014','agnes-api','PAUSED','PREPARATION_REQUIRED',0,?)""",
                (time.time(),),
            )
            for line, email, fields, reason in parsed if not ctl["source_sha256"] else []:
                user = users.get(email)
                uid = (
                    user["id"]
                    if user
                    else "mail-" + hashlib.sha256(email.encode()).hexdigest()[:16]
                )
                ref = user["secret_ref"] if user else uid
                if reason:
                    ref = "source-line-" + str(line)
                    additions[ref] = {
                        "email": email,
                        "mailbox_password": fields[1] if len(fields) > 1 else "",
                    }
                    uid = None
                    invalid += 1
                elif user:
                    duplicates += 1
                else:
                    record = records.get(ref)
                    if record and record.get("email", "").casefold() != email:
                        raise StorageError("CREDENTIAL_REFERENCE_COLLISION")
                    if not record:
                        additions[ref] = {
                            "email": email,
                            "mailbox_password": fields[1],
                            "client_id": fields[2],
                            "refresh_token": fields[3],
                            "mailbox_authorized": True,
                            "mailbox_transport": "graph",
                            "agnes_password": "Aa9!" + secrets.token_urlsafe(20),
                        }
                    db.execute(
                        """INSERT INTO users
                        (id,email,display_name,consent,consent_reference,mailbox_authorized,secret_ref,created_at)
                        VALUES(?,?,'',1,?,1,?,?)""",
                        (uid, email, settings.approval.reference, ref, time.time()),
                    )
                    job_id = str(uuid4())
                    legacy_exists = email in legacy_emails
                    db.execute(
                        """INSERT INTO registration_jobs
                        (id,batch_id,user_id,provider,state,phase,attempts,next_attempt_at,
                         error_code,message,created_at)
                        VALUES(?,'production-20261014',?,'agnes-api',?,'PREPARE',0,0,?,?,?)""",
                        (
                            job_id,
                            uid,
                            "NEEDS_REVIEW" if legacy_exists else "PENDING",
                            "EXISTING_LEGACY_ACCOUNT" if legacy_exists else "",
                            "旧库已登记，须核对既有成果" if legacy_exists else "",
                            time.time(),
                        ),
                    )
                    db.execute(
                        """INSERT INTO job_events(job_id,at,from_state,to_state,code,message)
                        VALUES(?,?,'',?,'SOURCE_IMPORTED','源清单去重导入')""",
                        (job_id, time.time(), "NEEDS_REVIEW" if legacy_exists else "PENDING"),
                    )
                    imported += 1
                db.execute(
                    "INSERT INTO bulk_source(line,email,user_id,secret_ref,reason) "
                    "VALUES(?,?,?,?,?)",
                    (line, email, uid, ref, reason),
                )
            if additions:
                vault.set_many(additions)
            historical_bytes = sum(
                g.get("proxy_sent_bytes", 0) + g.get("proxy_received_bytes", 0)
                for g in report.get("groups", [])
            )
            db.execute(
                """UPDATE bulk_control SET source_sha256=?,historical_bytes=?,
                       progress_at=?,reason='PREPARATION_REQUIRED' WHERE id=1""",
                (fingerprint, historical_bytes, time.time()),
            )
        # Import trusted historical evidence without another authentication request.
        records.update(additions)
        with bulk.connection(write=True) as db:
            for group in report.get("groups", []):
                ip = group.get("original_egress_ip", group.get("egress_ip", "unknown"))
                for account in group.get("accounts", []):
                    uid = account["user_id"]
                    user = next((u for u in users.values() if u["id"] == uid), None)
                    if not user:
                        raise StorageError("HISTORICAL_ACCOUNT_NOT_FOUND")
                    record = records[user["secret_ref"]]
                    if account.get("key_authenticated") and account.get("key_auth_status") == 200:
                        if not (
                            record.get("api_key")
                            and record.get("activated")
                            and account.get("account_activated")
                            and record.get("email", "").casefold() == user["email"].casefold()
                        ):
                            raise StorageError("HISTORICAL_KEY_EVIDENCE_MISMATCH")
                        db.execute(
                            "INSERT OR IGNORE INTO bulk_auth VALUES(?,?,?,200,1,?)",
                            (
                                uid,
                                hashlib.sha256(record["api_key"].encode()).hexdigest(),
                                report["finished_at"],
                                "proxy-registration-test-20261014.json",
                            ),
                        )
                jobs = list(
                    db.execute(
                        "SELECT id FROM registration_jobs WHERE batch_id=?", (group["batch"],)
                    )
                )
                for job in jobs:
                    events = list(
                        db.execute(
                            """SELECT at,code FROM job_events WHERE job_id=?
                        AND code IN ('CHECKPOINT_EMAIL_REQUESTED',
                                     'CHECKPOINT_REGISTRATION_SUBMITTED',
                                     'CHECKPOINT_KEY_REQUESTED') ORDER BY id""",
                            (job[0],),
                        )
                    )
                    for event in events:
                        db.execute(
                            """INSERT OR IGNORE INTO bulk_requests
                            (job_id,kind,ip,at,outcome,historical)
                            VALUES(?,?,?,?, 'HISTORICAL',1)""",
                            (job[0], event[1].removeprefix("CHECKPOINT_"), ip, event[0]),
                        )
        if report.get("status") == "PAUSED_PLATFORM_IP_LIMIT":
            bulk.block("IP_REGISTRATION_LIMIT", evidence="历史 HTTP 400；注册限流恢复时间未知")
            for group in report.get("groups", []):
                if group.get("status") == "IP_LIMIT_OBSERVED":
                    bulk.block(
                        "IP_REGISTRATION_LIMIT",
                        scope="ip",
                        subject=group["egress_ip"],
                        evidence="/api/verification HTTP 400; Retry-After 未提供",
                    )
        bulk.update(prepared_at=time.time(), phase="PREPARED_PAUSED")
        return {
            "imported": imported,
            "duplicates": duplicates,
            "invalid_source_rows": invalid,
            "source_records": len(parsed),
            "preserved_existing": True,
            "network_requests": 0,
        }
