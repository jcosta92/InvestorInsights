<h1><b>Investor Insights</b></h1>
<img align="center" width="1000" alt="Header Image" src="https://raw.githubusercontent.com/jcosta92/InvestorInsights/main/header.jpg" />

<details>
<summary><h2>1. Summary</h2></summary>

**Every investor has to start somewhere!**

The objective of this project is to provide the begginer investor with simple company's financial reports.

This project *Investor Insights* is based on a basic analysis of a company's financials and a simplistic method of rating them.
The method of rating each metric and the overall result of the report was done by me (with my modest knowledge about investments), and can be adapted by its user in the template.
This is an interface between Excel and Python. The Excel template is used to calculate simple formulas and the rating of each metric, whereas the Python model gathers all the info we need via webscrapping.

</details>

<details>
<summary><h2>2. Files</h2></summary>

- *competitors_data.py*
- *logo_stockanalysis.py*
- *stock_analysis_data.py*
- *yfinance_data.py*
- *Model.ipynb*
- *report_template.xlsx*

</details>

<details>
<summary><h2>3. Main Sources</h2></summary>

- Webscrapping:
   - [*stockanalysis.com*](https://www.stockanalysis.com)
   - [*marketbeat.com*](https://www.marketbeat.com)
- Yfinance library

</details>

<details>
<summary><h2>4. Interface</h2></summary>
  
<img align="center" width="1000" alt="Header Image" src="https://raw.githubusercontent.com/jcosta92/InvestorInsights/main/FlowChart.png" />
</details>

<details>
<summary><h2>5. Metrics</h2></summary>

In this project the following metrics and their performance over the last 5 years are considered for the rating:
*General*
- Analysts recommendations
- Volatility
- Company's risks
- Stock performance

*Financial Balance*
- Cash & Equivalents
- Revenue
- Net income
- Total assets
- Shareholders' Equity
- Treasury Stock
- Yearly Net Earnings
- Gross profit & profit margin
- SGA costs
- Operating income

*Cashflow*
- Capital Expenditures
- Operating Cash Flow
- Free Cash Flow
- Net Issuance of stock

*Ratios*
- EPS
- PE, PFCF, PB, PS
- PEG
- CAGR 5Y & 10Y
- ROA, ROE, ROIC
- Operating Cash Flow Ratio
- Current Ratio
- Debt / Equity Ratio

*Dividends*
- Dividends Paid
- Payout Ratio
- Dividend Growth

*Valuation*
- Book Value Per Share
- Price / Profit Ratio 

</details>

<details>
<summary><h2>6. Template</h2></summary>

The template has several formulas in the 'Comment' and 'Rating' columns that are connected to a hidden sheet.
The user can adapt this hidden sheet.
The score is given with a certain weight for each metric - this can also be adapted.

It is not recommended to change cells in the main sheet (e.g. adding, deleting, etc)

</details>

<details>
<summary><h2>7. How-to-Run Guide</h2></summary>

1.	Download the folder into your disk.
2.	Install Inkscape: [Link](https://inkscape.org/release/inkscape-1.4.2/windows/64-bit/msi/dl/)
3.	In the file *logo_stockanalysis.py* this path is used *inkscape_path = r"C:\Program Files\Inkscape\bin\inkscape.exe"*. Make sure that this is the same installed path for this software.
4.	Make sure you have all the pips installed for the following imports:
    - import re
    - import requests
    - from bs4 import BeautifulSoup
    - import pandas as pd
    - import numpy as np
  	 - import yfinance as yf
  	 - from pathlib import Path
    - import subprocess
    - import urllib3
  	 - from typing import Dict, Any, Tuple, Optional
  	 - import datetime as dt
  	 - import matplotlib
  	 - import matplotlib.pyplot as plt
6.	Open *Model.ipnyb*.
7.	Go to the 4th cell and choose the tickers of the companies you want.
8.	Run the full code of the file.
9.	Now your reports are in the "Reports" folder.

</details>

