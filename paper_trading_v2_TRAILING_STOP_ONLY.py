#!/usr/bin/env python3
"""
Paper Trading Bot: Multi-Pair Mode (with enhanced logging)
Runs validated bot settings on ZECUSDT, ENAUSDT, KATUSDT, TAOUSDT
"""

import sys
sys.path.insert(0, '/mnt/data/hermes/workspace/.local/lib/python3.13/site-packages')

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
PAIRS_CONFIG = {
    'ZEC/USDT': 'okx',
    'ENA/USDT': 'okx',
    'KAS/USDT': 'gateio',
    'TAO/USDT': 'gateio',
}
TIMEFRAME = '1m'

# STOP LOSS METHOD: 'fixed', 'trailing_continuous', 'trailing_interval'
STOP_METHOD = 'trailing_interval'

BOT_SETTINGS = {
    'rsi_oversold': 25,
    'rsi_overbought': 75,
    'take_profit': 0.8,
    'stop_loss': 1.0,
    'position_size': 7,
    'max_drawdown': 20,
    
    # TRAILING STOP SETTINGS
    'trailing_stop_pct': 1.0,        # 1% trailing distance
    'trailing_check_interval': 5,    # Update stop every 5 candles
}

INITIAL_CAPITAL = 10000
DATA_DIR = '/mnt/data/hermes/workspace/crypto_bot/paper_trading'
os.makedirs(DATA_DIR, exist_ok=True)

# Initialize exchanges
exchanges = {
    'okx': ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
    'gateio': ccxt.gateio({'enableRateLimit': True, 'options': {'defaultType': 'spot'}}),
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
class PaperTrader:
    def __init__(self, symbol, initial_capital, settings):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.settings = settings
        self.stop_method = STOP_METHOD
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
        """Update trailing stop loss based on method"""
        if self.position is None:
            return
        
        if self.stop_method == 'fixed':
            # Fixed stop loss - never moves
            self.current_stop = self.position['initial_sl']
        
        elif self.stop_method == 'trailing_continuous':
            # Update stop on EVERY candle based on highest price
            if self.position['type'] == 'LONG':
                self.highest_price = max(self.highest_price, row['high'])
                self.current_stop = self.highest_price * (1 - self.settings['trailing_stop_pct'] / 100)
            else:  # SHORT
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
        
        current_dd = (self.capital - self.peak_capital) / self.peak_capital * 100
        if current_dd <= -self.settings['max_drawdown']:
            return
        
        if self.position is None:
            if row['rsi'] < self.settings['rsi_oversold']:
                initial_sl = current_price * (1 - self.settings['stop_loss'] / 100)
                initial_tp = current_price * (1 + self.settings['take_profit'] / 100)
                self.position = {
                    'type': 'LONG', 'entry': current_price,
                    'size': self.capital * self.settings['position_size'] / 100,
                    'initial_sl': initial_sl,
                    'initial_tp': initial_tp,
                    'entry_time': timestamp
                }
                # Initialize trailing stop
                self.highest_price = current_price
                self.current_stop = initial_sl
                self.candles_since_entry = 0
                self.candles_since_update = 0
            elif row['rsi'] > self.settings['rsi_overbought']:
                initial_sl = current_price * (1 + self.settings['stop_loss'] / 100)
                initial_tp = current_price * (1 - self.settings['take_profit'] / 100)
                self.position = {
                    'type': 'SHORT', 'entry': current_price,
                    'size': self.capital * self.settings['position_size'] / 100,
                    'initial_sl': initial_sl,
                    'initial_tp': initial_tp,
                    'entry_time': timestamp
                }
                self.highest_price = current_price
                self.current_stop = initial_sl
                self.candles_since_entry = 0
                self.candles_since_update = 0
        else:
            # Update trailing stop before checking exits
            self.update_stop_loss(row)
            self.candles_since_entry += 1
            
            exit_p = None
            exit_reason = None
            
            if self.position['type'] == 'LONG':
                if row['low'] <= self.current_stop:
                    exit_p = self.current_stop
                    if self.stop_method == 'fixed':
                        exit_reason = 'Fixed SL'
                    else:
                        exit_reason = f'Trailing SL ({self.settings["trailing_stop_pct"]}%)'
                elif self.stop_method == 'fixed' and row['high'] >= self.position['initial_tp']:
                    exit_p = self.position['initial_tp']
                    exit_reason = 'Fixed TP'
                elif row['rsi'] > 50:
                    exit_p = current_price
                    exit_reason = 'RSI'
            else:
                if row['high'] >= self.current_stop:
                    exit_p = self.current_stop
                    if self.stop_method == 'fixed':
                        exit_reason = 'Fixed SL'
                    else:
                        exit_reason = f'Trailing SL ({self.settings["trailing_stop_pct"]}%)'
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
                
                # Log trade
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
# MAIN
# ============================================================================
log("="*70)
log("📄 PAPER TRADING BOT: Multi-Pair Mode")
log("="*70)
log(f"Pairs: {', '.join(PAIRS)}")
for pair, ex in PAIRS_CONFIG.items():
    log(f"  {pair} → {ex.upper()}")
log(f"Initial Capital: ${INITIAL_CAPITAL*len(PAIRS):,.2f} total")
log("")

traders = {}
for pair in PAIRS:
    traders[pair] = PaperTrader(pair, INITIAL_CAPITAL, BOT_SETTINGS)
    log(f"✅ Initialized {pair}")

log(" ")
log("🚀 Starting paper trading...")
log(" ")

iteration = 0
last_status = 0

try:
    while True:
        iteration += 1
        start_time = time.time()
        
        # Fetch and update all pairs
        for pair in PAIRS:
            df = fetch_ohlcv(pair, TIMEFRAME, limit=100)
            if df is not None:
                traders[pair].update(df)
        
        # Status every minute
        if iteration % 60 == 0:
            log("="*50)
            log(f"📊 Status Update (Iteration {iteration})")
            log("="*50)
            
            total_cap = 0
            total_pnl = 0
            total_trades = 0
            
            for pair in PAIRS:
                stats = traders[pair].get_stats()
                total_cap += stats['capital']
                total_pnl += stats['pnl']
                total_trades += stats['total_trades']
                
                pos = "LONG" if stats['position'] and stats['position']['type'] == 'LONG' else "SHORT" if stats['position'] else "FLAT"
                log(f"{pair}: ${stats['capital']:,.2f} ({stats['pnl']:+,.2f}) | {stats['total_trades']} trades | {stats['win_rate']:.1f}% WR | {pos}")
            
            log("-"*50)
            log(f"TOTAL: ${total_cap:,.2f} / $40,000 | PnL: ${total_pnl:+,.2f} | Trades: {total_trades}")
            log("="*50)
            
            # Save state
            state = {
                'timestamp': datetime.now().isoformat(),
                'iteration': iteration,
                'pairs': {pair: traders[pair].get_stats() for pair in PAIRS}
            }
            with open(f"{DATA_DIR}/state.json", 'w') as f:
                json.dump(state, f, indent=2, default=str)
            
            # Save trades
            for pair in PAIRS:
                if traders[pair].trades:
                    pd.DataFrame(traders[pair].trades).to_csv(f"{DATA_DIR}/{pair.replace('/', '')}_trades.csv", index=False)
        
        # Sleep until next minute
        elapsed = time.time() - start_time
        sleep_time = max(0, 60 - elapsed)
        time.sleep(sleep_time)

except KeyboardInterrupt:
    log()
    log("⏹️  Stopped by user")
except Exception as e:
    log(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Final summary
log("")
log("="*70)
log("📊 FINAL SUMMARY")
log("="*70)

total_cap = 0
for pair in PAIRS:
    stats = traders[pair].get_stats()
    total_cap += stats['capital']
    log(f"{pair}: ${stats['capital']:,.2f} ({stats['pnl']:+,.2f}) | {stats['total_trades']} trades | {stats['win_rate']:.1f}% WR")

log("-"*70)
log(f"TOTAL: ${total_cap:,.2f} / $40,000 ({(total_cap-40000):+,.2f})")
log("="*70)
