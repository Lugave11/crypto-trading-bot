#!/usr/bin/env python3
"""
Paper Trading Bot V4 - PROFITABLE MEAN REVERSION
Saves state every iteration for real-time monitoring
"""

import sys
sys.path.insert(0, '/mnt/data/hermes/workspace/.local/lib/python3.13/site-packages')

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import time
import os
import json

# ============================================================================
# CONFIGURATION
# ============================================================================
PAIRS = ['ZEC/USDT', 'ENA/USDT']
TIMEFRAME = '1m'
INITIAL_CAPITAL = 10000
DATA_DIR = '/mnt/data/hermes/workspace/crypto_bot/paper_trading_v3'
os.makedirs(DATA_DIR, exist_ok=True)

# STRATEGY SETTINGS
RSI_PERIOD = 14
RSI_LONG = 25
RSI_SHORT = 75
RSI_EXIT = 50
EMA_PERIOD = 50
ATR_PERIOD = 14
ATR_STOP_MULT = 3.0
ATR_TP_MULT = 2.0
POSITION_SIZE_PCT = 5

# ============================================================================
# LOGGING
# ============================================================================
def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {msg}", flush=True)

# ============================================================================
# INDICATORS
# ============================================================================
def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close'].shift(1)
    tr1 = high - low
    tr2 = abs(high - close)
    tr3 = abs(low - close)
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# ============================================================================
# TRADER
# ============================================================================
class Trader:
    def __init__(self, symbol, initial_capital):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None
        self.trades = []
        self.pnl = 0
        self.wins = 0
        self.df = pd.DataFrame()
        
    def process_candle(self, candle):
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        new_row = pd.DataFrame([candle], columns=cols)
        new_row.set_index('timestamp', inplace=True)
        self.df = pd.concat([self.df, new_row])
        if len(self.df) > 300:
            self.df = self.df.tail(300)
        
        if len(self.df) < 100:
            return
        
        self.check_exit()
        if self.position is None:
            self.check_entry()
    
    def check_entry(self):
        df = self.df.copy()
        df['rsi'] = calculate_rsi(df['close'], RSI_PERIOD)
        df['ema'] = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
        df['atr'] = calculate_atr(df, ATR_PERIOD)
        
        row = df.iloc[-1]
        if pd.isna(row['rsi']) or pd.isna(row['ema']) or pd.isna(row['atr']):
            return
        
        close = row['close']
        rsi = row['rsi']
        ema = row['ema']
        atr = row['atr']
        
        if rsi < RSI_LONG and close > ema:
            stop = close - (atr * ATR_STOP_MULT)
            tp = close + (atr * ATR_TP_MULT)
            self.enter('LONG', close, stop, tp, atr)
        elif rsi > RSI_SHORT and close < ema:
            stop = close + (atr * ATR_STOP_MULT)
            tp = close - (atr * ATR_TP_MULT)
            self.enter('SHORT', close, stop, tp, atr)
    
    def enter(self, side, entry, stop, tp, atr):
        size = self.capital * POSITION_SIZE_PCT / 100
        self.position = {'side': side, 'entry': entry, 'stop': stop, 'tp': tp, 'size': size, 'atr': atr}
        log(f"🎯 {self.symbol}: {side} @ ${entry:.4f} | Stop: ${stop:.4f} | TP: ${tp:.4f}")
    
    def check_exit(self):
        if not self.position:
            return
        
        row = self.df.iloc[-1]
        high, low, close = row['high'], row['low'], row['close']
        pos = self.position
        exit_price, reason = None, None
        
        if pos['side'] == 'LONG':
            if low <= pos['stop']:
                exit_price, reason = pos['stop'], 'Stop Loss'
            elif high >= pos['tp']:
                exit_price, reason = pos['tp'], 'Take Profit'
            elif calculate_rsi(self.df['close'].tail(14), 14).iloc[-1] > RSI_EXIT:
                exit_price, reason = close, 'RSI Exit'
        else:
            if high >= pos['stop']:
                exit_price, reason = pos['stop'], 'Stop Loss'
            elif low <= pos['tp']:
                exit_price, reason = pos['tp'], 'Take Profit'
            elif calculate_rsi(self.df['close'].tail(14), 14).iloc[-1] < RSI_EXIT:
                exit_price, reason = close, 'RSI Exit'
        
        if exit_price:
            self.exit(exit_price, reason)
    
    def exit(self, price, reason):
        pos = self.position
        pnl_pct = (price - pos['entry']) / pos['entry'] * 100 if pos['side'] == 'LONG' else (pos['entry'] - price) / pos['entry'] * 100
        pnl_usd = pos['size'] * pnl_pct / 100
        self.capital += pnl_usd
        self.pnl += pnl_usd
        if pnl_usd > 0:
            self.wins += 1
        
        self.trades.append({'timestamp': datetime.now().isoformat(), 'type': pos['side'], 'entry': pos['entry'], 'exit': price, 'pnl_pct': pnl_pct, 'pnl_usd': pnl_usd, 'reason': reason})
        log(f"💰 {self.symbol}: {pos['side']} | {pos['entry']:.4f} → {price:.4f} | PnL: ${pnl_usd:+.2f} ({pnl_pct:+.2f}%) [{reason}]")
        self.position = None
    
    def get_stats(self):
        wr = self.wins / len(self.trades) * 100 if self.trades else 0
        return {'capital': self.capital, 'pnl': self.pnl, 'trades': len(self.trades), 'wins': self.wins, 'win_rate': wr, 'position': self.position}

# ============================================================================
# MAIN
# ============================================================================
log("="*70)
log("🚀 BOT V4 - PROFITABLE MEAN REVERSION")
log("="*70)
log(f"Pairs: {', '.join(PAIRS)} | Capital: ${INITIAL_CAPITAL*len(PAIRS):,}")
log(f"Strategy: RSI({RSI_PERIOD}) mean reversion + EMA{EMA_PERIOD} filter")
log(f"Stops: {ATR_STOP_MULT}x ATR | Target: {ATR_TP_MULT}x ATR")
log("")

ex = ccxt.okx({'enableRateLimit': True})
traders = {pair: Trader(pair, INITIAL_CAPITAL) for pair in PAIRS}

iteration = 0
while True:
    iteration += 1
    
    for pair in PAIRS:
        try:
            ohlcv = ex.fetch_ohlcv(pair, TIMEFRAME, limit=10)
            if ohlcv:
                candle = ohlcv[-1]
                candle_data = {'timestamp': pd.Timestamp(candle[0], unit='ms'), 'open': candle[1], 'high': candle[2], 'low': candle[3], 'close': candle[4], 'volume': candle[5]}
                traders[pair].process_candle(candle_data)
        except Exception as e:
            log(f"⚠️  {pair}: {e}")
    
    # Save state EVERY iteration
    state = {'timestamp': datetime.now().isoformat(), 'iteration': iteration, 'pairs': {}}
    total_capital, total_trades, total_wins = 0, 0, 0
    
    for pair, t in traders.items():
        stats = t.get_stats()
        state['pairs'][pair] = stats
        total_capital += stats['capital']
        total_trades += stats['trades']
        total_wins += stats['wins']
    
    with open(f"{DATA_DIR}/state.json", 'w') as f:
        json.dump(state, f, indent=2, default=str)
    
    # Save trades
    all_trades = []
    for pair, t in traders.items():
        for trade in t.trades:
            trade['pair'] = pair
            all_trades.append(trade)
    if all_trades:
        pd.DataFrame(all_trades).to_csv(f"{DATA_DIR}/trades.csv", index=False)
    
    # Status log every 10 iterations
    if iteration % 10 == 0:
        total_pnl = total_capital - INITIAL_CAPITAL * len(PAIRS)
        log(f"Iter {iteration:4d} | Capital: ${total_capital:,.2f} | PnL: ${total_pnl:+,.2f} | Trades: {total_trades} | WR: {total_wins/total_trades*100 if total_trades else 0:.1f}%")
    
    time.sleep(60)
