# YaneuraOu Python Wrapper

A Python wrapper for the YaneuraOu shogi engine's legal move generation functionality, implemented using `pybind11`. This module allows Python programs to efficiently generate legal moves from a given shogi position (SFEN string).

## Features

-   Generate all legal moves from an SFEN position.
-   For each move, get the `from` square, `to` square, and the SFEN string of the position after the move.
-   High performance by directly calling YaneuraOu's C++ move generation logic.
-   Installable via `pip`.

## Installation

```bash
# First, ensure you have Git and CMake installed.
# Clone this repository (including YaneuraOu as a submodule)
git clone --recursive https://github.com/yaneuraou/yaneuraou-python-wrapper.git # Replace with actual repo if created
cd yaneuraou-python-wrapper

# Install the Python package
pip install .
```

## Usage

```python
import yaneuraou_wrapper

# Example SFEN for initial position
sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"

# Get legal moves information
moves_info = yaneuraou_wrapper.get_legal_moves_info(sfen)

for info in moves_info:
    print(f"Move: {info['usi']}, From: {info['from']}, To: {info['to']}")
    print(f"  SFEN after move: {info['sfen']}")
```

## Self-Play Tool

`tools/engine_invoker.py` can run parallel USI matches between two engines. If you use the same engine on both sides, it can be used for self-play data collection.

If `--book_file` is omitted, games start from the normal initial position. If you want to start from a prepared opening set, pass an SFEN file under `home/book` with `--book_file`.

When `--multipv` and `--save_candidates` are enabled, the tool keeps the existing `.sfen` output and also writes a JSONL sidecar file containing:

- played move sequence
- per-move normalized evaluation values
- per-move MultiPV candidate lists with score and PV
- selected move metadata for each ply
- black/white engine metadata for each game
- termination reason for each game

Experimental diversification is also available. If `--alt_move_prob` and `--alt_move_margin_cp` are set, the tool can occasionally choose a non-best move from close MultiPV candidates. Only candidates within the configured centipawn gap are eligible.

Example:

```bash
python yaneuraou_python/tools/engine_invoker.py \
  --home /path/to/home \
  --engine1 YaneuraOu-native \
  --eval1 eval \
  --engine2 YaneuraOu-native \
  --eval2 eval \
  --parallel_games 2 \
  --engine_threads 1 \
  --loop 10 \
  --time b1000 \
  --multipv 8 \
  --save_candidates
```

Example with close-candidate sampling:

```bash
python yaneuraou_python/tools/engine_invoker.py \
  --home /path/to/home \
  --engine1 YaneuraOu-native \
  --eval1 eval \
  --engine2 YaneuraOu-native \
  --eval2 eval \
  --parallel_games 1 \
  --engine_threads 1 \
  --loop 10 \
  --time d4 \
  --multipv 4 \
  --alt_move_prob 0.15 \
  --alt_move_margin_cp 20 \
  --alt_move_temperature 12 \
  --save_candidates
```

Example with an opening set:

```bash
python yaneuraou_python/tools/engine_invoker.py \
  --home /path/to/home \
  --engine1 YaneuraOu-native \
  --eval1 eval \
  --engine2 YaneuraOu-native \
  --eval2 eval \
  --book_file records2016_10818.sfen \
  --book_moves 24
```

## SPRT Match Tool

`tools/sprt_match.py` runs matches between two USI engines and stops early when the Sequential Probability Ratio Test reaches a decision.

By default, the tool uses a paired-opening pentanomial SPRT. Each opening is played twice with reversed colors, and the resulting two-game score is classified into one of five categories: `0`, `0.5`, `1`, `1.5`, `2`.

If you want a simpler non-paired test, `--sprt_mode trinomial` switches to a per-game `win / draw / loss` SPRT.

Main options:

- `--elo0`: lower Elo hypothesis
- `--elo1`: upper Elo hypothesis
- `--alpha`: type-I error rate
- `--beta`: type-II error rate
- `--sprt_mode`: `pentanomial` or `trinomial`
- `--min_pairs`: minimum number of finished opening pairs before allowing early stop in pentanomial mode
- `--min_games`: minimum number of finished games before allowing early stop in trinomial mode
- `--max_games`: hard cap if SPRT stays inconclusive

Example:

```bash
python yaneuraou_python/tools/sprt_match.py \
  --home /path/to/home \
  --engine1 YaneuraOu-native \
  --eval1 eval_a \
  --engine2 YaneuraOu-native \
  --eval2 eval_b \
  --parallel_games 2 \
  --engine_threads 1 \
  --time b1000 \
  --book_file records2016_10818.sfen \
  --book_moves 24 \
  --sprt_mode pentanomial \
  --elo0 0 \
  --elo1 5 \
  --alpha 0.05 \
  --beta 0.05 \
  --min_pairs 20 \
  --max_games 2000 \
  --report_every 20
```

Typical output contains:

- current `W/D/L`
- completed pair count in pentanomial mode
- score rate and estimated Elo
- current `llr`
- SPRT boundaries
- fitted `H0` / `H1` probability model

Pentanomial mode notes:

- it reuses the same opening twice on the same worker thread, once for each color assignment
- it works with `--book_file`, but also works without one by pairing two games from the normal initial position
- an odd unfinished pair at the `--max_games` limit is ignored by the pentanomial LLR until its mate game is completed

Trinomial mode example:

```bash
python yaneuraou_python/tools/sprt_match.py \
  --home /path/to/home \
  --engine1 YaneuraOu-native \
  --eval1 eval_a \
  --engine2 YaneuraOu-native \
  --eval2 eval_b \
  --sprt_mode trinomial \
  --elo0 0 \
  --elo1 5 \
  --min_games 40
```

Decision meaning:

- `decision=accept_h1`: engine1 is supported over `elo1` against engine2 under the configured SPRT settings
- `decision=accept_h0`: engine1 is supported at or below `elo0`
- `decision=inconclusive`: `max_games` was reached before crossing either boundary

If `--config` is used, `PyYAML` is required. Without `--config`, the script runs without that dependency.

## Converting Self-Play Output to CSA

`tools/selfplay_to_csa.py` converts the `.sfen` / `.jsonl` pair generated by `engine_invoker.py` into per-game `.csa` files.

The generated CSA files contain:

- the played move sequence
- one `\'** ...` comment line per move with the normalized evaluation
- optional MultiPV candidate metadata embedded into the same move comment

Example:

```bash
python yaneuraou_python/tools/selfplay_to_csa.py \
  20260315182534T1_d1.sfen \
  --jsonl-file 20260315182534T1_d1.jsonl \
  --output-dir out_csa \
  --engine1-name YaneuraOu \
  --engine2-name YaneuraOu
```

By default, draw records are exported as `%SENNICHITE`. If you need a different draw marker, use `--draw-endgame`.

## Original Project Reference

This Python wrapper heavily relies on the high-performance C++ move generation and position representation logic from the **YaneuraOu Shogi Engine**.

-   **YaneuraOu GitHub Repository**: [https://github.com/yaneuraou/YaneuraOu](https://github.com/yaneuraou/YaneuraOu)

We express our deepest gratitude to the Yaneuraou development team for their outstanding work.

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**.
This is due to its direct incorporation and linking with the YaneuraOu source code, which is also licensed under GPLv3.

You can find a copy of the license text in the `COPYING` file or at [https://www.gnu.org/licenses/gpl-3.0.en.html](https://www.gnu.org/licenses/gpl-3.0.en.html).
