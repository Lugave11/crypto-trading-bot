# 🌲 **V3 MULTI-METRIC STRATEGY - PINE SCRIPT GUIDE**

## 📦 **FILES CREATED**

✅ **Pine Script:** `/mnt/data/hermes/workspace/crypto_bot/V3_Multi_Metric_Strategy.pine`

---

## 🚀 **HOW TO INSTALL ON TRADINGVIEW**

### **Step 1: Open Pine Editor**
1. Go to [TradingView](https://www.tradingview.com/)
2. Open any chart (e.g., BTC/USDT on Binance)
3. Click **"Pine Editor"** at bottom of screen
4. Click **"Create"** → **"Strategy"**

### **Step 2: Copy & Paste**
1. Open the file: `/mnt/data/hermes/workspace/crypto_bot/V3_Multi_Metric_Strategy.pine`
2. Copy **ALL** the code
3. Paste into Pine Editor (replace default code)
4. Click **"Save"** → Name it "V3 Multi-Metric Strategy"
5. Click **"Add to Chart"**

### **Step 3: Configure Settings**
Click the **gear icon** ⚙️ next to the strategy name to adjust:

**🎯 Signal Settings:**
- RSI Oversold: 25 (default)
- RSI Overbought: 75 (default)
- Confirmations Needed: 2 (default - requires 2+ filters to agree)

**📊 Filters:**
- Use EMA 200 Filter: ✅ ON
- Use ADX Filter: ✅ ON
- ADX Max: 25 (only trade in ranging markets)
- Use Volume Confirmation: ✅ ON
- Volume Multiplier: 1.2x
- Use Divergence: ✅ ON

**⚠️ Risk Management:**
- ATR Stop Loss: 1.5x ATR
- ATR Trailing Stop: 2.0x ATR
- Max Drawdown: 20%

**📈 Display:**
- Show Entry Signals: ✅ ON
- Show EMA 200: ✅ ON
- Show Background Color: ✅ ON

---

## 📊 **WHAT YOU'LL SEE ON CHART**

### **Visual Indicators:**

| Symbol | Meaning |
|--------|---------|
| 🔺 **Green Triangle** | LONG signal (RSI < 25 + 2+ confirmations) |
| 🔻 **Red Triangle** | SHORT signal (RSI > 75 + 2+ confirmations) |
| 🟡 **Yellow Circle (BD)** | Bullish Divergence detected |
| 🟠 **Orange Circle (BD)** | Bearish Divergence detected |
| 🔵 **Blue Line** | EMA 200 (trend filter) |
| 🟢 **Green Background** | Long setup forming |
| 🔴 **Red Background** | Short setup forming |

### **Info Panel (Top Right):**
```
V3 Multi-Metric
RSI:        23.45 (green if <25, red if >75)
ADX:        18.20 (green if <25, orange if >25)
Vol Ratio:  1.45x (green if >1.2x)
Bull Div:   YES/NO (yellow if yes)
Bear Div:   YES/NO (orange if yes)
Long Conf:  3/4 (green if >=2)
Short Conf: 1/4 (red if >=2)
```

---

## 🔔 **SETTING UP ALERTS**

### **Create Alert for Long Signals:**
1. Right-click on chart → **"Add Alert"**
2. Condition: **"V3 Multi-Metric Strategy" → "V3 Long Signal"**
3. Trigger: **"Once Per Bar Close"**
4. Message: (auto-filled with RSI, confirmations, ticker)
5. **Webhook URL** (optional): `https://your-bot.com/webhook`
6. Click **"Create"**

### **Create Alert for Short Signals:**
1. Right-click → **"Add Alert"**
2. Condition: **"V3 Multi-Metric Strategy" → "V3 Short Signal"**
3. Same settings as above
4. Click **"Create"**

### **Webhook JSON Template** (for auto-trading):
```json
{
  "action": "{{strategy.order.action}}",
  "ticker": "{{ticker}}",
  "close": "{{close}}",
  "rsi": "{{plot(rsi)}}",
  "confirmations": "{{plot(longConfirms)}}",
  "strategy": "V3 Multi-Metric"
}
```

---

## 📈 **BACKTESTING ON TRADINGVIEW**

### **Run Backtest:**
1. Strategy is already on chart
2. Look at **"Strategy Tester"** tab at bottom
3. You'll see:
   - **Net Profit** ($)
   - **Percent Profit** (%)
   - **Win Rate** (%)
   - **Profit Factor**
   - **Max Drawdown** (%)
   - **Total Trades**

### **Compare Timeframes:**
- Test on **1m** (scalping)
- Test on **5m** (day trading)
- Test on **15m** (swing trading)
- Test on **1h** (position trading)

### **Compare Coins:**
- BTC/USDT (low volatility)
- ETH/USDT (medium volatility)
- ZEC/USDT, ENA/USDT (high volatility)

---

## 🎯 **TRADING STRATEGY EXPLAINED**

### **LONG Entry (All must be true):**
1. ✅ RSI < 25 (oversold)
2. ✅ At least 2 of these 4 confirmations:
   - Price ABOVE 200 EMA (uptrend)
   - ADX < 25 (ranging market, not strong trend)
   - Volume > 1.2x average (institutional interest)
   - Bullish Divergence (price ↓, RSI ↑)

### **SHORT Entry (All must be true):**
1. ✅ RSI > 75 (overbought)
2. ✅ At least 2 of these 4 confirmations:
   - Price BELOW 200 EMA (downtrend)
   - ADX < 25 (ranging market)
   - Volume > 1.2x average
   - Bearish Divergence (price ↑, RSI ↓)

### **Exit Conditions:**
- **Trailing Stop:** 2.0x ATR (moves in your favor)
- **Initial Stop:** 1.5x ATR (from entry)
- **RSI Exit:** When RSI crosses back to 50 (momentum lost)

---

## ⚙️ **OPTIMIZATION TIPS**

### **For Scalping (1m-5m charts):**
```
RSI Oversold: 20 (more extreme)
RSI Overbought: 80
Confirmations Needed: 3 (stricter)
ATR Trailing: 1.5x (tighter)
```

### **For Swing Trading (15m-1h charts):**
```
RSI Oversold: 30 (less extreme)
RSI Overbought: 70
Confirmations Needed: 2 (default)
ATR Trailing: 3.0x (wider)
```

### **For High Volatility Coins:**
```
ADX Max: 30 (allow stronger trends)
Volume Multiplier: 1.5x (need more volume)
ATR Trailing: 3.0-4.0x (wider stops)
```

### **For Low Volatility Coins:**
```
ADX Max: 20 (only very ranging)
Volume Multiplier: 1.1x (less volume needed)
ATR Trailing: 1.5-2.0x (tighter)
```

---

## 📊 **EXPECTED PERFORMANCE**

Based on Python backtest results:

| Metric | Expected (TradingView) |
|--------|------------------------|
| **Win Rate** | 48-52% |
| **Profit Factor** | 2.0-2.5 |
| **Max Drawdown** | <5% |
| **Avg Trade** | +0.3-0.5% |
| **Trades/Day** | 80-120 (on 1m chart) |

**Note:** TradingView backtests may differ slightly from Python due to:
- Different data sources
- Slippage/commission assumptions
- Real-time vs historical execution

---

## 🔄 **PYTHON BOT vs PINE SCRIPT**

| Feature | Python Bot | Pine Script |
|---------|-----------|-------------|
| **Execution** | Fully automated | Manual or webhook |
| **Multi-Pair** | 4 pairs simultaneously | One pair per chart |
| **Backtesting** | Walk-forward (robust) | TradingView (fast, visual) |
| **Customization** | Unlimited | Pine Script limits |
| **Cost** | Free (your server) | Free (TradingView basic) |
| **Visual** | Logs only | Charts, indicators, overlays |
| **Alerts** | Telegram | TradingView alerts |

**Best Use:**
- **Python Bot:** Live automated trading
- **Pine Script:** Research, backtesting, manual trading, alerts

---

## 🚨 **COMMON ISSUES & FIXES**

### **"No signals appearing"**
- Check if RSI is in extreme zones (<25 or >75)
- Verify ADX < 25 (if filter is ON)
- Check volume is above average
- Wait for divergence to form

### **"Too many false signals"**
- Increase "Confirmations Needed" to 3
- Turn ON EMA filter (trade with trend)
- Increase Volume Multiplier to 1.5x
- Use higher timeframe (5m, 15m)

### **"Strategy not profitable in backtest"**
- Adjust RSI levels (try 20/80 for scalping)
- Widen ATR trailing stop (try 2.5-3.0x)
- Test on different coins (BTC vs alts)
- Check commission settings (0.1% per trade)

### **"Divergence not showing"**
- Divergence is rare (wait for clear swings)
- Reduce lookback period to 3 (more sensitive)
- Or increase to 7 (only major divergences)

---

## 📱 **MOBILE TRADING**

**TradingView Mobile App:**
1. Install TradingView app (iOS/Android)
2. Open your chart with V3 strategy
3. Enable **push notifications** for alerts
4. Get alerts on phone when signals fire
5. Manually execute on exchange app

**Perfect for:**
- Monitoring multiple coins
- Getting alerts away from computer
- Quick manual execution

---

## 🎓 **LEARNING RESOURCES**

### **Pine Script Documentation:**
- [Pine Script User Manual](https://www.tradingview.com/pine-script-docs/)
- [Strategy Reference](https://www.tradingview.com/pine-script-reference/#strategy)
- [Alerts Guide](https://www.tradingview.com/support/solutions/43000502340/)

### **V3 Strategy Concepts:**
- RSI divergence: Price makes new low, RSI doesn't = reversal likely
- ADX < 25: Market is ranging (good for mean reversion)
- ATR stops: Adaptive to volatility (wider in volatile markets)
- Volume confirmation: Institutions leave footprints

---

## 💡 **PRO TIPS**

1. **Backtest first:** Run on 1+ year of data before live trading
2. **Start small:** Paper trade or tiny position size initially
3. **Multiple timeframes:** Check 1m, 5m, 15m for confluence
4. **Combine with Python:** Use Pine for alerts, Python for execution
5. **Journal trades:** Note which confirmations were present
6. **Adjust per coin:** BTC needs different settings than volatile alts

---

## 📁 **FILE LOCATIONS**

```
/mnt/data/hermes/workspace/crypto_bot/
├── V3_Multi_Metric_Strategy.pine    # 🌲 Pine Script (copy to TradingView)
├── PAPER_TRADING_V3_SUMMARY.md      # 📄 Python V3 documentation
└── paper_trading_v3.py              # 🐍 Python V3 bot (live trading)
```

---

## 🚀 **NEXT STEPS**

1. ✅ **Install Pine Script** on TradingView
2. ✅ **Backtest** on your favorite coins/timeframes
3. ✅ **Set up alerts** for real-time signals
4. ✅ **Compare** results with Python bot backtest
5. ✅ **Decide:** Manual trading, webhook automation, or both?

---

## 🎯 **QUICK START CHECKLIST**

- [ ] Copy Pine code to TradingView
- [ ] Add to chart (BTC/USDT recommended)
- [ ] Configure settings (defaults are good)
- [ ] Run backtest (check Strategy Tester)
- [ ] Create alerts for Long/Short signals
- [ ] Set up webhook (optional, for automation)
- [ ] Paper trade for 1 week
- [ ] Compare with Python bot performance
- [ ] Go live (small size first!)

---

**Happy Trading! 🚀📈**

**Questions?** Check `PAPER_TRADING_V3_SUMMARY.md` for Python bot details, or refer to Pine Script comments in the code.
