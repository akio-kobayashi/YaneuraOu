#!/usr/bin/env bash
set -euo pipefail

# Sample self-play runner for WSL2.
# - Windows .exe can be executed directly via /mnt/c/... paths.
# - engine_invoker.py uses engine paths as given.
# - --home is used only as the base for relative eval/book paths.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1) Set your YaneuraOu "home" directory.
# Example layout:
#   /mnt/d/shogi_home/
#     ├── eval/
#     └── book/
HOME_DIR="/mnt/c/Users/akiok/AobaNNUE"

# 2) Engine and eval settings.
# Use absolute WSL paths for engine binaries.
# (Optional conversion from Windows path:
#   ENGINE_EXE="$(wslpath -u 'C:\path\to\YaneuraOu.exe')"
# )
ENGINE_EXE="/mnt/c/Users/akiok/AobaNNUE/AobaNNUE_ZEN2.exe"
EVAL_DIR=""  # empty => use ${ENGINE_EXE%/*}/eval
#BOOK_FILE="/mnt/c/Users/akiok/AobaNNUE/book/start_sfens_ply32.txt"

# 3) Match conditions.
PARALLEL_GAMES=1
ENGINE_THREADS=16
TOTAL_GAMES=100000

# Time control examples:
#   "d12"                : fixed depth 12
#   "b1000"              : byoyomi 1000ms
#   "t300000/i3000"      : 5min + 3sec increment
#   "b1000.b2000"        : different settings for engine1/engine2
TIME_CONTROL="n200000"

# Opening book:
#   BOOK_FILE=""  : start from the initial position
#   BOOK_FILE=... : use the specified SFEN file
#   BOOK_MOVES>0  : truncate only startpos "moves ..." prefixes
BOOK_FILE=""
BOOK_MOVES=24
RAND_BOOK="--rand_book"

# Kifu output format: sfen or csa
KIFU_FORMAT="csa"

# Optional logging flags
LOG_FLAG="--log"
PARAM_LOG_PATH="" # e.g. "logs/params"

# --multipv 2 --save_candidates --alt_move_prob 0.05 --alt_move_margin_cp 10
ARGS=(
  --home "${HOME_DIR}"
  --engine1 "${ENGINE_EXE}"
  --engine2 "${ENGINE_EXE}"
  --parallel_games "${PARALLEL_GAMES}"
  --engine_threads "${ENGINE_THREADS}"
  --loop "${TOTAL_GAMES}"
  --time "${TIME_CONTROL}"
  --book_moves "${BOOK_MOVES}"
#  --kifu_format "${KIFU_FORMAT}"
)

MULTIPV=2
PROB=0.05
MARGIN=100
TEMP=1.0

if [[ -n "${TEMP}" ]]; then
    ARGS+=(--alt_move_temperature "${TEMP}")
fi
if [[ -n "${MULTIPV}" ]]; then
    ARGS+=(--multipv "${MULTIPV}")
    ARGS+=(--save_candidates)
fi

if [[ -n "${PROB}" ]]; then
    ARGS+=(--alt_move_prob "${PROB}")
fi

if [[ -n "${MARGIN}" ]]; then
    ARGS+=(--alt_move_margin_cp "${MARGIN}")
fi

if [[ -n "${EVAL_DIR}" ]]; then
  ARGS+=(--eval1 "${EVAL_DIR}" --eval2 "${EVAL_DIR}")
fi

if [[ -n "${BOOK_FILE}" ]]; then
  ARGS+=(--book_file "${BOOK_FILE}")
fi

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
