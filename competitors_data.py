"""
Functions to get competitors and its ratios for a given ticker.

"""

from typing import Dict, Any

## Import libraries

import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np

from datetime import datetime, timedelta

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

from stockanalysis_resolver import (
    get_stockanalysis_base_url,
    TickerNotFoundError,
    TickerAmbiguousError,
)


#  MarketBeat – check Competitors
def get_competitors_from_marketbeat(ticker: str, exchange: str = None, verbose: bool = True) -> pd.DataFrame:

    # Use the ticker we have to check competitors
    ticker = ticker.upper()

    # MarketBeat only covers US-exchange listings. If we already know this
    # ticker belongs to a non-US exchange (StockAnalysis exchange code, e.g.
    # "etr", "tyo"), skip MarketBeat entirely rather than risk matching an
    # unrelated US company that happens to share the same ticker letters
    # (e.g. "ENR" = Siemens Energy on etr, but also Energizer Holdings on NYSE).
    us_exchange_codes = {None, "nasdaq", "nyse", "arca", "amex", "otc"}
    if exchange is not None and exchange.lower() not in us_exchange_codes:
        if verbose:
            print(f"  Skipping MarketBeat for {ticker}: not a US exchange listing ({exchange}).")
        return pd.DataFrame({"ticker": [ticker]})

    # Exchanges to explore
    exchanges = ["NASDAQ", "NYSE", "ARCA", "AMEX", "OTC"]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def _extract_from_paragraph(soup: BeautifulSoup):
        # Extract peers from title like:
        # "NVDA vs. AAPL, AMD, AMZN, AVGO, and GOOG"

        h2 = soup.find("h2", class_="large-section-h mt-0")

        if not h2:
            return []

        text = h2.get_text(" ", strip=True)

        if " vs. " not in text:
            return []

        peers_part = text.split(" vs. ", 1)[1]
        peers_part = peers_part.replace(" and ", ", ")

        peers = [p.strip().upper() for p in peers_part.split(",") if p.strip()]

        return peers

    def _extract_from_table(soup: BeautifulSoup):
        table = soup.find("table", id="competitors-table")

        if not table:
            return []

        peers = []

        for row in table.find_all("tr"):
            cells = row.find_all("td")

            if not cells:
                continue

            cell = cells[0]

            clean_data = cell.get("data-clean", "")

            if "|" in clean_data:
                ticker = clean_data.split("|")[-1].strip().upper()
                peers.append(ticker)
                continue

            ticker_div = cell.find("div", class_="ticker-area")

            if ticker_div:
                ticker = ticker_div.get_text(strip=True).upper()
                peers.append(ticker)

        return peers

    # Try each exchange until we find one that works
    working_url = None
    all_peers = []

    for exch in exchanges:
        url = f"https://www.marketbeat.com/stocks/{exch}/{ticker}/competitors-and-alternatives/"
        #if verbose:
            #print(f"Trying URL: {url}")

        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            if verbose:
                print(f"  -> HTTP {resp.status_code}, skipping")
            continue

        # calling Bsoup to parse
        soup = BeautifulSoup(resp.text, "html.parser")

        # trying out the first function
        peers = _extract_from_paragraph(soup)
        if not peers:
            if verbose:
                print("  No peers in paragraph, trying table approach.")
            # from table
            peers = _extract_from_table(soup)

        if peers:
            working_url = url
            all_peers = peers
            #if verbose:
                #print(f"  Found {len(peers)} competitors on {exch}.")
            break
        else:
            if verbose:
                print("  No competitors found with this exchange.")

    if working_url is None:
        if verbose:
            print(f"Could not find a working MarketBeat page for {ticker}.")
        return pd.DataFrame({"ticker": [ticker]})

    # Ensure main ticker is included and is first in the list
    if ticker not in all_peers:
        all_peers = [ticker] + all_peers
    else:
        all_peers = [ticker] + [p for p in all_peers if p != ticker]

    df_peers = pd.DataFrame({"ticker": all_peers})

    #if verbose:
        #print(f"\nUsing MarketBeat URL: {working_url}")
        #print("Final peers list:", df_peers["ticker"].tolist())

    return df_peers



#  calculating CAGRs via yfinance
def get_price_cagr(ticker: str, years: int = 5):

    # checking yf is available for this ticker
    if not HAS_YF:
        return np.nan

    end = datetime.today()
    start = end - timedelta(days=365 * years)

    data = yf.download(
        ticker,
        start=start,
        end=end,
        progress=False,
        auto_adjust=False,
        group_by="column",
    )

    if data is None or data.empty:
        return np.nan

    # choose price series
    if "Adj Close" in data.columns:
        prices = data["Adj Close"]
    elif "Close" in data.columns:
        prices = data["Close"]
    else:
        return np.nan

    # if still DataFrame (multi-column), take first column
    if isinstance(prices, pd.DataFrame):
        prices = prices.iloc[:, 0]

    if len(prices) < 2:
        return np.nan

    start_price = float(prices.iloc[0])
    end_price = float(prices.iloc[-1])

    if start_price == 0:
        return np.nan

    cagr = (end_price / start_price) ** (1.0 / years) - 1.0
    return cagr



#  StockAnalysis – Ratios


# handling NAs and others
def _parse_float_sa(text: str):

    if text is None:
        return np.nan
    txt = text.strip()
    if txt == "" or txt.lower() in ("n/a", "na", "--", "-"):
        return np.nan
    # remove thousands separators and percent sign
    txt = txt.replace(",", "").replace("%", "")
    try:
        return float(txt)
    except ValueError:
        return np.nan

#### scraping the ratios
def get_ratios_from_stockanalysis(ticker: str, exchange: str = None, verbose: bool = True) -> pd.DataFrame:

    ticker = ticker.upper()

    # a peer ticker (scraped from MarketBeat) may be malformed or not covered
    # by StockAnalysis at all; treat that the same as a 404 - skip it rather
    # than blowing up the whole report.
    try:
        url = get_stockanalysis_base_url(ticker, exchange=exchange) + "/financials/ratios/"
    except (TickerNotFoundError, TickerAmbiguousError) as e:
        if verbose:
            print(f"  -> Could not resolve '{ticker}' on StockAnalysis ({e}), returning empty dataframe.")
        return pd.DataFrame(columns=["ticker", "metric", "Current"])

    #if verbose:
        #print(f"Fetching ratios from: {url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        if verbose:
            print(f"  -> HTTP {resp.status_code}, returning empty dataframe.")
        return pd.DataFrame(columns=["ticker", "metric", "Current"])

    soup = BeautifulSoup(resp.text, "html.parser")

    tables = soup.find_all("table")
    target_table = None

    for tbl in tables:
        hdr = tbl.find("thead")
        if not hdr:
            continue
        header_cells = [th.get_text(strip=True) for th in hdr.find_all("th")]
        if any(h in header_cells for h in ("Current", "TTM")) and "Fiscal Year" in "".join(header_cells):
            target_table = tbl
            break

    if target_table is None:
        if verbose:
            print("  Could not find a valid ratios table, returning empty dataframe.")
        return pd.DataFrame(columns=["ticker", "metric", "Current"])

    # Now parse the header row that contains 'Fiscal Year' / 'Current' / 'TTM'
    header_row = None
    for tr in target_table.find_all("tr"):
        ths = tr.find_all("th")
        if not ths:
            continue
        texts = [th.get_text(strip=True) for th in ths]
        if any("Fiscal Year" in t for t in texts):
            header_row = tr
            break

    if header_row is None:
        if verbose:
            print("  Could not find 'Fiscal Year' header row. Returning empty df.")
        return pd.DataFrame(columns=["ticker", "metric", "Current"])

    cols = []
    for th in header_row.find_all("th"):
        text = th.get_text(strip=True)
        if text in ("Fiscal Year", "2016 - 2019"):
            continue
        cols.append(text)

    if "Current" in cols:
        current_idx = cols.index("Current")
    elif "TTM" in cols:
        current_idx = cols.index("TTM")
    else:
        current_idx = 0
        if verbose:
            print("  Warning: 'Current'/'TTM' not found. Using first data column as Current.")

    metrics = []
    values = []

    for tr in target_table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue

        label_cell = tds[0]
        a = label_cell.find("a")
        if a and a.get_text(strip=True):
            metric_name = a.get_text(strip=True)
        else:
            metric_name = label_cell.get_text(" ", strip=True)

        metric_name = re.sub(r"\s+", " ", metric_name).strip()

        data_cells = [td.get_text(strip=True) for td in tds[1:]]
        if not data_cells:
            continue

        while len(data_cells) < len(cols):
            data_cells.append("")

        current_text = data_cells[current_idx]
        current_value = _parse_float_sa(current_text)

        metrics.append(metric_name)
        values.append(current_value)

    df_rat = pd.DataFrame(
        {
            "ticker": ticker.upper(),
            "metric": metrics,
            "Current": values,
        }
    )

    return df_rat


def get_ratios_for_peers_from_stockanalysis(
    df_peers: pd.DataFrame,
    main_ticker: str = None,
    main_exchange: str = None,
    main_yf_ticker: str = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    For each ticker in df_peers['ticker'], scrapes the ratios from StockAnalysis
    (using get_ratios_from_stockanalysis) and pivots them into a single dataframe
    with columns = metrics and rows = tickers. Adds 5Y CAGR and 10Y CAGR
    based on price history via yfinance (in percentage values, e.g. 12.5 = 12.5%).

    `main_exchange` (a StockAnalysis exchange code, e.g. "etr", "tyo") is only
    applied to `main_ticker`'s own row — peers come from MarketBeat, which is
    always a US-exchange listing, so they resolve fine without an exchange hint.

    `main_yf_ticker` is the Yahoo Finance ticker (e.g. "ENR.DE") for the main
    company's CAGR calculation — yfinance uses its own exchange-suffix
    convention, unrelated to StockAnalysis exchange codes, so a bare non-US
    ticker like "ENR" can silently resolve to an unrelated US company there.
    """

    peer_tickers = df_peers["ticker"].tolist()
    all_rows = []

    for tk in peer_tickers:
        #if verbose:
            #print(f"\nFetching ratios for peer: {tk}")
        is_main = bool(main_ticker) and tk.upper() == main_ticker.upper()
        tk_exchange = main_exchange if is_main else None
        df_rat = get_ratios_from_stockanalysis(tk, exchange=tk_exchange, verbose=verbose)

        if df_rat.empty:
            if verbose:
                print(f"  No ratios for {tk}, skipping ratios (still computing CAGR).")
            metric_map = {}
        else:
            metric_map = dict(zip(df_rat["metric"], df_rat["Current"]))
        
        wanted_metrics = {
            "PE Ratio": "PE",
            "PS Ratio": "PS",
            "PB Ratio": "PB",
            "P/FCF Ratio": "PFCF",
            "PEG Ratio": "PEG",                    
            "Return on Assets (ROA)": "ROA",
            "Return on Equity (ROE)": "ROE",
            "Return on Capital (ROIC)": "ROIC",
            "Debt / Equity Ratio": "D/E",
        }

        row_data = {"ticker": tk}

        for metric_name, short_name in wanted_metrics.items():
            val = metric_map.get(metric_name, np.nan)
            row_data[short_name] = val

        # ---------- 5Y / 10Y Price CAGR ----------
        yf_tk = main_yf_ticker if (is_main and main_yf_ticker) else tk
        c5 = get_price_cagr(yf_tk, 5)
        c10 = get_price_cagr(yf_tk, 10)

        # store in percentage (12.5 = 12.5%)
        row_data["5Y CAGR"] = c5 * 100 if c5 is not None and not np.isnan(c5) else np.nan
        row_data["10Y CAGR"] = c10 * 100 if c10 is not None and not np.isnan(c10) else np.nan

        all_rows.append(row_data)

    if not all_rows:
        return pd.DataFrame(
            columns=["ticker", "PE", "PFCF", "PB", "PS", "PEG", "ROA", "ROE", "ROIC", "D/E", "5Y CAGR", "10Y CAGR"]
        )

    df_out = pd.DataFrame(all_rows)

    # reorder the columns
    cols = ["ticker", "PE", "PFCF", "PB", "PS", "PEG", "ROA", "ROE", "ROIC", "D/E", "5Y CAGR", "10Y CAGR"]
    for c in cols:
        if c not in df_out.columns:
            df_out[c] = np.nan

    return df_out[cols]


#  wrapper functions

def _build_df_ratios_for_ticker(mainticker: str, exchange: str = None, yf_ticker: str = None) -> pd.DataFrame:
    """
    Builds df_ratios for a given ticker, using the helper functions above.
    This mirrors the end-to-end example in the original notebook.
    """
    mainticker = mainticker.upper()
    # 1) get competitors from MarketBeat (skipped automatically for non-US exchanges)
    df_peers = get_competitors_from_marketbeat(mainticker, exchange=exchange)
    # 2) get ratios for those tickers from StockAnalysis and calculates CAGRs from yfinance
    df_ratios = get_ratios_for_peers_from_stockanalysis(
        df_peers, main_ticker=mainticker, main_exchange=exchange, main_yf_ticker=yf_ticker
    )
    return df_ratios


def get_competitors_package(mainticker: str, exchange: str = None, yf_ticker: str = None) -> Dict[str, Any]:
    """
    External API: given a ticker, returns a dict with:
        - "ticker": mainticker
        - "df_ratios": dataframe with ratios for the ticker and its competitors
                       (including 5Y CAGR and 10Y CAGR in percentage values)

    `exchange` is a StockAnalysis exchange code (e.g. "etr", "tyo") for tickers
    not listed on a US exchange; leave it None for plain US tickers.
    `yf_ticker` is the Yahoo Finance ticker (e.g. "ENR.DE") used for the main
    company's CAGR calculation, if it differs from `mainticker`.
    """
    df_ratios = _build_df_ratios_for_ticker(mainticker, exchange=exchange, yf_ticker=yf_ticker)
    return {
        "ticker": mainticker,
        "df_ratios": df_ratios,
    }


if __name__ == "__main__":
    test_ticker = "AAPL"
    #print(f"Testing competitors_data for {test_ticker}...")
    pkg = get_competitors_package(test_ticker)
    #print(pkg["df_ratios"].head())
