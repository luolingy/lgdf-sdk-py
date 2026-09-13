"""扩展名 → 分类 / MIME / 格式标识 的映射表（对应标准第 5 章）。"""

_EXT_TYPE = {
    # image
    "jpg": "image", "jpeg": "image", "png": "image", "svg": "image",
    "webp": "image", "gif": "image", "bmp": "image", "ico": "image",
    # audio
    "mp3": "audio", "wav": "audio", "ogg": "audio", "flac": "audio",
    "m4a": "audio", "aac": "audio", "opus": "audio",
    # video
    "mp4": "video", "webm": "video", "mkv": "video", "mov": "video",
    # model
    "obj": "model", "gltf": "model", "glb": "model", "fbx": "model",
    "blend": "model", "stl": "model",
    # text
    "txt": "text", "md": "text", "json": "text", "xml": "text",
    "yaml": "text", "yml": "text", "csv": "text",
}

_EXT_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "svg": "image/svg+xml", "webp": "image/webp", "gif": "image/gif",
    "bmp": "image/bmp", "ico": "image/x-icon",
    "mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg",
    "flac": "audio/flac", "m4a": "audio/mp4", "aac": "audio/aac",
    "opus": "audio/ogg",
    "mp4": "video/mp4", "webm": "video/webm", "mkv": "video/x-matroska",
    "mov": "video/quicktime",
    "obj": "text/plain", "gltf": "model/gltf+json", "glb": "model/gltf-binary",
    "fbx": "application/octet-stream", "blend": "application/octet-stream",
    "stl": "model/stl",
    "txt": "text/plain", "md": "text/markdown", "json": "application/json",
    "xml": "application/xml", "yaml": "application/yaml", "yml": "application/yaml",
    "csv": "text/csv",
}

# 元数据 format 字段的别名（扩展名 → 规范格式名）
_FORMAT_ALIAS = {"jpg": "jpeg", "yml": "yaml"}

DEFAULT_MIME = "application/octet-stream"


def ext_of(rel_path):
    """取小写扩展名（不含点）；无扩展名返回空串。"""
    name = rel_path.rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[1].lower()


def guess_type(rel_path):
    """按扩展名推断分类；未知返回 'binary'。"""
    return _EXT_TYPE.get(ext_of(rel_path), "binary")


def guess_mime(rel_path):
    """按扩展名推断 MIME；未知返回 application/octet-stream。"""
    return _EXT_MIME.get(ext_of(rel_path), DEFAULT_MIME)


def format_of(rel_path):
    """按扩展名推断 format 字段（应用别名表）；无扩展名返回 None。"""
    ext = ext_of(rel_path)
    if not ext:
        return None
    return _FORMAT_ALIAS.get(ext, ext)
