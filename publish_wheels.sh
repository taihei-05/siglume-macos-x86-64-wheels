#!/bin/sh
# 4つの wheel を taihei-05/siglume-macos-x86-64-wheels の release に置き、認証なしで取り直して照らす台本。
# 上書きしない（--clobber を使わない。tag が既にあれば gh が止まる）。引数: wheels のフォルダー、取り直しの作業フォルダー。
set -eu
W=$1
D=$2
REPO=taihei-05/siglume-macos-x86-64-wheels
BUILD_NOTE="Built from the unmodified upstream sdist on an Intel Mac (macOS 15.8.2) with python.org CPython 3.11.9, Rust 1.98.1 and MACOSX_DEPLOYMENT_TARGET=13.0 by build_macos_x86_64_wheels.sh in this repository (the build-machine paths in the cryptography SBOM are replaced by the script). Pin the asset URL and SHA-256."

# tag、wheel、SHA-256、上流の sdist の SHA-256、追記
publish() {
  echo "$3  $W/$2" | shasum -a 256 -c -
  gh release create "$1" "$W/$2" --repo "$REPO" --target main --title "$1" \
    --notes "$2

SHA-256: $3
Upstream sdist SHA-256: $4

$BUILD_NOTE $5"
}

mkdir -p "$D"
publish cryptography-50.0.2-openssl-4.0.3 cryptography-50.0.2-cp311-abi3-macosx_13_0_x86_64.whl \
  2afa66a7a6e7d2c387333085d883c7595b245b8c1743b2c46ef9b385db028e3e \
  7b46165bb56eb4704e2eaaf86f3c940d19154535d9b0ca7d6d590b04060e00d5 \
  "Statically links OpenSSL 4.0.3 (source SHA-256 325b5c806167c13b40b1ffeadfe0248197c00eccc4cf123ec1e28d2d2fd216d9). OpenSSL make test passed (Files=368, Tests=4124). Upstream cryptography tests on this wheel: 4469 passed, 0 failed, 212 skipped."
publish cbor2-6.1.4 cbor2-6.1.4-cp311-cp311-macosx_13_0_x86_64.whl \
  5e1d9aac4e5a6cbee4fb84beece4a84cdeccbeb88ccb5cc80ffddfa65c392c37 \
  01ecc79a28f33d17331943ce508fc1e21f4b06553c73f874f4c77120d72b2ef9 ""
publish ckzg-2.1.8 ckzg-2.1.8-cp311-cp311-macosx_13_0_x86_64.whl \
  88c810afe427119c99f257e5315dad9c1b64d2bf1e3b2e7dac7541f40684059c \
  d7bef6b425dca6995457fc59fc5b30211d9b28cbbeee0e7a7bef1372e13f29ca ""
publish argon2-cffi-bindings-26.1.0 argon2_cffi_bindings-26.1.0-cp310-abi3-macosx_13_0_x86_64.whl \
  b65c3a665c670622011afa67b1a54758a760476b9089bfc80a7577faeaa064b3 \
  63505c71542a44b68b1e38060450fb006404170da375feb31af153e7f9c6205d ""

# 認証なしで取り直して照らす
check() {
  curl -fsSL --retry 3 -o "$D/$2" "https://github.com/$REPO/releases/download/$1/$2"
  echo "$3  $D/$2" | shasum -a 256 -c -
}
check cryptography-50.0.2-openssl-4.0.3 cryptography-50.0.2-cp311-abi3-macosx_13_0_x86_64.whl 2afa66a7a6e7d2c387333085d883c7595b245b8c1743b2c46ef9b385db028e3e
check cbor2-6.1.4 cbor2-6.1.4-cp311-cp311-macosx_13_0_x86_64.whl 5e1d9aac4e5a6cbee4fb84beece4a84cdeccbeb88ccb5cc80ffddfa65c392c37
check ckzg-2.1.8 ckzg-2.1.8-cp311-cp311-macosx_13_0_x86_64.whl 88c810afe427119c99f257e5315dad9c1b64d2bf1e3b2e7dac7541f40684059c
check argon2-cffi-bindings-26.1.0 argon2_cffi_bindings-26.1.0-cp310-abi3-macosx_13_0_x86_64.whl b65c3a665c670622011afa67b1a54758a760476b9089bfc80a7577faeaa064b3
