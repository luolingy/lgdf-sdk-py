"""LGDF v1.0.1 工程对象：创建 / 读取 / 修改 / 导出 / 导入。

用法::

    from lgdf import LgdfProject

    # 创建
    p = LgdfProject.create("demo", "./demo", author="me")
    p.add_asset("images/a.png", source="./a.png", properties={"width": 1})
    p.set_steps([{"id": "s1", "name": "导入"}])
    p.save()

    # 读取
    p = LgdfProject.open("./demo")
    meta = p.get_metadata("images/a.png")
    data = p.read_asset("images/a.png")

    # 导出
    path, sha = p.export("./dist/demo.lgdf")

    # 导入
    p2 = LgdfProject.import_from("./dist/demo.lgdf", "./restored")
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple

from .exceptions import (
    AssetNotFoundError,
    DuplicateAssetError,
    InvalidProjectError,
    LgdfError,
    ReadOnlyError,
    ValidationError,
)
from .mime import format_of, guess_mime, guess_type
from .model import AssetMetadata, AuthorSign, Info, Registry
from .validate import ValidationReport, validate_project

SDK_VERSION = 1
_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
_EXPORT_ENTRY_PREFIXES = ("assets/", "metadata/", "spec/")
_IMPORTABLE_ROOT_FILES = {"info.json", "registry.json"}


def _now() -> int:
    return int(time.time())


def _dumps(d) -> str:
    return json.dumps(d, ensure_ascii=False, indent="\t") + "\n"


def _norm_rel(rel: str) -> str:
    rel = rel.replace("\\", "/").lstrip("/")
    parts = PurePosixPath(rel).parts
    if any(p == ".." for p in parts):
        raise LgdfError(f"非法路径（含 '..'）: {rel!r}")
    return PurePosixPath(*parts).as_posix() if parts else ""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_info(root: Path) -> Info:
    p = root / "info.json"
    if not p.is_file():
        raise InvalidProjectError(f"缺少 info.json: {root}")
    try:
        return Info.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        raise InvalidProjectError(f"info.json 解析失败: {e}") from e


def _read_registry(root: Path) -> Registry:
    p = root / "registry.json"
    if not p.is_file():
        raise InvalidProjectError(f"缺少 registry.json: {root}")
    try:
        return Registry.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        raise InvalidProjectError(f"registry.json 解析失败: {e}") from e


def _check_info(info: Info):
    if info.format != "lgdf":
        raise InvalidProjectError(f"format 应为 'lgdf'，实际 {info.format!r}")
    if info.min_sdk > SDK_VERSION:
        raise InvalidProjectError(
            f"工程要求 min_sdk={info.min_sdk}，本 SDK 版本为 {SDK_VERSION}")


class LgdfProject:
    """LGDF 工程（始终为目录模式）。"""

    sdk_version = SDK_VERSION

    def __init__(self, root: Path, info: Info, registry: Registry):
        self.root = Path(root)
        self.info = info
        self.registry = registry

    # ---------------------------------------------------------------- 生命周期

    @classmethod
    def create(cls, name: str, path, *, author=None, description="",
               license=None, tags=None, display_name=None) -> "LgdfProject":
        if not _NAME_RE.match(name or ""):
            raise InvalidProjectError(f"name 非法: {name!r}")
        root = Path(path)
        if root.exists() and any(root.iterdir()):
            raise LgdfError(f"目标目录非空: {root}")
        now = _now()
        info = Info(
            name=name, display_name=display_name, description=description,
            author=author, license=license, tags=list(tags or []),
            created_time=now, last_update_time=now, version=1,
        )
        registry = Registry()
        proj = cls(root, info, registry)
        for d in ("assets", "metadata", "spec"):
            (root / d).mkdir(parents=True, exist_ok=True)
        proj._write_info()
        proj._write_registry()
        return proj

    @classmethod
    def open(cls, source) -> "LgdfProject":
        source = Path(source)
        if not source.is_dir():
            raise InvalidProjectError(f"不是目录: {source}")
        info = _read_info(source)
        _check_info(info)
        registry = _read_registry(source)
        return cls(source, info, registry)

    # ---------------------------------------------------------------- 路径工具

    def _fs(self, rel: str) -> Path:
        return self.root / Path(*rel.split("/"))

    @staticmethod
    def _asset_rel(rel: str) -> str:
        rel = _norm_rel(rel)
        if not rel.startswith("assets/"):
            rel = "assets/" + rel
        return rel

    @staticmethod
    def _meta_rel(asset_rel: str) -> str:
        return "metadata/" + asset_rel[len("assets/"):] + ".json"

    def _write_info(self):
        self._fs("info.json").write_text(
            _dumps(self.info.to_dict()), encoding="utf-8")

    def _write_registry(self):
        self._fs("registry.json").write_text(
            _dumps(self.registry.to_dict()), encoding="utf-8")

    def save(self):
        self.info.last_update_time = _now()
        self.registry.registered_files = sorted(set(self.registry.registered_files))
        self.registry.asset_count = len(self.registry.registered_files)
        self._write_info()
        self._write_registry()

    # ---------------------------------------------------------------- 资源操作

    @staticmethod
    def _load_bytes(source, data) -> bytes:
        if data is not None:
            return bytes(data)
        if source is None:
            raise LgdfError("需要提供 source 或 data")
        return Path(source).read_bytes()

    def add_asset(self, rel_path: str, source=None, data=None, *,
                  properties=None, extra=None) -> AssetMetadata:
        rel = self._asset_rel(rel_path)
        if rel in self.registry.registered_files:
            raise DuplicateAssetError(f"资源已注册: {rel}")
        blob = self._load_bytes(source, data)
        dest = self._fs(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        now = _now()
        meta = AssetMetadata(
            path=rel, type=guess_type(rel), mime=guess_mime(rel),
            format=format_of(rel), size=len(blob),
            sha256=hashlib.sha256(blob).hexdigest(),
            created_time=now, last_update_time=now,
            properties=dict(properties or {}), extra=dict(extra or {}),
        )
        self._write_metadata(meta)
        self.registry.registered_files.append(rel)
        self.save()
        return meta

    def replace_asset(self, rel_path: str, source=None, data=None, *,
                      properties=None) -> AssetMetadata:
        rel = self._asset_rel(rel_path)
        if rel not in self.registry.registered_files:
            raise AssetNotFoundError(f"资源未注册: {rel}")
        blob = self._load_bytes(source, data)
        self._fs(rel).write_bytes(blob)
        meta = self.get_metadata(rel)
        meta.size = len(blob)
        meta.sha256 = hashlib.sha256(blob).hexdigest()
        meta.last_update_time = _now()
        if properties:
            meta.properties.update(properties)
        self._write_metadata(meta)
        self.save()
        return meta

    def remove_asset(self, rel_path: str):
        rel = self._asset_rel(rel_path)
        if rel not in self.registry.registered_files:
            raise AssetNotFoundError(f"资源未注册: {rel}")
        self.registry.registered_files.remove(rel)
        self._fs(rel).unlink()
        self._fs(self._meta_rel(rel)).unlink()
        for base, sub in ((self.root / "assets", rel[len("assets/"):]),
                          (self.root / "metadata", self._meta_rel(rel)[len("metadata/"):])):
            d = (base / PurePosixPath(sub).parent).resolve()
            while d != base.resolve() and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
        self.save()

    def read_asset(self, rel_path: str) -> bytes:
        rel = self._asset_rel(rel_path)
        p = self._fs(rel)
        if not p.is_file():
            raise AssetNotFoundError(f"资源不存在: {rel}")
        return p.read_bytes()

    def _write_metadata(self, meta: AssetMetadata):
        p = self._fs(self._meta_rel(meta.path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_dumps(meta.to_dict()), encoding="utf-8")

    def get_metadata(self, rel_path: str) -> AssetMetadata:
        rel = self._asset_rel(rel_path)
        p = self._fs(self._meta_rel(rel))
        if not p.is_file():
            raise AssetNotFoundError(f"元数据不存在: {rel}")
        return AssetMetadata.from_dict(json.loads(p.read_text(encoding="utf-8")))

    # ---------------------------------------------------------------- 描述层

    def write_spec_file(self, name: str, text: str):
        rel = "spec/" + _norm_rel(name)
        p = self._fs(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def read_spec_file(self, name: str) -> str:
        return self._fs("spec/" + _norm_rel(name)).read_text(encoding="utf-8")

    def set_config(self, cfg: Dict):
        self._validate_config_against_schema(cfg)
        self._fs("spec").mkdir(parents=True, exist_ok=True)
        self._fs("spec/config.json").write_text(_dumps(cfg), encoding="utf-8")

    def _validate_config_against_schema(self, cfg):
        schema_path = self._fs("spec/config.schema.json")
        if not schema_path.is_file():
            return
        try:
            import jsonschema
        except ImportError:
            return
        jsonschema.validate(cfg, json.loads(schema_path.read_text(encoding="utf-8")))

    def get_config(self) -> Dict:
        p = self._fs("spec/config.json")
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}

    def write_config_schema(self, schema: Dict):
        self._fs("spec").mkdir(parents=True, exist_ok=True)
        self._fs("spec/config.schema.json").write_text(_dumps(schema), encoding="utf-8")

    def set_steps(self, steps: List[Dict], title: str = "制作步骤"):
        for s in steps:
            if not isinstance(s, dict) or not s.get("id") or not s.get("name"):
                raise ValueError("每个步骤必须包含 id 与 name")
        self._fs("spec").mkdir(parents=True, exist_ok=True)
        self._fs("spec/steps.json").write_text(
            _dumps({"title": title, "steps": steps}), encoding="utf-8")

    def get_steps(self) -> Dict:
        p = self._fs("spec/steps.json")
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"title": "", "steps": []}

    def set_overview(self, markdown: str):
        self.write_spec_file("overview.md", markdown)

    # ---------------------------------------------------------------- 签名

    def sign(self, private_key_path: str, algorithm: str = "RSA-SHA256"):
        """用私钥对工程关键字段签名，写入 info.json.author_sign。

        需要 cryptography 库：pip install cryptography
        """
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

        sign_obj = self._build_sign_object()
        payload = json.dumps(sign_obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")

        key_path = Path(private_key_path)
        key_data = key_path.read_bytes()
        try:
            private_key = serialization.load_pem_private_key(key_data, password=None)
        except Exception as e:
            raise LgdfError(f"加载私钥失败: {e}")

        if algorithm.startswith("RSA"):
            sig = private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
            pub = private_key.public_key()
        elif algorithm.startswith("ECDSA"):
            sig = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
            pub = private_key.public_key()
        else:
            raise LgdfError(f"不支持的算法: {algorithm}")

        import base64
        pub_pem = pub.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")

        self.info.author_sign = AuthorSign(
            algorithm=algorithm,
            public_key=pub_pem,
            signature=base64.b64encode(sig).decode("ascii"),
            signed_at=_now(),
        )
        self.save()

    def verify_sign(self) -> bool:
        """验证 author_sign，返回 True/False。需要 cryptography 库。"""
        if self.info.author_sign is None:
            return True  # 无签名视为通过
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, padding
        import base64

        sign = self.info.author_sign
        sign_obj = self._build_sign_object()
        payload = json.dumps(sign_obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")

        pub_key = serialization.load_pem_public_key(sign.public_key.encode("ascii"))
        sig_bytes = base64.b64decode(sign.signature)

        try:
            if sign.algorithm.startswith("RSA"):
                pub_key.verify(sig_bytes, payload, padding.PKCS1v15(), hashes.SHA256())
            elif sign.algorithm.startswith("ECDSA"):
                pub_key.verify(sig_bytes, payload, ec.ECDSA(hashes.SHA256()))
            else:
                return False
            return True
        except Exception:
            return False

    def _build_sign_object(self) -> dict:
        return {
            "format": self.info.format,
            "min_sdk": self.info.min_sdk,
            "name": self.info.name,
            "registered_files": sorted(self.registry.registered_files),
            "version": self.info.version,
        }

    # ---------------------------------------------------------------- 版本与校验

    def bump_version(self, steps: int = 1):
        if steps < 1:
            raise ValueError("steps 必须 >= 1")
        self.info.version += steps
        self.save()

    def validate(self) -> ValidationReport:
        return validate_project(self.root, self.info, self.registry)

    # ---------------------------------------------------------------- 导出

    def _collect_export_entries(self) -> List[str]:
        entries = ["info.json", "registry.json"]
        for sub in ("assets", "metadata", "spec"):
            base = self.root / sub
            if not base.is_dir():
                continue
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    entries.append(p.relative_to(self.root).as_posix())
        return entries

    def export(self, out_path=None, *, skip_validation=False) -> Tuple[Path, str]:
        """导出为压缩包（ZIP）。返回 (路径, sha256)。

        默认输出到 ``<工程>/dist/<name>.lgdf``，扩展名可自定义。
        """
        if not skip_validation:
            report = self.validate()
            if not report.ok:
                raise ValidationError(report)
        if out_path is None:
            out_path = self.root / "dist" / f"{self.info.name}.lgdf"
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel in self._collect_export_entries():
                zf.write(self._fs(rel), rel)
        digest = _sha256_file(out_path)
        Path(str(out_path) + ".sha256").write_text(digest + "\n", encoding="ascii")
        return out_path, digest

    # ---------------------------------------------------------------- 导入

    @classmethod
    def import_from(cls, source, dest, *, tmp_base=None) -> "LgdfProject":
        """从压缩包导入为目录模式工程。

        ``source``：压缩包路径；``dest``：目标目录。
        """
        source = Path(source)
        dest = Path(dest)
        if dest.exists() and any(dest.iterdir()):
            raise LgdfError(f"目标目录非空: {dest}")

        with zipfile.ZipFile(source) as zf:
            for zi in zf.infolist():
                if zi.is_dir():
                    continue
                rel = _norm_rel(zi.filename)
                if rel in _IMPORTABLE_ROOT_FILES or rel.startswith(_EXPORT_ENTRY_PREFIXES):
                    target = dest / Path(*rel.split("/"))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(zi) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        info = _read_info(dest)
        _check_info(info)
        registry = _read_registry(dest)
        proj = cls(dest, info, registry)
        report = proj.validate()
        if not report.ok:
            shutil.rmtree(dest, ignore_errors=True)
            raise ValidationError(report)
        return proj

    # ---------------------------------------------------------------- 便捷属性

    @property
    def registered_files(self) -> List[str]:
        return list(self.registry.registered_files)

    def list_assets(self) -> List[AssetMetadata]:
        return [self.get_metadata(rel) for rel in self.registry.registered_files]
