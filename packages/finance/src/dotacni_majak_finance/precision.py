"""Finance precision library: exact arithmetic for money and rates.

All amounts are stored as integer *minor units* (e.g. cents, haléře) and all
rates as *basis points* (1 bp = 0.01 %).  No floating-point is used for
critical amounts.  The only third-party dependency is the Python standard
library ``decimal`` module.

Design notes
------------
* ``Money`` is immutable and currency-aware.  Arithmetic across different
  currencies raises :class:`CurrencyMismatchError` rather than silently
  producing a meaningless result.
* ``Rate`` is immutable and bounded to ``[0, 10_000]`` bps (0–100 %).
  :meth:`Rate.apply_to` uses floor division so that a *maximum grant*
  estimate can never over-claim public support — this matches the
  conservative calculation in :class:`~dotacni_majak_finance.engine.FinanceEngine`.
* :class:`CurrencyRegistry` provides ISO 4217 decimal-place lookup.  Unknown
  currencies are *explicitly rejected* so that rounding behaviour is never
  guessed.
* :class:`MoneyRange` provides min/max cap operations: ``contains``,
  ``clamp`` and ``intersect``.
"""

from __future__ import annotations

import decimal as _decimal
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "CurrencyMismatchError",
    "CurrencyRegistry",
    "FinanceError",
    "Money",
    "MoneyRange",
    "Rate",
    "RateOutOfRangeError",
    "RoundingPolicy",
    "UnknownCurrencyError",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FinanceError(Exception):
    """Base exception for all finance-precision errors."""


class CurrencyMismatchError(FinanceError):
    """Raised when operating on values with different currency codes."""


class UnknownCurrencyError(FinanceError):
    """Raised when a currency code is not in the ISO 4217 registry."""


class RateOutOfRangeError(FinanceError):
    """Raised when a basis-point value is outside ``[0, 10_000]``."""


# ---------------------------------------------------------------------------
# Rounding policy
# ---------------------------------------------------------------------------

class RoundingPolicy(str, Enum):
    """Rounding modes backed by :mod:`decimal` constants.

    The default :attr:`HALF_EVEN` ("banker's rounding") is statistically
    unbiased and is the recommended choice for financial calculations.
    """

    #: Round to nearest, ties to even (banker's rounding). *Default.*
    HALF_EVEN = _decimal.ROUND_HALF_EVEN
    #: Round to nearest, ties away from zero (commercial rounding).
    HALF_UP = _decimal.ROUND_HALF_UP
    #: Round toward zero (truncation).
    DOWN = _decimal.ROUND_DOWN
    #: Round away from zero.
    UP = _decimal.ROUND_UP
    #: Round toward negative infinity.
    FLOOR = _decimal.ROUND_FLOOR
    #: Round toward positive infinity.
    CEILING = _decimal.ROUND_CEILING

    @property
    def decimal_rounding(self) -> str:
        """The ``decimal`` rounding-constant string usable with ``quantize``."""
        return self.value


# ---------------------------------------------------------------------------
# Currency registry (ISO 4217 subset)
# ---------------------------------------------------------------------------

class CurrencyRegistry:
    """Lookup table for ISO 4217 currency decimal places.

    Only currencies that are *relevant* for Dotační maják and its
    neighbours are pre-populated.  Unknown currencies are rejected
    explicitly rather than silently defaulting, so that rounding behaviour
    is never guessed.
    """

    #: Most ISO 4217 currencies use 2 decimal places.
    DEFAULT_DECIMALS = 2

    _DECIMALS: dict[str, int] = {
        # 0 decimal places
        "BIF": 0, "CLP": 0, "DJF": 0, "GNF": 0, "ISK": 0, "JPY": 0,
        "KMF": 0, "KRW": 0, "PYG": 0, "RWF": 0, "UGX": 0, "USX": 0,
        "VND": 0, "VUV": 0, "XAF": 0, "XOF": 0, "XPF": 0,
        # 3 decimal places
        "BHD": 3, "IQD": 3, "JOD": 3, "KWD": 3, "LYD": 3, "OMR": 3,
        "TND": 3,
        # 2 decimal places (most common, listed explicitly for clarity)
        "CZK": 2, "EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "AUD": 2,
        "CAD": 2, "CNY": 2, "SEK": 2, "NOK": 2, "DKK": 2, "PLN": 2,
    }

    @classmethod
    def decimals(cls, currency_code: str) -> int:
        """Return the number of decimal places for *currency_code*.

        Raises
        ------
        UnknownCurrencyError
            If the currency is not in the registry.
        """
        code = currency_code.upper()
        if code in cls._DECIMALS:
            return cls._DECIMALS[code]
        raise UnknownCurrencyError(
            f"Unknown currency code: {currency_code!r}. "
            f"Register it in CurrencyRegistry._DECIMALS or pass it explicitly."
        )

    @classmethod
    def decimals_or_default(
        cls, currency_code: str, default: int = DEFAULT_DECIMALS
    ) -> int:
        """Return decimal places, falling back to *default* for unknown codes."""
        try:
            return cls.decimals(currency_code)
        except UnknownCurrencyError:
            return default

    @classmethod
    def is_known(cls, currency_code: str) -> bool:
        """Return ``True`` if *currency_code* is in the registry."""
        return currency_code.upper() in cls._DECIMALS


# ---------------------------------------------------------------------------
# Money value object
# ---------------------------------------------------------------------------

# A type alias for anything that can be converted to ``Decimal``.
NumberLike = int | float | str | _decimal.Decimal


def _to_decimal(value: NumberLike) -> _decimal.Decimal:
    """Convert *value* to a :class:`~decimal.Decimal` safely."""
    if isinstance(value, _decimal.Decimal):
        return value
    try:
        # Go through str() to avoid binary-float representation issues.
        return _decimal.Decimal(str(value))
    except (_decimal.InvalidOperation, ValueError) as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal") from exc


@dataclass(frozen=True, slots=True)
class Money:
    """Immutable money value object stored as integer minor units.

    Examples
    --------
    >>> Money(3_500_000, "CZK").to_major_units()
    Decimal('35000.00')
    >>> Money.from_major_units(42.50, "CZK")
    Money(amount_minor=4250, currency_code='CZK')
    """

    amount_minor: int
    currency_code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency_code", self.currency_code.upper())
        if len(self.currency_code) != 3 or not self.currency_code.isalpha():
            raise ValueError(
                f"currency_code must be a 3-letter ISO 4217 code, "
                f"got {self.currency_code!r}"
            )

    # -- factories ---------------------------------------------------------

    @classmethod
    def from_major_units(
        cls,
        major: NumberLike,
        currency_code: str,
        *,
        rounding: RoundingPolicy = RoundingPolicy.HALF_EVEN,
    ) -> Money:
        """Create :class:`Money` from a *major-unit* amount.

        The conversion uses *rounding* to turn the (possibly fractional)
        major amount into integer minor units.  The default
        :attr:`RoundingPolicy.HALF_EVEN` is statistically unbiased.
        """
        decimals = CurrencyRegistry.decimals(currency_code)
        d = _to_decimal(major)
        quant = _decimal.Decimal(1).scaleb(-decimals)  # 0.01 for 2 dp
        d = d.quantize(quant, rounding=rounding.decimal_rounding)
        factor = _decimal.Decimal(10) ** decimals
        minor = int(d * factor)
        return cls(minor, currency_code)

    # -- conversion --------------------------------------------------------

    @property
    def decimals(self) -> int:
        """Number of decimal places for this money's currency."""
        return CurrencyRegistry.decimals(self.currency_code)

    def to_major_units(self) -> _decimal.Decimal:
        """Return the amount as a :class:`~decimal.Decimal` in major units."""
        decimals = self.decimals
        raw = _decimal.Decimal(self.amount_minor) / (
            _decimal.Decimal(10) ** decimals
        )
        quant = _decimal.Decimal(1).scaleb(-decimals)  # 0.01 for 2 dp
        return raw.quantize(quant)

    def format(
        self,
        *,
        symbol: str | None = None,
        locale: str = "cs_CZ",
    ) -> str:
        """Format as a human-readable string, e.g. ``"CZK 3 500 000.00"``."""
        major = self.to_major_units()
        decimals = self.decimals
        # Use non-breaking space grouping for CZ locale, comma for CZ decimal.
        if locale == "cs_CZ":
            groups = f"{major:,.{decimals}f}".replace(",", "\xa0")
            groups = groups.replace(".", ",")
        else:
            groups = f"{major:,.{decimals}f}"
        if symbol:
            return f"{symbol} {groups}"
        return f"{self.currency_code} {groups}"

    # -- arithmetic (same currency only) -----------------------------------

    def _check_currency(self, other: Money) -> None:
        if other.currency_code != self.currency_code:
            raise CurrencyMismatchError(
                f"Currency mismatch: {self.currency_code} vs {other.currency_code}"
            )

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency_code)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency_code)

    def __neg__(self) -> Money:
        return Money(-self.amount_minor, self.currency_code)

    def __pos__(self) -> Money:
        return self

    def __abs__(self) -> Money:
        return Money(abs(self.amount_minor), self.currency_code)

    def __mul__(self, scalar: int | _decimal.Decimal) -> Money:
        if isinstance(scalar, float):
            scalar = _to_decimal(scalar)
        if isinstance(scalar, _decimal.Decimal):
            result = int(scalar * self.amount_minor)
        elif isinstance(scalar, int):
            result = self.amount_minor * scalar
        else:
            return NotImplemented
        return Money(result, self.currency_code)

    __rmul__ = __mul__

    def __floordiv__(self, other: Money | int) -> int | Money:
        if isinstance(other, Money):
            self._check_currency(other)
            if other.amount_minor == 0:
                raise ZeroDivisionError("Cannot divide by zero-money")
            return self.amount_minor // other.amount_minor
        if isinstance(other, int):
            if other == 0:
                raise ZeroDivisionError("Cannot divide by zero")
            return Money(self.amount_minor // other, self.currency_code)
        return NotImplemented

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return (
            self.amount_minor == other.amount_minor
            and self.currency_code == other.currency_code
        )

    def __lt__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.amount_minor <= other.amount_minor

    def __gt__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.amount_minor > other.amount_minor

    def __ge__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.amount_minor >= other.amount_minor

    def __hash__(self) -> int:
        return hash((self.amount_minor, self.currency_code))

    def __repr__(self) -> str:
        return (
            f"Money(amount_minor={self.amount_minor}, "
            f"currency_code={self.currency_code!r}, "
            f"major={self.to_major_units()!r})"
        )


# ---------------------------------------------------------------------------
# Rate value object (basis points)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Rate:
    """Immutable rate value object stored as basis points.

    1 basis point = 0.01 % = 0.0001
    10 000 bps = 100 % = 1.0

    The value is always in ``[0, 10_000]``.

    Examples
    --------
    >>> Rate(9000).to_percent()
    Decimal('90')
    >>> Rate(9000).apply_to(3_500_000)
    3150000
    """

    bps: int

    def __post_init__(self) -> None:
        if not isinstance(self.bps, int) or isinstance(self.bps, bool):
            raise ValueError(f"bps must be an int, got {type(self.bps).__name__}")
        if not 0 <= self.bps <= 10_000:
            raise RateOutOfRangeError(
                f"bps must be between 0 and 10 000, got {self.bps}"
            )

    # -- factories ---------------------------------------------------------

    @classmethod
    def from_percent(
        cls,
        percent: NumberLike,
        *,
        rounding: RoundingPolicy = RoundingPolicy.HALF_EVEN,
    ) -> Rate:
        """Create :class:`Rate` from a percentage (e.g. ``90.0`` = 90 %).

        The percentage is converted to bps and rounded per *rounding*.
        Values outside ``[0, 100]`` raise :class:`RateOutOfRangeError`.
        """
        d = _to_decimal(percent)
        bps_exact = d * 100  # percent → bps
        bps = int(bps_exact.quantize(_decimal.Decimal("1"), rounding=rounding.decimal_rounding))
        return cls(bps)

    @classmethod
    def from_decimal(
        cls,
        multiplier: NumberLike,
        *,
        rounding: RoundingPolicy = RoundingPolicy.HALF_EVEN,
    ) -> Rate:
        """Create :class:`Rate` from a decimal multiplier (e.g. ``0.9`` = 90 %)."""
        d = _to_decimal(multiplier)
        bps_exact = d * 10_000  # multiplier → bps
        bps = int(
            bps_exact.quantize(
                _decimal.Decimal("1"), rounding=rounding.decimal_rounding
            )
        )
        return cls(bps)

    # -- conversion --------------------------------------------------------

    def to_decimal(self) -> _decimal.Decimal:
        """Return as a Decimal multiplier, e.g. ``9000 bps → Decimal('0.9')``."""
        return _decimal.Decimal(self.bps) / _decimal.Decimal(10_000)

    def to_percent(self) -> _decimal.Decimal:
        """Return as a Decimal percentage, e.g. ``9000 bps → Decimal('90')``."""
        return _decimal.Decimal(self.bps) / _decimal.Decimal(100)

    def apply_to(self, amount_minor: int) -> int:
        """Apply this rate to *amount_minor* (in minor units).

        Uses **floor division** so that a maximum-grant estimate can never
        over-claim public support.  This matches the conservative calculation
        in :class:`~dotacni_majak_finance.engine.FinanceEngine`:

        ``grant = eligible_costs * rate_bps // 10_000``

        The caller is responsible for ensuring *amount_minor* is non-negative.
        """
        return amount_minor * self.bps // 10_000

    # -- arithmetic --------------------------------------------------------

    def __add__(self, other: Rate) -> Rate:
        if not isinstance(other, Rate):
            return NotImplemented
        return Rate(self.bps + other.bps)

    def __sub__(self, other: Rate) -> Rate:
        if not isinstance(other, Rate):
            return NotImplemented
        return Rate(self.bps - other.bps)

    def __mul__(self, scalar: int | _decimal.Decimal) -> Rate:
        if isinstance(scalar, float):
            scalar = _to_decimal(scalar)
        if isinstance(scalar, _decimal.Decimal):
            result = int((scalar * self.bps).quantize(_decimal.Decimal("1"), rounding=_decimal.ROUND_HALF_EVEN))
        elif isinstance(scalar, int):
            result = self.bps * scalar
        else:
            return NotImplemented
        return Rate(result)

    __rmul__ = __mul__

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Rate):
            return NotImplemented
        return self.bps == other.bps

    def __lt__(self, other: Rate) -> bool:
        return self.bps < other.bps

    def __le__(self, other: Rate) -> bool:
        return self.bps <= other.bps

    def __gt__(self, other: Rate) -> bool:
        return self.bps > other.bps

    def __ge__(self, other: Rate) -> bool:
        return self.bps >= other.bps

    def __hash__(self) -> int:
        return hash(self.bps)

    def __repr__(self) -> str:
        return f"Rate(bps={self.bps}, percent={self.to_percent()!r})"


# ---------------------------------------------------------------------------
# Money range / cap operations
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MoneyRange:
    """A min/max range for :class:`Money` values of a single currency.

    Either bound may be ``None`` (open-ended).  At least one bound should
    typically be set.

    Examples
    --------
    >>> r = MoneyRange(Money(0, "CZK"), Money(2_000_000, "CZK"))
    >>> r.contains(Money(1_000_000, "CZK"))
    True
    >>> r.clamp(Money(5_000_000, "CZK"))
    Money(amount_minor=2000000, currency_code='CZK', major=Decimal('20000.00'))
    """

    min_money: Money | None = None
    max_money: Money | None = None

    def __post_init__(self) -> None:
        bounds = [b for b in (self.min_money, self.max_money) if b is not None]
        if len(bounds) == 2:
            if bounds[0].currency_code != bounds[1].currency_code:
                raise CurrencyMismatchError(
                    f"Range bounds have different currencies: "
                    f"{bounds[0].currency_code} vs {bounds[1].currency_code}"
                )
            if bounds[0].amount_minor > bounds[1].amount_minor:
                raise ValueError(
                    f"Range min ({bounds[0].amount_minor}) exceeds "
                    f"max ({bounds[1].amount_minor})"
                )

    @property
    def currency_code(self) -> str | None:
        """The currency of the bounds, or ``None`` if the range is empty."""
        if self.min_money is not None:
            return self.min_money.currency_code
        if self.max_money is not None:
            return self.max_money.currency_code
        return None

    @property
    def is_empty(self) -> bool:
        return self.min_money is None and self.max_money is None

    def contains(self, money: Money) -> bool | None:
        """Return whether *money* falls within the range.

        Returns ``None`` when the currency does not match (so the caller
        can distinguish "definitely outside" from "incomparable").
        """
        if self.is_empty:
            return None
        if self.currency_code != money.currency_code:
            return None
        ok = True
        if self.min_money is not None and money.amount_minor < self.min_money.amount_minor:
            ok = False
        if self.max_money is not None and money.amount_minor > self.max_money.amount_minor:
            ok = False
        return ok

    def __contains__(self, money: Money) -> bool:
        result = self.contains(money)
        if result is None:
            raise CurrencyMismatchError(
                f"Cannot compare {money.currency_code} with "
                f"{self.currency_code} range"
            )
        return result

    def clamp(self, money: Money) -> Money | None:
        """Return *money* restricted to the range.

        Returns ``None`` when the currency does not match.
        """
        if self.currency_code != money.currency_code:
            return None
        result = money.amount_minor
        if self.min_money is not None:
            result = max(result, self.min_money.amount_minor)
        if self.max_money is not None:
            result = min(result, self.max_money.amount_minor)
        return Money(result, money.currency_code)

    def intersect(self, other: MoneyRange) -> MoneyRange | None:
        """Return the intersection of two ranges, or ``None`` if disjoint.

        Returns ``None`` when currencies differ.
        """
        if self.is_empty:
            return MoneyRange()
        if other.is_empty:
            return MoneyRange()
        if self.currency_code != other.currency_code:
            return None

        new_min: Money | None = None
        if self.min_money is not None and other.min_money is not None:
            new_min = max(self.min_money, other.min_money)
        elif self.min_money is not None:
            new_min = self.min_money
        elif other.min_money is not None:
            new_min = other.min_money

        new_max: Money | None = None
        if self.max_money is not None and other.max_money is not None:
            new_max = min(self.max_money, other.max_money)
        elif self.max_money is not None:
            new_max = self.max_money
        elif other.max_money is not None:
            new_max = other.max_money

        if new_min is not None and new_max is not None:
            if new_min.amount_minor > new_max.amount_minor:
                return None  # empty intersection
        return MoneyRange(new_min, new_max)

    def __repr__(self) -> str:
        lo = self.min_money.amount_minor if self.min_money else None
        hi = self.max_money.amount_minor if self.max_money else None
        return f"MoneyRange(min_minor={lo}, max_minor={hi}, currency={self.currency_code!r})"
