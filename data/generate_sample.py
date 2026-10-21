#!/usr/bin/env python3
"""Generate data/sample_chain.csv: a SYNTHETIC option chain (no real market data).

Tickers SYNA..SYND are fictional. Prices come from Black-Scholes with a made-up
smile, then bid/ask spreads and open interest are simulated (wider and thinner
away from the money). Seeded, so output is reproducible.
Run from the project root:  python3 data/generate_sample.py
"""

import csv
import math
import os
import random
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ccscreen.bs import call_price, call_delta  # noqa: E402

ASOF = date(2026, 10, 14)
RATE = 0.0425
EXPIRIES = [date(2026, 10, 23), date(2026, 11, 6), date(2026, 11, 20), date(2026, 12, 4), date(2026, 12, 18)]
# symbol, spot, strike step, base iv, base OI, earnings, ex-div, include vendor delta?
UNDERLYINGS = [
    ("SYNA", 48.20, 1.0, 0.31, 3000, None, date(2026, 12, 10), True),
    ("SYNB", 187.35, 5.0, 0.36, 5000, date(2026, 11, 5), None, False),
    ("SYNC", 342.80, 10.0, 0.23, 1500, None, date(2026, 11, 12), True),
    ("SYND", 96.10, 2.5, 0.44, 800, date(2026, 12, 2), None, False),
]


def main():
    rng = random.Random(42)
    rows = []
    for sym, spot, step, base_iv, base_oi, earn, exdiv, vendor_delta in UNDERLYINGS:
        atm = round(spot / step) * step
        for exp in EXPIRIES:
            dte = (exp - ASOF).days
            t = dte / 365.0
            for k in range(-3, 9):
                strike = atm + k * step
                m = math.log(strike / spot)
                iv = base_iv * (1 - 0.9 * m + 4.0 * m * m) * (1 + 0.04 * math.sqrt(30.0 / dte))
                if earn and exp >= earn:
                    iv *= 1.12
                iv = max(0.08, iv * rng.uniform(0.985, 1.015))
                theo = call_price(spot, strike, t, RATE, iv)
                liq = math.exp(-(m / 0.09) ** 2) * (0.6 + 0.4 * min(1.0, 45.0 / dte))
                oi = int(base_oi * liq * rng.uniform(0.5, 1.5))
                vol = int(oi * rng.uniform(0.02, 0.25))
                half = 0.01 + theo * 0.007 * (1 + 7 * (1 - liq))
                bid = max(0.0, round(theo - half, 2))
                ask = round(max(theo + half, bid + 0.01), 2)
                if ask < 0.03:
                    continue
                d = round(call_delta(spot, strike, t, RATE, iv), 3) if vendor_delta else ""
                rows.append([sym, f"{spot:.2f}", exp.isoformat(), f"{strike:g}", f"{bid:.2f}", f"{ask:.2f}",
                             f"{iv:.4f}", oi, vol, d,
                             exdiv.isoformat() if exdiv else "", earn.isoformat() if earn else ""])
    path = os.path.join(os.path.dirname(__file__), "sample_chain.csv")
    with open(path, "w", newline="") as f:
        f.write("# SYNTHETIC SAMPLE DATA: fictional tickers, simulated prices, not market data. As of 2026-10-14.\n")
        w = csv.writer(f)
        w.writerow(["underlying", "spot", "expiry", "strike", "bid", "ask", "iv", "open_interest",
                    "volume", "delta", "ex_dividend_date", "earnings_date"])
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    main()
