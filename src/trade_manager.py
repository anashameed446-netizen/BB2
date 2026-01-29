"""Trade manager for executing and managing trades."""
import time
import json
import logging
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TradeManager:
    """Manages trade execution and position tracking."""
    
    def __init__(self, binance_client, risk_manager, trade_state_file: str = "logs/active_trade.json"):
        self.client = binance_client
        self.risk_manager = risk_manager
        self.active_trade: Optional[Dict] = None
        self.trade_state_file = Path(trade_state_file)
        self.load_trade_state()
    
    def execute_entry(self, symbol: str, entry_price: float) -> Optional[Dict]:
        """
        Execute market buy order with entire spot balance.
        
        Returns:
            Trade dict if successful, None otherwise
        """
        try:
            # Get available USDT balance (with retry logic)
            usdt_balance = self.client.get_account_balance('USDT')
            
            # Check if balance fetch failed (None means API error)
            if usdt_balance is None:
                logger.error(f"Failed to fetch USDT balance from Binance API - check connection and API credentials")
                return None
            
            if usdt_balance < 10:  # Minimum 10 USDT
                logger.error(f"Insufficient balance: {usdt_balance:.2f} USDT (minimum 10 USDT required)")
                return None
            
            logger.info(f"Executing buy order for {symbol} with {usdt_balance:.2f} USDT")
            
            # Place market buy order using entire balance
            order = self.client.place_market_buy(
                symbol=symbol,
                quote_amount=usdt_balance
            )
            
            if not order:
                logger.error(f"Failed to place order for {symbol} - order returned None")
                return None
            
            # Check if order was actually filled
            if 'executedQty' not in order or float(order.get('executedQty', 0)) == 0:
                logger.error(f"Order for {symbol} was not filled - executedQty: {order.get('executedQty', 'N/A')}")
                return None
            
            # Extract filled quantity and average price
            filled_qty = float(order['executedQty'])
            filled_price = float(order['fills'][0]['price']) if order['fills'] else entry_price
            
            # Calculate USDT amount used (entry_price * quantity)
            usdt_amount = filled_price * filled_qty
            
            # Calculate risk management levels
            stop_loss = self.risk_manager.calculate_stop_loss(filled_price)
            tp_trigger = self.risk_manager.calculate_take_profit_trigger(filled_price)
            
            # Create trade record
            trade = {
                'symbol': symbol,
                'entry_price': filled_price,
                'entry_time': datetime.now().isoformat(),
                'quantity': filled_qty,
                'usdt_amount': usdt_amount,  # USDT capital used
                'stop_loss': stop_loss,
                'tp_trigger': tp_trigger,
                'trailing_stop': None,
                'highest_price': filled_price,
                'current_price': filled_price,
                'trailing_active': False,
                'state': 'ACTIVE',
                'pnl_percent': 0.0,
                'entry_timestamp': time.time(),

            }
            
            self.active_trade = trade
            self.save_trade_state()  # Persist trade state
            logger.info(f"Trade opened: {symbol} @ {filled_price}")
            return trade
        
        except Exception as e:
            logger.error(f"Error executing entry for {symbol}: {e}")
            return None
    
    def execute_exit(self, reason: str) -> Optional[Dict]:
        """
        Execute market sell order to close position.
        
        Returns:
            Exit details if successful, None otherwise
        """
        if not self.active_trade:
            logger.warning("No active trade to exit")
            return None
        
        try:
            symbol = self.active_trade['symbol']
            
            # Extract base asset from symbol (e.g., BTCUSDT -> BTC)
            base_asset = symbol.replace('USDT', '')
            
            # Validate client is connected
            if not self.client or not self.client.connected:
                logger.error(f"Cannot execute exit: Binance client not connected")
                return None
            
            # Get actual balance from Binance instead of using stored quantity
            # This ensures we sell exactly what we have, avoiding "insufficient balance" errors
            actual_balance = self.client.get_account_balance(base_asset)
            
            # Validate balance - None means API error
            if actual_balance is None:
                logger.error(f"Failed to fetch {base_asset} balance from Binance API - cannot execute exit")
                return None
            
            if actual_balance <= 0:
                logger.error(f"Zero or negative balance for {symbol}: {actual_balance}")
                return None
            
            # Get symbol info to apply LOT_SIZE filter (round quantity to correct step size)
            symbol_info = self.client.get_symbol_info(symbol)
            if symbol_info:
                # Find LOT_SIZE filter
                lot_size_filter = None
                for filt in symbol_info.get('filters', []):
                    if filt.get('filterType') == 'LOT_SIZE':
                        lot_size_filter = filt
                        break
                
                if lot_size_filter:
                    # Get step size and minimum quantity
                    step_size = float(lot_size_filter.get('stepSize', '1'))
                    min_qty = float(lot_size_filter.get('minQty', '0'))
                    
                    # Round quantity to step size
                    # Calculate how many steps fit in the quantity
                    steps = actual_balance / step_size
                    rounded_steps = int(steps)  # Round down to avoid exceeding balance
                    rounded_quantity = rounded_steps * step_size
                    
                    # Ensure it meets minimum quantity requirement
                    if rounded_quantity < min_qty:
                        logger.warning(
                            f"Rounded quantity {rounded_quantity} for {symbol} is below minimum {min_qty}. "
                            f"Original balance: {actual_balance}, step size: {step_size}"
                        )
                        # If below minimum, we can't place the order
                        if actual_balance < min_qty:
                            logger.error(f"Balance {actual_balance} for {symbol} is below minimum quantity {min_qty}")
                            return None
                        # Use minimum quantity if balance is above it
                        rounded_quantity = min_qty
                    
                    # Update actual_balance to use rounded quantity
                    if abs(rounded_quantity - actual_balance) > step_size * 0.1:  # More than 10% of step size difference
                        logger.info(
                            f"Rounded quantity for {symbol}: {actual_balance} -> {rounded_quantity} "
                            f"(step size: {step_size})"
                        )
                    actual_balance = rounded_quantity
                else:
                    logger.warning(f"Could not find LOT_SIZE filter for {symbol}, using balance as-is")
            else:
                logger.warning(f"Could not get symbol info for {symbol}, using balance as-is")
            
            # Check for and cancel any open orders first (stop loss, take profit, etc.)
            open_orders = self.client.get_open_orders(symbol)
            if open_orders:
                logger.info(f"Found {len(open_orders)} open order(s) for {symbol}, cancelling before market sell...")
                for order in open_orders:
                    logger.info(f"  - Order ID {order.get('orderId')}: {order.get('type')} {order.get('side')} @ {order.get('price', 'N/A')}")
                
                if not self.client.cancel_all_orders(symbol):
                    logger.warning(f"Failed to cancel some orders for {symbol}, but proceeding with market sell")
                else:
                    logger.info(f"Successfully cancelled all open orders for {symbol}")
            else:
                logger.debug(f"No open orders found for {symbol}")
            
            # Log both stored quantity and actual balance for comparison
            stored_quantity = self.active_trade.get('quantity', 0)
            if abs(actual_balance - stored_quantity) > stored_quantity * 0.01:  # More than 1% difference
                logger.info(
                    f"Balance difference detected for {symbol}: stored={stored_quantity}, actual={actual_balance}. "
                    f"Using actual balance for sell order."
                )
            
            logger.info(f"Executing sell order for {symbol}: {actual_balance} (actual balance from Binance)")
            
            # Place market sell order using actual balance
            order = self.client.place_market_sell(
                symbol=symbol,
                quantity=actual_balance
            )
            
            if not order:
                logger.error(f"Failed to place sell order for {symbol} - order returned None")
                return None
            
            # Check if order was filled
            executed_qty = float(order.get('executedQty', 0))
            if executed_qty <= 0:
                logger.error(f"Sell order for {symbol} was not filled. Order status: {order.get('status')}, executedQty: {executed_qty}")
                return None
            
            # Extract exit price
            if order.get('fills') and len(order['fills']) > 0:
                exit_price = float(order['fills'][0]['price'])
            else:
                # Fallback to current price if fills not available
                exit_price = self.active_trade.get('current_price', self.active_trade['entry_price'])
                logger.warning(f"Using fallback exit price {exit_price} for {symbol} (no fills in order)")
            
            # Calculate final PnL
            pnl_percent = self.risk_manager.calculate_pnl_percent(
                self.active_trade['entry_price'],
                exit_price
            )
            
            # Store entry_time and usdt_amount before clearing active_trade
            entry_time = self.active_trade.get('entry_time')
            usdt_amount = self.active_trade.get('usdt_amount', 0)
            
            # Calculate exit USDT amount using executed quantity from order
            executed_qty = float(order.get('executedQty', 0))
            exit_usdt_amount = exit_price * executed_qty
            
            exit_details = {
                'symbol': symbol,
                'entry_price': self.active_trade['entry_price'],
                'exit_price': exit_price,
                'exit_time': datetime.now().isoformat(),
                'pnl_percent': pnl_percent,
                'exit_reason': reason,
                'usdt_amount': usdt_amount,  # USDT capital used
                'exit_usdt_amount': exit_usdt_amount  # USDT received on exit
            }
            
            # Add entry_time if available
            if entry_time:
                exit_details['entry_time'] = entry_time
            
            logger.info(f"Trade closed: {symbol} @ {exit_price}, PnL: {pnl_percent:.2f}%")
            
            self.active_trade = None
            self.save_trade_state()  # Persist state (clear active trade)
            return exit_details
        
        except Exception as e:
            logger.error(f"Error executing exit for {self.active_trade.get('symbol', 'unknown')}: {type(e).__name__}: {e}", exc_info=True)
            return None
    
    def update_trade_status(self, current_price: float) -> Dict:
        if not self.active_trade:
            return {'should_exit': False, 'reason': None}

        trade = self.active_trade
        trade['current_price'] = current_price

        # 1️⃣ Update highest price FIRST
        if current_price > trade['highest_price']:
            trade['highest_price'] = current_price

            # Move trailing stop UP ONLY
            if trade['trailing_active']:
                new_ts = self.risk_manager.calculate_trailing_stop(trade['highest_price'])
                if trade['trailing_stop'] is None or new_ts > trade['trailing_stop']:
                    trade['trailing_stop'] = new_ts

        # 2️⃣ Update PnL
        trade['pnl_percent'] = self.risk_manager.calculate_pnl_percent(
            trade['entry_price'],
            current_price
        )

        # 3️⃣ TIME-BASED EXIT (HARD EXIT)
        cfg = self.risk_manager.config
        if cfg.get('time_exit_enabled', False):
            max_minutes = cfg.get('max_trade_duration_minutes', 0)
            if max_minutes > 0:
                entry_ts = trade.get('entry_timestamp')

                # Backward compatibility for old trades
                if entry_ts is None:
                    # Fallback: use entry_time ISO string if available
                    entry_time_str = trade.get('entry_time')
                    if entry_time_str:
                        entry_ts = datetime.fromisoformat(entry_time_str).timestamp()
                        trade['entry_timestamp'] = entry_ts  # persist fix
                    else:
                        # Absolute last fallback: assume "now" to avoid crash
                        entry_ts = time.time()
                        trade['entry_timestamp'] = entry_ts

                elapsed_minutes = (time.time() - entry_ts) / 60

                if elapsed_minutes >= max_minutes:
                    logger.warning(
                        f"Exit: Time-based exit | "
                        f"Elapsed={elapsed_minutes:.2f}m | Limit={max_minutes}m"
                    )
                    exit_details = self.execute_exit(
                        reason=f"Time exit after {max_minutes} minutes"
                    )
                    return {'should_exit': True, 'reason': exit_details}

        # 4️⃣ Activate trailing ONCE
        if not trade['trailing_active'] and current_price >= trade['tp_trigger']:
            trade['trailing_active'] = True
            trade['state'] = 'TRAILING ACTIVE'
            trade['highest_price'] = current_price
            trade['trailing_stop'] = self.risk_manager.calculate_trailing_stop(current_price)

            logger.info(
                f"Trailing activated | price={current_price} | "
                f"TS={trade['trailing_stop']}"
            )

        # 5️⃣ TRAILING STOP EXIT
        if trade['trailing_active'] and trade['trailing_stop'] is not None:
            if current_price <= trade['trailing_stop']:
                logger.warning(
                    f"Exit: Trailing stop hit | "
                    f"price={current_price} <= TS={trade['trailing_stop']}"
                )
                exit_details = self.execute_exit(
                    reason=f"Trailing stop hit at {trade['trailing_stop']}"
                )
                return {'should_exit': True, 'reason': exit_details}

        # 6️⃣ STOP LOSS EXIT
        if current_price <= trade['stop_loss']:
            logger.warning(
                f"Exit: Stop loss hit | "
                f"price={current_price} <= SL={trade['stop_loss']}"
            )
            exit_details = self.execute_exit(
                reason=f"Stop loss hit at {trade['stop_loss']}"
            )
            return {'should_exit': True, 'reason': exit_details}

        self.save_trade_state()
        return {'should_exit': False, 'reason': None}


    
    def get_active_trade(self) -> Optional[Dict]:
        """Get current active trade details."""
        return self.active_trade
    
    def has_active_trade(self) -> bool:
        """Check if there's an active trade."""
        return self.active_trade is not None
    
    def save_trade_state(self) -> None:
        """Save active trade state to file."""
        try:
            # Ensure directory exists
            self.trade_state_file.parent.mkdir(parents=True, exist_ok=True)
            
            state = {
                'active_trade': self.active_trade,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.trade_state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)
            
            logger.debug(f"Trade state saved to {self.trade_state_file}")
        except Exception as e:
            logger.error(f"Error saving trade state: {e}")
    
    def load_trade_state(self) -> None:
        """Load active trade state from file."""
        try:
            if not self.trade_state_file.exists():
                logger.info("No saved trade state found")
                return
            
            with open(self.trade_state_file, 'r') as f:
                state = json.load(f)
            
            self.active_trade = state.get('active_trade')
            
            if self.active_trade:
                logger.info(f"Restored active trade: {self.active_trade.get('symbol')} @ {self.active_trade.get('entry_price')}")
                # Sync with Binance to verify trade still exists
                self.sync_with_binance()
        except Exception as e:
            logger.error(f"Error loading trade state: {e}")
            self.active_trade = None
    
    def sync_with_binance(self) -> bool:
        """
        Sync active trade state with Binance account.
        If trade was manually closed, clear the active trade.
        Ignores trades with less than 1 USDT remaining (dust).
        
        Returns:
            True if trade still exists, False if it was closed
        """
        if not self.active_trade:
            return False
        
        try:
            symbol = self.active_trade['symbol']
            
            # Extract base asset from symbol (e.g., BTCUSDT -> BTC)
            base_asset = symbol.replace('USDT', '')
            
            # Get current balance of base asset
            balance = self.client.get_account_balance(base_asset)
            
            # If balance fetch failed, assume trade still exists (don't clear on API error)
            if balance is None:
                logger.warning(f"Failed to fetch {base_asset} balance during sync - assuming trade still exists")
                return True
            
            # Get current price to calculate USDT value
            current_price = self.client.get_current_price(symbol)
            if not current_price:
                logger.warning(f"Could not get current price for {symbol} during sync, skipping USDT check")
                # Fall back to quantity-based check
                current_price = self.active_trade.get('entry_price', 0)
            
            # Calculate USDT value of remaining balance
            usdt_value = balance * current_price
            
            # If USDT value is less than 1, consider it dust and clear the trade
            if usdt_value < 1:
                logger.info(
                    f"Trade {symbol} has less than 1 USDT remaining ({usdt_value:.4f} USDT, balance: {balance}, price: {current_price}). "
                    f"Clearing active trade (likely dust from manual sale)."
                )
                self.active_trade = None
                self.save_trade_state()
                # Also release the trade lock
                return False
            
            # Get expected quantity from active trade
            expected_qty = self.active_trade.get('quantity', 0)
            
            # If balance is significantly less than expected (more than 5% difference),
            # consider the trade closed
            if balance < expected_qty * 0.95:
                logger.warning(
                    f"Trade sync: {symbol} balance ({balance}) is less than expected ({expected_qty}). "
                    f"Trade may have been closed manually."
                )
                
                # Check if balance is essentially zero (trade definitely closed)
                if balance < expected_qty * 0.01:  # Less than 1% of expected
                    logger.info(f"Trade {symbol} appears to have been closed manually. Clearing active trade.")
                    self.active_trade = None
                    self.save_trade_state()
                    return False
                else:
                    # Update quantity to match actual balance
                    logger.info(f"Updating trade quantity from {expected_qty} to {balance}")
                    self.active_trade['quantity'] = balance
                    # Update USDT amount based on new quantity
                    self.active_trade['usdt_amount'] = balance * current_price
                    self.save_trade_state()
                    return True
            else:
                # Trade still active, update quantity if it changed slightly
                if abs(balance - expected_qty) > expected_qty * 0.01:  # More than 1% difference
                    logger.info(f"Updating trade quantity from {expected_qty} to {balance}")
                    self.active_trade['quantity'] = balance
                    # Update USDT amount based on new quantity
                    self.active_trade['usdt_amount'] = balance * current_price
                    self.save_trade_state()
                return True
                
        except Exception as e:
            logger.error(f"Error syncing trade with Binance: {e}")
            # On error, assume trade still exists to be safe
            return True