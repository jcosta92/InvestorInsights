"""Fills report_template.xlsx for one ticker and exports it.

create_basic_report() is the notebook function, unchanged except for the export step:
- on Windows with Excel installed it still uses Excel (win32com) for the PDF;
- anywhere else it uses LibreOffice headless (soffice), which also recalculates every
  formula so the ratings can be read back with read_scores().
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.drawing.image import Image as XLImage
from pandas.tseries.offsets import DateOffset
from PIL import Image as PILImage

try:
    import win32com.client as win32
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

TEMPLATE = Path(__file__).resolve().parents[1] / "report_template.xlsx"


def soffice_path() -> Optional[str]:
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if os.path.exists(p):
            return p
    return None


def recalculate_and_export(xlsx_path: str, want_pdf: bool = True) -> Dict[str, Optional[str]]:
    """Open the filled workbook in LibreOffice headless, which recalculates all formulas,
    save it back with cached values, and optionally export a PDF next to it."""
    soffice = soffice_path()
    if soffice is None:
        return {"xlsx": xlsx_path, "pdf": None, "recalculated": False}
    xlsx_path = os.path.abspath(xlsx_path)
    out_dir = os.path.dirname(xlsx_path)
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, HOME=tmp)  # a private profile, so parallel runs do not clash
        subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx", "--outdir", tmp, xlsx_path],
                       check=True, capture_output=True, timeout=180, env=env)
        shutil.move(os.path.join(tmp, os.path.basename(xlsx_path)), xlsx_path)
        pdf, error = None, None
        if want_pdf:
            target = os.path.splitext(xlsx_path)[0] + ".pdf"
            r = subprocess.run([soffice, "--headless", "--calc", "--convert-to", "pdf:calc_pdf_Export", "--outdir", out_dir, xlsx_path],
                               capture_output=True, text=True, timeout=180, env=env)
            if os.path.isfile(target) and os.path.getsize(target) > 0:
                pdf = target
            else:
                error = (r.stderr or r.stdout or f"exit code {r.returncode}").strip()[-500:]
                print(f"[report] PDF export failed: {error}")
    return {"xlsx": xlsx_path, "pdf": pdf, "recalculated": True, "pdf_error": error}


def read_scores(xlsx_path: str) -> Dict[str, Any]:
    """The Score section of the template (rows 246-295), read from cached values.
    Needs a workbook that has been recalculated (Excel or recalculate_and_export)."""
    wb = load_workbook(xlsx_path, data_only=True)
    ws = wb["Sheet1"]
    overall = ws["K253"].value
    rows, category = [], None
    for r in range(247, 296):
        name, rating, weight = ws.cell(row=r, column=2).value, ws.cell(row=r, column=3).value, ws.cell(row=r, column=4).value
        if name is None:
            continue
        if weight == "Weight":            # category header row
            category = str(name).strip()
            continue
        rows.append({"category": category, "metric": str(name).strip(),
                     "rating": None if rating == "" else rating, "weight": None if weight == "" else weight})
    df = pd.DataFrame(rows)
    by_cat = None
    if not df.empty:
        d = df.dropna(subset=["rating", "weight"]).astype({"rating": float, "weight": float})
        by_cat = (d.assign(w=d.rating * d.weight).groupby("category", sort=False).agg(score=("w", "sum"), weight=("weight", "sum")))
        by_cat["score"] = by_cat.score / (5 * by_cat.weight)
    # the template's overall is 0 when the sentiment rating is empty (its formula starts from it);
    # overall_available is the same weighted average over the metrics that do have a rating
    overall_available = None
    if not df.empty:
        d = df.dropna(subset=["rating", "weight"]).astype({"rating": float, "weight": float})
        if d.weight.sum() > 0:
            overall_available = float((d.rating * d.weight).sum() / (5 * d.weight.sum()))
    return {"overall": None if overall in (None, "") else float(overall), "overall_available": overall_available, "metrics": df,
            "by_category": by_cat, "sentiment": ws["L13"].value, "volatility": ws["M15"].value}



def create_basic_report(
    info: pd.DataFrame,
    financials: pd.DataFrame,               
    prices: pd.DataFrame,
    ticker: str,
    logo_png: str,
    template_path: str = str(TEMPLATE),
    output_folder: str = ".",
    export_pdf: bool = True,
    price_chart_path=None,
    recs: pd.DataFrame | None = None,
    df_ratios: pd.DataFrame | None = None,
    recalc: bool = True,
):

    # cleaning ticker name
    safe_ticker = "".join(
        ch if ch.isalnum() or ch in ("-", "_", ".") else "_"
        for ch in ticker
    )

    # ---------- 0) Most recent year in df financials ----------
    year_cols = [c for c in financials.columns if str(c).isdigit()]
    most_recent_year = max(int(y) for y in year_cols) if year_cols else ""
    
    # Map: "Current", "2024", "2023", ... -> real column name in df
    col_name_map = {}
    for c in financials.columns:
        s = str(c).strip()
        if s.lower() == "current":
            col_name_map["Current"] = c
        elif s.isdigit():
            col_name_map[s] = c


    # ---------- 1) info -> dict ----------
    info_dict = dict(zip(info["Field"], info["Value"]))

    company_name          = info_dict["longName"]
    company_country       = info_dict["country"]
    company_sector        = info_dict["sector"]
    company_industry      = info_dict["industry"]
    company_employees     = info_dict["fullTimeEmployees"]
    company_marketcap     = info_dict["marketCap"]
    company_stockprice    = info_dict["currentPrice"]
    company_currency      = info_dict["currency"]
    company_52wklow       = info_dict["fiftyTwoWeekLow"]
    company_52wkhigh      = info_dict["fiftyTwoWeekHigh"]
    company_dividendyield = info_dict.get("dividendYield", None)
    company_audit_risk    = info_dict["auditRisk"]
    company_board_risk    = info_dict["boardRisk"]
    company_compensation_risk     = info_dict["compensationRisk"]
    company_shareholderrights_risk = info_dict["shareHolderRightsRisk"]
    company_overall_risk  = info_dict["overallRisk"]
    company_recommendation = info_dict["recommendationKey"]
    company_beta          = info_dict["beta"]
    company_forwardEPS    = info_dict["forwardEps"]
    company_forwardPE     = info_dict["forwardPE"]
    company_nranalysts    = info_dict["numberOfAnalystOpinions"]
    company_description   = info_dict["longBusinessSummary"]
    earnings_ts           = info_dict.get("earningsTimestamp", None)
    earnings_start_ts     = info_dict.get("earningsTimestampStart", None)
    earnings_call_ts      = info_dict.get("earningsCallTimestampEnd", None)
    company_profitmargins = info_dict["profitMargins"]
    company_ebitda        = info_dict["ebitda"]

    # ---------- 2) Open template ----------
    wb = load_workbook(template_path)
    ws = wb["Sheet1"]  

    # ---------- 3) helpers ----------
    
    # dealing with nans
    def is_nan(x):
        return isinstance(x, float) and math.isnan(x)

    # dates
    def set_date_cell(sheet, cell_ref, ts_value):
        if ts_value is None or is_nan(ts_value):
            return
        dt = datetime.fromtimestamp(int(ts_value))
        c = sheet[cell_ref]
        c.value = dt
        c.number_format = "dd/mm/yy"

    # formatting values to millions with currency
    def set_millions(sheet, cell_ref, value, currency=None):
        
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return

        c = sheet[cell_ref]
        c.value = float(value) / 1_000_000.0

        if currency == "USD":
            fmt = '#,##0.0 "M $"'
        elif currency == "EUR":
            fmt = '#,##0.0 "M €"'
        elif currency is not None:
            fmt = f'#,##0.0 "M {currency}"'
        else:
            fmt = '#,##0.0 "M"'
        c.number_format = fmt

    # cleaning out , and . to excel
    def to_float_eu(x):
        
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str):
            clean = x.replace(".", "").replace(",", ".").replace("%", "").strip()
            if clean == "":
                return None
            try:
                return float(clean)
            except ValueError:
                return None
        return None

    RATIO_METRICS = {
        "PE Ratio",
        "Forward PE",
        "PS Ratio",
        "PB Ratio",
        "P/TBV Ratio",
        "P/FCF Ratio",
        "P/OCF Ratio",
        "PEG Ratio",
        "EV/Sales Ratio",
        "EV/EBITDA Ratio",
        "EV/EBIT Ratio",
        "EV/FCF Ratio",
        "Debt / Equity Ratio",
        "Debt / EBITDA Ratio",
        "Debt / FCF Ratio",
        "Asset Turnover",
        "Inventory Turnover",
        "Quick Ratio",
        "Current Ratio",
    }

    ## function for stock price % change
    def pct_change_from_offset(prices_df, weeks=0, months=0, years=0):
        prices_df = prices_df.sort_index()
        prices_df.index = pd.to_datetime(prices_df.index)

        today = prices_df.index[-1]
        target_date = today - DateOffset(
            weeks=weeks,
            months=months,
            years=years,
        )

        past_row = prices_df.loc[:target_date].iloc[-1]

        close_today = float(prices_df.iloc[-1]["Close"])
        close_past = float(past_row["Close"])

        return (close_today - close_past) / close_past


    # ---------- 4) header  ----------
    ###  🔥 Made to cells in template that should not change 🔥
    ### 🔥 Adjust the cells if you change the template structure 🔥
    ### 

    ws["D39"] = most_recent_year
    ws["E4"] = company_name
    ws["E5"] = company_country
    ws["E6"] = company_sector
    ws["E7"] = company_industry
    ws["E8"] = ticker
    ws["E9"] = company_employees

    set_millions(ws, "E10", company_marketcap, company_currency)

    ws["E11"] = company_stockprice
    ws["F11"] = company_currency
    ws["E12"] = company_52wklow
    ws["F12"] = company_52wkhigh
    ws["L28"] = company_audit_risk
    ws["L29"] = company_board_risk
    ws["L30"] = company_compensation_risk
    ws["L31"] = company_shareholderrights_risk
    ws["L33"] = company_overall_risk
    ws["L13"] = company_recommendation
    ws["K15"] = company_beta
    ws["C136"] = company_forwardEPS
    ws["C142"] = company_forwardPE
    ws["O5"]   = company_nranalysts
    ws["B16"]  = company_description

    ##### Dividend yield format – 0.38 -> 0.38%

    if company_dividendyield is not None and not is_nan(company_dividendyield):
        ws["E13"] = float(company_dividendyield) / 100.0
        ws["E13"].number_format = "0.00%"
        ws["G22"] = "Growth & Dividend"
    else:
        ws["E13"] = None
        ws["G22"] = "Growth"

    ##### Company profit margins format – 0.25 -> 25%

    if company_profitmargins is not None and not is_nan(company_profitmargins):
        ws["L22"] = float(company_profitmargins)
        ws["L22"].number_format = "0.00%"
    else:
        ws["L22"] = None

    #####  EBITDA in millions

    if company_ebitda is not None and not is_nan(company_ebitda):
       set_millions(ws, "L23", company_ebitda, company_currency)

    ##### earnings dates

    set_date_cell(ws, "J18", earnings_ts)
    set_date_cell(ws, "J19", earnings_start_ts)
    set_date_cell(ws, "J20", earnings_call_ts)

    ### stock price performance
    if prices is not None and not prices.empty:
        try:
            ws["C35"] = pct_change_from_offset(prices, weeks=1)
            ws["D35"] = pct_change_from_offset(prices, months=1)
            ws["E35"] = pct_change_from_offset(prices, months=6)
            ws["F35"] = pct_change_from_offset(prices, years=1)
            ws["G35"] = pct_change_from_offset(prices, years=2)
            ws["H35"] = pct_change_from_offset(prices, years=4)

            for col in ("C", "D", "E", "F", "G", "H"):
                ws[f"{col}35"].number_format = "0.00%"
        except Exception:
            # If not enough history, leave blank
            for col in ("C", "D", "E", "F", "G", "H"):
                ws[f"{col}35"] = None


    # ---------- 5) Images ----------
    # Logo 
    tmp_files=[]
    if logo_png is not None and os.path.isfile(logo_png):
        pil_img = PILImage.open(logo_png)
        max_height = 200
        w, h = pil_img.size
        ratio = max_height / h if h > max_height else 1
        new_size = (int(w * ratio), int(h * ratio))
        pil_img = pil_img.resize(new_size, PILImage.LANCZOS)

        tmp_logo_path = os.path.join(output_folder, f"_tmp_logo_{ticker}.png")
        tmp_files.append(tmp_logo_path)

        pil_img.save(tmp_logo_path)

        img = XLImage(tmp_logo_path)

        ### 🔥 Adjust the cell if you change the template structure 🔥
        img.anchor = "B4"
        ws.add_image(img)

    # Price chart 
    if price_chart_path is not None:
        path_str = os.fspath(price_chart_path)
        if os.path.isfile(path_str):
            pil_img = PILImage.open(path_str)
            max_height = 350
            w, h = pil_img.size
            ratio = max_height / h if h > max_height else 1
            new_size = (int(w * ratio), int(h * ratio))
            pil_img = pil_img.resize(new_size, PILImage.LANCZOS)

            tmp_chart_path = os.path.join(output_folder, f"_tmp_price_{ticker}.png")
            tmp_files.append(tmp_chart_path)

            pil_img.save(tmp_chart_path)

            chart_img = XLImage(tmp_chart_path)
            
            ### 🔥 Adjust the cell if you change the template structure 🔥
            chart_img.anchor = "C24"
            ws.add_image(chart_img)

    # ---------- 6) Recommnedations of analysts (recs) in K8:O11 ----------
    ### 🔥 Adjust the cells if you change the template structure 🔥
    if recs is not None:
        col_map = {
            "strongBuy": "K",
            "buy": "L",
            "hold": "M",
            "sell": "N",
            "strongSell": "O",
        }

        for i in range(min(4, len(recs))):  
            excel_row = 8 + i
            row = recs.iloc[i]
            for col_name, col_letter in col_map.items():
                if col_name in row.index:
                    ws[f"{col_letter}{excel_row}"] = row[col_name]

    # ---------- 7) Fill in Financials (match coluna B -> DF index; copy values C:H) ----------
    ### 🔥 Adjust the cells if you change the template structure 🔥
    MILLION_METRICS = {
        "Cash & Equivalents",
        "Inventory",
        "Total Current Assets",
        "Total Current Liabilities",
        "Property, Plant & Equipment",
        "Revenue",
        "Net Income",
        "Total Assets",
        "Long-Term Debt",
        "Total Liabilities",
        "Shareholders' Equity",
        "Treasury Stock",
        "Retained Earnings",
        "Gross Profit",
        "Selling, General & Admin",
        "Operating Income",
        "Interest Expense",
        "Capital Expenditures",
        "Operating Cash Flow",
        "Free Cash Flow",
        "Issuance of Common Stock",
        "Repurchase of Common Stock",
        "Dividends Paid",
        "Common Dividends Paid"
    }

    financials.index = financials.index.astype(str).str.strip()

    INDEX_COL = 2       # column B
    FIRST_COL = 3       # column C
    LAST_COL  = 8       # column H
    num_target_cols = LAST_COL - FIRST_COL + 1  

    for row in range(39, 240):   ## range from beginning to end of financials section in template
        label_val = ws.cell(row=row, column=INDEX_COL).value
        if label_val is None:
            continue

        label = str(label_val).strip()

        if label not in financials.index:
            continue  

        df_row = financials.loc[label]

        for i in range(num_target_cols):
            
            val_raw = df_row.iloc[i] if i < len(df_row) else None
            val_num = to_float_eu(val_raw)

            cell = ws.cell(row=row, column=FIRST_COL + i)
            if isinstance(cell, MergedCell):   # section titles in the template
                continue

            if val_num is None or pd.isna(val_num):
                cell.value = None
                continue

            # million metrics
            if label in MILLION_METRICS:
                cell.value = float(val_num)
                if company_currency == "USD":
                    fmt = '#,##0.0 "M $"'
                elif company_currency == "EUR":
                    fmt = '#,##0.0 "M €"'
                elif company_currency:
                    fmt = f'#,##0.0 "M {company_currency}"'
                else:
                    fmt = '#,##0.0 "M"'
                cell.number_format = fmt

            else:
                # percentages: keep % as in df
                if isinstance(val_raw, str) and "%" in val_raw:
                    # val_num eg 6.43 -> "6,43%" 
                    cell.value = float(val_num) / 100.0
                    cell.number_format = "0.00%"
                else:
                    # numeric value as is
                    cell.value = float(val_num)

    # ---------- 8) Competitors ratios (df_ratios -> B188:N198) ----------
    if df_ratios is not None and not df_ratios.empty:
        ### 🔥 Adjust the cells if you change the template structure 🔥

        col_map = {
            2: "ticker",     # B
            3: "PE",         # C
            4: "PFCF",       # D
            5: "PB",         # E
            6: "PS",         # F
            7: "PEG",        # G
            10: "5Y CAGR",   # J
            11: "10Y CAGR",  # K
            12: "ROA",       # L
            13: "ROE",       # M
            14: "ROIC",      # N
        }

        start_row = 192   # first data row
        max_rows = 10     # last row

        num_rows = min(len(df_ratios), max_rows)

        ## mapping df in range
        for i in range(num_rows):
            excel_row = start_row + i
            row_data = df_ratios.iloc[i]

            for col_idx, df_col in col_map.items():
                if df_col not in df_ratios.columns:
                    continue

                val = row_data[df_col]
                cell = ws.cell(row=excel_row, column=col_idx)

                if pd.isna(val):
                    cell.value = None
                    continue

                # ticker is text
                if df_col == "ticker":
                    cell.value = str(val)
                    continue

                # metrics that should be percentages: df has 19.56 -> want 19.56%
                if df_col in ("5Y CAGR", "10Y CAGR", "ROA", "ROE", "ROIC"):
                    try:
                        num = float(val)
                    except (TypeError, ValueError):
                        num = to_float_eu(val) if isinstance(val, str) else None

                    if num is None or pd.isna(num):
                        cell.value = None
                    else:
                        cell.value = num / 100.0   
                        cell.number_format = "0.00%"
                else:
                    # numeric, non-percent 
                    try:
                        num = float(val)
                    except (TypeError, ValueError):
                        num = to_float_eu(val) if isinstance(val, str) else None

                    cell.value = None if num is None or pd.isna(num) else float(num)


    # ---------- 9) Saving Excel as temp and export PDF ----------

    # add in "reports" folder
    reports_folder = os.path.join(output_folder, "reports")
    os.makedirs(reports_folder, exist_ok=True)

    output_excel = os.path.join(reports_folder, f"report_{safe_ticker}.xlsx")
    output_pdf_path = os.path.join(reports_folder, f"report_{safe_ticker}.pdf")

    wb.save(output_excel)

    # export: Excel on Windows if available, otherwise LibreOffice (also recalculates)
    output_pdf = None
    if export_pdf and HAS_WIN32:
        excel_app = win32.DispatchEx("Excel.Application")
        excel_app.Visible = False
        abs_xlsx, abs_pdf = os.path.abspath(output_excel), os.path.abspath(output_pdf_path)
        if os.path.exists(abs_pdf):
            os.remove(abs_pdf)
        try:
            wb_excel = excel_app.Workbooks.Open(abs_xlsx)
            wb_excel.ExportAsFixedFormat(Type=0, Filename=abs_pdf)
            wb_excel.Close(SaveChanges=True)   # keeps the calculated values in the xlsx
            output_pdf = abs_pdf
        except Exception as e:
            print(f"[report] Excel export failed: {e}")
        finally:
            excel_app.Quit()
    elif export_pdf or recalc:
        res = recalculate_and_export(output_excel, want_pdf=export_pdf)
        output_pdf = res["pdf"]
        create_basic_report.last_pdf_error = res.get("pdf_error")

    # ---------- 10) Cleaning temp files ----------
    for f in tmp_files:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception as e:
            print(f"Could not delete temp file {f}: {e}")

    return output_excel, output_pdf

