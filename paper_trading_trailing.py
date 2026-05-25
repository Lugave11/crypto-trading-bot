#!/usr/bin/env python3
"""
Trailing Stop Loss Implementation for Paper Trading Bot
Three methods: Fixed (current), Trailing (continuous), Trailing (N-candle check)
"""

import sys
sys.path.insert(0, '/mnt/data/hermes/workspace/.local/lib/python3.13/site-packages')

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import time
import json
import os

# ============================================================================
# CONFIGURATION
# ============================================================================
PAIRS_CONFIG = {
    'ZEC/USDT': 'okx',
    'ENA/USDT': 'okx',
}
TIMEFRAME = '1m'

# Choose your stop loss method: 'fixed', 'trailing_continuous', 'trailing_interval'
STOP_METHOD = 'trailing_continuous'

BOT_SETTINGS = {
    'rsi_oversold': 25,
    'rsi_overbought': 75,
    'take_profit': 0.8,    # 0.8%
    'stop_loss': 1.0,      # 1.0%
    'position_size': 7,    # 7%
    'max_drawdown': 20,
    
    # TRAILING STOP SETTINGS
    'trailing_stop_pct': 1.0,        # 1% trailing distance
    'trailing_check_interval': 5,    # Update stop every N candles (if using interval method)
}

INITIAL_CAPITAL = 10000
DATA_DIR = '/mnt/data/hermes/workspace/crypto_bot/paper_trading_trailing'
os.makedirs(DATA_DIR, exist_ok=True)

# Initialize exchanges
exchanges = {
    'okx': ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
}

PAIRS = list(PAIRS_CONFIG.keys())

# ============================================================================
# LOGGING
# ============================================================================
def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {msg}", flush=True)

# ============================================================================
# UTILITIES
# ============================================================================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)

def fetch_ohlcv(symbol, timeframe='1m', limit=100):
    try:
        ex_name = PAIRS_CONFIG.get(symbol, 'okx')
        ex = exchanges[ex_name]
        ohlcv = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        log(f"❌ Error fetching {symbol}: {e}")
        return None

# ============================================================================
# PAPER TRADING ENGINE WITH TRAILING STOP
# ============================================================================
class PaperTraderTrailing:
    def __init__(self, symbol, initial_capital, settings, stop_method='trailing_continuous'):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.settings = settings
        self.stop_method = stop_method
        self.reset()
    
    def reset(self):
        self.capital = self.initial_capital
        self.position = None
        self.peak_capital = self.initial_capital
        self.trades = []
        self.pnl = 0
        self.total_trades = 0
        self.wins = 0
        
        # Trailing stop specific
        self.highest_price = None
        self.current_stop = None
        self.candles_since_entry = 0
        self.candles_since_update = 0
    
    def update_stop_loss(self, row):
        """
        Update trailing stop loss based on method
        """
        if self.position is None:
            return
        
        if self.stop_method == 'fixed':
            # Fixed stop loss - never moves
            self.current_stop = self.position['initial_sl']
        
        elif self.stop_method == 'trailing_continuous':
            # Update stop on EVERY candle based on highest price
            if self.position['type'] == 'LONG':
                # For LONG: trail below highest high
                self.highest_price = max(self.highest_price, row['high'])
                self.current_stop = self.highest_price * (1 - self.settings['trailing_stop_pct'] / 100)
            else:  # SHORT
                # For SHORT: trail above lowest low
                self.highest_price = min(self.highest_price, row['low']) if self.highest_price else row['low']
                self.current_stop = self.highest_price * (1 + self.settings['trailing_stop_pct'] / 100)
        
        elif self.stop_method == 'trailing_interval':
            # Update stop only every N candles
            self.candles_since_update += 1
            if self.candles_since_update >= self.settings['trailing_check_interval']:
                self.candles_since_update = 0
                if self.position['type'] == 'LONG':
                    self.highest_price = max(self.highest_price, row['high'])
                    self.current_stop = self.highest_price * (1 - self.settings['trailing_stop_pct'] / 100)
                else:  # SHORT
                    self.highest_price = min(self.highest_price, row['low']) if self.highest_price else row['low']
                    self.current_stop = self.highest_price * (1 + self.settings['trailing_stop_pct'] / 100)
    
    def update(self, df):
        if len(df) < 20:
            return
        
        df['rsi'] = rsi(df['close'])
        row = df.iloc[-1]
        
        if pd.isna(row['rsi']):
            return
        
        current_price = row['close']
        timestamp = row.name
        
        # Check drawdown
        current_dd = (self.capital - self.peak_capital) / self.peak_capital * 100
        if current_dd <= -self.settings['max_drawdown']:
            return
        
        # ENTRY LOGIC
        if self.position is None:
            if row['rsi'] < self.settings['rsi_oversold']:
                # Calculate initial stop and take profit
                initial_sl = current_price * (1 - self.settings['stop_loss'] / 100)
                initial_tp = current_price * (1 + self.settings['take_profit'] / 100)
                
                self.position = {
                    'type': 'LONG',
                    'entry': current_price,
                    'size': self.capital * self.settings['position_size'] / 100,
                    'initial_sl': initial_sl,  # Fixed SL reference
                    'initial_tp': initial_tp,  # Fixed TP reference
                    'entry_time': timestamp
                }
                
                # Initialize trailing stop
                self.highest_price = current_price
                if self.stop_method == 'fixed':
                    self.current_stop = initial_sl
                else:
                    self.current_stop = initial_sl  # Start at fixed SL, then trail
                
                self.candles_since_entry = 0
                self.candles_since_update = 0
                
            elif row['rsi'] > self.settings['rsi_overbought']:
                initial_sl = current_price * (1 + self.settings['stop_loss'] / 100)
                initial_tp = current_price * (1 - self.settings['take_profit'] / 100)
                
                self.position = {
                    'type': 'SHORT',
                    'entry': current_price,
                    'size': self.capital * self.settings['position_size'] / 100,
                    'initial_sl': initial_sl,
                    'initial_tp': initial_tp,
                    'entry_time': timestamp
                }
                
                self.highest_price = current_price
                if self.stop_method == 'fixed':
                    self.current_stop = initial_sl
                else:
                    self.current_stop = initial_sl
                
                self.candles_since_entry = 0
                self.candles_since_update = 0
        
        else:
            # Update trailing stop
            self.update_stop_loss(row)
            self.candles_since_entry += 1
            
            exit_p = None
            exit_reason = None
            
            if self.position['type'] == 'LONG':
                # Check stop loss (trailing or fixed)
                if row['low'] <= self.current_stop:
                    exit_p = self.current_stop
                    exit_reason = f'Trail SL ({self.settings["trailing_stop_pct"]}%)' if self.stop_method != 'fixed' else 'Fixed SL'
                
                # Check take profit (only for fixed method)
                elif self.stop_method == 'fixed' and row['high'] >= self.position['initial_tp']:
                    exit_p = self.position['initial_tp']
                    exit_reason = 'Fixed TP'
                
                # RSI exit
                elif row['rsi'] > 50:
                    exit_p = current_price
                    exit_reason = 'RSI'
            
            else:  # SHORT
                if row['high'] >= self.current_stop:
                    exit_p = self.current_stop
                    exit_reason = f'Trail SL ({self.settings["trailing_stop_pct"]}%)' if self.stop_method != 'fixed' else 'Fixed SL'
                
                elif self.stop_method == 'fixed' and row['low'] <= self.position['initial_tp']:
                    exit_p = self.position['initial_tp']
                    exit_reason = 'Fixed TP'
                
                elif row['rsi'] < 50:
                    exit_p = current_price
                    exit_reason = 'RSI'
            
            if exit_p:
                pnl_pct = (exit_p - self.position['entry']) / self.position['entry'] * 100 if self.position['type'] == 'LONG' else (self.position['entry'] - exit_p) / self.position['entry'] * 100
                pnl_usd = self.position['size'] * pnl_pct / 100
                self.capital += pnl_usd
                self.peak_capital = max(self.peak_capital, self.capital)
                self.pnl += pnl_usd
                self.total_trades += 1
                if pnl_usd > 0:
                    self.wins += 1
                
                self.trades.append({
                    'timestamp': timestamp,
                    'type': self.position['type'],
                    'entry': self.position['entry'],
                    'exit': exit_p,
                    'pnl_pct': pnl_pct,
                    'pnl_usd': pnl_usd,
                    'exit_reason': exit_reason,
                    'stop_method': self.stop_method,
                    'candles_held': self.candles_since_entry
                })
                
                # Log trade with trailing stop info
                if self.stop_method != 'fixed':
                    log(f"💰 {self.symbol}: {self.position['type']} | Entry: ${self.position['entry']:.4f} → Exit: ${exit_p:.4f} | PnL: ${pnl_usd:+.2f} ({pnl_pct:+.2f}%) [{exit_reason}] | Held: {self.candles_since_entry}c")
                else:
                    log(f"💰 {self.symbol}: {self.position['type']} | Entry: ${self.position['entry']:.4f} → Exit: ${exit_p:.4f} | PnL: ${pnl_usd:+.2f} ({pnl_pct:+.2f}%) [{exit_reason}]")
                
                self.position = None
    
    def get_stats(self):
        wr = self.wins / self.total_trades * 100 if self.total_trades > 0 else 0
        dd = (self.capital - self.peak_capital) / self.peak_capital * 100 if self.peak_capital > 0 else 0
        return {
            'capital': self.capital,
            'pnl': self.pnl,
            'total_trades': self.total_trades,
            'wins': self.wins,
            'win_rate': wr,
            'max_dd': dd,
            'position': self.position
        }

# ============================================================================
# MAIN - TEST DIFFERENT METHODS
# ============================================================================
log("="*70)
log("📊 TRAILING STOP LOSS COMPARISON")
log("="*70)
log("")
log(f"Testing on: {', '.join(PAIRS)}")
log(f"Stop Methods: Fixed vs Trailing (continuous) vs Trailing (5-candle)")
log("")

# Test all three methods
methods = ['fixed', 'trailing_continuous', 'trailing_interval']
results = {}

for method in methods:
    log(f"Testing {method}...")
    
    # Reset traders for this method
    traders = {}
    for pair in PAIRS:
        traders[pair] = PaperTraderTrailing(pair, INITIAL_CAPITAL, BOT_SETTINGS, stop_method=method)
    
    # Run for N iterations (simulate trading)
    iterations = 300  # 5 hours of 1-minute data
    for i in range(iterations):
        for pair in PAIRS:
            df = fetch_ohlcv(pair, TIMEFRAME, limit=100)
            if df is not None:
                traders[pair].update(df)
        
        # Small delay to avoid rate limits
        if i % 50 == 0:
            time.sleep(0.1)
    
    # Aggregate results
    total_cap = sum(traders[pair].get_stats()['capital'] for pair in PAIRS)
    total_pnl = sum(traders[pair].get_stats()['pnl'] for pair in PAIRS)
    total_trades = sum(traders[pair].get_stats()['total_trades'] for pair in PAIRS)
    total_wins = sum(traders[pair].get_stats()['wins'] for pair in PAIRS)
    
    results[method] = {
        'total_capital': total_cap,
        'total_pnl': total_pnl,
        'total_trades': total_trades,
        'win_rate': total_wins / total_trades * 100 if total_trades > 0 else 0,
        'traders': {pair: traders[pair].get_stats() for pair in PAIRS}
    }
    
    log(f"  {method}: {total_trades} trades, {results[method]['win_rate']:.1f}% WR, PnL: ${total_pnl:+.2f}")

log("")
log("="*70)
log("📊 COMPARISON RESULTS")
log("="*70)
log("")

print(f"{'Method':<25s} {'Trades':>8s} {'Win Rate':>10s} {'Total PnL':>12s} {'Final Capital':>15s}")
print("-"*70)

for method in methods:
    r = results[method]
    print(f"{method:<25s} {r['total_trades']:>8d} {r['win_rate']:>9.1f}% ${r['total_pnl']:>+10.2f} ${r['total_capital']:>13.2f}")

print("-"*70)

# Find best
best_method = max(results, key=lambda x: results[x]['total_pnl'])
log("")
log(f"🏆 BEST METHOD: {best_method}")
log(f"   PnL: ${results[best_method]['total_pnl']:+.2f}")
log(f"   Win Rate: {results[best_method]['win_rate']:.1f}%")
log("")

if best_method != 'fixed':
    improvement = results[best_method]['total_pnl'] - results['fixed']['total_pnl']
    log(f"💡 Trailing stop improved performance by ${improvement:+.2f} vs fixed stop loss!")
else:
    log("📊 Fixed stop loss performed best in this test period.")

log("")
log("="*70)
