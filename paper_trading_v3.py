#!/usr/bin/env python3
"""
Paper Trading Bot v3: MULTI-METRIC STRATEGY
Enhanced with: ADX, ATR, Volume, EMA, Divergence
Pairs: ZEC/USDT, ENA/USDT, KAS/USDT, TAO/USDT
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
# Using OKX only (more reliable API, better data)
PAIRS_CONFIG = {
    'ZEC/USDT': 'okx',
    'ENA/USDT': 'okx',
}

# Bot Settings v3 - ENHANCED WITH MULTIPLE METRICS
BOT_SETTINGS = {
    # RSI (core)
    'rsi_oversold': 25,
    'rsi_overbought': 75,
    
    # TREND FILTER - 200 EMA
    'use_ema_filter': True,
    'ema_period': 200,
    
    # TREND STRENGTH - ADX
    'use_adx_filter': True,
    'adx_period': 14,
    'adx_max': 25,  # Only trade when ADX < 25 (ranging market)
    
    # VOLATILITY - ATR
    'use_atr_stops': True,
    'atr_period': 14,
    'atr_stop_mult': 1.5,  # Stop loss = 1.5x ATR
    'atr_trailing_mult': 2.0,  # Trailing stop = 2.0x ATR
    
    # VOLUME CONFIRMATION
    'use_volume_confirm': True,
    'volume_period': 20,
    'volume_mult': 1.2,  # Volume must be >1.2x average
    
    # DIVERGENCE DETECTION
    'use_divergence': True,
    'divergence_lookback': 5,  # Look back 5 candles for divergence
    
    # POSITION SIZING
    'position_size': 5,  # 5% of capital per trade
    'max_drawdown': 20,
    
    # LEVERAGE SETTINGS (Hyperliquid)
    'leverage': 1,  # 1x = no leverage, 3x = 3x leverage, 5x = 5x leverage
    'use_leverage': False,  # Set True to enable leverage
    
    # FEES (Hyperliquid)
    'maker_fee': 0.02,  # 0.02% maker (limit orders)
    'taker_fee': 0.05,  # 0.05% taker (market orders)
    'fee_type': 'maker',  # 'maker' or 'taker' - USING MAKER NOW!
    
    # RSI (still core signal)
    'take_profit': 0.8,
    'stop_loss': 1.0,  # Fallback if ATR not available
    'trailing_stop_pct': 1.0,
    'trailing_check_interval': 5,
}

TIMEFRAME = '1m'
INITIAL_CAPITAL = 10000
DATA_DIR = '/mnt/data/hermes/workspace/crypto_bot/paper_trading_v3'
os.makedirs(DATA_DIR, exist_ok=True)

# Initialize exchanges
exchanges = {}
for pair, ex_name in PAIRS_CONFIG.items():
    if ex_name not in exchanges:
        ex_class = getattr(ccxt, ex_name)
        exchanges[ex_name] = ex_class({'enableRateLimit': True})

# ============================================================================
# LOGGING
# ============================================================================
def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {msg}", flush=True)

# ============================================================================
# TECHNICAL INDICATORS
# ============================================================================
def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss)

def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = abs(high - close)
    tr3 = abs(low - close)
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calculate_adx(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    
    # Calculate +DM and -DM
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    # Calculate ATR
    atr = calculate_atr(df, period)
    
    # Calculate +DI and -DI
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    
    # Calculate DX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    
    # Calculate ADX
    adx = dx.rolling(period).mean()
    
    return adx

def calculate_volume_sma(df, period=20):
    return df['volume'].rolling(period).mean()

def detect_divergence(df, rsi_series, lookback=5):
    """Detect bullish or bearish divergence"""
    if len(df) < lookback + 2:
        return None
    
    recent_closes = df['close'].tail(lookback + 1)
    recent_rsi = rsi_series.tail(lookback + 1)
    
    # Bullish divergence: Price makes lower low, RSI makes higher low
    price_low_1 = recent_closes.iloc[-2]
    price_low_2 = recent_closes.iloc[-1]
    rsi_low_1 = recent_rsi.iloc[-2]
    rsi_low_2 = recent_rsi.iloc[-1]
    
    if price_low_2 < price_low_1 and rsi_low_2 > rsi_low_1:
        return 'BULLISH'
    
    # Bearish divergence: Price makes higher high, RSI makes lower high
    price_high_1 = recent_closes.iloc[-2]
    price_high_2 = recent_closes.iloc[-1]
    rsi_high_1 = recent_rsi.iloc[-2]
    rsi_high_2 = recent_rsi.iloc[-1]
    
    if price_high_2 > price_high_1 and rsi_high_2 < rsi_high_1:
        return 'BEARISH'
    
    return None

# ============================================================================
# PAPER TRADING ENGINE V3
# ============================================================================
class PaperTraderV3:
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
        self.pnl = 0
        self.total_trades = 0
        self.wins = 0
        self.highest_price = None
        self.lowest_price = None
        self.candles_since_update = 0
        self.df_history = pd.DataFrame()
    
    def add_candle(self, candle):
        """Add new candle to history"""
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        new_row = pd.DataFrame([candle], columns=cols)
        new_row.set_index('timestamp', inplace=True)
        self.df_history = pd.concat([self.df_history, new_row])
        
        # Keep last 300 candles for indicator calculation
        if len(self.df_history) > 300:
            self.df_history = self.df_history.tail(300)
    
    def get_signals(self):
        """Get multi-metric signals"""
        df = self.df_history.copy()
        
        if len(df) < 200:
            return None, {}
        
        # Calculate all indicators
        df['rsi'] = calculate_rsi(df)
        df['ema200'] = calculate_ema(df, 200)
        df['atr'] = calculate_atr(df, 14)
        df['adx'] = calculate_adx(df, 14)
        df['vol_sma'] = calculate_volume_sma(df, 20)
        
        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        signals = {
            'rsi': row['rsi'],
            'ema200': row['ema200'],
            'atr': row['atr'],
            'adx': row['adx'],
            'volume_ratio': row['volume'] / row['vol_sma'] if row['vol_sma'] > 0 else 0,
            'divergence': detect_divergence(df, df['rsi'], 5),
        }
        
        # Check if price is above/below EMA
        above_ema = row['close'] > row['ema200']
        
        # Check ADX (ranging market)
        low_adx = row['adx'] < self.settings['adx_max']
        
        # Check volume confirmation
        high_volume = signals['volume_ratio'] > self.settings['volume_mult']
        
        # Divergence signal
        div_signal = signals['divergence']
        
        # ENTRY SIGNALS
        long_signal = False
        short_signal = False
        
        # LONG conditions
        if row['rsi'] < self.settings['rsi_oversold']:
            # Check filters
            ema_ok = not self.settings['use_ema_filter'] or above_ema
            adx_ok = not self.settings['use_adx_filter'] or low_adx
            vol_ok = not self.settings['use_volume_confirm'] or high_volume
            div_ok = not self.settings['use_divergence'] or div_signal == 'BULLISH'
            
            # Need at least 2 confirmations
            confirms = sum([ema_ok, adx_ok, vol_ok, div_ok])
            if confirms >= 2:
                long_signal = True
        
        # SHORT conditions
        if row['rsi'] > self.settings['rsi_overbought']:
            # Check filters
            ema_ok = not self.settings['use_ema_filter'] or not above_ema
            adx_ok = not self.settings['use_adx_filter'] or low_adx
            vol_ok = not self.settings['use_volume_confirm'] or high_volume
            div_ok = not self.settings['use_divergence'] or div_signal == 'BEARISH'
            
            # Need at least 2 confirmations
            confirms = sum([ema_ok, adx_ok, vol_ok, div_ok])
            if confirms >= 2:
                short_signal = True
        
        if long_signal:
            return 'LONG', signals
        elif short_signal:
            return 'SHORT', signals
        else:
            return None, signals
    
    def update(self, candle):
        """Process one candle"""
        try:
            self.add_candle(candle)
            
            if len(self.df_history) < 200:
                return
            
            row = self.df_history.iloc[-1]
            current_price = row['close']
            
            # Check drawdown
            current_dd = (self.capital - self.peak_capital) / self.peak_capital * 100
            if current_dd <= -self.settings['max_drawdown']:
                return
            
            # ENTRY
            if self.position is None:
                signal, signals = self.get_signals()
                
                if signal:
                    # Calculate stop loss based on ATR
                    if self.settings['use_atr_stops'] and 'atr' in signals and signals['atr'] and signals['atr'] > 0:
                        atr = signals['atr']
                        if signal == 'LONG':
                            initial_sl = current_price - (atr * self.settings['atr_stop_mult'])
                            trailing_dist = atr * self.settings['atr_trailing_mult']
                        else:  # SHORT
                            initial_sl = current_price + (atr * self.settings['atr_stop_mult'])
                            trailing_dist = atr * self.settings['atr_trailing_mult']
                    else:
                        # Fallback to fixed %
                        if signal == 'LONG':
                            initial_sl = current_price * (1 - self.settings['stop_loss'] / 100)
                            trailing_dist = current_price * self.settings['trailing_stop_pct'] / 100
                        else:
                            initial_sl = current_price * (1 + self.settings['stop_loss'] / 100)
                            trailing_dist = current_price * self.settings['trailing_stop_pct'] / 100
                    
                    # Calculate position size with leverage
                    base_size = self.capital * self.settings['position_size'] / 100
                    leverage = self.settings.get('leverage', 1)
                    use_leverage = self.settings.get('use_leverage', False)
                    effective_size = base_size * leverage if use_leverage else base_size
                    
                    self.position = {
                        'type': signal,
                        'entry': current_price,
                        'size': effective_size,
                        'base_size': base_size,  # Size without leverage
                        'leverage': leverage if use_leverage else 1,
                        'initial_sl': initial_sl,
                        'sl': initial_sl,
                        'trailing_dist': trailing_dist,
                        'signals': signals,
                    }
                    
                    if signal == 'LONG':
                        self.highest_price = current_price
                    else:
                        self.lowest_price = current_price
                    
                    self.candles_since_update = 0
                    log(f"🎯 {self.symbol}: {signal} @ ${current_price:.4f} | RSI: {signals.get('rsi', 'N/A')}, ADX: {signals.get('adx', 'N/A')}, Vol: {signals.get('volume_ratio', 'N/A')}x")
            
            else:
                # Update trailing stop
                self.candles_since_update += 1
                if self.candles_since_update >= self.settings['trailing_check_interval']:
                    self.candles_since_update = 0
                    
                    if self.position['type'] == 'LONG':
                        self.highest_price = max(self.highest_price, row['high'])
                        self.position['sl'] = self.highest_price - self.position['trailing_dist']
                    else:  # SHORT
                        self.lowest_price = min(self.lowest_price, row['low'])
                        self.position['sl'] = self.lowest_price + self.position['trailing_dist']
                
                # EXIT
                exit_p = None
                exit_reason = None
                
                rsi_val = row.get('rsi', 50) if hasattr(row, 'get') else getattr(row, 'rsi', 50)
                
                if self.position['type'] == 'LONG':
                    if row['low'] <= self.position['sl']:
                        exit_p = self.position['sl']
                        exit_reason = f'Trailing SL (ATR)' if self.settings['use_atr_stops'] else 'Trailing SL'
                    elif rsi_val and rsi_val > 50:
                        exit_p = current_price
                        exit_reason = 'RSI'
                else:  # SHORT
                    if row['high'] >= self.position['sl']:
                        exit_p = self.position['sl']
                        exit_reason = f'Trailing SL (ATR)' if self.settings['use_atr_stops'] else 'Trailing SL'
                    elif rsi_val and rsi_val < 50:
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
                        'timestamp': datetime.now().isoformat(),
                        'type': self.position['type'],
                        'entry': self.position['entry'],
                        'exit': exit_p,
                        'pnl_pct': pnl_pct,
                        'pnl_usd': pnl_usd,
                        'exit_reason': exit_reason,
                        'signals': self.position['signals'],
                    })
                    
                    log(f"💰 {self.symbol}: {self.position['type']} | Entry: ${self.position['entry']:.4f} → Exit: ${exit_p:.4f} | PnL: ${pnl_usd:+.2f} ({pnl_pct:+.2f}%) [{exit_reason}]")
                    
                    self.position = None
        except Exception as e:
            log(f"⚠️  Error processing {self.symbol}: {e}")
    
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
        }

# ============================================================================
# MAIN LOOP
# ============================================================================
log("="*70)
log("🚀 PAPER TRADING BOT V3 - MULTI-METRIC STRATEGY")
log("="*70)
log(f"Pairs: {', '.join(PAIRS_CONFIG.keys())}")
log(f"Timeframe: {TIMEFRAME}")
log("")
log("📊 ENHANCED METRICS:")
log(f"  ✅ ADX Filter (max: {BOT_SETTINGS['adx_max']})")
log(f"  ✅ ATR Stops ({BOT_SETTINGS['atr_stop_mult']}x ATR)")
log(f"  ✅ 200 EMA Trend Filter")
log(f"  ✅ Volume Confirmation ({BOT_SETTINGS['volume_mult']}x avg)")
log(f"  ✅ Divergence Detection")
log("")
log("🎯 ENTRY REQUIREMENTS:")
log("  - RSI oversold/overbought")
log("  - At least 2 confirmations from: EMA, ADX, Volume, Divergence")
log("")

# Initialize traders
traders = {}
for pair in PAIRS_CONFIG.keys():
    traders[pair] = PaperTraderV3(pair, INITIAL_CAPITAL, BOT_SETTINGS)
    log(f"✅ Initialized {pair}")

log("")
log("🚀 Starting paper trading...")
log("")

# Main loop
iteration = 0
while True:
    iteration += 1
    
    # Fetch and process each pair
    for pair, ex_name in PAIRS_CONFIG.items():
        try:
            ex = exchanges[ex_name]
            ohlcv = ex.fetch_ohlcv(pair, TIMEFRAME, limit=10)
            
            if ohlcv:
                # Get latest candle
                candle = ohlcv[-1]
                candle_data = {
                    'timestamp': pd.Timestamp(candle[0], unit='ms'),
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5],
                }
                
                traders[pair].update(candle_data)
        except Exception as e:
            log(f"⚠️  Error fetching {pair}: {e}")
    
    # Status update every 60 seconds
    if iteration % 60 == 0:
        log("="*70)
        log(f"📊 Status Update (Iteration {iteration})")
        log("="*70)
        
        total_capital = 0
        total_trades = 0
        total_wins = 0
        
        for pair, trader in traders.items():
            stats = trader.get_stats()
            total_capital += stats['capital']
            total_trades += stats['total_trades']
            total_wins += stats['wins']
            
            position = trader.position
            pos_str = f"{position['type']} @ ${position['entry']:.4f}" if position else "FLAT"
            
            log(f"{pair:15s}: Capital: ${stats['capital']:>9.2f} | PnL: ${stats['pnl']:>+8.2f} | Trades: {stats['total_trades']:3d} | WR: {stats['win_rate']:5.1f}% | Position: {pos_str}")
        
        log("-"*70)
        log(f"{'TOTAL':15s}: Capital: ${total_capital:>9.2f} | PnL: ${total_capital - INITIAL_CAPITAL * len(traders):>+8.2f} | Trades: {total_trades:3d} | WR: {total_wins/total_trades*100 if total_trades > 0 else 0:5.1f}%")
        log("="*70)
        log("")
        
        # Save state
        state = {
            'timestamp': datetime.now().isoformat(),
            'iteration': iteration,
            'pairs': {},
        }
        for pair, trader in traders.items():
            state['pairs'][pair] = {
                'capital': trader.capital,
                'pnl': trader.pnl,
                'trades': trader.total_trades,
                'wins': trader.wins,
                'position': trader.position,
            }
        
        with open(f"{DATA_DIR}/state.json", 'w') as f:
            json.dump(state, f, indent=2)
        
        # Save trade history
        all_trades = []
        for pair, trader in traders.items():
            for trade in trader.trades:
                trade['pair'] = pair
                all_trades.append(trade)
        
        if all_trades:
            df_trades = pd.DataFrame(all_trades)
            df_trades.to_csv(f"{DATA_DIR}/trades.csv", index=False)
    
    time.sleep(60)
