# Verification Checkpoints

This file records concrete checkpoints that were verified on the current branch,
so later refactoring can return to a known-good state.

## add-yaneuraou-python

Verified on 2026-03-15.

- `yaneuraou_python/tools/engine_invoker.py` can run a self-play smoke test.
- If `--book_file` is omitted, self-play starts from `startpos`.
- MultiPV candidate logging works with `--multipv` and `--save_candidates`.
- The smoke test completed one game with:
  - `--parallel_games 1`
  - `--engine_threads 1`
  - `--loop 1`
  - `--time d1`
- Outputs were generated as:
  - `.sfen` game record
  - `.jsonl` candidate sidecar
  - communication log

Smoke test environment:

- engine binary: `source/YaneuraOu-apple_m2`
- eval file: `source/eval/nn.bin`
- temporary self-play home:
  - `exe/YaneuraOu-apple_m2`
  - `eval/testeval/nn.bin`

Important fixes included in the branch state used for this verification:

- `USI_Hash` is used instead of the old `Hash` option name.
- `setoption name MinimumThinkingTime ...` is used with the proper USI syntax.
- `EngineState` is compared as an enum, not as string literals.
- Python 3 integer division issues (`i//2`) are fixed in the self-play path.
- The unconditional `EvalShare` option send was removed.

## refactor

Verified on 2026-03-15.

Latest full clean-build checkpoint:

- commit: `b77dce62`
- verified with:
  - `make -C source clean`
  - `make -C source normal APPLE_CPU=native -j4`
- result:
  - full rebuild from a clean object state completed successfully
  - linked output: `source/YaneuraOu-native`

- `source/YaneuraOu-apple_m2` builds successfully with:
  - `make -C source normal APPLE_CPU=native -j4`
- `source/eval/nn.bin` is loaded successfully by the engine.
- The following interactive USI flow was verified:
  - `usi`
  - `isready`
  - `position startpos`
  - `go depth 1`
  - `bestmove ...`
- The engine also passed the same one-game self-play smoke test used on
  `add-yaneuraou-python`.

Important fixes included in the branch state used for this verification:

- `source/usi.cpp` copies global `Options` after `Eval::add_options()`, so
  `EVAL_LEARN` builds no longer break `setoption` with duplicated option ids.
- `yaneuraou_python/tools/engine_invoker.py` can launch a minimal self-play run
  from the initial position and emit `.sfen` and `.jsonl` outputs.
