"""P/E expansion scanner for NSE stocks since 30 April 2024.

Usage:
    python pe_scanner.py            # update corporate actions from NSE, scan, write results.csv
    python pe_scanner.py --offline  # use the saved corporate_actions.json only

For every stock:
  EPS (each day)   = previous close / P/E         (NSE's "SYMBOL P/E")
                     NSE's daily PE file divides the PREVIOUS day's close by EPS (checked against
                     NSE's quote page), so we divide by the previous close to get EPS, and the P/E
                     we report for a day is that day's close / EPS - the figure NSE's quote page shows.
  Low              = lowest closing price since 30-Apr-2024, adjusted for
                     splits, bonuses and rights issues
  P/E expansion    = P/E today / P/E on the low day
  Price change     = (EPS today / EPS at low) x (P/E today / P/E at low), so the
                     price gain is split into an earnings part and a P/E part on a
                     log scale: earnings share = ln(EPS x) / ln(price x).

Left out: stocks that are loss-making today or were on their low day (no P/E),
average daily traded value below Rs 1 crore, fewer than 200 trading days in both
files, and stocks that did not trade on the latest day.

Tags (P/E x = P/E today / P/E on the low day):
  "Extreme"         P/E x >= 3, price up >= 50% from its low, EPS not fallen
  "Late stage"      P/E x >= 2 (under 3), price up >= 50% from its low, EPS not fallen
  "Profit collapse" P/E x >= 2 but EPS fell - the P/E rose because profits dropped,
                    not because investors pushed the price up. NOT P/E expansion.
  "Earnings-driven" P/E within +/-15% of the low-day P/E
The 50% "big move" threshold is our assumption; Minervini gives no number.

Corporate actions come from NSE's corporate-actions list (the data behind the
"Corporate Actions" page) and are saved to corporate_actions.json. NSE's daily P/E
is stale on a split/bonus ex-date (and often the day after), so the P/E on those
two days is ignored.
"""
import argparse
import io
import json
import math
import re
import time
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
PE_DIR, BHAV_DIR = HERE / "PE File", HERE / "bhav copy"
OUTPUT = HERE / "output"                  # everything a scan produces goes here
CA_FILE, OUT_FILE = HERE / "corporate_actions.json", OUTPUT / "results.csv"
CA_API = "https://www.nseindia.com/api/corporates-corporateActions?index=equities&from_date={:%d-%m-%Y}&to_date={:%d-%m-%Y}"
START = date(2024, 4, 30)
SERIES = ["EQ", "BE", "BZ", "SM", "ST"]  # equity series, in order of preference if a stock has two on one day
MIN_DAILY_VALUE = 1e7                     # Rs 1 crore
MIN_DAYS = 200
FLAT = (0.85, 1.15)                       # "roughly flat" P/E band for Earnings-driven
BIG_MOVE = 1.5                            # OUR assumption, not Minervini's: a "big move" = price up >= 50% from its low
ASSUMPTION = ("Assumption (ours, not Minervini's): a 'big price move' means the price is up at least 50% "
              "from its low. P/E expansion tags need that AND earnings not fallen.")


def tag(price_x, pe_x, eps_x):
    if pe_x >= 2 and eps_x < 1:
        return "Profit collapse"          # P/E up because earnings fell, not because the price ran ahead
    if pe_x >= 2 and price_x >= BIG_MOVE:
        return "Extreme" if pe_x >= 3 else "Late stage"
    if FLAT[0] <= pe_x <= FLAT[1]:
        return "Earnings-driven"
    return ""


# ---------- loading ----------

def load_prices():
    frames = []
    for f in sorted(BHAV_DIR.glob("*.zip")):
        with zipfile.ZipFile(f) as z:
            df = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
        if "TckrSymb" in df:  # UDiFF format
            df = df.rename(columns={"TradDt": "date", "TckrSymb": "sym", "SctySrs": "ser",
                                    "ClsPric": "close", "PrvsClsgPric": "prev", "TtlTrfVal": "value"})
            df["date"] = pd.to_datetime(df["date"])
        else:                 # old "CM - Bhavcopy(csv)" format
            df = df.rename(columns={"TIMESTAMP": "date", "SYMBOL": "sym", "SERIES": "ser",
                                    "CLOSE": "close", "PREVCLOSE": "prev", "TOTTRDVAL": "value"})
            df["date"] = pd.to_datetime(df["date"], format="%d-%b-%Y")
        frames.append(df[["date", "sym", "ser", "close", "prev", "value"]])
    b = pd.concat(frames)
    b = b[b.ser.isin(SERIES)]
    b["rank"] = b.ser.map(SERIES.index)
    return b.sort_values("rank").drop_duplicates(["date", "sym"]).drop(columns="rank")


def load_pe():
    frames = []
    for f in sorted(PE_DIR.glob("PE_*.csv")):
        df = pd.read_csv(f, usecols=[0, 1])
        df.columns = ["sym", "pe"]
        df["date"] = pd.to_datetime(f.stem[3:], format="%d%m%y")
        frames.append(df)
    return pd.concat(frames)


# ---------- corporate actions ----------

def corporate_actions(until, offline=False):
    """NSE corporate-action records up to `until`, refreshed from NSE unless offline."""
    saved = json.loads(CA_FILE.read_text(encoding="utf-8")) if CA_FILE.exists() else {"through": None, "records": []}
    through = date.fromisoformat(saved["through"]) if saved["through"] else None
    if offline or (through and through >= until):
        if not saved["records"]:
            raise SystemExit(f"No {CA_FILE.name} yet - run without --offline once.")
        return saved["records"]

    month = (through or START).replace(day=1)
    keep = [r for r in saved["records"] if pd.to_datetime(r["exDate"]).date() < month]
    fetched, today = [], date.today()
    print(f"Updating corporate actions from NSE ({month:%b %Y} onwards)...")
    try:
        while month <= today:
            end = (month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            req = urllib.request.Request(CA_API.format(month, end), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                fetched += json.load(resp)
            month = end + timedelta(days=1)
            time.sleep(2)
    except Exception as e:
        if saved["records"]:
            print(f"  Could not update ({e}); using saved {CA_FILE.name}.")
            return saved["records"]
        raise SystemExit(f"Could not download corporate actions from NSE: {e}")
    records = keep + fetched
    CA_FILE.write_text(json.dumps({"through": today.isoformat(), "records": records}), encoding="utf-8")
    return records


def price_factors(records, close):
    """Return [(symbol, ex_date, factor, what)] for splits, bonuses and rights.
    Prices before the ex-date are multiplied by factor to compare with prices after it."""
    events = []
    for r in records:
        s, sym = " ".join(r["subject"].split()), r["symbol"]
        ex = pd.Timestamp(pd.to_datetime(r["exDate"]).date())
        if sym not in close or ex <= close.index[0] or ex > close.index[-1]:
            continue
        if ("Split" in s or "Consolidation" in s) and (m := re.search(r"From R[se]\.?\s*([\d.]+).*?To R[se]\.?\s*([\d.]+)", s)):
            events.append((sym, ex, float(m[2]) / float(m[1]), s))
        elif m := re.fullmatch(r"Bonus (\d+)\s*:\s*(\d+)", s):           # a new shares for every b held
            a, b = int(m[1]), int(m[2])
            events.append((sym, ex, b / (a + b), s))
        elif m := re.match(r"Rights (\d+)\s*:\s*(\d+)\s*@\s*(?:Premium|Prm)\.?\s*(?:R[se]\.?)?\s*([\d.]+)", s):
            a, b = int(m[1]), int(m[2])
            before = close.loc[close.index < ex, sym].dropna()
            try:
                issue = float(r["faceVal"]) + float(m[3])
            except ValueError:
                continue
            if before.empty:
                continue
            cum = before.iloc[-1]
            terp = (b * cum + a * issue) / (a + b)                       # theoretical ex-rights price
            if terp < cum:
                events.append((sym, ex, terp / cum, s))
    return events


# ---------- scan ----------

def load_panel(offline=False):
    """Daily tables (dates x symbols): raw close, traded value, cleaned P/E, presence in PE file,
    adjusted price and EPS, plus the latest date."""
    print("Loading bhavcopies and PE files...")
    b, p = load_prices(), load_pe()
    close = b.pivot(index="date", columns="sym", values="close")
    value = b.pivot(index="date", columns="sym", values="value")
    pe = p.pivot_table(index="date", columns="sym", values="pe", aggfunc="first").reindex(index=close.index, columns=close.columns)
    in_pe_file = p.assign(x=1).pivot_table(index="date", columns="sym", values="x", aggfunc="first") \
                  .reindex(index=close.index, columns=close.columns).notna()
    last = close.index[-1]
    print(f"  {len(close.index)} trading days ({close.index[0]:%d %b %Y} to {last:%d %b %Y}), {close.shape[1]:,} symbols")

    events = price_factors(corporate_actions(last.date(), offline), close)
    adj = pd.DataFrame(1.0, index=close.index, columns=close.columns)
    for sym, ex, f, s in events:
        adj.loc[adj.index < ex, sym] *= f
        if "Rights" not in s:  # NSE's P/E is stale on the ex-date and often the next day
            i = close.index.searchsorted(ex)
            pe.iloc[i:i + 2, pe.columns.get_loc(sym)] = float("nan")
    print(f"  Adjusted {len(events)} splits / bonuses / rights issues")

    price = close * adj
    prev = b.pivot(index="date", columns="sym", values="prev")
    pe = (pe * close / prev).where(pe > 0)  # PE file uses the previous close; restate on the day's close
    eps = price / pe
    return close, value, pe, in_pe_file, price, eps, last


def scan(offline=False, panel=None):
    close, value, pe, in_pe_file, price, eps, last = panel or load_panel(offline)
    rows, skipped = [], {}
    for sym in close.columns:
        px = price[sym].dropna()
        reason = None
        if px.empty or px.index[-1] != last:
            reason = "not traded on latest day"
        elif (days := int((close[sym].notna() & in_pe_file[sym]).sum())) < MIN_DAYS:
            reason = f"fewer than {MIN_DAYS} days of data"
        elif (avg_value := value[sym].mean()) < MIN_DAILY_VALUE:
            reason = "illiquid (< Rs 1 cr/day)"
        elif pd.isna(pe.at[last, sym]):
            reason = "loss-making today (no P/E)"
        else:
            low_day = px.idxmin()
            if pd.isna(pe.at[low_day, sym]):
                reason = "no P/E on low day (loss-making then)"
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue

        price_x = px.iloc[-1] / px[low_day]
        pe_x = pe.at[last, sym] / pe.at[low_day, sym]
        eps_x = price_x / pe_x
        earn_share = 100 * math.log(eps_x) / math.log(price_x) if price_x > 1 else float("nan")
        rows.append({
            "symbol": sym, "low_date": low_day.date(), "low_price_adj": px[low_day], "price_now": px.iloc[-1],
            "price_change_pct": 100 * (price_x - 1),
            "pe_low": pe.at[low_day, sym], "pe_now": pe.at[last, sym], "pe_expansion_x": pe_x,
            "eps_low_adj": eps.at[low_day, sym], "eps_now": eps.at[last, sym], "eps_change_pct": 100 * (eps_x - 1),
            "from_earnings_pct": earn_share, "from_pe_pct": 100 - earn_share,
            "avg_daily_value_cr": avg_value / 1e7, "days_of_data": days,
            "big_move_50pct": price_x >= BIG_MOVE, "eps_not_fallen": eps_x >= 1,
            "tag": tag(price_x, pe_x, eps_x),
        })
    return pd.DataFrame(rows), skipped, last


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="don't contact NSE; use the saved corporate_actions.json")
    args = ap.parse_args()

    res, skipped, last = scan(args.offline)
    res = res.sort_values("pe_expansion_x", ascending=False)
    OUTPUT.mkdir(exist_ok=True)
    res.round(2).to_csv(OUT_FILE, index=False)
    print(f"\nScanned {len(res) + sum(skipped.values()):,} symbols; {len(res):,} kept. Left out:")
    for k, v in sorted(skipped.items(), key=lambda kv: -kv[1]):
        print(f"  {v:5,}  {k}")
    print(f"Saved {len(res):,} stocks to {OUT_FILE.name}. Tags: " +
          ", ".join(f"{t} {n}" for t, n in res.tag.replace("", "(none)").value_counts().items()))
    print(f"\n*** {ASSUMPTION} ***")

    show = {"symbol": "Symbol", "low_date": "Low date", "low_price_adj": "Low Rs", "price_now": "Now Rs",
            "price_change_pct": "Price %", "pe_low": "P/E low", "pe_now": "P/E now", "pe_expansion_x": "P/E x",
            "eps_change_pct": "EPS %", "from_earnings_pct": "From EPS %", "from_pe_pct": "From P/E %",
            "avg_daily_value_cr": "Rs cr/day"}
    for t, by in [("Extreme", "pe_expansion_x"), ("Late stage", "pe_expansion_x"),
                  ("Profit collapse", "pe_expansion_x"), ("Earnings-driven", "price_change_pct")]:
        top = res[res.tag == t].sort_values(by, ascending=False).head(20)
        note = "  [P/E rose because EPS fell - NOT P/E expansion]" if t == "Profit collapse" else ""
        print(f"\n=== {t}: top {len(top)} of {(res.tag == t).sum()} (by {show[by]}, as of {last:%d %b %Y}){note} ===")
        print(top[list(show)].rename(columns=show).to_string(index=False, float_format=lambda x: f"{x:,.1f}"))


if __name__ == "__main__":
    main()
