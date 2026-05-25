#!/usr/bin/env python3
"""
Paper Trading Bot V4 - SIMPLIFIED PROFITABLE STRATEGY
Focus: Mean reversion with wider stops, clear profit targets
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
# CONFIGURATION - OPTIMIZED FOR PROFITABILITY
# ============================================================================
PAIRS = ['ZEC/USDT', 'ENA/USDT']
EXCHANGE = 'okx'
TIMEFRAME = '1m'
INITIAL_CAPITAL = 10000
DATA_DIR = '/mnt/data/hermes/workspace/crypto_bot/paper_trading_v3'
os.makedirs(DATA_DIR, exist_ok=True)

# STRATEGY SETTINGS - CONSERVATIVE & PROFITABLE
RSI_PERIOD = 14
RSI_LONG = 25      # Buy when RSI < 25 (oversold)
RSI_SHORT = 75     # Sell when RSI > 75 (overbought)
RSI_EXIT = 50      # Exit when RSI crosses back to 50

EMA_PERIOD = 50    # Trend filter

ATR_PERIOD = 14
ATR_STOP_MULT = 3.0   # 3x ATR stop loss (wide to avoid noise)
ATR_TP_MULT = 2.0     # 2x ATR take profit

POSITION_SIZE_PCT = 5  # 5% of capital per trade

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
        
        # LONG: RSI oversold + price above EMA (uptrend pullback)
        if rsi < RSI_LONG and close > ema:
            stop = close - (atr * ATR_STOP_MULT)
            tp = close + (atr * ATR_TP_MULT)
            self.enter('LONG', close, stop, tp, atr)
        
        # SHORT: RSI overbought + price below EMA (downtrend bounce)
        elif rsi > RSI_SHORT and close < ema:
            stop = close + (atr * ATR_STOP_MULT)
            tp = close - (atr * ATR_TP_MULT)
            self.enter('SHORT', close, stop, tp, atr)
    
    def enter(self, side, entry, stop, tp, atr):
        size = self.capital * POSITION_SIZE_PCT / 100
        self.position = {
            'side': side,
            'entry': entry,
            'stop': stop,
            'tp': tp,
            'size': size,
            'atr': atr,
        }
        log(f"🎯 {self.symbol}: {side} @ ${entry:.4f} | RSI entry | Stop: ${stop:.4f} | TP: ${tp:.4f}")
    
    def check_exit(self):
        if not self.position:
            return
        
        row = self.df.iloc[-1]
        high = row['high']
        low = row['low']
        close = row['close']
        
        pos = self.position
        exit_price = None
        reason = None
        
        if pos['side'] == 'LONG':
            # Hit stop loss
            if low <= pos['stop']:
                exit_price = pos['stop']
                reason = 'Stop Loss'
            # Hit take profit
            elif high >= pos['tp']:
                exit_price = pos['tp']
                reason = 'Take Profit'
            # RSI mean reversion exit
            elif calculate_rsi(self.df['close'].tail(14), 14).iloc[-1] > RSI_EXIT:
                exit_price = close
                reason = 'RSI Exit'
        else:  # SHORT
            # Hit stop loss
            if high >= pos['stop']:
                exit_price = pos['stop']
                reason = 'Stop Loss'
            # Hit take profit
            elif low <= pos['tp']:
                exit_price = pos['tp']
                reason = 'Take Profit'
            # RSI mean reversion exit
            elif calculate_rsi(self.df['close'].tail(14), 14).iloc[-1] < RSI_EXIT:
                exit_price = close
                reason = 'RSI Exit'
        
        if exit_price:
            self.exit(exit_price, reason)
    
    def exit(self, price, reason):
        pos = self.position
        if pos['side'] == 'LONG':
            pnl_pct = (price - pos['entry']) / pos['entry'] * 100
        else:
            pnl_pct = (pos['entry'] - price) / pos['entry'] * 100
        
        pnl_usd = pos['size'] * pnl_pct / 100
        self.capital += pnl_usd
        self.pnl += pnl_usd
        
        if pnl_usd > 0:
            self.wins += 1
        
        self.trades.append({
            'timestamp': datetime.now().isoformat(),
            'type': pos['side'],
            'entry': pos['entry'],
            'exit': price,
            'pnl_pct': pnl_pct,
            'pnl_usd': pnl_usd,
            'reason': reason,
        })
        
        log(f"💰 {self.symbol}: {pos['side']} | {pos['entry']:.4f} → {price:.4f} | PnL: ${pnl_usd:+.2f} ({pnl_pct:+.2f}%) [{reason}]")
        self.position = None
    
    def get_stats(self):
        wr = self.wins / len(self.trades) * 100 if self.trades else 0
        return {
            'capital': self.capital,
            'pnl': self.pnl,
            'trades': len(self.trades),
            'wins': self.wins,
            'win_rate': wr,
            'position': self.position,
        }

# ============================================================================
# MAIN
# ============================================================================
log("="*70)
log("🚀 PAPER TRADING BOT V4 - PROFITABLE MEAN REVERSION")
log("="*70)
log(f"Pairs: {', '.join(PAIRS)}")
log(f"Initial Capital: ${INITIAL_CAPITAL:,}")
log("")
log("Strategy: RSI mean reversion with EMA filter")
log(f"  - Long: RSI < {RSI_LONG} + price > EMA{EMA_PERIOD}")
log(f"  - Short: RSI > {RSI_SHORT} + price < EMA{EMA_PERIOD}")
log(f"  - Stop: {ATR_STOP_MULT}x ATR")
log(f"  - Target: {ATR_TP_MULT}x ATR")
log("")

ex = ccxt.okx({'enableRateLimit': True})
traders = {pair: Trader(pair, INITIAL_CAPITAL) for pair in PAIRS}

log("Starting...")
log("")

iteration = 0
while True:
    iteration += 1
    
    for pair in PAIRS:
        try:
            ohlcv = ex.fetch_ohlcv(pair, TIMEFRAME, limit=10)
            if ohlcv:
                candle = ohlcv[-1]
                candle_data = {
                    'timestamp': pd.Timestamp(candle[0], unit='ms'),
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5],
                }
                traders[pair].process_candle(candle_data)
        except Exception as e:
            log(f"Error {pair}: {e}")
    
    # Status every 60 seconds
    if iteration % 10 == 0:  # Save every 10 minutes instead of 60
        log("="*70)
        log(f"Status (Iteration {iteration})")
        log("="*70)
        
        total_capital = 0
        total_trades = 0
        total_wins = 0
        
        for pair, t in traders.items():
            stats = t.get_stats()
            total_capital += stats['capital']
            total_trades += stats['trades']
            total_wins += stats['wins']
            
            pos = stats['position']
            pos_str = f"{pos['side']} @ ${pos['entry']:.4f}" if pos else "FLAT"
            
            log(f"{pair:15s}: ${stats['capital']:>9.2f} | PnL: ${stats['pnl']:>+8.2f} | Trades: {stats['trades']:3d} | WR: {stats['win_rate']:5.1f}% | {pos_str}")
        
        log("-"*70)
        total_pnl = total_capital - INITIAL_CAPITAL * len(PAIRS)
        log(f"{'TOTAL':15s}: ${total_capital:>9.2f} | PnL: ${total_pnl:>+8.2f} | Trades: {total_trades:3d} | WR: {total_wins/total_trades*100 if total_trades else 0:5.1f}%")
        log("="*70)
        
        # Save state
        state = {
            'timestamp': datetime.now().isoformat(),
            'iteration': iteration,
            'pairs': {pair: traders[pair].get_stats() for pair in PAIRS},
        }
        with open(f"{DATA_DIR}/state.json", 'w') as f:
            json.dump(state, f, indent=2, default=str)
        
        # Save trades
        all_trades = []
        for pair, t in traders.items():
            for trade in t.trades:
                trade['pair'] = pair
                all_trades.append(trade)
        if all_trades:
            df_trades = pd.DataFrame(all_trades)
            df_trades.to_csv(f"{DATA_DIR}/trades.csv", index=False)
    
    time.sleep(60)
