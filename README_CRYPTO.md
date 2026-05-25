# 🚀 TradingAgents Crypto - Hyperliquid Setup Guide

## Overview
Adapt TradingAgents from stocks to crypto trading on Hyperliquid DEX

## Quick Start

### 1. Install Dependencies

```bash
# Using system Python (has ccxt, pandas already installed)
cd /mnt/data/hermes/workspace/crypto_bot

# Or install manually:
pip install ccxt pandas numpy
```

### 2. Copy Crypto Config

```bash
cp .env.crypto.example .env
```

Edit `.env` and add:
- Your LLM API key (OpenAI, Anthropic, etc.)
- Crypto exchange settings

### 3. Run Crypto Analysis

```bash
# Using system Python
PYTHONPATH=/mnt/data/hermes/workspace/.local/lib/python3.13/site-packages \
python3 -m cli.main --symbol BTC/USDT

# Or with custom config
python3 setup_crypto.py  # Installs packages and tests
```

## Architecture Changes

### What Changed from Stocks → Crypto

| Stock Feature | Crypto Replacement |
|--------------|-------------------|
| yfinance | CCXT + Hyperliquid API |
| Company fundamentals | Tokenomics + On-chain metrics |
| Earnings reports | Protocol revenue + TVL |
| P/E ratios | NVT ratios + MVRV |
| Market hours | 24/7 trading |
| Stock symbols | Trading pairs (BTC/USDT) |

### What Stayed the Same

- ✅ Multi-agent architecture
- ✅ Bull/Bear researcher debates
- ✅ Technical analysis (RSI, MACD, etc.)
- ✅ Sentiment analysis (news, social)
- ✅ Risk management
- ✅ Portfolio management

## Data Sources

### Primary: Hyperliquid DEX
- **URL:** https://hyperliquid.xyz
- **Testnet:** https://testnet.hyperliquid.xyz
- **API:** No key required (DEX)
- **Data:** OHLCV, orderbook, trades, funding rates

### Secondary: CCXT Exchanges
- **Kraken:** Most reliable free API
- **Binance:** Largest volume (geo-restricted)
- **OKX, Bybit, Gate.io:** Backup options

### On-Chain: Glassnode MCP
- **Already configured** in Hermes
- **No API key needed**
- **Metrics:** MVRV, NUPL, exchange flows, active addresses

### News & Sentiment
- **CoinDesk RSS:** Free crypto news
- **LunarCrush:** Social sentiment (free tier)
- **Reddit/Twitter:** Via existing sentiment analyst

## File Structure

```
crypto_bot/
├── tradingagents/
│   ├── data/
│   │   └── crypto_data.py          # NEW: Crypto data fetcher
│   ├── agents/
│   │   └── utils/
│   │       ├── crypto_data_tools.py    # Adapted for crypto
│   │       └── tokenomics_tools.py     # NEW: Token metrics
│   └── default_config.py           # Modified for crypto
├── .env.crypto.example             # NEW: Crypto config template
├── setup_crypto.py                 # NEW: Setup script
├── ADAPTATION_PLAN.md              # Implementation plan
└── README.md                       # This file
```

## Configuration

### Environment Variables

```bash
# LLM Provider (REQUIRED)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Or Anthropic
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...

# Crypto Settings
CRYPTO_EXCHANGE=kraken  # kraken, binance, hyperliquid
CRYPTO_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
OHLCV_TIMEFRAME=1h
OHLCV_LIMIT=100

# Risk Management
MAX_POSITION_PCT=10
LEVERAGE=1
STOP_LOSS_PCT=5
TAKE_PROFIT_PCT=10
```

## Usage Examples

### Analyze Bitcoin

```bash
python3 -m cli.main --symbol BTC/USDT
```

### Analyze Ethereum

```bash
python3 -m cli.main --symbol ETH/USDT
```

### Multiple Assets

```bash
# Edit .env and set:
CRYPTO_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,AVAX/USDT

# Then run:
python3 -m cli.main
```

## Testing

### Test Data Fetch

```bash
python3 -c "
import sys
sys.path.insert(0, 'tradingagents/data')
from crypto_data import get_crypto_market_data

data = get_crypto_market_data('BTC/USDT', exchange='kraken')
print(f'BTC Price: \${data[\"ticker\"][\"last\"]:,.2f}')
print(f'24h Change: {data[\"ticker\"][\"change_24h\"]:+.2f}%')
"
```

### Test Full Pipeline

```bash
# With mock data (no API calls)
python3 test.py --mock

# With live data
python3 test.py --symbol BTC/USDT
```

## Troubleshooting

### Package Installation Issues

```bash
# If pip install fails, try:
pip install --user ccxt pandas numpy

# Or use conda:
conda install -c conda-forge ccxt pandas numpy
```

### API Rate Limits

- Kraken: 15 requests/second (free tier)
- Reduce `OHLCV_LIMIT` if hitting limits
- Add retry logic with exponential backoff

### Geo-Restrictions

- Binance blocked in some regions (451 error)
- Use Kraken or OKX as alternative
- Consider VPN for unrestricted access

## Next Steps

1. ✅ Data layer created (crypto_data.py)
2. ⏳ Adapt analysts for crypto
3. ⏳ Update CLI for crypto symbols
4. ⏳ Test with live Hyperliquid data
5. ⏳ Add on-chain metrics (Glassnode MCP)
6. ⏳ Implement paper trading on Hyperliquid

## Resources

- **TradingAgents Original:** https://github.com/TauricResearch/TradingAgents
- **Hyperliquid Docs:** https://hyperliquid.gitbook.io/hyperliquid-docs
- **CCXT Manual:** https://docs.ccxt.com/
- **Glassnode MCP:** Already configured in Hermes

## Disclaimer

This is for **research and educational purposes only**. Not financial or trading advice. Crypto trading involves significant risk. Past performance does not guarantee future results.
