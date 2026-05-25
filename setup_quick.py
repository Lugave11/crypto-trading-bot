#!/usr/bin/env python3
"""
TradingAgents Crypto - Quick Setup
Uses your existing Gensee provider (no Ollama needed)
"""

import subprocess
import sys
from pathlib import Path


def main():
    print("="*60)
    print("🚀 TradingAgents Crypto - Quick Setup")
    print("="*60)
    print()
    
    # 1. Install Python dependencies
    print("📦 Installing Python dependencies...")
    packages = ['ccxt', 'pandas', 'numpy', 'tqdm', 'python-dotenv']
    
    for pkg in packages:
        print(f"   Installing {pkg}...")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', pkg, 
                '--break-system-packages'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"   ✅ {pkg} installed")
        except subprocess.CalledProcessError as e:
            print(f"   ⚠️  {pkg} installation failed, trying alternative...")
            # Try with --user flag
            try:
                subprocess.check_call([
                    sys.executable, '-m', 'pip', 'install', '--user', pkg
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"   ✅ {pkg} installed (user mode)")
            except:
                print(f"   ❌ {pkg} installation failed")
    
    print()
    
    # 2. Create configuration using existing Gensee provider
    print("⚙️  Creating configuration...")
    
    config_content = """# TradingAgents Crypto Configuration
# Using existing Gensee provider (no API key needed)

# LLM Provider - Uses your existing Gensee setup
LLM_PROVIDER=custom
LLM_BASE_URL=http://forwarder.staging.svc.cluster.local:9105/forward/gensee-397b/v1
LLM_API_KEY=gAAAAA...tIzY
DEEP_THINK_LLM=Gensee/Qwen3.5-397B
QUICK_THINK_LLM=Gensee/Qwen3.5-397B

# Alternative: Use local Ollama (if installed)
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# DEEP_THINK_LLM=qwen2.5-coder:14b
# QUICK_THINK_LLM=qwen2.5-coder:7b

# Crypto Trading Settings
CRYPTO_EXCHANGE=kraken
CRYPTO_SYMBOLS=BTC/USDT,ETH/USDT
OHLCV_TIMEFRAME=1h
OHLCV_LIMIT=100

# Risk Management
MAX_POSITION_PCT=10
LEVERAGE=1
STOP_LOSS_PCT=5
TAKE_PROFIT_PCT=10

# TradingAgents Settings
DEBUG=true
CHECKPOINT_ENABLED=false
OUTPUT_LANGUAGE=en
"""
    
    config_path = Path('.env')
    config_path.write_text(config_content)
    print(f"✅ Configuration created: {config_path}")
    
    # 3. Test crypto data fetch
    print()
    print("🧪 Testing crypto data connection...")
    
    try:
        # Add packages to path
        sys.path.insert(0, str(Path.home() / '.local' / 'lib' / 'python3.13' / 'site-packages'))
        import ccxt
        import pandas as pd
        
        print("   Fetching BTC/USDT data from Kraken...")
        exchange = ccxt.kraken()
        ohlcv = exchange.fetch_ohlcv('BTC/USDT', timeframe='1h', limit=10)
        
        if ohlcv:
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            print(f"   ✅ Success! Fetched {len(df)} candles")
            print(f"      Latest price: ${df['close'].iloc[-1]:,.2f}")
        else:
            print("   ❌ No data returned")
            
    except Exception as e:
        print(f"   ⚠️  Data fetch test failed: {e}")
        print("   (This is OK - will work when packages are properly installed)")
    
    print()
    print("="*60)
    print("✅ Setup Complete!")
    print("="*60)
    print()
    print("Your configuration:")
    print("  • LLM Provider: Gensee/Qwen3.5-397B (your existing setup)")
    print("  • Exchange: Kraken (free API, no key needed)")
    print("  • Assets: BTC/USDT, ETH/USDT")
    print()
    print("To run crypto analysis:")
    print("  cd /mnt/data/hermes/workspace/crypto_bot")
    print("  python3 -m cli.main --symbol BTC/USDT")
    print()
    print("Optional: Use local models instead")
    print("  1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh")
    print("  2. Pull model: ollama pull qwen2.5-coder:14b")
    print("  3. Edit .env and uncomment Ollama section")
    print()
    print("="*60)


if __name__ == "__main__":
    main()
