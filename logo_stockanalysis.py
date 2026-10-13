"""
Fetches a company's logo from StockAnalysis and converts it to PNG using Inkscape.

"""

### Importing libraries
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import shutil
import subprocess
import urllib3

# disable warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_logo_png(
    ticker: str,
    out_dir: str = "logos",
    dpi: int = 300,
    verbose: bool = True,
):

    # 🔥 Adjust this path if Inkscape is installed elsewhere!! 🔥
    inkscape_path = r"C:\Program Files\Inkscape\bin\inkscape.exe"
    if not Path(inkscape_path).exists():          # Linux / macOS / cloud host: use the one on PATH
        inkscape_path = shutil.which("inkscape") or inkscape_path
    # 🔥 Adjust this path if Inkscape is installed elsewhere!! 🔥

    ticker_lower = ticker.lower()
    ticker_upper = ticker.upper()
    page_url = f"https://stockanalysis.com/stocks/{ticker_lower}/company/"

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

    # find <img> whose src contains "logos.stockanalysis.com"
    logo_tag = soup.find("img", src=lambda s: s and "logos.stockanalysis.com" in s)
    if not logo_tag:
        print("[logo] Could not find logo img in HTML.")
        return None

    svg_url = logo_tag["src"]
    #if verbose:
        #print(f"[logo] Found SVG URL: {svg_url}")

    # download SVG
    try:
        svg_resp = requests.get(svg_url, timeout=10, verify=False)
    except Exception as e:
        print(f"[logo] Error downloading SVG: {e}")
        return None

    if svg_resp.status_code != 200:
        print(f"[logo] Failed to download SVG: HTTP {svg_resp.status_code}")
        return None

    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    svg_path = out_dir_path / f"{ticker_upper}.svg"
    png_path = out_dir_path / f"{ticker_upper}.png"

    # Save SVG to disk
    with open(svg_path, "wb") as f:
        f.write(svg_resp.content)

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
        subprocess.run(inkscape_cmd, check=True, capture_output=True, timeout=60)
        if png_path.exists():
            return png_path
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"[logo] Inkscape unavailable or failed ({e.__class__.__name__}); trying cairosvg")

    # fallback without Inkscape (cloud hosts): cairosvg renders the SVG directly
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg_resp.content, write_to=str(png_path), dpi=dpi, output_height=400)
    except Exception as e:
        print(f"[logo] cairosvg failed: {e}")
        return None

   # if verbose:
       # print(f"[logo] Converted to PNG: {png_path}")

    return png_path


if __name__ == "__main__":
    # Quick manual test
    test_ticker = "AAPL"
    path = get_logo_png(test_ticker)
   # print("Result:", path)
