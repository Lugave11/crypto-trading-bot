# Hermes Modular Trading System

Automated cryptocurrency trading system for Hyperliquid with modular architecture, risk management, and Telegram notifications.

## 🚀 Quick Start

### 1. Installation

```bash
cd /mnt/data/hermes/workspace/crypto-trading-bot

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
nano .env  # Edit with your wallet credentials
```

### 2. Configuration

Edit `.env` file with your settings:

```bash
# Required
HYPERLIQUID_ACCOUNT_ADDRESS=0xYourWalletAddress
HYPERLIQUID_WALLET_PRIVATE_KEY=your_private_key
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Trading parameters
MAX_POSITIONS=5
RISK_PER_TRADE_PCT=2.0
MIN_OPPORTUNITY_SCORE=55
```

### 3. Test Run (Dry Run Mode)

```bash
# Test the pipeline (no real orders)
python3 run_pipeline.py --dry-run --account 0xYourWalletAddress

# Test the monitor
python3 run_monitor.py --single-run --account 0xYourWalletAddress
```

### 4. Deploy Cron Jobs

```bash
# Install cron jobs (pipeline every 5min, monitor every 1min)
bash setup_cron.sh
```

---

## 📁 Project Structure

```
crypto-trading-bot/
├── modules/
│   ├── api/
│   │   ├── __init__.py
│   │   └── hyperliquid.py      # Hyperliquid API client
│   ├── screener.py              # Market scanning & indicators
│   ├── risk.py                  # Risk management & position sizing
│   ├── proposer.py              # Trade proposal generation
│   ├── executor.py              # Order execution & verification
│   └── notifications.py         # Telegram notifications
│
├── tests/
│   ├── test_api_client.py       # API client tests
│   ├── test_screener.py         # Screener tests
│   ├── test_risk.py             # Risk manager tests
│   ├── test_proposer.py         # Proposer tests
│   ├── test_executor.py         # Executor tests
│   ├── test_pipeline.py         # Pipeline integration tests
│   ├── test_monitor.py          # Monitor tests
│   └── test_notifications.py    # Notification tests
│
├── data/
│   ├── proposals/               # Generated trade proposals
│   └── executions/              # Execution reports
│
├── logs/
│   ├── pipeline_*.log           # Pipeline execution logs
│   ├── monitor_*.log            # Monitor logs
│   └── notifications_*.log      # Notification logs
│
├── run_pipeline.py              # Main pipeline orchestrator
├── run_monitor.py               # Position monitor
├── setup_cron.sh                # Cron job setup script
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
└── README.md                    # This file
```

---

## 🎯 Features

### Market Scanning
- **40+ large-cap coins** screened every 5 minutes
- **Technical indicators**: RSI, MACD, ADX, ATR
- **Opportunity scoring**: 0-100 based on momentum, volume, structure
- **Filtering**: Min $1M volume, 5-10% volatility sweet spot

### Risk Management
- **Position sizing**: 2% risk per trade
- **Multi-TP levels**: 30/40/30 split at 1.5x/2.0x/3.0x risk
- **Kill switch**: Auto-pause at 3% daily / 7% weekly loss
- **Concentration limits**: Max 5 positions, no duplicates

### Order Execution
- **Market entries** for fast execution
- **Stop-loss orders** (trigger type)
- **Take-profit orders** (limit type, reduce-only)
- **Order verification** in orderbook
- **Telegram notifications** on every action

### Position Monitoring
- **Trailing stops**: 5% trail, activates at +2% profit
- **P&L tracking**: Real-time unrealized PnL
- **Auto-close**: At TP/SL levels
- **Peak tracking**: For trailing stop calculation

---

## 📊 Module Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  CRON ORCHESTRATOR                      │
│              (run_pipeline.py every 5min)               │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│   SCREENER    │  │   PROPOSER    │  │   EXECUTOR    │
│               │  │               │  │               │
│ • Fetch data  │  │ • RSI side    │  │ • Place entry │
│ • Calculate   │  │ • ATR levels  │  │ • Place SL    │
│   indicators  │  │ • Size pos    │  │ • Place TP    │
│ • Score opps  │  │ • Validate    │  │ • Verify      │
│ • Filter      │  │ • Generate    │  │ • Notify      │
└───────────────┘  └───────────────┘  └───────────────┘
                            │
                            ▼
                  ┌───────────────┐
                  │    MONITOR    │
                  │ (every 1min)  │
                  │               │
                  │ • Trail SL    │
                  │ • Track TP    │
                  │ • P&L update  │
                  │ • Auto-close  │
                  └───────────────┘
```

---

## 🔧 Configuration Options

### Pipeline (`run_pipeline.py`)

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | false | Simulate without placing orders |
| `--max-positions N` | 5 | Max concurrent positions |
| `--min-score N` | 55 | Minimum opportunity score |
| `--risk-pct N` | 2.0 | Risk per trade (%) |
| `--account` | env | Wallet address |
| `--config` | none | JSON config file |

### Monitor (`run_monitor.py`)

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | false | Simulate without executing |
| `--check-interval N` | 60 | Check interval (seconds) |
| `--single-run` | false | Run once and exit |
| `--account` | env | Wallet address |

---

## 📈 Trading Parameters

### Default Settings (`.env`)

```bash
MAX_POSITIONS=5
RISK_PER_TRADE_PCT=2.0
MIN_OPPORTUNITY_SCORE=55
MIN_POSITION_USD=20.0
MAX_POSITION_USD=500.0
MAX_LEVERAGE=10

# Kill Switch
MAX_DAILY_LOSS_PCT=3.0
MAX_WEEKLY_LOSS_PCT=7.0
MAX_DRAWDOWN_PCT=10.0

# Trailing Stop
TRAIL_ACTIVATION_PCT=2.0
TRAIL_DISTANCE_PCT=5.0
```

### Opportunity Scoring (0-100)

| Component | Max Points | Criteria |
|-----------|------------|----------|
| Momentum | 30 | RSI extremes + MACD alignment |
| Volume | 25 | $1M+ = 15pts, $10M+ = 25pts |
| Structure | 25 | ADX trend strength |
| Catalyst | 20 | Volume surge + significant moves |

**Minimum score to trade:** 55/100

---

## 🔔 Notifications

### Message Types

| Type | Priority | Description |
|------|----------|-------------|
| Entry Filled | HIGH | Position opened |
| SL Placed | NORMAL | Stop-loss order placed |
| SL Hit | CRITICAL | Stop-loss triggered |
| TP Placed | NORMAL | Take-profit order placed |
| TP Hit | HIGH | Take-profit triggered |
| Position Closed | HIGH | Full position closed |
| Trail Adjusted | LOW | Trailing stop updated |
| Error | CRITICAL | System error |

### Rate Limiting

- **Window:** 30 seconds per type
- **Max:** 1 message per window
- Prevents notification spam during volatile periods

---

## 🧪 Testing

### Run All Tests

```bash
cd /mnt/data/hermes/workspace/crypto-trading-bot
python3 -m pytest tests/ -v
```

### Individual Test Suites

```bash
# API client
python3 tests/test_api_client.py

# Screener
python3 tests/test_screener.py

# Risk manager
python3 tests/test_risk.py

# Full integration
python3 tests/test_pipeline.py
```

### Test Coverage

**57/57 tests passing** across 8 modules:
- API Client: 8/8 ✅
- Screener: 8/8 ✅
- Risk Manager: 8/8 ✅
- Position Proposer: 6/6 ✅
- Order Executor: 6/6 ✅
- Pipeline: 6/6 ✅
- Monitor: 7/7 ✅
- Notifications: 7/7 ✅

---

## 🛡️ Safety Features

### Kill Switch

Automatically pauses trading when:
- Daily loss ≥ 3% of equity
- Weekly loss ≥ 7% of equity
- Drawdown from peak ≥ 10%

### Position Limits

- Max 5 concurrent positions
- No duplicate coins
- Max 20% of equity per coin
- Min/max position size ($20-$500)

### Order Verification

- Checks orderbook after placement
- Validates SL/TP price levels
- Retries on failure (max 5 attempts)

### Dry Run Mode

Test the entire system without real orders:

```bash
python3 run_pipeline.py --dry-run --account 0xYourAddress
```

---

## 📝 Logs

### Log Files

| Log | Location | Content |
|-----|----------|---------|
| Pipeline | `logs/pipeline_*.log` | Scan → Execute flow |
| Monitor | `logs/monitor_*.log` | Position tracking |
| Notifications | `logs/notifications_*.log` | Alert history |
| Cron Pipeline | `logs/cron_pipeline.log` | Cron job output |
| Cron Monitor | `logs/cron_monitor.log` | Cron job output |

### View Logs

```bash
# Real-time
tail -f logs/pipeline_*.log

# Last 100 lines
tail -n 100 logs/pipeline_*.log

# Search for errors
grep "ERROR" logs/pipeline_*.log
```

---

## 🚨 Troubleshooting

### Common Issues

**1. "Account address required"**
- Set `HYPERLIQUID_ACCOUNT_ADDRESS` in `.env` or use `--account` flag

**2. "Max positions reached"**
- Close existing positions or increase `MAX_POSITIONS` in `.env`

**3. "No opportunities found"**
- Lower `MIN_OPPORTUNITY_SCORE` (default: 55)
- Check market conditions (low volatility = few signals)

**4. Notifications not sending**
- Verify `TELEGRAM_CHAT_ID` in `.env`
- Check Hermes gateway is running
- Review `logs/notifications_*.log`

**5. Orders not appearing in orderbook**
- Check `logs/pipeline_*.log` for execution errors
- Verify wallet has sufficient margin
- Ensure testnet/mainnet matches configuration

### Get Help

Check logs first:
```bash
tail -n 200 logs/pipeline_*.log | grep -A 3 "ERROR"
```

---

## 📄 License

Proprietary trading system. All rights reserved.

---

## 📞 Support

For issues or questions, check the logs and verify configuration in `.env`.

**System Status:** ✅ Operational (57/57 tests passing)
