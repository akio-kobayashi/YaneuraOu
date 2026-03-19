# Evaluation Dependency Audit

This document records where search currently depends on evaluation-value meaning and scale.

Primary references:
- [`docs/eval_value_contract.md`](/Users/akio/Documents/GitHub/YaneuraOu/docs/eval_value_contract.md)
- [`docs/refactor_roadmap.md`](/Users/akio/Documents/GitHub/YaneuraOu/docs/refactor_roadmap.md)

## Scope

Audited files:
- [`source/engine/yaneuraou-engine/yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)
- [`source/engine/yaneuraou-engine/yaneuraou-search.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.h)
- [`source/search.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/search.h)
- [`source/eval/nnue/evaluate_nnue.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/evaluate_nnue.cpp)

## Main Findings

### A. Search directly consumes evaluator-domain values as pruning inputs

Examples:
- razoring threshold uses `eval < alpha - 514 - 294 * depth * depth`
  - [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)
- child futility uses a depth-dependent margin applied directly to `eval`
  - [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)
- null move condition uses `ss->staticEval >= beta - 18 * depth + 390`
  - [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)
- probcut uses `probCutBeta = beta + 224 - 64 * improving`
  and `probCutDepth = depth - 5 - (ss->staticEval - beta) / 306`
  - [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)
- capture and quiet futility pruning use direct arithmetic on `ss->staticEval`
  - [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Assessment:
- High priority
- These are the main places where evaluator scale leaks into search behavior.

### B. `staticEval` mixes at least three meanings

Observed meanings:
- raw evaluator output via `evaluate(pos)`
- corrected static evaluation via `to_corrected_static_eval(...)`
- transposition-table value reused as a better estimate than local eval

Examples:
- `unadjustedStaticEval = evaluate(pos);`
- `ss->staticEval = eval = to_corrected_static_eval(unadjustedStaticEval, correctionValue);`
- `if (is_valid(ttData.value) ... ) eval = ttData.value;`
  - [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Assessment:
- Highest priority
- This is the core semantic ambiguity that the refactor must resolve.

### C. TT values and evaluator values are partially blended

Examples:
- TT eval reused when `ttData.eval` is valid
- TT search score can replace local static eval estimate under bound checks
- `value_to_tt()` / `value_from_tt()` coexist with direct `ttData.value` comparisons
  - [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Assessment:
- High priority
- TT values belong to the search-score domain, while static eval should remain distinct.

### D. History and ordering updates depend on static eval differences

Examples:
- bonus based on `(ss - 1)->staticEval + ss->staticEval`
- `improving` and `opponentWorsening` computed from static eval comparisons
- depth adjustments depend on sums/comparisons of static eval values
  - [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Assessment:
- High priority
- These uses may remain valid, but they must consume a clearly defined normalized static-eval domain.

### E. QSearch has the same semantic mixing problem

Examples:
- qsearch computes `unadjustedStaticEval`
- immediately converts it with `to_corrected_static_eval(...)`
- then uses the result for stand-pat, futility base, and alpha updates
  - [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Assessment:
- High priority
- Any static-eval contract must apply to both main search and qsearch.

### F. Evaluator entry points are too weakly named

Examples:
- `Eval::evaluate(pos)`
- `Eval::compute_eval(pos)`
- `Eval::evaluate_with_no_return(pos)`
  - [`evaluate_nnue.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/evaluate_nnue.cpp)

Assessment:
- Medium priority
- Current naming does not expose score semantics clearly enough.

## Immediate Refactor Implications

The first code changes should not try to remove all numeric tuning.
They should instead introduce explicit boundaries.

### Required boundary split

At minimum, search should distinguish:
- raw evaluator output
- normalized static eval
- search score

### First concrete code target

Introduce named conversion helpers and migrate call sites to them.

Suggested initial API shape:
- `raw_eval_from_evaluator(...)`
- `normalize_static_eval(raw_eval, correction, context)`
- `search_score_from_tt(...)`

The names do not need to be final, but the semantic separation does.

## Recommended First Migration Candidates

Start with the smallest central seam:

1. [`to_corrected_static_eval(...)`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)
2. `ttData.eval` / `ttData.value` decision points
3. `improving` / `opponentWorsening`
4. null move and razoring entry conditions

These changes expose the semantic contract without immediately rewriting every pruning constant.

## Completed Initial Slices

### Slice 1: raw eval / normalized static eval / TT estimate seam

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `normalize_static_eval(...)`
- `merge_tt_into_static_eval_estimate(...)`

Purpose:
- make the first semantic boundary explicit without changing tuning constants

### Slice 2: search-entry predicates consume normalized static eval

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `is_improving_from_normalized_static_eval(...)`
- `is_opponent_worsening_from_normalized_static_eval(...)`
- `should_razor_from_normalized_static_eval(...)`
- `should_try_null_move_from_normalized_static_eval(...)`
- `probcut_beta_from_improving_flag(...)`

Purpose:
- make it explicit that these search heuristics depend on normalized static eval semantics
- keep pruning formulas stable while moving evaluator-scale assumptions behind named predicates

### Slice 3: futility and shallow-depth pruning consume normalized static eval

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `futility_margin_from_normalized_static_eval(...)`
- `should_futility_prune_child_from_normalized_static_eval(...)`
- `quiet_move_skip_threshold_from_normalized_static_eval(...)`
- `capture_futility_value_from_normalized_static_eval(...)`
- `quiet_futility_value_from_normalized_static_eval(...)`
- `qsearch_futility_base_from_normalized_static_eval(...)`

Purpose:
- isolate evaluator-scale assumptions inside named futility helpers
- keep capture/quiet futility and qsearch futility base tied to normalized static eval semantics

### Slice 4: correction/history updates consume normalized static eval deltas

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `search_outcome_delta_from_normalized_static_eval(...)`
- `is_large_fail_low_against_normalized_static_eval(...)`
- `is_opponent_large_fail_low_against_normalized_static_eval(...)`
- `should_apply_correction_history_from_normalized_static_eval(...)`
- `correction_history_bonus_from_normalized_static_eval_delta(...)`
- `correction_history_scale_from_normalized_static_eval_delta(...)`

Purpose:
- make fail-low bonus and correction-history updates explicitly depend on search-outcome versus normalized-static-eval deltas
- keep existing tuning while reducing direct score-scale arithmetic at the call sites

### Slice 5: qsearch stand-pat semantics use named helpers

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `soften_qsearch_stand_pat_fail_high(...)`
- `qsearch_alpha_from_stand_pat(...)`
- `qsearch_capture_futility_value_from_normalized_static_eval(...)`

Purpose:
- make qsearch stand-pat updates explicit instead of leaving semantic meaning inside inline arithmetic
- keep qsearch futility estimates tied to normalized static eval semantics

### Slice 6: TT search-score decoding and cutoff checks use named helpers

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `search_score_from_tt_entry(...)`
- `tt_bound_allows_search_score_cutoff(...)`

Purpose:
- make it explicit that `ttData.value` belongs to the search-score domain, not the normalized-static-eval domain
- centralize TT score decoding and cutoff-bound interpretation for both main search and qsearch

### Slice 7: TT writeback and repetition/max-move draw scores use named helpers

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `search_score_for_tt_storage(...)`
- `tt_bound_for_completed_search_result(...)`
- `tt_bound_for_non_exact_search_result(...)`
- `repetition_search_score(...)`
- `max_move_draw_search_score(...)`

Purpose:
- make TT writeback explicitly operate in the search-score domain instead of repeating inline `value_to_tt(...)` conversions and bound selection rules
- centralize repetition and max-move draw outcomes as search-score helpers, including cases where draw handling can return mate-like values

### Slice 8: terminal draw and no-legal-move outcomes use named search-score helpers

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `plain_draw_search_score()`
- `search_score_is_below_draw(...)`
- `no_legal_move_search_score(...)`

Purpose:
- make plain draw outcomes explicit in the search-score domain instead of scattering `VALUE_DRAW`
- make no-legal-move terminal returns use a named helper that distinguishes excluded-move, mate, and draw cases

### Slice 9: shogi terminal mate returns use named helpers

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `checkmated_search_score(...)`
- `shogi_no_legal_move_search_score(...)`

Purpose:
- remove remaining direct `mated_in(...)` call sites from shogi-specific terminal branches that conceptually belong to the search-score domain
- make root no-move, main-search no-legal-move, qsearch in-check no-legal-move, and mate-distance alpha floor updates speak the same named search-score language

### Slice 10: evaluator entry points are routed through a transitional context

Implemented in:
- [`yaneuraou-search.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.h)
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `Search::EvaluationContext`
- `EvaluationContext::prepare_for_descend(...)`
- `EvaluationContext::evaluate(...)`

Purpose:
- stop spreading direct `Eval::evaluate(...)` and `Eval::evaluate_with_no_return(...)` calls through search control flow
- introduce the first stable evaluator-facing wrapper without changing current `Position` and `StateInfo` ownership

### Slice 11: classic NNUE state is accessed through `Position` helpers

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)
- [`evaluate_nnue.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/evaluate_nnue.cpp)
- [`nnue_feature_transformer.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/nnue_feature_transformer.h)

Added helpers:
- `Position::nnue_accumulator()`
- `Position::mutable_nnue_accumulator()`
- `Position::previous_nnue_accumulator()`
- `Position::invalidate_nnue_accumulator()`
- `Position::invalidate_nnue_score()`

Purpose:
- reduce direct `state()->accumulator` coupling in classic NNUE code paths
- make future movement of evaluator-local state out of `StateInfo` possible without forcing search or NNUE code to know the storage layout

### Slice 12: classic-eval material, dirty-piece, and eval-sum state use `Position` accessors

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)
- [`extra/sfen_packer.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/extra/sfen_packer.cpp)
- [`eval/material/evaluate_material.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/material/evaluate_material.cpp)
- [`mate/mate_move_picker.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/mate/mate_move_picker.h)
- [`eval/nnue/features/feature_set.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/features/feature_set.h)
- [`eval/nnue/features/k.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/features/k.cpp)
- [`eval/nnue/features/p.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/features/p.cpp)
- [`eval/nnue/features/pe9.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/features/pe9.cpp)
- [`eval/nnue/features/half_kp.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/features/half_kp.cpp)
- [`eval/nnue/features/half_kp_vm.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/features/half_kp_vm.cpp)
- [`eval/nnue/features/half_relative_kp.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/features/half_relative_kp.cpp)
- [`eval/nnue/features/half_kpe9.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/nnue/features/half_kpe9.cpp)
- [`eval/kppt/evaluate_kppt.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/kppt/evaluate_kppt.cpp)
- [`eval/kpp_kkpt/evaluate_kpp_kkpt.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/eval/kpp_kkpt/evaluate_kpp_kkpt.cpp)
- [`learn/learner.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/learn/learner.cpp)

Added helpers:
- `Position::dirty_piece()`
- `Position::material_value()`
- `Position::set_material_value(...)`
- `Position::eval_sum()`
- `Position::set_eval_sum(...)`

Purpose:
- remove remaining open-coded `state()->dirtyPiece`, `state()->materialValue`, and `state()->sum` accesses from active evaluator code paths
- finish the access-boundary step for classic-eval state without changing storage ownership yet
- leave `config.h` comments as the only remaining `state()->dirtyPiece` textual reference in the tree

### Slice 13: remaining TT search-score predicates use named helpers

Implemented in:
- [`yaneuraou-search.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine/yaneuraou-engine/yaneuraou-search.cpp)

Added helpers:
- `tt_search_score_is_at_least_beta(...)`
- `tt_search_score_is_below_threshold(...)`
- `tt_search_score_supports_cutnode_assumption(...)`
- `tt_search_score_supports_small_probcut(...)`
- `tt_search_score_supports_singular_extension(...)`
- `tt_search_score_can_seed_static_eval_estimate(...)`
- `singular_beta_from_tt_search_score(...)`
- `reduction_adjustment_from_tt_search_score(...)`

Purpose:
- finish the remaining active TT search-score threshold checks that were still expressed as raw `ttData.value` predicates inside main search
- leave TT decode, return, and writeback operations as the intentional low-level primitives for the search-score domain

Phase A completion note:
- With Slice 13, the active search-path score semantics work is complete under the roadmap definition.
- Remaining direct `ttData.value` comparisons in this file are confined to disabled `#if 0` code or explanatory comments.

### Slice 14: classic NNUE accumulator storage moves behind `Position` ownership

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `StateInfo` no longer embeds a classic NNUE `Accumulator` object directly.
- `StateInfo` now keeps only a sidecar pointer.
- `Position` owns and binds accumulator slots while preserving the existing `nnue_accumulator()` / `mutable_nnue_accumulator()` / `previous_nnue_accumulator()` accessors.

Purpose:
- start Phase C with the accumulator-like cache family recommended by the roadmap
- remove the largest active evaluator-owned storage object from `StateInfo` without forcing evaluator call-site churn
- preserve null-move accumulator reuse by cloning the previous sidecar state before invalidating score-only cache bits

Verification note:
- the affected release-build translation units compile successfully
- a full clean link is currently blocked by pre-existing unresolved-symbol issues in the top-level `normal` / `tournament` targets, so full-engine runtime validation remains pending after that separate build issue is addressed

### Slice 15: classic evaluator state moves behind `Position` ownership

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `StateInfo` no longer embeds classic evaluator-owned `materialValue`, `EvalSum`, or `DirtyPiece` storage directly.
- `StateInfo` now keeps a classic-eval sidecar pointer.
- `Position` owns and binds classic sidecar slots while preserving existing `material_value(...)`, `eval_sum(...)`, and `dirty_piece(...)` accessors.

Purpose:
- continue Phase C with the remaining classic evaluator-owned state family after the NNUE accumulator move
- keep active evaluator, learner, and move-update code on the existing accessor seam while removing inline `StateInfo` ownership
- preserve null-move classic-eval semantics by cloning the previous sidecar state before continuing with score/cache invalidation

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds after the target object-directory split fix
- the resulting tournament binary passes `usi`, `isready`, short `go movetime`, and `quit`

### Slice 16: thread root positions own the active evaluator-storage compatibility object

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)
- [`thread.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/thread.h)
- [`thread.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/thread.cpp)

Changed seam:
- `Position` now treats `EvaluatorStorage` as a bindable compatibility object instead of an always-self-owned allocation.
- Non-search callers still get a local fallback allocation path through `bind_evaluator_storage()`.
- Search-thread root positions bind `EvaluatorStorage` from `Thread` scope, so active search no longer depends on `Position` owning the evaluator sidecars itself.

Purpose:
- continue Phase C by moving evaluator-storage ownership one step outward from `Position`
- keep the existing `Position` accessors and sidecar binding rules stable while changing only the lifetime owner
- prepare for later worker-context or NUMA-local ownership work without forcing unrelated helper-tool call sites to move at the same time

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, and `quit`

### Slice 17: evaluator-storage cleanup is owned by the compatibility object itself

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position::EvaluatorStorage` now exposes `reset()` and owns teardown of NNUE slots, classic-eval slots, and `EvalList` clearing.
- `Position` now decides only whether storage is externally bound or locally owned, and delegates teardown of active sidecars to the storage object.

Purpose:
- keep Phase C moving by shrinking `Position`'s direct knowledge of evaluator-storage internals
- make later movement of the compatibility object into worker or thread context simpler, because cleanup follows the storage object instead of the binder

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, and `quit`

### Slice 18: evaluator-storage owns slot binding for active state families

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `EvaluatorStorage` now owns slot lookup and slot creation for classic-eval state and NNUE accumulators.
- `Position` delegates `bind_classic_eval_state(...)` and `bind_nnue_accumulator(...)` to the compatibility object after choosing or binding the active storage owner.
- `EvalList` accessors on `Position` also delegate through `EvaluatorStorage`.

Purpose:
- continue shrinking `Position`'s knowledge of evaluator-state storage layout during Phase C
- make the compatibility object closer to a real worker-context owned evaluator bundle instead of a passive bag of pointers

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, and `quit`

### Slice 19: evaluator-storage reset is separated from storage-owner release

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position` now has `reset_evaluator_storage()` alongside owner-release logic.
- `Position::set()` resets active sidecars in place without saving and restoring external evaluator-storage bindings.
- External bind and detach paths now reuse the same reset-only path before changing owners.

Purpose:
- further separate storage lifetime policy from sidecar reinitialization during Phase C
- make external evaluator-storage ownership less fragile by removing ad hoc binding preservation around `Position::set()`

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, and `quit`

### Slice 20: legacy family-specific release helpers are removed from `Position`

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position` no longer exposes separate release helpers for `EvalList`, classic-eval slots, or NNUE slots.
- Active code now relies on `EvaluatorStorage::reset()` for teardown and on the per-family bind delegates already housed on `EvaluatorStorage`.

Purpose:
- reduce transitional API surface during Phase C
- make the unified evaluator-storage object the only active storage-management seam instead of carrying both new and old helper families in parallel

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, and `quit`

### Slice 21: state-level evaluator sidecar wiring is grouped behind shared helpers

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position::bind_state_evaluator_storage(...)` now handles per-state sidecar rebinding for move/setup paths.
- `Position::clone_state_evaluator_storage(...)` now handles null-move sidecar cloning for classic-eval and NNUE state families.
- `set()`, `do_move()`, and `do_null_move()` now reuse those helpers instead of open-coding evaluator-storage wiring.

Purpose:
- reduce repeated state-transition knowledge during Phase C
- keep evaluator-storage transition logic in one place so later ownership moves affect fewer call sites

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, and `quit`

### Slice 22: evaluator-storage owns state-level bind and clone operations

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `EvaluatorStorage::bind_state(...)` now owns per-state sidecar rebinding.
- `EvaluatorStorage::clone_state(...)` now owns null-move sidecar cloning.
- `Position` no longer exposes per-family bind helpers for classic-eval or NNUE state families; it forwards to the active storage owner.

Purpose:
- continue Phase C by moving state-transition ownership from `Position` into the evaluator-storage compatibility object
- reduce the remaining evaluator-state policy embedded in `Position` before later thread-context or worker-context relocation

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, and `quit`

### Slice 23: `Position` forwards through `active_evaluator_storage()`

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position` now routes eval-list access and state-transition forwarding through `active_evaluator_storage()`.
- Transitional `Position` wrapper helpers for state bind/clone and eval-list-sidecar binding are removed.
- The active storage owner remains the same, but `Position` now carries less evaluator-specific wrapper code.

Purpose:
- continue Phase C by shrinking `Position` toward an owner-selection seam rather than an evaluator-storage orchestration layer
- reduce the number of transitional wrapper entry points that must be rewritten again when storage ownership moves further outward

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, and `quit`

### Slice 24: local-versus-external storage policy is grouped behind `EvaluatorStorageBinding`

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `ownedEvaluatorStorage` and `evaluatorStorage` are replaced by `EvaluatorStorageBinding`.
- Reset, release, local fallback allocation, external bind, and external detach now live on the binding object.
- `Position` no longer open-codes raw owner-pointer transitions directly.

Purpose:
- continue Phase C by moving owner policy out of `Position` and into a dedicated compatibility object
- prepare for later relocation of evaluator storage policy into worker or thread context without keeping pointer choreography spread across `Position`

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, and `quit`

### Slice 25: external binding now attaches the whole binding policy object

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)
- [`thread.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/thread.h)
- [`thread.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/thread.cpp)

Changed seam:
- `Thread` now owns `EvaluatorStorageBinding` instead of only raw evaluator storage.
- `Position` binds external evaluator state through `set_evaluator_storage_binding(...)`.
- `Position::set()` now preserves an external binding-policy owner across `memset` instead of preserving only a raw storage pointer.

Purpose:
- move Phase C one step closer to thread-context ownership by keeping storage owner policy and storage object together
- reduce the amount of local/external ownership choreography that still lives in `Position`

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, `quit`, and a short self-play smoke test

### Slice 26: active evaluator-state access now delegates through the binding object

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `EvaluatorStorageBinding` now owns active-path delegation for eval-list access and state bind/clone transitions.
- `Position` no longer reaches through an `active_evaluator_storage()` wrapper for eval-list reads/writes or for `set()` / `do_move()` / `do_null_move()` setup.
- Active callers now talk to the binding-policy object directly, leaving `Position` with less raw knowledge of storage-selection details.

Purpose:
- keep Phase C moving by making the binding object, rather than `Position`, the direct compatibility seam for evaluator-owned state
- shrink the remaining amount of owner-policy forwarding that still lives on `Position`

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, `quit`, and a short self-play smoke test

### Slice 27: evaluator-storage lifecycle wrappers removed from Position

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position` no longer carries dedicated `reset_evaluator_storage()` / `release_evaluator_storage()` wrappers.
- Destructor cleanup, binding swaps, and `set()` reset flow now call the bound `EvaluatorStorageBinding` directly.
- Active lifecycle control is therefore one step closer to the binding-policy object and one step farther from `Position`.

Purpose:
- keep shrinking the compatibility surface on `Position`
- make the binding object the single active seam for both storage selection and storage lifecycle

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, `quit`, and a short self-play smoke test

### Slice 28: local fallback and external binding now share one selection API

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)
- [`thread.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/thread.cpp)

Changed seam:
- `Position` no longer exposes a separate API to switch back to local evaluator storage.
- `set_evaluator_storage_binding(nullptr)` now means "use the local fallback binding", while a non-null pointer installs the external binding policy.
- `Position::set()` uses the same binding-install path after `memset`, so binding restoration and normal binding swaps share one helper.

Purpose:
- shrink the public compatibility surface on `Position`
- keep Phase C moving by making local-versus-external selection a single operation instead of two separate control paths

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, `quit`, and a short self-play smoke test

### Slice 29: active binding access now flows through a Position seam

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position` now uses `active_evaluator_storage_binding()` for eval-list access, destructor cleanup, and state bind/clone transitions.
- Direct reads of the raw `evaluatorStorageBinding` member are reduced to installation and fallback selection points.
- Active callers therefore reach evaluator-owned state through a named binding seam instead of through a raw pointer member.

Purpose:
- continue shrinking the amount of implicit ownership knowledge embedded in `Position`
- make the active binding object the explicit compatibility seam for Phase C code paths

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, `quit`, and a short self-play smoke test

### Slice 30: local fallback binding access now flows through a Position seam

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position` now resolves the local fallback binding through `local_evaluator_storage_binding()`.
- Binding installation and active-binding fallback no longer reference `localEvaluatorStorageBinding` directly.
- This keeps both active and local binding selection behind named seams instead of raw member references.

Purpose:
- continue reducing fallback-policy knowledge embedded directly in `Position`
- make future binding relocation work less dependent on a specific member name or storage location

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, `quit`, and a short self-play smoke test

### Slice 31: Position::set binding reset/restore now lives behind named helpers

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position::set()` no longer open-codes evaluator-binding reset and restore directly.
- The `memset` boundary now uses `prepare_evaluator_storage_binding_for_set()` and `restore_evaluator_storage_binding_after_set(...)`.
- This narrows the amount of binding-lifecycle choreography embedded in the body of `set()`.

Purpose:
- keep Phase C moving by isolating the most special-case ownership transition remaining in `Position`
- make the eventual relocation of binding ownership less tied to the implementation details of `set()`

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, `quit`, and a short self-play smoke test

### Slice 32: null binding pointer now means local fallback

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `Position` no longer stores the local binding pointer as the default active state.
- A null `evaluatorStorageBinding` now canonically means "use the local fallback binding".
- Binding resolution is handled through `resolve_evaluator_storage_binding(...)`, leaving the member itself as a raw external-binding override only.

Purpose:
- simplify the compatibility-state representation inside `Position`
- reduce special cases tied to the local binding object and make later ownership relocation less dependent on a stored fallback pointer

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, `quit`, and a short self-play smoke test

### Slice 33: Position::set now preserves canonical binding form

Implemented in:
- [`position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h)
- [`position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp)

Changed seam:
- `prepare_evaluator_storage_binding_for_set()` now returns the raw installed binding override, not the resolved active binding object.
- `Position::set()` restores binding state by reusing `set_evaluator_storage_binding(...)`.
- When the caller was using local fallback, `set()` now preserves the canonical `nullptr` form instead of restoring a pointer to the local binding object.

Purpose:
- keep Phase C moving by reducing the amount of special-case binding representation logic in `set()`
- preserve the simpler internal invariant that only external overrides are stored explicitly

Verification note:
- `make -C source tournament APPLE_CPU=native -j4` succeeds
- the resulting tournament binary passes `usi`, `isready`, `position startpos`, short `go movetime`, `quit`, and a short self-play smoke test

## Non-Goals For The First Pass

Do not start by:
- retuning all pruning constants
- changing evaluator strength
- changing `.nnue` format
- replacing every `Value` in the codebase

The first pass should isolate meaning, not redesign all tuning.
