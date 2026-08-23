// TradingView Backtesting Rankings - Dashboard Logic
document.addEventListener("DOMContentLoaded", () => {
    
    // Application State
    let db = null;
    let selectedStrategyId = null;
    let currentTicker = "SPY"; // Active ticker for detail visualization
    let activeFilter = "GLOBAL"; // Active sorting filter for sidebar
    let activeTab = "tab-chart";
    let equityChart = null; // Chart.js instance

    // Dom Elements
    const elTickerFilter = document.getElementById("ticker-filter");
    const elStrategyList = document.getElementById("strategy-list");
    const elStrategyCount = document.getElementById("strategy-count");
    const elNoSelectionState = document.getElementById("no-selection-state");
    const elDashboardState = document.getElementById("dashboard-state");
    
    // Header Elements
    const elStratRank = document.getElementById("strat-rank");
    const elStratName = document.getElementById("strat-name");
    const elStratDesc = document.getElementById("strat-desc");
    const elStratTags = document.getElementById("strat-tags");
    
    // Agg Metrics Elements
    const elAggReturn = document.getElementById("agg-return");
    const elAggReturnSub = document.getElementById("agg-return-sub");
    const elAggSharpe = document.getElementById("agg-sharpe");
    const elAggSharpeStatus = document.getElementById("agg-sharpe-status");
    const elAggDrawdown = document.getElementById("agg-drawdown");
    const elAggBeaten = document.getElementById("agg-beaten");
    
    // Ticker Details Elements
    const elCurrentTickerName = document.getElementById("current-ticker-name");
    const elTkReturn = document.getElementById("tk-return");
    const elTkBhReturn = document.getElementById("tk-bh-return");
    const elTkDrawdown = document.getElementById("tk-drawdown");
    const elTkBhDrawdown = document.getElementById("tk-bh-drawdown");
    const elTkSharpe = document.getElementById("tk-sharpe");
    const elTkWinrate = document.getElementById("tk-winrate");
    const elTkPf = document.getElementById("tk-pf");
    const elTkTrades = document.getElementById("tk-trades");
    const elTkDuration = document.getElementById("tk-duration");
    const elOutperformanceMargin = document.getElementById("outperformance-margin");
    const elBenchCompBanner = document.getElementById("bench-comp-banner");
    const elTickerChips = document.getElementById("ticker-chips");
    
    // Tables & Tabs Elements
    const elCompareTableBody = document.getElementById("compare-table-body");
    const elTradesTableBody = document.getElementById("trades-table-body");
    const elTradesTickerTitle = document.getElementById("trades-ticker-title");
    
    // Pine Script Elements
    const elPineScriptCode = document.getElementById("pinescript-code");
    const elBtnCopyCode = document.getElementById("btn-copy-code");
    const elToastMessage = document.getElementById("toast-message");

    // -------------------------------------------------------------------------
    // 1. Data Initialization & Dynamic Recalculation
    // -------------------------------------------------------------------------
    const elRecalcBtn = document.getElementById("recalc-btn");
    const elCommissionInput = document.getElementById("commission-input");

    if (elRecalcBtn) {
        elRecalcBtn.addEventListener("click", () => {
            const comm = elCommissionInput.value || 0.4;
            const startDate = document.getElementById("start-date").value;
            const endDate = document.getElementById("end-date").value;
            loadDatabase(comm, startDate, endDate);
        });
    }

    async function loadDatabase(commission = null, startDate = null, endDate = null) {
        try {
            if (commission !== null) {
                elStrategyList.innerHTML = `<li class="loading-item"><i class="fa-solid fa-spinner fa-spin"></i> Recalculando...</li>`;
            }
            
            let url = "../data/results.json";
            if (commission !== null) {
                url = `/api/recalculate?commission=${commission}`;
                if (startDate) url += `&start_date=${startDate}`;
                if (endDate) url += `&end_date=${endDate}`;
            }
            
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error("No se pudo cargar results.json. Asegúrate de iniciar un servidor local.");
            }
            db = await response.json();
            
            
            // Set up UI
            if (commission === null) {
                initUI();
            } else {
                // Just refresh list and current view
                elStrategyCount.textContent = db.ranking.length;
                renderSidebarRanking();
                if (selectedStrategyId) {
                    selectStrategy(selectedStrategyId);
                }
                populateTopAssetsTable();
            }
        } catch (error) {
            console.error(error);
            elStrategyList.innerHTML = `<li class="loading-item text-danger" style="padding:20px;">
                <i class="fa-solid fa-triangle-exclamation" style="font-size:24px;margin-bottom:10px;display:block;"></i>
                <strong>Error al cargar resultados:</strong><br>
                ${error.message}<br><br>
                <small>Ejecuta <code>uv run python -m http.server 8000</code> en el directorio del proyecto y abre la URL en tu navegador.</small>
            </li>`;
        }
    }

    function initUI() {
        elStrategyCount.textContent = db.ranking.length;
        
        // Populate sidebar rankings for the first time
        renderSidebarRanking();
        
        populateTopAssetsTable();
        
        // Select the first strategy by default if available
        if (db.ranking.length > 0) {
            selectStrategy(db.ranking[0].strategy_id);
        } else {
            showNoSelectionState(true);
        }

        checkAIStatus();
    }

    let aiStatusInterval = null;
    let wasRunningAI = false;

    async function checkAIStatus() {
        try {
            const res = await fetch("/api/ai-status");
            if (!res.ok) return;
            const data = await res.json();
            updateAIBanner(data);
            
            if (data.status === "running") {
                wasRunningAI = true;
                if (!aiStatusInterval) {
                    aiStatusInterval = setInterval(checkAIStatus, 3000);
                }
            } else {
                if (aiStatusInterval) {
                    clearInterval(aiStatusInterval);
                    aiStatusInterval = null;
                }
                if (wasRunningAI && data.status === "up_to_date") {
                    wasRunningAI = false;
                    loadDatabase();
                }
            }
        } catch (e) {
            console.warn("No se pudo verificar estado de IA:", e);
        }
    }

    function updateAIBanner(data) {
        const banner = document.getElementById("ai-status-banner");
        const title = document.getElementById("ai-banner-title");
        const desc = document.getElementById("ai-banner-desc");
        const btn = document.getElementById("ai-update-btn");
        const badge = document.getElementById("ai-status-badge");
        if (!banner) return;

        function formatDDMMAAAA(dateStr) {
            if (!dateStr || dateStr === "Desconocido") return dateStr;
            const parts = dateStr.split("-");
            if (parts.length === 3) {
                return `${parts[2]}/${parts[1]}/${parts[0]}`;
            }
            return dateStr;
        }

        const aiDateFmt = formatDDMMAAAA(data.last_ai_date);
        const mktDateFmt = formatDDMMAAAA(data.latest_market_date);

        banner.classList.remove("hidden", "warning", "running", "success");
        if (btn) btn.classList.add("hidden");
        if (badge) badge.classList.add("hidden");

        if (data.status === "outdated") {
            banner.classList.add("warning");
            if (title) title.textContent = "⚠️ Predicciones de IA Desactualizadas";
            if (desc) desc.textContent = `Las señales calculadas llegan hasta el ${aiDateFmt}, pero el mercado avanzó hasta el ${mktDateFmt}. Puedes recalcular en 2º plano.`;
            if (btn) btn.classList.remove("hidden");
        } else if (data.status === "running") {
            banner.classList.add("running");
            if (title) title.textContent = "⏳ Actualizando Oráculo IA en GPU (Segundo Plano)";
            if (desc) desc.textContent = `${data.step_name || 'Calculando modelos neuronales...'} ${data.step ? `(Paso ${data.step}/${data.total})` : ''}`;
        } else if (data.status === "up_to_date") {
            banner.classList.add("success");
            if (title) title.textContent = "✨ Oráculo IA Sincronizado";
            if (desc) desc.textContent = `Modelos neuronales 100% al día con el mercado (${aiDateFmt}).`;
            if (badge) {
                badge.classList.remove("hidden");
                badge.textContent = "Al día";
            }
        } else {
            banner.classList.add("hidden");
        }
    }

    window.startAIUpdate = async function() {
        const btn = document.getElementById("ai-update-btn");
        if (btn) btn.classList.add("hidden");
        try {
            await fetch("/api/update-ai", { method: "POST" });
            checkAIStatus();
        } catch (e) {
            console.error("Error iniciando actualización:", e);
        }
    };

    // -------------------------------------------------------------------------
    // 2. Sidebar Rendering & Sorting
    // -------------------------------------------------------------------------
    function renderSidebarRanking() {
        elStrategyList.innerHTML = "";
        
        // Sort ranking list depending on the activeFilter (GLOBAL or specific ticker)
        let sortedRanking = [...db.ranking];
        
        if (activeFilter !== "GLOBAL") {
            // Sort by return on specific ticker descending
            sortedRanking.sort((a, b) => {
                const returnA = a.ticker_results[activeFilter]?.metrics.total_return || 0;
                const returnB = b.ticker_results[activeFilter]?.metrics.total_return || 0;
                return returnB - returnA;
            });
        } else {
            // Sort by average return descending
            sortedRanking.sort((a, b) => b.aggregate_metrics.avg_return - a.aggregate_metrics.avg_return);
        }

        sortedRanking.forEach((strat, idx) => {
            const li = document.createElement("li");
            li.className = `strategy-item ${strat.strategy_id === selectedStrategyId ? 'active' : ''}`;
            li.dataset.id = strat.strategy_id;
            
            // Calculate label metric
            let metricLabel = "";
            let metricValue = "";
            
            if (activeFilter === "GLOBAL") {
                metricLabel = "Avg Return";
                metricValue = `${strat.aggregate_metrics.avg_return.toFixed(1)}%`;
            } else {
                const tr = strat.ticker_results[activeFilter]?.metrics.total_return || 0;
                metricLabel = `${activeFilter} Return`;
                metricValue = `${tr.toFixed(1)}%`;
            }

            li.innerHTML = `
                <div class="strat-card-header">
                    <span class="strat-card-rank">Rank #${idx + 1}</span>
                    <span class="strat-card-score">${strat.strategy_id}</span>
                </div>
                <div class="strat-card-title">${strat.name}</div>
                <div class="strat-card-metrics">
                    <span>${metricLabel}:</span>
                    <span class="strat-card-return">${metricValue}</span>
                </div>
            `;
            
            li.addEventListener("click", () => selectStrategy(strat.strategy_id));
            elStrategyList.appendChild(li);
        });
    }

    // Handle Active Ticker Filter for Rankings
    elTickerFilter.addEventListener("change", (e) => {
        activeFilter = e.target.value;
        
        if (activeFilter !== "GLOBAL") {
            currentTicker = activeFilter;
        } else {
            currentTicker = "SPY";
        }
        
        // Re-render sidebar rankings
        renderSidebarRanking();
        
        // If we have selected a strategy, update the entire dashboard (metrics, chart, rank)
        if (selectedStrategyId) {
            selectStrategy(selectedStrategyId);
        }
    });

    function updateDashboardHeaderRank() {
        const sortedList = Array.from(elStrategyList.querySelectorAll(".strategy-item"));
        const activeIdx = sortedList.findIndex(li => li.dataset.id === selectedStrategyId);
        if (activeIdx !== -1) {
            elStratRank.textContent = `#${activeIdx + 1}`;
        }
    }

    // -------------------------------------------------------------------------
    // 3. Strategy Selection & Metrics Populating
    // -------------------------------------------------------------------------
    function selectStrategy(strategyId) {
        selectedStrategyId = strategyId;
        showNoSelectionState(false);

        // Highlight sidebar active item
        elStrategyList.querySelectorAll(".strategy-item").forEach(li => {
            if (li.dataset.id === strategyId) {
                li.classList.add("active");
            } else {
                li.classList.remove("active");
            }
        });

        const strategy = db.ranking.find(s => s.strategy_id === strategyId);
        if (!strategy) return;

        // 1. Header Information
        elStratName.textContent = strategy.name;
        elStratDesc.textContent = strategy.description;
        updateDashboardHeaderRank();
        
        // Render Indicators Tags
        elStratTags.innerHTML = "";
        strategy.indicators.forEach(ind => {
            const tag = document.createElement("span");
            tag.className = "tag-item";
            tag.textContent = ind;
            elStratTags.appendChild(tag);
        });

        // 2. Summary Metric Cards (Dynamic depending on activeFilter context)
        let displayReturn, displayCagr, displaySharpe, displayMaxDD, displayBeaten;
        
        if (activeFilter === "GLOBAL") {
            displayReturn = `${strategy.aggregate_metrics.avg_return.toFixed(1)}%`;
            displayCagr = `${strategy.aggregate_metrics.avg_cagr.toFixed(1)}%`;
            displaySharpe = strategy.aggregate_metrics.avg_sharpe.toFixed(2);
            displayMaxDD = `${strategy.aggregate_metrics.avg_max_dd.toFixed(1)}%`;
            const totalTickers = Object.keys(strategy.ticker_results).length;
            displayBeaten = `${strategy.aggregate_metrics.outperform_count} / ${totalTickers}`;
            
            elAggReturnSub.textContent = `CAGR Promedio: ${displayCagr}`;
            elAggSharpeStatus.textContent = getSharpeStatus(strategy.aggregate_metrics.avg_sharpe);
        } else {
            const tkData = strategy.ticker_results[activeFilter];
            displayReturn = `${tkData.metrics.total_return.toFixed(1)}%`;
            displayCagr = `${tkData.metrics.cagr.toFixed(1)}%`;
            displaySharpe = tkData.metrics.sharpe.toFixed(2);
            displayMaxDD = `${tkData.metrics.max_drawdown.toFixed(1)}%`;
            displayBeaten = tkData.outperformed ? "Superado" : "No Superado";
            
            elAggReturnSub.textContent = `CAGR en ${activeFilter}: ${displayCagr}`;
            elAggSharpeStatus.textContent = getSharpeStatus(tkData.metrics.sharpe);
        }
        
        elAggReturn.textContent = displayReturn;
        elAggSharpe.textContent = displaySharpe;
        elAggDrawdown.textContent = displayMaxDD;
        elAggBeaten.textContent = displayBeaten;

        // 3. Render Ticker Selector Chips for Chart tab
        renderTickerChips(strategy);

        // 4. Update current ticker detail & plot equity curve
        // Keep the previous selection if it's one of the options, otherwise fallback to SPY
        if (!strategy.ticker_results[currentTicker]) {
            currentTicker = "SPY";
        }
        updateTickerDetails(strategy, currentTicker);

        // 5. Populate Ticker Breakdown Comparison Table
        populateComparisonTable(strategy);

        // 6. Populate Pine Script v5 Code
        elPineScriptCode.textContent = strategy.pinescript;

        // Reset scroll position of code container
        elPineScriptCode.parentElement.parentElement.scrollTop = 0;
    }

    function getSharpeStatus(val) {
        if (val >= 2) return "Excelente";
        if (val >= 1.5) return "Muy Bueno";
        if (val >= 1.0) return "Bueno";
        if (val >= 0.5) return "Moderado";
        return "Bajo/Riesgoso";
    }

    function showNoSelectionState(show) {
        if (show) {
            elNoSelectionState.classList.remove("hidden");
            elDashboardState.classList.add("hidden");
        } else {
            elNoSelectionState.classList.add("hidden");
            elDashboardState.classList.remove("hidden");
        }
    }

    // -------------------------------------------------------------------------
    // 4. Ticker Chips & Specific Ticker Details (Chart Tab)
    // -------------------------------------------------------------------------
    function renderTickerChips(strategy) {
        elTickerChips.innerHTML = "";
        
        // Add SPY, QQQ, etc. dynamically
        const tickers = Object.keys(strategy.ticker_results);
        tickers.forEach(tk => {
            const chip = document.createElement("div");
            chip.className = `ticker-chip ${tk === currentTicker ? 'active' : ''}`;
            chip.textContent = tk;
            
            chip.addEventListener("click", () => {
                currentTicker = tk;
                elTickerChips.querySelectorAll(".ticker-chip").forEach(c => c.classList.remove("active"));
                chip.classList.add("active");
                
                updateTickerDetails(strategy, tk);
            });
            elTickerChips.appendChild(chip);
        });
    }

    function updateTickerDetails(strategy, ticker) {
        const tkData = strategy.ticker_results[ticker];
        const tkBh = db.benchmarks[ticker];
        if (!tkData || !tkBh) return;

        // UI Labels
        elCurrentTickerName.textContent = ticker;
        elTradesTickerTitle.textContent = ticker;
        
        elTkReturn.textContent = `${tkData.metrics.total_return.toFixed(1)}%`;
        elTkBhReturn.textContent = `${tkBh.total_return.toFixed(1)}%`;
        
        elTkDrawdown.textContent = `${tkData.metrics.max_drawdown.toFixed(1)}%`;
        elTkBhDrawdown.textContent = `${tkBh.max_drawdown.toFixed(1)}%`;
        
        elTkSharpe.textContent = tkData.metrics.sharpe.toFixed(2);
        elTkWinrate.textContent = `${tkData.metrics.win_rate.toFixed(1)}%`;
        elTkPf.textContent = tkData.metrics.profit_factor.toFixed(2);
        elTkTrades.textContent = tkData.metrics.num_trades;
        elTkDuration.textContent = `${Math.round(tkData.metrics.avg_duration)} días`;

        // Style return indicators
        elTkReturn.className = tkData.metrics.total_return >= 0 ? "text-success" : "text-danger";
        elTkDrawdown.className = "text-danger";

        // Performance banner
        const diff = tkData.metrics.total_return - tkBh.total_return;
        elOutperformanceMargin.textContent = `${Math.abs(diff).toFixed(1)}%`;
        
        if (diff >= 0) {
            elBenchCompBanner.className = "bench-comparison-card";
            elBenchCompBanner.innerHTML = `<i class="fa-solid fa-circle-check text-success"></i>
                <span>¡Supera a Buy & Hold por <strong id="outperformance-margin">${diff.toFixed(1)}%</strong>!</span>`;
        } else {
            elBenchCompBanner.className = "bench-comparison-card beaten-false";
            elBenchCompBanner.innerHTML = `<i class="fa-solid fa-circle-xmark text-danger"></i>
                <span>Rinde <strong id="outperformance-margin">${Math.abs(diff).toFixed(1)}%</strong> menos que Buy & Hold</span>`;
        }

        // Draw Equity Curves
        renderEquityChart(tkData.equity_curve, tkBh.equity_curve, ticker);

        // Populate Recent Trades Table
        populateTradesTable(tkData.trades);
    }

    // -------------------------------------------------------------------------
    // 5. Chart.js Equity Curve Graph
    // -------------------------------------------------------------------------
    function renderEquityChart(strategyCurve, benchmarkCurve, tickerName) {
        if (equityChart) {
            equityChart.destroy();
        }

        // Align dates
        const dates = strategyCurve.map(pt => pt.date);
        const strategyValues = strategyCurve.map(pt => pt.value);
        
        // Map benchmark values. Dates might be slightly misaligned due to decimation steps,
        // so we map benchmark values to closest dates or align indexing.
        // Since we decimated them with the same step, lengths match closely.
        // Let's map benchmark values directly based on matching indices to keep it simple.
        const benchmarkValues = benchmarkCurve.map(pt => pt.value);

        const ctx = document.getElementById("equityChart").getContext("2d");
        
        // Custom Area Gradient
        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, "rgba(92, 96, 245, 0.25)");
        gradient.addColorStop(1, "rgba(92, 96, 245, 0.0)");

        equityChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: dates,
                datasets: [
                    {
                        label: 'Estrategia',
                        data: strategyValues,
                        borderColor: '#5c60f5',
                        borderWidth: 2,
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.15,
                        pointRadius: 0,
                        pointHoverRadius: 5
                    },
                    {
                        label: 'Buy & Hold (Referencia)',
                        data: benchmarkValues,
                        borderColor: 'rgba(255, 179, 0, 0.8)',
                        borderWidth: 1.5,
                        borderDash: [5, 5],
                        backgroundColor: 'transparent',
                        fill: false,
                        tension: 0.15,
                        pointRadius: 0,
                        pointHoverRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            color: '#8a94a6',
                            font: {
                                family: 'Inter',
                                size: 11
                            }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 17, 24, 0.95)',
                        titleColor: '#f5f6fa',
                        bodyColor: '#8a94a6',
                        borderColor: 'rgba(255, 255, 255, 0.08)',
                        borderWidth: 1,
                        padding: 10,
                        font: {
                            family: 'Inter'
                        },
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed.y !== null) {
                                    label += new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(context.parsed.y);
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.02)'
                        },
                        ticks: {
                            color: '#8a94a6',
                            font: { size: 10 },
                            maxTicksLimit: 8
                        }
                    },
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.02)'
                        },
                        ticks: {
                            color: '#8a94a6',
                            font: { size: 10 },
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });
    }

    // -------------------------------------------------------------------------
    // 6. Cross-Ticker Breakdown Table
    // -------------------------------------------------------------------------
    function getSignalBadge(signal) {
        if (signal === "BUY") {
            return '<span style="color: #39ff14; font-weight: bold; text-shadow: 0 0 5px #39ff14;">BUY</span>';
        } else if (signal === "SELL") {
            return '<span style="color: #ff3333; font-weight: bold;">SELL</span>';
        } else {
            return `<span style="color: #888888; font-weight: bold;">${signal || "WAIT"}</span>`;
        }
    }

    function populateComparisonTable(strategy) {
        elCompareTableBody.innerHTML = "";
        
        const tickers = Object.keys(strategy.ticker_results);
        
        tickers.forEach(tk => {
            const tkData = strategy.ticker_results[tk];
            const tkBh = db.benchmarks[tk];
            if (!tkData || !tkBh) return;

            const diff = tkData.metrics.total_return - tkBh.total_return;
            const diffClass = diff >= 0 ? "text-success" : "text-danger";
            const diffPrefix = diff >= 0 ? "+" : "";

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td class="compare-row-ticker">${tk}</td>
                <td class="${tkData.metrics.total_return >= 0 ? 'text-success' : 'text-danger'} font-bold">${tkData.metrics.total_return.toFixed(1)}%</td>
                <td>${tkBh.total_return.toFixed(1)}%</td>
                <td class="${diffClass} font-bold">${diffPrefix}${diff.toFixed(1)}%</td>
                <td class="text-danger">${tkData.metrics.max_drawdown.toFixed(1)}%</td>
                <td>${tkBh.max_drawdown.toFixed(1)}%</td>
                <td>${tkData.metrics.sharpe.toFixed(2)}</td>
                <td>${tkData.metrics.num_trades}</td>
                <td>${tkData.metrics.win_rate.toFixed(1)}%</td>
                <td>${getSignalBadge(tkData.metrics.current_signal)}</td>
                <td class="live-price-cell" data-ticker="${tk}" data-last-price="${tkData.metrics.current_price}">$${tkData.metrics.current_price.toFixed(2)}</td>
                <td>
                    <span class="badge ${tkData.outperformed ? 'badge-success' : 'badge-danger'}">
                        ${tkData.outperformed ? 'Superó B&H' : 'No Superó'}
                    </span>
                </td>
                <td>${tkData.metrics.exit_threshold || '-'}</td>
            `;
            
            // Double click row to select that ticker in the dashboard chart
            tr.addEventListener("click", () => {
                currentTicker = tk;
                
                // Swap back to the chart tab to view details
                switchTab("tab-chart");
                
                // Highlight the correct chip in UI
                elTickerChips.querySelectorAll(".ticker-chip").forEach(chip => {
                    if (chip.textContent === tk) {
                        chip.classList.add("active");
                    } else {
                        chip.classList.remove("active");
                    }
                });
                
                updateTickerDetails(strategy, tk);
            });
            
            elCompareTableBody.appendChild(tr);
        });
    }

    // -------------------------------------------------------------------------
    // 6.5. Top Assets Table
    // -------------------------------------------------------------------------
    function populateTopAssetsTable() {
        const elTopAssetsTableBody = document.getElementById("top-assets-table-body");
        if (!elTopAssetsTableBody) return;
        elTopAssetsTableBody.innerHTML = "";
        
        const tickers = db.metadata.tickers;
        
        tickers.forEach(tk => {
            // Find the best strategy for this ticker
            let bestStrat = null;
            let maxReturn = -Infinity;
            
            db.ranking.forEach(strat => {
                const tkData = strat.ticker_results[tk];
                if (tkData && tkData.metrics.total_return > maxReturn) {
                    maxReturn = tkData.metrics.total_return;
                    bestStrat = strat;
                }
            });
            
            if (!bestStrat) return;
            
            const tkData = bestStrat.ticker_results[tk];
            const tkBh = db.benchmarks[tk];
            if (!tkData || !tkBh) return;

            const diff = tkData.metrics.total_return - tkBh.total_return;
            const diffClass = diff >= 0 ? "text-success" : "text-danger";
            const diffPrefix = diff >= 0 ? "+" : "";

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td class="compare-row-ticker">${tk}</td>
                <td><a href="#" class="strategy-link" data-id="${bestStrat.strategy_id}" style="color: #5c60f5; text-decoration: underline; font-weight: bold;">${bestStrat.strategy_id}</a></td>
                <td class="${tkData.metrics.total_return >= 0 ? 'text-success' : 'text-danger'} font-bold">${tkData.metrics.total_return.toFixed(1)}%</td>
                <td>${tkBh.total_return.toFixed(1)}%</td>
                <td class="${diffClass} font-bold">${diffPrefix}${diff.toFixed(1)}%</td>
                <td class="text-danger">${tkData.metrics.max_drawdown.toFixed(1)}%</td>
                <td>${tkBh.max_drawdown.toFixed(1)}%</td>
                <td>${tkData.metrics.sharpe.toFixed(2)}</td>
                <td>${tkData.metrics.num_trades}</td>
                <td>${tkData.metrics.win_rate.toFixed(1)}%</td>
                <td>${getSignalBadge(tkData.metrics.current_signal)}</td>
                <td>
                    <span class="badge ${tkData.outperformed ? 'badge-success' : 'badge-danger'}">
                        ${tkData.outperformed ? 'Superó B&H' : 'No Superó'}
                    </span>
                </td>
            `;
            
            // Add click listener to the strategy link
            const link = tr.querySelector(".strategy-link");
            link.addEventListener("click", (e) => {
                e.preventDefault();
                selectStrategy(bestStrat.strategy_id);
                // Optionally scroll to top
                window.scrollTo({ top: 0, behavior: "smooth" });
            });
            
            elTopAssetsTableBody.appendChild(tr);
        });
    }

    // -------------------------------------------------------------------------
    // 7. Trade Log Table
    // -------------------------------------------------------------------------
    function populateTradesTable(trades) {
        elTradesTableBody.innerHTML = "";
        
        if (!trades || trades.length === 0) {
            elTradesTableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:30px;">
                No se registran operaciones en el historial para este activo.
            </td></tr>`;
            return;
        }

        // Show all trades (reverse chronological order - newest first)
        const recentTrades = [...trades].reverse();
        
        recentTrades.forEach((trade, idx) => {
            const retClass = trade.pct_return >= 0 ? "text-success" : "text-danger";
            const retPrefix = trade.pct_return >= 0 ? "+" : "";

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${trades.length - idx}</td>
                <td>${trade.entry_date}</td>
                <td>$${trade.entry_price.toFixed(2)}</td>
                <td>${trade.exit_date}</td>
                <td>$${trade.exit_price.toFixed(2)}</td>
                <td>${trade.duration_days} días</td>
                <td class="${retClass} font-bold">${retPrefix}${trade.pct_return.toFixed(2)}%</td>
                <td><span style="font-size:11px;opacity:0.8;">${trade.reason}</span></td>
            `;
            elTradesTableBody.appendChild(tr);
        });
    }

    // -------------------------------------------------------------------------
    // 8. Clipboard Utilities & UI Interactivity
    // -------------------------------------------------------------------------
    elBtnCopyCode.addEventListener("click", () => {
        const code = elPineScriptCode.textContent;
        navigator.clipboard.writeText(code).then(() => {
            // Show toast
            elToastMessage.classList.add("show");
            setTimeout(() => {
                elToastMessage.classList.remove("show");
            }, 3000);
        }).catch(err => {
            alert("No se pudo copiar el código: " + err);
        });
    });

    // Tab Navigation
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.dataset.tab;
            switchTab(targetTab);
        });
    });

    function switchTab(tabId) {
        activeTab = tabId;
        
        // Buttons highlight
        document.querySelectorAll(".tab-btn").forEach(b => {
            if (b.dataset.tab === tabId) {
                b.classList.add("active");
            } else {
                b.classList.remove("active");
            }
        });
        
        // Contents switch
        document.querySelectorAll(".tab-content").forEach(content => {
            if (content.id === tabId) {
                content.classList.add("active");
            } else {
                content.classList.remove("active");
            }
        });

        // Trigger chart redraw to handle resizing if swapping back to chart
        if (tabId === "tab-chart" && equityChart) {
            setTimeout(() => {
                equityChart.resize();
            }, 50);
        }
    }

    // -------------------------------------------------------------------------
    // 9. Live Price Polling (10s)
    // -------------------------------------------------------------------------
    setInterval(async () => {
        try {
            const res = await fetch('/api/live-prices');
            if (!res.ok) return;
            const prices = await res.json();
            
            // Update table cells
            document.querySelectorAll('.live-price-cell').forEach(cell => {
                const tk = cell.getAttribute('data-ticker');
                if (prices[tk]) {
                    const newPrice = prices[tk];
                    const oldPrice = parseFloat(cell.getAttribute('data-last-price'));
                    
                    if (newPrice !== oldPrice) {
                        cell.innerHTML = `$${newPrice.toFixed(2)}`;
                        cell.setAttribute('data-last-price', newPrice);
                        
                        // Flash red or green
                        cell.classList.remove('flash-green', 'flash-red');
                        // Force reflow to restart animation
                        void cell.offsetWidth;
                        
                        if (newPrice > oldPrice) {
                            cell.classList.add('flash-green');
                        } else {
                            cell.classList.add('flash-red');
                        }
                    }
                }
            });
        } catch (e) {
            // Ignore polling errors silently
        }
    }, 10000);

    // -------------------------------------------------------------------------
    // Start Load (With Server Readiness Polling)
    // -------------------------------------------------------------------------
    const elStartupLoader = document.getElementById("startup-loader");
    const elLoaderStatusText = document.getElementById("loader-status-text");
    
    // -------------------------------------------------------------------------
    // LIVE SCANNER DASHBOARD LOGIC (SS11 & AIS11 GPU 300 TICKERS)
    // -------------------------------------------------------------------------
    let liveScannerData = null;
    let selectedScannerStrategy = "SS11"; // SS11, AIS11, COMBO
    let selectedScannerUniverse = "ALL";  // ALL, US, CRYPTO, BUY_ONLY

    const elNavBtnScanner = document.getElementById("nav-btn-scanner");
    const elNavBtnBacktester = document.getElementById("nav-btn-backtester");
    const elScannerViewPanel = document.getElementById("scanner-view-panel");

    const elGpuNameText = document.getElementById("gpu-name-text");
    const elGpuCudaBadge = document.getElementById("gpu-cuda-badge");

    const elMacroGuardBanner = document.getElementById("macro-guard-banner");
    const elMacroIcon = document.getElementById("macro-icon");
    const elMacroStatusTitle = document.getElementById("macro-status-title");
    const elMacroStatusDesc = document.getElementById("macro-status-desc");
    const elMacroStatusTag = document.getElementById("macro-status-tag");
    const elBtnRefreshScanner = document.getElementById("btn-refresh-scanner");

    const elOpportunitiesCardsGrid = document.getElementById("opportunities-cards-grid");
    const elBuyCountBadge = document.getElementById("buy-count-badge");
    const elLiveScannerTbody = document.getElementById("live-scanner-tbody");
    const elScannerSearchInput = document.getElementById("scanner-search-input");

    const elTvTradeLogPanel = document.getElementById("tv-trade-log-panel");
    const elBtnCloseTvTrades = document.getElementById("btn-close-tv-trades");
    const elSelectedTradeTicker = document.getElementById("selected-trade-ticker");
    const elSelectedTradeStrat = document.getElementById("selected-trade-strat");
    const elTvNetProfit = document.getElementById("tv-net-profit");
    const elTvProfitFactor = document.getElementById("tv-profit-factor");
    const elTvWinRate = document.getElementById("tv-win-rate");
    const elTvTotalTrades = document.getElementById("tv-total-trades");
    const elTvTradesTbody = document.getElementById("tv-trades-tbody");

    // Top Navigation View Switcher
    if (elNavBtnScanner && elNavBtnBacktester) {
        elNavBtnScanner.addEventListener("click", () => {
            elNavBtnScanner.classList.add("active");
            elNavBtnBacktester.classList.remove("active");
            if (elScannerViewPanel) elScannerViewPanel.classList.remove("hidden");
            if (elDashboardState) elDashboardState.classList.add("hidden");
            if (elNoSelectionState) elNoSelectionState.classList.add("hidden");
        });

        elNavBtnBacktester.addEventListener("click", () => {
            elNavBtnBacktester.classList.add("active");
            elNavBtnScanner.classList.remove("active");
            if (elScannerViewPanel) elScannerViewPanel.classList.add("hidden");
            if (selectedStrategyId) {
                if (elDashboardState) elDashboardState.classList.remove("hidden");
                if (elNoSelectionState) elNoSelectionState.classList.add("hidden");
            } else {
                if (elDashboardState) elDashboardState.classList.add("hidden");
                if (elNoSelectionState) elNoSelectionState.classList.remove("hidden");
            }
        });
    }

    // Hardware GPU Detection
    async function loadHardwareStatus() {
        try {
            const res = await fetch('/api/hardware');
            if (res.ok) {
                const hw = await res.json();
                if (elGpuNameText) {
                    if (hw.cuda_available) {
                        elGpuNameText.textContent = `⚡ NVIDIA CUDA GPU: ${hw.device_name}`;
                    } else {
                        elGpuNameText.textContent = `CPU Processing (${hw.device_name})`;
                    }
                }
            }
        } catch (e) {
            if (elGpuNameText) elGpuNameText.textContent = "Hardware Engine Ready";
        }
    }

    // Strategy & Universe Pills Listeners
    document.querySelectorAll("#strategy-pill-group .pill-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll("#strategy-pill-group .pill-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            selectedScannerStrategy = btn.getAttribute("data-strat");
            renderLiveScannerData();
        });
    });

    document.querySelectorAll("#universe-pill-group .pill-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll("#universe-pill-group .pill-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            selectedScannerUniverse = btn.getAttribute("data-univ");
            renderLiveScannerData();
        });
    });

    if (elBtnRefreshScanner) {
        elBtnRefreshScanner.addEventListener("click", () => {
            fetchLiveScanner(true);
        });
    }

    if (elScannerSearchInput) {
        elScannerSearchInput.addEventListener("input", () => {
            renderLiveScannerData();
        });
    }

    if (elBtnCloseTvTrades) {
        elBtnCloseTvTrades.addEventListener("click", () => {
            if (elTvTradeLogPanel) elTvTradeLogPanel.classList.add("hidden");
        });
    }

    // Fetch Live Scanner Data from API
    async function fetchLiveScanner(forceRefresh = false) {
        if (elBtnRefreshScanner) {
            elBtnRefreshScanner.disabled = true;
            elBtnRefreshScanner.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Escaneando...`;
        }

        try {
            const url = forceRefresh ? '/api/live-scanner?refresh=true' : '/api/live-scanner';
            const res = await fetch(url);
            if (res.ok) {
                liveScannerData = await res.json();
                renderLiveScannerData();
            }
        } catch (e) {
            console.error("Error fetching live scanner:", e);
        } finally {
            if (elBtnRefreshScanner) {
                elBtnRefreshScanner.disabled = false;
                elBtnRefreshScanner.innerHTML = `<i class="fa-solid fa-rotate"></i> Escanear Cotizaciones`;
            }
        }
    }

    // Render Scanner Data
    function renderLiveScannerData() {
        if (!liveScannerData) return;

        // 1. Render Macro Guard Banner
        const mg = liveScannerData.macro_guard;
        if (mg && elMacroGuardBanner) {
            if (mg.is_active) {
                elMacroGuardBanner.classList.add("danger");
                if (elMacroIcon) elMacroIcon.className = "fa-solid fa-triangle-exclamation macro-icon text-danger";
                if (elMacroStatusTitle) elMacroStatusTitle.textContent = "🚨 CRASH SISTÉMICO MACRO DETECTADO (SPY)";
                if (elMacroStatusDesc) elMacroStatusDesc.textContent = `Filtro Macro activado: Caída brusca en SPY. Capital en Liquidez por ${mg.days_remaining} sesiones restantes.`;
                if (elMacroStatusTag) elMacroStatusTag.textContent = `CRASH ACTIVO (${mg.days_remaining}d)`;
            } else {
                elMacroGuardBanner.classList.remove("danger");
                if (elMacroIcon) elMacroIcon.className = "fa-solid fa-shield-halved macro-icon text-success";
                if (elMacroStatusTitle) elMacroStatusTitle.textContent = "🟢 Filtro Macro Anti-Crash Global: MERCADO SEGURO";
                if (elMacroStatusDesc) elMacroStatusDesc.textContent = "El índice S&P 500 se encuentra estable. Las estrategias están operando con normalidad.";
                if (elMacroStatusTag) elMacroStatusTag.textContent = "MERCADO SEGURO (SPY OK)";
            }
        }

        // Determine list of signals based on strategy pill
        let list = [];
        if (selectedScannerStrategy === "SS11") {
            list = liveScannerData.ss11_signals || [];
        } else if (selectedScannerStrategy === "AIS11") {
            list = liveScannerData.ais11_signals || [];
        } else {
            // COMBO view
            list = liveScannerData.ss11_signals || [];
        }

        // Apply Universe Filter
        const searchTerm = (elScannerSearchInput ? elScannerSearchInput.value : "").trim().toUpperCase();
        let filtered = list.filter(item => {
            if (searchTerm && !item.ticker.toUpperCase().includes(searchTerm)) {
                return false;
            }
            if (selectedScannerUniverse === "US") return item.category === "US Stock";
            if (selectedScannerUniverse === "CRYPTO") return item.category === "Crypto";
            if (selectedScannerUniverse === "BUY_ONLY") return item.signal === "BUY";
            return true;
        });

        // 2. Render Opportunities Cards (BUY signals)
        const buyItems = list.filter(item => item.signal === "BUY");
        if (elBuyCountBadge) elBuyCountBadge.textContent = `${buyItems.length} Activos en BUY`;

        if (elOpportunitiesCardsGrid) {
            if (buyItems.length === 0) {
                elOpportunitiesCardsGrid.innerHTML = `
                    <div class="empty-cards-notice">
                        <i class="fa-solid fa-shield-cat" style="font-size: 24px; margin-bottom: 8px; color: var(--text-muted); display: block;"></i>
                        No hay señales de compra activas en este instante. El sistema está protegiendo el capital o en espera de confirmación.
                    </div>
                `;
            } else {
                elOpportunitiesCardsGrid.innerHTML = buyItems.map(item => `
                    <div class="opp-card">
                        <div class="opp-card-header">
                            <span class="opp-ticker">${item.ticker}</span>
                            <span class="opp-cat">${item.category}</span>
                        </div>
                        <div class="opp-price-row">
                            <span class="opp-price">$${item.price.toFixed(item.price > 1 ? 2 : 4)}</span>
                            <span class="opp-change ${item.change_24h >= 0 ? 'text-success' : 'text-danger'}">
                                ${item.change_24h >= 0 ? '+' : ''}${item.change_24h.toFixed(2)}%
                            </span>
                        </div>
                        <div class="opp-details-grid">
                            <div>
                                <span>Dist. Stop Loss (-15%)</span>
                                <strong class="${item.dist_sl_pct >= 0 ? 'text-success' : 'text-danger'}">${item.dist_sl_pct > 0 ? '+' : ''}${item.dist_sl_pct.toFixed(1)}%</strong>
                            </div>
                            <div>
                                <span>Dist. Recup. SMA(20)</span>
                                <strong class="${item.dist_sma20_pct >= 0 ? 'text-success' : 'text-danger'}">${item.dist_sma20_pct > 0 ? '+' : ''}${item.dist_sma20_pct.toFixed(1)}%</strong>
                            </div>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
                            <span class="badge-signal buy"><i class="fa-solid fa-circle"></i> BUY</span>
                            <button class="btn btn-secondary btn-view-trades" data-ticker="${item.ticker}" style="font-size: 11px; padding: 4px 10px;">
                                <i class="fa-solid fa-list-check"></i> Ver Trades
                            </button>
                        </div>
                    </div>
                `).join('');
            }
        }

        // 3. Render Live Signals Table
        if (elLiveScannerTbody) {
            if (filtered.length === 0) {
                elLiveScannerTbody.innerHTML = `<tr><td colspan="9" class="text-center p-4 text-muted">No se encontraron activos para los filtros seleccionados.</td></tr>`;
            } else {
                elLiveScannerTbody.innerHTML = filtered.map(item => {
                    const sigClass = item.signal.toLowerCase();
                    const sigIcon = item.signal === 'BUY' ? 'fa-circle-dot' : (item.signal === 'HOLD' ? 'fa-lock' : (item.signal === 'SELL' ? 'fa-triangle-exclamation' : 'fa-clock'));
                    const floatPnl = item.metrics.floating_pnl_pct || 0.0;
                    
                    return `
                        <tr>
                            <td><strong style="font-family: var(--font-mono); font-size: 14px;">${item.ticker}</strong></td>
                            <td><span class="opp-cat">${item.category}</span></td>
                            <td style="font-family: var(--font-mono); font-weight: 600;">$${item.price.toFixed(item.price > 1 ? 2 : 4)}</td>
                            <td style="font-family: var(--font-mono);" class="${item.change_24h >= 0 ? 'text-success' : 'text-danger'}">
                                ${item.change_24h >= 0 ? '+' : ''}${item.change_24h.toFixed(2)}%
                            </td>
                            <td>
                                <span class="badge-signal ${sigClass}"><i class="fa-solid ${sigIcon}"></i> ${item.signal}</span>
                            </td>
                            <td style="font-family: var(--font-mono);" class="${floatPnl >= 0 ? 'text-success' : 'text-danger'}">
                                ${item.metrics.is_currently_in_position ? `${floatPnl >= 0 ? '+' : ''}${floatPnl.toFixed(2)}%` : '<span class="text-muted">-</span>'}
                            </td>
                            <td style="font-family: var(--font-mono);" class="${item.dist_sl_pct >= 0 ? 'text-success' : 'text-danger'}">
                                ${item.dist_sl_pct > 0 ? '+' : ''}${item.dist_sl_pct.toFixed(1)}%
                            </td>
                            <td style="font-family: var(--font-mono);" class="${item.dist_sma20_pct >= 0 ? 'text-success' : 'text-danger'}">
                                ${item.dist_sma20_pct > 0 ? '+' : ''}${item.dist_sma20_pct.toFixed(1)}%
                            </td>
                            <td>
                                <button class="btn btn-secondary btn-view-trades" data-ticker="${item.ticker}" style="font-size: 11px; padding: 4px 10px;">
                                    <i class="fa-solid fa-list-check"></i> Pine Trades
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // Attach event listeners for "Ver Trades" buttons
        document.querySelectorAll(".btn-view-trades").forEach(btn => {
            btn.addEventListener("click", () => {
                const tk = btn.getAttribute("data-ticker");
                openTradingViewTradeLog(tk, selectedScannerStrategy);
            });
        });
    }

    // Open TradingView Trade Log Modal/Section
    function openTradingViewTradeLog(ticker, stratId) {
        if (!liveScannerData) return;

        let list = (stratId === "AIS11") ? liveScannerData.ais11_signals : liveScannerData.ss11_signals;
        const item = (list || []).find(x => x.ticker === ticker);
        if (!item) return;

        if (elSelectedTradeTicker) elSelectedTradeTicker.textContent = ticker;
        if (elSelectedTradeStrat) elSelectedTradeStrat.textContent = (stratId === "AIS11") ? "AIS11: Multi-IA GPU" : "SS11: Macro Base Pura";

        const m = item.metrics;
        if (elTvNetProfit) {
            elTvNetProfit.textContent = `$${m.net_profit_usd.toFixed(2)}`;
            elTvNetProfit.className = `val ${m.net_profit_usd >= 0 ? 'text-success' : 'text-danger'}`;
        }
        if (elTvProfitFactor) elTvProfitFactor.textContent = m.profit_factor.toFixed(2);
        if (elTvWinRate) elTvWinRate.textContent = `${m.win_rate.toFixed(1)}%`;
        if (elTvTotalTrades) elTvTotalTrades.textContent = m.trades_count;

        const trades = item.recent_trades || [];
        if (elTvTradesTbody) {
            if (trades.length === 0) {
                elTvTradesTbody.innerHTML = `<tr><td colspan="10" class="text-center p-4 text-muted">No se registran operaciones históricas cerradas para este activo.</td></tr>`;
            } else {
                elTvTradesTbody.innerHTML = trades.map((t, idx) => `
                    <tr>
                        <td>#${idx + 1}</td>
                        <td><span class="badge-signal buy">LONG</span></td>
                        <td>${t.entry_date}</td>
                        <td>$${t.entry_price.toFixed(2)}</td>
                        <td>${t.exit_date}</td>
                        <td>$${t.exit_price.toFixed(2)}</td>
                        <td class="${t.pct_return >= 0 ? 'text-success' : 'text-danger'}">${t.pct_return >= 0 ? '+' : ''}${t.pct_return.toFixed(2)}%</td>
                        <td class="${t.pnl >= 0 ? 'text-success' : 'text-danger'}">${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}</td>
                        <td>${t.duration_days}d</td>
                        <td><span class="opp-cat">${t.reason}</span></td>
                    </tr>
                `).join('');
            }
        }

        if (elTvTradeLogPanel) {
            elTvTradeLogPanel.classList.remove("hidden");
            elTvTradeLogPanel.scrollIntoView({ behavior: 'smooth' });
        }
    }

    // Load Hardware Status & Initial Scanner Data
    loadHardwareStatus();
    fetchLiveScanner(false);

    // Bucle de refresco automático de 60 segundos
    const elAutoTimerBadge = document.getElementById("auto-timer-badge");
    let autoRefreshCountdown = 60;

    setInterval(() => {
        autoRefreshCountdown--;
        if (autoRefreshCountdown <= 0) {
            autoRefreshCountdown = 60;
            fetchLiveScanner(false);
        }
        if (elAutoTimerBadge) {
            elAutoTimerBadge.innerHTML = `<i class="fa-solid fa-clock"></i> Auto (${autoRefreshCountdown}s)`;
        }
    }, 1000);

    async function checkServerStatus() {
        try {
            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                if (data.loading === false) {
                    // Server is ready! Hide loader and load data
                    if (elLoaderStatusText) elLoaderStatusText.textContent = "Datos listos. Iniciando dashboard...";
                    setTimeout(() => {
                        if (elStartupLoader) {
                            elStartupLoader.classList.add("hidden-loader");
                            setTimeout(() => { elStartupLoader.style.display = "none"; }, 800);
                        }
                        loadDatabase();
                    }, 500);
                    return;
                }
            }
        } catch (e) {
            // Server might not be responding yet, just keep polling
        }
        
        // Poll again in 1 second
        setTimeout(checkServerStatus, 1000);
    }
    
    // Start polling
    checkServerStatus();
});
