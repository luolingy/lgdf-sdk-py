"""LGDF v2.0 数据模型：Info / Registry / AssetMetadata。

所有模型支持与 dict 双向转换；顶层未知字段自动收纳进 extra/properties。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AuthorSign:
    """作者签名（RSA/ECC，见标准 4.3）。"""

    algorithm: str = ""      # RSA-SHA256 / ECDSA-P256-SHA256 / ...
    public_key: str = ""     # PEM 格式公钥
    signature: str = ""      # Base64 签名值
    signed_at: int = 0       # 签名时间（Unix 秒）

    _KNOWN = ("algorithm", "public_key", "signature", "signed_at")

    def to_dict(self):
        return {k: getattr(self, k) for k in self._KNOWN}

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            return None
        kw = {k: d[k] for k in cls._KNOWN if k in d}
        return cls(**kw)


@dataclass
class TimestampSign:
    """公共 TSA 时间戳签名（见标准 5.2）。"""

    tsa_url: str = ""
    token: str = ""      # Base64 RFC 3161 token
    signed_at: int = 0

    _KNOWN = ("tsa_url", "token", "signed_at")

    def to_dict(self):
        return {k: getattr(self, k) for k in self._KNOWN}

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            return None
        kw = {k: d[k] for k in cls._KNOWN if k in d}
        return cls(**kw)


# ---------------------------------------------------------------- info.json

@dataclass
class Info:
    """info.json 的内存模型（lgdf-standard.md v2.0 第 4 章）。"""

    name: str
    format: str = "lgdf"
    min_sdk: int = 1
    display_name: Optional[str] = None
    description: str = ""
    author: Optional[str] = None
    author_sign: Optional[AuthorSign] = None
    license: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_time: int = 0
    last_update_time: int = 0
    version: int = 1
    extra: Dict = field(default_factory=dict)

    _KNOWN = (
        "format", "min_sdk", "name", "display_name", "description", "author",
        "license", "tags", "created_time", "last_update_time", "version",
    )

    def to_dict(self):
        d = {}
        for k in self._KNOWN:
            v = getattr(self, k)
            if k == "tags":
                d[k] = list(v)
            else:
                d[k] = v
        if self.display_name is not None:
            d["display_name"] = self.display_name
        if self.author is not None:
            d["author"] = self.author
        if self.license is not None:
            d["license"] = self.license
        if self.author_sign is not None:
            d["author_sign"] = self.author_sign.to_dict()
        for k, v in self.extra.items():
            if k not in d:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            raise ValueError("info.json 必须是 JSON 对象")
        rest = dict(d)
        kw = {}
        for k in cls._KNOWN:
            if k in rest:
                kw[k] = rest.pop(k)
        sign_d = rest.pop("author_sign", None)
        extra = rest.pop("extra", {}) or {}
        extra.update(rest)
        kw["extra"] = extra
        obj = cls(**kw)
        obj.author_sign = AuthorSign.from_dict(sign_d)
        return obj


# --------------------------------------------------------- registry.json

@dataclass
class Registry:
    """registry.json 的内存模型（lgdf-standard.md v2.0 第 5 章）。"""

    registered_files: List[str] = field(default_factory=list)
    asset_count: Optional[int] = None
    timestamp_sign: Optional[TimestampSign] = None
    extra: Dict = field(default_factory=dict)

    _KNOWN = ("registered_files", "asset_count")

    def to_dict(self):
        d = {"registered_files": list(self.registered_files)}
        if self.asset_count is not None:
            d["asset_count"] = self.asset_count
        if self.timestamp_sign is not None:
            d["timestamp_sign"] = self.timestamp_sign.to_dict()
        for k, v in self.extra.items():
            if k not in d:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            raise ValueError("registry.json 必须是 JSON 对象")
        rest = dict(d)
        kw = {}
        for k in cls._KNOWN:
            if k in rest:
                kw[k] = rest.pop(k)
        ts_d = rest.pop("timestamp_sign", None)
        extra = rest.pop("extra", {}) or {}
        extra.update(rest)
        kw["extra"] = extra
        obj = cls(**kw)
        obj.timestamp_sign = TimestampSign.from_dict(ts_d)
        return obj


# ------------------------------------------------------ metadata/*.json

@dataclass
class AssetMetadata:
    """单个资源的元数据（标准第 7 章）。"""

    path: str
    type: str = "other"
    mime: Optional[str] = None
    format: Optional[str] = None
    size: int = 0
    sha256: str = ""
    hash_algorithm: str = "sha256"
    created_time: int = 0
    last_update_time: int = 0
    properties: Dict = field(default_factory=dict)
    extra: Dict = field(default_factory=dict)

    _KNOWN = (
        "path", "type", "mime", "format", "size", "sha256", "hash_algorithm",
        "created_time", "last_update_time",
    )

    def to_dict(self):
        d = {"path": self.path, "type": self.type}
        if self.mime is not None:
            d["mime"] = self.mime
        if self.format is not None:
            d["format"] = self.format
        d["size"] = self.size
        d["sha256"] = self.sha256
        d["hash_algorithm"] = self.hash_algorithm
        d["created_time"] = self.created_time
        d["last_update_time"] = self.last_update_time
        for k, v in self.properties.items():
            if k not in d:
                d[k] = v
        if self.extra:
            d["extra"] = dict(self.extra)
        return d

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            raise ValueError("元数据必须是 JSON 对象")
        rest = dict(d)
        kw = {}
        for k in cls._KNOWN:
            if k in rest:
                kw[k] = rest.pop(k)
        kw["extra"] = rest.pop("extra", {}) or {}
        kw["properties"] = rest
        return cls(**kw)

    @property
    def width(self):
        return self.properties.get("width")

    @property
    def height(self):
        return self.properties.get("height")

    @property
    def duration_seconds(self):
        return self.properties.get("duration_seconds")
