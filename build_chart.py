"""Build pe_chart.html: an interactive, offline, single-file chart of every scanned stock,
plus a plain-English check of our results against Minervini's P/E observations.

Usage:
    python run_scan.py   (or python build_chart.py - same thing; add --offline to skip
                          updating corporate actions)
"""
import json
from html import escape

import pandas as pd

import pe_backtest
import pe_scanner

HERE = pe_scanner.HERE
OUT = pe_scanner.OUTPUT / "pe_chart.html"
GROUPS = {"Earnings-driven": "earn", "Late stage": "late", "Extreme": "extreme",
          "Profit collapse": "collapse", "": "other"}


def winners_pe(panel, res):
    """For each stock: price rise from its low to its highest close after the low, and the P/E change
    over that same stretch (the 'start' and 'end' of its big move, judged with hindsight like Minervini's study)."""
    price, pe, last = panel[4], panel[2], panel[6]
    rows = []
    for sym in res.symbol:
        px = price[sym].dropna()
        low = px.idxmin()
        peak = px[px.index >= low].idxmax()
        rows.append({"symbol": sym, "low": low, "peak": peak, "rise": px[peak] / px[low],
                     "pe_x": pe.at[peak, sym] / pe.at[low, sym]})
    w = pd.DataFrame(rows).dropna()
    w["eps_x"] = w.rise / w.pe_x
    w["recent_peak"] = (last - w.peak).dt.days <= 92  # peak within the last 3 months: move may not be over
    return w


def describe_winners(w, label):
    return {"label": label, "n": len(w), "rise": w.rise.median(), "pe_x": w.pe_x.median(),
            "q1": w.pe_x.quantile(.25), "q3": w.pe_x.quantile(.75),
            "in_2_3": 100 * w.pe_x.between(2, 3).mean(), "over_2": 100 * (w.pe_x >= 2).mean(),
            "under_1_5": 100 * (w.pe_x < 1.5).mean(), "eps_x": w.eps_x.median(),
            "recent": 100 * w.recent_peak.mean()}


def fmt_x(v):
    return f"{v:.1f}×"


def pct(v, signed=True):
    return f"{v:+.1f}%" if signed else f"{v:.0f}%"


def findings_html(w, ev2, ev3, last, n_stocks):
    top50 = describe_winners(w.nlargest(50, "rise"), "Top 50 risers")
    top10 = describe_winners(w.nlargest(max(1, round(len(w) / 10)), "rise"), "Top 10% of risers")
    trip = describe_winners(w[w.rise >= 3], "Every stock that at least tripled")
    q1_rows = "".join(
        f"<tr><th scope='row'>{d['label']}</th><td>{d['n']}</td><td>{fmt_x(d['rise'])}</td>"
        f"<td><strong>{fmt_x(d['pe_x'])}</strong></td><td>{fmt_x(d['q1'])} – {fmt_x(d['q3'])}</td>"
        f"<td>{pct(d['in_2_3'], False)}</td><td>{pct(d['under_1_5'], False)}</td><td>{fmt_x(d['eps_x'])}</td></tr>"
        for d in (top50, top10, trip))

    s = {(g, lab): pe_backtest.summary(ev, g, lab)
         for ev, g in ((ev2, "Hype-led"), (ev2, "Earnings-led"))
         for lab in pe_backtest.HORIZONS}
    s3 = {lab: pe_backtest.summary(ev3, "Hype-led", lab) for lab in pe_backtest.HORIZONS}

    def q2_row(name, d):
        return (f"<tr><th scope='row'>{name}</th><td>{d['Stocks measured']}</td>"
                f"<td>{pct(d['Median return %'])}</td><td>{pct(d['Market same days %'])}</td>"
                f"<td><strong>{d['Median vs market %']:+.1f} pts</strong></td><td>{pct(d['Beat market %'], False)}</td></tr>")

    q2_rows = ""
    for lab in pe_backtest.HORIZONS:
        q2_rows += f"<tr class='sub'><th colspan='6' scope='rowgroup'>{lab} later</th></tr>"
        q2_rows += q2_row("P/E had doubled (price up 50%+, earnings not down)", s["Hype-led", lab])
        q2_rows += q2_row("P/E had tripled (same rules)", s3[lab])
        q2_rows += q2_row("For comparison: price up 50%+, P/E flat", s["Earnings-led", lab])

    d3, d6 = s["Hype-led", "3 months"], s["Hype-led", "6 months"]
    e6 = s["Earnings-led", "6 months"]
    worse = d6["Median vs market %"] < -2 or d3["Median vs market %"] < -2
    q2_verdict = (
        f"<strong>No, not in our data.</strong> Three months after the P/E first doubled, the typical stock was "
        f"{d3['Median vs market %']:+.1f} points against the market; six months later, {d6['Median vs market %']:+.1f} points. "
        f"About half beat the market ({d3['Beat market %']:.0f}% and {d6['Beat market %']:.0f}%) – the same as a coin toss, "
        f"and no different from the stocks whose rise was matched by earnings ({e6['Median vs market %']:+.1f} points, "
        f"{e6['Beat market %']:.0f}% beat the market at six months)."
        if not worse else
        f"<strong>Yes.</strong> Three months after the P/E first doubled, the typical stock trailed the market by "
        f"{-d3['Median vs market %']:.1f} points; six months later by {-d6['Median vs market %']:.1f} points.")

    t6 = s3["6 months"]
    tripled_worse = t6["Median vs market %"] < 0
    tripled_note = (f"<li>Stocks whose P/E <em>tripled</em> were {abs(t6['Median vs market %']):.1f} points "
                    f"{'behind' if tripled_worse else 'ahead of'} the market six months later – but there are only "
                    f"{t6['Stocks measured']} of them, far too few to prove anything.</li>")
    return f"""
<section class="findings" aria-labelledby="mv">
  <h2 id="mv">Does our NSE data agree with Minervini?</h2>
  <p class="lede">Mark Minervini writes that in his study of the biggest winners, the P/E typically rose
  <strong>two to three times</strong> from the start of the big move to its end – and that a P/E that has doubled
  or tripled is a <strong>warning that the move may be late, not a sell signal by itself</strong>. Here is what
  {n_stocks:,} NSE stocks from 30 Apr 2024 to {last:%d %b %Y} say.</p>

  <h3>1. Did the biggest winners' P/E really rise about two to three times?</h3>
  <p><strong>Roughly, at the very top – less so further down.</strong> For the 50 stocks that rose the most, the
  middle (median) stock's P/E rose <strong>{fmt_x(top50['pe_x'])}</strong> from its low to its highest price – just inside
  Minervini's range. Widen the net to the top 10% and the median falls to {fmt_x(top10['pe_x'])}. But the spread is wide: only
  {top50['in_2_3']:.0f}% of the top 50 landed between 2× and 3×, and {top50['under_1_5']:.0f}% saw their P/E rise less than 1.5×.
  The winners' <em>earnings</em> also grew a lot (median {fmt_x(top50['eps_x'])}), so the big moves came from both
  profits and P/E together.</p>
  <div class="tablewrap"><table>
    <thead><tr><th scope="col">Stocks</th><th scope="col">How many</th><th scope="col">Median price rise</th>
    <th scope="col">Median P/E rise</th><th scope="col">Middle half of P/E rises</th><th scope="col">P/E rose 2–3×</th>
    <th scope="col">P/E rose under 1.5×</th><th scope="col">Median earnings rise</th></tr></thead>
    <tbody>{q1_rows}</tbody></table></div>
  <p class="note">"Start" = the stock's lowest price since 30 Apr 2024; "end" = its highest price after that low.
  {top10['recent']:.0f}% of the top-10% winners hit that high in the last three months, so many moves may not be over –
  their final P/E rise could end up bigger.</p>

  <h3>2. After the P/E had doubled, did those stocks do worse than the market?</h3>
  <p>{q2_verdict}</p>
  <div class="tablewrap"><table>
    <thead><tr><th scope="col">Signal (first day it showed, no hindsight)</th><th scope="col">Stocks</th>
    <th scope="col">Median return</th><th scope="col">Market, same days</th><th scope="col">Typical stock vs market</th>
    <th scope="col">Beat the market</th></tr></thead>
    <tbody>{q2_rows}</tbody></table></div>
  <p class="note">How this was tested: we walked forward day by day using only what was known on each day – the lowest
  price <em>so far</em> and the P/E on that day. On the first day the P/E had doubled from that low while the price was up at
  least 50% (and earnings had not fallen), we "bought" at the next day's close and measured 3 and 6 months later.
  "Market" is the median return of all {n_stocks:,} stocks over exactly the same days. "Typical stock vs market" is the median of
  each stock's return minus the market's. The 50% "big move" line is <strong>our assumption</strong>; Minervini gives no number.
  The tripled group is small, so treat its numbers as anecdote, not evidence.</p>

  <h3>3. Where we agree with Minervini – and where we don't</h3>
  <div class="cols">
    <div class="card agree"><h4>Agrees</h4><ul>
      <li>The very biggest winners did see their P/E roughly double (median {fmt_x(top50['pe_x'])} for the top 50) – P/E expansion
      is a normal part of a big move, as he says.</li>
      <li>A doubled P/E is <em>not</em> a sell signal by itself: after it appeared, about half the stocks still beat the
      market. Selling every one of them would have thrown away as many winners as losers.</li>
      {tripled_note if tripled_worse else ""}
    </ul></div>
    <div class="card differ"><h4>Doesn't agree, or can't tell</h4><ul>
      <li>"Two to three times" is not typical across our winners: most landed outside that range, many well below it.</li>
      <li>We found no sign that a doubled P/E meant the move was late: those stocks did about as well as the market
      over the next 3 and 6 months, and about as well as stocks whose rise was backed by earnings.</li>
      <li>Many P/Es that "doubled" did so because profits <em>fell</em>, not because of excitement. We kept those
      separate (the purple squares on the chart) – a plain P/E screen would mix them in.</li>
      {"" if tripled_worse else tripled_note}
    </ul></div>
  </div>

  <h3>Why our study is not the same as his</h3>
  <ul class="diffs">
    <li><strong>Market and time.</strong> He studied the biggest US winners across many decades and market cycles. We have
    about two and a half years of one market (NSE), much of it a falling market – one cycle at most.</li>
    <li><strong>Who is in the sample.</strong> He picked the greatest winners after the fact. We include every liquid,
    profitable NSE stock with enough history – winners and also-rans.</li>
    <li><strong>Survivors only.</strong> Our list holds only stocks still trading today, so companies that collapsed and were
    delisted are missing. That flatters the results, most of all for the hyped stocks.</li>
    <li><strong>What "P/E" means.</strong> We use NSE's daily P/E (price ÷ trailing earnings per share). His figures may use a
    different earnings basis.</li>
    <li><strong>Small numbers.</strong> Around a hundred signals, many on the same few weeks, so they are not independent.
    A different two-and-a-half years could give a different answer.</li>
  </ul>
  <p class="bottomline"><strong>Bottom line:</strong> in this short NSE sample, a rising P/E was a normal part of big moves,
  and a doubled P/E was not, on its own, a useful warning. That doesn't disprove Minervini – his point is about context, and
  our test is far smaller than his study – but it is a reason not to sell a stock just because its P/E has doubled.</p>
</section>"""


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>P/E Expansion Map</title>
<style>
:root {
  color-scheme: light;
  --page: #f3f5f8; --surface: #fbfcfd; --ink: #10151c; --ink-2: #485361; --muted: #738090;
  --grid: #dde2e8; --axis: #c4cbd4; --ring: rgba(16,21,28,0.10); --band: rgba(27,175,122,0.10);
  --earn: #1baf7a; --late: #eda100; --extreme: #e34948; --collapse: #6250d6; --other: #a9b1bb;
  --agree: #0b6b2f; --differ: #b3261e;
  --f-display: "Bahnschrift", "DIN Alternate", "Barlow Semi Condensed", "Arial Narrow", sans-serif;
  --f-body: "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, sans-serif;
  --f-mono: "Cascadia Mono", "Cascadia Code", Consolas, ui-monospace, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0e1218; --surface: #151a22; --ink: #e8ecf1; --ink-2: #a9b3c0; --muted: #7d8796;
    --grid: #242b35; --axis: #353e4a; --ring: rgba(255,255,255,0.10); --band: rgba(25,158,112,0.14);
    --earn: #199e70; --late: #c98500; --extreme: #d03b3b; --collapse: #9085e9; --other: #4a5361;
    --agree: #2fb35f; --differ: #ef7470;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0e1218; --surface: #151a22; --ink: #e8ecf1; --ink-2: #a9b3c0; --muted: #7d8796;
  --grid: #242b35; --axis: #353e4a; --ring: rgba(255,255,255,0.10); --band: rgba(25,158,112,0.14);
  --earn: #199e70; --late: #c98500; --extreme: #d03b3b; --collapse: #9085e9; --other: #4a5361;
  --agree: #2fb35f; --differ: #ef7470;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 16px/1.55 var(--f-body); }
h1, h2, h3, h4 { font-family: var(--f-display); font-weight: 600; text-wrap: balance; }
main { max-width: 1120px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: clamp(1.6rem, 3.5vw, 2.3rem); line-height: 1.15; margin: 0 0 8px; letter-spacing: -0.01em; }
h2 { font-size: 1.55rem; margin: 0 0 8px; }
h3 { font-size: 1.15rem; margin: 32px 0 8px; }
h4 { margin: 0 0 6px; font-size: 1rem; }
p { margin: 0 0 12px; max-width: 78ch; }
.sub-title { color: var(--ink-2); margin-bottom: 20px; }
.how { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin: 0 0 20px; padding: 0; list-style: none; }
.how li { border-top: 2px solid var(--ink); padding: 10px 2px 0; font-size: .9rem; color: var(--ink-2); }
.how strong { color: var(--ink); display: block; }
.panel { background: var(--surface); border: 1px solid var(--ring); border-radius: 4px; padding: 16px; }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px; flex: 1 1 auto; }
.legend button { display: inline-flex; align-items: center; gap: 8px; font: inherit; font-size: .9rem; color: var(--ink);
  background: transparent; border: 1px solid var(--axis); border-radius: 3px; padding: 5px 12px 5px 10px; cursor: pointer; }
.legend button[aria-pressed="false"] { color: var(--muted); border-style: dashed; }
.legend button[aria-pressed="false"] svg { opacity: .25; }
.legend button:hover { background: var(--ring); }
.legend .count { color: var(--muted); font: .82rem var(--f-mono); }
.search { position: relative; flex: 0 1 260px; }
.search input { width: 100%; font: inherit; font-size: .95rem; padding: 7px 12px; border-radius: 3px;
  border: 1px solid var(--axis); background: var(--page); color: var(--ink); }
.search-msg { font-size: .85rem; color: var(--muted); min-height: 1.3em; margin: 0 0 4px; }
.chart { position: relative; }
svg.plot { width: 100%; height: auto; display: block; touch-action: none; }
.plot text { fill: var(--muted); font-size: 12px; font-family: var(--f-mono); }
.plot .region-title, .plot .ref-label, .plot .axis-title { font-family: var(--f-display); }
.plot .tick-line { stroke: var(--grid); stroke-width: 1; }
.plot .axis-title { fill: var(--ink-2); font-size: 13px; font-weight: 600; }
.plot .ref { stroke: var(--axis); stroke-width: 1.5; fill: none; }
.plot .ref.dash { stroke-dasharray: 5 4; }
.plot .ref-label { fill: var(--ink-2); font-size: 11.5px; font-weight: 600; }
.plot .region-title { fill: var(--ink); font-size: 13px; font-weight: 700; }
.plot .region-text { fill: var(--ink-2); font-size: 12px; }
.plot .dot { stroke: var(--surface); stroke-width: 1; }
.plot .dot.other { opacity: .55; }
.plot .sel { fill: none; stroke: var(--ink); stroke-width: 2; }
.tip { position: absolute; pointer-events: none; background: var(--surface); color: var(--ink); border: 1px solid var(--axis);
  border-radius: 4px; padding: 10px 12px; font-size: .86rem; box-shadow: 0 6px 24px rgba(0,0,0,.18); min-width: 220px; display: none; z-index: 2; }
.tip .name { font: 600 1rem var(--f-mono); }
.tip .grp { display: flex; align-items: center; gap: 6px; color: var(--ink-2); margin-bottom: 6px; }
.tip .grp i { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
.tip dl { display: grid; grid-template-columns: auto auto; gap: 2px 14px; margin: 0; }
.tip dt { color: var(--ink-2); } .tip dd { margin: 0; font-weight: 600; text-align: right; font-variant-numeric: tabular-nums; }
.tip .foot { color: var(--muted); font-size: .78rem; margin-top: 6px; }
.footnote { color: var(--muted); font-size: .85rem; margin: 10px 0 0; }
details.table-view { margin-top: 14px; }
details.table-view summary { cursor: pointer; color: var(--ink-2); font-weight: 600; }
.tablewrap { overflow-x: auto; margin: 8px 0 12px; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; font-variant-numeric: tabular-nums; }
th, td { text-align: right; padding: 6px 10px; border-bottom: 1px solid var(--grid); white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
thead th { color: var(--ink-2); font-weight: 600; vertical-align: bottom; white-space: normal; }
tr.sub th { text-align: left; background: var(--page); color: var(--ink); padding-top: 10px; }
.scroll { max-height: 420px; overflow: auto; }
.findings { margin-top: 48px; }
.lede { font-size: 1.05rem; }
.note { color: var(--ink-2); font-size: .9rem; }
.cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
.card { border-top: 2px solid var(--ink); padding: 12px 2px 0; }
.card ul, .diffs { margin: 0; padding-left: 20px; } .card li, .diffs li { margin-bottom: 8px; max-width: 78ch; }
.card.agree h4 { color: var(--agree); } .card.differ h4 { color: var(--differ); }
.bottomline { margin-top: 24px; padding: 14px 0 0; border-top: 2px solid var(--ink); font-size: 1.05rem; }
@media (max-width: 640px) { .plot .region-text { display: none; } }
/* ?embed: just the chart, for the START_HERE page */
.embed, .embed body { background: transparent; overflow: hidden; }  /* the host page sizes the frame to fit */
.embed main { padding: 0; }
.embed h1, .embed .sub-title, .embed .findings, .embed main > .footnote { display: none; }
</style>
</head>
<body>
<main>
  <h1>When does a rising P/E mean hype?</h1>
  <p class="sub-title">__N__ NSE stocks, from each stock's lowest price since 30 Apr 2024 to __ASOF__. Prices are adjusted for splits, bonuses and rights issues.</p>
  <ul class="how">
    <li><strong>Every dot is one stock.</strong>Hover over (or tap) a dot to see its details.</li>
    <li><strong>Up = the price rose more</strong>since its lowest point.</li>
    <li><strong>Right = profits grew more</strong>(earnings per share) over the same time.</li>
    <li><strong>The diagonal lines are the P/E.</strong>On the green band, price and profits grew together. Above it, the price ran ahead.</li>
  </ul>

  <div class="panel">
    <div class="controls">
      <div class="legend" id="legend" role="group" aria-label="Show or hide groups"></div>
      <div class="search">
        <label for="q" class="sr" style="position:absolute;left:-9999px">Find a stock</label>
        <input id="q" type="search" list="syms" placeholder="Find a stock, e.g. RELIANCE" autocomplete="off">
        <datalist id="syms"></datalist>
      </div>
    </div>
    <p class="search-msg" id="msg" aria-live="polite">Click a group above to show or hide it.</p>
    <div class="chart" id="chart">
      <svg class="plot" id="plot" viewBox="0 0 1000 640" role="img"
           aria-label="Scatter chart: price rise since the low against earnings change, one dot per stock, coloured by group"></svg>
      <div class="tip" id="tip" role="status"></div>
    </div>
    <p class="footnote">Both axes are stretched evenly by multiples (×2 is the same distance as ×4 → ×8). A few stocks with
    extreme earnings changes are pinned to the chart edge; their tooltip shows the true numbers. Groups: <b>Late stage</b> = P/E
    at least doubled, <b>Extreme</b> = at least tripled – both only when the price is up 50%+ (our assumption, not Minervini's) and
    earnings did not fall. <b>Profits collapsed</b> = P/E at least doubled because earnings fell. <b>Earnings-driven</b> = P/E within ±15%.</p>
    <details class="table-view">
      <summary>See every stock as a table</summary>
      <div class="tablewrap scroll"><table id="tbl">
        <thead><tr><th scope="col">Stock</th><th scope="col">Group</th><th scope="col">Low date</th><th scope="col">P/E at low</th>
        <th scope="col">P/E today</th><th scope="col">Price rise</th><th scope="col">Earnings change</th></tr></thead>
        <tbody></tbody></table></div>
    </details>
  </div>
  __FINDINGS__
  <p class="footnote" style="margin-top:32px">Source: NSE daily PE Ratio files and CM bhavcopies; corporate actions from NSE.
  Data to __ASOF__. "P/E" is NSE's Symbol P/E. Loss-making stocks, stocks trading under ₹1 crore a day and stocks with under
  200 trading days of data are left out. Not investment advice.</p>
</main>
<script>
if (new URLSearchParams(location.search).has("embed")) document.documentElement.classList.add("embed");
const DATA = __DATA__;
const GROUPS = [
  {key: "earn", name: "Earnings-driven", shape: "circle"},
  {key: "late", name: "Late stage", shape: "triangle"},
  {key: "extreme", name: "Extreme", shape: "diamond"},
  {key: "collapse", name: "Profits collapsed", shape: "square"},
  {key: "other", name: "The rest", shape: "small"},
];
const byKey = Object.fromEntries(GROUPS.map(g => [g.key, g]));
const NS = "http://www.w3.org/2000/svg";
const W = 1000, H = 640, M = {l: 78, r: 22, t: 18, b: 62};
const X0 = 0.05, X1 = 20, Y0 = 1, Y1 = 40;
const sx = v => M.l + Math.log(v / X0) / Math.log(X1 / X0) * (W - M.l - M.r);
const sy = v => H - M.b - Math.log(v / Y0) / Math.log(Y1 / Y0) * (H - M.t - M.b);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const svg = document.getElementById("plot"), tip = document.getElementById("tip"), chart = document.getElementById("chart");
const visible = Object.fromEntries(GROUPS.map(g => [g.key, true]));
let selected = null;

function el(name, attrs, parent, text) {
  const e = document.createElementNS(NS, name);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}
function shapePath(shape, x, y, r) {
  if (shape === "triangle") return `M${x},${y - r * 1.25}L${x + r * 1.15},${y + r * .85}L${x - r * 1.15},${y + r * .85}Z`;
  if (shape === "diamond") return `M${x},${y - r * 1.35}L${x + r * 1.15},${y}L${x},${y + r * 1.35}L${x - r * 1.15},${y}Z`;
  if (shape === "square") return `M${x - r * .9},${y - r * .9}h${r * 1.8}v${r * 1.8}h${-r * 1.8}Z`;
  const rr = shape === "small" ? r * .65 : r;
  return `M${x - rr},${y}a${rr},${rr} 0 1,0 ${rr * 2},0a${rr},${rr} 0 1,0 ${-rr * 2},0`;
}
const fx = v => v >= 1 ? `+${Math.round((v - 1) * 100).toLocaleString()}%` : `${Math.round((v - 1) * 100)}%`;
const fpe = v => v >= 100 ? Math.round(v).toLocaleString() : v.toFixed(1);

function draw() {
  svg.textContent = "";
  const clip = el("clipPath", {id: "area"}, el("defs", {}, svg));
  el("rect", {x: M.l, y: M.t, width: W - M.l - M.r, height: H - M.t - M.b}, clip);
  // grid + axes
  const xt = [[0.1, "fell 90%"], [0.25, "fell 75%"], [0.5, "halved"], [1, "no change"], [2, "doubled"], [4, "4×"], [10, "10×"], [20, "20×"]];
  const yt = [[1, "no rise"], [1.5, "+50%"], [2, "doubled"], [3, "3×"], [5, "5×"], [10, "10×"], [20, "20×"], [40, "40×"]];
  for (const [v, t] of xt) { el("line", {class: "tick-line", x1: sx(v), x2: sx(v), y1: M.t, y2: H - M.b}, svg);
    el("text", {x: sx(v), y: H - M.b + 18, "text-anchor": "middle"}, svg, t); }
  for (const [v, t] of yt) { el("line", {class: "tick-line", x1: M.l, x2: W - M.r, y1: sy(v), y2: sy(v)}, svg);
    el("text", {x: M.l - 8, y: sy(v) + 4, "text-anchor": "end"}, svg, t); }
  el("text", {class: "axis-title", x: (M.l + W - M.r) / 2, y: H - 14, "text-anchor": "middle"}, svg,
     "How much the company's earnings per share changed  →");
  el("text", {class: "axis-title", transform: `translate(18 ${(M.t + H - M.b) / 2}) rotate(-90)`, "text-anchor": "middle"}, svg,
     "How much the share price rose since its low  →");
  const g = el("g", {"clip-path": "url(#area)"}, svg);
  // P/E roughly flat band (0.85x - 1.15x) and P/E lines
  const band = [[X0, X0 * 0.85], [X1, X1 * 0.85], [X1, X1 * 1.15], [X0, X0 * 1.15]];
  el("path", {d: "M" + band.map(([x, y]) => `${sx(x)},${sy(y)}`).join("L") + "Z", fill: "var(--band)"}, g);
  for (const k of [1, 2, 3, 0.5]) el("line", {class: "ref" + (k === 1 ? "" : " dash"), x1: sx(X0), y1: sy(X0 * k), x2: sx(X1), y2: sy(X1 * k)}, g);
  el("line", {class: "ref dash", x1: sx(1), x2: sx(1), y1: M.t, y2: H - M.b}, g);
  el("line", {class: "ref dash", x1: M.l, x2: W - M.r, y1: sy(1.5), y2: sy(1.5)}, g);
  // labels along the P/E lines
  const ang = Math.atan2(sy(10) - sy(1), sx(10) - sx(1)) * 180 / Math.PI;
  const lineLabel = (x, k, t) => el("text", {class: "ref-label", transform: `translate(${sx(x)} ${sy(x * k) - 6}) rotate(${ang})`}, g, t);
  lineLabel(13, 1, "P/E unchanged");
  lineLabel(10, 2, "P/E doubled");
  lineLabel(8, 3, "P/E tripled");
  lineLabel(10.5, 0.5, "P/E halved");
  el("text", {class: "ref-label", x: W - M.r - 4, y: sy(1.5) - 6, "text-anchor": "end"}, g, "price +50% (our “big move” line)");
  // plain-English region labels
  const region = (x, y, title, lines, anchor = "start") => {
    const t = el("text", {x: sx(x), y: sy(y), "text-anchor": anchor}, g);
    el("tspan", {class: "region-title", x: sx(x), dy: 0}, t, title);
    lines.forEach(l => el("tspan", {class: "region-text", x: sx(x), dy: 16}, t, l));
  };
  region(1.08, 22, "Price ran ahead of profits", ["The P/E went up: investors paid more", "for each rupee of profit. This is the", "“late stage” zone Minervini warns about."]);
  region(0.06, 33, "Profits fell, price didn't", ["The P/E rose only because", "earnings shrank – not hype."]);
  region(19, 2.55, "Profits ran ahead of the price", ["The stock got cheaper:", "its P/E went down."], "end");
  const tb = el("text", {class: "region-title", transform: `translate(${sx(3.3)} ${sy(3.3 * 1.15) - 8}) rotate(${ang})`}, g);
  tb.textContent = "Price grew in line with profits";
  // dots: "the rest" first so the groups sit on top
  const order = ["other", "earn", "collapse", "late", "extreme"];
  const R = 5.2;
  for (const key of order) {
    if (!visible[key]) continue;
    const grp = el("g", {}, g);
    for (const d of DATA) if (d.g === key) {
      d.px = sx(clamp(d.x, X0 * 1.08, X1 / 1.04)); d.py = sy(clamp(d.y, Y0, Y1 / 1.04));
      el("path", {class: `dot ${key}`, d: shapePath(byKey[key].shape, d.px, d.py, R), fill: `var(--${key})`}, grp);
    }
  }
  if (selected && visible[selected.g]) el("circle", {class: "sel", cx: selected.px, cy: selected.py, r: 11}, g);
}

function showTip(d) {
  tip.textContent = "";
  const add = (tag, cls, txt, parent = tip) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; parent.appendChild(e); return e; };
  add("div", "name", d.s);
  const grp = add("div", "grp"); const sw = add("i", null, null, grp); sw.style.background = `var(--${d.g})`; add("span", null, byKey[d.g].name, grp);
  const dl = add("dl");
  const row = (k, v) => { add("dt", null, k, dl); add("dd", null, v, dl); };
  row("P/E at the low", fpe(d.pl)); row("P/E today", fpe(d.pn));
  row("Price rose", fx(d.y)); row("Earnings " + (d.x >= 1 ? "rose" : "fell"), fx(d.x));
  add("div", "foot", `Low on ${d.ld} · P/E changed ${(d.pn / d.pl).toFixed(2)}×`);
  tip.style.display = "block";
  const box = chart.getBoundingClientRect(), k = box.width / W;
  let left = d.px * k + 14, top = d.py * k - 20;
  if (left + tip.offsetWidth > box.width) left = d.px * k - tip.offsetWidth - 14;
  if (top + tip.offsetHeight > box.height) top = box.height - tip.offsetHeight;
  tip.style.left = Math.max(0, left) + "px"; tip.style.top = Math.max(0, top) + "px";
}
function hideTip() { if (!selected) tip.style.display = "none"; else showTip(selected); }

svg.addEventListener("pointermove", e => {
  const box = svg.getBoundingClientRect(), k = W / box.width;
  const mx = (e.clientX - box.left) * k, my = (e.clientY - box.top) * k;
  let best = null, bd = (18 * k) ** 2;
  for (const d of DATA) if (visible[d.g] && d.px != null) {
    const dd = (d.px - mx) ** 2 + (d.py - my) ** 2;
    if (dd < bd) { bd = dd; best = d; }
  }
  best ? showTip(best) : hideTip();
});
svg.addEventListener("pointerleave", hideTip);

// legend toggles
const legend = document.getElementById("legend");
for (const gr of GROUPS) {
  const b = document.createElement("button"); b.type = "button"; b.setAttribute("aria-pressed", "true");
  const ic = el("svg", {width: 14, height: 14, viewBox: "0 0 14 14", "aria-hidden": "true"}, b);
  el("path", {d: shapePath(gr.shape, 7, 7, 5), fill: `var(--${gr.key})`}, ic);
  b.appendChild(document.createTextNode(gr.name + " "));
  const c = document.createElement("span"); c.className = "count"; c.textContent = DATA.filter(d => d.g === gr.key).length; b.appendChild(c);
  b.addEventListener("click", () => { visible[gr.key] = !visible[gr.key]; b.setAttribute("aria-pressed", visible[gr.key]); draw(); hideTip(); });
  legend.appendChild(b);
}

// search
const q = document.getElementById("q"), msg = document.getElementById("msg"), dlist = document.getElementById("syms");
for (const d of DATA) { const o = document.createElement("option"); o.value = d.s; dlist.appendChild(o); }
const bySym = Object.fromEntries(DATA.map(d => [d.s.toUpperCase(), d]));
function find(text, pick) {
  const t = text.trim().toUpperCase();
  filterTable(t);
  if (!t) { selected = null; msg.textContent = "Click a group above to show or hide it."; draw(); hideTip(); return; }
  let d = bySym[t] || (pick ? DATA.find(x => x.s.toUpperCase().startsWith(t)) : null);
  if (!d) { msg.textContent = DATA.some(x => x.s.toUpperCase().startsWith(t)) ? "Keep typing, or press Enter for the first match." :
    `“${text.trim()}” isn't in the chart – it may be loss-making, illiquid or too new.`; return; }
  if (!visible[d.g]) { visible[d.g] = true; legend.children[GROUPS.findIndex(g => g.key === d.g)].setAttribute("aria-pressed", "true"); }
  selected = d; draw(); showTip(d);
  msg.textContent = `Showing ${d.s} (${byKey[d.g].name}). Clear the box to deselect.`;
}
q.addEventListener("input", () => find(q.value, false));
q.addEventListener("keydown", e => { if (e.key === "Enter") find(q.value, true); if (e.key === "Escape") { q.value = ""; find("", false); } });

// table view
const tbody = document.querySelector("#tbl tbody");
const sorted = [...DATA].sort((a, b) => a.s.localeCompare(b.s));
for (const d of sorted) {
  const tr = document.createElement("tr"); tr.dataset.s = d.s.toUpperCase();
  for (const v of [d.s, byKey[d.g].name, d.ld, fpe(d.pl), fpe(d.pn), fx(d.y), fx(d.x)]) { const td = document.createElement("td"); td.textContent = v; tr.appendChild(td); }
  tbody.appendChild(tr);
}
function filterTable(t) { for (const tr of tbody.children) tr.hidden = !!t && !tr.dataset.s.startsWith(t); }

draw();
window.addEventListener("resize", () => { if (selected) showTip(selected); });
</script>
</body>
</html>
"""


def write_page(res, w, ev2, ev3, last):
    """Write output/pe_chart.html from the scan results, the winners table and both fair tests."""
    data = [{"s": r.symbol, "g": GROUPS[r.tag if isinstance(r.tag, str) else ""],
             "x": round(1 + r.eps_change_pct / 100, 4), "y": round(1 + r.price_change_pct / 100, 4),
             "pl": round(r.pe_low, 2), "pn": round(r.pe_now, 2), "ld": f"{r.low_date:%d %b %Y}"}
            for r in res.itertuples()]
    html = (PAGE.replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
                .replace("__FINDINGS__", findings_html(w, ev2, ev3, last, len(res)))
                .replace("__N__", f"{len(res):,}").replace("__ASOF__", escape(f"{last:%d %b %Y}")))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT.name} ({len(html) / 1024:.0f} KB) - open it in any browser; it needs no internet.")


if __name__ == "__main__":
    import run_scan  # the full pipeline builds this page along with everything else
    run_scan.main()
