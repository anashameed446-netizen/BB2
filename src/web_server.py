"""FastAPI web server for the trading bot."""
import asyncio
import json
import logging
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

from config_manager import ConfigManager

logger = logging.getLogger(__name__)

app = FastAPI(title="Binance Trading Bot")

# Global state
config_manager = ConfigManager()
websocket_clients: Set[WebSocket] = set()
bot_instance = None  # Will be set by main.py


# Mount static files
web_dir = Path(__file__).parent.parent / "web"
app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.get("/")
async def read_root():
    """Serve the main HTML page."""
    return FileResponse(str(web_dir / "index.html"))


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    config = config_manager.config.copy()
    return JSONResponse(config)


@app.post("/api/config")
async def update_config(config: dict):
    """Update configuration."""
    try:
        config_manager.save(config)
        
        # Update bot if running
        if bot_instance and bot_instance.running:
            bot_instance.reload_config()
        
        await broadcast_message({
            'type': 'log',
            'message': 'Configuration updated successfully',
            'level': 'info'
        })
        
        return {"status": "success", "message": "Configuration updated"}
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=400
        )


@app.post("/api/bot/start")
async def start_bot():
    """Start the trading bot."""
    try:
        if bot_instance:
            await bot_instance.start()
            await broadcast_message({
                'type': 'bot_status',
                'running': True
            })
            return {"status": "success", "message": "Bot started"}
        else:
            return JSONResponse(
                {"status": "error", "message": "Bot instance not initialized"},
                status_code=500
            )
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


@app.post("/api/bot/stop")
async def stop_bot():
    """Stop the trading bot."""
    try:
        if bot_instance:
            await bot_instance.stop()
            await broadcast_message({
                'type': 'bot_status',
                'running': False
            })
            return {"status": "success", "message": "Bot stopped"}
        else:
            return JSONResponse(
                {"status": "error", "message": "Bot instance not initialized"},
                status_code=500
            )
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


@app.get("/api/bot/state")
async def get_bot_state():
    """Get current bot state for page restoration."""
    try:
        if not bot_instance:
            return JSONResponse({
                "running": False,
                "active_trade": None,
                "markets": [],
                "history": [],
                "monitored_symbols_count": 0,
                "total_scanned": 0
            })
        
        # Get active trade and filter out trades with less than 1 USDT
        active_trade = bot_instance.trade_manager.get_active_trade() if bot_instance.trade_manager else None
        
        # Check if trade has valid USDT amount (>= 1 USDT)
        if active_trade and bot_instance.trade_manager:
            # Force sync to get actual balance from Binance
            if not bot_instance.trade_manager.sync_with_binance():
                # Trade was cleared by sync (less than 1 USDT)
                active_trade = None
                if bot_instance.state_manager:
                    bot_instance.state_manager.release_trade_lock()
            else:
                # Trade still valid, update usdt_amount for display
                symbol = active_trade['symbol']
                current_price = bot_instance.binance_client.get_current_price(symbol) if bot_instance.binance_client else None
                quantity = active_trade.get('quantity', 0)
                
                if current_price and quantity:
                    current_usdt_value = quantity * current_price
                    active_trade['usdt_amount'] = current_usdt_value
        
        # Get market data - limit to requested count
        market_data = []
        requested_count = getattr(bot_instance, 'requested_count', bot_instance.config_manager['top_gainers_count']) if bot_instance.config_manager else 35
        
        if bot_instance.monitored_symbols:
            for symbol in bot_instance.monitored_symbols:
                # Stop if we have enough valid coins
                if len(market_data) >= requested_count:
                    break
                
                prev_candle = bot_instance.candle_tracker.get_previous_candle(symbol) if bot_instance.candle_tracker else None
                current_candle = bot_instance.candle_tracker.get_current_candle(symbol) if bot_instance.candle_tracker else None
                current_price = bot_instance.binance_client.get_current_price(symbol) if bot_instance.binance_client else None
                
                # Validate elapsed time
                elapsed_minutes = current_candle.get('elapsed_minutes') if current_candle else None
                if elapsed_minutes is None or elapsed_minutes < 0 or elapsed_minutes > 60:
                    continue
                
                if prev_candle and current_candle and current_price:
                    result = bot_instance.entry_conditions.check_all_conditions(
                        symbol=symbol,
                        prev_candle_close=prev_candle.close_price,
                        prev_candle_volume=prev_candle.volume,
                        current_price=current_price,
                        current_volume=current_candle['volume'],
                        elapsed_minutes=elapsed_minutes,
                        is_trade_active=bot_instance.state_manager.is_trade_active() if bot_instance.state_manager else False,
                        is_in_cooldown=bot_instance.state_manager.is_in_cooldown(symbol) if bot_instance.state_manager else False
                    )
                    
                    market_data.append({
                        'symbol': symbol,
                        'price': current_price,
                        'prev_close_price': prev_candle.close_price,
                        'current_volume': current_candle['volume'],
                        'prev_volume': prev_candle.volume,
                        'elapsed_minutes': elapsed_minutes,
                        'status': result['status']
                    })
        
        # Limit to requested count
        market_data = market_data[:requested_count]
        
        # Get trade history
        history = bot_instance.trade_history.get_all_trades() if bot_instance.trade_history else []
        
        return JSONResponse({
            "running": bot_instance.running,
            "active_trade": active_trade,
            "markets": market_data,
            "history": history,
            "monitored_symbols_count": len(market_data),  # Use filtered count, not original
            "total_scanned": len(bot_instance.monitored_symbols) if bot_instance.monitored_symbols else 0
        })
    except Exception as e:
        logger.error(f"Error getting bot state: {e}")
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500
        )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    websocket_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total clients: {len(websocket_clients)}")
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_clients.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(websocket_clients)}")


async def broadcast_message(message: dict):
    """Broadcast message to all connected WebSocket clients."""
    if not websocket_clients:
        return
    
    message_json = json.dumps(message)
    disconnected = set()
    
    for client in websocket_clients:
        try:
            await client.send_text(message_json)
        except Exception as e:
            logger.error(f"Error sending to client: {e}")
            disconnected.add(client)
    
    # Remove disconnected clients
    for client in disconnected:
        websocket_clients.discard(client)


def set_bot_instance(bot):
    """Set the bot instance for the web server."""
    global bot_instance
    bot_instance = bot


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
