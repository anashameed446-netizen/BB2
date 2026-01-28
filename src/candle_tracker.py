"""
Candle tracker for monitoring 1H candles (FINAL, STABLE).
"""
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CandleData:
    def __init__(self, open_time_ms: int, close_price: float, volume: float):
        self.open_time_ms = open_time_ms
        self.close_price = close_price
        self.volume = volume


class CandleTracker:
    """
    Guarantees:
    - Previous candle fetched ONCE per hour
    - Current candle tracked live
    - Elapsed minutes always 0–60
    """

    def __init__(self, binance_client):
        self.client = binance_client

        self.previous_candles: Dict[str, CandleData] = {}
        self.current_candles: Dict[str, Dict] = {}
        self._prev_candle_hour: Dict[str, int] = {}


        self._last_fetch_ts = {}
        self._fetch_ttl = 10  # seconds (safe, fast enough)

    # ------------------------------------------------------------------

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _current_hour_start_ms(self) -> int:
        now = self._utc_now()
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        return int(hour_start.timestamp() * 1000)

    # ------------------------------------------------------------------

    def update_candles(self, symbol: str) -> bool:
        now = time.time()
        if now - self._last_fetch_ts.get(symbol, 0) < self._fetch_ttl:
            return True

        try:
            klines = self.client.get_klines(symbol=symbol, interval="1h", limit=2)
            if not klines or len(klines) < 2:
                return False

            prev, curr = klines[-2], klines[-1]

            # ---- CURRENT HOUR START (UTC) ----
            hour_start_ms = int(
                datetime.utcnow()
                .replace(minute=0, second=0, microsecond=0)
                .timestamp() * 1000
            )

            # ---- PREVIOUS CANDLE (PER SYMBOL, ONCE PER HOUR) ----
            last_hour = self._prev_candle_hour.get(symbol)

            if last_hour != hour_start_ms:
                self.previous_candles[symbol] = CandleData(
                    open_time_ms=int(prev[0]),
                    close_price=float(prev[4]),
                    volume=float(prev[5])
                )
                self._prev_candle_hour[symbol] = hour_start_ms
                logger.info(f"[{symbol}] 🔒 Previous candle locked")

            # ---- CURRENT CANDLE ----
            elapsed = self._elapsed_minutes(int(curr[0]))

            self.current_candles[symbol] = {
                "open_time": int(curr[0]),
                "price": float(curr[4]),
                "volume": float(curr[5]),
                "elapsed_minutes": elapsed
            }

            self._last_fetch_ts[symbol] = now
            return True

        except Exception as e:
            logger.error(f"Candle update failed for {symbol}: {e}")
            return False


    # ------------------------------------------------------------------

    def _elapsed_minutes(self, open_time_ms: int) -> int:
        now = datetime.utcnow()
        open_time = datetime.utcfromtimestamp(open_time_ms / 1000)

        elapsed = int((now - open_time).total_seconds() / 60)

        if elapsed < 0:
            return 0
        if elapsed >= 60:
            return 60  # used only for TIME OUT logic, NOT persistence

        return elapsed


    # ------------------------------------------------------------------

    def get_previous_candle(self, symbol: str) -> Optional[CandleData]:
        return self.previous_candles.get(symbol)

    def get_current_candle(self, symbol: str) -> Optional[Dict]:
        return self.current_candles.get(symbol)
