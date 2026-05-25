#!/usr/bin/env python3
"""
Paper Trading Bot: Multi-Pair Mode
Runs validated bot settings on ZECUSDT, ENAUSDT, KATUSDT, TAOUSDT
No real orders - simulation only
"""

import sys
sys.path.insert(0, '/mnt/data/hermes/workspace/.local/lib/python3.13/site-packages')

# Force unbuffered output
sys.stdout.flush()

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import json
import os

# ============================================================================
# CONFIGURATION
# ============================================================================
# Pairs and their exchanges
PAIRS_CONFIG = {
    'ZEC/USDT': 'okx',
    'ENA/USDT': 'okx',
    'KAS/USDT': 'gateio',
    'TAO/USDT': 'gateio',
}
TIMEFRAME = '1m'

# Validated Bot Settings
BOT_SETTINGS = {
    'rsi_oversold': 25,
    'rsi_overbought': 75,
    'take_profit': 0.8,  # 0.8%
    'stop_loss': 1.0,    # 1.0%
    'position_size': 7,  # 7% of capital
    'max_drawdown': 20,  # 20% max
}

# Paper Trading Settings
INITIAL_CAPITAL = 10000  # $10,000 per pair
DATA_DIR = '/mnt/data/hermes/workspace/crypto_bot/paper_trading'

# ============================================================================
# SETUP
# ============================================================================
os.makedirs(DATA_DIR, exist_ok=True)

# Initialize exchanges
exchanges = {
    'okx': ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'gateio': ccxt.gateio({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
}

PAIRS = list(PAIRS_CONFIG.keys())

print("="*70)
print("📄 PAPER TRADING BOT: Multi-Pair Mode")
print("="*70)
print()
print(f"Pairs: {', '.join(PAIRS)}")
print(f"Timeframe: {TIMEFRAME}")
for pair, ex in PAIRS_CONFIG.items():
    print(f"  {pair} → {ex.upper()}")
print()
print("Bot Settings (Validated):")
for key, value in BOT_SETTINGS.items():
    print(f"  {key}: {value}")
print()
print(f"Initial Capital: ${INITIAL_CAPITAL:,.2f} per pair")
print(f"Total Capital: ${INITIAL_CAPITAL * len(PAIRS):,.2f}")
print()

# ============================================================================
# UTILITIES
# ============================================================================
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)

def fetch_ohlcv(symbol, timeframe='1m', limit=100):
    """Fetch OHLCV data from appropriate exchange"""
    try:
        ex_name = PAIRS_CONFIG.get(symbol, 'okx')
        ex = exchanges[ex_name]
        ohlcv = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

def format_currency(value):
    return f"${value:,.2f}"

# ============================================================================
# PAPER TRADING ENGINE
# ============================================================================
class PaperTrader:
    def __init__(self, symbol, initial_capital, settings):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.settings = settings
        self.reset()
    
    def reset(self):
        self.capital = self.initial_capital
        self.position = None
        self.peak_capital = self.initial_capital
        self.trades = []
        self.equity_curve = []
        self.pnl = 0
        self.total_trades = 0
        self.wins = 0
    
    def update(self, df):
        """Process latest candle and check for trades"""
        if len(df) < 20:
            return
        
        # Calculate RSI
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
        
        # Entry logic
        if self.position is None:
            if row['rsi'] < self.settings['rsi_oversold']:
                self.position = {
                    'type': 'LONG',
                    'entry': current_price,
                    'size': self.capital * self.settings['position_size'] / 100,
                    'sl': current_price * (1 - self.settings['stop_loss'] / 100),
                    'tp': current_price * (1 + self.settings['take_profit'] / 100),
                    'entry_time': timestamp
                }
            elif row['rsi'] > self.settings['rsi_overbought']:
                self.position = {
                    'type': 'SHORT',
                    'entry': current_price,
                    'size': self.capital * self.settings['position_size'] / 100,
                    'sl': current_price * (1 + self.settings['stop_loss'] / 100),
                    'tp': current_price * (1 - self.settings['take_profit'] / 100),
                    'entry_time': timestamp
                }
        else:
            # Exit logic
            exit_p = None
            exit_reason = None
            
            if self.position['type'] == 'LONG':
                if row['low'] <= self.position['sl']:
                    exit_p = self.position['sl']
                    exit_reason = 'SL'
                elif row['high'] >= self.position['tp']:
                    exit_p = self.position['tp']
                    exit_reason = 'TP'
                elif row['rsi'] > 50:
                    exit_p = current_price
                    exit_reason = 'RSI'
            else:
                if row['high'] >= self.position['sl']:
                    exit_p = self.position['sl']
                    exit_reason = 'SL'
                elif row['low'] <= self.position['tp']:
                    exit_p = self.position['tp']
                    exit_reason = 'TP'
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
                    'exit_reason': exit_reason
                })
                self.position = None
        
        self.equity_curve.append({
            'timestamp': timestamp,
            'equity': self.capital,
            'position': 'LONG' if self.position and self.position['type'] == 'LONG' else 'SHORT' if self.position else 'FLAT'
        })
    
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
# MAIN LOOP
# ============================================================================
print("="*70, flush=True)
print("🚀 Starting Paper Trading...")
print("="*70, flush=True)
print()

# Initialize traders
traders = {}
for pair in PAIRS:
    traders[pair] = PaperTrader(pair, INITIAL_CAPITAL, BOT_SETTINGS)
    print(f"✅ Initialized {pair}: ${INITIAL_CAPITAL:,.2f}", flush=True)

print()
print("Monitoring markets... (Press Ctrl+C to stop)", flush=True)
print()

# Run loop
iteration = 0
try:
    while True:
        iteration += 1
        start_time = time.time()
        
        # Fetch and update all pairs
        for pair in PAIRS:
            df = fetch_ohlcv(pair, TIMEFRAME, limit=100)
            if df is not None:
                traders[pair].update(df)
        
        # Print status every 60 seconds
        if iteration % 60 == 0:
            sys.stdout.flush()
            print("="*70, flush=True)
            print(f"📊 Paper Trading Status: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*70)
            print()
            
            total_capital = 0
            total_pnl = 0
            total_trades = 0
            total_wins = 0
            
            for pair in PAIRS:
                stats = traders[pair].get_stats()
                total_capital += stats['capital']
                total_pnl += stats['pnl']
                total_trades += stats['total_trades']
                total_wins += stats['wins']
                
                pos = "LONG" if stats['position'] and stats['position']['type'] == 'LONG' else \
                      "SHORT" if stats['position'] else "FLAT"
                
                print(f"{pair}:")
                print(f"  Capital: {format_currency(stats['capital'])} | PnL: {format_currency(stats['pnl']):>10} ({stats['pnl']/INITIAL_CAPITAL*100:+.2f}%)")
                print(f"  Trades: {stats['total_trades']} | WR: {stats['win_rate']:.1f}% | DD: {stats['max_dd']:.2f}%")
                print(f"  Position: {pos}")
                print()
            
            print("-" * 70, flush=True)
            print(f"TOTAL:", flush=True)
            print(f"  Capital: {format_currency(total_capital)} / {format_currency(INITIAL_CAPITAL * len(PAIRS))}")
            print(f"  Total PnL: {format_currency(total_pnl)} ({total_pnl/(INITIAL_CAPITAL * len(PAIRS))*100:+.2f}%)")
            print(f"  Total Trades: {total_trades} | Win Rate: {total_wins/total_trades*100 if total_trades > 0 else 0:.1f}%")
            print("="*70)
            print()
        
        # Save state every 5 minutes
        if iteration % 300 == 0:
            state = {
                'timestamp': datetime.now().isoformat(),
                'pairs': {}
            }
            for pair in PAIRS:
                stats = traders[pair].get_stats()
                state['pairs'][pair] = stats
                # Save trades to CSV
                if traders[pair].trades:
                    trades_df = pd.DataFrame(traders[pair].trades)
                    trades_df.to_csv(f"{DATA_DIR}/{pair.replace('/', '')}_trades.csv", index=False)
            
            with open(f"{DATA_DIR}/state.json", 'w') as f:
                json.dump(state, f, indent=2, default=str)
        
        # Wait for next candle
        elapsed = time.time() - start_time
        sleep_time = max(0, 60 - elapsed)
        time.sleep(sleep_time)

except KeyboardInterrupt:
    print()
    print("="*70)
    print("⏹️  Paper Trading Stopped")
    print("="*70)

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# Final summary
print()
print("="*70)
print("📊 FINAL PAPER TRADING SUMMARY")
print("="*70)
print()

total_capital = 0
total_pnl = 0

for pair in PAIRS:
    stats = traders[pair].get_stats()
    total_capital += stats['capital']
    total_pnl += stats['pnl']
    
    print(f"{pair}:")
    print(f"  Final Capital: {format_currency(stats['capital'])}")
    print(f"  PnL: {format_currency(stats['pnl'])} ({stats['pnl']/INITIAL_CAPITAL*100:+.2f}%)")
    print(f"  Trades: {stats['total_trades']} | Win Rate: {stats['win_rate']:.1f}%")
    print(f"  Max DD: {stats['max_dd']:.2f}%")
    print()

print("-" * 70)
print(f"TOTAL:")
print(f"  Initial: {format_currency(INITIAL_CAPITAL * len(PAIRS))}")
print(f"  Final: {format_currency(total_capital)}")
print(f"  Total PnL: {format_currency(total_pnl)} ({total_pnl/(INITIAL_CAPITAL * len(PAIRS))*100:+.2f}%)")
print("="*70)
print()
print(f"Trade logs saved to: {DATA_DIR}/")
print()
