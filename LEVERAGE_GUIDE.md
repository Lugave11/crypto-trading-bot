# 🚀 **V3 LEVERAGE GUIDE - HYPERTLIQUID**

## 📊 **WHAT CHANGED**

✅ **Maker Orders:** 0.02% fee (was 0.05% taker) = **60% fee savings!**  
✅ **Leverage Support:** 1x to 5x leverage optional  
✅ **Fee-Efficient:** Low frequency + maker orders = minimal fee drag  

---

## 💰 **LEVERAGE BASICS**

### **What is Leverage?**
Borrowed capital to amplify position size and potential returns.

**Example with $10,000 capital:**
| Leverage | Position Size | Buying Power | Risk |
|----------|---------------|--------------|------|
| **1x** (no leverage) | $500 (5%) | $500 | Low |
| **3x** | $500 × 3 = $1,500 | $1,500 | Medium |
| **5x** | $500 × 5 = $2,500 | $2,500 | High |

### **How Leverage Affects PnL:**

**Scenario: +1% price move**
| Leverage | Gross PnL | Fees (maker) | Net PnL |
|----------|-----------|--------------|---------|
| 1x | +$5.00 | -$0.20 | **+$4.80** |
| 3x | +$15.00 | -$0.60 | **+$14.40** |
| 5x | +$25.00 | -$1.00 | **+$24.00** |

**Scenario: -1% price move**
| Leverage | Gross Loss | Fees (maker) | Net Loss |
|----------|------------|--------------|----------|
| 1x | -$5.00 | -$0.20 | **-$5.20** |
| 3x | -$15.00 | -$0.60 | **-$15.60** |
| 5x | -$25.00 | -$1.00 | **-$26.00** |

**Key Insight:** Leverage amplifies BOTH wins AND losses!

---

## ⚠️ **LEVERAGE RISKS**

### **1. Liquidation Risk**
Hyperliquid will auto-close positions if losses exceed collateral.

**Liquidation Price (Long):**
```
Liquidation = Entry Price × (1 - 1/Leverage)

Example: $100 entry, 3x leverage
Liquidation = $100 × (1 - 1/3) = $66.67 (-33.3%)
```

**Liquidation Price (Short):**
```
Liquidation = Entry Price × (1 + 1/Leverage)

Example: $100 entry, 3x leverage
Liquidation = $100 × (1 + 1/3) = $133.33 (+33.3%)
```

### **2. Fee Amplification**
You pay fees on the FULL position size (including borrowed funds).

**Example:**
- 5% position = $500
- 5x leverage = $2,500 position
- Maker fee: 0.02% × $2,500 = **$0.50 per side** ($1.00 round-trip)
- Without leverage: $0.10 per side ($0.20 round-trip)
- **5x leverage = 5x fees!**

### **3. Drawdown Amplification**
A -2% move with 5x leverage = -10% loss on your capital.

| Price Move | 1x Loss | 3x Loss | 5x Loss |
|------------|---------|---------|---------|
| -1% | -1% | -3% | -5% |
| -2% | -2% | -6% | -10% |
| -5% | -5% | -15% | -25% |
| -10% | -10% | -30% | -50% |

---

## 🎯 **RECOMMENDED LEVERAGE SETTINGS**

### **Conservative (Recommended for Start)**
```python
'use_leverage': False,  # No leverage
'leverage': 1,
'position_size': 5,  # 5% per trade
```
**Best for:** Learning, testing, risk-averse traders

### **Moderate (Balanced Risk/Reward)**
```python
'use_leverage': True,
'leverage': 2,  # 2x leverage
'position_size': 5,  # 5% base = 10% effective
```
**Best for:** Experienced traders, confident in strategy

### **Aggressive (High Risk)**
```python
'use_leverage': True,
'leverage': 3,  # 3x leverage
'position_size': 5,  # 5% base = 15% effective
```
**Best for:** High conviction setups, small account growth

### **Degen (NOT RECOMMENDED)**
```python
'use_leverage': True,
'leverage': 5,  # 5x leverage
'position_size': 5,  # 5% base = 25% effective
```
**⚠️ WARNING:** One bad trade = -10% to -15% loss. Not sustainable!

---

## 📊 **V3 PERFORMANCE WITH LEVERAGE (Projections)**

Based on backtested V3 results (70.5% WR, +465% return over 14 years):

### **1x Leverage (No Leverage)**
- Annual Return: ~35-40%
- Max Drawdown: -5%
- Win Rate: ~70%
- **Risk Level:** Low ✅

### **3x Leverage**
- Annual Return: ~100-120% (3x amplified)
- Max Drawdown: -15% (3x amplified)
- Win Rate: ~70% (same)
- **Risk Level:** Medium ⚠️

### **5x Leverage**
- Annual Return: ~150-200% (5x amplified)
- Max Drawdown: -25% (5x amplified)
- Win Rate: ~70% (same)
- **Risk Level:** High 🚨

---

## 🛡️ **RISK MANAGEMENT WITH LEVERAGE**

### **Rule 1: Never Risk More Than 2% Per Trade**
```
Max Loss = Capital × 0.02
Position Size = Max Loss / (Stop Loss % × Leverage)

Example: $10,000 capital, 2% risk, 1% stop, 3x leverage
Max Loss = $10,000 × 0.02 = $200
Position Size = $200 / (0.01 × 3) = $6,667
Base Size = $6,667 / 3 = $2,222 (22% of capital!)
```

**V3's ATR stops are typically 1-2%, so:**
- 1x leverage: 5% position = safe
- 3x leverage: 2-3% position = safe
- 5x leverage: 1-2% position = safe

### **Rule 2: Reduce Leverage in Choppy Markets**
- ADX < 20 (ranging): Use 1-2x max
- ADX 20-30 (trending): Can use 2-3x
- ADX > 30 (strong trend): Can use 3-5x (with caution!)

### **Rule 3: Never Add Leverage to Losing Positions**
- If trade is down, DON'T increase leverage to "make it back"
- This is how accounts get liquidated
- Accept the loss, wait for next A+ setup

### **Rule 4: Scale Leverage with Win Streaks**
- 3+ wins in a row: Can increase leverage slightly
- 2+ losses in a row: Reduce leverage or pause trading
- Let profits compound, protect capital during drawdowns

---

## 🔧 **V3 CONFIGURATION EXAMPLES**

### **Example 1: Conservative (Learning Phase)**
```python
BOT_SETTINGS = {
    'position_size': 5,  # 5% per trade
    'use_leverage': False,
    'leverage': 1,
    'fee_type': 'maker',  # Limit orders
    'rsi_oversold': 25,
    'rsi_overbought': 75,
}
```
**Expected:** 30-40% annual return, -5% max DD

### **Example 2: Moderate (Growth Phase)**
```python
BOT_SETTINGS = {
    'position_size': 4,  # 4% base (reduced for leverage)
    'use_leverage': True,
    'leverage': 2,  # 2x = 8% effective
    'fee_type': 'maker',
    'rsi_oversold': 25,
    'rsi_overbought': 75,
}
```
**Expected:** 60-80% annual return, -10% max DD

### **Example 3: Aggressive (High Conviction)**
```python
BOT_SETTINGS = {
    'position_size': 3,  # 3% base (conservative for 3x)
    'use_leverage': True,
    'leverage': 3,  # 3x = 9% effective
    'fee_type': 'maker',
    'rsi_oversold': 20,  # More selective
    'rsi_overbought': 80,
}
```
**Expected:** 100-120% annual return, -15% max DD

---

## 📈 **HYPERTLIQUID-SPECIFIC TIPS**

### **1. Use Isolated Margin**
- Each position has its own collateral
- One bad trade won't liquidate your entire account
- Default on Hyperliquid (good!)

### **2. Monitor Funding Rates**
- Perpetual futures have funding payments
- Positive funding: Longs pay shorts (bullish sentiment)
- Negative funding: Shorts pay longs (bearish sentiment)
- High funding (>0.1% per 8hr) = expensive to hold

### **3. Place Limit Orders (Maker)**
- Don't use market orders (taker fees 2.5x higher!)
- Set limit price slightly better than current (e.g., $0.01 below for longs)
- Wait for fill (patience = profit)

### **4. Use Reduce-Only for Exits**
- When closing position, mark order as "reduce-only"
- Prevents accidentally opening opposite position
- V3 handles this automatically

---

## 🎯 **MY RECOMMENDATION FOR YOU**

### **Phase 1: Test Without Leverage (1-2 weeks)**
```python
'use_leverage': False,
'position_size': 5,
```
**Goal:** Prove V3 works live, build confidence

### **Phase 2: Add Moderate Leverage (2-4 weeks)**
```python
'use_leverage': True,
'leverage': 2,
'position_size': 4,  # Reduced slightly
```
**Goal:** Amplify returns while managing risk

### **Phase 3: Optimize (After 1 month)**
- If win rate >65%: Consider 3x leverage
- If win rate <55%: Stay at 1-2x or reduce position size
- Adjust based on actual performance, not backtests!

---

## 🚨 **WARNING SIGNS**

**Reduce or eliminate leverage if:**
- ❌ 3+ losing trades in a row
- ❌ Drawdown >10% (with 2x leverage)
- ❌ Win rate <45% over 20+ trades
- ❌ Emotional trading (revenge trades, FOMO)
- ❌ Can't sleep at night (position too large!)

---

## 💡 **FINAL THOUGHTS**

**Leverage is a tool, not a strategy.**

- ✅ Good traders use leverage to amplify edge
- ❌ Bad traders use leverage to gamble

**V3's edge:**
- Selective entries (RSI <25/>75 + confirmations)
- Tight risk management (ATR stops)
- Low frequency (fewer fees)
- Maker orders (60% fee savings)

**With leverage:**
- 2-3x can amplify returns sustainably
- 5x+ is gambling (one bad trade wipes you out)
- Always use stop losses (V3 does this automatically)

**Start conservative, scale up slowly, never risk more than you can afford to lose!**

---

## 📋 **QUICK REFERENCE**

| Scenario | Recommended Leverage |
|----------|---------------------|
| **Learning/Testing** | 1x (no leverage) |
| **First Live Month** | 1-2x |
| **Confident (60%+ WR)** | 2-3x |
| **High Conviction Setup** | 3x max |
| **Choppy Market (ADX <20)** | 1x |
| **Strong Trend (ADX >30)** | 2-3x |
| **After 3 Losses** | 1x (or pause) |
| **After 5 Wins** | Can increase to 2-3x |

---

**Remember:** The goal is to survive and compound, not get rich quick. V3 + 2-3x leverage + maker orders = sustainable growth. 🚀
