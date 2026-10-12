"""Fallback for the company header when Yahoo Finance returns nothing.

yfinance works on a laptop but Yahoo often refuses requests from cloud hosts
(Streamlit Community Cloud included), which left the app with no price, no name, no
analysts and an overall score of 0. This module reads the same facts from
StockAnalysis's overview and company pages (the scrapers already depend on that site)
and returns them under the yfinance field names the report expects.

Everything here is best-effort: any failure returns an empty dict, never an exception.
"""
from __future__ import annotations

import re
from typing import Any, Dict

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# StockAnalysis label (lower case, as shown on the overview page) -> yfinance key
LABELS = {
    "market cap": "marketCap", "pe ratio": "trailingPE", "forward pe": "forwardPE", "beta": "beta",
    "dividend yield": "dividendYield", "eps (ttm)": "trailingEps", "analysts": "recommendationKey",
    "52-week range": "fiftyTwoWeekRange", "previous close": "previousClose", "earnings date": "earningsDate",
    "employees": "fullTimeEmployees", "sector": "sector", "industry": "industry", "country": "country",
    "net income": "netIncomeToCommon", "revenue": "totalRevenue", "profit margin": "profitMargins",
}
MULT = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}


def _num(text: str):
    """'3.21T' -> 3.21e12, '12.5%' -> 12.5, '1,234' -> 1234.0, 'n/a' -> None."""
    t = text.replace(",", "").replace("$", "").strip()
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*([TBMK])?%?$", t)
    if not m:
        return None
    v = float(m.group(1))
    return v * MULT.get(m.group(2), 1)


def _pairs(soup: BeautifulSoup) -> Dict[str, str]:
    """All label/value cell pairs on the page, keyed by lower-case label."""
    out = {}
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) == 2 and cells[0]:
            out.setdefault(cells[0].lower(), cells[1])
    # the overview page also uses <div> pairs for some facts
    for div in soup.find_all("div"):
        kids = [k for k in div.find_all(recursive=False) if k.name in ("span", "div")]
        if len(kids) == 2:
            a, b = kids[0].get_text(" ", strip=True), kids[1].get_text(" ", strip=True)
            if a and b and len(a) < 40:
                out.setdefault(a.lower(), b)
    return out


def _get(url: str) -> BeautifulSoup | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        return BeautifulSoup(r.text, "html.parser")
    except Exception:
        return None


def stockanalysis_overview(ticker: str, base_url: str | None = None) -> Dict[str, Any]:
    base = (base_url or f"https://stockanalysis.com/stocks/{ticker.lower()}").rstrip("/")
    info: Dict[str, Any] = {}
    soup = _get(base + "/")
    if soup is not None:
        h1 = soup.find("h1")
        if h1:
            info["longName"] = re.sub(r"\s*\(.*?\)\s*$", "", h1.get_text(" ", strip=True))
        pairs = _pairs(soup)
        for label, key in LABELS.items():
            if label in pairs:
                raw = pairs[label]
                if key == "recommendationKey":
                    info[key] = re.sub(r"\s*\(.*\)", "", raw).strip().lower().replace(" ", "_")
                elif key == "fiftyTwoWeekRange":
                    lo_hi = re.findall(r"\d+(?:\.\d+)?", raw.replace(",", ""))
                    if len(lo_hi) >= 2:
                        info["fiftyTwoWeekLow"], info["fiftyTwoWeekHigh"] = float(lo_hi[0]), float(lo_hi[1])
                elif key in ("sector", "industry", "country", "earningsDate"):
                    info[key] = raw
                elif key == "dividendYield":
                    m = re.search(r"(\d+(?:\.\d+)?)%", raw)
                    info[key] = float(m.group(1)) if m else None
                elif key == "profitMargins":
                    v = _num(raw.rstrip("%"))
                    info[key] = v / 100 if v is not None else None
                else:
                    info[key] = _num(raw)
        if info.get("previousClose") is not None:
            info["currentPrice"] = info.pop("previousClose")   # the last close; good enough for the header
        if "analysts" in pairs:
            m = re.search(r"\((\d+)\)", pairs["analysts"])
            if m:
                info["numberOfAnalystOpinions"] = int(m.group(1))
        info["currency"] = "USD" if "/stocks/" in base else None

    # facts still missing: the statistics page repeats market cap, dividend yield, beta, margins
    if any(info.get(k) is None for k in ("marketCap", "dividendYield", "beta", "profitMargins")):
        stats = _get(base + "/statistics/")
        if stats is not None:
            pairs = _pairs(stats)
            info.setdefault("_stat_labels", list(pairs)[:80])
            for label, key in (("market cap", "marketCap"), ("dividend yield", "dividendYield"), ("beta (5y)", "beta"),
                               ("beta", "beta"), ("profit margin", "profitMargins"), ("forward pe", "forwardPE"), ("pe ratio", "trailingPE")):
                if info.get(key) is None and label in pairs:
                    raw = pairs[label]
                    if key == "dividendYield":
                        m = re.search(r"(\d+(?:\.\d+)?)%", raw)
                        info[key] = float(m.group(1)) if m else None
                    elif key == "profitMargins":
                        v = _num(raw.rstrip("%")); info[key] = v / 100 if v is not None else None
                    else:
                        info[key] = _num(raw)
    # "Dividend" on the overview reads like "$3.32 (0.62%)"
    if info.get("dividendYield") is None and soup is not None:
        pairs = _pairs(soup)
        for label in ("dividend", "dividend (yield)", "dividend yield"):
            m = re.search(r"\((\d+(?:\.\d+)?)%\)", pairs.get(label, ""))
            if m:
                info["dividendYield"] = float(m.group(1)); break
    # number of analysts lives on the forecast page: "... based on 42 analysts ..."
    if not info.get("numberOfAnalystOpinions"):
        fc = _get(base + "/forecast/")
        if fc is not None:
            m = re.search(r"(\d+)\s+analysts?", fc.get_text(" ", strip=True))
            if m:
                info["numberOfAnalystOpinions"] = int(m.group(1))
    if soup is not None:
        info.setdefault("_overview_labels", list(_pairs(soup))[:80])

    comp = _get(base + "/company/")
    if comp is not None:
        pairs = _pairs(comp)
        for label, key in (("sector", "sector"), ("industry", "industry"), ("country", "country"), ("employees", "fullTimeEmployees")):
            if label in pairs and not info.get(key):
                info[key] = _num(pairs[label]) if key == "fullTimeEmployees" else pairs[label]
        if not info.get("longBusinessSummary"):
            paras = [p.get_text(" ", strip=True) for p in comp.find_all("p")]
            paras = [p for p in paras if len(p) > 200]
            if paras:
                info["longBusinessSummary"] = paras[0]
    return {k: v for k, v in info.items() if v is not None}  # keys starting with _ are diagnostics


def yahoo_is_empty(info: Dict[str, Any]) -> bool:
    return not info or not (info.get("longName") or info.get("currentPrice") or info.get("marketCap"))
