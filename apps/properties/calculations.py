"""
The property billing arithmetic, in one place, with its precision rules stated.

    consumption   = closing_reading - opening_reading               (3 dp, exact)
    billed_units  = consumption * multiplier, rounded to 3 dp        ROUND_HALF_UP
    charge_cents  = billed_units * rate_per_unit_cents, rounded to   ROUND_HALF_UP
                    a whole minor unit (paise / cents)

Readings (3 dp), multipliers (4 dp) and rates (4 dp, in minor units per unit)
are carried as Decimals end to end; nothing passes through a float. Rounding
happens exactly twice, at the two boundaries above, so the same inputs always
produce the same bill.

Worked example from the plan (§7): opening 12000.5, closing 12150.5, rate
₹8.25 = 825 paise/unit -> 150.000 units -> 123750 paise = ₹1,237.50.
"""

from decimal import ROUND_HALF_UP, Decimal

UNITS_QUANTUM = Decimal("0.001")
MINOR_QUANTUM = Decimal("1")


class NegativeConsumption(ValueError):
    """The closing reading is below the opening reading."""


def to_decimal(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


def consumption(opening, closing):
    opening, closing = to_decimal(opening), to_decimal(closing)
    if closing < opening:
        raise NegativeConsumption(f"closing {closing} is below opening {opening}")
    return closing - opening


def billed_units(opening, closing, multiplier=Decimal("1")):
    return (consumption(opening, closing) * to_decimal(multiplier)).quantize(
        UNITS_QUANTUM, rounding=ROUND_HALF_UP
    )


def charge_cents(units, rate_per_unit_cents):
    amount = (to_decimal(units) * to_decimal(rate_per_unit_cents)).quantize(
        MINOR_QUANTUM, rounding=ROUND_HALF_UP
    )
    return int(amount)
