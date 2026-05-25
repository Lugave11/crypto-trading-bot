# 📄 Paper Trading Bot - Multi-Pair Mode

## Status: ✅ RUNNING

**Started:** May 23, 2026  
**Mode:** Paper Trading (Simulation Only - No Real Orders)

---

## Configuration

### Pairs & Exchanges
| Pair | Exchange | Status |
|------|----------|--------|
| ZEC/USDT | OKX | ✅ Active |
| ENA/USDT | OKX | ✅ Active |
| KAS/USDT | Gate.io | ✅ Active |
| TAO/USDT | Gate.io | ✅ Active |

### Bot Settings (Validated on BTC 14.4-year backtest)
```python
RSI_OVERSOLD = 25      # Buy signal
RSI_OVERBOUGHT = 75    # Sell signal
TAKE_PROFIT = 0.8%     # Exit at +0.8%
STOP_LOSS = 1.0%       # Exit at -1.0%
POSITION_SIZE = 7%     # Capital per trade
MAX_DRAWDOWN = 20%     # Stop trading if DD > 20%
```

### Capital Allocation
- **Per Pair:** $10,000
- **Total Capital:** $40,000
- **Risk per Trade:** ~$700 (7% of $10k)

---

## Expected Performance (Based on BTC Backtest)

| Metric | Expected (per backtest) |
|--------|------------------------|
| Win Rate | 65-70% |
| Trades/Day | ~50-100 (all pairs combined) |
| Monthly Return | +1-3% |
| Max Drawdown | <5% |

---

## Files & Monitoring

### Data Location
```
/mnt/data/hermes/workspace/crypto_bot/paper_trading/
├── state.json              # Current state (updated every 5 min)
├── ZECUSDT_trades.csv      # Trade history
├── ENAUSDT_trades.csv
├── KASUSDT_trades.csv
└── TAOUSDT_trades.csv
```

### Check Status
```bash
cd /mnt/data/hermes/workspace/crypto_bot
python3 check_paper_status.py
```

### View Running Process
```bash
process action="poll" session_id="proc_6bb42c84362f"
```

---

## How It Works

1. **Data Fetching:** Fetches 1-minute candles from OKX and Gate.io every 60 seconds
2. **Signal Detection:** Calculates RSI(14) for each pair
3. **Entry Signals:**
   - LONG when RSI < 25 (oversold)
   - SHORT when RSI > 75 (overbought)
4. **Exit Signals:**
   - Take Profit at +0.8%
   - Stop Loss at -1.0%
   - RSI Crossback (RSI > 50 for LONG, RSI < 50 for SHORT)
5. **Risk Management:**
   - 7% position sizing
   - 20% max drawdown circuit breaker
   - Per-pair isolation (no cross-margin)

---

## What to Expect

### First Hour
- Bot will monitor markets and wait for RSI signals
- May not trade immediately if no extreme RSI readings
- State file created after 5 minutes

### First Day
- Expect 20-50 trades per pair (varies by volatility)
- Win rate should be 60-70% if markets behave like BTC historical
- Small PnL swings (±0.5% typical)

### First Week
- Performance pattern should emerge
- Compare win rate to expected 65-70%
- Monitor drawdown (should stay <5%)

---

## Stop/Restart

### Stop
```bash
# Send Ctrl+C to the running process
process action="kill" session_id="proc_6bb42c84362f"
```

### Restart
```bash
cd /mnt/data/hermes/workspace/crypto_bot
python3 paper_trading.py
```

### View Trade History
```bash
cat /mnt/data/hermes/workspace/crypto_bot/paper_trading/ZECUSDT_trades.csv
```

---

## Next Steps

1. **Monitor for 24-48 hours** - Let the bot collect data and execute trades
2. **Check status periodically** - Run `check_paper_status.py` every few hours
3. **Review after 1 week** - Analyze win rate, PnL, and drawdown
4. **Compare to backtest** - Validate real-time performance vs historical

---

## Notes

- ✅ **No real money** - Pure simulation
- ✅ **Validated settings** - Tested on 14.4 years of BTC data
- ✅ **Multi-exchange** - OKX for ZEC/ENA, Gate.io for KAS/TAO
- ✅ **Production-ready code** - Same logic as backtest
- ⚠️ **Slippage not included** - Real trading may have 0.1-0.3% slippage
- ⚠️ **Fees not included** - Exchange fees ~0.1% per trade

---

**Good luck! 🚀**
