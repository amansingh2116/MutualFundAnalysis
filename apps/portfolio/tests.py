"""Tests for Fund & ETF Watchlists in apps/portfolio."""
import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.funds.models import Scheme, FundScreenerSnapshot
from apps.portfolio.models import Watchlist, WatchlistItem


class WatchlistTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client = Client()
        self.client.login(username='testuser', password='password123')

        self.scheme1 = Scheme.objects.create(
            amfi_code='120001',
            scheme_name='Test Flexi Cap Direct Growth',
            fund_house='Test Mutual Fund',
            scheme_category='Equity: Flexi Cap',
            is_direct=True,
            is_etf=False,
            expense_ratio=0.75,
        )
        self.scheme2 = Scheme.objects.create(
            amfi_code='120002',
            scheme_name='Test Nifty 50 ETF',
            fund_house='Test Mutual Fund',
            scheme_category='Other: ETF',
            is_direct=False,
            is_etf=True,
            expense_ratio=0.15,
        )

        FundScreenerSnapshot.objects.create(
            scheme=self.scheme1,
            fund_name=self.scheme1.scheme_name,
            fund_house=self.scheme1.fund_house,
            category_group='Equity',
            scheme_sub_category='Flexi Cap Fund',
            is_direct=True,
            is_etf=False,
            aum_cr=12500.0,
            returns_1y_pct=22.5,
            cagr_3y_pct=18.4,
            returns_5y_pct=16.8,
            expense_ratio=0.75,
            sharpe_ratio=1.25,
            model_score=88.5,
        )

    def test_default_watchlist_created_on_hub_access(self):
        url = reverse('portfolio:watchlist_hub')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Watchlist.objects.filter(user=self.user, is_default=True).exists())
        self.assertContains(resp, 'Fund & ETF Watchlists')

    def test_custom_watchlist_crud_api(self):
        api_url = reverse('portfolio:watchlist_api')
        
        # 1. Create custom watchlist
        post_resp = self.client.post(
            api_url,
            data=json.dumps({'name': 'Tech & ETFs', 'description': 'Thematic funds'}),
            content_type='application/json'
        )
        self.assertEqual(post_resp.status_code, 200)
        data = post_resp.json()
        wl_id = data['id']
        self.assertEqual(data['name'], 'Tech & ETFs')

        # 2. Rename watchlist
        patch_resp = self.client.patch(
            api_url,
            data=json.dumps({'watchlist_id': wl_id, 'name': 'Tech & Global ETFs'}),
            content_type='application/json'
        )
        self.assertEqual(patch_resp.status_code, 200)
        self.assertEqual(patch_resp.json()['name'], 'Tech & Global ETFs')

        # 3. List watchlists
        get_resp = self.client.get(api_url)
        self.assertEqual(get_resp.status_code, 200)
        wls = get_resp.json()['watchlists']
        self.assertTrue(any(w['name'] == 'Tech & Global ETFs' for w in wls))

        # 4. Delete watchlist
        del_resp = self.client.delete(
            api_url,
            data=json.dumps({'watchlist_id': wl_id}),
            content_type='application/json'
        )
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse(Watchlist.objects.filter(id=wl_id).exists())

    def test_watchlist_item_add_and_remove(self):
        wl = Watchlist.objects.create(user=self.user, name='My Core Funds', is_default=True)
        item_api = reverse('portfolio:watchlist_items_api')

        # Add scheme 1
        add_resp = self.client.post(
            item_api,
            data=json.dumps({'watchlist_id': wl.id, 'scheme_id': self.scheme1.id, 'notes': 'Top SIP pick'}),
            content_type='application/json'
        )
        self.assertEqual(add_resp.status_code, 200)
        self.assertEqual(add_resp.json()['status'], 'added')
        self.assertEqual(wl.items.count(), 1)

        # Update note
        item_id = add_resp.json()['item_id']
        note_resp = self.client.patch(
            item_api,
            data=json.dumps({'item_id': item_id, 'notes': 'Core portfolio 40%'}),
            content_type='application/json'
        )
        self.assertEqual(note_resp.status_code, 200)
        item = WatchlistItem.objects.get(id=item_id)
        self.assertEqual(item.notes, 'Core portfolio 40%')

        # Remove item
        del_resp = self.client.delete(
            item_api,
            data=json.dumps({'item_id': item_id}),
            content_type='application/json'
        )
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(wl.items.count(), 0)

    def test_watchlist_toggle_and_search_api(self):
        toggle_url = reverse('portfolio:watchlist_toggle_api')
        search_url = reverse('portfolio:watchlist_search_api')

        # 1. Search API
        s_resp = self.client.get(f'{search_url}?q=Flexi')
        self.assertEqual(s_resp.status_code, 200)
        results = s_resp.json()['results']
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0]['amfi_code'], '120001')

        # 2. Toggle API - Add
        t_resp = self.client.post(
            toggle_url,
            data=json.dumps({'amfi_code': '120001', 'action': 'toggle'}),
            content_type='application/json'
        )
        self.assertEqual(t_resp.status_code, 200)
        self.assertTrue(t_resp.json()['is_watched'])

        # 3. Check status
        status_resp = self.client.get(f'{toggle_url}?amfi_code=120001')
        self.assertEqual(status_resp.status_code, 200)
        self.assertTrue(status_resp.json()['is_in_any'])

        # 4. Toggle API - Remove
        t_resp2 = self.client.post(
            toggle_url,
            data=json.dumps({'amfi_code': '120001', 'action': 'toggle'}),
            content_type='application/json'
        )
        self.assertEqual(t_resp2.status_code, 200)
        self.assertFalse(t_resp2.json()['is_watched'])
