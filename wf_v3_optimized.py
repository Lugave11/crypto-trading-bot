#!/usr/bin/env python3
"""
Walk-Forward Backtest: V3 Multi-Metric Strategy (OPTIMIZED)
Pre-calculates all indicators upfront for speed
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os
import json

# ============================================================================
# CONFIGURATION
# ============================================================================
DATA_FILE = '/mnt/data/hermes/workspace/crypto_bot/data/btcusd_1m_kaggle_full.csv'

BOT_SETTINGS = {
    'rsi_oversold': 25,
    'rsi_overbought': 75,
    'use_ema_filter': True,
    'ema_period': 200,
    'use_adx_filter': True,
    'adx_period': 14,
    'adx_max': 25,
    'use_atr_stops': True,
    'atr_period': 14,
    'atr_stop_mult': 1.5,
    'atr_trailing_mult': 2.0,
    'use_volume_confirm': True,
    'volume_period': 20,
    'volume_mult': 1.2,
    'use_divergence': True,
    'divergence_lookback': 5,
    'position_size': 5,
    'max_drawdown': 20,
    'stop_loss': 1.0,
    'trailing_stop_pct': 1.0,
    'trailing_check_interval': 5,
}

TRAIN_DAYS = 30
TEST_DAYS = 15
INITIAL_CAPITAL = 10000
CANDLES_1YEAR = 365 * 24 * 60

DATA_DIR = '/mnt/data/hermes/workspace/crypto_bot/data/wf_v3_multi_metric'
os.makedirs(DATA_DIR, exist_ok=True)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ============================================================================
# LOAD & PREPARE DATA
# ============================================================================
log("="*70)
log("📊 WALK-FORWARD: V3 MULTI-METRIC (BTC 1-YEAR) - OPTIMIZED")
log("="*70)

log(f"Loading data...")
df_full = pd.read_csv(DATA_FILE)
log(f"Total candles: {len(df_full):,}")

df_full['Timestamp'] = pd.to_datetime(df_full['Timestamp'], unit='s')
df_full.set_index('Timestamp', inplace=True)
df_full = df_full[~df_full.index.duplicated(keep='last')]
df_full = df_full.sort_index()

# Take most recent 1 year
df_full = df_full.tail(CANDLES_1YEAR)
log(f"Using: {len(df_full):,} candles (~1 year)")
log(f"Date range: {df_full.index[0]} to {df_full.index[-1]}")
log("")

# ============================================================================
# PRE-CALCULATE ALL INDICATORS (OPTIMIZATION)
# ============================================================================
log("📐 Pre-calculating all indicators for entire dataset...")
log("(This takes 2-3 minutes but makes backtest 10x faster)")

df = df_full.copy()

# RSI
delta = df['Close'].diff()
gain = delta.where(delta > 0, 0).rolling(14).mean()
loss = -delta.where(delta < 0, 0).rolling(14).mean()
df['rsi'] = 100 - 100 / (1 + gain / loss)

# EMA 200
df['ema200'] = df['Close'].ewm(span=200, adjust=False).mean()

# ATR
high = df['High']
low = df['Low']
close_prev = df['Close'].shift(1)
tr1 = high - low
tr2 = (high - close_prev).abs()
tr3 = (low - close_prev).abs()
tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
df['atr'] = tr.rolling(14).mean()

# ADX
plus_dm = high.diff()
minus_dm = -low.diff()
plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
plus_di = 100 * (plus_dm.rolling(14).mean() / df['atr'])
minus_di = 100 * (minus_dm.rolling(14).mean() / df['atr'])
dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
df['adx'] = dx.rolling(14).mean()

# Volume SMA
df['vol_sma'] = df['Volume'].rolling(20).mean()
df['volume_ratio'] = df['Volume'] / df['vol_sma']

# Divergence (simplified - check last 5 candles)
def detect_div(row_idx):
    if row_idx < 7:
        return None
    closes = df['Close'].iloc[row_idx-5:row_idx+1]
    rsis = df['rsi'].iloc[row_idx-5:row_idx+1]
    
    if len(closes) < 2 or len(rsis) < 2:
        return None
    
    # Bullish
    if closes.iloc[-1] < closes.iloc[-2] and rsis.iloc[-1] > rsis.iloc[-2]:
        return 'BULLISH'
    # Bearish
    if closes.iloc[-1] > closes.iloc[-2] and rsis.iloc[-1] < rsis.iloc[-2]:
        return 'BEARISH'
    
    return None

log("  Calculating divergence...")
df['divergence'] = [detect_div(i) for i in range(len(df))]

# Drop NaN rows
df = df.dropna()
log(f"  ✅ Ready! {len(df):,} candles with all indicators")
log("")

# ============================================================================
# TRADING ENGINE (OPTIMIZED - uses pre-calculated indicators)
# ============================================================================
class TraderV3Optimized:
    def __init__(self, settings):
        self.settings = settings
        self.reset()
    
    def reset(self):
        self.capital = INITIAL_CAPITAL
        self.position = None
        self.peak = INITIAL_CAPITAL
        self.trades = []
        self.pnl = 0
        self.wins = 0
        self.total = 0
        self.highest = None
        self.lowest = None
        self.candles_since_update = 0
    
    def run_on_df(self, test_df):
        """Run backtest on pre-calculated DataFrame"""
        for idx, row in test_df.iterrows():
            price = row['Close']
            dd = (self.capital - self.peak) / self.peak * 100
            
            if dd <= -self.settings['max_drawdown']:
                continue
            
            # ENTRY
            if self.position is None:
                rsi = row['rsi']
                ema200 = row['ema200']
                adx = row['adx']
                volume_ratio = row['volume_ratio']
                divergence = row['divergence']
                atr = row['atr']
                
                # Check filters
                above_ema = price > ema200
                low_adx = adx < self.settings['adx_max'] if not pd.isna(adx) else True
                high_volume = volume_ratio > self.settings['volume_mult'] if not pd.isna(volume_ratio) else True
                
                # LONG
                if rsi < self.settings['rsi_oversold']:
                    confirms = 0
                    if not self.settings['use_ema_filter'] or above_ema:
                        confirms += 1
                    if not self.settings['use_adx_filter'] or low_adx:
                        confirms += 1
                    if not self.settings['use_volume_confirm'] or high_volume:
                        confirms += 1
                    if not self.settings['use_divergence'] or divergence == 'BULLISH':
                        confirms += 1
                    
                    if confirms >= 2:
                        # Calculate stop
                        if self.settings['use_atr_stops'] and not pd.isna(atr) and atr > 0:
                            initial_sl = price - (atr * self.settings['atr_stop_mult'])
                            trailing_dist = atr * self.settings['atr_trailing_mult']
                        else:
                            initial_sl = price * (1 - self.settings['stop_loss'] / 100)
                            trailing_dist = price * self.settings['trailing_stop_pct'] / 100
                        
                        self.position = {
                            'type': 'LONG',
                            'entry': price,
                            'size': self.capital * self.settings['position_size'] / 100,
                            'sl': initial_sl,
                            'trailing_dist': trailing_dist,
                        }
                        self.highest = price
                        self.candles_since_update = 0
                
                # SHORT
                elif rsi > self.settings['rsi_overbought']:
                    confirms = 0
                    if not self.settings['use_ema_filter'] or not above_ema:
                        confirms += 1
                    if not self.settings['use_adx_filter'] or low_adx:
                        confirms += 1
                    if not self.settings['use_volume_confirm'] or high_volume:
                        confirms += 1
                    if not self.settings['use_divergence'] or divergence == 'BEARISH':
                        confirms += 1
                    
                    if confirms >= 2:
                        if self.settings['use_atr_stops'] and not pd.isna(atr) and atr > 0:
                            initial_sl = price + (atr * self.settings['atr_stop_mult'])
                            trailing_dist = atr * self.settings['atr_trailing_mult']
                        else:
                            initial_sl = price * (1 + self.settings['stop_loss'] / 100)
                            trailing_dist = price * self.settings['trailing_stop_pct'] / 100
                        
                        self.position = {
                            'type': 'SHORT',
                            'entry': price,
                            'size': self.capital * self.settings['position_size'] / 100,
                            'sl': initial_sl,
                            'trailing_dist': trailing_dist,
                        }
                        self.lowest = price
                        self.candles_since_update = 0
            
            else:
                # Update trailing stop
                self.candles_since_update += 1
                if self.candles_since_update >= self.settings['trailing_check_interval']:
                    self.candles_since_update = 0
                    
                    if self.position['type'] == 'LONG':
                        self.highest = max(self.highest, row['High'])
                        self.position['sl'] = self.highest - self.position['trailing_dist']
                    else:
                        self.lowest = min(self.lowest, row['Low'])
                        self.position['sl'] = self.lowest + self.position['trailing_dist']
                
                # EXIT
                exit_p = None
                reason = None
                
                if self.position['type'] == 'LONG':
                    if row['Low'] <= self.position['sl']:
                        exit_p = self.position['sl']
                        reason = 'Trailing SL (ATR)'
                    elif not pd.isna(row['rsi']) and row['rsi'] > 50:
                        exit_p = price
                        reason = 'RSI'
                else:
                    if row['High'] >= self.position['sl']:
                        exit_p = self.position['sl']
                        reason = 'Trailing SL (ATR)'
                    elif not pd.isna(row['rsi']) and row['rsi'] < 50:
                        exit_p = price
                        reason = 'RSI'
                
                if exit_p:
                    pnl_pct = (exit_p - self.position['entry']) / self.position['entry'] * 100 if self.position['type'] == 'LONG' else (self.position['entry'] - exit_p) / self.position['entry'] * 100
                    pnl = self.position['size'] * pnl_pct / 100
                    self.capital += pnl
                    self.peak = max(self.peak, self.capital)
                    self.pnl += pnl
                    self.total += 1
                    if pnl > 0:
                        self.wins += 1
                    
                    self.trades.append({
                        'entry': self.position['entry'],
                        'exit': exit_p,
                        'pnl': pnl,
                        'reason': reason,
                    })
                    
                    self.position = None
        
        return self.stats()
    
    def stats(self):
        wr = self.wins / self.total * 100 if self.total > 0 else 0
        dd = (self.capital - self.peak) / self.peak * 100
        return {'capital': self.capital, 'pnl': self.pnl, 'trades': self.total, 'wins': self.wins, 'wr': wr, 'dd': dd}

# ============================================================================
# WALK-FORWARD
# ============================================================================
def run_wf(df):
    total = len(df)
    train_c = TRAIN_DAYS * 24 * 60
    test_c = TEST_DAYS * 24 * 60
    
    if total < train_c + test_c:
        return None
    
    windows = []
    idx = 0
    window_num = 0
    
    log(f"Running WF: {total:,} candles, {TRAIN_DAYS}d/{TEST_DAYS}d")
    
    while idx + train_c + test_c <= total:
        window_num += 1
        test_df = df.iloc[idx + train_c:idx + train_c + test_c].copy()
        
        t = TraderV3Optimized(BOT_SETTINGS)
        stats = t.run_on_df(test_df)
        
        if stats['trades'] > 0:
            windows.append({
                'window': window_num,
                'start': str(test_df.index[0]),
                'end': str(test_df.index[-1]),
                'trades': stats['trades'],
                'wr': stats['wr'],
                'pnl': stats['pnl'],
                'ret': (stats['capital'] - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100,
                'dd': stats['dd'],
            })
        
        idx += test_c
        
        if window_num % 5 == 0:
            log(f"  Completed {window_num} windows...")
    
    return windows

# ============================================================================
# MAIN
# ============================================================================
windows = run_wf(df)

if not windows:
    log("❌ No successful windows")
    import sys
    sys.exit(1)

# ============================================================================
# RESULTS
# ============================================================================
log("")
log("="*70)
log("📊 RESULTS - V3 MULTI-METRIC")
log("="*70)

pw = len([w for w in windows if w['pnl'] > 0])
awr = np.mean([w['wr'] for w in windows])
tpnl = sum([w['pnl'] for w in windows])
mindd = min([w['dd'] for w in windows])
total_trades = sum([w['trades'] for w in windows])

log(f"\n📍 BTC/USD (1 Year, 1-Minute, V3 Multi-Metric)")
log(f"   Windows: {len(windows)} | Profitable: {pw}/{len(windows)} ({pw/len(windows)*100:.0f}%)")
log(f"   Total Trades: {total_trades:,}")
log(f"   Avg Win Rate: {awr:.1f}%")
log(f"   Total PnL: ${tpnl:+,.2f}")
log(f"   Max Drawdown: {mindd:.2f}%")

# Window breakdown
log(f"\n📋 WINDOW BREAKDOWN:")
for w in windows[:10]:
    status = "✅" if w['pnl'] > 0 else "❌"
    log(f"   {status} W{w['window']:2d}: {w['trades']:4d} trades, {w['wr']:5.1f}% WR, {w['ret']:+7.2f}% ret, {w['dd']:+6.2f}% DD")

if len(windows) > 10:
    log(f"   ... and {len(windows) - 10} more windows")

log(f"\n{'='*70}")
log("📋 VALIDATION (DD < 20%, WR > 50%)")
log(f"{'='*70}")

if mindd > -20:
    log(f"✅ DD: {mindd:.2f}% (PASS)")
else:
    log(f"❌ DD: {mindd:.2f}% (FAIL)")

if awr >= 50:
    log(f"✅ WR: {awr:.1f}% (PASS)")
else:
    log(f"❌ WR: {awr:.1f}% (FAIL)")

if tpnl > 0:
    log(f"✅ PnL: ${tpnl:+,.2f} (PASS)")
else:
    log(f"❌ PnL: ${tpnl:+,.2f} (FAIL)")

log(f"\n{'='*70}")
log("✅ COMPLETE!")
log(f"{'='*70}")

# Save
summary = {
    'strategy': 'V3 Multi-Metric',
    'asset': 'BTC/USD',
    'timeframe': '1m',
    'period': '1 year',
    'windows': len(windows),
    'trades': total_trades,
    'win_rate': float(awr),
    'pnl': float(tpnl),
    'drawdown': float(mindd),
    'profitable_windows': pw,
    'settings': BOT_SETTINGS,
}

with open(f"{DATA_DIR}/summary.json", 'w') as f:
    json.dump(summary, f, indent=2)

with open(f"{DATA_DIR}/windows.json", 'w') as f:
    json.dump(windows, f, indent=2)

log(f"\n📁 Saved: {DATA_DIR}/")

# Comparison with V2
log(f"\n{'='*70}")
log("📊 COMPARISON: V2 vs V3")
log(f"{'='*70}")

v2 = {'wr': 64.8, 'pnl': 9.13, 'dd': -0.52, 'trades': 15284}

log(f"\n{'Metric':<15} | {'V2':<12} | {'V3':<12} | {'Change':<10}")
log("-"*65)
log(f"{'Win Rate':<15} | {v2['wr']:>9.1f}%   | {awr:>9.1f}%   | {awr - v2['wr']:>+7.1f}%")
log(f"{'Total PnL':<15} | ${v2['pnl']:>9.2f}  | ${tpnl:>9.2f}  | ${tpnl - v2['pnl']:>+8.2f}")
log(f"{'Max Drawdown':<15} | {v2['dd']:>9.2f}%   | {mindd:>9.2f}%   | {mindd - v2['dd']:>+7.2f}%")
log(f"{'Total Trades':<15} | {v2['trades']:>9,}  | {total_trades:>9,}  | {total_trades - v2['trades']:>+8,}")

log(f"\n💡 ANALYSIS:")
if awr > v2['wr']:
    log(f"   ✅ Win rate IMPROVED by {awr - v2['wr']:.1f}%")
else:
    log(f"   ⚠️  Win rate decreased by {v2['wr'] - awr:.1f}%")

if tpnl > v2['pnl']:
    log(f"   ✅ Profitability IMPROVED by ${tpnl - v2['pnl']:+.2f}")
else:
    log(f"   ⚠️  Profitability decreased by ${tpnl - v2['pnl']:+.2f}")

if total_trades < v2['trades']:
    reduction = (v2['trades'] - total_trades) / v2['trades'] * 100
    log(f"   ✅ Trade frequency REDUCED by {reduction:.1f}% (higher quality)")

log(f"\n{'='*70}")
