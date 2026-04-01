"""STR Investment Analyzer — CLI entry point.

Usage:
    # From a Zillow URL — prompts for rehab budget and financing details
    python src/main.py --url "https://www.zillow.com/homedetails/..."

    # Skip interactive prompts by passing everything directly
    python src/main.py --url "..." --rehab 75000 \\
        --down-payment 0.25 --rate 7.5 --loan-type conventional_30yr

    # Fully manual input (no scraping)
    python src/main.py \\
        --price 850000 --beds 7 --baths 4 --sqft 3200 \\
        --address "123 Mountain View Dr" --city "Gatlinburg" \\
        --state "TN" --zip 37738 --market "Gatlinburg" \\
        --rehab 50000 --down-payment 0.25 --rate 7.5 --loan-type dscr_30yr

    # Batch mode from CSV
    python src/main.py --batch listings.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path  # noqa: F401 — used in run_single_analysis

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import load_config
from market_data import get_market_data
from models import FinancingInputs, PropertyListing
from report import save_markdown, save_xlsx, to_markdown
from scraper import build_listing_manual
from underwriting import underwrite

# Valid loan type identifiers
LOAN_TYPES = {
    "1": "conventional_30yr",
    "2": "dscr_30yr",
    "3": "arm_5_1",
    "4": "arm_7_1",
    "5": "arm_10_1",
}
LOAN_TYPE_LABELS = {
    "conventional_30yr": "Conforming 30-Year Fixed",
    "dscr_30yr":         "DSCR 30-Year Fixed",
    "arm_5_1":           "5/1 ARM (fixed 5 yrs, then adjusts annually)",
    "arm_7_1":           "7/1 ARM (fixed 7 yrs, then adjusts annually)",
    "arm_10_1":          "10/1 ARM (fixed 10 yrs, then adjusts annually)",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a property's potential as an STR investment."
    )
    # Input modes
    parser.add_argument("--url", type=str, help="Zillow listing URL")
    parser.add_argument("--batch", type=str, help="CSV file with multiple listings")

    # Manual property input
    parser.add_argument("--price", type=float, help="Purchase price")
    parser.add_argument("--beds", type=int, help="Number of bedrooms")
    parser.add_argument("--baths", type=float, help="Number of bathrooms")
    parser.add_argument("--sqft", type=int, help="Square footage")
    parser.add_argument("--address", type=str, default="[Manual Entry]")
    parser.add_argument("--city", type=str, default="Unknown")
    parser.add_argument("--state", type=str, default="Unknown")
    parser.add_argument("--zip", type=str, default="00000")
    parser.add_argument("--market", type=str, help="Market name (e.g. Gatlinburg)")
    parser.add_argument("--year-built", type=int, default=None)
    parser.add_argument("--property-tax", type=float, default=None)
    parser.add_argument("--hoa", type=float, default=0.0)

    # Revenue overrides
    parser.add_argument("--adr", type=float, help="Override ADR estimate")
    parser.add_argument("--occupancy", type=float, help="Override occupancy (decimal)")

    # Rehab / improvements
    parser.add_argument(
        "--rehab", type=float, default=None,
        help="Estimated rehab/improvement budget in dollars (e.g. 75000). "
             "If omitted, you will be prompted interactively."
    )

    # Financing (all optional — skips interactive prompts when provided)
    parser.add_argument(
        "--down-payment", type=float, default=None,
        help="Down payment as a decimal (e.g. 0.25 for 25%%). "
             "If omitted, you will be prompted interactively."
    )
    parser.add_argument(
        "--rate", type=float, default=None,
        help="Mortgage interest rate as a percentage (e.g. 7.5 for 7.5%%). "
             "If omitted, you will be prompted interactively."
    )
    parser.add_argument(
        "--loan-type", type=str, default=None,
        choices=list(LOAN_TYPE_LABELS.keys()),
        help=(
            "Loan product: conventional_30yr | dscr_30yr | "
            "arm_5_1 | arm_7_1 | arm_10_1. "
            "If omitted, you will be prompted interactively."
        )
    )
    parser.add_argument(
        "--closing-credits", type=float, default=None,
        help="Seller closing credits in dollars (e.g. 20000). "
             "Reduces cash-to-close. If omitted, you will be prompted interactively."
    )

    # Config
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to custom assumptions YAML"
    )

    # Output
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output file path (markdown). Prints to stdout if not set."
    )
    parser.add_argument(
        "--no-xlsx", action="store_true",
        help="Skip Excel spreadsheet generation."
    )

    return parser.parse_args()


# ─── Interactive Prompts ──────────────────────────────────────────────────────

def prompt_rehab_budget(args: argparse.Namespace) -> float:
    """Ask the user about rehab/improvement plans at the onset.

    Skipped if --rehab was already provided on the command line.
    Returns the rehab budget as a float (0.0 if none planned).
    """
    if args.rehab is not None:
        return float(args.rehab)

    print("\n" + "=" * 60)
    print("  STEP 1 OF 2 — REHAB & IMPROVEMENT BUDGET")
    print("=" * 60)
    print("Do you plan to do any rehab, renovations, or improvements")
    print("on this property before or after acquisition?")
    print("(Examples: furnishing, cosmetic updates, structural work,")
    print(" adding amenities like a hot tub, deck, game room, etc.)\n")

    while True:
        answer = input("  Do you have a rehab/improvement budget? [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            break
        elif answer in ("n", "no"):
            print("  No rehab budget — proceeding with purchase price only.\n")
            return 0.0
        else:
            print("  Please enter 'y' or 'n'.")

    while True:
        raw = input("  Enter your estimated total rehab budget ($): ").strip()
        try:
            budget = float(raw.replace(",", "").replace("$", ""))
            if budget < 0:
                print("  Budget must be a positive number.")
                continue
            print(f"  Rehab budget set to ${budget:,.0f}.\n")
            return budget
        except ValueError:
            print("  Please enter a valid dollar amount (e.g. 75000 or 75,000).")


def prompt_financing_details(args: argparse.Namespace) -> FinancingInputs:
    """Ask the user for their financing terms.

    Each field is skipped if the corresponding CLI flag was already provided.
    Returns a fully-populated FinancingInputs instance.
    """
    all_provided = (
        args.down_payment is not None
        and args.rate is not None
        and args.loan_type is not None
        and args.closing_credits is not None
    )

    if not all_provided:
        print("\n" + "=" * 60)
        print("  STEP 2 OF 2 — FINANCING DETAILS")
        print("=" * 60)
        print("These details feed the financing model directly.\n")

    # ── Down payment ─────────────────────────────────────────────────────────
    if args.down_payment is not None:
        down_pct = float(args.down_payment)
        # Accept either 0.25 or 25 — normalize to decimal
        if down_pct > 1:
            down_pct /= 100
    else:
        while True:
            raw = input("  Down payment percentage (e.g. 25 for 25%): ").strip()
            try:
                val = float(raw.replace("%", "").strip())
                if val <= 0 or val >= 100:
                    print("  Please enter a value between 1 and 99.")
                    continue
                down_pct = val / 100
                print(f"  Down payment: {val:.1f}%")
                break
            except ValueError:
                print("  Please enter a number (e.g. 25).")

    # ── Interest rate ────────────────────────────────────────────────────────
    if args.rate is not None:
        rate = float(args.rate)
        if rate > 1:
            rate /= 100  # normalize 7.5 → 0.075
    else:
        while True:
            raw = input("  Mortgage interest rate (e.g. 7.5 for 7.5%): ").strip()
            try:
                val = float(raw.replace("%", "").strip())
                if val <= 0 or val > 30:
                    print("  Please enter a reasonable rate (e.g. 6.5, 7.25, 8.0).")
                    continue
                rate = val / 100
                print(f"  Interest rate: {val:.3f}%")
                break
            except ValueError:
                print("  Please enter a number (e.g. 7.5).")

    # ── Loan type ────────────────────────────────────────────────────────────
    if args.loan_type is not None:
        loan_type = args.loan_type
    else:
        print("\n  Loan type:")
        for key, label in LOAN_TYPE_LABELS.items():
            num = {v: k for k, v in LOAN_TYPES.items()}[key]
            print(f"    [{num}] {label}")
        while True:
            choice = input("\n  Select loan type [1-5]: ").strip()
            if choice in LOAN_TYPES:
                loan_type = LOAN_TYPES[choice]
                print(f"  Loan type: {LOAN_TYPE_LABELS[loan_type]}")
                break
            else:
                print("  Please enter a number between 1 and 5.")

    # Determine term (all current products are 30-year)
    loan_term_years = 30

    # ── Seller closing credits ────────────────────────────────────────────────
    if args.closing_credits is not None:
        seller_closing_credits = float(args.closing_credits)
    else:
        print()
        print("  Seller closing credits:")
        print("  Will the seller provide any closing cost credits?")
        print("  (Enter 0 if none. Credits reduce your cash needed to close.)\n")
        while True:
            raw = input("  Seller closing credits ($): ").strip()
            try:
                seller_closing_credits = float(raw.replace(",", "").replace("$", ""))
                if seller_closing_credits < 0:
                    print("  Please enter a positive amount (or 0 for none).")
                    continue
                if seller_closing_credits > 0:
                    print(f"  Seller credits: -${seller_closing_credits:,.0f} (reduces cash-to-close)")
                else:
                    print("  No seller credits.")
                break
            except ValueError:
                print("  Please enter a dollar amount (e.g. 20000 or 0).")

    if not all_provided:
        print()  # spacing before analysis begins

    return FinancingInputs(
        down_payment_pct=down_pct,
        interest_rate=rate,
        loan_type=loan_type,
        loan_term_years=loan_term_years,
        seller_closing_credits=seller_closing_credits,
    )


# ─── Analysis Runner ──────────────────────────────────────────────────────────

def run_single_analysis(args: argparse.Namespace) -> None:
    """Run analysis for a single property."""

    # ── Prompt for rehab budget and financing details at the very start ───
    rehab_budget = prompt_rehab_budget(args)
    financing_inputs = prompt_financing_details(args)

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)

    # Build the listing
    if args.url:
        # In Claude Code agent mode, the agent would:
        # 1. web_fetch the URL
        # 2. Parse the content to build a PropertyListing
        # 3. Pass it through the pipeline
        # For CLI mode, require manual input as fallback
        print(f"URL mode: {args.url}")
        print("In Claude Code, the agent will fetch and parse this URL.")
        print("For standalone CLI, provide manual inputs with --price, --beds, etc.")
        if not args.price:
            print("Error: --price is required for CLI mode. Use Claude Code for URL parsing.")
            sys.exit(1)

    if not args.price:
        print("Error: Either --url (in agent mode) or --price (manual) is required.")
        sys.exit(1)

    listing = build_listing_manual(
        address=args.address,
        city=args.city,
        state=args.state,
        zip_code=args.zip,
        price=args.price,
        bedrooms=args.beds or 4,
        bathrooms=args.baths or 2.0,
        sqft=args.sqft or 2000,
        year_built=args.year_built,
        property_tax_annual=args.property_tax,
        hoa_monthly=args.hoa,
        listing_url=args.url,
        market_name=args.market,
        rehab_budget=rehab_budget,
    )

    # Get market data
    market = get_market_data(
        market_name=args.market or args.city,
        zip_code=args.zip,
        bedrooms=listing.bedrooms,
        config=config,
        adr_override=args.adr,
        occupancy_override=args.occupancy,
    )

    # Run underwriting — financing_inputs drives the financing model
    memo = underwrite(listing, market, config, financing_inputs=financing_inputs)

    # ── Markdown output ───────────────────────────────────────────────────
    if args.output:
        save_markdown(memo, args.output)
        md_path = Path(args.output)
    else:
        print(to_markdown(memo))
        md_path = None

    # ── Excel spreadsheet output (auto-generated unless --no-xlsx) ────────
    if not getattr(args, "no_xlsx", False):
        if md_path:
            xlsx_path = md_path.with_suffix(".xlsx")
        else:
            xlsx_path = None  # save_xlsx will auto-derive from address
        save_xlsx(memo, output_path=xlsx_path)


def main():
    args = parse_args()

    if args.batch:
        print("Batch mode not yet implemented. Use single property analysis.")
        print("Tip: In Claude Code, ask the agent to loop through a CSV.")
        sys.exit(1)

    run_single_analysis(args)


if __name__ == "__main__":
    main()
