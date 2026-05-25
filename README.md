# Crypto Trading Bot

Multi-agent crypto trading system with walk-forward backtesting.

## Features

- Multi-agent architecture (Data Feed, On-Chain, Technical, Sentiment analysts)
- Walk-forward validation (10+ iterations)
- Risk-adjusted returns optimization (DD <15%)
- Position sizing: 5-6% base (15-18% with 3x leverage)
- Manager-controlled exits (60% threshold)
- 100% FREE data sources (Glassnode MCP, Kraken public data, CoinDesk RSS)

## Getting Started

```bash
pip install -r requirements.txt
python cli.py --help
```

## License

MIT
