"""State manager for trade locks and cooldowns."""
import time
import json
from typing import Dict, Set
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class StateManager:
    """Manages bot state including trade locks and cooldowns."""
    
    def __init__(self, cooldown_minutes: int = 60, state_file: str = "logs/bot_state.json"):
        self.cooldown_minutes = cooldown_minutes
        self.active_trade = False
        self.active_symbol: str = None
        self.cooldowns: Dict[str, float] = {}  # symbol -> cooldown_end_time
        self.state_file = Path(state_file)
        self.load_state()
    
    def set_trade_active(self, symbol: str) -> None:
        """Set global trade lock."""
        self.active_trade = True
        self.active_symbol = symbol
        logger.info(f"Trade lock activated for {symbol}")
    
    def release_trade_lock(self) -> None:
        """Release global trade lock."""
        self.active_trade = False
        self.active_symbol = None
        logger.info("Trade lock released")
    
    def is_trade_active(self) -> bool:
        """Check if a trade is currently active."""
        return self.active_trade
    
    def get_active_symbol(self) -> str:
        """Get the currently active trade symbol."""
        return self.active_symbol
    
    def add_cooldown(self, symbol: str) -> None:
        """Add a symbol to cooldown."""
        cooldown_end = time.time() + (self.cooldown_minutes * 60)
        self.cooldowns[symbol] = cooldown_end
        logger.info(f"Cooldown applied to {symbol} for {self.cooldown_minutes} minutes")
    
    def is_in_cooldown(self, symbol: str) -> bool:
        """Check if a symbol is in cooldown."""
        if symbol not in self.cooldowns:
            return False
        
        current_time = time.time()
        if current_time >= self.cooldowns[symbol]:
            # Cooldown expired, remove it
            del self.cooldowns[symbol]
            logger.info(f"Cooldown expired for {symbol}")
            return False
        
        return True
    
    def get_cooldown_remaining(self, symbol: str) -> int:
        """Get remaining cooldown time in minutes."""
        if symbol not in self.cooldowns:
            return 0
        
        current_time = time.time()
        remaining_seconds = self.cooldowns[symbol] - current_time
        
        if remaining_seconds <= 0:
            return 0
        
        return int(remaining_seconds // 60) + 1
    
    def update_cooldown_duration(self, cooldown_minutes: int) -> None:
        """Update cooldown duration (doesn't affect existing cooldowns)."""
        self.cooldown_minutes = cooldown_minutes
        logger.info(f"Cooldown duration updated to {cooldown_minutes} minutes")
    
    def clear_all_cooldowns(self) -> None:
        """Clear all cooldowns."""
        self.cooldowns.clear()
        logger.info("All cooldowns cleared")
    
    def get_state_summary(self) -> Dict:
        """Get current state summary."""
        return {
            'trade_active': self.active_trade,
            'active_symbol': self.active_symbol,
            'cooldown_count': len(self.cooldowns),
            'symbols_in_cooldown': list(self.cooldowns.keys())
        }
    
    def save_state(self) -> None:
        """Save state to file for persistence."""
        try:
            # Ensure directory exists
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            
            state = {
                'active_trade': self.active_trade,
                'active_symbol': self.active_symbol,
                'cooldowns': self.cooldowns,
                'cooldown_minutes': self.cooldown_minutes,
                'saved_at': time.time()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            logger.debug(f"State saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def load_state(self) -> None:
        """Load state from file."""
        try:
            if not self.state_file.exists():
                logger.info("No saved state found, starting fresh")
                return
            
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            # Restore state
            self.active_trade = state.get('active_trade', False)
            self.active_symbol = state.get('active_symbol')
            self.cooldowns = {k: float(v) for k, v in state.get('cooldowns', {}).items()}
            
            # Clean expired cooldowns
            current_time = time.time()
            expired_symbols = [
                symbol for symbol, end_time in self.cooldowns.items()
                if current_time >= end_time
            ]
            for symbol in expired_symbols:
                del self.cooldowns[symbol]
            
            if expired_symbols:
                logger.info(f"Cleaned {len(expired_symbols)} expired cooldowns on load")
            
            if self.active_trade:
                logger.info(f"Restored active trade state: {self.active_symbol}")
            if self.cooldowns:
                logger.info(f"Restored {len(self.cooldowns)} active cooldowns")
            
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            # Start fresh on error
            self.active_trade = False
            self.active_symbol = None
            self.cooldowns = {}
    
    def set_trade_active(self, symbol: str) -> None:
        """Set global trade lock."""
        self.active_trade = True
        self.active_symbol = symbol
        self.save_state()  # Persist state
        logger.info(f"Trade lock activated for {symbol}")
    
    def release_trade_lock(self) -> None:
        """Release global trade lock."""
        self.active_trade = False
        self.active_symbol = None
        self.save_state()  # Persist state
        logger.info("Trade lock released")
    
    def add_cooldown(self, symbol: str) -> None:
        """Add a symbol to cooldown."""
        cooldown_end = time.time() + (self.cooldown_minutes * 60)
        self.cooldowns[symbol] = cooldown_end
        self.save_state()  # Persist state
        logger.info(f"Cooldown applied to {symbol} for {self.cooldown_minutes} minutes")