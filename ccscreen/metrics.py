"""Per-call covered-call metrics and flags."""

from dataclasses import dataclass, field
from datetime import date
from typing import List

from .bs import call_delta, call_price
from .models import Call


@dataclass
class Params:
    asof: date
    rate: float = 0.04            # risk-free rate, decimal
    div_yield: float = 0.0        # continuous dividend yield used for model delta
    max_spread_pct: float = 0.10  # spread / mid above this -> WIDE_SPREAD
    min_open_interest: int = 100  # below this -> LOW_OI
    premium_basis: str = "mid"    # "mid" or "bid"
    max_model_gap_pct: float = 0.10  # |mid - model| / mid above this (and above min_model_gap) -> IV_MISMATCH
    min_model_gap: float = 0.05      # dollars; smaller gaps are penny rounding, not a mismatch


@dataclass
class Result:
    call: Call
    dte: int
    mid: float
    spread_pct: float
    premium: float
    static_return: float
    annualized_yield: float
    if_called_return: float
    if_called_annualized: float
    breakeven: float
    downside_cushion: float
    upside_to_strike: float
    delta: float
    delta_source: str             # "csv" or "model"
    model_price: float            # Black-Scholes price at the row's own iv (nan if not computable)
    model_gap: float              # mid - model_price
    flags: List[str] = field(default_factory=list)


def in_window(event, asof, expiry):
    """True if an event date falls after as-of and on/before expiry."""
    return event is not None and asof < event <= expiry


def analyze(call: Call, p: Params) -> Result:
    dte = (call.expiry - p.asof).days
    mid = (call.bid + call.ask) / 2.0
    spread_pct = (call.ask - call.bid) / mid if mid > 0 else float("inf")
    premium = mid if p.premium_basis == "mid" else call.bid

    static = premium / call.spot
    ann = static * 365.0 / dte if dte > 0 else float("nan")
    called = (premium + call.strike - call.spot) / call.spot
    called_ann = called * 365.0 / dte if dte > 0 else float("nan")

    if call.delta is not None:
        delta, src = call.delta, "csv"
    else:
        delta, src = call_delta(call.spot, call.strike, dte / 365.0, p.rate, call.iv, p.div_yield), "model"

    # Data-quality check, not a pricing signal: if iv is this quote's own implied vol, the model price
    # should reproduce the mid to within rounding. A large gap means a stale or inconsistent row.
    if dte > 0 and call.iv > 0:
        model = call_price(call.spot, call.strike, dte / 365.0, p.rate, call.iv, p.div_yield)
        gap = mid - model
    else:
        model, gap = float("nan"), float("nan")

    flags = []
    if in_window(call.earnings_date, p.asof, call.expiry):
        flags.append("EARNINGS")
    if in_window(call.ex_dividend_date, p.asof, call.expiry):
        flags.append("EX_DIV")
    if spread_pct > p.max_spread_pct:
        flags.append("WIDE_SPREAD")
    if call.open_interest < p.min_open_interest:
        flags.append("LOW_OI")
    if gap == gap and abs(gap) > p.min_model_gap and mid > 0 and abs(gap) / mid > p.max_model_gap_pct:
        flags.append("IV_MISMATCH")

    return Result(call, dte, mid, spread_pct, premium, static, ann, called, called_ann,
                  call.spot - premium, premium / call.spot, (call.strike - call.spot) / call.spot,
                  delta, src, model, gap, flags)
