"""LGDF v2.0 工程校验（标准第 10 章）。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .model import AssetMetadata, Info, Registry

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
_TEXT_TYPES = {"text"}


@dataclass
class ValidationIssue:
    code: str
    message: str
    path: Optional[str] = None

    def __str__(self):
        return f"[{self.code}] {self.path or ''} {self.message}".rstrip()


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self):
        return not self.issues

    def add(self, code, message, path=None):
        self.issues.append(ValidationIssue(code, message, path))

    def summary(self):
        if self.ok:
            return "OK（0 个问题）"
        return "\n".join(str(i) for i in self.issues)


def _list_files(root: Path, sub: str):
    base = root / sub
    out = {}
    if not base.is_dir():
        return out
    for p in base.rglob("*"):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = p
    return out


def _check_utf8(path: Path) -> bool:
    """检查文件是否为合法 UTF-8。"""
    try:
        path.read_text(encoding="utf-8")
        return True
    except (UnicodeDecodeError, ValueError):
        return False


def validate_project(root, info: Info, registry: Optional[Registry] = None) -> ValidationReport:
    """全量校验。"""
    root = Path(root)
    rep = ValidationReport()

    # ---- 0. 基本字段
    if info.format != "lgdf":
        rep.add("FORMAT_MISMATCH", f"format 应为 'lgdf'，实际 {info.format!r}", "info.json")
    if not _NAME_RE.match(info.name or ""):
        rep.add("NAME_INVALID", f"name 非法: {info.name!r}", "info.json")
    if info.last_update_time < info.created_time:
        rep.add("TIME_ORDER", "last_update_time 早于 created_time", "info.json")

    # ---- 1. registry.json
    if registry is None:
        reg_path = root / "registry.json"
        if not reg_path.is_file():
            rep.add("MISSING_REGISTRY", "缺少 registry.json", "registry.json")
            return rep
        try:
            registry = Registry.from_dict(json.loads(reg_path.read_text(encoding="utf-8")))
        except (ValueError, json.JSONDecodeError) as e:
            rep.add("BAD_REGISTRY_JSON", f"registry.json 解析失败: {e}", "registry.json")
            return rep

    reg_list = list(registry.registered_files)
    if not isinstance(reg_list, list):
        rep.add("BAD_REGISTRY", "registered_files 不是数组", "registry.json")
        return rep
    if len(set(reg_list)) != len(reg_list):
        rep.add("DUP_REGISTERED", "registered_files 存在重复项", "registry.json")
    for rel in reg_list:
        if not rel.startswith("assets/"):
            rep.add("NOT_UNDER_ASSETS", "注册路径必须位于 assets/ 下", rel)
    if registry.asset_count is not None and registry.asset_count != len(reg_list):
        rep.add("ASSET_COUNT_MISMATCH",
                f"asset_count={registry.asset_count} 与实际 {len(reg_list)} 不一致",
                "registry.json")

    # ---- 2. 枚举实际文件
    asset_files = _list_files(root, "assets")
    meta_files = _list_files(root, "metadata")

    # ---- 3. 注册资源逐项核对
    for rel in reg_list:
        asset_path = asset_files.get(rel)
        if asset_path is None:
            rep.add("MISSING_ASSET", "注册的资源文件不存在", rel)
            continue
        meta_rel = "metadata/" + rel[len("assets/"):] + ".json"
        meta_path = meta_files.get(meta_rel)
        if meta_path is None:
            rep.add("NO_METADATA", "缺少元数据文件", rel)
            continue
        try:
            meta = AssetMetadata.from_dict(json.loads(meta_path.read_text(encoding="utf-8")))
        except (ValueError, json.JSONDecodeError) as e:
            rep.add("BAD_METADATA_JSON", f"元数据 JSON 解析失败: {e}", meta_rel)
            continue
        if meta.path != rel:
            rep.add("PATH_FIELD_MISMATCH",
                    f"元数据 path={meta.path!r} 与注册路径 {rel!r} 不一致", meta_rel)
        blob = asset_path.read_bytes()
        real_hash = hashlib.sha256(blob).hexdigest()
        if not _SHA256_RE.match(meta.sha256 or ""):
            rep.add("BAD_SHA256_FORMAT", "sha256 字段不是 64 位小写十六进制", meta_rel)
        elif real_hash != meta.sha256:
            rep.add("HASH_MISMATCH", f"实际哈希 {real_hash[:12]}… 与元数据不符", rel)
        if len(blob) != meta.size:
            rep.add("SIZE_MISMATCH", f"实际大小 {len(blob)} 与元数据 size={meta.size} 不符", rel)

        # ---- 3b. 文本类型 UTF-8 校验
        if meta.type in _TEXT_TYPES:
            if not _check_utf8(asset_path):
                rep.add("INVALID_UTF8", f"文本类型资源不是合法 UTF-8: {rel}", rel)

    # ---- 4. 双向镜像
    for rel in asset_files:
        if rel not in reg_list:
            rep.add("UNREGISTERED_ASSET", "游离资源：存在但未注册", rel)
        meta_rel = "metadata/" + rel[len("assets/"):] + ".json"
        if meta_rel not in meta_files:
            rep.add("NO_METADATA", "资源缺少对应元数据", rel)
    for mrel in meta_files:
        asset_rel = "assets/" + mrel[len("metadata/"):-len(".json")]
        if asset_rel not in asset_files:
            rep.add("ORPHAN_METADATA", "孤儿元数据：无对应资源", mrel)

    return rep
