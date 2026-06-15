# TaoStats API Integration Plan

## 🎯 Objective

Integrate TaoStats API into the crypto-trading-bot system to enable:
1. **Bittensor subnet data fetching** for mining decisions
2. **Real-time price feeds** for TAO and Alpha tokens
3. **Validator performance metrics** for staking strategies
4. **On-chain data access** for wallet/portfolio tracking

---

## 📋 Current State Analysis

### Existing Repository Structure
```
crypto-trading-bot/
├── tradingagents/          # Core trading logic
├── paper_trading_v4.py     # Current paper trading implementation
├── run_production.py       # Production runner
├── setup_crypto.px         # Setup scripts
├── requirements.txt        # Python dependencies
└── docs/                   # Documentation (NEW)
```

### Current Capabilities
- ✅ Paper trading with trailing stops
- ✅ Multi-metric strategy execution
- ✅ Pine Script integration (TradingView)
- ✅ Hyperliquid-ready architecture (via `run_production.py`)
- ❌ No Bittensor/TaoStats integration yet

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Crypto Trading Bot                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌─────────────┐  │
│  │   Trading    │    │   Portfolio  │    │    Risk      │  │
│  │   Strategies │    │   Manager    │    │  Management  │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘  │
│         │                   │                   │          │
│         └───────────────────┼───────────────────┘          │
│                             │                               │
│                    ┌────────▼────────┐                      │
│                    │  Data Layer     │                      │
│                    │ (NEW MODULE)   │                     │
│                    └──────────────┐                     │
│                             │                               │
│         ┌───────────────────┼───────────────────┐          │
│         │                   │                   │          │
│  ┌──────▼───────┐   ┌──────▼───────┐   ┌──────▼───────┐   │
│  │   TaoStats   │   │   Hyperliquid│   │  On-Chain    │   │
│  │     API      │   │     API      │   │   (Subtensor)│   │
│  └──────────────┘   └──────────────┘   └──────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Phase 1: Setup & Authentication (Week 1)

### 1.1 Dependencies

**File:** `requirements.txt`
```txt
# Existing
requests
pandas
numpy

# NEW - TaoStats Integration
@taostats/sdk>=1.0.0          # Official TypeScript SDK (use via subprocess or alternative)
# OR Python alternative:
bittensor>=7.0.0              # Official Bittensor SDK
substrate-interface>=1.0.0    # Low-level chain access
aiohttp>=3.9.0                # Async HTTP for API calls
pydantic>=2.0.0               # Data validation
```

**Note:** TaoStats has a TypeScript SDK. For Python, we'll use:
- Direct REST API calls (`aiohttp`)
- OR `bittensor` SDK for on-chain data
- OR wrap TS SDK via Node.js subprocess

### 1.2 Configuration

**File:** `.env`
```bash
# TaoStats API Configuration
TAOSTATS_API_KEY=your_api_key_here
TAOSTATS_BASE_URL=https://management-api.taostats.io/api/v1

# Bittensor Network
BITTENSOR_NETWORK=finney
BITTENSOR_WS_URL=wss://finney.opentensor.ai:443

# Existing (Hyperliquid, etc.)
HYPERLIQUID_API_KEY=...
HYPERLIQUID_PRIVATE_KEY=...
```

### 1.3 API Client Module

**File:** `tradingagents/data/taostats_client.py` (NEW)