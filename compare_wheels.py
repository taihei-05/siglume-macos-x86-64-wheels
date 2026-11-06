import hashlib, io, json, re, sys, tempfile, zipfile
from pathlib import Path
from macholib.MachO import MachO
from macholib.mach_o import LC_SEGMENT_64, LC_UUID

old_dir, new_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
MAGICS = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}


def macho_facts(data):
    with tempfile.NamedTemporaryFile(suffix=".bin") as handle:
        handle.write(data)
        handle.flush()
        macho = MachO(handle.name)
    header = macho.headers[0]
    facts = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "uuid": None, "text_sha256": None, "sections": {}}
    for load, cmd, section_list in header.commands:
        if load.cmd == LC_UUID:
            facts["uuid"] = bytes(cmd.uuid).hex()
        elif load.cmd == LC_SEGMENT_64:
            for section in section_list:
                name = section.segname.rstrip(b"\0").decode() + "," + section.sectname.rstrip(b"\0").decode()
                start = header.offset + section.offset
                piece = data[start:start + section.size] if section.offset else b""
                facts["sections"][name] = hashlib.sha256(piece).hexdigest()[:16]
                if name == "__TEXT,__text":
                    facts["text_sha256"] = hashlib.sha256(piece).hexdigest()
    paths = sorted({m.decode("latin-1") for m in re.findall(rb"/(?:Users|private|tmp|var/folders)/[\x21-\x7e]{1,200}", data)})
    facts["absolute_path_count"] = len(paths)
    facts["absolute_paths_first_30"] = paths[:30]
    return facts


def members(path):
    found = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            data = archive.read(info)
            found[info.filename] = {"crc": info.CRC, "date_time": list(info.date_time), "size": info.file_size,
                                    "compress_size": info.compress_size, "data": data}
    return found


result = {"same_version": {}, "published_candidates": {}}
for new_path in sorted(new_dir.glob("*.whl")):
    new = members(new_path)
    result["published_candidates"][new_path.name] = {
        "sha256": hashlib.sha256(new_path.read_bytes()).hexdigest(),
        "date_times": sorted({tuple(m["date_time"]) for m in new.values()})[:5],
        "machos": {n: macho_facts(m["data"]) for n, m in new.items() if m["data"][:4] in MAGICS},
    }
    old_path = old_dir / new_path.name
    if not old_path.is_file():
        continue
    old = members(old_path)
    differ = sorted(n for n in set(old) | set(new) if n not in old or n not in new or old[n]["data"] != new[n]["data"])
    entry = {
        "members": len(new),
        "members_with_different_bytes": differ,
        "date_time_differs": sum(1 for n in new if n in old and old[n]["date_time"] != new[n]["date_time"]),
        "compress_size_differs": sum(1 for n in new if n in old and old[n]["compress_size"] != new[n]["compress_size"]),
        "old_date_times": sorted({tuple(m["date_time"]) for m in old.values()})[:5],
        "new_date_times": sorted({tuple(m["date_time"]) for m in new.values()})[:5],
    }
    for name in differ:
        if name in old and name in new and old[name]["data"][:4] in MAGICS:
            a, b = macho_facts(old[name]["data"]), macho_facts(new[name]["data"])
            entry.setdefault("macho", {})[name] = {
                "old": a, "new": b, "text_same": a["text_sha256"] == b["text_sha256"], "uuid_same": a["uuid"] == b["uuid"],
                "sections_differ": sorted(k for k in set(a["sections"]) | set(b["sections"]) if a["sections"].get(k) != b["sections"].get(k)),
            }
        elif name in old and name in new:
            entry.setdefault("text_diff_sizes", {})[name] = [len(old[name]["data"]), len(new[name]["data"])]
    result["same_version"][new_path.name] = entry
out.write_text(json.dumps(result, indent=1, sort_keys=True, default=list))
print(json.dumps({k: {"differ": v["members_with_different_bytes"], "date_time_differs": v["date_time_differs"],
                      "macho": {n: {"text_same": m["text_same"], "uuid_same": m["uuid_same"], "sections_differ": m["sections_differ"]} for n, m in v.get("macho", {}).items()}}
                  for k, v in result["same_version"].items()}, indent=1))
for name, item in result["published_candidates"].items():
    print(name, item["sha256"], {n: f["absolute_path_count"] for n, f in item["machos"].items()})
