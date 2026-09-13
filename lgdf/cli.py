"""LGDF v2.0 CLI。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import LgdfProject
from .exceptions import LgdfError


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="lgdf", description="LGDF v2.0 SDK CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create", help="创建空工程")
    c.add_argument("dir"); c.add_argument("--name", required=True)
    c.add_argument("--author"); c.add_argument("--description", default="")
    c.add_argument("--license")

    a = sub.add_parser("add", help="注册资源")
    a.add_argument("project"); a.add_argument("rel"); a.add_argument("file")

    r = sub.add_parser("remove", help="注销资源")
    r.add_argument("project"); r.add_argument("rel")

    for name, ht in (("list", "列出资源"), ("info", "打印配置"), ("validate", "校验")):
        sp = sub.add_parser(name, help=ht); sp.add_argument("path")

    e = sub.add_parser("export", help="导出为压缩包")
    e.add_argument("project"); e.add_argument("-o", "--output"); e.add_argument("--ext", default=".lgdf")

    i = sub.add_parser("import", help="从压缩包导入")
    i.add_argument("source"); i.add_argument("dest")

    return ap


def _run(args) -> int:
    if args.cmd == "create":
        p = LgdfProject.create(args.name, args.dir, author=args.author,
                               description=args.description, license=args.license)
        print(f"已创建: {p.root}")
        return 0

    if args.cmd == "validate":
        with LgdfProject.open(args.path) if False else _ctx(args.path) as p:
            rep = p.validate()
        if rep.ok: print("OK"); return 0
        print(rep.summary(), file=sys.stderr); return 2

    if args.cmd == "info":
        with _ctx(args.path) as p:
            for k, v in [("name", p.info.name), ("version", p.info.version),
                         ("author", p.info.author), ("registered", len(p.registry.registered_files))]:
                print(f"{k:20}{v}")
        return 0

    if args.cmd == "list":
        with _ctx(args.path) as p:
            for m in p.list_assets():
                print(f"{m.size:>12}  {m.type:7}  {m.sha256[:12]}…  {m.path}")
        return 0

    if args.cmd == "export":
        with _ctx(args.project) as p:
            out = args.output or str(Path(args.project) / "dist" / f"{p.info.name}{args.ext}")
            z, d = p.export(out)
        print(f"已导出: {z}\nsha256: {d}")
        return 0

    if args.cmd == "import":
        p = LgdfProject.import_from(args.source, args.dest)
        print(f"已导入: {p.root}")
        return 0

    if args.cmd == "add":
        with _ctx(args.project) as p:
            m = p.add_asset(args.rel, source=args.file)
        print(f"已注册: {m.path}（{m.size} B）")
        return 0

    if args.cmd == "remove":
        with _ctx(args.project) as p:
            p.remove_asset(args.rel)
        print(f"已删除: {args.rel}")
        return 0

    return 1


def _ctx(path):
    """上下文管理器辅助。"""
    class _Ctx:
        def __init__(self, p): self.p = p
        def __enter__(self): return self.p
        def __exit__(self, *_): pass
    return _Ctx(LgdfProject.open(path))


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return _run(args)
    except LgdfError as e:
        print(f"错误: {e}", file=sys.stderr); return 1
