#!/usr/bin/env python3
"""Optional: the same main charts as matplotlib PNGs, written to docs/mpl/.

The core project is standard-library only. This script needs matplotlib
(see requirements-extra.txt). Without it, the script exits with a message.
Data is SYNTHETIC (the bundled sample chain). Run from the project root:
    python3 plots_mpl.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "docs", "mpl")

NAVY, TEAL, GRID, TEXT = "#1f3a5f", "#14b8a6", "#cbd5e1", "#334155"


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(TEXT)
    ax.spines["bottom"].set_color(TEXT)
    ax.tick_params(colors=TEXT, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def build(out_dir=OUT):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from charts import SUB, load_results
    from ccscreen.charts import FLAGS, flag_counts, heatmap_grid, payoff_points

    os.makedirs(out_dir, exist_ok=True)
    results, all_results, top = load_results()
    sym = top.call.underlying
    written = []

    def save(fig, name):
        path = os.path.join(out_dir, name)
        fig.savefig(path, dpi=150, facecolor="white", bbox_inches="tight")
        plt.close(fig)
        written.append(path)

    # 1. Yield vs delta scatter
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    clean = [r for r in results if not r.flags]
    flagged = [r for r in results if r.flags]
    ax.scatter([r.delta for r in clean], [r.annualized_yield * 100 for r in clean], color=TEAL, s=34, label="Clean")
    ax.scatter([r.delta for r in flagged], [r.annualized_yield * 100 for r in flagged], color=NAVY, marker="x", s=40,
               linewidths=2, label="Flagged")
    ax.set_xlabel("Call Delta (Rough Probability of Assignment)", color=TEXT)
    ax.set_ylabel("Annualized Premium Yield (%)", color=TEXT)
    ax.set_title("Annualized Yield vs Delta\n" + SUB, fontsize=10, color=TEXT)
    ax.legend(frameon=False, fontsize=9)
    _style(ax)
    save(fig, "yield_vs_delta.png")

    # 2. Top 10 bars
    top10 = results[:10]
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    labels = [f"{i + 1}. {r.call.underlying} {r.call.expiry.isoformat()} K{r.call.strike:g}" for i, r in enumerate(top10)]
    colors = [TEAL if r.flags else NAVY for r in top10]
    vals = [r.annualized_yield * 100 for r in top10]
    ax.barh(range(len(top10)), vals, color=colors)
    ax.set_yticks(range(len(top10)))
    ax.set_yticklabels(labels, color=TEXT, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Annualized Yield (%), in Rank Order", color=TEXT)
    ax.set_title("Top 10 Candidates by Annualized Yield\n" + SUB, fontsize=10, color=TEXT)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=NAVY, label="No Flags"),
                       plt.Rectangle((0, 0), 1, 1, color=TEAL, label="Has at Least One Flag")],
              frameon=False, fontsize=9, loc="lower right")
    save(fig, "top_candidates.png")

    # 3. Payoff of the top pick at expiry
    xs, cov, stk = payoff_points(top)
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    ax.plot(xs, stk, color=TEAL, linestyle="--", linewidth=1.8, label="Stock Only")
    ax.plot(xs, cov, color=NAVY, linewidth=2.4, label="Covered Call")
    ax.axhline(0, color=TEXT, linewidth=0.9)
    ax.axvline(top.call.strike, color=TEXT, linestyle=":", linewidth=1)
    ax.scatter([top.breakeven], [0], color=NAVY, zorder=3)
    ax.annotate(f"Breakeven {top.breakeven:.2f}", (top.breakeven, 0), xytext=(-8, 12), textcoords="offset points",
                ha="right", fontsize=9, color=TEXT)
    ax.set_xlabel("Stock Price at Expiry ($)", color=TEXT)
    ax.set_ylabel("Profit / Loss at Expiry ($ per Share)", color=TEXT)
    ax.set_title(f"Payoff at Expiry: Top Pick {sym} {top.call.expiry.isoformat()} K{top.call.strike:g}\n"
                 "Synthetic sample data; per share, mid premium", fontsize=10, color=TEXT)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    _style(ax)
    save(fig, "payoff_top_pick.png")

    # 4. Strike x expiry heatmap
    strikes, expiries, cells = heatmap_grid(all_results, sym)
    grid = [[cells.get((e, k), float("nan")) * 100 for k in strikes] for e in expiries]
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    im = ax.imshow(grid, cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(strikes)), [f"{k:g}" for k in strikes], color=TEXT, fontsize=9)
    ax.set_yticks(range(len(expiries)), [e.isoformat() for e in expiries], color=TEXT, fontsize=9)
    flat = [v for row in grid for v in row if v == v]
    vmin, vmax = min(flat), max(flat)
    for i in range(len(expiries)):
        for j in range(len(strikes)):
            v = grid[i][j]
            if v == v:  # not NaN
                dark_cell = (v - vmin) / (vmax - vmin) > 0.55 if vmax > vmin else True
                ax.text(j, i, f"{v:.1f}%", ha="center", va="center", fontsize=8,
                        color="white" if dark_cell else TEXT)
    cb = fig.colorbar(im, ax=ax, fraction=0.04)
    cb.set_label("Annualized Yield (%)", color=TEXT, fontsize=9)
    ax.set_title(f"{sym}: Annualized Yield by Strike and Expiry\n"
                 "Synthetic sample data; delta 0.10-0.50; no flag filter", fontsize=10, color=TEXT)
    ax.set_xlabel("Strike", color=TEXT)
    save(fig, "strike_expiry_heatmap.png")

    # 5. Risk flag counts
    counts = flag_counts(results)
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    vals = [counts[f] for f in FLAGS]
    bars = ax.bar(FLAGS, vals, color=NAVY)
    for b, v in zip(bars, vals):
        ax.annotate(str(v), (b.get_x() + b.get_width() / 2, v), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=10, color=TEXT, fontweight="bold")
    ax.set_ylabel("Candidates Carrying the Flag", color=TEXT)
    ax.set_title(f"Risk Flag Counts Across the Candidates\nSynthetic sample data; {len(results)} candidates passing the screen",
                 fontsize=10, color=TEXT)
    _style(ax)
    save(fig, "risk_flags.png")
    return written


def main():
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("matplotlib is not installed. This is an optional extra: pip install -r requirements-extra.txt")
        return 0
    for path in build():
        print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
