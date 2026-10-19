from __future__ import annotations

import csv
import hashlib
import io
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, model_validator
from sqlalchemy import select

from .models import Job, User
from .storage import Storage, StorageError
from .vault import Vault


class UserInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_id: str = Field(min_length=1, max_length=80, pattern=r"^[\w.-]+$")
    email: EmailStr
    consent: bool
    consent_reference: str = Field(min_length=1, max_length=256)
    display_name: str = Field(default="", max_length=120)
    mailbox_authorized: bool = False
    secret_ref: str = Field(default="", max_length=120, pattern=r"^[\w.-]*$")

    @model_validator(mode="after")
    def authorized(self):
        if not self.consent:
            raise ValueError("缺少用户开户授权")
        return self


def import_users(storage: Storage, path: Path) -> dict:
    report = {"imported": 0, "duplicates": 0, "rejected": 0, "errors": []}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        required = {"user_id", "email", "consent", "consent_reference"}
        if len(fields) != len(set(fields)) or not required.issubset(fields):
            raise StorageError(
                "CSV 需要 user_id、email、consent、consent_reference 且列名不能重复。"
            )
        if set(fields) - set(UserInput.model_fields):
            raise StorageError("CSV 存在未知列。密码和令牌应导入加密凭证库。")
        with storage.session.begin() as session:
            for number, row in enumerate(reader, 2):
                try:
                    data = UserInput.model_validate(row)
                except ValidationError as error:
                    report["rejected"] += 1
                    rejected_fields = sorted(
                        {
                            str(e["loc"][0]) if e["loc"] else "consent"
                            for e in error.errors(include_input=False)
                        }
                    )
                    report["errors"].append({"row": number, "fields": rejected_fields})
                    continue
                email = str(data.email).casefold()
                existing = session.get(User, data.user_id)
                other = session.scalar(select(User).where(User.email == email))
                if existing or other:
                    if existing and existing.email == email:
                        report["duplicates"] += 1
                    else:
                        report["rejected"] += 1
                        report["errors"].append(
                            {
                                "row": number,
                                "fields": ["user_id", "email"],
                                "reason": "重复标识或邮箱冲突",
                            }
                        )
                    continue
                session.add(
                    User(
                        id=data.user_id,
                        email=email,
                        consent=data.consent,
                        consent_reference=data.consent_reference,
                        display_name=data.display_name,
                        mailbox_authorized=data.mailbox_authorized,
                        secret_ref=data.secret_ref or data.user_id,
                        created_at=time.time(),
                    )
                )
                session.flush()
                report["imported"] += 1
    return report


def _split_account_line(line: str, delimiter: str) -> list[str]:
    if delimiter and delimiter != "auto":
        sep = "\t" if delimiter in ("\\t", "tab", "TAB") else delimiter
        return [p.strip() for p in line.split(sep)]
    for candidate in ("----", "\t", "|", ";", ",", ":"):
        if candidate in line:
            return [p.strip() for p in line.split(candidate)]
    return [line.strip()]


def parse_accounts_text(
    text: str, *, format_hint: str = "auto", delimiter: str = "auto", password_role: str = "both"
) -> list[dict]:
    """Parse without side effects; errors never contain the source credentials."""
    if format_hint not in {"auto", "four_part", "three_part", "two_part", "email_only", "csv"}:
        raise StorageError("不支持的账号格式。")
    if password_role not in {"both", "agnes_only", "mailbox_only"}:
        raise StorageError("不支持的密码用途。")
    raw = text.lstrip("\ufeff")
    first = next((s.strip() for s in raw.splitlines() if s.strip()), "")
    csv_mode = format_hint == "csv" or (
        format_hint == "auto" and "email" in [v.strip().strip('"') for v in first.split(",")]
    )
    records: list[tuple[int, dict | list]] = []
    if csv_mode:
        reader = csv.reader(io.StringIO(raw), strict=True)
        try:
            fields = []
            while not fields:
                values = next(reader, None)
                if values is None:
                    break
                if any(v.strip() for v in values):
                    fields = [s.strip() for s in values]
            allowed = set(UserInput.model_fields) | {
                "mailbox_password", "agnes_password", "password", "client_id", "refresh_token"
            }
            if "email" not in fields or len(fields) != len(set(fields)) or set(fields) - allowed:
                raise StorageError("CSV 需要唯一的 email 列；请检查是否有重复或未知列名。")
            while True:
                number = reader.line_num + 1
                values = next(reader, None)
                if values is None:
                    break
                if not values or not any(values):
                    continue
                records.append((number, dict(zip(fields, values)) if len(values) == len(fields)
                                else {"_error": "CSV 列数与表头不一致"}))
        except csv.Error as error:
            raise StorageError(f"CSV 第 {reader.line_num} 行引号或分列格式不正确。") from error
    else:
        for number, source in enumerate(raw.splitlines(), 1):
            line = source.strip()
            if line and not line.startswith("#") and line not in ("卡密导出", "email"):
                records.append((number, _split_account_line(line, delimiter)))

    result = []
    for number, values in records:
        row = dict(row=number, email="", mailbox_password="", agnes_password="",
                   client_id="", refresh_token="", kind="CSV" if csv_mode else "", error="")
        if isinstance(values, dict):
            row.update({k: str(values.get(k) or "").strip() for k in (
                "email", "mailbox_password", "agnes_password", "client_id", "refresh_token"
            )})
            password = str(values.get("password") or "").strip()
            row["user_id"] = str(values.get("user_id") or "").strip()
            row["error"] = values.get("_error", "")
            if values.get("consent", "true").strip().lower() not in {"true", "1", "yes"}:
                row["error"] = "缺少用户开户授权"
        else:
            count = len(values)
            row["email"] = values[0]
            row["kind"] = {1: "纯邮箱", 2: "两段式账密", 3: "三段式双密码",
                           4: "四段式OAuth", 5: "五段式全凭证"}.get(count, "格式错误")
            expected = {"four_part": 4, "three_part": 3, "two_part": 2, "email_only": 1}
            if count > 5 or (format_hint in expected and count != expected[format_hint]):
                row["error"] = "字段数量与所选格式不一致（支持 1 至 5 段）"
            password = values[1] if count == 2 else ""
            if count == 3:
                row["mailbox_password"], row["agnes_password"] = values[1:3]
            elif count == 4:
                row["mailbox_password"], row["client_id"], row["refresh_token"] = values[1:4]
            elif count == 5:
                for key, value in zip(
                    ("mailbox_password", "agnes_password", "client_id", "refresh_token"), values[1:]
                ):
                    row[key] = value
        if password:
            if password_role in {"both", "mailbox_only"}:
                row["mailbox_password"] = row["mailbox_password"] or password
            if password_role in {"both", "agnes_only"}:
                row["agnes_password"] = row["agnes_password"] or password
        if bool(row["client_id"]) != bool(row["refresh_token"]) or (
            row["kind"] in {"四段式OAuth", "五段式全凭证"}
            and not (row["client_id"] and row["refresh_token"])
        ):
            row["error"] = "OAuth ClientID 与 RefreshToken 需要同时提供"
        try:
            uid = row.get("user_id") or (
                "mail-" + hashlib.sha256(row["email"].casefold().encode()).hexdigest()[:16]
            )
            data = UserInput(user_id=uid, email=row["email"], consent=True,
                             consent_reference="解析校验")
            row["email"] = str(data.email).casefold()
            row["user_id"] = uid
        except ValidationError:
            row["error"] = "未识别到有效邮箱地址或用户ID格式错误"
        result.append(row)
    return result


def import_accounts_flexible(
    storage: Storage,
    vault: Vault,
    text: str,
    *,
    format_hint: Literal[
        "auto", "four_part", "three_part", "two_part", "email_only", "csv"
    ] = "auto",
    delimiter: str = "auto",
    password_role: Literal["both", "agnes_only", "mailbox_only"] = "both",
    mailbox_transport: Literal["graph", "imap", "imap_password"] = "graph",
    consent_reference: str = "批量导入授权",
    batch_id: str | None = None,
    provider: str = "agnes-api",
    import_mode: Literal["register", "existing_login"] = "register",
    update_existing: bool = True,
) -> dict:
    if not text.strip():
        raise StorageError("导入内容不能为空。")
    if import_mode not in {"register", "existing_login"}:
        raise StorageError("不支持的账号执行模式。")
    if batch_id and (not batch_id.strip() or len(batch_id.strip()) > 80):
        raise StorageError("批次名称应为 1 至 80 个字符。")
    if batch_id and any(b["id"] == batch_id.strip() and b["provider"] != provider
                        for b in storage.batches()):
        raise StorageError("此批次属于另一个执行模式，请使用新的批次名称。")

    report = {
        "imported": 0,
        "updated": 0,
        "duplicates": 0,
        "rejected": 0,
        "errors": [],
        "user_ids": [],
        "batch": None,
    }

    parsed_entries = []
    for row in parse_accounts_text(
        text, format_hint=format_hint, delimiter=delimiter, password_role=password_role
    ):
        line_no = row["row"]
        if row["error"]:
            report["rejected"] += 1
            report["errors"].append({"row": line_no, "reason": row["error"]})
            continue
        mailbox_password, agnes_password, client_id, refresh_token = (
            row[k] for k in ("mailbox_password", "agnes_password", "client_id", "refresh_token")
        )
        uid = row["user_id"]
        try:
            validated = UserInput(
                user_id=uid,
                email=row["email"],
                consent=True,
                consent_reference=consent_reference or "批量导入授权",
                mailbox_authorized=bool((client_id and refresh_token) or mailbox_password),
                secret_ref=uid,
            )
        except ValidationError:
            report["rejected"] += 1
            report["errors"].append({"row": line_no, "reason": "邮箱格式校验未通过"})
            continue

        parsed_entries.append(
            (validated, mailbox_password, agnes_password, client_id, refresh_token, line_no)
        )

    vault_updates: dict[str, dict] = {}
    with storage.session.begin() as session:
        for data, mb_pwd, ag_pwd, cid, rtoken, line_no in parsed_entries:
            email_norm = str(data.email).casefold()
            existing = session.scalar(select(User).where(User.email == email_norm))
            id_owner = session.get(User, data.user_id)
            if id_owner and id_owner.email != email_norm:
                report["rejected"] += 1
                report["errors"].append({"row": line_no, "reason": "用户ID已被其他邮箱使用"})
                continue
            existing_ref = (existing.secret_ref or existing.id) if existing else data.user_id
            if import_mode == "existing_login" and not (
                ag_pwd or (vault_updates.get(existing_ref) or vault.get(existing_ref)).get(
                    "agnes_password"
                )
            ):
                report["rejected"] += 1
                report["errors"].append({"row": line_no, "reason": "已有账号需要平台登录密码"})
                continue
            if existing:
                user_id = existing.id
                secret_ref = existing.secret_ref or existing.id
                if update_existing:
                    if data.mailbox_authorized:
                        existing.mailbox_authorized = True
                    report["updated"] += 1
                else:
                    report["duplicates"] += 1
                    report["user_ids"].append(user_id)
                    continue
            else:
                user_id = data.user_id
                secret_ref = data.secret_ref or data.user_id
                session.add(
                    User(
                        id=user_id,
                        email=email_norm,
                        consent=True,
                        consent_reference=data.consent_reference,
                        display_name=data.display_name,
                        mailbox_authorized=data.mailbox_authorized,
                        secret_ref=secret_ref,
                        created_at=time.time(),
                    )
                )
                session.flush()
                report["imported"] += 1

            report["user_ids"].append(user_id)
            rec = (vault_updates.get(secret_ref) or vault.get(secret_ref)).copy()
            rec["email"] = email_norm
            if mb_pwd:
                rec["mailbox_password"] = mb_pwd
            if ag_pwd:
                rec["agnes_password"] = ag_pwd
            if cid:
                rec["client_id"] = cid
            if rtoken:
                rec["refresh_token"] = rtoken
            if (cid and rtoken) or mb_pwd:
                rec["mailbox_authorized"] = True
                if cid and rtoken:
                    rec["mailbox_transport"] = (
                        mailbox_transport if mailbox_transport in ("graph", "imap") else "graph"
                    )
                else:
                    rec["mailbox_transport"] = "imap_password"
            else:
                rec.setdefault("mailbox_authorized", False)
            vault_updates[secret_ref] = rec

    if vault_updates:
        vault.set_many(vault_updates)
        for ref in vault_updates:
            vault.ensure_account_password(ref)

    if batch_id and report["user_ids"]:
        batch_info = storage.create_batch(batch_id.strip(), provider, report["user_ids"])
        if import_mode == "existing_login":
            with storage.session.begin() as session:
                jobs = list(
                    session.scalars(
                        select(Job).where(
                            Job.batch_id == batch_id.strip(),
                            Job.user_id.in_(report["user_ids"]),
                        )
                    )
                )
                for j in jobs:
                    if j.state == "PENDING":
                        old = j.state
                        j.state = "PENDING_VERIFY"
                        j.phase = "REGISTRATION_SUBMITTED"
                        j.submitted_at = j.submitted_at or time.time()
                        j.error_code = "EXISTING_ACCOUNT_IMPORT"
                        j.message = "已有账号导入，等待登录核验与提取结果"
                        storage._event(session, j, old, j.error_code, j.message)
        report["batch"] = batch_info

    return report
