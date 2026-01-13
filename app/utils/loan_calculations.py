from decimal import Decimal, ROUND_HALF_UP


def money(x) -> Decimal:
    """Always return 2-decimal Decimal with HALF_UP rounding."""
    if x is None:
        x = 0
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_interest_total_tenure_flat(
        principal: Decimal,
        interest_rate_percent: Decimal,
) -> Decimal:
    """
    TENURE-FLAT:
      total_interest = principal * (rate% / 100)

    Example:
      principal=22000, rate=12.5 => 2750.00
    """
    principal = money(principal)
    rate = money(interest_rate_percent)  # safe parse
    return money(principal * rate / Decimal("100"))


def compute_interest_total_from_defaults(
        principal: Decimal,
        interest_rate_percent: Decimal,
        week_divider: Decimal,
        duration_weeks: int,
) -> Decimal:
    """
    ANNUAL PRORATED BY WEEKS:
      interest_per_week = (principal * rate%)/week_divider
      total_interest = interest_per_week * duration_weeks
    """
    principal = money(principal)
    if week_divider is None or week_divider <= 0:
        week_divider = Decimal("1")

    r = Decimal(str(interest_rate_percent)) / Decimal("100")
    interest_per_week = (principal * r) / Decimal(str(week_divider))
    return money(interest_per_week * Decimal(int(duration_weeks)))


def build_weekly_schedule(
        principal: Decimal,
        interest_total: Decimal,
        duration_weeks: int,
        fees_total: Decimal = Decimal("0.00"),
):
    """
    Returns:
      principal_week, interest_week, base_installment, first_extra

    base_installment = (principal + interest_total)/weeks (NO fees)
    first_extra = fees_total (added ONLY in installment #1)
    """
    principal = money(principal)
    interest_total = money(interest_total)
    fees_total = money(fees_total)

    weeks = int(duration_weeks)
    if weeks <= 0:
        raise ValueError("duration_weeks must be > 0")

    principal_week = money(principal / weeks)
    interest_week = money(interest_total / weeks)

    base_installment = money(principal_week + interest_week)
    first_extra = fees_total

    return principal_week, interest_week, base_installment, first_extra
