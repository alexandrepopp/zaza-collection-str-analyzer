"""STR market data enrichment.

Provides market comps (ADR, occupancy, RevPAR) for a given location
and bedroom count. Supports multiple data sources with fallback chain:

1. AirDNA API (highest confidence)
2. PriceLabs / Mashvisor API
3. Manual user input
4. Conservative defaults from config

In Claude Code agent mode, the agent can also use web search to find
recent market reports, forum posts, or blog articles with STR data
for the target market.
"""

from __future__ import annotations

from typing import Any

from models import MarketComps
from config_loader import get_revenue_defaults


def from_airdna(
    zip_code: str,
    bedrooms: int,
    api_key: str | None = None,
) -> MarketComps | None:
    """Fetch market data from AirDNA API.

    Requires AirDNA API key. Returns None if unavailable.

    TODO Phase 2: Implement AirDNA API integration
    - Endpoint: https://api.airdna.co/v1/market/property_list
    - Returns: ADR, occupancy, revenue by property type and bedroom count
    """
    if not api_key:
        return None

    # Placeholder for API integration
    # response = requests.get(
    #     "https://api.airdna.co/v1/market/overview",
    #     params={"zip_code": zip_code, "bedrooms": bedrooms},
    #     headers={"Authorization": f"Bearer {api_key}"},
    # )
    return None


def from_user_input(
    market_name: str,
    bedrooms: int,
    adr: float,
    occupancy: float,
    data_source: str = "manual",
) -> MarketComps:
    """Build MarketComps from user-provided estimates."""
    return MarketComps(
        market_name=market_name,
        bedroom_count=bedrooms,
        avg_adr=adr,
        avg_occupancy=occupancy,
        avg_revpar=round(adr * occupancy, 2),
        data_source=data_source,
        confidence="medium" if data_source != "manual" else "low",
    )


def from_defaults(
    market_name: str,
    bedrooms: int,
    config: dict[str, Any],
) -> MarketComps:
    """Fall back to conservative defaults from config."""
    adr, occupancy = get_revenue_defaults(config, bedrooms)

    return MarketComps(
        market_name=market_name,
        bedroom_count=bedrooms,
        avg_adr=adr,
        avg_occupancy=occupancy,
        avg_revpar=round(adr * occupancy, 2),
        data_source="config_defaults",
        confidence="low",
        notes="Using conservative defaults. Validate with AirDNA or local PM.",
    )


def get_market_data(
    market_name: str,
    zip_code: str,
    bedrooms: int,
    config: dict[str, Any],
    adr_override: float | None = None,
    occupancy_override: float | None = None,
    airdna_api_key: str | None = None,
) -> MarketComps:
    """Main entry point: try data sources in priority order.

    Priority:
    1. User overrides (if both ADR and occupancy provided)
    2. AirDNA API (if key available)
    3. Config defaults (always available)
    """
    # User overrides take priority
    if adr_override and occupancy_override:
        return from_user_input(
            market_name, bedrooms, adr_override, occupancy_override
        )

    # Try AirDNA
    airdna = from_airdna(zip_code, bedrooms, airdna_api_key)
    if airdna:
        return airdna

    # Fall back to defaults
    return from_defaults(market_name, bedrooms, config)
