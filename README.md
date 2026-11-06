# siglume-macos-x86-64-wheels

Python wheels for Intel Macs (`macosx_13_0_x86_64`), built by the Siglume project from unmodified upstream source
distributions. The upstream projects below do not publish wheels for Intel Macs at the versions the Siglume desktop
application pins, so this repository builds them. The upstream projects are not involved in these builds and do not
support them. Use the upstream releases on any other platform.

| Wheel | Upstream | Upstream license |
| --- | --- | --- |
| `cryptography` | [pyca/cryptography](https://github.com/pyca/cryptography) | Apache-2.0 OR BSD-3-Clause |
| `cbor2` | [agronholm/cbor2](https://github.com/agronholm/cbor2) | MIT |
| `ckzg` | [ethereum/c-kzg-4844](https://github.com/ethereum/c-kzg-4844) | Apache-2.0 (includes blst, Apache-2.0) |
| `argon2-cffi-bindings` | [hynek/argon2-cffi-bindings](https://github.com/hynek/argon2-cffi-bindings) | MIT (includes libargon2) |

Each wheel carries its upstream license files in `*.dist-info/licenses/`.

## What differs from an upstream wheel

- The Python and native source is the upstream sdist, byte for byte; the build script checks its SHA-256. No patch is
  applied and the version name stays the upstream one.
- `cryptography` statically links OpenSSL, as upstream wheels do. OpenSSL is built from the official source release with
  the flags of upstream's [pyca/infra](https://github.com/pyca/infra) (`cryptography-linux/openssl-version.sh`), except
  that `no-apps` is left out because OpenSSL's `make test` needs the apps. The OpenSSL version is in the release tag. The
  OpenSSL `--prefix` and `--openssldir` are `/nonexistent/siglume-openssl`, so no configuration file is read from a
  default location.
- The build machine's paths are not left in the binaries. The build maps its home, tool and work directories to
  `/siglume-build/…` (`--remap-path-prefix` for Rust, `-ffile-prefix-map` for C) and links without debug symbol entries;
  the check script requires that no file in a wheel contains a path under `/Users/`, `/private/var/` or `/var/folders/`, or
  one of the build directories. The one place the Rust mapping does not reach is the CycloneDX SBOM that `maturin` writes
  into the `cryptography` wheel (`*.dist-info/sboms/cryptography-rust.cyclonedx.json`, whose component references are the
  build directory's `path+file://` URLs). The build rewrites those paths with the same mapping, after checking that the
  JSON still parses and that the number of `bom-ref` entries and the references between them are unchanged, and updates
  that file's `RECORD` entry; the check script recomputes every `RECORD` hash and size. No other file in the wheel is
  changed apart from the added license.
- The `cryptography` wheel also holds OpenSSL's Apache-2.0 license text as
  `*.dist-info/licenses/OPENSSL-LICENSE.txt`, with its line in `RECORD`.

## How a wheel is built and checked

`build_macos_x86_64_wheels.sh` builds all four on an Intel Mac with the python.org CPython 3.11.9, Rust 1.98.1,
`MACOSX_DEPLOYMENT_TARGET=13.0`, `ARCHFLAGS="-arch x86_64"`, fixed build tool versions and no Homebrew on `PATH`. It runs
OpenSSL's `make test`. `add_openssl_license.py` adds the license. `check_macos_x86_64_wheels.py` then requires, for every
Mach-O file: the wheel's tag, only the `x86_64` architecture, a minimum macOS of 13.0, and only system libraries loaded;
and that `cryptography` reports the expected OpenSSL version. Upstream's `cryptography` test suite is run against the
built wheel, because upstream no longer tests Intel Macs.

`compare_wheels.py` compares two sets of wheels of the same names and writes a JSON report: for each wheel, the files
whose bytes differ and, for each Mach-O file, the sections and the UUID that differ. It makes no pass or fail decision;
its exit status does not depend on the differences it finds. `publish_wheels.sh` is the script that created the four
releases of 2026-11-05: it holds their tags, wheel SHA-256 values and release notes, never uses `--clobber`, and
downloads each asset again without authentication to check its SHA-256. The script itself does not check whether a tag
exists; if it is run again, `gh release create` refuses the first tag, which already exists, and the script stops there.
The comments in the scripts are in Japanese.

Builds are not guaranteed to be byte-identical. What a consumer should pin is the SHA-256 of the release asset. What was
observed when the same versions were built twice, in two different build folders: the `cbor2`, `ckzg` and
`argon2-cffi-bindings` binaries were byte-identical and the wheels differed only in the timestamps inside the zip
archive; in `cryptography`, the machine code (`__TEXT,__text`) was identical, and the only difference between the
strings of the binary was the `built on:` date and time that OpenSSL records when it is compiled (the strings of the two
builds differ in that one line). The UUID of the binary also differed; its cause was not examined. The SBOM differs
by design (it holds a timestamp and a serial number). Two
earlier `ckzg` builds of the same version, made in two different folders before the build linked without debug symbol
entries (and with the build folder's path still in the binary), differed only in the UUID of the binary and in `RECORD`.

## Where the scripts come from

The five scripts in this repository are byte-for-byte copies of `scripts/release/macos_x86_64_wheels/` in the Siglume
project's development repository (not public) at commit `cfd912e0c715c222d3789b9fb934a2f9bfcf5fa3`. The four releases of
2026-11-05 were built before these scripts were in that repository's main branch, by scripts with the same bytes. A
rebuild from the main branch had the same file list as the published wheels and the same machine code (`__TEXT,__text`)
in every Mach-O file; the other differences are the ones described above (the `built on:` line and the UUID in
`cryptography`, the SBOM, `RECORD` and the zip timestamps).

## Releases

Each build of a wheel is one release, tagged for example `cryptography-50.0.2-openssl-4.0.3`. Assets are never replaced:
a rebuild, including one that only updates OpenSSL, is a new tag. Pin the asset URL and its SHA-256.

## Security updates

These wheels get fixes only when this repository rebuilds them. The Siglume project follows the `pyca/cryptography`
advisories and changelog, the OpenSSL vulnerabilities page, and the releases of the other three projects. Report a problem
in these builds in this repository's issues, not to the upstream projects.
