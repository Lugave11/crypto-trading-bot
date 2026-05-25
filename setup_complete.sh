#!/bin/bash
# TradingAgents Crypto - Complete Setup Script
# Installs Ollama, local models, and all dependencies

set -e

echo "============================================================"
echo "🚀 TradingAgents Crypto - Complete Setup"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Install Ollama
echo "📦 Step 1: Installing Ollama..."
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}✅ Ollama already installed${NC}"
else
    echo "   Downloading and installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Ollama installed${NC}"
    else
        echo -e "${RED}❌ Ollama installation failed${NC}"
        exit 1
    fi
fi

# 2. Start Ollama service
echo ""
echo "🔄 Step 2: Starting Ollama service..."
ollama serve > /dev/null 2>&1 &
OLLAMA_PID=$!
sleep 3
echo -e "${GREEN}✅ Ollama service started (PID: $OLLAMA_PID)${NC}"

# 3. Pull local models
echo ""
echo "📥 Step 3: Downloading local LLM models..."
echo "   This may take 10-30 minutes depending on your internet speed"
echo ""

# Model selection
echo "   Select model size:"
echo "   1) Qwen2.5-Coder:7b (4.5GB) - Fast, good for coding"
echo "   2) Qwen2.5-Coder:14b (9GB) - Balanced"
echo "   3) Qwen2.5-Coder:32b (20GB) - Best quality, slower"
echo "   4) Llama3.1:8b (4.7GB) - General purpose"
echo "   5) Mistral:7b (4.1GB) - Lightweight"
read -p "   Choose model (1-5, default=2): " MODEL_CHOICE

case ${MODEL_CHOICE:-2} in
    1) MODEL="qwen2.5-coder:7b" ;;
    2) MODEL="qwen2.5-coder:14b" ;;
    3) MODEL="qwen2.5-coder:32b" ;;
    4) MODEL="llama3.1:8b" ;;
    5) MODEL="mistral:7b" ;;
    *) MODEL="qwen2.5-coder:14b" ;;
esac

echo ""
echo "   Pulling $MODEL..."
ollama pull $MODEL
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Model downloaded: $MODEL${NC}"
else
    echo -e "${RED}❌ Model download failed${NC}"
    exit 1
fi

# 4. Install Python dependencies
echo ""
echo "📦 Step 4: Installing Python dependencies..."

# Check if we're in a virtual environment
if [ -n "$VIRTUAL_ENV" ]; then
    PIP_CMD="pip"
    echo "   Using virtual environment: $VIRTUAL_ENV"
else
    # Try system pip with --user
    PIP_CMD="pip3 --user"
    echo "   Using system Python with --user flag"
fi

$PIP_CMD install ccxt pandas numpy tqdm requests python-dotenv

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Python packages installed${NC}"
else
    echo -e "${RED}❌ Python package installation failed${NC}"
    exit 1
fi

# 5. Create configuration
echo ""
echo "⚙️  Step 5: Creating configuration..."

cat > .env << 'EOF'
# TradingAgents Crypto Configuration

# Local LLM (Ollama)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
DEEP_THINK_LLM=qwen2.5-coder:14b
QUICK_THINK_LLM=qwen2.5-coder:7b

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
EOF

echo -e "${GREEN}✅ Configuration created: .env${NC}"

# 6. Test setup
echo ""
echo "🧪 Step 6: Testing setup..."

# Test Ollama
echo "   Testing Ollama connection..."
ollama ps > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "   ${GREEN}✅ Ollama running${NC}"
else
    echo -e "   ${RED}❌ Ollama not responding${NC}"
fi

# Test Python packages
echo "   Testing Python imports..."
python3 -c "import ccxt, pandas, numpy" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "   ${GREEN}✅ Python packages working${NC}"
else
    echo -e "   ${RED}❌ Python import failed${NC}"
fi

echo ""
echo "============================================================"
echo "✅ Setup Complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Keep Ollama running: ollama serve"
echo "2. Run crypto analysis: python3 -m cli.main --symbol BTC/USDT"
echo ""
echo "Current model: $MODEL"
echo "To change model: edit .env and modify DEEP_THINK_LLM"
echo ""
echo "============================================================"
