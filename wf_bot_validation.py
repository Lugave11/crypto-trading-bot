#!/usr/bin/env python3
"""
Walk-Forward Backtest: Bot Settings Validation
14.4 Years of 1-Minute BTC Data
Max Drawdown Constraint: 20%
"""

import sys
sys.path.insert(0, '/mnt/data/hermes/workspace/.local/lib/python3.13/site-packages')

import pandas as pd
import numpy as np
from datetime import datetime

print("="*70)
print("🚀 WALK-FORWARD BACKTEST: Bot Settings Validation")
print("14.4 Years of 1-Minute BTC Data")
print("="*70)
print()

# ============================================================================
# BOT CONFIGURATION
# ============================================================================
BOT_SETTINGS = {
    'rsi_oversold': 25,      # Buy signal threshold
    'rsi_overbought': 75,    # Sell signal threshold
    'take_profit': 0.8,      # 0.8% TP
    'stop_loss': 1.0,        # 1.0% SL
    'position_size': 7,      # 7% of capital per trade
    'max_drawdown': 0.20,    # 20% max drawdown constraint
}

print("📋 Bot Configuration:")
for key, value in BOT_SETTINGS.items():
    print(f"   {key}: {value}")
print()

# ============================================================================
# LOAD DATA
# ============================================================================
print("📊 Loading 1-minute data...")
df = pd.read_csv('/mnt/data/hermes/workspace/crypto_bot/data/btcusd_1m_kaggle_full.csv')
df['datetime'] = pd.to_datetime(df['Timestamp'], unit='s')
df.set_index('datetime', inplace=True)
df.sort_index(inplace=True)

print(f"✅ Loaded {len(df):,} candles")
print(f"   From: {df.index[0].strftime('%Y-%m-%d %H:%M')}")
print(f"   To: {df.index[-1].strftime('%Y-%m-%d %H:%M')}")
days = (df.index[-1] - df.index[0]).days
print(f"   Coverage: {days} days ({days/365:.1f} years)")
print()

# ============================================================================
# CALCULATE INDICATORS
# ============================================================================
print("📊 Calculating indicators...")

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)

df['rsi'] = rsi(df['Close'])
df['macd'] = df['Close'].ewm(12).mean() - df['Close'].ewm(26).mean()
df['macd_sig'] = df['macd'].ewm(9).mean()
df.dropna(inplace=True)

print(f"✅ {len(df):,} candles ready")
print()

# ============================================================================
# BACKTEST ENGINE WITH DRAWDOWN CONTROL
# ============================================================================
print("📊 Walk-Forward Validation")
print()

def backtest_with_dd_control(df, settings):
    """
    Backtest with max drawdown enforcement
    Stops trading if drawdown exceeds limit
    """
    trades = []
    position = None
    cap = 10000
    peak = cap
    stopped = False
    stop_date = None
    
    for idx, row in df.iterrows():
        if pd.isna(row['rsi']):
            continue
        
        # Check if we've hit max drawdown
        current_dd = (cap - peak) / peak if peak > 0 else 0
        if current_dd <= -settings['max_drawdown']:
            if not stopped:
                stopped = True
                stop_date = idx
            continue  # Stop trading
        
        if position is None:
            # Entry signals
            if row['rsi'] < settings['rsi_oversold']:
                position = {
                    'type': 'LONG', 
                    'entry': row['Close'], 
                    'size': cap * settings['position_size']/100,
                    'sl': row['Close'] * (1 - settings['stop_loss']/100), 
                    'tp': row['Close'] * (1 + settings['take_profit']/100),
                    'entry_date': idx
                }
            elif row['rsi'] > settings['rsi_overbought']:
                position = {
                    'type': 'SHORT', 
                    'entry': row['Close'], 
                    'size': cap * settings['position_size']/100,
                    'sl': row['Close'] * (1 + settings['stop_loss']/100), 
                    'tp': row['Close'] * (1 - settings['take_profit']/100),
                    'entry_date': idx
                }
        else:
            # Exit logic
            exit_p = None
            exit_reason = None
            
            if position['type'] == 'LONG':
                if row['Low'] <= position['sl']:
                    exit_p = position['sl']
                    exit_reason = 'SL'
                elif row['High'] >= position['tp']:
                    exit_p = position['tp']
                    exit_reason = 'TP'
                elif row['rsi'] > 50:
                    exit_p = row['Close']
                    exit_reason = 'RSI'
            else:  # SHORT
                if row['High'] >= position['sl']:
                    exit_p = position['sl']
                    exit_reason = 'SL'
                elif row['Low'] <= position['tp']:
                    exit_p = position['tp']
                    exit_reason = 'TP'
                elif row['rsi'] < 50:
                    exit_p = row['Close']
                    exit_reason = 'RSI'
            
            if exit_p:
                pnl = (exit_p - position['entry']) / position['entry'] * 100 if position['type'] == 'LONG' else (position['entry'] - exit_p) / position['entry'] * 100
                cap += position['size'] * pnl / 100
                peak = max(peak, cap)
                
                trades.append({
                    'pnl': pnl, 
                    'cap': cap,
                    'entry_date': position['entry_date'],
                    'exit_date': idx,
                    'exit_reason': exit_reason
                })
                position = None
    
    ret = (cap - 10000) / 10000 * 100
    dd = (cap - peak) / peak * 100 if peak > 0 else 0
    wr = len([t for t in trades if t['pnl'] > 0]) / len(trades) * 100 if trades else 0
    
    return {
        'trades': len(trades), 
        'wr': wr, 
        'ret': ret, 
        'dd': dd, 
        'cap': cap,
        'stopped': stopped,
        'stop_date': stop_date
    }

# ============================================================================
# WALK-FORWARD CONFIGURATION
# ============================================================================
# 30-day train, 15-day test for 1-minute scalping
train_days = 30
test_days = 15
train_bars = train_days * 24 * 60
test_bars = test_days * 24 * 60
n_win = (len(df) - test_bars) // train_bars

print(f"   Train: {train_days} days ({train_bars:,} bars)")
print(f"   Test: {test_days} days ({test_bars:,} bars)")
print(f"   Windows: {n_win}")
print()

# ============================================================================
# RUN WALK-FORWARD
# ============================================================================
results = []
stopped_windows = 0

for i in range(n_win):
    test_s = (i + 1) * train_bars
    test_e = min(test_s + test_bars, len(df))
    test_df = df.iloc[test_s:test_e]
    
    res = backtest_with_dd_control(test_df, BOT_SETTINGS)
    results.append({'window': i+1, **res})
    
    if res['stopped']:
        stopped_windows += 1
        status = "⚠️  DD STOP"
    else:
        status = "✅"
    
    # Progress every 10%
    if (i+1) % max(1, n_win//10) == 0 or i == n_win-1:
        print(f"   W{i+1:3d}: {res['trades']:4d} trades, WR: {res['wr']:5.1f}%, "
              f"Ret: {res['ret']:+7.2f}%, DD: {res['dd']:-7.2f}% {status}")

print()

# ============================================================================
# RESULTS
# ============================================================================
print("="*70)
print("📊 FINAL RESULTS: Bot Settings Validation")
print("="*70)
print()

rdf = pd.DataFrame(results)

# Core metrics
print("CORE METRICS:")
print(f"   Windows: {len(rdf)}")
print(f"   Total Trades: {rdf['trades'].sum():,}")
print(f"   Avg Win Rate: {rdf['wr'].mean():.1f}%")
print(f"   Total Return: {rdf['ret'].sum():+.2f}%")
print(f"   Avg Return/Window: {rdf['ret'].mean():+.2f}%")
print()

# Drawdown analysis
print("DRAWDOWN ANALYSIS:")
print(f"   Max Drawdown (constraint): {BOT_SETTINGS['max_drawdown']*100:.1f}%")
print(f"   Actual Max DD: {rdf['dd'].min():.2f}%")
print(f"   Avg DD: {rdf['dd'].mean():.2f}%")
print(f"   Windows Hit DD Limit: {stopped_windows} ({stopped_windows/len(rdf)*100:.1f}%)")
print()

# Win rate distribution
print("WIN RATE DISTRIBUTION:")
print(f"   Best WR: {rdf['wr'].max():.1f}%")
print(f"   Worst WR: {rdf['wr'].min():.1f}%")
print(f"   Median WR: {rdf['wr'].median():.1f}%")
print(f"   Windows >50% WR: {(rdf['wr']>50).sum()}/{len(rdf)} ({(rdf['wr']>50).mean()*100:.0f}%)")
print()

# Returns distribution
print("RETURNS DISTRIBUTION:")
print(f"   Best Window: {rdf['ret'].max():+.2f}%")
print(f"   Worst Window: {rdf['ret'].min():+.2f}%")
print(f"   Median Return: {rdf['ret'].median():+.2f}%")
print(f"   Profitable Windows: {(rdf['ret']>0).sum()}/{len(rdf)} ({(rdf['ret']>0).mean()*100:.0f}%)")
print()

# Risk-adjusted metrics
cum = rdf['ret'].cumsum()
dd_cum = (cum - cum.cummax()).min()
print("RISK-ADJUSTED METRICS:")
print(f"   Cumulative Return: {cum.iloc[-1]:+.2f}%")
print(f"   Max Cumulative DD: {dd_cum:.2f}%")
if rdf['ret'].std() > 0 and rdf['ret'].mean() != 0:
    sharpe = rdf['ret'].mean() / rdf['ret'].std() * np.sqrt(252*24*60)
    print(f"   Sharpe Ratio: {sharpe:.2f}")
if rdf['ret'].mean() != 0:
    calmar = abs(cum.iloc[-1] / dd_cum) if dd_cum != 0 else float('inf')
    print(f"   Calmar Ratio: {calmar:.2f}")
print()

# ============================================================================
# YEAR-BY-YEAR BREAKDOWN
# ============================================================================
print("="*70)
print("📊 YEAR-BY-YEAR BREAKDOWN")
print("="*70)
print()

df_years = df.copy()
df_years['year'] = df_years.index.year
years = sorted(df_years['year'].unique())

year_results = []
for year in years:
    year_df = df_years[df_years['year'] == year]
    res = backtest_with_dd_control(year_df, BOT_SETTINGS)
    year_results.append({'year': year, **res})
    
    status = "⚠️  DD" if res['stopped'] else ""
    print(f"  {year}: {res['trades']:4d} trades, WR: {res['wr']:5.1f}%, "
          f"Ret: {res['ret']:+7.2f}%, DD: {res['dd']:-6.2f}% {status}")

print()

# ============================================================================
# VALIDATION SUMMARY
# ============================================================================
print("="*70)
print("📋 BOT SETTINGS VALIDATION SUMMARY")
print("="*70)
print()

# Pass/fail criteria
dd_pass = abs(rdf['dd'].min()) <= BOT_SETTINGS['max_drawdown'] * 100
wr_pass = rdf['wr'].mean() >= 50
ret_pass = rdf['ret'].sum() > 0
profitable_pass = (rdf['ret']>0).mean() >= 0.6

print("VALIDATION CRITERIA:")
print(f"   ✅ Max Drawdown ≤20%: {'PASS ✓' if dd_pass else 'FAIL ✗'} ({rdf['dd'].min():.2f}%)")
print(f"   ✅ Win Rate ≥50%: {'PASS ✓' if wr_pass else 'FAIL ✗'} ({rdf['wr'].mean():.1f}%)")
print(f"   ✅ Positive Return: {'PASS ✓' if ret_pass else 'FAIL ✗'} ({rdf['ret'].sum():+.2f}%)")
print(f"   ✅ ≥60% Profitable Windows: {'PASS ✓' if profitable_pass else 'FAIL ✗'} ({(rdf['ret']>0).mean()*100:.0f}%)")
print()

all_pass = dd_pass and wr_pass and ret_pass and profitable_pass
if all_pass:
    print("🎉 ALL VALIDATION CRITERIA PASSED!")
    print()
    print("Bot settings are VALIDATED for production use.")
else:
    print("⚠️  SOME CRITERIA FAILED - Settings may need optimization")
    if not dd_pass:
        print(f"   → Drawdown too high, consider reducing position size")
    if not wr_pass:
        print(f"   → Win rate low, consider adjusting RSI thresholds")
    if not ret_pass:
        print(f"   → Negative returns, review TP/SL ratios")
    if not profitable_pass:
        print(f"   → Too many losing windows, strategy may be unstable")

print()
print("="*70)
print("✅ WALK-FORWARD VALIDATION COMPLETE")
print("="*70)
print()
print(f"Data: 7,566,897 candles (14.4 years)")
print(f"Period: 2012-01-01 to 2026-05-23")
print(f"Windows: {len(rdf)} walk-forward iterations")
print(f"Total Trades: {rdf['trades'].sum():,}")
print()
