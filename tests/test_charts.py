"""Chart tests: every SVG is generated and is valid XML; payoff, flag and heatmap data are checked."""

import os
import unittest
import xml.etree.ElementTree as ET
from datetime import date

from ccscreen import Filters, Params, analyze, load_chain, screen
from ccscreen import charts as C

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(HERE, "data", "sample_chain.csv")
ASOF = date(2026, 10, 14)


def _results():
    calls, _ = load_chain(SAMPLE)
    p = Params(asof=ASOF)
    res = screen(calls, p, Filters())
    allr = [analyze(c, p) for c in calls if (c.expiry - ASOF).days > 0]
    return res, allr


def _parse(svg):
    root = ET.fromstring(svg)  # raises if not well-formed XML
    return root, root.tag.split("}")[-1]


class SvgValidityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res, cls.allr = _results()
        cls.top = cls.res[0]
        cls.sym = cls.top.call.underlying

    def test_every_chart_is_valid_svg_in_light_and_dark(self):
        makers = [
            lambda d: C.yield_vs_delta_svg(self.res, "t", "s", d),
            lambda d: C.top_candidates_svg(self.res, 10, "t", "s", d),
            lambda d: C.payoff_svg(self.top, "t", "s", d),
            lambda d: C.heatmap_svg(self.allr, self.sym, "t", "s", d),
            lambda d: C.flag_counts_svg(self.res, "t", "s", d),
            lambda d: C.terminal_svg(["$ cmd", "line two"], "t", d),
        ]
        for make in makers:
            for dark in (False, True):
                _, tag = _parse(make(dark))
                self.assertEqual(tag, "svg")

    def test_banner_is_1200_by_240(self):
        for dark in (False, True):
            root, _ = _parse(C.banner_svg("Covered Call Screener", "tagline", "note", dark))
            self.assertEqual(root.get("viewBox"), "0 0 1200 240")


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res, cls.allr = _results()
        cls.top = cls.res[0]

    def test_payoff_at_strike_is_premium_plus_gain_to_strike(self):
        xs, cov, _ = C.payoff_points(self.top)
        k, s0, prem = self.top.call.strike, self.top.call.spot, self.top.premium
        i = min(range(len(xs)), key=lambda j: abs(xs[j] - k))
        # at the grid point nearest the strike, covered = prem + min(S, K) - S0
        self.assertAlmostEqual(cov[i], prem + min(xs[i], k) - s0, places=9)
        # the cap: above the strike the payoff is flat at the maximum gain
        above = [c for x, c in zip(xs, cov) if x > k]
        self.assertTrue(all(abs(c - (prem + k - s0)) < 1e-9 for c in above))
        # the if-called return matches the metrics module
        self.assertAlmostEqual((prem + k - s0) / s0, self.top.if_called_return, places=9)

    def test_payoff_crosses_zero_at_breakeven(self):
        xs, cov, _ = C.payoff_points(self.top, lo=self.top.breakeven - 1, hi=self.top.breakeven + 1, n=201)
        for x, c in zip(xs, cov):
            if x < self.top.breakeven - 0.01:
                self.assertLess(c, 0)
            if x > self.top.breakeven + 0.01 and x < self.top.call.strike:
                self.assertGreater(c, 0)

    def test_flag_counts_match_results(self):
        counts = C.flag_counts(self.res)
        self.assertEqual(set(counts), set(C.FLAGS))
        for f in C.FLAGS:
            self.assertEqual(counts[f], sum(1 for r in self.res if f in r.flags))

    def test_heatmap_cells_match_window(self):
        strikes, expiries, cells = C.heatmap_grid(self.allr, self.top.call.underlying)
        self.assertEqual(len(cells), sum(1 for r in self.allr
                                         if r.call.underlying == self.top.call.underlying
                                         and r.call.bid > 0 and 0.10 <= r.delta <= 0.50 and r.dte > 0))
        self.assertTrue(all(0.10 <= r.delta <= 0.50 for r in self.allr
                            if (r.call.expiry, r.call.strike) in cells and r.call.underlying == self.top.call.underlying))
        self.assertEqual(strikes, sorted(strikes))
        self.assertEqual(expiries, sorted(expiries))


class WorkedExampleTests(unittest.TestCase):
    """The README worked example quotes these values; they must stay in line with the code."""

    def test_worked_example_matches_readme(self):
        import figures
        w = figures.worked_example()
        r = w["result"]
        self.assertEqual(r.dte, 23)
        self.assertAlmostEqual(r.mid, 1.96)
        self.assertAlmostEqual(r.static_return, 0.0204, places=4)
        self.assertAlmostEqual(r.annualized_yield, 0.324, places=3)
        self.assertAlmostEqual(r.if_called_return, 0.0870, places=4)
        self.assertAlmostEqual(r.breakeven, 94.14)
        self.assertAlmostEqual(r.delta, 0.306, places=3)
        self.assertAlmostEqual(w["nd2"], 0.2685, places=4)
        self.assertAlmostEqual(r.model_gap, 0.0040, places=4)


if __name__ == "__main__":
    unittest.main()
