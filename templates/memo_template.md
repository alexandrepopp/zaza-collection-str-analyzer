# STR Investment Memo — {{address}}

**Analysis Date:** {{date}}
**Data Confidence:** {{confidence}}
**Recommendation:** **{{recommendation}}**

---

> This template is used by the report generator. The actual output
> is produced by `src/report.py` using structured data from the
> underwriting engine. This file serves as a reference for the
> expected output structure.

## Sections

1. **Property Summary** — Location, price, physical characteristics
2. **Revenue Estimate** — ADR × occupancy × 365, with data source
3. **Expense Breakdown** — Itemized annual OpEx, expense ratio
4. **Financing** — Loan terms, monthly payment, cash to close
5. **Return Metrics** — CoC, gross yield, total return over hold period
6. **Tax Impact** — Cost seg breakdown, Year 1 federal depreciation benefit
7. **Risk Factors** — Regulatory, market, operational, financial
8. **Recommendation** — Scored recommendation with rationale

---

## Section Details

### 1. Property Summary
- Address, market area, zip code
- List price, beds, baths, sqft
- Property type and notable amenities (hot tub, pool, views, etc.)

### 2. Revenue Estimate
- Average Daily Rate (ADR) by season
- Occupancy rate
- Gross annual revenue
- Data source and confidence level (AirDNA / PriceLabs / user-provided / default)

### 3. Expense Breakdown
- Platform fees (3% of gross)
- Property management (20% of gross)
- Cleaning (per turn, based on bedroom count)
- Supplies (annual, based on bedroom count)
- Utilities, insurance, property tax (from listing), maintenance (by bedroom count)
- Lawn/snow, pest control, hot tub/pool, permits, software
- Mortgage insurance (0.5% of loan value annually)
- Total OpEx and expense ratio (% of gross revenue)

### 4. Financing
- Purchase price, down payment (10%), loan amount
- Interest rate (7.0%), loan term (30yr conventional)
- Monthly mortgage payment
- Total cash to close (down payment + closing costs at 3%)

### 5. Return Metrics
- **Cash-on-Cash Return** — annual net cash flow ÷ total cash invested
- **Gross Yield** — gross revenue ÷ purchase price
- **Total Return ({{holding_period_years}}-year hold)** — sum of all holding benefits:
  - Cumulative net cash flow
  - Federal tax savings from depreciation (cost seg + bonus depreciation)
  - Equity from appreciation (at assumed rate — 0% conservative baseline)
  - Equity from mortgage paydown (principal reduction each year)
- Year 1, Year 3, Year 5, Year 10 snapshots

*Note: No exit assumed. DSCR and cap rate are not used as evaluation metrics.*

### 6. Tax Impact
- Depreciable basis (purchase price less land value at 20%)
- Cost segregation breakdown:
  - Personal property (25%) — 5-year MACRS
  - Land improvements (15%) — 15-year MACRS
  - Building (40%) — 39-year straight-line
- Bonus depreciation applied to 5-year and 15-year components (federal only)
- Year 1 federal depreciation deduction and estimated tax benefit at 37% rate
- *California note: CA does not conform to federal bonus depreciation and does not
  allow STR losses to offset CA state income — no state tax benefit modeled.*

### 7. Risk Factors
- **Regulatory** — STR permitting, HOA restrictions, local ordinances
- **Market** — Saturation, comp supply growth, platform dependency
- **Operational** — Seasonality, management quality, capital expenditure risk
- **Financial** — Interest rate sensitivity, vacancy risk, insurance exposure

### 8. Recommendation
Scored against the following thresholds:

| Rating | Cash-on-Cash |
|--------|-------------|
| Strong Buy | ≥ 10% |
| Buy | ≥ 8% |
| Hold | ≥ 6% |
| Pass | < 5% |

Include: primary rationale, key upside drivers, key risks, and any sensitivity notes
(e.g. what if ADR drops 15%? what if occupancy drops 10%?).

---

## Agent Instructions

When generating a memo, follow the structure above and enrich with:

- Narrative commentary between sections
- Market-specific insights from web research
- Comparable property references
- Sensitivity analysis on ADR and occupancy
- 1031 exchange suitability notes if relevant to portfolio context
