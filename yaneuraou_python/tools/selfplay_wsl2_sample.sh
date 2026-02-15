#!/usr/bin/env bash
set -euo pipefail

# Sample self-play runner for WSL2.
# - Windows .exe can be executed directly via /mnt/c/... paths.
# - engine_invoker.py expects --home to contain:
#   - exe/
#   - eval/
#   - book/records2016_10818.sfen

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1) Set your YaneuraOu "home" directory.
# Example layout:
#   /mnt/d/shogi_home/
#     ├── exe/
#     ├── eval/
#     └── book/records2016_10818.sfen
HOME_DIR="/mnt/d/shogi_home"

# 2) Engine and eval settings.
# Use absolute WSL paths for Windows executables.
# (Optional conversion from Windows path:
#   ENGINE_EXE="$(wslpath -u 'C:\path\to\YaneuraOu.exe')"
# )
ENGINE_EXE="/mnt/c/Users/yourname/engines/YaneuraOu-by-gcc.exe"
EVAL_DIR="nnue/eval"  # relative to ${HOME_DIR}/eval

# 3) Match conditions.
PARALLEL_GAMES=2
ENGINE_THREADS=1
TOTAL_GAMES=200

# Time control examples:
#   "d12"                : fixed depth 12
#   "b1000"              : byoyomi 1000ms
#   "t300000/i3000"      : 5min + 3sec increment
#   "b1000.b2000"        : different settings for engine1/engine2
TIME_CONTROL="d12"

# Opening book:
#   >0 : use records2016_10818.sfen prefix moves
#   0  : effectively no opening prefix
BOOK_MOVES=24
RAND_BOOK="--rand_book"

# Kifu output format: sfen or csa
KIFU_FORMAT="csa"

# Optional logging flags
LOG_FLAG="--log"
PARAM_LOG_PATH="" # e.g. "logs/params"

ARGS=(
  --home "${HOME_DIR}"
  --engine1 "${ENGINE_EXE}"
  --eval1 "${EVAL_DIR}"
  --engine2 "${ENGINE_EXE}"
  --eval2 "${EVAL_DIR}"
  --parallel_games "${PARALLEL_GAMES}"
  --engine_threads "${ENGINE_THREADS}"
  --loop "${TOTAL_GAMES}"
  --time "${TIME_CONTROL}"
  --book_moves "${BOOK_MOVES}"
  --kifu_format "${KIFU_FORMAT}"
)

if [[ -n "${RAND_BOOK}" ]]; then
  ARGS+=("${RAND_BOOK}")
fi

if [[ -n "${LOG_FLAG}" ]]; then
  ARGS+=("${LOG_FLAG}")
fi

if [[ -n "${PARAM_LOG_PATH}" ]]; then
  ARGS+=(--param_log_path "${PARAM_LOG_PATH}")
fi

python3 "${SCRIPT_DIR}/engine_invoker.py" "${ARGS[@]}"
