from unittest.mock import patch
from django.test import TestCase, RequestFactory
from apps.funds.models import Scheme
from apps.funds.report import (
    _chrome_html_to_pdf,
    _system_chrome_html_to_pdf,
    generate_fund_report_response,
)


class FundReportPdfTest(TestCase):
    def setUp(self):
        self.scheme = Scheme.objects.create(
            amfi_code="122639",
            scheme_name="Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
            scheme_category="Equity Scheme - Flexi Cap Fund",
            fund_house="PPFAS Mutual Fund",
            is_direct=True,
            plan="GROWTH",
        )
        self.rf = RequestFactory()

    def test_chrome_html_to_pdf_returns_bytes(self):
        html = "<html><body><h1>Research Report Test</h1></body></html>"
        pdf_bytes = _chrome_html_to_pdf(html)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_system_chrome_html_to_pdf_returns_bytes(self):
        html = "<html><body><h1>System Chrome CLI Test</h1></body></html>"
        pdf_bytes = _system_chrome_html_to_pdf(html)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_generate_fund_report_response_pdf(self):
        req = self.rf.get("/")
        resp = generate_fund_report_response(req, self.scheme)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertIn("FundReport_Parag_Parikh", resp.headers.get("Content-Disposition"))

    @patch("apps.funds.report._chrome_html_to_pdf")
    def test_generate_fund_report_response_fallback_html(self, mock_pdf):
        mock_pdf.side_effect = RuntimeError("All PDF engines failed")
        req = self.rf.get("/")
        resp = generate_fund_report_response(req, self.scheme)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("Content-Type"))
        self.assertEqual(resp.headers.get("X-Report-Fallback"), "HTML")
