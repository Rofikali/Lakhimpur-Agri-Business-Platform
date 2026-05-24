"""Shared utility functions used across modules."""

import re
from decimal import ROUND_HALF_UP, Decimal

DP2 = Decimal("0.01")
DP5 = Decimal("0.00001")


def slugify(text: str) -> str:
    """Convert product name to URL slug: 'Joha Rice' → 'joha-rice'"""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug.strip("-")


def rupees(value: Decimal, dp: int = 2) -> str:
    """Format Decimal as Indian rupee string: 1234.5 → '₹1,234.50'"""
    quantized = value.quantize(Decimal(f"0.{'0' * dp}"), ROUND_HALF_UP)
    return f"₹{quantized:,}"


def mask_phone(phone: str) -> str:
    """Mask phone for logs: +919876543210 → +91987****210"""
    if len(phone) >= 10:
        return phone[:-7] + "****" + phone[-3:]
    return "****"


def current_month() -> str:
    """Returns current month as 'YYYY-MM'"""
    from datetime import date

    return date.today().strftime("%Y-%m")


def month_date_range(month: str) -> tuple:
    """Returns (start_date, end_date) for a 'YYYY-MM' month string."""
    from datetime import date

    y, m = int(month[:4]), int(month[5:7])
    import calendar

    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)
