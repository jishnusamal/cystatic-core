from engine.repository.materialization.budget import (
    MaterializationBudget,
)


def test_materialization_budget_creation():
    budget = MaterializationBudget(
        max_files=10,
        max_bytes=1000,
        max_remote_requests=2,
    )
    assert budget.max_files == 10
    assert budget.max_bytes == 1000
    assert budget.max_remote_requests == 2
