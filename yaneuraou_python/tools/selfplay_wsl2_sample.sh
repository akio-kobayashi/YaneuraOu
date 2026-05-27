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
HOME_DIR="/mnt/d/shogi_home"

# 2) Engine and eval settings.
# Use absolute WSL paths for engine binaries.
# (Optional conversion from Windows path:
#   ENGINE_EXE="$(wslpath -u 'C:\path\to\YaneuraOu.exe')"
# )
ENGINE_EXE="/mnt/c/Users/yourname/engines/YaneuraOu-by-gcc.exe"
EVAL_DIR=""  # empty => use ${ENGINE_EXE%/*}/eval
BOOK_FILE="/Users/yourname/GitHub/engines/book/start_sfens_ply32.txt"

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
#   BOOK_FILE=""  : start from the initial position
#   BOOK_FILE=... : use the specified SFEN file
#   BOOK_MOVES>0  : truncate only startpos "moves ..." prefixes
BOOK_MOVES=24
RAND_BOOK="--rand_book"

# MultiPV / candidate move sampling:
#   MULTIPV=1            : best move only
#   MULTIPV>1            : request that many MultiPV candidates
#   ALT_MOVE_PROB=0.0    : always use best move
#   ALT_MOVE_PROB>0.0    : occasionally sample a non-best candidate
#   ALT_MOVE_MARGIN_CP<0 : disable alternative move selection
#   ALT_MOVE_TEMPERATURE : larger => flatter sampling among alternatives
MULTIPV=1
ALT_MOVE_PROB=0.0
ALT_MOVE_MARGIN_CP=-1
ALT_MOVE_TEMPERATURE=12.0

# Kifu output:
#   engine_invoker.py currently saves self-play records as .sfen only.

# Optional logging flags
LOG_FLAG="--log"
PARAM_LOG_PATH="" # e.g. "logs/params"

ARGS=(
  --home "${HOME_DIR}"
  --engine1 "${ENGINE_EXE}"
  --engine2 "${ENGINE_EXE}"
  --parallel_games "${PARALLEL_GAMES}"
  --engine_threads "${ENGINE_THREADS}"
  --loop "${TOTAL_GAMES}"
  --time "${TIME_CONTROL}"
  --book_moves "${BOOK_MOVES}"
  --multipv "${MULTIPV}"
  --alt_move_prob "${ALT_MOVE_PROB}"
  --alt_move_margin_cp "${ALT_MOVE_MARGIN_CP}"
  --alt_move_temperature "${ALT_MOVE_TEMPERATURE}"
)

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
