# Evaluation Value Contract

This document defines the contract for numeric evaluation values shared across:

- training code such as `nnue-pytorch`
- serialization/deserialization of `.nnue`
- runtime evaluation in `YaneuraOu`
- search heuristics that consume static evaluation values

This contract is the highest-priority architectural reference for the `refactor` branch.
Refactor work that changes evaluator wiring, score interpretation, or search thresholds must refer to this document first.

Current dependency inventory:
- [`docs/eval_dependency_audit.md`](/Users/akio/Documents/GitHub/YaneuraOu/docs/eval_dependency_audit.md)

## Goal

Prevent hidden numeric coupling between:

- model output scale
- serialized network assumptions
- static evaluation used by search
- search score semantics
- training target scaling

The main design rule is:

> No search component should depend directly on raw evaluator output semantics.

Instead, all score flow must pass through explicit conversion boundaries.

## Required Score Layers

Three layers of score meaning must be distinguished.

### 1. Raw Evaluator Output

Definition:
- The direct numeric output produced by the evaluator implementation before search-specific interpretation.

Examples:
- raw NNUE output
- quantized/dequantized network output before engine-side conversion

Properties:
- evaluator-specific
- not safe to use directly in pruning heuristics
- may change when the training setup changes

### 2. Normalized Static Evaluation

Definition:
- The evaluator output converted into the engine's agreed static-eval domain.

Properties:
- stable meaning inside the engine
- may be used by search heuristics
- should be the only evaluation layer consumed by most pruning code

Requirements:
- conversion from raw output must be centralized
- scale and interpretation must not be duplicated across call sites

### 3. Search Score

Definition:
- The score domain used by alpha-beta search, mate handling, draw logic, and TT interactions.

Properties:
- includes engine-specific score conventions
- may differ from normalized static eval
- must preserve mate/draw semantics separately from evaluator calibration

## Contract Between `nnue-pytorch` and `YaneuraOu`

The following items must be treated as explicit contract data.

### Output Scale

The training side and engine side must agree on:

- how raw model output maps to normalized static evaluation
- which coefficient converts model output to engine score units

This value must not be assumed implicitly across multiple files.

### Training Score Mapping

The following must be defined explicitly:

- teacher score scale
- sigmoid / win-rate conversion convention
- any ponanza-style coefficient
- whether the network is trained to predict centipawn-like values, win-probability logits, or another target

### Serialization Expectations

The following must be documented and versioned:

- feature set name
- feature hash
- output interpretation
- quantization assumptions relevant to evaluation scaling

### Search Consumption Rules

Search code must specify whether it consumes:

- raw evaluator output
- normalized static eval
- full search score

Using plain `Value` without semantic context should be treated as technical debt in refactor work.

## Refactor Rules

The following rules apply on this branch.

### Rule 1

Do not introduce new search logic that depends directly on evaluator raw output.

### Rule 2

Do not hard-code evaluator scaling constants at multiple call sites.

If a constant exists, it must live behind one conversion boundary or one contract definition point.

### Rule 3

Any change to training score scaling or `.nnue` interpretation must update this document.

### Rule 4

Any refactor that touches:

- evaluator interfaces
- static eval computation
- search thresholds
- serializer/deserializer score handling

must cite this document as the governing contract.

## Immediate Implementation Targets

The first implementation tasks derived from this contract are:

1. Identify where raw evaluator outputs are converted into engine values.
2. Identify where search heuristics assume a particular evaluation scale.
3. Introduce explicit conversion helpers for:
   - raw evaluator output -> normalized static eval
   - normalized static eval -> search score when needed
4. Remove duplicated scaling assumptions from search code.

## Non-Goals

This document does not define:

- the best numeric scale
- the best training loss
- the best pruning constants

It defines where such choices are allowed to live and how they must be connected.
