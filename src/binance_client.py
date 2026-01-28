"""Binance API client wrapper with WebSocket support."""
import asyncio
import time
from decimal import Decimal
from typing import Dict, List, Optional, Callable
from binance.client import Client
from binance.exceptions import BinanceAPIException
from binance import ThreadedWebsocketManager
import logging

logger = logging.getLogger(__name__)

# Binance API error codes
RATE_LIMIT_ERROR_CODES = [-1015, -1003]  # Rate limit exceeded, too many requests
AUTH_ERROR_CODES = [-2015, -2014, -1022]  # Invalid API key/signature errors
IP_BAN_ERROR_CODE = -1003  # IP banned for excessive requests


class BinanceClient:
    """Wrapper for Binance API with WebSocket support."""
    
    # Rate limit settings
    RATE_LIMIT_WAIT_SECONDS = 30  # Wait time when rate limited
    DEFAULT_RETRY_WAIT = 0.5  # Base wait time for retries (exponential backoff)
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.client: Optional[Client] = None
        self.ws_manager = None  # Optional[ThreadedWebsocketManager] - may not be available
        self.connected = False
        self._last_request_time = 0
        self._price_cache = {}  # symbol -> (price, timestamp)
        self._price_cache_ttl = 2  # seconds
        self._min_request_interval = 0.1  # Minimum 100ms between requests to avoid rate limits
    
    def _wait_for_rate_limit(self) -> None:
        """Ensure minimum interval between API requests to avoid rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()
    
    def _handle_rate_limit_error(self, error_code: int, attempt: int, max_retries: int) -> bool:
        """
        Handle rate limit errors with appropriate waiting.
        
        Returns:
            True if should retry, False if should give up
        """
        if error_code in RATE_LIMIT_ERROR_CODES:
            if attempt < max_retries:
                wait_time = self.RATE_LIMIT_WAIT_SECONDS
                logger.warning(
                    f"Rate limit hit (code {error_code}). Waiting {wait_time}s before retry "
                    f"(attempt {attempt}/{max_retries})"
                )
                time.sleep(wait_time)
                return True
            else:
                logger.error(f"Rate limit exceeded and max retries reached. Try again later.")
                return False
        return True  # Not a rate limit error, continue with normal retry logic
    
    def _get_retry_wait_time(self, attempt: int, error_code: Optional[int] = None) -> float:
        """Calculate wait time for retry based on attempt number and error type."""
        if error_code in RATE_LIMIT_ERROR_CODES:
            return self.RATE_LIMIT_WAIT_SECONDS
        # Exponential backoff: 0.5s, 1s, 1.5s, 2s, etc.
        return self.DEFAULT_RETRY_WAIT * attempt
    
    def connect(self) -> None:
        """Initialize Binance client connection."""
        try:
            self.client = Client(self.api_key, self.api_secret)
            # Test connection
            self.client.ping()
            self.connected = True
            logger.info("Successfully connected to Binance API")
        except BinanceAPIException as e:
            logger.error(f"Failed to connect to Binance: {e}")
            raise
    
    def get_top_gainers(self, count: int = 35, retries: int = 2) -> List[Dict]:
        """Get top gainers from Binance USDT pairs with rate limit handling."""
        for attempt in range(1, retries + 1):
            try:
                self._wait_for_rate_limit()
                tickers = self.client.get_ticker()
                
                # Filter USDT pairs only
                usdt_pairs = [
                    ticker for ticker in tickers 
                    if ticker['symbol'].endswith('USDT') and 
                    not any(x in ticker['symbol'] for x in ['DOWN', 'UP', 'BEAR', 'BULL'])
                ]
                
                # Sort by price change percentage
                sorted_pairs = sorted(
                    usdt_pairs,
                    key=lambda x: float(x['priceChangePercent']),
                    reverse=True
                )
                
                return sorted_pairs[:count]
            
            except BinanceAPIException as e:
                error_code = getattr(e, 'code', None)
                
                # Handle rate limiting
                if error_code in RATE_LIMIT_ERROR_CODES:
                    if attempt < retries:
                        logger.warning(f"Rate limit hit fetching top gainers. Waiting {self.RATE_LIMIT_WAIT_SECONDS}s...")
                        time.sleep(self.RATE_LIMIT_WAIT_SECONDS)
                        continue
                    logger.error(f"Rate limit exceeded fetching top gainers")
                    return []
                
                logger.error(f"Error fetching top gainers: {e}")
                return []
            except Exception as e:
                logger.error(f"Unexpected error fetching top gainers: {type(e).__name__}: {e}")
                return []
        return []
    
    def get_klines(self, symbol: str, interval: str, limit: int = 2, retries: int = 2) -> List[List]:
        """Get candlestick data for a symbol with rate limit handling."""
        for attempt in range(1, retries + 1):
            try:
                self._wait_for_rate_limit()
                klines = self.client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=limit
                )
                return klines
            except BinanceAPIException as e:
                error_code = getattr(e, 'code', None)
                
                # Handle rate limiting
                if error_code in RATE_LIMIT_ERROR_CODES:
                    if attempt < retries:
                        logger.warning(f"Rate limit hit fetching klines for {symbol}. Waiting {self.RATE_LIMIT_WAIT_SECONDS}s...")
                        time.sleep(self.RATE_LIMIT_WAIT_SECONDS)
                        continue
                    logger.error(f"Rate limit exceeded fetching klines for {symbol}")
                    return []
                
                logger.error(f"Error fetching klines for {symbol}: {e}")
                return []
            except Exception as e:
                logger.error(f"Unexpected error fetching klines for {symbol}: {type(e).__name__}: {e}")
                return []
        return []
    
    # def get_current_price(self, symbol: str, retries: int = 2) -> Optional[float]:
    #     """Get current price for a symbol with rate limit handling."""
    #     for attempt in range(1, retries + 1):
    #         try:
    #             self._wait_for_rate_limit()
    #             ticker = self.client.get_symbol_ticker(symbol=symbol)
    #             return float(ticker['price'])
    #         except BinanceAPIException as e:
    #             error_code = getattr(e, 'code', None)
                
    #             # Handle rate limiting
    #             if error_code in RATE_LIMIT_ERROR_CODES:
    #                 if attempt < retries:
    #                     logger.warning(f"Rate limit hit fetching price for {symbol}. Waiting {self.RATE_LIMIT_WAIT_SECONDS}s...")
    #                     time.sleep(self.RATE_LIMIT_WAIT_SECONDS)
    #                     continue
    #                 logger.error(f"Rate limit exceeded fetching price for {symbol}")
    #                 return None
                
    #             logger.error(f"Error fetching price for {symbol}: {e}")
    #             return None
    #         except Exception as e:
    #             logger.error(f"Unexpected error fetching price for {symbol}: {type(e).__name__}: {e}")
    #             return None
    #     return None
    
    
    def get_current_price(self, symbol: str, retries: int = 2) -> Optional[float]:
        """Get current price with short-term cache (low latency)."""
        now = time.time()

        # Serve from cache if fresh
        cached = self._price_cache.get(symbol)
        if cached and (now - cached[1]) < self._price_cache_ttl:
            return cached[0]

        for attempt in range(1, retries + 1):
            try:
                self._wait_for_rate_limit()
                ticker = self.client.get_symbol_ticker(symbol=symbol)
                price = float(ticker['price'])

                # Update cache
                self._price_cache[symbol] = (price, now)
                return price

            except Exception:
                if attempt >= retries:
                    return cached[0] if cached else None
                
    def get_fast_prices(self) -> dict:
        now = time.time()
        if hasattr(self, "_fast_price_cache"):
            prices, ts = self._fast_price_cache
            if now - ts < 1:
                return prices

        tickers = self.client.get_ticker()
        prices = {t['symbol']: float(t['lastPrice']) for t in tickers}
        self._fast_price_cache = (prices, now)
        return prices

    def get_fast_volumes(self) -> dict:
        """
        Returns live base-asset volume deltas for symbols.
        Uses 24h ticker as a fast approximation.
        """
        try:
            tickers = self.client.get_ticker()
            volumes = {}

            for t in tickers:
                symbol = t.get("symbol")
                if not symbol or not symbol.endswith("USDT"):
                    continue

                # base asset volume (NOT quote volume)
                volumes[symbol] = float(t.get("volume", 0))

            return volumes

        except Exception as e:
            logger.error(f"Fast volume fetch failed: {e}")
            return {}


    def get_all_prices(self) -> Dict[str, float]:
        """Fetch all symbol prices in ONE call."""
        self._wait_for_rate_limit()
        tickers = self.client.get_ticker()

        now = time.time()
        prices = {}

        for t in tickers:
            try:
                price = float(t['lastPrice'])
                symbol = t['symbol']
                prices[symbol] = price
                self._price_cache[symbol] = (price, now)
            except:
                continue

        return prices


    
    def get_24h_volume(self, symbol: str) -> Optional[float]:
        """Get 24h volume for a symbol."""
        try:
            ticker = self.client.get_ticker(symbol=symbol)
            return float(ticker['volume'])
        except BinanceAPIException as e:
            logger.error(f"Error fetching volume for {symbol}: {e}")
            return None
    
    def get_account_balance(self, asset: str = 'USDT', retries: int = 3) -> Optional[float]:
        """
        Get account balance for an asset with retry logic and rate limit handling.
        
        Returns:
            float: The available balance, or None if all retries failed
        """
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                # Wait to avoid rate limiting
                self._wait_for_rate_limit()
                
                balance = self.client.get_asset_balance(asset=asset)
                if balance is None:
                    logger.warning(f"Balance response is None for {asset} (attempt {attempt}/{retries})")
                    last_error = f"Balance response is None for {asset}"
                    if attempt < retries:
                        time.sleep(self._get_retry_wait_time(attempt))
                        continue
                    return None
                return float(balance['free'])
            except BinanceAPIException as e:
                error_code = getattr(e, 'code', None)
                error_msg = getattr(e, 'message', str(e))
                
                # Check for rate limit errors
                if error_code in RATE_LIMIT_ERROR_CODES:
                    logger.warning(
                        f"Rate limit hit fetching {asset} balance (attempt {attempt}/{retries}): "
                        f"code={error_code}. Waiting {self.RATE_LIMIT_WAIT_SECONDS}s..."
                    )
                    last_error = f"Rate limit exceeded (code {error_code})"
                    if attempt < retries:
                        time.sleep(self.RATE_LIMIT_WAIT_SECONDS)
                        continue
                    return None
                
                # Don't retry on authentication errors
                if error_code in AUTH_ERROR_CODES:
                    logger.error(f"Authentication error - not retrying: {error_msg}")
                    return None
                
                logger.warning(
                    f"Binance API error fetching {asset} balance (attempt {attempt}/{retries}): "
                    f"code={error_code}, message={error_msg}"
                )
                last_error = f"Binance API error: {error_msg}"
                
                if attempt < retries:
                    time.sleep(self._get_retry_wait_time(attempt, error_code))
            except Exception as e:
                logger.warning(
                    f"Unexpected error fetching {asset} balance (attempt {attempt}/{retries}): "
                    f"{type(e).__name__}: {e}"
                )
                last_error = f"{type(e).__name__}: {e}"
                if attempt < retries:
                    time.sleep(self._get_retry_wait_time(attempt))
        
        logger.error(f"Failed to fetch {asset} balance after {retries} attempts. Last error: {last_error}")
        return None
    
    def place_market_buy(self, symbol: str, quantity: Optional[float] = None, 
                         quote_amount: Optional[float] = None, retries: int = 2) -> Optional[Dict]:
        """
        Place a market buy order with rate limit handling.
        Either quantity (in base asset) or quote_amount (in USDT) must be provided.
        """
        for attempt in range(1, retries + 1):
            try:
                self._wait_for_rate_limit()
                
                if quote_amount:
                    # Buy using quote asset (USDT)
                    order = self.client.order_market_buy(
                        symbol=symbol,
                        quoteOrderQty=quote_amount
                    )
                else:
                    # Buy using base asset quantity
                    order = self.client.order_market_buy(
                        symbol=symbol,
                        quantity=quantity
                    )
                
                logger.info(f"Market buy order placed: {order}")
                return order
            
            except BinanceAPIException as e:
                error_code = getattr(e, 'code', None)
                error_msg = getattr(e, 'message', str(e))
                
                # Handle rate limiting
                if error_code in RATE_LIMIT_ERROR_CODES:
                    if attempt < retries:
                        logger.warning(f"Rate limit hit placing buy order for {symbol}. Waiting {self.RATE_LIMIT_WAIT_SECONDS}s...")
                        time.sleep(self.RATE_LIMIT_WAIT_SECONDS)
                        continue
                    logger.error(f"Rate limit exceeded placing buy order for {symbol}")
                    return None
                
                logger.error(f"Binance API error placing buy order for {symbol}: {e}")
                logger.error(f"Error code: {error_code}, Message: {error_msg}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error placing buy order for {symbol}: {type(e).__name__}: {e}")
                return None
        return None
    
    def place_market_sell(self, symbol: str, quantity: float, retries: int = 2) -> Optional[Dict]:
        """Place a market sell order with rate limit handling."""
        for attempt in range(1, retries + 1):
            try:
                self._wait_for_rate_limit()
                
                order = self.client.order_market_sell(
                    symbol=symbol,
                    quantity=quantity
                )
                logger.info(f"Market sell order placed: {order}")
                return order
            
            except BinanceAPIException as e:
                error_code = getattr(e, 'code', None)
                error_msg = getattr(e, 'message', str(e))
                
                # Handle rate limiting
                if error_code in RATE_LIMIT_ERROR_CODES:
                    if attempt < retries:
                        logger.warning(f"Rate limit hit placing sell order for {symbol}. Waiting {self.RATE_LIMIT_WAIT_SECONDS}s...")
                        time.sleep(self.RATE_LIMIT_WAIT_SECONDS)
                        continue
                    logger.error(f"Rate limit exceeded placing sell order for {symbol}")
                    return None
                
                logger.error(f"Binance API error placing sell order for {symbol}: {e}")
                logger.error(f"Error code: {error_code}, Message: {error_msg}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error placing sell order for {symbol}: {type(e).__name__}: {e}")
                return None
        return None
    
    def get_open_orders(self, symbol: str) -> List[Dict]:
        """Get all open orders for a symbol."""
        try:
            orders = self.client.get_open_orders(symbol=symbol)
            return orders
        except BinanceAPIException as e:
            logger.error(f"Error fetching open orders for {symbol}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching open orders for {symbol}: {type(e).__name__}: {e}")
            return []
    
    def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open orders for a symbol."""
        try:
            result = self.client.cancel_open_orders(symbol=symbol)
            logger.info(f"Cancelled all open orders for {symbol}: {result}")
            return True
        except BinanceAPIException as e:
            # If no open orders exist, Binance returns an error - this is OK
            if hasattr(e, 'code') and e.code == -2011:  # Unknown order sent
                logger.info(f"No open orders to cancel for {symbol}")
                return True
            logger.error(f"Error cancelling orders for {symbol}: {e}")
            logger.error(f"Error code: {e.code if hasattr(e, 'code') else 'N/A'}, Message: {e.message if hasattr(e, 'message') else str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error cancelling orders for {symbol}: {type(e).__name__}: {e}")
            return False
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get symbol trading info (filters, precision, etc.)."""
        try:
            info = self.client.get_symbol_info(symbol=symbol)
            return info
        except BinanceAPIException as e:
            logger.error(f"Error fetching symbol info for {symbol}: {e}")
            return None
    
    def start_websocket(self, callback: Callable) -> None:
        """Start WebSocket manager for real-time data."""
        if ThreadedWebsocketManager is None:
            logger.warning("WebSocket functionality not available in this python-binance version")
            return
        self.ws_manager = ThreadedWebsocketManager(
            api_key=self.api_key,
            api_secret=self.api_secret
        )
        self.ws_manager.start()
        logger.info("WebSocket manager started")
    
    def subscribe_ticker(self, symbol: str, callback: Callable) -> None:
        """Subscribe to ticker updates for a symbol."""
        if self.ws_manager:
            self.ws_manager.start_symbol_ticker_socket(
                callback=callback,
                symbol=symbol.lower()
            )
    
    def stop_websocket(self) -> None:
        """Stop WebSocket manager."""
        if self.ws_manager:
            self.ws_manager.stop()
            logger.info("WebSocket manager stopped")
    
    def disconnect(self) -> None:
        """Disconnect from Binance."""
        self.stop_websocket()
        self.connected = False
        logger.info("Disconnected from Binance")
