"""Did hype-led rallies do worse than earnings-led ones? A test with no hindsight.

Usage:
    python pe_backtest.py            # (add --offline to skip updating corporate actions)

Walk through the days in order, using only what was known on each day:
  low      = lowest adjusted close SO FAR (since 30-Apr-2024), and the P/E on that day
  Hype-led     = first day the price is up >= 50% from that low AND the P/E has at least
                 doubled from the low-day P/E AND EPS has not fallen
  Earnings-led = first day the price is up >= 50% from that low AND the P/E is within
                 +/-15% of the low-day P/E (earnings grew along with the price)

The PE file comes out after the close, so an investor could act on the NEXT day: entry is
the next trading day's close. Returns are measured 63 trading days (~3 months) and
126 trading days (~6 months) after entry.

Benchmark ("market"): the median return of all stocks pe_scanner analysed, over exactly
the same entry and exit days. 50% "big move" is our assumption, not Minervini's.
Writes each signal to output/backtest_events.csv.
"""
import argparse
import math

import pandas as pd

import pe_scanner

HERE = pe_scanner.HERE
HORIZONS = {"3 months": 63, "6 months": 126}  # trading days


def first_signals(px, pe, pe_mult=2):
    """First day of each signal for one stock, using only data up to that day."""
    low, low_pe, found = math.inf, math.nan, {}
    for i, (p, e) in enumerate(zip(px, pe)):
        if math.isnan(p):
            continue
        if p < low:
            low, low_pe = p, e
            continue
        if math.isnan(low_pe) or math.isnan(e) or p / low < pe_scanner.BIG_MOVE:
            continue
        pe_x = e / low_pe
        eps_x = (p / low) / pe_x
        if "Hype-led" not in found and pe_x >= pe_mult and eps_x >= 1:
            found["Hype-led"] = (i, p / low, pe_x)
        if "Earnings-led" not in found and pe_scanner.FLAT[0] <= pe_x <= pe_scanner.FLAT[1]:
            found["Earnings-led"] = (i, p / low, pe_x)
        if len(found) == 2:
            break
    return found


def build_events(panel, universe, pe_mult=2):
    """One row per first signal, with 3- and 6-month returns and the market's return over the same days."""
    price, pe = panel[4][universe], panel[2][universe]
    held = price.ffill()  # a suspended stock keeps its last price
    dates = price.index
    n = len(dates)

    bench_cache = {}

    def market(i, j):
        if (i, j) not in bench_cache:
            r = (held.iloc[j] / held.iloc[i] - 1).dropna()
            bench_cache[i, j] = r.median()
        return bench_cache[i, j]

    events = []
    for sym in universe:
        for group, (i, price_x, pe_x) in first_signals(price[sym].to_numpy(), pe[sym].to_numpy(), pe_mult).items():
            entry = i + 1
            row = {"group": group, "symbol": sym, "signal_date": dates[i].date(),
                   "price_up_from_low_pct": 100 * (price_x - 1), "pe_x_from_low": pe_x,
                   "entry_date": dates[entry].date() if entry < n else None}
            for label, h in HORIZONS.items():
                exit_ = entry + h
                if exit_ < n:
                    row[f"return_{label}"] = 100 * (held[sym].iloc[exit_] / held[sym].iloc[entry] - 1)
                    row[f"market_{label}"] = 100 * market(entry, exit_)
            events.append(row)
    return pd.DataFrame(events)


def summary(ev, group, label):
    g = ev[(ev.group == group) & ev[f"return_{label}"].notna()]
    return {"Group": group, "Signals": int((ev.group == group).sum()), "Stocks measured": len(g),
            "Median return %": g[f"return_{label}"].median(),
            "Market same days %": g[f"market_{label}"].median(),
            "Median vs market %": (g[f"return_{label}"] - g[f"market_{label}"]).median(),
            "Beat market %": 100 * (g[f"return_{label}"] > g[f"market_{label}"]).mean()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="don't contact NSE; use the saved corporate_actions.json")
    args = ap.parse_args()

    panel = pe_scanner.load_panel(args.offline)
    universe = pe_scanner.scan(panel=panel)[0].symbol.tolist()
    dates = panel[4].index
    ev = build_events(panel, universe)
    pe_scanner.OUTPUT.mkdir(exist_ok=True)
    ev.round(2).to_csv(pe_scanner.OUTPUT / "backtest_events.csv", index=False)

    print(f"\nUniverse: the {len(universe):,} stocks pe_scanner analysed. "
          f"Data {dates[0]:%d %b %Y} to {dates[-1]:%d %b %Y}.")
    print("Assumption (ours, not Minervini's): a 'big move' = price up at least 50% from its low.")
    for label in HORIZONS:
        rows = [summary(ev, g, label) for g in ["Hype-led", "Earnings-led"]]
        print(f"\n=== {label} after the signal (entry next day's close) ===")
        print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f"{x:,.1f}"))
    print("\n(Stocks measured < Signals when the signal is too recent for that horizon.) Saved backtest_events.csv.")


if __name__ == "__main__":
    main()
