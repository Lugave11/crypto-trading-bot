#!/usr/bin/env python3
"""
Paper Trading Status Checker
Reads current state and displays summary
"""

import json
import os
import pandas as pd
from datetime import datetime

DATA_DIR = '/mnt/data/hermes/workspace/crypto_bot/paper_trading'
STATE_FILE = f'{DATA_DIR}/state.json'

PAIRS = ['ZEC/USDT', 'ENA/USDT', 'KAS/USDT', 'TAO/USDT']
INITIAL_CAPITAL = 10000

print("="*70)
print("📊 PAPER TRADING STATUS")
print("="*70)
print()

if not os.path.exists(STATE_FILE):
    print("⏳ No state file yet - bot is still running first cycle...")
    print(f"State will be saved to: {STATE_FILE}")
    print()
    print("Check back in a few minutes or wait for the first status update.")
else:
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
        
        print(f"Last Update: {state.get('timestamp', 'Unknown')}")
        print()
        
        total_capital = 0
        total_pnl = 0
        total_trades = 0
        total_wins = 0
        
        for pair in PAIRS:
            if pair in state['pairs']:
                stats = state['pairs'][pair]
                total_capital += stats['capital']
                total_pnl += stats['pnl']
                total_trades += stats['total_trades']
                total_wins += stats['wins']
                
                pos = "LONG" if stats['position'] and stats['position']['type'] == 'LONG' else \
                      "SHORT" if stats['position'] else "FLAT"
                
                print(f"{pair}:")
                print(f"  Capital: ${stats['capital']:,.2f} | PnL: ${stats['pnl']:+,.2f} ({stats['pnl']/INITIAL_CAPITAL*100:+.2f}%)")
                print(f"  Trades: {stats['total_trades']} | WR: {stats['win_rate']:.1f}% | DD: {stats['max_dd']:.2f}%")
                print(f"  Position: {pos}")
                print()
        
        print("-" * 70)
        print(f"TOTAL:")
        print(f"  Capital: ${total_capital:,.2f} / ${INITIAL_CAPITAL * len(PAIRS):,.2f}")
        print(f"  Total PnL: ${total_pnl:+,.2f} ({total_pnl/(INITIAL_CAPITAL * len(PAIRS))*100:+.2f}%)")
        if total_trades > 0:
            print(f"  Total Trades: {total_trades} | Win Rate: {total_wins/total_trades*100:.1f}%")
        else:
            print(f"  Total Trades: 0 (waiting for signals...)")
        print("="*70)
        
        # Show recent trades
        print()
        print("📈 RECENT TRADES:")
        print("-" * 70)
        all_trades = []
        for pair in PAIRS:
            trade_file = f"{DATA_DIR}/{pair.replace('/', '')}_trades.csv"
            if os.path.exists(trade_file):
                df = pd.read_csv(trade_file)
                if len(df) > 0:
                    df['pair'] = pair
                    all_trades.append(df)
        
        if all_trades:
            all_df = pd.concat(all_trades, ignore_index=True)
            all_df['timestamp'] = pd.to_datetime(all_df['timestamp'])
            all_df = all_df.sort_values('timestamp', ascending=False).head(10)
            
            for _, row in all_df.iterrows():
                ts = pd.to_datetime(row['timestamp']).strftime('%H:%M')
                print(f"  {ts} {row['pair']:12s} {row['type']:5s} | Entry: ${row['entry']:,.4f} → Exit: ${row['exit']:,.4f} | PnL: ${row['pnl_usd']:+.2f} ({row['pnl_pct']:+.2f}%) [{row['exit_reason']}]")
        else:
            print("  No trades executed yet...")
        
        print()
        
    except Exception as e:
        print(f"Error reading state: {e}")
        print("Bot may still be initializing...")

print()
print(f"Data directory: {DATA_DIR}")
print()
