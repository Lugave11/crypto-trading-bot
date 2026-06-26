#!/usr/bin/env python3
"""
Trading Pipeline Orchestrator

Main entry point for automated trading.
Runs the full flow: Scan → Propose → Execute → Monitor

Usage:
    python3 run_pipeline.py [--dry-run] [--max-positions N] [--min-score N]
"""

import sys
import os
import json
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Add modules to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.api.hyperliquid import HyperliquidClient
from modules.screener import OpportunityScreener
from modules.risk import RiskManager, RiskConfig
from modules.proposer import PositionProposer
from modules.executor import OrderExecutor, ExecutionStatus


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_CONFIG = {
    # Trading parameters
    "testnet": True,
    "max_positions": 5,
    "risk_per_trade_pct": 2.0,
    "min_score": 55,
    
    # Position limits
    "min_position_usd": 12.0,  # Hyperliquid minimum ~$10 + buffer
    "max_position_usd": 500.0,
    "max_leverage": 10,
    "default_leverage": 3,  # Default leverage for position sizing
    "max_exposure_pct": 20.0,  # Max % of equity in single position
    
    # Kill switch
    "max_daily_loss_pct": 3.0,
    "max_weekly_loss_pct": 7.0,
    
    # CIRCUIT BREAKERS (NEW - prevent rapid repeated trading)
    "max_trades_per_hour": 3,  # Max 3 trades per hour
    "max_consecutive_losses": 2,  # Pause after 2 consecutive losses
    "cooldown_after_loss_minutes": 15,  # Wait 15 min after a loss
    "min_account_balance_usd": 50.0,  # Don't trade if balance < $50
    "max_drawdown_pct": 10.0,
    
    # Execution
    "dry_run": False,  # Simulate orders without placing
    "verify_orders": True,
    "send_notifications": True,
    
    # Logging
    "log_level": "INFO",
    "log_dir": "logs",
}


# ============================================================================
# PIPELINE ORCHESTRATOR
# ============================================================================

class TradingPipeline:
    """
    Orchestrates the full trading pipeline.
    
    Flow:
    1. Check account health (kill switch)
    2. Scan markets for opportunities
    3. Generate proposals for top opportunities
    4. Execute proposals (place orders)
    5. Verify orders
    6. Generate execution report
    """
    
    def __init__(
        self,
        config: Dict,
        account_address: str,
        private_key: Optional[str] = None
    ):
        """
        Initialize the pipeline.
        
        Args:
            config: Configuration dict
            account_address: Wallet address
            private_key: Private key for signing (required for live trading)
        """
        self.config = config
        self.account_address = account_address
        self.private_key = private_key
        self.dry_run = config.get("dry_run", False)
        
        # Setup logging
        self._setup_logging()
        
        # Initialize modules
        # CRITICAL: Market data from MAINNET, execution on TESTNET
        self.client = HyperliquidClient(testnet=config["testnet"])  # For execution
        self.market_client = HyperliquidClient(testnet=False)  # For market data (mainnet)
        
        risk_config = RiskConfig(
            max_positions=config["max_positions"],
            risk_per_trade_pct=config["risk_per_trade_pct"],
            default_leverage=config.get("default_leverage", 3),
            min_position_usd=config["min_position_usd"],
            max_position_usd=config["max_position_usd"],
            max_leverage=config["max_leverage"],
            max_exposure_pct=config.get("max_exposure_pct", 20.0),
            max_daily_loss_pct=config["max_daily_loss_pct"],
            max_weekly_loss_pct=config["max_weekly_loss_pct"],
            max_drawdown_pct=config["max_drawdown_pct"],
        )
        
        self.risk = RiskManager(self.client, risk_config)
        self.screener = OpportunityScreener(self.market_client)  # Use mainnet client for data
        
        # Find soul.md path
        soul_path = None
        workspace = Path(__file__).parent.parent
        potential_paths = [
            workspace / "soul.md",
            workspace / "crypto-trading-bot" / "soul.md",
            Path("/mnt/data/hermes/workspace/crypto-trading-bot/soul.md")
        ]
        for p in potential_paths:
            if p.exists():
                soul_path = str(p)
                break
        
        self.proposer = PositionProposer(
            self.market_client,  # Use mainnet for scanning/proposing
            config=risk_config,
            min_score=config["min_score"],
            max_proposals=config["max_positions"],
            soul_path=soul_path,  # Load strategies from soul.md
            account_client=self.client,  # Use testnet for account state
            testnet=config["testnet"]  # Filter universe to testnet coins
        )
        
        # Executor (only if private key provided)
        if private_key and not self.dry_run:
            self.executor = OrderExecutor(
                self.client,
                account_address,
                private_key,
                testnet=config["testnet"]
            )
        else:
            self.executor = None
            mode = "DRY RUN" if self.dry_run else "NO PRIVATE KEY"
            self.logger.warning(f"Executor disabled: {mode}")
        
        self.logger.info("="*70)
        self.logger.info("TRADING PIPELINE INITIALIZED")
        self.logger.info("="*70)
        self.logger.info(f"Network: {'TESTNET' if config['testnet'] else 'MAINNET'}")
        self.logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        self.logger.info(f"Max Positions: {config['max_positions']}")
        self.logger.info(f"Risk/Trade: {config['risk_per_trade_pct']}%")
        self.logger.info(f"Min Score: {config['min_score']}")
    
    def _setup_logging(self):
        """Setup logging configuration."""
        log_dir = Path(self.config.get("log_dir", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        log_file = log_dir / f"pipeline_{timestamp}.log"
        
        log_level = getattr(logging, self.config.get("log_level", "INFO").upper())
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Log file: {log_file}")
    
    def _check_kill_switch(self) -> bool:
        """
        Check if trading is allowed (kill switch not triggered).
        
        Returns:
            True if trading allowed, False if kill switch active
        """
        self.logger.info("\n" + "="*70)
        self.logger.info("STEP 1: KILL SWITCH CHECK")
        self.logger.info("="*70)
        
        health = self.risk.check_account_health()
        
        self.logger.info(f"Total Equity: ${health.total_equity:,.2f}")
        self.logger.info(f"Margin Used: ${health.margin_used:,.2f} ({health.margin_ratio:.1f}%)")
        self.logger.info(f"Drawdown: {health.current_drawdown_pct:.2f}%")
        self.logger.info(f"Risk Level: {health.risk_level.value.upper()}")
        
        # NEW: Check minimum balance
        min_balance = self.config.get("min_account_balance_usd", 50.0)
        if health.total_equity < min_balance:
            self.logger.error(f"❌ ACCOUNT BALANCE TOO LOW - ${health.total_equity:.2f} < ${min_balance:.2f} minimum")
            self.logger.error("   Please fund account before resuming trading")
            return False
        
        if health.kill_switch_active:
            self.logger.error("❌ KILL SWITCH ACTIVE - Trading paused")
            for warning in health.warnings:
                self.logger.error(f"   - {warning}")
            return False
        
        if not health.can_trade:
            self.logger.warning("⚠️  Trading disabled due to risk limits")
            for warning in health.warnings:
                self.logger.warning(f"   - {warning}")
            return False
        
        self.logger.info("✅ Kill switch OK - Trading allowed")
        return True
    
    def _scan_markets(self) -> List:
        """
        Scan markets for opportunities.
        
        Returns:
            List of scored opportunities
        """
        self.logger.info("\n" + "="*70)
        self.logger.info("STEP 2: MARKET SCAN")
        self.logger.info("="*70)
        
        opportunities = self.screener.run_scan(
            min_score=self.config["min_score"],
            top_n=self.config["max_positions"] * 2
        )
        
        self.logger.info(f"Found {len(opportunities)} opportunities (score >= {self.config['min_score']})")
        
        if opportunities:
            self.logger.info("\nTop Opportunities:")
            for i, opp in enumerate(opportunities[:5], 1):
                self.logger.info(
                    f"  {i}. {opp.coin} | Score: {opp.score}/100 | "
                    f"{opp.side} @ ${opp.price:,.2f} | "
                    f"Vol: ${opp.volume_24h:,.0f}"
                )
        
        return opportunities
    
    def _generate_proposals(self, opportunities: List) -> List[Dict]:
        """
        Generate trade proposals from opportunities.
        
        Args:
            opportunities: List of scored opportunities
            
        Returns:
            List of proposal dicts
        """
        self.logger.info("\n" + "="*70)
        self.logger.info("STEP 3: PROPOSAL GENERATION")
        self.logger.info("="*70)
        
        if not opportunities:
            self.logger.info("ℹ️  No opportunities to propose")
            return []
        
        # Get current positions to calculate available slots
        from modules.api.hyperliquid import HyperliquidClient
        client = HyperliquidClient(testnet=self.config.get("testnet", True))
        existing_positions = client.get_perp_positions()
        
        # Check for direction reversals (existing position vs new signal)
        reversals = []
        positions_by_coin = {}
        for p in existing_positions:
            # Position objects have attributes, not dict keys
            if hasattr(p, 'position') and hasattr(p.position, 'coin'):
                positions_by_coin[p.position.coin.upper()] = p
            elif isinstance(p, dict) and 'position' in p:
                positions_by_coin[p['position']['coin'].upper()] = p
        
        for opp in opportunities:
            if opp.coin.upper() not in positions_by_coin:
                continue  # No existing position for this coin
            
            # Determine proposed side
            proposed_side, strategy_name, strategy_id = self.proposer.determine_side_and_strategy(opp)
            
            if proposed_side == "HOLD":
                continue
            
            # Get existing position side
            existing_pos = positions_by_coin[opp.coin.upper()]
            # Handle both Position objects and dicts
            if hasattr(existing_pos, 'position') and hasattr(existing_pos.position, 'szi'):
                existing_szi = float(existing_pos.position.szi)
            elif isinstance(existing_pos, dict) and 'position' in existing_pos:
                existing_szi = float(existing_pos['position']['szi'])
            else:
                continue  # Skip if we can't read the position
            existing_side = "SHORT" if existing_szi < 0 else "LONG"
            
            # Check for reversal
            if (existing_side == "SHORT" and proposed_side == "LONG") or \
               (existing_side == "LONG" and proposed_side == "SHORT"):
                
                # Only reverse if new signal is high conviction (score >= 85)
                if opp.score >= 85:
                    reversals.append({
                        'coin': opp.coin,
                        'existing_side': existing_side,
                        'new_side': proposed_side,
                        'score': opp.score,
                        'strategy': strategy_name,
                        'opportunity': opp
                    })
                    self.logger.info(
                        f"🔄 REVERSAL DETECTED: {opp.coin} {existing_side} → {proposed_side} "
                        f"(score {opp.score}/100, {strategy_name})"
                    )
        
        # Process reversals first (close old, open new)
        slots_available = self.config["max_positions"] - len(existing_positions) + len(reversals)
        
        if slots_available <= 0:
            self.logger.info(f"⏸️  At max positions ({len(existing_positions)}/{self.config['max_positions']}) - skipping proposal generation")
            return []
        
        self.logger.info(f"📈 {len(existing_positions)}/{self.config['max_positions']} positions open - can add {slots_available} more (including {len(reversals)} reversals)")
        
        proposals = []
        
        # Add reversal proposals first
        for rev in reversals:
            opp = rev['opportunity']
            side = rev['new_side']
            strategy_name = rev['strategy']
            strategy_id = self.proposer.strategy_selector.strategy_profiles.get(
                side.lower().replace('long', '').replace('short', ''), 
                'ross_cameron_momentum'
            )
            
            entry, sl, tp = self.proposer.refine_levels(opp, side)
            proposal = self.proposer.build_proposal(opp, side, entry, sl, tp, strategy_name, strategy_id)
            
            if proposal:
                proposal['is_reversal'] = True
                proposal['close_existing'] = rev['existing_side']
                proposals.append(proposal)
                self.logger.info(
                    f"✅ REVERSAL: {proposal['symbol']} ({side}) | "
                    f"Closing {rev['existing_side']}, opening {side} | "
                    f"Entry: ${entry:,.2f} | SL: ${sl:,.2f} | TP: ${tp:,.2f}"
                )
        
        # Then add new position proposals
        for opp in opportunities:
            # Skip coins we're already reversing
            if any(r['coin'] == opp.coin for r in reversals):
                continue
            
            # Stop if we've filled all available slots
            if len(proposals) >= slots_available:
                self.logger.info(f"\\n✅ Reached max proposal limit ({slots_available}) for this run")
                break
            
            # Determine side AND strategy
            side, strategy_name, strategy_id = self.proposer.determine_side_and_strategy(opp)
            
            # Skip if HOLD
            if side == "HOLD":
                self.logger.info(f"⏸️  {opp.coin}: No clear setup (RSI {opp.indicators.rsi:.1f}, ADX {opp.indicators.adx:.1f})")
                continue
            
            entry, sl, tp = self.proposer.refine_levels(opp, side)
            
            # Build proposal with strategy info
            proposal = self.proposer.build_proposal(opp, side, entry, sl, tp, strategy_name, strategy_id)
            
            if proposal:
                proposals.append(proposal)
                self.logger.info(
                    f"✅ {proposal['symbol']} ({side}) | "
                    f"Entry: ${entry:,.2f} | SL: ${sl:,.2f} | TP: ${tp:,.2f} | "
                    f"Size: ${proposal['position_sizing']['size_usd']:.2f}"
                )
        
        self.logger.info(f"\nGenerated {len(proposals)} proposals")
        
        # Save proposals to file
        if proposals:
            filepath = self.proposer.save_proposals(proposals)
            self.logger.info(f"Proposals saved: {filepath}")
        
        return proposals
    
    def _execute_proposals(self, proposals: List[Dict]) -> List:
        """
        Execute trade proposals.
        
        Args:
            proposals: List of proposal dicts
            
        Returns:
            List of ExecutionResult objects
        """
        self.logger.info("\n" + "="*70)
        self.logger.info("STEP 4: ORDER EXECUTION")
        self.logger.info("="*70)
        
        if not proposals:
            self.logger.info("ℹ️  No proposals to execute")
            return []
        
        if not self.executor:
            self.logger.warning("⚠️  Executor not available - skipping execution")
            return []
        
        results = []
        
        for i, proposal in enumerate(proposals):
            symbol = proposal['symbol']
            side = proposal['side']
            
            # Check if this is a reversal (close existing opposite position first)
            if proposal.get('is_reversal'):
                existing_side = proposal.get('close_existing')
                self.logger.info(f"\\n🔄 REVERSAL TRADE: Closing {existing_side}, opening {side}")
                
                if not self.dry_run:
                    # Close existing position first
                    self.logger.info(f"   Closing existing {existing_side} position...")
                    close_result = self.executor.close_position(symbol, reason="Direction reversal")
                    
                    if close_result:
                        self.logger.info(f"   ✅ Closed {existing_side} at ${close_result.get('price', 'N/A')}")
                    else:
                        self.logger.warning(f"   ⚠️  Failed to close {existing_side}, skipping reversal")
                        from modules.executor import ExecutionResult, ExecutionStatus
                        result = ExecutionResult(
                            status=ExecutionStatus.FAILED,
                            symbol=symbol,
                            side=side,
                            error="Failed to close existing position"
                        )
                        results.append(result)
                        continue
                    
                    # Wait for exchange to update
                    time.sleep(1)
            
            self.logger.info(f"\\n📍 Executing proposal {i+1}/{len(proposals)}: {symbol} ({side})")
            
            if self.dry_run:
                self.logger.info("   [DRY RUN] Simulating execution...")
                # Simulate successful execution
                from modules.executor import ExecutionResult
                result = ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    symbol=proposal['symbol'],
                    side=proposal['side'],
                    entry_filled=True,
                    entry_price=proposal['entry_price'],
                    entry_oid=999999,
                    entry_size=proposal['position_sizing']['size_usd'] / proposal['entry_price'],
                    sl_placed=True,
                    sl_price=proposal['sl_price'],
                    sl_oid=999998,
                    tp_placed=True,
                    tp_levels_placed=len(proposal.get('take_profit_levels', [])),
                    tp_orders=[
                        {"level": tp['level'], "success": True}
                        for tp in proposal.get('take_profit_levels', [])
                    ],
                    timestamp=datetime.now(timezone.utc)
                )
                results.append(result)
                continue
            
            # Live execution - SEQUENTIAL with portfolio check after each
            self.logger.info(f"\n📍 Executing proposal {i+1}/{len(proposals)}: {proposal['symbol']}")
            
            result = self.executor.execute_proposal(proposal)
            results.append(result)
            
            # If successful, verify and check portfolio before next
            if result.entry_filled:
                # Verify orders
                if self.config.get("verify_orders", True):
                    sl_ok, tp_ok = self.executor.verify_orders(result, proposal['symbol'])
                    
                    if not sl_ok:
                        self.logger.warning("⚠️  SL verification failed")
                    if not tp_ok:
                        self.logger.warning("⚠️  TP verification failed")
                
                # Check portfolio margin before proceeding to next
                if i < len(proposals) - 1:  # Not the last proposal
                    self.logger.info("\n⏳ Checking portfolio margin before next position...")
                    time.sleep(2)  # Wait for exchange to update
                    
                    account = self.client.get_account_state()
                    margin_ratio = account.margin_used / account.total_equity * 100
                    
                    self.logger.info(f"   Total Equity: ${account.total_equity:.2f}")
                    self.logger.info(f"   Margin Used: ${account.margin_used:.2f} ({margin_ratio:.1f}%)")
                    
                    # Pause if margin usage is getting high
                    if margin_ratio > 15:  # 15% margin usage threshold
                        self.logger.warning(f"⚠️  Margin usage high ({margin_ratio:.1f}%) - stopping execution")
                        self.logger.info("   Remaining proposals will be processed on next pipeline run")
                        break
                    else:
                        self.logger.info(f"   ✅ Margin OK - proceeding to next position")
                        time.sleep(1)  # Brief pause before next
            else:
                self.logger.warning(f"⚠️  Entry failed for {proposal['symbol']} - continuing to next")
        
        # Summary
        successful = sum(1 for r in results if r.status == ExecutionStatus.SUCCESS)
        partial = sum(1 for r in results if r.status == ExecutionStatus.PARTIAL)
        failed = sum(1 for r in results if r.status == ExecutionStatus.FAILED)
        
        self.logger.info(f"\n📊 Execution Summary:")
        self.logger.info(f"   ✅ Successful: {successful}")
        self.logger.info(f"   ⚠️  Partial: {partial}")
        self.logger.info(f"   ❌ Failed: {failed}")
        
        return results
    
    def _monitor_positions(self):
        """
        Monitor existing positions and adjust trailing stops.
        
        This runs on EVERY pipeline execution (every 5 minutes).
        
        Returns:
            List of PositionStatus objects
        """
        self.logger.info("\n" + "="*70)
        self.logger.info("STEP 5: POSITION MONITORING")
        self.logger.info("="*70)
        
        try:
            from modules.monitor import PositionMonitor, MonitorConfig
            
            # Initialize monitor
            config = MonitorConfig(
                dry_run=False,  # Always live for monitoring
                auto_close=True,
                send_notifications=True
            )
            monitor = PositionMonitor(
                client=self.client,
                config=config,
                account_address=self.account_address
            )
            
            # Store monitor for later access
            self.monitor = monitor
            
            # Check all positions
            statuses = monitor.check_all_positions()
            
            if not statuses:
                self.logger.info("ℹ️  No open positions to monitor")
                return []
            
            # Log summary
            total_pnl = sum(s.unrealized_pnl for s in statuses)
            active_trails = sum(1 for s in statuses if s.trail_active)
            
            self.logger.info(f"\n📊 Monitoring Summary:")
            self.logger.info(f"   Positions: {len(statuses)}")
            self.logger.info(f"   Total PnL: ${total_pnl:+.2f}")
            self.logger.info(f"   Active Trails: {active_trails}")
            
            # Log any SL adjustments
            adjustments = [s for s in statuses if s.action.name == "ADJUST_SL"]
            if adjustments:
                self.logger.info(f"\n🔄 SL Adjustments:")
                for adj in adjustments:
                    self.logger.info(
                        f"   • {adj.coin}: SL → ${adj.new_sl:.2f} ({adj.reason})"
                    )
            
            return statuses
            
        except ImportError as e:
            self.logger.warning(f"⚠️  Monitor module not available: {e}")
        except Exception as e:
            self.logger.error(f"❌ Error monitoring positions: {e}")
        
        return []
    
    def _generate_summary_table(self, summary: Dict, opportunities: List, proposals: List, results: List, statuses: List):
        """
        Generate a consolidated summary table for Telegram notifications.
        Matches the user's spreadsheet format exactly.
        """
        self.logger.info("\n" + "="*70)
        self.logger.info("TRADING SUMMARY")
        self.logger.info("="*70)
        
        # Account status
        try:
            account = self.client.get_account_state()
            equity = account.total_equity
            margin_used = account.margin_used
            positions_count = len(self.client.get_perp_positions())
            total_pnl = account.total_pnl if hasattr(account, 'total_pnl') else 0
        except:
            equity = 0
            margin_used = 0
            total_pnl = 0
            positions_count = 0
        
        self.logger.info(f"Equity: ${equity:,.2f} | Margin: ${margin_used:,.2f} | PnL: ${total_pnl:+,.2f} | Positions: {positions_count}")
        self.logger.info("")
        
        # Execution status
        successful = sum(1 for r in results if r.status.name == "SUCCESS") if results else 0
        
        if results and successful > 0:
            for r in results:
                if r.status.name == "SUCCESS":
                    strategy = getattr(r, 'strategy', 'Unknown')
                    coin = r.symbol.replace("-PERP", "") if hasattr(r, 'symbol') else getattr(r, 'coin', 'UNKNOWN')
                    pnl = getattr(r, 'unrealized_pnl', 0)
                    sl = getattr(r, 'sl_price', 0)
                    self.logger.info(f"* {coin} | {r.side.upper()} | {strategy} | ${pnl:+.2f} | {sl:.2f}")
        else:
            self.logger.info("No new positions opened")
        
        self.logger.info("")
        
        # Positions table header
        self.logger.info("Coin | Direction | Strategy | PnL$ | Trail")
        self.logger.info("-" * 50)
        
        # Position details
        if statuses:
            for s in statuses:
                strategy = self._get_strategy_for_coin(s.coin)
                
                # Check if trailing stop has activated (profit >= 2%)
                # Calculate profit percentage based on entry price
                pnl_pct = abs(s.unrealized_pnl) / abs(s.entry_price * s.size) * 100 if s.size > 0 else 0
                trail_status = "✓" if pnl_pct >= 2.0 else ""
                
                self.logger.info(f"{s.coin} | {s.side.upper()} | {strategy} | ${s.unrealized_pnl:+.2f} | {trail_status}")
        else:
            self.logger.info("No open positions")
        
        self.logger.info("")
        
        # Recommendation
        self.logger.info("RECOMMENDATION")
        
        # Get best opportunity from scan
        best_opp = opportunities[0] if opportunities else None
        
        # Get losing positions
        losing_positions = [s for s in statuses if s.unrealized_pnl < -0.50] if statuses else []
        
        if positions_count == 0:
            if best_opp and best_opp.score >= 65:
                self.logger.info(f"Open {best_opp.coin} {best_opp.side} - score {best_opp.score}/100, {best_opp.strategy} setup.")
                self.logger.info(f"Entry ${best_opp.entry_price:.2f}, SL ${best_opp.stop_loss_price:.2f}, risk 2% of equity.")
            elif best_opp:
                self.logger.info(f"Best: {best_opp.coin} {best_opp.side} (score {best_opp.score}), but below 65 threshold - wait.")
                self.logger.info("Market conditions not ideal - continue monitoring for higher-conviction setups.")
            else:
                self.logger.info("No qualifying opportunities - market too quiet or ranging.")
                self.logger.info("Wait for score >55 with clear RSI divergence before entering.")
        
        elif positions_count >= 5:
            if losing_positions:
                worst = min(losing_positions, key=lambda s: s.unrealized_pnl)
                self.logger.info(f"Review {worst.coin} {worst.side} - down ${worst.unrealized_pnl:.2f}, thesis may be broken.")
                self.logger.info("Consider manual close if setup invalidated - frees capital for better opportunities.")
            else:
                self.logger.info("Portfolio at max capacity - no new trades until positions close.")
                self.logger.info("Watch for trailing stop activations to lock profits and free slots.")
        
        else:
            if best_opp and best_opp.score >= 70:
                self.logger.info(f"Add {best_opp.coin} {best_opp.side} - high conviction ({best_opp.score}/100, {best_opp.strategy}).")
                self.logger.info(f"Entry ${best_opp.entry_price:.2f}, SL ${best_opp.stop_loss_price:.2f}, {5-positions_count} slots remaining.")
            elif positions_count > 0:
                self.logger.info(f"{positions_count}/5 positions open - monitor existing trades.")
                self.logger.info("Watch for +2% moves to activate trailing stops.")
        
        # Alternative coins (ALWAYS show top 2 opportunities we DON'T have positions in)
        self.logger.info("")
        self.logger.info("Alternative coins:")
        self.logger.info("coin | reason | strategy")
        self.logger.info("-" * 50)
        
        # Get coins we already have positions in
        existing_coins = set(s.coin for s in statuses) if statuses else set()
        
        # Filter opportunities to exclude existing positions
        alternative_opps = [opp for opp in opportunities if opp.coin not in existing_coins]
        
        if alternative_opps:
            for i, opp in enumerate(alternative_opps[:2], 1):
                reason = f"score {opp.score}, RSI {opp.indicators.rsi:.1f}"
                self.logger.info(f"{opp.coin} | {reason} | {opp.strategy}")
        else:
            self.logger.info("No qualifying opportunities - all top coins already in portfolio")
        
        self.logger.info("="*70)
    
    def _get_strategy_for_coin(self, coin: str) -> str:
        """
        Get the strategy name for a coin from the most recent proposal.
        """
        try:
            # Look for the most recent proposal file for this coin
            import glob
            import json
            
            # Check the correct proposals directory
            proposal_files = sorted(glob.glob("/mnt/data/hermes/workspace/crypto-trading-bot/data/proposals/proposals_*.json"), reverse=True)
            
            for filepath in proposal_files[:5]:  # Check last 5 proposal files
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    proposals = data.get('proposals', [])
                    for p in proposals:
                        if p.get('coin') == coin:
                            return p.get('strategy', 'Unknown')
        except Exception as e:
            pass
        
        return "Unknown"
    
    def _generate_reports(self, results: List):
        """
        Generate execution reports.
        
        Args:
            results: List of ExecutionResult objects
        """
        self.logger.info("\n" + "="*70)
        self.logger.info("STEP 5: REPORT GENERATION")
        self.logger.info("="*70)
        
        if not results:
            self.logger.info("ℹ️  No results to report")
            return
        
        if not self.executor:
            self.logger.info("ℹ️  Executor not available - skipping reports")
            return
        
        for result in results:
            filepath = self.executor.generate_report(result)
            if filepath:
                self.logger.info(f"📄 Report: {filepath}")
    
    def run(self) -> Dict:
        """
        Run the full pipeline.
        
        Returns:
            Pipeline summary dict
        """
        start_time = datetime.now(timezone.utc)
        self.logger.info(f"\n🚀 Pipeline started: {start_time.isoformat()}")
        
        try:
            # Step 1: Kill switch check
            if not self._check_kill_switch():
                return {
                    "status": "paused",
                    "reason": "kill_switch_active",
                    "timestamp": start_time.isoformat()
                }
            
            # Step 2: Market scan
            opportunities = self._scan_markets()
            
            # Step 3: Generate proposals
            proposals = self._generate_proposals(opportunities)
            
            # Step 4: Execute proposals
            results = self._execute_proposals(proposals)
            
            # Step 5: Monitor positions (trailing stops)
            statuses = self._monitor_positions()
            
            # Step 6: Generate reports
            self._generate_reports(results)
            
            # Summary
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            summary = {
                "status": "completed",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "opportunities_found": len(opportunities),
                "proposals_generated": len(proposals),
                "executions": len(results),
                "successful": sum(1 for r in results if r.status == ExecutionStatus.SUCCESS),
                "partial": sum(1 for r in results if r.status == ExecutionStatus.PARTIAL),
                "failed": sum(1 for r in results if r.status == ExecutionStatus.FAILED),
            }
            
            self.logger.info("\n" + "="*70)
            self.logger.info("PIPELINE COMPLETED")
            self.logger.info("="*70)
            self.logger.info(f"Duration: {duration:.1f}s")
            self.logger.info(f"Opportunities: {len(opportunities)}")
            self.logger.info(f"Proposals: {len(proposals)}")
            self.logger.info(f"Executions: {summary['successful']} success, {summary['partial']} partial, {summary['failed']} failed")
            
            # Generate consolidated summary table
            self._generate_summary_table(summary, opportunities, proposals, results, statuses)
            
            return summary
            
        except Exception as e:
            self.logger.exception(f"❌ Pipeline failed with exception: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": start_time.isoformat()
            }


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Trading Pipeline Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without placing orders")
    parser.add_argument("--max-positions", type=int, default=5, help="Maximum concurrent positions")
    parser.add_argument("--min-score", type=int, default=55, help="Minimum opportunity score")
    parser.add_argument("--risk-pct", type=float, default=2.0, help="Risk per trade (%)")
    parser.add_argument("--config", type=str, help="Path to config file (JSON)")
    parser.add_argument("--account", type=str, help="Account address (override env)")
    parser.add_argument("--private-key", type=str, help="Private key (override env)")
    
    args = parser.parse_args()
    
    # Load config
    config = DEFAULT_CONFIG.copy()
    
    if args.config:
        with open(args.config, 'r') as f:
            file_config = json.load(f)
            config.update(file_config)
    
    # Override with CLI args
    config["dry_run"] = args.dry_run or config["dry_run"]
    config["max_positions"] = args.max_positions or config["max_positions"]
    config["min_score"] = args.min_score or config["min_score"]
    config["risk_per_trade_pct"] = args.risk_pct or config["risk_per_trade_pct"]
    
    # Get credentials
    account = args.account or os.environ.get("HYPERLIQUID_ACCOUNT_ADDRESS") or os.environ.get("HYPERLIQUID_WALLET_ADDRESS")
    private_key = args.private_key or os.environ.get("HYPERLIQUID_WALLET_PRIVATE_KEY")
    
    if not account:
        print("❌ Error: Account address required (use --account or HYPERLIQUID_ACCOUNT_ADDRESS)")
        sys.exit(1)
    
    if not private_key and not config["dry_run"]:
        print("⚠️  Warning: No private key provided - running in simulation mode")
        config["dry_run"] = True
    
    # Run pipeline
    pipeline = TradingPipeline(config, account, private_key)
    summary = pipeline.run()
    
    # Output summary
    print("\n" + "="*70)
    print("PIPELINE SUMMARY")
    print("="*70)
    print(json.dumps(summary, indent=2))
    
    # Exit code based on status
    if summary["status"] == "completed":
        sys.exit(0)
    elif summary["status"] == "paused":
        sys.exit(2)  # Kill switch
    else:
        sys.exit(1)  # Failed


if __name__ == "__main__":
    main()
