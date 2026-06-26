#!/usr/bin/env python3
"""
Position Proposer Module

Generates complete trade proposals by combining:
- Market screening ( OpportunityScreener )
- Risk management ( RiskManager )
- Side determination ( RSI-based mean reversion )

Output: JSON proposal files ready for execution
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.api.hyperliquid import HyperliquidClient
from modules.screener import OpportunityScreener
from modules.risk import RiskManager, RiskConfig
from modules.strategy_selector import StrategySelector

# Import strategy loader for 4-strategy matching
try:
    from modules.strategy_loader import load_strategies_from_profile
    STRATEGY_LOADER_AVAILABLE = True
except ImportError:
    STRATEGY_LOADER_AVAILABLE = False
    print("⚠️  Strategy loader not available - using basic RSI logic")


class PositionProposer:
    """
    Generates trade proposals from market scans.
    
    Usage:
        proposer = PositionProposer(client, config)
        proposals = proposer.generate_proposals()
        proposer.save_proposals(proposals)
    """
    
    def __init__(
        self,
        client: HyperliquidClient,
        config: Optional[RiskConfig] = None,
        output_dir: str = "data/proposals",
        min_score: int = 55,
        max_proposals: int = 5,
        soul_path: str = None,
        account_client: HyperliquidClient = None,  # Separate client for account state
        testnet: bool = True
    ):
        """
        Initialize the proposer.
        
        Args:
            client: Hyperliquid API client
            config: Risk configuration
            output_dir: Directory for proposal JSON files
            min_score: Minimum opportunity score
            max_proposals: Maximum proposals to generate
            soul_path: Path to soul.md strategy file
            testnet: Whether execution is on testnet (filters universe accordingly)
        """
        self.client = client
        self.account_client = account_client or client  # Use provided client or fallback to main client
        self.config = config or RiskConfig()
        self.risk = RiskManager(self.account_client, self.config)  # Use account client for risk checks
        self.screener = OpportunityScreener(client, testnet=testnet)
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.min_score = min_score
        self.max_proposals = max_proposals
        
        # Initialize LLM-based strategy selector
        self.strategy_selector = StrategySelector()
        print(f"✅ Strategy selector loaded with {len(self.strategy_selector.strategy_profiles)} strategies")
        
        # Load strategies from soul.md if available (legacy support)
        self.strategies = {}
        if soul_path and STRATEGY_LOADER_AVAILABLE:
            try:
                self.strategies = load_strategies_from_profile(soul_path)
                print(f"✅ Loaded {len(self.strategies)} strategies from {soul_path}")
            except Exception as e:
                print(f"⚠️  Could not load strategies: {e}")
    
    def determine_side_and_strategy(self, opportunity) -> tuple:
        """
        Use LLM-based strategy selector to pick optimal strategy.
        
        Falls back to heuristic selection if LLM unavailable.
        
        Returns:
            Tuple of (side, strategy_name, strategy_id) or ("HOLD", "No Clear Setup", "none")
        """
        # Build coin data dict for strategy selector
        coin_data = {
            "coin": opportunity.coin,
            "price": opportunity.price,
            "rsi": opportunity.indicators.rsi,
            "macd_histogram": opportunity.indicators.macd_histogram,
            "adx": opportunity.indicators.adx,
            "change_24h": opportunity.change_24h_pct,
            "volume_score": opportunity.volume_score
        }
        
        # Use strategy selector (LLM-based with heuristic fallback)
        selection = self.strategy_selector.select_strategy(coin_data)
        
        if selection:
            return (
                selection["side"],
                selection["strategy_name"],
                selection["selected_strategy"]
            )
        else:
            return ("HOLD", "No Clear Setup", "none")
    
    def _determine_side_basic(self, opportunity) -> str:
        """
        Basic RSI-based side determination (fallback).
        """
        rsi = opportunity.indicators.rsi
        macd_hist = opportunity.indicators.macd_histogram
        change_24h = opportunity.change_24h_pct
        
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
    
    # Keep old method name for backwards compatibility
    def determine_side(self, opportunity) -> str:
        """Backwards compatibility - calls determine_side_and_strategy."""
        side, _, _ = self.determine_side_and_strategy(opportunity)
        return side
    
    def refine_levels(
        self,
        opportunity,
        side: str
    ) -> tuple:
        """
        Refine entry, SL, and TP levels based on side.
        
        For LONG:
        - SL below recent support (2x ATR)
        - TP above resistance (3x ATR)
        
        For SHORT:
        - SL above recent resistance (2x ATR)
        - TP below support (3x ATR)
        
        Args:
            opportunity: Scored opportunity
            side: "LONG" or "SHORT"
            
        Returns:
            Tuple of (entry_price, sl_price, tp_price)
        """
        entry = opportunity.price
        atr = opportunity.indicators.atr
        
        if side == "LONG":
            sl = entry - (atr * 2)
            tp = entry + (atr * 3)
        else:  # SHORT
            sl = entry + (atr * 2)
            tp = entry - (atr * 3)
        
        return entry, max(0, sl), max(0, tp)
    
    def build_proposal(
        self,
        opportunity,
        side: str,
        entry: float,
        sl: float,
        tp: float,
        strategy_name: str = "Basic RSI",
        strategy_id: str = "basic_rsi"
    ) -> Optional[Dict]:
        """
        Build a complete proposal dict.
        
        Args:
            opportunity: Scored opportunity
            side: "LONG" or "SHORT"
            entry: Entry price
            sl: Stop loss price
            tp: Take profit price
            strategy_name: Name of matching strategy
            strategy_id: Strategy identifier
            
        Returns:
            Proposal dict or None if invalid
        """
        # Get account state for sizing (use account_client for testnet state)
        account = self.account_client.get_account_state()
        
        # Calculate position size
        position = self.risk.calculate_position_size(
            entry_price=entry,
            stop_loss_price=sl,
            take_profit_price=tp,
            account_equity=account.total_equity
        )
        
        if not position.is_valid:
            print(f"   ⚠️  {opportunity.coin}: {position.error_message}")
            return None
        
        # Validate against existing positions (use account_client for testnet positions)
        existing_positions = self.account_client.get_perp_positions()
        is_valid, error = self.risk.validate_proposal(
            coin=opportunity.coin,
            size_usd=position.size_usd,
            existing_positions=existing_positions
        )
        
        if not is_valid:
            print(f"   ⚠️  {opportunity.coin}: {error}")
            return None
        
        # Build proposal
        proposal = {
            "symbol": f"{opportunity.coin}-PERP",
            "coin": opportunity.coin,
            "type": "PERP",
            "side": side,
            "strategy": strategy_name,
            "strategy_id": strategy_id,
            "score": opportunity.score,
            "breakdown": {
                "momentum": opportunity.momentum_score,
                "volume": opportunity.volume_score,
                "structure": opportunity.structure_score,
                "catalyst": opportunity.catalyst_score
            },
            "entry": {
                "price": entry,
                "type": "MARKET"
            },
            "entry_price": entry,
            "sl_price": sl,
            "tp_price": tp,
            "stop_loss": {
                "price": sl,
                "pct": abs(entry - sl) / entry * 100
            },
            "take_profit": {
                "price": tp,
                "pct": abs(tp - entry) / entry * 100
            },
            "position_sizing": {
                "portfolio_pct": (position.size_usd / account.total_equity) * 100,
                "size_usd": position.size_usd,
                "leverage": position.leverage,
                "total_risk_usd": position.risk_usd,
                "risk_reward_ratio": position.risk_reward_ratio
            },
            "take_profit_levels": position.tp_levels,
            "thesis": (
                f"Score {opportunity.score}/100 | "
                f"Momentum {opportunity.momentum_score}/30 | "
                f"Volume {opportunity.volume_score}/25 | "
                f"Structure {opportunity.structure_score}/25 | "
                f"Catalyst {opportunity.catalyst_score}/20"
            ),
            "market_data": {
                "price": opportunity.price,
                "volume_24h": opportunity.volume_24h,
                "change_24h_pct": opportunity.change_24h_pct,
                "rsi": opportunity.indicators.rsi,
                "adx": opportunity.indicators.adx,
                "atr_pct": opportunity.indicators.atr_pct
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return proposal
    
    def generate_proposals(self) -> List[Dict]:
        """
        Generate trade proposals from market scan.
        
        Returns:
            List of proposal dicts
        """
        print("🔍 Scanning markets...")
        
        # Run screener
        opportunities = self.screener.run_scan(
            min_score=self.min_score,
            top_n=self.max_proposals * 2  # Get extra for filtering
        )
        
        if not opportunities:
            print("ℹ️  No opportunities found")
            return []
        
        print(f"\n📊 Found {len(opportunities)} opportunities (score >= {self.min_score})")
        
        # Check account health
        health = self.risk.check_account_health()
        
        if not health.can_trade:
            print(f"⚠️  Trading disabled: {health.warnings}")
            return []
        
        # NEW: Check position count limit
        existing_positions = self.account_client.get_perp_positions()
        if len(existing_positions) >= self.risk.config.max_positions:
            print(f"⚠️  Max positions ({self.risk.config.max_positions}) already open: {len(existing_positions)} positions")
            print(f"   Current positions: {[p.coin for p in existing_positions]}")
            print("   Waiting for positions to close before opening new trades.")
            return []
        
        # Calculate how many more positions we can open
        slots_available = self.risk.config.max_positions - len(existing_positions)
        print(f"📈 {len(existing_positions)}/{self.risk.config.max_positions} positions open - can add {slots_available} more")
        
        # Generate proposals (limit to available slots)
        proposals = []
        
        for opp in opportunities:
            # Stop if we've filled all available slots
            if len(proposals) >= slots_available:
                print(f"\n✅ Reached max proposal limit ({slots_available}) for this run")
                break
            
            if len(proposals) >= self.max_proposals:
                break
            
            # Determine side AND strategy
            side, strategy_name, strategy_id = self.determine_side_and_strategy(opp)
            
            # Skip coins with no clear setup (HOLD)
            if side == "HOLD":
                print(f"\n⏸️  {opp.coin}: {strategy_name} (skipping)")
                print(f"   RSI: {opp.indicators.rsi:.1f}, MACD: {opp.indicators.macd_histogram:.2f}, ADX: {opp.indicators.adx:.1f}, 24h: {opp.change_24h_pct:+.1f}%")
                continue
            
            print(f"\n{opp.coin}: {side} via {strategy_name}")
            print(f"   RSI: {opp.indicators.rsi:.1f}, MACD: {opp.indicators.macd_histogram:.2f}, ADX: {opp.indicators.adx:.1f}")
            
            # Set strategy on opportunity (for pipeline summary)
            opp.strategy = strategy_name
            
            # Refine levels
            entry, sl, tp = self.refine_levels(opp, side)
            
            # Build proposal with strategy info
            proposal = self.build_proposal(opp, side, entry, sl, tp, strategy_name, strategy_id)
            
            if proposal:
                proposals.append(proposal)
                print(f"   ✅ Proposal generated: ${proposal['position_sizing']['size_usd']:.2f} @ {proposal['position_sizing']['leverage']}x")
        
        print(f"\n✅ Generated {len(proposals)} proposals")
        
        return proposals
    
    def save_proposals(self, proposals: List[Dict]) -> Optional[str]:
        """
        Save proposals to JSON file.
        
        Args:
            proposals: List of proposal dicts
            
        Returns:
            File path or None
        """
        if not proposals:
            return None
        
        # Generate filename
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"proposals_{timestamp}.json"
        filepath = self.output_dir / filename
        
        # Build output structure
        output = {
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "proposals_count": len(proposals),
            "max_positions": self.risk.config.max_positions,
            "criteria": {
                "min_score": self.min_score,
                "min_adx": 18.0,
                "min_liquidity": 1_000_000
            },
            "proposals": proposals
        }
        
        # Write to file
        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n💾 Saved to: {filepath}")
        
        return str(filepath)
    
    def run(self) -> Optional[str]:
        """
        Run the full proposal generation pipeline.
        
        Returns:
            File path or None
        """
        proposals = self.generate_proposals()
        filepath = self.save_proposals(proposals)
        
        return filepath


# ============================================================================
# TEST HARNESS
# ============================================================================

if __name__ == "__main__":
    from modules.api.hyperliquid import HyperliquidClient
    
    print("=" * 70)
    print("POSITION PROPOSER - TEST MODE")
    print("=" * 70)
    
    client = HyperliquidClient(testnet=True)
    proposer = PositionProposer(
        client,
        min_score=50,
        max_proposals=3
    )
    
    # Run proposal generation
    filepath = proposer.run()
    
    if filepath:
        print("\n" + "=" * 70)
        print("GENERATED PROPOSALS")
        print("=" * 70)
        
        # Load and display
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        for i, prop in enumerate(data["proposals"], 1):
            print(f"\n{i}. {prop['symbol']} ({prop['side']})")
            print(f"   Score: {prop['score']}/100")
            print(f"   Entry: ${prop['entry_price']:,.2f} ({prop['entry']['type']})")
            print(f"   SL: ${prop['sl_price']:,.2f} ({prop['stop_loss']['pct']:.2f}%)")
            print(f"   TP: ${prop['tp_price']:,.2f} ({prop['take_profit']['pct']:.2f}%)")
            print(f"   Size: ${prop['position_sizing']['size_usd']:.2f} @ {prop['position_sizing']['leverage']}x")
            print(f"   Risk: ${prop['position_sizing']['total_risk_usd']:.2f}")
            print(f"   R:R: {prop['position_sizing']['risk_reward_ratio']:.2f}x")
            print(f"   TP Levels: {len(prop['take_profit_levels'])}")
            
            for tp in prop['take_profit_levels']:
                print(f"      TP{tp['level']}: {tp['pct']*100:.0f}% @ ${tp['target_price']:,.2f} ({tp['risk_multiple']}x)")
    else:
        print("\n⚠️  No proposals generated")
    
    print("\n✅ Test complete!")
