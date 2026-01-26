"""Market scanner for finding top gainers."""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class MarketScanner:
    """Scans and monitors top gainers on Binance."""
    
    def __init__(self, binance_client):
        self.client = binance_client
        self.top_gainers: List[Dict] = []
    
    def scan_top_gainers(self, count: int = 35) -> List[str]:
        """
        Scan and return top gainer symbols.
        
        Returns:
            List of top gainer symbols (e.g., ['BTCUSDT', 'ETHUSDT', ...])
        """
        try:
            self.top_gainers = self.client.get_top_gainers(count=count)
            symbols = [gainer['symbol'] for gainer in self.top_gainers]
            
            logger.info(f"Scanned {len(symbols)} top gainers")
            return symbols
        
        except Exception as e:
            logger.error(f"Error scanning top gainers: {e}")
            return []
    
    def get_gainer_info(self, symbol: str) -> Dict:
        """Get detailed info for a specific gainer."""
        for gainer in self.top_gainers:
            if gainer['symbol'] == symbol:
                return {
                    'symbol': symbol,
                    'price': float(gainer['lastPrice']),
                    'price_change_percent': float(gainer['priceChangePercent']),
                    'volume': float(gainer['volume']),
                    'quote_volume': float(gainer['quoteVolume'])
                }
        return {}
    
    def get_all_gainers_info(self) -> List[Dict]:
        """Get info for all tracked gainers."""
        return [
            {
                'symbol': gainer['symbol'],
                'price': float(gainer['lastPrice']),
                'price_change_percent': float(gainer['priceChangePercent']),
                'volume': float(gainer['volume']),
                'quote_volume': float(gainer['quoteVolume'])
            }
            for gainer in self.top_gainers
        ]
