# Binance Spot Volume Breakout Trading Bot

A sophisticated Python trading bot that monitors Binance Spot markets and executes trades based on volume acceleration and price momentum using 1-hour candle analysis.

## 🌟 Features

- **Real-time Market Monitoring**: Tracks top gainers on Binance with 1-hour candle analysis
- **Volume Breakout Detection**: Identifies when current candle volume exceeds configurable thresholds
- **Dynamic Risk Management**: Stop loss, take profit triggers, and trailing stops
- **Modern Web Interface**: Beautiful, responsive UI for configuration and monitoring
- **Trade History**: Complete logging of all trades with PnL tracking
- **One Trade at a Time**: Global trade lock with per-coin cooldown system
- **WebSocket Integration**: Real-time updates to the web interface

## 📋 Requirements

- Python 3.10+
- Binance API key and secret
- `uv` package manager

## 🚀 Installation

### 1. Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone or navigate to the project directory

```bash
cd binance_bot
```

### 3. Install dependencies using uv

```bash
uv pip install -e .
```

Or manually install dependencies:

```bash
uv pip install python-binance fastapi uvicorn websockets pandas python-dateutil aiofiles
```

## ⚙️ Configuration

### 1. Get Binance API Credentials

1. Log in to your Binance account
2. Go to API Management
3. Create a new API key
4. **Enable Spot Trading** permissions
5. Save your API Key and Secret Key

### 2. Configure via Web UI

The bot uses a web-based configuration interface. All settings can be adjusted through the UI:

- **API Configuration**: Binance API key and secret
- **Market Settings**: Top gainers count, candle timeframe
- **Volume Conditions**: Volume multiplier, time limit
- **Price Conditions**: Minimum price change percentage
- **Risk Management**: Stop loss %, take profit %, trailing stop %
- **Trade Restrictions**: Cooldown period per coin

## 🎯 Running the Bot

### Start the bot

```bash
cd src
uv run python main.py
```

The web interface will be available at: **http://localhost:8000**

### Using the Web Interface

1. Open your browser to `http://localhost:8000`
2. Enter your Binance API credentials in the Configuration Panel
3. Adjust trading parameters as needed
4. Click **SAVE CONFIG**
5. Click **START BOT** to begin trading

## 📊 How It Works

### Entry Conditions (ALL must be met)

1. **Time Condition**: Elapsed time ≤ Volume time limit
2. **Volume Condition**: Current 1H volume ≥ Previous 1H volume × Multiplier
3. **Price Condition**: Current price ≥ Previous 1H close + Change %
4. **No Active Trade**: Only one trade allowed at a time
5. **Not in Cooldown**: 60-minute cooldown per symbol after trade

### Risk Management

- **Stop Loss**: Fixed % below entry price
- **Take Profit Trigger**: When reached, activates trailing stop
- **Trailing Stop**: Follows highest price at configurable distance

### Position Sizing

⚠️ **IMPORTANT**: The bot uses your **entire spot balance** for each trade. This is extremely high risk. Ensure you understand the risks before running live.

## 📁 Project Structure

```
binance_bot/
├── config/
│   └── config.json          - Configuration file
├── web/
│   ├── index.html           - Web UI
│   ├── styles.css           - Styling
│   └── app.js               - Frontend logic
├── src/
│   ├── main.py              - Bot orchestrator
│   ├── web_server.py        - FastAPI server
│   ├── config_manager.py    - Config management
│   ├── binance_client.py    - Binance API wrapper
│   ├── candle_tracker.py    - Candle monitoring
│   ├── market_scanner.py    - Top gainers scanner
│   ├── entry_conditions.py  - Signal validation
│   ├── trade_manager.py     - Trade execution
│   ├── risk_manager.py      - Risk management
│   ├── state_manager.py     - State & cooldowns
│   └── trade_history.py     - History logging
├── logs/
│   ├── trade_history.json   - Trade log
│   └── bot.log              - Bot logs
└── pyproject.toml           - Project config
```

## 🎨 Web Interface Features

- **Configuration Panel**: Dynamic inputs for all parameters
- **Live Market Monitor**: Real-time top gainers with status
- **Active Trade Display**: Current position with PnL
- **Bot Logs**: Live event stream
- **Trading History**: Complete trade history with statistics

## ⚠️ Risk Warning

**THIS BOT TRADES WITH REAL MONEY. USE AT YOUR OWN RISK.**

- The bot uses your entire spot balance for each trade
- Cryptocurrency trading is highly risky
- Past performance does not guarantee future results
- Always start with small amounts
- Use testnet first if possible
- Monitor the bot continuously, especially initially

## 🔧 Troubleshooting

### API Connection Issues

- Verify API key and secret are correct
- Ensure API has Spot Trading permissions enabled
- Check if IP whitelisting is required

### Bot Not Starting

- Check logs in `logs/bot.log`
- Verify configuration in `config/config.json`
- Ensure sufficient USDT balance (minimum 10 USDT)

### WebSocket Disconnects

- The bot automatically reconnects on disconnection
- Check your internet connection
- Binance may rate limit excessive requests

## 📝 License

MIT License - Use at your own risk

## 🙏 Support

For issues or questions, check the logs first. The bot provides detailed logging of all operations.

---

**Remember**: Always test thoroughly with small amounts before deploying with significant capital.
