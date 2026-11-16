"""Check the downloaded PE Ratio files and bhavcopies against trading_days.csv.

Usage:
    python check_data.py
    python check_data.py --data "D:/some/other/folder"

For every trading day it checks that both files exist, open properly, and have a
normal number of stocks: at least 80% of the median for the same report over the
surrounding +/-10 trading days (stock counts grow over time, so a fixed number
wouldn't work). Bhavcopies are counted by EQ-series rows, so the old and new
formats are comparable.
"""
import argparse
import csv
import io
import statistics
import zipfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
WINDOW = 10        # trading days either side used for the "normal" count
MIN_RATIO = 0.80   # below this share of the local median counts as abnormal
PE_HEADER = ["SYMBOL", "SYMBOL P/E", "ADJUSTED P/E"]


def pe_file(folder, d):
    return [folder / "PE File" / f"PE_{d:%d%m%y}.csv"]


def bhav_files(folder, d):
    return [folder / "bhav copy" / f"BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip",
            folder / "bhav copy" / f"cm{d:%d}{d.strftime('%b').upper()}{d:%Y}bhav.csv.zip"]


def count_pe(path):
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    if not rows or [c.strip() for c in rows[0]] != PE_HEADER:
        raise ValueError("unexpected header")
    return sum(1 for r in rows[1:] if r and r[0].strip())


def count_bhav(path):
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError("corrupt zip")
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"expected 1 CSV inside, found {len(names)}")
        reader = csv.DictReader(io.TextIOWrapper(z.open(names[0]), encoding="utf-8-sig"))
        series = "SctySrs" if "SctySrs" in reader.fieldnames else "SERIES" if "SERIES" in reader.fieldnames else None
        if series is None:
            raise ValueError("no series column - not a bhavcopy?")
        return sum(1 for r in reader if (r[series] or "").strip() == "EQ")


def check(data=HERE):
    """Return {"days", "ok": {report: n}, "complete", "problems": [(date, report, issue)]}."""
    with open(HERE / "trading_days.csv", newline="") as f:
        days = [date.fromisoformat(r["date"]) for r in csv.DictReader(f)]

    checks = {"PE": (pe_file, count_pe), "BHAV": (bhav_files, count_bhav)}
    counts = {k: [None] * len(days) for k in checks}   # stock count, or None if unusable
    problems = []                                       # (date, report, issue)
    for i, d in enumerate(days):
        for key, (paths, counter) in checks.items():
            path = next((p for p in paths(data, d) if p.exists()), None)
            if path is None:
                problems.append((d, key, "missing"))
                continue
            try:
                counts[key][i] = counter(path)
            except Exception as e:  # anything that stops the file being read
                problems.append((d, key, f"won't open: {path.name} ({e})"))

    for key, values in counts.items():
        for i, n in enumerate(values):
            if n is None:
                continue
            nearby = [v for v in values[max(0, i - WINDOW): i + WINDOW + 1] if v is not None]
            median = statistics.median(nearby)
            if n < MIN_RATIO * median:
                problems.append((days[i], key, f"only {n} stocks (normal here is about {median:.0f})"))
                values[i] = None  # an abnormal file doesn't count as complete

    complete = sum(1 for i in range(len(days)) if all(counts[k][i] is not None for k in checks))
    ok = {k: sum(v is not None for v in counts[k]) for k in checks}
    return {"days": days, "ok": ok, "complete": complete, "problems": sorted(problems)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=HERE, help='folder holding "PE File" and "bhav copy"')
    args = p.parse_args()

    r = check(args.data)
    days, problems = r["days"], r["problems"]
    print(f"Trading days checked: {len(days)} ({days[0]} to {days[-1]})")
    for key, ok in r["ok"].items():
        print(f"  {key:4} files OK: {ok}/{len(days)} ({ok / len(days):.1%})")
    print(f"Completeness (both files OK): {r['complete']}/{len(days)} = {r['complete'] / len(days):.1%}")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for d, key, issue in problems:
            print(f"  {d} {d:%a}  {key:4}  {issue}")
    else:
        print("\nNo problems found.")


if __name__ == "__main__":
    main()
