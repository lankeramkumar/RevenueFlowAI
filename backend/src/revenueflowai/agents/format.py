"""Human-readable rendering of stored decimal strings for finding statements.
Values are computed exactly and stored as Decimal strings; this only changes
how they read in narrative text, never the number itself.
"""

from decimal import Decimal


def money(raw: str | Decimal) -> str:
    return f"{Decimal(str(raw)).quantize(Decimal('0.01')):,.2f}"


def qty(raw: str | Decimal) -> str:
    return format(Decimal(str(raw)).normalize(), "f")
