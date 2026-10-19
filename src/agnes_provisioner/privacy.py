from __future__ import annotations

import re


def mask_email(value: str) -> str:
    name, _, domain = value.partition("@")
    return (name[:1] + "***@" + domain) if domain else "***"


def redact(value: str) -> str:
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", lambda m: mask_email(m[0]), value)
    value = re.sub(r"(?i)(?:sk-|M\.C)[^\s\"']+", "[凭证已隐藏]", value)
    value = re.sub(r"(?i)(https?://)[^\s/@]+:[^\s/@]+@", r"\1[凭证已隐藏]@", value)
    return value


def safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
