"""Run the whole analysis in one go and save everything to the output folder.

Usage:
    python run_scan.py            # (add --offline to skip updating corporate actions from NSE)

Writes to output/:
    results.csv          every analysed stock with its P/E expansion and tag
    backtest_events.csv  every fair-test signal with its 3- and 6-month returns
    pe_chart.html        the interactive chart + Minervini comparison (works offline)
    scan_summary.json    counts, lists and tables for the START_HERE page ("Show last scan")
"""
import argparse
import json
import math
from datetime import datetime

import build_chart
import pe_backtest
import pe_scanner

OUTPUT = pe_scanner.OUTPUT
SUMMARY = OUTPUT / "scan_summary.json"
# tag in results.csv -> (key used by the page, label, sort column for its list)
TAGS = {"Extreme": ("extreme", "Extreme", "pe_expansion_x"),
        "Late stage": ("late", "Late stage", "pe_expansion_x"),
        "Earnings-driven": ("earn", "Earnings-driven", "price_change_pct"),
        "Profit collapse": ("collapse", "Profits collapsed", "pe_expansion_x")}


def clean(v):
    """JSON-safe number: NaN -> None, floats rounded."""
    if isinstance(v, float):
        return None if math.isnan(v) else round(v, 2)
    return v


def stock_rows(df):
    return [{"s": r.symbol, "ld": f"{r.low_date:%d %b %Y}", "pc": clean(r.price_change_pct),
             "pl": clean(r.pe_low), "pn": clean(r.pe_now), "px": clean(r.pe_expansion_x),
             "ec": clean(r.eps_change_pct), "tag": r.tag if isinstance(r.tag, str) else ""}
            for r in df.itertuples()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="don't contact NSE; use the saved corporate_actions.json")
    args = ap.parse_args()
    OUTPUT.mkdir(exist_ok=True)

    panel = pe_scanner.load_panel(args.offline)
    res, skipped, last = pe_scanner.scan(panel=panel)
    res = res.sort_values("pe_expansion_x", ascending=False)
    res.round(2).to_csv(OUTPUT / "results.csv", index=False)
    print(f"Analysed {len(res):,} stocks; saved results.csv")

    print("Running the fair test (first day the P/E had doubled / tripled, no hindsight)...")
    universe = res.symbol.tolist()
    ev2 = pe_backtest.build_events(panel, universe, pe_mult=2)
    ev3 = pe_backtest.build_events(panel, universe, pe_mult=3)
    ev2.round(2).to_csv(OUTPUT / "backtest_events.csv", index=False)
    print(f"  {len(ev2):,} signals; saved backtest_events.csv")

    print("Building the chart page...")
    build_chart.write_page(res, build_chart.winners_pe(panel, res), ev2, ev3, last)

    tags = res.tag.fillna("")
    groups = {}
    for tag, (key, label, by) in TAGS.items():
        g = res[tags == tag].sort_values(by, ascending=False)
        groups[key] = {"label": label, "count": len(g), "share": round(100 * len(g) / len(res), 1),
                       "sortedBy": "price rise" if by == "price_change_pct" else "P/E expansion",
                       "stocks": stock_rows(g)}
    fair = []
    for label in pe_backtest.HORIZONS:
        for name, ev, grp in [("P/E had doubled (price up 50%+, earnings not down)", ev2, "Hype-led"),
                              ("P/E had tripled (same rules)", ev3, "Hype-led"),
                              ("Price up 50%+ with P/E flat (earnings-led)", ev2, "Earnings-led")]:
            s = pe_backtest.summary(ev, grp, label)
            fair.append({"horizon": label, "group": name, "stocks": s["Stocks measured"],
                         "median": clean(float(s["Median return %"])), "market": clean(float(s["Market same days %"])),
                         "vsMarket": clean(float(s["Median vs market %"])), "beat": clean(float(s["Beat market %"]))})
    summary = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "asOf": f"{last:%Y-%m-%d}",
        "analysed": len(res),
        "skipped": skipped,
        "groups": groups,
        "all": stock_rows(res.sort_values("symbol")),
        "fairTest": fair,
        "assumption": "A 'big move' means the price is up at least 50% from its low - our assumption, not Minervini's.",
    }
    tmp = SUMMARY.with_suffix(".tmp")  # write-then-rename: a stopped scan never leaves half a summary
    tmp.write_text(json.dumps(summary, separators=(",", ":")), encoding="utf-8")
    tmp.replace(SUMMARY)
    print("Saved scan_summary.json")
    print("SCAN COMPLETE: " + ", ".join(f"{g['label']} {g['count']}" for g in groups.values()) +
          f" (of {len(res):,} stocks).")


if __name__ == "__main__":
    main()
