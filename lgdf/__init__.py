"""lgdf-sdk — LGDF v1.0.1 Python 解析器库。"""

from .core import SDK_VERSION, LgdfProject
from .exceptions import (
    AssetNotFoundError, DuplicateAssetError, InvalidProjectError,
    LgdfError, ReadOnlyError, SignatureError, ValidationError,
)
from .model import AssetMetadata, AuthorSign, Info, Registry, TimestampSign
from .validate import ValidationIssue, ValidationReport, validate_project

__version__ = "1.0.1"

__all__ = [
    "LgdfProject", "Info", "Registry", "AssetMetadata",
    "AuthorSign", "TimestampSign",
    "ValidationIssue", "ValidationReport", "validate_project",
    "LgdfError", "InvalidProjectError", "ValidationError",
    "ReadOnlyError", "AssetNotFoundError", "DuplicateAssetError",
    "SignatureError", "SDK_VERSION", "__version__",
]


def create_project(name, path, **kwargs) -> LgdfProject:
    return LgdfProject.create(name, path, **kwargs)


def open_project(source) -> LgdfProject:
    return LgdfProject.open(source)
