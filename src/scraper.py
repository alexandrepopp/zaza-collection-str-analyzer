"""Property data extraction from Zillow listings.

Phase 1: Uses web fetch (via Claude Code's built-in tools) to extract
listing data from a Zillow URL. The agent will call this module's
parse functions on the raw page content.

Phase 2+: Swap in RapidAPI Zillow endpoint or MCP server for
structured data extraction.
"""

from __future__ import annotations

import json
import re
from models import PropertyListing


def parse_zillow_url(url: str) -> dict:
    """Extract the Zillow property ID (zpid) from a URL.

    Returns dict with zpid and normalized URL.
    """
    # Match patterns like /homedetails/123-Main-St/12345678_zpid/
    zpid_match = re.search(r"/(\d+)_zpid", url)
    if zpid_match:
        return {"zpid": zpid_match.group(1), "url": url}
    raise ValueError(f"Could not extract zpid from URL: {url}")


def parse_listing_from_text(raw_text: str, url: str | None = None) -> PropertyListing:
    """Parse property details from raw page text or pasted listing info.

    This is a best-effort parser. In Claude Code, the agent should:
    1. Use web_fetch to get the Zillow page content
    2. Pass the text content to this function
    3. Review and correct any parsing errors

    The agent can also construct a PropertyListing directly from
    structured data if it extracts fields via other means.
    """
    # This function provides extraction helpers the agent can use.
    # In practice, Claude Code will likely extract fields directly
    # from the page content using its own reasoning rather than
    # relying on brittle regex patterns.

    listing = PropertyListing(
        address=_extract_or_prompt("address", raw_text),
        city=_extract_or_prompt("city", raw_text),
        state=_extract_or_prompt("state", raw_text),
        zip_code=_extract_or_prompt("zip", raw_text),
        price=_extract_price(raw_text),
        bedrooms=_extract_int(raw_text, r"(\d+)\s*(?:bed|br|bedroom)", 0),
        bathrooms=_extract_float(raw_text, r"(\d+\.?\d*)\s*(?:bath|ba|bathroom)", 0),
        sqft=_extract_int(raw_text, r"([\d,]+)\s*(?:sq\s*ft|sqft|square feet)", 0),
        listing_url=url,
    )
    return listing


def build_listing_manual(
    address: str,
    city: str,
    state: str,
    zip_code: str,
    price: float,
    bedrooms: int,
    bathrooms: float,
    sqft: int,
    **kwargs,
) -> PropertyListing:
    """Build a PropertyListing from manual input arguments."""
    return PropertyListing(
        address=address,
        city=city,
        state=state,
        zip_code=zip_code,
        price=price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        sqft=sqft,
        **kwargs,
    )


# ─── Extraction Helpers ──────────────────────────────────────────────────────

def _extract_price(text: str) -> float:
    """Try to pull a price from text like '$850,000' or '850000'."""
    match = re.search(r"\$?([\d,]+(?:\.\d{2})?)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return 0.0


def _extract_int(text: str, pattern: str, default: int = 0) -> int:
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(",", ""))
    return default


def _extract_float(text: str, pattern: str, default: float = 0.0) -> float:
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", ""))
    return default


def _extract_or_prompt(field: str, text: str) -> str:
    """Placeholder — in agent mode, Claude will extract or ask the user."""
    return f"[{field} — extract from listing]"
