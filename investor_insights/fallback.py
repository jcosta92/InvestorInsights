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
            info["longBusinessSummary"] = pick_description(comp, info.get("longName", ""), ticker)
    return {k: v for k, v in info.items() if v is not None}  # keys starting with _ are diagnostics


BOILERPLATE = ("provided by", "sourced from", "sourced directly", "s&p global", "sec.gov", "eod historical",
               "cookie", "subscribe", "upgrade to", "pro members", "terms of use", "disclaimer", "list of executives")


def pick_description(soup: BeautifulSoup, name: str, ticker: str) -> str | None:
    """The business description from a StockAnalysis company page.
    Skips the data-attribution footer ("The company profile ... is provided by S&P Global ...")
    and prefers paragraphs that talk about the company itself."""
    first_word = (name.split()[0] if name else ticker).lower()
    best, best_score, best_el = None, 0.0, None
    for p in soup.find_all(["p", "div"]):
        if p.find(["p", "div"]):           # only leaf blocks, so we don't take a whole section at once
            continue
        text = p.get_text(" ", strip=True)
        low = text.lower()
        if len(text) < 120 or any(b in low for b in BOILERPLATE):
            continue
        score = len(text)
        if first_word and first_word in low:
            score *= 3
        if any(w in low for w in (" operates", " designs", " provides", " develops", " engages", " manufactures",
                                   " offers", " is a ", " was founded", " was incorporated", " headquartered")):
            score *= 2
        if score > best_score:
            best, best_score, best_el = text, score, p
    # the description is often split over several paragraphs in the same block: keep them together
    if best_el is not None and best_el.parent is not None:
        parts = [s.get_text(" ", strip=True) for s in best_el.parent.find_all("p", recursive=False)]
        parts = [s for s in parts if s and not any(b in s.lower() for b in BOILERPLATE)]
        if best in parts and len(parts) > 1:
            best = " ".join(parts)
    return best


def yahoo_is_empty(info: Dict[str, Any]) -> bool:
    return not info or not (info.get("longName") or info.get("currentPrice") or info.get("marketCap"))


def yahoo_governance(ticker: str) -> Dict[str, Any]:
    """The four ISS governance pillar scores from Yahoo's profile page (HTML, not the API that
    cloud hosts get blocked on). Text looks like: "... pillar scores are Audit: 3; Board: 4;
    Shareholder Rights: 2; Compensation: 5." and "ISS Governance QualityScore ... is 3".
    Returns {} if the page is refused or the sentence is not there."""
    out: Dict[str, Any] = {}
    text = None
    for fetcher in ("curl_cffi", "requests"):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker.upper()}/profile/"
            if fetcher == "curl_cffi":
                from curl_cffi import requests as cr
                r = cr.get(url, impersonate="chrome", timeout=20, headers={"Accept-Language": "en-US,en;q=0.9"})
            else:
                r = requests.get(url, headers={**HEADERS, "Accept-Language": "en-US,en;q=0.9"}, timeout=20)
            if r.status_code == 200 and "overnance" in r.text:
                text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
                break
            out["_governance_http"] = f"{fetcher}: HTTP {r.status_code}"
        except Exception as e:
            out["_governance_http"] = f"{fetcher}: {e.__class__.__name__}"
    if not text:
        # last resort: a public page-to-text relay, which reaches Yahoo from a different network
        try:
            r = requests.get(f"https://r.jina.ai/https://finance.yahoo.com/quote/{ticker.upper()}/profile/",
                             headers={"Accept": "text/plain", "X-No-Cache": "true"}, timeout=40)
            if r.status_code == 200 and "overnance" in r.text:
                text = r.text
            else:
                out["_governance_http"] = (out.get("_governance_http", "") + f"; relay: HTTP {r.status_code}").strip("; ")
        except Exception as e:
            out["_governance_http"] = (out.get("_governance_http", "") + f"; relay: {e.__class__.__name__}").strip("; ")
    if not text:
        return out
    for label, key in (("Audit", "auditRisk"), ("Board", "boardRisk"), ("Shareholder Rights", "shareHolderRightsRisk"),
                       ("Compensation", "compensationRisk")):
        m = re.search(label + r"\s*:\s*(\d+)", text)
        if m:
            out[key] = int(m.group(1))
    m = re.search(r"QualityScore[^.]{0,80}?\bis\s+(\d+)", text)
    if m:
        out["overallRisk"] = int(m.group(1))
    return out
