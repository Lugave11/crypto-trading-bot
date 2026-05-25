#!/usr/bin/env python3
"""
Fee Analysis: Recalculate V2 and V3 performance with Hyperliquid fees
"""

import json
import os
from datetime import datetime

# Hyperliquid fees
MAKER_FEE = 0.0002  # 0.02%
TAKER_FEE = 0.0005  # 0.05%
FEE_TYPE = 'taker'  # Assuming market orders

def calculate_fees(trades, fee_per_trade=0.001):  # 0.1% round-trip taker
    """
    Recalculate PnL after fees
    
    Args:
        trades: List of trade dicts with 'pnl_usd' and 'entry'/'exit' prices
        fee_per_trade: Total round-trip fee (0.001 = 0.1% for taker-taker)
    """
    total_gross = 0
    total_fees = 0
    total_net = 0
    wins = 0
    losses = 0
    
    print(f"{'='*80}")
    print(f"FEE ANALYSIS (Hyperliquid {FEE_TYPE.upper()} fees: {fee_per_trade*100:.2f}% round-trip)")
    print(f"{'='*80}\n")
    
    for i, trade in enumerate(trades, 1):
        gross_pnl = trade.get('pnl_usd', 0)
        entry = trade.get('entry', 0)
        size = trade.get('size', entry * 0.05)  # Assume 5% position if not specified
        
        # Calculate fee in USD
        fee_usd = size * fee_per_trade
        net_pnl = gross_pnl - fee_usd
        
        total_gross += gross_pnl
        total_fees += fee_usd
        total_net += net_pnl
        
        if net_pnl > 0:
            wins += 1
        else:
            losses += 1
        
        print(f"Trade {i:3d}: Gross: ${gross_pnl:+7.2f} | Fees: ${fee_usd:.2f} | Net: ${net_pnl:+7.2f} | {trade.get('pair', 'N/A')}")
    
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Total Trades:     {len(trades)}")
    print(f"Gross PnL:        ${total_gross:+.2f}")
    print(f"Total Fees:       ${total_fees:.2f}")
    print(f"Net PnL:          ${total_net:+.2f}")
    print(f"Win Rate (net):   {wins/len(trades)*100:.1f}% ({wins}W / {losses}L)")
    print(f"Fee Drag:         {total_fees/abs(total_gross)*100:.1f}% of gross PnL")
    print(f"{'='*80}\n")
    
    return {
        'total_trades': len(trades),
        'gross_pnl': total_gross,
        'total_fees': total_fees,
        'net_pnl': total_net,
        'wins': wins,
        'losses': losses,
        'win_rate': wins/len(trades)*100 if len(trades) > 0 else 0,
        'fee_drag_pct': total_fees/abs(total_gross)*100 if total_gross != 0 else 0,
    }

# Parse V3 log
def parse_v3_log(log_path):
    trades = []
    with open(log_path, 'r') as f:
        for line in f:
            if '💰' in line and 'Entry:' in line:
                # Parse: [timestamp] 💰 PAIR: TYPE | Entry: $X → Exit: $Y | Net: $Z (P%) | Fees: $F [reason]
                try:
                    # Extract pair
                    parts = line.split('💰')[1].split(':')[0].strip()
                    pair = parts.split()[0]
                    
                    # Extract entry and exit
                    entry_str = line.split('Entry: $')[1].split(' →')[0]
                    exit_str = line.split('Exit: $')[1].split(' |')[0]
                    
                    entry = float(entry_str)
                    exit_p = float(exit_str)
                    
                    # Extract net PnL
                    if 'Net: $' in line:
                        net_str = line.split('Net: $')[1].split(' (')[0]
                        net_pnl = float(net_str)
                    else:
                        # Old format without fees
                        pnl_str = line.split('PnL: $')[1].split(' (')[0]
                        net_pnl = float(pnl_str)
                    
                    # Assume $500 position size (5% of $10k)
                    size = 500
                    
                    trades.append({
                        'pair': pair,
                        'entry': entry,
                        'exit': exit_p,
                        'pnl_usd': net_pnl,
                        'size': size,
                    })
                except Exception as e:
                    continue
    
    return trades

# Parse V2 log
def parse_v2_log(log_path):
    trades = []
    with open(log_path, 'r') as f:
        for line in f:
            if '💰' in line and 'Entry:' in line:
                try:
                    parts = line.split('💰')[1].split(':')[0].strip()
                    pair = parts.split()[0]
                    
                    entry_str = line.split('Entry: $')[1].split(' →')[0]
                    exit_str = line.split('Exit: $')[1].split(' |')[0]
                    
                    entry = float(entry_str)
                    exit_p = float(exit_str)
                    
                    pnl_str = line.split('PnL: $')[1].split(' (')[0]
                    pnl = float(pnl_str)
                    
                    size = 700  # V2 uses 7% position
                    
                    trades.append({
                        'pair': pair,
                        'entry': entry,
                        'exit': exit_p,
                        'pnl_usd': pnl,
                        'size': size,
                    })
                except Exception as e:
                    continue
    
    return trades

# Main analysis
print("\n" + "="*80)
print("HYPERLIQUID FEE ANALYSIS")
print("="*80 + "\n")

# V3 Analysis
print("\n📊 V3 BOT (Multi-Metric) - Fee Analysis\n")
v3_trades = parse_v3_log('/mnt/data/hermes/workspace/crypto_bot/paper_trading_v3.log')
if v3_trades:
    v3_results = calculate_fees(v3_trades, fee_per_trade=0.001)
else:
    print("No V3 trades found yet.")

# V2 Analysis
print("\n📊 V2 BOT (Trailing Stop) - Fee Analysis\n")
v2_trades = parse_v2_log('/mnt/data/hermes/workspace/crypto_bot/paper_trading_live.log')
if v2_trades:
    v2_results = calculate_fees(v2_trades, fee_per_trade=0.001)
else:
    print("No V2 trades found yet.")

# Comparison
if v3_trades and v2_trades:
    print("\n" + "="*80)
    print("BOT COMPARISON (After Hyperliquid Fees)")
    print("="*80)
    print(f"{'Metric':<20} {'V2 (Trailing)':<20} {'V3 (Multi-Metric)':<20}")
    print(f"{'-'*80}")
    print(f"{'Total Trades':<20} {v2_results['total_trades']:<20} {v3_results['total_trades']:<20}")
    print(f"{'Gross PnL':<20} ${v2_results['gross_pnl']:+.2f}{'':<14} ${v3_results['gross_pnl']:+.2f}{'':<14}")
    print(f"{'Total Fees':<20} ${v2_results['total_fees']:.2f}{'':<14} ${v3_results['total_fees']:.2f}{'':<14}")
    print(f"{'Net PnL':<20} ${v2_results['net_pnl']:+.2f}{'':<14} ${v3_results['net_pnl']:+.2f}{'':<14}")
    print(f"{'Win Rate':<20} {v2_results['win_rate']:.1f}%{'':<15} {v3_results['win_rate']:.1f}%{'':<15}")
    print(f"{'Fee Drag':<20} {v2_results['fee_drag_pct']:.1f}%{'':<15} {v3_results['fee_drag_pct']:.1f}%{'':<15}")
    print("="*80 + "\n")
