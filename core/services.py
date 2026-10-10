"""Small, dependency-free money helpers shared across apps.

Every currency value in this project is a Decimal, never a float, to
avoid binary floating-point rounding errors on money.
"""

from decimal import ROUND_HALF_UP, ROUND_UP, Decimal

TWO_PLACES = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    """Round a Decimal to exactly 2 decimal places, bankers'-safe for display."""
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def round_up_to_nearest(amount: Decimal, round_to: Decimal) -> Decimal:
    """Smallest non-negative amount to add to `amount` to reach a multiple of `round_to`.

    Example: amount=4.35, round_to=1.00 -> 0.65 (4.35 + 0.65 = 5.00).
    If `amount` is already an exact multiple of `round_to`, returns 0.
    """
    if round_to <= 0:
        return Decimal("0.00")
    amount = Decimal(amount)
    round_to = Decimal(round_to)
    multiples = (amount / round_to).to_integral_value(rounding=ROUND_UP)
    target = multiples * round_to
    roundup = target - amount
    if roundup < 0:
        roundup = Decimal("0.00")
    return quantize_money(roundup)
