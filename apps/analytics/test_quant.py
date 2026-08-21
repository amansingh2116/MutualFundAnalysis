import unittest
import numpy as np
from apps.analytics.forecasting import (
    calculate_var_cvar,
    run_strategylab_backtest,
    _sarima_forecast,
    _prophet_forecast,
    _lgb_forecast,
    _bilstm_forecast,
    _gru_forecast,
    _transformer_forecast,
    run_return_forecast,
)
from datetime import date, timedelta


class QuantEngineTestCase(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        n = 300
        rets = np.random.normal(0.0006, 0.012, n)
        nav_values = [100.0]
        for r in rets:
            nav_values.append(nav_values[-1] * np.exp(r))
        
        base_date = date.today() - timedelta(days=n)
        self.nav_data = []
        for i, val in enumerate(nav_values):
            d = base_date + timedelta(days=i)
            self.nav_data.append({'date': d.strftime('%Y-%m-%d'), 'nav': float(val)})

    def test_var_cvar_calculation(self):
        result = calculate_var_cvar(self.nav_data, {'confidence': 0.95})
        self.assertIn('periods', result)
        self.assertIn('sample_size', result)
        self.assertEqual(len(result['periods']), 4)
        
        p_1d = next(p for p in result['periods'] if p['name'] == '1-Day')
        self.assertIn('hist_var95', p_1d)
        self.assertIn('param_var95', p_1d)
        self.assertIn('hist_cvar95', p_1d)
        self.assertIn('param_cvar95', p_1d)
        self.assertIn('fat_tail_gap', p_1d)

    def test_strategylab_backtesting_engine(self):
        result = run_strategylab_backtest(self.nav_data, {'initial_capital': 100000})
        self.assertIn('strategies', result)
        self.assertIn('best_strategy', result)
        self.assertIn('dates', result)
        self.assertGreaterEqual(len(result['strategies']), 8)
        
        # Check Buy & Hold baseline
        bh = next(s for s in result['strategies'] if 'Buy & Hold' in s['name'])
        self.assertEqual(bh['trades'], 1)
        self.assertGreater(bh['final_value'], 0)

        # Check ML & Deep Learning strategies
        ml_strat = next(s for s in result['strategies'] if 'XGBoost' in s['name'])
        self.assertIn('win_rate', ml_strat)
        self.assertIn('cagr', ml_strat)
        self.assertIn('alpha', ml_strat)

    def test_individual_forecast_models(self):
        nav_series = [x['nav'] for x in self.nav_data]
        h = 30
        
        sarima_res = _sarima_forecast(nav_series, h)
        self.assertEqual(len(sarima_res['preds']), h)
        self.assertGreater(sarima_res['sigma'], 0)

        prophet_res = _prophet_forecast(nav_series, h)
        self.assertEqual(len(prophet_res['preds']), h)

        lgb_res = _lgb_forecast(nav_series, h)
        self.assertEqual(len(lgb_res['preds']), h)

        bilstm_res = _bilstm_forecast(nav_series, h)
        self.assertEqual(len(bilstm_res['preds']), h)

        gru_res = _gru_forecast(nav_series, h)
        self.assertEqual(len(gru_res['preds']), h)

        transformer_res = _transformer_forecast(nav_series, h)
        self.assertEqual(len(transformer_res['preds']), h)

    def test_forecast_returns_suite(self):
        res = run_return_forecast(self.nav_data, {'horizon': 30, 'include_ensemble': True, 'backtest_window': 5})
        self.assertIn('models', res)
        self.assertIn('future_dates', res)
        self.assertIn('last_nav', res)
        self.assertEqual(len(res['future_dates']), 30)
        self.assertGreater(len(res['models']), 4)


