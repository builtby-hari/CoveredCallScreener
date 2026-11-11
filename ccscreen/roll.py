"""Read-only roll check for an open short call (research estimate, not advice)."""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from .metrics import in_window
from .models import Call

LABEL = "Research estimate, not advice."
SHARES = 100


@dataclass
class Position:
    underlying: str
    strike: float
    expiry: date
    premium: float      # premium received per share when the call was sold
    contracts: int = 1


@dataclass
class RollCandidate:
    call: Call
    dte: int
    net_per_share: Optional[float]      # new bid minus buyback ask; None = UNKNOWN
    if_called_return: Optional[float]   # None = UNKNOWN


@dataclass
class RollReport:
    pos: Position
    asof: date
    dte: int
    spot: Optional[float]
    buyback: Optional[float]            # current ask; None = UNKNOWN
    intrinsic: Optional[float]
    extrinsic: Optional[float]
    signals: List[str] = field(default_factory=list)
    ranked: List[RollCandidate] = field(default_factory=list)
    unknown: List[RollCandidate] = field(default_factory=list)


def roll_check(calls: List[Call], pos: Position, asof: date) -> RollReport:
    """Report on one open short call and rank roll candidates (later expiry, same or higher strike).

    Buyback uses the ask and the new sale uses the bid, so net credit is a conservative fill.
    Ranked by net credit per extra day of duration, so a long expiry does not win on size alone.
    If-called return of a rolled position = (premium received + net roll credit + new strike - spot) / spot.
    """
    dte = (pos.expiry - asof).days
    mine = [c for c in calls if c.underlying == pos.underlying]
    cur = next((c for c in mine if c.expiry == pos.expiry and c.strike == pos.strike), None)
    spot = (cur or mine[0]).spot if (cur or mine) else None
    buyback = cur.ask if cur is not None and cur.ask > 0 else None
    intrinsic = max(spot - pos.strike, 0.0) if spot is not None else None
    extrinsic = buyback - intrinsic if buyback is not None and intrinsic is not None else None

    sig = []
    if spot is None:
        sig.append("Spot UNKNOWN (underlying not in chain)")
    elif spot > pos.strike:
        sig.append(f"ITM by {spot - pos.strike:.2f} per share")
    else:
        sig.append("Not ITM")
    sig.append(f"DTE {dte}" + (" (expiry is today or past)" if dte <= 0 else ""))
    if extrinsic is None:
        sig.append("Extrinsic UNKNOWN (no ask for the open call in the chain)")
    if cur is not None:
        if in_window(cur.earnings_date, asof, pos.expiry):
            sig.append(f"Earnings {cur.earnings_date} before expiry")
        if in_window(cur.ex_dividend_date, asof, pos.expiry):
            if cur.dividend is None:
                sig.append(f"Ex-dividend {cur.ex_dividend_date} before expiry, dividend UNKNOWN")
            elif spot > pos.strike and extrinsic is not None:
                low = extrinsic < cur.dividend
                sig.append(f"Ex-dividend {cur.ex_dividend_date} before expiry: extrinsic {extrinsic:.2f} "
                           f"{'BELOW' if low else 'not below'} dividend {cur.dividend:.2f}"
                           + (" (early assignment risk)" if low else ""))
            else:
                sig.append(f"Ex-dividend {cur.ex_dividend_date} before expiry, dividend {cur.dividend:.2f}")

    rep = RollReport(pos, asof, dte, spot, buyback, intrinsic, extrinsic, sig)
    for c in mine:
        if c.expiry <= pos.expiry or c.strike < pos.strike or c.expiry <= asof:
            continue
        if buyback is None or c.bid <= 0:  # missing quote: UNKNOWN, never ranked
            rep.unknown.append(RollCandidate(c, (c.expiry - asof).days, None, None))
            continue
        net = c.bid - buyback
        called = (pos.premium + net + c.strike - c.spot) / c.spot
        rep.ranked.append(RollCandidate(c, (c.expiry - asof).days, net, called))
    rep.ranked.sort(key=lambda r: (-r.net_per_share / (r.call.expiry - pos.expiry).days, -r.if_called_return, r.call.expiry, r.call.strike))
    return rep
