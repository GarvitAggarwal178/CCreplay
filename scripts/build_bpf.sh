#!/usr/bin/env bash
# Rebuild host-specific recorder products without writing into source/evidence.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
CONTROLLER=all
VARIANT=production
while [[ $# -gt 0 ]]; do
  case "$1" in
    --controller) CONTROLLER="${2:?missing controller}"; shift 2 ;;
    --variant) VARIANT="${2:?missing variant}"; shift 2 ;;
    --help) echo 'Usage: scripts/build_bpf.sh [--controller all|reno|cubic|covegas] [--variant production|norecord]'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
case "$CONTROLLER" in all|reno|cubic|covegas) ;; *) echo 'Unknown controller' >&2; exit 2 ;; esac
case "$VARIANT" in
  production) ;;
  norecord) echo 'norecord source is absent in this older checkout; restore bpf/diagnostic/reno_wrapper_norecord.bpf.c and its matching build procedure from the original audit source before use.' >&2; exit 2 ;;
  *) echo 'Unknown variant' >&2; exit 2 ;;
esac
for tool in clang bpftool cc pkg-config; do
  command -v "$tool" >/dev/null || { echo "Required build tool missing: $tool" >&2; exit 2; }
done
[[ -r /sys/kernel/btf/vmlinux ]] || { echo 'Kernel BTF missing: /sys/kernel/btf/vmlinux' >&2; exit 2; }
pkg-config --exists libbpf || { echo 'libbpf development package missing' >&2; exit 2; }
case "$(uname -m)" in
  x86_64) TARGET_ARCH=x86 ;;
  aarch64) TARGET_ARCH=arm64 ;;
  *) echo 'Unsupported build architecture; verify source assumptions before extending' >&2; exit 2 ;;
esac
OUT=build_local
mkdir -p "$OUT"
bpftool btf dump file /sys/kernel/btf/vmlinux format c > "$OUT/vmlinux.h.tmp"
mv "$OUT/vmlinux.h.tmp" "$OUT/vmlinux.h"
read -r -a BPF_CFLAGS <<< "$(pkg-config --cflags libbpf)"
read -r -a BPF_LIBS <<< "$(pkg-config --libs libbpf)"
for controller in reno cubic covegas; do
  [[ "$CONTROLLER" == all || "$CONTROLLER" == "$controller" ]] || continue
  case "$controller" in
    reno) LOADER=user/ccr_recorder.c; BINARY=ccr_recorder ;;
    *) LOADER="user/ccr_recorder_${controller}.c"; BINARY="ccr_recorder_${controller}" ;;
  esac
  clang -target bpf -D"__TARGET_ARCH_${TARGET_ARCH}" -g -O2 \
    -I "$OUT" -I bpf "${BPF_CFLAGS[@]}" \
    -c "bpf/${controller}_wrapper.bpf.c" -o "$OUT/${controller}_wrapper.bpf.o"
  bpftool gen skeleton "$OUT/${controller}_wrapper.bpf.o" > "$OUT/${controller}_wrapper.skel.h.tmp"
  mv "$OUT/${controller}_wrapper.skel.h.tmp" "$OUT/${controller}_wrapper.skel.h"
  cc -g -O2 -I "$OUT" "${BPF_CFLAGS[@]}" "$LOADER" -o "$OUT/$BINARY" "${BPF_LIBS[@]}"
  echo "Built $OUT/$BINARY"
done
{
  uname -a
  clang --version
  bpftool version
  pkg-config --modversion libbpf
  sha256sum bpf/*wrapper.bpf.c bpf/ccr_event*.h "$OUT/vmlinux.h"
} > "$OUT/BUILD_INFO.txt"
echo 'Build complete. No controller was loaded; host compatibility requires a separate recording/self-replay check.'
python3 - <<'PY'
import hashlib,json,pathlib,platform
out=pathlib.Path('build_local')
paths=[p for p in out.glob('ccr_recorder*') if p.is_file()]+list(pathlib.Path('bpf').glob('*wrapper.bpf.c'))+list(pathlib.Path('bpf').glob('ccr_event*.h'))
data={'kernel':platform.release(),'artifacts':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(out/'BUILD_INFO.json').write_text(json.dumps(data,indent=2)+'\n')
PY
