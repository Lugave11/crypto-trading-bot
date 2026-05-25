#!/bin/bash
# TradingAgents Crypto - Launch Script
# Uses system Python with user packages

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set Python path to include user packages
export PYTHONPATH="/mnt/data/hermes/workspace/.local/lib/python3.13/site-packages:/usr/lib/python3/dist-packages:$PYTHONPATH"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating default configuration..."
    cat > .env << 'EOF'
# TradingAgents Crypto Configuration

# Using Gensee provider (your existing setup)
LLM_PROVIDER=custom
LLM_BASE_URL=http://forwarder.staging.svc.cluster.local:9105/forward/gensee-397b/v1
DEEP_THINK_LLM=Gensee/Qwen3.5-397B
QUICK_THINK_LLM=Gensee/Qwen3.5-397B

# Crypto Settings
CRYPTO_EXCHANGE=kraken
CRYPTO_SYMBOLS=BTC/USDT,ETH/USDT
OHLCV_TIMEFRAME=1h
OHLCV_LIMIT=100

# Risk
MAX_POSITION_PCT=10
LEVERAGE=1
STOP_LOSS_PCT=5
TAKE_PROFIT_PCT=10

DEBUG=true
EOF
    echo "✅ Created .env"
fi

# Test imports
echo "🧪 Testing Python environment..."
python3 -c "import ccxt, pandas, numpy" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Python packages loaded"
else
    echo "❌ Python packages not found"
    echo ""
    echo "To install packages, run:"
    echo "  pip install --user ccxt pandas numpy tqdm python-dotenv"
    echo ""
    echo "Or use the setup script:"
    echo "  python3 setup_quick.py"
    exit 1
fi

echo ""
echo "============================================================"
echo "🚀 TradingAgents Crypto - Ready"
echo "============================================================"
echo ""
echo "Configuration:"
echo "  • LLM: Gensee/Qwen3.5-397B"
echo "  • Exchange: Kraken"
echo "  • Assets: BTC/USDT, ETH/USDT"
echo ""
echo "Usage:"
echo "  ./run_crypto.sh --symbol BTC/USDT"
echo "  ./run_crypto.sh --symbol ETH/USDT"
echo ""
echo "============================================================"
echo ""

# Run the CLI
python3 -m cli.main "$@"
