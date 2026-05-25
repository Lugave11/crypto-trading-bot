// ============================================================================
// V3 MULTI-METRIC STRATEGY - Pine Script v5
// TradingView: https://www.tradingview.com/
// 
// Metrics: RSI + ADX + ATR + EMA 200 + Volume + Divergence
// Entry: RSI extreme + 2+ confirmations (EMA, ADX, Volume, Divergence)
// Exit: ATR Trailing Stop (2.0x ATR)
//
// Author: Jeremiah (Crypto Trading Bot V3)
// Created: May 24, 2026
// ============================================================================

//@version=5
strategy("V3 Multi-Metric Strategy", 
         overlay=true,
         initial_capital=10000,
         default_qty_type=strategy.percent_of_equity,
         default_qty_value=5,
         commission_type=strategy.commission.percent,
         commission_value=0.1,
         slippage=2,
         pyramiding=1,
         calc_on_every_tick=true)

// ============================================================================
// INPUTS
// ============================================================================
grp_signals = "🎯 Signal Settings"
rsiOversold = input.int(25, "RSI Oversold Level", minval=1, maxval=50, group=grp_signals)
rsiOverbought = input.int(75, "RSI Overbought Level", minval=50, maxval=99, group=grp_signals)
confirmationsNeeded = input.int(2, "Confirmations Needed", minval=1, maxval=4, group=grp_signals)

grp_filters = "📊 Filters"
useEmaFilter = input.bool(true, "Use EMA 200 Filter", group=grp_filters)
useAdxFilter = input.bool(true, "Use ADX Filter", group=grp_filters)
adxMax = input.int(25, "ADX Max (Ranging Market)", minval=1, maxval=50, group=grp_filters)
useVolConfirm = input.bool(true, "Use Volume Confirmation", group=grp_filters)
volMult = input.float(1.2, "Volume Multiplier", minval=0.5, maxval=5.0, step=0.1, group=grp_filters)
useDivergence = input.bool(true, "Use Divergence Detection", group=grp_filters)

grp_risk = "⚠️ Risk Management"
atrStopMult = input.float(1.5, "ATR Stop Loss Multiplier", minval=0.5, maxval=5.0, step=0.1, group=grp_risk)
atrTrailMult = input.float(2.0, "ATR Trailing Stop Multiplier", minval=0.5, maxval=5.0, step=0.1, group=grp_risk)
maxDrawdown = input.float(20.0, "Max Drawdown %", minval=1, maxval=50, step=1, group=grp_risk)

grp_display = "📈 Display"
showSignals = input.bool(true, "Show Entry Signals", group=grp_display)
showEma = input.bool(true, "Show EMA 200", group=grp_display)
showBackgroundColor = input.bool(true, "Show Background Color", group=grp_display)

// ============================================================================
// INDICATORS
// ============================================================================

// RSI (14 period)
rsi = ta.rsi(close, 14)

// EMA 200 (Trend Filter)
ema200 = ta.ema(close, 200)
aboveEma = close > ema200

// ADX (14 period) - Trend Strength
[diplus, diminus, adx] = ta.dmi(14, 14)
lowAdx = adx < adxMax

// ATR (14 period) - Volatility for Stops
atr = ta.atr(14)
stopDistance = atr * atrStopMult
trailDistance = atr * atrTrailMult

// Volume Confirmation
volSma = ta.sma(volume, 20)
volRatio = volume / volSma
highVolume = volRatio > volMult

// ============================================================================
// DIVERGENCE DETECTION
// ============================================================================
// Bullish Divergence: Price makes lower low, RSI makes higher low
// Bearish Divergence: Price makes higher high, RSI makes lower high

lookback = 5

// Find recent lows and highs
priceLow = ta.lowest(low, lookback)
priceHigh = ta.highest(high, lookback)
rsiLow = ta.lowest(rsi, lookback)
rsiHigh = ta.highest(rsi, lookback)

// Check if price is at recent low/high
atPriceLow = low == priceLow
atPriceHigh = high == priceHigh
atRsiLow = rsi == rsiLow
atRsiHigh = rsi == rsiHigh

// Bullish Divergence: Price at low, RSI NOT at low (or making higher low)
bullishDiv = false
if atPriceLow
    // Check if RSI is making a higher low
    prevRsiLow = ta.lowest(rsi, lookback * 2)[lookback]
    if rsi > prevRsiLow
        bullishDiv := true

// Bearish Divergence: Price at high, RSI NOT at high (or making lower high)
bearishDiv = false
if atPriceHigh
    // Check if RSI is making a lower high
    prevRsiHigh = ta.highest(rsi, lookback * 2)[lookback]
    if rsi < prevRsiHigh
        bearishDiv := true

// ============================================================================
// ENTRY CONDITIONS
// ============================================================================

// Count confirmations for LONG
longConfirms = 0
if not useEmaFilter or aboveEma
    longConfirms += 1
if not useAdxFilter or lowAdx
    longConfirms += 1
if not useVolConfirm or highVolume
    longConfirms += 1
if not useDivergence or bullishDiv
    longConfirms += 1

// Count confirmations for SHORT
shortConfirms = 0
if not useEmaFilter or not aboveEma
    shortConfirms += 1
if not useAdxFilter or lowAdx
    shortConfirms += 1
if not useVolConfirm or highVolume
    shortConfirms += 1
if not useDivergence or bearishDiv
    shortConfirms += 1

// Final Entry Signals
longCondition = (rsi < rsiOversold) and (longConfirms >= confirmationsNeeded)
shortCondition = (rsi > rsiOverbought) and (shortConfirms >= confirmationsNeeded)

// ============================================================================
// DRAWDDOWN CHECK
// ============================================================================
// Calculate current drawdown
peakEquity = ta.highest(strategy.equity, 100)
currentDD = ((strategy.equity - peakEquity) / peakEquity) * 100
inDrawdownLimit = currentDD > -maxDrawdown

// ============================================================================
// EXECUTION
// ============================================================================

// Long Entry
if longCondition and inDrawdownLimit and strategy.position_size == 0
    strategy.entry("Long", strategy.long, comment="LONG")
    // Set stop loss and trailing stop
    strategy.exit("Exit Long", "Long",
                  stop=close - stopDistance,
                  trail_price=close,
                  trail_offset=trailDistance,
                  comment="Trailing SL")

// Short Entry
if shortCondition and inDrawdownLimit and strategy.position_size == 0
    strategy.entry("Short", strategy.short, comment="SHORT")
    // Set stop loss and trailing stop
    strategy.exit("Exit Short", "Short",
                  stop=close + stopDistance,
                  trail_price=close,
                  trail_offset=trailDistance,
                  comment="Trailing SL")

// ============================================================================
// PLOTTING & VISUALS
// ============================================================================

// EMA 200
plot(showEma ? ema200 : na, "EMA 200", color=color.blue, linewidth=2)

// Background color for signals
bgcolor(showBackgroundColor and longCondition ? color.new(color.green, 90) : na, title="Long Signal")
bgcolor(showBackgroundColor and shortCondition ? color.new(color.red, 90) : na, title="Short Signal")

// Plot entry signals
plotshape(showSignals and longCondition ? low : na, "Long Signal", 
          shape.triangleup, location.belowbar, color.green, size=size.small)
plotshape(showSignals and shortCondition ? high : na, "Short Signal", 
          shape.triangledown, location.abovebar, color.red, size=size.small)

// Divergence markers
plotshape(showSignals and bullishDiv ? low : na, "Bullish Div", 
          shape.circle, location.belowbar, color.yellow, size=size.tiny, text="BD")
plotshape(showSignals and bearishDiv ? high : na, "Bearish Div", 
          shape.circle, location.abovebar, color.orange, size=size.tiny, text="BD")

// ============================================================================
// ALERTS
// ============================================================================
alertcondition(longCondition, title="V3 Long Signal", message="V3 LONG: {{ticker}} RSI={{plot(rsi)}} Confirms={{longConfirms}}")
alertcondition(shortCondition, title="V3 Short Signal", message="V3 SHORT: {{ticker}} RSI={{plot(rsi)}} Confirms={{shortConfirms}}")
alertcondition(bullishDiv, title="V3 Bullish Divergence", message="V3 BULLISH DIV: {{ticker}}")
alertcondition(bearishDiv, title="V3 Bearish Divergence", message="V3 BEARISH DIV: {{ticker}}")

// ============================================================================
// INFORMATION PANEL
// ============================================================================
var table infoTable = table.new(position.top_right, 2, 8, bgcolor=color.black)

if barstate.islast
    table.cell(infoTable, 0, 0, "V3 Multi-Metric", text_color=color.white, text_size=size.small)
    table.cell(infoTable, 1, 0, "", text_color=color.white)
    
    table.cell(infoTable, 0, 1, "RSI", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 1, str.tostring(rsi, "#.##"), text_color=rsi < rsiOversold ? color.green : rsi > rsiOverbought ? color.red : color.white, text_size=size.tiny)
    
    table.cell(infoTable, 0, 2, "ADX", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 2, str.tostring(adx, "#.##"), text_color=lowAdx ? color.green : color.orange, text_size=size.tiny)
    
    table.cell(infoTable, 0, 3, "Vol Ratio", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 3, str.tostring(volRatio, "#.##x"), text_color=highVolume ? color.green : color.gray, text_size=size.tiny)
    
    table.cell(infoTable, 0, 4, "Bull Div", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 4, bullishDiv ? "YES" : "NO", text_color=bullishDiv ? color.yellow : color.gray, text_size=size.tiny)
    
    table.cell(infoTable, 0, 5, "Bear Div", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 5, bearishDiv ? "YES" : "NO", text_color=bearishDiv ? color.orange : color.gray, text_size=size.tiny)
    
    table.cell(infoTable, 0, 6, "Long Confirms", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 6, str.tostring(longConfirms) + "/4", text_color=longConfirms >= confirmationsNeeded ? color.green : color.gray, text_size=size.tiny)
    
    table.cell(infoTable, 0, 7, "Short Confirms", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 7, str.tostring(shortConfirms) + "/4", text_color=shortConfirms >= confirmationsNeeded ? color.red : color.gray, text_size=size.tiny)

// ============================================================================
// STRATEGY INFO
// ============================================================================
// Display current position info
if strategy.position_size > 0
    label.new(bar_index, high, "📈 LONG\nEntry: " + str.tostring(strategy.position_avg_price, "#.##") + 
              "\nTrail: " + str.tostring(close - trailDistance, "#.##"), 
              color=color.green, textcolor=color.white, style=label.style_label_down)
else if strategy.position_size < 0
    label.new(bar_index, low, "📉 SHORT\nEntry: " + str.tostring(strategy.position_avg_price, "#.##") + 
              "\nTrail: " + str.tostring(close + trailDistance, "#.##"), 
              color=color.red, textcolor=color.white, style=label.style_label_up)
