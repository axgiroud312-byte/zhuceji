"""Small OOXML writer: strings stay literal and the finished ZIP is read back exactly."""

from __future__ import annotations

import os
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from .bulk_store import BulkStore
from .storage import StorageError
from .vault import Vault

FIELDS = ("邮箱账号", "邮箱密码", "Agnes 登录密码", "API Key", "结果", "失败/跳过原因", "用户 ID")
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REASONS = {
    "MAILBOX_TOKEN_INVALID": "邮箱登录令牌已失效，未提交注册",
    "MAILBOX_NETWORK": "邮箱连接失败，退避后仍无法连接，未提交注册",
    "VERIFY_TIMEOUT": "验证码未收到，未提交注册；不重发",
    "SOURCE_INVALID_FIELDS": "源行字段缺失或格式无效",
    "SOURCE_DUPLICATE_EMAIL": "源清单重复邮箱，未重复注册",
}


def export_rows(bulk: BulkStore, records):
    rows = []
    ctl = bulk.control()
    for row in bulk.rows():
        record = records.get(row["secret_ref"], {})
        if bulk.confirmed(row, record):
            result, reason = "已完成", ""
        elif row["reason"] or row["state"] == "SKIPPED":
            result = "已跳过"
            code = row["reason"] or row["error_code"]
            reason = REASONS.get(code, row["message"] or code)
        elif row["state"] in ("PENDING", "RETRY_WAIT"):
            result = "未处理"
            reason = "等待执行；" + (ctl["reason"] or "尚未到达")
        else:
            result = "待核查"
            reason = row["message"] or row["error_code"] or "身份、完整密钥或认证尚未全部确认"
        rows.append(
            [
                row["email"],
                record.get("mailbox_password", ""),
                record.get("agnes_password", "")
                if record.get("activated") or row["submitted_at"]
                else "",
                record.get("api_key", ""),
                result,
                reason,
                row["user_id"] or "源行 " + str(row["line"]),
            ]
        )
    keys = [r[3] for r in rows if r[3]]
    if len(keys) != len(set(keys)):
        raise StorageError("EXPORT_DUPLICATE_KEYS")
    return rows


def sheet_xml(rows, widths):
    def cell(column, number, value, header=False):
        address = chr(65 + column) + str(number)
        text = escape(str(value))
        return (
            f'<c r="{address}" t="inlineStr" s="{1 if header else 0}">'
            f'<is><t xml:space="preserve">{text}</t></is></c>'
        )

    data = "".join(
        f'<row r="{i}" ht="30" customHeight="1">'
        + "".join(cell(c, i, v, i == 1) for c, v in enumerate(row))
        + "</row>"
        for i, row in enumerate(rows, 1)
    )
    cols = "".join(
        f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, 1)
    )
    end = chr(64 + len(widths)) + str(len(rows))
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{NS}">'
        f'<dimension ref="A1:{end}"/><sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        f"</sheetView></sheetViews><cols>{cols}</cols><sheetData>{data}</sheetData>"
        f'<autoFilter ref="A1:{end}"/></worksheet>'
    )


def verify_workbook(path: Path, expected: dict, records: dict):
    ns = {"s": NS}
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise StorageError("EXPORT_ZIP_INVALID")
        for index, (_, rows) in enumerate(expected.items(), 1):
            xml = ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
            actual = []
            for row in xml.findall("s:sheetData/s:row", ns):
                values = []
                for cell in row.findall("s:c", ns):
                    if cell.find("s:f", ns) is not None:
                        raise StorageError("EXPORT_UNEXPECTED_FORMULA")
                    values.append("".join(cell.find("s:is", ns).itertext()))
                actual.append(values)
            if actual != [[str(value) for value in row] for row in rows]:
                raise StorageError("EXPORT_EXACT_READBACK_MISMATCH")
        contents = "\n".join(archive.read(p).decode("utf-8") for p in archive.namelist())
        for record in records.values():
            for field in ("client_id", "refresh_token"):
                value = record.get(field)
                if value and escape(value) in contents:
                    raise StorageError("EXPORT_OAUTH_LEAK")


def write_bulk_excel(path: Path, bulk: BulkStore, vault: Vault):
    records = vault.snapshot()
    rows = export_rows(bulk, records)
    counts = Counter(r[4] for r in rows)
    ctl = bulk.control()
    when = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    sheets = {
        "汇总": [
            ["项目", "实际值"],
            ["导出时间（北京时间）", when],
            ["源邮箱记录", len(rows)],
            ["已完成", counts["已完成"]],
            ["已跳过", counts["已跳过"]],
            ["待核查", counts["待核查"]],
            ["未处理", counts["未处理"]],
            [
                "交付状态",
                "全部有结论" if not counts["待核查"] and not counts["未处理"] else "部分完成",
            ],
            ["生产累计代理字节", ctl["used_bytes"]],
            ["暂停原因", ctl["reason"]],
        ],
        "已完成账号": [list(FIELDS)] + [r for r in rows if r[4] == "已完成"],
        "未完成记录": [list(FIELDS)] + [r for r in rows if r[4] != "已完成"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.xlsx")
    relationships = "http://schemas.openxmlformats.org/package/2006/relationships"
    docrel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    types = "http://schemas.openxmlformats.org/package/2006/content-types"
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            content = "application/vnd.openxmlformats-officedocument.spreadsheetml."
            overrides = (
                f'<Override PartName="/xl/workbook.xml" ContentType="{content}sheet.main+xml"/>'
            )
            overrides += f'<Override PartName="/xl/styles.xml" ContentType="{content}styles+xml"/>'
            for i in range(1, len(sheets) + 1):
                overrides += (
                    f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                    f'ContentType="{content}worksheet+xml"/>'
                )
            archive.writestr(
                "[Content_Types].xml",
                f'<Types xmlns="{types}"><Default Extension="rels" '
                'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                f"{overrides}</Types>",
            )
            archive.writestr(
                "_rels/.rels",
                f'<Relationships xmlns="{relationships}"><Relationship Id="rId1" '
                f'Type="{docrel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
            )
            names = "".join(
                f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
                for i, name in enumerate(sheets, 1)
            )
            archive.writestr(
                "xl/workbook.xml",
                f'<workbook xmlns="{NS}" xmlns:r="{docrel}"><sheets>{names}</sheets></workbook>',
            )
            links = "".join(
                f'<Relationship Id="rId{i}" Type="{docrel}/worksheet" '
                f'Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            links += f'<Relationship Id="styles" Type="{docrel}/styles" Target="styles.xml"/>'
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                f'<Relationships xmlns="{relationships}">{links}</Relationships>',
            )
            archive.writestr(
                "xl/styles.xml",
                f'''<styleSheet xmlns="{NS}">
                <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>
                <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>
                <fills count="3"><fill><patternFill patternType="none"/></fill>
                <fill><patternFill patternType="gray125"/></fill>
                <fill><patternFill patternType="solid"><fgColor rgb="FF253858"/>
                </patternFill></fill></fills>
                <borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>
                <cellXfs count="2">
                <xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">
                <alignment vertical="center" wrapText="1"/></xf>
                <xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1">
                <alignment vertical="center"/></xf></cellXfs>
                <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>
                </cellStyles></styleSheet>''',
            )
            for i, (_, values) in enumerate(sheets.items(), 1):
                archive.writestr(
                    f"xl/worksheets/sheet{i}.xml",
                    sheet_xml(values, [32, 60] if i == 1 else [42, 24, 38, 62, 18, 65, 28]),
                )
        verify_workbook(temporary, sheets, records)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "output": str(path.resolve()),
        "rows": len(rows),
        "states": dict(counts),
        "unique_keys": sum(bool(r[3]) for r in rows),
        "exact_readback": True,
        "oauth_credentials_absent": True,
    }
