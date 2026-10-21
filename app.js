let cachedData = null;
let activeTab = 'market';
let chartInstances = [];

document.addEventListener('DOMContentLoaded', () => {
    fetchStockData();
});

function getTodayStr() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function getUpdateStatus() {
    const updatedAt = (cachedData && cachedData.updated_at) ? cachedData.updated_at : '';
    const updatedDate = updatedAt ? updatedAt.substring(0, 10) : '';
    const todayStr = getTodayStr();
    let diffDays = 0;
    if (updatedDate) {
        const d1 = new Date(todayStr + 'T00:00:00');
        const d2 = new Date(updatedDate + 'T00:00:00');
        diffDays = Math.round((d1 - d2) / 86400000);
    }
    const isUpdatedToday = updatedDate === todayStr;
    return { updatedAt, updatedDate, todayStr, diffDays, isUpdatedToday };
}

function buildUpdateBadgeHtml(dataDate) {
    const { updatedAt, todayStr, diffDays, isUpdatedToday } = getUpdateStatus();
    if (!updatedAt) return '';

    const dataDateHtml = dataDate
        ? `<span class="ml-2 pl-2 border-l border-white/15 ${dataDate < todayStr ? 'text-amber-300' : 'text-ink-soft'}">行情基準日：<b class="font-mono">${dataDate}</b></span>`
        : '';

    if (isUpdatedToday) {
        return `<div class="inline-flex items-center flex-wrap gap-y-1 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-xs font-mono text-emerald-300 shadow-sm">
            <span class="w-2 h-2 rounded-full bg-emerald-400 mr-2 animate-pulse"></span>
            <span>今日已更新：<b>${updatedAt}</b></span>
            ${dataDateHtml}
        </div>`;
    } else {
        const agoText = diffDays > 0 ? `（距今 ${diffDays} 天前，請記得執行更新！）` : '';
        return `<div class="inline-flex items-center flex-wrap gap-y-1 px-3 py-1.5 rounded-lg bg-amber-500/15 border border-amber-500/40 text-xs font-mono text-amber-300 shadow-sm">
            <span class="mr-1.5">⚠️ 尚未更新今日資料</span>
            <span>上次更新：<b>${updatedAt}</b>${agoText}</span>
            ${dataDateHtml}
        </div>`;
    }
}

function onDataLoaded(isLocal) {
    if (cachedData.updated_at) {
        const { updatedAt, diffDays, isUpdatedToday } = getUpdateStatus();
        const navEl = document.getElementById('last-updated');
        if (isUpdatedToday) {
            navEl.className = "shrink-0 text-[11px] font-mono px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/25 text-emerald-300";
            navEl.textContent = `🟢 最後更新：${updatedAt}${isLocal ? '（本地）' : ''}`;
        } else {
            navEl.className = "shrink-0 text-[11px] font-mono px-2.5 py-1 rounded-md bg-amber-500/15 border border-amber-500/40 text-amber-300 font-semibold";
            navEl.textContent = `⚠️ 舊資料：${updatedAt}${diffDays > 0 ? ` (${diffDays}天前)` : ''}`;
        }
    }
    document.getElementById('loading').classList.add('hidden');
    renderIndices(cachedData.data.indices);
    // 支援網址 #etf / #tea ... 直接開啟指定頁籤
    const hashTab = location.hash.replace('#', '');
    switchTab(['market', 'tea', 'moon', 'etf', 'fifty'].includes(hashTab) ? hashTab : 'market');
}

async function fetchStockData() {
    const localStatusEl = () => {
        const el = document.getElementById('local-data-note');
        if (el) el.classList.remove('hidden');
    };

    // 在本機 (直接雙擊 file:// 或 開啟頁面.bat localhost) 瀏覽時，優先讀本機最新資料，
    // 避免 file:// 因瀏覽器 CORS 攔截 fetch('data.json') 而誤抓 GitHub 上的舊版資料。
    const isLocal = location.protocol === 'file:' || ['localhost', '127.0.0.1', ''].includes(location.hostname);
    if (isLocal) {
        if (location.protocol !== 'file:') {
            try {
                const localResp = await fetch('data.json?t=' + new Date().getTime());
                if (localResp.ok) {
                    cachedData = await localResp.json();
                    localStatusEl();
                    onDataLoaded(true);
                    return;
                }
            } catch (e) {
                console.warn('本機 data.json fetch 失敗，改用內嵌 data.js:', e.message);
            }
        }
        if (window.__LOCAL_STOCK_DATA__) {
            cachedData = window.__LOCAL_STOCK_DATA__;
            localStatusEl();
            onDataLoaded(true);
            return;
        }
    }

    try {
        const url = 'https://raw.githubusercontent.com/SunTaiyo1331/yuanta-stock-screener/main/data.json?t=' + new Date().getTime();
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        cachedData = await response.json();
        onDataLoaded(false);
    } catch (error) {
        // 本地備援：GitHub 拉不到時改讀本機 frontend/data.json
        try {
            console.warn("GitHub 資料來源連線中斷，改讀本地 data.json:", error.message);
            const localResp = await fetch('data.json?t=' + new Date().getTime());
            if (localResp.ok) {
                cachedData = await localResp.json();
                localStatusEl();
                onDataLoaded(true);
                return;
            }
        } catch (e2) {
            console.warn("本地 data.json 也無法讀取 (若用 file:// 開啟請透過 開啟頁面.bat 啟動伺服器):", e2.message);
        }
        console.error("無法載入股票資料:", error);
        document.getElementById('last-updated').textContent = `資料載入失敗 (${error.message})`;
        const loadingEl = document.getElementById('loading');
        if (loadingEl) {
            loadingEl.textContent = `載入失敗: ${error.message}`;
            loadingEl.classList.remove('hidden');
        }
    }
}

function switchTab(tabName) {
    activeTab = tabName;

    // 更新所有 Tab 按鈕的高亮樣式 (Windows 11 深色模式風格)
    const tabs = ['market', 'tea', 'moon', 'etf', 'fifty'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-${t}`);
        if (!btn) return;
        if (t === tabName) {
            btn.className = "tab-btn px-3.5 py-1.5 rounded-md text-xs font-semibold whitespace-nowrap bg-accent-primary text-white shadow-win-active transition-all";
        } else {
            btn.className = "tab-btn px-3.5 py-1.5 rounded-md text-xs font-medium text-ink-soft hover:text-ink hover:bg-white/5 whitespace-nowrap transition-all";
        }
    });

    const viewMarket = document.getElementById('view-market');
    const viewScreener = document.getElementById('view-screener');

    if (tabName === 'market') {
        viewScreener.classList.add('hidden');
        viewMarket.classList.remove('hidden');
        if (cachedData && cachedData.data && cachedData.data.indices) {
            renderIndices(cachedData.data.indices);
        }
        // 延遲強制觸發所有圖表 resize 確保滿版正常
        setTimeout(() => {
            chartInstances.forEach(chart => {
                if (chart && typeof chart.resize === 'function') {
                    chart.resize();
                }
            });
        }, 100);
    } else {
        viewMarket.classList.add('hidden');
        viewScreener.classList.remove('hidden');
        renderStrategyData(tabName);
    }
}

function renderIndices(indices) {
    if (!indices || indices.length === 0) return;
    const ticker = document.getElementById('indices-ticker');
    ticker.innerHTML = '';

    const taiexIdx = indices.find(i => i.symbol === '^TWII' || i.name === '台股加權指數');
    const taiexDate = (taiexIdx && taiexIdx.history && taiexIdx.history.length > 0)
        ? taiexIdx.history[taiexIdx.history.length - 1].date
        : null;
    const marketBadgeEl = document.getElementById('market-update-badge');
    if (marketBadgeEl) {
        marketBadgeEl.innerHTML = buildUpdateBadgeHtml(taiexDate);
    }
    
    let html = '';
    indices.forEach(idx => {
        if (idx.symbol === '^TWII' || idx.name === '台股加權指數') {
            renderTaiexChart(idx);
        }
        
        const isUp = idx.change >= 0;
        const colorClass = isUp ? 'text-danger' : 'text-success';
        const sign = isUp ? '+' : '';
        html += `
            <div class="flex flex-col items-center justify-center p-3 bg-card-bg border border-card-border rounded-xl shadow-win-card backdrop-blur-md hover:border-white/20 transition-all">
                <span class="text-xs text-ink-soft font-medium mb-1 truncate w-full text-center">${idx.name}</span>
                <div class="flex flex-col items-center font-mono">
                    <span class="text-ink font-bold text-sm">${idx.price ? idx.price.toLocaleString() : '-'}</span>
                    <span class="text-[11px] font-semibold ${colorClass}">${sign}${idx.change} (${sign}${idx.change_percent}%)</span>
                </div>
            </div>
        `;
    });
    
    ticker.innerHTML = html;
    renderUSIndicesCharts(indices);
}

function formatVolumeWithUnit(val, unitType) {
    if (val === null || val === undefined || val === '-') return '-';
    const num = Number(val);
    if (isNaN(num) || num <= 0) return '-';
    if (unitType === '億元') {
        return `${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 億元`;
    }
    if (unitType === '股') {
        if (num >= 1e8) {
            return `${(num / 1e8).toFixed(2)} 億股`;
        }
        if (num >= 1e4) {
            return `${(num / 1e4).toFixed(0).toLocaleString()} 萬股`;
        }
        return `${num.toLocaleString()} 股`;
    }
    if (unitType === '張') {
        return `${num.toLocaleString()} 張`;
    }
    return num.toLocaleString();
}

function makeEChartsTooltipFormatter(unitType) {
    return function (params) {
        if (!params || !params.length) return '';
        const dateLabel = params[0].axisValueLabel || params[0].name || '';
        let html = `<div style="color:#f3f4f6;font-size:12px;line-height:1.6;min-width:155px;">`;
        html += `<div style="font-weight:700;color:#60cdff;margin-bottom:4px;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:2px;">📅 ${dateLabel}</div>`;
        params.forEach(p => {
            if (p.seriesType === 'candlestick' && Array.isArray(p.data)) {
                const openVal = p.data[1];
                const closeVal = p.data[2];
                const lowVal = p.data[3];
                const highVal = p.data[4];
                const isUp = closeVal >= openVal;
                const cColor = isUp ? '#f87171' : '#34d399';
                html += `<div style="display:flex;justify-content:space-between;gap:12px;"><span style="color:#b0b8c4;">開盤</span><span style="font-family:monospace;font-weight:600;color:#f3f4f6;">${Number(openVal).toLocaleString()}</span></div>`;
                html += `<div style="display:flex;justify-content:space-between;gap:12px;"><span style="color:#b0b8c4;">收盤</span><span style="font-family:monospace;font-weight:700;color:${cColor};">${Number(closeVal).toLocaleString()}</span></div>`;
                html += `<div style="display:flex;justify-content:space-between;gap:12px;"><span style="color:#b0b8c4;">最高</span><span style="font-family:monospace;font-weight:600;color:#f87171;">${Number(highVal).toLocaleString()}</span></div>`;
                html += `<div style="display:flex;justify-content:space-between;gap:12px;"><span style="color:#b0b8c4;">最低</span><span style="font-family:monospace;font-weight:600;color:#34d399;">${Number(lowVal).toLocaleString()}</span></div>`;
            } else {
                const rawVal = (p.data && typeof p.data === 'object' && 'value' in p.data) ? p.data.value : p.value;
                if (rawVal === null || rawVal === undefined || rawVal === '-') return;
                const isVol = (p.seriesName === '成交量' || p.seriesName === '成交金額');
                if (isVol && (!rawVal || rawVal === 0)) return;
                const formattedVal = isVol
                    ? formatVolumeWithUnit(rawVal, unitType)
                    : (typeof rawVal === 'number' ? rawVal.toLocaleString() : rawVal);
                html += `<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">
                    <span style="color:#b0b8c4;">${p.marker || ''}${p.seriesName}</span>
                    <span style="font-family:monospace;font-weight:600;color:#f3f4f6;">${formattedVal}</span>
                </div>`;
            }
        });
        html += `</div>`;
        return html;
    };
}

function renderTaiexChart(idx) {
    document.getElementById('taiex-current-price').textContent = idx.price ? idx.price.toLocaleString() : '';
    const isUp = idx.change >= 0;
    const sign = isUp ? '+' : '';
    const colorClass = isUp ? 'text-danger bg-danger/15' : 'text-success bg-success/15';
    const changeEl = document.getElementById('taiex-change');
    changeEl.textContent = `${sign}${idx.change} (${sign}${idx.change_percent}%)`;
    changeEl.className = `font-mono text-xs sm:text-sm px-2.5 py-0.5 rounded-md ${colorClass}`;
    
    if (!idx.history || idx.history.length === 0) return;

    const latestHist = idx.history[idx.history.length - 1];
    const volBadge = document.getElementById('taiex-volume-badge');
    if (volBadge && latestHist && latestHist.volume) {
        volBadge.textContent = `成交金額 ${formatVolumeWithUnit(latestHist.volume, '億元')}`;
        volBadge.classList.remove('hidden');
    }
    
    const chartDom = document.getElementById('taiex-chart');
    if (!chartDom) return;
    
    let myChart = echarts.getInstanceByDom(chartDom);
    if (!myChart) {
        myChart = echarts.init(chartDom);
        chartInstances.push(myChart);
    }
    
    const categoryData = [];
    const values = []; 
    const volumes = [];
    const ma5 = [];
    const ma20 = [];
    
    idx.history.forEach(item => {
        categoryData.push(item.date.substring(5)); 
        values.push([item.open, item.close, item.low, item.high]);
        volumes.push({
            value: item.volume,
            itemStyle: { color: item.close >= item.open ? '#f87171' : '#34d399' }
        });
        ma5.push(item.ma5);
        ma20.push(item.ma20);
    });

    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(28, 31, 38, 0.96)',
            borderColor: '#3b4252',
            textStyle: { color: '#f3f4f6', fontSize: 12 },
            formatter: makeEChartsTooltipFormatter('億元')
        },
        grid: [
            { left: 65, right: 20, top: '10%', height: '56%' }, 
            { left: 65, right: 20, top: '72%', height: '20%' }
        ],
        xAxis: [
            {
                type: 'category',
                data: categoryData,
                gridIndex: 0,
                axisLabel: { show: false },
                axisLine: { lineStyle: { color: '#3b4252' } }
            },
            {
                type: 'category',
                data: categoryData,
                gridIndex: 1,
                axisLabel: { color: '#8b949e', fontSize: 10 },
                axisLine: { lineStyle: { color: '#3b4252' } }
            }
        ],
        yAxis: [
            {
                scale: true,
                gridIndex: 0,
                splitLine: { show: true, lineStyle: { color: '#272c37', type: 'dashed' } },
                axisLabel: { color: '#8b949e', fontSize: 10 }
            },
            {
                gridIndex: 1,
                splitLine: { show: false },
                axisLabel: { show: false }
            }
        ],
        dataZoom: [
            { type: 'inside', xAxisIndex: [0, 1], start: 20, end: 100 }
        ],
        series: [
            {
                name: 'K線',
                type: 'candlestick',
                data: values,
                xAxisIndex: 0,
                yAxisIndex: 0,
                itemStyle: {
                    color: '#f87171', 
                    color0: '#34d399', 
                    borderColor: '#f87171',
                    borderColor0: '#34d399'
                }
            },
            {
                name: 'MA5',
                type: 'line',
                data: ma5,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#fef08a' },
                lineStyle: { width: 1.5 } 
            },
            {
                name: 'MA20',
                type: 'line',
                data: ma20,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#60cdff' },
                lineStyle: { width: 1.5 } 
            },
            {
                name: '成交金額',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: volumes
            }
        ]
    };

    myChart.setOption(option);
    setTimeout(() => myChart.resize(), 50);
}

function renderUSIndicesCharts(indices) {
    const container = document.getElementById('us-indices-charts');
    if (!container) return;
    container.innerHTML = '';

    const usTargets = [
        { symbol: '^SOX', name: '費城半導體' },
        { symbol: '^DJI', name: '道瓊工業指數' },
        { symbol: '^IXIC', name: 'NASDAQ 指數' },
        { symbol: '^GSPC', name: 'S&P 500 指數' }
    ];

    usTargets.forEach((target, idx) => {
        const item = indices.find(i => i.symbol === target.symbol || (i.name && i.name.includes(target.name.substring(0, 2))));
        if (!item || !item.history || item.history.length === 0) return;

        const cardDom = document.createElement('div');
        cardDom.className = "bg-card-bg border border-card-border rounded-xl p-4 shadow-win-card relative w-full";

        const isUp = item.change >= 0;
        const sign = isUp ? '+' : '';
        const colorClass = isUp ? 'text-danger bg-danger/15' : 'text-success bg-success/15';

        const latestHist = item.history[item.history.length - 1];
        const latestVolText = (latestHist && latestHist.volume > 0)
            ? `量 ${formatVolumeWithUnit(latestHist.volume, '股')}`
            : '';

        const chartId = `us-chart-${idx}`;
        cardDom.innerHTML = `
            <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div class="flex items-center gap-2">
                    <h4 class="text-base font-bold text-ink tracking-tight">${item.name}</h4>
                    <span class="text-xs text-ink-faint font-mono">${item.symbol || ''}</span>
                </div>
                <div class="flex items-center font-mono gap-2 flex-wrap">
                    ${latestVolText ? `<span class="text-[11px] text-ink-soft bg-white/5 px-2 py-0.5 rounded">${latestVolText}</span>` : ''}
                    <span class="text-ink font-bold text-base">${item.price ? item.price.toLocaleString() : ''}</span>
                    <span class="text-xs px-2 py-0.5 rounded font-semibold ${colorClass}">${sign}${item.change} (${sign}${item.change_percent}%)</span>
                </div>
            </div>
            <div id="${chartId}" class="w-full h-[280px] rounded-lg bg-[#1a1c22] border border-white/5"></div>
        `;

        container.appendChild(cardDom);

        setTimeout(() => {
            renderGenericIndexChart(chartId, item.history);
        }, 60);
    });
}

function renderGenericIndexChart(chartId, history) {
    const chartDom = document.getElementById(chartId);
    if (!chartDom) return;
    
    let myChart = echarts.getInstanceByDom(chartDom);
    if (!myChart) {
        myChart = echarts.init(chartDom);
        chartInstances.push(myChart);
    }

    const categoryData = [];
    const values = []; 
    const volumes = [];
    const ma5 = [];
    const ma20 = [];

    history.forEach(item => {
        categoryData.push(item.date.substring(5)); 
        values.push([item.open, item.close, item.low, item.high]);
        volumes.push({
            value: item.volume,
            itemStyle: { color: item.close >= item.open ? '#f87171' : '#34d399' }
        });
        ma5.push(item.ma5);
        ma20.push(item.ma20);
    });

    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(28, 31, 38, 0.96)',
            borderColor: '#3b4252',
            textStyle: { color: '#f3f4f6', fontSize: 11 },
            formatter: makeEChartsTooltipFormatter('股')
        },
        grid: [
            { left: 60, right: 15, top: '10%', height: '56%' }, 
            { left: 60, right: 15, top: '72%', height: '20%' }
        ],
        xAxis: [
            {
                type: 'category',
                data: categoryData,
                gridIndex: 0,
                axisLabel: { show: false },
                axisLine: { lineStyle: { color: '#3b4252' } }
            },
            {
                type: 'category',
                data: categoryData,
                gridIndex: 1,
                axisLabel: { color: '#8b949e', fontSize: 9 },
                axisLine: { lineStyle: { color: '#3b4252' } }
            }
        ],
        yAxis: [
            {
                scale: true,
                gridIndex: 0,
                splitLine: { show: true, lineStyle: { color: '#272c37', type: 'dashed' } },
                axisLabel: { color: '#8b949e', fontSize: 9 }
            },
            {
                gridIndex: 1,
                splitLine: { show: false },
                axisLabel: { show: false }
            }
        ],
        dataZoom: [
            { type: 'inside', xAxisIndex: [0, 1], start: 20, end: 100 }
        ],
        series: [
            {
                name: 'K線',
                type: 'candlestick',
                data: values,
                xAxisIndex: 0,
                yAxisIndex: 0,
                itemStyle: {
                    color: '#f87171', 
                    color0: '#34d399', 
                    borderColor: '#f87171',
                    borderColor0: '#34d399'
                }
            },
            {
                name: 'MA5',
                type: 'line',
                data: ma5,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#fef08a' },
                lineStyle: { width: 1.2 } 
            },
            {
                name: 'MA20',
                type: 'line',
                data: ma20,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#60cdff' },
                lineStyle: { width: 1.2 } 
            },
            {
                name: '成交量',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: volumes
            }
        ]
    };

    myChart.setOption(option);
    setTimeout(() => myChart.resize(), 50);
}

function renderStrategyData(strategy) {
    if (!cachedData || !cachedData.data) return;
    
    const titles = {
        'tea': '觀察區法人篇',
        'moon': '觀察區低檔科技股',
        'etf': '📊 ETF 專區',
        'fifty': '觀察區元大50'
    };
    
    document.getElementById('screener-title').textContent = titles[strategy] || strategy;

    // 計算該頁籤資料的行情基準日，連同最後更新時間顯示在每一頁右上角
    let tabDataDate = null;
    if (strategy === 'etf') {
        const allEtfs = [...(cachedData.data['long_etf'] || []), ...(cachedData.data['high_div'] || [])];
        if (allEtfs.length > 0) tabDataDate = allEtfs[0].date || null;
    } else {
        const list = cachedData.data[strategy] || [];
        if (list.length > 0) tabDataDate = list[0].date || null;
    }
    const screenerBadgeEl = document.getElementById('screener-update-badge');
    if (screenerBadgeEl) {
        screenerBadgeEl.innerHTML = buildUpdateBadgeHtml(tabDataDate);
    }
    
    const grid = document.getElementById('stock-grid');
    const emptyState = document.getElementById('empty-state');
    const tableContainer = document.getElementById('table-container');
    
    grid.innerHTML = '';
    
    ['long-etf-title', 'long-etf-table-wrap', 'high-div-title', 'high-div-table-wrap'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    });
    
    if (strategy === 'etf') {
        const longEtfs = cachedData.data['long_etf'] || [];
        const highDivEtfs = cachedData.data['high_div'] || [];
        
        if (longEtfs.length === 0 && highDivEtfs.length === 0) {
            tableContainer.classList.add('hidden');
            grid.classList.add('hidden');
            emptyState.classList.remove('hidden');
        } else {
            emptyState.classList.add('hidden');
            grid.classList.add('hidden');
            tableContainer.classList.remove('hidden');
            
            // 先渲染高股息 ETF (投資人最關注)
            if (highDivEtfs.length > 0) {
                document.getElementById('high-div-title').classList.remove('hidden');
                document.getElementById('high-div-table-wrap').classList.remove('hidden');
                renderETFTable('high_div', highDivEtfs, 'high-div-table-head', 'high-div-table-body');
            }

            // 再渲染長期市值型 ETF
            if (longEtfs.length > 0) {
                document.getElementById('long-etf-title').classList.remove('hidden');
                document.getElementById('long-etf-table-wrap').classList.remove('hidden');
                renderETFTable('long_etf', longEtfs, 'long-etf-table-head', 'long-etf-table-body');
            }
        }
    } else {
        tableContainer.classList.add('hidden');
        const stocks = cachedData.data[strategy];
        if (stocks && stocks.length > 0) {
            grid.classList.remove('hidden');
            emptyState.classList.add('hidden');
            renderStocks(stocks);
        } else {
            grid.classList.add('hidden');
            emptyState.classList.remove('hidden');
        }
    }
}

function renderStocks(stocks) {
    const grid = document.getElementById('stock-grid');
    const template = document.getElementById('stock-card-template');
    
    grid.innerHTML = '';
    
    stocks.forEach((stock, index) => {
        const clone = template.content.cloneNode(true);
        const card = clone.querySelector('.stock-card');
        
        clone.querySelector('.stock-name').textContent = stock.name;
        clone.querySelector('.stock-symbol').textContent = stock.date ? `${stock.symbol} · 行情日 ${stock.date}` : stock.symbol;
        
        const formatPrice = (num) => (num !== null && num !== undefined) ? new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num) : '-';
        clone.querySelector('.stock-price').textContent = formatPrice(stock.price);
        
        const changeEl = clone.querySelector('.stock-change');
        const changeValueEl = clone.querySelector('.change-value');
        const changePercentEl = clone.querySelector('.change-percent');
        const changeIconEl = clone.querySelector('.change-icon');
        
        if (stock.change === null || stock.change === undefined) {
            changeEl.classList.add('text-ink-faint', 'bg-white/5');
            changeValueEl.textContent = '-';
            changePercentEl.textContent = '-';
            changeIconEl.textContent = '';
        } else if (stock.change > 0) {
            changeEl.classList.add('text-danger', 'bg-danger/15');
            changeValueEl.textContent = `+${formatPrice(stock.change)}`;
            changePercentEl.textContent = `+${stock.change_percent}%`;
            changeIconEl.textContent = '▲';
        } else if (stock.change < 0) {
            changeEl.classList.add('text-success', 'bg-success/15');
            changeValueEl.textContent = formatPrice(stock.change);
            changePercentEl.textContent = `${stock.change_percent}%`;
            changeIconEl.textContent = '▼';
        } else {
            changeEl.classList.add('text-ink-soft', 'bg-white/5');
            changeValueEl.textContent = '0.00';
            changePercentEl.textContent = '0.00%';
            changeIconEl.textContent = '-';
        }
        
        let volVal = (stock.volume !== null && stock.volume !== undefined) ? new Intl.NumberFormat('en-US').format(stock.volume) : '-';
        clone.querySelector('.stock-volume').textContent = volVal;
        
        if (stock.suggested_buy_price !== null && stock.suggested_buy_price !== undefined) {
            clone.querySelector('.stock-suggest-price').textContent = formatPrice(stock.suggested_buy_price);
        } else {
            clone.querySelector('.stock-suggest-price').textContent = '-';
        }
        
        const chartId = `chart-${stock.symbol}-${index}`;
        const chartContainer = clone.querySelector('.chart-container');
        chartContainer.id = chartId;
        
        grid.appendChild(clone);
        
        if (stock.history && stock.history.length > 0) {
            setTimeout(() => {
                renderChart(chartId, stock.history);
            }, 100);
        }
    });
}

function renderETFTable(strategy, etfs, theadId, tbodyId) {
    const thead = document.getElementById(theadId || 'etf-table-head');
    const tbody = document.getElementById(tbodyId || 'etf-table-body');

    const isNum = (v) => v !== null && v !== undefined && !Number.isNaN(v);
    const pct = (v) => isNum(v) ? `${v.toFixed(2)}%` : '-';
    const signedPct = (v) => isNum(v) ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '-';
    const perfColor = (v) => !isNum(v) ? 'text-ink-faint' : (v >= 0 ? 'text-danger' : 'text-success');
    const note = (n) => n ? `<span class="block text-[10px] text-amber-400/90 font-sans font-normal leading-tight mt-0.5">${n}</span>` : '';

    // 欄位順序：商品 | 股價 (當日漲跌) | 今年漲跌 | 今年累計殖利率 | 去年漲跌 | 去年殖利率 | 去年100萬
    const th = (label, tip, align = 'text-right', extra = '') =>
        `<th class="py-3 px-4 ${align} ${extra}" title="${tip}">${label}</th>`;
    thead.innerHTML = '<tr>' +
        th('商品', '商品名稱 / 代號 / 配息頻率', 'text-left', 'w-[22%]') +
        th('股價 (當日漲跌)', '最新收盤價與當日漲跌幅', 'text-right', 'w-[17%]') +
        th('今年漲跌', '今年迄今單純股價累計漲幅（不含息，已還原股票分割）', 'text-right', 'w-[12%]') +
        th('今年累計殖利率', '今年度已除息各次之累計殖利率（配息 ÷ 除息前一日收盤價加總）', 'text-right', 'w-[12%] text-sky-400') +
        th('去年漲跌', '去年全年單純股價累計漲幅（不含息，下方為去年12/31收盤價）', 'text-right', 'w-[12%]') +
        th('去年殖利率', '去年全年度各次除息之累計殖利率（配息 ÷ 除息前一日收盤價加總）', 'text-right', 'w-[11%] text-accent-cyan') +
        th('去年100萬', '去年初投入台幣 100 萬元持有至年底之總損益（含股價漲跌 + 實領現金股息 + 股票分割）', 'text-right', 'w-[14%] text-amber-300') +
        '</tr>';

    let rows = '';
    etfs.forEach(etf => {
        const freq = etf.div_freq || '-';
        const priceStr = isNum(etf.price) ? etf.price.toFixed(2) : '-';
        const chgStr = isNum(etf.change_percent)
            ? `<span class="text-xs ml-1.5 ${perfColor(etf.change_percent)}">(${signedPct(etf.change_percent)})</span>` : '';
        const lyPriceHtml = isNum(etf.last_year_close)
            ? `<span class="block text-[11px] text-ink-faint font-mono font-normal leading-tight mt-0.5">${etf.last_year_close.toFixed(2)}</span>`
            : '';

        let profitHtml = '<span class="text-ink-faint">-</span>';
        let profitTip = '';
        if (isNum(etf.last_year_1m_profit)) {
            const p = etf.last_year_1m_profit;
            const prefix = p >= 0 ? '賺' : '賠';
            const absWan = (Math.abs(p) / 10000).toFixed(2);
            const absNum = Math.round(Math.abs(p)).toLocaleString('en-US');
            const colorCls = p >= 0 ? 'text-danger' : 'text-success';
            const pricePart = isNum(etf.last_year_1m_price_profit) ? `${etf.last_year_1m_price_profit >= 0 ? '+' : ''}${etf.last_year_1m_price_profit.toLocaleString('en-US')}` : '0';
            const divPart = isNum(etf.last_year_1m_div_profit) ? `+${etf.last_year_1m_div_profit.toLocaleString('en-US')}` : '+0';
            profitTip = `去年投入 100 萬：價差 ${pricePart} 元、領息 ${divPart} 元，合計${prefix} ${absNum} 元`;
            profitHtml = `<span class="${colorCls}">${prefix} ${absWan}萬</span><span class="block text-[11px] text-ink-faint font-mono font-normal leading-tight mt-0.5">${p >= 0 ? '+' : '-'}${absNum}</span>`;
        }

        const splitBadges = (etf.splits || []).map(s => {
            const shortDate = (s.date || '').substring(2);
            const tip = `${s.date} 進行 1 拆 ${s.ratio} 分割（分割前 ${s.before} 元 → 分割後 ${s.after} 元），漲跌幅已還原`;
            return `<span class="inline-block ml-1.5 px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 text-[10px] font-sans font-medium" title="${tip}">1拆${s.ratio} (${shortDate})</span>`;
        }).join('');

        const listingBadge = etf.listing_date ? (() => {
            const shortDate = etf.listing_date.substring(2);
            const tip = `${etf.listing_date} 掛牌上市${etf.last_year_perf === null ? '（今年新上市，故無去年資料）' : '（去年績效自上市日起算）'}`;
            return `<span class="inline-block ml-1.5 px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 text-[10px] font-sans font-medium" title="${tip}">上市 (${shortDate})</span>`;
        })() : '';

        rows += `<tr class="hover:bg-white/[0.04] transition-colors">
            <td class="py-3.5 px-4">
                <div class="font-bold text-ink text-sm leading-tight">${etf.name}</div>
                <div class="text-[11px] text-ink-faint font-mono mt-0.5 flex items-center flex-wrap gap-y-1">
                    <span>${etf.symbol} · <span class="text-ink-soft">${freq}</span></span>${splitBadges}${listingBadge}
                </div>
            </td>
            <td class="py-3.5 px-4 font-mono text-right text-ink font-semibold">${priceStr}${chgStr}</td>
            <td class="py-3.5 px-4 font-mono font-bold text-right ${perfColor(etf.ytd)}">${signedPct(etf.ytd)}</td>
            <td class="py-3.5 px-4 font-mono font-bold text-right text-sky-400">${pct(etf.ytd_yield)}</td>
            <td class="py-3.5 px-4 font-mono font-bold text-right ${perfColor(etf.last_year_perf)}">${signedPct(etf.last_year_perf)}${lyPriceHtml}</td>
            <td class="py-3.5 px-4 font-mono font-bold text-right text-accent-cyan">${pct(etf.last_year_yield)}</td>
            <td class="py-3.5 px-4 font-mono font-bold text-right" title="${profitTip}">${profitHtml}</td>
        </tr>`;
    });
    tbody.innerHTML = rows;
}

function renderChart(containerId, history) {
    const chartDom = document.getElementById(containerId);
    if (!chartDom) return;
    
    let myChart = echarts.getInstanceByDom(chartDom);
    if (!myChart) {
        myChart = echarts.init(chartDom);
        chartInstances.push(myChart);
    }
    
    const categoryData = [];
    const values = []; 
    const volumes = [];
    const ma5 = [];
    const ma10 = [];
    const ma60 = [];
    const ma248 = [];
    const bbUpper = [];
    const bbLower = [];
    const macd = [];
    const signal = [];
    const hist = [];
    
    history.forEach(item => {
        categoryData.push(item.date.substring(5)); 
        values.push([item.open, item.close, item.low, item.high]);
        volumes.push({
            value: item.volume,
            itemStyle: { color: item.close >= item.open ? '#f87171' : '#34d399' }
        });
        ma5.push(item.ma5);
        ma10.push(item.ma10);
        ma60.push(item.ma60);
        ma248.push(item.ma248);
        bbUpper.push(item.bb_upper);
        bbLower.push(item.bb_lower);
        macd.push(item.macd);
        signal.push(item.signal);
        hist.push(item.hist);
    });

    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(28, 31, 38, 0.96)',
            borderColor: '#3b4252',
            textStyle: { color: '#f3f4f6', fontSize: 12 },
            padding: 10,
            formatter: makeEChartsTooltipFormatter('張')
        },
        grid: [
            { left: 55, right: 15, top: '5%', height: '45%' }, 
            { left: 55, right: 15, top: '55%', height: '15%' },
            { left: 55, right: 15, top: '75%', height: '20%' }  
        ],
        xAxis: [
            {
                type: 'category',
                data: categoryData,
                gridIndex: 0,
                axisLabel: { show: false },
                axisLine: { lineStyle: { color: '#3b4252' } }
            },
            {
                type: 'category',
                data: categoryData,
                gridIndex: 1,
                axisLabel: { show: false },
                axisLine: { lineStyle: { color: '#3b4252' } }
            },
            {
                type: 'category',
                data: categoryData,
                gridIndex: 2,
                axisLabel: { color: '#8b949e', fontSize: 10 },
                axisLine: { lineStyle: { color: '#3b4252' } }
            }
        ],
        yAxis: [
            {
                scale: true,
                gridIndex: 0,
                splitLine: { show: true, lineStyle: { color: '#272c37', type: 'dashed' } },
                axisLabel: { color: '#8b949e', fontSize: 10 }
            },
            {
                gridIndex: 1,
                splitLine: { show: false },
                axisLabel: { show: false }
            },
            {
                gridIndex: 2,
                splitLine: { show: false },
                axisLabel: { show: false }
            }
        ],
        dataZoom: [
            { type: 'inside', xAxisIndex: [0, 1, 2], start: 0, end: 100 }
        ],
        series: [
            {
                name: 'K線',
                type: 'candlestick',
                data: values,
                xAxisIndex: 0,
                yAxisIndex: 0,
                itemStyle: {
                    color: '#f87171', 
                    color0: '#34d399', 
                    borderColor: '#f87171',
                    borderColor0: '#34d399'
                }
            },
            {
                name: 'MA5',
                type: 'line',
                data: ma5,
                xAxisIndex: 0,
                yAxisIndex: 0,
                smooth: false,
                showSymbol: false,
                connectNulls: true,
                itemStyle: { color: '#fef08a' },
                lineStyle: { width: 1.5, color: '#fef08a' } 
            },
            {
                name: 'MA10',
                type: 'line',
                data: ma10,
                xAxisIndex: 0,
                yAxisIndex: 0,
                smooth: false,
                showSymbol: false,
                connectNulls: true,
                itemStyle: { color: '#f472b6' },
                lineStyle: { width: 1.5, color: '#f472b6' } 
            },
            {
                name: 'MA60',
                type: 'line',
                data: ma60,
                xAxisIndex: 0,
                yAxisIndex: 0,
                smooth: false,
                showSymbol: false,
                connectNulls: true,
                itemStyle: { color: '#0abab5' },
                lineStyle: { width: 1.5, color: '#0abab5' } 
            },
            {
                name: 'MA248',
                type: 'line',
                data: ma248,
                xAxisIndex: 0,
                yAxisIndex: 0,
                smooth: false,
                showSymbol: false,
                connectNulls: true,
                itemStyle: { color: '#fb923c' },
                lineStyle: { width: 1.5, color: '#fb923c' } 
            },
            {
                name: 'BB上軌',
                type: 'line',
                data: bbUpper,
                xAxisIndex: 0,
                yAxisIndex: 0,
                smooth: false,
                showSymbol: false,
                connectNulls: true,
                itemStyle: { color: '#60cdff' },
                lineStyle: { width: 1, type: 'dashed', color: '#60cdff' } 
            },
            {
                name: 'BB下軌',
                type: 'line',
                data: bbLower,
                xAxisIndex: 0,
                yAxisIndex: 0,
                smooth: false,
                showSymbol: false,
                connectNulls: true,
                itemStyle: { color: '#60cdff' },
                lineStyle: { width: 1, type: 'dashed', color: '#60cdff' } 
            },
            {
                name: '成交量',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: volumes
            },
            {
                name: 'DIF',
                type: 'line',
                data: macd,
                xAxisIndex: 2,
                yAxisIndex: 2,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#38bdf8' },
                lineStyle: { width: 1 } 
            },
            {
                name: 'DEM',
                type: 'line',
                data: signal,
                xAxisIndex: 2,
                yAxisIndex: 2,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#fbbf24' },
                lineStyle: { width: 1 } 
            },
            {
                name: 'OSC',
                type: 'bar',
                xAxisIndex: 2,
                yAxisIndex: 2,
                data: hist.map(val => ({
                    value: val,
                    itemStyle: { color: val >= 0 ? '#f87171' : '#34d399' }
                }))
            }
        ]
    };

    myChart.setOption(option);
    setTimeout(() => myChart.resize(), 50);
}

window.addEventListener('resize', () => {
    chartInstances.forEach(chart => {
        if (chart && typeof chart.resize === 'function') {
            chart.resize();
        }
    });
});
