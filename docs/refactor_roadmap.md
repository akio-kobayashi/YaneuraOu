# YaneuraOu Refactor Roadmap

This branch is for structural cleanup before low-level optimization work.
The main goal is to improve extension points, reduce build-time coupling, and make the codebase easier to evolve without repeated global rewrites.

Mandatory reference:
- [`docs/eval_value_contract.md`](/Users/akio/Documents/GitHub/YaneuraOu/docs/eval_value_contract.md)
- [`docs/eval_dependency_audit.md`](/Users/akio/Documents/GitHub/YaneuraOu/docs/eval_dependency_audit.md)

All refactor work that touches evaluation, search scoring, serializer behavior, or training compatibility must be checked against the evaluation value contract first.

## Priorities

### 1. Separate evaluator output semantics from search scoring

Current symptoms:
- Search code depends not only on the existence of an evaluation function, but on the numeric meaning and scale of its return value.
- Pruning and search heuristics implicitly assume evaluator-specific score behavior.
- Learning and analysis paths also consume evaluator outputs with weakly defined boundaries.

Why this matters:
- Swapping or redesigning the evaluator should not require silent retuning across unrelated search code.
- Numeric coupling is a hidden form of architectural coupling.
- Without this cleanup, ownership refactors only move the same problem behind a different interface.

Refactor direction:
- Define separate layers for:
  - raw evaluator output
  - normalized static evaluation used by search
  - full search score including mate/draw/special handling
- Make conversion boundaries explicit and centralized.
- Reduce the number of places where evaluator-specific score assumptions are embedded.

Recommended first slice:
- Audit the main search heuristics that consume static eval values.
- Introduce named conversion helpers or wrapper types for static-eval versus search-score usage.
- Use [`docs/eval_value_contract.md`](/Users/akio/Documents/GitHub/YaneuraOu/docs/eval_value_contract.md) as the governing specification for this work.

### 2. Decouple `Position` from evaluation-specific state

Current symptoms:
- [`source/position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h) contains `#if defined(EVAL_NNUE)` blocks.
- `Position` directly owns NNUE-specific state such as `Eval::NNUE::Accumulator`.
- Evaluation-specific update paths leak into [`source/position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp).

Why this matters:
- Board representation and evaluation are separate concerns.
- Adding new evaluators should not require invasive edits to `Position`.
- Current coupling increases rebuild cost and makes evaluator experiments fragile.

Refactor direction:
- Introduce an evaluation context object owned by search/evaluation layers rather than `Position`.
- Define a narrow evaluator-facing interface that reads immutable board state from `Position`.
- Move NNUE-specific caches/accumulators out of `Position` and into evaluator state or thread-local search state.

Recommended first slice:
- Replace direct `Position::accumulator` ownership with an adapter type referenced from search code.
- Keep behavior unchanged by using a compatibility wrapper during transition.

### 3. Reduce dependence on `config.h` feature macros

Current symptoms:
- Large parts of the engine are configured by preprocessor switches in [`source/config.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/config.h).
- Source files across engine, search, eval, mate, and deep-learning paths include `config.h` directly.
- Feature composition is mostly compile-time and creates many hard-to-test build permutations.

Why this matters:
- Macro-driven architecture hides control flow and feature dependencies.
- It makes cross-feature testing harder and increases branch-specific drift.
- Runtime flexibility is limited even when behavior differences are not performance critical.

Refactor direction:
- Split configuration into:
  - compile-time platform capabilities
  - runtime engine options
  - build profiles
- Move feature-selection policy from preprocessor branches to C++ types or settings objects where practical.
- Keep only hard architectural switches at compile time.

Recommended first slice:
- Introduce a small `BuildConfig` / `EngineConfig` layer that centralizes capability queries.
- Start by replacing read-only macro checks in non-hot code paths.

### 4. Improve NUMA and thread-local evaluation ownership

Current symptoms:
- [`source/engine.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/engine.h), [`source/search.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/search.h), and [`source/numa.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/numa.h) already use `LazyNumaReplicated`, but the ownership model is inconsistent.
- Search state, evaluator caches, and replicated network state are spread across engine/search layers.
- Memory locality is not expressed clearly in the type structure.

Why this matters:
- On large multi-socket systems, memory placement dominates small SIMD wins.
- Thread migration and remote memory accesses can erase low-level evaluation gains.
- Cleaner ownership is required before deeper NUMA tuning.

Refactor direction:
- Make per-thread search state explicit.
- Distinguish clearly between:
  - process-wide immutable network weights
  - NUMA-local replicas
  - thread-local mutable caches
- Push evaluator caches closer to worker-thread state.

Recommended first slice:
- Document and simplify ownership of `networks`, accumulator stacks, and refresh tables.
- Introduce a single thread-context object consumed by search.

### 5. Modernize the build system incrementally

Current symptoms:
- The project maintains a complex [`source/Makefile`](/Users/akio/Documents/GitHub/YaneuraOu/source/Makefile) plus Visual Studio project files.
- Build profiles and CPU tuning logic are interwoven with feature selection.
- External integrations are hard to add without editing multiple parallel build descriptions.

Why this matters:
- Build friction slows refactoring.
- CI coverage is difficult to scale.
- Contributor onboarding is harder than it needs to be.

Refactor direction:
- Visual Studio project files are not a compatibility target on this branch.
- Treat build modernization as a simplification project, not a multi-IDE support project.
- Standardize on non-Visual-Studio build definitions and remove duplicate project maintenance.
- Use Makefile cleanup as the short-term path and move toward a single modern build system such as CMake or Meson.

Recommended first slice:
- Stop updating `.sln`, `.vcxproj`, and `.vcxproj.filters` files.
- Define a minimal non-Visual-Studio build target for a small set of engine configurations.
- Extract CPU tuning, evaluator selection, and output naming into reusable variables.

## Sequencing

Recommended order:

1. evaluator score-semantics cleanup
2. search-entry predicate cleanup on normalized static eval
3. `Position` / evaluator decoupling
4. Thread-context and NUMA ownership cleanup
5. Macro reduction through config abstraction
6. Build-system modernization
7. SIMD/vendor-specific cleanup after ownership and build boundaries are clearer

Rationale:
- Numeric score coupling must be reduced before evaluator boundaries are truly clean.
- SIMD work on top of unstable ownership boundaries tends to be thrown away.
- Evaluation decoupling and thread-context cleanup create the seams needed for later specialization.
- Build modernization is much easier once those seams exist.

## Concrete Phase Plan

### Phase A: Stabilize evaluation semantics
- Separate evaluator output meaning from search score usage.
- Introduce explicit helpers or types for conversion boundaries.
- Identify heuristic thresholds that currently assume a specific evaluator scale.
- Migrate `improving`, `opponentWorsening`, razoring, null-move entry, and probcut entry to named helpers that explicitly consume normalized static eval.
- Migrate futility margins, move-count skip thresholds, and qsearch futility base to named helpers that explicitly consume normalized static eval.
- Migrate fail-low bonus and correction-history updates to named helpers that explicitly consume search-outcome versus normalized-static-eval deltas.
- Migrate qsearch stand-pat updates and qsearch capture-futility estimates to named helpers.
- Migrate TT score decoding and TT cutoff-bound interpretation to named search-score helpers shared by main search and qsearch.
- Migrate TT writeback, TT bound selection, and repetition/max-move draw outcomes to named search-score helpers.
- Migrate terminal draw and no-legal-move outcomes to named search-score helpers.
- Migrate remaining shogi-specific mate-return sites to named search-score helpers and treat the search-score semantics pass as complete once direct search-path references are limited to intentionally low-level primitives.

### Phase B: Create stable interfaces
- Introduce evaluator-facing interfaces and compatibility wrappers.
- Move evaluation caches out of `Position` ownership.
- Add comments documenting ownership and invalidation rules.

### Phase C: Restructure search/eval state
- Define a search thread context object.
- Consolidate accumulator/cache ownership.
- Clarify NUMA-local versus thread-local data.

### Phase D: Replace macro usage in non-hot layers
- Convert simple feature checks into typed config helpers.
- Shrink direct `config.h` includes in leaf modules.
- Preserve compile-time optimization in hot loops where justified.

### Phase E: Build cleanup
- Remove Visual Studio from the supported build matrix.
- Provide one maintained non-Visual-Studio build path.
- Encode CPU targeting and evaluator selection cleanly.
- Add CI-friendly target definitions.

## Explicit Non-Goals

The following are out of scope for this branch:

- preserving Visual Studio solution/project maintenance
- keeping `.sln` and `.vcxproj` files in sync with refactor work
- designing around Windows IDE-specific workflows

## Immediate Next Step

The next implementation slice on this branch should be:
- introduce an evaluation context abstraction now that the search-score semantics pass is nearly complete,
- then remove direct NNUE accumulator ownership from `Position`,
- keep existing NNUE behavior through a transitional compatibility layer,
- and verify each step against [`docs/eval_value_contract.md`](/Users/akio/Documents/GitHub/YaneuraOu/docs/eval_value_contract.md).
