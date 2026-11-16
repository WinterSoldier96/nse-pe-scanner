"""NSE P/E Scanner - the one-click app behind START_HERE.bat.

Opens a page in an Edge/Chrome app window with four steps: quick download test,
download everything, check the data, run the scanner. Each step runs one of our
own scripts and streams its output to the page.

Safety:
  * listens on 127.0.0.1 only, and rejects requests whose Host isn't this computer
    (blocks DNS-rebinding tricks from websites);
  * every action needs a secret token that only the page served here knows, so other
    websites open in the browser can't start anything;
  * the page can only ask for a named step - the scripts and their arguments are fixed below;
  * it can only serve files listed in OUTPUT_FILES, from the output folder.
It shuts itself down a couple of minutes after the window is closed (unless a step is running).
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output"
PORT = 8642
URL = f"http://127.0.0.1:{PORT}"
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
TOKEN = secrets.token_urlsafe(32)  # new every launch; embedded in the page we serve
IDLE_SHUTDOWN = 150
MAX_LINES = 20000

# The only things the page can run: step name -> (title, [script + fixed arguments, ...])
JOBS = {
    "quick": ("Quick test: download the last 7 trading days",
              [["trading_days.py"], ["fetch_nse.py", "--last", "7", "--delay", "1.5"]]),
    "all": ("Download everything",
            [["trading_days.py"], ["fetch_nse.py", "--delay", "1.5"]]),
    "check": ("Check the data is complete", [["check_data.py"]]),
    "scan": ("Run the scanner", [["run_scan.py"]]),
}
# The only files the page can open, all inside the output folder.
OUTPUT_FILES = {
    "pe_chart.html": "text/html; charset=utf-8",
    "results.csv": "text/csv; charset=utf-8",
    "backtest_events.csv": "text/csv; charset=utf-8",
    "scan_summary.json": "application/json",
}

state = {"running": False, "job": None, "title": None, "lines": [], "base": 0, "done": 0, "total": 0,
         "finished": None, "ok": None, "message": None, "stop": False, "proc": None}
lock = threading.Lock()
last_seen = time.time()


def log(line):
    with lock:
        state["lines"].append(line)
        extra = len(state["lines"]) - MAX_LINES
        if extra > 0:
            del state["lines"][:extra]
            state["base"] += extra


def run_job(key):
    title, steps = JOBS[key]
    ok, message = True, f"{title}: finished."
    for script, *args in steps:
        with lock:
            if state["stop"]:
                ok, message = False, "Stopped."
                break
        log(f"> {script} {' '.join(args)}".rstrip())
        proc = subprocess.Popen(
            [sys.executable, "-u", str(HERE / script), *args], cwd=HERE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with lock:
            state["proc"] = proc
        for line in proc.stdout:
            line = line.rstrip()
            log(line)
            if m := re.match(r"\[(\d+)/(\d+)\]", line):  # fetch_nse progress, e.g. "[12/631]"
                with lock:
                    state["done"], state["total"] = int(m[1]), int(m[2])
        code = proc.wait()
        with lock:
            state["proc"] = None
            stopped = state["stop"]
        if stopped:
            ok, message = False, "Stopped. Files already saved are kept; run it again to continue."
            break
        if code != 0:
            ok, message = False, f"{script} stopped with an error (exit code {code}) - see the log."
            break
    log(message)
    with lock:
        state.update(running=False, finished=key, ok=ok, message=message)


def start_job(key):
    with lock:
        if state["running"]:
            return False
        state.update(running=True, job=key, title=JOBS[key][0], lines=[], base=0, done=0, total=0,
                     finished=None, ok=None, message=None, stop=False)
    threading.Thread(target=run_job, args=(key,), daemon=True).start()
    return True


def file_dates(folder, pattern, parse):
    dates = []
    for f in (HERE / folder).glob(pattern) if (HERE / folder).exists() else []:
        try:
            dates.append(parse(f.name))
        except ValueError:
            pass
    dates.sort()
    return {"count": len(dates), "first": dates[0].isoformat() if dates else None,
            "last": dates[-1].isoformat() if dates else None}


def bhav_date(name):
    if name.startswith("BhavCopy_"):
        return datetime.strptime(name.split("_")[6], "%Y%m%d").date()
    return datetime.strptime(name[2:11], "%d%b%Y").date()  # old format: cm07MAY2024bhav.csv.zip


def info():
    days = []
    if (HERE / "trading_days.csv").exists():
        days = (HERE / "trading_days.csv").read_text(encoding="utf-8").split()[1:]
    summary = OUTPUT / "scan_summary.json"
    last_scan = None
    if summary.exists():
        try:
            s = json.loads(summary.read_text(encoding="utf-8"))
            last_scan = {"generated": s["generated"], "asOf": s["asOf"]}
        except (ValueError, KeyError):
            pass
    return {
        "pe": file_dates("PE File", "PE_*.csv", lambda n: datetime.strptime(n[3:9], "%d%m%y").date()),
        "bhav": file_dates("bhav copy", "*.zip", bhav_date),
        "tradingDays": {"count": len(days), "first": days[0].split(",")[0] if days else None,
                        "last": days[-1].split(",")[0] if days else None},
        "lastScan": last_scan,
        "outputs": [{"name": n, "size": (OUTPUT / n).stat().st_size}
                    for n in OUTPUT_FILES if (OUTPUT / n).exists()],
    }


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def trusted_host(self):
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            self.send(403, {"error": "This app only answers on this computer."})
            return False
        return True

    def do_GET(self):
        global last_seen
        if not self.trusted_host():
            return
        last_seen = time.time()
        url = urlparse(self.path)
        if url.path == "/":
            page = (HERE / "ui.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            return self.send(200, page.encode(), "text/html; charset=utf-8", {
                "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                           "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                           "frame-src 'self'; frame-ancestors 'none'; connect-src 'self'"})
        if url.path == "/api/ping":
            return self.send(200, {"app": "nse-pe-scanner"})
        if url.path == "/api/info":
            return self.send(200, info())
        if url.path == "/api/status":
            since = int((parse_qs(url.query).get("since") or ["0"])[0] or 0)
            with lock:
                start = max(0, since - state["base"])
                return self.send(200, {k: state[k] for k in ("running", "job", "title", "done", "total",
                                                             "finished", "ok", "message")} |
                                 {"lines": state["lines"][start:], "next": state["base"] + len(state["lines"])})
        if url.path == "/api/last-scan":
            f = OUTPUT / "scan_summary.json"
            return self.send(200, f.read_bytes()) if f.exists() else self.send(404, {"error": "No scan saved yet."})
        if url.path.startswith("/output/"):
            name = url.path[len("/output/"):]
            target = (OUTPUT / name).resolve()
            if name not in OUTPUT_FILES or target.parent != OUTPUT.resolve() or not target.is_file():
                return self.send(404, {"error": "Not an output file."})
            extra = {"Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; "
                                                "style-src 'unsafe-inline'; frame-ancestors 'self'"}
            if name.endswith(".csv"):
                extra["Content-Disposition"] = f'attachment; filename="{name}"'
            return self.send(200, target.read_bytes(), OUTPUT_FILES[name], extra)
        self.send(404, {"error": "not found"})

    def do_POST(self):
        global last_seen
        if not self.trusted_host():
            return
        origin = self.headers.get("Origin")
        if self.headers.get("X-Token") != TOKEN or (origin and origin not in {f"http://{h}" for h in ALLOWED_HOSTS}):
            return self.send(403, {"error": "Not allowed."})
        last_seen = time.time()
        path = urlparse(self.path).path
        if path.startswith("/api/run/"):
            key = path[len("/api/run/"):]
            if key not in JOBS:
                return self.send(404, {"error": "Unknown step."})
            ok = start_job(key)
            return self.send(202 if ok else 409, {"ok": ok} if ok else {"error": "Something is already running."})
        if path == "/api/stop":
            with lock:
                state["stop"] = True
                proc = state["proc"]
            if proc and proc.poll() is None:
                proc.terminate()
            return self.send(200, {"ok": True})
        if path == "/api/open-output":
            OUTPUT.mkdir(exist_ok=True)
            os.startfile(OUTPUT)  # opens the output folder itself, nothing else
            return self.send(200, {"ok": True})
        self.send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


def open_window():
    for exe in [shutil.which("msedge"), shutil.which("chrome"),
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]:
        if exe and Path(exe).exists():
            subprocess.Popen([exe, f"--app={URL}", "--window-size=1320,900"])
            return
    webbrowser.open(URL)


def already_running():
    try:
        with urllib.request.urlopen(URL + "/api/ping", timeout=2) as r:
            return json.load(r).get("app") == "nse-pe-scanner"
    except Exception:
        return False


def main():
    no_window = "--no-window" in sys.argv
    if already_running():  # second double-click: just show the window again
        if not no_window:
            open_window()
        return
    ThreadingHTTPServer.allow_reuse_address = False  # on Windows, reuse would let two copies share the port
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        raise SystemExit(f"Port {PORT} is in use by another program.")

    def watchdog():
        while True:
            time.sleep(10)
            with lock:
                busy = state["running"]
            if not busy and time.time() - last_seen > IDLE_SHUTDOWN:
                server.shutdown()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    print(f"NSE P/E Scanner is running at {URL} - close the app window to stop it.")
    if not no_window:
        open_window()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
