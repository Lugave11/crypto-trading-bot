#!/usr/bin/env python3
"""
Opportunity Screener Module

Scans markets, calculates technical indicators, and scores trading opportunities.
Uses the Hyperliquid API client for market data.

Features:
- Large-cap universe filtering
- Technical indicators (RSI, MACD, ADX, ATR)
- Opportunity scoring (0-100)
- Volume and volatility filtering
"""

import sys
import os
import math
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.api.hyperliquid import HyperliquidClient
from modules.strategy_selector import StrategySelector


@dataclass
class CoinData:
    """Raw market data for a coin."""
    coin: str
    price: float
    volume_24h: float
    change_24h_pct: float
    candles_1h: List[Dict]  # Last 100 1h candles
    candles_4h: List[Dict]  # Last 50 4h candles
    funding_rate_8h: float = 0.0  # 8-hour funding rate
    oi_change_24h_pct: float = 0.0  # Open interest change
    # Breakout detection
    is_breakout: bool = False  # Price making new high/low
    volume_spike: float = 1.0  # Current vol / avg vol
    high_24h: float = 0.0  # 24h high
    low_24h: float = 0.0  # 24h low


@dataclass
class Indicators:
    """Calculated technical indicators."""
    rsi: float  # 14-period RSI
    macd: float  # MACD line
    macd_signal: float  # Signal line
    macd_histogram: float  # Histogram
    adx: float  # 14-period ADX
    atr: float  # 14-period ATR
    atr_pct: float  # ATR as % of price


@dataclass
class Opportunity:
    """Scored trading opportunity."""
    coin: str
    score: int  # 0-100
    side: str  # "LONG" or "SHORT"
    price: float
    volume_24h: float
    change_24h_pct: float
    indicators: Indicators
    
    # Scoring breakdown
    momentum_score: int  # 0-30
    volume_score: int  # 0-25
    structure_score: int  # 0-25
    catalyst_score: int  # 0-20
    
    # Entry/exit levels
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    
    # Metadata
    timestamp: datetime
    
    # Strategy (must have default to satisfy dataclass field ordering)
    strategy: str = "Unknown"  # Strategy name (set by proposer)


class OpportunityScreener:
    """
    Scans markets for trading opportunities.
    
    Usage:
        screener = OpportunityScreener(client)
        opportunities = screener.run_scan()
    """
    
    # Large-cap universe (top 40 by market cap)
    LARGE_CAPS = [
        "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "TRX", "DOT",
        "MATIC", "LINK", "ATOM", "UNI", "LTC", "ETC", "NEAR", "XMR", "BCH", "APT",
        "FIL", "ARB", "OP", "VET", "ALGO", "ICP", "QNT", "GRT", "AAVE", "MKR",
        "SNX", "SAND", "MANA", "AXS", "THETA", "XTZ", "EOS", "FTM", "EGLD", "RUNE"
    ]
    
    # Scoring thresholds
    MIN_VOLUME_24H = 1_000_000  # $1M minimum
    VOLATILITY_SWEET_SPOT = (5.0, 10.0)  # 5-10% 24h change = max score
    
    def __init__(self, client: HyperliquidClient, testnet: bool = True):
        """
        Initialize the screener.
        
        Args:
            client: Hyperliquid API client
            testnet: Whether execution is on testnet (filters universe accordingly)
        """
        self.client = client
        self.testnet = testnet
        self.strategy_selector = StrategySelector()
        
        # Filter LARGE_CAPS to only include coins available on testnet
        if testnet:
            self.large_caps = self._filter_testnet_coins(self.LARGE_CAPS)
            print(f"✅ Screener: {len(self.large_caps)}/{len(self.LARGE_CAPS)} large caps available on testnet")
        else:
            self.large_caps = list(self.LARGE_CAPS)
    
    def _filter_testnet_coins(self, coins: List[str]) -> List[str]:
        """Filter coins to only include those available on testnet."""
        try:
            url = "https://api.hyperliquid-testnet.xyz/info"
            meta = requests.post(url, json={"type": "meta"}, timeout=10).json()
            testnet_coins = {c['name'] for c in meta.get('universe', [])}
            filtered = [c for c in coins if c in testnet_coins]
            excluded = [c for c in coins if c not in testnet_coins]
            print(f"   ℹ️  Excluded from testnet: {', '.join(excluded)}")
            return filtered
        except Exception as e:
            print(f"⚠️  Could not filter testnet coins: {e}")
            return list(coins)  # Return all if we can't fetch the list
    
    def fetch_universe(self) -> List[CoinData]:
        """
        Fetch market data for all coins in the universe.
        
        Returns:
            List of CoinData objects
        """
        coin_data = []
        
        for coin in self.large_caps:
            try:
                # Get current price
                price = self.client.get_current_price(coin)
                if price <= 0:
                    continue
                
                # Get 1h candles for indicators
                candles_1h = self.client.get_candles(coin, interval="1h", limit=100)
                if not candles_1h:
                    continue
                
                # Get 4h candles for trend context
                candles_4h = self.client.get_candles(coin, interval="4h", limit=50)
                
                # Calculate 24h volume and change from 1h candles
                volume_24h = sum(c.get("volume", 0) * c.get("close", 0) for c in candles_1h[-24:])
                change_24h_pct = ((candles_1h[-1]["close"] - candles_1h[-24]["close"]) / candles_1h[-24]["close"]) * 100 if len(candles_1h) >= 24 else 0
                
                # Calculate 24h high/low for breakout detection
                high_24h = max(c.get("high", 0) for c in candles_1h[-24:]) if len(candles_1h) >= 24 else price
                low_24h = min(c.get("low", 0) for c in candles_1h[-24:]) if len(candles_1h) >= 24 else price
                
                # Detect breakout (price above 24h high or below 24h low)
                is_breakout = price > high_24h * 1.01 or price < low_24h * 0.99  # 1% beyond
                
                # Calculate volume spike (current hour vs 24h average)
                avg_hourly_vol = volume_24h / 24 if volume_24h > 0 else 1
                current_hour_vol = candles_1h[-1].get("volume", 0) * candles_1h[-1].get("close", 0) if candles_1h else 0
                volume_spike = current_hour_vol / avg_hourly_vol if avg_hourly_vol > 0 else 1.0
                
                # Get funding rate
                funding_data = self.client.get_funding_rates(coin)
                funding_rate_8h = funding_data["funding_rate_8h"] if funding_data else 0.0
                
                # Get OI data
                oi_data = self.client.get_open_interest(coin)
                if oi_data:
                    prev_px = oi_data.get("prev_day_px", 0)
                    if prev_px > 0:
                        oi_change_24h_pct = ((price - prev_px) / prev_px) * 100
                    else:
                        oi_change_24h_pct = 0.0
                else:
                    oi_change_24h_pct = 0.0
                
                coin_data.append(CoinData(
                    coin=coin,
                    price=price,
                    volume_24h=volume_24h,
                    change_24h_pct=change_24h_pct,
                    candles_1h=candles_1h,
                    candles_4h=candles_4h,
                    funding_rate_8h=funding_rate_8h,
                    oi_change_24h_pct=oi_change_24h_pct,
                    is_breakout=is_breakout,
                    volume_spike=volume_spike,
                    high_24h=high_24h,
                    low_24h=low_24h
                ))
                
            except Exception as e:
                print(f"⚠️  Error fetching {coin}: {e}")
                continue
        
        return coin_data
    
    def calculate_rsi(self, candles: List[Dict], period: int = 14) -> float:
        """
        Calculate RSI (Relative Strength Index).
        
        Args:
            candles: List of candle dicts with 'close' key
            period: RSI period (default 14)
            
        Returns:
            RSI value (0-100)
        """
        if len(candles) < period + 1:
            return 50.0  # Neutral if not enough data
        
        closes = [c["close"] for c in candles[-period-1:]]
        
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_macd(self, candles: List[Dict], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        
        Args:
            candles: List of candle dicts
            fast: Fast EMA period
            slow: Slow EMA period
            signal: Signal line period
            
        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        if len(candles) < slow + signal:
            return 0.0, 0.0, 0.0
        
        closes = [c["close"] for c in candles]
        
        # Calculate EMAs
        def ema(values: List[float], period: int) -> List[float]:
            multiplier = 2 / (period + 1)
            ema_values = [sum(values[:period]) / period]
            
            for value in values[period:]:
                ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
            
            return ema_values
        
        fast_ema = ema(closes, fast)
        slow_ema = ema(closes, slow)
        
        # Align lengths
        offset = len(slow_ema) - len(fast_ema)
        if offset > 0:
            fast_ema = fast_ema[offset:]
        
        # MACD line
        macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
        
        # Signal line (EMA of MACD)
        signal_line = ema(macd_line, signal)
        
        # Histogram
        offset = len(signal_line) - len(macd_line)
        if offset > 0:
            macd_line = macd_line[offset:]
        histogram = [m - s for m, s in zip(macd_line, signal_line)]
        
        return macd_line[-1], signal_line[-1], histogram[-1]
    
    def calculate_adx(self, candles: List[Dict], period: int = 14) -> float:
        """
        Calculate ADX (Average Directional Index).
        
        Simplified calculation - measures trend strength.
        
        Args:
            candles: List of candle dicts with 'high', 'low', 'close'
            period: ADX period
            
        Returns:
            ADX value (0-100)
        """
        if len(candles) < period + 1:
            return 20.0  # Default weak trend
        
        tr_values = []
        plus_dm = []
        minus_dm = []
        
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i-1]["close"]
            prev_high = candles[i-1]["high"]
            prev_low = candles[i-1]["low"]
            
            # True Range
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
            
            # Directional Movement
            up_move = high - prev_high
            down_move = prev_low - low
            
            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0)
            
            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0)
        
        # Smooth with EMA
        def smooth(values: List[float], period: int) -> float:
            return sum(values[-period:]) / period
        
        tr_smooth = smooth(tr_values, period)
        plus_smooth = smooth(plus_dm, period)
        minus_smooth = smooth(minus_dm, period)
        
        if tr_smooth == 0:
            return 20.0
        
        plus_di = (plus_smooth / tr_smooth) * 100
        minus_di = (minus_smooth / tr_smooth) * 100
        
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
        
        return dx
    
    def calculate_atr(self, candles: List[Dict], period: int = 14) -> Tuple[float, float]:
        """
        Calculate ATR (Average True Range).
        
        Args:
            candles: List of candle dicts
            period: ATR period
            
        Returns:
            Tuple of (atr_value, atr_as_pct_of_price)
        """
        if len(candles) < period + 1:
            return 0.0, 0.0
        
        tr_values = []
        
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i-1]["close"]
            
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_values.append(tr)
        
        atr = sum(tr_values[-period:]) / period
        current_price = candles[-1]["close"]
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0
        
        return atr, atr_pct
    
    def calculate_indicators(self, coin: CoinData) -> Indicators:
        """
        Calculate all technical indicators for a coin.
        
        Args:
            coin: CoinData object
            
        Returns:
            Indicators object
        """
        candles = coin.candles_1h
        
        rsi = self.calculate_rsi(candles)
        macd, macd_signal, macd_hist = self.calculate_macd(candles)
        adx = self.calculate_adx(candles)
        atr, atr_pct = self.calculate_atr(candles)
        
        return Indicators(
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_hist,
            adx=adx,
            atr=atr,
            atr_pct=atr_pct
        )
    
    def score_momentum(self, rsi: float, macd_histogram: float, change_24h: float) -> int:
        """
        Score momentum (0-30 points).
        
        - RSI 35-65 = neutral (15 pts)
        - RSI <35 or >65 = strong signal (25-30 pts)
        - MACD histogram alignment = bonus
        - 24h change in sweet spot = bonus
        """
        score = 15  # Base score
        
        # RSI scoring
        if 30 <= rsi <= 70:
            score += 5  # Normal range
        elif rsi < 30 or rsi > 70:
            score += 15  # Extreme = strong signal
        
        # MACD histogram
        if abs(macd_histogram) > 0:
            score += 5  # MACD moving
        
        # 24h change sweet spot (5-10% = volatile but not crazy)
        abs_change = abs(change_24h)
        if 5 <= abs_change <= 10:
            score += 5  # Sweet spot
        elif 3 <= abs_change < 5 or 10 < abs_change <= 15:
            score += 3  # Decent volatility
        elif abs_change < 3:
            score += 0  # Too quiet
        elif abs_change > 15:
            score -= 5  # Too volatile (risk penalty)
        
        return max(0, min(30, score))
    
    def score_volume(self, volume_24h: float) -> int:
        """
        Score volume (0-25 points).
        
        Higher volume = better liquidity = higher score.
        """
        if volume_24h >= 10_000_000:
            return 25  # Excellent
        elif volume_24h >= 5_000_000:
            return 20
        elif volume_24h >= 1_000_000:
            return 15
        elif volume_24h >= 500_000:
            return 10
        elif volume_24h >= 100_000:
            return 5
        else:
            return 0
    
    def score_structure(self, adx: float, atr_pct: float) -> int:
        """
        Score market structure (0-25 points).
        
        - ADX > 25 = strong trend
        - ATR % in reasonable range = good volatility
        """
        score = 10  # Base
        
        # ADX scoring (trend strength)
        if adx >= 40:
            score += 10  # Very strong trend
        elif adx >= 25:
            score += 7  # Strong trend
        elif adx >= 18:
            score += 4  # Developing trend
        else:
            score += 0  # Weak/no trend
        
        # ATR % scoring (volatility quality)
        if 1 <= atr_pct <= 5:
            score += 5  # Good volatility
        elif 0.5 <= atr_pct < 1 or 5 < atr_pct <= 8:
            score += 3  # Acceptable
        else:
            score += 0  # Too low or too high
        
        return max(0, min(25, score))
    
    def score_catalyst(self, change_24h: float, volume_24h: float) -> int:
        """
        Score catalyst potential (0-20 points).
        
        High volume + significant move = likely catalyst.
        """
        score = 10  # Base
        
        abs_change = abs(change_24h)
        
        # Significant move
        if abs_change >= 10:
            score += 5
        elif abs_change >= 5:
            score += 3
        
        # Volume surge (above average)
        if volume_24h >= 10_000_000:
            score += 5
        elif volume_24h >= 5_000_000:
            score += 3
        
        return max(0, min(20, score))
    
    def determine_side(self, indicators: Indicators, change_24h: float) -> str:
        """
        Determine LONG or SHORT bias based on RSI + mean reversion.
        
        Logic:
        - RSI > 65 + weak momentum = SHORT (overbought fade)
        - RSI < 35 + positive momentum = LONG (oversold bounce)
        - Otherwise follow trend
        """
        rsi = indicators.rsi
        macd_hist = indicators.macd_histogram
        
        # Overbought = potential SHORT
        if rsi > 65:
            if macd_hist < 0 or change_24h > 5:
                return "SHORT"
        
        # Oversold = potential LONG
        if rsi < 35:
            if macd_hist > 0 or change_24h < -5:
                return "LONG"
        
        # Default: follow momentum
        if macd_hist > 0:
            return "LONG"
        elif macd_hist < 0:
            return "SHORT"
        else:
            return "LONG"  # Default bias
    
    def calculate_levels(self, coin: CoinData, side: str, indicators: Indicators) -> Tuple[float, float, float]:
        """
        Calculate entry, stop-loss, and take-profit levels.
        
        Args:
            coin: CoinData object
            side: "LONG" or "SHORT"
            indicators: Indicators object
            
        Returns:
            Tuple of (entry_price, sl_price, tp_price)
        """
        entry = coin.price
        atr = indicators.atr
        
        if side == "LONG":
            stop_loss = entry - (atr * 2)  # 2x ATR below entry
            take_profit = entry + (atr * 3)  # 3x ATR above entry (1.5x R:R)
        else:  # SHORT
            stop_loss = entry + (atr * 2)  # 2x ATR above entry
            take_profit = entry - (atr * 3)  # 3x ATR below entry
        
        return entry, max(0, stop_loss), max(0, take_profit)
    
    def score_opportunity(self, coin: CoinData, indicators: Indicators) -> Opportunity:
        """
        Generate a scored opportunity from coin data.
        
        Args:
            coin: CoinData object
            indicators: Calculated indicators
            
        Returns:
            Opportunity object with scores and levels
        """
        # Build coin data dict for strategy selector
        coin_data = {
            "coin": coin.coin,
            "price": coin.price,
            "rsi": indicators.rsi,
            "macd_histogram": indicators.macd_histogram,
            "adx": indicators.adx,
            "change_24h": coin.change_24h_pct,
            "volume_score": min(25, coin.volume_24h / 1_000_000 * 25),  # Scale to 0-25
            "funding_rate": coin.funding_rate_8h,
            "oi_change": coin.oi_change_24h_pct,
        }
        
        # Check if strategy selector sees a valid setup
        strategy_result = self.strategy_selector.select_strategy(coin_data)
        
        # If no strategy matches, return with score 0 (will be filtered out)
        if not strategy_result or strategy_result.get("side") == "HOLD":
            return Opportunity(
                coin=coin.coin,
                score=0,  # Will be filtered out
                side="HOLD",
                price=coin.price,
                volume_24h=coin.volume_24h,
                change_24h_pct=coin.change_24h_pct,
                indicators=indicators,
                momentum_score=0,
                volume_score=0,
                structure_score=0,
                catalyst_score=0,
                entry_price=coin.price,
                stop_loss_price=coin.price * 0.95,
                take_profit_price=coin.price * 1.05,
                timestamp=datetime.now(timezone.utc)
            )
        
        # Strategy matched - use its side and boost score
        side = strategy_result["side"]
        strategy_confidence = strategy_result.get("confidence", 50)
        
        # Calculate base scores
        momentum_score = self.score_momentum(indicators.rsi, indicators.macd_histogram, coin.change_24h_pct)
        volume_score = self.score_volume(coin.volume_24h)
        structure_score = self.score_structure(indicators.adx, indicators.atr_pct)
        catalyst_score = self.score_catalyst(coin.change_24h_pct, coin.volume_24h)
        
        # Base score from technicals
        total_score = momentum_score + volume_score + structure_score + catalyst_score
        
        # Boost score based on strategy confidence (up to +20 points)
        confidence_boost = int((strategy_confidence - 50) * 0.4)
        total_score = min(100, total_score + confidence_boost)
        
        # Calculate levels
        entry, sl, tp = self.calculate_levels(coin, side, indicators)
        
        return Opportunity(
            coin=coin.coin,
            score=total_score,
            side=side,
            price=coin.price,
            volume_24h=coin.volume_24h,
            change_24h_pct=coin.change_24h_pct,
            indicators=indicators,
            momentum_score=momentum_score,
            volume_score=volume_score,
            structure_score=structure_score,
            catalyst_score=catalyst_score,
            entry_price=entry,
            stop_loss_price=sl,
            take_profit_price=tp,
            strategy=strategy_result.get("strategy_name", "Unknown"),
            timestamp=datetime.now(timezone.utc)
        )
    
    def filter_opportunities(self, opportunities: List[Opportunity]) -> List[Opportunity]:
        """
        Filter opportunities by minimum criteria.
        
        Args:
            opportunities: List of scored opportunities
            
        Returns:
            Filtered list
        """
        filtered = []
        
        for opp in opportunities:
            # Minimum volume filter
            if opp.volume_24h < self.MIN_VOLUME_24H:
                continue
            
            # Minimum score filter
            if opp.score < 50:
                continue
            
            filtered.append(opp)
        
        return filtered
    
    def run_scan(self, min_score: int = 50, top_n: int = 5) -> List[Opportunity]:
        """
        Run a full market scan.
        
        Args:
            min_score: Minimum score threshold
            top_n: Number of top opportunities to return
            
        Returns:
            List of top Opportunities sorted by score
        """
        print("🔍 Starting market scan...")
        
        # Step 1: Fetch universe data
        print("   📊 Fetching market data...")
        coin_data = self.fetch_universe()
        print(f"   ✅ Fetched {len(coin_data)} coins")
        
        # Step 2: Calculate indicators and score
        print("   📈 Calculating indicators...")
        opportunities = []
        for coin in coin_data:
            try:
                indicators = self.calculate_indicators(coin)
                opp = self.score_opportunity(coin, indicators)
                opportunities.append(opp)
            except Exception as e:
                print(f"   ⚠️  Error scoring {coin.coin}: {e}")
        
        print(f"   ✅ Scored {len(opportunities)} opportunities")
        
        # Step 3: Filter
        print("   🔧 Filtering...")
        filtered = self.filter_opportunities(opportunities)
        print(f"   ✅ {len(filtered)} passed filters")
        
        # Step 4: Sort by score
        filtered.sort(key=lambda x: x.score, reverse=True)
        
        # Step 5: Return top N
        top = filtered[:top_n]
        
        print(f"\n📋 Top {len(top)} Opportunities:")
        for i, opp in enumerate(top, 1):
            print(f"   {i}. {opp.coin} | Score: {opp.score}/100 | {opp.side} @ ${opp.price:,.2f} | Vol: ${opp.volume_24h:,.0f}")
        
        return top


# ============================================================================
# TEST HARNESS
# ============================================================================

if __name__ == "__main__":
    from modules.api.hyperliquid import HyperliquidClient
    
    print("=" * 70)
    print("OPPORTUNITY SCREENER - TEST MODE")
    print("=" * 70)
    
    client = HyperliquidClient(testnet=True)
    screener = OpportunityScreener(client)
    
    # Run scan
    opportunities = screener.run_scan(min_score=40, top_n=5)
    
    if opportunities:
        print("\n" + "=" * 70)
        print("DETAILED ANALYSIS")
        print("=" * 70)
        
        for opp in opportunities:
            print(f"\n{opp.coin} ({opp.side})")
            print(f"  Score: {opp.score}/100")
            print(f"  Price: ${opp.price:,.2f}")
            print(f"  24h Change: {opp.change_24h_pct:+.2f}%")
            print(f"  Volume: ${opp.volume_24h:,.0f}")
            print(f"  RSI: {opp.indicators.rsi:.1f}")
            print(f"  ADX: {opp.indicators.adx:.1f}")
            print(f"  ATR: {opp.indicators.atr_pct:.2f}%")
            print(f"  Entry: ${opp.entry_price:,.2f}")
            print(f"  SL: ${opp.stop_loss_price:,.2f}")
            print(f"  TP: ${opp.take_profit_price:,.2f}")
            print(f"  Breakdown: Mom={opp.momentum_score}/30 Vol={opp.volume_score}/25 Str={opp.structure_score}/25 Cat={opp.catalyst_score}/20")
    
    print("\n✅ Test complete!")
