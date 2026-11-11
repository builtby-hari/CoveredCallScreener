"""Black-Scholes helpers using only the standard library."""

import math


def norm_cdf(x):
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def d1_d2(spot, strike, t_years, rate, vol, div_yield=0.0):
    """Black-Scholes d1 and d2 (continuous dividend yield q)."""
    if spot <= 0 or strike <= 0 or t_years <= 0 or vol <= 0:
        raise ValueError("spot, strike, t_years and vol must be positive")
    vt = vol * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * vol * vol) * t_years) / vt
    return d1, d1 - vt


def call_delta(spot, strike, t_years, rate, vol, div_yield=0.0):
    """European call delta: exp(-qT) * N(d1)."""
    d1, _ = d1_d2(spot, strike, t_years, rate, vol, div_yield)
    return math.exp(-div_yield * t_years) * norm_cdf(d1)


def call_price(spot, strike, t_years, rate, vol, div_yield=0.0):
    """European call price."""
    d1, d2 = d1_d2(spot, strike, t_years, rate, vol, div_yield)
    return (spot * math.exp(-div_yield * t_years) * norm_cdf(d1)
            - strike * math.exp(-rate * t_years) * norm_cdf(d2))


def call_itm_prob(spot, strike, t_years, rate, vol, div_yield=0.0):
    """Risk-neutral probability a European call finishes in the money: N(d2). Below delta (N(d1))."""
    _, d2 = d1_d2(spot, strike, t_years, rate, vol, div_yield)
    return norm_cdf(d2)
