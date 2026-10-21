#!/usr/bin/env python3
"""Command-line interface for the covered-call screener (screening/education only, not advice)."""

import argparse
import os
from datetime import date

from ccscreen import Filters, Params, load_chain, screen, write_csv
from ccscreen.charts import write_svg

HERE = os.path.dirname(os.path.abspath(__file__))


def build_parser():
    p = argparse.ArgumentParser(description="Covered-call screener (education only, not investment advice)")
    p.add_argument("chain", nargs="?", default=os.path.join(HERE, "data", "sample_chain.csv"),
                   help="option-chain CSV (default: bundled synthetic sample)")
    p.add_argument("--asof", type=date.fromisoformat, default=date.today(), help="valuation date YYYY-MM-DD (default today)")
    p.add_argument("--rate", type=float, default=4.0, help="risk-free rate, percent (for model delta)")
    p.add_argument("--div-yield", type=float, default=0.0, help="dividend yield, percent (for model delta)")
    p.add_argument("--min-dte", type=int, default=20)
    p.add_argument("--max-dte", type=int, default=45)
    p.add_argument("--min-delta", type=float, default=0.15)
    p.add_argument("--max-delta", type=float, default=0.35)
    p.add_argument("--min-oi", type=int, default=100, help="open interest below this is flagged LOW_OI")
    p.add_argument("--max-spread", type=float, default=10.0, help="bid/ask spread %% of mid above this is flagged WIDE_SPREAD")
    p.add_argument("--max-model-gap", type=float, default=10.0,
                   help="|mid - Black-Scholes price at the row's iv| above this %% of mid (and over $0.05) "
                        "is flagged IV_MISMATCH")
    p.add_argument("--basis", choices=["mid", "bid"], default="mid", help="premium assumed received")
    p.add_argument("--exclude-flagged", action="store_true", help="drop calls that carry any flag")
    p.add_argument("--top", type=int, default=15, help="rows to print")
    p.add_argument("--csv", help="write the full ranked table to this CSV path")
    p.add_argument("--svg", help="write the yield-vs-delta chart to this SVG path")
    return p


def fmt_table(results, top):
    hdr = (f"{'#':>2} {'Sym':<5}{'Expiry':<11}{'DTE':>4}{'Strike':>8}{'Mid':>7}{'Sprd%':>7}{'Delta':>7}"
           f"{'Static%':>8}{'Ann%':>7}{'Called%':>8}{'B/E':>8}{'OI':>6}  Flags")
    lines = [hdr]
    for i, r in enumerate(results[:top], 1):
        c = r.call
        lines.append(f"{i:>2} {c.underlying:<5}{c.expiry.isoformat():<11}{r.dte:>4}{c.strike:>8g}{r.mid:>7.2f}"
                     f"{r.spread_pct*100:>7.1f}{r.delta:>7.3f}{r.static_return*100:>8.2f}{r.annualized_yield*100:>7.1f}"
                     f"{r.if_called_return*100:>8.2f}{r.breakeven:>8.2f}{c.open_interest:>6}  {','.join(r.flags) or '-'}")
    return "\n".join(lines)


def main(argv=None):
    a = build_parser().parse_args(argv)
    calls, warnings = load_chain(a.chain)
    params = Params(asof=a.asof, rate=a.rate / 100, div_yield=a.div_yield / 100,
                    max_spread_pct=a.max_spread / 100, min_open_interest=a.min_oi, premium_basis=a.basis,
                    max_model_gap_pct=a.max_model_gap / 100)
    filt = Filters(a.min_dte, a.max_dte, a.min_delta, a.max_delta, a.exclude_flagged)
    results = screen(calls, params, filt)

    print(f"Covered-call screen as of {a.asof}  |  {len(calls)} calls loaded, {len(results)} pass "
          f"(DTE {a.min_dte}-{a.max_dte}, delta {a.min_delta}-{a.max_delta}, rate {a.rate:g}%, premium={a.basis})")
    for w in warnings:
        print("warning:", w)
    expired = sum(1 for c in calls if c.expiry <= a.asof)
    if expired:
        print(f"warning: {expired} call(s) expire on or before {a.asof} and were skipped")
    if results:
        clean = sum(1 for r in results if not r.flags)
        print(f"{clean} unflagged, {len(results) - clean} flagged. Unflagged rank first, then by annualized yield.\n")
        print(fmt_table(results, a.top))
    else:
        print("No calls passed the filters.")
    print("\nScreening/education tool only. Not investment advice. Synthetic sample data unless you supply your own.")
    if a.csv:
        os.makedirs(os.path.dirname(os.path.abspath(a.csv)), exist_ok=True)
        write_csv(results, a.csv)
        print("wrote", a.csv)
    if a.svg:
        os.makedirs(os.path.dirname(os.path.abspath(a.svg)), exist_ok=True)
        write_svg(results, a.svg)
        print("wrote", a.svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
