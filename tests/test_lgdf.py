"""lgdf-sdk v2.0 单元测试。"""
import base64
import hashlib
import json
import os
import shutil
import sys
import time
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lgdf import (  # noqa: E402
    AssetNotFoundError, DuplicateAssetError, InvalidProjectError,
    LgdfProject, ValidationError,
)

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class LgdfV2Tests(unittest.TestCase):
    def setUp(self):
        env_base = os.environ.get("LGDF_TEST_BASE")
        base = Path(env_base) if env_base else Path(__file__).resolve().parent / ".tmp"
        base.mkdir(parents=True, exist_ok=True)
        self.work = base / f"lgdf-test-{time.time_ns()}"
        self.work.mkdir()
        self.addCleanup(shutil.rmtree, str(self.work), True)
        self.root = self.work / "proj"

    def _make(self, **kw):
        return LgdfProject.create("demo", self.root, author="tester", **kw)

    def test_create_skeleton(self):
        p = self._make()
        self.assertTrue((self.root / "assets").is_dir())
        self.assertTrue((self.root / "metadata").is_dir())
        self.assertTrue((self.root / "spec").is_dir())
        self.assertTrue((self.root / "info.json").is_file())
        self.assertTrue((self.root / "registry.json").is_file())
        info = json.loads((self.root / "info.json").read_text(encoding="utf-8"))
        self.assertEqual(info["format"], "lgdf")
        self.assertNotIn("one_file", info)
        self.assertNotIn("registered_files", info)
        reg = json.loads((self.root / "registry.json").read_text(encoding="utf-8"))
        self.assertIn("registered_files", reg)
        self.assertTrue(p.validate().ok)

    def test_add_and_metadata(self):
        p = self._make()
        meta = p.add_asset("images/a.png", data=PNG_BYTES,
                           properties={"width": 1, "height": 1})
        self.assertEqual(meta.path, "assets/images/a.png")
        self.assertEqual(meta.type, "image")
        self.assertEqual(meta.sha256, hashlib.sha256(PNG_BYTES).hexdigest())
        self.assertTrue((self.root / "metadata/images/a.png.json").is_file())
        self.assertEqual(p.registry.asset_count, 1)
        self.assertTrue(p.validate().ok, p.validate().summary())

    def test_replace_and_remove(self):
        p = self._make()
        m1 = p.add_asset("audio/b.wav", data=b"old")
        m2 = p.replace_asset("audio/b.wav", data=b"new-content")
        self.assertNotEqual(m1.sha256, m2.sha256)
        self.assertEqual(m1.created_time, m2.created_time)
        p.remove_asset("audio/b.wav")
        self.assertFalse((self.root / "assets/audio/b.wav").exists())
        self.assertFalse((self.root / "metadata/audio/b.wav.json").exists())
        self.assertTrue(p.validate().ok)

    def test_duplicate_and_missing(self):
        p = self._make()
        p.add_asset("a.bin", data=b"x")
        with self.assertRaises(DuplicateAssetError):
            p.add_asset("assets/a.bin", data=b"y")
        with self.assertRaises(AssetNotFoundError):
            p.remove_asset("assets/none.bin")

    def test_spec_layers(self):
        p = self._make()
        p.set_steps([{"id": "s1", "name": "n"}], title="T")
        self.assertEqual(p.get_steps()["steps"][0]["id"], "s1")
        with self.assertRaises(ValueError):
            p.set_steps([{"id": "x"}])
        p.set_config({"volume": 0.5})
        self.assertEqual(p.get_config()["volume"], 0.5)

    def test_export_and_import(self):
        p = self._make()
        p.add_asset("images/a.png", data=PNG_BYTES, properties={"width": 1})
        p.set_config({"volume": 0.5})

        # 导出
        out = self.work / "demo.lgdf"
        z, digest = p.export(out)
        self.assertTrue(z.is_file())
        self.assertEqual(hashlib.sha256(z.read_bytes()).hexdigest(), digest)
        sidecar = Path(str(z) + ".sha256")
        self.assertEqual(sidecar.read_text("ascii").strip(), digest)

        # 条目检查
        with zipfile.ZipFile(z) as zf:
            names = set(zf.namelist())
        self.assertTrue(all("\\" not in n for n in names))
        for need in ("info.json", "registry.json", "assets/images/a.png",
                     "metadata/images/a.png.json", "spec/config.json"):
            self.assertIn(need, names)

        # 导入
        dest = self.work / "imported"
        p2 = LgdfProject.import_from(z, dest)
        self.assertEqual(sorted(p2.registered_files), sorted(p.registered_files))
        self.assertEqual(p2.read_asset("assets/images/a.png"), PNG_BYTES)
        self.assertTrue(p2.validate().ok)

    def test_export_custom_ext(self):
        p = self._make()
        p.add_asset("a.bin", data=b"x")
        out = self.work / "demo.zip"
        z, _ = p.export(out)
        self.assertTrue(z.suffix == ".zip")

    def test_export_refuses_invalid(self):
        p = self._make()
        p.add_asset("images/a.png", data=PNG_BYTES)
        (self.root / "assets/images/a.png").write_bytes(b"tampered")
        with self.assertRaises(ValidationError):
            p.export(self.work / "bad.lgdf")

    def test_validation_detects_problems(self):
        p = self._make()
        p.add_asset("images/a.png", data=PNG_BYTES)
        (self.root / "assets/images/stray.txt").write_text("x", encoding="utf-8")
        codes = {i.code for i in p.validate().issues}
        self.assertIn("UNREGISTERED_ASSET", codes)
        (self.root / "metadata/images").mkdir(parents=True, exist_ok=True)
        (self.root / "metadata/images/orphan.txt.json").write_text("{}", encoding="utf-8")
        codes = {i.code for i in p.validate().issues}
        self.assertIn("ORPHAN_METADATA", codes)

    def test_text_utf8_validation(self):
        p = self._make()
        # 合法 UTF-8 文本
        p.add_asset("notes/readme.txt", data="hello 你好".encode("utf-8"),
                    properties={"encoding": "utf-8"})
        self.assertTrue(p.validate().ok)
        # 非法 UTF-8（手动构造）
        bad = self.root / "assets/notes/bad.txt"
        bad.write_bytes(b"\x80\x81\x82")
        from lgdf.model import AssetMetadata
        meta = AssetMetadata(
            path="assets/notes/bad.txt", type="text", size=3,
            sha256=hashlib.sha256(b"\x80\x81\x82").hexdigest(),
            created_time=0, last_update_time=0, properties={"encoding": "utf-8"})
        p.registry.registered_files.append("assets/notes/bad.txt")
        p.save()
        (self.root / "metadata/notes/bad.txt.json").write_text(
            json.dumps(meta.to_dict(), ensure_ascii=False, indent="\t"), encoding="utf-8")
        codes = {i.code for i in p.validate().issues}
        self.assertIn("INVALID_UTF8", codes)

    def test_create_bad_name(self):
        with self.assertRaises(InvalidProjectError):
            LgdfProject.create("Bad Name!", self.work / "p2")


if __name__ == "__main__":
    unittest.main()
