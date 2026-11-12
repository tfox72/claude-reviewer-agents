"""Invoice helpers for the billing service."""

from decimal import Decimal, ROUND_HALF_UP

TAX_RATE = Decimal("0.08")
CENT = Decimal("0.01")


def _to_decimal(value, field):
    """Return value as a finite Decimal, or raise if it is not a real number."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise TypeError(f"{field} must be a number, got {type(value).__name__}")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError(f"{field} must be finite, got {value}")
    return number


def line_total(qty, unit_price, discount_pct=0):
    """Return the line total after discount as an exact, unrounded Decimal.

    discount_pct is 0-100. Rounding happens once per invoice, in invoice_total.
    Negative qty or unit_price is allowed, for example on credit notes.
    """
    qty = _to_decimal(qty, "qty")
    unit_price = _to_decimal(unit_price, "unit_price")
    discount_pct = _to_decimal(discount_pct, "discount_pct")
    if not 0 <= discount_pct <= 100:
        raise ValueError(f"discount_pct must be 0-100, got {discount_pct}")
    return qty * unit_price * (1 - discount_pct / 100)


def invoice_total(lines):
    """Return the subtotal of (qty, price, discount_pct) lines plus sales tax.

    The result is a Decimal, rounded half-up to the cent once for the invoice.
    Ties on negative totals round away from zero, so a 2.03 charge and its
    credit of -2.03 cancel exactly.
    """
    subtotal = sum((line_total(*line) for line in lines), Decimal(0))
    return (subtotal * (1 + TAX_RATE)).quantize(CENT, rounding=ROUND_HALF_UP)


def find_customer(conn, name):
    """Return the customer's (id, name) row from sqlite3, or None if not found.

    Customer names are unique, so at most one row can match.
    """
    cursor = conn.execute("SELECT id, name FROM customers WHERE name = ?", (name,))
    return cursor.fetchone()
