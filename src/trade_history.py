"""Trade history logger and storage."""
import json
import logging
from typing import Dict, List
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class TradeHistory:
    """Manages trade history logging and retrieval."""
    
    def __init__(self, history_file: str = "logs/trade_history.json"):
        self.history_file = Path(history_file)
        self.history: List[Dict] = []
        self.load()
    
    def load(self) -> None:
        """Load trade history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
                logger.info(f"Loaded {len(self.history)} trades from history")
            except Exception as e:
                logger.error(f"Error loading trade history: {e}")
                self.history = []
        else:
            self.history = []
    
    def save(self) -> None:
        """Save trade history to file."""
        try:
            # Ensure directory exists
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
            
            logger.debug(f"Trade history saved: {len(self.history)} trades to {self.history_file}")
        except Exception as e:
            logger.error(f"Error saving trade history: {e}", exc_info=True)
    
    def add_trade(self, trade_details: Dict) -> None:
        """Add a completed trade to history."""
        trade_record = {
            'symbol': trade_details['symbol'],
            'entry_price': trade_details['entry_price'],
            'entry_time': trade_details.get('entry_time', datetime.now().isoformat()),
            'exit_price': trade_details['exit_price'],
            'exit_time': trade_details['exit_time'],
            'pnl_percent': trade_details['pnl_percent'],
            'exit_reason': trade_details['exit_reason'],
            'usdt_amount': trade_details.get('usdt_amount', 0),  # USDT capital used
            'exit_usdt_amount': trade_details.get('exit_usdt_amount', 0)  # USDT received on exit
        }
        
        self.history.append(trade_record)
        self.save()
        
        logger.info(f"Trade added to history: {trade_record['symbol']} - PnL: {trade_record['pnl_percent']:.2f}%")
    
    def get_all_trades(self) -> List[Dict]:
        """Get all trades from history."""
        return self.history
    
    def get_recent_trades(self, count: int = 10) -> List[Dict]:
        """Get recent trades."""
        return self.history[-count:] if len(self.history) > count else self.history
    
    def get_statistics(self) -> Dict:
        """Calculate trading statistics."""
        if not self.history:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'average_pnl': 0.0,
                'total_pnl': 0.0
            }
        
        winning_trades = [t for t in self.history if t['pnl_percent'] > 0]
        losing_trades = [t for t in self.history if t['pnl_percent'] <= 0]
        
        total_pnl = sum(t['pnl_percent'] for t in self.history)
        avg_pnl = total_pnl / len(self.history)
        
        return {
            'total_trades': len(self.history),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': (len(winning_trades) / len(self.history)) * 100,
            'average_pnl': avg_pnl,
            'total_pnl': total_pnl
        }
    
    def clear_history(self) -> None:
        """Clear all trade history."""
        self.history = []
        self.save()
        logger.info("Trade history cleared")
