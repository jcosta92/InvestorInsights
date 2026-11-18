"""Fallback competitor list when MarketBeat refuses the request.

MarketBeat sits behind a Cloudflare bot challenge that answers plain requests with
HTTP 403 ("Just a moment..."). When that happens competitors_data returns only the
main ticker, the Competitors table in the report has a single row, and every
"in the average of its competitors" rating compares the company with itself.

StockAnalysis (which the scrapers already depend on) links each company to its
industry page, and that page lists every company in the industry with its market
cap. The peers are the companies in the same industry closest in market cap.

Everything here is best-effort: any failure returns an empty list, never an exception.
"""
from __future__ import annotations

import math
import re
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from .fallback import HEADERS, _num

BASE = "https://stockanalysis.com"


def _get(url: str) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        return BeautifulSoup(r.text, "html.parser")
    except Exception:
        return None


def _base_url(ticker: str) -> str:
    """StockAnalysis base URL for the ticker, also for non-US listings (/quote/{exchange}/{ticker})."""
    try:
        from stockanalysis_resolver import get_stockanalysis_base_url
        return get_stockanalysis_base_url(ticker).rstrip("/")
    except Exception:
        return f"{BASE}/stocks/{ticker.lower()}"


def _group_url(base: str, kind: str) -> Optional[str]:
    """Link to the company's industry (kind='industry') or sector (kind='sector') page."""
    for page in (base + "/company/", base + "/"):
        soup = _get(page)
        if soup is None:
            continue
        for a in soup.find_all("a", href=re.compile(rf"^/stocks/{kind}/[^/]+/?$")):
            return BASE + a["href"]
    return None


def _companies(group_url: str) -> List[dict]:
    """Rows of an industry/sector page: [{'ticker': 'AMD', 'market_cap': 8.3e11}, ...]."""
    soup = _get(group_url)
    if soup is None:
        return []
    table = soup.find("table")
    if table is None:
        return []
    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    try:
        sym_i, cap_i = headers.index("symbol"), headers.index("market cap")
    except ValueError:
        return []
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) <= max(sym_i, cap_i):
            continue
        a = tds[sym_i].find("a", href=True)
        # only plain US listings: the ratio scraper builds /stocks/{ticker}/ URLs
        if a is None or not re.match(r"^/stocks/[^/]+/?$", a["href"]):
            continue
        out.append({"ticker": tds[sym_i].get_text(strip=True).upper(),
                    "market_cap": _num(tds[cap_i].get_text(strip=True))})
    return out


def stockanalysis_peers(ticker: str, n: int = 5, market_cap: Optional[float] = None) -> List[str]:
    """Up to n tickers in the same industry (sector if the industry is too small),
    closest in market cap to `ticker`. The main ticker is not included."""
    ticker = ticker.upper()
    base = _base_url(ticker)
    for kind in ("industry", "sector"):
        url = _group_url(base, kind)
        if url is None:
            continue
        rows = [r for r in _companies(url) if r["market_cap"]]
        own = next((r["market_cap"] for r in rows if r["ticker"] == ticker), None) or market_cap
        others = [r for r in rows if r["ticker"] != ticker]
        if len(others) < 2:
            continue
        if own:
            others.sort(key=lambda r: abs(math.log(r["market_cap"]) - math.log(own)))
        else:
            others.sort(key=lambda r: -r["market_cap"])
        return [r["ticker"] for r in others[:n]]
    return []
