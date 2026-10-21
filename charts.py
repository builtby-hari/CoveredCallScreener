#!/usr/bin/env python3
"""Regenerate every README chart (light and dark SVG) plus the sample terminal output.

All data is SYNTHETIC: the bundled sample chain, as of 2026-10-14.
Run from the project root:  python3 charts.py
"""

import contextlib
import io
import os
from datetime import date

from ccscreen import Filters, Params, analyze, load_chain, screen
from ccscreen import charts as C
from cli import main as cli_main

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "data", "sample_chain.csv")
DOCS = os.path.join(HERE, "docs")
ASOF = date(2026, 10, 14)
SUB = "Synthetic sample chain; as of 2026-10-14; 20-45 DTE, delta 0.15-0.35"


def load_results():
    """Return (results, all_results, top_result): screened candidates and every live call analyzed."""
    calls, _ = load_chain(SAMPLE)
    params = Params(asof=ASOF)
    results = screen(calls, params, Filters())
    all_results = [analyze(c, params) for c in calls if (c.expiry - ASOF).days > 0]
    return results, all_results, results[0]


def terminal_lines():
    """The real CLI output for the README (same command as the Quickstart)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli_main(["--asof", ASOF.isoformat()])
    return buf.getvalue().rstrip("\n").split("\n")


def build_all(out_dir=DOCS):
    """Write all charts as <name>.svg and <name>-dark.svg. Returns the list of written paths."""
    os.makedirs(out_dir, exist_ok=True)
    results, all_results, top = load_results()
    sym = top.call.underlying
    lines = terminal_lines()
    charts = {
        "yield_vs_delta": lambda d: C.yield_vs_delta_svg(
            results, "Annualized Yield vs Delta", SUB, d),
        "top_candidates": lambda d: C.top_candidates_svg(
            results, 10, "Top 10 Candidates by Annualized Yield", SUB, d),
        "payoff_top_pick": lambda d: C.payoff_svg(
            top, f"Payoff at Expiry: Top Pick {sym} {top.call.expiry.isoformat()} K{top.call.strike:g}",
            f"Synthetic sample data; per share, mid premium {top.premium:.2f}, no dividends or early exercise", d),
        "strike_expiry_heatmap": lambda d: C.heatmap_svg(
            all_results, sym, f"{sym}: Annualized Yield by Strike and Expiry",
            f"Synthetic sample data; every {sym} call with delta 0.10-0.50; no flag filter", d),
        "risk_flags": lambda d: C.flag_counts_svg(
            results, "Risk Flag Counts Across the Candidates",
            f"Synthetic sample data; {len(results)} candidates passing the screen", d),
        "sample-output": lambda d: C.terminal_svg(
            ["$ python3 cli.py --asof 2026-10-14"] + lines,
            "cli.py on the Synthetic Sample Chain", d),
    }
    written = []
    for name, fn in charts.items():
        for dark, suffix in ((False, ""), (True, "-dark")):
            path = os.path.join(out_dir, f"{name}{suffix}.svg")
            with open(path, "w", encoding="utf-8") as f:
                f.write(fn(dark))
            written.append(path)
    for dark, suffix in ((False, ""), (True, "-dark")):
        path = os.path.join(out_dir, f"banner{suffix}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(C.banner_svg("Covered Call Screener",
                                 "Ranks Covered-Call Candidates from an Option Chain, with Risk Flags",
                                 "Synthetic sample data; screening and education only, not investment advice",
                                 dark))
        written.append(path)
    return written


if __name__ == "__main__":
    for path in build_all():
        print("wrote", path)
