#!/usr/bin/env python3
"""
Setup script for TradingAgents Crypto - Hyperliquid
Installs required packages and configures for crypto trading
"""

import subprocess
import sys
from pathlib import Path


def install_packages():
    """Install crypto-specific packages"""
    packages = [
        'ccxt>=4.0.0',  # Crypto exchange API
        'pandas>=2.0.0',  # Data manipulation
        'numpy>=1.24.0',  # Numerical computing
        'hyperliquid-sdk>=0.7.0',  # Hyperliquid DEX (optional)
    ]
    
    print("📦 Installing crypto trading packages...")
    for pkg in packages:
        print(f"   Installing {pkg}...")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '--break-system-packages'])
            print(f"   ✅ {pkg} installed")
        except subprocess.CalledProcessError as e:
            print(f"   ⚠️  {pkg} installation failed: {e}")
    
    print("\n✅ Package installation complete!")


def create_crypto_config():
    """Create crypto-specific configuration"""
    
    config_content = """# TradingAgents Crypto Configuration
# Copy this to .env and add your API keys

# LLM Provider (required)
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here

# Or use other providers:
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=your_anthropic_key_here

# LLM Models
DEEP_THINK_LLM=gpt-4o
QUICK_THINK_LLM=gpt-4o-mini

# Crypto Trading Settings
CRYPTO_EXCHANGE=kraken  # kraken, binance, hyperliquid
HYPERLIQUID_TESTNET=true  # Use Hyperliquid testnet

# Trading Pairs to analyze
CRYPTO_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT

# Risk Settings
MAX_POSITION_PCT=10  # Max position size as % of portfolio
LEVERAGE=1  # Leverage multiplier (1 = no leverage)
STOP_LOSS_PCT=5  # Stop loss percentage
TAKE_PROFIT_PCT=10  # Take profit percentage

# Data Settings
OHLCV_TIMEFRAME=1h  # Primary timeframe for analysis
OHLCV_LIMIT=100  # Number of candles to fetch

# Optional: Glassnode MCP (already configured in Hermes)
# No API key needed - uses Hermes MCP server

# Optional: Additional data sources
# LUNARCRUSH_API_KEY=  # Social sentiment
# COINGECKO_API_KEY=  # CoinGecko API
"""
    
    config_path = Path('.env.crypto.example')
    config_path.write_text(config_content)
    print(f"✅ Created crypto config: {config_path}")


def test_crypto_data():
    """Test crypto data fetching"""
    print("\n🧪 Testing crypto data fetch...")
    
    try:
        from tradingagents.data.crypto_data import get_crypto_market_data
        
        print("   Fetching BTC/USDT data from Kraken...")
        data = get_crypto_market_data("BTC/USDT", exchange="kraken")
        
        if data and data.get('ticker'):
            print(f"   ✅ Success!")
            print(f"      Price: ${data['ticker'].get('last', 0):,.2f}")
            print(f"      24h Change: {data['ticker'].get('change_24h', 0):+.2f}%")
            return True
        else:
            print("   ❌ No data returned")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def main():
    print("="*60)
    print("🚀 TradingAgents Crypto - Hyperliquid Setup")
    print("="*60)
    
    # Install packages
    install_packages()
    
    # Create config
    create_crypto_config()
    
    # Test data fetch
    test_crypto_data()
    
    print("\n" + "="*60)
    print("✅ Setup complete!")
    print("\nNext steps:")
    print("1. Copy .env.crypto.example to .env")
    print("2. Add your LLM API key (OpenAI, Anthropic, etc.)")
    print("3. Run: python -m cli.main --symbol BTC/USDT")
    print("="*60)


if __name__ == "__main__":
    main()
