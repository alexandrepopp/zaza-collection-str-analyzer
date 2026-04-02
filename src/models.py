"""Data models for STR investment analysis."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


# ─── Property Data ───────────────────────────────────────────────────────────

class PropertyListing(BaseModel):
    """Raw property listing data extracted from Zillow or manual input."""
    address: str
    city: str
    state: str
    zip_code: str
    price: float
    bedrooms: int
    bathrooms: float
    sqft: int
    lot_sqft: int | None = None
    year_built: int | None = None
    property_type: str | None = None  # Single Family, Cabin, Condo, etc.
    hoa_monthly: float = 0.0
    property_tax_annual: float | None = None
    listing_url: str | None = None
    market_name: str | None = None  # e.g. "Gatlinburg", "Scottsdale", "Destin"
    rehab_budget: float = 0.0  # Estimated cost of planned rehab/improvements (added to cash-in and depreciable basis)


# ─── Financing Inputs (collected interactively or via CLI) ───────────────────

class FinancingInputs(BaseModel):
    """User-provided financing terms for the acquisition."""
    down_payment_pct: float          # e.g. 0.25 for 25%
    interest_rate: float             # annual, e.g. 0.075 for 7.5%
    loan_type: str                   # "conventional_30yr" | "dscr_30yr" | "arm_5_1" | "arm_7_1" | "arm_10_1"
    loan_term_years: int = 30        # amortization term (initial period for ARMs)
    closing_cost_pct: float = 0.03   # standard ~3%; not prompted (well-established default)
    points: float = 0.0              # origination points as a percentage of loan amount
    seller_closing_credits: float = 0.0  # one-time credit from seller; reduces cash-to-close

    @property
    def loan_type_label(self) -> str:
        labels = {
            "conventional_30yr": "Conventional 30-Year Fixed",
            "dscr_30yr":         "DSCR 30-Year Fixed",
            "arm_5_1":           "5/1 ARM",
            "arm_7_1":           "7/1 ARM",
            "arm_10_1":          "10/1 ARM",
        }
        return labels.get(self.loan_type, self.loan_type)

    @property
    def is_arm(self) -> bool:
        return self.loan_type.startswith("arm_")


# ─── Market Data ─────────────────────────────────────────────────────────────

class MarketComps(BaseModel):
    """STR market data for the property's location and bedroom count."""
    market_name: str
    bedroom_count: int
    avg_adr: float = Field(description="Average daily rate")
    median_adr: float | None = None
    avg_occupancy: float = Field(description="As decimal, e.g. 0.65")
    avg_revpar: float | None = None
    comparable_count: int | None = None  # How many comps this is based on
    data_source: str = "manual"  # airdna | pricelabs | mashvisor | manual
    confidence: str = "low"  # high | medium | low
    notes: str | None = None


# ─── Financial Model ─────────────────────────────────────────────────────────

class RevenueProjection(BaseModel):
    """Annual revenue estimate."""
    gross_revenue: float
    adr: float
    occupancy_rate: float
    total_nights_booked: float
    avg_stay_nights: float
    total_turnovers: float


class ExpenseBreakdown(BaseModel):
    """Itemized annual operating expenses."""
    platform_fees: float
    property_management: float
    cleaning: float
    supplies: float
    utilities: float
    insurance: float
    property_tax: float
    hoa: float
    maintenance_reserve: float
    lawn_snow: float
    pest_control: float
    hot_tub_pool: float
    permits_licenses: float
    accounting: float
    software: float
    total_expenses: float
    expense_ratio: float = Field(description="Total expenses / gross revenue")


class HoldingCosts(BaseModel):
    """3-month carrying cost reserve for the period before the property goes live.

    Captures only fixed recurring ownership costs — not guest-facing operating
    expenses. Total is added to total_cash_required in FinancingDetails.
    """
    months: int = 3
    internet: float
    utilities: float          # combined water + electricity + natural gas (bedroom-keyed)
    garbage: float
    pest_control: float
    pool_maintenance: float
    landscaping: float
    property_taxes: float
    home_insurance: float
    mortgage: float
    total: float


class FinancingDetails(BaseModel):
    """Loan and cash requirement details."""
    purchase_price: float
    down_payment: float
    loan_amount: float
    closing_costs: float
    seller_closing_credits: float = 0.0  # negative line item reducing cash-to-close
    holding_costs_reserve: float = 0.0   # 3-month carrying cost reserve (see HoldingCosts)
    total_cash_required: float  # down payment + closing + rehab - credits + holding reserve
    monthly_payment: float  # P&I only
    mortgage_insurance_annual: float = 0.0  # PMI/MIP — only charged when down payment ≤ 10%
    annual_debt_service: float  # P&I + mortgage insurance
    interest_rate: float
    loan_term_years: int
    loan_type: str


class ReturnMetrics(BaseModel):
    """Core investment return calculations."""
    noi: float = Field(description="Net operating income")
    cash_flow_before_tax: float
    cash_on_cash_return: float
    cap_rate: float
    gross_yield: float
    dscr: float
    # Multi-year projections
    year3_equity: float | None = None
    year3_roe: float | None = None
    year5_equity: float | None = None
    year5_roe: float | None = None


class TaxImpact(BaseModel):
    """Cost segregation and depreciation analysis."""
    depreciable_basis: float  # Purchase price - land value
    land_value: float
    # Cost seg breakdown
    personal_property_basis: float  # 5/7 year
    land_improvement_basis: float  # 15 year
    building_basis: float  # 27.5 year
    # Year 1 depreciation
    year1_bonus_depreciation: float  # Federal only — cost seg accelerated deduction
    year1_straight_line: float
    year1_total_depreciation: float  # Federal
    year1_ca_depreciation: float  # California (no bonus)
    # Long-term straight-line depreciation
    long_term_depreciation_annual: float  # (total_cost_basis - land_value) / 39 — annual recurring deduction
    # Tax savings
    federal_tax_savings: float
    ca_tax_savings: float
    total_tax_savings: float
    effective_year1_cost: float  # Total cash in - tax savings


# ─── Recommendation ──────────────────────────────────────────────────────────

class Recommendation(str, Enum):
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    PASS = "PASS"


class RiskFactor(BaseModel):
    """Individual risk item."""
    category: str  # regulatory | market | operational | financial | concentration
    description: str
    severity: str  # high | medium | low


class InvestmentMemo(BaseModel):
    """Complete investment analysis output."""
    property: PropertyListing
    market: MarketComps
    revenue: RevenueProjection
    expenses: ExpenseBreakdown
    financing: FinancingDetails
    holding_costs: HoldingCosts
    returns: ReturnMetrics
    tax: TaxImpact
    risks: list[RiskFactor]
    recommendation: Recommendation
    recommendation_rationale: str
    analysis_date: str
    data_confidence: str  # high | medium | low
