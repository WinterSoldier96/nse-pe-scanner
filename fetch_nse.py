"""Download the PE Ratio file and CM bhavcopy for every day in trading_days.csv.

Requests go through NSE's archive API, the same call the "Archives" tab on
NSE's All Reports page makes when you click Download.

Usage:
    python fetch_nse.py            # every trading day in trading_days.csv
    python fetch_nse.py --last 7   # only the most recent 7 trading days

Files already on disk are never downloaded again. A "not found" answer is
retried once. If the new (UDiFF) bhavcopy is missing for a day before
1-Jul-2024, the old "CM - Bhavcopy(csv)" file is fetched instead.
"""
import argparse
import csv
import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
API = "https://www.nseindia.com/api/reports"
OLD_FORMAT_BEFORE = date(2024, 7, 1)
CONNECTION_RETRY_WAITS = [10, 30, 60]  # seconds; NSE drops connections when hit too fast

# report -> (name on NSE's archive page, folder, file name NSE gives it)
REPORTS = {
    "PE": ("PE Ratio", "PE File", lambda d: f"PE_{d:%d%m%y}.csv"),
    "BHAV": ("CM-UDiFF Common Bhavcopy Final (zip)", "bhav copy",
             lambda d: f"BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"),
    "OLD BHAV": ("CM - Bhavcopy(csv)", "bhav copy",
                 lambda d: f"cm{d:%d}{d.strftime('%b').upper()}{d:%Y}bhav.csv.zip"),  # cm30APR2024bhav.csv.zip
}


def load_days():
    with open(HERE / "trading_days.csv", newline="") as f:
        return [date.fromisoformat(r["date"]) for r in csv.DictReader(f)]


def request(report_name, d, delay, log=print):
    """Return the file's bytes, or None if NSE says "not found" twice."""
    archives = json.dumps([{"name": report_name, "type": "daily-reports",
                            "category": "capital-market", "section": "equities"}])
    url = API + "?" + urllib.parse.urlencode(
        {"archives": archives, "date": f"{d:%d-%b-%Y}", "type": "equities", "mode": "single"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    not_found = 0
    waits = iter(CONNECTION_RETRY_WAITS)
    while True:
        time.sleep(delay)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if data[:1] == b"<":  # an HTML error page, not a CSV/zip
                raise urllib.error.URLError("NSE returned a web page instead of a file")
            return data
        except urllib.error.HTTPError as e:
            if e.code != 404:
                err = e
            elif not_found == 0:
                not_found = 1
                log("      not found - retrying once")
                continue
            else:
                return None
        except (http.client.HTTPException, OSError) as e:  # dropped/cut-off connections, incl. IncompleteRead
            err = e
        wait = next(waits, None)
        if wait is None:
            raise RuntimeError(f"Giving up: {err}. NSE may be throttling you - wait a while and run again "
                               "(files already saved will be skipped).")
        log(f"      connection problem ({err}) - retrying in {wait}s")
        time.sleep(wait)


def save(out, folder, filename, data):
    target = out / folder / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")  # a half-written file never counts as downloaded
    part.write_bytes(data)
    part.replace(target)
    return target


def run(days, delay=1.0, out=HERE, log=print, progress=None, stop=None):
    """Fetch both reports for each day. progress(done, total) is called after each day;
    stop() returning True ends the run after the current file."""
    counts = {"saved": 0, "already had": 0, "not available": 0}
    log(f"{len(days)} trading days: {days[0]} to {days[-1]}")
    for i, d in enumerate(days, 1):
        for key in ("PE", "BHAV"):
            if stop and stop():
                log("Stopped.")
                return counts
            candidates = [key] + (["OLD BHAV"] if key == "BHAV" and d < OLD_FORMAT_BEFORE else [])
            have = [REPORTS[k][2](d) for k in candidates if (out / REPORTS[k][1] / REPORTS[k][2](d)).exists()]
            prefix = f"[{i}/{len(days)}] {d}  {key:4}"
            if have:
                log(f"{prefix}  already have {have[0]}")
                counts["already had"] += 1
                continue
            for k in candidates:
                name, folder, filename = REPORTS[k]
                data = request(name, d, delay, log)
                if data is not None:
                    target = save(out, folder, filename(d), data)
                    log(f"{prefix}  saved {target.name} ({len(data):,} bytes)")
                    counts["saved"] += 1
                    break
                if k != candidates[-1]:
                    log(f"{prefix}  new format not found - trying old CM - Bhavcopy(csv)")
            else:
                log(f"{prefix}  NOT AVAILABLE")
                counts["not available"] += 1
        if progress:
            progress(i, len(days))
    log("Done: " + ", ".join(f"{v} {k}" for k, v in counts.items()) + ".")
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--last", type=int, help="only the most recent N trading days")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests (default: 1)")
    p.add_argument("--out", type=Path, default=HERE, help="folder to save into (default: this folder)")
    args = p.parse_args()

    days = load_days()
    if args.last:
        days = days[-args.last:]
    try:
        run(days, args.delay, args.out)
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
