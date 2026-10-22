import csv
import math
import os
import tempfile
import unittest
from datetime import date

from ccscreen import (
    Call,
    Filters,
    Params,
    analyze,
    call_delta,
    call_itm_prob,
    call_price,
    in_window,
    load_chain,
    norm_cdf,
    screen,
    write_csv,
)

ASOF = date(2026, 1, 2)


def make_call(**kw):
    base = {"underlying": "TST", "spot": 100.0, "expiry": date(2026, 2, 6), "strike": 105.0, "bid": 1.95,
            "ask": 2.05, "iv": 0.30, "open_interest": 500, "volume": 50}
    base.update(kw)
    return Call(**base)


class TestBlackScholes(unittest.TestCase):
    def test_itm_prob_textbook_and_below_delta(self):
        # S=K=100, r=5%, vol=20%, T=1: d2 = 0.15, N(0.15) = 0.5596
        self.assertAlmostEqual(call_itm_prob(100, 100, 1, 0.05, 0.2), 0.5596, places=3)
        self.assertLess(call_itm_prob(100, 105, 30 / 365, 0.04, 0.3), call_delta(100, 105, 30 / 365, 0.04, 0.3))

    def test_analyze_reports_prob_assigned_and_nan_without_iv(self):
        r = analyze(make_call(), Params(asof=ASOF))
        self.assertTrue(0 < r.prob_assigned < r.delta)
        r2 = analyze(make_call(iv=0.0, delta=0.25), Params(asof=ASOF))
        self.assertTrue(math.isnan(r2.prob_assigned))

    def test_norm_cdf(self):
        self.assertAlmostEqual(norm_cdf(0), 0.5)
        self.assertAlmostEqual(norm_cdf(1.96), 0.975, places=3)
        self.assertAlmostEqual(norm_cdf(-1.0) + norm_cdf(1.0), 1.0)

    def test_textbook_values(self):
        # S=K=100, r=5%, vol=20%, T=1: price 10.4506, delta N(0.35) = 0.6368
        self.assertAlmostEqual(call_price(100, 100, 1, 0.05, 0.2), 10.4506, places=3)
        self.assertAlmostEqual(call_delta(100, 100, 1, 0.05, 0.2), 0.6368, places=3)

    def test_atm_delta_slightly_above_half(self):
        d = call_delta(100, 100, 30 / 365, 0.04, 0.30)
        self.assertTrue(0.50 < d < 0.56, d)       # drift and vol^2/2 push d1 above zero

    def test_delta_with_zero_rate_zero_vol_term_is_near_half(self):
        self.assertAlmostEqual(call_delta(100, 100, 30 / 365, 0.0, 0.01), 0.5, delta=0.01)

    def test_delta_decreases_with_strike_and_in_unit_interval(self):
        ds = [call_delta(100, k, 30 / 365, 0.04, 0.3) for k in range(80, 130, 5)]
        self.assertEqual(ds, sorted(ds, reverse=True))
        self.assertTrue(all(0 < d < 1 for d in ds))

    def test_dividend_yield_lowers_delta(self):
        self.assertLess(call_delta(100, 100, 0.5, 0.04, 0.3, 0.03), call_delta(100, 100, 0.5, 0.04, 0.3))

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            call_delta(100, 100, 0, 0.04, 0.3)


class TestMetrics(unittest.TestCase):
    def test_core_math(self):
        r = analyze(make_call(), Params(asof=ASOF))
        self.assertEqual(r.dte, 35)
        self.assertAlmostEqual(r.mid, 2.00)
        self.assertAlmostEqual(r.spread_pct, 0.05)
        self.assertAlmostEqual(r.static_return, 0.02)
        self.assertAlmostEqual(r.annualized_yield, 0.02 * 365 / 35)
        self.assertAlmostEqual(r.if_called_return, 0.07)            # (2 + 5) / 100
        self.assertAlmostEqual(r.if_called_annualized, 0.07 * 365 / 35)
        self.assertAlmostEqual(r.breakeven, 98.0)
        self.assertAlmostEqual(r.downside_cushion, 0.02)
        self.assertAlmostEqual(r.upside_to_strike, 0.05)

    def test_itm_if_called_return(self):
        r = analyze(make_call(strike=95.0, bid=6.4, ask=6.6), Params(asof=ASOF))
        self.assertAlmostEqual(r.if_called_return, (6.5 - 5.0) / 100)

    def test_bid_basis(self):
        r = analyze(make_call(), Params(asof=ASOF, premium_basis="bid"))
        self.assertAlmostEqual(r.static_return, 0.0195)

    def test_delta_source(self):
        self.assertEqual(analyze(make_call(), Params(asof=ASOF)).delta_source, "model")
        r = analyze(make_call(delta=0.27), Params(asof=ASOF))
        self.assertEqual((r.delta, r.delta_source), (0.27, "csv"))

    def test_model_delta_uses_rate(self):
        lo = analyze(make_call(), Params(asof=ASOF, rate=0.0)).delta
        hi = analyze(make_call(), Params(asof=ASOF, rate=0.08)).delta
        self.assertGreater(hi, lo)
        expected = call_delta(100, 105, 35 / 365, 0.0, 0.30)
        self.assertAlmostEqual(lo, expected)


class TestFlags(unittest.TestCase):
    def flags(self, **kw):
        return analyze(make_call(**kw), Params(asof=ASOF)).flags

    def test_clean(self):
        self.assertEqual(self.flags(), [])

    def test_earnings_before_expiry(self):
        self.assertEqual(self.flags(earnings_date=date(2026, 1, 20)), ["EARNINGS"])

    def test_earnings_after_expiry_or_past_not_flagged(self):
        self.assertEqual(self.flags(earnings_date=date(2026, 3, 1)), [])
        self.assertEqual(self.flags(earnings_date=date(2025, 12, 1)), [])

    def test_expiry_day_event_counts(self):
        self.assertTrue(in_window(date(2026, 2, 6), ASOF, date(2026, 2, 6)))
        self.assertFalse(in_window(ASOF, ASOF, date(2026, 2, 6)))

    def test_earnings_boundaries(self):
        self.assertEqual(self.flags(earnings_date=date(2026, 1, 1)), [])      # day before as-of
        self.assertEqual(self.flags(earnings_date=ASOF), ["EARNINGS"])        # as-of day
        self.assertEqual(self.flags(earnings_date=date(2026, 2, 6)), ["EARNINGS"])  # expiry day
        self.assertEqual(self.flags(earnings_date=date(2026, 2, 7)), [])      # day after expiry

    def test_ex_dividend(self):
        self.assertEqual(self.flags(ex_dividend_date=date(2026, 1, 15)), ["EX_DIV"])

    def test_wide_spread(self):
        self.assertEqual(self.flags(bid=1.5, ask=2.5), ["WIDE_SPREAD"])   # 50% of mid

    def test_low_oi(self):
        self.assertEqual(self.flags(open_interest=40), ["LOW_OI"])

    def test_multiple(self):
        f = self.flags(open_interest=1, bid=1.0, ask=3.0, earnings_date=date(2026, 1, 10))
        self.assertEqual(f, ["EARNINGS", "WIDE_SPREAD", "LOW_OI"])


class TestScreen(unittest.TestCase):
    def setUp(self):
        self.p = Params(asof=ASOF)
        # delta supplied so filters are deterministic
        self.ok = make_call(delta=0.25)

    def run_screen(self, calls, **fk):
        return screen(calls, self.p, Filters(**fk))

    def test_passes_default(self):
        self.assertEqual(len(self.run_screen([self.ok])), 1)

    def test_dte_filter(self):
        short = make_call(delta=0.25, expiry=date(2026, 1, 16))   # 14 DTE
        long_ = make_call(delta=0.25, expiry=date(2026, 3, 20))   # 77 DTE
        self.assertEqual(self.run_screen([short, long_]), [])
        self.assertEqual(len(self.run_screen([short], min_dte=10)), 1)

    def test_delta_filter(self):
        lo, hi = make_call(delta=0.05), make_call(delta=0.60)
        self.assertEqual(self.run_screen([lo, hi]), [])
        self.assertEqual(len(self.run_screen([lo, hi], min_delta=0.0, max_delta=1.0)), 2)

    def test_delta_bounds_inclusive(self):
        self.assertEqual(len(self.run_screen([make_call(delta=0.15), make_call(delta=0.35)])), 2)

    def test_zero_bid_excluded(self):
        self.assertEqual(self.run_screen([make_call(delta=0.25, bid=0.0, ask=0.05)]), [])

    def test_exclude_flagged(self):
        bad = make_call(delta=0.25, open_interest=5)
        self.assertEqual(len(self.run_screen([self.ok, bad])), 2)
        self.assertEqual(len(self.run_screen([self.ok, bad], exclude_flagged=True)), 1)

    def test_rank_clean_first_then_yield(self):
        # iv=0 with a vendor delta: no model price, so only the flags under test are in play
        rich_flagged = make_call(delta=0.25, bid=4.9, ask=5.1, open_interest=5, iv=0.0)
        clean_low = make_call(delta=0.25, iv=0.0)
        clean_high = make_call(delta=0.25, bid=2.9, ask=3.1, iv=0.0)
        out = self.run_screen([rich_flagged, clean_low, clean_high])
        self.assertEqual([r.mid for r in out], [3.0, 2.0, 5.0])

    def test_model_delta_filter(self):
        # 5% OTM, 30% vol, 35 DTE: model delta should land inside 0.15-0.35
        r = self.run_screen([make_call()])
        self.assertEqual(len(r), 1)
        self.assertTrue(0.15 <= r[0].delta <= 0.35)


class TestIO(unittest.TestCase):
    def write(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(text)
        self.addCleanup(os.unlink, f.name)
        return f.name

    HDR = "underlying,spot,expiry,strike,bid,ask,iv,open_interest,volume,delta,ex_dividend_date,earnings_date\n"

    def test_load_and_skip_bad_rows(self):
        path = self.write(self.HDR +
                          "abc,100,2026-02-06,105,1.9,2.1,0.3,500,50,,,2026-01-20\n"
                          "abc,100,2026-02-06,110,x,2.1,0.3,500,50,,,\n"
                          "abc,100,2026-02-06,115,0.5,0.6,,500,50,,,\n")
        calls, warns = load_chain(path)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(warns), 2)
        self.assertEqual(calls[0].underlying, "ABC")
        self.assertEqual(calls[0].earnings_date, date(2026, 1, 20))
        self.assertIsNone(calls[0].delta)

    def test_non_finite_numbers_are_skipped(self):
        path = self.write(self.HDR +
                          "abc,100,2026-02-06,105,nan,2.1,0.3,500,50,,,\n"
                          "abc,100,2026-02-06,105,1.9,inf,0.3,500,50,,,\n"
                          "abc,100,2026-02-06,105,1.9,2.1,nan,500,50,,,\n"
                          "abc,100,2026-02-06,105,1.9,2.1,0.3,500,50,nan,,\n"
                          "abc,100,2026-02-06,105,1.9,2.1,0.3,500,50,,,\n")
        calls, warns = load_chain(path)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(warns), 4)

    def test_percent_style_iv_is_skipped(self):
        path = self.write(self.HDR +
                          "abc,100,2026-02-06,105,1.9,2.1,32,500,50,,,\n"
                          "abc,100,2026-02-06,105,1.9,2.1,0.32,500,50,,,\n")
        calls, warns = load_chain(path)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(warns), 1)
        self.assertIn("percent", warns[0])

    def test_vendor_delta_outside_zero_one_is_skipped(self):
        path = self.write(self.HDR +
                          "abc,100,2026-02-06,105,1.9,2.1,0.3,500,50,25,,\n"
                          "abc,100,2026-02-06,105,1.9,2.1,0.3,500,50,-0.2,,\n"
                          "abc,100,2026-02-06,105,1.9,2.1,0.3,500,50,0.25,,\n")
        calls, warns = load_chain(path)
        self.assertEqual([c.delta for c in calls], [0.25])
        self.assertEqual(len(warns), 2)

    def test_missing_column(self):
        with self.assertRaises(ValueError):
            load_chain(self.write("underlying,spot\nA,1\n"))

    def test_optional_columns_may_be_absent(self):
        path = self.write("underlying,spot,expiry,strike,bid,ask,iv,open_interest,volume\n"
                          "A,100,2026-02-06,105,1.9,2.1,0.3,500,50\n")
        self.assertEqual(len(load_chain(path)[0]), 1)

    def test_sample_chain_loads_and_screens(self):
        root = os.path.join(os.path.dirname(__file__), "..", "data", "sample_chain.csv")
        calls, warns = load_chain(root)
        self.assertEqual(warns, [])
        self.assertGreater(len(calls), 100)
        res = screen(calls, Params(asof=date(2026, 10, 14)), Filters())
        self.assertGreater(len(res), 5)
        self.assertTrue(any(r.flags for r in res) and any(not r.flags for r in res))

    def test_write_csv_roundtrip(self):
        res = screen([make_call(delta=0.25)], Params(asof=ASOF), Filters())
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            pass
        self.addCleanup(os.unlink, out.name)
        write_csv(res, out.name)
        with open(out.name, newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(float(rows[0]["annualized_yield"]), 0.02 * 365 / 35, places=4)


class TestModelCheck(unittest.TestCase):
    """The model price is a data-quality check on a row, not a pricing signal."""

    def consistent_call(self, **kw):
        dte = (date(2026, 2, 6) - ASOF).days
        fair = call_price(100.0, 105.0, dte / 365.0, 0.04, 0.30)
        return make_call(bid=round(fair - 0.05, 2), ask=round(fair + 0.05, 2), **kw)

    def test_hull_textbook_call_price(self):
        # Hull: S=42, K=40, r=10%, vol=20%, T=0.5 -> 4.76
        self.assertAlmostEqual(call_price(42, 40, 0.5, 0.10, 0.20), 4.76, places=2)

    def test_consistent_quote_has_small_gap_and_no_flag(self):
        r = analyze(self.consistent_call(), Params(asof=ASOF))
        self.assertLess(abs(r.model_gap), 0.02)
        self.assertNotIn("IV_MISMATCH", r.flags)

    def test_inconsistent_quote_is_flagged(self):
        # A $3.00 mid against a 30% IV that implies about $1.93
        r = analyze(make_call(bid=2.95, ask=3.05), Params(asof=ASOF))
        self.assertGreater(r.model_gap, 1.0)
        self.assertIn("IV_MISMATCH", r.flags)

    def test_penny_rounding_on_cheap_options_is_not_flagged(self):
        # Far OTM: model ~0.01 vs mid 0.04 is a large percentage but only a few cents
        r = analyze(make_call(strike=135.0, bid=0.03, ask=0.05, open_interest=900), Params(asof=ASOF))
        self.assertGreater(abs(r.model_gap) / r.mid, 0.10)
        self.assertLess(abs(r.model_gap), 0.05)
        self.assertNotIn("IV_MISMATCH", r.flags)

    def test_no_iv_means_no_model_check(self):
        r = analyze(make_call(delta=0.25, iv=0.0), Params(asof=ASOF))
        self.assertTrue(math.isnan(r.model_price) and math.isnan(r.model_gap))
        self.assertNotIn("IV_MISMATCH", r.flags)

    def test_threshold_is_configurable(self):
        c = make_call(bid=2.35, ask=2.45)            # mid 2.40 vs model 1.93: 20% gap
        self.assertIn("IV_MISMATCH", analyze(c, Params(asof=ASOF)).flags)
        self.assertNotIn("IV_MISMATCH", analyze(c, Params(asof=ASOF, max_model_gap_pct=0.30)).flags)

    def test_bundled_sample_has_no_mismatches(self):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_chain.csv")
        calls, _ = load_chain(root)
        res = screen(calls, Params(asof=date(2026, 10, 14)), Filters(min_dte=0, max_dte=400, min_delta=0, max_delta=1))
        self.assertTrue(len(res) > 100)
        self.assertFalse(any("IV_MISMATCH" in r.flags for r in res))


class TestExpiredRows(unittest.TestCase):
    def test_analyze_raises_on_expired_or_same_day(self):
        for expiry in (date(2025, 12, 1), ASOF):
            for delta in (None, 0.25):
                with self.subTest(expiry=expiry, delta=delta), self.assertRaises(ValueError):
                    analyze(make_call(expiry=expiry, delta=delta), Params(asof=ASOF))

    def test_expired_and_same_day_calls_are_skipped_not_fatal(self):
        # No vendor delta, so model delta would raise for T <= 0 if the row reached analyze()
        expired = make_call(expiry=date(2025, 12, 1))
        same_day = make_call(expiry=ASOF)
        live = make_call()
        out = screen([expired, same_day, live], Params(asof=ASOF), Filters())
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].call.expiry, live.expiry)

    def test_csv_includes_model_columns(self):
        res = screen([make_call()], Params(asof=ASOF), Filters())
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out:
            pass
        self.addCleanup(os.unlink, out.name)
        write_csv(res, out.name)
        with open(out.name, newline="") as fh:
            row = next(csv.DictReader(fh))
        self.assertIn("model_price", row)
        self.assertAlmostEqual(float(row["model_gap"]), res[0].model_gap, places=3)


class TestEarlyAssign(unittest.TestCase):
    # ITM 95 strike on a 100 spot: intrinsic 5. iv=0 with a vendor delta keeps IV_MISMATCH out of the way.
    EX = date(2026, 1, 20)  # inside the window (ASOF 2026-01-02 .. expiry 2026-02-06)

    def flags(self, **kw):
        base = {"strike": 95.0, "bid": 5.4, "ask": 5.6, "delta": 0.9, "iv": 0.0, "ex_dividend_date": self.EX,
                "dividend": 1.0}
        base.update(kw)
        return analyze(make_call(**base), Params(asof=ASOF)).flags

    def test_fires_when_itm_extrinsic_below_dividend(self):
        # mid 5.5, extrinsic 0.5 < dividend 1.0
        self.assertIn("EARLY_ASSIGN", self.flags())

    def test_not_when_otm(self):
        self.assertNotIn("EARLY_ASSIGN", self.flags(strike=105.0, bid=1.9, ask=2.1))

    def test_not_when_extrinsic_at_or_above_dividend(self):
        self.assertNotIn("EARLY_ASSIGN", self.flags(dividend=0.5))   # extrinsic 0.5 == dividend
        self.assertNotIn("EARLY_ASSIGN", self.flags(dividend=0.4))

    def test_not_when_ex_div_outside_window(self):
        self.assertNotIn("EARLY_ASSIGN", self.flags(ex_dividend_date=date(2025, 12, 20)))
        self.assertNotIn("EARLY_ASSIGN", self.flags(ex_dividend_date=date(2026, 3, 1)))

    def test_not_when_no_dividend_or_zero(self):
        self.assertNotIn("EARLY_ASSIGN", self.flags(dividend=None))
        self.assertNotIn("EARLY_ASSIGN", self.flags(dividend=0.0))


class TestLiquidityFlags(unittest.TestCase):
    def flags(self, params, **kw):
        return analyze(make_call(**kw), params).flags

    def test_off_by_default(self):
        self.assertNotIn("LOW_VOLUME", self.flags(Params(asof=ASOF), volume=0))
        self.assertNotIn("THIN_PREMIUM", self.flags(Params(asof=ASOF), bid=0.01, ask=0.02))

    def test_low_volume_only_when_threshold_set(self):
        self.assertEqual(self.flags(Params(asof=ASOF, min_volume=100), volume=50), ["LOW_VOLUME"])
        self.assertNotIn("LOW_VOLUME", self.flags(Params(asof=ASOF, min_volume=50), volume=50))

    def test_thin_premium_only_when_threshold_set(self):
        # mid 2.0 per share
        self.assertEqual(self.flags(Params(asof=ASOF, min_premium=2.5)), ["THIN_PREMIUM"])
        self.assertNotIn("THIN_PREMIUM", self.flags(Params(asof=ASOF, min_premium=1.5)))


class TestDividendColumnIO(unittest.TestCase):
    HDR = ("underlying,spot,expiry,strike,bid,ask,iv,open_interest,volume,delta,ex_dividend_date,"
           "earnings_date,dividend\n")

    def write(self, text):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(text)
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_negative_iv_skipped_zero_iv_with_delta_kept(self):
        path = self.write(self.HDR +
                          "abc,100,2026-02-06,105,1.9,2.1,-0.3,500,50,0.25,,,\n"
                          "abc,100,2026-02-06,110,1.9,2.1,0,500,50,0.25,,,\n")
        calls, warns = load_chain(path)
        self.assertEqual([c.strike for c in calls], [110.0])
        self.assertEqual(len(warns), 1)
        self.assertIn("negative iv", warns[0])

    def test_parses_dividend_and_skips_negative(self):
        path = self.write(self.HDR +
                          "abc,100,2026-02-06,95,5.4,5.6,0.3,500,50,0.9,2026-01-20,,1.0\n"
                          "abc,100,2026-02-06,105,1.9,2.1,0.3,500,50,,,,\n"
                          "abc,100,2026-02-06,110,1.9,2.1,0.3,500,50,,,,-0.2\n")
        calls, warns = load_chain(path)
        self.assertEqual([c.dividend for c in calls], [1.0, None])
        self.assertEqual(len(warns), 1)
        self.assertIn("negative dividend", warns[0])


class TestCliHeader(unittest.TestCase):
    def test_table_has_assignment_probability_column(self):
        from cli import fmt_table
        res = screen([make_call(delta=0.25)], Params(asof=ASOF), Filters())
        header = fmt_table(res, 5).splitlines()[0]
        self.assertIn("P(asn)%", header)
        self.assertIn("Cush%", header)


class TestLoaderRobustness(unittest.TestCase):
    def test_inf_open_interest_and_short_row_are_skipped(self):
        hdr = "underlying,spot,expiry,strike,bid,ask,iv,open_interest,volume\n"
        body = "T,100,2026-02-06,105,1,1.1,0.3,inf,5\nT,100,2026-02-06,105,1,1.1,0.3,10,5\nT,100\n"
        with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(__file__))) as d:
            path = os.path.join(d, "c.csv")
            with open(path, "w") as f:
                f.write(hdr + body)
            calls, warnings = load_chain(path)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(warnings), 2)


class TestPresetAndEarnings(unittest.TestCase):
    def test_weekly_preset_window_and_override(self):
        from ccscreen import preset_filters
        f = preset_filters("weekly")
        self.assertEqual((f.min_dte, f.max_dte, f.min_delta, f.max_delta), (3, 10, 0.15, 0.35))
        self.assertEqual(preset_filters("weekly", max_dte=14).max_dte, 14)
        self.assertEqual((Filters().min_dte, Filters().max_dte), (20, 45))   # no preset: unchanged

    def test_exclude_earnings_drops_only_earnings_calls(self):
        calls = [make_call(strike=105.0, earnings_date=date(2026, 1, 20)), make_call(strike=106.0, delta=0.25)]
        calls[0].delta = 0.25
        p = Params(asof=ASOF)
        f = Filters(exclude_earnings=True)
        kept = screen(calls, p, f)
        self.assertEqual([r.call.strike for r in kept], [106.0])
        self.assertEqual(len(screen(calls, p, Filters())), 2)       # default: flagged, not dropped
        out = screen([make_call(delta=0.25, earnings_date=date(2026, 3, 1))], p, f)
        self.assertEqual(len(out), 1)                                # earnings after expiry is kept


ROLL_CSV = """underlying,spot,expiry,strike,bid,ask,iv,open_interest,volume,delta,ex_dividend_date,earnings_date,dividend
TST,102,2026-01-09,100,2.30,2.50,0.3,500,50,0.7,2026-01-07,,0.80
TST,102,2026-01-16,100,3.40,3.60,0.3,500,50,0.65,,,
TST,102,2026-01-16,105,1.60,1.80,0.3,500,50,0.4,,,
TST,102,2026-01-23,105,2.20,2.40,0.3,500,50,0.4,,,
TST,102,2026-01-23,110,0.00,0.10,0.3,500,50,0.2,,,
TST,102,2026-01-16,95,6.00,6.20,0.3,500,50,0.8,,,
"""


class TestRoll(unittest.TestCase):
    def report(self, **kw):
        from ccscreen import Position, roll_check
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.csv")
            with open(path, "w") as f:
                f.write(kw.pop("csv", ROLL_CSV))
            calls, _ = load_chain(path)
        pos = Position("TST", kw.get("strike", 100.0), date(2026, 1, 9), 1.5, 2)
        return roll_check(calls, pos, date(2026, 1, 5))

    def test_buyback_intrinsic_extrinsic_and_signals(self):
        r = self.report()
        self.assertEqual((r.buyback, r.intrinsic), (2.50, 2.0))
        self.assertAlmostEqual(r.extrinsic, 0.50)
        text = " ".join(r.signals)
        self.assertIn("ITM by 2.00", text)
        self.assertIn("BELOW dividend 0.80", text)       # extrinsic 0.50 < 0.80 before expiry
        self.assertEqual(r.dte, 4)

    def test_candidates_ranked_and_filtered(self):
        r = self.report()
        got = [(c.call.expiry.isoformat(), c.call.strike) for c in r.ranked]
        self.assertNotIn(("2026-01-16", 95.0), got)       # lower strike excluded
        self.assertEqual(got[0], ("2026-01-16", 100.0))   # 0.90 net over 7 days beats the rest
        top = r.ranked[0]
        self.assertAlmostEqual(top.net_per_share, 3.40 - 2.50)
        self.assertAlmostEqual(top.if_called_return, (1.5 + 0.9 + 100 - 102) / 102)

    def test_missing_quote_is_unknown_not_ranked(self):
        r = self.report()
        self.assertEqual([c.call.strike for c in r.unknown], [110.0])   # bid 0
        self.assertNotIn(110.0, [c.call.strike for c in r.ranked])

    def test_open_call_missing_from_chain_makes_everything_unknown(self):
        r = self.report(strike=101.0)
        self.assertIsNone(r.buyback)
        self.assertEqual(r.ranked, [])
        self.assertTrue(r.unknown)

    def test_cli_roll_labels_output(self):
        import contextlib
        import io
        from cli import main
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.csv")
            with open(path, "w") as f:
                f.write(ROLL_CSV)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["roll", path, "--asof", "2026-01-05", "--underlying", "tst", "--strike", "100",
                           "--expiry", "2026-01-09", "--premium", "1.5", "--contracts", "2"])
        self.assertEqual(rc, 0)
        self.assertIn("Research estimate, not advice", buf.getvalue())
        self.assertIn("UNKNOWN", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
