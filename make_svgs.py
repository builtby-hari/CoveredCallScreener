#!/usr/bin/env python3
"""Write the README charts as SVG, light and dark, with no installs.

Every chart is drawn by ccscreen/charts.py from the bundled synthetic chain (data/sample_chain.csv,
as of 2026-10-14) at the screener's default settings. The terminal picture is the real output of
`python3 cli.py --asof 2026-10-14`. Run from the project root:  python3 make_svgs.py
"""

import contextlib
import io
import os
from datetime import date

import cli
from ccscreen import Filters, Params, analyze, load_chain, screen
from ccscreen import charts as C

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "data", "sample_chain.csv")
OUT = os.path.join(HERE, "docs")
ASOF = date(2026, 10, 14)
NOTE = "Synthetic sample chain, as of 2026-10-14. Fictional tickers."


def cli_lines():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.main(["--asof", ASOF.isoformat(), "--top", "10"])
    return ["$ python3 cli.py --asof 2026-10-14 --top 10"] + buf.getvalue().rstrip().splitlines()


def main():
    calls, _ = load_chain(SAMPLE)
    params = Params(asof=ASOF, rate=0.04)
    results = screen(calls, params, Filters())
    everything = [analyze(c, params) for c in calls if c.expiry > ASOF]
    top = results[0]
    sym = top.call.underlying
    lines = cli_lines()
    jobs = {
        "yield_vs_delta": lambda d: C.yield_vs_delta_svg(results, "Annualized Yield vs Delta", NOTE, d),
        "yield_heatmap": lambda d: C.heatmap_svg(everything, sym, f"{sym}: Annualized Yield by Strike and Expiry", NOTE, d),
        "risk_flags": lambda d: C.flag_counts_svg(results, "Risk Flags on the Candidates", NOTE, d),
        "sample-output": lambda d: C.terminal_svg(lines, "Sample Output", d),
    }
    os.makedirs(OUT, exist_ok=True)
    for name, make in jobs.items():
        for dark in (False, True):
            path = os.path.join(OUT, f"{name}{'-dark' if dark else ''}.svg")
            with open(path, "w", encoding="utf-8") as f:
                f.write(make(dark))
            print("wrote", os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
