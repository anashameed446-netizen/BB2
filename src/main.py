"""Main trading bot orchestrator."""
import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config_manager import ConfigManager
from binance_client import BinanceClient
from candle_tracker import CandleTracker
from market_scanner import MarketScanner
from entry_conditions import EntryConditions
from risk_manager import RiskManager
from state_manager import StateManager
from trade_manager import TradeManager
from trade_history import TradeHistory
import web_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """Main trading bot orchestrator."""
    
    def __init__(self):
        self.running = False
        self.config_manager = ConfigManager()
        
        # Initialize components
        self.binance_client = None
        self.candle_tracker = None
        self.market_scanner = None
        self.entry_conditions = None
        self.risk_manager = None
        self.state_manager = None
        self.trade_manager = None
        self.trade_history = TradeHistory()
        
        self.scan_interval = 2  # Scan every 10 seconds
        self.monitored_symbols = []
    
    def initialize(self):
        """Initialize all bot components."""
        try:
            # Initialize Binance client
            api_key = self.config_manager['api_key']
            api_secret = self.config_manager['api_secret']
            
            if not api_key or not api_secret:
                raise ValueError("API key and secret must be configured")
            
            self.binance_client = BinanceClient(api_key, api_secret)
            self.binance_client.connect()
            
            # Initialize other components
            self.candle_tracker = CandleTracker(self.binance_client)
            self.market_scanner = MarketScanner(self.binance_client)
            self.entry_conditions = EntryConditions(self.config_manager)
            self.risk_manager = RiskManager(self.config_manager)
            self.state_manager = StateManager(
                cooldown_minutes=self.config_manager['cooldown_minutes']
            )
            self.trade_manager = TradeManager(
                self.binance_client,
                self.risk_manager
            )
            
            logger.info("Bot initialized successfully")
            return True
        
        except Exception as e:
            logger.error(f"Error initializing bot: {e}")
            return False
    
    async def start(self):
        """Start the trading bot."""
        if self.running:
            logger.warning("Bot is already running")
            return
        
        if not self.initialize():
            await self.log_to_ui("❌ Failed to initialize bot. Check API credentials.", "error")
            return
        
        self.running = True
        logger.info("🚀 Trading bot started")
        await self.log_to_ui("🚀 Bot started and scanning markets...")
        
        # Start main loop
        asyncio.create_task(self.main_loop())
    
    async def stop(self):
        """Stop the trading bot and close any active trades."""
        self.running = False
        
        # Close any active trade before stopping
        # Close any active trade before stopping (FORCE)
        active_trade = self.trade_manager.get_active_trade()

        if active_trade:
            symbol = active_trade['symbol']
            logger.info(f"FORCE closing active trade {symbol} due to bot stop")
            await self.log_to_ui(f"🛑 Force closing active trade {symbol} (bot stopped)...")

            # 🚨 Force exit (market sell, no conditions)
            exit_details = self.trade_manager.force_exit_on_stop()

            if exit_details:
                # Add to history
                self.trade_history.add_trade(exit_details)

                pnl_emoji = "📈" if exit_details['pnl_percent'] > 0 else "📉"
                await self.log_to_ui(
                    f"{pnl_emoji} Trade force-closed - PnL: {exit_details['pnl_percent']:+.2f}%"
                )
            else:
                # Sell failed, but we MUST clear state
                logger.error(
                    f"Force sell failed for {symbol}. Clearing state to prevent lock."
                )
                await self.log_to_ui(
                    f"⚠️ Force sell failed for {symbol}. State cleared.",
                    "error"
                )

            # 🔥 HARD GUARANTEE — ALWAYS CLEAR STATE
            self.trade_manager.active_trade = None
            self.trade_manager.save_trade_state()
            self.state_manager.release_trade_lock()

        
        # Disconnect client after closing trade (if any)
        if self.binance_client:
            self.binance_client.disconnect()
        
        logger.info("⏹️ Trading bot stopped")
        await self.log_to_ui("⏹️ Bot stopped")
    
    async def main_loop(self):
        """Main bot execution loop."""
        while self.running:
            try:
                # Step 1: Scan top gainers
                await self.scan_markets()
                
                # Step 2: Update candle data for monitored symbols
                await self.update_candles()
                
                # Step 3: Check for entry signals (if no active trade)
                if not self.state_manager.is_trade_active():
                    await self.check_entry_signals()
                
                # Step 4: Monitor active trade (if exists)
                else:
                    await self.monitor_active_trade()
                
                # Step 5: Broadcast updates to UI
                await self.broadcast_updates()
                
                # Wait before next iteration
                await asyncio.sleep(self.scan_interval)
            
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await self.log_to_ui(f"❌ Error: {str(e)}", "error")
                await asyncio.sleep(5)
    
    async def scan_markets(self):
        """Scan and update top gainers."""
        top_gainers_count = self.config_manager['top_gainers_count']
        # Scan extra coins (1.5x) to account for filtering out stale coins
        # This ensures we have enough valid coins to display the requested count
        scan_buffer = max(int(top_gainers_count * 1.5), top_gainers_count + 10)
        symbols = self.market_scanner.scan_top_gainers(count=scan_buffer)
        
        if symbols:
            self.monitored_symbols = symbols
            self.requested_count = top_gainers_count  # Store requested count for filtering
            logger.debug(f"Scanned {len(symbols)} symbols (requested: {top_gainers_count}, buffer: {scan_buffer})")
    
    async def update_candles(self):
        """Update candle data for all monitored symbols."""
        # Timeframe is hardcoded to 1h (requirement: 1H only)
        interval = "1h"
        
        # Update all monitored symbols with small delay to avoid rate limits
        for symbol in self.monitored_symbols:
            self.candle_tracker.update_candles(symbol, interval)
            # Small delay between requests to respect rate limits (50ms = 20 req/sec max)
            await asyncio.sleep(0.01)
    
    async def check_entry_signals(self):
        """Check for entry signals across monitored symbols."""
        for symbol in self.monitored_symbols:
            # Get candle data
            prev_candle = self.candle_tracker.get_previous_candle(symbol)
            current_candle = self.candle_tracker.get_current_candle(symbol)
            
            if not prev_candle or not current_candle:
                continue
            
            # Get current price
            current_price = self.binance_client.get_current_price(symbol)
            if not current_price:
                continue
            
            # Check conditions
            result = self.entry_conditions.check_all_conditions(
                symbol=symbol,
                prev_candle_close=prev_candle.close_price,
                prev_candle_volume=prev_candle.volume,
                current_price=current_price,
                current_volume=current_candle['volume'],
                elapsed_minutes=current_candle['elapsed_minutes'],
                is_trade_active=self.state_manager.is_trade_active(),
                is_in_cooldown=self.state_manager.is_in_cooldown(symbol)
            )
            
            # Execute trade if signal detected
            if result['signal']:
                await self.execute_entry(symbol, current_price, result['reason'])
                break  # Only one trade at a time
    
    async def execute_entry(self, symbol: str, current_price: float, reason: str):
        """Execute entry trade."""
        logger.info(f"🔥 Entry signal: {symbol} @ {current_price} - {reason}")
        await self.log_to_ui(f"🔥 Entry signal detected: {symbol}")
        
        # Execute trade
        trade = self.trade_manager.execute_entry(symbol, current_price)
        
        if trade:
            # Set global trade lock
            self.state_manager.set_trade_active(symbol)
            
            # Apply cooldown
            self.state_manager.add_cooldown(symbol)
            
            await self.log_to_ui(f"✅ BUY executed @ {trade['entry_price']}")
            await self.log_to_ui(f"🛡️ SL: {trade['stop_loss']:.8f} | TP trigger: {trade['tp_trigger']:.8f}")
        else:
            # Get more detailed error information
            error_msg = f"❌ Failed to execute entry for {symbol}"
            try:
                usdt_balance = self.trade_manager.client.get_account_balance('USDT') if self.trade_manager.client else None
                if usdt_balance is None:
                    error_msg += " - Failed to fetch balance from Binance API (connection/rate limit issue)"
                elif usdt_balance < 10:
                    error_msg += f" - Insufficient balance: {usdt_balance:.2f} USDT (minimum 10 USDT required)"
                else:
                    error_msg += f" - Order placement failed (balance: {usdt_balance:.2f} USDT)"
            except Exception as e:
                error_msg += f" - Error checking balance: {type(e).__name__}"
            await self.log_to_ui(error_msg, "error")
            logger.error(f"Trade execution failed for {symbol}. Entry price: {current_price}")
    
    async def monitor_active_trade(self):
        """Monitor and update active trade."""
        trade = self.trade_manager.get_active_trade()

        if not trade:
            # Safety: trade vanished but lock may still exist
            if self.state_manager.is_trade_active():
                logger.warning("Active trade missing but lock exists. Releasing lock.")
                self.state_manager.release_trade_lock()
            return

        
        # Sync with Binance to check if trade was manually closed
        if not self.trade_manager.sync_with_binance():
            # Trade was closed manually, clear it and log
            logger.info(f"Trade {trade['symbol']} was closed manually, clearing from bot state")
            await self.log_to_ui(f"ℹ️ Trade {trade['symbol']} was closed manually, state cleared")
            self.state_manager.release_trade_lock()
            return
        
        symbol = trade['symbol']
        current_price = self.binance_client.get_current_price(symbol)
        
        if not current_price:
            return
        
        # Update trade status and get exit check result (uses updated values)
        exit_result = self.trade_manager.update_trade_status(current_price)

        if exit_result and exit_result['should_exit']:
            exit_details = exit_result['reason']

            if exit_details:
                # 1️⃣ Add to history
                self.trade_history.add_trade(exit_details)

                # 2️⃣ Release lock
                self.state_manager.release_trade_lock()

                pnl_emoji = "📈" if exit_details['pnl_percent'] > 0 else "📉"
                await self.log_to_ui(
                    f"{pnl_emoji} Trade closed - PnL: {exit_details['pnl_percent']:+.2f}%"
                )

    
    async def execute_exit(self, reason: str):
        """Execute exit trade."""
        logger.info(f"🔚 Exit signal: {reason}")
        await self.log_to_ui(f"🔚 Exit signal: {reason}")
        
        exit_details = self.trade_manager.execute_exit(reason)
        
        if exit_details:
            # Add to trade history
            active_trade = self.trade_manager.get_active_trade()
            entry_time = active_trade.get('entry_time') if active_trade else None
            if entry_time:
                exit_details['entry_time'] = entry_time
            else:
                # If entry_time not found, use current time as fallback
                from datetime import datetime
                exit_details['entry_time'] = datetime.now().isoformat()
                logger.warning(f"Entry time not found for {exit_details.get('symbol', 'unknown')}, using current time")
            
            self.trade_history.add_trade(exit_details)
            logger.info(f"Trade history updated: {len(self.trade_history.get_all_trades())} total trades")
            
            # Release trade lock
            self.state_manager.release_trade_lock()
            
            pnl_emoji = "📈" if exit_details['pnl_percent'] > 0 else "📉"
            await self.log_to_ui(
                f"{pnl_emoji} Trade closed - PnL: {exit_details['pnl_percent']:+.2f}%"
            )
    
    async def broadcast_updates(self):
        """Broadcast updates to web UI."""
        # Market update - filter and limit to requested count
        market_data = []
        requested_count = getattr(self, 'requested_count', self.config_manager['top_gainers_count'])
        
        for symbol in self.monitored_symbols:
            # Stop if we have enough valid coins
            if len(market_data) >= requested_count:
                break
            
            prev_candle = self.candle_tracker.get_previous_candle(symbol)
            current_candle = self.candle_tracker.get_current_candle(symbol)
            current_price = self.binance_client.get_current_price(symbol)
            
            # Get elapsed minutes and validate it
            elapsed_minutes = current_candle.get('elapsed_minutes') if current_candle else None
            
            # Filter out symbols with invalid elapsed time (None, negative, or > 60 minutes)
            if elapsed_minutes is None or elapsed_minutes < 0 or elapsed_minutes > 60:
                # Skip this symbol - invalid elapsed time indicates bad candle data
                continue
            
            if prev_candle and current_candle and current_price:
                result = self.entry_conditions.check_all_conditions(
                    symbol=symbol,
                    prev_candle_close=prev_candle.close_price,
                    prev_candle_volume=prev_candle.volume,
                    current_price=current_price,
                    current_volume=current_candle['volume'],
                    elapsed_minutes=elapsed_minutes,
                    is_trade_active=self.state_manager.is_trade_active(),
                    is_in_cooldown=self.state_manager.is_in_cooldown(symbol)
                )
                
                market_data.append({
                    'symbol': symbol,
                    'price': current_price,
                    'prev_close_price': prev_candle.close_price,
                    'current_volume': current_candle['volume'],
                    'prev_volume': prev_candle.volume,
                    'elapsed_minutes': elapsed_minutes,
                    'status': result['status']
                })
            else:
                # Show symbol even if candle data not ready yet (with placeholder status)
                # But only if elapsed_minutes is valid
                if elapsed_minutes is not None and 0 <= elapsed_minutes <= 60:
                    market_data.append({
                        'symbol': symbol,
                        'price': current_price if current_price else 0.0,
                        'prev_close_price': prev_candle.close_price if prev_candle else 0.0,
                        'current_volume': current_candle['volume'] if current_candle else 0.0,
                        'prev_volume': prev_candle.volume if prev_candle else 0.0,
                        'elapsed_minutes': elapsed_minutes,
                        'status': 'LOADING'
                    })
        
        # Limit to requested count (should already be done, but ensure it)
        market_data = market_data[:requested_count]
        
        await web_server.broadcast_message({
            'type': 'market_update',
            'markets': market_data,
            'filtered_count': len(market_data),
            'total_scanned': len(self.monitored_symbols),
            'requested_count': requested_count
        })
        
        # Trade update - filter out trades with less than 1 USDT
        active_trade = self.trade_manager.get_active_trade()
        
        # Check if trade has valid USDT amount (>= 1 USDT)
        if active_trade:
            # Force sync first to get actual balance from Binance
            if not self.trade_manager.sync_with_binance():
                # Trade was cleared by sync (less than 1 USDT)
                active_trade = None
                self.state_manager.release_trade_lock()
            else:
                # Trade still valid, update usdt_amount for display
                symbol = active_trade['symbol']
                current_price = self.binance_client.get_current_price(symbol)
                quantity = active_trade.get('quantity', 0)
                
                if current_price and quantity:
                    current_usdt_value = quantity * current_price
                    active_trade['usdt_amount'] = current_usdt_value
        
        await web_server.broadcast_message({
            'type': 'trade_update',
            'trade': active_trade
        })
        
        # History update
        await web_server.broadcast_message({
            'type': 'history_update',
            'history': self.trade_history.get_all_trades()
        })
    
    async def log_to_ui(self, message: str, level: str = "info"):
        """Send log message to UI."""
        await web_server.broadcast_message({
            'type': 'log',
            'message': message,
            'level': level
        })
    
    def reload_config(self):
        """Reload configuration."""
        self.config_manager.load()
        self.state_manager.update_cooldown_duration(
            self.config_manager['cooldown_minutes']
        )
        logger.info("Configuration reloaded")


async def run_server():
    """Run the FastAPI server."""
    import uvicorn
    config = uvicorn.Config(
        web_server.app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """Main entry point."""
    # Create bot instance
    bot = TradingBot()
    
    # Set bot instance in web server
    web_server.set_bot_instance(bot)
    
    # Run web server
    logger.info("Starting web server on http://localhost:8000")
    await run_server()


if __name__ == "__main__":
    asyncio.run(main())
