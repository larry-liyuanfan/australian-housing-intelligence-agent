# Deterministic evaluation report

> Synthetic/deidentified contract evaluation only; not real-corpus answer quality.

| Variant | Task success | Argument validity | Logical tool success | Attempt success | Citation completeness | Failure recovery | P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| direct_no_tools | 15.0% | 100.0% | n/a | n/a | 0.0% | 0.0% | 0.010 |
| single_tool | 40.0% | 100.0% | 88.2% | 88.2% | 100.0% | 0.0% | 2.096 |
| state_machine | 100.0% | 100.0% | 100.0% | 94.0% | 100.0% | 100.0% | 1.474 |

## Interpretation

The full state machine succeeds on the generated fixture contract because the generator and deterministic corpus are deliberately controlled. The attempt-level success rate includes injected first-attempt failures; logical success reflects bounded recovery. Do not transfer these percentages to a resume until a human-labeled, real-corpus evaluation is completed.
