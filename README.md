# NSE P/E Scanner

Companion code for **"Testing trading books with AI · Ep 1: Earnings or hype?"**

Mark Minervini says that in the biggest winners the P/E typically rose two to three times during the
big move, and that a P/E that has doubled or tripled is a warning that the move may be late. This tool
tests that idea on NSE stocks using the exchange's own daily files, and it was built with Claude Code.

> **Education using past data, not a recommendation.** Nothing here is investment advice, and you use the
> tool at your own risk. Please read the [Disclaimer](DISCLAIMER.md) before using it.

The prompts used in the video are in [`prompts/PROMPTS.md`](prompts/PROMPTS.md) (Word copy:
[`prompts/Claude_Code_prompts.docx`](prompts/Claude_Code_prompts.docx)).

## What it does

1. Downloads NSE's daily **PE Ratio** file and **CM bhavcopy** for every trading day since 30 April 2024.
2. Checks the data is complete (both files present, readable, a normal number of stocks).
3. For every liquid, profitable stock it finds the lowest price since 30 April 2024 (adjusted for splits,
   bonuses and rights issues) and measures how much of the rise came from **earnings** and how much from
   the **P/E**.
4. Tags each stock:
   - **Extreme**: P/E up 3× or more, price up 50%+, earnings not down
   - **Late stage**: P/E up 2× (under 3×), price up 50%+, earnings not down
   - **Profits collapsed**: P/E up 2×+ only because earnings fell (not P/E expansion)
   - **Earnings-driven**: P/E within ±15% of where it was at the low
5. Runs a **fair test with no hindsight**: on the first day each signal appeared, it "buys" at the next
   day's close and compares the 3- and 6-month return with the median stock over the same days.
6. Builds an interactive chart and summary page you open in your browser.

The 50% "big move" threshold is **our assumption**. Minervini gives no number.

## How to run it (Windows)

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/) and tick
   **"Add python.exe to PATH"** during setup.
2. Download this repository (green **Code** button → **Download ZIP**) and unzip it.
3. Double-click **`START_HERE.bat`**. On the first run it installs `pandas` and `numpy`, then opens the app window.
4. Click the four steps in order: **Quick test → Download everything → Check the data → Run the scanner**.

"Download everything" fetches about 1,260 files from NSE, with a pause between requests, and takes
roughly 30–40 minutes the first time. Files you already have are never downloaded again, so you can stop
and resume it at any time.

Results are saved in the `output` folder:

| File | What it is |
|---|---|
| `pe_chart.html` | Interactive chart with the Minervini comparison (works offline) |
| `results.csv` | Every analysed stock with its P/E change and group |
| `backtest_events.csv` | Every fair-test signal with its 3- and 6-month returns |
| `scan_summary.json` | The figures behind the app's results page |

### Running the scripts directly

```
pip install -r requirements.txt
python trading_days.py     # build the list of NSE trading days
python fetch_nse.py        # download the PE files and bhavcopies (--last 7 for a quick test)
python check_data.py       # completeness check
python run_scan.py         # scan, fair test and chart
```

## Files

| File | Purpose |
|---|---|
| `START_HERE.bat`, `app.py`, `ui.html` | The one-click app (runs only on your own computer, at 127.0.0.1) |
| `trading_days.py` | NSE trading days from NSE's holiday list |
| `fetch_nse.py` | Downloads the daily PE Ratio files and bhavcopies |
| `check_data.py` | Checks the downloaded data is complete |
| `pe_scanner.py` | EPS, P/E expansion and tags; adjusts for corporate actions |
| `pe_backtest.py` | The no-hindsight fair test |
| `build_chart.py` | The interactive chart page |
| `run_scan.py` | Runs the whole analysis in one go |
| `nse_holidays.json`, `trading_days.csv`, `corporate_actions.json` | Saved copies of NSE's lists, used when NSE's site doesn't answer |

The NSE data files themselves are not included. The app downloads them from NSE.

## Limitations

- Only about 2.5 years of data, much of it a falling market, so the sample is small and signals are bunched together.
- **Survivorship bias:** only stocks still trading today are included, and stocks that collapsed and were delisted are missing.
- Loss-making stocks, stocks trading under ₹1 crore a day and stocks with fewer than 200 trading days of data are left out.
- "P/E" is NSE's daily Symbol P/E (price ÷ trailing EPS), which may differ from the earnings basis in Minervini's study.
- NSE can change or throttle its website at any time. If downloads fail, wait a while and run again.

## License

The code is released under the [MIT License](LICENSE): you can use, change and share it freely, with no
warranty. It covers this code only, not NSE's data, which you download from NSE yourself and which
stays subject to NSE's terms.
