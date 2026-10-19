"""Versioned, deliberately small contract for trusted local site scripts."""

from __future__ import annotations

import ast
import importlib.util
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScriptFailure(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ResultField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=80)
    type: Literal["string", "number", "integer", "boolean"] = "string"
    required: bool = False
    sensitive: bool = False


class Requirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mailbox: bool = False
    proxy: bool = False


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_version: Literal[1]
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    site_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,39}$")
    entrypoint: str = Field(default="run", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    resources: Requirements = Field(default_factory=Requirements)
    parameters: dict = Field(default_factory=dict)
    result_fields: list[ResultField] = Field(min_length=1, max_length=40)
    dependencies: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def unique_fields(self):
        if len({f.key for f in self.result_fields}) != len(self.result_fields):
            raise ValueError("结果字段 key 不能重复。")
        return self


def validate_package(package: dict) -> tuple[Manifest, str]:
    try:
        manifest = Manifest.model_validate(package.get("manifest"))
    except ValueError:
        raise ValueError("脚本声明无效：请检查接口版本 1、标识、版本和结果字段。") from None
    source = package.get("source")
    if not isinstance(source, str) or not source.strip() or len(source) > 1_000_000:
        raise ValueError("source 必须是非空 Python 源码，大小不能超过 1MB。")
    try:
        tree = ast.parse(source)
        compile(tree, "<site-script>", "exec")
    except (SyntaxError, ValueError):
        raise ValueError("脚本 Python 语法无效，请让编写脚本的 AI 修正。") from None
    functions = {n.name: n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)}
    for name in [manifest.entrypoint] + (["close"] if "close" in functions else []):
        node = functions.get(name)
        if node is None or len(node.args.args) != 1 or node.args.vararg or node.args.kwonlyargs:
            raise ValueError(f"入口必须声明为 async def {name}(ctx)。")
    if any(isinstance(n, ast.FunctionDef) and n.name == "close" for n in tree.body):
        raise ValueError("清理入口必须是 async def close(ctx)。")
    modules = set(manifest.dependencies)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise ValueError("单文件脚本不支持相对导入。")
            modules.add((node.module or "").split(".")[0])
    for module in modules:
        if not module.isidentifier():
            raise ValueError("dependencies 使用 Python 顶层模块名，不填写 pip 安装表达式。")
        if importlib.util.find_spec(module) is None:
            raise ValueError(f"缺少依赖 {module}，请在当前 Python 环境安装后再导入。")
    return manifest, source


def validate_results(fields: list[dict], values: dict) -> dict:
    if not isinstance(values, dict):
        raise ScriptFailure("INVALID_RESULT", "脚本结果必须是字段对象。")
    declared = {f["key"] for f in fields}
    if set(values) - declared:
        raise ScriptFailure("INVALID_RESULT", "脚本返回了未声明的结果字段。")
    for field in fields:
        key = field["key"]
        value = values.get(key)
        if value is None:
            if field.get("required"):
                raise ScriptFailure("INVALID_RESULT", f"缺少必需结果字段：{key}。")
            continue
        kind = field["type"]
        valid = (
            (kind == "string" and isinstance(value, str))
            or (kind == "boolean" and type(value) is bool)
            or (kind == "integer" and type(value) is int)
            or (kind == "number" and type(value) in (int, float) and math.isfinite(value))
        )
        if not valid:
            raise ScriptFailure("INVALID_RESULT", f"结果字段 {key} 类型应为 {kind}。")
        if isinstance(value, str) and len(value) > 100_000:
            raise ScriptFailure("INVALID_RESULT", f"结果字段 {key} 超过大小限制。")
    return values
