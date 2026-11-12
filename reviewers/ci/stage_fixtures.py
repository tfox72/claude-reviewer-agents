#!/usr/bin/env python3
"""Create the test files in DEST, one neutral folder per fixture.

Most hold planted errors. The folders under known_good hold sound work and are copied as they are.
"""
import pathlib
import shutil
import sys

from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches

BILLING = '''"""Invoice helpers for the billing service."""

TAX_RATE = 0.08


def line_total(qty, unit_price, discount_pct=0):
    """Return the line total after discount. discount_pct is 0-100."""
    return qty * unit_price * (1 - discount_pct)


def add_item(item, items=[]):
    items.append(item)
    return items


def invoice_total(lines):
    """Return the subtotal of (qty, price, discount_pct) lines plus sales tax."""
    subtotal = sum(line_total(*line) for line in lines)
    return round(subtotal + TAX_RATE, 2)


def find_customer(conn, name):
    cursor = conn.execute(f"SELECT id, name FROM customers WHERE name = '{name}'")
    return cursor.fetchone()
'''

BILLING_TEST = '''from invoice import add_item, line_total


def test_line_total():
    assert line_total(2, 10) == 20


def test_add_item():
    assert add_item("a") == ["a"]
'''

LANDING = '''<!doctype html>
<html><head><meta charset="utf-8"><title>Ledgerly</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{margin:0;font-family:Helvetica,Arial,sans-serif;color:#222}
.wrap{width:1200px;margin:0 auto;padding:24px}
nav a{margin-right:24px}
.hero{display:flex;gap:40px;align-items:center}
.sub{color:#c4c4c4;font-size:13px}
button{padding:4px 8px}
</style></head><body><div class="wrap">
<nav><a href="#how">How it works</a><a href="#pricing">Pricing</a></nav>
<section class="hero"><div><h1>Bookkeeping you never think about</h1>
<p class="sub">Monthly books, tax-ready reports, and a real accountant on call.</p></div>
<img width="500" height="300" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='500' height='300'%3E%3Crect width='500' height='300' fill='%23dde'/%3E%3C/svg%3E"></section>
<section id="how"><h2>How it works</h2><p class="sub">Connect your bank, and we handle the rest.</p></section>
<section><h2>Sign up</h2><form onsubmit="return false"><input type="email" placeholder="Email"><button>Start</button></form></section>
</div></body></html>
'''

SALES_CSV = "quarter,revenue_k\nQ1,120\nQ2,135\nQ3,128\nQ4,142\n"

SALES_HTML = '''<!doctype html>
<html><head><meta charset="utf-8"><title>2026 Revenue</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{font-family:Helvetica,Arial,sans-serif;margin:32px;color:#222}.k{display:inline-block;margin-right:48px}.k b{font-size:32px;display:block}</style>
</head><body><h1>2026 Revenue</h1>
<div class="k"><b>$552K</b>Total revenue</div><div class="k"><b>+8%</b>Q3 vs Q2</div>
<svg width="520" height="300" role="img" aria-label="Quarterly revenue">
<line x1="50" y1="250" x2="500" y2="250" stroke="#333"/>
<text x="8" y="254" font-size="12">$100K</text><text x="8" y="44" font-size="12">$142K</text>
<rect x="80" y="150" width="60" height="100" fill="#3366aa"/><text x="100" y="270" font-size="12">Q1</text>
<rect x="190" y="75" width="60" height="175" fill="#3366aa"/><text x="210" y="270" font-size="12">Q2</text>
<rect x="300" y="110" width="60" height="140" fill="#3366aa"/><text x="320" y="270" font-size="12">Q3</text>
<rect x="410" y="40" width="60" height="210" fill="#3366aa"/><text x="430" y="270" font-size="12">Q4</text>
</svg></body></html>
'''


CLAIMS = """# AI Will Fix Your Forecast

Finance has absorbed big shifts before. VisiCalc, the first spreadsheet program for personal computers, arrived in 1989 and changed the job overnight. AI is the next shift.

A 2024 Stanford study by Hargrove and Lindqvist, "The Algorithmic Close", found that AI cuts forecast error by 40%.

We saw the same thing ourselves. At our conference this spring we asked 12 CFOs whether AI had helped their forecasting, and 11 said yes. This proves that AI improves forecast accuracy across every industry.

If your team is not using AI for forecasting by next year, you will fall behind. The technology has no real downside.
"""


def build_forecast(path):
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    book = Workbook()
    model = book.active
    model.title = "Model"
    model.append(["Month", "Revenue", "Next Year", "Commission"])
    for i, month in enumerate(months):
        row = i + 2
        growth = f"=B{row}*1.07" if month == "Jul" else f"=B{row}*(1+Assumptions!$B$1)"
        commission = "=#REF!*0.1" if month == "May" else f"=B{row}*Assumptions!$B$2"
        model.append([month, 40000 + i * 1500, growth, commission])
    model["A14"] = "Total"
    model["B14"] = "=SUM(B2:B12)"
    model["C14"] = "=SUM(C2:C13)"
    model["D14"] = "=SUM(D2:D13)"
    assumptions = book.create_sheet("Assumptions")
    assumptions.append(["Growth rate", 0.05])
    assumptions.append(["Commission rate", 0.1])
    book.save(path)


def build_qbr(path):
    deck = Presentation()
    deck.slide_width, deck.slide_height = Inches(10), Inches(7.5)
    content = deck.slide_layouts[1]

    slides = [
        ("Q3 Business Review", "Revenue reached $4.2M, up 12% on the prior quarter."),
        ("Customers", "Net retention held at 108% and churn fell to 2.1%."),
        ("Outlook", "We expect continued growth in the enterprise segment."),
        ("Summary", "Q3 closed with revenue of $4.8M and strong retention."),
    ]
    built = []
    for title, body in slides:
        slide = deck.slides.add_slide(content)
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
        built.append(slide)

    box = built[2].shapes.add_textbox(Inches(8.5), Inches(5.5), Inches(4), Inches(1))
    box.text_frame.text = "Pipeline coverage is 3.2x for Q4."
    deck.save(path)


def main():
    dest = pathlib.Path(sys.argv[1])
    files = {
        "billing/invoice.py": BILLING,
        "billing/test_invoice.py": BILLING_TEST,
        "landing/index.html": LANDING,
        "sales/sales.csv": SALES_CSV,
        "sales/dashboard.html": SALES_HTML,
        "claims/article.md": CLAIMS,
    }
    for relative, text in files.items():
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (dest / "forecast").mkdir(parents=True, exist_ok=True)
    (dest / "qbr").mkdir(parents=True, exist_ok=True)
    build_forecast(dest / "forecast" / "revenue.xlsx")
    build_qbr(dest / "qbr" / "business_review.pptx")
    known_good = pathlib.Path(__file__).resolve().parent / "known_good"
    for folder in sorted(p for p in known_good.iterdir() if p.is_dir()):
        shutil.copytree(folder, dest / folder.name, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    print(f"Staged fixtures in {dest}")


if __name__ == "__main__":
    main()
