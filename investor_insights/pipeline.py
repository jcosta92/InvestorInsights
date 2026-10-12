"""Gathers everything the report needs for one ticker.

Scrapers are untouched: yfinance_data, stock_analysis_data, competitors_data and
logo_stockanalysis do the fetching; this module only assembles their output.
"""
from __future__ import annotations

import re
from typing import Any, Dict

import pandas as pd

from competitors_data import get_competitors_package
from logo_stockanalysis import get_logo_png
from stock_analysis_data import get_stockanalysis_package
from yfinance_data import build_info_df, get_yf_package

from .fallback import stockanalysis_overview, yahoo_is_empty


def prepare_ticker_data(ticker: str, charts_dir: str = "charts", logos_dir: str = "logos") -> Dict[str, Any]:
    """Returns prices, info, financials, charts, recs, df_ratios and logo_png for a ticker."""
    ##### loading the py files
    warnings = []
    try:
        data = get_yf_package(ticker, charts_dir=charts_dir)
    except Exception as e:  # Yahoo refuses many cloud hosts; keep going with what StockAnalysis has
        warnings.append(f"Yahoo Finance failed ({e.__class__.__name__}); price history and analyst history are missing.")
        data = {"history": pd.DataFrame(), "info": {}, "info_df": build_info_df({}), "recs_summary": None, "charts": {}}
    yahoo_error = None
    if yahoo_is_empty(data["info"]):
        # second try: a browser-like session, which gets past Yahoo's blocking of cloud hosts more often
        try:
            from curl_cffi import requests as cffi_requests
            import yfinance as yf
            tk = yf.Ticker(ticker, session=cffi_requests.Session(impersonate="chrome"))
            info2 = tk.info or {}
            if not yahoo_is_empty(info2):
                data["info"], data["info_df"] = info2, build_info_df(info2)
                if data["history"] is None or data["history"].empty:
                    data["history"] = tk.history(period="5y", interval="1d")
                warnings.append("Yahoo Finance answered only on a second attempt with a browser-like session.")
        except Exception as e:
            yahoo_error = f"{e.__class__.__name__}: {str(e)[:300]}"
    if yahoo_is_empty(data["info"]):
        fb = stockanalysis_overview(ticker)
        if fb:
            merged = {**data["info"], **{k: v for k, v in fb.items() if data["info"].get(k) is None}}
            data["info"], data["info_df"] = merged, build_info_df(merged)
            warnings.append("Yahoo Finance returned no company data from this host; name, price, market cap, ratios and "
                            "analyst view were taken from StockAnalysis instead. Governance risks and sentiment history are missing.")
        else:
            warnings.append("Yahoo Finance returned no company data and the StockAnalysis fallback found nothing: "
                            "the header, sentiment, volatility and risk ratings are empty.")
    sdata = get_stockanalysis_package(ticker)
    cdata = get_competitors_package(ticker)

    #### creating dfs

    # from yfinance
    prices = data["history"]
    info = data["info_df"]
    recs = data["recs_summary"]
    charts = data["charts"]

    # from stock analysis
    financials = sdata["combined_df"]
    financials = financials.loc[:, ~financials.columns.str.match(r"^\d{4}\s*-\s*\d{4}$")]

    # convert FY columns → years (FY25 → 2025, FY24 → 2024, ...)
    def fy_to_year(col):
        match = re.match(r"FY(\d+)", col)
        if match:
            fy = int(match.group(1))
            # rule: FY25 corresponds to the fiscal year ending in December 2024
            return str(2000 + fy)
        return col

    financials.columns = [fy_to_year(c) for c in financials.columns]

    ### Reorder columns
    cols = list(financials.columns)

    # first Current
    ordered = ["Current"]

    # rest of columns that are years → sort desc
    year_cols = [c for c in cols if c != "Current" and c.isdigit()]
    year_cols = sorted(year_cols, reverse=True)

    # gathering all together
    ordered += year_cols

    # apply in financials
    financials = financials[ordered]

    # from competitors ratios
    df_ratios = cdata["df_ratios"]

    # getting logo
    logo_png = get_logo_png(ticker, out_dir=logos_dir)

    return {
    "prices": prices,
    "info": info,
    "financials": financials,
    "charts": charts,
    "recs": recs,
    "df_ratios": df_ratios,
    "logo_png": logo_png,
    "warnings": warnings,
    "yahoo_error": yahoo_error,
    }