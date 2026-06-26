#!/usr/bin/env python3
"""
LLM-Based Strategy Selector

Uses LLM to analyze market conditions and select the optimal strategy
from available strategy profiles (soul.md files).
"""

import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple


class StrategySelector:
    """
    LLM-powered strategy selection based on market regime and strategy profiles.
    """
    
    def __init__(self, strategies_dir: str = "/mnt/data/hermes/workspace/crypto-trading-bot/strategies"):
        self.strategies_dir = Path(strategies_dir)
        self.strategy_profiles = self._load_strategy_profiles()
    
    def _load_strategy_profiles(self) -> Dict[str, str]:
        """Load all strategy soul.md files."""
        profiles = {}
        
        if not self.strategies_dir.exists():
            print(f"⚠️  Strategies directory not found: {self.strategies_dir}")
            return profiles
        
        for profile_file in self.strategies_dir.glob("*.md"):
            try:
                content = profile_file.read_text()
                # Extract strategy ID from frontmatter
                if "**Strategy ID:**" in content:
                    for line in content.split("\n"):
                        if "**Strategy ID:**" in line:
                            strategy_id = line.split("`")[1]
                            profiles[strategy_id] = content
                            break
            except Exception as e:
                print(f"⚠️  Could not load {profile_file.name}: {e}")
        
        return profiles
    
    def build_strategy_prompt(self, coin_data: Dict) -> str:
        """
        Build the LLM prompt for strategy selection.
        
        Args:
            coin_data: Dict with coin metrics and indicators
        
        Returns:
            Formatted prompt string
        """
        prompt = f"""You are a crypto trading strategy selector. Your job is to choose the BEST strategy for the current market conditions.

## Available Strategies

You have access to these strategy profiles:

{chr(10).join([f"### {sid}" for sid in self.strategy_profiles.keys()])}

## Current Market Data

**Coin:** {coin_data.get('coin', 'UNKNOWN')}
**Price:** ${coin_data.get('price', 0):,.2f}

### Technical Indicators
- **RSI (14):** {coin_data.get('rsi', 0):.1f}
- **MACD Histogram:** {coin_data.get('macd_histogram', 0):.4f}
- **ADX (14):** {coin_data.get('adx', 0):.1f}
- **24h Change:** {coin_data.get('change_24h', 0):+.1f}%
- **Volume Score:** {coin_data.get('volume_score', 0)}/30

### Market Regime Analysis

Based on the indicators:
- **Trend Strength:** {'STRONG' if coin_data.get('adx', 0) > 30 else 'MODERATE' if coin_data.get('adx', 0) > 20 else 'WEAK/RANGING'}
- **Direction:** {'UPTREND' if coin_data.get('change_24h', 0) > 3 else 'DOWNTREND' if coin_data.get('change_24h', 0) < -3 else 'SIDEWAYS'}
- **Momentum:** {'STRONG' if abs(coin_data.get('change_24h', 0)) > 5 else 'MODERATE' if abs(coin_data.get('change_24h', 0)) > 2 else 'WEAK'}
- **RSI State:** {'OVERBOUGHT' if coin_data.get('rsi', 0) > 70 else 'OVERSOLD' if coin_data.get('rsi', 0) < 30 else 'NEUTRAL'}

## Your Task

Select the SINGLE BEST strategy for these conditions.

### Decision Framework

1. **If ADX > 30 and |24h change| > 5%:** Strong trend → Use Trend Pullback or Momentum Breakout
2. **If ADX < 20 and |24h change| < 3%:** Ranging → Use Mean Reversion RSI
3. **If RSI extreme (>75 or <25):** Consider fading the extreme (if ranging) or waiting (if trending)
4. **If ADX 20-30:** Moderate trend → Momentum Breakout if volume supports it

### Critical Rules

- NEVER short strong uptrends (ADX > 30, +24h > 5%)
- NEVER long strong downtrends (ADX > 30, -24h < -5%)
- In strong trends, wait for pullbacks (RSI < 45 in uptrend, > 55 in downtrend)
- In ranging markets, fade RSI extremes (>70 short, <30 long)
- If no strategy fits well, recommend HOLD

## Output Format

Respond in JSON format ONLY:

```json
{{
    "selected_strategy": "strategy_id",
    "strategy_name": "Human-readable name",
    "side": "LONG or SHORT or HOLD",
    "confidence": 0-100,
    "reasoning": "2-3 sentences explaining why this strategy fits current conditions",
    "entry_conditions": ["list", "of", "specific", "conditions", "met"],
    "risk_factors": ["list", "of", "risks", "to", "watch"],
    "alternative_strategy": "backup strategy if primary fails"
}}
```

## Example Response

```json
{{
    "selected_strategy": "trend_pullback",
    "strategy_name": "Trend Pullback",
    "side": "LONG",
    "confidence": 78,
    "reasoning": "Strong uptrend (ADX 35, +7% 24h) with RSI dipping to 42, ideal pullback entry. Momentum still bullish per MACD.",
    "entry_conditions": ["ADX > 30", "24h change +7%", "RSI dipped to 42", "MACD bullish"],
    "risk_factors": ["RSI could dip further", "Trend exhaustion if RSI > 80"],
    "alternative_strategy": "momentum_breakout"
}}
```

Now analyze the data above and select the best strategy."""
        
        return prompt
    
    def select_strategy(self, coin_data: Dict, llm_client=None) -> Optional[Dict]:
        """
        Select best strategy using LLM.
        
        Args:
            coin_data: Dict with coin metrics
            llm_client: Optional LLM client (defaults to simple heuristic if None)
        
        Returns:
            Dict with strategy selection or None if HOLD
        """
        if not self.strategy_profiles:
            print("⚠️  No strategy profiles loaded, using heuristic fallback")
            return self._heuristic_selection(coin_data)
        
        # Build prompt
        prompt = self.build_strategy_prompt(coin_data)
        
        # Call LLM (placeholder - integrate with your LLM client)
        if llm_client:
            try:
                response = llm_client.generate(prompt, max_tokens=500, temperature=0.1)
                # Parse JSON response
                import re
                json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
                if json_match:
                    selection = json.loads(json_match.group(1))
                    return selection
                else:
                    # Try parsing raw JSON
                    selection = json.loads(response)
                    return selection
            except Exception as e:
                print(f"⚠️  LLM selection failed: {e}, using heuristic fallback")
        
        # Fallback to heuristic
        return self._heuristic_selection(coin_data)
    
    def _heuristic_selection(self, coin_data: Dict) -> Optional[Dict]:
        """
        Heuristic-based strategy selection using market regime framework.
        
        Decision Framework (from prompt lines 88-100):
        1. If ADX > 30 and |24h change| > 5%: Strong trend → Trend Pullback or Momentum Breakout
        2. If ADX < 20 and |24h change| < 3%: Ranging → Mean Reversion RSI
        3. If RSI extreme (>75 or <25): Consider fading (if ranging) or waiting (if trending)
        4. If ADX 20-30: Moderate trend → Momentum Breakout if volume supports
        
        Strategies:
        1. Mean Reversion RSI - RSI extremes in ranging markets
        2. Momentum Breakout - Breakouts with volume spike and ADX
        3. Funding Contrarian - Crowded trades via funding rate
        4. Regime-Adaptive MR - Alt/BTC divergence in ranging markets
        5. Ross Cameron Momentum - High momentum setups
        6. Power of 3 - Accumulation/manipulation/distribution patterns
        """
        rsi = coin_data.get('rsi', 50)
        macd_hist = coin_data.get('macd_histogram', 0)
        adx = coin_data.get('adx', 0)
        change_24h = coin_data.get('change_24h', 0)
        volume_score = coin_data.get('volume_score', 0)
        
        # Determine market regime FIRST
        trend_strength = 'STRONG' if adx > 30 else 'MODERATE' if adx > 20 else 'WEAK'
        trend_direction = 'UPTREND' if change_24h > 3 else 'DOWNTREND' if change_24h < -3 else 'SIDEWAYS'
        momentum = 'STRONG' if abs(change_24h) > 5 else 'MODERATE' if abs(change_24h) > 2 else 'WEAK'
        
        # ========== STRONG TREND REGIME (ADX > 30) ==========
        if trend_strength == 'STRONG':
            # Rule: NEVER short strong uptrends, NEVER long strong downtrends
            if trend_direction == 'UPTREND' and change_24h > 5:
                # Wait for pullback (RSI < 45) or use Momentum Breakout
                if rsi < 45 and macd_hist > 0:
                    return {
                        "selected_strategy": "ross_cameron_momentum",
                        "strategy_name": "Ross Cameron Momentum",
                        "side": "LONG",
                        "confidence": 72,
                        "reasoning": f"Strong uptrend (ADX {adx:.1f}, +{change_24h:.1f}%) with pullback (RSI {rsi:.1f})",
                        "entry_conditions": [f"ADX > 30 ({adx:.1f})", f"Uptrend +{change_24h:.1f}%", f"Pullback RSI < 45 ({rsi:.1f})"],
                        "risk_factors": ["Trend exhaustion", "RSI could go more extreme"],
                        "alternative_strategy": "momentum_breakout"
                    }
                elif change_24h > 8 and volume_score > 20:
                    return {
                        "selected_strategy": "momentum_breakout",
                        "strategy_name": "Momentum Breakout",
                        "side": "LONG",
                        "confidence": 68,
                        "reasoning": f"Strong momentum (+{change_24h:.1f}%) with volume (score {volume_score})",
                        "entry_conditions": [f"ADX > 30 ({adx:.1f})", f"Momentum +{change_24h:.1f}%", f"Volume score > 20 ({volume_score})"],
                        "risk_factors": ["Chasing top", "Momentum reversal"],
                        "alternative_strategy": "power_of_3"
                    }
                # Otherwise HOLD - waiting for better entry
                return None
            
            elif trend_direction == 'DOWNTREND' and change_24h < -5:
                # Wait for bounce (RSI > 55) or use Momentum Breakout short
                if rsi > 55 and macd_hist < 0:
                    return {
                        "selected_strategy": "ross_cameron_momentum",
                        "strategy_name": "Ross Cameron Momentum",
                        "side": "SHORT",
                        "confidence": 72,
                        "reasoning": f"Strong downtrend (ADX {adx:.1f}, {change_24h:.1f}%) with bounce (RSI {rsi:.1f})",
                        "entry_conditions": [f"ADX > 30 ({adx:.1f})", f"Downtrend {change_24h:.1f}%", f"Bounce RSI > 55 ({rsi:.1f})"],
                        "risk_factors": ["Trend exhaustion", "RSI could go more extreme"],
                        "alternative_strategy": "momentum_breakout"
                    }
                elif change_24h < -8 and volume_score > 20:
                    return {
                        "selected_strategy": "momentum_breakout",
                        "strategy_name": "Momentum Breakout",
                        "side": "SHORT",
                        "confidence": 68,
                        "reasoning": f"Strong momentum ({change_24h:.1f}%) with volume (score {volume_score})",
                        "entry_conditions": [f"ADX > 30 ({adx:.1f})", f"Momentum {change_24h:.1f}%", f"Volume score > 20 ({volume_score})"],
                        "risk_factors": ["Catching bottom", "Momentum reversal"],
                        "alternative_strategy": "power_of_3"
                    }
                # Otherwise HOLD
                return None
            
            # STRONG trend but moderate move (-5% < change < -3% or +3% < change < +5%)
            # Use Mean Reversion RSI if RSI is at extreme
            if change_24h < -3 and rsi < 40:  # Relaxed from 35 to 40
                return {
                    "selected_strategy": "mean_reversion_rsi",
                    "strategy_name": "Mean Reversion RSI",
                    "side": "LONG",
                    "confidence": 62,
                    "reasoning": f"Strong downtrend (ADX {adx:.1f}) but RSI oversold ({rsi:.1f}) - counter-trend bounce play",
                    "entry_conditions": [f"ADX > 30 ({adx:.1f})", f"Downtrend {change_24h:.1f}%", f"RSI < 40 ({rsi:.1f})"],
                    "risk_factors": ["Catching falling knife", "Trend could continue"],
                    "alternative_strategy": "ross_cameron_momentum"
                }
            if change_24h > 3 and rsi > 60:  # Relaxed from 65 to 60
                return {
                    "selected_strategy": "mean_reversion_rsi",
                    "strategy_name": "Mean Reversion RSI",
                    "side": "SHORT",
                    "confidence": 62,
                    "reasoning": f"Strong uptrend (ADX {adx:.1f}) but RSI overbought ({rsi:.1f}) - counter-trend fade",
                    "entry_conditions": [f"ADX > 30 ({adx:.1f})", f"Uptrend +{change_24h:.1f}%", f"RSI > 60 ({rsi:.1f})"],
                    "risk_factors": ["Fighting the trend", "RSI could go more extreme"],
                    "alternative_strategy": "ross_cameron_momentum"
                }
            
            # STRONG trend with RSI in middle zone - use momentum
            if abs(change_24h) > 3 and 40 <= rsi <= 60:
                side = "SHORT" if change_24h < 0 else "LONG"
                return {
                    "selected_strategy": "ross_cameron_momentum",
                    "strategy_name": "Ross Cameron Momentum",
                    "side": side,
                    "confidence": 65,
                    "reasoning": f"Strong {side.lower()}trend (ADX {adx:.1f}, {change_24h:+.1f}%) with neutral RSI ({rsi:.1f})",
                    "entry_conditions": [f"ADX > 30 ({adx:.1f})", f"Trend {change_24h:+.1f}%", f"RSI 40-60 ({rsi:.1f})"],
                    "risk_factors": ["Trend reversal", "Momentum fading"],
                    "alternative_strategy": "momentum_breakout"
                }
            
            # STRONG trend - if nothing else matches, follow the trend with Ross Cameron
            # This catches cases like BTC: ADX 56.5, change -2.5%, RSI 35.5
            if adx > 30 and abs(change_24h) > 2:
                side = "SHORT" if change_24h < 0 else "LONG"
                return {
                    "selected_strategy": "ross_cameron_momentum",
                    "strategy_name": "Ross Cameron Momentum",
                    "side": side,
                    "confidence": 60,
                    "reasoning": f"Strong {side.lower()}trend (ADX {adx:.1f}, {change_24h:+.1f}%) - momentum play",
                    "entry_conditions": [f"ADX > 30 ({adx:.1f})", f"Trend {change_24h:+.1f}%"],
                    "risk_factors": ["Trend exhaustion", "Reversal risk"],
                    "alternative_strategy": "mean_reversion_rsi"
                }
        
        # ========== RANGING REGIME (ADX < 20) ==========
        if trend_strength == 'WEAK':
            # Mean Reversion RSI is best for ranging markets
            # Fade RSI extremes
            if rsi < 35:
                if macd_hist > 0 or rsi < 25:
                    return {
                        "selected_strategy": "mean_reversion_rsi",
                        "strategy_name": "Mean Reversion RSI",
                        "side": "LONG",
                        "confidence": 70 if rsi < 25 else 65,
                        "reasoning": f"Ranging market (ADX {adx:.1f}), oversold RSI ({rsi:.1f})",
                        "entry_conditions": [f"ADX < 20 ({adx:.1f})", f"RSI < 35 ({rsi:.1f})", "MACD positive or RSI < 25"],
                        "risk_factors": ["Range breakdown", "False reversal"],
                        "alternative_strategy": "regime_adaptive_mr"
                    }
            if rsi > 65:
                if macd_hist < 0 or rsi > 75:
                    return {
                        "selected_strategy": "mean_reversion_rsi",
                        "strategy_name": "Mean Reversion RSI",
                        "side": "SHORT",
                        "confidence": 70 if rsi > 75 else 65,
                        "reasoning": f"Ranging market (ADX {adx:.1f}), overbought RSI ({rsi:.1f})",
                        "entry_conditions": [f"ADX < 20 ({adx:.1f})", f"RSI > 65 ({rsi:.1f})", "MACD negative or RSI > 75"],
                        "risk_factors": ["Range breakout", "False reversal"],
                        "alternative_strategy": "regime_adaptive_mr"
                    }
            
            # Regime-Adaptive MR for altcoin divergence
            btc_corr = coin_data.get('btc_correlation', 0.8)
            if btc_corr < 0.5 and 40 < rsi < 60:
                return {
                    "selected_strategy": "regime_adaptive_mr",
                    "strategy_name": "Regime-Adaptive MR",
                    "side": "LONG" if macd_hist > 0 else "SHORT",
                    "confidence": 62,
                    "reasoning": f"Low BTC correlation ({btc_corr:.2f}), neutral RSI ({rsi:.1f}), MACD {macd_hist:+.4f}",
                    "entry_conditions": [f"BTC correlation < 0.5 ({btc_corr:.2f})", "RSI 40-60", "MACD signal"],
                    "risk_factors": ["Correlation could increase", "BTC move could drag"],
                    "alternative_strategy": "mean_reversion_rsi"
                }
        
        # ========== MODERATE TREND REGIME (ADX 20-30) ==========
        if trend_strength == 'MODERATE':
            # Momentum Breakout if volume supports
            breakout = coin_data.get('is_breakout', False)
            volume_spike = coin_data.get('volume_spike', 1.0)
            
            if breakout and volume_spike > 1.5:
                side = "LONG" if change_24h > 0 else "SHORT"
                return {
                    "selected_strategy": "momentum_breakout",
                    "strategy_name": "Momentum Breakout",
                    "side": side,
                    "confidence": 66,
                    "reasoning": f"Moderate trend (ADX {adx:.1f}), breakout with {volume_spike:.1f}x volume",
                    "entry_conditions": [
                        f"ADX 20-30 ({adx:.1f})",
                        f"Breakout with {volume_spike:.1f}x volume",
                        f"{'Positive' if side == 'LONG' else 'Negative'} momentum ({change_24h:+.1f}%)"
                    ],
                    "risk_factors": ["False breakout", "Trend weakening"],
                    "alternative_strategy": "ross_cameron_momentum"
                }
            
            # Power of 3 pattern detection (accumulation/manipulation/distribution)
            # Simplified: look for consolidation after move
            if abs(change_24h) > 3 and 25 < adx < 35:
                # Check if price is consolidating (simplified: RSI 40-60 after move)
                if 40 < rsi < 60:
                    side = "LONG" if change_24h > 0 else "SHORT"
                    return {
                        "selected_strategy": "power_of_3",
                        "strategy_name": "Power of 3",
                        "side": side,
                        "confidence": 64,
                        "reasoning": f"Consolidation after {'up' if side == 'LONG' else 'down'} move (ADX {adx:.1f}, RSI {rsi:.1f})",
                        "entry_conditions": [
                            f"Strong move ({change_24h:+.1f}%)",
                            f"Consolidation (RSI 40-60, ADX {adx:.1f})",
                            "Waiting for continuation"
                        ],
                        "risk_factors": ["Reversal instead of continuation", "Consolidation too long"],
                        "alternative_strategy": "momentum_breakout"
                    }
        
        # ========== FUNDING CONTRARIAN (works in any regime) ==========
        funding_rate = coin_data.get('funding_rate_8h', 0.0)
        oi_change = coin_data.get('oi_change_24h_pct', 0.0)
        
        # LONG: Shorts are crowded
        if funding_rate < -0.0003 and oi_change > 5.0 and rsi > 35:
            return {
                "selected_strategy": "funding_contrarian",
                "strategy_name": "Funding Contrarian",
                "side": "LONG",
                "confidence": 68,
                "reasoning": f"Crowded shorts (funding {funding_rate*100:.3f}%, OI +{oi_change:.1f}%)",
                "entry_conditions": [f"Funding < -0.03% ({funding_rate*100:.3f}%)", f"OI +{oi_change:.1f}%", "RSI > 35"],
                "risk_factors": ["Short squeeze could continue"],
                "alternative_strategy": "mean_reversion_rsi"
            }
        
        # SHORT: Longs are crowded
        if funding_rate > 0.0008 and oi_change > 7.0 and rsi < 65:
            return {
                "selected_strategy": "funding_contrarian",
                "strategy_name": "Funding Contrarian",
                "side": "SHORT",
                "confidence": 68,
                "reasoning": f"Crowded longs (funding {funding_rate*100:.3f}%, OI +{oi_change:.1f}%)",
                "entry_conditions": [f"Funding > 0.08% ({funding_rate*100:.3f}%)", f"OI +{oi_change:.1f}%", "RSI < 65"],
                "risk_factors": ["Long squeeze could continue"],
                "alternative_strategy": "mean_reversion_rsi"
            }
        
        # No clear setup
        return None


def main():
    """Test strategy selector."""
    selector = StrategySelector()
    
    print(f"Loaded {len(selector.strategy_profiles)} strategy profiles:")
    for sid in selector.strategy_profiles.keys():
        print(f"  - {sid}")
    
    # Test case 1: Strong uptrend
    print("\n" + "="*70)
    print("Test 1: Strong Uptrend (SOL +8%, ADX 35)")
    print("="*70)
    
    test_data = {
        "coin": "SOL",
        "price": 68.50,
        "rsi": 42,
        "macd_histogram": 0.15,
        "adx": 35,
        "change_24h": 8.0,
        "volume_score": 25
    }
    
    selection = selector.select_strategy(test_data)
    if selection:
        print(f"Selected: {selection['strategy_name']} ({selection['side']})")
        print(f"Confidence: {selection['confidence']}%")
        print(f"Reasoning: {selection['reasoning']}")
    else:
        print("Result: HOLD (no suitable strategy)")
    
    # Test case 2: Ranging market
    print("\n" + "="*70)
    print("Test 2: Ranging Market (ETH +1%, ADX 15)")
    print("="*70)
    
    test_data = {
        "coin": "ETH",
        "price": 1650,
        "rsi": 73,
        "macd_histogram": -0.08,
        "adx": 15,
        "change_24h": 1.2,
        "volume_score": 12
    }
    
    selection = selector.select_strategy(test_data)
    if selection:
        print(f"Selected: {selection['strategy_name']} ({selection['side']})")
        print(f"Confidence: {selection['confidence']}%")
        print(f"Reasoning: {selection['reasoning']}")
    else:
        print("Result: HOLD (no suitable strategy)")
    
    # Test case 3: Strong downtrend
    print("\n" + "="*70)
    print("Test 3: Strong Downtrend (AAVE -12%, ADX 40)")
    print("="*70)
    
    test_data = {
        "coin": "AAVE",
        "price": 75.00,
        "rsi": 62,
        "macd_histogram": -0.25,
        "adx": 40,
        "change_24h": -12.0,
        "volume_score": 28
    }
    
    selection = selector.select_strategy(test_data)
    if selection:
        print(f"Selected: {selection['strategy_name']} ({selection['side']})")
        print(f"Confidence: {selection['confidence']}%")
        print(f"Reasoning: {selection['reasoning']}")
    else:
        print("Result: HOLD (no suitable strategy)")


if __name__ == "__main__":
    main()
