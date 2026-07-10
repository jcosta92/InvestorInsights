"""
Resolves a ticker to its StockAnalysis.com URL, covering both plain US
listings (stockanalysis.com/stocks/{ticker}/) and exchange-qualified listings
from any other exchange StockAnalysis covers (stockanalysis.com/quote/{exchange}/{ticker}/).

Uses StockAnalysis's own autocomplete/search API (the one behind the search
box on their site) to look up which URL form a ticker belongs to, instead of
assuming every ticker is a US listing.
"""

from typing import Any, Dict, List, Optional

import requests

SEARCH_URL = "https://stockanalysis.com/api/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class TickerNotFoundError(Exception):
    pass


class TickerAmbiguousError(Exception):
    def __init__(self, ticker: str, candidates: List[Dict[str, Any]]):
        self.ticker = ticker
        self.candidates = candidates
        listing = ", ".join(
            f"{c['exchange'] or 'US'}:{c['ticker']} ({c['name']})" for c in candidates
        )
        super().__init__(
            f"Ticker '{ticker}' matches listings on multiple exchanges: {listing}. "
            "Pass exchange=... to disambiguate."
        )


_search_cache: Dict[str, List[Dict[str, Any]]] = {}


def clear_cache() -> None:
    """Drops all cached search results (mainly useful for tests)."""
    _search_cache.clear()


def search_stockanalysis(query: str) -> List[Dict[str, Any]]:
    """Results from StockAnalysis's autocomplete/search API, cached per query
    (case-insensitive) so repeated lookups of the same ticker/name — e.g. in a
    peer-ratio loop — don't re-hit the network."""
    key = query.strip().lower()
    if key in _search_cache:
        return _search_cache[key]

    resp = requests.get(SEARCH_URL, params={"q": query}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    _search_cache[key] = data
    return data


def _to_candidate(entry: Dict[str, Any]) -> Dict[str, Any]:
    slug = entry.get("s", "")
    if "/" in slug:
        exchange, tick = slug.split("/", 1)
    else:
        exchange, tick = None, slug

    entry_type = entry.get("t")
    sub_type = entry.get("st")
    is_stock = (sub_type == "s") if entry_type == "sy" else (entry_type == "s")

    return {
        "ticker": tick.upper(),
        "exchange": exchange.lower() if exchange else None,
        "name": entry.get("n", ""),
        "is_stock": is_stock,
        "slug": slug,
    }


def resolve_ticker(ticker: str, exchange: Optional[str] = None) -> Dict[str, Any]:
    """
    Resolves a ticker (optionally scoped to an exchange) to its StockAnalysis
    listing, e.g. {"ticker": "ENR", "exchange": "etr", "name": "Siemens Energy AG", ...}.

    When `exchange` isn't given and the ticker matches listings on several
    exchanges, a single plain "home" listing is preferred, and duplicate
    cross-listings of the *same* company (e.g. Apple trading on secondary
    exchanges under the same ticker) collapse to one result. Ambiguity is
    only raised when the ticker maps to genuinely different companies on
    different exchanges (e.g. "ENR" = Energizer Holdings on NYSE vs. Siemens
    Energy on etr/swx/vie/fra) and no exchange was given to disambiguate.

    Raises TickerNotFoundError if nothing matches, or TickerAmbiguousError if
    still ambiguous after the above.
    """
    ticker_up = ticker.upper()
    candidates = [
        c for c in (_to_candidate(e) for e in search_stockanalysis(ticker))
        if c["is_stock"] and c["ticker"] == ticker_up
    ]

    if exchange:
        exchange_low = exchange.lower()
        candidates = [c for c in candidates if c["exchange"] == exchange_low]

    if not candidates:
        where = f" on exchange '{exchange}'" if exchange else ""
        raise TickerNotFoundError(f"No StockAnalysis listing found for ticker '{ticker}'{where}.")

    if len(candidates) == 1:
        return candidates[0]

    if exchange:
        # exchange already pinned the match down; if several rows slipped
        # through (shouldn't normally happen) just take the first.
        return candidates[0]

    # prefer the plain "home" listing (no exchange prefix) when present
    home = [c for c in candidates if c["exchange"] is None]
    if home:
        return home[0]

    # otherwise, collapse cross-listings of the same company into one result
    distinct_names = {c["name"] for c in candidates}
    if len(distinct_names) == 1:
        return candidates[0]

    # same ticker, genuinely different companies on different exchanges
    raise TickerAmbiguousError(ticker, candidates)


def get_stockanalysis_base_url(ticker: str, exchange: Optional[str] = None) -> str:
    """
    Returns the base StockAnalysis.com URL for a ticker, e.g.:
        https://stockanalysis.com/stocks/AAPL
        https://stockanalysis.com/quote/etr/ENR
    """
    match = resolve_ticker(ticker, exchange=exchange)
    if match["exchange"]:
        return f"https://stockanalysis.com/quote/{match['exchange']}/{match['ticker']}"
    return f"https://stockanalysis.com/stocks/{match['ticker']}"


if __name__ == "__main__":
    print(get_stockanalysis_base_url("AAPL"))
    print(get_stockanalysis_base_url("ENR", exchange="etr"))
    print(get_stockanalysis_base_url("6503", exchange="tyo"))
