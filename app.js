// Global state
let analysisData = null;
let selectedStockCode = null;
let stockPricesCache = {};
let myChart = null;
let sharesOutstandingDb = {};

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
    document.getElementById("stat-avg-volatility").innerText = avgVol.toFixed(2) + "%";
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
    
    if (bonds.length === 0) {
        tbody.innerHTML = `<tr><td colspan="15" class="text-center text-muted">無符合的轉換公司債數據</td></tr>`;
        return;
    }
    
    bonds.forEach(bond => {
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
        
        tbody.appendChild(tr);
    });
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
    // Search input
    document.getElementById("search-input").addEventListener("input", filterAndRenderTable);
    
    // Sector Filter
    document.getElementById("sector-filter").addEventListener("change", filterAndRenderTable);
    
    // Inst Filters
    document.getElementById("filter-foreign-min").addEventListener("input", filterAndRenderTable);
    document.getElementById("filter-trust-min").addEventListener("input", filterAndRenderTable);
    
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
        const tracks = await response.json();

        listContainer.innerHTML = "";

        if (tracks.length === 0) {
            listContainer.innerHTML = `<div class="text-center text-muted py-4">目前無進行中的 SOP 監控個股</div>`;
            return;
        }

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
            listContainer.appendChild(card);
        });

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

