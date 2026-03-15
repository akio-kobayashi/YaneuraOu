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

## Non-Goals For The First Pass

Do not start by:
- retuning all pruning constants
- changing evaluator strength
- changing `.nnue` format
- replacing every `Value` in the codebase

The first pass should isolate meaning, not redesign all tuning.
