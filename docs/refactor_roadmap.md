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

### 2. Introduce access boundaries around evaluation-specific state

Current symptoms:
- [`source/position.h`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.h) contains `#if defined(EVAL_NNUE)` blocks.
- `Position` directly owns NNUE-specific state such as `Eval::NNUE::Accumulator`.
- Evaluation-specific update paths leak into [`source/position.cpp`](/Users/akio/Documents/GitHub/YaneuraOu/source/position.cpp).

Why this matters:
- Board representation and evaluation are separate concerns.
- Adding new evaluators should not require invasive edits to `Position`.
- Current coupling increases rebuild cost and makes evaluator experiments fragile.
- The current codebase still expects classic NNUE to mutate cache-like state through `const Position&`, so direct ownership removal is riskier than first introducing stable access seams.

Refactor direction:
- Introduce an evaluation context object owned by search/evaluation layers rather than `Position`.
- Define a narrow evaluator-facing interface that reads immutable board state from `Position`.
- Replace open-coded `state()->...` evaluator accesses with `Position` helpers or evaluator-context methods before changing ownership.

Recommended first slice:
- Route search-side evaluation entry points through a compatibility object.
- Route classic NNUE accumulator access through `Position` helpers.
- Keep behavior unchanged by using compatibility wrappers during transition.

### 3. Move evaluator-specific ownership out of `Position` and `StateInfo`

Current symptoms:
- Even after accessors are introduced, `StateInfo` still physically stores evaluator-specific fields such as `Accumulator`, `DirtyPiece`, and classic-eval caches.
- `position.cpp`, classic NNUE, and search still rely on those fields existing in the current storage layout.

Why this matters:
- Access seams alone improve readability, but they do not yet reduce ownership coupling.
- Actual evaluator replacement or alternative cache layouts still require `StateInfo` edits until the storage is relocated.

Refactor direction:
- Use the newly introduced access seams to move evaluator-local mutable state into evaluator-owned or worker-owned storage.
- Keep a compatibility layer until all call sites stop depending on `StateInfo` layout.
- Move one evaluator-specific field group at a time instead of attempting a one-shot rewrite.

Recommended first slice:
- Group classic NNUE-specific state behind accessor-backed storage.
- Then relocate one field family at a time, starting with accumulator-like caches rather than broad `StateInfo` surgery.

### 4. Reduce dependence on `config.h` feature macros

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

### 5. Improve NUMA and thread-local evaluation ownership

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

### 6. Modernize the build system incrementally

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
3. evaluator access-boundary cleanup
4. evaluator ownership move out of `Position` / `StateInfo`
5. Thread-context and NUMA ownership cleanup
6. Macro reduction through config abstraction
7. Build-system modernization
8. SIMD/vendor-specific cleanup after ownership and build boundaries are clearer

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
- Route evaluator access through those wrappers before changing ownership.
- Add comments documenting ownership and invalidation rules.

Current status:
- Phase A is complete on this branch: active search-path score semantics now flow through named helpers, and remaining raw `ttData.value` comparisons are limited to disabled code or explanatory comments.
- Initial transitional wrapper introduced on the search side as `Search::EvaluationContext`.
- This keeps existing behavior while creating a seam for later evaluator-state ownership changes.
- Classic NNUE accumulator access is now routed through `Position` helper methods instead of open-coded `state()->accumulator` references.
- Classic-eval `materialValue`, `DirtyPiece`, and `EvalSum` access is now also routed through `Position` helper methods or setter helpers in active evaluator code paths.
- `EvalList` reads and writes in active evaluator, learner, NNUE feature, and serializer paths are now also routed through `Position` helper methods.
- Phase B is complete for active code paths: remaining direct storage references are limited to helper implementations inside `Position`, storage declarations, assertions, or explanatory comments.
- The next remaining work is Phase C storage relocation and compatibility cleanup rather than additional broad search/eval call-site churn.

### Phase C: Move evaluator ownership
- Relocate evaluator-local mutable state out of `StateInfo` in small slices.
- Keep accessor compatibility during the transition.
- Verify each storage move with a full clean rebuild before proceeding.

Current status:
- Phase C is complete for active code paths.
- `StateInfo` now keeps only an NNUE sidecar pointer, while `Position` owns the accumulator slot list and binds fresh storage on `set()`, `do_move()`, and `do_null_move()`.
- Existing `Position` accumulator accessors remain the compatibility layer, so evaluator and feature-transformer call sites do not depend on the storage move.
- `do_null_move()` explicitly clones the previous accumulator state before invalidating the score cache so null-move reuse semantics stay unchanged.
- Classic evaluator-owned `materialValue`, `EvalSum`, and `DirtyPiece` storage now also move through a `Position`-owned sidecar, leaving `StateInfo` with compatibility pointers instead of inline storage for those active code paths.
- `EvalList` and the active evaluator sidecars are now grouped under a single `Position::EvaluatorStorage` compatibility object.
- Worker root positions now bind that compatibility object from `Thread` scope instead of always allocating it inside `Position`, so the first external ownership step is now in place for active search paths.
- Cleanup of evaluator sidecars now runs through `EvaluatorStorage::reset()`, reducing `Position`'s storage-layout knowledge to binding and fallback-ownership decisions instead of family-by-family teardown code.
- Slot lookup and slot creation for classic-eval and NNUE sidecars now also live on `EvaluatorStorage`, so `Position` no longer needs to know the linked-list details of active evaluator state families.
- Storage lifecycle is now split between `reset_evaluator_storage()` and owner release, so `Position::set()` no longer has to save and restore external evaluator-storage bindings just to reinitialize sidecars.
- The remaining family-specific release helpers have been removed from `Position`, leaving evaluator reset and per-family bind delegation on the unified compatibility object instead of the earlier transitional wrappers.
- State-level sidecar bind and clone steps are now grouped behind shared `Position` helpers, so `set()`, `do_move()`, and `do_null_move()` no longer duplicate evaluator-storage wiring logic.
- State-level sidecar bind and clone ownership now lives on `EvaluatorStorage` itself, leaving `Position` to select the active storage owner and forward setup/move/null-move transitions.
- `Position` now uses an `active_evaluator_storage()` seam for eval-list access and state-transition forwarding, further reducing the remaining wrapper logic around the unified evaluator-storage object.
- Ownership policy for local-versus-external evaluator storage is now grouped behind `EvaluatorStorageBinding`, so `Position` no longer open-codes the two-pointer owner dance directly.
- External search-path binding now happens at the `EvaluatorStorageBinding` level rather than the raw storage level, so thread-owned owner policy can move outward together with the storage it controls.
- Active evaluator-state access now delegates through `EvaluatorStorageBinding`, so `Position` no longer needs a separate `active_evaluator_storage()` wrapper for eval-list access or state bind/clone transitions.
- `Position` no longer carries dedicated reset/release wrappers for evaluator storage lifecycle; active cleanup now routes straight through the bound policy object.
- Local fallback and external binding selection now share the same `set_evaluator_storage_binding(...)` entry point, so `Position` no longer exposes a separate "switch back to local" API.
- `Position` now reaches the active binding-policy object through a dedicated accessor, reducing direct raw-member access to the binding pointer itself.
- Local fallback binding selection now also flows through a dedicated accessor, reducing direct references to the local binding member.
- `Position::set()` no longer open-codes evaluator-binding reset/restore choreography; that reset boundary now lives behind dedicated helpers.
- `Position` now treats a null binding pointer as the canonical local-fallback state, with resolution handled by a dedicated seam instead of by storing the local binding pointer directly.
- `Position::set()` now preserves that canonical null-versus-external binding form across `memset`, instead of restoring the resolved local binding object pointer.
- Unused transitional bind/detach helpers have been removed from `EvaluatorStorageBinding`, tightening the active compatibility surface around the paths still in use.
- The dedicated binding-install helper has also been removed from `Position`, leaving fewer forwarding layers between binding selection and the active path.
- `Thread` teardown no longer switches `rootPos` back to local storage explicitly; cleanup now relies on the existing binding seam during normal destruction.
- `Position::set()` now restores evaluator-binding state through the same `set_evaluator_storage_binding(...)` entry point used elsewhere, removing one more direct member update from the reset path.
- The dedicated `prepare_evaluator_storage_binding_for_set()` helper has also been removed, leaving the reset path with fewer one-off compatibility helpers.
- Fallback resolution is now folded directly into the active binding accessor, removing another thin forwarding helper from `Position`.
- Raw evaluator-binding override access is now routed through a named accessor as well, leaving fewer direct touches of the compatibility pointer state inside `Position`.
- The remaining local-versus-external binding policy is now grouped under `EvaluatorStorageBindingState`, so `Position` no longer owns separate local and override members for evaluator-storage compatibility state.
- The build target mismatch that previously mixed `normal` and `tournament` object files is also fixed by splitting object directories per target, so clean tournament rebuilds and short USI search runs now succeed again.

### Phase D: Restructure search/eval state
- Define a search thread context object.
- Consolidate accumulator/cache ownership.
- Clarify NUMA-local versus thread-local data.

Current status:
- The first Phase D slice is now in progress: thread-local root search state is grouped under `Search::ThreadRootState`, and worker construction now receives a `Search::RootSearchContext` instead of three loose root references.
- This does not change ownership yet, but it fixes the first typed seam for later hot-state relocation and locality cleanup.
- Root-position setup in `ThreadPool::start_thinking()` now also routes through that same root-search context seam instead of open-coding three separate worker-root member updates.
- `ThreadRootState` now owns the actual root-position and root-move setup helpers as well, so `ThreadPool::start_thinking()` no longer open-codes the per-thread root-state population sequence.
- That per-thread root-search preparation is now grouped under one `ThreadRootState::prepare_root_search(...)` call, reducing more duplicated setup choreography before locality work starts.
- The thread-local root state's evaluator-binding hookup now also lives on `ThreadRootState`, so `Thread` construction no longer reaches inside the root position to wire that compatibility state manually.
- `ThreadPool::start_thinking()` now hands off per-thread search setup through `Thread::prepare_for_search(...)`, so thread-local preparation logic is starting to live on the thread-side seam rather than in the pool loop body.
- The non-Stockfish per-thread root-search reset path now executes through `Worker::prepare_for_search(...)`, which is a better home for worker-local hot-state reset than open-coding that logic in `ThreadPool`.
- Thread-local NUMA and root-search state are now grouped under `Search::ThreadSearchContext`, so `Thread` no longer stores its NUMA token and root-search state as unrelated members.

### Phase E: Replace macro usage in non-hot layers
- Convert simple feature checks into typed config helpers.
- Shrink direct `config.h` includes in leaf modules.
- Preserve compile-time optimization in hot loops where justified.

### Phase F: Build cleanup
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
- continue moving evaluator-storage ownership outward from `Position` toward worker or thread context objects,
- keep fallback storage for non-search utility callers until those call sites are explicitly migrated,
- then proceed to broader thread-context and NUMA ownership cleanup,
- keep existing NNUE behavior through the current compatibility layer,
- and verify each step against [`docs/eval_value_contract.md`](/Users/akio/Documents/GitHub/YaneuraOu/docs/eval_value_contract.md).
