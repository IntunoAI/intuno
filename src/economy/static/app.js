const API = '';
const WS_URL = `ws://${location.host}/ws`;

let ws = null;
let priceChart = null;
let walletChart = null;
let initialBalances = {};
let priceHistory = [];
let tickLabels = [];
let walletAgentMap = {};

// ── Initialization ─────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    await loadScenarios();
    initCharts();
    connectWebSocket();
    pollStatus();
    loadCreditPackages();
    refreshWallets();
});

async function loadScenarios() {
    try {
        const res = await fetch(`${API}/scenarios`);
        const scenarios = await res.json();
        const select = document.getElementById('scenarioSelect');
        scenarios.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.name;
            opt.textContent = s.name.replace(/_/g, ' ');
            opt.title = s.description;
            select.appendChild(opt);
        });

        select.addEventListener('change', () => {
            const scenario = scenarios.find(s => s.name === select.value);
            if (scenario && scenario.default_config) {
                document.getElementById('tickCount').value = scenario.default_config.tick_count;
                document.getElementById('tickInterval').value = scenario.default_config.tick_interval_ms;
                document.getElementById('serviceCount').value = scenario.default_config.service_agent_count;
                document.getElementById('buyerCount').value = scenario.default_config.buyer_agent_count;
            }
        });

        if (scenarios.length > 0) select.dispatchEvent(new Event('change'));
    } catch (e) {
        console.error('Failed to load scenarios:', e);
    }
}

// ── Charts ─────────────────────────────────────────────────

function initCharts() {
    const chartDefaults = {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 200 },
        scales: {
            x: { ticks: { color: '#8b8fa3', maxTicksLimit: 20 }, grid: { color: 'rgba(45,49,65,0.5)' } },
            y: { ticks: { color: '#8b8fa3' }, grid: { color: 'rgba(45,49,65,0.5)' } },
        },
        plugins: { legend: { labels: { color: '#e4e6eb', boxWidth: 12 } } },
    };

    priceChart = new Chart(document.getElementById('priceChart'), {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, title: { display: false } } },
    });

    walletChart = new Chart(document.getElementById('walletChart'), {
        type: 'bar',
        data: { labels: [], datasets: [{ label: 'Balance', data: [], backgroundColor: '#3366ff' }] },
        options: { ...chartDefaults, indexAxis: 'y' },
    });
}

// ── WebSocket ──────────────────────────────────────────────

function connectWebSocket() {
    ws = new WebSocket(WS_URL);

    ws.onmessage = (event) => {
        const envelope = JSON.parse(event.data);
        handleEvent(envelope);
    };

    ws.onclose = () => {
        setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = () => {
        ws.close();
    };
}

function handleEvent(envelope) {
    const { event: eventType, data, timestamp } = envelope;

    addFeedItem(eventType, data, timestamp);

    switch (eventType) {
        case 'TradeMatched':
            addPricePoint(data);
            break;
        case 'SettlementComplete':
            if (data.status === 'settled') refreshWallets();
            break;
        case 'SimulationTick':
            updateStats(data);
            break;
        case 'SimulationStarted':
            resetDashboard();
            setStatus('running');
            document.getElementById('statAgents').textContent = data.agents_count || 0;
            break;
        case 'SimulationCompleted':
        case 'SimulationStopped':
            setStatus(eventType === 'SimulationCompleted' ? 'completed' : 'stopped');
            setBtnState(false);
            refreshWallets();
            break;
    }
}

// ── Feed ───────────────────────────────────────────────────

function addFeedItem(eventType, data, timestamp) {
    const list = document.getElementById('feedList');
    const li = document.createElement('li');
    li.className = 'feed-item';

    let evtClass = 'sim';
    if (eventType.includes('Trade')) evtClass = 'trade';
    else if (eventType.includes('Order')) evtClass = 'order';
    else if (eventType.includes('Settlement')) evtClass = 'settlement';

    const text = formatEventText(eventType, data);
    const time = new Date(timestamp).toLocaleTimeString();

    li.innerHTML = `
        <span class="feed-event ${evtClass}">${eventType.replace('Simulation', 'Sim')}</span>
        <span class="feed-text">${text}</span>
        <span class="feed-time">${time}</span>
    `;

    list.prepend(li);
    while (list.children.length > 100) list.lastChild.remove();
}

function formatEventText(eventType, data) {
    switch (eventType) {
        case 'TradeMatched':
            return `${data.capability} @ ${data.price} credits (tick ${data.tick})`;
        case 'SettlementComplete':
            return `${data.capability || ''} — ${data.status} in ${data.latency_ms}ms`;
        case 'OrderPlaced':
            return `${data.side.toUpperCase()} ${data.capability} @ ${data.price}`;
        case 'SimulationTick':
            return `Tick ${data.tick} / ${data.total_ticks}`;
        case 'SimulationStarted':
            return `${data.scenario_name} with ${data.agents_count} agents`;
        default:
            return JSON.stringify(data).slice(0, 80);
    }
}

// ── Price Chart ────────────────────────────────────────────

function addPricePoint(data) {
    const label = `T${data.tick}`;
    if (!tickLabels.includes(label)) tickLabels.push(label);

    let dataset = priceChart.data.datasets.find(d => d.label === data.capability);
    if (!dataset) {
        const colors = ['#00d68f', '#3366ff', '#ffaa00', '#ff4d6a', '#a855f7'];
        dataset = {
            label: data.capability,
            data: [],
            borderColor: colors[priceChart.data.datasets.length % colors.length],
            backgroundColor: 'transparent',
            tension: 0.3,
            pointRadius: 2,
        };
        priceChart.data.datasets.push(dataset);
    }

    dataset.data.push(data.price);
    priceChart.data.labels = tickLabels;
    priceChart.update('none');
}

// ── Wallet Chart ───────────────────────────────────────────

async function refreshWallets() {
    try {
        const res = await fetch(`${API}/wallets?limit=20`);
        const wallets = await res.json();

        const agentRes = await fetch(`${API}/agents?limit=50`);
        const agents = await agentRes.json();
        const agentMap = {};
        agents.forEach(a => { agentMap[a.id] = a; });

        walletAgentMap = {};
        wallets.forEach(w => {
            if (w.wallet_type === 'user') {
                walletAgentMap[w.id] = 'User Wallet';
            } else if (w.agent_id) {
                const agent = agentMap[w.agent_id];
                walletAgentMap[w.id] = agent ? agent.name : w.agent_id.slice(0, 8);
            } else {
                walletAgentMap[w.id] = w.id.slice(0, 8);
            }
        });

        const labels = [];
        const balances = [];
        const colors = [];

        wallets.forEach(w => {
            const name = walletAgentMap[w.id] || w.id.slice(0, 8);
            labels.push(name);
            balances.push(w.balance);
            colors.push(w.balance >= 0 ? '#00d68f' : '#ff4d6a');
        });

        walletChart.data.labels = labels;
        walletChart.data.datasets[0].data = balances;
        walletChart.data.datasets[0].backgroundColor = colors;
        walletChart.update('none');

        populateWalletSelect(wallets);
        await refreshLeaderboard(wallets);
    } catch (e) {
        console.error('Failed to refresh wallets:', e);
    }
}

function populateWalletSelect(wallets) {
    const select = document.getElementById('walletSelect');
    const currentVal = select.value;
    const opts = ['<option value="">-- pick a wallet --</option>'];
    wallets.forEach(w => {
        const name = walletAgentMap[w.id] || w.id.slice(0, 8);
        opts.push(`<option value="${w.id}">${name} (${w.balance} cr)</option>`);
    });
    select.innerHTML = opts.join('');
    if (currentVal) select.value = currentVal;
}

async function refreshLeaderboard(wallets) {
    const rows = [];
    const summaryPromises = wallets.map(w =>
        fetch(`${API}/wallets/${w.id}/summary`).then(r => r.json()).catch(() => null)
    );
    const summaries = await Promise.all(summaryPromises);

    wallets.forEach((w, i) => {
        const name = walletAgentMap[w.id] || w.id.slice(0, 8);
        const s = summaries[i] || {};
        rows.push({
            name,
            balance: w.balance,
            granted: s.total_granted || 0,
            earned: s.total_earned || 0,
            spent: s.total_spent || 0,
            purchased: s.total_purchased || 0,
        });
    });

    rows.sort((a, b) => b.balance - a.balance);
    const tbody = document.getElementById('leaderboardBody');
    tbody.innerHTML = rows.map(r => `
        <tr>
            <td>${r.name}</td>
            <td>${r.balance}</td>
            <td style="color:var(--accent-blue)">${r.granted}</td>
            <td class="balance-positive">+${r.earned}</td>
            <td class="balance-negative">-${r.spent}</td>
            <td style="color:var(--accent-yellow)">${r.purchased}</td>
        </tr>
    `).join('');
}

// ── Simulation Controls ────────────────────────────────────

async function startSimulation() {
    const config = {
        scenario_name: document.getElementById('scenarioSelect').value,
        tick_count: parseInt(document.getElementById('tickCount').value),
        tick_interval_ms: parseInt(document.getElementById('tickInterval').value),
        service_agent_count: parseInt(document.getElementById('serviceCount').value),
        buyer_agent_count: parseInt(document.getElementById('buyerCount').value),
        initial_balance: 1000,
    };

    try {
        const res = await fetch(`${API}/scenarios/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config),
        });
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || 'Failed to start');
            return;
        }
        setBtnState(true);
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function stopSimulation() {
    try {
        await fetch(`${API}/scenarios/stop`, { method: 'POST' });
        setBtnState(false);
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

// ── Helpers ────────────────────────────────────────────────

function setBtnState(running) {
    document.getElementById('btnStart').disabled = running;
    document.getElementById('btnStop').disabled = !running;
}

function setStatus(status) {
    const badge = document.getElementById('statusBadge');
    badge.className = `status-badge ${status}`;
    document.getElementById('statusText').textContent =
        status.charAt(0).toUpperCase() + status.slice(1);
}

function updateStats(data) {
    document.getElementById('statTick').textContent = `${data.tick} / ${data.total_ticks}`;
}

function resetDashboard() {
    priceChart.data.labels = [];
    priceChart.data.datasets = [];
    priceChart.update();
    tickLabels = [];
    priceHistory = [];
    initialBalances = {};
    document.getElementById('feedList').innerHTML = '';
    document.getElementById('leaderboardBody').innerHTML = '';
    document.getElementById('statTrades').textContent = '0';
    document.getElementById('statVolume').textContent = '0';
}

async function pollStatus() {
    try {
        const res = await fetch(`${API}/scenarios/status`);
        const status = await res.json();
        setStatus(status.status);
        document.getElementById('statTick').textContent =
            `${status.current_tick} / ${status.total_ticks}`;
        document.getElementById('statTrades').textContent = status.total_trades;
        document.getElementById('statVolume').textContent = status.total_volume;
        document.getElementById('statAgents').textContent = status.agents_count;
        setBtnState(status.status === 'running');
    } catch (e) { /* server not ready yet */ }

    setInterval(async () => {
        try {
            const res = await fetch(`${API}/scenarios/status`);
            const status = await res.json();
            document.getElementById('statTrades').textContent = status.total_trades;
            document.getElementById('statVolume').textContent = status.total_volume;
        } catch (e) { /* ignore */ }
    }, 2000);
}

// ── Credits Management ────────────────────────────────────

async function loadCreditPackages() {
    try {
        const res = await fetch(`${API}/credits/packages`);
        const packages = await res.json();
        const grid = document.getElementById('packageCards');
        grid.innerHTML = packages.map(pkg => `
            <div class="package-card" data-pkg-id="${pkg.id}">
                <div class="package-credits">${pkg.credits.toLocaleString()}</div>
                <div class="package-price">${pkg.label}</div>
                <div class="package-label">${pkg.id}</div>
                <button class="btn-buy" onclick="buyPackage('${pkg.id}')">Buy</button>
            </div>
        `).join('');
    } catch (e) {
        console.error('Failed to load packages:', e);
    }
}

async function loadWalletSummary() {
    const walletId = document.getElementById('walletSelect').value;
    const card = document.getElementById('walletSummaryCard');
    if (!walletId) {
        card.classList.add('hidden');
        return;
    }
    try {
        const res = await fetch(`${API}/wallets/${walletId}/summary`);
        const s = await res.json();
        const name = walletAgentMap[walletId] || walletId.slice(0, 8);

        document.getElementById('summaryAgentName').textContent = name;
        document.getElementById('summaryBalance').textContent = s.balance.toLocaleString();
        document.getElementById('sumGranted').textContent = s.total_granted.toLocaleString();
        document.getElementById('sumPurchased').textContent = s.total_purchased.toLocaleString();
        document.getElementById('sumEarned').textContent = `+${s.total_earned.toLocaleString()}`;
        document.getElementById('sumSpent').textContent = `-${s.total_spent.toLocaleString()}`;
        document.getElementById('sumTxCount').textContent = s.transaction_count;

        card.classList.remove('hidden');
    } catch (e) {
        console.error('Failed to load wallet summary:', e);
    }
}

async function grantCredits() {
    const walletId = document.getElementById('walletSelect').value;
    if (!walletId) return showResult('grantResult', 'Select a wallet first', false);

    const amount = parseInt(document.getElementById('grantAmount').value);
    const grantType = document.getElementById('grantType').value;
    if (!amount || amount <= 0) return showResult('grantResult', 'Enter a positive amount', false);

    try {
        const res = await fetch(`${API}/wallets/${walletId}/grant`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount, grant_type: grantType }),
        });
        if (!res.ok) {
            const err = await res.json();
            return showResult('grantResult', err.detail || 'Grant failed', false);
        }
        const wallet = await res.json();
        showResult('grantResult', `Granted ${amount} credits. New balance: ${wallet.balance}`, true);
        loadWalletSummary();
        refreshWallets();
    } catch (e) {
        showResult('grantResult', 'Error: ' + e.message, false);
    }
}

async function buyPackage(packageId) {
    const walletId = document.getElementById('walletSelect').value;
    if (!walletId) return showResult('purchaseResult', 'Select a wallet first', false);

    try {
        const createRes = await fetch(`${API}/credits/wallets/${walletId}/purchase`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ package_id: packageId }),
        });
        if (!createRes.ok) {
            const err = await createRes.json();
            return showResult('purchaseResult', err.detail || 'Purchase failed', false);
        }
        const purchase = await createRes.json();
        showResult('purchaseResult', `Purchase pending (${purchase.provider_reference}). Confirming...`, true);

        const confirmRes = await fetch(`${API}/credits/purchases/${purchase.id}/confirm`, {
            method: 'POST',
        });
        if (!confirmRes.ok) {
            const err = await confirmRes.json();
            return showResult('purchaseResult', err.detail || 'Confirmation failed', false);
        }
        const confirmed = await confirmRes.json();
        showResult('purchaseResult', `Purchased ${confirmed.credits_amount} credits (${packageId})`, true);
        loadWalletSummary();
        refreshWallets();
    } catch (e) {
        showResult('purchaseResult', 'Error: ' + e.message, false);
    }
}

function showResult(elementId, message, isSuccess) {
    const el = document.getElementById(elementId);
    el.textContent = message;
    el.className = `action-result ${isSuccess ? 'success' : 'error'}`;
    el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 4000);
}
