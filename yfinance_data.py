## Libraries

from pathlib import Path
from typing import Dict, Any, Tuple, Optional

import yfinance as yf
import matplotlib
matplotlib.use("Agg")  # backend wo graphical interface
import matplotlib.pyplot as plt
import pandas as pd


# specific fields we need
WANTED_INFO_FIELDS = [
    "auditRisk", "boardRisk", "compensationRisk", "shareHolderRightsRisk", "overallRisk",
    "profitMargins", "floatShares", "trailingEps", "forwardEps", "beta", "longName",
    "country", "industry", "sector", "longBusinessSummary", "fullTimeEmployees",
    "dividendYield", "forwardPE", "trailingPE", "marketCap",
    "fiftyTwoWeekLow", "fiftyTwoWeekHigh", "currency", "currentPrice",
    "recommendationKey", "numberOfAnalystOpinions", "ebitda",
    "earningsTimestamp", "earningsTimestampStart", "earningsCallTimestampEnd"
]

### for getting a df as we want
def build_info_df(info: Dict[str, Any]) -> pd.DataFrame:
    df_info = pd.DataFrame(
        [(k, info.get(k, None)) for k in WANTED_INFO_FIELDS],
        columns=["Field", "Value"]
    )
    return df_info

## downloading data from yfinance
def get_yf_data(
    mainticker: str,
    period: str = "5y",
    interval: str = "1d",
) -> Tuple[pd.DataFrame, Dict[str, Any], Optional[pd.DataFrame]]:

    tk = yf.Ticker(mainticker)

    # price history
    df_history = tk.history(period=period, interval=interval)

    # company's info
    info = tk.info  

    # getting analysts recommendations 
    recs_summary = None
    try:
        if hasattr(tk, "get_recommendations_summary"):
            recs_summary = tk.get_recommendations_summary()
        elif hasattr(tk, "recommendations_summary"):
            recs_summary = tk.recommendations_summary
    except Exception as e:
        print(f"[WARN] Not possible to obtain recommendations_summary for {mainticker}: {e}")

    return df_history, info, recs_summary

### getting a stock price history chart
def save_yf_charts(
    df_history: pd.DataFrame,
    mainticker: str,
    out_dir: str = "charts",
) -> Dict[str, Path]:

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    chart_paths: Dict[str, Path] = {}

    # stock price history chart
    if "Close" in df_history.columns:
        price_png = out_path / f"{mainticker}_price.png"

        fig_price, ax_price = plt.subplots()
        ax_price.plot(df_history.index, df_history["Close"])
        ax_price.set_title(f"{mainticker} - Closing Price")
        ax_price.set_xlabel("Date")
        ax_price.set_ylabel("Price")

        fig_price.tight_layout()
        fig_price.savefig(price_png, bbox_inches="tight")
        plt.close(fig_price)

        chart_paths["price"] = price_png
    else:
        print(f"[WARN] df_history doesn't have column 'Close' for {mainticker}, no price chart generated.")

    # volume chart -> not going to use in this project
    if "Volume" in df_history.columns:
        volume_png = out_path / f"{mainticker}_volume.png"

        fig_vol, ax_vol = plt.subplots()
        ax_vol.bar(df_history.index, df_history["Volume"])
        ax_vol.set_title(f"{mainticker} - Volume")
        ax_vol.set_xlabel("Date")
        ax_vol.set_ylabel("Volume")

        fig_vol.tight_layout()
        fig_vol.savefig(volume_png, bbox_inches="tight")
        plt.close(fig_vol)

        chart_paths["volume"] = volume_png
    else:
        print(f"[WARN] df_history doesn't have column 'Volume' for {mainticker}, no volume chart generated.")

    return chart_paths

### All gathered
def get_yf_package(
    mainticker: str,
    period: str = "5y",
    interval: str = "1d",
    charts_dir: str = "charts",
) -> Dict[str, Any]:

    df_history, info, recs_summary = get_yf_data(
        mainticker=mainticker,
        period=period,
        interval=interval,
    )

    chart_paths = save_yf_charts(
        df_history=df_history,
        mainticker=mainticker,
        out_dir=charts_dir,
    )

    # filtered df
    df_info = build_info_df(info)

    result: Dict[str, Any] = {
        "ticker": mainticker,
        "history": df_history,
        "info": info,          
        "info_df": df_info,    
        "recs_summary": recs_summary,
        "charts": chart_paths,
    }
    return result


if __name__ == "__main__":
    
    test_ticker = "AAPL"
 #   print(f"Quick test with {test_ticker}...")
    pkg = get_yf_package(test_ticker, period="1y", interval="1d", charts_dir="charts_test")
 #   print("History:", pkg["history"].tail(3))
 #   print("Info_df:")
 #   print(pkg["info_df"].to_string())
 #   print("Recs summary:", pkg["recs_summary"])
 #   print("Charts:", pkg["charts"])
