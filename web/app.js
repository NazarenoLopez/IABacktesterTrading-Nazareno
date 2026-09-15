// PineLab Dashboard Logic
document.addEventListener("DOMContentLoaded", () => {
    
    // Application State
    let db = null;
    let selectedStrategyId = null;
    let currentTicker = "SPY"; // Active ticker for detail visualization
    let activeFilter = "GLOBAL"; // Active sorting filter for sidebar
    let activeTab = "tab-chart";
    let equityChart = null; // Chart.js instance
    let drawdownChart = null;
    let currentView = "scanner"; // scanner | lab
    let currentEquityTrades = [];
    let drawerMode = "single"; // single | all
    let drawerTicker = null;
    let drawerStratFilter = "BOTH"; // SS11 | AIS11 | BOTH

    // Dom Elements
    const elTickerFilter = document.getElementById("ticker-filter");

    // Dynamic Price Formatter for micro-crypto and stocks
    function formatPrice(price) {
        if (price === null || price === undefined || isNaN(price)) return "$0.00";
        const p = parseFloat(price);
        if (p === 0) return "$0.00";
        const absP = Math.abs(p);
        if (absP >= 100) return "$" + p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (absP >= 1) return "$" + p.toFixed(2);
        if (absP >= 0.01) return "$" + p.toFixed(4);
        if (absP >= 0.0001) return "$" + p.toFixed(6);
        return "$" + p.toFixed(8).replace(/0+$/, '').replace(/\.$/, '');
    }
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
    const elAggCagr = document.getElementById("agg-cagr");
    const elAggSharpe = document.getElementById("agg-sharpe");
    const elAggSharpeStatus = document.getElementById("agg-sharpe-status");
    const elAggDrawdown = document.getElementById("agg-drawdown");
    const elAggWinrate = document.getElementById("agg-winrate");
    const elAggPf = document.getElementById("agg-pf");
    const elAggBeaten = document.getElementById("agg-beaten");
    const elStratNarrative = document.getElementById("strat-narrative");
    
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

        function formatDateTime(timeStr) {
            if (!timeStr || timeStr === "Desconocido") return timeStr;
            const parts = timeStr.split(" ");
            if (parts.length === 2) {
                const dateParts = parts[0].split("-");
                if (dateParts.length === 3) {
                    return `${dateParts[2]}/${dateParts[1]}/${dateParts[0]} ${parts[1]}`;
                }
            }
            return timeStr;
        }

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
        const updatedTimeFmt = formatDateTime(data.last_updated_time);

        banner.classList.remove("hidden", "warning", "running", "success");
        if (btn) btn.classList.add("hidden");
        if (badge) badge.classList.add("hidden");

        if (data.status === "outdated") {
            banner.classList.add("warning");
            if (title) title.textContent = "Señales de IA desactualizadas";
            if (desc) desc.textContent = `Las señales llegan hasta el ${aiDateFmt}, pero el mercado avanzó hasta el ${mktDateFmt}. (Última actualización: ${updatedTimeFmt})`;
            if (btn) btn.classList.remove("hidden");
        } else if (data.status === "running") {
            banner.classList.add("running");
            if (title) title.textContent = "Actualizando datos de mercado e IA…";
            if (desc) desc.textContent = `${data.step_name || 'Calculando modelos…'} ${data.step ? `(Paso ${data.step}/${data.total})` : ''}`;
        } else if (data.status === "up_to_date") {
            banner.classList.add("success");
            if (title) title.textContent = "Modelos IA al día";
            if (desc) desc.textContent = `Señales sincronizadas (${aiDateFmt}). Última actualización: ${updatedTimeFmt}.`;
            if (badge) {
                badge.classList.remove("hidden");
                badge.textContent = `Actualizado: ${updatedTimeFmt}`;
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
                metricLabel = "Retorno medio";
                metricValue = `${strat.aggregate_metrics.avg_return.toFixed(1)}%`;
            } else {
                const tr = strat.ticker_results[activeFilter]?.metrics.total_return || 0;
                metricLabel = `Retorno ${activeFilter}`;
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
    if (elTickerFilter) {
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
    }

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
        if (currentView === "lab") {
            showNoSelectionState(false);
        }

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

        try {
        // 1. Header Information
        elStratName.textContent = strategy.name;
        elStratDesc.textContent = strategy.description;
        updateDashboardHeaderRank();
        
        // Render Indicators Tags (short + tooltip)
        elStratTags.innerHTML = "";
        (strategy.indicators || []).forEach(ind => {
            const tag = document.createElement("span");
            tag.className = "tag-item";
            tag.textContent = ind.length > 18 ? ind.slice(0, 16) + "…" : ind;
            tag.title = ind;
            elStratTags.appendChild(tag);
        });

        // 2. Summary Metric Cards (Dynamic depending on activeFilter context)
        let displayReturn, displayCagr, displaySharpe, displayMaxDD, displayBeaten, displayWinrate, displayPf;
        let sharpeNum, ddNum, wrNum, pfNum;
        
        if (activeFilter === "GLOBAL") {
            const agg = strategy.aggregate_metrics;
            displayReturn = `${agg.avg_return.toFixed(1)}%`;
            displayCagr = `${agg.avg_cagr.toFixed(1)}%`;
            displaySharpe = agg.avg_sharpe.toFixed(2);
            displayMaxDD = `${agg.avg_max_dd.toFixed(1)}%`;
            displayWinrate = `${(agg.avg_win_rate || 0).toFixed(1)}%`;
            displayPf = (agg.avg_profit_factor || 0).toFixed(2);
            const totalTickers = Object.keys(strategy.ticker_results).length;
            displayBeaten = `${agg.outperform_count} / ${totalTickers} vs Buy & Hold`;
            sharpeNum = agg.avg_sharpe;
            ddNum = Math.abs(agg.avg_max_dd);
            wrNum = agg.avg_win_rate || 0;
            pfNum = agg.avg_profit_factor || 0;
            
            elAggReturnSub.textContent = `CAGR medio: ${displayCagr}`;
            elAggSharpeStatus.textContent = getSharpeStatus(agg.avg_sharpe);
            if (elStratNarrative) {
                elStratNarrative.textContent = `Supera Buy & Hold en ${agg.outperform_count}/${totalTickers} activos · Sharpe medio ${displaySharpe} · Max DD ${displayMaxDD}`;
            }
        } else {
            const tkData = strategy.ticker_results[activeFilter];
            displayReturn = `${tkData.metrics.total_return.toFixed(1)}%`;
            displayCagr = `${tkData.metrics.cagr.toFixed(1)}%`;
            displaySharpe = tkData.metrics.sharpe.toFixed(2);
            displayMaxDD = `${tkData.metrics.max_drawdown.toFixed(1)}%`;
            displayWinrate = `${tkData.metrics.win_rate.toFixed(1)}%`;
            displayPf = tkData.metrics.profit_factor.toFixed(2);
            displayBeaten = tkData.outperformed ? "Supera Buy & Hold" : "No supera Buy & Hold";
            sharpeNum = tkData.metrics.sharpe;
            ddNum = Math.abs(tkData.metrics.max_drawdown);
            wrNum = tkData.metrics.win_rate;
            pfNum = tkData.metrics.profit_factor;
            
            elAggReturnSub.textContent = `CAGR en ${activeFilter}: ${displayCagr}`;
            elAggSharpeStatus.textContent = getSharpeStatus(tkData.metrics.sharpe);
            if (elStratNarrative) {
                elStratNarrative.textContent = `${activeFilter}: ${displayBeaten} · Sharpe ${displaySharpe} · Max DD ${displayMaxDD}`;
            }
        }
        
        elAggReturn.textContent = displayReturn;
        if (elAggCagr) elAggCagr.textContent = displayCagr;
        elAggSharpe.textContent = displaySharpe;
        elAggDrawdown.textContent = displayMaxDD;
        if (elAggWinrate) elAggWinrate.textContent = displayWinrate;
        if (elAggPf) elAggPf.textContent = displayPf;
        if (elAggBeaten) elAggBeaten.textContent = displayBeaten;

        applyMetricCardTone("card-agg-sharpe", sharpeNum >= 1 ? "good" : (sharpeNum >= 0.5 ? "warn" : "bad"));
        applyMetricCardTone("card-agg-dd", ddNum <= 30 ? "good" : (ddNum <= 50 ? "warn" : "bad"));
        applyMetricCardTone("card-agg-wr", wrNum >= 50 ? "good" : (wrNum >= 40 ? "warn" : "bad"));
        applyMetricCardTone("card-agg-pf", pfNum >= 1.5 ? "good" : (pfNum >= 1 ? "warn" : "bad"));
        applyMetricCardTone("card-agg-return", parseFloat(displayReturn) >= 0 ? "good" : "bad");
        applyMetricCardTone("card-agg-cagr", parseFloat(displayCagr) >= 0 ? "good" : "bad");

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
        if (elPineScriptCode) elPineScriptCode.textContent = strategy.pinescript || "";

        // Reset scroll position of code container
        const codeWrap = elPineScriptCode?.parentElement?.parentElement;
        if (codeWrap) codeWrap.scrollTop = 0;
        } catch (err) {
            console.error("Error al renderizar estrategia:", err);
        }
    }

    function applyMetricCardTone(id, tone) {
        const card = document.getElementById(id);
        if (!card) return;
        card.classList.remove("metric-good", "metric-warn", "metric-bad");
        if (tone === "good") card.classList.add("metric-good");
        else if (tone === "warn") card.classList.add("metric-warn");
        else if (tone === "bad") card.classList.add("metric-bad");
    }

    function getSharpeStatus(val) {
        if (val >= 2) return "Excelente";
        if (val >= 1.5) return "Muy Bueno";
        if (val >= 1.0) return "Bueno";
        if (val >= 0.5) return "Moderado";
        return "Bajo/Riesgoso";
    }

    function showNoSelectionState(show) {
        if (currentView !== "lab") {
            if (elNoSelectionState) elNoSelectionState.classList.add("hidden");
            if (elDashboardState) elDashboardState.classList.add("hidden");
            return;
        }
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

        // Draw Equity Curves with trade markers
        currentEquityTrades = tkData.trades || [];
        renderEquityChart(tkData.equity_curve, tkBh.equity_curve, ticker, currentEquityTrades);

        // Populate Recent Trades Table
        populateTradesTable(tkData.trades);
    }

    // -------------------------------------------------------------------------
    // 5. Chart.js Equity Curve Graph + Drawdown
    // -------------------------------------------------------------------------
    function computeDrawdownSeries(values) {
        let peak = values[0] || 10000;
        return values.map(v => {
            if (v > peak) peak = v;
            return peak > 0 ? ((v - peak) / peak) * 100 : 0;
        });
    }

    function buildTradeMarkerDatasets(dates, values, trades) {
        const dateIndex = new Map(dates.map((d, i) => [d, i]));
        const findNearest = (dateStr) => {
            if (!dateStr) return -1;
            if (dateIndex.has(dateStr)) return dateIndex.get(dateStr);
            let best = -1;
            for (let i = 0; i < dates.length; i++) {
                if (dates[i] <= dateStr) best = i;
                else break;
            }
            return best;
        };

        const entryData = Array(dates.length).fill(null);
        const exitData = Array(dates.length).fill(null);
        (trades || []).forEach(t => {
            const ei = findNearest(t.entry_date);
            if (ei >= 0) entryData[ei] = values[ei];
            if (t.exit_date && t.exit_date !== "EN CURSO") {
                const xi = findNearest(t.exit_date);
                if (xi >= 0) exitData[xi] = values[xi];
            }
        });
        return { entryData, exitData };
    }

    function renderEquityChart(strategyCurve, benchmarkCurve, tickerName, trades = []) {
        if (equityChart) {
            equityChart.destroy();
            equityChart = null;
        }
        if (drawdownChart) {
            drawdownChart.destroy();
            drawdownChart = null;
        }

        const dates = strategyCurve.map(pt => pt.date);
        const strategyValues = strategyCurve.map(pt => pt.value);
        const benchmarkValues = benchmarkCurve.map(pt => pt.value);
        const ddValues = computeDrawdownSeries(strategyValues);
        const { entryData, exitData } = buildTradeMarkerDatasets(dates, strategyValues, trades);

        const equityCanvas = document.getElementById("equityChart");
        const ddCanvas = document.getElementById("drawdownChart");
        if (!equityCanvas) return;

        const ctx = equityCanvas.getContext("2d");
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
                        pointHoverRadius: 5,
                        order: 3
                    },
                    {
                        label: 'Buy & Hold',
                        data: benchmarkValues,
                        borderColor: 'rgba(255, 179, 0, 0.8)',
                        borderWidth: 1.5,
                        borderDash: [5, 5],
                        backgroundColor: 'transparent',
                        fill: false,
                        tension: 0.15,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        order: 4
                    },
                    {
                        label: 'Entradas',
                        data: entryData,
                        borderColor: '#00e676',
                        backgroundColor: '#00e676',
                        showLine: false,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        pointStyle: 'triangle',
                        order: 1
                    },
                    {
                        label: 'Salidas',
                        data: exitData,
                        borderColor: '#ff1744',
                        backgroundColor: '#ff1744',
                        showLine: false,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        pointStyle: 'rectRot',
                        order: 2
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
                            font: { family: 'Inter', size: 11 },
                            filter: (item) => item.text !== undefined
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 17, 24, 0.95)',
                        titleColor: '#f5f6fa',
                        bodyColor: '#8a94a6',
                        borderColor: 'rgba(255, 255, 255, 0.08)',
                        borderWidth: 1,
                        padding: 10,
                        callbacks: {
                            label: function(context) {
                                if (context.parsed.y === null) return null;
                                let label = context.dataset.label || '';
                                if (label) label += ': ';
                                if (context.dataset.label === 'Entradas' || context.dataset.label === 'Salidas') {
                                    return label + new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(context.parsed.y);
                                }
                                return label + new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(context.parsed.y);
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.02)' },
                        ticks: { color: '#8a94a6', font: { size: 10 }, maxTicksLimit: 8 }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.02)' },
                        ticks: {
                            color: '#8a94a6',
                            font: { size: 10 },
                            callback: function(value) { return '$' + value.toLocaleString(); }
                        }
                    }
                }
            }
        });

        if (ddCanvas) {
            const ddCtx = ddCanvas.getContext("2d");
            const ddGrad = ddCtx.createLinearGradient(0, 0, 0, 120);
            ddGrad.addColorStop(0, "rgba(255, 23, 68, 0.05)");
            ddGrad.addColorStop(1, "rgba(255, 23, 68, 0.25)");

            drawdownChart = new Chart(ddCtx, {
                type: 'line',
                data: {
                    labels: dates,
                    datasets: [{
                        label: `Drawdown ${tickerName}`,
                        data: ddValues,
                        borderColor: '#ff1744',
                        borderWidth: 1.5,
                        backgroundColor: ddGrad,
                        fill: true,
                        tension: 0.1,
                        pointRadius: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true,
                            labels: { color: '#8a94a6', font: { family: 'Inter', size: 10 } }
                        },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `Drawdown: ${ctx.parsed.y.toFixed(2)}%`
                            }
                        }
                    },
                    scales: {
                        x: {
                            display: false
                        },
                        y: {
                            grid: { color: 'rgba(255, 255, 255, 0.02)' },
                            ticks: {
                                color: '#8a94a6',
                                font: { size: 9 },
                                callback: (v) => v.toFixed(0) + '%'
                            }
                        }
                    }
                }
            });
        }
    }

    // -------------------------------------------------------------------------
    // 6. Cross-Ticker Breakdown Table
    // -------------------------------------------------------------------------
    function getSignalBadge(signal) {
        const sig = (signal || "WAIT").toUpperCase();
        const cls = sig === "BUY" ? "signal-buy" : (sig === "SELL" ? "signal-sell" : (sig === "HOLD" ? "signal-hold" : "signal-wait"));
        return `<span class="badge-signal ${cls}">${sig}</span>`;
    }

    function populateComparisonTable(strategy) {
        elCompareTableBody.innerHTML = "";
        
        const tickers = Object.keys(strategy.ticker_results);
        
        tickers.forEach(tk => {
            const tkData = strategy.ticker_results[tk];
            const tkBh = db.benchmarks[tk];
            if (!tkData || !tkBh) return;

            const tipParts = [
                `Sortino: ${(tkData.metrics.sortino || 0).toFixed(2)}`,
                `Duración media: ${Math.round(tkData.metrics.avg_duration || 0)}d`,
                `Valor final: $${(tkData.metrics.ending_val || 0).toLocaleString()}`,
                `B&H: ${tkBh.total_return.toFixed(1)}%`
            ].join(" · ");

            const tr = document.createElement("tr");
            tr.title = tipParts;
            tr.innerHTML = `
                <td class="compare-row-ticker sticky-col">${tk}</td>
                <td class="${tkData.metrics.total_return >= 0 ? 'text-success' : 'text-danger'} font-bold">${tkData.metrics.total_return.toFixed(1)}%</td>
                <td>${tkData.metrics.cagr.toFixed(1)}%</td>
                <td>${tkData.metrics.sharpe.toFixed(2)}</td>
                <td class="text-danger">${tkData.metrics.max_drawdown.toFixed(1)}%</td>
                <td>${tkData.metrics.num_trades}</td>
                <td>${getSignalBadge(tkData.metrics.current_signal)}</td>
                <td>
                    <span class="badge ${tkData.outperformed ? 'badge-success' : 'badge-danger'}">
                        ${tkData.outperformed ? 'Supera' : 'No'}
                    </span>
                </td>
            `;
            
            tr.addEventListener("click", () => {
                currentTicker = tk;
                switchTab("tab-chart");
                elTickerChips.querySelectorAll(".ticker-chip").forEach(chip => {
                    if (chip.textContent === tk) chip.classList.add("active");
                    else chip.classList.remove("active");
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
            const diffPrefix = diff >= 0 ? "+" : "";

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td class="compare-row-ticker sticky-col">${tk}</td>
                <td><a href="#" class="strategy-link" data-id="${bestStrat.strategy_id}">${bestStrat.strategy_id}</a></td>
                <td class="${tkData.metrics.total_return >= 0 ? 'text-success' : 'text-danger'} font-bold">${tkData.metrics.total_return.toFixed(1)}%</td>
                <td class="${diff >= 0 ? 'text-success' : 'text-danger'} font-bold">${diffPrefix}${diff.toFixed(1)}%</td>
                <td class="text-danger">${tkData.metrics.max_drawdown.toFixed(1)}%</td>
                <td>${tkData.metrics.sharpe.toFixed(2)}</td>
                <td>${tkData.metrics.num_trades}</td>
                <td>${getSignalBadge(tkData.metrics.current_signal)}</td>
            `;
            
            // Add click listener to the strategy link
            const link = tr.querySelector(".strategy-link");
            link.addEventListener("click", (e) => {
                e.preventDefault();
                selectStrategy(bestStrat.strategy_id);
                window.scrollTo({ top: 0, behavior: "smooth" });
            });
            
            elTopAssetsTableBody.appendChild(tr);
        });
    }

    // -------------------------------------------------------------------------
    // 7. Trade Log Table (Probador Histórico)
    // -------------------------------------------------------------------------
    let histTradesSortKey = "entry_date";
    let histTradesSortDir = "DESC"; // DESC = más reciente primero, ASC = más antiguo primero
    let activeHistTradesList = [];

    const elThHistEntryDate = document.getElementById("th-hist-entry-date");
    const elThHistExitDate = document.getElementById("th-hist-exit-date");

    if (elThHistEntryDate) {
        elThHistEntryDate.addEventListener("click", () => {
            if (histTradesSortKey === "entry_date") {
                histTradesSortDir = (histTradesSortDir === "DESC") ? "ASC" : "DESC";
            } else {
                histTradesSortKey = "entry_date";
                histTradesSortDir = "DESC";
            }
            renderHistTradesTable();
        });
    }

    if (elThHistExitDate) {
        elThHistExitDate.addEventListener("click", () => {
            if (histTradesSortKey === "exit_date") {
                histTradesSortDir = (histTradesSortDir === "DESC") ? "ASC" : "DESC";
            } else {
                histTradesSortKey = "exit_date";
                histTradesSortDir = "DESC";
            }
            renderHistTradesTable();
        });
    }

    function populateTradesTable(trades) {
        activeHistTradesList = trades || [];
        renderHistTradesTable();
    }

    function renderHistTradesTable() {
        if (!elTradesTableBody) return;
        
        if (!activeHistTradesList || activeHistTradesList.length === 0) {
            elTradesTableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:30px;">
                No se registran operaciones en el historial para este activo.
            </td></tr>`;
            return;
        }

        const sorted = [...activeHistTradesList].sort((a, b) => {
            let valA = new Date(a[histTradesSortKey] || "1970-01-01").getTime();
            let valB = new Date(b[histTradesSortKey] || "1970-01-01").getTime();
            return histTradesSortDir === "DESC" ? (valB - valA) : (valA - valB);
        });

        // Iconos de ordenamiento
        const iconEntry = document.getElementById("icon-hist-entry-date");
        const iconExit = document.getElementById("icon-hist-exit-date");
        if (iconEntry) iconEntry.className = histTradesSortKey === "entry_date" ? (histTradesSortDir === "DESC" ? "fa-solid fa-sort-down text-warning" : "fa-solid fa-sort-up text-warning") : "fa-solid fa-sort";
        if (iconExit) iconExit.className = histTradesSortKey === "exit_date" ? (histTradesSortDir === "DESC" ? "fa-solid fa-sort-down text-warning" : "fa-solid fa-sort-up text-warning") : "fa-solid fa-sort";

        elTradesTableBody.innerHTML = sorted.map((trade, idx) => {
            const retClass = trade.pct_return >= 0 ? "text-success" : "text-danger";
            const retPrefix = trade.pct_return >= 0 ? "+" : "";

            return `
                <tr>
                    <td>#${idx + 1}</td>
                    <td>${trade.entry_date}</td>
                    <td>${formatPrice(trade.entry_price)}</td>
                    <td>${trade.exit_date}</td>
                    <td>${formatPrice(trade.exit_price)}</td>
                    <td>${trade.duration_days} días</td>
                    <td class="${retClass} font-bold">${retPrefix}${trade.pct_return.toFixed(2)}%</td>
                    <td><span style="font-size:11px;opacity:0.8;">${trade.reason}</span></td>
                </tr>
            `;
        }).join('');
    }

    // -------------------------------------------------------------------------
    // 8. Clipboard Utilities & UI Interactivity
    // -------------------------------------------------------------------------
    // Clipboard
    if (elBtnCopyCode) {
        elBtnCopyCode.addEventListener("click", () => {
            const code = elPineScriptCode.textContent;
            navigator.clipboard.writeText(code).then(() => {
                elToastMessage.classList.add("show");
                setTimeout(() => {
                    elToastMessage.classList.remove("show");
                }, 3000);
            }).catch(err => {
                alert("No se pudo copiar el código: " + err);
            });
        });
    }

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
        if (tabId === "tab-chart") {
            setTimeout(() => {
                if (equityChart) equityChart.resize();
                if (drawdownChart) drawdownChart.resize();
            }, 50);
        }
    }

    // Pine Script shortcut
    const elBtnGotoPine = document.getElementById("btn-goto-pine");
    if (elBtnGotoPine) {
        elBtnGotoPine.addEventListener("click", () => switchTab("tab-pine"));
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
                        cell.innerHTML = formatPrice(newPrice);
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
    let selectedScannerStrategy = "COMBO"; // SS11, AIS11, COMBO
    let selectedScannerUniverse = "ALL";  // ALL, US, CRYPTO, BUY_ONLY
    let watchlistPage = 0;
    const WATCHLIST_PAGE_SIZE = 60;
    let watchlistActionableOnly = false;
    let lastWatchlistFiltered = [];

    function signalPriority(sig) {
        const s = (sig || "WAIT").toUpperCase();
        if (s === "BUY") return 0;
        if (s === "SELL") return 1;
        if (s === "HOLD") return 2;
        return 3;
    }

    function pickPrimarySignal(signalsByStrat) {
        const vals = Object.values(signalsByStrat || {});
        if (!vals.length) return "WAIT";
        return vals.slice().sort((a, b) => signalPriority(a) - signalPriority(b))[0];
    }

    function mergeComboByTicker(ss11List, ais11List) {
        const map = new Map();
        const ingest = (item) => {
            const key = item.ticker;
            if (!map.has(key)) {
                map.set(key, {
                    ...item,
                    signals_by_strat: { [item.strat_label]: item.signal },
                    legs: [item],
                    is_combo: true
                });
                return;
            }
            const row = map.get(key);
            row.signals_by_strat[item.strat_label] = item.signal;
            row.legs.push(item);
            // Prefer non-null metrics / fresher price
            if (item.price != null) row.price = item.price;
            if (item.change_24h != null) row.change_24h = item.change_24h;
            if (item.dist_sl_pct != null) row.dist_sl_pct = item.dist_sl_pct;
            if (item.dist_sma20_pct != null) row.dist_sma20_pct = item.dist_sma20_pct;
            row.signal = pickPrimarySignal(row.signals_by_strat);
            const posLegs = row.legs.filter(l => l.metrics && l.metrics.is_currently_in_position);
            if (posLegs.length) {
                // Prefer the leg with larger |PnL| for display metrics
                const best = posLegs.slice().sort((a, b) =>
                    Math.abs(b.metrics.floating_pnl_pct || 0) - Math.abs(a.metrics.floating_pnl_pct || 0)
                )[0];
                row.metrics = { ...best.metrics, is_currently_in_position: true };
                row.strat_label = best.strat_label;
                row.dist_sl_pct = best.dist_sl_pct != null ? best.dist_sl_pct : row.dist_sl_pct;
            } else {
                row.metrics = row.metrics || item.metrics || {};
                if (row.metrics) row.metrics.is_currently_in_position = false;
            }
        };
        ss11List.forEach(ingest);
        ais11List.forEach(ingest);
        return Array.from(map.values());
    }

    function renderSignalCell(item) {
        if (item.is_combo && item.signals_by_strat) {
            return ["SS11", "AIS11"].map(strat => {
                if (item.signals_by_strat[strat] == null) return "";
                const sig = String(item.signals_by_strat[strat]).toUpperCase();
                const cls = sig === "BUY" ? "signal-buy" : (sig === "SELL" ? "signal-sell" : (sig === "HOLD" ? "signal-hold" : "signal-wait"));
                return `<span class="badge-signal-pair"><span class="strat-mini">${strat}</span><span class="badge-signal ${cls}">${sig}</span></span>`;
            }).join("");
        }
        const sig = (item.signal || "WAIT").toUpperCase();
        const cls = sig === "BUY" ? "signal-buy" : (sig === "SELL" ? "signal-sell" : (sig === "HOLD" ? "signal-hold" : "signal-wait"));
        return `<span class="badge-signal ${cls}">${sig}</span>`;
    }

    // Table sorting states
    let posSortKey = "pnl";
    let posSortDir = "DESC";

    let scannerSortKey = "ticker";
    let scannerSortDir = "ASC";

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
    const elActivePositionsTbody = document.getElementById("active-positions-tbody");
    const elActivePosCountBadge = document.getElementById("active-pos-count-badge");
    const elLiveScannerTbody = document.getElementById("live-scanner-tbody");
    const elScannerSearchInput = document.getElementById("scanner-search-input");

    const elTvTradeLogPanel = document.getElementById("tv-trade-log-panel");
    const elTradeDrawerOverlay = document.getElementById("trade-drawer-overlay");
    const elBtnCloseTvTrades = document.getElementById("btn-close-tv-trades");
    const elSelectedTradeTicker = document.getElementById("selected-trade-ticker");
    const elSelectedTradeStrat = document.getElementById("selected-trade-strat");
    const elTvNetProfit = document.getElementById("tv-net-profit");
    const elTvProfitFactor = document.getElementById("tv-profit-factor");
    const elTvWinRate = document.getElementById("tv-win-rate");
    const elTvTotalTrades = document.getElementById("tv-total-trades");
    const elTvTradesTbody = document.getElementById("tv-trades-tbody");
    const elDrawerStratTabs = document.getElementById("drawer-strat-tabs");
    const elKpiOpenPos = document.getElementById("kpi-open-positions");
    const elKpiBuySignals = document.getElementById("kpi-buy-signals");
    const elKpiAvgPnl = document.getElementById("kpi-avg-pnl");
    const elKpiLastScan = document.getElementById("kpi-last-scan");
    const elKpiScanCountdown = document.getElementById("kpi-scan-countdown");
    const elBtnOpenSidebar = document.getElementById("btn-open-sidebar");
    const elBtnCloseSidebar = document.getElementById("btn-close-sidebar");
    const elSidebarBackdrop = document.getElementById("sidebar-backdrop");

    function setAppView(view) {
        currentView = view;
        document.body.setAttribute("data-view", view);
        document.body.classList.remove("sidebar-open");

        if (view === "scanner") {
            elNavBtnScanner.classList.add("active");
            elNavBtnBacktester.classList.remove("active");
            if (elScannerViewPanel) elScannerViewPanel.classList.remove("hidden");
            if (elDashboardState) elDashboardState.classList.add("hidden");
            if (elNoSelectionState) elNoSelectionState.classList.add("hidden");
        } else {
            elNavBtnBacktester.classList.add("active");
            elNavBtnScanner.classList.remove("active");
            if (elScannerViewPanel) elScannerViewPanel.classList.add("hidden");
            if (selectedStrategyId) {
                if (elDashboardState) elDashboardState.classList.remove("hidden");
                if (elNoSelectionState) elNoSelectionState.classList.add("hidden");
                setTimeout(() => {
                    if (equityChart) equityChart.resize();
                    if (drawdownChart) drawdownChart.resize();
                }, 80);
            } else {
                if (elDashboardState) elDashboardState.classList.add("hidden");
                if (elNoSelectionState) elNoSelectionState.classList.remove("hidden");
            }
        }
    }

    function openLabSidebar() {
        document.body.classList.add("sidebar-open");
    }
    function closeLabSidebar() {
        document.body.classList.remove("sidebar-open");
    }

    if (elBtnOpenSidebar) elBtnOpenSidebar.addEventListener("click", openLabSidebar);
    if (elBtnCloseSidebar) elBtnCloseSidebar.addEventListener("click", closeLabSidebar);
    if (elSidebarBackdrop) elSidebarBackdrop.addEventListener("click", closeLabSidebar);

    function openTradeDrawer() {
        if (elTvTradeLogPanel) elTvTradeLogPanel.classList.remove("hidden");
        if (elTradeDrawerOverlay) elTradeDrawerOverlay.classList.remove("hidden");
    }
    function closeTradeDrawer() {
        if (elTvTradeLogPanel) elTvTradeLogPanel.classList.add("hidden");
        if (elTradeDrawerOverlay) elTradeDrawerOverlay.classList.add("hidden");
    }

    // Top Navigation View Switcher
    if (elNavBtnScanner && elNavBtnBacktester) {
        elNavBtnScanner.addEventListener("click", () => setAppView("scanner"));
        elNavBtnBacktester.addEventListener("click", () => setAppView("lab"));
    }
    setAppView("scanner");

    // Hardware GPU Detection
    async function loadHardwareStatus() {
        try {
            const res = await fetch('/api/hardware');
            if (res.ok) {
                const hw = await res.json();
                if (elGpuNameText) {
                    if (hw.cuda_available) {
                        elGpuNameText.textContent = `CUDA: ${hw.device_name}`;
                    } else {
                        elGpuNameText.textContent = `CPU (${hw.device_name})`;
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
            watchlistPage = 0;
            renderLiveScannerData();
        });
    });

    document.querySelectorAll("#universe-pill-group .pill-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll("#universe-pill-group .pill-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            selectedScannerUniverse = btn.getAttribute("data-univ");
            watchlistPage = 0;
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
            watchlistPage = 0;
            renderLiveScannerData();
        });
    }

    const elWatchlistActionable = document.getElementById("watchlist-actionable-only");
    if (elWatchlistActionable) {
        elWatchlistActionable.addEventListener("change", () => {
            watchlistActionableOnly = !!elWatchlistActionable.checked;
            watchlistPage = 0;
            renderLiveScannerData();
        });
    }

    // Sort Headers Event Listeners
    document.querySelectorAll(".pos-sortable-th").forEach(th => {
        th.addEventListener("click", () => {
            const key = th.getAttribute("data-sort");
            if (posSortKey === key) {
                posSortDir = posSortDir === "ASC" ? "DESC" : "ASC";
            } else {
                posSortKey = key;
                posSortDir = (key === "ticker" || key === "category" || key === "signal") ? "ASC" : "DESC";
            }
            renderLiveScannerData();
        });
    });

    document.querySelectorAll(".scanner-sortable-th").forEach(th => {
        th.addEventListener("click", () => {
            const key = th.getAttribute("data-sort");
            if (scannerSortKey === key) {
                scannerSortDir = scannerSortDir === "ASC" ? "DESC" : "ASC";
            } else {
                scannerSortKey = key;
                scannerSortDir = (key === "ticker" || key === "category" || key === "signal") ? "ASC" : "DESC";
            }
            watchlistPage = 0;
            renderLiveScannerData();
        });
    });

    if (elBtnCloseTvTrades) {
        elBtnCloseTvTrades.addEventListener("click", closeTradeDrawer);
    }
    if (elTradeDrawerOverlay) {
        elTradeDrawerOverlay.addEventListener("click", closeTradeDrawer);
    }

    if (elDrawerStratTabs) {
        elDrawerStratTabs.querySelectorAll("[data-drawer-strat]").forEach(btn => {
            btn.addEventListener("click", () => {
                elDrawerStratTabs.querySelectorAll(".pill-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                drawerStratFilter = btn.getAttribute("data-drawer-strat");
                if (drawerMode === "all") {
                    openAllTradesDrawer(false);
                } else if (drawerTicker) {
                    openTradingViewTradeLog(drawerTicker, drawerStratFilter === "BOTH" ? "COMBO" : drawerStratFilter, false);
                }
            });
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
                if (elMacroStatusTitle) elMacroStatusTitle.textContent = "Crash sistémico Macro detectado (SPY)";
                if (elMacroStatusDesc) elMacroStatusDesc.textContent = `Filtro Macro activo: caída brusca en SPY. Capital en liquidez por ${mg.days_remaining} sesiones.`;
                if (elMacroStatusTag) elMacroStatusTag.textContent = `CRASH ACTIVO (${mg.days_remaining}d)`;
            } else {
                elMacroGuardBanner.classList.remove("danger");
                if (elMacroIcon) elMacroIcon.className = "fa-solid fa-shield-halved macro-icon text-success";
                if (elMacroStatusTitle) elMacroStatusTitle.textContent = "Filtro Macro: mercado seguro";
                if (elMacroStatusDesc) elMacroStatusDesc.textContent = "El S&P 500 está estable. Las estrategias operan con normalidad.";
                if (elMacroStatusTag) elMacroStatusTag.textContent = "MERCADO SEGURO";
            }
        }

        if (elKpiLastScan && liveScannerData.timestamp) {
            elKpiLastScan.textContent = liveScannerData.timestamp;
        }

        // Prepare signal lists with strategy tags
        const ss11 = (liveScannerData.ss11_signals || []).map(x => ({ ...x, strat_label: "SS11" }));
        const ais11 = (liveScannerData.ais11_signals || []).map(x => ({ ...x, strat_label: "AIS11" }));

        // Determine list of signals based on strategy pill
        // COMBO: 1 fila por ticker (sin duplicar SS11+AIS11)
        let list = [];
        let positionLegs = [];
        if (selectedScannerStrategy === "SS11") {
            list = ss11;
            positionLegs = ss11;
        } else if (selectedScannerStrategy === "AIS11") {
            list = ais11;
            positionLegs = ais11;
        } else {
            list = mergeComboByTicker(ss11, ais11);
            positionLegs = [...ss11, ...ais11];
        }

        // Update Universe Pill Count Badges dynamically
        const totalCount = list.length;
        const usCount = list.filter(x => x.category === "US Stock").length;
        const cryptoCount = list.filter(x => x.category === "Crypto").length;
        const buyCount = list.filter(x => {
            if (x.signals_by_strat) {
                return Object.values(x.signals_by_strat).some(s => s === "BUY");
            }
            return x.signal === "BUY";
        }).length;
        const posCount = list.filter(x => x.metrics && x.metrics.is_currently_in_position).length;

        const pillAll = document.querySelector("#universe-pill-group [data-univ='ALL']");
        const pillUs = document.querySelector("#universe-pill-group [data-univ='US']");
        const pillCrypto = document.querySelector("#universe-pill-group [data-univ='CRYPTO']");
        const pillBuy = document.querySelector("#universe-pill-group [data-univ='BUY_ONLY']");
        const pillPos = document.querySelector("#universe-pill-group [data-univ='POS_ONLY']");

        if (pillAll) pillAll.textContent = `Todos (${totalCount})`;
        if (pillUs) pillUs.textContent = `EE.UU. (${usCount})`;
        if (pillCrypto) pillCrypto.textContent = `Cripto (${cryptoCount})`;
        if (pillBuy) pillBuy.textContent = `BUY (${buyCount})`;
        if (pillPos) pillPos.textContent = `Posiciones (${posCount})`;

        // KPI strip
        const posForKpi = list.filter(x => x.metrics && x.metrics.is_currently_in_position);
        const avgPnl = posForKpi.length
            ? posForKpi.reduce((acc, x) => acc + (x.metrics.floating_pnl_pct || 0), 0) / posForKpi.length
            : null;
        if (elKpiOpenPos) elKpiOpenPos.textContent = String(posCount);
        if (elKpiBuySignals) elKpiBuySignals.textContent = String(buyCount);
        if (elKpiAvgPnl) {
            if (avgPnl === null) {
                elKpiAvgPnl.textContent = "—";
                elKpiAvgPnl.className = "scanner-kpi-value";
            } else {
                elKpiAvgPnl.textContent = `${avgPnl >= 0 ? "+" : ""}${avgPnl.toFixed(2)}%`;
                elKpiAvgPnl.className = `scanner-kpi-value ${avgPnl >= 0 ? "text-success" : "text-danger"}`;
            }
        }

        // Auto-collapse watchlist when there are actionable items (once preference allows)
        maybeCollapseWatchlist(buyCount, posCount);

        const searchTerm = (elScannerSearchInput ? elScannerSearchInput.value : "").trim().toUpperCase();

        // 2. Render Active Positions Table (sortable list view)
        // En Combo: una fila por estrategia en posición (entrada/PnL distintos), no duplicar en watchlist
        const activePosItems = positionLegs.filter(item => {
            if (searchTerm && !item.ticker.toUpperCase().includes(searchTerm)) return false;
            if (selectedScannerUniverse === "US" && item.category !== "US Stock") return false;
            if (selectedScannerUniverse === "CRYPTO" && item.category !== "Crypto") return false;
            return item.metrics && item.metrics.is_currently_in_position;
        });

        if (elActivePosCountBadge) elActivePosCountBadge.textContent = `${activePosItems.length} abiertas`;

        // Sort Active Positions
        activePosItems.sort((a, b) => {
            let valA, valB;
            if (posSortKey === "ticker") {
                valA = a.ticker || ""; valB = b.ticker || "";
                return posSortDir === "ASC" ? valA.localeCompare(valB) : valB.localeCompare(valA);
            } else if (posSortKey === "category") {
                valA = (a.strat_label || "") + (a.category || "");
                valB = (b.strat_label || "") + (b.category || "");
                return posSortDir === "ASC" ? valA.localeCompare(valB) : valB.localeCompare(valA);
            } else if (posSortKey === "entry_price") {
                valA = a.metrics && a.metrics.entry_price ? a.metrics.entry_price : a.price;
                valB = b.metrics && b.metrics.entry_price ? b.metrics.entry_price : b.price;
            } else if (posSortKey === "price") {
                valA = a.price || 0; valB = b.price || 0;
            } else if (posSortKey === "pnl") {
                valA = (a.metrics && a.metrics.floating_pnl_pct !== undefined) ? a.metrics.floating_pnl_pct : -999;
                valB = (b.metrics && b.metrics.floating_pnl_pct !== undefined) ? b.metrics.floating_pnl_pct : -999;
            } else if (posSortKey === "dist_sl") {
                valA = (a.dist_sl_pct !== undefined && a.dist_sl_pct !== null) ? a.dist_sl_pct : -15.0;
                valB = (b.dist_sl_pct !== undefined && b.dist_sl_pct !== null) ? b.dist_sl_pct : -15.0;
            } else if (posSortKey === "signal") {
                valA = a.signal || ""; valB = b.signal || "";
                return posSortDir === "ASC" ? valA.localeCompare(valB) : valB.localeCompare(valA);
            } else {
                valA = 0; valB = 0;
            }
            return posSortDir === "ASC" ? (valA - valB) : (valB - valA);
        });

        // Update Active Positions Header Icons
        document.querySelectorAll(".pos-sortable-th").forEach(th => {
            const key = th.getAttribute("data-sort");
            const icon = th.querySelector("i");
            if (icon) {
                if (posSortKey === key) {
                    icon.className = posSortDir === "ASC" ? "fa-solid fa-sort-up text-warning" : "fa-solid fa-sort-down text-warning";
                } else {
                    icon.className = "fa-solid fa-sort";
                }
            }
        });

        if (elActivePositionsTbody) {
            if (activePosItems.length === 0) {
                let emptyMsg = `No hay posiciones actualmente abiertas para los filtros seleccionados (${selectedScannerStrategy}).`;
                if (selectedScannerStrategy === "SS11" && selectedScannerUniverse === "CRYPTO") {
                    emptyMsg = `🛡️ <b>SS11 (Macro Base Pura)</b> está optimizada exclusivamente para acciones y ETFs de Wall Street basadas en el filtro SPY. Para operar Criptomonedas, selecciona la estrategia <b>AIS11 (Multi-IA GPU)</b>.`;
                }
                elActivePositionsTbody.innerHTML = `
                    <tr>
                        <td colspan="8" class="text-center p-4 text-muted">
                            <i class="fa-solid fa-folder-open" style="font-size: 18px; margin-right: 8px; color: var(--text-muted);"></i>
                            ${emptyMsg}
                        </td>
                    </tr>
                `;
            } else {
                elActivePositionsTbody.innerHTML = activePosItems.map(item => {
                    const met = item.metrics || {};
                    const floatPnl = met.floating_pnl_pct || 0.0;
                    const entryP = met.entry_price ? formatPrice(met.entry_price) : formatPrice(item.price);
                    const currP = formatPrice(item.price);
                    const stratTag = item.strat_label === "AIS11"
                        ? `<span class="badge-strat ais11"><i class="fa-solid fa-microchip"></i>AIS11</span>`
                        : `<span class="badge-strat ss11"><i class="fa-solid fa-chess-knight"></i>SS11</span>`;
                    const distSlVal = (item.dist_sl_pct !== undefined && item.dist_sl_pct !== null) ? item.dist_sl_pct : -15.0;
                    const sig = (item.signal || "HOLD").toUpperCase();
                    const sigClass = sig === "BUY" ? "signal-buy" : (sig === "SELL" ? "signal-sell" : (sig === "HOLD" ? "signal-hold" : "signal-wait"));
                    const pnlChip = `<span class="pnl-chip ${floatPnl >= 0 ? "pnl-pos" : "pnl-neg"}">${floatPnl >= 0 ? "+" : ""}${floatPnl.toFixed(2)}%</span>`;

                    return `
                        <tr>
                            <td class="sticky-col">
                                <strong style="font-family: var(--font-mono); font-size: 14px;">${item.ticker}</strong>
                            </td>
                            <td>${stratTag}</td>
                            <td style="font-family: var(--font-mono);">${entryP}</td>
                            <td style="font-family: var(--font-mono);">${currP}</td>
                            <td>${pnlChip}</td>
                            <td style="font-family: var(--font-mono);" class="${distSlVal >= 0 ? 'text-success' : 'text-danger'}">
                                ${distSlVal > 0 ? '+' : ''}${distSlVal.toFixed(1)}%
                            </td>
                            <td>
                                <span class="badge-signal ${sigClass}">${sig}</span>
                            </td>
                            <td style="text-align: center;">
                                <button class="btn btn-secondary btn-view-trades" data-ticker="${item.ticker}" data-strat="${item.strat_label || selectedScannerStrategy}" type="button" style="font-size: 11px; padding: 4px 12px;">
                                    <i class="fa-solid fa-list-check"></i> Trades
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // Apply Main Table Filter
        let filtered = list.filter(item => {
            if (searchTerm && !item.ticker.toUpperCase().includes(searchTerm)) {
                return false;
            }
            if (selectedScannerUniverse === "US" && item.category !== "US Stock") return false;
            if (selectedScannerUniverse === "CRYPTO" && item.category !== "Crypto") return false;
            if (selectedScannerUniverse === "BUY_ONLY") {
                if (buyCount > 0) {
                    if (item.signals_by_strat) {
                        return Object.values(item.signals_by_strat).some(s => s === "BUY");
                    }
                    return item.signal === "BUY";
                }
                return !item.metrics || !item.metrics.is_currently_in_position;
            }
            if (selectedScannerUniverse === "POS_ONLY" && (!item.metrics || !item.metrics.is_currently_in_position)) return false;
            if (watchlistActionableOnly) {
                const hasBuySell = item.signals_by_strat
                    ? Object.values(item.signals_by_strat).some(s => s === "BUY" || s === "SELL")
                    : (item.signal === "BUY" || item.signal === "SELL");
                const inPos = item.metrics && item.metrics.is_currently_in_position;
                if (!hasBuySell && !inPos) return false;
            }
            return true;
        });

        // Sort Live Scanner Table
        filtered.sort((a, b) => {
            let valA, valB;
            if (scannerSortKey === "ticker") {
                valA = a.ticker || ""; valB = b.ticker || "";
                return scannerSortDir === "ASC" ? valA.localeCompare(valB) : valB.localeCompare(valA);
            } else if (scannerSortKey === "category") {
                valA = (a.strat_label || "") + (a.category || "");
                valB = (b.strat_label || "") + (b.category || "");
                return scannerSortDir === "ASC" ? valA.localeCompare(valB) : valB.localeCompare(valA);
            } else if (scannerSortKey === "price") {
                valA = a.price || 0; valB = b.price || 0;
            } else if (scannerSortKey === "change_24h") {
                valA = a.change_24h || 0; valB = b.change_24h || 0;
            } else if (scannerSortKey === "signal") {
                valA = signalPriority(a.signal);
                valB = signalPriority(b.signal);
                if (valA === valB) {
                    return (a.ticker || "").localeCompare(b.ticker || "");
                }
                return scannerSortDir === "ASC" ? (valA - valB) : (valB - valA);
            } else if (scannerSortKey === "pnl") {
                valA = (a.metrics && a.metrics.floating_pnl_pct !== undefined) ? a.metrics.floating_pnl_pct : -999;
                valB = (b.metrics && b.metrics.floating_pnl_pct !== undefined) ? b.metrics.floating_pnl_pct : -999;
            } else if (scannerSortKey === "dist_sl") {
                valA = (a.dist_sl_pct !== undefined && a.dist_sl_pct !== null) ? a.dist_sl_pct : -15.0;
                valB = (b.dist_sl_pct !== undefined && b.dist_sl_pct !== null) ? b.dist_sl_pct : -15.0;
            } else if (scannerSortKey === "dist_sma20") {
                valA = (a.dist_sma20_pct !== undefined && a.dist_sma20_pct !== null) ? a.dist_sma20_pct : 0.0;
                valB = (b.dist_sma20_pct !== undefined && b.dist_sma20_pct !== null) ? b.dist_sma20_pct : 0.0;
            } else {
                valA = 0; valB = 0;
            }
            return scannerSortDir === "ASC" ? (valA - valB) : (valB - valA);
        });

        // Default: priorizar señales accionables cuando el sort es ticker ASC (carga inicial)
        if (scannerSortKey === "ticker" && scannerSortDir === "ASC" && selectedScannerUniverse === "ALL") {
            filtered.sort((a, b) => {
                const pa = signalPriority(a.signal);
                const pb = signalPriority(b.signal);
                if (pa !== pb) return pa - pb;
                return (a.ticker || "").localeCompare(b.ticker || "");
            });
        }

        lastWatchlistFiltered = filtered;
        const elWatchlistCount = document.getElementById("watchlist-count-badge");
        if (elWatchlistCount) elWatchlistCount.textContent = `${filtered.length} tickers`;

        const totalPages = Math.max(1, Math.ceil(filtered.length / WATCHLIST_PAGE_SIZE));
        if (watchlistPage >= totalPages) watchlistPage = totalPages - 1;
        if (watchlistPage < 0) watchlistPage = 0;
        const pageSlice = filtered.slice(
            watchlistPage * WATCHLIST_PAGE_SIZE,
            (watchlistPage + 1) * WATCHLIST_PAGE_SIZE
        );

        // Update Scanner Table Header Icons
        document.querySelectorAll(".scanner-sortable-th").forEach(th => {
            const key = th.getAttribute("data-sort");
            const icon = th.querySelector("i");
            if (icon) {
                if (scannerSortKey === key) {
                    icon.className = scannerSortDir === "ASC" ? "fa-solid fa-sort-up text-indigo" : "fa-solid fa-sort-down text-indigo";
                } else {
                    icon.className = "fa-solid fa-sort";
                }
            }
        });

        // 3. Render Opportunities Cards (BUY signals or Top Candidates if BUY count is 0)
        let buyItems = list.filter(item => {
            if (searchTerm && !item.ticker.toUpperCase().includes(searchTerm)) return false;
            if (selectedScannerUniverse === "US" && item.category !== "US Stock") return false;
            if (selectedScannerUniverse === "CRYPTO" && item.category !== "Crypto") return false;
            if (item.signals_by_strat) {
                return Object.values(item.signals_by_strat).some(s => s === "BUY");
            }
            return item.signal === "BUY";
        });

        let isShowingCandidates = false;
        let displayOppItems = buyItems;

        if (buyItems.length === 0) {
            isShowingCandidates = true;
            const candidatesPool = list.filter(item => {
                if (searchTerm && !item.ticker.toUpperCase().includes(searchTerm)) return false;
                if (selectedScannerUniverse === "US" && item.category !== "US Stock") return false;
                if (selectedScannerUniverse === "CRYPTO" && item.category !== "Crypto") return false;
                return !item.metrics || !item.metrics.is_currently_in_position;
            });
            candidatesPool.sort((a, b) => (b.ai_score || b.change_24h || 0) - (a.ai_score || a.change_24h || 0));
            displayOppItems = candidatesPool.slice(0, 6);
        }

        if (elBuyCountBadge) {
            if (isShowingCandidates) {
                elBuyCountBadge.textContent = `0 en BUY hoy (Mostrando Top Próximos Candidatos)`;
                elBuyCountBadge.style.background = "rgba(92, 96, 245, 0.15)";
                elBuyCountBadge.style.color = "#a5b4fc";
                elBuyCountBadge.style.borderColor = "rgba(92, 96, 245, 0.4)";
            } else {
                elBuyCountBadge.textContent = `${buyItems.length} Activos en BUY`;
                elBuyCountBadge.style.background = "rgba(16, 185, 129, 0.15)";
                elBuyCountBadge.style.color = "#10b981";
                elBuyCountBadge.style.borderColor = "rgba(16, 185, 129, 0.3)";
            }
        }

        if (elOpportunitiesCardsGrid) {
            if (displayOppItems.length === 0) {
                elOpportunitiesCardsGrid.innerHTML = `
                    <div class="empty-cards-notice">
                        <i class="fa-solid fa-shield-cat" style="font-size: 24px; margin-bottom: 8px; color: var(--text-muted); display: block;"></i>
                        No hay oportunidades ni candidatos disponibles para los filtros seleccionados.
                    </div>
                `;
            } else {
                elOpportunitiesCardsGrid.innerHTML = displayOppItems.map((item, idx) => {
                    const stratTag = item.strat_label === "AIS11"
                        ? `<span class="badge-strat ais11"><i class="fa-solid fa-microchip"></i>AIS11</span>`
                        : `<span class="badge-strat ss11"><i class="fa-solid fa-chess-knight"></i>SS11</span>`;
                    const badgeHtml = isShowingCandidates 
                        ? `<span class="badge-signal signal-wait"><i class="fa-solid fa-fire"></i> Candidato #${idx + 1}</span>`
                        : `<span class="badge-signal signal-buy">BUY</span>`;
                    
                    const distSlOpp = (item.dist_sl_pct !== undefined && item.dist_sl_pct !== null) ? item.dist_sl_pct : -15.0;
                    const distSma20Opp = (item.dist_sma20_pct !== undefined && item.dist_sma20_pct !== null) ? item.dist_sma20_pct : 0.0;
                    const scoreText = (item.ai_score !== undefined && item.ai_score !== null)
                        ? `Score IA: ${Number(item.ai_score).toFixed(1)}/100`
                        : (item.signal === "NO_AI"
                            ? "Sin señales IA (no operable AIS11)"
                            : `Dist. SMA20: ${distSma20Opp > 0 ? '+' : ''}${distSma20Opp.toFixed(1)}%`);

                    return `
                        <div class="opp-card">
                            <div class="opp-card-header">
                                <span class="opp-ticker">${item.ticker}</span>
                                <span class="opp-cat">${stratTag}${item.category}</span>
                            </div>
                            <div class="opp-price-row">
                                <span class="opp-price">${formatPrice(item.price)}</span>
                                <span class="opp-change ${(item.change_24h || 0) >= 0 ? 'text-success' : 'text-danger'}">
                                    ${(item.change_24h || 0) >= 0 ? '+' : ''}${(item.change_24h || 0).toFixed(2)}%
                                </span>
                            </div>
                            <div class="opp-details-grid">
                                <div>
                                    <span>${scoreText}</span>
                                    <strong class="${item.signal === 'BUY' ? 'text-success' : (item.signal === 'SELL' ? 'text-danger' : 'text-warning')}">${item.signal}</strong>
                                </div>
                                <div>
                                    <span>Dist. Stop Loss (-15%)</span>
                                    <strong class="${distSlOpp >= 0 ? 'text-success' : 'text-danger'}">${distSlOpp > 0 ? '+' : ''}${distSlOpp.toFixed(1)}%</strong>
                                </div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
                                ${badgeHtml}
                                <button class="btn btn-secondary btn-view-trades" data-ticker="${item.ticker}" data-strat="${item.strat_label || selectedScannerStrategy}" style="font-size: 11px; padding: 4px 10px;">
                                    <i class="fa-solid fa-list-check"></i> Ver Trades
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        // 4. Render Live Signals Table (paginated, no duplicates in Combo)
        if (elLiveScannerTbody) {
            if (filtered.length === 0) {
                let msg = "No se encontraron activos para los filtros seleccionados.";
                if (selectedScannerStrategy === "SS11" && selectedScannerUniverse === "CRYPTO") {
                    msg = `<b>SS11</b> está pensada para acciones/ETFs (filtro Macro SPY). Para cripto usá <b>AIS11</b>.`;
                } else if (selectedScannerUniverse === "BUY_ONLY") {
                    msg = `No hay señales BUY hoy. Revisá <b>Posiciones</b> (${posCount}).`;
                } else if (selectedScannerUniverse === "POS_ONLY") {
                    msg = `No hay posiciones abiertas para este filtro.`;
                } else if (watchlistActionableOnly) {
                    msg = `No hay filas accionables. Desactivá «Solo accionables» para ver el universo completo.`;
                }
                elLiveScannerTbody.innerHTML = `<tr><td colspan="7" class="text-center p-4 text-muted">${msg}</td></tr>`;
            } else {
                elLiveScannerTbody.innerHTML = pageSlice.map(item => {
                    const distSl = (item.dist_sl_pct !== undefined && item.dist_sl_pct !== null) ? item.dist_sl_pct : 0;
                    const distSma = (item.dist_sma20_pct !== undefined && item.dist_sma20_pct !== null) ? item.dist_sma20_pct : 0;
                    const stratLine = item.is_combo
                        ? `<div class="ticker-sub">${item.category || ""}</div>`
                        : `<div class="ticker-sub">${item.strat_label || ""} · ${item.category || ""}</div>`;
                    
                    return `
                        <tr>
                            <td class="sticky-col">
                                <strong class="ticker-main">${item.ticker}</strong>
                                ${stratLine}
                            </td>
                            <td class="mono-cell">${formatPrice(item.price)}</td>
                            <td class="mono-cell ${(item.change_24h || 0) >= 0 ? 'text-success' : 'text-danger'}">
                                ${(item.change_24h || 0) >= 0 ? '+' : ''}${(item.change_24h || 0).toFixed(2)}%
                            </td>
                            <td class="signal-cell">${renderSignalCell(item)}</td>
                            <td class="mono-cell ${distSl >= 0 ? 'text-success' : 'text-danger'}" title="Distancia al stop loss -15%">
                                ${distSl > 0 ? '+' : ''}${distSl.toFixed(1)}%
                            </td>
                            <td class="mono-cell ${distSma >= 0 ? 'text-success' : 'text-danger'}" title="Distancia a SMA 20 (reentrada)">
                                ${distSma > 0 ? '+' : ''}${distSma.toFixed(1)}%
                            </td>
                            <td style="text-align:center;">
                                <button class="btn btn-secondary btn-view-trades" data-ticker="${item.ticker}" data-strat="${item.is_combo ? 'COMBO' : (item.strat_label || selectedScannerStrategy)}" type="button" style="font-size: 11px; padding: 4px 10px;">
                                    <i class="fa-solid fa-list-check"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        renderWatchlistPager(filtered.length, totalPages);

        // Attach event listeners for "Ver Trades" buttons
        document.querySelectorAll(".btn-view-trades").forEach(btn => {
            btn.addEventListener("click", () => {
                const tk = btn.getAttribute("data-ticker");
                const strat = btn.getAttribute("data-strat") || selectedScannerStrategy;
                openTradingViewTradeLog(tk, strat);
            });
        });
    }

    function renderWatchlistPager(totalItems, totalPages) {
        const elPager = document.getElementById("watchlist-pager");
        if (!elPager) return;
        if (totalItems <= WATCHLIST_PAGE_SIZE) {
            elPager.innerHTML = totalItems
                ? `<span class="pager-meta">Mostrando ${totalItems} tickers</span>`
                : "";
            return;
        }
        const from = watchlistPage * WATCHLIST_PAGE_SIZE + 1;
        const to = Math.min(totalItems, (watchlistPage + 1) * WATCHLIST_PAGE_SIZE);
        elPager.innerHTML = `
            <span class="pager-meta">${from}–${to} de ${totalItems}</span>
            <div class="pager-actions">
                <button type="button" class="btn btn-secondary btn-pager" id="watchlist-prev" ${watchlistPage <= 0 ? "disabled" : ""}>
                    <i class="fa-solid fa-chevron-left"></i> Anterior
                </button>
                <span class="pager-page">Pág. ${watchlistPage + 1} / ${totalPages}</span>
                <button type="button" class="btn btn-secondary btn-pager" id="watchlist-next" ${watchlistPage >= totalPages - 1 ? "disabled" : ""}>
                    Siguiente <i class="fa-solid fa-chevron-right"></i>
                </button>
            </div>
        `;
        const prev = document.getElementById("watchlist-prev");
        const next = document.getElementById("watchlist-next");
        if (prev) prev.addEventListener("click", () => { watchlistPage -= 1; renderLiveScannerData(); });
        if (next) next.addEventListener("click", () => { watchlistPage += 1; renderLiveScannerData(); });
    }

    // Open TradingView Trade Log Modal/Section
    let tvTradesSortKey = "entry_date";
    let tvTradesSortDir = "DESC"; // DESC = más reciente primero, ASC = más antiguo primero
    let activeTvTradesList = [];

    // Header click listeners for all sortable columns in TV Trades table
    document.querySelectorAll(".tv-sortable-th").forEach(th => {
        th.addEventListener("click", () => {
            const key = th.getAttribute("data-sort");
            if (tvTradesSortKey === key) {
                tvTradesSortDir = tvTradesSortDir === "ASC" ? "DESC" : "ASC";
            } else {
                tvTradesSortKey = key;
                tvTradesSortDir = (key === "ticker") ? "ASC" : "DESC";
            }
            renderTvTradesTable();
        });
    });

    // Botón para ver TODOS los trades globales de la cartera por fecha
    const elBtnShowAllTrades = document.getElementById("btn-show-all-trades");
    if (elBtnShowAllTrades) {
        elBtnShowAllTrades.addEventListener("click", () => openAllTradesDrawer(true));
    }

    function collectSignalsForDrawer(stratFilter) {
        if (!liveScannerData) return [];
        const ss11 = (liveScannerData.ss11_signals || []).map(x => ({ ...x, strat_label: "SS11" }));
        const ais11 = (liveScannerData.ais11_signals || []).map(x => ({ ...x, strat_label: "AIS11" }));
        if (stratFilter === "SS11") return ss11;
        if (stratFilter === "AIS11") return ais11;
        return [...ss11, ...ais11];
    }

    function summarizeTrades(allTrades) {
        const BASE_CAPITAL_PER_TRADE = 10000;
        const normalized = allTrades.map(t => {
            if (t.pnl !== undefined && t.pnl !== null && !Number.isNaN(Number(t.pnl))) return t;
            const retPct = Number(t.pct_return) || 0;
            return { ...t, pnl: Math.round((retPct / 100.0) * BASE_CAPITAL_PER_TRADE * 100) / 100 };
        });
        const closedTrades = normalized.filter(t => !t.is_open && t.exit_date !== "EN CURSO");
        const totalClosed = closedTrades.length;
        const wins = closedTrades.filter(t => (Number(t.pct_return) || 0) > 0);
        const winRate = totalClosed > 0 ? (wins.length / totalClosed) * 100 : 0;
        const totalNetProfit = closedTrades.reduce((acc, t) => acc + (Number(t.pnl) || 0), 0);
        const gains = closedTrades.filter(t => (Number(t.pct_return) || 0) > 0).reduce((acc, t) => acc + Number(t.pnl), 0);
        const losses = closedTrades.filter(t => (Number(t.pct_return) || 0) < 0).reduce((acc, t) => acc + Math.abs(Number(t.pnl)), 0);
        const profitFactor = losses > 0 ? (gains / losses) : (gains > 0 ? 99.0 : 1.0);
        return { normalized, totalClosed, winRate, totalNetProfit, profitFactor };
    }

    function applyTvSummary(summary) {
        if (elTvNetProfit) {
            elTvNetProfit.textContent = `$${summary.totalNetProfit.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
            elTvNetProfit.className = `val ${summary.totalNetProfit >= 0 ? 'text-success' : 'text-danger'}`;
        }
        if (elTvProfitFactor) elTvProfitFactor.textContent = summary.profitFactor.toFixed(2);
        if (elTvWinRate) elTvWinRate.textContent = `${summary.winRate.toFixed(1)}%`;
        if (elTvTotalTrades) elTvTotalTrades.textContent = summary.totalClosed;
    }

    function openAllTradesDrawer(resetTabs = true) {
        if (!liveScannerData) return;
        drawerMode = "all";
        drawerTicker = null;
        if (resetTabs) {
            drawerStratFilter = selectedScannerStrategy === "COMBO" ? "BOTH" : selectedScannerStrategy;
            syncDrawerStratTabs();
        }
        if (elDrawerStratTabs) elDrawerStratTabs.classList.remove("hidden-tabs");

        const list = collectSignalsForDrawer(drawerStratFilter);
        let allTrades = [];
        list.forEach(item => {
            (item.recent_trades || []).forEach(t => {
                allTrades.push({ ...t, ticker: item.ticker, strat_label: item.strat_label });
            });
        });

        const summary = summarizeTrades(allTrades);
        if (elSelectedTradeTicker) elSelectedTradeTicker.textContent = `Todos los activos (${summary.normalized.length})`;
        if (elSelectedTradeStrat) {
            elSelectedTradeStrat.textContent = drawerStratFilter === "BOTH" ? "SS11 + AIS11" : drawerStratFilter;
        }
        applyTvSummary(summary);
        activeTvTradesList = summary.normalized;
        tvTradesSortKey = "entry_date";
        tvTradesSortDir = "DESC";
        renderTvTradesTable();
        openTradeDrawer();
    }

    function syncDrawerStratTabs() {
        if (!elDrawerStratTabs) return;
        elDrawerStratTabs.querySelectorAll(".pill-btn").forEach(b => {
            b.classList.toggle("active", b.getAttribute("data-drawer-strat") === drawerStratFilter);
        });
    }

    let watchlistAutoCollapsedOnce = false;
    function maybeCollapseWatchlist(buyCount, posCount) {
        if (watchlistAutoCollapsedOnce) return;
        if (buyCount <= 0 && posCount <= 0) return;
        const header = document.querySelector('[data-collapse-target="live-signals-body"]');
        const body = document.getElementById("live-signals-body");
        if (!header || !body) return;
        if (localStorage.getItem("collapse_state_live-signals-body") !== null) {
            watchlistAutoCollapsedOnce = true;
            return;
        }
        header.classList.add("is-collapsed");
        body.style.display = "none";
        const hintSpan = header.querySelector(".collapse-hint");
        if (hintSpan) hintSpan.innerHTML = `<i class="fa-solid fa-expand"></i> Expandir`;
        localStorage.setItem("collapse_state_live-signals-body", "true");
        watchlistAutoCollapsedOnce = true;
    }

    function renderTvTradesTable() {
        if (!elTvTradesTbody) return;

        if (!activeTvTradesList || activeTvTradesList.length === 0) {
            elTvTradesTbody.innerHTML = `<tr><td colspan="10" class="text-center p-4 text-muted">No se registran operaciones históricas cerradas para este activo.</td></tr>`;
            return;
        }

        const sorted = [...activeTvTradesList].sort((a, b) => {
            let valA, valB;
            if (tvTradesSortKey === "entry_date" || tvTradesSortKey === "exit_date") {
                let strA = a[tvTradesSortKey] === "EN CURSO" ? "2099-12-31" : (a[tvTradesSortKey] || "1970-01-01");
                let strB = b[tvTradesSortKey] === "EN CURSO" ? "2099-12-31" : (b[tvTradesSortKey] || "1970-01-01");
                valA = new Date(strA).getTime();
                valB = new Date(strB).getTime();
                if (isNaN(valA)) valA = 0;
                if (isNaN(valB)) valB = 0;
            } else if (tvTradesSortKey === "ticker") {
                valA = a.ticker || ""; valB = b.ticker || "";
                return tvTradesSortDir === "ASC" ? valA.localeCompare(valB) : valB.localeCompare(valA);
            } else if (tvTradesSortKey === "pct_return") {
                valA = a.pct_return !== undefined ? a.pct_return : -999;
                valB = b.pct_return !== undefined ? b.pct_return : -999;
            } else if (tvTradesSortKey === "pnl") {
                valA = a.pnl !== undefined ? a.pnl : -999;
                valB = b.pnl !== undefined ? b.pnl : -999;
            } else if (tvTradesSortKey === "duration_days") {
                valA = a.duration_days !== undefined ? a.duration_days : 0;
                valB = b.duration_days !== undefined ? b.duration_days : 0;
            } else {
                valA = 0; valB = 0;
            }
            return tvTradesSortDir === "ASC" ? (valA - valB) : (valB - valA);
        });

        // Update header sort icons
        document.querySelectorAll(".tv-sortable-th").forEach(th => {
            const key = th.getAttribute("data-sort");
            const icon = th.querySelector("i");
            if (icon) {
                if (tvTradesSortKey === key) {
                    icon.className = tvTradesSortDir === "ASC" ? "fa-solid fa-sort-up text-warning" : "fa-solid fa-sort-down text-warning";
                } else {
                    icon.className = "fa-solid fa-sort";
                }
            }
        });

        elTvTradesTbody.innerHTML = sorted.map((t, idx) => `
            <tr>
                <td>#${idx + 1}</td>
                <td><strong style="font-family: var(--font-mono); font-size: 13px; color: var(--text-bright);">${t.ticker || 'LONG'}</strong></td>
                <td>${t.entry_date}</td>
                <td>${formatPrice(t.entry_price)}</td>
                <td>${t.exit_date}</td>
                <td>${formatPrice(t.exit_price)}</td>
                <td class="${t.pct_return >= 0 ? 'text-success' : 'text-danger'}">${t.pct_return >= 0 ? '+' : ''}${t.pct_return.toFixed(2)}%</td>
                <td class="${t.pnl >= 0 ? 'text-success' : 'text-danger'}">${t.pnl >= 0 ? '+' : ''}$${t.pnl.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                <td>${t.duration_days}d</td>
                <td><span class="opp-cat">${t.reason}</span></td>
            </tr>
        `).join('');
    }

    function openTradingViewTradeLog(ticker, stratId, resetTabs = true) {
        if (!liveScannerData) return;

        drawerMode = "single";
        drawerTicker = ticker;

        let effectiveStrat = stratId;
        if (!effectiveStrat || effectiveStrat === "COMBO") {
            effectiveStrat = drawerStratFilter === "AIS11" ? "AIS11" : (drawerStratFilter === "SS11" ? "SS11" : "BOTH");
        }

        if (resetTabs) {
            if (stratId === "AIS11" || stratId === "SS11") {
                drawerStratFilter = stratId;
            } else {
                drawerStratFilter = "BOTH";
            }
            syncDrawerStratTabs();
        }

        if (elDrawerStratTabs) elDrawerStratTabs.classList.remove("hidden-tabs");

        const filter = resetTabs ? drawerStratFilter : (drawerStratFilter || effectiveStrat);
        const list = collectSignalsForDrawer(filter === "BOTH" ? "BOTH" : filter);
        const matches = list.filter(x => x.ticker === ticker);
        if (!matches.length) return;

        let allTrades = [];
        matches.forEach(item => {
            (item.recent_trades || []).forEach(t => {
                allTrades.push({ ...t, ticker, strat_label: item.strat_label });
            });
        });

        if (elSelectedTradeTicker) elSelectedTradeTicker.textContent = ticker;
        if (elSelectedTradeStrat) {
            elSelectedTradeStrat.textContent = filter === "BOTH"
                ? matches.map(m => m.strat_label).join(" + ")
                : (filter === "AIS11" ? "AIS11" : "SS11");
        }

        if (matches.length === 1 && matches[0].metrics) {
            const m = matches[0].metrics;
            if (elTvNetProfit) {
                elTvNetProfit.textContent = `$${(m.net_profit_usd || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                elTvNetProfit.className = `val ${(m.net_profit_usd || 0) >= 0 ? 'text-success' : 'text-danger'}`;
            }
            if (elTvProfitFactor) elTvProfitFactor.textContent = (m.profit_factor || 0).toFixed(2);
            if (elTvWinRate) elTvWinRate.textContent = `${(m.win_rate || 0).toFixed(1)}%`;
            if (elTvTotalTrades) elTvTotalTrades.textContent = m.trades_count || allTrades.length;
            activeTvTradesList = allTrades;
        } else {
            const summary = summarizeTrades(allTrades);
            applyTvSummary(summary);
            activeTvTradesList = summary.normalized;
        }

        renderTvTradesTable();
        openTradeDrawer();
    }

    // -------------------------------------------------------------------------
    // Collapsible Sections Handler
    // -------------------------------------------------------------------------
    function initCollapsibleSections() {
        document.querySelectorAll(".collapsible-header").forEach(header => {
            const targetId = header.getAttribute("data-collapse-target");
            if (!targetId) return;

            const targetBody = document.getElementById(targetId);
            const hintSpan = header.querySelector(".collapse-hint");

            // Restore saved preference from localStorage
            const storageKey = `collapse_state_${targetId}`;
            const isCollapsedSaved = localStorage.getItem(storageKey) === "true";

            if (isCollapsedSaved && targetBody) {
                header.classList.add("is-collapsed");
                if (targetBody) targetBody.style.display = "none";
                if (hintSpan) hintSpan.innerHTML = `<i class="fa-solid fa-expand"></i> Expandir`;
            }

            header.addEventListener("click", (e) => {
                // Ignore clicks on buttons, inputs or links inside the header
                if (e.target.closest("button") || e.target.closest("input") || e.target.closest("a")) {
                    return;
                }

                const isCurrentlyCollapsed = header.classList.contains("is-collapsed");

                if (isCurrentlyCollapsed) {
                    header.classList.remove("is-collapsed");
                    if (targetBody) targetBody.style.display = "";
                    if (hintSpan) hintSpan.innerHTML = `<i class="fa-solid fa-compress"></i> Colapsar`;
                    localStorage.setItem(storageKey, "false");
                } else {
                    header.classList.add("is-collapsed");
                    if (targetBody) targetBody.style.display = "none";
                    if (hintSpan) hintSpan.innerHTML = `<i class="fa-solid fa-expand"></i> Expandir`;
                    localStorage.setItem(storageKey, "true");
                }
            });
        });
    }

    initCollapsibleSections();

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
        if (elKpiScanCountdown) {
            elKpiScanCountdown.textContent = `Auto ${autoRefreshCountdown}s`;
        }
    }, 1000);

    async function checkServerStatus() {
        try {
            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                if (data.loading === false) {
                    // Server is ready! Hide loader and load data
                    if (elLoaderStatusText) elLoaderStatusText.textContent = "Datos listos. Iniciando PineLab…";
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
