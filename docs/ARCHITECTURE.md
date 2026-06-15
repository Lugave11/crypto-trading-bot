# Trading System - Architecture

## Overview
Fully automated crypto trading system using Hermes Kanban for orchestration.

## Profiles
- ``trading-data`: Collects market data, whale activity, news
- ``trading-orchestrator`: Makes routing decisions
- ``trading-mean-reversion`: Executes RSI strategies

## Cron Jobs
- Data Collection: `/5 * * * *` (every 5 min)
- Orchestrator: `*/15 * * * *` (every 15 min)

## Data Sources
- OHLCV: Binance.US
- Whale Tracking: Etherscan V2
- News: 4 RSS feeds

## Monitoring
```bash
hermes kanban list
hermes cron list
```
