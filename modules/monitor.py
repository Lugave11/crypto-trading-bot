#!/usr/bin/env python3
"""
Position Monitor Module

Monitors open positions and manages:
- Trailing stop-losses (5% trail, activates +2%)
- Take-profit level tracking
- P&L monitoring
- Position close notifications

Usage:
    from modules.monitor import PositionMonitor, MonitorConfig
    
    config = MonitorConfig()
    monitor = PositionMonitor(client, config)
    status = monitor.check_all_positions()
"""

import sys
import os
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

# Add modules to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.api.hyperliquid import HyperliquidClient, Position

# Import Exchange SDK for order placement
try:
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    from eth_account import Account
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    Exchange = None
    Info = None
    Account = None


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class MonitorConfig:
    """Position monitor configuration."""
    # Base trailing stop (fallback)
    base_trail_distance_pct: float = 5.0
    base_activation_pct: float = 2.0
    
    # Volatility-based adaptive trailing
    use_adaptive_trail: bool = True
    velocity_lookback_min: int = 5  # Lookback period for velocity calculation
    
    # Volatility tiers: min_velocity -> (trail_distance, activation_threshold)
    # Higher velocity = tighter trail, higher activation threshold
    volatility_tiers: List[Dict] = None
    
    # Execution
    dry_run: bool = False
    auto_close: bool = True
    
    # Notifications
    send_notifications: bool = True
    
    def __post_init__(self):
        """Initialize default volatility tiers if not provided."""
        if self.volatility_tiers is None:
            self.volatility_tiers = [
                {"min_velocity": 5.0, "trail": 1.0, "activation": 3.0},   # Explosive (>5% in 5min)
                {"min_velocity": 3.0, "trail": 2.0, "activation": 2.5},   # Strong (3-5%)
                {"min_velocity": 1.0, "trail": 3.5, "activation": 2.0},   # Moderate (1-3%)
                {"min_velocity": 0.0, "trail": 5.0, "activation": 2.0},   # Slow (<1%)
            ]


class PositionAction(Enum):
    """Action to take on a position."""
    HOLD = "hold"
    ADJUST_SL = "adjust_sl"
    CLOSE_TP = "close_tp"
    CLOSE_SL = "close_sl"


@dataclass
class PositionStatus:
    """Status of a monitored position."""
    coin: str
    side: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    
    # Peak tracking
    peak_price: float
    peak_pnl_pct: float
    
    # Trailing stop
    trail_active: bool
    current_sl: Optional[float]
    new_sl: Optional[float]
    
    # Action
    action: PositionAction
    reason: str
    
    timestamp: datetime


# ============================================================================
# POSITION MONITOR
# ============================================================================

class PositionMonitor:
    """
    Monitors and manages open positions with trailing stops.
    
    Features:
    - Trailing stop-loss (5% trail, activates +2%)
    - Peak price tracking per position
    - Auto-close at TP/SL (optional)
    - P&L monitoring
    """
    
    def __init__(
        self,
        client: HyperliquidClient,
        config: MonitorConfig = None,
        account_address: str = None
    ):
        """
        Initialize the position monitor.
        
        Args:
            client: Hyperliquid API client (testnet for execution)
            config: Monitor configuration
            account_address: Wallet address for queries
        """
        self.client = client
        self.config = config or MonitorConfig()
        self.account_address = account_address
        self.dry_run = self.config.dry_run
        
        # Initialize Exchange SDK for order placement
        self.exchange = None
        self.sdk_ready = False
        
        if SDK_AVAILABLE and not self.dry_run:
            try:
                # Load wallet from private key
                private_key = os.environ.get("HYPERLIQUID_PRIVATE_KEY")
                if private_key:
                    wallet = Account.from_key(private_key)
                    api_url = "https://api.hyperliquid-testnet.xyz" if client.testnet else "https://api.hyperliquid.xyz"
                    self.exchange = Exchange(wallet, api_url, account_address=account_address)
                    self.sdk_ready = True
                    print(f"✅ Exchange SDK initialized - {'TESTNET' if client.testnet else 'MAINNET'}")
                else:
                    print("⚠️  No private key found - trailing stops will be DRY RUN only")
            except Exception as e:
                print(f"⚠️  Exchange SDK init failed: {e} - trailing stops will be DRY RUN only")
        else:
            if not SDK_AVAILABLE:
                print("⚠️  Hyperliquid SDK not available - trailing stops will be DRY RUN only")
            else:
                print("ℹ️  DRY RUN mode - no actual orders will be placed")
        
        # State tracking
        self.peak_prices: Dict[str, float] = {}  # coin -> peak price
        self.peak_pnls: Dict[str, float] = {}    # coin -> peak PnL %
        self.price_history: Dict[str, Dict] = {}  # coin -> {timestamp, price, 5min_ago_price}
        
        # Track placed stop-loss orders per coin
        # CRITICAL: Load from existing open orders on init (not empty!)
        self.placed_sl_orders: Dict[str, Optional[int]] = self._load_existing_sl_orders()
        
        print("="*70)
        print("POSITION MONITOR INITIALIZED")
        print("="*70)
        print(f"Network: {'TESTNET' if client.testnet else 'MAINNET'}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"SDK Ready: {'YES' if self.sdk_ready else 'NO'}")
        if self.config.use_adaptive_trail:
            print(f"Adaptive Trailing: ENABLED (volatility-based)")
            print(f"Trail: ADAPTIVE (1-5% based on volatility)")
            print(f"Lookback: {self.config.velocity_lookback_min} minutes")
        else:
            print(f"Trail: {self.config.base_trail_distance_pct}% (activates +{self.config.base_activation_pct}%)")
        print(f"Tracked SL orders: {len(self.placed_sl_orders)} coins")
        for coin, oid in self.placed_sl_orders.items():
            print(f"  • {coin}: OID {oid}")
        print()
    
    def _load_existing_sl_orders(self) -> Dict[str, int]:
        """
        Load existing trailing stop orders from open orders.
        
        This is CRITICAL because the monitor is re-created on each pipeline run,
        so we need to reload the order IDs from the exchange.
        
        Returns:
            Dict mapping coin -> most recent trailing stop OID
        """
        sl_orders = {}
        try:
            # Fetch all open orders
            open_orders = self.client.get_open_orders()
            
            # Group by coin
            from collections import defaultdict
            orders_by_coin = defaultdict(list)
            for order in open_orders:
                orders_by_coin[order["coin"]].append(order)
            
            # For each coin, find the trailing stop (largest OID = most recent)
            for coin, orders in orders_by_coin.items():
                # Trailing stops are reduce-only trigger orders
                # For LONG positions: SL is SELL (side="A")
                # For SHORT positions: SL is BUY (side="B")
                # They have the same size as the position
                trailing_stops = [o for o in orders if o.get("reduceOnly", False)]
                
                if trailing_stops:
                    # Get the most recent one (highest OID)
                    most_recent = max(trailing_stops, key=lambda o: o["oid"])
                    sl_orders[coin] = most_recent["oid"]
                    
            if sl_orders:
                print(f"✅ Loaded {len(sl_orders)} existing trailing stops from exchange")
            else:
                print("ℹ️  No existing trailing stops found")
                
        except Exception as e:
            print(f"⚠️  Could not load existing SL orders: {e}")
        
        return sl_orders
    
    def calculate_unrealized_pnl(
        self,
        position: Position,
        current_price: float
    ) -> Tuple[float, float]:
        """
        Calculate unrealized P&L for a position.
        
        Returns:
            Tuple of (pnl_usd, pnl_pct)
        """
        entry_price = position.entry_price
        size = abs(position.size)
        side = position.side
        
        if side == "long":
            pnl_usd = (current_price - entry_price) * size
            pnl_pct = (current_price - entry_price) / entry_price * 100
        else:  # short
            pnl_usd = (entry_price - current_price) * size
            pnl_pct = (entry_price - current_price) / entry_price * 100
        
        return pnl_usd, pnl_pct
    
    def update_price_history(self, coin: str, current_price: float, current_time: datetime):
        """
        Update price history for a coin to track velocity.
        
        Args:
            coin: Coin symbol
            current_price: Current market price
            current_time: Current timestamp
        """
        if coin not in self.price_history:
            self.price_history[coin] = {
                "first_seen": current_time,
                "last_price": current_price,
                "last_update": current_time,
                "price_5min_ago": current_price,  # Initialize with current
                "high_since_entry": current_price,
                "low_since_entry": current_price,
            }
            return
        
        history = self.price_history[coin]
        time_diff = (current_time - history["last_update"]).total_seconds() / 60.0  # minutes
        
        # Update high/low
        if current_price > history["high_since_entry"]:
            history["high_since_entry"] = current_price
        if current_price < history["low_since_entry"]:
            history["low_since_entry"] = current_price
        
        # If enough time passed, update 5min_ago price
        if time_diff >= self.config.velocity_lookback_min:
            history["price_5min_ago"] = history["last_price"]
            history["last_update"] = current_time
        
        history["last_price"] = current_price
    
    def calculate_price_velocity(self, coin: str) -> float:
        """
        Calculate price velocity (% change over lookback period).
        
        Returns:
            Absolute % change over the lookback period
        """
        if coin not in self.price_history:
            return 0.0
        
        history = self.price_history[coin]
        current_price = history["last_price"]
        price_5min_ago = history["price_5min_ago"]
        
        if price_5min_ago == 0:
            return 0.0
        
        # Calculate absolute % change
        velocity = abs(current_price - price_5min_ago) / price_5min_ago * 100
        return velocity
    
    def get_dynamic_trail_config(self, coin: str) -> Tuple[float, float]:
        """
        Get dynamic trail distance and activation threshold based on volatility.
        
        Returns:
            Tuple of (trail_distance_pct, activation_pct)
        """
        if not self.config.use_adaptive_trail:
            return self.config.base_trail_distance_pct, self.config.base_activation_pct
        
        # Calculate velocity
        velocity = self.calculate_price_velocity(coin)
        
        # Find matching tier (tiers are ordered high to low)
        for tier in self.config.volatility_tiers:
            if velocity >= tier["min_velocity"]:
                return tier["trail"], tier["activation"]
        
        # Fallback to base config
        return self.config.base_trail_distance_pct, self.config.base_activation_pct
    
    def check_trailing_stop(
        self,
        position: Position,
        current_price: float,
        peak_price: float,
        peak_pnl_pct: float
    ) -> Tuple[bool, Optional[float], str]:
        """
        Check if trailing stop should be adjusted or placed initially.
        
        Returns:
            Tuple of (should_adjust, new_sl_price, reason)
        """
        coin = position.coin
        side = position.side
        entry_price = position.entry_price
        
        # Get dynamic trail config based on volatility
        trail_distance, activation_pct = self.get_dynamic_trail_config(coin)
        
        # Calculate initial SL based on entry price (for positions without SL)
        # For long: SL below entry. For short: SL above entry
        if side == "long":
            initial_sl = entry_price * (1 - trail_distance / 100)
            sl_type = "below entry"
        else:  # short
            initial_sl = entry_price * (1 + trail_distance / 100)
            sl_type = "above entry"
        
        # Check if we already have a stop-loss from tracking
        # Since Position object doesn't include stop_loss_price, check our internal tracking
        has_existing_sl = coin in self.placed_sl_orders and self.placed_sl_orders[coin] is not None
        
        # If no SL exists, place initial stop immediately (don't wait for activation)
        if not has_existing_sl:
            velocity = self.calculate_price_velocity(coin)
            return True, initial_sl, f"Initial SL {sl_type} ${entry_price:.2f} @ {trail_distance}% (vel {velocity:.1f}%)"
        
        # Check if trail should activate for adjustment
        if peak_pnl_pct < activation_pct:
            velocity = self.calculate_price_velocity(coin)
            return False, None, f"Trail not activated (peak PnL {peak_pnl_pct:.1f}% < {activation_pct}%, velocity {velocity:.1f}%)"
        
        # Calculate new SL based on peak and dynamic trail distance
        if side == "long":
            new_sl = peak_price * (1 - trail_distance / 100)
            sl_type = "below peak"
        else:  # short
            new_sl = peak_price * (1 + trail_distance / 100)
            sl_type = "above peak"
        
        # For long: raise SL if new SL is higher
        # For short: lower SL if new SL is lower
        # Get the current SL price from our tracking or estimate
        # Since we can't query existing SL prices, we'll just calculate based on peak
        current_sl = peak_price * (1 - trail_distance / 100) if side == "long" else peak_price * (1 + trail_distance / 100)
        
        if side == "long":
            if new_sl > current_sl:
                velocity = self.calculate_price_velocity(coin)
                return True, new_sl, f"Raising SL (vel {velocity:.1f}%) to ${new_sl:.2f} {sl_type}"
        else:
            if new_sl < current_sl:
                velocity = self.calculate_price_velocity(coin)
                return True, new_sl, f"Lowering SL (vel {velocity:.1f}%) to ${new_sl:.2f} {sl_type}"
        
        return False, current_sl, f"SL unchanged (vel {self.calculate_price_velocity(coin):.1f}%)"
    
    def _get_sz_decimals(self, coin: str) -> int:
        """Get szDecimals for a coin from exchange metadata."""
        try:
            # Query metadata for universe info
            url = "https://api.hyperliquid-testnet.xyz/info" if self.client.testnet else "https://api.hyperliquid.xyz/info"
            meta = requests.post(url, json={"type": "meta"}, timeout=10).json()
            for asset in meta.get("universe", []):
                if asset.get("name") == coin:
                    return asset.get("szDecimals", 2)
            return 2  # Default fallback
        except Exception:
            return 2
    
    def _round_price(self, price: float, sz_decimals: int) -> float:
        """
        Round price to valid significant figures for Hyperliquid.
        Max 5 significant figures, and max (6 - sz_decimals) decimal places for perps.
        """
        max_decimals = 6 - sz_decimals
        # First round to max decimals
        rounded = round(price, max_decimals)
        # Then ensure max 5 significant figures
        if rounded != 0:
            sig_figs = len(f"{rounded:.10f}".rstrip('0').replace('.', '').lstrip('0'))
            if sig_figs > 5:
                # Reduce precision
                rounded = round(rounded, 5 - len(str(int(rounded))))
        return rounded
    
    def _place_trailing_stop(
        self,
        coin: str,
        side: str,
        size: float,
        trigger_price: float
    ) -> Tuple[bool, Optional[int], str]:
        """
        Place or update a trailing stop-loss order.
        
        Args:
            coin: Coin symbol (e.g., "BTC")
            side: "long" or "short"
            size: Position size in coin
            trigger_price: Price that triggers the stop
            
        Returns:
            Tuple of (success, order_id, message)
        """
        if not self.sdk_ready:
            return False, None, "SDK not ready - DRY RUN only"
        
        try:
            # Get szDecimals for proper rounding
            sz_decimals = self._get_sz_decimals(coin)
            
            # Round size and price using Hyperliquid rules
            size_rounded = round(size, sz_decimals)
            trigger_rounded = self._round_price(trigger_price, sz_decimals)
            
            # For stop-loss, side is opposite of position
            # If LONG, SL is SELL. If SHORT, SL is BUY
            is_buy = (side.lower() == "short")
            
            print(f"   🛡️  Placing trailing SL: {side.upper()} {size_rounded} {coin} @ ${trigger_rounded} (szDec={sz_decimals})")
            
            # Place trigger order (stop market)
            result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=size_rounded,
                limit_px=trigger_rounded,  # Required by SDK even for market orders
                order_type={
                    "trigger": {
                        "triggerPx": trigger_rounded,
                        "isMarket": True,
                        "tpsl": "sl"  # Stop loss
                    }
                },
                reduce_only=True
            )
            
            print(f"   📝 SL order response: {result}")
            
            if result.get('status') == 'ok':
                data = result.get('response', {}).get('data', {})
                statuses = data.get('statuses', []) if isinstance(data, dict) else []
                
                # Check if order was accepted
                if statuses and len(statuses) > 0:
                    status = statuses[0]
                    if 'resting' in status:
                        oid = status['resting'].get('oid')
                        print(f"   ✅ Trailing SL placed (OID: {oid})")
                        return True, oid, f"SL placed at ${trigger_rounded}"
                    elif 'error' in status:
                        error = status['error']
                        print(f"   ❌ SL rejected: {error}")
                        return False, None, f"SL rejected: {error}"
                
                print(f"   ⚠️  SL response unclear: {result}")
                return True, None, "SL placed (OID unknown)"
            else:
                error = result.get('response', {}).get('data', {}).get('errorMsg', 'Unknown error')
                return False, None, f"SL rejected: {error}"
                
        except Exception as e:
            return False, None, f"SL failed: {str(e)}"
    
    def _cancel_order(self, coin: str, order_id: int) -> bool:
        """Cancel an existing order."""
        if not self.sdk_ready:
            return False
        
        try:
            result = self.exchange.cancel(coin, order_id)
            if result.get('status') == 'ok':
                print(f"   ✅ Cancelled order {order_id} for {coin}")
                return True
            else:
                print(f"   ⚠️  Cancel failed for {coin} order {order_id}")
                return False
        except Exception as e:
            print(f"   ❌ Cancel failed: {e}")
            return False
    
    def _cancel_all_reduce_only_orders(self, coin: str) -> int:
        """
        Cancel ALL reduce-only orders for a coin.
        
        This is used to clean up duplicate trailing stops and TP orders.
        
        Args:
            coin: Coin symbol
            
        Returns:
            Number of orders cancelled
        """
        if not self.sdk_ready:
            return 0
        
        cancelled_count = 0
        try:
            # Fetch all open orders
            open_orders = self.client.get_open_orders()
            
            # Find all reduce-only orders for this coin
            coin_orders = [o for o in open_orders if o["coin"] == coin and o.get("reduceOnly", False)]
            
            # Cancel each one
            for order in coin_orders:
                oid = order["oid"]
                if self._cancel_order(coin, oid):
                    cancelled_count += 1
            
            if cancelled_count > 0:
                print(f"   ✅ Cancelled {cancelled_count} duplicate order(s) for {coin}")
            else:
                print(f"   ℹ️  No duplicate orders for {coin}")
                
        except Exception as e:
            print(f"   ❌ Failed to cancel orders: {e}")
        
        return cancelled_count
    
    def monitor_position(
        self,
        position: Position,
        current_price: float
    ) -> PositionStatus:
        """
        Monitor a single position and determine action.
        
        Returns:
            PositionStatus object
        """
        coin = position.coin
        side = position.side
        size = abs(position.size)
        entry_price = position.entry_price
        current_time = datetime.now(timezone.utc)
        
        # Update price history for velocity calculation
        self.update_price_history(coin, current_price, current_time)
        
        # Calculate P&L
        pnl_usd, pnl_pct = self.calculate_unrealized_pnl(position, current_price)
        
        # Update peak tracking
        if coin not in self.peak_prices:
            self.peak_prices[coin] = current_price
            self.peak_pnls[coin] = pnl_pct
        
        # Update peak if better
        if side == "long":
            if current_price > self.peak_prices[coin]:
                self.peak_prices[coin] = current_price
                self.peak_pnls[coin] = pnl_pct
        else:  # short
            if current_price < self.peak_prices[coin]:
                self.peak_prices[coin] = current_price
                self.peak_pnls[coin] = pnl_pct
        
        peak_price = self.peak_prices[coin]
        peak_pnl = self.peak_pnls[coin]
        
        # Check trailing stop
        trail_adjust, new_sl, trail_reason = self.check_trailing_stop(
            position, current_price, peak_price, peak_pnl
        )
        
        # Determine action
        if trail_adjust and new_sl is not None:
            action = PositionAction.ADJUST_SL
            reason = trail_reason
        else:
            action = PositionAction.HOLD
            reason = f"Holding | Peak: ${peak_price:.2f} ({peak_pnl:+.1f}%)"
        
        # Get current SL (not available in Position object yet)
        current_sl = None
        
        # Check if trail is active (use dynamic activation threshold)
        _, activation_pct = self.get_dynamic_trail_config(coin)
        trail_active = peak_pnl >= activation_pct
        
        return PositionStatus(
            coin=coin,
            side=side,
            size=size,
            entry_price=entry_price,
            current_price=current_price,
            unrealized_pnl=pnl_usd,
            unrealized_pnl_pct=pnl_pct,
            peak_price=peak_price,
            peak_pnl_pct=peak_pnl,
            trail_active=trail_active,
            current_sl=current_sl,
            new_sl=new_sl if trail_adjust else current_sl,
            action=action,
            reason=reason,
            timestamp=datetime.now(timezone.utc)
        )
    
    def check_all_positions(self) -> List[PositionStatus]:
        """
        Check all open positions.
        
        Returns:
            List of PositionStatus objects
        """
        # Get open positions
        positions = self.client.get_perp_positions()
        
        if not positions:
            print("ℹ️  No open positions")
            return []
        
        print(f"📊 Checking {len(positions)} position(s)...")
        print()
        
        statuses = []
        
        for position in positions:
            coin = position.coin
            
            # Get current price
            try:
                all_mids = self.client.get_all_mids()
                current_price = float(all_mids.get(coin, 0))
                
                if current_price == 0:
                    print(f"⚠️  Could not get price for {coin}, skipping")
                    continue
                
                # Monitor the position
                status = self.monitor_position(position, current_price)
                statuses.append(status)
                
                # Print status
                self._print_status(status)
                
                # Execute action if needed
                if status.action == PositionAction.ADJUST_SL and status.new_sl:
                    if self.config.auto_close:
                        if not self.dry_run and self.sdk_ready:
                            # CRITICAL: Cancel ALL reduce-only orders for this coin (cleanup duplicates)
                            print(f"   🔄 Cancelling ALL existing SL/TP orders for {coin}...")
                            self._cancel_all_reduce_only_orders(coin)
                            
                            # Place new trailing stop
                            print(f"   🔄 Placing trailing SL at ${status.new_sl:.2f}...")
                            success, oid, msg = self._place_trailing_stop(
                                coin=coin,
                                side=status.side,
                                size=status.size,
                                trigger_price=status.new_sl
                            )
                            
                            if success:
                                self.placed_sl_orders[coin] = oid
                                print(f"   ✅ {msg}")
                            else:
                                print(f"   ❌ {msg}")
                        else:
                            print(f"   📝 [DRY RUN] Would update SL to ${status.new_sl:.2f}")
                    else:
                        print(f"   📝 [AUTO-CLOSE DISABLED] Would update SL to ${status.new_sl:.2f}")
                
            except Exception as e:
                print(f"❌ Error monitoring {position.coin}: {e}")
                continue
        
        print()
        return statuses
    
    def _print_status(self, status: PositionStatus):
        """Print position status."""
        side_icon = "🟢" if status.side == "long" else "🔴"
        pnl_icon = "📈" if status.unrealized_pnl >= 0 else "📉"
        
        # Calculate velocity for display
        velocity = self.calculate_price_velocity(status.coin) if status.coin in self.price_history else 0.0
        
        # Determine volatility tier
        tier_label = "SLOW"
        if velocity >= 5.0:
            tier_label = "EXPLOSIVE 🔥"
        elif velocity >= 3.0:
            tier_label = "STRONG ⚡"
        elif velocity >= 1.0:
            tier_label = "MODERATE 📊"
        
        print(f"{side_icon} {status.coin} {status.side.upper()}")
        print(f"   Size: {status.size:.4f} @ ${status.entry_price:.2f}")
        print(f"   Current: ${status.current_price:.2f}")
        print(f"   {pnl_icon} PnL: ${status.unrealized_pnl:+.2f} ({status.unrealized_pnl_pct:+.2f}%)")
        print(f"   Peak: ${status.peak_price:.2f} ({status.peak_pnl_pct:+.1f}%)")
        print(f"   📈 Velocity: {velocity:.1f}% ({tier_label})")
        
        if status.trail_active:
            trail_dist, act_pct = self.get_dynamic_trail_config(status.coin)
            print(f"   🛡️  Trail: ACTIVE @ {trail_dist:.1f}% (activates at +{act_pct:.1f}%)")
            if status.new_sl and status.action == PositionAction.ADJUST_SL:
                print(f"   🔄 Action: {status.reason}")
        else:
            trail_dist, act_pct = self.get_dynamic_trail_config(status.coin)
            print(f"   🛡️  Trail: INACTIVE (needs +{act_pct:.1f}%, current trail: {trail_dist:.1f}%)")
        
        print(f"   ⚡ Action: {status.action.value.upper()}")
        print()
    
    def reset_peaks(self, coin: str = None):
        """
        Reset peak tracking for a coin or all coins.
        
        Args:
            coin: Coin to reset (None for all)
        """
        if coin:
            if coin in self.peak_prices:
                del self.peak_prices[coin]
            if coin in self.peak_pnls:
                del self.peak_pnls[coin]
            print(f"✅ Reset peak tracking for {coin}")
        else:
            self.peak_prices.clear()
            self.peak_pnls.clear()
            print("✅ Reset all peak tracking")


# ============================================================================
# MAIN (for standalone testing)
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Position Monitor")
    parser.add_argument("--dry-run", action="store_true", help="Don't execute trades")
    parser.add_argument("--account", type=str, help="Account address")
    parser.add_argument("--testnet", action="store_true", default=True, help="Use testnet")
    args = parser.parse_args()
    
    # Initialize client
    client = HyperliquidClient(testnet=args.testnet)
    
    # Initialize monitor
    config = MonitorConfig(
        dry_run=args.dry_run,
        auto_close=not args.dry_run
    )
    monitor = PositionMonitor(client, config, args.account)
    
    # Check positions
    statuses = monitor.check_all_positions()
    
    # Summary
    if statuses:
        total_pnl = sum(s.unrealized_pnl for s in statuses)
        print("="*70)
        print(f"Total Unrealized PnL: ${total_pnl:+.2f}")
        print(f"Positions: {len(statuses)}")
        active_trails = sum(1 for s in statuses if s.trail_active)
        print(f"Active Trails: {active_trails}")
