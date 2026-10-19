from __future__ import annotations

import os
from pathlib import Path

from .storage import StorageError


class RunLock:
    """同一数据库只允许一个调度器；进程退出时操作系统自动释放。"""

    def __init__(self, database: Path):
        self.path = database.with_suffix(database.suffix + ".lock")
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            self.handle = None
            raise StorageError(
                "此数据库已有调度器运行。请通过 pause、resume 或 stop 控制它。"
            ) from error
        return self

    def __exit__(self, *_):
        if self.handle:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()
