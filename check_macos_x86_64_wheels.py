"""組んだ4つの wheel を確かめて JSON で出す（§4.5 項目3 の「組んだ後の確かめ」）。

引数: wheels のフォルダー、期待する OpenSSL の版、出力の JSON、（任意）組み立て機の道を表す文字列（作業フォルダー・
道具のフォルダー・HOME など。何個でも）。判定の材料だけを出し、合わなければ exit 1。

組み立て機の道が wheel に残っていないことも確かめる: Mach-O を含む全ファイルで、/Users/・/private/var/・/var/folders/
の下の道と、引数で渡した文字列を探す（残っていれば problems に入れる）。
"""

import base64
import csv
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

wheels_dir, expected_openssl, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
EXPECTED = {
    "cryptography": "cryptography-50.0.2-cp311-abi3-macosx_13_0_x86_64.whl",
    "cbor2": "cbor2-6.1.4-cp311-cp311-macosx_13_0_x86_64.whl",
    "ckzg": "ckzg-2.1.8-cp311-cp311-macosx_13_0_x86_64.whl",
    "argon2_cffi_bindings": "argon2_cffi_bindings-26.1.0-cp310-abi3-macosx_13_0_x86_64.whl",
}
SYSTEM = ("/usr/lib/", "/System/Library/")
BUILDER_PATH = re.compile(rb"/(?:Users|private/var|var/folders)/[\x21-\x7e]{1,200}")
BUILDER_STRINGS = [item.rstrip("/").encode() for item in sys.argv[4:] if item.rstrip("/")]
MAGICS = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}
problems = []
report = {"wheels": {}}


def run(*command):
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout


for name, filename in EXPECTED.items():
    wheel = wheels_dir / filename
    if not wheel.is_file():
        problems.append(f"{name}: {filename} missing; found {sorted(p.name for p in wheels_dir.glob('*.whl'))}")
        continue
    entry = {"sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "size": wheel.stat().st_size, "binaries": {}}
    with tempfile.TemporaryDirectory() as raw, zipfile.ZipFile(wheel) as archive:
        archive.extractall(raw)
        root = Path(raw)
        tags = [line.split(":", 1)[1].strip() for path in root.glob("*.dist-info/WHEEL")
                for line in path.read_text().splitlines() if line.startswith("Tag:")]
        entry["tags"] = tags
        if tags != [filename[:-4].split("-", 2)[2]]:
            problems.append(f"{name}: WHEEL tags {tags}")
        entry["licenses"] = sorted(path.relative_to(root).as_posix() for path in root.rglob("*")
                                   if path.is_file() and re.search(r"licen[sc]e|copying", path.name, re.I))
        count = 0
        entry["builder_paths"] = {}
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            content = path.read_bytes()
            leaked = sorted({m.decode("latin-1") for m in BUILDER_PATH.findall(content)}
                            | {s.decode("latin-1") for s in BUILDER_STRINGS if s in content})
            if leaked:
                entry["builder_paths"][path.relative_to(root).as_posix()] = {"count": len(leaked), "first_5": leaked[:5]}
                problems.append(f"{path.relative_to(root).as_posix()}: build machine paths {len(leaked)}, e.g. {leaked[:2]}")
            with path.open("rb") as handle:
                if handle.read(4) not in MAGICS:
                    continue
            count += 1
            relative = path.relative_to(root).as_posix()
            archs = run("/usr/bin/lipo", "-archs", str(path)).strip()
            commands = run("/usr/bin/otool", "-l", str(path))
            minos, command = [], ""
            for line in commands.splitlines():
                words = line.split()
                if len(words) == 2 and words[0] == "cmd":
                    command = words[1]
                elif len(words) == 2 and ((command == "LC_BUILD_VERSION" and words[0] == "minos")
                                          or (command == "LC_VERSION_MIN_MACOSX" and words[0] == "version")):
                    minos.append(words[1])
            loads = [line.split()[0] for line in run("/usr/bin/otool", "-L", str(path)).splitlines()[1:]]
            own_id = run("/usr/bin/otool", "-D", str(path)).splitlines()[1:]
            outside = [item for item in loads if not item.startswith(SYSTEM) and item not in own_id]
            entry["binaries"][relative] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                           "archs": archs, "minos": minos, "loads": loads}
            if archs != "x86_64":
                problems.append(f"{relative}: archs {archs}")
            if minos != ["13.0"]:
                problems.append(f"{relative}: minos {minos}")
            if outside:
                problems.append(f"{relative}: loads {outside}")
        if count == 0:
            problems.append(f"{name}: no Mach-O")
        # RECORD の hash・size が中身に合うこと（仕上げで file を書き換えた後の整合）
        records = list(root.glob("*.dist-info/RECORD"))
        if len(records) != 1:
            problems.append(f"{name}: RECORD files {len(records)}")
        else:
            listed = {row[0]: row[1:] for row in csv.reader(records[0].read_text(encoding="utf-8").splitlines()) if row}
            actual = {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}
            self_name = records[0].relative_to(root).as_posix()
            wrong = []
            for relative, path in actual.items():
                if relative == self_name or relative.endswith(("/RECORD.jws", "/RECORD.p7s")):
                    continue
                if relative not in listed:
                    wrong.append(f"{relative}: not in RECORD")
                    continue
                if len(listed[relative]) < 2:
                    wrong.append(f"{relative}: malformed RECORD row")
                    continue
                digest, size = listed[relative][0], listed[relative][1]
                content = path.read_bytes()
                expected = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
                if digest != expected or size != str(len(content)):
                    wrong.append(f"{relative}: RECORD hash or size differs")
            wrong += [f"{relative}: in RECORD but missing" for relative in listed if relative not in actual]
            entry["record_mismatches"] = wrong
            problems.extend(f"{name}: {item}" for item in wrong)
        # SBOM（PEP 770。maturin が作る CycloneDX）が JSON として読めること。中身の要約を残す
        entry["sboms"] = {}
        for path in sorted(root.glob("*.dist-info/sboms/*")):
            relative = path.relative_to(root).as_posix()
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                entry["sboms"][relative] = {"bomFormat": document.get("bomFormat"), "specVersion": document.get("specVersion"),
                                            "components": len(document.get("components") or []),
                                            "dependencies": len(document.get("dependencies") or [])}
            except (ValueError, AttributeError) as error:
                problems.append(f"{relative}: SBOM unreadable ({error})")
    report["wheels"][name] = entry

if (wheels_dir / EXPECTED["cryptography"]).is_file():
    with tempfile.TemporaryDirectory() as raw:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "--disable-pip-version-check",
                        "--target", raw, str(wheels_dir / EXPECTED["cryptography"])], check=True)
        probe = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "from cryptography.hazmat.backends.openssl import backend;"
            "print(backend.openssl_version_text())"
        )
        text = subprocess.run([sys.executable, "-c", probe, raw], capture_output=True, text=True, check=True).stdout.strip()
    report["cryptography_openssl_version_text"] = text
    if not text.startswith(f"OpenSSL {expected_openssl} "):
        problems.append(f"cryptography OpenSSL {text}")

report["problems"] = problems
out.write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print(json.dumps({"problems": problems, "sha256": {k: v["sha256"] for k, v in report["wheels"].items()},
                  "openssl": report.get("cryptography_openssl_version_text")}, indent=1))
raise SystemExit(1 if problems else 0)
