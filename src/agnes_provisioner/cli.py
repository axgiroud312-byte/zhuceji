from __future__ import annotations

import argparse
import asyncio
import csv
import getpass
import json
import sqlite3
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from .agnes import AgnesAdapter
from .config import load_settings
from .domain import STATE_LABELS, State
from .lock import RunLock
from .mailbox import MailboxError, OutlookMailbox
from .mock import MockAdapter
from .privacy import mask_email, safe_cell
from .proxy import ProxyManager
from .scheduler import Scheduler
from .storage import Storage, StorageError
from .users import import_users
from .vault import Vault, VaultError


def emit(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Agnes 开户任务管理。先用 demo 检查模拟流程。")
    root.add_argument("--config", type=Path, help="本地 TOML 配置文件")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="初始化本地数据库")
    imports = commands.add_parser("import-users", help="从 CSV 导入获准开户的用户")
    imports.add_argument("path", type=Path)
    create = commands.add_parser("create-batch", help="创建任务；已存在的用户任务会去重")
    create.add_argument("batch")
    create.add_argument("--users", nargs="+", help="只为指定的用户 ID 创建任务")
    run = commands.add_parser("run", help="执行或继续批次；中断后的已提交任务先核查")
    run.add_argument("batch")
    run.add_argument("--limit", type=int, help="本次最多启动的任务数")
    verify = commands.add_parser("verify-job", help="核验既有注册结果；已提交账号只尝试正常登录")
    verify.add_argument("job_id")
    for name, help_text in (
        ("pause", "暂停新提交"),
        ("resume", "允许运行中的批次继续"),
        ("stop", "停止后续任务"),
        ("recover", "恢复中断状态，保留已提交结果"),
    ):
        cmd = commands.add_parser(name, help=help_text)
        cmd.add_argument("batch")
    status = commands.add_parser("status", help="查看批次统计")
    status.add_argument("batch", nargs="?")
    jobs = commands.add_parser("jobs", help="查看脱敏任务列表")
    jobs.add_argument("--batch")
    history = commands.add_parser("events", help="查看某个任务的状态历史")
    history.add_argument("job_id")
    review = commands.add_parser("review-not-created", help="核查确认未开户后，重新排队")
    review.add_argument("job_id")
    review.add_argument("--evidence", required=True, help="核查记录的引用，不填写密码或令牌")
    proxy = commands.add_parser("proxy-import", help="导入授权代理，凭证使用环境变量引用")
    proxy.add_argument("path", type=Path)
    commands.add_parser("proxy-list", help="查看代理健康状态")
    check = commands.add_parser("proxy-check", help="检测代理连通性")
    check.add_argument("proxy_id")
    mailboxes = commands.add_parser(
        "import-mailboxes", help="加密导入邮箱----密码----客户端ID----令牌"
    )
    mailboxes.add_argument("path", type=Path)
    mailboxes.add_argument("--authorized", action="store_true", help="已获这些用户的邮箱验证授权")
    mailboxes.add_argument("--consent-reference", required=True, help="本次用户授权记录的引用")
    mailbox = commands.add_parser("mailbox-check", help="只读检查某用户的验证码接收连接")
    mailbox.add_argument("user_id")
    secret = commands.add_parser("set-account-password", help="以隐藏输入设置用户的 Agnes 登录密码")
    secret.add_argument("user_id")
    export = commands.add_parser("export", help="导出任务 Excel 或 CSV；默认隐藏邮箱与凭证")
    export.add_argument("path", type=Path)
    export.add_argument("--batch")
    export.add_argument(
        "--include-secrets", action="store_true", help="交付文件包含邮箱密码和 API Key"
    )
    demo = commands.add_parser("demo", help="在独立数据库执行模拟任务，不访问 Agnes")
    demo.add_argument("--count", type=int, default=1000)
    demo.add_argument("--directory", type=Path, default=Path("output/demo"))
    remove = commands.add_parser("delete-user", help="删除此用户的本地任务记录和加密凭证")
    remove.add_argument("user_id")
    backup = commands.add_parser("backup", help="一致性备份任务数据库与加密凭证")
    backup.add_argument("directory", type=Path)
    web = commands.add_parser("web", help="启动可视化 Web 前端控制台")
    web.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    web.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    web.add_argument("--no-browser", action="store_true", help="启动时不自动打开浏览器")
    from .bulk import add_parser

    add_parser(commands)
    return root


def import_mailboxes(
    storage: Storage, vault: Vault, path: Path, authorized: bool, consent_reference: str
) -> dict:
    if not authorized:
        raise StorageError("邮箱验证导入需要 --authorized 和用户授权记录。")
    from .users import UserInput

    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        parts = line.strip().split("----")
        if len(parts) != 4:
            raise StorageError("邮箱文件每行需要四段；请检查邮箱、密码、客户端ID和令牌。")
        email_address, password, client_id, token = parts
        key = (
            "mail-"
            + __import__("hashlib").sha256(email_address.casefold().encode()).hexdigest()[:16]
        )
        data = UserInput(
            user_id=key,
            email=email_address,
            consent=True,
            consent_reference=consent_reference,
            mailbox_authorized=True,
            secret_ref=key,
        )
        rows.append((data, password, client_id, token))
    temporary = path.parent / (".agnes-users-" + str(time.time_ns()) + ".csv")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(UserInput.model_fields))
            writer.writeheader()
            writer.writerows(data.model_dump() for data, *_ in rows)
        result = import_users(storage, temporary)
        if result["rejected"]:
            raise StorageError("邮箱资料与已有用户冲突，请先核对用户记录。")
        for data, password, client_id, token in rows:
            record = vault.get(data.secret_ref)
            record.update(
                email=str(data.email).casefold(),
                mailbox_password=password,
                client_id=client_id,
                refresh_token=token,
                mailbox_authorized=True,
                mailbox_transport="graph",
            )
            vault.set(data.secret_ref, record)
            vault.ensure_account_password(data.secret_ref)
        return result
    finally:
        temporary.unlink(missing_ok=True)


def export_rows(storage: Storage, vault: Vault, batch: str | None, secrets: bool) -> list[dict]:
    values = []
    for job in storage.jobs(batch):
        record = vault.get(job["secret_ref"]) if secrets and job["provider"] == "agnes-api" else {}
        state = STATE_LABELS[State(job["state"])]
        if job["error_code"] == "EMAIL_DOMAIN_BLOCKED":
            state = "无法注册" if job["attempts"] else "未提交"
        if job["state"] == State.SUCCEEDED and (
            record.get("api_key") or job["error_code"] == "ACTIVATED_WITH_KEY"
        ):
            state = "已完成"
        elif job["state"] == State.SUCCEEDED:
            state = "账号已确认，缺 API Key" if job["provider"] == "agnes-api" else state
        if job["provider"] == "mock":
            state = "模拟成功" if job["state"] == State.SUCCEEDED else "模拟：" + state
        values.append(
            {
                "用户ID": job["user_id"],
                "邮箱账号": job["email"] if secrets else mask_email(job["email"]),
                "邮箱密码": record.get("mailbox_password", ""),
                "Agnes密码": record.get("agnes_password", "") if record.get("activated") else "",
                "API Key": record.get("api_key", ""),
                "状态": state,
                "说明": job["message"],
                "错误分类": job["error_code"],
                "任务ID": job["job_id"],
                "批次": job["batch"],
                "尝试次数": job["attempts"],
            }
        )
    return values


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise StorageError("没有可导出的任务，请先创建批次。")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({k: safe_cell(v) for k, v in row.items()} for row in rows)


async def demo(args) -> dict:
    if not 1 <= args.count <= 100000:
        raise StorageError("模拟任务数需要在 1 至 100000 之间。")
    from .config import Settings

    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    run_id = str(time.time_ns())
    batch_id = "demo-" + run_id
    path = directory / "users.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["user_id", "email", "consent", "consent_reference"])
        writer.writerows(
            [f"DEMO{run_id}-{i:06d}", f"demo{run_id}-{i}@example.com", True, "模拟数据"]
            for i in range(1, args.count + 1)
        )
    settings = Settings(
        database=directory / "demo.db", concurrency=8, per_minute=1000000, retry_delay_seconds=0.01
    )
    storage = Storage(settings.database)
    try:
        storage.initialize()
        imported = import_users(storage, path)
        batch = storage.create_batch(batch_id, "mock")
        adapter = MockAdapter()
        report = await Scheduler(storage, settings, adapter).run(batch_id)
        report.update(
            imported=imported["imported"],
            created=batch["created"],
            actual_peak=adapter.peak,
            submissions=sum(adapter.submissions.values()),
            duplicate_submissions=sum(v > 1 for v in adapter.submissions.values()),
            environment="mock",
            batch=batch_id,
        )
        write_csv(
            directory / "results.csv", export_rows(storage, Vault(settings.vault), batch_id, False)
        )
        (directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return report
    finally:
        storage.close()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    storage = None
    try:
        if args.command == "bulk":
            from .bulk import handle

            emit(handle(args))
            return 0
        if args.command == "web":
            from .web import serve_web

            serve_web(
                config_path=args.config,
                host=args.host,
                port=args.port,
                open_browser=not args.no_browser,
            )
            return 0
        if args.command == "demo":
            emit(asyncio.run(demo(args)))
            return 0
        settings = load_settings(args.config)
        if settings.database.exists():
            with sqlite3.connect(
                settings.database.resolve().as_uri() + "?mode=ro", uri=True
            ) as probe:
                managed = probe.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='bulk_control'"
                ).fetchone()
            if managed:
                raise StorageError("此库由生产入口管理，请使用 bulk 子命令。")
        storage = Storage(settings.database)
        storage.initialize()
        vault = Vault(settings.vault)
        proxies = ProxyManager(storage)
        cmd = args.command
        if cmd == "init":
            emit({"database": str(storage.path), "mode": settings.mode, "initialized": True})
        elif cmd == "import-users":
            with RunLock(storage.path):
                report = import_users(storage, args.path)
                if settings.mode == "agnes":
                    from sqlalchemy import select

                    from .models import User

                    with storage.session() as session:
                        for user in session.scalars(select(User)):
                            if not vault.get(user.secret_ref):
                                vault.set(
                                    user.secret_ref,
                                    {"email": user.email, "mailbox_authorized": False},
                                )
                                vault.ensure_account_password(user.secret_ref)
            emit(report)
        elif cmd == "create-batch":
            emit(
                storage.create_batch(
                    args.batch, "mock" if settings.mode == "mock" else "agnes-api", args.users
                )
            )
        elif cmd == "run":
            if args.limit is not None and args.limit <= 0:
                raise StorageError("--limit 需要是正整数。")
            adapter = MockAdapter() if settings.mode == "mock" else AgnesAdapter(settings, vault)
            emit(asyncio.run(Scheduler(storage, settings, adapter).run(args.batch, args.limit)))
        elif cmd == "verify-job":
            adapter = MockAdapter() if settings.mode == "mock" else AgnesAdapter(settings, vault)
            emit(asyncio.run(Scheduler(storage, settings, adapter).verify_job(args.job_id)))
        elif cmd in {"pause", "resume", "stop"}:
            action = {"pause": "PAUSED", "resume": "RUNNING", "stop": "STOPPING"}[cmd]
            storage.control(args.batch, action)
            emit({"batch": args.batch, "action": action})
        elif cmd == "recover":
            with RunLock(storage.path):
                emit(storage.recover(args.batch))
        elif cmd == "status":
            report = storage.summary(args.batch)
            if args.batch:
                batch = storage.batch(args.batch)
                report.update(
                    action=batch.action,
                    pause_reason=batch.pause_reason,
                    blocked_until=batch.blocked_until,
                )
            emit(report)
        elif cmd == "jobs":
            records = storage.jobs(args.batch)
            for record in records:
                record["email"] = mask_email(record["email"])
            emit(records)
        elif cmd == "events":
            emit(storage.events(args.job_id))
        elif cmd == "review-not-created":
            with RunLock(storage.path):
                storage.review_not_created(args.job_id, args.evidence)
            emit({"job_id": args.job_id, "state": "PENDING"})
        elif cmd == "proxy-import":
            with RunLock(storage.path):
                emit({"imported": proxies.import_file(args.path)})
        elif cmd == "proxy-list":
            emit(proxies.list())
        elif cmd == "proxy-check":
            with RunLock(storage.path):
                emit(asyncio.run(proxies.check(args.proxy_id, settings.proxy_check_url)))
        elif cmd == "import-mailboxes":
            with RunLock(storage.path):
                emit(
                    import_mailboxes(
                        storage, vault, args.path, args.authorized, args.consent_reference
                    )
                )
        elif cmd == "mailbox-check":
            baseline = OutlookMailbox(vault, storage.secret_reference(args.user_id)).baseline()
            emit(
                {
                    "user_id": args.user_id,
                    "status": "READY",
                    "transport": baseline.get("transport", "imap"),
                }
            )
        elif cmd == "set-account-password":
            with RunLock(storage.path):
                secret_ref = storage.secret_reference(args.user_id)
                records = [
                    job
                    for job in storage.jobs()
                    if job["user_id"] == args.user_id and job["provider"] == "agnes-api"
                ]
                if any(
                    job["phase"] in {"REGISTRATION_SUBMITTED", "KEY_REQUESTED"} for job in records
                ):
                    raise StorageError("账号已提交；请在 Agnes 正常修改密码后再更新交付资料。")
                password = getpass.getpass("输入 Agnes 密码（输入过程隐藏）：")
                if len(password) < 12:
                    raise StorageError("请使用至少 12 位的 Agnes 密码。")
                record = vault.get(secret_ref)
                if not record:
                    raise StorageError("此用户尚未导入加密凭证。")
                record["agnes_password"] = password
                vault.set(secret_ref, record)
            emit({"user_id": args.user_id, "password_saved": True})
        elif cmd == "export":
            with RunLock(storage.path):
                rows = export_rows(storage, vault, args.batch, args.include_secrets)
                if args.path.suffix.casefold() == ".xlsx":
                    from .excel import write_excel

                    report = write_excel(args.path, rows)
                    report.pop("preview", None)
                elif args.path.suffix.casefold() == ".csv":
                    write_csv(args.path, rows)
                    report = {"output": str(args.path.resolve()), "rows": len(rows)}
                else:
                    raise StorageError("导出文件需要使用 .xlsx 或 .csv 后缀。")
            emit(dict(report, includes_secrets=args.include_secrets))
        elif cmd == "delete-user":
            with RunLock(storage.path):
                secret_ref = storage.secret_reference(args.user_id)
                storage.delete_user(args.user_id)
                vault.delete(secret_ref)
            emit({"user_id": args.user_id, "deleted": True})
        elif cmd == "backup":
            with RunLock(storage.path):
                args.directory.mkdir(parents=True, exist_ok=True)
                with (
                    sqlite3.connect(storage.path) as source,
                    sqlite3.connect(args.directory / "agnes.db") as destination,
                ):
                    source.backup(destination)
                if settings.vault.exists():
                    import shutil

                    shutil.copy2(settings.vault, args.directory / "credentials.dpapi")
            emit({"backup_directory": str(args.directory.resolve())})
        return 0
    except (StorageError, VaultError, MailboxError, OSError, ValueError) as error:
        if isinstance(error, ValidationError):
            print("配置或导入资料无效，请核对字段和授权限制。", file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断。再次运行时会恢复未提交任务，并保留已提交任务供核查。", file=sys.stderr)
        return 130
    finally:
        if storage:
            storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
