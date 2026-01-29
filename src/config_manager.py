"""Configuration manager for the trading bot."""
import json
import os
from typing import Dict, Any
from pathlib import Path


class ConfigManager:
    """Manages bot configuration from JSON file."""
    
    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.load()
    
    def load(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)
        
        self._validate()
        return self.config
    
    def save(self, config: Dict[str, Any]) -> None:
        """Save configuration to JSON file."""
        self.config = config
        # Always enforce 1h timeframe (requirement: 1H only)
        self.config['candle_timeframe'] = '1h'
        self._validate()
        
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=4)
    
    def _validate(self) -> None:
        """Validate configuration parameters."""
        # Timeframe is hardcoded to 1h - remove from required keys
        # ---- Time-based exit defaults ----
        self.config.setdefault("time_exit_enabled", False)
        self.config.setdefault("max_trade_duration_minutes", 0)

        required_keys = [
            'api_key', 'api_secret', 'top_gainers_count',
            'volume_multiplier', 'volume_time_limit', 'price_change_percent',
            'stop_loss_percent', 'take_profit_percent', 'trailing_stop_percent',
            'cooldown_minutes'
        ]
        
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"Missing required config key: {key}")
        
        # Hardcode timeframe to 1h (requirement: 1H only)
        self.config['candle_timeframe'] = '1h'
        
        # Validate ranges
        if self.config['volume_multiplier'] < 0.1:
            raise ValueError("volume_multiplier must be >= 0.1")
        
        if self.config['volume_time_limit'] < 1 or self.config['volume_time_limit'] > 60:
            raise ValueError("volume_time_limit must be between 1 and 60 minutes")
        
        if self.config['price_change_percent'] < 0:
            raise ValueError("price_change_percent must be >= 0")
        
        # ---- Time-based exit validation ----
        if self.config["time_exit_enabled"]:
            if not isinstance(self.config["max_trade_duration_minutes"], int):
                raise ValueError("max_trade_duration_minutes must be an integer")

            if self.config["max_trade_duration_minutes"] <= 0:
                raise ValueError("max_trade_duration_minutes must be > 0 when time_exit_enabled")

    
    def __getitem__(self, key: str):
        """Get configuration value by key."""
        # Prevent modification of timeframe
        if key == 'candle_timeframe':
            return '1h'
        return self.config[key]
    
    def get(self, key: str, default=None):
        """Get configuration value by key."""
        return self.config.get(key, default)
    
    def __getitem__(self, key: str):
        """Get configuration value by key."""
        return self.config[key]
