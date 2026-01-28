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
        trailing_active: bool,
        trailing_stop: Optional[float]
    ) -> Dict:
        """
        Exit priority:
        1️⃣ Stop Loss (always active)
        2️⃣ Trailing Stop (only if activated)
        """

        # -------------------------------
        # 1️⃣ HARD STOP LOSS
        if current_price <= stop_loss:
            return {
                "should_exit": True,
                "reason": "STOP LOSS HIT"
            }

        # -------------------------------
        # 2️⃣ TRAILING STOP
        if trailing_active:
            if trailing_stop is None:
                logger.error("Trailing active but trailing_stop is None")
                return {"should_exit": False, "reason": None}

            if current_price <= trailing_stop:
                return {
                    "should_exit": True,
                    "reason": "TRAILING STOP HIT"
                }

        # -------------------------------
        # 3️⃣ HOLD
        return {
            "should_exit": False,
            "reason": None
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
