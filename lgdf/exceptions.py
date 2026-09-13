"""lgdf-sdk 异常类型。"""


class LgdfError(Exception):
    """LGDF SDK 所有异常的基类。"""


class InvalidProjectError(LgdfError):
    """工程结构不合法。"""


class ValidationError(LgdfError):
    """校验未通过。"""

    def __init__(self, report):
        self.report = report
        lines = [f"校验失败（{len(report.issues)} 个问题）："]
        lines += [f"  [{i.code}] {i.path or ''} {i.message}".rstrip() for i in report.issues[:10]]
        if len(report.issues) > 10:
            lines.append(f"  ... 其余 {len(report.issues) - 10} 条省略")
        super().__init__("\n".join(lines))


class ReadOnlyError(LgdfError):
    """工程只读（已移除，保留兼容）。"""


class AssetNotFoundError(LgdfError):
    """资源不存在。"""


class DuplicateAssetError(LgdfError):
    """资源已注册。"""


class SignatureError(LgdfError):
    """签名验证失败。"""
