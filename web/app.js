// WebSocket connection
let ws = null;
let botRunning = false;

// DOM Elements
const configForm = document.getElementById('configForm');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const statusBadge = document.getElementById('botStatus');
const statusText = document.getElementById('statusText');
const activeTrade = document.getElementById('activeTrade');
const botState = document.getElementById('botState');
const marketTableBody = document.getElementById('marketTableBody');
const logsContainer = document.getElementById('logsContainer');
const historyTableBody = document.getElementById('historyTableBody');
const activeTradeTableBody = document.getElementById('activeTradeTableBody');
const tradePanel = document.getElementById('tradePanel');
const timeExitEnabled = document.getElementById('timeExitEnabled');
const maxTradeDurationMinutes = document.getElementById('maxTradeDurationMinutes');


// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Load from localStorage first (instant restore)
    loadFromLocalStorage();
    // Then sync with server
    loadConfig();
    setupEventListeners();
    connectWebSocket();
    // Load bot state and auto-restart if needed (will be called after WebSocket connects)
    loadBotState();
    console.log('DOMContentLoaded');
});

// Setup Event Listeners
function setupEventListeners() {
    configForm.addEventListener('submit', saveConfig);
    startBtn.addEventListener('click', startBot);
    stopBtn.addEventListener('click', stopBot);
    
    // Password visibility toggle
    const apiSecretToggle = document.getElementById('apiSecretToggle');
    const apiSecretInput = document.getElementById('apiSecret');
    if (apiSecretToggle && apiSecretInput) {
        apiSecretToggle.addEventListener('click', () => {
            const isPassword = apiSecretInput.type === 'password';
            apiSecretInput.type = isPassword ? 'text' : 'password';
            apiSecretToggle.querySelector('.toggle-icon').textContent = isPassword ? '🙈' : '👁️';
        });
    }
}

// LocalStorage Keys
const STORAGE_KEYS = {
    CONFIG: 'binance_bot_config',
    BOT_STATE: 'binance_bot_state',
    MARKETS: 'binance_bot_markets',
    HISTORY: 'binance_bot_history',
    ACTIVE_TRADE: 'binance_bot_active_trade'
};

// Save to LocalStorage
function saveToLocalStorage(key, data) {
    try {
        localStorage.setItem(key, JSON.stringify(data));
    } catch (error) {
        console.error(`Error saving to localStorage (${key}):`, error);
    }
}

// Load from LocalStorage
function loadFromLocalStorage() {
    try {
        // Load bot state (don't auto-start here, wait for loadBotState to check)
        const savedState = localStorage.getItem(STORAGE_KEYS.BOT_STATE);
        if (savedState) {
            const state = JSON.parse(savedState);
            botRunning = state.running || false;
            updateBotStatus(botRunning);
            if (botRunning) {
                addLog('📦 Bot state restored from local storage - Will auto-restart if needed');
            }
        }
        
        // Load markets
        const savedMarkets = localStorage.getItem(STORAGE_KEYS.MARKETS);
        if (savedMarkets) {
            const markets = JSON.parse(savedMarkets);
            updateMarketTable(markets);
            addLog(`📦 Market data restored: ${markets.length} symbols`);
        }
        
        // Load history
        const savedHistory = localStorage.getItem(STORAGE_KEYS.HISTORY);
        if (savedHistory) {
            const history = JSON.parse(savedHistory);
            updateTradeHistory(history);
            addLog(`📦 Trade history restored: ${history.length} trades`);
        }
        
        // Load active trade
        const savedActiveTrade = localStorage.getItem(STORAGE_KEYS.ACTIVE_TRADE);
        if (savedActiveTrade) {
            const trade = JSON.parse(savedActiveTrade);
            if (trade) {
                updateActiveTrade(trade);
                addLog(`📦 Active trade restored: ${trade.symbol}`);
            }
        } else {
            // Ensure table shows empty state if no trade
            updateActiveTradeTable(null);
        }
    } catch (error) {
        console.error('Error loading from localStorage:', error);
    }
}

// Load Configuration
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const config = await response.json();
            populateForm(config);
            addLog('Configuration loaded from server');
        }
    } catch (error) {
        addLog('Failed to load configuration: ' + error.message, 'error');
    }
}

// Check and restart bot if needed
async function checkAndRestartBot() {
    try {
        // Check localStorage to see if bot was running before reload
        const savedState = localStorage.getItem(STORAGE_KEYS.BOT_STATE);
        const wasRunning = savedState ? JSON.parse(savedState).running : false;
        
        if (!wasRunning) {
            // Bot wasn't running, no need to restart
            return;
        }
        
        // Check server state
        const response = await fetch('/api/bot/state');
        if (response.ok) {
            const state = await response.json();
            
            // If bot was running before reload but server says it's stopped, restart it
            if (!state.running) {
                addLog('🔄 Bot was running before reload - Auto-restarting...');
                // Automatically restart the bot
                await startBot();
            } else {
                // Bot is already running on server, just update UI
                botRunning = true;
                updateBotStatus(true);
                addLog('✅ Bot is already running on server');
            }
        }
    } catch (error) {
        addLog('❌ Error checking bot state: ' + error.message, 'error');
    }
}

// Load Bot State (for page restoration)
async function loadBotState() {
    try {
        const response = await fetch('/api/bot/state');
        if (response.ok) {
            const state = await response.json();
            
            // Save to localStorage
            saveToLocalStorage(STORAGE_KEYS.BOT_STATE, { running: state.running });
            
            // Restore bot running status
            if (state.running) {
                botRunning = true;
                updateBotStatus(true);
                addLog('Bot state synced from server - Bot is RUNNING');
            } else {
                botRunning = false;
                updateBotStatus(false);
                addLog('Bot state synced from server - Bot is STOPPED');
            }
            
            // Restore active trade
            if (state.active_trade) {
                updateActiveTrade(state.active_trade);
                saveToLocalStorage(STORAGE_KEYS.ACTIVE_TRADE, state.active_trade);
                addLog(`Active trade restored: ${state.active_trade.symbol}`);
            } else {
                // Clear if no active trade
                updateActiveTrade(null);
                localStorage.removeItem(STORAGE_KEYS.ACTIVE_TRADE);
            }
            
            // Restore market data (update if server has newer data)
            if (state.markets && state.markets.length > 0) {
                updateMarketTable(state.markets);
                saveToLocalStorage(STORAGE_KEYS.MARKETS, state.markets);
            }
            
            // Restore trade history (update if server has newer data)
            if (state.history && state.history.length > 0) {
                updateTradeHistory(state.history);
                saveToLocalStorage(STORAGE_KEYS.HISTORY, state.history);
            }
            
            // Display filtered count if available
            const filteredCount = state.monitored_symbols_count || 0;
            const totalScanned = state.total_scanned || filteredCount;
            if (filteredCount < totalScanned) {
                addLog(`📊 Displaying ${filteredCount} of ${totalScanned} scanned symbols (${totalScanned - filteredCount} filtered out due to invalid data)`);
            } else {
                addLog(`📊 Monitoring ${filteredCount} symbols`);
            }
        }
    } catch (error) {
        addLog('Failed to load bot state: ' + error.message, 'error');
    }
}

// Populate Form with Config
function populateForm(config) {
    document.getElementById('apiKey').value = config.api_key || '';
    document.getElementById('apiSecret').value = config.api_secret || '';
    document.getElementById('topGainersCount').value = config.top_gainers_count || 35;
    document.getElementById('candleTimeframe').value = config.candle_timeframe || '1h';
    document.getElementById('volumeMultiplier').value = config.volume_multiplier || 1.0;
    document.getElementById('volumeTimeLimit').value = config.volume_time_limit || 15;
    document.getElementById('priceChangePercent').value = config.price_change_percent || 2.0;
    document.getElementById('stopLossPercent').value = config.stop_loss_percent || 1.5;
    document.getElementById('takeProfitPercent').value = config.take_profit_percent || 5.0;
    document.getElementById('trailingStopPercent').value = config.trailing_stop_percent || 1.0;
    document.getElementById('cooldownMinutes').value = config.cooldown_minutes || 60;
    timeExitEnabled.checked = !!config.time_exit_enabled;
    maxTradeDurationMinutes.value = config.max_trade_duration_minutes || 60;
}

// Save Configuration
async function saveConfig(e) {
    e.preventDefault();
    
    const config = {
        api_key: document.getElementById('apiKey').value,
        api_secret: document.getElementById('apiSecret').value,
        top_gainers_count: parseInt(document.getElementById('topGainersCount').value),
        candle_timeframe: document.getElementById('candleTimeframe').value,
        volume_multiplier: parseFloat(document.getElementById('volumeMultiplier').value),
        volume_time_limit: parseInt(document.getElementById('volumeTimeLimit').value),
        price_change_percent: parseFloat(document.getElementById('priceChangePercent').value),
        stop_loss_percent: parseFloat(document.getElementById('stopLossPercent').value),
        take_profit_percent: parseFloat(document.getElementById('takeProfitPercent').value),
        trailing_stop_percent: parseFloat(document.getElementById('trailingStopPercent').value),
        cooldown_minutes: parseInt(document.getElementById('cooldownMinutes').value),
        time_exit_enabled: timeExitEnabled.checked,
        max_trade_duration_minutes: parseInt(maxTradeDurationMinutes.value)
    };
    
    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        });
        
        if (response.ok) {
            addLog('✅ Configuration saved successfully');
        } else {
            addLog('❌ Failed to save configuration', 'error');
        }
    } catch (error) {
        addLog('❌ Error saving configuration: ' + error.message, 'error');
    }
}

// Start Bot
async function startBot() {
    try {
        const response = await fetch('/api/bot/start', {
            method: 'POST'
        });
        
        if (response.ok) {
            botRunning = true;
            updateBotStatus(true);
            saveToLocalStorage(STORAGE_KEYS.BOT_STATE, { running: true });
            addLog('🚀 Bot started successfully');
        } else {
            addLog('❌ Failed to start bot', 'error');
        }
    } catch (error) {
        addLog('❌ Error starting bot: ' + error.message, 'error');
    }
}

// Stop Bot
async function stopBot() {
    try {
        const response = await fetch('/api/bot/stop', {
            method: 'POST'
        });
        
        if (response.ok) {
            botRunning = false;
            updateBotStatus(false);
            saveToLocalStorage(STORAGE_KEYS.BOT_STATE, { running: false });
            addLog('⏹️ Bot stopped');
        } else {
            addLog('❌ Failed to stop bot', 'error');
        }
    } catch (error) {
        addLog('❌ Error stopping bot: ' + error.message, 'error');
    }
}

// Update Bot Status UI
function updateBotStatus(running) {
    if (running) {
        statusBadge.classList.add('running');
        statusText.textContent = 'RUNNING';
        botState.innerHTML = 'Bot State: <strong>SCANNING</strong>';
        startBtn.disabled = true;
        stopBtn.disabled = false;
    } else {
        statusBadge.classList.remove('running');
        statusText.textContent = 'STOPPED';
        botState.innerHTML = 'Bot State: <strong>STOPPED</strong>';
        startBtn.disabled = false;
        stopBtn.disabled = true;
    }
}

// WebSocket Connection
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        addLog('🔌 WebSocket connected');
        // After WebSocket connects, check if bot needs to be restarted
        checkAndRestartBot();
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
    
    ws.onerror = (error) => {
        addLog('⚠️ WebSocket error', 'error');
    };
    
    ws.onclose = () => {
        addLog('🔌 WebSocket disconnected, reconnecting...');
        setTimeout(connectWebSocket, 3000);
    };
}

// Handle WebSocket Messages
function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'market_update':
            updateMarketTable(data.markets);
            // Save to localStorage
            if (data.markets) {
                saveToLocalStorage(STORAGE_KEYS.MARKETS, data.markets);
            }
            // Update count display with filtered count
            if (data.filtered_count !== undefined) {
                const totalScanned = data.total_scanned || data.filtered_count;
                if (data.filtered_count < totalScanned) {
                    addLog(`📊 Displaying ${data.filtered_count} of ${totalScanned} scanned symbols (${totalScanned - data.filtered_count} filtered out due to invalid data)`);
                } else {
                    addLog(`📊 Monitoring ${data.filtered_count} symbols`);
                }
            }
            break;
        case 'trade_update':
            updateActiveTrade(data.trade);
            // Save to localStorage
            if (data.trade) {
                saveToLocalStorage(STORAGE_KEYS.ACTIVE_TRADE, data.trade);
            } else {
                localStorage.removeItem(STORAGE_KEYS.ACTIVE_TRADE);
            }
            break;
        case 'log':
            addLog(data.message, data.level);
            break;
        case 'history_update':
            updateTradeHistory(data.history);
            // Save to localStorage
            if (data.history) {
                saveToLocalStorage(STORAGE_KEYS.HISTORY, data.history);
            }
            break;
        case 'bot_status':
            updateBotStatus(data.running);
            botRunning = data.running;
            // Save to localStorage
            saveToLocalStorage(STORAGE_KEYS.BOT_STATE, { running: data.running });
            break;
    }
}

// Update Market Table
function updateMarketTable(markets) {
    if (!markets || markets.length === 0) {
        marketTableBody.innerHTML = '<tr class="empty-state"><td colspan="7">No market data available</td></tr>';
        return;
    }
    
    marketTableBody.innerHTML = markets.map(market => `
        <tr>
            <td><strong>${market.symbol}</strong></td>
            <td>${formatPrice(market.price)}</td>
            <td>${formatPrice(market.prev_close_price || 0)}</td>
            <td>${formatVolume(market.current_volume)}</td>
            <td>${formatVolume(market.prev_volume)}</td>
            <td>${market.elapsed_minutes}m</td>
            <td>${getStatusEmoji(market.status)} ${market.status}</td>
        </tr>
    `).join('');
}

// Update Active Trade
function updateActiveTrade(trade) {
    // Update the old trade panel (if it exists)
    if (tradePanel) {
        if (!trade) {
            tradePanel.style.display = 'none';
            if (activeTrade) activeTrade.innerHTML = 'Active Trade: <strong>NO</strong>';
        } else {
            tradePanel.style.display = 'block';
            if (activeTrade) activeTrade.innerHTML = 'Active Trade: <strong>YES</strong>';
            
            const symbolEl = document.getElementById('tradeSymbol');
            const entryPriceEl = document.getElementById('tradeEntryPrice');
            const currentPriceEl = document.getElementById('tradeCurrentPrice');
            const stopLossEl = document.getElementById('tradeStopLoss');
            const tpTriggerEl = document.getElementById('tradeTpTrigger');
            const trailingStopEl = document.getElementById('tradeTrailingStop');
            const stateEl = document.getElementById('tradeState');
            const pnlElement = document.getElementById('tradePnl');
            
            if (symbolEl) symbolEl.textContent = trade.symbol;
            if (entryPriceEl) entryPriceEl.textContent = formatPrice(trade.entry_price);
            if (currentPriceEl) currentPriceEl.textContent = formatPrice(trade.current_price);
            if (stopLossEl) stopLossEl.textContent = formatPrice(trade.stop_loss);
            if (tpTriggerEl) tpTriggerEl.textContent = formatPrice(trade.tp_trigger);
            if (trailingStopEl) trailingStopEl.textContent = formatPrice(trade.trailing_stop || '-');
            if (stateEl) stateEl.textContent = trade.state;
            
            if (pnlElement) {
                const pnlValue = trade.pnl_percent || 0;
                pnlElement.textContent = `${pnlValue >= 0 ? '+' : ''}${pnlValue.toFixed(2)}%`;
                pnlElement.className = pnlValue >= 0 ? 'pnl-positive' : 'pnl-negative';
            }
        }
    }
    
    // Update the new active trade table
    updateActiveTradeTable(trade);
}

// Update Active Trade Table
function updateActiveTradeTable(trade) {
    if (!activeTradeTableBody) return;
    
    if (!trade) {
        activeTradeTableBody.innerHTML = '<tr class="empty-state"><td colspan="9">No active trade...</td></tr>';
        return;
    }
    
    const pnlValue = trade.pnl_percent || 0;
    const pnlClass = pnlValue >= 0 ? 'pnl-positive' : 'pnl-negative';
    const pnlDisplay = `${pnlValue >= 0 ? '+' : ''}${pnlValue.toFixed(2)}%`;
    const usdtAmount = trade.usdt_amount || 0;
    
    activeTradeTableBody.innerHTML = `
        <tr>
            <td><strong>${trade.symbol}</strong></td>
            <td>${formatPrice(trade.entry_price)}</td>
            <td>${formatPrice(trade.current_price)}</td>
            <td>${usdtAmount.toFixed(2)} USDT</td>
            <td>${formatPrice(trade.stop_loss)}</td>
            <td>${formatPrice(trade.tp_trigger)}</td>
            <td>${trade.trailing_stop ? formatPrice(trade.trailing_stop) : '-'}</td>
            <td class="${pnlClass}"><strong>${pnlDisplay}</strong></td>
            <td>${trade.state || 'ACTIVE'}</td>
        </tr>
    `;
}

// Update Trade History
function updateTradeHistory(history) {
    if (!history || history.length === 0) {
        historyTableBody.innerHTML = '<tr class="empty-state"><td colspan="7">No trades yet...</td></tr>';
        return;
    }
    
    // Show all trades with latest on top (reverse the array)
    historyTableBody.innerHTML = history.slice().reverse().map(trade => {
        const pnlClass = trade.pnl_percent >= 0 ? 'pnl-positive' : 'pnl-negative';
        const usdtAmount = trade.usdt_amount || 0;
        return `
            <tr>
                <td>${formatDateTime(trade.entry_time)}</td>
                <td><strong>${trade.symbol}</strong></td>
                <td>${formatPrice(trade.entry_price)}</td>
                <td>${formatPrice(trade.exit_price)}</td>
                <td>${usdtAmount.toFixed(2)} USDT</td>
                <td class="${pnlClass}">${trade.pnl_percent >= 0 ? '+' : ''}${trade.pnl_percent.toFixed(2)}%</td>
                <td>${trade.exit_reason}</td>
            </tr>
        `;
    }).join('');
}

// Add Log Entry
function addLog(message, level = 'info') {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    logEntry.innerHTML = `
        <span class="log-time">[${time}]</span>
        <span class="log-message">${message}</span>
    `;
    
    logsContainer.appendChild(logEntry);
    logsContainer.scrollTop = logsContainer.scrollHeight;
    
    // Keep only last 100 logs
    while (logsContainer.children.length > 100) {
        logsContainer.removeChild(logsContainer.firstChild);
    }
}

// Format Helpers
function formatPrice(price) {
    if (!price) return '-';
    return parseFloat(price).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 8
    });
}

function formatVolume(volume) {
    if (!volume) return '-';
    if (volume >= 1000000) {
        return (volume / 1000000).toFixed(1) + 'M';
    } else if (volume >= 1000) {
        return (volume / 1000).toFixed(1) + 'K';
    }
    return volume.toFixed(0);
}

function formatDateTime(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });
}

function getStatusEmoji(status) {
    const emojiMap = {
        'WAIT': '⏳',
        'SIGNAL': '🔥',
        'IN TRADE': '🟢',
        'LOCKED': '🔒',
        'COOLDOWN': '🧊',
        'TIME OUT': '❌'
    };
    return emojiMap[status] || '⏳';
}
