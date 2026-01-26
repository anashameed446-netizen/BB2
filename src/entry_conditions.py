"""Entry conditions checker for trade signals."""
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class EntryConditions:
    """Validates all entry conditions for trade signals."""
    
    def __init__(self, config_manager):
        self.config = config_manager
    
    def check_all_conditions(
        self,
        symbol: str,
        prev_candle_close: float,
        prev_candle_volume: float,
        current_price: float,
        current_volume: float,
        elapsed_minutes: int,
        is_trade_active: bool,
        is_in_cooldown: bool
    ) -> Dict:
        """
        Check all entry conditions for a symbol.
        
        Returns:
            Dict with 'signal' (bool) and 'reason' (str) keys
        """
        # Check trade restrictions first
        if is_trade_active:
            return {
                'signal': False,
                'status': 'LOCKED',
                'reason': 'Another trade is active (global lock)'
            }
        
        if is_in_cooldown:
            return {
                'signal': False,
                'status': 'COOLDOWN',
                'reason': f'Coin in {self.config["cooldown_minutes"]}-minute cooldown'
            }
        
        # Check time condition (elapsed <= time limit)
        volume_time_limit = self.config['volume_time_limit']
        if elapsed_minutes > volume_time_limit:  # > is correct here (exceeded limit)
            return {
                'signal': False,
                'status': 'TIME OUT',
                'reason': f'Exceeded {volume_time_limit} minute time limit'
            }
        
        # Check volume condition (current_volume >= required_volume)
        volume_multiplier = self.config['volume_multiplier']
        required_volume = prev_candle_volume * volume_multiplier
        
        if current_volume < required_volume:  # < is correct (not reached yet)
            return {
                'signal': False,
                'status': 'WAIT',
                'reason': f'Volume not reached (need {required_volume:.0f}, have {current_volume:.0f})'
            }
        
        # Check price condition (current_price >= required_price)
        price_change_percent = self.config['price_change_percent']
        required_price = prev_candle_close * (1 + price_change_percent / 100)
        
        if current_price < required_price:  # < is correct (not reached yet)
            return {
                'signal': False,
                'status': 'WAIT',
                'reason': f'Price not reached (need {required_price:.2f}, have {current_price:.2f})'
            }
        
        # All conditions met!
        return {
            'signal': True,
            'status': 'SIGNAL',
            'reason': f'All conditions met! Volume: {current_volume:.0f}/{required_volume:.0f}, Price: {current_price:.2f}/{required_price:.2f}'
        }
    
    def calculate_required_metrics(
        self,
        prev_candle_close: float,
        prev_candle_volume: float
    ) -> Dict:
        """Calculate required price and volume thresholds."""
        volume_multiplier = self.config['volume_multiplier']
        price_change_percent = self.config['price_change_percent']
        
        return {
            'required_volume': prev_candle_volume * volume_multiplier,
            'required_price': prev_candle_close * (1 + price_change_percent / 100),
            'volume_time_limit': self.config['volume_time_limit']
        }
