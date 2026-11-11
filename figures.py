#!/usr/bin/env python3
"""Worked example and three PNG figures for the README.

Prints a step-by-step worked example (standard library only), then writes three PNGs to docs/figures/
(needs matplotlib: pip install -r requirements-extra.txt). Every input is the bundled SYNTHETIC sample
chain (data/sample_chain.csv, as of 2026-10-14), so all numbers are illustrative, not live market data.
Run from the project root:  python3 figures.py
"""

import os
from datetime import date

from ccscreen import (
    Params,
    Position,
    analyze,
    call_delta,
    d1_d2,
    load_chain,
    norm_cdf,
    roll_check,
)
from ccscreen.charts import payoff_points

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "data", "sample_chain.csv")
OUT = os.path.join(HERE, "docs", "figures")
ASOF = date(2026, 10, 14)
RATE = 0.04
EXAMPLE = ("SYND", date(2026, 11, 6), 102.5)          # underlying, expiry, strike of the worked example
ROLL = Position("SYND", 100.0, date(2026, 10, 23), 1.20, 2)  # open short call, premium per share, contracts
NAVY, TEAL, GRID, TEXT = "#1f3a5f", "#14b8a6", "#cbd5e1", "#334155"
SOURCE = "Source: data/sample_chain.csv (synthetic, as of 2026-10-14). Black-Scholes, r = 4%, q = 0. Illustrative only."


def find_call(calls, sym, expiry, strike):
    return next(c for c in calls if c.underlying == sym and c.expiry == expiry and c.strike == strike)


def worked_example():
    """Every intermediate number for the worked example. Pure function of the sample chain."""
    calls, _ = load_chain(SAMPLE)
    c = find_call(calls, *EXAMPLE)
    r = analyze(c, Params(asof=ASOF, rate=RATE))
    t = r.dte / 365.0
    d1, d2 = d1_d2(c.spot, c.strike, t, RATE, c.iv)
    return {"call": c, "result": r, "t": t, "d1": d1, "d2": d2,
            "nd1": norm_cdf(d1), "nd2": norm_cdf(d2)}


def print_example(w):
    c, r = w["call"], w["result"]
    print("Worked example (illustrative: synthetic sample chain, as of 2026-10-14)")
    print(f"Contract: sell 1 {c.underlying} {c.expiry} {c.strike:g} call against 100 shares")
    print(f"Inputs:   spot {c.spot:.2f}, bid {c.bid:.2f}, ask {c.ask:.2f}, iv {c.iv:.4f}, rate {RATE:.0%}, q 0")
    print(f"Step 1  DTE            = {c.expiry} minus {ASOF} = {r.dte} days, T = {r.dte}/365 = {w['t']:.4f} years")
    print(f"Step 2  mid            = ({c.bid:.2f} + {c.ask:.2f}) / 2 = {r.mid:.2f}")
    print(f"Step 3  spread %       = ({c.ask:.2f} - {c.bid:.2f}) / {r.mid:.2f} = {r.spread_pct:.1%}")
    print(f"Step 4  static return  = {r.mid:.2f} / {c.spot:.2f} = {r.static_return:.2%}")
    print(f"Step 5  annualized     = {r.static_return:.4%} x 365 / {r.dte} = {r.annualized_yield:.1%}")
    print(f"Step 6  if-called      = ({r.mid:.2f} + {c.strike:g} - {c.spot:.2f}) / {c.spot:.2f} = {r.if_called_return:.2%}")
    print(f"Step 7  breakeven      = {c.spot:.2f} - {r.mid:.2f} = {r.breakeven:.2f}")
    print(f"Step 8  d1, d2         = {w['d1']:.4f}, {w['d2']:.4f}")
    print(f"Step 9  delta          = N(d1) = {w['nd1']:.4f}   (model; no vendor delta in this file)")
    print(f"Step 10 P(finish ITM)  = N(d2) = {w['nd2']:.4f}   (risk-neutral proxy, not a forecast)")
    print(f"Step 11 model price    = {r.model_price:.4f} vs mid {r.mid:.2f}, gap {r.model_gap:+.4f} (data check)")
    print(f"Result  if the stock ends at 110 at expiry: covered call +{r.premium + c.strike - c.spot:.2f}/share "
          f"(capped at strike); stock alone +{110 - c.spot:.2f}/share")
    print("Interpretation: you collect 2.04% in 23 days, about 32% annualized, and give up gains above 102.5.")


def fig_payoff(w, plt):
    c, r = w["call"], w["result"]
    xs, cov, stk = payoff_points(r)
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    ax.plot(xs, stk, color=TEAL, linestyle="--", linewidth=1.8, label="Stock only")
    ax.plot(xs, cov, color=NAVY, linewidth=2.4, label="Covered call")
    ax.axhline(0, color=TEXT, linewidth=0.9)
    ax.axvline(c.strike, color=TEXT, linestyle=":", linewidth=1)
    ax.scatter([r.breakeven], [0], color=NAVY, zorder=3)
    ax.annotate(f"Breakeven {r.breakeven:.2f}", (r.breakeven, 0), xytext=(-10, 14), textcoords="offset points",
                ha="right", fontsize=9, color=TEXT)
    ax.annotate(f"Strike {c.strike:g}: gain capped at +{r.premium + c.strike - c.spot:.2f}/sh",
                (c.strike, r.premium + c.strike - c.spot), xytext=(-8, 8), textcoords="offset points",
                ha="right", fontsize=9, color=TEXT)
    ax.set_xlabel("Stock Price at Expiry ($)", color=TEXT)
    ax.set_ylabel("Profit or Loss at Expiry ($ per Share)", color=TEXT)
    ax.set_title(f"Covered-Call Payoff at Expiry: {c.underlying} {c.expiry.isoformat()} K{c.strike:g}\n"
                 f"Mid premium {r.premium:.2f}, spot {c.spot:.2f}, no dividends or early exercise", fontsize=10, color=TEXT)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    _finish(fig, ax, plt)
    return fig


def fig_delta_surface(w, plt):
    import numpy as np
    c = w["call"]
    sigma = c.iv  # one flat vol for the whole surface: a model picture, not a smile
    strikes = np.arange(85.0, 115.01, 0.5)
    dtes = np.arange(3, 91)
    z = np.array([[call_delta(c.spot, k, d / 365.0, RATE, sigma) for k in strikes] for d in dtes])
    fig, ax = plt.subplots(figsize=(7.6, 4.8))
    mesh = ax.pcolormesh(strikes, dtes, z, cmap="Blues", shading="auto", vmin=0, vmax=1)
    cs = ax.contour(strikes, dtes, z, levels=[0.15, 0.25, 0.35], colors=[TEAL, NAVY, TEAL], linewidths=1.4)
    ax.clabel(cs, fmt="delta %.2f", fontsize=8, inline=True)
    ax.axvline(c.spot, color=TEXT, linestyle=":", linewidth=1)
    ax.text(c.spot + 0.4, 85, f"spot {c.spot:.2f}", fontsize=8, color=TEXT)
    cb = fig.colorbar(mesh, ax=ax, fraction=0.04)
    cb.set_label("Call Delta (0 to 1)", color=TEXT, fontsize=9)
    ax.set_xlabel("Strike ($)", color=TEXT)
    ax.set_ylabel("Days to Expiry (calendar days)", color=TEXT)
    ax.set_title(f"Black-Scholes Call Delta by Strike and Days to Expiry\n"
                 f"Flat vol {sigma:.1%} (the {c.underlying} top pick's iv), r = 4%, no dividend; model only", fontsize=10,
                 color=TEXT)
    _finish(fig, ax, plt)
    return fig


def fig_roll(plt):
    calls, _ = load_chain(SAMPLE)
    rep = roll_check(calls, ROLL, ASOF)
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    if rep.ranked:
        xs = [r.dte for r in rep.ranked]
        ys = [r.net_per_share for r in rep.ranked]
        sc = ax.scatter(xs, ys, c=[r.call.strike for r in rep.ranked], cmap="Blues", edgecolors=NAVY, s=60, zorder=3)
        cb = fig.colorbar(sc, ax=ax, fraction=0.04)
        cb.set_label("Candidate Strike ($)", color=TEXT, fontsize=9)
        best = rep.ranked[0]
        ax.annotate(f"Top rank: {best.call.expiry.isoformat()} K{best.call.strike:g}, net {best.net_per_share:+.2f}/sh",
                    (best.dte, best.net_per_share), xytext=(-10, -22), textcoords="offset points", ha="right",
                    fontsize=9, color=TEXT, arrowprops={"arrowstyle": "-", "color": TEXT, "lw": 0.8})
    ax.axhline(0, color=TEXT, linewidth=0.9)
    ax.set_xlabel("Days to Candidate Expiry (calendar days from 2026-10-14)", color=TEXT)
    ax.set_ylabel("Net Roll Credit ($ per Share)", color=TEXT)
    buy = rep.buyback if rep.buyback is not None else float("nan")
    ax.set_title(f"Roll Candidates for a Short {ROLL.underlying} {ROLL.strike:g} Call expiring {ROLL.expiry.isoformat()}\n"
                 f"Net = new bid - buyback ask ({buy:.2f}); premium received {ROLL.premium:.2f}/sh; "
                 "same or higher strike only", fontsize=10, color=TEXT)
    _finish(fig, ax, plt)
    return fig


def _finish(fig, ax, plt):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.text(0.01, -0.02, SOURCE, fontsize=7, color=TEXT, ha="left")


def main():
    w = worked_example()
    print_example(w)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\nmatplotlib is not installed, so no figures were written. Run: pip install -r requirements-extra.txt")
        return 1
    os.makedirs(OUT, exist_ok=True)
    figs = [("payoff_breakeven.png", fig_payoff(w, plt)), ("delta_surface.png", fig_delta_surface(w, plt)),
            ("roll_candidates.png", fig_roll(plt))]
    for name, fig in figs:
        path = os.path.join(OUT, name)
        fig.savefig(path, dpi=150, facecolor="white", bbox_inches="tight")
        plt.close(fig)
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
