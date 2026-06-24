// Global state
let analysisData = null;
let selectedStockCode = null;
let stockPricesCache = {};
let myChart = null;
let sharesOutstandingDb = {};

const todayTime = new Date(new Date().toISOString().slice(0, 10)).getTime();

function parseDateTime(value) {
    if (typeof value !== "string") return null;
    const text = value.slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
    const time = new Date(`${text}T00:00:00`).getTime();
    return Number.isFinite(time) ? time : null;
}

function latestDateString(values) {
    return values
        .filter(value => typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value))
        .map(value => value.slice(0, 10))
        .sort()
        .pop() || null;
}

function bondSortTime(bond) {
    const dates = [bond.announcement_date, bond.issue_date, bond.high_after_date, bond.low_before_date]
        .map(parseDateTime)
        .filter(Number.isFinite);
    return dates.length ? Math.max(...dates) : 0;
}

function sortBondsByRecentDate(bonds) {
    return [...(bonds || [])].sort((a, b) => bondSortTime(b) - bondSortTime(a));
}

function trackFocusTime(track) {
    const stationTimes = (track.stations || [])
        .map(station => parseDateTime(station.date))
        .filter(Number.isFinite);
    const expected = parseDateTime(track.expected_listing_date);
    const futureTimes = [...stationTimes, expected].filter(time => Number.isFinite(time) && time >= todayTime);
    if (futureTimes.length) return Math.min(...futureTimes);
    if (stationTimes.length) return Math.max(...stationTimes);
    return expected || 0;
}

function sortTracksByNearestDate(tracks) {
    return [...(tracks || [])].sort((a, b) => {
        const deltaA = Math.abs(trackFocusTime(a) - todayTime);
        const deltaB = Math.abs(trackFocusTime(b) - todayTime);
        return deltaA - deltaB;
    });
}

function updateDataLastUpdated(extraDates = []) {
    const bondDates = (analysisData?.bonds_analysis || []).flatMap(bond => [
        bond.announcement_date,
        bond.issue_date,
        bond.high_after_date,
        bond.low_before_date
    ]);
    const latest = latestDateString([...bondDates, ...extraDates]);
    const target = document.getElementById("data-last-updated");
    if (target) target.innerText = latest ? `Latest date: ${latest}` : "Latest date: -";
}

function debounce(fn, delay = 120) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", async () => {
    await loadDashboardData();
    setupEventListeners();
    await loadActiveTracks();
});

async function loadDashboardData() {
    try {
        const [analysisResponse, sharesResponse] = await Promise.all([
            fetch(`backend/data/analysis_results.json?t=${Date.now()}`),
            fetch(`backend/data/shares_outstanding.json?t=${Date.now()}`).catch(() => null)
        ]);
        
        if (!analysisResponse.ok) throw new Error("無法載入分析結果數據");
        analysisData = await analysisResponse.json();
        analysisData.bonds_analysis = sortBondsByRecentDate(analysisData.bonds_analysis || []);
        
        if (sharesResponse && sharesResponse.ok) {
            sharesOutstandingDb = await sharesResponse.json();
        }
        
        // Populate Sector Filter Dropdown
        const sectorFilter = document.getElementById("sector-filter");
        sectorFilter.innerHTML = '<option value="">所有產業族群</option>';
        if (analysisData.sectors) {
            analysisData.sectors.forEach(sec => {
                const opt = document.createElement("option");
                opt.value = sec;
                opt.innerText = sec;
                sectorFilter.appendChild(opt);
            });
        }
        
        // Populate Summary Stats
        populateStats();
        updateDataLastUpdated();
        
        // Populate Table
        populateTable(analysisData.bonds_analysis);
        
        // Select first bond by default to display in chart
        if (analysisData.bonds_analysis.length > 0) {
            selectStock(analysisData.bonds_analysis[0].ticker, analysisData.bonds_analysis[0].company_name);
        }
        
        // Render Strategy Results
        renderStrategyCards();
        
        // Pre-run default backtest to show initial stats
        runBacktest(-5, 5);
        
    } catch (error) {
        console.error("Error loading dashboard data:", error);
        alert("載入數據錯誤，請確認已執行後端分析程式！");
    }
}

function populateStats() {
    const bonds = analysisData.bonds_analysis;
    document.getElementById("stat-total-bonds").innerText = bonds.length;
    
    // Average volatility
    const avgVol = bonds.reduce((sum, b) => sum + b.fluctuation_pct, 0) / bonds.length;
    const avgVolatilityEl = document.getElementById("stat-avg-volatility");
    if (avgVolatilityEl) avgVolatilityEl.innerText = avgVol.toFixed(2) + "%";
}

function renderStrategyCards() {
    // Render strategy cards in UI
    const container = document.getElementById("strategy-cards-container");
    if (!container) return;
    
    container.innerHTML = "";
    
    const sr = analysisData.strategy_results;
    if (!sr) return;
    
    const displayStrategies = [
        { key: "CB_RESOLUTION_TO_EFFECTIVE", name: "可轉債：董事會 ➔ 申報生效", icon: "📋" },
        { key: "CB_EFFECTIVE_TO_PRICING", name: "可轉債：申報生效 ➔ 公告定價", icon: "💰" },
        { key: "CB_PRICING_TO_LISTING", name: "可轉債：公告定價 ➔ 掛牌日", icon: "🚀" },
        { key: "CB_PRICING_TO_POST_LISTING", name: "壓低套利：公告定價 ➔ 掛牌後 19 天", icon: "📉" },
        { key: "PRIVATE_PLACEMENT", name: "策略：私募特定人入股", icon: "🤝" },
        { key: "BUYBACK", name: "策略：庫藏股護盤區間買進", icon: "🛡️" },
        { key: "TENDER_OFFER", name: "策略：公開溢價收購套利", icon: "🎯" }
    ];
    
    displayStrategies.forEach(strat => {
        const data = sr[strat.key];
        if (!data) return;
        
        const card = document.createElement("div");
        card.className = "strategy-card-item";
        
        const winRateClass = data.win_rate >= 60 ? "text-green" : (data.win_rate >= 45 ? "text-yellow" : "text-red");
        const returnClass = data.avg_return >= 0 ? "text-green" : "text-red";
        
        card.innerHTML = `
            <div class="strategy-card-header">
                <span class="strategy-icon">${strat.icon}</span>
                <h4>${strat.name}</h4>
            </div>
            <div class="strategy-stats-row">
                <div class="strat-stat">
                    <span class="strat-lbl">總交易筆數</span>
                    <span class="strat-val">${data.total_trades} 筆</span>
                </div>
                <div class="strat-stat">
                    <span class="strat-lbl">歷史勝率</span>
                    <span class="strat-val ${winRateClass}">${data.win_rate.toFixed(1)}%</span>
                </div>
                <div class="strat-stat">
                    <span class="strat-lbl">平均報酬率</span>
                    <span class="strat-val ${returnClass}">${data.avg_return >= 0 ? "+" : ""}${data.avg_return.toFixed(2)}%</span>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function populateTable(bonds) {
    const tbody = document.getElementById("bonds-table-body");
    tbody.innerHTML = "";
    const orderedBonds = sortBondsByRecentDate(bonds);
    
    if (orderedBonds.length === 0) {
        tbody.innerHTML = `<tr><td colspan="15" class="text-center text-muted">無符合的轉換公司債數據</td></tr>`;
        return;
    }
    
    const fragment = document.createDocumentFragment();
    orderedBonds.forEach(bond => {
        const tr = document.createElement("tr");
        tr.id = `row-${bond.ticker}`;
        
        const annToIssReturnClass = bond.ann_to_iss_return >= 0 ? "text-green" : "text-red";
        const annToIssReturnStr = (bond.ann_to_iss_return >= 0 ? "+" : "") + bond.ann_to_iss_return.toFixed(2) + "%";
        
        const fNetClass = bond.foreign_accum_10d >= 0 ? "text-green" : "text-red";
        const tNetClass = bond.trust_accum_10d >= 0 ? "text-green" : "text-red";
        
        tr.innerHTML = `
            <td><strong>${bond.company_name}</strong></td>
            <td><code>${bond.ticker}</code></td>
            <td><span class="badge live-badge">${bond.sector}</span></td>
            <td>${bond.announcement_date}</td>
            <td>${bond.issue_date}</td>
            <td class="${fNetClass}">${bond.foreign_accum_10d >= 0 ? "+" : ""}${bond.foreign_accum_10d}</td>
            <td class="${tNetClass}">${bond.trust_accum_10d >= 0 ? "+" : ""}${bond.trust_accum_10d}</td>
            <td>$${bond.announcement_price.toFixed(1)}</td>
            <td>$${bond.issue_price.toFixed(1)}</td>
            <td class="${annToIssReturnClass}">${annToIssReturnStr}</td>
            <td>${bond.low_before_date}</td>
            <td>$${bond.low_before_price.toFixed(1)}</td>
            <td>$${bond.high_after_date}</td>
            <td>$${bond.high_after_price.toFixed(1)}</td>
            <td class="text-green"><strong>+${bond.fluctuation_pct.toFixed(1)}%</strong></td>
            <td><a class="action-link" onclick="selectStock('${bond.ticker}', '${bond.company_name}')">查看圖表</a></td>
        `;
        
        fragment.appendChild(tr);
    });
    tbody.appendChild(fragment);
}

function filterAndRenderTable() {
    if (!analysisData) return;
    
    const query = document.getElementById("search-input").value.toLowerCase();
    const sector = document.getElementById("sector-filter").value;
    const foreignMin = parseFloat(document.getElementById("filter-foreign-min").value) || 0;
    const trustMin = parseFloat(document.getElementById("filter-trust-min").value) || 0;
    
    const filtered = analysisData.bonds_analysis.filter(b => {
        const matchesQuery = b.company_name.toLowerCase().includes(query) || b.ticker.toLowerCase().includes(query);
        const matchesSector = sector === "" || b.sector === sector;
        const matchesForeign = b.foreign_accum_10d >= foreignMin;
        const matchesTrust = b.trust_accum_10d >= trustMin;
        return matchesQuery && matchesSector && matchesForeign && matchesTrust;
    });
    
    populateTable(filtered);
}

function setupEventListeners() {
    const debouncedFilterAndRenderTable = debounce(filterAndRenderTable, 120);

    // Search input
    document.getElementById("search-input").addEventListener("input", debouncedFilterAndRenderTable);
    
    // Sector Filter
    document.getElementById("sector-filter").addEventListener("change", filterAndRenderTable);
    
    // Inst Filters
    document.getElementById("filter-foreign-min").addEventListener("input", debouncedFilterAndRenderTable);
    document.getElementById("filter-trust-min").addEventListener("input", debouncedFilterAndRenderTable);
    
    // Run Backtest button
    document.getElementById("btn-run-backtest").addEventListener("click", () => {
        const entry = parseInt(document.getElementById("entry-days").value);
        const exit = parseInt(document.getElementById("exit-days").value);
        runBacktest(entry, exit);
    });
}

async function selectStock(ticker, companyName) {
    selectedStockCode = ticker;
    
    // Highlight table row
    document.querySelectorAll("#bonds-table-body tr").forEach(tr => tr.classList.remove("selected-row"));
    const selectedRow = document.getElementById(`row-${ticker}`);
    if (selectedRow) selectedRow.classList.add("selected-row");
    
    // Update labels
    document.getElementById("stock-ticker-tag").innerText = ticker;
    document.getElementById("selected-stock-title").innerText = `${companyName} (${ticker}) 股價與法人籌碼對照圖`;
    
    // Load prices
    let prices = stockPricesCache[ticker];
    if (!prices) {
        try {
            const response = await fetch(`backend/data/prices/${ticker}.json?t=${Date.now()}`);
            if (!response.ok) throw new Error("無法載入個股股價數據");
            prices = await response.json();
            stockPricesCache[ticker] = prices;
        } catch (e) {
            console.error("Error fetching individual stock prices:", e);
            alert("載入個股歷史股價與籌碼失敗！");
            return;
        }
    }
    
    renderChart(prices, ticker);
}

function renderChart(prices, ticker) {
    const ctx = document.getElementById("stockChart").getContext("2d");
    
    // Find bond announcement and issue date in analysisData
    const bondInfo = analysisData.bonds_analysis.find(b => b.ticker === ticker);
    if (!bondInfo) return;
    
    const labels = prices.map(p => p.date);
    const closePrices = prices.map(p => p.close);
    
    // Calculate cumulative institutional net buying
    let cumForeign = 0;
    let cumTrust = 0;
    const cumForeignData = [];
    const cumTrustData = [];
    
    prices.forEach(p => {
        cumForeign += (p.foreign_net || 0);
        cumTrust += (p.trust_net || 0);
        cumForeignData.push(cumForeign);
        cumTrustData.push(cumTrust);
    });
    
    // Markers dataset
    const markerDataset = {
        label: "關鍵事件點",
        data: prices.map(p => {
            if (p.date === bondInfo.announcement_date) return p.close;
            if (p.date === bondInfo.issue_date) return p.close;
            if (p.date === bondInfo.low_before_date) return p.close;
            if (p.date === bondInfo.high_after_date) return p.close;
            return null;
        }),
        backgroundColor: prices.map(p => {
            if (p.date === bondInfo.announcement_date) return "#fbbf24"; // Yellow
            if (p.date === bondInfo.issue_date) return "#3b82f6"; // Blue
            if (p.date === bondInfo.low_before_date) return "#ef4444"; // Red
            if (p.date === bondInfo.high_after_date) return "#10b981"; // Green
            return "rgba(0,0,0,0)";
        }),
        pointRadius: prices.map(p => {
            if (p.date === bondInfo.announcement_date || p.date === bondInfo.issue_date || 
                p.date === bondInfo.low_before_date || p.date === bondInfo.high_after_date) return 7;
            return 0;
        }),
        type: 'scatter',
        showLine: false,
        yAxisID: 'y'
    };

    if (myChart) {
        myChart.destroy();
    }
    
    myChart = new Chart(ctx, {
        data: {
            labels: labels,
            datasets: [
                {
                    type: 'line',
                    label: "收盤價",
                    data: closePrices,
                    borderColor: "#6366f1",
                    borderWidth: 2,
                    pointRadius: 1,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y'
                },
                {
                    type: 'line',
                    label: "外資累計買超 (張)",
                    data: cumForeignData,
                    borderColor: "#10b981",
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y1'
                },
                {
                    type: 'line',
                    label: "投信累計買超 (張)",
                    data: cumTrustData,
                    borderColor: "#f59e0b",
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.1,
                    yAxisID: 'y1'
                },
                markerDataset
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        color: '#9ca3af'
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const date = context.chart.data.labels[context.dataIndex];
                            let label = `${context.dataset.label}: `;
                            if (context.datasetIndex === 0) {
                                label += `$${context.raw.toFixed(1)}`;
                                if (date === bondInfo.announcement_date) {
                                    label += " (公告發文日 ⚠️)";
                                } else if (date === bondInfo.issue_date) {
                                    label += " (發行上市日 🚀)";
                                } else if (date === bondInfo.low_before_date) {
                                    label += " (發行前15日最低點 📉)";
                                } else if (date === bondInfo.high_after_date) {
                                    label += " (發行後15日最高點 📈)";
                                }
                            } else {
                                label += `${context.raw.toFixed(1)} 張`;
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: "rgba(255, 255, 255, 0.05)"
                    },
                    ticks: {
                        color: "#9ca3af",
                        maxTicksLimit: 12
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: {
                        color: "rgba(255, 255, 255, 0.05)"
                    },
                    ticks: {
                        color: "#9ca3af"
                    },
                    title: {
                        display: true,
                        text: '收盤價 (元)',
                        color: '#9ca3af'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: {
                        drawOnChartArea: false
                    },
                    ticks: {
                        color: "#9ca3af"
                    },
                    title: {
                        display: true,
                        text: '法人累計買超 (張)',
                        color: '#9ca3af'
                    }
                }
            }
        }
    });
}

// Client-side backtesting engine with filters
async function runBacktest(entryOffset, exitOffset) {
    if (!analysisData) return;
    
    let totalTrades = 0;
    let winCount = 0;
    let lossCount = 0;
    let sumReturns = 0;
    
    // Read current filter settings
    const sector = document.getElementById("sector-filter").value;
    const foreignMin = parseFloat(document.getElementById("filter-foreign-min").value) || 0;
    const trustMin = parseFloat(document.getElementById("filter-trust-min").value) || 0;
    
    const bonds = analysisData.bonds_analysis;
    
    for (const bond of bonds) {
        // Apply institutional and sector filters
        if (sector !== "" && bond.sector !== sector) continue;
        if (bond.foreign_accum_10d < foreignMin) continue;
        if (bond.trust_accum_10d < trustMin) continue;
        
        let prices = stockPricesCache[bond.ticker];
        if (!prices) {
            try {
                const response = await fetch(`backend/data/prices/${bond.ticker}.json?t=${Date.now()}`);
                if (response.ok) {
                    prices = await response.json();
                    stockPricesCache[bond.ticker] = prices;
                }
            } catch (e) {
                console.error(`Error loading prices for backtest ticker ${bond.ticker}:`, e);
            }
        }
        
        if (!prices) continue;
        
        const issIdx = prices.findIndex(p => p.date === bond.issue_date);
        if (issIdx === -1) continue;
        
        const buyIdx = issIdx + entryOffset;
        const sellIdx = issIdx + exitOffset;
        
        if (buyIdx >= 0 && buyIdx < prices.length && sellIdx >= 0 && sellIdx < prices.length && buyIdx < sellIdx) {
            const buyPrice = prices[buyIdx].open;
            const sellPrice = prices[sellIdx].close;
            if (buyPrice === null || sellPrice === null || isNaN(buyPrice) || isNaN(sellPrice)) continue;
            const tradeReturn = (sellPrice - buyPrice) / buyPrice * 100;
            
            totalTrades++;
            sumReturns += tradeReturn;
            if (tradeReturn > 0) {
                winCount++;
            } else {
                lossCount++;
            }
        }
    }
    
    const winRate = totalTrades > 0 ? (winCount / totalTrades * 100) : 0;
    const avgReturn = totalTrades > 0 ? (sumReturns / totalTrades) : 0;
    
    // Update UI elements
    document.getElementById("res-total-trades").innerText = totalTrades;
    
    const winRateEl = document.getElementById("res-win-rate");
    winRateEl.innerText = winRate.toFixed(1) + "%";
    winRateEl.className = winRate >= 50 ? "res-val text-green" : "res-val text-red";
    
    const avgReturnEl = document.getElementById("res-avg-return");
    avgReturnEl.innerText = (avgReturn >= 0 ? "+" : "") + avgReturn.toFixed(2) + "%";
    avgReturnEl.className = avgReturn >= 0 ? "res-val text-green" : "res-val text-red";
    
    document.getElementById("res-win-loss-ratio").innerText = `${winCount} 勝 / ${lossCount} 敗`;
    
    // If this is the initial run, update the main header stats
    if (entryOffset === -5 && exitOffset === 5) {
        document.getElementById("stat-win-rate").innerText = winRate.toFixed(1) + "%";
        document.getElementById("stat-avg-return").innerText = (avgReturn >= 0 ? "+" : "") + avgReturn.toFixed(2) + "%";
    }
}

// ------------------------------------------------------------------
// Tab Navigation Routing
// ------------------------------------------------------------------
function switchTab(tabId) {
    // Toggle active state of nav buttons
    document.querySelectorAll(".nav-tab-btn").forEach(btn => {
        btn.classList.remove("text-white", "bg-slate-800");
        btn.classList.add("text-slate-400", "hover:text-white");
    });
    const activeBtn = document.getElementById(`tab-btn-${tabId}`);
    if (activeBtn) {
        activeBtn.classList.add("text-white", "bg-slate-800");
        activeBtn.classList.remove("text-slate-400", "hover:text-white");
    }

    // Toggle panel visibility
    document.querySelectorAll(".tab-content-panel").forEach(panel => panel.classList.remove("active-panel"));
    const activePanel = document.getElementById(`panel-${tabId}`);
    if (activePanel) activePanel.classList.add("active-panel");

    // Load tab-specific data
    if (tabId === "active-tracks") {
        loadActiveTracks();
    } else if (tabId === "success-cases") {
        initSuccessCases();
    } else if (tabId === "bond-report") {
        loadBondStrategyReport();
    }
}

// Expose switchTab globally so onclick events work
window.switchTab = switchTab;

// ------------------------------------------------------------------
// Subway Route Timeline Map Renderer
// ------------------------------------------------------------------
async function loadActiveTracks() {
    const listContainer = document.getElementById("active-tracks-list");
    if (!listContainer) return;

    try {
        const response = await fetch(`backend/data/active_tracks.json?t=${Date.now()}`);
        if (!response.ok) throw new Error("無法載入執行軌道資料");
        const tracks = sortTracksByNearestDate(await response.json());
        updateDataLastUpdated(tracks.flatMap(track => [
            track.expected_listing_date,
            ...(track.stations || []).map(station => station.date)
        ]));

        listContainer.innerHTML = "";

        if (tracks.length === 0) {
            listContainer.innerHTML = `<div class="text-center text-muted py-4">目前無進行中的 SOP 監控個股</div>`;
            return;
        }

        const fragment = document.createDocumentFragment();
        tracks.forEach(track => {
            const card = document.createElement("div");
            card.className = "route-card";

            // Status style
            let badgeClass = "route-badge";
            if (track.status_type === "success") badgeClass += " success";
            if (track.status_type === "failed") badgeClass += " failed";

            // Performance string
            let perfHtml = "";
            if (track.performance) {
                const ret = track.performance.return_pct;
                const retClass = ret >= 0 ? "text-green" : "text-red";
                perfHtml = `
                    <div class="route-perf-badge ${retClass}">
                        帳面回報: ${ret >= 0 ? "+" : ""}${ret.toFixed(2)}% 
                        ($${track.performance.buy_price} ➔ $${track.performance.current_price})
                    </div>
                `;
            }

            // Timeline route type class
            let mapClass = "route-timeline-map";
            if (track.status_type === "success") mapClass += " route-success";
            if (track.status_type === "failed") mapClass += " route-failed";
            if (track.status_type === "pending") mapClass += " route-pending";

            // Render stations
            let stationsHtml = "";
            track.stations.forEach((station, idx) => {
                let stationClass = "station-node";
                if (station.status === "completed") stationClass += " completed";
                if (station.status === "active") stationClass += " active";
                if (station.status === "failed") stationClass += " failed";
                if (station.status === "upcoming") stationClass += " upcoming";

                stationsHtml += `
                    <div class="${stationClass}">
                        <div class="station-dot">${idx + 1}</div>
                        <div class="station-name">${station.name}</div>
                        <div class="station-date">${station.date}</div>
                        <div class="station-desc-tooltip">
                            <strong>${station.name}</strong><br>
                            ${station.description}
                        </div>
                    </div>
                `;
            });

            // Strategy info HTML
            let strategyHtml = "";
            if (track.strategy_info) {
                strategyHtml = `
                    <div class="route-strategy-info text-xs text-slate-400 mt-2.5 flex items-center gap-2 flex-wrap">
                        <span class="bg-indigo-950/60 border border-indigo-900/40 px-2 py-0.5 rounded text-indigo-300 font-medium">${track.strategy_info.name}</span>
                        <span class="bg-emerald-950/60 border border-emerald-900/40 px-2 py-0.5 rounded text-emerald-300 font-medium">勝率: ${track.strategy_info.win_rate.toFixed(1)}%</span>
                        <span class="bg-cyan-950/60 border border-cyan-900/40 px-2 py-0.5 rounded text-cyan-300 font-medium">平均報酬: +${track.strategy_info.avg_return.toFixed(1)}%</span>
                    </div>
                `;
            }

            card.innerHTML = `
                <div class="route-header">
                    <div style="flex: 1;">
                        <div class="route-title-group flex items-center gap-2 flex-wrap">
                            <span class="card-tag">${track.stock_code}</span>
                            <h3 class="font-bold text-slate-100" style="margin: 0;">${track.company_name} (${track.stock_code}) - ${track.bond_name}</h3>
                            <span class="${badgeClass}">${track.status_text}</span>
                        </div>
                        ${strategyHtml}
                    </div>
                    ${perfHtml}
                </div>
                <div class="${mapClass}">
                    ${stationsHtml}
                </div>
            `;
            fragment.appendChild(card);
        });
        listContainer.appendChild(fragment);

    } catch (e) {
        console.error("Error loading active tracks:", e);
        listContainer.innerHTML = `<div class="text-center text-red py-4">加載軌道監控看板失敗，請確認後端狀態。</div>`;
    }
}

// ------------------------------------------------------------------
// Success Cases View Logic
// ------------------------------------------------------------------
const SUCCESS_STRATEGIES = [
    {
        name: "🥇 策略 1: 外資定價前卡位 (勝率100% / 報酬+45.0%)",
        entry: -15,
        exit: 19,
        f_th: 2000,
        t_th: 0,
        desc: "外資在訂價前大舉買超 > 2,000 張，在掛牌日後 19 天進行賣出結算，獲取最佳化的波段利潤。"
    },
    {
        name: "🥈 策略 2: 投信定價前卡位 (勝率100% / 報酬+42.9%)",
        entry: -15,
        exit: 19,
        f_th: -2000,
        t_th: 2000,
        desc: "投信在訂價前大舉買超 > 2,000 張，在掛牌日後 19 天進行賣出結算，專注於投信作帳認養行情。"
    },
    {
        name: "🥉 策略 3: 雙法人共振卡位 (勝率100% / 報酬+42.9%)",
        entry: -15,
        exit: 19,
        f_th: 2000,
        t_th: 2000,
        desc: "外資與投信在訂價前同時買超各 > 2,000 張，此共振效應使現貨在掛牌日前後極易拉抬。"
    },
    {
        name: "📈 策略 4: 投信卡位 + 股本佔比型 (勝率100% / 報酬+43.6%)",
        entry: -15,
        exit: 19,
        desc: "投信在訂價前累積買超 > 2,000 張，且買超金額佔公司總股本超過 0.5%。此策略鎖定中小型投信作帳認養股，排除大型冷門股，歷史勝率高達 100%。",
        customFilter: (bond) => {
            const shares = sharesOutstandingDb[bond.ticker] || 100000000;
            const pct = (bond.trust_accum_10d * 1000) / shares * 100;
            return bond.trust_accum_10d > 2000 && pct > 0.5;
        }
    },
    {
        name: "📊 策略 5: 外資卡位 + 股本佔比型 (勝率92.9% / 報酬+37.2%)",
        entry: -15,
        exit: 19,
        desc: "外資在訂價前累積買超 > 2,000 張，且買超佔公司總股本超過 0.5%。此策略專注於外資主導的中小型可轉債成長股，避開權值股干擾，歷史勝率為 92.9%。",
        customFilter: (bond) => {
            const shares = sharesOutstandingDb[bond.ticker] || 100000000;
            const pct = (bond.foreign_accum_10d * 1000) / shares * 100;
            return bond.foreign_accum_10d > 2000 && pct > 0.5;
        }
    }
];

let activeCaseStrategyIndex = 0;

function initSuccessCases() {
    const tabList = document.getElementById("case-tabs-list");
    if (!tabList) return;

    tabList.innerHTML = "";
    SUCCESS_STRATEGIES.forEach((strat, idx) => {
        const btn = document.createElement("button");
        btn.className = `case-tab-btn ${idx === activeCaseStrategyIndex ? 'active-case-tab' : ''}`;
        btn.innerText = strat.name;
        btn.onclick = () => {
            activeCaseStrategyIndex = idx;
            document.querySelectorAll(".case-tab-btn").forEach((b, i) => {
                if (i === idx) b.classList.add("active-case-tab");
                else b.classList.remove("active-case-tab");
            });
            loadSuccessCaseStrategy(idx);
        };
        tabList.appendChild(btn);
    });

    loadSuccessCaseStrategy(activeCaseStrategyIndex);
}

async function loadSuccessCaseStrategy(index) {
    const strat = SUCCESS_STRATEGIES[index];
    const tbody = document.getElementById("case-trades-table-body");
    const summaryContainer = document.getElementById("selected-case-summary");
    
    if (!tbody || !summaryContainer || !analysisData) return;

    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">正在載入並分析歷史案例明細...</td></tr>`;

    // Render strategy overview
    let thresholdDesc = "";
    if (strat.customFilter) {
        thresholdDesc = "篩選門檻：累積買超 &ge; 2,000張 且 佔個股總股本 &ge; 0.5%";
    } else {
        thresholdDesc = `篩選門檻：外資 &ge; ${strat.f_th}張 / 投信 &ge; ${strat.t_th}張`;
    }

    summaryContainer.innerHTML = `
        <div style="background: rgba(99, 102, 241, 0.05); border: 1px solid rgba(99, 102, 241, 0.2); padding: 1.25rem; border-radius: 12px; margin-top: 1rem;">
            <strong>策略條件說明：</strong> ${strat.desc}<br>
            <span style="font-size: 0.85rem; color: var(--text-secondary);">
                進場時點：T${strat.entry} ➔ 出場時點：T+${strat.exit} | 
                ${thresholdDesc}
            </span>
        </div>
    `;

    const bonds = analysisData.bonds_analysis;
    const trades = [];

    for (const bond of bonds) {
        // Filter criteria
        if (strat.customFilter) {
            if (!strat.customFilter(bond)) continue;
        } else {
            if (bond.foreign_accum_10d < strat.f_th) continue;
            if (bond.trust_accum_10d < strat.t_th) continue;
        }

        // Fetch prices from cache or fetch new
        let prices = stockPricesCache[bond.ticker];
        if (!prices) {
            try {
                const response = await fetch(`backend/data/prices/${bond.ticker}.json?t=${Date.now()}`);
                if (response.ok) {
                    prices = await response.json();
                    stockPricesCache[bond.ticker] = prices;
                }
            } catch (e) {
                console.error(`Error loading prices for success case: ${bond.ticker}`, e);
            }
        }

        if (!prices) continue;

        const issIdx = prices.findIndex(p => p.date === bond.issue_date);
        if (issIdx === -1) continue;

        const buyIdx = issIdx + strat.entry;
        const sellIdx = issIdx + strat.exit;

        if (buyIdx >= 0 && buyIdx < prices.length && sellIdx >= 0 && sellIdx < prices.length && buyIdx < sellIdx) {
            const buyPrice = prices[buyIdx].open;
            const sellPrice = prices[sellIdx].close;
            if (buyPrice === null || sellPrice === null || isNaN(buyPrice) || isNaN(sellPrice)) continue;

            const ret = (sellPrice - buyPrice) / buyPrice * 100;
            const holdDays = sellIdx - buyIdx;

            trades.append ? trades.push({
                name: bond.company_name,
                ticker: bond.ticker,
                buy_date: prices[buyIdx].date,
                buy_price: buyPrice,
                sell_date: prices[sellIdx].date,
                sell_price: sellPrice,
                hold_days: holdDays,
                return_pct: ret
            }) : trades.push({
                name: bond.company_name,
                ticker: bond.ticker,
                buy_date: prices[buyIdx].date,
                buy_price: buyPrice,
                sell_date: prices[sellIdx].date,
                sell_price: sellPrice,
                hold_days: holdDays,
                return_pct: ret
            });
        }
    }

    // Sort trades by return descending
    trades.sort((a, b) => b.return_pct - a.return_pct);

    tbody.innerHTML = "";

    if (trades.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">目前暫無符合該篩選參數的成交紀錄</td></tr>`;
        return;
    }

    trades.forEach(trade => {
        const tr = document.createElement("tr");
        const retClass = trade.return_pct >= 0 ? "text-green" : "text-red";
        
        tr.innerHTML = `
            <td><strong>${trade.name}</strong></td>
            <td><code>${trade.ticker}</code></td>
            <td>${trade.buy_date}</td>
            <td>$${trade.buy_price.toFixed(1)}</td>
            <td>${trade.sell_date}</td>
            <td>$${trade.sell_price.toFixed(1)}</td>
            <td>${trade.hold_days} 天</td>
            <td class="${retClass}"><strong>${trade.return_pct >= 0 ? "+" : ""}${trade.return_pct.toFixed(2)}%</strong></td>
        `;
        tbody.appendChild(tr);
    });
}
window.initSuccessCases = initSuccessCases;


// ==================================================================
// Bond Strategy Annual Report
// ==================================================================

const BOND_STRATEGY_LABELS = {
    CB_RESOLUTION_TO_EFFECTIVE: "董事會至申報生效",
    CB_EFFECTIVE_TO_PRICING: "申報生效至公告定價",
    CB_PRICING_TO_LISTING: "公告定價至掛牌日",
    CB_PRICING_TO_POST_LISTING: "公告定價至掛牌後19日",
    PRIVATE_PLACEMENT: "私募事件策略",
    BUYBACK: "庫藏股事件策略",
    TENDER_OFFER: "公開收購事件策略"
};

let bondReportSubTab = "overview";
let bondTradesPage = 1;
const bondTradesPageSize = 15;
const eliteBondStrategyCount = 4;
const eliteBondInitialCapital = 1000000;
let bondReportTrades = [];
let bondTradesFiltered = [];
let bondPortfolioMetrics = null;
let bondStrategyChartObj = null;
let bondYearlyChartObj = null;

function formatPct(value, digits = 1) {
    if (!Number.isFinite(value)) return "-";
    return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function safeTradeDate(dateValue) {
    return typeof dateValue === "string" && /^\d{4}-\d{2}-\d{2}/.test(dateValue)
        ? dateValue.slice(0, 10)
        : null;
}

function formatCurrency(value) {
    if (!Number.isFinite(value)) return "-";
    return `NT$${Math.round(value).toLocaleString("zh-TW")}`;
}

function getYearEndMark(prices, buyIdx, sellIdx) {
    const buyYear = prices[buyIdx].date.slice(0, 4);
    if (prices[sellIdx].date.slice(0, 4) === buyYear) {
        return {
            exitDate: prices[sellIdx].date,
            exitPrice: Number(prices[sellIdx].close),
            isYearEndMark: false
        };
    }

    const yearEnd = `${buyYear}-12-31`;
    let markIdx = buyIdx;
    for (let idx = buyIdx; idx < prices.length; idx++) {
        if (prices[idx].date > yearEnd) break;
        markIdx = idx;
    }

    return {
        exitDate: prices[markIdx].date,
        exitPrice: Number(prices[markIdx].close),
        isYearEndMark: true
    };
}

async function getPricesForTicker(ticker) {
    let prices = stockPricesCache[ticker];
    if (prices) return prices;

    try {
        const response = await fetch(`backend/data/prices/${ticker}.json?t=${Date.now()}`);
        if (response.ok) {
            prices = await response.json();
            stockPricesCache[ticker] = prices;
            return prices;
        }
    } catch (e) {
        console.error(`Error loading prices for elite bond report: ${ticker}`, e);
    }

    return null;
}

async function buildEliteBondReportTrades() {
    if (!analysisData?.bonds_analysis) return [];

    const rows = [];
    const eliteStrategies = SUCCESS_STRATEGIES.slice(0, eliteBondStrategyCount);

    for (const strategy of eliteStrategies) {
        for (const bond of analysisData.bonds_analysis) {
            if (strategy.customFilter) {
                if (!strategy.customFilter(bond)) continue;
            } else {
                if (bond.foreign_accum_10d < strategy.f_th) continue;
                if (bond.trust_accum_10d < strategy.t_th) continue;
            }

            const prices = await getPricesForTicker(bond.ticker);
            if (!prices) continue;

            const listingIdx = prices.findIndex(p => p.date === bond.issue_date);
            if (listingIdx === -1) continue;

            const buyIdx = listingIdx + strategy.entry;
            const sellIdx = listingIdx + strategy.exit;
            if (buyIdx < 0 || sellIdx >= prices.length || buyIdx >= sellIdx) continue;

            const buyPrice = Number(prices[buyIdx].open);
            const sellPrice = Number(prices[sellIdx].close);
            if (!Number.isFinite(buyPrice) || !Number.isFinite(sellPrice) || buyPrice <= 0) continue;

            const returnPct = (sellPrice - buyPrice) / buyPrice * 100;
            const annualMark = getYearEndMark(prices, buyIdx, sellIdx);
            if (!Number.isFinite(annualMark.exitPrice)) continue;
            const yearReturnPct = (annualMark.exitPrice - buyPrice) / buyPrice * 100;
            const holdDays = sellIdx - buyIdx;
            rows.push({
                strategyName: strategy.name.replace(/^[^ ]+\s*/, ""),
                stockCode: bond.ticker,
                companyName: bond.company_name,
                eventTitle: bond.bond_name || "",
                buyDate: prices[buyIdx].date,
                sellDate: prices[sellIdx].date,
                yearExitDate: annualMark.exitDate,
                buyPrice,
                sellPrice,
                yearExitPrice: annualMark.exitPrice,
                isYearEndMark: annualMark.isYearEndMark,
                holdDays,
                returnPct,
                yearReturnPct
            });
        }
    }

    return simulateYearlyCapital(rows).sort((a, b) => {
        const dateA = a.buyDate || "9999-12-31";
        const dateB = b.buyDate || "9999-12-31";
        return dateB.localeCompare(dateA);
    });
}

function allocateYearClusters(trades, currentCapital, yearInitialCapital, allocated) {
    const ordered = [...trades].sort((a, b) => a.buyDate.localeCompare(b.buyDate) || a.sellDate.localeCompare(b.sellDate));
    let cluster = [];
    let clusterEnd = null;

    function flushCluster(items) {
        if (items.length === 0) return 0;

        const checkpoints = [...new Set(items.flatMap(t => [t.buyDate, t.yearExitDate]))].sort();
        let maxConcurrent = 1;
        checkpoints.forEach(date => {
            const activeCount = items.filter(t => t.buyDate <= date && t.yearExitDate >= date).length;
            maxConcurrent = Math.max(maxConcurrent, activeCount);
        });

        const allocatedCapital = currentCapital / maxConcurrent;
        let clusterProfit = 0;
        items.forEach(trade => {
            const grossProfit = allocatedCapital * trade.yearReturnPct / 100;
            clusterProfit += grossProfit;
            allocated.push({
                ...trade,
                allocatedCapital,
                grossProfit,
                overlapSlots: maxConcurrent,
                capitalReturnPct: grossProfit / yearInitialCapital * 100
            });
        });
        return clusterProfit;
    }

    ordered.forEach(trade => {
        if (!cluster.length) {
            cluster = [trade];
            clusterEnd = trade.yearExitDate;
            return;
        }

        if (trade.buyDate <= clusterEnd) {
            cluster.push(trade);
            if (trade.yearExitDate > clusterEnd) clusterEnd = trade.yearExitDate;
        } else {
            currentCapital += flushCluster(cluster);
            cluster = [trade];
            clusterEnd = trade.yearExitDate;
        }
    });
    currentCapital += flushCluster(cluster);

    return currentCapital;
}

function simulateYearlyCapital(trades) {
    const byYear = {};
    trades.forEach(trade => {
        const year = trade.buyDate?.slice(0, 4);
        if (!year) return;
        if (!byYear[year]) byYear[year] = [];
        byYear[year].push(trade);
    });

    const allocated = [];
    Object.entries(byYear).forEach(([year, yearTrades]) => {
        const endingCapital = allocateYearClusters(yearTrades, eliteBondInitialCapital, eliteBondInitialCapital, allocated);
        allocated.forEach(trade => {
            if (trade.buyDate?.slice(0, 4) === year) {
                trade.simulationYear = year;
                trade.yearEndingCapital = endingCapital;
            }
        });
    });

    return allocated;
}

function calculatePortfolioMetrics(trades) {
    const yearly = {};
    trades.forEach(trade => {
        const year = trade.simulationYear;
        if (!year) return;
        if (!yearly[year]) yearly[year] = { profit: 0, trades: 0, endingCapital: eliteBondInitialCapital };
        yearly[year].profit += trade.grossProfit || 0;
        yearly[year].trades += 1;
        yearly[year].endingCapital = eliteBondInitialCapital + yearly[year].profit;
        yearly[year].returnPct = yearly[year].profit / eliteBondInitialCapital * 100;
    });

    const yearlyRows = Object.values(yearly);
    const averageAnnualReturn = yearlyRows.length
        ? yearlyRows.reduce((sum, row) => sum + row.returnPct, 0) / yearlyRows.length
        : 0;
    const averageEndingCapital = yearlyRows.length
        ? yearlyRows.reduce((sum, row) => sum + row.endingCapital, 0) / yearlyRows.length
        : eliteBondInitialCapital;

    return {
        capital: eliteBondInitialCapital,
        averageAnnualReturn,
        averageEndingCapital,
        yearly
    };
}

function groupedAverage(rows, getKey, getValue = row => row.returnPct) {
    const groups = {};
    rows.forEach(row => {
        const key = getKey(row);
        const value = getValue(row);
        if (!key) return;
        if (!Number.isFinite(value)) return;
        if (!groups[key]) groups[key] = [];
        groups[key].push(value);
    });

    const averages = {};
    Object.entries(groups).forEach(([key, values]) => {
        averages[key] = values.reduce((sum, v) => sum + v, 0) / values.length;
    });
    return averages;
}

function groupedSum(rows, getKey, getValue) {
    const groups = {};
    rows.forEach(row => {
        const key = getKey(row);
        const value = getValue(row);
        if (!key || !Number.isFinite(value)) return;
        groups[key] = (groups[key] || 0) + value;
    });
    return groups;
}

async function loadBondStrategyReport() {
    if (!analysisData) return;

    document.getElementById("bond-total-trades").innerText = "...";
    bondReportTrades = await buildEliteBondReportTrades();
    bondPortfolioMetrics = calculatePortfolioMetrics(bondReportTrades);
    renderBondReportStats();
    renderBondHealthPills();
    renderBondThresholds();

    const searchInput = document.getElementById("bond-trade-search");
    if (searchInput) {
        searchInput.removeEventListener("input", onBondTradeSearchInput);
        searchInput.addEventListener("input", onBondTradeSearchInput);
    }

    renderBondReportActiveSubTab();
}

function renderBondReportStats() {
    const allTrades = bondReportTrades;
    const wins = allTrades.filter(t => t.returnPct > 0).length;
    const overallWinRate = allTrades.length ? wins / allTrades.length * 100 : 0;

    document.getElementById("bond-average-annual-return").innerText = formatPct(bondPortfolioMetrics?.averageAnnualReturn || 0, 2);
    document.getElementById("bond-elite-avg-return").innerText = formatCurrency(bondPortfolioMetrics?.averageEndingCapital || eliteBondInitialCapital);
    document.getElementById("bond-total-trades").innerText = allTrades.length;
    document.getElementById("bond-overall-win-rate").innerText = `${overallWinRate.toFixed(1)}%`;
}

function renderBondHealthPills() {
    const container = document.getElementById("bond-health-pills");
    if (!container) return;

    const strategyMap = {};
    bondReportTrades.forEach(trade => {
        if (!strategyMap[trade.strategyName]) strategyMap[trade.strategyName] = [];
        strategyMap[trade.strategyName].push(trade);
    });

    const rows = Object.entries(strategyMap).map(([name, trades]) => {
        const avgReturn = trades.reduce((sum, t) => sum + t.returnPct, 0) / trades.length;
        const capitalContribution = trades.reduce((sum, t) => sum + (t.grossProfit || 0), 0) / eliteBondInitialCapital * 100;
        const winRate = trades.filter(t => t.returnPct > 0).length / trades.length * 100;
        return { name, totalTrades: trades.length, avgReturn, capitalContribution, winRate };
    }).sort((a, b) => b.capitalContribution - a.capitalContribution);

    const pills = rows.slice(0, 5).map(row => ({
        title: row.name,
        value: formatPct(row.capitalContribution, 2),
        sub: `均報酬 ${formatPct(row.avgReturn, 2)} / 勝率 ${row.winRate.toFixed(1)}%`,
        target: `${row.totalTrades} 筆 / 資金貢獻`
    }));

    container.innerHTML = pills.map(p => `
        <div class="health-pill">
            <span class="health-pill-title">${p.title}</span>
            <span class="health-pill-value">${p.value}</span>
            <span class="text-[10px] text-slate-400 mb-2">${p.sub}</span>
            <span class="health-pill-target">${p.target}</span>
        </div>
    `).join("");
}

function renderBondThresholds() {
    const container = document.getElementById("bond-thresholds");
    if (!container) return;

    const totalTrades = bondReportTrades.length;
    const avgReturn = totalTrades ? bondReportTrades.reduce((sum, t) => sum + t.returnPct, 0) / totalTrades : 0;
    const averageAnnualReturn = bondPortfolioMetrics?.averageAnnualReturn || 0;
    const winRate = totalTrades ? bondReportTrades.filter(t => t.returnPct > 0).length / totalTrades * 100 : 0;
    const years = new Set(bondReportTrades.map(t => t.buyDate?.slice(0, 4)).filter(Boolean));
    const maxOverlap = bondReportTrades.reduce((max, t) => Math.max(max, t.overlapSlots || 1), 1);

    const checks = [
        { label: "只採用外資/投信精華濾網", val: `前 ${eliteBondStrategyCount} 組`, pass: true },
        { label: "精華策略勝率 >= 90%", val: `${winRate.toFixed(1)}%`, pass: winRate >= 90 },
        { label: "平均報酬 >= 40%", val: formatPct(avgReturn, 2), pass: avgReturn >= 40 },
        { label: "平均年度報酬 > 50%", val: formatPct(averageAnnualReturn, 2), pass: averageAnnualReturn > 50 },
        { label: "重疊訊號平均分攤資金", val: `最多 ${maxOverlap} 檔`, pass: maxOverlap >= 1 },
        { label: "涵蓋年度 >= 2 年", val: `${years.size} 年`, pass: years.size >= 2 },
        { label: "進出場固定 T-15 到 T+19", val: "34 交易日", pass: true }
    ];

    container.innerHTML = checks.map(c => `
        <div class="threshold-item">
            <span class="threshold-lbl font-semibold">${c.label}</span>
            <span class="threshold-target">${c.val}</span>
            <span class="threshold-status ${c.pass ? 'pass' : 'fail'}">${c.pass ? '✓' : '✗'}</span>
        </div>
    `).join("");
}

function switchBondReportSubTab(subTabId) {
    bondReportSubTab = subTabId;

    document.querySelectorAll(".sub-tab-btn").forEach(btn => {
        btn.classList.remove("text-white", "bg-slate-800", "active-sub-tab");
        btn.classList.add("text-slate-400", "hover:text-white");
    });

    const activeBtn = document.getElementById(`sub-btn-${subTabId}`);
    if (activeBtn) {
        activeBtn.classList.add("text-white", "bg-slate-800", "active-sub-tab");
        activeBtn.classList.remove("text-slate-400", "hover:text-white");
    }

    document.querySelectorAll(".sub-tab-panel").forEach(panel => panel.classList.remove("active-panel"));
    const activePanel = document.getElementById(`sub-panel-${subTabId}`);
    if (activePanel) activePanel.classList.add("active-panel");

    renderBondReportActiveSubTab();
}

function renderBondReportActiveSubTab() {
    if (bondReportSubTab === "overview") {
        renderBondStrategyOverview();
    } else if (bondReportSubTab === "monthly") {
        renderBondMonthlyHeatmap();
    } else if (bondReportSubTab === "trades") {
        bondTradesPage = 1;
        filterBondTrades();
        renderBondTradesTable();
    } else if (bondReportSubTab === "yearly") {
        renderBondYearlyChart();
    }
}

function renderBondStrategyOverview() {
    const strategyMap = {};
    bondReportTrades.forEach(trade => {
        if (!strategyMap[trade.strategyName]) strategyMap[trade.strategyName] = [];
        strategyMap[trade.strategyName].push(trade);
    });

    const rows = Object.entries(strategyMap)
        .map(([name, trades]) => {
            const returns = trades.map(t => t.returnPct).filter(Number.isFinite);
            const capitalContribution = trades.reduce((sum, t) => sum + (t.grossProfit || 0), 0) / eliteBondInitialCapital * 100;
            return {
                name,
                totalTrades: trades.length,
                winRate: trades.filter(t => t.returnPct > 0).length / trades.length * 100,
                avgReturn: returns.length ? returns.reduce((sum, v) => sum + v, 0) / returns.length : 0,
                capitalContribution,
                best: returns.length ? Math.max(...returns) : null,
                worst: returns.length ? Math.min(...returns) : null
            };
        })
        .filter(row => row.totalTrades > 0)
        .sort((a, b) => b.capitalContribution - a.capitalContribution);

    const tbody = document.getElementById("bond-strategy-summary-body");
    if (tbody) {
        tbody.innerHTML = rows.map(row => `
            <tr>
                <td><strong>${row.name}</strong></td>
                <td>${row.totalTrades}</td>
                <td>${row.winRate.toFixed(1)}%</td>
                <td class="${row.avgReturn >= 0 ? 'text-green' : 'text-red'}"><strong>${formatPct(row.avgReturn, 2)}</strong></td>
                <td class="${row.capitalContribution >= 0 ? 'text-green' : 'text-red'}"><strong>${formatPct(row.capitalContribution, 2)}</strong></td>
                <td class="text-green">${row.best === null ? "-" : formatPct(row.best, 2)}</td>
                <td class="text-red">${row.worst === null ? "-" : formatPct(row.worst, 2)}</td>
            </tr>
        `).join("");
    }

    const ctx = document.getElementById("bondStrategyChart")?.getContext("2d");
    if (!ctx) return;
    if (bondStrategyChartObj) bondStrategyChartObj.destroy();

    bondStrategyChartObj = new Chart(ctx, {
        type: "bar",
        data: {
            labels: rows.map(row => row.name),
            datasets: [
                {
                    label: "資金貢獻報酬率 (%)",
                    data: rows.map(row => Number(row.capitalContribution.toFixed(2))),
                    backgroundColor: rows.map(row => row.capitalContribution >= 0 ? "rgba(16, 185, 129, 0.75)" : "rgba(239, 68, 68, 0.7)"),
                    borderColor: rows.map(row => row.capitalContribution >= 0 ? "#10b981" : "#ef4444"),
                    borderWidth: 1.5,
                    yAxisID: "y"
                },
                {
                    label: "勝率 (%)",
                    data: rows.map(row => Number(row.winRate.toFixed(1))),
                    type: "line",
                    borderColor: "#38bdf8",
                    backgroundColor: "rgba(56, 189, 248, 0.15)",
                    borderWidth: 2,
                    pointRadius: 3,
                    yAxisID: "y1"
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: "#9ca3af" } } },
            scales: {
                x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" } },
                y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" }, title: { display: true, text: "資金貢獻報酬率 (%)", color: "#9ca3af" } },
                y1: { position: "right", grid: { drawOnChartArea: false }, ticks: { color: "#9ca3af" }, title: { display: true, text: "勝率 (%)", color: "#9ca3af" } }
            }
        }
    });
}

function renderBondMonthlyHeatmap() {
    const tbody = document.getElementById("bond-monthly-matrix-body");
    if (!tbody) return;

    const monthGroups = groupedSum(bondReportTrades, row => row.sellDate?.slice(0, 7), row => row.capitalReturnPct);
    const years = [...new Set(Object.keys(monthGroups).map(key => key.slice(0, 4)))].sort().reverse();
    const allMonthReturns = Object.values(monthGroups);

    tbody.innerHTML = years.map(year => {
        const cells = [];
        const yearValues = [];

        for (let m = 1; m <= 12; m++) {
            const key = `${year}-${String(m).padStart(2, "0")}`;
            const val = monthGroups[key];
            if (val === undefined) {
                cells.push(`<td class="heatmap-cell-zero">-</td>`);
            } else {
                yearValues.push(val);
                let cellClass = "";
                if (val > 5.0) cellClass = "heatmap-cell-pos-high";
                else if (val > 1.5) cellClass = "heatmap-cell-pos-med";
                else if (val > 0) cellClass = "heatmap-cell-pos-low";
                else if (val < -5.0) cellClass = "heatmap-cell-neg-high";
                else if (val < -1.5) cellClass = "heatmap-cell-neg-med";
                else cellClass = "heatmap-cell-neg-low";
                cells.push(`<td class="${cellClass}">${formatPct(val, 1)}</td>`);
            }
        }

        const annual = yearValues.length ? yearValues.reduce((sum, v) => sum + v, 0) : null;
        const annualClass = annual === null ? "heatmap-cell-zero" : (annual >= 0 ? "text-green font-bold bg-slate-900/40" : "text-red font-bold bg-slate-900/40");
        return `<tr><td><strong>${year}</strong></td>${cells.join("")}<td class="${annualClass}">${annual === null ? "-" : formatPct(annual, 1)}</td></tr>`;
    }).join("");

    const avgMonthly = allMonthReturns.length ? allMonthReturns.reduce((sum, r) => sum + r, 0) / allMonthReturns.length : 0;
    const winRate = allMonthReturns.length ? allMonthReturns.filter(r => r > 0).length / allMonthReturns.length * 100 : 0;
    document.getElementById("bond-monthly-stats-summary").innerText = `平均月報酬: ${formatPct(avgMonthly, 2)} | 月勝率: ${winRate.toFixed(1)}%`;
}

function onBondTradeSearchInput() {
    bondTradesPage = 1;
    filterBondTrades();
    renderBondTradesTable();
}

function filterBondTrades() {
    const query = (document.getElementById("bond-trade-search")?.value || "").toLowerCase().trim();
    if (!query) {
        bondTradesFiltered = [...bondReportTrades];
        return;
    }

    bondTradesFiltered = bondReportTrades.filter(t =>
        t.strategyName.toLowerCase().includes(query) ||
        t.companyName.toLowerCase().includes(query) ||
        t.stockCode.toLowerCase().includes(query) ||
        t.eventTitle.toLowerCase().includes(query)
    );
}

function renderBondTradesTable() {
    const tbody = document.getElementById("bond-trades-tbody");
    if (!tbody) return;

    tbody.innerHTML = "";
    if (bondTradesFiltered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted">無符合的公司債策略交易明細</td></tr>`;
        document.getElementById("bond-trades-page-info").innerText = "第 0 頁 / 共 0 頁";
        return;
    }

    const totalPages = Math.ceil(bondTradesFiltered.length / bondTradesPageSize);
    if (bondTradesPage > totalPages) bondTradesPage = totalPages;
    if (bondTradesPage < 1) bondTradesPage = 1;

    document.getElementById("bond-trades-page-info").innerText = `第 ${bondTradesPage} 頁 / 共 ${totalPages} 頁 (共 ${bondTradesFiltered.length} 筆)`;

    const startIdx = (bondTradesPage - 1) * bondTradesPageSize;
    const pageTrades = bondTradesFiltered.slice(startIdx, startIdx + bondTradesPageSize);

    tbody.innerHTML = pageTrades.map(trade => {
        const returnClass = trade.returnPct >= 0 ? "text-green" : "text-red";
        return `
            <tr>
                <td><strong>${trade.companyName}</strong></td>
                <td><code>${trade.stockCode}</code></td>
                <td>${trade.strategyName}</td>
                <td>${trade.buyDate || "-"}</td>
                <td>${formatCurrency(trade.allocatedCapital)}</td>
                <td>${Number.isFinite(trade.buyPrice) ? `$${trade.buyPrice.toFixed(1)}` : "-"}</td>
                <td>${trade.sellDate || "-"}</td>
                <td>${Number.isFinite(trade.sellPrice) ? `$${trade.sellPrice.toFixed(1)}` : "-"}</td>
                <td class="${returnClass}"><strong>${formatPct(trade.returnPct, 2)}</strong></td>
                <td class="${trade.capitalReturnPct >= 0 ? 'text-green' : 'text-red'}"><strong>${formatPct(trade.capitalReturnPct, 2)}</strong></td>
            </tr>
        `;
    }).join("");
}

function prevBondTradesPage() {
    if (bondTradesPage > 1) {
        bondTradesPage--;
        renderBondTradesTable();
    }
}

function nextBondTradesPage() {
    const totalPages = Math.ceil(bondTradesFiltered.length / bondTradesPageSize);
    if (bondTradesPage < totalPages) {
        bondTradesPage++;
        renderBondTradesTable();
    }
}

function renderBondYearlyChart() {
    const yearly = bondPortfolioMetrics?.yearly || {};
    const years = Object.keys(yearly).sort();
    const data = years.map(year => Number((yearly[year].returnPct || 0).toFixed(2)));

    const datasets = [{
        label: "100萬資金年度實現報酬 (%)",
        data,
        backgroundColor: data.map(v => v >= 0 ? "rgba(16, 185, 129, 0.75)" : "rgba(239, 68, 68, 0.7)"),
        borderColor: data.map(v => v >= 0 ? "#10b981" : "#ef4444"),
        borderWidth: 1.5
    }];

    const ctx = document.getElementById("bondYearlyChart")?.getContext("2d");
    if (!ctx) return;
    if (bondYearlyChartObj) bondYearlyChartObj.destroy();

    bondYearlyChartObj = new Chart(ctx, {
        type: "bar",
        data: { labels: years, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: "#9ca3af" } },
                tooltip: {
                    callbacks: {
                        label: context => `${context.dataset.label}: ${formatPct(context.raw, 2)}`,
                        afterLabel: context => {
                            const info = yearly[context.label];
                            return info ? `交易筆數: ${info.trades}` : "";
                        }
                    }
                }
            },
            scales: {
                x: { stacked: false, grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" } },
                y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#9ca3af" }, title: { display: true, text: "年度實現報酬率 (%)", color: "#9ca3af" } }
            }
        }
    });
}

window.loadBondStrategyReport = loadBondStrategyReport;
window.switchBondReportSubTab = switchBondReportSubTab;
window.prevBondTradesPage = prevBondTradesPage;
window.nextBondTradesPage = nextBondTradesPage;
