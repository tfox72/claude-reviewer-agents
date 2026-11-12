import sqlite3
from decimal import Decimal

import pytest

from invoice import find_customer, invoice_total, line_total


def test_line_total():
    assert line_total(2, 10) == 20


@pytest.mark.parametrize(
    "qty, price, discount, expected",
    [
        (2, 10, 10, "18"),
        (2, 10, 0, "20"),
        (1, 100, 1, "99"),
        (1, 100, 50, "50"),
        (1, 100, 100, "0"),
        (3, 1, 12.5, "2.625"),
        (1, 100, Decimal("0.5"), "99.5"),
    ],
)
def test_line_total_applies_percentage_discount(qty, price, discount, expected):
    assert line_total(qty, price, discount) == Decimal(expected)


def test_line_total_is_not_rounded():
    assert line_total(2, 1.25, 15) == Decimal("2.125")


def test_line_total_avoids_binary_float_error():
    assert line_total(3, 0.1) == Decimal("0.3")


def test_line_total_accepts_decimal_input():
    assert line_total(Decimal("2"), Decimal("19.99"), Decimal("10")) == Decimal("35.982")


@pytest.mark.parametrize("discount", [-10, -0.01, 100.01, 150])
def test_line_total_rejects_out_of_range_discount(discount):
    with pytest.raises(ValueError):
        line_total(1, 100, discount)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), Decimal("NaN"), Decimal("-Infinity")])
@pytest.mark.parametrize("position", [0, 1, 2])
def test_line_total_rejects_non_finite_values(bad, position):
    args = [1, 100, 10]
    args[position] = bad
    with pytest.raises(ValueError):
        line_total(*args)


@pytest.mark.parametrize("bad", ["2", None, True, False, [1]])
@pytest.mark.parametrize("position", [0, 1, 2])
def test_line_total_rejects_non_numeric_and_boolean_values(bad, position):
    args = [1, 100, 10]
    args[position] = bad
    with pytest.raises(TypeError):
        line_total(*args)


@pytest.mark.parametrize(
    "lines, expected",
    [
        ([(1, 100, 0)], "108.00"),
        ([(1, 100, 10)], "97.20"),
        ([(1, 1000000, 0)], "1080000.00"),
        ([(1, 100, 0), (2, 50, 50)], "162.00"),
    ],
)
def test_invoice_total_includes_tax(lines, expected):
    total = invoice_total(lines)
    assert total == Decimal(expected)
    assert str(total) == expected


def test_invoice_total_of_empty_invoice_is_zero():
    assert str(invoice_total([])) == "0.00"


def test_invoice_total_accepts_lines_without_a_discount():
    assert invoice_total([(2, 50)]) == Decimal("108.00")


def test_invoice_total_accepts_decimal_prices():
    assert invoice_total([(1, Decimal("100"), 0)]) == Decimal("108.00")


@pytest.mark.parametrize(
    "lines, expected",
    [
        # 1.875 * 1.08 = 2.025, which half-even would round to 2.02.
        ([(3, 1.25, 50)], "2.03"),
        ([(2, 1.25, 15)], "2.30"),
        ([(3, 1.00, 12.5)], "2.84"),
        # 0.004 * 1.08 = 0.00432, which is below half a cent, so it rounds down.
        ([(1, Decimal("0.004"), 0)], "0.00"),
    ],
)
def test_invoice_total_rounds_half_up(lines, expected):
    assert invoice_total(lines) == Decimal(expected)


def test_invoice_total_rounds_once_for_the_whole_invoice():
    # Exact: 2.01 * 1.08 = 2.1708. Rounding each line first gives 2.18.
    assert invoice_total([(1, Decimal("1.005")), (1, Decimal("1.005"))]) == Decimal("2.17")
    # Exact: 0.014 * 1.08 = 0.01512. Rounding the subtotal or any tax first gives 0.01.
    assert invoice_total([(1, Decimal("0.014"))]) == Decimal("0.02")


@pytest.mark.parametrize(
    "qty, price, discount, expected",
    [
        (-1, 100, 0, "-100"),
        (1, -100, 0, "-100"),
        (-1, -100, 0, "100"),
        (-2, 10, 10, "-18"),
    ],
)
def test_line_total_allows_negative_quantity_and_price(qty, price, discount, expected):
    assert line_total(qty, price, discount) == Decimal(expected)


@pytest.mark.parametrize("line", [(-1, 100, 10), (1, -100, 10)])
def test_invoice_total_of_a_credit_line_is_negative(line):
    assert str(invoice_total([line])) == "-97.20"


@pytest.mark.parametrize("credit", [(-1, Decimal("1.875")), (1, Decimal("-1.875"))])
def test_invoice_total_rounds_negative_ties_away_from_zero(credit):
    # Exact: -1.875 * 1.08 = -2.025. Rounding toward positive infinity would give -2.02.
    charge = invoice_total([(1, Decimal("1.875"))])
    refund = invoice_total([credit])
    assert charge == Decimal("2.03")
    assert refund == Decimal("-2.03")
    assert charge + refund == 0


def test_invoice_total_nets_credit_lines_before_rounding():
    # Exact: (1.875 - 0.5) * 1.08 = 1.485, a tie that rounds to 1.49.
    assert invoice_total([(1, Decimal("1.875")), (-1, Decimal("0.5"))]) == Decimal("1.49")
    # Exact: (0.014 - 0.004) * 1.08 = 0.0108. Rounding charges and credits separately gives 0.02.
    assert invoice_total([(1, Decimal("0.014")), (-1, Decimal("0.004"))]) == Decimal("0.01")


def test_invoice_total_rejects_a_bad_line():
    with pytest.raises(ValueError):
        invoice_total([(1, 100, 0), (1, 100, 150)])


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, ssn TEXT)"
    )
    connection.executemany(
        "INSERT INTO customers (id, name, ssn) VALUES (?, ?, ?)",
        [(1, "Alice", "111"), (2, "Bob", "222"), (3, "O'Brien", "333")],
    )
    yield connection
    connection.close()


def test_find_customer_returns_the_matching_row(conn):
    assert find_customer(conn, "Bob") == (2, "Bob")


def test_find_customer_returns_none_when_missing(conn):
    assert find_customer(conn, "Nobody") is None


def test_find_customer_handles_an_apostrophe(conn):
    assert find_customer(conn, "O'Brien") == (3, "O'Brien")


@pytest.mark.parametrize(
    "attack",
    [
        "x' OR '1'='1",
        "x' UNION SELECT id, ssn FROM customers WHERE name='Bob' -- ",
        "x'; DROP TABLE customers; -- ",
    ],
)
def test_find_customer_treats_injection_as_a_plain_name(conn, attack):
    assert find_customer(conn, attack) is None
    assert conn.execute("SELECT COUNT(*) FROM customers").fetchone() == (3,)
