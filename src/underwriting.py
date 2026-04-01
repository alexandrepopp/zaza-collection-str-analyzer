"""Core STR underwriting engine.

Takes a PropertyListing + MarketComps + config assumptions and produces
a complete InvestmentMemo with all financial calculations.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from models import (
    ExpenseBreakdown,
    FinancingDetails,
    FinancingInputs,
    HoldingCosts,
    InvestmentMemo,
    MarketComps,
    PropertyListing,
    Recommendation,
    ReturnMetrics,
    RevenueProjection,
    RiskFactor,
    TaxImpact,
)
from config_loader import (
    get_expense_config,
    get_holding_costs_config,
    get_projection_config,
    get_tax_config,
    get_thresholds,
)


# ─── Revenue ─────────────────────────────────────────────────────────────────

def calculate_revenue(
    adr: float,
    occupancy: float,
    config: dict[str, Any],
) -> RevenueProjection:
    """Calculate annual revenue from ADR and occupancy."""
    exp = get_expense_config(config)
    avg_stay = exp["avg_stay_nights"]

    total_nights = 365 * occupancy
    gross_revenue = adr * total_nights
    total_turnovers = total_nights / avg_stay

    return RevenueProjection(
        gross_revenue=round(gross_revenue, 2),
        adr=adr,
        occupancy_rate=occupancy,
        total_nights_booked=round(total_nights, 1),
        avg_stay_nights=avg_stay,
        total_turnovers=round(total_turnovers, 1),
    )


# ─── Expenses ────────────────────────────────────────────────────────────────

def _lookup_by_bedrooms(bed_dict: dict, bedrooms: int) -> float:
    """Return the value from a bedroom-keyed dict closest to the given count."""
    keys = sorted(int(k) for k in bed_dict.keys())
    best = min(keys, key=lambda k: abs(k - bedrooms))
    return float(bed_dict[best])


def calculate_expenses(
    gross_revenue: float,
    total_turnovers: float,
    listing: PropertyListing,
    config: dict[str, Any],
) -> ExpenseBreakdown:
    """Calculate itemized annual operating expenses."""
    exp = get_expense_config(config)
    beds = listing.bedrooms

    platform_fees = gross_revenue * exp["platform_fees"]

    # Cleaning cost: per-turnover rate from bedroom-keyed table
    cleaning_rate = _lookup_by_bedrooms(exp["cleaning_per_turn"], beds)
    cleaning = total_turnovers * cleaning_rate

    # Property management: 20% of revenue net of cleaning fees
    # (PM earns on bookable revenue, not on pass-through cleaning charges)
    property_management = (gross_revenue - cleaning) * exp["property_management"]

    # Supplies: annual fixed amount from bedroom-keyed table
    supplies = _lookup_by_bedrooms(exp["supplies_by_bedrooms"], beds)

    utilities = exp["utilities_monthly"] * 12
    insurance = exp["insurance_annual"]

    # Property tax: use listing data if available; YAML value "from_listing"
    # signals no formula fallback — use 1% default if listing has no data.
    if listing.property_tax_annual:
        property_tax = listing.property_tax_annual
    else:
        property_tax = listing.price * 0.01  # Conservative 1% default

    hoa = (listing.hoa_monthly or 0.0) * 12

    # Maintenance: annual fixed amount from bedroom-keyed table
    maintenance_reserve = _lookup_by_bedrooms(exp["maintenance_by_bedrooms"], beds)

    lawn_snow = exp["lawn_snow_monthly"] * 12
    pest_control = exp["pest_control_annual"]
    hot_tub_pool = exp["hot_tub_pool_monthly"] * 12
    permits_licenses = exp["permits_licenses_annual"]
    accounting = float(exp.get("accounting_annual", 500))
    software = exp["software_monthly"] * 12

    total = (
        platform_fees + property_management + cleaning + supplies
        + utilities + insurance + property_tax + hoa + maintenance_reserve
        + lawn_snow + pest_control + hot_tub_pool + permits_licenses
        + accounting + software
    )

    return ExpenseBreakdown(
        platform_fees=round(platform_fees, 2),
        property_management=round(property_management, 2),
        cleaning=round(cleaning, 2),
        supplies=round(supplies, 2),
        utilities=round(utilities, 2),
        insurance=round(insurance, 2),
        property_tax=round(property_tax, 2),
        hoa=round(hoa, 2),
        maintenance_reserve=round(maintenance_reserve, 2),
        lawn_snow=round(lawn_snow, 2),
        pest_control=round(pest_control, 2),
        hot_tub_pool=round(hot_tub_pool, 2),
        permits_licenses=round(permits_licenses, 2),
        accounting=round(accounting, 2),
        software=round(software, 2),
        total_expenses=round(total, 2),
        expense_ratio=round(total / gross_revenue, 4) if gross_revenue else 0,
    )


# ─── Financing ───────────────────────────────────────────────────────────────

def calculate_financing(
    price: float,
    financing_inputs: FinancingInputs,
    config: dict[str, Any],
    rehab_budget: float = 0.0,
) -> FinancingDetails:
    """Calculate loan details and cash required to close.

    Uses user-provided FinancingInputs (down payment %, rate, loan type)
    rather than config defaults.  rehab_budget is treated as an all-cash
    outlay added on top of down payment + closing costs.

    Mortgage insurance applies only when down_payment_pct <= 10%.
    """
    down_payment = price * financing_inputs.down_payment_pct
    loan_amount = price - down_payment
    closing_costs = price * financing_inputs.closing_cost_pct
    point_cost = loan_amount * (financing_inputs.points / 100)
    credits = financing_inputs.seller_closing_credits
    total_cash = down_payment + closing_costs + point_cost + rehab_budget - credits

    # Monthly P&I using standard amortization formula.
    # For ARMs we model at the initial fixed rate for the full term —
    # conservative underwrite; rate-adjustment risk is flagged separately.
    rate = financing_inputs.interest_rate
    term = financing_inputs.loan_term_years
    monthly_rate = rate / 12
    n_payments = term * 12
    if monthly_rate > 0:
        monthly_payment = loan_amount * (
            monthly_rate * (1 + monthly_rate) ** n_payments
        ) / ((1 + monthly_rate) ** n_payments - 1)
    else:
        monthly_payment = loan_amount / n_payments

    # Mortgage insurance — only charged when down payment is 10% or less
    mi_annual = 0.0
    if financing_inputs.down_payment_pct <= 0.10:
        exp = get_expense_config(config)
        mi_rate = exp.get("mortgage_insurance_annual_pct", 0.005)
        mi_annual = loan_amount * mi_rate

    annual_debt_service = monthly_payment * 12 + mi_annual

    return FinancingDetails(
        purchase_price=price,
        down_payment=round(down_payment, 2),
        loan_amount=round(loan_amount, 2),
        closing_costs=round(closing_costs + point_cost, 2),
        seller_closing_credits=round(credits, 2),
        total_cash_required=round(total_cash, 2),
        monthly_payment=round(monthly_payment, 2),
        mortgage_insurance_annual=round(mi_annual, 2),
        annual_debt_service=round(annual_debt_service, 2),
        interest_rate=rate,
        loan_term_years=term,
        loan_type=financing_inputs.loan_type_label,
    )


# ─── Returns ─────────────────────────────────────────────────────────────────

def calculate_returns(
    revenue: RevenueProjection,
    expenses: ExpenseBreakdown,
    financing: FinancingDetails,
    config: dict[str, Any],
) -> ReturnMetrics:
    """Calculate core return metrics and multi-year projections."""
    proj = get_projection_config(config)

    noi = revenue.gross_revenue - expenses.total_expenses
    cash_flow = noi - financing.annual_debt_service
    total_cash_in = financing.total_cash_required

    coc = cash_flow / total_cash_in if total_cash_in else 0
    cap_rate = noi / financing.purchase_price if financing.purchase_price else 0
    gross_yield = revenue.gross_revenue / financing.purchase_price if financing.purchase_price else 0
    dscr = noi / financing.annual_debt_service if financing.annual_debt_service else 999

    # Multi-year equity projections
    appreciation = proj["annual_appreciation"]
    rev_growth = proj["annual_revenue_growth"]
    exp_growth = proj["annual_expense_growth"]

    year3_equity = _project_equity(financing, revenue, expenses, appreciation, rev_growth, exp_growth, 3)
    year5_equity = _project_equity(financing, revenue, expenses, appreciation, rev_growth, exp_growth, 5)

    year3_roe = (year3_equity - total_cash_in) / total_cash_in if total_cash_in else 0
    year5_roe = (year5_equity - total_cash_in) / total_cash_in if total_cash_in else 0

    return ReturnMetrics(
        noi=round(noi, 2),
        cash_flow_before_tax=round(cash_flow, 2),
        cash_on_cash_return=round(coc, 4),
        cap_rate=round(cap_rate, 4),
        gross_yield=round(gross_yield, 4),
        dscr=round(dscr, 2),
        year3_equity=round(year3_equity, 2),
        year3_roe=round(year3_roe, 4),
        year5_equity=round(year5_equity, 2),
        year5_roe=round(year5_roe, 4),
    )


def _project_equity(
    financing: FinancingDetails,
    revenue: RevenueProjection,
    expenses: ExpenseBreakdown,
    appreciation: float,
    rev_growth: float,
    exp_growth: float,
    years: int,
) -> float:
    """Project total equity position at year N.

    Equity = property value - remaining loan balance + cumulative cash flow
    """
    property_value = financing.purchase_price * (1 + appreciation) ** years

    # Approximate remaining loan balance
    monthly_rate = financing.interest_rate / 12
    n_total = financing.loan_term_years * 12
    n_paid = years * 12
    if monthly_rate > 0:
        balance = financing.loan_amount * (
            (1 + monthly_rate) ** n_total - (1 + monthly_rate) ** n_paid
        ) / ((1 + monthly_rate) ** n_total - 1)
    else:
        balance = financing.loan_amount * (1 - n_paid / n_total)

    # Cumulative cash flow (growing revenue, growing expenses)
    cumulative_cf = 0.0
    for y in range(1, years + 1):
        yr_rev = revenue.gross_revenue * (1 + rev_growth) ** (y - 1)
        yr_exp = expenses.total_expenses * (1 + exp_growth) ** (y - 1)
        yr_noi = yr_rev - yr_exp
        yr_cf = yr_noi - financing.annual_debt_service
        cumulative_cf += yr_cf

    return (property_value - balance) + cumulative_cf


# ─── Tax / Cost Segregation ──────────────────────────────────────────────────

def calculate_tax_impact(
    price: float,
    config: dict[str, Any],
    financing: FinancingDetails,
    rehab_budget: float = 0.0,
) -> TaxImpact:
    """Estimate Year 1 tax impact from cost segregation + bonus depreciation.

    rehab_budget is added to the depreciable basis — capital improvements
    increase the property's basis and are eligible for cost segregation and
    bonus depreciation treatment just like the acquisition cost.

    financing.total_cash_required is used for the effective Year 1 cost
    calculation (replaces the old config-derived cash-in figure).
    """
    tax = get_tax_config(config)
    cs = tax["cost_seg"]

    land_value = price * cs["land_value_pct"]
    # Rehab/improvements are 100% depreciable (no land component)
    depreciable_basis = (price - land_value) + rehab_budget

    personal_property = depreciable_basis * cs["personal_property_pct"]
    land_improvements = depreciable_basis * cs["land_improvements_pct"]
    building = depreciable_basis * cs["building_pct"]

    bonus_rate = tax["bonus_depreciation_rate"]

    # Federal Year 1 depreciation
    bonus_on_personal = personal_property * bonus_rate
    bonus_on_land_impr = land_improvements * bonus_rate
    # Straight-line on remaining basis after bonus
    sl_personal = (personal_property - bonus_on_personal) / 7  # 7-year avg
    sl_land_impr = (land_improvements - bonus_on_land_impr) / 15
    sl_building = building / 27.5

    year1_bonus = bonus_on_personal + bonus_on_land_impr
    year1_sl = sl_personal + sl_land_impr + sl_building
    year1_total_federal = year1_bonus + year1_sl

    # California: NO bonus depreciation, straight-line only
    ca_sl_personal = personal_property / 7
    ca_sl_land_impr = land_improvements / 15
    ca_sl_building = building / 27.5
    year1_ca = ca_sl_personal + ca_sl_land_impr + ca_sl_building

    # Long-term straight-line depreciation: (total cost basis - land value) / 39
    # depreciable_basis already equals (price - land_value) + rehab_budget,
    # which is the same as (total cost basis - land value).
    long_term_depreciation_annual = depreciable_basis / 39

    # Tax savings — CA state_marginal_rate excluded from config (CA does not
    # allow STR losses to offset state income), so CA savings = 0.
    federal_savings = year1_total_federal * tax["federal_marginal_rate"]
    ca_savings = 0.0
    total_savings = federal_savings + ca_savings

    # Effective Year 1 cost = total cash deployed minus federal tax benefit
    total_cash_in = financing.total_cash_required

    return TaxImpact(
        depreciable_basis=round(depreciable_basis, 2),
        land_value=round(land_value, 2),
        personal_property_basis=round(personal_property, 2),
        land_improvement_basis=round(land_improvements, 2),
        building_basis=round(building, 2),
        year1_bonus_depreciation=round(year1_bonus, 2),
        year1_straight_line=round(year1_sl, 2),
        year1_total_depreciation=round(year1_total_federal, 2),
        year1_ca_depreciation=round(year1_ca, 2),
        long_term_depreciation_annual=round(long_term_depreciation_annual, 2),
        federal_tax_savings=round(federal_savings, 2),
        ca_tax_savings=round(ca_savings, 2),
        total_tax_savings=round(total_savings, 2),
        effective_year1_cost=round(total_cash_in - total_savings, 2),
    )


# ─── Risk Assessment ─────────────────────────────────────────────────────────

def assess_risks(
    listing: PropertyListing,
    market: MarketComps,
    returns: ReturnMetrics,
    financing: FinancingDetails | None = None,
) -> list[RiskFactor]:
    """Generate risk factors based on property and market data."""
    risks: list[RiskFactor] = []

    # DSCR risk
    if returns.dscr < 1.25:
        severity = "high" if returns.dscr < 1.0 else "medium"
        risks.append(RiskFactor(
            category="financial",
            description=f"DSCR of {returns.dscr:.2f} is below target of 1.25. "
            f"Property may not cover debt service under stress scenarios.",
            severity=severity,
        ))

    # Low confidence data
    if market.confidence == "low":
        risks.append(RiskFactor(
            category="market",
            description="Revenue estimates based on low-confidence data "
            f"(source: {market.data_source}). Recommend validating with AirDNA "
            "or local PM operator before proceeding.",
            severity="high",
        ))

    # High price point
    if listing.price > 1_500_000:
        risks.append(RiskFactor(
            category="financial",
            description=f"Purchase price of ${listing.price:,.0f} represents "
            "significant capital concentration in a single asset.",
            severity="medium",
        ))

    # Regulatory risk (blanket for popular STR markets)
    risks.append(RiskFactor(
        category="regulatory",
        description="Verify local STR regulations, permit requirements, "
        "and any pending ordinance changes. Check county/city zoning "
        "and HOA restrictions.",
        severity="medium",
    ))

    # Seasonality
    risks.append(RiskFactor(
        category="operational",
        description="Revenue is seasonal. Ensure cash reserves cover "
        "off-peak months (typically Jan-Feb). Model assumes blended "
        "annual occupancy.",
        severity="low",
    ))

    # ARM rate-adjustment risk
    if financing and financing.loan_type.startswith(("5/1", "7/1", "10/1")):
        risks.append(RiskFactor(
            category="financial",
            description=f"Loan is an {financing.loan_type}. After the initial "
            "fixed period, rate adjustments could materially increase debt "
            "service. Model uses the initial rate for all projections. "
            "Stress-test at +2% before committing.",
            severity="medium",
        ))

    return risks


# ─── Recommendation Engine ───────────────────────────────────────────────────

def generate_recommendation(
    returns: ReturnMetrics,
    tax: TaxImpact,
    config: dict[str, Any],
) -> tuple[Recommendation, str]:
    """Generate buy/pass recommendation based on return thresholds."""
    thresholds = get_thresholds(config)

    coc = returns.cash_on_cash_return
    dscr = returns.dscr
    cap = returns.cap_rate

    coc_thresh = thresholds["cash_on_cash"]
    # Fallback defaults if not defined in YAML thresholds block
    dscr_thresh = thresholds.get("dscr", {"target": 1.25, "minimum": 1.0})
    cap_thresh = thresholds.get("cap_rate", {"target": 0.08, "minimum": 0.06})

    reasons: list[str] = []

    # Score the deal
    score = 0

    if coc >= coc_thresh["strong_buy"]:
        score += 3
        reasons.append(f"CoC return of {coc:.1%} exceeds strong-buy threshold of {coc_thresh['strong_buy']:.0%}")
    elif coc >= coc_thresh["buy"]:
        score += 2
        reasons.append(f"CoC return of {coc:.1%} meets buy threshold")
    elif coc >= coc_thresh["hold"]:
        score += 1
        reasons.append(f"CoC return of {coc:.1%} is marginal (hold range)")
    else:
        score -= 2
        reasons.append(f"CoC return of {coc:.1%} is below minimum threshold of {coc_thresh['pass']:.0%}")

    if dscr >= dscr_thresh["target"]:
        score += 1
        reasons.append(f"DSCR of {dscr:.2f} provides adequate debt service coverage")
    elif dscr < dscr_thresh["minimum"]:
        score -= 3
        reasons.append(f"DSCR of {dscr:.2f} is below 1.0 — property does not cover debt service")

    if cap >= cap_thresh["target"]:
        score += 1
    elif cap < cap_thresh["minimum"]:
        score -= 1
        reasons.append(f"Cap rate of {cap:.1%} is below minimum of {cap_thresh['minimum']:.0%}")

    # Tax benefit bonus
    tax_benefit_pct = tax.total_tax_savings / (tax.depreciable_basis + tax.land_value)
    if tax_benefit_pct > 0.05:
        reasons.append(
            f"Year 1 tax savings of ${tax.total_tax_savings:,.0f} "
            f"significantly reduces effective cost basis"
        )

    # Map score to recommendation
    if score >= 4:
        rec = Recommendation.STRONG_BUY
    elif score >= 2:
        rec = Recommendation.BUY
    elif score >= 0:
        rec = Recommendation.HOLD
    else:
        rec = Recommendation.PASS

    rationale = " | ".join(reasons)
    return rec, rationale


# ─── Holding Costs ───────────────────────────────────────────────────────────

def calculate_holding_costs(
    listing: PropertyListing,
    financing: FinancingDetails,
    config: dict[str, Any],
) -> HoldingCosts:
    """Calculate the 3-month carrying cost reserve before the property goes live.

    Covers fixed ownership costs only — not guest-facing operating expenses.
    Sources each line item from config, listing data, or the already-computed
    FinancingDetails so no double-counting occurs.
    """
    hc = get_holding_costs_config(config)
    exp = get_expense_config(config)
    months = int(hc.get("months", 3))

    # ── Utilities (from holding_costs config) ─────────────────────────────
    internet    = hc["internet_monthly"]    * months
    water       = hc["water_monthly"]       * months
    electricity = hc["electricity_monthly"] * months
    natural_gas = hc["natural_gas_monthly"] * months
    garbage     = hc["garbage_monthly"]     * months

    # ── Fixed recurring ownership costs (from expenses config) ────────────
    pest_control    = (exp["pest_control_annual"] / 12)      * months
    pool_maint      = exp["hot_tub_pool_monthly"]            * months
    landscaping     = exp["lawn_snow_monthly"]               * months

    # ── Property-level costs ──────────────────────────────────────────────
    # Property tax: use listing value if available, else 1% default
    annual_tax = listing.property_tax_annual or (listing.price * 0.01)
    property_taxes  = (annual_tax / 12) * months

    home_insurance  = (exp["insurance_annual"] / 12) * months

    # ── Mortgage (P&I + MI already rolled into annual_debt_service) ───────
    mortgage = (financing.annual_debt_service / 12) * months

    total = (
        internet + water + electricity + natural_gas + garbage
        + pest_control + pool_maint + landscaping
        + property_taxes + home_insurance + mortgage
    )

    return HoldingCosts(
        months=months,
        internet=round(internet, 2),
        water=round(water, 2),
        electricity=round(electricity, 2),
        natural_gas=round(natural_gas, 2),
        pest_control=round(pest_control, 2),
        pool_maintenance=round(pool_maint, 2),
        landscaping=round(landscaping, 2),
        garbage_supplies=round(garbage, 2),
        property_taxes=round(property_taxes, 2),
        home_insurance=round(home_insurance, 2),
        mortgage=round(mortgage, 2),
        total=round(total, 2),
    )


# ─── Main Orchestrator ───────────────────────────────────────────────────────

def underwrite(
    listing: PropertyListing,
    market: MarketComps,
    config: dict[str, Any],
    financing_inputs: FinancingInputs,
) -> InvestmentMemo:
    """Run the full underwriting pipeline and return a complete InvestmentMemo."""

    revenue = calculate_revenue(market.avg_adr, market.avg_occupancy, config)
    expenses = calculate_expenses(
        revenue.gross_revenue, revenue.total_turnovers, listing, config
    )
    financing = calculate_financing(
        listing.price, financing_inputs, config, rehab_budget=listing.rehab_budget
    )

    # Holding costs depend on the computed financing (for the mortgage line),
    # so they are calculated after financing is finalized. The total is then
    # folded back into total_cash_required as a named reserve line item.
    holding_costs = calculate_holding_costs(listing, financing, config)
    financing = FinancingDetails(
        **{k: v for k, v in financing.model_dump().items()
           if k not in ("holding_costs_reserve", "total_cash_required")},
        holding_costs_reserve=holding_costs.total,
        total_cash_required=financing.total_cash_required + holding_costs.total,
    )

    returns = calculate_returns(revenue, expenses, financing, config)
    tax = calculate_tax_impact(
        listing.price, config, financing, rehab_budget=listing.rehab_budget
    )
    risks = assess_risks(listing, market, returns, financing=financing)
    recommendation, rationale = generate_recommendation(returns, tax, config)

    return InvestmentMemo(
        property=listing,
        market=market,
        revenue=revenue,
        expenses=expenses,
        financing=financing,
        holding_costs=holding_costs,
        returns=returns,
        tax=tax,
        risks=risks,
        recommendation=recommendation,
        recommendation_rationale=rationale,
        analysis_date=date.today().isoformat(),
        data_confidence=market.confidence,
    )
