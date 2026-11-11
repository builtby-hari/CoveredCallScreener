#!/usr/bin/env python3
"""Command-line interface for the covered-call screener (screening/education only, not advice)."""

import argparse
import os
from datetime import date

from ccscreen import PRESETS, Filters, Params, Position, load_chain, preset_filters, roll_check, screen, write_csv
from ccscreen.charts import write_svg

HERE = os.path.dirname(os.path.abspath(__file__))


def build_parser():
    p = argparse.ArgumentParser(description="Covered-call screener (education only, not investment advice)")
    p.add_argument("chain", nargs="?", default=os.path.join(HERE, "data", "sample_chain.csv"),
                   help="option-chain CSV (default: bundled synthetic sample)")
    p.add_argument("--asof", type=date.fromisoformat, default=date.today(), help="valuation date YYYY-MM-DD (default today)")
    p.add_argument("--rate", type=float, default=4.0, help="risk-free rate, percent (for model delta)")
    p.add_argument("--div-yield", type=float, default=0.0, help="dividend yield, percent (for model delta)")
    p.add_argument("--min-dte", type=int, default=None, help="default 20, or the preset value")
    p.add_argument("--max-dte", type=int, default=None, help="default 45, or the preset value")
    p.add_argument("--min-delta", type=float, default=None, help="default 0.15, or the preset value")
    p.add_argument("--max-delta", type=float, default=None, help="default 0.35, or the preset value")
    p.add_argument("--min-oi", type=int, default=100, help="open interest below this is flagged LOW_OI")
    p.add_argument("--min-volume", type=int, default=0, help="volume below this is flagged LOW_VOLUME (0 = off)")
    p.add_argument("--min-premium", type=float, default=0.0,
                   help="premium per share below this is flagged THIN_PREMIUM (0 = off)")
    p.add_argument("--max-spread", type=float, default=10.0, help="bid/ask spread %% of mid above this is flagged WIDE_SPREAD")
    p.add_argument("--max-model-gap", type=float, default=10.0,
                   help="|mid - Black-Scholes price at the row's iv| above this %% of mid (and over $0.05) "
                        "is flagged IV_MISMATCH")
    p.add_argument("--basis", choices=["mid", "bid"], default="mid", help="premium assumed received")
    p.add_argument("--preset", choices=sorted(PRESETS), help="named DTE and delta window (weekly: DTE 3-10); "
                   "explicit --min-dte etc. override it")
    p.add_argument("--exclude-earnings", action="store_true", help="drop calls whose window contains an earnings date")
    p.add_argument("--exclude-flagged", action="store_true", help="drop calls that carry any flag")
    p.add_argument("--top", type=int, default=15, help="rows to print")
    p.add_argument("--csv", help="write the full ranked table to this CSV path")
    p.add_argument("--svg", help="write the yield-vs-delta chart to this SVG path")
    return p


def fmt_table(results, top):
    hdr = (f"{'#':>2} {'Sym':<5}{'Expiry':<11}{'DTE':>4}{'Strike':>8}{'Mid':>7}{'Sprd%':>7}{'Delta':>7}"
           f"{'Static%':>8}{'Ann%':>7}{'Called%':>8}{'B/E':>8}{'Cush%':>7}{'P(asn)%':>8}{'OI':>6}  Flags")
    lines = [hdr]
    for i, r in enumerate(results[:top], 1):
        c = r.call
        lines.append(f"{i:>2} {c.underlying:<5}{c.expiry.isoformat():<11}{r.dte:>4}{c.strike:>8g}{r.mid:>7.2f}"
                     f"{r.spread_pct*100:>7.1f}{r.delta:>7.3f}{r.static_return*100:>8.2f}{r.annualized_yield*100:>7.1f}"
                     f"{r.if_called_return*100:>8.2f}{r.breakeven:>8.2f}{r.downside_cushion*100:>7.2f}{r.prob_assigned*100:>8.1f}{c.open_interest:>6}  {','.join(r.flags) or '-'}")
    return "\n".join(lines)


def build_roll_parser():
    p = argparse.ArgumentParser(prog="cli.py roll", description="Roll check for an open short call "
                                "(read-only research estimate, not advice)")
    p.add_argument("chain", help="current option-chain CSV")
    p.add_argument("--asof", type=date.fromisoformat, default=date.today(), help="valuation date YYYY-MM-DD (default today)")
    p.add_argument("--underlying", required=True)
    p.add_argument("--strike", type=float, required=True)
    p.add_argument("--expiry", type=date.fromisoformat, required=True, help="expiry of the open call, YYYY-MM-DD")
    p.add_argument("--premium", type=float, required=True, help="premium received per share")
    p.add_argument("--contracts", type=int, default=1)
    p.add_argument("--top", type=int, default=10, help="roll candidates to print")
    return p


def money(x):
    return "UNKNOWN" if x is None else f"{x:.2f}"


def roll_main(argv):
    parser = build_roll_parser()
    a = parser.parse_args(argv)
    if a.contracts < 1:
        parser.error("--contracts must be at least 1")
    try:
        calls, warnings = load_chain(a.chain)
    except (OSError, ValueError) as e:
        parser.error(str(e))
    pos = Position(a.underlying.upper(), a.strike, a.expiry, a.premium, a.contracts)
    r = roll_check(calls, pos, a.asof)
    n = a.contracts * 100
    print(f"Roll check as of {a.asof}: {pos.underlying} {a.contracts}x short {pos.strike:g} call "
          f"expiring {pos.expiry}, premium received {pos.premium:.2f}/share")
    print("Research estimate, not advice.")
    for w in warnings:
        print("warning:", w)
    print(f"\nSpot {money(r.spot)}  |  Buyback (ask) {money(r.buyback)}  |  Intrinsic {money(r.intrinsic)}  "
          f"|  Extrinsic {money(r.extrinsic)}")
    if r.buyback is not None:
        print(f"Buyback total {r.buyback * n:.2f}; P/L if closed now {(pos.premium - r.buyback) * n:+.2f}")
    print("Assignment risk signals:")
    for s in r.signals:
        print("  -", s)
    print(f"\nRoll candidates (later expiry, strike >= {pos.strike:g}), ranked by net credit per extra day; net = new bid - buyback ask:")
    if r.ranked:
        print(f"{'#':>2} {'Expiry':<11}{'DTE':>4}{'Strike':>8}{'NewBid':>8}{'Net/sh':>8}{'Net total':>10}{'Called%':>9}")
        for i, c in enumerate(r.ranked[:a.top], 1):
            print(f"{i:>2} {c.call.expiry.isoformat():<11}{c.dte:>4}{c.call.strike:>8g}{c.call.bid:>8.2f}"
                  f"{c.net_per_share:>+8.2f}{c.net_per_share * n:>+10.2f}{c.if_called_return * 100:>9.2f}")
    else:
        print("  none ranked")
    if r.unknown:
        print(f"{len(r.unknown)} candidate(s) UNKNOWN (missing quote) and not ranked.")
    print("\nResearch estimate, not advice. Uses ask to buy back and bid to sell. Ignores commissions, taxes, dividends.")
    return 0


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "roll":
        return roll_main(argv[1:])
    parser = build_parser()
    a = parser.parse_args(argv)
    try:
        calls, warnings = load_chain(a.chain)
    except (OSError, ValueError) as e:
        parser.error(str(e))
    params = Params(asof=a.asof, rate=a.rate / 100, div_yield=a.div_yield / 100,
                    max_spread_pct=a.max_spread / 100, min_open_interest=a.min_oi, premium_basis=a.basis,
                    max_model_gap_pct=a.max_model_gap / 100,
                    min_volume=a.min_volume, min_premium=a.min_premium)
    win = dict(min_dte=a.min_dte, max_dte=a.max_dte, min_delta=a.min_delta, max_delta=a.max_delta)
    filt = preset_filters(a.preset, **win) if a.preset else Filters(**{k: v for k, v in win.items() if v is not None})
    filt.exclude_flagged, filt.exclude_earnings = a.exclude_flagged, a.exclude_earnings
    if filt.min_dte > filt.max_dte or not 0 <= filt.min_delta <= filt.max_delta <= 1:
        parser.error("need min DTE <= max DTE and 0 <= min delta <= max delta <= 1")
    results = screen(calls, params, filt)

    print(f"Covered-call screen as of {a.asof}  |  {len(calls)} calls loaded, {len(results)} pass "
          f"(DTE {filt.min_dte}-{filt.max_dte}, delta {filt.min_delta}-{filt.max_delta}, rate {a.rate:g}%, premium={a.basis})")
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
    for path, write in ((a.csv, write_csv), (a.svg, write_svg)):
        if not path:
            continue
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            write(results, path)
        except OSError as e:
            parser.error(f"could not write {path}: {e}")
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
