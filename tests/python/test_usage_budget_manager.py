import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "budget" / "src"))

from dotacni_majak_budget import (
    BudgetAction,
    BudgetLimit,
    BudgetMetric,
    BudgetState,
    UsageBudgetManager,
)


class UsageBudgetManagerTest(unittest.TestCase):
    def make_manager(self):
        return UsageBudgetManager({
            BudgetMetric.D1_ROWS_READ: BudgetLimit(hard_limit=1000),
            BudgetMetric.VECTOR_QUERIED_DIMENSIONS: BudgetLimit(
                hard_limit=100,
                critical_action=BudgetAction.DEGRADE,
                exhausted_action=BudgetAction.DEGRADE,
            ),
        })

    def test_thresholds_70_85_95_are_explicit(self):
        manager = self.make_manager()

        self.assertEqual(
            manager.reserve(BudgetMetric.D1_ROWS_READ, 699).state,
            BudgetState.HEALTHY,
        )
        self.assertEqual(
            manager.reserve(BudgetMetric.D1_ROWS_READ, 1).state,
            BudgetState.NOTICE,
        )
        self.assertEqual(
            manager.reserve(BudgetMetric.D1_ROWS_READ, 150).state,
            BudgetState.WARNING,
        )
        decision = manager.reserve(BudgetMetric.D1_ROWS_READ, 100)
        self.assertEqual(decision.state, BudgetState.CRITICAL)
        self.assertEqual(decision.action, BudgetAction.DEGRADE)

    def test_exhausted_budget_does_not_consume_usage(self):
        manager = self.make_manager()
        manager.set_usage(BudgetMetric.D1_ROWS_READ, 990)
        decision = manager.reserve(BudgetMetric.D1_ROWS_READ, 20)

        self.assertFalse(decision.granted)
        self.assertEqual(decision.state, BudgetState.EXHAUSTED)
        self.assertEqual(decision.action, BudgetAction.BLOCK)
        self.assertEqual(manager.usage(BudgetMetric.D1_ROWS_READ).used, 990)

    def test_semantic_budget_can_degrade_instead_of_breaking_whole_search(self):
        manager = self.make_manager()
        manager.set_usage(BudgetMetric.VECTOR_QUERIED_DIMENSIONS, 95)

        critical = manager.evaluate(
            BudgetMetric.VECTOR_QUERIED_DIMENSIONS,
            requested=1,
        )
        self.assertTrue(critical.granted)
        self.assertTrue(critical.should_degrade)
        self.assertEqual(critical.action, BudgetAction.DEGRADE)

        exhausted = manager.reserve(
            BudgetMetric.VECTOR_QUERIED_DIMENSIONS,
            10,
        )
        self.assertFalse(exhausted.granted)
        self.assertTrue(exhausted.should_degrade)
        self.assertEqual(exhausted.action, BudgetAction.DEGRADE)

    def test_limits_are_configuration_not_provider_constants(self):
        manager = UsageBudgetManager({
            BudgetMetric.R2_STORAGE_BYTES: BudgetLimit(
                hard_limit=123456789
            )
        })
        decision = manager.reserve(
            BudgetMetric.R2_STORAGE_BYTES,
            123456789,
        )
        self.assertTrue(decision.granted)
        self.assertEqual(decision.state, BudgetState.CRITICAL)

    def test_snapshot_does_not_mutate_usage(self):
        manager = self.make_manager()
        manager.reserve(BudgetMetric.D1_ROWS_READ, 10)
        snapshot = manager.snapshot()
        self.assertEqual(
            snapshot[BudgetMetric.D1_ROWS_READ].used_before,
            10,
        )
        self.assertEqual(manager.usage(BudgetMetric.D1_ROWS_READ).used, 10)


if __name__ == "__main__":
    unittest.main()
