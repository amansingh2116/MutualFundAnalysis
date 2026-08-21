from django.test import SimpleTestCase
from apps.benchmarks.metric_providers import (
    METRIC_CATALOGUE,
    FRED_KEYS,
    VALUATION_KEYS,
    NSE_SENTIMENT_KEYS,
    TECHNICAL_KEYS,
    get_all_metric_values,
)
from apps.benchmarks.api_views import CATEGORY_ORDER, CATEGORY_LABELS


class MarketMetricsCatalogueTest(SimpleTestCase):
    def test_catalogue_size_and_keys(self):
        """Ensure all 33 required market metrics are present in the catalogue."""
        self.assertEqual(len(METRIC_CATALOGUE), 33)

        expected_valuation = {"nifty_pe", "nifty_pb", "nifty_dy", "earnings_yield_gap", "buffett_india"}
        self.assertEqual(VALUATION_KEYS, expected_valuation)
        for k in expected_valuation:
            self.assertIn(k, METRIC_CATALOGUE)
            self.assertEqual(METRIC_CATALOGUE[k]["category"], "valuation")

        expected_sentiment = {"nifty_pcr", "fii_net", "adv_dec", "sip_inflows"}
        self.assertEqual(NSE_SENTIMENT_KEYS, expected_sentiment)
        for k in expected_sentiment:
            self.assertIn(k, METRIC_CATALOGUE)
            self.assertEqual(METRIC_CATALOGUE[k]["category"], "sentiment")

    def test_repo_rate_label_fixed(self):
        """Ensure repo_rate is accurately labeled as India 10Y Yield."""
        self.assertEqual(METRIC_CATALOGUE["repo_rate"]["label"], "India 10Y Yield")
        self.assertIn("10-Year", METRIC_CATALOGUE["repo_rate"]["tooltip_what"])

    def test_all_metrics_structure(self):
        """Ensure get_all_metric_values returns valid structures for all 33 metrics."""
        results = get_all_metric_values()
        self.assertEqual(len(results), 33)
        for k, v in results.items():
            self.assertIn("label", v, f"Missing label for {k}")
            self.assertIn("category", v, f"Missing category for {k}")
            self.assertIn("unit", v, f"Missing unit for {k}")
            self.assertIn("stale", v, f"Missing stale flag for {k}")
            self.assertIn(v["category"], CATEGORY_ORDER, f"Unknown category {v['category']} for {k}")
