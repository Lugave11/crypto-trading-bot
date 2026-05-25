#!/usr/bin/env python3
"""
Crypto Data Tools for TradingAgents
Replaces stock-specific tools with crypto data sources

Primary: Hyperliquid DEX (testnet/mainnet)
Backup: CCXT exchanges (Kraken, Binance, etc.)
On-chain: Glassnode MCP (already available)
"""

import sys
sys.path.insert(0, '/mnt/data/hermes/workspace/.local/lib/python3.13/site-packages')

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
import ccxt


class CryptoDataFetcher:
    """Fetch crypto market data from Hyperliquid and other exchanges"""
    
    def __init__(self, exchange: str = "hyperliquid", testnet: bool = True):
        """
        Initialize crypto data fetcher
        
        Args:
            exchange: Primary exchange ('hyperliquid', 'kraken', 'binance', etc.)
            testnet: Use testnet for Hyperliquid
        """
        self.exchange_name = exchange
        self.testnet = testnet
        self.exchange = self._init_exchange(exchange, testnet)
    
    def _init_exchange(self, name: str, testnet: bool = True) -> Any:
        """Initialize CCXT exchange"""
        try:
            if name.lower() == "hyperliquid":
                # Hyperliquid via CCXT (if available) or direct API
                exchange = ccxt.hyperliquid()
                if testnet:
                    exchange.set_sandbox_mode(True)
            elif name.lower() == "kraken":
                exchange = ccxt.kraken()
            elif name.lower() == "binance":
                exchange = ccxt.binance()
            else:
                exchange = getattr(ccxt, name.lower())()
            
            return exchange
        except Exception as e:
            print(f"⚠️  Could not initialize {name}: {e}")
            # Fallback to Kraken (most reliable free API)
            print("   Falling back to Kraken")
            return ccxt.kraken()
    
    def get_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
        """
        Fetch OHLCV data
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT', 'ETH/USDT')
            timeframe: Candle timeframe ('1m', '5m', '15m', '1h', '4h', '1d')
            limit: Number of candles to fetch
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            return df
        except Exception as e:
            print(f"❌ Error fetching OHLCV: {e}")
            return pd.DataFrame()
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker
        
        Args:
            symbol: Trading pair
        
        Returns:
            Dict with ticker data (last, bid, ask, volume, etc.)
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'symbol': symbol,
                'last': ticker.get('last', 0),
                'bid': ticker.get('bid', 0),
                'ask': ticker.get('ask', 0),
                'volume': ticker.get('quoteVolume', 0),
                'change_24h': ticker.get('percentage', 0),
                'high_24h': ticker.get('high', 0),
                'low_24h': ticker.get('low', 0),
                'timestamp': datetime.now()
            }
        except Exception as e:
            print(f"❌ Error fetching ticker: {e}")
            return {}
    
    def get_orderbook(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """
        Fetch orderbook
        
        Args:
            symbol: Trading pair
            limit: Number of levels
        
        Returns:
            Dict with bids and asks
        """
        try:
            orderbook = self.exchange.fetch_order_book(symbol, limit=limit)
            return {
                'symbol': symbol,
                'bids': orderbook.get('bids', []),
                'asks': orderbook.get('asks', []),
                'spread': orderbook.get('bids', [[0]])[0][0] - orderbook.get('asks', [[float('inf')]])[0][0] if orderbook.get('bids') and orderbook.get('asks') else 0,
                'timestamp': datetime.now()
            }
        except Exception as e:
            print(f"❌ Error fetching orderbook: {e}")
            return {}
    
    def get_market_info(self, symbol: str) -> Dict[str, Any]:
        """
        Get comprehensive market info for a crypto asset
        
        Args:
            symbol: Trading pair
        
        Returns:
            Dict with all market data
        """
        ohlcv_1h = self.get_ohlcv(symbol, timeframe='1h', limit=100)
        ohlcv_4h = self.get_ohlcv(symbol, timeframe='4h', limit=50)
        ohlcv_1d = self.get_ohlcv(symbol, timeframe='1d', limit=30)
        ticker = self.get_ticker(symbol)
        orderbook = self.get_orderbook(symbol)
        
        # Calculate technical indicators
        indicators = self._calculate_indicators(ohlcv_1h)
        
        return {
            'symbol': symbol,
            'ticker': ticker,
            'orderbook': orderbook,
            'ohlcv': {
                '1h': ohlcv_1h,
                '4h': ohlcv_4h,
                '1d': ohlcv_1d
            },
            'indicators': indicators,
            'timestamp': datetime.now()
        }
    
    def _calculate_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate technical indicators from OHLCV data"""
        if df.empty:
            return {}
        
        indicators = {}
        
        # RSI
        indicators['rsi_14'] = self._calculate_rsi(df['close'], 14)
        
        # MACD
        macd = self._calculate_macd(df['close'])
        indicators.update(macd)
        
        # Moving averages
        indicators['sma_20'] = df['close'].rolling(window=20).mean().iloc[-1]
        indicators['sma_50'] = df['close'].rolling(window=50).mean().iloc[-1]
        indicators['ema_20'] = df['close'].ewm(span=20).mean().iloc[-1]
        
        # Bollinger Bands
        bb = self._calculate_bollinger_bands(df['close'])
        indicators.update(bb)
        
        # Volume profile
        indicators['avg_volume_20'] = df['volume'].rolling(window=20).mean().iloc[-1]
        indicators['volume_ratio'] = df['volume'].iloc[-1] / indicators['avg_volume_20'] if indicators['avg_volume_20'] > 0 else 1
        
        return indicators
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not rsi.empty else 50.0
    
    def _calculate_macd(self, prices: pd.Series) -> Dict[str, float]:
        """Calculate MACD"""
        ema_12 = prices.ewm(span=12).mean()
        ema_26 = prices.ewm(span=26).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line.iloc[-1] if not macd_line.empty else 0,
            'macd_signal': signal_line.iloc[-1] if not signal_line.empty else 0,
            'macd_histogram': histogram.iloc[-1] if not histogram.empty else 0
        }
    
    def _calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> Dict[str, float]:
        """Calculate Bollinger Bands"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        return {
            'bb_upper': upper.iloc[-1] if not upper.empty else prices.iloc[-1],
            'bb_middle': sma.iloc[-1] if not sma.empty else prices.iloc[-1],
            'bb_lower': lower.iloc[-1] if not lower.empty else prices.iloc[-1],
            'bb_width': (upper.iloc[-1] - lower.iloc[-1]) / sma.iloc[-1] * 100 if not upper.empty and not sma.empty else 0
        }


def get_crypto_market_data(symbol: str = "BTC/USDT", exchange: str = "kraken") -> Dict[str, Any]:
    """
    Get comprehensive crypto market data
    
    Args:
        symbol: Trading pair (e.g., 'BTC/USDT', 'ETH/USDT')
        exchange: Exchange name
    
    Returns:
        Dict with all market data
    """
    fetcher = CryptoDataFetcher(exchange=exchange)
    return fetcher.get_market_info(symbol)


if __name__ == "__main__":
    # Test with BTC/USDT on Kraken
    print("📊 Fetching crypto market data...")
    data = get_crypto_market_data("BTC/USDT", exchange="kraken")
    
    if data:
        print(f"\n✅ Symbol: {data['symbol']}")
        print(f"   Last price: ${data['ticker'].get('last', 0):,.2f}")
        print(f"   24h change: {data['ticker'].get('change_24h', 0):+.2f}%")
        print(f"   Volume: ${data['ticker'].get('volume', 0):,.2f}")
        
        print(f"\n📈 Technical Indicators:")
        indicators = data['indicators']
        print(f"   RSI(14): {indicators.get('rsi_14', 0):.2f}")
        print(f"   MACD: {indicators.get('macd', 0):.4f}")
        print(f"   MACD Signal: {indicators.get('macd_signal', 0):.4f}")
        print(f"   SMA(20): ${indicators.get('sma_20', 0):,.2f}")
        print(f"   SMA(50): ${indicators.get('sma_50', 0):,.2f}")
        print(f"   Bollinger Width: {indicators.get('bb_width', 0):.2f}%")
    else:
        print("❌ Failed to fetch data")
