"""cryptography の wheel の仕上げ（§4.5 項目3）。

1. dist-info/licenses/ に OpenSSL の LICENSE.txt を足す。
2. （任意）dist-info/sboms/ の下の JSON（maturin が作る CycloneDX の SBOM）に入った組み立て機の道を、固定の道へ置き換える。

引数: 元の wheel、OpenSSL の LICENSE.txt、出力のフォルダー、（任意）置き換え FROM=TO を何個でも。
  例: /Users/user=/siglume-build/home /Users/user/work=/siglume-build/work
FROM が長い方から先に置き換える。FROM の直後が英数字・'.'・'_'・'-' なら別の名前なので置き換えない。
置き換えるのは sboms/ の下の JSON だけで、Mach-O を含むほかの file のバイトは変えない。置き換えた JSON は、
JSON として読めること、bom-ref の数が変わらないこと、参照（ref・dependsOn）が bom-ref に合うことを確かめ、FROM が
残っていれば止まる。足した file と置き換えた file は RECORD の hash・size を直す。
出力は同じ入力で同じバイトになる（時刻は固定、並びは file の名前の順）。
"""

import base64
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

FIXED_TIME = (2026, 1, 1, 0, 0, 0)

source, license_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
replacements = []
for item in sys.argv[4:]:
    old, separator, new = item.rpartition("=")
    if not separator or not old.startswith("/") or not new.startswith("/") or old.rstrip("/") == "":
        raise SystemExit(f"bad replacement {item!r}")
    replacements.append((old.rstrip("/"), new.rstrip("/")))
replacements.sort(key=lambda pair: len(pair[0]), reverse=True)


def record_hash(data):
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def replace_paths(text):
    count = 0
    for old, new in replacements:
        text, found = re.subn(r"(?<![A-Za-z0-9._-])" + re.escape(old) + r"(?![A-Za-z0-9._-])", lambda _match, new=new: new, text)
        count += found
    return text, count


def walk(node, refs, bom_refs):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "bom-ref" and isinstance(value, str):
                bom_refs.append(value)
            elif key == "ref" and isinstance(value, str):
                refs.add(value)
            elif key == "dependsOn" and isinstance(value, list):
                refs.update(item for item in value if isinstance(item, str))
            walk(value, refs, bom_refs)
    elif isinstance(node, list):
        for value in node:
            walk(value, refs, bom_refs)


def reference_facts(document):
    refs, bom_refs = set(), []
    walk(document, refs, bom_refs)
    return len(bom_refs), len(set(bom_refs)), sorted(refs - set(bom_refs))


license_bytes = license_path.read_bytes()
with zipfile.ZipFile(source) as archive:
    files = {info.filename: (archive.read(info), info.external_attr) for info in archive.infolist() if not info.is_dir()}
records = [name for name in files if name.endswith(".dist-info/RECORD")]
if len(records) != 1:
    raise SystemExit(f"expected one RECORD, found {records}")
signatures = [name for name in files if name.endswith(("/RECORD.jws", "/RECORD.p7s"))]
if signatures:
    raise SystemExit(f"RECORD signature present, rewriting would invalidate it: {signatures}")
record_name = records[0]
added = record_name[: -len("RECORD")] + "licenses/OPENSSL-LICENSE.txt"
if added in files:
    raise SystemExit(f"{added} already exists")
files[added] = (license_bytes, 0o644 << 16)
changed = {added: record_hash(license_bytes)}
changed_sizes = {added: len(license_bytes)}

rewritten = 0
if replacements:
    for name in sorted(files):
        if ".dist-info/sboms/" not in name or not name.endswith(".json"):
            continue
        data, attributes = files[name]
        text = data.decode("utf-8")
        before = reference_facts(json.loads(text))
        new_text, count = replace_paths(text)
        if new_text == text:
            continue
        after = reference_facts(json.loads(new_text))
        if before[:2] != after[:2] or len(before[2]) != len(after[2]):
            raise SystemExit(f"{name}: references changed by the replacement: {before} -> {after}")
        left = [old for old, _ in replacements if re.search(r"(?<![A-Za-z0-9._-])" + re.escape(old) + r"(?![A-Za-z0-9._-])", new_text)]
        if left:
            raise SystemExit(f"{name}: {left} still present")
        new_data = new_text.encode("utf-8")
        files[name] = (new_data, attributes)
        changed[name] = record_hash(new_data)
        changed_sizes[name] = len(new_data)
        rewritten += 1
        print(f"{name}: {count} paths replaced; bom-refs {after[0]} ({after[1]} distinct), unresolved refs {len(after[2])}")

if replacements and rewritten == 0:
    raise SystemExit("replacements given but no SBOM under dist-info/sboms/ had a path to replace")

record_lines = files[record_name][0].decode("utf-8").splitlines()
lines = []
seen = set()
for line in record_lines:
    name = line.rsplit(",", 2)[0]
    if name in changed and name != added:
        line = f"{name},sha256={changed[name]},{changed_sizes[name]}"
        seen.add(name)
    lines.append(line)
missing = sorted(set(changed) - seen - {added})
if missing:
    raise SystemExit(f"not in RECORD: {missing}")
lines.insert(len(lines) - 1, f"{added},sha256={changed[added]},{changed_sizes[added]}")
files[record_name] = (("\n".join(lines) + "\n").encode("utf-8"), files[record_name][1])

out_dir.mkdir(parents=True, exist_ok=True)
target = out_dir / source.name
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(files):
        data, attributes = files[name]
        info = zipfile.ZipInfo(name, FIXED_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = attributes
        archive.writestr(info, data)
print(target)
