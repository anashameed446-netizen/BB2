"""Risk manager for stop loss, take profit, and trailing stop."""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RiskManager:
    """Manages stop loss, take profit, and trailing stop logic."""
    
    def __init__(self, config_manager):
        self.config = config_manager
    
    def calculate_stop_loss(self, entry_price: float) -> float:
        """Calculate initial stop loss price."""
        sl_percent = self.config['stop_loss_percent']
        stop_loss = entry_price * (1 - sl_percent / 100)
        return stop_loss
    
    def calculate_take_profit_trigger(self, entry_price: float) -> float:
        """Calculate take profit trigger price."""
        tp_percent = self.config['take_profit_percent']
        tp_trigger = entry_price * (1 + tp_percent / 100)
        return tp_trigger
    
    def calculate_trailing_stop(self, highest_price: float) -> float:
        """Calculate trailing stop loss price."""
        trailing_percent = self.config['trailing_stop_percent']
        trailing_stop = highest_price * (1 - trailing_percent / 100)
        return trailing_stop
    
    def check_exit_conditions(
        self,
        entry_price: float,
        current_price: float,
        stop_loss: float,
        tp_trigger: float,
        trailing_active: bool,
        highest_price: float
    ) -> Dict:
        """
        Check if exit conditions are met.
        
        Returns:
            Dict with 'should_exit' (bool), 'reason' (str), and 'new_trailing_active' (bool)
        """
        # Check stop loss hit
        if current_price <= stop_loss:
            return {
                'should_exit': True,
                'reason': 'Stop loss hit',
                'new_trailing_active': trailing_active
            }
        
        # Check if TP trigger reached (activate trailing)
        if not trailing_active and current_price >= tp_trigger:
            logger.info(f"Take profit trigger reached at {current_price}, activating trailing stop")
            return {
                'should_exit': False,
                'reason': 'TP reached - trailing activated',
                'new_trailing_active': True
            }
        
        # If trailing is active, check trailing stop
        if trailing_active:
            trailing_stop = self.calculate_trailing_stop(highest_price)
            
            # Check if current price is at or below trailing stop
            if current_price <= trailing_stop:
                logger.info(f"Trailing stop hit: current_price={current_price:.8f} <= trailing_stop={trailing_stop:.8f}")
                return {
                    'should_exit': True,
                    'reason': f'Trailing stop hit at {trailing_stop:.8f}',
                    'new_trailing_active': trailing_active
                }
        
        return {
            'should_exit': False,
            'reason': 'Conditions not met',
            'new_trailing_active': trailing_active
        }
    
    def calculate_pnl_percent(self, entry_price: float, current_price: float) -> float:
        """Calculate PnL percentage."""
        pnl = ((current_price - entry_price) / entry_price) * 100
        return pnl
    
    def update_highest_price(
        self,
        current_highest: float,
        current_price: float
    ) -> float:
        """Update and return highest price."""
        return max(current_highest, current_price)
