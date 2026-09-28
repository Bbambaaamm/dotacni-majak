"""Tests for the finance precision library (Money, Rate, CurrencyRegistry, etc.)

These tests are *deterministic*: property tests use :mod:`random` with a fixed
seed so CI results are reproducible.
"""

import sys
import unittest
from pathlib import Path
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "finance" / "src"))

from dotacni_majak_finance import (  # noqa: E402
    CurrencyMismatchError,
    CurrencyRegistry,
    Money,
    MoneyRange,
    Rate,
    RateOutOfRangeError,
    RoundingPolicy,
    UnknownCurrencyError,
)
from dotacni_majak_finance.engine import (  # noqa: E402
    FinanceEngine,
    FinanceStatus,
    FundingScenario,
    ProjectFinanceInput,
    ScenarioApplicability,
)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def czk(amount: int) -> int:
    """Convert major CZK units to CZK minor units (1 CZK = 100 haléřů)."""
    return amount * 100


SEED = 0x5EED  # deterministic seed for property tests


# --------------------------------------------------------------------------
# CurrencyRegistry
# --------------------------------------------------------------------------


class CurrencyRegistryTest(unittest.TestCase):
    def test_known_currencies(self):
        self.assertEqual(CurrencyRegistry.decimals("CZK"), 2)
        self.assertEqual(CurrencyRegistry.decimals("EUR"), 2)
        self.assertEqual(CurrencyRegistry.decimals("USD"), 2)
        self.assertEqual(CurrencyRegistry.decimals("JPY"), 0)
        self.assertEqual(CurrencyRegistry.decimals("BHD"), 3)

    def test_case_insensitive(self):
        self.assertEqual(CurrencyRegistry.decimals("czk"), 2)
        self.assertEqual(CurrencyRegistry.decimals("CZK"), 2)

    def test_unknown_currency_raises(self):
        with self.assertRaises(UnknownCurrencyError):
            CurrencyRegistry.decimals("XYZ")

    def test_decimals_or_default_for_unknown(self):
        self.assertEqual(CurrencyRegistry.decimals_or_default("XYZ"), 2)
        self.assertEqual(CurrencyRegistry.decimals_or_default("XYZ", 0), 0)

    def test_is_known(self):
        self.assertTrue(CurrencyRegistry.is_known("CZK"))
        self.assertTrue(CurrencyRegistry.is_known("jpy"))
        self.assertFalse(CurrencyRegistry.is_known("XYZ"))


# --------------------------------------------------------------------------
# RoundingPolicy
# --------------------------------------------------------------------------


class RoundingPolicyTest(unittest.TestCase):
    def test_half_even_is_default(self):
        self.assertEqual(RoundingPolicy.HALF_EVEN.decimal_rounding, "ROUND_HALF_EVEN")

    def test_half_up(self):
        self.assertEqual(RoundingPolicy.HALF_UP.decimal_rounding, "ROUND_HALF_UP")

    def test_down(self):
        self.assertEqual(RoundingPolicy.DOWN.decimal_rounding, "ROUND_DOWN")


# --------------------------------------------------------------------------
# Money unit tests
# --------------------------------------------------------------------------


class MoneyTest(unittest.TestCase):
    def test_post_init_uppercases_currency(self):
        m = Money(100, "czk")
        self.assertEqual(m.currency_code, "CZK")

    def test_invalid_currency_code(self):
        with self.assertRaises(ValueError):
            Money(100, "us")  # too short

    def test_from_major_units_czk(self):
        m = Money.from_major_units("42.50", "CZK")
        self.assertEqual(m.amount_minor, 4250)
        self.assertEqual(m.currency_code, "CZK")

    def test_from_major_units_jpy_no_decimals(self):
        m = Money.from_major_units("1000", "JPY")
        self.assertEqual(m.amount_minor, 1000)

    def test_from_major_units_bhd_three_decimals(self):
        m = Money.from_major_units("1.234", "BHD")
        self.assertEqual(m.amount_minor, 1234)

    def test_from_major_units_rounds_half_even(self):
        # 0.015 → 1 minor unit with HALF_EVEN (1 is odd, rounds to 2)
        m = Money.from_major_units("0.015", "CZK", rounding=RoundingPolicy.HALF_EVEN)
        self.assertEqual(m.amount_minor, 2)

    def test_from_major_units_rounds_half_up(self):
        # 0.015 → 2 with HALF_UP (rounds away from zero)
        m = Money.from_major_units("0.015", "CZK", rounding=RoundingPolicy.HALF_UP)
        self.assertEqual(m.amount_minor, 2)

    def test_from_major_units_rounds_half_down_truncates(self):
        # 0.019 → 1 with DOWN (truncate)
        m = Money.from_major_units("0.019", "CZK", rounding=RoundingPolicy.DOWN)
        self.assertEqual(m.amount_minor, 1)

    def test_from_major_units_float_safe(self):
        # 0.1 + 0.2 = 0.30000000000000004 in float; must round to 30 minor
        m = Money.from_major_units(0.1 + 0.2, "CZK")
        self.assertEqual(m.amount_minor, 30)

    def test_to_major_units(self):
        m = Money(3_500_000, "CZK")
        self.assertEqual(m.to_major_units(), Decimal("35000.00"))

    def test_to_major_units_jpy(self):
        m = Money(1000, "JPY")
        self.assertEqual(m.to_major_units(), Decimal("1000"))

    def test_round_trip(self):
        original = "12345.67"
        m = Money.from_major_units(original, "CZK")
        self.assertEqual(m.to_major_units(), Decimal("12345.67"))

    def test_format_czech_locale(self):
        m = Money(czk(1_234_567), "CZK")
        formatted = m.format()
        self.assertIn("1 234 567,00", formatted.replace("\xa0", " "))

    def test_format_with_symbol(self):
        m = Money(czk(1_000), "CZK")
        formatted = m.format(symbol="Kč")
        self.assertIn("Kč", formatted)

    def test_format_jpy(self):
        m = Money(1000, "JPY")
        self.assertIn("1 000", m.format().replace("\xa0", " "))

    def test_add_same_currency(self):
        a = Money(100, "CZK")
        b = Money(50, "CZK")
        c = a + b
        self.assertEqual(c, Money(150, "CZK"))

    def test_sub_same_currency(self):
        a = Money(100, "CZK")
        b = Money(30, "CZK")
        c = a - b
        self.assertEqual(c, Money(70, "CZK"))

    def test_add_different_currency_raises(self):
        a = Money(100, "CZK")
        b = Money(100, "EUR")
        with self.assertRaises(CurrencyMismatchError):
            a + b

    def test_sub_different_currency_raises(self):
        a = Money(100, "CZK")
        b = Money(100, "EUR")
        with self.assertRaises(CurrencyMismatchError):
            a - b

    def test_mul_by_int(self):
        m = Money(100, "CZK") * 3
        self.assertEqual(m, Money(300, "CZK"))

    def test_rmul(self):
        m = 3 * Money(100, "CZK")
        self.assertEqual(m, Money(300, "CZK"))

    def test_mul_by_decimal(self):
        m = Money(100, "CZK") * Decimal("1.5")
        self.assertEqual(m, Money(150, "CZK"))

    def test_neg(self):
        m = -Money(100, "CZK")
        self.assertEqual(m, Money(-100, "CZK"))

    def test_abs(self):
        m = abs(Money(-100, "CZK"))
        self.assertEqual(m, Money(100, "CZK"))

    def test_comparison_same_currency(self):
        a = Money(100, "CZK")
        b = Money(200, "CZK")
        self.assertLess(a, b)
        self.assertGreater(b, a)
        self.assertLessEqual(a, b)
        self.assertGreaterEqual(b, a)

    def test_comparison_different_currency_raises(self):
        a = Money(100, "CZK")
        b = Money(100, "EUR")
        with self.assertRaises(CurrencyMismatchError):
            a < b

    def test_equality_different_values(self):
        self.assertNotEqual(Money(100, "CZK"), Money(200, "CZK"))
        self.assertNotEqual(Money(100, "CZK"), Money(100, "EUR"))

    def test_floordiv_by_int(self):
        m = Money(100, "CZK") // 3
        self.assertEqual(m, Money(33, "CZK"))

    def test_floordiv_by_zero_raises(self):
        with self.assertRaises(ZeroDivisionError):
            Money(100, "CZK") // 0

    def test_floordiv_by_money(self):
        ratio = Money(200, "CZK") // Money(50, "CZK")
        self.assertEqual(ratio, 4)

    def test_floordiv_by_money_different_currency_raises(self):
        with self.assertRaises(CurrencyMismatchError):
            Money(200, "CZK") // Money(50, "EUR")

    def test_repr_is_explainable(self):
        r = repr(Money(3_500_000, "CZK"))
        self.assertIn("amount_minor=3500000", r)
        self.assertIn("currency_code='CZK'", r)
        self.assertIn("major=Decimal('35000.00')", r)

    def test_hashable(self):
        d = {Money(100, "CZK"): "value"}
        self.assertEqual(d[Money(100, "CZK")], "value")

    def test_immutable(self):
        m = Money(100, "CZK")
        with self.assertRaises(Exception):
            m.amount_minor = 200  # type: ignore[misc]


# --------------------------------------------------------------------------
# Rate unit tests
# --------------------------------------------------------------------------


class RateTest(unittest.TestCase):
    def test_from_bps(self):
        r = Rate(9000)
        self.assertEqual(r.bps, 9000)

    def test_zero_rate(self):
        r = Rate(0)
        self.assertEqual(r.bps, 0)
        self.assertEqual(r.to_percent(), Decimal("0"))
        self.assertEqual(r.to_decimal(), Decimal("0"))

    def test_full_rate(self):
        r = Rate(10_000)
        self.assertEqual(r.to_percent(), Decimal("100"))
        self.assertEqual(r.to_decimal(), Decimal("1"))

    def test_below_zero_raises(self):
        with self.assertRaises(RateOutOfRangeError):
            Rate(-1)

    def test_above_max_raises(self):
        with self.assertRaises(RateOutOfRangeError):
            Rate(10_001)

    def test_from_percent_round_trip(self):
        r = Rate.from_percent("90")
        self.assertEqual(r.bps, 9000)
        self.assertEqual(r.to_percent(), Decimal("90"))

    def test_from_percent_with_decimal(self):
        r = Rate.from_percent("85.5")
        self.assertEqual(r.bps, 8550)

    def test_from_percent_half_even(self):
        # 90.005 % → 9000.5 bps → rounds to 9000 (half-even: 0 is even)
        r = Rate.from_percent("90.005")
        self.assertEqual(r.bps, 9000)

    def test_from_decimal_multiplier(self):
        r = Rate.from_decimal("0.9")
        self.assertEqual(r.bps, 9000)

    def test_from_decimal_full(self):
        r = Rate.from_decimal("1.0")
        self.assertEqual(r.bps, 10_000)

    def test_apply_to(self):
        r = Rate(9000)
        self.assertEqual(r.apply_to(czk(3_500_000)), czk(3_150_000))

    def test_apply_to_floor_division(self):
        # 99 bps on 100 → 99 // 100 = 0 (floor division, conservative)
        self.assertEqual(Rate(99).apply_to(100), 0)

    def test_apply_to_zero(self):
        self.assertEqual(Rate(5000).apply_to(0), 0)

    def test_apply_to_full_rate(self):
        self.assertEqual(Rate(10_000).apply_to(1000), 1000)

    def test_add(self):
        self.assertEqual(Rate(3000) + Rate(6000), Rate(9000))

    def test_add_overflow_raises(self):
        with self.assertRaises(RateOutOfRangeError):
            Rate(6000) + Rate(5000)

    def test_sub(self):
        self.assertEqual(Rate(9000) - Rate(3000), Rate(6000))

    def test_sub_underflow_raises(self):
        with self.assertRaises(RateOutOfRangeError):
            Rate(3000) - Rate(5000)

    def test_mul_by_int(self):
        self.assertEqual(Rate(1000) * 2, Rate(2000))

    def test_mul_by_decimal(self):
        self.assertEqual(Rate(1000) * Decimal("1.5"), Rate(1500))

    def test_mul_overflow_raises(self):
        with self.assertRaises(RateOutOfRangeError):
            Rate(6000) * 2

    def test_comparison(self):
        self.assertLess(Rate(1000), Rate(2000))
        self.assertGreater(Rate(3000), Rate(2000))
        self.assertLessEqual(Rate(2000), Rate(2000))
        self.assertGreaterEqual(Rate(2000), Rate(2000))

    def test_eq(self):
        self.assertEqual(Rate(9000), Rate(9000))
        self.assertNotEqual(Rate(9000), Rate(8000))

    def test_hashable(self):
        d = {Rate(9000): "value"}
        self.assertEqual(d[Rate(9000)], "value")

    def test_repr_is_explainable(self):
        r = repr(Rate(9000))
        self.assertIn("bps=9000", r)
        self.assertIn("percent=Decimal('90')", r)


# --------------------------------------------------------------------------
# MoneyRange unit tests
# --------------------------------------------------------------------------


class MoneyRangeTest(unittest.TestCase):
    def test_contains_within(self):
        r = MoneyRange(Money(0, "CZK"), Money(1_000_000, "CZK"))
        self.assertTrue(r.contains(Money(500_000, "CZK")))

    def test_contains_at_min(self):
        r = MoneyRange(Money(0, "CZK"), Money(1_000_000, "CZK"))
        self.assertTrue(r.contains(Money(0, "CZK")))

    def test_contains_at_max(self):
        r = MoneyRange(Money(0, "CZK"), Money(1_000_000, "CZK"))
        self.assertTrue(r.contains(Money(1_000_000, "CZK")))

    def test_contains_below_min(self):
        r = MoneyRange(Money(100, "CZK"), Money(1_000_000, "CZK"))
        self.assertFalse(r.contains(Money(50, "CZK")))

    def test_contains_above_max(self):
        r = MoneyRange(Money(0, "CZK"), Money(1_000_000, "CZK"))
        self.assertFalse(r.contains(Money(2_000_000, "CZK")))

    def test_contains_currency_mismatch_returns_none(self):
        r = MoneyRange(Money(0, "CZK"), Money(1_000_000, "CZK"))
        self.assertIsNone(r.contains(Money(500, "EUR")))

    def test_contains_empty_range_returns_none(self):
        r = MoneyRange()
        self.assertIsNone(r.contains(Money(500, "CZK")))

    def test_dunder_contains_currency_mismatch_raises(self):
        r = MoneyRange(Money(0, "CZK"), Money(1_000_000, "CZK"))
        with self.assertRaises(CurrencyMismatchError):
            Money(500, "EUR") in r

    def test_clamp_within_range(self):
        r = MoneyRange(Money(0, "CZK"), Money(1_000_000, "CZK"))
        clamped = r.clamp(Money(500_000, "CZK"))
        self.assertEqual(clamped, Money(500_000, "CZK"))

    def test_clamp_above_max(self):
        r = MoneyRange(Money(0, "CZK"), Money(1_000_000, "CZK"))
        clamped = r.clamp(Money(5_000_000, "CZK"))
        self.assertEqual(clamped, Money(1_000_000, "CZK"))

    def test_clamp_below_min(self):
        r = MoneyRange(Money(100, "CZK"), Money(1_000_000, "CZK"))
        clamped = r.clamp(Money(50, "CZK"))
        self.assertEqual(clamped, Money(100, "CZK"))

    def test_clamp_currency_mismatch_returns_none(self):
        r = MoneyRange(Money(0, "CZK"), Money(1_000_000, "CZK"))
        self.assertIsNone(r.clamp(Money(500, "EUR")))

    def test_intersect_overlapping(self):
        a = MoneyRange(Money(0, "CZK"), Money(1_000, "CZK"))
        b = MoneyRange(Money(500, "CZK"), Money(2_000, "CZK"))
        result = a.intersect(b)
        self.assertIsNotNone(result)
        self.assertEqual(result.min_money, Money(500, "CZK"))
        self.assertEqual(result.max_money, Money(1_000, "CZK"))

    def test_intersect_disjoint_returns_none(self):
        a = MoneyRange(Money(0, "CZK"), Money(1_000, "CZK"))
        b = MoneyRange(Money(2_000, "CZK"), Money(3_000, "CZK"))
        self.assertIsNone(a.intersect(b))

    def test_intersect_currency_mismatch_returns_none(self):
        a = MoneyRange(Money(0, "CZK"), Money(1_000, "CZK"))
        b = MoneyRange(Money(0, "EUR"), Money(1_000, "EUR"))
        self.assertIsNone(a.intersect(b))

    def test_intersect_with_empty(self):
        a = MoneyRange(Money(0, "CZK"), Money(1_000, "CZK"))
        b = MoneyRange()
        result = a.intersect(b)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_empty)

    def test_open_ended_range(self):
        r = MoneyRange(max_money=Money(1_000_000, "CZK"))
        self.assertTrue(r.contains(Money(500, "CZK")))
        self.assertFalse(r.contains(Money(2_000_000, "CZK")))
        self.assertFalse(r.contains(Money(2_000_001, "CZK")))

    def test_min_exceeds_max_raises(self):
        with self.assertRaises(ValueError):
            MoneyRange(Money(1_000, "CZK"), Money(0, "CZK"))

    def test_mismatched_bounds_currencies_raise(self):
        with self.assertRaises(CurrencyMismatchError):
            MoneyRange(Money(0, "CZK"), Money(1_000, "EUR"))


# --------------------------------------------------------------------------
# Integration: precision library ↔ FinanceEngine consistency
# --------------------------------------------------------------------------


class EngineConsistencyTest(unittest.TestCase):
    """Verify that the precision library produces the same results as the
    existing :class:`FinanceEngine` for the main grant calculation path."""

    def setUp(self):
        self.engine = FinanceEngine()
        self.project = ProjectFinanceInput(
            currency_code="CZK",
            total_project_cost_minor=czk(4_000_000),
            eligible_costs_minor=czk(3_500_000),
            ineligible_costs_minor=czk(400_000),
            nonrecoverable_vat_minor=czk(100_000),
        )
        self.scenario = FundingScenario(
            id="sports-90",
            currency_code="CZK",
            support_rate_max_bps=9000,
        )

    def test_grant_matches_rate_apply_to(self):
        """Rate.apply_to must equal the engine's floor-division grant."""
        result = self.engine.evaluate(self.project, self.scenario)
        rate = Rate(self.scenario.support_rate_max_bps)
        expected_grant = rate.apply_to(self.project.eligible_costs_minor)
        self.assertEqual(result.max_grant_minor, expected_grant)
        self.assertEqual(result.max_grant_minor, czk(3_150_000))

    def test_cap_matches_range_clamp(self):
        """grant_amount_max_minor cap must equal MoneyRange.clamp."""
        capped_scenario = FundingScenario(
            id="capped",
            currency_code="CZK",
            support_rate_max_bps=9000,
            grant_amount_max_minor=czk(2_000_000),
        )
        project_all_eligible = ProjectFinanceInput(
            currency_code="CZK",
            total_project_cost_minor=czk(4_000_000),
            eligible_costs_minor=czk(4_000_000),
            ineligible_costs_minor=0,
            nonrecoverable_vat_minor=0,
        )
        result = self.engine.evaluate(project_all_eligible, capped_scenario)

        rate = Rate(capped_scenario.support_rate_max_bps)
        uncapped_grant = rate.apply_to(project_all_eligible.eligible_costs_minor)
        r = MoneyRange(
            None,
            Money(capped_scenario.grant_amount_max_minor, "CZK"),
        )
        capped_grant = r.clamp(Money(uncapped_grant, "CZK"))
        self.assertIsNotNone(capped_grant)
        self.assertEqual(capped_grant.amount_minor, result.max_grant_minor)
        self.assertEqual(result.max_grant_minor, czk(2_000_000))

    def test_real_cash_requirement_matches_money_arithmetic(self):
        """minimum_real_cash_requirement must equal Money arithmetic."""
        result = self.engine.evaluate(self.project, self.scenario)
        grant = Money(result.max_grant_minor, "CZK")
        eligible = Money(self.project.eligible_costs_minor, "CZK")
        ineligible = Money(self.project.ineligible_costs_minor, "CZK")
        vat = Money(self.project.nonrecoverable_vat_minor, "CZK")
        own_eligible = eligible - grant
        expected_cash = own_eligible + ineligible + vat
        self.assertEqual(
            result.minimum_real_cash_requirement_minor,
            expected_cash.amount_minor,
        )
        self.assertEqual(
            result.minimum_real_cash_requirement_minor,
            czk(850_000),
        )


# --------------------------------------------------------------------------
# Property tests (deterministic via fixed seed)
# --------------------------------------------------------------------------


class MoneyPropertyTest(unittest.TestCase):
    def setUp(self):
        import random
        self.rng = random.Random(SEED)

    def _random_minor(self) -> int:
        return self.rng.randint(0, 10_000_000)

    def test_from_major_to_minor_round_trip(self):
        """For any non-negative integer major amount, the round-trip
        from_major_units → to_major_units must be exact."""
        for _ in range(500):
            major = self.rng.randint(0, 1_000_000)
            minor_expected = major * 100
            m = Money.from_major_units(float(major), "CZK")
            self.assertEqual(m.amount_minor, minor_expected)
            self.assertEqual(m.to_major_units(), Decimal(major) / Decimal(1))

    def test_money_addition_is_commutative(self):
        for _ in range(500):
            a = Money(self._random_minor(), "CZK")
            b = Money(self._random_minor(), "CZK")
            self.assertEqual(a + b, b + a)

    def test_money_addition_is_associative(self):
        for _ in range(500):
            a = Money(self._random_minor(), "CZK")
            b = Money(self._random_minor(), "CZK")
            c = Money(self._random_minor(), "CZK")
            self.assertEqual((a + b) + c, a + (b + c))

    def test_money_add_sub_identity(self):
        for _ in range(500):
            a = Money(self._random_minor(), "CZK")
            self.assertEqual(a + Money(0, "CZK"), a)
            self.assertEqual(a - Money(0, "CZK"), a)

    def test_money_sub_add_inverse(self):
        for _ in range(500):
            a = Money(self._random_minor(), "CZK")
            b = Money(self._random_minor(), "CZK")
            # Only test when a >= b to avoid negative amounts
            if a >= b:
                self.assertEqual((a - b) + b, a)

    def test_money_mul_scalar_distributive(self):
        for _ in range(200):
            a = Money(self._random_minor(), "CZK")
            scalar = self.rng.randint(1, 100)
            self.assertEqual(a * (scalar + scalar), (a * scalar) + (a * scalar))

    def test_money_comparison_total_order(self):
        for _ in range(200):
            x = self._random_minor()
            y = self._random_minor()
            a = Money(x, "CZK")
            b = Money(y, "CZK")
            if x < y:
                self.assertLess(a, b)
                self.assertLessEqual(a, b)
            elif x > y:
                self.assertGreater(a, b)
                self.assertGreaterEqual(a, b)
            else:
                self.assertEqual(a, b)
                self.assertLessEqual(a, b)
                self.assertGreaterEqual(a, b)


class RatePropertyTest(unittest.TestCase):
    def setUp(self):
        import random
        self.rng = random.Random(SEED)

    def test_rate_bps_in_range(self):
        for _ in range(1000):
            bps = self.rng.randint(0, 10_000)
            r = Rate(bps)
            self.assertTrue(0 <= r.bps <= 10_000)

    def test_rate_from_percent_in_range(self):
        for _ in range(500):
            percent = self.rng.randint(0, 100)
            r = Rate.from_percent(str(percent))
            self.assertEqual(r.bps, percent * 100)

    def test_rate_add_stays_in_range(self):
        for _ in range(500):
            a_bps = self.rng.randint(0, 5_000)
            b_bps = self.rng.randint(0, 5_000)
            if a_bps + b_bps <= 10_000:
                result = Rate(a_bps) + Rate(b_bps)
                self.assertEqual(result.bps, a_bps + b_bps)

    def test_rate_to_decimal_to_percent(self):
        for _ in range(500):
            bps = self.rng.randint(0, 10_000)
            r = Rate(bps)
            self.assertEqual(r.to_percent(), r.to_decimal() * 100)
            self.assertEqual(r.to_decimal() * 10_000, Decimal(bps))

    def test_rate_apply_to_monotonic(self):
        rate = Rate(9000)
        for _ in range(500):
            a = self._random_positive()
            b = self._random_positive()
            if a <= b:
                self.assertLessEqual(rate.apply_to(a), rate.apply_to(b))

    def _random_positive(self) -> int:
        import random
        rng = random.Random(SEED + 1)
        return rng.randint(0, 10_000_000)


class MoneyRangePropertyTest(unittest.TestCase):
    def setUp(self):
        import random
        self.rng = random.Random(SEED)

    def _random_money(self, currency="CZK") -> Money:
        return Money(self.rng.randint(0, 10_000_000), currency)

    def test_clamp_always_in_range(self):
        for _ in range(500):
            lo = self.rng.randint(0, 5_000_000)
            hi = self.rng.randint(lo, 10_000_000)
            money = self._random_money()
            r = MoneyRange(Money(lo, "CZK"), Money(hi, "CZK"))
            clamped = r.clamp(money)
            self.assertIsNotNone(clamped)
            self.assertGreaterEqual(clamped.amount_minor, lo)
            self.assertLessEqual(clamped.amount_minor, hi)

    def test_contains_after_clamp(self):
        for _ in range(500):
            lo = self.rng.randint(0, 5_000_000)
            hi = self.rng.randint(lo, 10_000_000)
            money = self._random_money()
            r = MoneyRange(Money(lo, "CZK"), Money(hi, "CZK"))
            clamped = r.clamp(money)
            self.assertIsNotNone(clamped)
            self.assertTrue(r.contains(clamped))

    def test_intersect_subset_property(self):
        """Intersection is always contained in both original ranges."""
        for _ in range(500):
            lo_a = self.rng.randint(0, 5_000_000)
            hi_a = self.rng.randint(lo_a, 10_000_000)
            lo_b = self.rng.randint(0, 5_000_000)
            hi_b = self.rng.randint(lo_b, 10_000_000)
            a = MoneyRange(Money(lo_a, "CZK"), Money(hi_a, "CZK"))
            b = MoneyRange(Money(lo_b, "CZK"), Money(hi_b, "CZK"))
            inter = a.intersect(b)
            if inter is not None and not inter.is_empty:
                # If intersection has bounds, check they are within both
                if inter.max_money is not None:
                    self.assertLessEqual(
                        inter.max_money.amount_minor, max(hi_a, hi_b)
                    )
                    self.assertLessEqual(
                        inter.max_money.amount_minor, hi_a
                    )
                    self.assertLessEqual(
                        inter.max_money.amount_minor, hi_b
                    )
                if inter.min_money is not None:
                    self.assertGreaterEqual(
                        inter.min_money.amount_minor, lo_a
                    )
                    self.assertGreaterEqual(
                        inter.min_money.amount_minor, lo_b
                    )

    def test_empty_range_intersect_identity(self):
        for _ in range(100):
            r = MoneyRange(
                Money(self.rng.randint(0, 5_000_000), "CZK"),
                Money(self.rng.randint(5_000_000, 10_000_000), "CZK"),
            )
            empty = MoneyRange()
            result = r.intersect(empty)
            self.assertIsNotNone(result)
            self.assertTrue(result.is_empty)

    def test_clamp_currency_mismatch_returns_none(self):
        for _ in range(10):
            r = MoneyRange(Money(0, "CZK"), Money(1_000, "CZK"))
            money = Money(self.rng.randint(0, 1_000), "EUR")
            self.assertIsNone(r.clamp(money))


if __name__ == "__main__":
    unittest.main()
