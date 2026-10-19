"""Durable production controls. No credential values belong in this database."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .storage import StorageError

SCHEMA = """
CREATE TABLE IF NOT EXISTS bulk_control (
 id INTEGER PRIMARY KEY CHECK(id=1), action TEXT NOT NULL DEFAULT 'PAUSED',
 reason TEXT NOT NULL DEFAULT 'PREPARATION_REQUIRED', pid INTEGER,
 heartbeat REAL NOT NULL DEFAULT 0, supervisor_at REAL NOT NULL DEFAULT 0,
 progress_at REAL NOT NULL DEFAULT 0, phase TEXT NOT NULL DEFAULT 'PREPARATION',
 used_bytes INTEGER NOT NULL DEFAULT 0, budget_bytes INTEGER NOT NULL DEFAULT 50000000,
 supplier_remaining INTEGER, balance_at REAL, balance_used INTEGER NOT NULL DEFAULT 0,
 balance_evidence TEXT NOT NULL DEFAULT '', accepted_count INTEGER NOT NULL DEFAULT 0,
 baseline_bytes REAL, source_sha256 TEXT NOT NULL DEFAULT '',
 historical_bytes INTEGER NOT NULL DEFAULT 0, prepared_at REAL NOT NULL DEFAULT 0,
 budget_basis TEXT NOT NULL DEFAULT 'supplier_observation',
 finish_reserve_bytes INTEGER NOT NULL DEFAULT 100000000
);
INSERT OR IGNORE INTO bulk_control(id) VALUES (1);
CREATE TABLE IF NOT EXISTS bulk_source (
 line INTEGER PRIMARY KEY, email TEXT NOT NULL, user_id TEXT,
 secret_ref TEXT NOT NULL, reason TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS bulk_source_user ON bulk_source(user_id)
 WHERE user_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS bulk_auth (
 user_id TEXT PRIMARY KEY, key_sha256 TEXT NOT NULL, key_authenticated_at REAL NOT NULL,
 http_status INTEGER NOT NULL, identity_confirmed INTEGER NOT NULL,
 evidence TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bulk_requests (
 id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, kind TEXT NOT NULL,
 ip TEXT NOT NULL, at REAL NOT NULL, outcome TEXT NOT NULL DEFAULT 'RESERVED',
 historical INTEGER NOT NULL DEFAULT 0,
 UNIQUE(job_id,kind)
);
CREATE INDEX IF NOT EXISTS bulk_request_time ON bulk_requests(kind,at);
CREATE TABLE IF NOT EXISTS bulk_blocks (
 id INTEGER PRIMARY KEY, scope TEXT NOT NULL, subject TEXT NOT NULL,
 code TEXT NOT NULL, observed_at REAL NOT NULL, retry_at REAL,
 evidence TEXT NOT NULL, released_at REAL, release_evidence TEXT
);
CREATE TABLE IF NOT EXISTS bulk_repairs (
 id INTEGER PRIMARY KEY, at REAL NOT NULL, reason TEXT NOT NULL,
 evidence TEXT NOT NULL, code_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bulk_runs (
 id TEXT PRIMARY KEY, pid INTEGER NOT NULL, started_at REAL NOT NULL, finished_at REAL,
 sent_bytes INTEGER NOT NULL DEFAULT 0, received_bytes INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bulk_results (
 id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, at REAL NOT NULL, code TEXT NOT NULL,
 state TEXT NOT NULL, ip TEXT NOT NULL, used_bytes INTEGER NOT NULL,
 flow_verified INTEGER NOT NULL DEFAULT 0
);
"""


class BulkStore:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    @contextmanager
    def connection(self, *, write=False):
        if not self.path.exists():
            raise StorageError("生产库尚未准备；先运行 bulk prepare。")
        mode = "rw" if write else "ro"
        db = sqlite3.connect(self.path.as_uri() + f"?mode={mode}", uri=True, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
        with self.connection(write=True) as db:
            db.executescript(SCHEMA)
            fields = {row[1] for row in db.execute("PRAGMA table_info(bulk_control)")}
            if "budget_basis" not in fields:
                db.execute(
                    "ALTER TABLE bulk_control ADD COLUMN budget_basis TEXT NOT NULL "
                    "DEFAULT 'supplier_observation'"
                )
            if "finish_reserve_bytes" not in fields:
                db.execute(
                    "ALTER TABLE bulk_control ADD COLUMN finish_reserve_bytes "
                    "INTEGER NOT NULL DEFAULT 100000000"
                )

    def control(self) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM bulk_control WHERE id=1").fetchone()
            if not row:
                raise StorageError("生产元数据缺失。")
            return dict(row)

    def update(self, **values):
        allowed = set(self.control()) - {"id"}
        if not values or not set(values) <= allowed:
            raise StorageError("无效的生产控制字段。")
        with self.connection(write=True) as db:
            db.execute(
                "UPDATE bulk_control SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=1",
                tuple(values.values()),
            )

    def rows(self) -> list[dict]:
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute("""
                SELECT s.*, j.id job_id,j.state,j.phase,j.error_code,j.message,j.submitted_at,
                       a.key_sha256,a.key_authenticated_at,a.http_status,a.identity_confirmed
                FROM bulk_source s LEFT JOIN registration_jobs j ON j.user_id=s.user_id
                  AND j.provider='agnes-api'
                LEFT JOIN bulk_auth a ON a.user_id=s.user_id ORDER BY s.line
            """)
            ]

    @staticmethod
    def confirmed(row, record=None):
        matched = (
            row["state"] == "SUCCEEDED"
            and row["http_status"] == 200
            and bool(row["key_authenticated_at"])
            and bool(row["identity_confirmed"])
        )
        if record is not None:
            matched = (
                matched
                and record.get("activated")
                and bool(record.get("api_key"))
                and record.get("email", "").casefold() == row["email"].casefold()
                and hashlib.sha256(record.get("api_key", "").encode()).hexdigest()
                == row["key_sha256"]
            )
        return bool(matched)

    def status(self, records=None):
        rows, ctl = self.rows(), self.control()
        success = sum(
            self.confirmed(r, records.get(r["secret_ref"], {}) if records is not None else None)
            for r in rows
        )
        skipped = sum(bool(r["reason"]) or r["state"] == "SKIPPED" for r in rows)
        pending = sum(not r["reason"] and r["state"] in ("PENDING", "RETRY_WAIT") for r in rows)
        with self.connection() as db:
            recent = db.execute("SELECT code,at FROM bulk_results ORDER BY id DESC LIMIT 1")
            recent = recent.fetchone()
            blocks = [
                dict(r)
                for r in db.execute(
                    "SELECT id,scope,subject,code,retry_at FROM bulk_blocks "
                    "WHERE released_at IS NULL"
                )
            ]
        return {
            "total": len(rows),
            "succeeded_authenticated": success,
            "skipped": skipped,
            "needs_review": len(rows) - success - skipped - pending,
            "unprocessed": pending,
            "remaining_without_verified_key": len(rows) - success,
            "action": ctl["action"],
            "pause_reason": ctl["reason"],
            "phase": ctl["phase"],
            "pid": ctl["pid"],
            "heartbeat": ctl["heartbeat"],
            "heartbeat_fresh": time.time() - ctl["heartbeat"] < 45,
            "supervisor_at": ctl["supervisor_at"],
            "last_progress_at": ctl["progress_at"],
            "used_bytes": ctl["used_bytes"],
            "budget_remaining_bytes": max(0, ctl["budget_bytes"] - ctl["used_bytes"]),
            "supplier_remaining_bytes": self.supplier_remaining(ctl),
            "budget_basis": ctl["budget_basis"],
            "supplier_balance_verified": ctl["budget_basis"] == "supplier_observation",
            "historical_recorded_bytes": ctl["historical_bytes"],
            "historical_traffic_complete": False,
            "accepted_processed_count": ctl["accepted_count"],
            "latest_result": dict(recent) if recent else None,
            "active_blocks": blocks,
            "bulk_ready_claimed": ctl["accepted_count"] >= 20
            and not any(b["scope"] == "global" for b in blocks),
        }

    def ip_ledger(self):
        with self.connection() as db:
            addresses = [r[0] for r in db.execute("SELECT DISTINCT ip FROM bulk_requests")]
            result = []
            for ip in addresses:
                counts = dict(
                    db.execute(
                        "SELECT kind,count(*) FROM bulk_requests WHERE ip=? GROUP BY kind", (ip,)
                    )
                )
                successful = db.execute(
                    """SELECT count(DISTINCT r.job_id) FROM bulk_requests r
                    JOIN registration_jobs j ON j.id=r.job_id
                    JOIN bulk_auth a ON a.user_id=j.user_id
                    WHERE r.ip=? AND r.kind='REGISTRATION_SUBMITTED'
                    AND j.state='SUCCEEDED' AND a.http_status=200""",
                    (ip,),
                ).fetchone()[0]
                failed = db.execute(
                    """SELECT count(DISTINCT r.job_id) FROM bulk_requests r
                    JOIN registration_jobs j ON j.id=r.job_id
                    WHERE r.ip=? AND j.state IN ('SKIPPED','FAILED','NEEDS_REVIEW','UNKNOWN')""",
                    (ip,),
                ).fetchone()[0]
                blocked = bool(
                    db.execute(
                        "SELECT 1 FROM bulk_blocks WHERE subject=? AND released_at IS NULL", (ip,)
                    ).fetchone()
                )
                result.append(
                    {
                        "ip": ip,
                        "requests": counts,
                        "successes": successful,
                        "failed_or_unknown": failed,
                        "blocked": blocked,
                    }
                )
        return result

    @staticmethod
    def supplier_remaining(ctl):
        if ctl["supplier_remaining"] is None:
            return None
        return max(0, ctl["supplier_remaining"] - (ctl["used_bytes"] - ctl["balance_used"]))

    def block(
        self,
        code,
        *,
        scope="global",
        subject="registration",
        retry_at=None,
        evidence="platform response",
        pause=True,
    ):
        with self.connection(write=True) as db:
            if not db.execute(
                """SELECT 1 FROM bulk_blocks WHERE scope=? AND subject=? AND code=?
                                AND released_at IS NULL""",
                (scope, subject, code),
            ).fetchone():
                db.execute(
                    """INSERT INTO bulk_blocks(scope,subject,code,observed_at,retry_at,evidence)
                           VALUES(?,?,?,?,?,?)""",
                    (scope, subject, code, time.time(), retry_at, evidence),
                )
            if pause:
                db.execute("UPDATE bulk_control SET action='PAUSED',reason=? WHERE id=1", (code,))

    def gate(self, *, new_account=False):
        ctl = self.control()
        if not ctl["prepared_at"]:
            raise StorageError("PREPARATION_INCOMPLETE")
        if ctl["action"] != "RUNNING":
            raise StorageError(ctl["reason"] or ctl["action"])
        with self.connection() as db:
            if db.execute(
                "SELECT 1 FROM bulk_blocks WHERE released_at IS NULL AND scope='global'"
            ).fetchone():
                raise StorageError("PLATFORM_BLOCK_UNRESOLVED")
        if time.time() - ctl["supervisor_at"] > 600:
            raise StorageError("SUPERVISOR_LOST")
        if time.time() - ctl["progress_at"] > 300:
            raise StorageError("NO_PROGRESS")
        if not ctl["balance_at"] or (
            ctl["budget_basis"] == "supplier_observation"
            and time.time() - ctl["balance_at"] > 86400
        ):
            raise StorageError("SUPPLIER_BALANCE_REQUIRED")
        allowance = 10_000_000 if new_account else 0
        if ctl["used_bytes"] + allowance >= ctl["budget_bytes"]:
            raise StorageError("TRAFFIC_BUDGET")
        remaining = self.supplier_remaining(ctl)
        reserve = ctl["finish_reserve_bytes"]
        if remaining is None or remaining <= reserve + allowance:
            raise StorageError("SUPPLIER_BALANCE_LOW")

    def reserve(self, job_id: str, kind: str, ip: str, per_minute: float) -> float:
        """Reserve before sending; never refund uncertain requests. Return throttle delay."""
        self.gate()
        if kind not in {"EMAIL_REQUESTED", "REGISTRATION_SUBMITTED", "KEY_REQUESTED"} or not ip:
            raise StorageError("REQUEST_SCOPE_INVALID")
        with self.connection(write=True) as db:
            control = db.execute("SELECT action,reason FROM bulk_control WHERE id=1").fetchone()
            if control[0] != "RUNNING":
                raise StorageError(control[1] or control[0])
            if db.execute(
                "SELECT 1 FROM bulk_requests WHERE job_id=? AND kind=?", (job_id, kind)
            ).fetchone():
                raise StorageError("REQUEST_ALREADY_RESERVED")
            if db.execute(
                """SELECT 1 FROM bulk_blocks WHERE released_at IS NULL AND
                             (scope='global' OR (scope='ip' AND subject=?))""",
                (ip,),
            ).fetchone():
                raise StorageError("PLATFORM_BLOCK_UNRESOLVED")
            if kind == "EMAIL_REQUESTED":
                count = db.execute(
                    "SELECT count(*) FROM bulk_requests WHERE ip=? AND kind=?", (ip, kind)
                ).fetchone()[0]
                if count >= 2:
                    raise StorageError("IP_SEND_BUDGET_EXHAUSTED")
            if kind != "KEY_REQUESTED":
                last = db.execute(
                    "SELECT max(at) FROM bulk_requests WHERE kind=? AND ip=?", (kind, ip)
                )
                delay = (last.fetchone()[0] or 0) + 60 / per_minute - time.time()
                if delay > 0:
                    return delay
            db.execute(
                "INSERT INTO bulk_requests(job_id,kind,ip,at) VALUES(?,?,?,?)",
                (job_id, kind, ip, time.time()),
            )
            db.execute(
                "UPDATE bulk_control SET phase=?,progress_at=? WHERE id=1", (kind, time.time())
            )
        return 0

    def authenticate(self, user_id, key, identity, *, at=None, evidence="models HTTP 200"):
        if not key or not identity:
            raise StorageError("KEY_IDENTITY_NOT_CONFIRMED")
        with self.connection(write=True) as db:
            db.execute(
                """INSERT INTO bulk_auth VALUES(?,?,?,200,1,?)
                ON CONFLICT(user_id) DO UPDATE SET key_sha256=excluded.key_sha256,
                key_authenticated_at=excluded.key_authenticated_at,http_status=200,
                identity_confirmed=1,evidence=excluded.evidence""",
                (user_id, hashlib.sha256(key.encode()).hexdigest(), at or time.time(), evidence),
            )

    def start_run(self, run_id):
        with self.connection(write=True) as db:
            db.execute(
                "INSERT INTO bulk_runs(id,pid,started_at) VALUES(?,?,?)",
                (run_id, os.getpid(), time.time()),
            )
            db.execute(
                "UPDATE bulk_control SET pid=?,heartbeat=?,progress_at=? WHERE id=1",
                (os.getpid(), time.time(), time.time()),
            )

    def traffic(self, run_id, sent, received):
        with self.connection(write=True) as db:
            old = db.execute(
                "SELECT sent_bytes,received_bytes FROM bulk_runs WHERE id=?", (run_id,)
            ).fetchone()
            delta = sent + received - old[0] - old[1]
            if delta < 0:
                raise StorageError("TRAFFIC_COUNTER_REGRESSED")
            db.execute(
                "UPDATE bulk_runs SET sent_bytes=?,received_bytes=? WHERE id=?",
                (sent, received, run_id),
            )
            db.execute(
                "UPDATE bulk_control SET used_bytes=used_bytes+?,heartbeat=? WHERE id=1",
                (delta, time.time()),
            )

    def finish_run(self, run_id):
        with self.connection(write=True) as db:
            db.execute("UPDATE bulk_runs SET finished_at=? WHERE id=?", (time.time(), run_id))
            db.execute(
                """UPDATE bulk_control SET pid=NULL,heartbeat=?,
                       action=CASE WHEN action IN ('RUNNING','STOPPING') THEN 'STOPPED'
                       ELSE action END WHERE id=1""",
                (time.time(),),
            )

    def result(self, task, result, ip, used_bytes, flow_verified=False):
        with self.connection(write=True) as db:
            db.execute(
                """INSERT INTO bulk_results(job_id,at,code,state,ip,used_bytes,flow_verified)
                       VALUES(?,?,?,?,?,?,?)""",
                (
                    task.id,
                    time.time(),
                    result.code,
                    result.state,
                    ip,
                    used_bytes,
                    int(flow_verified),
                ),
            )
            db.execute(
                "UPDATE bulk_requests SET outcome=? WHERE job_id=? AND outcome='RESERVED'",
                (result.code or result.state, task.id),
            )
            db.execute(
                "UPDATE bulk_control SET progress_at=?,phase=? WHERE id=1",
                (time.time(), result.state),
            )
        with self.connection() as db:
            recent = list(
                db.execute(
                    "SELECT code,state,used_bytes FROM bulk_results ORDER BY id DESC LIMIT 10"
                )
            )
        if used_bytes > 10_000_000:
            return "ACCOUNT_TRAFFIC_HIGH"
        baseline = self.control()["baseline_bytes"]
        if len(recent) == 10 and baseline and sum(r[2] for r in recent) / 10 > baseline * 2:
            return "TRAFFIC_AVERAGE_HIGH"
        if (
            len(recent) >= 3
            and len({r[0] for r in recent[:3]}) == 1
            and all(r[1] != "SUCCEEDED" for r in recent[:3])
        ):
            return "REPEATED_FAILURE"
        if len(recent) == 10 and sum(r[1] != "SUCCEEDED" for r in recent) >= 5:
            return "FAILURE_RATIO_HIGH"
        return ""

    def incident(self, directory: Path, code, task=None, ip=""):
        self.update(action="PAUSED", reason=code)
        payload = {
            "at": time.time(),
            "code": code,
            "job_id": task.id if task else None,
            "ip": ip,
            "used_bytes": self.control()["used_bytes"],
        }
        if task:
            with self.connection() as db:
                row = db.execute(
                    "SELECT phase,submitted_at FROM registration_jobs WHERE id=?", (task.id,)
                ).fetchone()
            payload.update(phase=row[0], request_reserved=row[1] is not None)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "latest-incident.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
        return path
