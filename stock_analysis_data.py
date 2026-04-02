## Importing libraries

from typing import Dict, Any
from pathlib import Path
import re
import datetime as dt

import requests
from bs4 import BeautifulSoup
import pandas as pd


# scrape StockAnalysis pages and build combined df with all the financials

def _load_full_stockanalysis_dataset(mainticker: str) -> pd.DataFrame:

    ticker = mainticker.upper()

    # different pages
    base = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials"
    pages = [
        base + "/",                       # Overview 
        base + "/balance-sheet/",         # Balance Sheet
        base + "/cash-flow-statement/",   # Cash Flow
        base + "/ratios/",                # Ratios
    ]

    # headers for working around anti-scraping
    headers_req = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    headers_full = None
    dfs = []

    for url in pages:
        html = requests.get(url, headers=headers_req, timeout=30).text
        soup = BeautifulSoup(html, "html.parser")

        # finding header row
        head_tr = None
        for tr in soup.find_all("tr"):
            ths = tr.find_all("th")
            if not ths:
                continue
            texts = [th.get_text(strip=True) for th in ths]
            if any("Fiscal Year" in t for t in texts):
                head_tr = tr
                break

        if head_tr is None:
            raise RuntimeError(f"Could not find the header row on: {url}")

        # building labels
        cols = []
        for th in head_tr.find_all("th"):
            text = th.get_text(strip=True)
            if text in ("Fiscal Year", "2016 - 2019"):
                continue

            # "FY 2024" -> "FY24"
            m = re.match(r"FY\s*(\d{4})", text)
            if m:
                year = m.group(1)
                cols.append(f"FY{year[-2:]}")
            else:
                # keep "Current", "TTM"
                cols.append(text)

        if not cols:
            raise RuntimeError(f"No columns parsed from header on: {url}")

        headers_full = cols  # last list of headers found will be used for all pages

        # parsing rows
        page_rows = []
        idx_names = []

        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue

            # metric name
            metric_name = None
            a = tds[0].find("a")
            if a and a.get_text(strip=True):
                metric_name = a.get_text(strip=True)
            else:
                label = tds[0].get_text(" ", strip=True)
                metric_name = re.sub(r"\s+", " ", label).strip()

            # rest of values, ignoring "Upgrade" function of website
            vals = []
            for td in tds[1:]:
                txt = td.get_text(strip=True)
                if not txt or txt.lower().startswith("upgrade"):
                    continue
                vals.append(txt)

            if not vals:
                continue

            # clear out nr of rows
            while len(vals) < len(headers_full):
                vals.append(None)
            vals = vals[:len(headers_full)]

            idx_names.append(metric_name)
            page_rows.append(vals)

        if not page_rows:
            # nothing useful in the page
            continue

        page_df = pd.DataFrame(page_rows, columns=headers_full, index=idx_names)

        # unify "Current" and "TTM"
        cols_set = page_df.columns.tolist()
        has_current = "Current" in cols_set
        has_ttm = "TTM" in cols_set

        if has_current and has_ttm:
            combined_col = page_df["Current"].where(
                page_df["Current"].notna(), page_df["TTM"]
            )
            page_df = page_df.drop(columns=["TTM"])
            page_df.insert(0, "Current", combined_col)

        elif (not has_current) and has_ttm:
            page_df = page_df.rename(columns={"TTM": "Current"})
            new_cols = ["Current"] + [c for c in page_df.columns if c != "Current"]
            page_df = page_df[new_cols]

        else:
            if has_current:
                new_cols = ["Current"] + [c for c in page_df.columns if c != "Current"]
                page_df = page_df[new_cols]
        
        # changing "," with "" in strings
        def _replace_comma(x):
            if isinstance(x, str):
                return x.replace(",", "")
            return x
        
        # changing "." with "," in strings
        def _replace_dot(x):
            if isinstance(x, str):
                return x.replace(".", ",")
            return x
        
        page_df = page_df.map(_replace_comma)
        page_df = page_df.map(_replace_dot)

        dfs.append(page_df)

    if not dfs:
        # nothing found in this ticker
        return pd.DataFrame()

    # gather all the pages
    combined = pd.concat(dfs, axis=0, sort=False)

    # removing duplicates
    combined = combined[~combined.index.duplicated(keep="first")]

    # reorder columns
    preferred_order = ["Current", "FY24", "FY23", "FY22", "FY21", "FY20"]
    ordered = [c for c in preferred_order if c in combined.columns]
    rest = [c for c in combined.columns if c not in ordered]
    combined = combined[ordered + rest]

    return combined


## main function to be called
def get_stockanalysis_package(mainticker: str) -> Dict[str, Any]:

    combined = _load_full_stockanalysis_dataset(mainticker)

    return {
        "ticker": mainticker,
        "combined_df": combined,
    }


if __name__ == "__main__":
    # Quick manual test
    test_ticker = "AAPL"
   # print(f"Testing StockAnalysis scrape for {test_ticker}...")
    sdata = get_stockanalysis_package(test_ticker)
  #  print(sdata["combined_df"].head())
