"""
Fetches a company's logo from StockAnalysis and converts it to PNG using Inkscape.

"""

### Importing libraries
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import subprocess
import urllib3

from stockanalysis_resolver import get_stockanalysis_base_url

# disable warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_logo_png(
    ticker: str,
    exchange: str = None,
    out_dir: str = "logos",
    dpi: int = 300,
    verbose: bool = True,
):

    # 🔥 Adjust this path if Inkscape is installed elsewhere!! 🔥
    inkscape_path = r"C:\Program Files\Inkscape\bin\inkscape.exe"
    # 🔥 Adjust this path if Inkscape is installed elsewhere!! 🔥

    ticker_upper = ticker.upper()
    page_url = get_stockanalysis_base_url(ticker, exchange=exchange) + "/company/"

    #if verbose:
       # print(f"[logo] Fetching HTML from: {page_url}")

    try:
        resp = requests.get(page_url, timeout=10, verify=False)
    except Exception as e:
        print(f"[logo] Error fetching page: {e}")
        return None

    if resp.status_code != 200:
        print(f"[logo] Failed to fetch page: HTTP {resp.status_code}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # US "/stocks/.../company/" pages serve the logo as an SVG from
    # logos.stockanalysis.com; international "/quote/{exchange}/.../company/"
    # pages serve it as a PNG from img.stockanalysis.com instead.
    logo_tag = soup.find(
        "img",
        src=lambda s: s and ("logos.stockanalysis.com" in s or "img.stockanalysis.com/logos" in s),
    )
    if not logo_tag:
        print("[logo] Could not find logo img in HTML.")
        return None

    logo_url = logo_tag["src"]
    #if verbose:
        #print(f"[logo] Found logo URL: {logo_url}")

    # download logo
    try:
        logo_resp = requests.get(logo_url, timeout=10, verify=False)
    except Exception as e:
        print(f"[logo] Error downloading logo: {e}")
        return None

    if logo_resp.status_code != 200:
        print(f"[logo] Failed to download logo: HTTP {logo_resp.status_code}")
        return None

    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    png_path = out_dir_path / f"{ticker_upper}.png"

    # already a raster image (e.g. PNG from img.stockanalysis.com) - save directly
    if not logo_url.lower().endswith(".svg"):
        with open(png_path, "wb") as f:
            f.write(logo_resp.content)
        return png_path

    svg_path = out_dir_path / f"{ticker_upper}.svg"

    # Save SVG to disk
    with open(svg_path, "wb") as f:
        f.write(logo_resp.content)

    #if verbose:
       # print(f"[logo] Saved SVG to: {svg_path}")

    # Inkscape command to convert to PNG
    inkscape_cmd = [
        inkscape_path,
        str(svg_path),
        "--export-type=png",
        f"--export-filename={png_path}",
        f"--export-dpi={dpi}",
    ]

   # if verbose:
      #  print(f"[logo] Running Inkscape: {' '.join(inkscape_cmd)}")

    try:
        subprocess.run(inkscape_cmd, check=True)
    except FileNotFoundError:
        print(
            "[logo] Error: 'inkscape' not found. "
            "Update 'inkscape_path' in get_logo_png() to the correct location."
        )
        return None
    except subprocess.CalledProcessError as e:
        print(f"[logo] Inkscape failed: {e}")
        return None

   # if verbose:
       # print(f"[logo] Converted to PNG: {png_path}")

    return png_path


if __name__ == "__main__":
    # Quick manual test
    test_ticker = "AAPL"
    path = get_logo_png(test_ticker)
   # print("Result:", path)
