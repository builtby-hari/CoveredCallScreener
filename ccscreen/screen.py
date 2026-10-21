"""Filtering, ranking and CSV output."""

import csv
from dataclasses import dataclass
from typing import List

from .metrics import Params, Result, analyze
from .models import Call


@dataclass
class Filters:
    min_dte: int = 20
    max_dte: int = 45
    min_delta: float = 0.15
    max_delta: float = 0.35
    exclude_flagged: bool = False   # drop any call carrying a flag


def passes(r: Result, f: Filters) -> bool:
    if r.call.bid <= 0:
        return False
    if not (f.min_dte <= r.dte <= f.max_dte):
        return False
    if not (f.min_delta <= r.delta <= f.max_delta):
        return False
    if f.exclude_flagged and r.flags:
        return False
    return True


def rank(results: List[Result]) -> List[Result]:
    """Unflagged calls first, then by annualized yield (highest first)."""
    return sorted(results, key=lambda r: (bool(r.flags), -r.annualized_yield, r.call.underlying, r.call.strike))


def screen(calls: List[Call], params: Params, filters: Filters) -> List[Result]:
    """Analyze, filter and rank. Calls that expire on or before the as-of date are skipped."""
    live = [c for c in calls if (c.expiry - params.asof).days > 0]
    return rank([r for r in (analyze(c, params) for c in live) if passes(r, filters)])


CSV_COLUMNS = ["rank", "underlying", "expiry", "dte", "strike", "spot", "bid", "ask", "mid",
               "spread_pct", "delta", "delta_source", "model_price", "model_gap", "static_return", "annualized_yield",
               "if_called_return", "if_called_annualized", "breakeven", "downside_cushion",
               "upside_to_strike", "open_interest", "volume", "flags"]


def write_csv(results: List[Result], path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for i, r in enumerate(results, 1):
            c = r.call
            w.writerow([i, c.underlying, c.expiry.isoformat(), r.dte, c.strike, c.spot, c.bid, c.ask,
                        f"{r.mid:.4f}", f"{r.spread_pct:.4f}", f"{r.delta:.4f}", r.delta_source,
                        f"{r.model_price:.4f}", f"{r.model_gap:.4f}",
                        f"{r.static_return:.5f}", f"{r.annualized_yield:.5f}",
                        f"{r.if_called_return:.5f}", f"{r.if_called_annualized:.5f}",
                        f"{r.breakeven:.2f}", f"{r.downside_cushion:.5f}", f"{r.upside_to_strike:.5f}",
                        c.open_interest, c.volume, "|".join(r.flags)])
