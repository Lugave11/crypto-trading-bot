#!/usr/bin/env python3
"""
Trailing Stop Loss Visualization & Comparison
Shows the difference between fixed stop loss and trailing stop
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

# Create sample price data (simulating a trade)
np.random.seed(42)
n_points = 100

# Simulate price movement with uptrend then reversal
base_price = 100
trend = np.linspace(0, 15, n_points)  # Upward trend
noise = np.cumsum(np.random.randn(n_points) * 0.5)  # Random walk
price = base_price + trend + noise

# Add a peak and reversal
peak_idx = 70
price[peak_idx:] = price[peak_idx] - np.linspace(0, 12, n_points - peak_idx)

# Create DataFrame
df = pd.DataFrame({
    'close': price,
    'high': price + np.random.uniform(0.5, 1.5, n_points),
    'low': price - np.random.uniform(0.5, 1.5, n_points)
})
df.index = pd.date_range('2026-01-01', periods=n_points, freq='1min')

# ============================================================================
# FIXED STOP LOSS
# ============================================================================
entry_price = df['close'].iloc[10]  # Enter at candle 10
fixed_sl = entry_price * 0.99  # 1% fixed stop
fixed_tp = entry_price * 1.02  # 2% fixed TP

fixed_exit_idx = None
fixed_exit_price = None
fixed_exit_reason = None

for i in range(11, n_points):
    if df['low'].iloc[i] <= fixed_sl:
        fixed_exit_idx = i
        fixed_exit_price = fixed_sl
        fixed_exit_reason = 'Stop Loss'
        break
    elif df['high'].iloc[i] >= fixed_tp:
        fixed_exit_idx = i
        fixed_exit_price = fixed_tp
        fixed_exit_reason = 'Take Profit'
        break

if fixed_exit_idx is None:
    fixed_exit_idx = n_points - 1
    fixed_exit_price = df['close'].iloc[fixed_exit_idx]
    fixed_exit_reason = 'End'

fixed_pnl = (fixed_exit_price - entry_price) / entry_price * 100

# ============================================================================
# TRAILING STOP LOSS (1% trailing)
# ============================================================================
trailing_stop_pct = 0.01  # 1% trailing
highest_price = entry_price
trailing_sl = entry_price * (1 - trailing_stop_pct)

trailing_exit_idx = None
trailing_exit_price = None
trailing_sl_history = []

for i in range(11, n_points):
    # Update highest price
    highest_price = max(highest_price, df['high'].iloc[i])
    
    # Move stop loss up (never down)
    new_trailing_sl = highest_price * (1 - trailing_stop_pct)
    trailing_sl = max(trailing_sl, new_trailing_sl)
    trailing_sl_history.append(trailing_sl)
    
    # Check if stopped out
    if df['low'].iloc[i] <= trailing_sl:
        trailing_exit_idx = i
        trailing_exit_price = trailing_sl
        break

if trailing_exit_idx is None:
    trailing_exit_idx = n_points - 1
    trailing_exit_price = df['close'].iloc[trailing_exit_idx]

trailing_pnl = (trailing_exit_price - entry_price) / entry_price * 100

# ============================================================================
# TRAILING STOP WITH RE-ENTRY (Lock Profits Every N Candles)
# ============================================================================
check_interval = 5  # Check every 5 candles
highest_price_2 = entry_price
trailing_sl_2 = entry_price * (1 - trailing_stop_pct)
locked_profit = 0

trailing2_exit_idx = None
trailing2_exit_price = None
trailing2_sl_history = []

for i in range(11, n_points):
    # Update highest price
    highest_price_2 = max(highest_price_2, df['high'].iloc[i])
    
    # Check every N candles
    if (i - 10) % check_interval == 0:
        new_trailing_sl = highest_price_2 * (1 - trailing_stop_pct)
        trailing_sl_2 = max(trailing_sl_2, new_trailing_sl)
    
    trailing2_sl_history.append(trailing_sl_2)
    
    # Check if stopped out
    if df['low'].iloc[i] <= trailing_sl_2:
        trailing2_exit_idx = i
        trailing2_exit_price = trailing_sl_2
        break

if trailing2_exit_idx is None:
    trailing2_exit_idx = n_points - 1
    trailing2_exit_price = df['close'].iloc[trailing2_exit_idx]

trailing2_pnl = (trailing2_exit_price - entry_price) / entry_price * 100

# ============================================================================
# PLOT
# ============================================================================
fig, axes = plt.subplots(2, 1, figsize=(14, 10))

# Price chart
ax1 = axes[0]
ax1.plot(df.index, df['close'], 'b-', linewidth=2, label='Price')
ax1.axvline(df.index[10], color='gray', linestyle='--', alpha=0.5, label='Entry')
ax1.axhline(entry_price, color='gray', linestyle='--', alpha=0.5)

# Fixed stop loss
ax1.axhline(fixed_sl, color='red', linestyle='-', linewidth=2, label=f'Fixed SL (-1%): ${fixed_sl:.2f}')
ax1.axhline(fixed_tp, color='green', linestyle='-', linewidth=2, label=f'Fixed TP (+2%): ${fixed_tp:.2f}')
if fixed_exit_idx:
    ax1.axvline(df.index[fixed_exit_idx], color='orange', linestyle=':', linewidth=3, 
                label=f'Fixed Exit: ${fixed_exit_price:.2f} ({fixed_pnl:+.2f}%)')

# Trailing stop (continuous)
if len(trailing_sl_history) > 0:
    trailing_dates = df.index[11:11+len(trailing_sl_history)]
    ax1.plot(trailing_dates, trailing_sl_history, color='purple', linestyle='-', linewidth=2, 
             label=f'Trailing SL (1%): Exit ${trailing_exit_price:.2f} ({trailing_pnl:+.2f}%)')

# Trailing stop (check every 5 candles)
if len(trailing2_sl_history) > 0:
    trailing2_dates = df.index[11:11+len(trailing2_sl_history)]
    ax1.plot(trailing2_dates, trailing2_sl_history, color='magenta', linestyle='-.', linewidth=2, 
             label=f'Trailing SL (5-candle check): ${trailing2_exit_price:.2f} ({trailing2_pnl:+.2f}%)')

ax1.set_title('📊 Fixed Stop Loss vs Trailing Stop Loss Comparison', fontsize=14, fontweight='bold')
ax1.set_ylabel('Price ($)')
ax1.legend(loc='upper left', fontsize=9)
ax1.grid(True, alpha=0.3)
ax1.xaxis.set_major_formatter(DateFormatter('%H:%M'))

# PnL comparison
ax2 = axes[1]
methods = ['Fixed SL', 'Trailing SL\n(continuous)', 'Trailing SL\n(5-candle check)']
pnl_values = [fixed_pnl, trailing_pnl, trailing2_pnl]
colors = ['red', 'purple', 'magenta']

bars = ax2.bar(methods, pnl_values, color=colors, edgecolor='black', linewidth=2)
ax2.axhline(0, color='black', linewidth=1)

# Add value labels
for bar, pnl in zip(bars, pnl_values):
    height = bar.get_height()
    ax2.text(bar.get_x() + bar.get_width()/2., height,
             f'{pnl:+.2f}%',
             ha='center', va='bottom' if height > 0 else 'top',
             fontsize=11, fontweight='bold')

ax2.set_title('💰 Profit/Loss Comparison', fontsize=14, fontweight='bold')
ax2.set_ylabel('PnL (%)')
ax2.grid(True, alpha=0.3, axis='y')

# Add improvement annotation
best_pnl = max(pnl_values)
improvement = best_pnl - fixed_pnl
if improvement > 0:
    ax2.text(1.5, best_pnl + 0.5, f'🎯 +{improvement:.2f}% improvement\nwith trailing stop!',
             fontsize=11, fontweight='bold', color='green',
             bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))

plt.tight_layout()
plt.savefig('/mnt/data/hermes/workspace/crypto_bot/trailing_stop_comparison.png', dpi=150, bbox_inches='tight')
print("✅ Chart saved to: /mnt/data/hermes/workspace/crypto_bot/trailing_stop_comparison.png")

# ============================================================================
# SUMMARY
# ============================================================================
print()
print("="*70)
print("📊 TRAILING STOP LOSS ANALYSIS")
print("="*70)
print()
print(f"Entry Price: ${entry_price:.2f}")
print()
print("METHOD COMPARISON:")
print("-"*70)
print(f"{'Method':<30s} {'Exit Price':>12s} {'PnL':>12s}")
print("-"*70)
print(f"{'Fixed Stop Loss (-1% / +2%)':<30s} ${fixed_exit_price:>10.2f} {fixed_pnl:>+11.2f}%")
print(f"{'Trailing Stop (continuous 1%)':<30s} ${trailing_exit_price:>10.2f} {trailing_pnl:>+11.2f}%")
print(f"{'Trailing Stop (check every 5c)':<30s} ${trailing2_exit_price:>10.2f} {trailing2_pnl:>+11.2f}%")
print("-"*70)
print()

best_method = "Trailing (continuous)" if trailing_pnl >= trailing2_pnl else "Trailing (5-candle)"
best_value = max(trailing_pnl, trailing2_pnl)

if best_value > fixed_pnl:
    print(f"🎯 WINNER: {best_method}")
    print(f"   Improvement: +{best_value - fixed_pnl:.2f}% vs fixed stop loss")
    print()
    print("KEY BENEFITS OF TRAILING STOP:")
    print("  ✅ Locks in profits as price moves in your favor")
    print("  ✅ Lets winners run (no fixed take profit ceiling)")
    print("  ✅ Adapts to market volatility")
    print("  ✅ Reduces regret from giving back profits")
    print()
    print("TRADE-OFFS:")
    print("  ⚠️  More complex to implement")
    print("  ⚠️  Can exit earlier in choppy markets")
    print("  ⚠️  Requires more frequent monitoring/updates")
else:
    print(f"📊 Fixed stop loss performed better in this scenario")
    print(f"   (This can happen in ranging/choppy markets)")

print()
print("="*70)
