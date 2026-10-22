"""Hand-written SVG charts (no plotting library). Every chart has a light and a dark variant.

Data in these charts is SYNTHETIC (the bundled sample chain). Regenerate all of them with:
    python3 charts.py
"""

import math
from datetime import date
from xml.sax.saxutils import escape

from .metrics import Result

W, H = 760, 460
L, R, T, B = 80, 30, 70, 70
FONT = 'font-family="Helvetica, Arial, sans-serif"'
MONO = 'font-family="Menlo, Consolas, Liberation Mono, monospace"'

# Palette from the README visuals spec. The ramp endpoints are extra neutrals for the heatmap only.
LIGHT = {"bg": "#ffffff", "navy": "#1f3a5f", "teal": "#14b8a6", "grid": "#cbd5e1", "text": "#334155",
         "ramp_lo": "#f1f5f9", "ramp_hi": "#1f3a5f", "ink_hi": "#ffffff", "ink_lo": "#334155"}
DARK = {"bg": None, "navy": "#60a5fa", "teal": "#2dd4bf", "grid": "#475569", "text": "#e2e8f0",
        "ramp_lo": "#1e293b", "ramp_hi": "#60a5fa", "ink_hi": "#0f172a", "ink_lo": "#e2e8f0"}

FLAGS = ["EARNINGS", "EX_DIV", "WIDE_SPREAD", "LOW_OI", "IV_MISMATCH"]


def _pal(dark):
    return DARK if dark else LIGHT


def _open(w, h, title, subtitle, dark, label):
    c = _pal(dark)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
           f'role="img" aria-label="{escape(label)}">']
    if c["bg"]:
        out.append(f'<rect width="{w}" height="{h}" fill="{c["bg"]}"/>')
    out.append(f'<text x="{w / 2}" y="28" text-anchor="middle" font-size="16" font-weight="bold" '
               f'fill="{c["text"]}" {FONT}>{escape(title)}</text>')
    out.append(f'<text x="{w / 2}" y="48" text-anchor="middle" font-size="12" fill="{c["text"]}" '
               f'{FONT}>{escape(subtitle)}</text>')
    return out


def _ticks(lo, hi, n=5):
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    t, out = math.ceil(lo / step - 1e-9) * step, []
    while t <= hi + 1e-9:
        out.append(round(t, 10))
        t += step
    return out


def _bar_path(x, y, w, h, r, horizontal):
    """Bar with rounded data-end only (the end away from the baseline); baseline end stays square."""
    r = max(0.0, min(r, w / 2, h / 2))
    if horizontal:  # baseline on the left, data-end on the right
        return (f"M{x:.1f} {y:.1f} H{x + w - r:.1f} Q{x + w:.1f} {y:.1f} {x + w:.1f} {y + r:.1f} "
                f"V{y + h - r:.1f} Q{x + w:.1f} {y + h:.1f} {x + w - r:.1f} {y + h:.1f} H{x:.1f} Z")
    # vertical: baseline at the bottom, data-end at the top
    return (f"M{x:.1f} {y + h:.1f} V{y + r:.1f} Q{x:.1f} {y:.1f} {x + r:.1f} {y:.1f} "
            f"H{x + w - r:.1f} Q{x + w:.1f} {y:.1f} {x + w:.1f} {y + r:.1f} V{y + h:.1f} Z")


# ---------- data helpers (pure, tested) ----------

def payoff_points(r: Result, lo=None, hi=None, n=121):
    """Covered-call payoff per share at expiry for one result, and the stock-only line for comparison.

    covered(S_T) = premium + min(S_T, K) - S0   (premium kept; shares called away above K)
    stock(S_T)   = S_T - S0
    """
    s0, k, prem = r.call.spot, r.call.strike, r.premium
    lo = 0.75 * s0 if lo is None else lo
    hi = 1.25 * s0 if hi is None else hi
    xs = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    covered = [prem + min(s, k) - s0 for s in xs]
    stock = [s - s0 for s in xs]
    return xs, covered, stock


def flag_counts(results):
    counts = {f: 0 for f in FLAGS}
    for r in results:
        for f in r.flags:
            counts[f] = counts.get(f, 0) + 1
    return counts


def heatmap_grid(all_results, underlying, dmin=0.10, dmax=0.50):
    """Annualized yield by (expiry, strike) for one underlying, over calls with delta in [dmin, dmax]."""
    rows = [r for r in all_results if r.call.underlying == underlying and r.dte > 0
            and r.call.bid > 0 and dmin <= r.delta <= dmax]
    strikes = sorted({r.call.strike for r in rows})
    expiries = sorted({r.call.expiry for r in rows})
    cells = {(r.call.expiry, r.call.strike): r.annualized_yield for r in rows}
    return strikes, expiries, cells


# ---------- charts ----------

def yield_vs_delta_svg(results, title="Annualized Yield vs Delta", subtitle="", dark=False):
    """Scatter of annualized yield (%) against delta. Flagged calls are navy X marks."""
    c = _pal(dark)
    pts = [(r.delta, r.annualized_yield * 100, bool(r.flags)) for r in results]
    xmin = math.floor(min([p[0] for p in pts] + [0.15]) * 20) / 20 - 0.01
    xmax = math.ceil(max([p[0] for p in pts] + [0.35]) * 20) / 20 + 0.01
    ymax = max([p[1] for p in pts] + [1.0]) * 1.08
    xs = lambda v: L + (v - xmin) / (xmax - xmin) * (W - L - R)
    ys = lambda v: H - B - v / ymax * (H - B - T)
    p = _open(W, H, title, subtitle, dark, title)
    for v in _ticks(0, ymax):
        p.append(f'<line x1="{L}" x2="{W - R}" y1="{ys(v):.1f}" y2="{ys(v):.1f}" stroke="{c["grid"]}"/>')
        p.append(f'<text x="{L - 8}" y="{ys(v) + 4:.1f}" text-anchor="end" font-size="11" fill="{c["text"]}" {FONT}>{v:g}%</text>')
    for v in _ticks(xmin, xmax):
        p.append(f'<line x1="{xs(v):.1f}" x2="{xs(v):.1f}" y1="{H - B}" y2="{H - B + 5}" stroke="{c["text"]}"/>')
        p.append(f'<text x="{xs(v):.1f}" y="{H - B + 19}" text-anchor="middle" font-size="11" fill="{c["text"]}" {FONT}>{v:.2f}</text>')
    p.append(f'<line x1="{L}" x2="{L}" y1="{T}" y2="{H - B}" stroke="{c["text"]}"/>')
    p.append(f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" stroke="{c["text"]}"/>')
    p.append(f'<text x="{(L + W - R) / 2}" y="{H - 40}" text-anchor="middle" font-size="12" fill="{c["text"]}" {FONT}>Call Delta (Rough Probability of Assignment)</text>')
    p.append(f'<text transform="translate(18 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle" font-size="12" fill="{c["text"]}" {FONT}>Annualized Premium Yield</text>')
    for d, y, flagged in pts:
        x, yy = xs(d), ys(y)
        if flagged:
            p.append(f'<path d="M{x - 4:.1f} {yy - 4:.1f} L{x + 4:.1f} {yy + 4:.1f} M{x - 4:.1f} {yy + 4:.1f} L{x + 4:.1f} {yy - 4:.1f}" stroke="{c["navy"]}" stroke-width="2" fill="none"/>')
        else:
            p.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="4" fill="{c["teal"]}" fill-opacity="0.85"/>')
    ly = H - 14
    p.append(f'<circle cx="{L + 10}" cy="{ly - 4}" r="4" fill="{c["teal"]}" fill-opacity="0.85"/>')
    p.append(f'<text x="{L + 20}" y="{ly}" font-size="11" fill="{c["text"]}" {FONT}>Clean</text>')
    p.append(f'<path d="M{L + 80} {ly - 8} L{L + 88} {ly} M{L + 80} {ly} L{L + 88} {ly - 8}" stroke="{c["navy"]}" stroke-width="2"/>')
    p.append(f'<text x="{L + 95}" y="{ly}" font-size="11" fill="{c["text"]}" {FONT}>Flagged (Earnings, Ex-Div, Wide Spread, Low OI or IV Mismatch)</text>')
    p.append('</svg>')
    return "\n".join(p)


def top_candidates_svg(results, n=10, title="Top Candidates by Annualized Yield", subtitle="", dark=False):
    """Horizontal bars for the top n in rank order. Navy = no flags, teal = at least one flag."""
    c = _pal(dark)
    top = results[:n]
    vals = [r.annualized_yield * 100 for r in top]
    xmax = max(vals + [1.0]) * 1.12
    left, right = 250, 70
    slot = (H - B - T) / n
    bh = slot * 0.62
    xs = lambda v: left + v / xmax * (W - left - right)
    p = _open(W, H, title, subtitle, dark, title)
    for v in _ticks(0, xmax):
        p.append(f'<line x1="{xs(v):.1f}" x2="{xs(v):.1f}" y1="{T}" y2="{H - B}" stroke="{c["grid"]}"/>')
        p.append(f'<text x="{xs(v):.1f}" y="{H - B + 16}" text-anchor="middle" font-size="11" fill="{c["text"]}" {FONT}>{v:g}%</text>')
    p.append(f'<line x1="{left}" x2="{left}" y1="{T}" y2="{H - B}" stroke="{c["text"]}"/>')
    for i, (r, v) in enumerate(zip(top, vals)):
        y = T + i * slot + (slot - bh) / 2
        cc = r.call
        label = f"{i + 1}. {cc.underlying}  {cc.expiry.isoformat()}  K{cc.strike:g}"
        p.append(f'<text x="{left - 10}" y="{y + bh / 2 + 4:.1f}" text-anchor="end" font-size="11" fill="{c["text"]}" {FONT}>{escape(label)}</text>')
        fill = c["teal"] if r.flags else c["navy"]
        width = xs(v) - left
        p.append(f'<path d="{_bar_path(left, y, width, bh, 4, True)}" fill="{fill}"/>')
        p.append(f'<text x="{xs(v) + 6:.1f}" y="{y + bh / 2 + 4:.1f}" font-size="11" fill="{c["text"]}" {FONT}>{v:.1f}%</text>')
    p.append(f'<text x="{(left + W - right) / 2}" y="{H - 36}" text-anchor="middle" font-size="12" fill="{c["text"]}" {FONT}>Annualized Yield (%), in Rank Order</text>')
    ly = H - 16
    p.append(f'<rect x="{left}" y="{ly - 9}" width="11" height="11" rx="2" fill="{c["navy"]}"/>')
    p.append(f'<text x="{left + 17}" y="{ly}" font-size="11" fill="{c["text"]}" {FONT}>No Flags</text>')
    p.append(f'<rect x="{left + 90}" y="{ly - 9}" width="11" height="11" rx="2" fill="{c["teal"]}"/>')
    p.append(f'<text x="{left + 107}" y="{ly}" font-size="11" fill="{c["text"]}" {FONT}>Has at Least One Flag</text>')
    p.append('</svg>')
    return "\n".join(p)


def payoff_svg(r: Result, title="Payoff at Expiry: Top Pick", subtitle="", dark=False):
    """Covered-call P/L per share at expiry (navy) against stock-only (teal dashed)."""
    c = _pal(dark)
    xs_v, cov, stk = payoff_points(r)
    k, be = r.call.strike, r.breakeven
    xmin, xmax = xs_v[0], xs_v[-1]
    ymin = min(min(cov), min(stk), 0.0)
    ymax = max(max(cov), max(stk), 0.0)
    pad = (ymax - ymin) * 0.08
    ymin, ymax = ymin - pad, ymax + pad
    px = lambda v: L + (v - xmin) / (xmax - xmin) * (W - L - R)
    py = lambda v: H - B - (v - ymin) / (ymax - ymin) * (H - B - T)
    p = _open(W, H, title, subtitle, dark, title)
    for v in _ticks(ymin, ymax):
        p.append(f'<line x1="{L}" x2="{W - R}" y1="{py(v):.1f}" y2="{py(v):.1f}" stroke="{c["grid"]}"/>')
        p.append(f'<text x="{L - 8}" y="{py(v) + 4:.1f}" text-anchor="end" font-size="11" fill="{c["text"]}" {FONT}>{v:+g}</text>')
    for v in _ticks(xmin, xmax):
        p.append(f'<text x="{px(v):.1f}" y="{H - B + 18}" text-anchor="middle" font-size="11" fill="{c["text"]}" {FONT}>{v:g}</text>')
    p.append(f'<line x1="{L}" x2="{W - R}" y1="{py(0):.1f}" y2="{py(0):.1f}" stroke="{c["text"]}" stroke-width="1"/>')
    p.append(f'<line x1="{L}" x2="{L}" y1="{T}" y2="{H - B}" stroke="{c["text"]}"/>')
    p.append(f'<line x1="{px(k):.1f}" x2="{px(k):.1f}" y1="{T}" y2="{H - B}" stroke="{c["text"]}" stroke-dasharray="3 4"/>')
    p.append(f'<text x="{px(k) + 6:.1f}" y="{T + 14}" font-size="11" fill="{c["text"]}" {FONT}>Strike {k:g}</text>')
    p.append(f'<line x1="{px(be):.1f}" x2="{px(be):.1f}" y1="{py(0):.1f}" y2="{H - B}" stroke="{c["text"]}" stroke-dasharray="3 4"/>')
    p.append(f'<circle cx="{px(be):.1f}" cy="{py(0):.1f}" r="4" fill="{c["navy"]}"/>')
    p.append(f'<text x="{px(be) - 6:.1f}" y="{H - B - 8}" text-anchor="end" font-size="11" fill="{c["text"]}" {FONT}>Breakeven {be:.2f}</text>')
    stk_pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs_v, stk))
    cov_pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs_v, cov))
    p.append(f'<polyline points="{stk_pts}" fill="none" stroke="{c["teal"]}" stroke-width="2" stroke-dasharray="6 4"/>')
    p.append(f'<polyline points="{cov_pts}" fill="none" stroke="{c["navy"]}" stroke-width="2.5"/>')
    max_gain = r.premium + k - r.call.spot
    p.append(f'<text x="{px(k) - 10:.1f}" y="{py(max_gain) - 10:.1f}" text-anchor="end" font-size="11" fill="{c["navy"]}" {FONT}>Max Gain +{max_gain:.2f}/sh ({r.if_called_return * 100:+.2f}%)</text>')
    p.append(f'<text x="{px(xmax) - 4:.1f}" y="{py(cov[-1]) + 16:.1f}" text-anchor="end" font-size="12" font-weight="bold" fill="{c["navy"]}" {FONT}>Covered Call</text>')
    p.append(f'<text x="{px(xmax) - 4:.1f}" y="{py(stk[-1]) - 8:.1f}" text-anchor="end" font-size="12" fill="{c["teal"]}" {FONT}>Stock Only</text>')
    p.append(f'<text x="{(L + W - R) / 2}" y="{H - 30}" text-anchor="middle" font-size="12" fill="{c["text"]}" {FONT}>Stock Price at Expiry ($)</text>')
    p.append(f'<text transform="translate(18 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle" font-size="12" fill="{c["text"]}" {FONT}>Profit / Loss at Expiry ($ per Share)</text>')
    p.append('</svg>')
    return "\n".join(p)


def _mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb))


def heatmap_svg(all_results, underlying, title="Strike x Expiry Heatmap", subtitle="", dark=False):
    """Annualized yield by strike (columns) and expiry (rows) for one underlying. Blank = no call in window."""
    c = _pal(dark)
    strikes, expiries, cells = heatmap_grid(all_results, underlying)
    nc, nr = len(strikes), len(expiries)
    left, gt = 110, 84
    cw = (W - left - R) / nc
    ch = 50
    gh = nr * ch
    h = gt + gh + 74
    vals = list(cells.values())
    vmin, vmax = (min(vals), max(vals)) if vals else (0.0, 1.0)
    p = _open(W, h, title, subtitle, dark, title)
    for j, k in enumerate(strikes):
        p.append(f'<text x="{left + (j + 0.5) * cw:.1f}" y="{gt - 8}" text-anchor="middle" font-size="11" fill="{c["text"]}" {FONT}>{k:g}</text>')
    p.append(f'<text x="{left - 10}" y="{gt - 8}" text-anchor="end" font-size="11" fill="{c["text"]}" {FONT}>Expiry / Strike</text>')
    for i, e in enumerate(expiries):
        y0 = gt + i * ch
        p.append(f'<text x="{left - 10}" y="{y0 + ch / 2 + 4:.1f}" text-anchor="end" font-size="11" fill="{c["text"]}" {FONT}>{e.isoformat()}</text>')
        for j, k in enumerate(strikes):
            x0 = left + j * cw
            v = cells.get((e, k))
            if v is None:
                p.append(f'<rect x="{x0 + 1:.1f}" y="{y0 + 1:.1f}" width="{cw - 2:.1f}" height="{ch - 2}" fill="none" stroke="{c["grid"]}" stroke-dasharray="3 3"/>')
                p.append(f'<text x="{x0 + cw / 2:.1f}" y="{y0 + ch / 2 + 4:.1f}" text-anchor="middle" font-size="11" fill="{c["text"]}" {FONT}>-</text>')
                continue
            t = (v - vmin) / (vmax - vmin) if vmax > vmin else 1.0
            ink = c["ink_hi"] if t > 0.55 else c["ink_lo"]
            p.append(f'<rect x="{x0 + 1:.1f}" y="{y0 + 1:.1f}" width="{cw - 2:.1f}" height="{ch - 2}" rx="3" fill="{_mix(c["ramp_lo"], c["ramp_hi"], t)}"/>')
            p.append(f'<text x="{x0 + cw / 2:.1f}" y="{y0 + ch / 2 + 4:.1f}" text-anchor="middle" font-size="11" fill="{ink}" {FONT}>{v * 100:.1f}%</text>')
    by = gt + gh + 24
    p.append(f'<defs><linearGradient id="ramp" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="{c["ramp_lo"]}"/>'
             f'<stop offset="1" stop-color="{c["ramp_hi"]}"/></linearGradient></defs>')
    p.append(f'<rect x="{left}" y="{by}" width="240" height="10" rx="2" fill="url(#ramp)" stroke="{c["grid"]}"/>')
    p.append(f'<text x="{left}" y="{by + 26}" font-size="11" fill="{c["text"]}" {FONT}>{vmin * 100:.1f}%</text>')
    p.append(f'<text x="{left + 240}" y="{by + 26}" text-anchor="end" font-size="11" fill="{c["text"]}" {FONT}>{vmax * 100:.1f}%</text>')
    p.append(f'<text x="{left + 256}" y="{by + 9}" font-size="11" fill="{c["text"]}" {FONT}>Annualized Yield (Blank = Outside Window)</text>')
    p.append('</svg>')
    return "\n".join(p)


def flag_counts_svg(results, title="Risk Flags on the Candidates", subtitle="", dark=False):
    """Vertical bars: how many candidates carry each flag. One series, so one colour and no legend."""
    c = _pal(dark)
    counts = flag_counts(results)
    vals = [counts[f] for f in FLAGS]
    top_val = max(vals + [1])
    step = max(1, math.ceil(top_val / 5))
    ymax = top_val * 1.2
    ticks = list(range(0, int(top_val) + step, step))
    slot = (W - L - R) / len(FLAGS)
    bw = slot * 0.5
    py = lambda v: H - B - v / ymax * (H - B - T)
    p = _open(W, H, title, subtitle, dark, title)
    for v in ticks:
        p.append(f'<line x1="{L}" x2="{W - R}" y1="{py(v):.1f}" y2="{py(v):.1f}" stroke="{c["grid"]}"/>')
        p.append(f'<text x="{L - 8}" y="{py(v) + 4:.1f}" text-anchor="end" font-size="11" fill="{c["text"]}" {FONT}>{v}</text>')
    p.append(f'<line x1="{L}" x2="{L}" y1="{T}" y2="{H - B}" stroke="{c["text"]}"/>')
    p.append(f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" stroke="{c["text"]}"/>')
    for i, (f, v) in enumerate(zip(FLAGS, vals)):
        x = L + i * slot + (slot - bw) / 2
        cx = L + (i + 0.5) * slot
        if v > 0:
            p.append(f'<path d="{_bar_path(x, py(v), bw, H - B - py(v), 4, False)}" fill="{c["navy"]}"/>')
        p.append(f'<text x="{cx:.1f}" y="{py(v) - 6:.1f}" text-anchor="middle" font-size="12" font-weight="bold" fill="{c["text"]}" {FONT}>{v}</text>')
        p.append(f'<text x="{cx:.1f}" y="{H - B + 18}" text-anchor="middle" font-size="11" fill="{c["text"]}" {FONT}>{f}</text>')
    p.append(f'<text transform="translate(18 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle" font-size="12" fill="{c["text"]}" {FONT}>Candidates Carrying the Flag</text>')
    p.append('</svg>')
    return "\n".join(p)


def banner_svg(name, tagline, note, dark=False):
    """1200x240 README banner: spaced project name, one-line tagline, teal rule, synthetic-data note."""
    c = _pal(dark)
    w, h = 1200, 240
    name_fill = c["navy"]
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{escape(name)}: {escape(tagline)}">']
    if c["bg"]:
        p.append(f'<rect width="{w}" height="{h}" fill="{c["bg"]}"/>')
    p.append(f'<text x="80" y="108" font-size="58" font-weight="bold" letter-spacing="2" fill="{name_fill}" {FONT}>{escape(name)}</text>')
    p.append(f'<line x1="80" y1="130" x2="240" y2="130" stroke="{c["teal"]}" stroke-width="3"/>')
    p.append(f'<text x="80" y="172" font-size="22" fill="{c["text"]}" {FONT}>{escape(tagline)}</text>')
    p.append(f'<line x1="80" y1="200" x2="1120" y2="200" stroke="{c["grid"]}" stroke-width="1"/>')
    p.append(f'<text x="80" y="222" font-size="13" fill="{c["text"]}" {FONT}>{escape(note)}</text>')
    p.append('</svg>')
    return "\n".join(p)


def terminal_svg(lines, title="Terminal", dark=False):
    """Terminal-window rendering of plain text output (monospace, rounded window, three dots)."""
    c = _pal(dark)
    lh, top = 18, 56
    w = 1060
    h = top + len(lines) * lh + 28
    body = "#f8fafc" if not dark else "#0f172a"
    bar = "#e2e8f0" if not dark else "#1e293b"
    dot = "#cbd5e1" if not dark else "#475569"
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{escape(title)}">']
    p.append(f'<rect x="8" y="8" width="{w - 16}" height="{h - 16}" rx="10" fill="{body}" stroke="{c["grid"]}"/>')
    p.append(f'<rect x="8" y="8" width="{w - 16}" height="36" rx="10" fill="{bar}"/>')
    p.append(f'<rect x="8" y="30" width="{w - 16}" height="14" fill="{bar}"/>')
    for i in range(3):
        p.append(f'<circle cx="{28 + i * 18}" cy="26" r="6" fill="{dot}"/>')
    p.append(f'<text x="{w / 2}" y="31" text-anchor="middle" font-size="12" fill="{c["text"]}" {FONT}>{escape(title)}</text>')
    for i, line in enumerate(lines):
        y = top + i * lh
        p.append(f'<text x="28" y="{y}" font-size="13" fill="{c["text"]}" {MONO} xml:space="preserve" style="white-space:pre">{escape(line)}</text>')
    p.append('</svg>')
    return "\n".join(p)


def write_svg(results, path, title="Annualized Yield vs Delta", dark=False):
    """Write the hero scatter to a file (used by the CLI --svg option)."""
    subtitle = "Synthetic sample data unless you supply your own chain"
    with open(path, "w", encoding="utf-8") as f:
        f.write(yield_vs_delta_svg(results, title, subtitle, dark))
