"""Data model and CSV loading for option chains."""

import csv
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

REQUIRED = ["underlying", "spot", "expiry", "strike", "bid", "ask", "iv", "open_interest", "volume"]


@dataclass
class Call:
    underlying: str
    spot: float
    expiry: date
    strike: float
    bid: float
    ask: float
    iv: float                       # decimal, e.g. 0.32
    open_interest: int
    volume: int
    delta: Optional[float] = None   # vendor delta if supplied
    ex_dividend_date: Optional[date] = None
    earnings_date: Optional[date] = None


def _date(s):
    s = (s or "").strip()
    return date.fromisoformat(s) if s else None


def _float(s):
    s = (s or "").strip()
    return float(s) if s else None


def load_chain(path) -> Tuple[List[Call], List[str]]:
    """Read a chain CSV. Returns (calls, warnings). Bad rows are skipped with a warning."""
    calls, warnings = [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(line for line in f if not line.startswith("#"))  # '#' lines = comments
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing required column(s): {', '.join(missing)}")
        for n, row in enumerate(reader, start=2):
            try:
                iv = _float(row["iv"])
                call = Call(
                    underlying=row["underlying"].strip().upper(),
                    spot=float(row["spot"]), expiry=date.fromisoformat(row["expiry"].strip()),
                    strike=float(row["strike"]), bid=float(row["bid"]), ask=float(row["ask"]),
                    iv=iv if iv is not None else 0.0,
                    open_interest=int(float(row["open_interest"])), volume=int(float(row["volume"])),
                    delta=_float(row.get("delta")),
                    ex_dividend_date=_date(row.get("ex_dividend_date")),
                    earnings_date=_date(row.get("earnings_date")),
                )
            except (ValueError, TypeError) as e:
                warnings.append(f"row {n}: skipped ({e})")
                continue
            if call.spot <= 0 or call.strike <= 0 or call.bid < 0 or call.ask < call.bid:
                warnings.append(f"row {n}: skipped (bad price fields)")
                continue
            if call.delta is None and call.iv <= 0:
                warnings.append(f"row {n}: skipped (no delta and no usable iv)")
                continue
            calls.append(call)
    return calls, warnings
