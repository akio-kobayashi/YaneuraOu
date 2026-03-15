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
