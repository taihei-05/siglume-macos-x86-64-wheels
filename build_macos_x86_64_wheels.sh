#!/bin/sh
# Intel の Mac の公開の wheel が無い4つの native の依存を、上流の sdist（source を変えない）から
# macosx_13_0_x86_64 の wheel に組む台本（llm docs/design/minnano-ai-macos-desktop/README.md §4.5 項目3）。
# 使い方: build_macos_x86_64_wheels.sh <作業フォルダー> <道具のフォルダー（rustup・cargo・cmake がある）>
# 手前に取った物: <作業フォルダー>/dl/ に下の5つの source。無ければ取得する。SHA-256 が違えば止まる。
set -eu

# 道は絶対にして固定する（成果物に残さない道の置き換えの元になる）。空白を含む道は止める。
mkdir -p "$1"
B=$(cd "$1" && pwd -P)
T=$(cd "$2" && pwd -P)
H=$(cd "$HOME" && pwd -P)
if [ "$H" = "/" ]; then echo "HOME が / になっている。止まる。" >&2; exit 1; fi
case "$H$T$B" in
  *[[:space:]]*) echo "HOME・道具のフォルダー・作業フォルダーの道に空白がある。止まる。" >&2; exit 1;;
esac
PYORG=/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11

OPENSSL_VERSION=4.0.3
OPENSSL_SHA256=325b5c806167c13b40b1ffeadfe0248197c00eccc4cf123ec1e28d2d2fd216d9
OPENSSL_URL=https://github.com/openssl/openssl/releases/download/openssl-$OPENSSL_VERSION/openssl-$OPENSSL_VERSION.tar.gz
RUST_TOOLCHAIN=1.98.1

# 名前 版 SHA-256 URL（uv.lock の sdist と同じ物）
SDISTS="cryptography 50.0.2 7b46165bb56eb4704e2eaaf86f3c940d19154535d9b0ca7d6d590b04060e00d5 https://files.pythonhosted.org/packages/9d/af/182eb91b0df3fe75c4d9f26fe70684569566745f6ba7e5c9c73a862c5252/cryptography-50.0.2.tar.gz
cbor2 6.1.4 01ecc79a28f33d17331943ce508fc1e21f4b06553c73f874f4c77120d72b2ef9 https://files.pythonhosted.org/packages/c6/14/b02446bacfe44351b1689c04937ade007588f44570431880a6937e525e6c/cbor2-6.1.4.tar.gz
ckzg 2.1.8 d7bef6b425dca6995457fc59fc5b30211d9b28cbbeee0e7a7bef1372e13f29ca https://files.pythonhosted.org/packages/2b/88/552337d9fc69dc85fb6102c18b73a9f3f77efb39bb9a0c1a8c61bbdd7274/ckzg-2.1.8.tar.gz
argon2_cffi_bindings 26.1.0 63505c71542a44b68b1e38060450fb006404170da375feb31af153e7f9c6205d https://files.pythonhosted.org/packages/0b/43/bb8b6e8708d49a5ab36781333af092d9f483b198a2710d01281204640055/argon2_cffi_bindings-26.1.0.tar.gz"

mkdir -p "$B/dl" "$B/src" "$B/wheels" "$B/logs"

fetch() { # 道 SHA-256 URL
  if [ ! -f "$1" ]; then
    curl -fL --retry 3 -o "$1.part" "$3"
    echo "$2  $1.part" | shasum -a 256 -c -
    mv "$1.part" "$1"
  fi
  echo "$2  $1" | shasum -a 256 -c -
}

fetch "$B/dl/openssl-$OPENSSL_VERSION.tar.gz" "$OPENSSL_SHA256" "$OPENSSL_URL"
echo "$SDISTS" | while read -r name version sha url; do
  fetch "$B/dl/$name-$version.tar.gz" "$sha" "$url"
done

# 隔離した環境。PATH に Homebrew を入れない。
CMAKE=$(find "$T/cmake" -type f -name cmake -perm +111 | head -1)
test -x "$CMAKE"
CMAKE_BIN=$(dirname "$CMAKE")
test -x "$T/cargo/bin/cargo"
export RUSTUP_HOME="$T/rustup" CARGO_HOME="$T/cargo" RUSTUP_TOOLCHAIN="$RUST_TOOLCHAIN"
export PATH="$T/cargo/bin:$CMAKE_BIN:/usr/bin:/bin:/usr/sbin:/sbin"
export MACOSX_DEPLOYMENT_TARGET=13.0 ARCHFLAGS="-arch x86_64"
unset PKG_CONFIG_PATH CFLAGS CXXFLAGS LDFLAGS CPPFLAGS CC CXX SDKROOT CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH RUSTFLAGS OPENSSL_DIR OPENSSL_STATIC OPENSSL_LIB_DIR OPENSSL_INCLUDE_DIR OPENSSL_LIBS PYTHONPATH || true
rustc --version
cargo --version
cmake --version | head -1

[ -x "$B/env/bin/python" ] || "$PYORG" -m venv "$B/env"
"$B/env/bin/python" -m pip install --quiet --disable-pip-version-check \
  maturin==1.16.0 cffi==2.1.1 setuptools==84.2.1 wheel==0.48.0 setuptools-rust==1.13.0 \
  setuptools-scm==10.3.4 scikit-build-core==1.1.2
"$B/env/bin/python" -m pip freeze --disable-pip-version-check > "$B/logs/build-env.freeze.txt"
export PYO3_PYTHON="$B/env/bin/python"
export PATH="$B/env/bin:$PATH"

# 1. OpenSSL（静的）。--prefix・--openssldir はどの Mac にも無い道（§4.5 項目3）。
PREFIX=/nonexistent/siglume-openssl
STAGE="$B/openssl-stage"
if [ ! -f "$STAGE$PREFIX/lib/libcrypto.a" ]; then
  rm -rf "$B/src/openssl-$OPENSSL_VERSION" "$STAGE"
  tar -xzf "$B/dl/openssl-$OPENSSL_VERSION.tar.gz" -C "$B/src"
  (
    cd "$B/src/openssl-$OPENSSL_VERSION"
    # 上流の pyca/infra の OPENSSL_BUILD_FLAGS と同じ。ただし make test に要るので no-apps は外す。
    ./Configure darwin64-x86_64-cc no-zlib no-shared no-module no-comp no-docs no-sm2-precomp no-atexit \
      enable-ec_nistp_64_gcc_128 --prefix="$PREFIX" --openssldir="$PREFIX" --libdir=lib
    make -j4
    make test HARNESS_JOBS=2
    make install_sw DESTDIR="$STAGE"
  ) > "$B/logs/openssl.log" 2>&1
fi
tail -3 "$B/logs/openssl.log"
grep -n 'Result:\|Files=' "$B/logs/openssl.log" | tail -3

# 2 以降は、組み立て機の道（HOME・道具のフォルダー・作業フォルダー）を成果物に残さない。OpenSSL（1）はこの前に、
# 上の設定のままで済んでいる。後ろの指定が先に合う（rustc・clang とも）ので、広い HOME を先に並べる。
#  - Rust（cryptography・cbor2）: panic の場所の文字列などに入る registry・source の道を --remap-path-prefix で置き換える。
#  - C（ckzg）: __FILE__ などを -ffile-prefix-map で置き換える。CPPFLAGS は distutils の compile の引数に入る。
#    CFLAGS には触れない: blst の build.sh は CFLAGS が未設定の時だけ既定（-O2 -fno-builtin -fPIC …）を使う。
#  - 連結（C の ckzg・cmake の argon2）: LDFLAGS=-Wl,-S で debug の印（N_OSO。.o の絶対の道が入る）を出力に入れない。
#    Rust の連結は LDFLAGS を読まない（rustc が行う）。
#  - 効かない所: ckzg の blst（build.sh は CC・CFLAGS だけを読む。相対の道で、-g も無い）と、cmake の argon2
#    （CPPFLAGS を読まない。_ffi.c は同梱済みで __FILE__ を使わず、-g も無い）。ここは下の check が最後の保証になる。
# 置き換えの先の /siglume-build/ は実在しない道。check_macos_x86_64_wheels.py が、道が残っていないことを確かめる。
RUST_REMAP="--remap-path-prefix=$H=/siglume-build/home --remap-path-prefix=$T=/siglume-build/tools --remap-path-prefix=$B=/siglume-build/work"
C_REMAP="-ffile-prefix-map=$H=/siglume-build/home -ffile-prefix-map=$T=/siglume-build/tools -ffile-prefix-map=$B=/siglume-build/work"
# 使える物かを先に確かめる（使えなければここで止まる。置き換え無しで進めない）。
echo 'fn main() {}' | rustc --crate-name remap_probe --emit=metadata -o "$B/logs/remap-probe.rmeta" $RUST_REMAP -
echo 'int main(void) { return 0; }' | /usr/bin/cc $C_REMAP -x c -c -o "$B/logs/remap-probe.o" -
/usr/bin/cc -arch x86_64 -Wl,-S -o "$B/logs/remap-probe.bin" "$B/logs/remap-probe.o"
rm -f "$B/logs/remap-probe.rmeta" "$B/logs/remap-probe.o" "$B/logs/remap-probe.bin"
export RUSTFLAGS="$RUST_REMAP" CPPFLAGS="$C_REMAP" LDFLAGS="-Wl,-S"

# 2. cryptography（maturin の PEP 517。abi3 の tag は sdist の設定のまま）
rm -rf "$B/src/cryptography-50.0.2" "$B/wheels-raw"
tar -xzf "$B/dl/cryptography-50.0.2.tar.gz" -C "$B/src"
(
  cd "$B/src/cryptography-50.0.2"
  OPENSSL_STATIC=1 OPENSSL_DIR="$STAGE$PREFIX" CARGO_TARGET_DIR="$B/cargo-target" \
    python -m pip wheel --no-build-isolation --no-deps --disable-pip-version-check --wheel-dir "$B/wheels-raw" .
) > "$B/logs/cryptography.log" 2>&1

# 3. cbor2（setuptools-rust）。setup.py が無いので setuptools を直に呼ぶ。
rm -rf "$B/src/cbor2-6.1.4"
tar -xzf "$B/dl/cbor2-6.1.4.tar.gz" -C "$B/src"
(
  cd "$B/src/cbor2-6.1.4"
  CARGO_TARGET_DIR="$B/cargo-target" python -c "import setuptools; setuptools.setup()" \
    bdist_wheel --plat-name macosx-13.0-x86_64 --dist-dir "$B/wheels"
) > "$B/logs/cbor2.log" 2>&1

# 4. ckzg（setup.py）
rm -rf "$B/src/ckzg-2.1.8"
tar -xzf "$B/dl/ckzg-2.1.8.tar.gz" -C "$B/src"
(
  cd "$B/src/ckzg-2.1.8"
  python setup.py bdist_wheel --plat-name macosx-13.0-x86_64 --dist-dir "$B/wheels"
) > "$B/logs/ckzg.log" 2>&1

# 5. argon2-cffi-bindings（scikit-build-core。abi3 の tag は sdist の設定のまま）
rm -rf "$B/src/argon2_cffi_bindings-26.1.0"
tar -xzf "$B/dl/argon2_cffi_bindings-26.1.0.tar.gz" -C "$B/src"
(
  cd "$B/src/argon2_cffi_bindings-26.1.0"
  python -m pip wheel --no-build-isolation --no-deps --disable-pip-version-check --wheel-dir "$B/wheels" .
) > "$B/logs/argon2.log" 2>&1

# 6. cryptography の wheel の仕上げ: OpenSSL のライセンスを足す。maturin が作る SBOM（dist-info/sboms/*.json）に入る
#    組み立て機の道は、上の置き換えと同じ対応で固定の道にする。ほかの file（Mach-O を含む）のバイトは変えない。
tar -xzOf "$B/dl/openssl-$OPENSSL_VERSION.tar.gz" "openssl-$OPENSSL_VERSION/LICENSE.txt" > "$B/logs/OPENSSL-LICENSE.txt"
python "$(dirname "$0")/add_openssl_license.py" "$B"/wheels-raw/cryptography-50.0.2-*.whl "$B/logs/OPENSSL-LICENSE.txt" "$B/wheels" \
  "$H=/siglume-build/home" "$T=/siglume-build/tools" "$B=/siglume-build/work"

(cd "$B/wheels" && ls -l && shasum -a 256 ./*.whl)
