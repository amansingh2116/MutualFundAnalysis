from datetime import date
from pathlib import Path

from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.analytics.models import RiskMetrics, RollingReturn, TrailingReturn
from apps.benchmarks.models import BenchmarkIndex, BenchmarkNAV
from apps.funds.models import FundScreenerSnapshot, NAVHistory, Scheme
from apps.funds.screener import classify_scheme, refresh_snapshot_for_scheme
from apps.funds.screener_reports import generate_top_screener_reports
from apps.funds.views import FundScreenerView


class ScreenerDerivationTests(TestCase):
    def make_scheme(self, code="100001", name="Axis Small Cap Fund Direct Growth"):
        return Scheme.objects.create(
            amfi_code=code,
            scheme_name=name,
            fund_house="Axis Mutual Fund",
            scheme_type="Open Ended",
            scheme_category="Equity Scheme - Small Cap Fund",
            plan="GROWTH",
            is_direct=True,
            is_active=True,
            aum_cr=1234,
            expense_ratio=0.45,
            nav_latest=150,
            nav_date=date(2026, 6, 14),
        )

    def test_classify_scheme_maps_common_categories(self):
        self.assertEqual(classify_scheme("", "Axis Small Cap Fund Direct Growth"), ("Equity", "Small Cap Fund"))
        self.assertEqual(classify_scheme("", "SBI Magnum Gilt Fund Direct Growth"), ("Debt", "Gilt Fund"))
        self.assertEqual(classify_scheme("", "HDFC Balanced Advantage Fund Direct Growth"), ("Hybrid", "Dynamic Asset Allocation or Balanced Advantage"))

    def test_refresh_snapshot_persists_derived_filter_fields(self):
        scheme = self.make_scheme()
        NAVHistory.objects.create(scheme=scheme, date=date(2023, 6, 14), nav=100)
        NAVHistory.objects.create(scheme=scheme, date=date(2026, 6, 14), nav=150)
        TrailingReturn.objects.create(scheme=scheme, period="3Y", years=3, cagr_pct=14.25, as_of=date(2026, 6, 14))
        RollingReturn.objects.create(
            scheme=scheme,
            window="3Y",
            window_days=756,
            mean_pct=13.1,
            as_of=date(2026, 6, 14),
        )
        RiskMetrics.objects.create(
            scheme=scheme,
            period="3Y",
            period_days=1096,
            std_dev_ann=18.4,
            as_of=date(2026, 6, 14),
        )

        snapshot = refresh_snapshot_for_scheme(scheme)

        self.assertEqual(snapshot.fund_house, "Axis")
        self.assertEqual(snapshot.category_group, "Equity")
        self.assertEqual(snapshot.scheme_sub_category, "Small Cap Fund")
        self.assertEqual(snapshot.plan_type, "Direct")
        self.assertEqual(snapshot.risk_label, "High")
        self.assertEqual(float(snapshot.cagr_3y_pct), 14.25)
        self.assertEqual(float(snapshot.rolling_return_3y_pct), 13.1)

    def test_screener_view_filters_by_category_and_range(self):
        scheme = self.make_scheme()
        other = self.make_scheme("100002", "Axis Liquid Fund Direct Growth")
        FundScreenerSnapshot.objects.create(
            scheme=scheme,
            fund_name=scheme.scheme_name,
            fund_house="Axis",
            category_group="Equity",
            scheme_sub_category="Small Cap Fund",
            plan_type="Direct",
            cagr_3y_pct=14,
            rolling_return_3y_pct=12,
            volatility_3y_pct=18,
        )
        FundScreenerSnapshot.objects.create(
            scheme=other,
            fund_name=other.scheme_name,
            fund_house="Axis",
            category_group="Debt",
            scheme_sub_category="Liquid Fund",
            plan_type="Direct",
            cagr_3y_pct=6,
            rolling_return_3y_pct=5,
            volatility_3y_pct=2,
        )

        request = RequestFactory().get("/funds/screener/", {"category": "Equity", "cagr_3y_min": "10"})
        view = FundScreenerView()
        view.setup(request)

        self.assertEqual(list(view.filtered_queryset()), [scheme.screener_snapshot])

    def test_generate_top_reports_writes_csv_and_html(self):
        scheme = self.make_scheme()
        NAVHistory.objects.create(scheme=scheme, date=date(2026, 6, 12), nav=100)
        NAVHistory.objects.create(scheme=scheme, date=date(2026, 6, 13), nav=105)
        NAVHistory.objects.create(scheme=scheme, date=date(2026, 6, 14), nav=110)
        benchmark = BenchmarkIndex.objects.create(name="NIFTY 50", yahoo_ticker="^NSEI")
        BenchmarkNAV.objects.create(index=benchmark, date=date(2026, 6, 12), close=10000)
        BenchmarkNAV.objects.create(index=benchmark, date=date(2026, 6, 14), close=10100)
        FundScreenerSnapshot.objects.create(
            scheme=scheme,
            fund_name=scheme.scheme_name,
            fund_house="Axis",
            category_group="Equity",
            scheme_sub_category="Small Cap Fund",
            plan_type="Direct",
            benchmark_name="NIFTY 50",
            cagr_3y_pct=14,
            rolling_return_3y_pct=12,
            volatility_3y_pct=18,
            data_as_of=date(2026, 6, 14),
        )

        output_dir = Path(settings.BASE_DIR) / "media" / "test_screener_reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        with override_settings(MEDIA_ROOT=output_dir):
            result = generate_top_screener_reports(top=1, output_dir=output_dir)

        self.assertTrue(result.csv_path.exists())
        self.assertEqual(len(result.report_paths), 1)
        html = result.report_paths[0].read_text(encoding="utf-8")
        self.assertIn("Performance Summary", html)
        self.assertIn("Axis Small Cap Fund", html)

    def test_screener_report_route_returns_html(self):
        scheme = self.make_scheme()
        FundScreenerSnapshot.objects.create(
            scheme=scheme,
            fund_name=scheme.scheme_name,
            fund_house="Axis",
            category_group="Equity",
            scheme_sub_category="Small Cap Fund",
            plan_type="Direct",
            cagr_3y_pct=14,
            data_as_of=date(2026, 6, 14),
        )

        response = self.client.get(reverse("funds:screener_report", args=[scheme.amfi_code]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Performance Summary")
        self.assertContains(response, scheme.scheme_name)
