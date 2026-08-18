from __future__ import annotations

from collections import Counter

from housing_agent.evaluation import evaluate, generate_tasks


def test_generator_creates_exact_deterministic_distribution() -> None:
    first = generate_tasks()
    second = generate_tasks()
    assert first == second
    assert len(first) == 100
    assert Counter(task.category for task in first) == {
        "direct_retrieval": 30,
        "multi_hop": 25,
        "normalization": 15,
        "clarification": 15,
        "failure_recovery": 15,
    }
    assert sum(task.reviewed for task in first) == 15


def test_small_eval_exposes_three_variants_and_valid_arguments() -> None:
    metrics, rows = evaluate(generate_tasks()[:4])
    assert set(metrics["variants"]) == {"direct_no_tools", "single_tool", "state_machine"}
    assert all(row["argument_valid"] for row in rows)
