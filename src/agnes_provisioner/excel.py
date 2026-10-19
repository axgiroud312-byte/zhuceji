from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .storage import StorageError


def write_excel(path: Path, rows: list[dict]) -> dict:
    if not rows:
        raise StorageError("没有可导出的任务，请先创建批次。")
    bundle = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node"
    executable = bundle / "bin/node.exe"
    packages = bundle / "node_modules"
    root = Path(__file__).resolve().parents[2]
    builder = root / "tools/export_workbook.mjs"
    link = builder.parent / "node_modules"
    if not executable.exists() or not (packages / "@oai/artifact-tool").exists():
        raise StorageError("缺少 Codex 本地 Excel 运行库，请在 Codex 中加载工作区依赖。")
    if not link.exists():
        env = dict(os.environ, AGNES_ARTIFACT_LINK=str(link), AGNES_ARTIFACT_PACKAGES=str(packages))
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "New-Item -ItemType Junction -Path $env:AGNES_ARTIFACT_LINK "
                "-Target $env:AGNES_ARTIFACT_PACKAGES | Out-Null",
            ],
            env=env,
            capture_output=True,
            check=True,
        )
    elif link.resolve() != packages.resolve():
        raise StorageError("Excel 依赖目录与 Codex 运行库不匹配，请检查 tools/node_modules。")
    payload = {
        "rows": rows,
        "exported_date": datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
    }
    started_at_ns = time.time_ns()
    process = subprocess.run(
        [str(executable), str(builder), str(path.resolve())],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    if process.returncode:
        raise StorageError("Excel 导出未完成，请检查本地 Excel 运行库；可先导出 CSV 保留结果。")
    if not path.exists() or not path.stat().st_size or path.stat().st_mtime_ns < started_at_ns:
        raise StorageError("Excel 导出没有产生文件，请检查本地运行库。")
    return {
        "output": str(path.resolve()),
        "rows": len(rows),
        "keys": sum(bool(row["API Key"]) for row in rows),
    }
