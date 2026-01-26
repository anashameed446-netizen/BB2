"""Candle tracker for monitoring 1H candles."""
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class CandleData:
    """Represents candle data."""
    def __init__(self, open_time: int, close_price: float, volume: float):
        self.open_time = open_time
        self.close_price = close_price
        self.volume = volume


class CandleTracker:
    """Tracks previous and current 1H candles for each symbol."""
    
    def __init__(self, binance_client):
        self.client = binance_client
        self.previous_candles: Dict[str, CandleData] = {}
        self.current_candles: Dict[str, Dict] = {}
        self.candle_start_times: Dict[str, int] = {}
        self.previous_candle_fetched_hour: Dict[str, int] = {}  # Track when previous candle was fetched
    
    def _get_current_hour(self) -> int:
        """Get current hour (0-23) for tracking when to fetch previous candle."""
        return datetime.now().hour
    
    def _should_fetch_previous_candle(self, symbol: str) -> bool:
        """
        Check if we should fetch previous candle (once per hour at hour start).
        Returns True if:
        1. Previous candle not fetched yet for this symbol, OR
        2. New hour has started (previous candle was fetched in different hour)
        """
        current_hour = self._get_current_hour()
        
        if symbol not in self.previous_candle_fetched_hour:
            return True
        
        # Fetch once per hour - if we're in a new hour, fetch again
        if self.previous_candle_fetched_hour[symbol] != current_hour:
            return True
        
        return False
    
    def update_candles(self, symbol: str, interval: str = "1h") -> bool:
        """
        Update previous and current candle data for a symbol.
        Previous candle is fetched once at the start of each hour.
        Current candle is updated continuously.
        Returns True if successful, False otherwise.
        """
        try:
            # Always fetch current candle data
            klines = self.client.get_klines(symbol=symbol, interval=interval, limit=2)
            
            if not klines or len(klines) < 2:
                logger.warning(f"Insufficient kline data for {symbol}")
                return False
            
            # Fetch previous closed candle ONCE at the start of each hour
            if self._should_fetch_previous_candle(symbol):
                # Previous closed candle (index -2, as -1 is current forming)
                prev_candle = klines[-2]
                prev_close_price = float(prev_candle[4])  # Close price
                prev_volume = float(prev_candle[5])  # Volume
                prev_open_time = int(prev_candle[0])  # Open time
                
                # Store previous candle
                self.previous_candles[symbol] = CandleData(
                    open_time=prev_open_time,
                    close_price=prev_close_price,
                    volume=prev_volume
                )
                
                # Mark that we've fetched previous candle for this hour
                self.previous_candle_fetched_hour[symbol] = self._get_current_hour()
                logger.info(f"Previous candle fetched for {symbol} at hour {self._get_current_hour()}: "
                          f"Close={prev_close_price:.8f}, Volume={prev_volume:.2f}")
            
            # Current forming candle - update continuously
            current_candle = klines[-1]
            current_open_time = int(current_candle[0])
            current_volume = float(current_candle[5])
            current_price = float(current_candle[4])  # Current close (real-time)
            
            # Check if new candle period started
            if symbol not in self.candle_start_times or \
               self.candle_start_times[symbol] != current_open_time:
                self.candle_start_times[symbol] = current_open_time
                # Reset previous candle fetch flag when new candle starts
                if symbol in self.previous_candle_fetched_hour:
                    del self.previous_candle_fetched_hour[symbol]
                logger.info(f"New candle started for {symbol} at {current_open_time}")
            
            # Calculate elapsed minutes with validation
            elapsed_minutes = self._get_elapsed_minutes(current_open_time)
            
            # Only update if elapsed time is valid
            if elapsed_minutes is not None:
                # Update current candle data continuously
                self.current_candles[symbol] = {
                    'open_time': current_open_time,
                    'volume': current_volume,
                    'price': current_price,
                    'elapsed_minutes': elapsed_minutes
                }
            else:
                # Log warning but don't update with invalid data
                logger.warning(f"Skipping update for {symbol} - invalid elapsed time calculation")
            
            return True
        
        except Exception as e:
            logger.error(f"Error updating candles for {symbol}: {e}")
            return False
    
    def _get_elapsed_minutes(self, candle_open_time: int) -> Optional[int]:
        """
        Calculate elapsed minutes since candle opened.
        Returns None if the calculation is invalid (negative or > 60 minutes).
        """
        try:
            current_time_ms = int(time.time() * 1000)
            elapsed_ms = current_time_ms - candle_open_time
            
            # Validate: elapsed time should be positive and reasonable
            if elapsed_ms < 0:
                logger.warning(f"Negative elapsed time detected: {elapsed_ms}ms (candle_open_time may be in future)")
                return None
            
            elapsed_minutes = elapsed_ms // (60 * 1000)
            
            # For 1-hour candles, elapsed time should be 0-60 minutes
            # If it's more than 60, the candle data is likely stale or incorrect
            if elapsed_minutes > 60:
                logger.warning(f"Elapsed time exceeds 60 minutes: {elapsed_minutes}m (candle data may be stale)")
                return None
            
            return int(elapsed_minutes)
        except Exception as e:
            logger.error(f"Error calculating elapsed minutes: {e}")
            return None
    
    def get_previous_candle(self, symbol: str) -> Optional[CandleData]:
        """Get previous closed candle data."""
        return self.previous_candles.get(symbol)
    
    def get_current_candle(self, symbol: str) -> Optional[Dict]:
        """Get current forming candle data."""
        return self.current_candles.get(symbol)
    
    def update_current_price_volume(self, symbol: str) -> None:
        """Update current candle with real-time price and volume."""
        try:
            # Get current price
            current_price = self.client.get_current_price(symbol)
            
            # Get current candle data (includes volume)
            klines = self.client.get_klines(symbol=symbol, interval="1h", limit=1)
            if klines:
                current_candle = klines[0]
                current_volume = float(current_candle[5])
                current_open_time = int(current_candle[0])
                
                if symbol in self.current_candles:
                    elapsed_minutes = self._get_elapsed_minutes(current_open_time)
                    # Only update if elapsed time is valid
                    if elapsed_minutes is not None:
                        self.current_candles[symbol]['price'] = current_price
                        self.current_candles[symbol]['volume'] = current_volume
                        self.current_candles[symbol]['elapsed_minutes'] = elapsed_minutes
                    else:
                        logger.warning(f"Skipping elapsed time update for {symbol} - invalid calculation")
        
        except Exception as e:
            logger.error(f"Error updating current price/volume for {symbol}: {e}")
    
    def is_new_candle_period(self, symbol: str) -> bool:
        """Check if we've entered a new candle period."""
        try:
            klines = self.client.get_klines(symbol=symbol, interval="1h", limit=1)
            if klines:
                current_open_time = int(klines[0][0])
                if symbol in self.candle_start_times:
                    return current_open_time != self.candle_start_times[symbol]
            return False
        except Exception as e:
            logger.error(f"Error checking new candle period for {symbol}: {e}")
            return False
