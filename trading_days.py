"""Build NSE Capital Market trading days from NSE's own holiday list.

Usage:
    python trading_days.py            # refresh holidays from NSE, write trading_days.csv
    python trading_days.py --offline  # use the saved nse_holidays.json only

The holiday data is the same as on NSE's "Market Timings & Holidays" page
(api/holiday-master?type=trading&year=YYYY, "CM" segment). It is saved to
nse_holidays.json so the list can be rebuilt when NSE's site doesn't answer.

Rule: a trading day is a weekday that is not in NSE's CM holiday list, plus any
day NSE lists as "Special Live Trading", plus the EXTRA_SESSIONS below (special
and Muhurat sessions the API doesn't flag). New special sessions must be added
to EXTRA_SESSIONS by hand.
"""
import argparse
import json
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
HOLIDAYS_FILE = HERE / "nse_holidays.json"
DAYS_FILE = HERE / "trading_days.csv"
API = "https://www.nseindia.com/api/holiday-master?type=trading&year={}"
FIRST_DAY = date(2024, 4, 30)  # oldest PE file in NSE's archive

# Sessions that happened but that NSE's holiday API doesn't show as trading days.
# Each one was confirmed by a CM bhavcopy existing in NSE's archive for that date.
EXTRA_SESSIONS = {
    date(2024, 5, 18): "Saturday special live trading session",
    date(2025, 2, 1): "Saturday Union Budget session",
    date(2025, 10, 21): "Diwali Muhurat trading (listed as a holiday)",
    date(2026, 2, 1): "Sunday Union Budget session",
    date(2026, 11, 8): "Sunday Diwali Muhurat trading",
}


def refresh(years, log=print):
    """Download CM holidays for the given years and save them. Returns True on success."""
    data = {"source": API.format("YYYY"), "fetched": datetime.now().isoformat(timespec="seconds"), "CM": {}}
    try:
        for y in years:
            req = urllib.request.Request(API.format(y), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data["CM"][str(y)] = json.load(resp)["CM"]
            time.sleep(2)
    except Exception as e:  # any network/format problem -> keep the saved copy
        log(f"Could not refresh from NSE ({e}); using saved {HOLIDAYS_FILE.name}.")
        return False
    HOLIDAYS_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")
    log(f"Saved NSE holiday list for {', '.join(data['CM'])} to {HOLIDAYS_FILE.name}.")
    return True


def load_calendar():
    """Return (holidays, special_sessions, years_covered) from the saved file."""
    data = json.loads(HOLIDAYS_FILE.read_text(encoding="utf-8"))
    holidays, special = set(), set()
    for entries in data["CM"].values():
        for h in entries:
            d = datetime.strptime(h["tradingDate"], "%d-%b-%Y").date()
            (special if "special live trading" in h["description"].lower() else holidays).add(d)
    return holidays, special, {int(y) for y in data["CM"]}


def trading_days(start, end):
    """List NSE CM trading days from start to end (inclusive), using the saved holiday file."""
    holidays, special, years = load_calendar()
    missing = sorted(set(range(start.year, end.year + 1)) - years)
    if missing:
        raise RuntimeError(f"No saved NSE holidays for {missing}. Run: python trading_days.py")
    days, d = [], start
    while d <= end:
        if d in special or d in EXTRA_SESSIONS or (d.weekday() < 5 and d not in holidays):
            days.append(d)
        d += timedelta(days=1)
    return days


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--offline", action="store_true", help="don't contact NSE; use the saved holiday file")
    args = p.parse_args()
    try:
        build(offline=args.offline)
    except RuntimeError as e:
        raise SystemExit(str(e))


def build(offline=False, log=print):
    """Refresh holidays (unless offline) and rewrite trading_days.csv up to today."""
    today = date.today()
    if not offline:
        refresh(range(FIRST_DAY.year, today.year + 1), log)
    if not HOLIDAYS_FILE.exists():
        raise RuntimeError(f"No {HOLIDAYS_FILE.name} yet and NSE didn't answer - try again later.")

    days = trading_days(FIRST_DAY, today)
    DAYS_FILE.write_text("date,weekday\n" + "".join(f"{d},{d:%a}\n" for d in days), encoding="utf-8")
    log(f"Wrote {len(days)} trading days ({days[0]} to {days[-1]}) to {DAYS_FILE.name}.")
    return days


if __name__ == "__main__":
    main()
