"""Windows 当前用户 DPAPI；明文只在调用期间进入内存。"""

from __future__ import annotations

import ctypes
import json
import os
import secrets
import threading
from ctypes import wintypes
from pathlib import Path


class VaultError(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def _transform(value: bytes, encrypt: bool) -> bytes:
    if os.name != "nt":
        raise VaultError("本地凭证库需要 Windows DPAPI；其他系统请使用环境变量。")
    buffer = ctypes.create_string_buffer(value)
    source = _Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = _Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    if encrypt:
        function = crypt.CryptProtectData
        function.argtypes = [
            ctypes.POINTER(_Blob),
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_Blob),
        ]
        ok = function(
            ctypes.byref(source), "Agnes credentials", None, None, None, 1, ctypes.byref(target)
        )
    else:
        function = crypt.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(_Blob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_Blob),
        ]
        ok = function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    function.restype = wintypes.BOOL
    if not ok:
        raise VaultError("无法访问加密凭证；请使用保存凭证时的 Windows 用户。")
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class Vault:
    _locks: dict[str, threading.RLock] = {}

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = self._locks.setdefault(str(self.path.resolve()), threading.RLock())

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(_transform(self.path.read_bytes(), False))
        except (OSError, ValueError) as error:
            raise VaultError("本地凭证文件损坏或不可读取。") from error

    def _write(self, values: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        payload = json.dumps(values, ensure_ascii=False).encode("utf-8")
        temporary.write_bytes(_transform(payload, True))
        os.replace(temporary, self.path)

    def get(self, key: str) -> dict:
        return self._read().get(key, {}).copy()

    def set(self, key: str, value: dict) -> None:
        with self.lock:
            values = self._read()
            values[key] = value
            self._write(values)

    def delete(self, key: str) -> None:
        with self.lock:
            values = self._read()
            values.pop(key, None)
            self._write(values)

    def keys(self) -> list[str]:
        return list(self._read())

    def snapshot(self) -> dict:
        """Only for in-memory migration/export under the database process lock."""
        with self.lock:
            return self._read()

    def set_many(self, records: dict[str, dict]) -> None:
        with self.lock:
            values = self._read()
            values.update(records)
            self._write(values)

    def ensure_account_password(self, key: str) -> str:
        record = self.get(key)
        if not record.get("agnes_password"):
            record["agnes_password"] = "Aa9!" + secrets.token_urlsafe(20)
            self.set(key, record)
        return record["agnes_password"]
