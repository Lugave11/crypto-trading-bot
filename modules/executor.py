#!/usr/bin/env python3
"""
Order Executor Module - LIVE TRADING

Executes trade proposals by placing REAL orders on Hyperliquid.

Features:
- Market entry orders (REAL)
- Stop-loss trigger orders (REAL)
- Multi-level take-profit orders (REAL)
- Order verification
- Telegram notifications
- Execution reporting
"""

import sys
import os
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.api.hyperliquid import HyperliquidClient

# Import Hyperliquid SDK for real order placement
try:
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    from hyperliquid.utils import constants
    import eth_account
    SDK_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Hyperliquid SDK not available: {e}")
    SDK_AVAILABLE = False


def get_sz_decimals(coin: str, testnet: bool = True) -> int:
    """
    Get the szDecimals for a coin from Hyperliquid API.
    
    Args:
        coin: Coin symbol (e.g., 'AAVE', 'BTC')
        testnet: Use testnet API if True
        
    Returns:
        szDecimals value (default 2 if not found)
    """
    url = "https://api.hyperliquid-testnet.xyz/info" if testnet else "https://api.hyperliquid.xyz/info"
    try:
        meta = requests.post(url, json={"type": "meta"}, timeout=10).json()
        for coin_info in meta.get('universe', []):
            if coin_info.get('name') == coin:
                return coin_info.get('szDecimals', 2)
    except Exception as e:
        print(f"⚠️  Could not fetch szDecimals for {coin}: {e}")
    return 2  # Default fallback


def round_size(size: float, sz_decimals: int) -> float:
    """
    Round size to correct decimal places for Hyperliquid.
    
    Args:
        size: Raw size value
        sz_decimals: Asset's szDecimals from API
        
    Returns:
        Rounded size
    """
    return round(size, sz_decimals)


def round_price(price: float, sz_decimals: int) -> float:
    """
    Round price to valid significant figures for Hyperliquid.
    Max 5 significant figures, and max (6 - sz_decimals) decimal places for perps.
    
    Args:
        price: Raw price value
        sz_decimals: Asset's szDecimals from API
        
    Returns:
        Rounded price
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


class ExecutionStatus(Enum):
    """Execution result status."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass
class ExecutionResult:
    """Result of order execution."""
    status: ExecutionStatus
    symbol: str
    side: str
    
    # Entry
    entry_filled: bool
    entry_price: Optional[float]
    entry_oid: Optional[int]
    entry_size: float
    
    # Stop Loss
    sl_placed: bool
    sl_price: Optional[float]
    sl_oid: Optional[int]
    
    # Take Profits
    tp_placed: bool
    tp_levels_placed: int
    tp_orders: List[Dict]
    
    # Metadata
    timestamp: datetime
    error_message: Optional[str] = None


class OrderExecutor:
    """
    Executes trade proposals on Hyperliquid with REAL orders.
    
    Usage:
        executor = OrderExecutor(client, account_address, private_key, testnet=True)
        result = executor.execute_proposal(proposal)
    """
    
    def __init__(
        self,
        client: HyperliquidClient,
        account_address: str,
        private_key: str,
        testnet: bool = True,
        notification_url: Optional[str] = None
    ):
        """
        Initialize the executor with REAL trading capability.
        
        Args:
            client: Hyperliquid API client
            account_address: Wallet address
            private_key: Wallet private key for signing orders
            testnet: Use testnet (True) or mainnet (False)
            notification_url: Optional webhook for notifications
        """
        self.client = client
        self.account_address = account_address
        self.private_key = private_key
        self.testnet = testnet
        self.notification_url = notification_url
        
        # Initialize Hyperliquid SDK for real order placement
        self.exchange = None
        self.info = None
        
        if SDK_AVAILABLE:
            try:
                api_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
                wallet = eth_account.Account.from_key(private_key)
                
                self.info = Info(api_url, skip_ws=True)
                self.exchange = Exchange(wallet, api_url, account_address=account_address)
                
                print(f"✅ Exchange SDK initialized - {'TESTNET' if testnet else 'MAINNET'}")
                print(f"   Address: {account_address}")
            except Exception as e:
                print(f"❌ Exchange SDK initialization failed: {e}")
                print("   Orders will be SIMULATED only")
        
        self.sdk_ready = (self.exchange is not None)
        
        # Cache of testnet coins (fetched once on init)
        self._testnet_coins = None
        if testnet:
            self._testnet_coins = self._fetch_testnet_coins()
            print(f"✅ Testnet coins loaded: {len(self._testnet_coins)} coins available")
    
    def _fetch_testnet_coins(self) -> set:
        """Fetch the list of coins available on testnet."""
        try:
            url = "https://api.hyperliquid-testnet.xyz/info"
            meta = requests.post(url, json={"type": "meta"}, timeout=10).json()
            coins = {c['name'] for c in meta.get('universe', [])}
            return coins
        except Exception as e:
            print(f"⚠️  Could not fetch testnet coins: {e}")
            return set()
    
    def _coin_available_on_testnet(self, coin: str) -> bool:
        """Check if a coin is available on testnet."""
        if not self.testnet:
            return True  # All coins available on mainnet
        if self._testnet_coins is None:
            return True  # Assume available if we couldn't fetch the list
        return coin in self._testnet_coins
    
    def _send_notification(self, message: str):
        """Send Telegram notification via Hermes gateway."""
        if not self.notification_url:
            print(f"   ℹ️  Notification: {message}")
            return
        
        try:
            response = requests.post(
                self.notification_url,
                json={"message": message},
                timeout=5
            )
            if response.status_code == 200:
                print(f"   ✅ Notification sent")
            else:
                print(f"   ⚠️  Notification failed: {response.status_code}")
        except Exception as e:
            print(f"   ⚠️  Notification error: {e}")
    
    def _place_market_order(
        self,
        coin: str,
        side: str,
        size_usd: float,
        leverage: int
    ) -> Tuple[bool, Optional[float], Optional[int], Optional[str]]:
        """
        Place a REAL market order on Hyperliquid.
        
        Args:
            coin: Coin symbol (e.g., "BTC")
            side: "buy" or "sell"
            size_usd: Position size in USD
            leverage: Leverage to use
            
        Returns:
            Tuple of (success, fill_price, order_id, error_message)
        """
        if not self.sdk_ready:
            return False, None, None, "SDK not initialized"
        
        try:
            # Check if coin is available on testnet (if executing on testnet)
            if not self._coin_available_on_testnet(coin):
                error_msg = f"Coin {coin} not available on testnet"
                print(f"   ❌ {error_msg}")
                return False, None, None, error_msg
            
            # Get current price
            price = self.client.get_current_price(coin)
            if price <= 0:
                return False, None, None, "Invalid price"
            
            # Calculate size in coin
            size_coin = size_usd / price
            
            # Get szDecimals for this coin and round properly
            sz_decimals = get_sz_decimals(coin, self.testnet)
            size_coin = round_size(size_coin, sz_decimals)
            
            # Also round price if needed
            price = round_price(price, sz_decimals)
            
            is_buy = (side.lower() == "buy")
            slippage = 0.05  # 5% slippage tolerance
            
            print(f"   📍 Placing REAL market order: {side.upper()} {size_coin} {coin} @ ~${price:.2f}")
            print(f"   Leverage: {leverage}x | Size: ${size_usd:.2f} (szDecimals={sz_decimals})")
            
            # Place market order via SDK
            result = self.exchange.market_open(
                name=coin,
                is_buy=is_buy,
                sz=size_coin,
                px=None,  # None = market order
                slippage=slippage
            )
            
            print(f"   📝 Order response: {result}")
            
            # Parse response to get fill info
            # Hyperliquid returns dict with 'status' and order details
            if result.get('status') == 'ok':
                # Extract fill price and OID from response
                fills = result.get('response', {}).get('data', {}).get('fills', [])
                if fills:
                    fill = fills[0]
                    fill_price = float(fill.get('px', price))
                    fill_oid = int(fill.get('oid', 0))
                    print(f"   ✅ FILLED @ ${fill_price:.2f} (OID: {fill_oid})")
                    return True, fill_price, fill_oid, None
            
            # If we get here, order was placed but fill info not immediately available
            print(f"   ⚠️  Order placed, awaiting fill confirmation")
            return True, price, 0, None  # OID=0 means pending confirmation
            
        except Exception as e:
            error_msg = f"Order failed: {str(e)}"
            print(f"   ❌ {error_msg}")
            return False, None, None, error_msg
    
    def _place_stop_loss(
        self,
        coin: str,
        side: str,
        size_coin: float,
        trigger_price: float,
        limit_price: float
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Place a REAL stop-loss order on Hyperliquid.
        
        Uses trigger order type with sl (stop loss) trigger.
        
        Args:
            coin: Coin symbol
            side: "buy" or "sell" (opposite of entry)
            size_coin: Position size in coin
            trigger_price: Price that triggers the stop
            limit_price: Limit price for the order (used if is_market=False)
            
        Returns:
            Tuple of (success, order_id, error_message)
        """
        if not self.sdk_ready:
            return False, None, "SDK not initialized"
        
        try:
            is_buy = (side.lower() == "buy")
            
            # Get szDecimals and round size/price
            sz_decimals = get_sz_decimals(coin, self.testnet)
            size_coin = round_size(size_coin, sz_decimals)
            
            if trigger_price is None:
                return False, None, "Trigger price is None"
            
            trigger_price_rounded = round_price(trigger_price, sz_decimals)
            
            if trigger_price_rounded is None:
                return False, None, f"round_price returned None for {trigger_price}"
            
            print(f"   🛡️  Placing REAL stop-loss: {side.upper()} {size_coin} {coin}")
            print(f"   Trigger: ${trigger_price_rounded:.2f} | Type: STOP MARKET (szDecimals={sz_decimals})")
            
            # Place stop-loss as trigger order (market order when triggered)
            # For stop market: limit_px = trigger price, isMarket = True
            result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=size_coin,
                limit_px=float(trigger_price_rounded),  # Required by SDK even for market orders
                order_type={
                    "trigger": {
                        "triggerPx": float(trigger_price_rounded),
                        "isMarket": True,
                        "tpsl": "sl"  # Stop loss
                    }
                },
                reduce_only=True
            )
            
            print(f"   📝 SL order response: {result}")
            
            if result.get('status') == 'ok':
                # Extract OID from response
                data = result.get('response', {}).get('data', {})
                oid = data.get('oid') if isinstance(data, dict) else None
                if oid:
                    print(f"   ✅ SL placed (OID: {oid})")
                    return True, oid, None
                print(f"   ⚠️  SL placed but OID not returned")
                return True, None, None
            
            return False, None, "SL order rejected"
            
        except Exception as e:
            error_msg = f"SL failed: {str(e)}"
            print(f"   ❌ {error_msg}")
            return False, None, error_msg
    
    def _place_take_profit(
        self,
        coin: str,
        side: str,
        size_coin: float,
        target_price: float
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Place a REAL take-profit order on Hyperliquid.
        
        Uses trigger order type with tp (take profit) trigger.
        
        Args:
            coin: Coin symbol
            side: "buy" or "sell" (opposite of entry)
            size_coin: Size for this TP level
            target_price: Target price for TP
            
        Returns:
            Tuple of (success, order_id, error_message)
        """
        if not self.sdk_ready:
            return False, None, "SDK not initialized"
        
        try:
            is_buy = (side.lower() == "buy")
            
            # Get szDecimals and round size/price
            sz_decimals = get_sz_decimals(coin, self.testnet)
            size_coin = round_size(size_coin, sz_decimals)
            target_price = round_price(target_price, sz_decimals)
            
            print(f"   🎯 Placing REAL TP: {side.upper()} {size_coin} {coin} @ ${target_price:.2f} (szDecimals={sz_decimals})")
            
            # Place take-profit as trigger order (limit order when triggered)
            result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=size_coin,
                limit_px=float(target_price),
                order_type={
                    "trigger": {
                        "triggerPx": float(target_price),
                        "isMarket": False,  # Execute as limit order
                        "tpsl": "tp"  # Take profit
                    }
                },
                reduce_only=True
            )
            
            print(f"   📝 TP order response: {result}")
            
            if result.get('status') == 'ok':
                # Extract OID from response
                data = result.get('response', {}).get('data', {})
                oid = data.get('oid') if isinstance(data, dict) else None
                if oid:
                    print(f"   ✅ TP placed (OID: {oid})")
                    return True, oid, None
                print(f"   ⚠️  TP placed but OID not returned")
                return True, None, None
            
            return False, None, "TP order rejected"
            
        except Exception as e:
            error_msg = f"TP failed: {str(e)}"
            print(f"   ❌ {error_msg}")
            return False, None, error_msg
    
    def close_position(self, coin: str, reason: str = "Manual close") -> Optional[Dict]:
        """
        Close an existing position at market price.
        
        Uses Hyperliquid SDK's exchange.order() with reduce_only=True.
        Market orders are implemented as aggressive limit orders with IOC.
        
        Args:
            coin: Coin symbol (e.g., 'ETH', 'BTC')
            reason: Reason for closing (for logging)
            
        Returns:
            Dict with close details or None if failed
            
        Reference:
            https://github.com/hyperliquid-dex/hyperliquid-python-sdk
            exchange.order(name, is_buy, sz, limit_px, order_type, reduce_only, cloid)
        """
        if not self.sdk_ready:
            print(f"   ⚠️  SDK not available for closing position")
            return None
        
        try:
            # Get current position
            positions = self.client.get_perp_positions()
            position = None
            
            for pos in positions:
                pos_coin = pos.coin if hasattr(pos, 'coin') else getattr(pos, 'coin', '')
                if pos_coin == coin.upper():
                    position = pos
                    break
            
            if not position:
                print(f"   ⚠️  No position found for {coin}")
                return None
            
            # Get position details
            szi = float(getattr(position, 'szi', 0))
            if szi == 0:
                print(f"   ⚠️  Position size is 0 for {coin}")
                return None
            
            # Determine close side (opposite of position)
            # LONG position (szi > 0) → SELL to close
            # SHORT position (szi < 0) → BUY to close
            is_buy = szi < 0  # Buy to cover short
            size_coin = abs(szi)
            
            # Get current mid price for aggressive limit order
            # Market orders in Hyperliquid SDK are aggressive limit orders with IOC
            all_mids = requests.post(
                f"{self.client.base_url}/info",
                json={"type": "allMids"},
                timeout=5
            ).json()
            
            mid_price = float(all_mids.get(coin, 0))
            if mid_price <= 0:
                print(f"   ⚠️  Invalid mid price for {coin}")
                return None
            
            # Calculate aggressive price (1% away from mid to ensure fill)
            if is_buy:
                aggressive_px = mid_price * 1.01  # Buy 1% above mid
            else:
                aggressive_px = mid_price * 0.99  # Sell 1% below mid
            
            print(f"   📍 Closing {coin} {'LONG' if szi > 0 else 'SHORT'} position...")
            print(f"   Size: {size_coin} {coin} | Mid: ${mid_price:.2f} | Aggressive: ${aggressive_px:.2f}")
            
            # Place aggressive limit order with IOC (Immediate-or-Cancel) = market order
            # Reference: https://github.com/hyperliquid-dex/hyperliquid-python-sdk/issues/29
            order_result = self.exchange.order(
                coin=coin,
                is_buy=is_buy,
                sz=size_coin,
                limit_px=aggressive_px,
                order_type={"limit": {"tif": "Ioc"}},  # IOC = market order
                reduce_only=True,  # CRITICAL: only reduces position, won't increase
                cloid=None
            )
            
            if order_result and 'status' in order_result:
                status = order_result.get('status', '')
                if status == 'ok':
                    # Get fill price from response
                    filled_px = order_result.get('filled_px', aggressive_px)
                    oid = order_result.get('oid', 0)
                    
                    print(f"   ✅ Position closed @ ${filled_px:.2f} (OID: {oid})")
                    
                    return {
                        'coin': coin,
                        'side': 'BUY' if is_buy else 'SELL',
                        'size': size_coin,
                        'price': filled_px,
                        'oid': oid,
                        'reason': reason
                    }
                else:
                    print(f"   ❌ Order rejected: {status}")
                    print(f"   Response: {order_result}")
                    return None
            else:
                print(f"   ❌ Order failed: {order_result}")
                return None
                
        except Exception as e:
            error_msg = f"Close failed: {str(e)}"
            print(f"   ❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return None
    
    def execute_proposal(self, proposal: Dict) -> ExecutionResult:
        """
        Execute a trade proposal with REAL orders.
        
        Args:
            proposal: Proposal dict from PositionProposer
            
        Returns:
            ExecutionResult object
        """
        print(f"\n{'='*70}")
        print(f"EXECUTING: {proposal['symbol']} ({proposal['side']})")
        print(f"{'='*70}")
        
        # Extract proposal data
        coin = proposal['coin']
        side = proposal['side'].lower()
        entry_price = proposal['entry_price']
        sl_price = proposal['sl_price']
        tp_price = proposal['tp_price']
        size_usd = proposal['position_sizing']['size_usd']
        leverage = proposal['position_sizing']['leverage']
        tp_levels = proposal.get('take_profit_levels', [])
        
        # Step 1: Place market entry
        print(f"\n📍 Entry...")
        entry_ok, entry_px, entry_oid, entry_err = self._place_market_order(
            coin, side, size_usd, leverage
        )
        
        if not entry_ok:
            self._send_notification(f"❌ {coin} entry failed: {entry_err}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                symbol=proposal['symbol'],
                side=proposal['side'],
                entry_filled=False,
                entry_price=None,
                entry_oid=None,
                entry_size=0,
                sl_placed=False,
                sl_price=None,
                sl_oid=None,
                tp_placed=False,
                tp_levels_placed=0,
                tp_orders=[],
                timestamp=datetime.now(timezone.utc),
                error_message=entry_err
            )
        
        # Use actual fill price or proposal price
        actual_entry = entry_px if entry_px else entry_price
        size_coin = size_usd / actual_entry
        
        print(f"   ✅ Entry filled @ ${actual_entry:.2f} (OID: {entry_oid})")
        
        # CRITICAL: Wait for position to appear before placing SL/TP
        # Market orders fill asynchronously - position may not exist yet
        print(f"\n   ⏳ Waiting for position to appear...")
        import time
        max_retries = 20  # Increased from 10 to 20 (10 seconds total)
        position_found = False
        
        for attempt in range(max_retries):
            time.sleep(0.5)  # Wait 500ms between checks
            positions = self.client.get_perp_positions()
            
            # Check if our position exists (positions are Position objects, not dicts)
            for pos in positions:
                coin_name = pos.coin if hasattr(pos, 'coin') else getattr(pos, 'coin', '')
                if coin_name == coin.upper().replace('-PERP', ''):
                    position_found = True
                    entry_px = float(getattr(pos, 'entry_px', 0))
                    print(f"   ✅ Position confirmed: {getattr(pos, 'szi', 0)} {coin} @ ${entry_px:.2f}")
                    break
            
            if position_found:
                break
        
        if not position_found:
            print(f"   ⚠️  Warning: Position not found after {max_retries} attempts, proceeding anyway...")
            # DON'T place SL/TP if position doesn't exist - they'll execute immediately!
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                symbol=proposal['symbol'],
                side=proposal['side'],
                entry_filled=True,
                entry_price=actual_entry,
                entry_oid=entry_oid,
                entry_size=size_coin,
                sl_placed=False,
                sl_price=None,
                sl_oid=None,
                tp_placed=False,
                tp_levels_placed=0,
                tp_orders=[],
                timestamp=datetime.now(timezone.utc),
                error_message="Position not found - cannot place SL/TP safely"
            )
        
        # Step 2: Place stop-loss
        print(f"\n🛡️  Stop-loss...")
        # Convert side: LONG→buy, SHORT→sell for entry; then flip for closing orders
        is_long = (side.lower() == "long")
        sl_side = "sell" if is_long else "buy"  # Close LONG with SELL, close SHORT with BUY
        
        if not sl_price:
            print(f"   ❌ SL price not provided in proposal!")
            sl_ok, sl_oid, sl_err = False, None, "No SL price in proposal"
        else:
            sl_ok, sl_oid, sl_err = self._place_stop_loss(
                coin, sl_side, size_coin, sl_price, sl_price * 0.999
            )
        
        if not sl_ok:
            print(f"   ⚠️  SL failed: {sl_err}")
        
        # Step 3: Place take-profits
        print(f"\n🎯 Take-profits...")
        tp_orders = []
        tp_side = "sell" if is_long else "buy"  # Close LONG with SELL, close SHORT with BUY
        
        for tp_level in tp_levels:
            tp_ok, tp_oid, tp_err = self._place_take_profit(
                coin,
                tp_side,
                tp_level['size_coin'],
                tp_level['target_price']
            )
            
            tp_orders.append({
                "level": tp_level['level'],
                "oid": tp_oid,
                "price": tp_level['target_price'],
                "size": tp_level['size_coin'],
                "success": tp_ok
            })
        
        tp_placed_count = sum(1 for o in tp_orders if o['success'])
        
        # Determine overall status
        if entry_ok and sl_ok and tp_placed_count == len(tp_levels):
            status = ExecutionStatus.SUCCESS
        elif entry_ok:
            status = ExecutionStatus.PARTIAL
        else:
            status = ExecutionStatus.FAILED
        
        # Send notification
        if status == ExecutionStatus.SUCCESS:
            self._send_notification(
                f"✅ {coin} {side.upper()} executed @ ${actual_entry:.2f}\n"
                f"Size: ${size_usd:.2f} @ {leverage}x\n"
                f"SL: ${sl_price:.2f} | TP: ${tp_price:.2f}"
            )
        elif status == ExecutionStatus.PARTIAL:
            self._send_notification(
                f"⚠️ {coin} {side.upper()} PARTIAL execution\n"
                f"Entry: ✅ | SL/TP: ❌"
            )
        
        # Return result
        return ExecutionResult(
            status=status,
            symbol=proposal['symbol'],
            side=proposal['side'],
            entry_filled=entry_ok,
            entry_price=actual_entry,
            entry_oid=entry_oid,
            entry_size=size_coin,
            sl_placed=sl_ok,
            sl_price=sl_price,
            sl_oid=sl_oid,
            tp_placed=(tp_placed_count > 0),
            tp_levels_placed=tp_placed_count,
            tp_orders=tp_orders,
            timestamp=datetime.now(timezone.utc),
            error_message=entry_err if not entry_ok else (sl_err if not sl_ok else None)
        )


    def generate_report(self, result: ExecutionResult) -> str:
        """
        Generate an execution report markdown file.
        
        Args:
            result: ExecutionResult object
            
        Returns:
            File path to the report
        """
        timestamp = result.timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"execution_{result.symbol}_{timestamp}.md"
        filepath = Path("data/executions") / filename
        
        # Create directory if needed
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate report content
        status_emoji = "✅" if result.status == ExecutionStatus.SUCCESS else "⚠️" if result.status == ExecutionStatus.PARTIAL else "❌"
        
        # Format prices safely
        entry_price_str = f"${result.entry_price:.2f}" if result.entry_price is not None else "N/A"
        sl_price_str = f"${result.sl_price:.2f}" if result.sl_price is not None else "N/A"
        
        content = f"""# Execution Report - {result.symbol}

**Status:** {result.status.value.upper()}  
**Timestamp:** {result.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}

## Order Details

| Field | Value |
|-------|-------|
| Symbol | {result.symbol} |
| Side | {result.side} |
| Entry Filled | {'✅ Yes' if result.entry_filled else '❌ No'} |
| Entry Price | {entry_price_str} |
| Entry OID | {result.entry_oid if result.entry_oid else 'N/A'} |
| Entry Size | {result.entry_size:.6f} |

## Risk Management

| Order | Status | Price | OID |
|-------|--------|-------|-----|
| Stop Loss | {'✅ Placed' if result.sl_placed else '❌ Failed'} | {sl_price_str} | {result.sl_oid if result.sl_oid else 'N/A'} |
| Take Profits | {result.tp_levels_placed} levels placed | - | - |

## TP Levels

"""
        for tp in result.tp_orders:
            status = "✅" if tp['success'] else "❌"
            content += f"- TP{tp['level']}: {status} @ ${tp['price']:.2f} (OID: {tp['oid']})\n"
        
        if result.error_message:
            content += f"\n## Error\n\n{result.error_message}\n"
        
        # Write file
        with open(filepath, 'w') as f:
            f.write(content)
        
        return str(filepath)

    def verify_orders(self, result: ExecutionResult, symbol: str) -> Tuple[bool, bool]:
        """
        Verify that SL and TP orders were placed successfully.
        
        Args:
            result: ExecutionResult object
            symbol: Trading pair symbol
            
        Returns:
            Tuple of (sl_ok, tp_ok)
        """
        # For now, trust the placement results
        # Real implementation would check open orders via API
        sl_ok = result.sl_placed
        tp_ok = result.tp_levels_placed > 0
        
        return sl_ok, tp_ok


# Test harness
if __name__ == "__main__":
    print("="*70)
    print("ORDER EXECUTOR - TEST MODE")
    print("="*70)
    
    # Load credentials from .env
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    private_key = os.getenv("HYPERLIQUID_WALLET_PRIVATE_KEY")
    account_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
    
    if not private_key or not account_address:
        print("❌ Missing credentials in .env")
        print("   Set HYPERLIQUID_WALLET_PRIVATE_KEY and HYPERLIQUID_WALLET_ADDRESS")
        sys.exit(1)
    
    # Initialize client and executor
    client = HyperliquidClient(testnet=True)
    executor = OrderExecutor(client, account_address, private_key, testnet=True)
    
    print(f"\n✅ Executor ready")
    print(f"   SDK: {'Ready' if executor.sdk_ready else 'Not available'}")
    print(f"   Testnet: True")
    
    # Example proposal (DO NOT EXECUTE - for testing only)
    test_proposal = {
        "coin": "BTC",
        "symbol": "BTC-PERP",
        "side": "SHORT",
        "entry_price": 60500.0,
        "sl_price": 62100.0,
        "tp_price": 58000.0,
        "position_sizing": {
            "size_usd": 100.0,
            "leverage": 5
        },
        "take_profit_levels": [
            {
                "level": 1,
                "target_price": 58000.0,
                "size_coin": 0.0005
            }
        ]
    }
    
    print(f"\n📋 Test proposal prepared")
    print(f"   Symbol: {test_proposal['symbol']}")
    print(f"   Side: {test_proposal['side']}")
    print(f"   Size: ${test_proposal['position_sizing']['size_usd']}")
    
    response = input("\n⚠️  EXECUTE TEST ORDER? (yes/no): ")
    if response.lower() == "yes":
        print(f"\n🚀 Executing test order...")
        result = executor.execute_proposal(test_proposal)
        print(f"\n📊 Result: {result.status.value}")
        print(f"   Entry: {result.entry_filled} @ ${result.entry_price}")
        print(f"   SL: {result.sl_placed} (OID: {result.sl_oid})")
        print(f"   TP: {result.tp_levels_placed} levels")
    else:
        print(f"\n✅ Test aborted - no orders placed")
    
    print("\n" + "="*70)
