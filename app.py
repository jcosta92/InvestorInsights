"""Investor Insights app: type a ticker, get the rated report.

Run:  streamlit run app.py
Everything is fetched live by the existing scrapers (StockAnalysis, MarketBeat, yfinance),
then written into report_template.xlsx, recalculated and shown here. The Excel and PDF
reports are offered for download at the end.
"""
from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st

from investor_insights import create_basic_report, prepare_ticker_data, read_scores
from investor_insights.report import soffice_path, HAS_WIN32

st.set_page_config(page_title="Investor Insights", page_icon="📈", layout="wide")
WORK = Path(tempfile.gettempdir()) / "investor_insights"
WORK.mkdir(exist_ok=True)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch(ticker: str) -> dict:
    d = prepare_ticker_data(ticker, charts_dir=str(WORK / "charts"), logos_dir=str(WORK / "logos"))
    d["info_dict"] = dict(zip(d["info"]["Field"], d["info"]["Value"]))
    return d


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def build_report(ticker: str, want_pdf: bool) -> dict:
    d = fetch(ticker)
    xlsx, pdf = create_basic_report(
        info=d["info"], financials=d["financials"], prices=d["prices"], ticker=ticker, logo_png=d["logo_png"],
        output_folder=str(WORK), export_pdf=want_pdf, price_chart_path=d["charts"].get("price"),
        recs=d["recs"], df_ratios=d["df_ratios"])
    scores = read_scores(xlsx)
    return {"xlsx": xlsx, "pdf": pdf, "scores": scores, "pdf_error": getattr(create_basic_report, "last_pdf_error", None)}


def money(v, cur):
    if v is None or pd.isna(v):
        return "—"
    v = float(v)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= div:
            return f"{v / div:,.1f} {unit} {cur or ''}".strip()
    return f"{v:,.0f} {cur or ''}".strip()


def stars(rating):
    if rating is None or pd.isna(rating):
        return "—"
    r = int(round(float(rating)))
    return "★" * r + "☆" * (5 - r)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("Investor Insights")
    st.caption("Simple financial reports for the beginner investor. Not investment advice.")
    ticker = st.text_input("Ticker", value="AAPL", help="US tickers as on StockAnalysis, e.g. AAPL, MSFT, DVA").strip().upper()
    want_pdf = st.checkbox("Also export PDF", value=True)
    run = st.button("Build report", type="primary", width="stretch")
    exporter = "Excel" if HAS_WIN32 else ("LibreOffice" if soffice_path() else None)
    if exporter is None:
        st.warning("Neither Excel nor LibreOffice found: the Excel file is produced, but ratings and the PDF need one of them.")
    else:
        st.caption(f"Formulas and PDF via {exporter}. A report takes about 30 s.")
    st.markdown("[Source on GitHub](https://github.com/jcosta92/InvestorInsights)")

if not run and "last" not in st.session_state:
    st.markdown("## Type a ticker and press **Build report**")
    st.markdown("The app scrapes the company's financial statements, ratios, competitors, analyst views and price history, "
                "fills the rating template and shows the result. Metrics are rated 0–5 and weighted into one overall score; "
                "the weights live in `report_template.xlsx` and can be changed there.")
    st.stop()

if run:
    st.session_state["last"] = ticker
ticker = st.session_state["last"]

try:
    with st.spinner(f"Fetching {ticker} from StockAnalysis, MarketBeat and yfinance…"):
        d = fetch(ticker)
    with st.spinner("Filling the template and rating…"):
        rep = build_report(ticker, want_pdf)
except Exception as e:  # scrapers break when sites change; show the trace so it can be fixed
    st.error(f"Could not build the report for {ticker}: {e}")
    with st.expander("Details"):
        st.code(traceback.format_exc())
    st.stop()

info, scores = d["info_dict"], rep["scores"]
cur = info.get("currency")
for w in d.get("warnings", []):
    st.warning(w)

# ---------------------------------------------------------------- header
c1, c2 = st.columns([1, 5])
with c1:
    if d["logo_png"] and os.path.isfile(d["logo_png"]):
        st.image(d["logo_png"], width="stretch")
with c2:
    st.markdown(f"## {info.get('longName') or ticker}  \n`{ticker}` · {info.get('sector') or ''} · {info.get('industry') or ''} · {info.get('country') or ''}")
    overall = scores["overall"] if scores["overall"] else scores.get("overall_available")
    if overall is not None:
        note = "" if scores["overall"] else " <small>(over the metrics with data)</small>"
        st.markdown(f"### Overall score: **{100 * overall:.0f} / 100**{note}", unsafe_allow_html=True)

k = st.columns(6)
k[0].metric("Price", f"{info.get('currentPrice')} {cur or ''}")
k[1].metric("Market cap", money(info.get("marketCap"), cur))
k[2].metric("Forward P/E", f"{info.get('forwardPE'):.1f}" if info.get("forwardPE") else "—")
k[3].metric("Dividend yield", f"{info.get('dividendYield'):.2f}%" if info.get("dividendYield") else "—")
k[4].metric("Analysts", f"{info.get('recommendationKey') or '—'} ({info.get('numberOfAnalystOpinions') or 0})")
k[5].metric("Volatility", scores.get("volatility") or "—", help=f"beta {info.get('beta')}")

tabs = st.tabs(["Score", "Price", "Financials", "Peers", "Company", "Download"])

with tabs[0]:
    bc = scores["by_category"]
    if bc is not None and not bc.empty:
        cols = st.columns(len(bc))
        for col, (cat, row) in zip(cols, bc.iterrows()):
            col.metric(cat, f"{100 * row.score:.0f}", help=f"weight {100 * row.weight:.0f}% of the overall score")
    m = scores["metrics"].copy()
    if not m.empty:
        m["rating"] = m.rating.map(stars)
        m["weight"] = m.weight.map(lambda w: f"{100 * float(w):.1f}%" if w not in (None, "") and not pd.isna(w) else "—")
        for cat, g in m.groupby("category", sort=False):
            st.markdown(f"**{cat}**")
            st.dataframe(g[["metric", "rating", "weight"]].set_index("metric"), width="stretch")
    st.caption("0–5 stars per metric from the rules in the template; the overall score is the weighted average, out of 100.")

with tabs[1]:
    prices = d["prices"]
    if prices is not None and not prices.empty:
        st.line_chart(prices["Close"], height=320)
        last = prices["Close"].iloc[-1]
        perf = {}
        for label, delta in (("1 month", pd.DateOffset(months=1)), ("6 months", pd.DateOffset(months=6)),
                             ("1 year", pd.DateOffset(years=1)), ("2 years", pd.DateOffset(years=2)), ("4 years", pd.DateOffset(years=4))):
            past = prices.loc[: prices.index[-1] - delta]
            if len(past):
                perf[label] = last / past["Close"].iloc[-1] - 1
        if perf:
            pc = st.columns(len(perf))
            for col, (label, v) in zip(pc, perf.items()):
                col.metric(label, f"{100 * v:+.1f}%")
    recs = d["recs"]
    if recs is not None and len(recs):
        st.markdown("**Analyst recommendations** (now, then 1, 2 and 3 months ago)")
        st.dataframe(recs.set_index(recs.columns[0]) if "period" in recs.columns else recs, width="stretch")

with tabs[2]:
    fin = d["financials"]
    key = [r for r in ("Revenue", "Gross Profit", "Operating Income", "Net Income", "Operating Cash Flow", "Free Cash Flow",
                       "Capital Expenditures", "Cash & Equivalents", "Total Assets", "Total Liabilities", "Shareholders' Equity",
                       "Long-Term Debt", "EPS (Diluted)", "PE Ratio", "PB Ratio", "PS Ratio", "P/FCF Ratio", "Debt / Equity Ratio",
                       "Return on Equity (ROE)", "Return on Assets (ROA)", "Return on Capital (ROIC)") if r in fin.index]
    st.markdown("**Key lines** (values as published on StockAnalysis, in millions unless a ratio or %)")
    st.dataframe(fin.loc[key], width="stretch")
    with st.expander(f"All {len(fin)} lines"):
        st.dataframe(fin, width="stretch")

with tabs[3]:
    r = d["df_ratios"]
    if r is not None and not r.empty:
        st.markdown("**Competitors** (MarketBeat peers, ratios from StockAnalysis, CAGR from price history)")
        st.dataframe(r.set_index("ticker") if "ticker" in r.columns else r, width="stretch")
    else:
        st.info("No competitor data found for this ticker.")

with tabs[4]:
    st.write(info.get("longBusinessSummary") or "")
    g = st.columns(5)
    for col, (label, field) in zip(g, (("Audit risk", "auditRisk"), ("Board risk", "boardRisk"), ("Compensation risk", "compensationRisk"),
                                      ("Shareholder rights risk", "shareHolderRightsRisk"), ("Overall risk", "overallRisk"))):
        col.metric(label, info.get(field) if info.get(field) is not None else "—", help="1 (low) to 10 (high), from Yahoo Finance")
    st.caption(f"Employees: {info.get('fullTimeEmployees') or '—'} · 52-week range: {info.get('fiftyTwoWeekLow')} – {info.get('fiftyTwoWeekHigh')} {cur or ''}")

with tabs[5]:
    with open(rep["xlsx"], "rb") as f:
        st.download_button("Download Excel report", f, file_name=os.path.basename(rep["xlsx"]),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if rep["pdf"] and os.path.isfile(rep["pdf"]):
        with open(rep["pdf"], "rb") as f:
            st.download_button("Download PDF report", f, file_name=os.path.basename(rep["pdf"]), mime="application/pdf")
    elif want_pdf:
        st.info("The PDF was not produced." + (f" LibreOffice said: {rep['pdf_error']}" if rep.get("pdf_error") else
                " PDF export needs Excel (Windows) or LibreOffice on this machine."))
    st.caption("Data is cached for 6 hours per ticker. Change the weights or rules in report_template.xlsx to change the rating.")
