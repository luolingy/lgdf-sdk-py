# lgdf-sdk

LGDF v2.0（分层通用数据格式）Python 解析器库：**创建 / 读取 / 修改 / 校验 / 导出 / 导入**。

纯标准库实现，零必选依赖（Python ≥ 3.8）；签名功能需要 `cryptography`，schema 校验需要 `jsonschema`。

## 快速上手

```python
from lgdf import LgdfProject

# 创建
p = LgdfProject.create("demo", "./demo", author="me")
p.add_asset("images/a.png", source="./a.png", properties={"width": 1, "height": 1})
p.set_steps([{"id": "s1", "name": "导入资源"}])
p.set_config({"volume": 0.8})
p.save()

# 校验
print(p.validate().summary())

# 导出（扩展名可自定义）
path, sha = p.export("./dist/demo.lgdf")

# 导入
p2 = LgdfProject.import_from("./dist/demo.lgdf", "./restored")
print(p2.registered_files)

# 修改
p.replace_asset("images/a.png", source="./new.png")
p.remove_asset("images/a.png")
p.bump_version()
p.save()
```

## 签名（需要 cryptography）

```bash
pip install cryptography
```

```python
# 用私钥签名
p.sign("private_key.pem", algorithm="RSA-SHA256")

# 验证签名
assert p.verify_sign()
```

## API 速查

| 方法 | 说明 |
| --- | --- |
| `create(name, path)` | 创建空工程 |
| `open(path)` | 读取目录工程 |
| `add_asset(rel, source/data, properties)` | 注册资源 |
| `replace_asset(rel, source/data)` | 替换资源 |
| `remove_asset(rel)` | 注销资源 |
| `read_asset(rel)` / `get_metadata(rel)` | 读取 |
| `set_config` / `set_steps` / `set_overview` | 描述层 |
| `sign(private_key, algorithm)` | RSA/ECC 签名 |
| `verify_sign()` | 验证签名 |
| `validate()` | 全量校验 |
| `export(out_path)` | 导出为压缩包 |
| `import_from(source, dest)` | 从压缩包导入 |
| `bump_version()` / `save()` | 版本管理 |

## CLI

```bash
python -m lgdf create   ./demo --name demo
python -m lgdf add      ./demo images/a.png ./a.png
python -m lgdf remove   ./demo images/a.png
python -m lgdf list     ./demo
python -m lgdf info     ./demo
python -m lgdf validate ./demo
python -m lgdf export   ./demo -o dist/demo.lgdf
python -m lgdf import   dist/demo.lgdf ./restored
```

## 与 v1.0 的变化

- 移除单文件模式，改为导出/导入机制
- `registered_files` 从 `info.json` 拆分到 `registry.json`
- 移除 `one_file`、`version_control`、`read_only`、`asset_count` 等字段
- 作者签名要求 RSA/ECC（不再接受纯字符串）
- 文本类型资源强制 UTF-8
- 推荐标准文件格式与人类可读描述格式
