from django.test import TestCase

from apps.funds.models import Scheme
from apps.funds.peers import get_peer_matches
from apps.funds.runtime import find_peer_funds


class PeerDiscoveryTests(TestCase):
    def make_scheme(
        self,
        code,
        name,
        house,
        *,
        aum=None,
        plan="GROWTH",
        is_direct=True,
        category="",
        scheme_type="",
        is_active=True,
    ):
        return Scheme.objects.create(
            amfi_code=str(code),
            scheme_name=name,
            fund_house=house,
            scheme_type=scheme_type,
            scheme_category=category,
            plan=plan,
            is_direct=is_direct,
            is_active=is_active,
            aum_cr=aum,
        )

    def peer_codes(self, base, max_peers=8):
        return [match.scheme.amfi_code for match in get_peer_matches(base, max_peers=max_peers)]

    def test_small_cap_direct_growth_peers_rank_by_aum_and_exclude_wrong_options(self):
        base = self.make_scheme("145206", "Tata Small Cap Fund-Direct Plan-Growth", "Tata Mutual Fund")
        nippon = self.make_scheme("1", "Nippon India Small Cap Fund - Direct Plan Growth Plan", "Nippon India Mutual Fund", aum=700)
        axis = self.make_scheme("2", "Axis Small Cap Fund - Direct Plan - Growth Option", "Axis Mutual Fund", aum=100)
        self.make_scheme("3", "HDFC Mid Cap Fund - Direct Plan - Growth", "HDFC Mutual Fund", aum=10000)
        self.make_scheme("4", "Mirae Asset Large & Mid Cap Fund - Direct Plan - Growth", "Mirae Asset Mutual Fund", aum=9000)
        self.make_scheme("5", "Tata Small Cap Fund-Regular Plan-Growth", "Tata Mutual Fund", is_direct=False, aum=800)
        self.make_scheme("6", "Kotak Small Cap Fund - Direct Plan - IDCW", "Kotak Mahindra Mutual Fund", plan="IDCW", aum=600)

        matches = get_peer_matches(base, max_peers=5)

        self.assertEqual([m.scheme for m in matches], [nippon, axis])
        self.assertTrue(all(m.score == 800 for m in matches))
        self.assertEqual(find_peer_funds(base, max_peers=5), [nippon, axis])

    def test_small_cap_does_not_fall_through_to_other_equity_categories(self):
        base = self.make_scheme("10", "Tata Small Cap Fund Direct Plan Growth", "Tata Mutual Fund")
        peer = self.make_scheme("11", "Axis Small Cap Fund Direct Plan Growth", "Axis Mutual Fund")
        self.make_scheme("12", "HDFC Mid Cap Fund Direct Plan Growth", "HDFC Mutual Fund", aum=999)
        self.make_scheme("13", "SBI Flexi Cap Fund Direct Plan Growth", "SBI Mutual Fund", aum=998)
        self.make_scheme("14", "ICICI Prudential Large & Mid Cap Fund Direct Growth", "ICICI Prudential Mutual Fund", aum=997)

        self.assertEqual(self.peer_codes(base), [peer.amfi_code])

    def test_nifty_50_passive_peers_do_not_match_nifty_next_50(self):
        base = self.make_scheme("20", "HDFC Nifty 50 Index Fund - Direct Plan - Growth", "HDFC Mutual Fund")
        uti = self.make_scheme("21", "UTI Nifty 50 Index Fund - Growth Option - Direct", "UTI Mutual Fund", aum=500)
        sbi_etf = self.make_scheme("22", "SBI Nifty 50 ETF - Direct Plan - Growth", "SBI Mutual Fund", aum=400)
        self.make_scheme("23", "ICICI Prudential Nifty Next 50 Index Fund - Direct Growth", "ICICI Prudential Mutual Fund", aum=900)
        self.make_scheme("24", "Aditya Birla Sun Life Nifty 50 Equal Weight Index Fund-Direct Growth", "Aditya Birla Sun Life Mutual Fund", aum=800)
        self.make_scheme("25", "Bajaj Finserv ELSS Tax Saver Nifty 50 Index Fund Direct Growth", "Bajaj Finserv Mutual Fund", aum=700)

        matches = get_peer_matches(base, max_peers=5)

        self.assertEqual([m.scheme for m in matches], [uti, sbi_etf])
        self.assertTrue(all(m.match_group == "index:nifty_50" for m in matches))

    def test_elss_tax_saver_index_fund_matches_elss_not_plain_index(self):
        base = self.make_scheme("26", "360 ONE ELSS Tax Saver Nifty 50 Index Fund - Direct Plan - Growth", "360 ONE Mutual Fund")
        active_elss = self.make_scheme("27", "Axis ELSS Tax Saver Fund - Direct Plan - Growth", "Axis Mutual Fund", aum=300)
        passive_elss = self.make_scheme("28", "Bajaj Finserv ELSS Tax Saver Nifty 50 Index Fund Direct Growth", "Bajaj Finserv Mutual Fund", aum=200)
        self.make_scheme("29", "UTI Nifty 50 Index Fund - Growth Option - Direct", "UTI Mutual Fund", aum=1000)

        matches = get_peer_matches(base, max_peers=5)

        self.assertEqual([m.scheme for m in matches], [active_elss, passive_elss])
        self.assertTrue(all(m.match_group == "equity:elss" for m in matches))

    def test_banking_psu_debt_is_not_banking_sector_equity(self):
        base = self.make_scheme("30", "Axis Banking & PSU Debt Fund - Direct Plan - Growth", "Axis Mutual Fund")
        debt_peer = self.make_scheme("31", "Aditya Birla Sun Life Banking and PSU Debt Fund - Direct Plan Growth", "Aditya Birla Sun Life Mutual Fund", aum=300)
        self.make_scheme("32", "Nippon India Banking & Financial Services Fund - Direct Growth", "Nippon India Mutual Fund", aum=1000)

        matches = get_peer_matches(base, max_peers=5)

        self.assertEqual([m.scheme for m in matches], [debt_peer])
        self.assertEqual(matches[0].match_group, "active_debt:banking_psu")

    def test_pharma_and_healthcare_sector_funds_match_each_other_only(self):
        base = self.make_scheme("40", "Tata India Pharma & Healthcare Fund Direct Growth", "Tata Mutual Fund")
        peer = self.make_scheme("41", "SBI Healthcare Opportunities Fund Direct Growth", "SBI Mutual Fund")
        self.make_scheme("42", "ICICI Prudential Infrastructure Fund Direct Growth", "ICICI Prudential Mutual Fund")
        self.make_scheme("43", "Axis Thematic Fund Direct Growth", "Axis Mutual Fund")

        matches = get_peer_matches(base, max_peers=5)

        self.assertEqual([m.scheme for m in matches], [peer])
        self.assertEqual(matches[0].match_group, "sector:pharma_health")

    def test_overseas_nasdaq_fof_does_not_match_domestic_fof(self):
        base = self.make_scheme("50", "Mirae Asset NYSE FANG+ ETF Fund of Fund Direct Growth", "Mirae Asset Mutual Fund")
        us_peer = self.make_scheme("51", "Motilal Oswal Nasdaq 100 Fund of Fund Direct Growth", "Motilal Oswal Mutual Fund", aum=400)
        self.make_scheme("52", "ICICI Prudential Passive Strategy Fund of Fund Direct Growth", "ICICI Prudential Mutual Fund", aum=1000)
        self.make_scheme("53", "Bandhan US Treasury Bond 0-1 year Debt Passive FOF Direct Growth", "Bandhan Mutual Fund", aum=999)

        matches = get_peer_matches(base, max_peers=5)

        self.assertEqual([m.scheme for m in matches], [us_peer])
        self.assertIn(matches[0].match_group, {"fof_region:us", "fof:fof_overseas"})

    def test_gilt_and_gilt_10_year_do_not_mix(self):
        base = self.make_scheme("60", "SBI Magnum Gilt Fund Direct Growth", "SBI Mutual Fund")
        peer = self.make_scheme("61", "ICICI Prudential Gilt Fund Direct Plan Growth", "ICICI Prudential Mutual Fund", aum=200)
        self.make_scheme("62", "Axis Gilt Fund with 10 year Constant Duration Direct Growth", "Axis Mutual Fund", aum=999)

        matches = get_peer_matches(base, max_peers=5)

        self.assertEqual([m.scheme for m in matches], [peer])
        self.assertEqual(matches[0].match_group, "active_debt:gilt")

    def test_empty_category_still_matches_from_names(self):
        base = self.make_scheme("70", "Tata Small Cap Fund Direct Plan Growth", "Tata Mutual Fund", category="")
        peer = self.make_scheme("71", "Nippon India Small Cap Fund Direct Growth", "Nippon India Mutual Fund", category="")

        self.assertEqual(self.peer_codes(base), [peer.amfi_code])

    def test_same_fund_house_dedupes_to_best_variant(self):
        base = self.make_scheme("80", "Tata Small Cap Fund Direct Plan Growth", "Tata Mutual Fund")
        best = self.make_scheme("81", "Axis Small Cap Fund Direct Plan Growth", "Axis Mutual Fund", aum=500)
        self.make_scheme("82", "Axis Small Cap Fund Direct Growth Option", "Axis Mutual Fund", aum=100)
        other = self.make_scheme("83", "SBI Small Cap Fund Direct Plan Growth", "SBI Mutual Fund", aum=400)

        self.assertEqual([m.scheme for m in get_peer_matches(base, max_peers=8)], [best, other])
