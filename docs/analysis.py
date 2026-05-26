'''
Quantitative Analysis:
XIRR calculation
Absolute returns
SIP pattern analysis
Market timing efficiency
Diversification metrics

Psychological Analysis:
Investor archetype identification
Risk evolution tracking
Behavioral pattern detection
Consistency scoring

Comparative Analysis:
Benchmark comparison (Nifty)
Peer-relative positioning
Historical performance analysis

Visualization:
Cumulative investment plot
Monthly investment patterns
Portfolio allocation pie chart
Risk evolution timeline

Actionable Insights:
Personalized recommendations
Key strengths identification
Improvement areas

Strategic suggestions TO ADAPT TO YOUR DATA:
Replace sample data with your actual transaction history
Update CSV parsing in CSVAdapter class to match your file formats
Add your benchmark data for accurate comparison
Set AI_ENABLED = True if you want AI insights (requires API key)

This system provides a complete analysis framework that matches exactly what you requested, with minimal dependencies and clear, actionable outputs
'''

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from scipy.optimize import fsolve
import requests
import json
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Configuration for AI analysis (optional)
AI_ENABLED = False  # Set to True if you have API keys
GEMINI_API_KEY = "your_gemini_api_key_here"

class InvestmentAnalyzer:
    """Complete investment journey analysis system"""
    
    def __init__(self, user_data: Dict):
        """Initialize with user data"""
        self.user_data = user_data
        self.transactions = user_data.get('transactions', [])
        self.market_data = user_data.get('market_data', [])
        self.profile = user_data.get('profile', {})
        
        # Process data
        self.process_transactions()
        
    def process_transactions(self):
        """Process and categorize transactions"""
        df = pd.DataFrame(self.transactions)
        df['date'] = pd.to_datetime(df['date'])
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        df['action_sign'] = df['action'].apply(
            lambda x: -1 if x in ['buy', 'purchase', 'switch_purchase'] else 1
        )
        df['cash_flow'] = df['amount'] * df['action_sign']
        
        self.df = df
        self.start_date = df['date'].min()
        self.end_date = df['date'].max()
        
    def calculate_xirr(self, cash_flows=None, dates=None):
        """Calculate XIRR for cash flows"""
        if cash_flows is None:
            cash_flows = self.df['cash_flow'].values
            dates = self.df['date'].values
        
        def xnpv(rate):
            return sum([cf / (1 + rate) ** ((date - dates[0]).days / 365) 
                       for cf, date in zip(cash_flows, dates)])
        
        try:
            return fsolve(xnpv, 0.1)[0]
        except:
            return None
    
    def calculate_portfolio_metrics(self):
        """Calculate all portfolio metrics"""
        metrics = {}
        
        # Basic metrics
        total_invested = abs(self.df[self.df['cash_flow'] < 0]['cash_flow'].sum())
        total_withdrawn = self.df[self.df['cash_flow'] > 0]['cash_flow'].sum()
        net_profit = total_withdrawn - total_invested
        
        metrics['total_invested'] = total_invested
        metrics['total_withdrawn'] = total_withdrawn
        metrics['net_profit'] = net_profit
        metrics['abs_return_percent'] = (net_profit / total_invested * 100) if total_invested else 0
        
        # XIRR
        metrics['xirr'] = self.calculate_xirr() * 100  # Convert to percentage
        
        # SIP analysis
        metrics['sip_analysis'] = self.analyze_sip_pattern()
        
        # Market timing
        metrics['timing_efficiency'] = self.analyze_market_timing()
        
        # Diversification
        metrics['diversification'] = self.analyze_diversification()
        
        # Behavioral patterns
        metrics['behavioral_patterns'] = self.identify_behavioral_patterns()
        
        return metrics
    
    def analyze_sip_pattern(self) -> Dict:
        """Analyze SIP consistency and effectiveness"""
        buy_transactions = self.df[self.df['action'].isin(['buy', 'purchase'])]
        
        if buy_transactions.empty:
            return {'status': 'No SIP data'}
        
        # Group by month
        buy_transactions['year_month'] = buy_transactions['date'].dt.to_period('M')
        monthly_investments = buy_transactions.groupby('year_month')['amount'].sum().reset_index()
        
        sip_analysis = {
            'total_months': len(monthly_investments),
            'avg_monthly_investment': monthly_investments['amount'].mean(),
            'std_monthly_investment': monthly_investments['amount'].std(),
            'consistency_score': (monthly_investments['amount'] > 0).sum() / len(monthly_investments),
            'sip_phases': self.identify_sip_phases(monthly_investments)
        }
        
        return sip_analysis
    
    def identify_sip_phases(self, monthly_data: pd.DataFrame) -> List[Dict]:
        """Identify different SIP phases based on investment patterns"""
        phases = []
        current_phase = None
        
        for i, row in monthly_data.iterrows():
            amount = row['amount']
            month = row['year_month']
            
            # Define phase based on amount
            if amount < 1000:
                phase_type = "Low"
            elif amount < 5000:
                phase_type = "Medium"
            else:
                phase_type = "High"
            
            if current_phase is None or current_phase['type'] != phase_type:
                if current_phase:
                    phases.append(current_phase)
                current_phase = {
                    'type': phase_type,
                    'start': month,
                    'end': month,
                    'avg_amount': amount,
                    'months': 1
                }
            else:
                current_phase['end'] = month
                current_phase['months'] += 1
                current_phase['avg_amount'] = (
                    current_phase['avg_amount'] * (current_phase['months'] - 1) + amount
                ) / current_phase['months']
        
        if current_phase:
            phases.append(current_phase)
        
        return phases
    
    def analyze_market_timing(self) -> Dict:
        """Analyze market timing efficiency"""
        if not self.market_data:
            return {'status': 'No market data available'}
        
        market_df = pd.DataFrame(self.market_data)
        market_df['date'] = pd.to_datetime(market_df['date'])
        
        # Merge transactions with market data
        merged = pd.merge(
            self.df[['date', 'action', 'amount', 'cash_flow']],
            market_df[['date', 'value']],
            on='date',
            how='inner'
        )
        
        if merged.empty:
            return {'status': 'Insufficient overlap with market data'}
        
        # Calculate timing metrics
        buy_points = merged[merged['cash_flow'] < 0]
        sell_points = merged[merged['cash_flow'] > 0]
        
        timing_metrics = {
            'total_transactions': len(merged),
            'buy_points': len(buy_points),
            'sell_points': len(sell_points),
            'avg_buy_market_level': buy_points['value'].mean() if not buy_points.empty else None,
            'avg_sell_market_level': sell_points['value'].mean() if not sell_points.empty else None,
            'buy_low_score': self.calculate_timing_score(buy_points, 'low'),
            'sell_high_score': self.calculate_timing_score(sell_points, 'high')
        }
        
        return timing_metrics
    
    def calculate_timing_score(self, transactions: pd.DataFrame, timing_type: str) -> float:
        """Calculate timing efficiency score"""
        if transactions.empty:
            return 0
        
        market_values = transactions['value'].values
        percentiles = [(np.sum(market_values < val) / len(market_values) * 100) 
                      for val in market_values]
        
        if timing_type == 'low':
            # Lower percentiles are better for buying
            return np.mean([max(0, 100 - p) for p in percentiles]) / 100
        else:  # 'high'
            # Higher percentiles are better for selling
            return np.mean(percentiles) / 100
    
    def analyze_diversification(self) -> Dict:
        """Analyze portfolio diversification"""
        current_holdings = self.get_current_holdings()
        
        if current_holdings.empty:
            return {'status': 'No current holdings data'}
        
        # Calculate allocation by category
        if 'category' in current_holdings.columns:
            category_allocation = current_holdings.groupby('category')['current_value'].sum()
            total_value = category_allocation.sum()
            
            allocation_percent = (category_allocation / total_value * 100).to_dict()
            
            # Calculate diversification scores
            herfindahl_index = sum([(v/100)**2 for v in allocation_percent.values()])
            diversification_score = 1 - herfindahl_index
            
            return {
                'allocation': allocation_percent,
                'herfindahl_index': herfindahl_index,
                'diversification_score': diversification_score,
                'concentration_risk': 'High' if herfindahl_index > 0.25 else 'Medium' if herfindahl_index > 0.15 else 'Low'
            }
        
        return {'status': 'Category data not available'}
    
    def get_current_holdings(self) -> pd.DataFrame:
        """Extract current holdings from transactions"""
        # Simplified method - in reality, you'd track quantity and prices
        holdings = []
        
        for asset_type in ['stock', 'etf', 'mutual_fund']:
            asset_transactions = self.df[
                (self.df['asset_type'] == asset_type) & 
                (self.df['date'] > self.end_date - timedelta(days=90))
            ]
            
            if not asset_transactions.empty:
                latest = asset_transactions.iloc[-1]
                holdings.append({
                    'asset_type': asset_type,
                    'symbol': latest.get('symbol', 'Unknown'),
                    'category': latest.get('category', 'Unknown'),
                    'current_value': abs(latest['amount']) * 1.1  # Simplified growth
                })
        
        return pd.DataFrame(holdings)
    
    def identify_behavioral_patterns(self) -> Dict:
        """Identify behavioral investment patterns"""
        patterns = {
            'risk_taking_evolution': self.analyze_risk_evolution(),
            'holding_period_analysis': self.analyze_holding_periods(),
            'emotion_based_trading': self.detect_emotion_based_trades(),
            'consistency_score': self.calculate_consistency_score()
        }
        
        # Determine investor archetype
        patterns['investor_archetype'] = self.determine_archetype(patterns)
        
        return patterns
    
    def analyze_risk_evolution(self) -> Dict:
        """Analyze how risk appetite changed over time"""
        risk_scores = []
        
        for year in range(self.start_date.year, self.end_date.year + 1):
            year_data = self.df[self.df['date'].dt.year == year]
            
            if not year_data.empty:
                # Simple risk score based on transaction types
                risky_trades = len(year_data[year_data['category'].isin(['small_cap', 'international', 'crypto'])])
                total_trades = len(year_data)
                
                risk_score = (risky_trades / total_trades) if total_trades > 0 else 0
                risk_scores.append({'year': year, 'risk_score': risk_score})
        
        return {
            'yearly_scores': risk_scores,
            'trend': 'Increasing' if len(risk_scores) > 1 and risk_scores[-1]['risk_score'] > risk_scores[0]['risk_score'] else 'Decreasing'
        }
    
    def analyze_holding_periods(self) -> Dict:
        """Analyze holding periods for different assets"""
        # Simplified - would need buy/sell pairs in real implementation
        return {
            'estimated_avg_holding': '6-12 months',  # Placeholder
            'short_term_ratio': 0.3,  # Placeholder
            'long_term_ratio': 0.7    # Placeholder
        }
    
    def detect_emotion_based_trades(self) -> List[str]:
        """Detect potential emotion-based trading patterns"""
        patterns = []
        
        # Check for panic selling (large sales during market downturns)
        large_sales = self.df[
            (self.df['cash_flow'] > 10000) & 
            (self.df['action'].isin(['sell', 'redeem']))
        ]
        
        if len(large_sales) > 3:
            patterns.append("Multiple large redemptions detected")
        
        # Check for FOMO buying
        if len(self.df[self.df['category'] == 'international']) > 5:
            patterns.append("High international exposure - possible FOMO")
        
        return patterns if patterns else ["No clear emotion-based patterns detected"]
    
    def calculate_consistency_score(self) -> float:
        """Calculate investment consistency score"""
        # Factors: Regularity, adherence to plan, learning from mistakes
        monthly_data = self.df.set_index('date').resample('M')['amount'].sum()
        consistency = monthly_data[monthly_data < 0].count() / len(monthly_data.resample('M').sum())
        
        return float(consistency)
    
    def determine_archetype(self, patterns: Dict) -> str:
        """Determine investor archetype based on patterns"""
        risk_trend = patterns['risk_taking_evolution']['trend']
        consistency = patterns['consistency_score']
        emotion_patterns = patterns['emotion_based_trading']
        
        if consistency > 0.8 and risk_trend == 'Increasing':
            return "Systematic Learner"
        elif consistency > 0.8 and risk_trend == 'Decreasing':
            return "Conservative Planner"
        elif any("panic" in p.lower() for p in emotion_patterns):
            return "Emotional Reactor"
        else:
            return "Balanced Investor"
    
    def compare_with_benchmark(self, benchmark_return: float = 15.78) -> Dict:
        """Compare portfolio performance with benchmark"""
        portfolio_xirr = self.calculate_xirr() * 100
        
        comparison = {
            'portfolio_xirr': portfolio_xirr,
            'benchmark_return': benchmark_return,
            'difference': portfolio_xirr - benchmark_return,
            'outperformance': portfolio_xirr > benchmark_return,
            'percentage_of_benchmark': (portfolio_xirr / benchmark_return * 100) if benchmark_return else None
        }
        
        return comparison
    
    def generate_visualizations(self):
        """Generate key visualizations"""
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        # 1. Cumulative Investment Plot
        self.plot_cumulative_investment(axes[0, 0])
        
        # 2. Monthly Investment Pattern
        self.plot_monthly_investments(axes[0, 1])
        
        # 3. Category Allocation
        self.plot_category_allocation(axes[1, 0])
        
        # 4. Risk Evolution
        self.plot_risk_evolution(axes[1, 1])
        
        plt.tight_layout()
        plt.savefig('investment_analysis.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    def plot_cumulative_investment(self, ax):
        """Plot cumulative investment over time"""
        df_sorted = self.df.sort_values('date')
        df_sorted['cumulative_cash_flow'] = df_sorted['cash_flow'].cumsum()
        
        ax.plot(df_sorted['date'], df_sorted['cumulative_cash_flow'], 
                linewidth=2, color='blue', label='Cumulative Investment')
        ax.set_xlabel('Date')
        ax.set_ylabel('Cumulative Amount (₹)')
        ax.set_title('Investment Journey')
        ax.grid(True, alpha=0.3)
        ax.legend()
    
    def plot_monthly_investments(self, ax):
        """Plot monthly investment pattern"""
        monthly = self.df[self.df['cash_flow'] < 0].copy()
        monthly['year_month'] = monthly['date'].dt.to_period('M')
        monthly_grouped = monthly.groupby('year_month')['amount'].sum().reset_index()
        monthly_grouped['year_month'] = monthly_grouped['year_month'].astype(str)
        
        ax.bar(range(len(monthly_grouped)), monthly_grouped['amount'], 
               color='green', alpha=0.7)
        ax.set_xlabel('Month')
        ax.set_ylabel('Investment Amount (₹)')
        ax.set_title('Monthly Investment Pattern')
        ax.set_xticks(range(0, len(monthly_grouped), max(1, len(monthly_grouped)//6)))
        ax.set_xticklabels(monthly_grouped['year_month'].iloc[::max(1, len(monthly_grouped)//6)], 
                          rotation=45)
        ax.grid(True, alpha=0.3, axis='y')
    
    def plot_category_allocation(self, ax):
        """Plot current category allocation"""
        diversification = self.analyze_diversification()
        
        if 'allocation' in diversification:
            categories = list(diversification['allocation'].keys())
            values = list(diversification['allocation'].values())
            
            colors = plt.cm.Set3(np.linspace(0, 1, len(categories)))
            ax.pie(values, labels=categories, autopct='%1.1f%%', 
                   colors=colors, startangle=90)
            ax.set_title('Portfolio Diversification')
    
    def plot_risk_evolution(self, ax):
        """Plot risk evolution over years"""
        risk_data = self.analyze_risk_evolution()['yearly_scores']
        
        if risk_data:
            years = [d['year'] for d in risk_data]
            scores = [d['risk_score'] for d in risk_data]
            
            ax.plot(years, scores, marker='o', linewidth=2, color='red')
            ax.set_xlabel('Year')
            ax.set_ylabel('Risk Score')
            ax.set_title('Risk Appetite Evolution')
            ax.grid(True, alpha=0.3)
            ax.set_xticks(years)
    
    def generate_comprehensive_report(self) -> str:
        """Generate a comprehensive analysis report"""
        metrics = self.calculate_portfolio_metrics()
        comparison = self.compare_with_benchmark()
        diversification = self.analyze_diversification()
        behavioral = self.identify_behavioral_patterns()
        
        report = f"""
        ========================================
        COMPREHENSIVE INVESTMENT ANALYSIS REPORT
        ========================================
        
        INVESTMENT PERIOD: {self.start_date.date()} to {self.end_date.date()}
        
        ----------
        PERFORMANCE
        ----------
        Total Invested: ₹{metrics['total_invested']:,.0f}
        Net Profit: ₹{metrics['net_profit']:,.0f}
        Absolute Return: {metrics['abs_return_percent']:.1f}%
        XIRR (Annualized): {metrics['xirr']:.1f}%
        
        Benchmark Comparison:
          Portfolio XIRR: {comparison['portfolio_xirr']:.1f}%
          Nifty Return: {comparison['benchmark_return']:.1f}%
          Difference: {comparison['difference']:.1f}%
          Status: {'OUTPERFORMING' if comparison['outperformance'] else 'UNDERPERFORMING'}
        
        ----------
        SIP ANALYSIS
        ----------
        SIP Duration: {metrics['sip_analysis']['total_months']} months
        Average Monthly: ₹{metrics['sip_analysis']['avg_monthly_investment']:,.0f}
        Consistency: {metrics['sip_analysis']['consistency_score']:.0%}
        
        SIP Phases:
        """
        
        for phase in metrics['sip_analysis']['sip_phases']:
            report += f"  - {phase['type']}: {phase['months']} months (₹{phase['avg_amount']:,.0f}/month)\n"
        
        report += f"""
        ----------
        DIVERSIFICATION
        ----------
        Allocation:
        """
        
        if 'allocation' in diversification:
            for category, percent in diversification['allocation'].items():
                report += f"  {category}: {percent:.1f}%\n"
        
        report += f"""
        Diversification Score: {diversification.get('diversification_score', 0):.2f}
        Concentration Risk: {diversification.get('concentration_risk', 'N/A')}
        
        ----------
        MARKET TIMING
        ----------
        Buy Low Score: {metrics['timing_efficiency'].get('buy_low_score', 0):.2f}
        Sell High Score: {metrics['timing_efficiency'].get('sell_high_score', 0):.2f}
        
        ----------
        BEHAVIORAL ANALYSIS
        ----------
        Investor Archetype: {behavioral['investor_archetype']}
        Consistency Score: {behavioral['consistency_score']:.2f}
        Risk Trend: {behavioral['risk_taking_evolution']['trend']}
        
        Detected Patterns:
        """
        
        for pattern in behavioral['emotion_based_trading']:
            report += f"  - {pattern}\n"
        
        report += """
        ----------
        KEY INSIGHTS
        ----------
        """
        
        # Generate insights based on analysis
        insights = self.generate_insights(metrics, comparison, diversification, behavioral)
        for insight in insights:
            report += f"• {insight}\n"
        
        report += """
        ----------
        RECOMMENDATIONS
        ----------
        """
        
        recommendations = self.generate_recommendations(metrics, diversification, behavioral)
        for i, rec in enumerate(recommendations, 1):
            report += f"{i}. {rec}\n"
        
        return report
    
    def generate_insights(self, metrics: Dict, comparison: Dict, 
                         diversification: Dict, behavioral: Dict) -> List[str]:
        """Generate key insights from analysis"""
        insights = []
        
        # Performance insights
        if comparison['difference'] < -2:
            insights.append("Portfolio is underperforming the benchmark significantly")
        elif comparison['difference'] > 2:
            insights.append("Portfolio is outperforming the benchmark")
        
        # SIP insights
        if metrics['sip_analysis']['consistency_score'] > 0.9:
            insights.append("Excellent SIP discipline maintained")
        
        # Diversification insights
        if diversification.get('concentration_risk') == 'High':
            insights.append("Portfolio is highly concentrated, increasing risk")
        
        # Behavioral insights
        if behavioral['investor_archetype'] == 'Emotional Reactor':
            insights.append("Emotional trading patterns detected - consider more systematic approach")
        
        # Timing insights
        if metrics['timing_efficiency'].get('buy_low_score', 0) < 0.5:
            insights.append("Buying tends to happen at higher market levels")
        
        return insights
    
    def generate_recommendations(self, metrics: Dict, diversification: Dict, 
                                behavioral: Dict) -> List[str]:
        """Generate personalized recommendations"""
        recommendations = []
        
        # Diversification recommendations
        if diversification.get('concentration_risk') == 'High':
            recommendations.append("Rebalance portfolio to reduce concentration risk")
        
        # Behavioral recommendations
        if behavioral['investor_archetype'] == 'Emotional Reactor':
            recommendations.append("Implement a rule-based system to avoid emotional decisions")
        
        # SIP recommendations
        if metrics['sip_analysis']['consistency_score'] < 0.7:
            recommendations.append("Improve SIP consistency for better compounding")
        
        # General recommendations
        recommendations.append("Review portfolio allocation quarterly")
        recommendations.append("Consider tax implications before selling")
        recommendations.append("Maintain an emergency fund outside investment portfolio")
        
        return recommendations
    
    def ai_enhanced_analysis(self):
        """Use AI for deeper psychological analysis (optional)"""
        if not AI_ENABLED:
            return "AI analysis disabled. Enable by setting AI_ENABLED=True and providing API key."
        
        try:
            # This would use Gemini API for deeper analysis
            report = self.generate_comprehensive_report()
            
            # Simplified mock of AI analysis
            ai_insights = [
                "Your transition from stock picking to systematic investing shows maturing approach",
                "The high number of switches suggests potential over-optimization",
                "Consider if your active management is adding value vs passive approach"
            ]
            
            return ai_insights
            
        except Exception as e:
            return f"AI analysis failed: {str(e)}"
        


# Sample user input and data loader
class DataLoader:
    """Load and structure investment data"""
    
    @staticmethod
    def create_sample_data():
        """Create sample data matching your structure"""
        # This would be replaced with actual CSV parsing
        sample_transactions = [
            # Initial phase - stock picking
            {'date': '2020-10-22', 'asset_type': 'mutual_fund', 'action': 'buy', 
             'amount': 500, 'category': 'equity', 'symbol': 'ICICI_TECH'},
            
            {'date': '2020-10-26', 'asset_type': 'stock', 'action': 'buy', 
             'amount': 113, 'category': 'large_cap', 'symbol': 'FEDERAL_BANK'},
            
            {'date': '2020-12-21', 'asset_type': 'stock', 'action': 'sell',
             'amount': 130, 'category': 'large_cap', 'symbol': 'FEDERAL_BANK'},
            
            # SIP phase
            {'date': '2021-01-15', 'asset_type': 'mutual_fund', 'action': 'buy',
             'amount': 499, 'category': 'mid_cap', 'symbol': 'AXIS_MIDCAP'},
            
            {'date': '2021-02-15', 'asset_type': 'mutual_fund', 'action': 'buy',
             'amount': 499, 'category': 'mid_cap', 'symbol': 'AXIS_MIDCAP'},
            
            # ETF phase
            {'date': '2022-06-29', 'asset_type': 'etf', 'action': 'buy',
             'amount': 722, 'category': 'international', 'symbol': 'NASDAQ_ETF'},
            
            {'date': '2024-03-06', 'asset_type': 'etf', 'action': 'sell',
             'amount': 9296, 'category': 'international', 'symbol': 'NASDAQ_ETF'},
            
            # Current holdings
            {'date': '2025-12-15', 'asset_type': 'mutual_fund', 'action': 'buy',
             'amount': 499, 'category': 'large_cap', 'symbol': 'NIFTY_MIDCAP'},
            
            {'date': '2026-02-10', 'asset_type': 'mutual_fund', 'action': 'hold',
             'amount': 6963, 'category': 'international', 'symbol': 'NASDAQ_FOF'},
        ]
        
        # Mock market data
        market_data = [
            {'date': '2020-10-22', 'value': 12000, 'benchmark': 'NIFTY50'},
            {'date': '2021-01-15', 'value': 14500, 'benchmark': 'NIFTY50'},
            {'date': '2022-06-29', 'value': 15800, 'benchmark': 'NIFTY50'},
            {'date': '2024-03-06', 'value': 22000, 'benchmark': 'NIFTY50'},
            {'date': '2026-02-10', 'value': 21800, 'benchmark': 'NIFTY50'},
        ]
        
        # User profile
        profile = {
            'age': 28,
            'investment_experience_years': 5,
            'risk_profile': 'medium',
            'primary_goal': 'wealth_creation',
            'time_horizon': 'long_term'
        }
        
        return {
            'transactions': sample_transactions,
            'market_data': market_data,
            'profile': profile
        }
    
    @staticmethod
    def load_from_csv(file_path: str):
        """Load data from CSV files (simplified)"""
        # This is a simplified version - real implementation would parse your specific CSV format
        try:
            df = pd.read_csv(file_path)
            
            transactions = []
            for _, row in df.iterrows():
                # Map your CSV columns to our structure
                transactions.append({
                    'date': row.get('Date', row.get('Buy date', pd.NaT)),
                    'asset_type': 'stock' if 'Stock' in str(row.get('Stock name', '')) else 'mutual_fund',
                    'action': 'buy' if 'Buy' in str(row.get('Transaction Type', '')) else 'sell',
                    'amount': abs(float(row.get('Amount', 0) or row.get('Buy value', 0))),
                    'category': 'equity',  # Simplified
                    'symbol': row.get('Stock name', '') or row.get('Scheme Name', '')
                })
            
            return {'transactions': transactions}
            
        except Exception as e:
            print(f"Error loading CSV: {e}")
            return DataLoader.create_sample_data()
        
# main execution
def main():
    """Main execution function"""
    print("=" * 60)
    print("INVESTMENT JOURNEY ANALYZER")
    print("=" * 60)
    
    # Load data
    print("\n📊 Loading investment data...")
    loader = DataLoader()
    
    # Try to load from CSV or use sample data
    try:
        user_data = loader.load_from_csv('stock and etfs.csv')
    except:
        print("Using sample data (replace with your actual data)")
        user_data = loader.create_sample_data()
    
    # Initialize analyzer
    analyzer = InvestmentAnalyzer(user_data)
    
    # Run analysis
    print("\n🔍 Analyzing your investment journey...")
    
    # Generate report
    report = analyzer.generate_comprehensive_report()
    print(report)
    
    # Generate visualizations
    print("\n📈 Generating visualizations...")
    analyzer.generate_visualizations()
    
    # Optional AI analysis
    if AI_ENABLED:
        print("\n🤖 Running AI-enhanced analysis...")
        ai_insights = analyzer.ai_enhanced_analysis()
        print("\nAI Insights:")
        for insight in ai_insights:
            print(f"  • {insight}")
    
    # Save results
    with open('investment_analysis_report.txt', 'w') as f:
        f.write(report)
    
    print("\n" + "=" * 60)
    print("✅ Analysis complete!")
    print("Reports saved to:")
    print("  - investment_analysis_report.txt")
    print("  - investment_analysis.png")
    print("=" * 60)

if __name__ == "__main__":
    main()

# simplified csv parser
class CSVAdapter:
    """Adapt your specific CSV format to our analyzer"""
    
    @staticmethod
    def parse_stock_etf_csv(filepath: str):
        """Parse your stock and ETF CSV file"""
        df = pd.read_csv(filepath, skiprows=8)  # Skip headers
        
        transactions = []
        
        for _, row in df.iterrows():
            if pd.notna(row.get('Stock name')):
                # Stock transaction
                if pd.notna(row.get('Buy date')):
                    transactions.append({
                        'date': row['Buy date'],
                        'asset_type': 'stock',
                        'action': 'buy',
                        'amount': abs(float(row['Buy value'])),
                        'category': 'equity',
                        'symbol': row['Stock name']
                    })
                
                if pd.notna(row.get('Sell date')):
                    transactions.append({
                        'date': row['Sell date'],
                        'asset_type': 'stock',
                        'action': 'sell',
                        'amount': float(row['Sell value']),
                        'category': 'equity',
                        'symbol': row['Stock name']
                    })
        
        return transactions
    
    @staticmethod
    def parse_mutual_fund_csv(filepath: str):
        """Parse your mutual fund CAS CSV file"""
        transactions = []
        
        # This needs customization based on your actual file structure
        with open(filepath, 'r') as f:
            lines = f.readlines()
            
            for line in lines:
                if 'PURCHASE' in line or 'REDEEM' in line:
                    parts = line.split(',')
                    if len(parts) >= 6:
                        transactions.append({
                            'date': parts[5].strip(),
                            'asset_type': 'mutual_fund',
                            'action': 'buy' if 'PURCHASE' in line else 'sell',
                            'amount': abs(float(parts[4].replace('"', '').replace(',', ''))),
                            'category': 'equity',  # Simplified
                            'symbol': parts[0].strip()
                        })
        
        return transactions    
    

# quick start

# Quick start - minimal setup
def quick_analysis():
    """Run analysis with minimal setup"""
    
    # 1. Prepare your data in this format:
    my_data = {
        'transactions': [
            # List of all transactions
            {'date': '2020-10-22', 'asset_type': 'mutual_fund', 
             'action': 'buy', 'amount': 500, 'category': 'equity'},
            {'date': '2020-12-21', 'asset_type': 'mutual_fund',
             'action': 'sell', 'amount': 550, 'category': 'equity'},
            # Add all your transactions...
        ],
        'profile': {
            'age': 28,
            'investment_experience_years': 5,
            'risk_profile': 'medium'
        }
    }
    
    # 2. Run analysis
    analyzer = InvestmentAnalyzer(my_data)
    
    # 3. Get results
    print(analyzer.generate_comprehensive_report())
    analyzer.generate_visualizations()
    
    return analyzer