let cachedData = null;
let activeTab = 'market';
let verifyUnlocked = false;
let chartInstances = [];

document.addEventListener('DOMContentLoaded', () => {
    fetchStockData();
});

function unlockVerifyArea() {
    if (verifyUnlocked) return;
    const pwd = prompt('請輸入密碼：');
    if (pwd === '5957+') {
        verifyUnlocked = true;
        const lockBtn = document.getElementById('verify-lock-btn');
        const expandedTabs = document.getElementById('verify-expanded-tabs');
        if (lockBtn) lockBtn.classList.add('hidden');
        if (expandedTabs) expandedTabs.classList.remove('hidden');
        switchTab('etf');
    } else if (pwd !== null) {
        alert('密碼錯誤！');
    }
}

async function fetchStockData() {
    try {
        const url = 'https://raw.githubusercontent.com/SunTaiyo1331/yuanta-stock-screener/main/data.json?t=' + new Date().getTime();
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        cachedData = await response.json();
        
        if (cachedData.updated_at) {
            document.getElementById('last-updated').textContent = `最後更新時間：${cachedData.updated_at}`;
        }
        
        document.getElementById('loading').classList.add('hidden');
        renderIndices(cachedData.data.indices);
        switchTab('market');
    } catch (error) {
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

    // 更新所有 Tab 按鈕的高亮樣式
    const tabs = ['market', 'tea', 'moon', 'etf', 'fifty'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-${t}`);
        if (!btn) return;
        if (t === tabName) {
            btn.className = "tab-btn px-4 py-2.5 rounded-xl font-bold text-sm transition-all whitespace-nowrap bg-accent-primary text-white shadow-glow";
        } else {
            btn.className = "tab-btn px-4 py-2.5 rounded-xl font-bold text-sm text-gray-400 hover:text-white hover:bg-gray-800/60 transition-all whitespace-nowrap";
        }
    });

    const viewMarket = document.getElementById('view-market');
    const viewScreener = document.getElementById('view-screener');

    if (tabName === 'market') {
        viewScreener.classList.add('hidden');
        viewMarket.classList.remove('hidden');
        if (cachedData && cachedData.data.indices) {
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
    
    let html = '';
    indices.forEach(idx => {
        if (idx.symbol === '^TWII' || idx.name === '台股加權指數') {
            renderTaiexChart(idx);
        }
        
        const isUp = idx.change >= 0;
        const colorClass = isUp ? 'text-danger' : 'text-success';
        const sign = isUp ? '+' : '';
        html += `
            <div class="flex flex-col items-center justify-center p-3 bg-gray-900/60 border border-gray-800 rounded-2xl shadow-lg backdrop-blur-md">
                <span class="text-xs text-gray-400 font-semibold mb-1 truncate w-full text-center">${idx.name}</span>
                <div class="flex flex-col items-center font-mono">
                    <span class="text-white font-bold text-sm">${idx.price ? idx.price.toLocaleString() : '-'}</span>
                    <span class="text-[11px] font-semibold ${colorClass}">${sign}${idx.change} (${sign}${idx.change_percent}%)</span>
                </div>
            </div>
        `;
    });
    
    ticker.innerHTML = html;
    renderUSIndicesCharts(indices);
}

function renderTaiexChart(idx) {
    document.getElementById('taiex-current-price').textContent = idx.price ? idx.price.toLocaleString() : '';
    const isUp = idx.change >= 0;
    const sign = isUp ? '+' : '';
    const colorClass = isUp ? 'text-danger bg-danger/10' : 'text-success bg-success/10';
    const changeEl = document.getElementById('taiex-change');
    changeEl.textContent = `${sign}${idx.change} (${sign}${idx.change_percent}%)`;
    changeEl.className = `font-mono text-xs sm:text-sm px-2 py-0.5 rounded ml-2 ${colorClass}`;
    
    if (!idx.history || idx.history.length === 0) return;
    
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
            itemStyle: { color: item.close >= item.open ? '#ef4444' : '#10b981' }
        });
        ma5.push(item.ma5);
        ma20.push(item.ma20);
    });

    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(23, 27, 36, 0.9)',
            borderColor: '#374151',
            textStyle: { color: '#e5e7eb', fontSize: 12 },
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
                axisLine: { lineStyle: { color: '#4b5563' } }
            },
            {
                type: 'category',
                data: categoryData,
                gridIndex: 1,
                axisLabel: { color: '#9ca3af', fontSize: 10 },
                axisLine: { lineStyle: { color: '#4b5563' } }
            }
        ],
        yAxis: [
            {
                scale: true,
                gridIndex: 0,
                splitLine: { show: true, lineStyle: { color: '#1f2937', type: 'dashed' } },
                axisLabel: { color: '#9ca3af', fontSize: 10 }
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
                    color: '#ef4444', 
                    color0: '#10b981', 
                    borderColor: '#ef4444',
                    borderColor0: '#10b981'
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
                itemStyle: { color: '#38bdf8' },
                lineStyle: { width: 1.5 } 
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
        cardDom.className = "bg-gray-900/60 border border-gray-800 rounded-3xl p-5 backdrop-blur-md shadow-2xl relative w-full";

        const isUp = item.change >= 0;
        const sign = isUp ? '+' : '';
        const colorClass = isUp ? 'text-danger bg-danger/10' : 'text-success bg-success/10';

        const chartId = `us-chart-${idx}`;
        cardDom.innerHTML = `
            <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div class="flex items-center gap-2">
                    <h4 class="text-lg font-bold text-white tracking-tight">${item.name}</h4>
                    <span class="text-xs text-gray-400 font-mono">${item.symbol || ''}</span>
                </div>
                <div class="flex items-center font-mono">
                    <span class="text-white font-bold text-base mr-2">${item.price ? item.price.toLocaleString() : ''}</span>
                    <span class="text-xs px-2 py-0.5 rounded font-semibold ${colorClass}">${sign}${item.change} (${sign}${item.change_percent}%)</span>
                </div>
            </div>
            <div id="${chartId}" class="w-full h-[300px] rounded-xl bg-[#0e121a] border border-gray-800/80"></div>
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
            itemStyle: { color: item.close >= item.open ? '#ef4444' : '#10b981' }
        });
        ma5.push(item.ma5);
        ma20.push(item.ma20);
    });

    const option = {
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(23, 27, 36, 0.9)',
            borderColor: '#374151',
            textStyle: { color: '#e5e7eb', fontSize: 11 },
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
                axisLine: { lineStyle: { color: '#4b5563' } }
            },
            {
                type: 'category',
                data: categoryData,
                gridIndex: 1,
                axisLabel: { color: '#9ca3af', fontSize: 9 },
                axisLine: { lineStyle: { color: '#4b5563' } }
            }
        ],
        yAxis: [
            {
                scale: true,
                gridIndex: 0,
                splitLine: { show: true, lineStyle: { color: '#1f2937', type: 'dashed' } },
                axisLabel: { color: '#9ca3af', fontSize: 9 }
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
                    color: '#ef4444', 
                    color0: '#10b981', 
                    borderColor: '#ef4444',
                    borderColor0: '#10b981'
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
                itemStyle: { color: '#38bdf8' },
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
    if (!cachedData) return;
    
    const titles = {
        'tea': '🍵 茶葉智慧站',
        'moon': '🌙 止月策略',
        'etf': '📊 ETF 區',
        'fifty': '🏆 50大'
    };
    
    document.getElementById('screener-title').textContent = titles[strategy] || strategy;
    
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
            
            if (longEtfs.length > 0) {
                document.getElementById('long-etf-title').classList.remove('hidden');
                document.getElementById('long-etf-table-wrap').classList.remove('hidden');
                renderETFTable('long_etf', longEtfs, 'long-etf-table-head', 'long-etf-table-body');
            }
            if (highDivEtfs.length > 0) {
                document.getElementById('high-div-title').classList.remove('hidden');
                document.getElementById('high-div-table-wrap').classList.remove('hidden');
                renderETFTable('high_div', highDivEtfs, 'high-div-table-head', 'high-div-table-body');
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
        clone.querySelector('.stock-symbol').textContent = stock.symbol;
        
        const formatPrice = (num) => (num !== null && num !== undefined) ? new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num) : '-';
        clone.querySelector('.stock-price').textContent = formatPrice(stock.price);
        
        const changeEl = clone.querySelector('.stock-change');
        const changeValueEl = clone.querySelector('.change-value');
        const changePercentEl = clone.querySelector('.change-percent');
        const changeIconEl = clone.querySelector('.change-icon');
        
        if (stock.change === null || stock.change === undefined) {
            changeEl.classList.add('text-gray-400');
            changePercentEl.classList.add('bg-gray-800', 'text-gray-300');
            changeValueEl.textContent = '-';
            changePercentEl.textContent = '-';
            changeIconEl.textContent = '-';
        } else if (stock.change > 0) {
            changeEl.classList.add('text-danger');
            changePercentEl.classList.add('bg-danger/20', 'text-danger');
            changeValueEl.textContent = `+${formatPrice(stock.change)}`;
            changePercentEl.textContent = `+${stock.change_percent}%`;
            changeIconEl.textContent = '▲';
        } else if (stock.change < 0) {
            changeEl.classList.add('text-success');
            changePercentEl.classList.add('bg-success/20', 'text-success');
            changeValueEl.textContent = formatPrice(stock.change);
            changePercentEl.textContent = `${stock.change_percent}%`;
            changeIconEl.textContent = '▼';
        } else {
            changeEl.classList.add('text-gray-400');
            changePercentEl.classList.add('bg-gray-800', 'text-gray-300');
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
    
    thead.innerHTML = '';
    tbody.innerHTML = '';
    
    let headerHtml = '<tr><th class="py-4 px-6 text-left">代號</th><th class="py-4 px-6 text-left">名稱</th><th class="py-4 px-6 text-right">股價</th>';
    if (strategy === 'long_etf') {
        headerHtml += '<th class="py-4 px-6 text-right">去年績效</th><th class="py-4 px-6 text-right">本年度迄今績效</th></tr>';
    } else {
        headerHtml += '<th class="py-4 px-6 text-center">配息頻率</th><th class="py-4 px-6 text-right">去年殖利率</th><th class="py-4 px-6 text-right">今年累計殖利率</th><th class="py-4 px-6 text-right">去年績效</th><th class="py-4 px-6 text-right">本年度迄今績效</th></tr>';
    }
    thead.innerHTML = headerHtml;
    
    etfs.forEach(etf => {
        let ytdColor = (etf.ytd !== null && etf.ytd !== undefined && etf.ytd >= 0) ? 'text-danger' : 'text-success';
        let ytdVal = (etf.ytd !== null && etf.ytd !== undefined) ? (etf.ytd > 0 ? `+${etf.ytd.toFixed(2)}%` : `${etf.ytd.toFixed(2)}%`) : '-';
        
        let lastYearColor = (etf.last_year_perf !== null && etf.last_year_perf !== undefined && etf.last_year_perf >= 0) ? 'text-danger' : 'text-success';
        let lastYearVal = (etf.last_year_perf !== null && etf.last_year_perf !== undefined) ? (etf.last_year_perf > 0 ? `+${etf.last_year_perf.toFixed(2)}%` : `${etf.last_year_perf.toFixed(2)}%`) : '-';

        let priceVal = (etf.price !== null && etf.price !== undefined) ? etf.price : '-';
        
        let rowHtml = `<tr class="border-b border-gray-800 hover:bg-white/5 transition-colors">
            <td class="py-4 px-6 font-mono text-gray-400">${etf.symbol}</td>
            <td class="py-4 px-6 font-bold text-white text-lg">${etf.name}</td>
            <td class="py-4 px-6 font-mono text-right text-lg">${priceVal}</td>`;
            
        if (strategy === 'long_etf') {
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${lastYearColor}">${lastYearVal}</td>`;
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${ytdColor}">${ytdVal}</td>`;
        } else {
            let yieldColor = 'text-accent-primary';
            let ytdYieldColor = 'text-pink-400';
            rowHtml += `<td class="py-4 px-6 text-center"><span class="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-xs font-semibold tracking-widest">${etf.div_freq}</span></td>`;
            let yieldVal = (etf.last_year_yield !== null && etf.last_year_yield !== undefined) ? `${etf.last_year_yield.toFixed(2)}%` : '-';
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${yieldColor}">${yieldVal}</td>`;
            let ytdYieldVal = (etf.ytd_yield !== null && etf.ytd_yield !== undefined) ? `${etf.ytd_yield.toFixed(2)}%` : "-";
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${ytdYieldColor}">${ytdYieldVal}</td>`;
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${lastYearColor}">${lastYearVal}</td>`;
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${ytdColor}">${ytdVal}</td>`;
        }
        rowHtml += '</tr>';
        tbody.innerHTML += rowHtml;
    });
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
            itemStyle: { color: item.close >= item.open ? '#ef4444' : '#10b981' }
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
            backgroundColor: 'rgba(23, 27, 36, 0.9)',
            borderColor: '#374151',
            textStyle: { color: '#e5e7eb', fontSize: 12 },
            padding: 10
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
                axisLine: { lineStyle: { color: '#4b5563' } }
            },
            {
                type: 'category',
                data: categoryData,
                gridIndex: 1,
                axisLabel: { show: false },
                axisLine: { lineStyle: { color: '#4b5563' } }
            },
            {
                type: 'category',
                data: categoryData,
                gridIndex: 2,
                axisLabel: { color: '#9ca3af', fontSize: 10 },
                axisLine: { lineStyle: { color: '#4b5563' } }
            }
        ],
        yAxis: [
            {
                scale: true,
                gridIndex: 0,
                splitLine: { show: true, lineStyle: { color: '#1f2937', type: 'dashed' } },
                axisLabel: { color: '#9ca3af', fontSize: 10 }
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
                    color: '#ef4444', 
                    color0: '#10b981', 
                    borderColor: '#ef4444',
                    borderColor0: '#10b981'
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
                itemStyle: { color: '#a0522d' },
                lineStyle: { width: 1.5, color: '#a0522d' } 
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
                itemStyle: { color: '#60a5fa' },
                lineStyle: { width: 1, type: 'dashed', color: '#60a5fa' } 
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
                itemStyle: { color: '#60a5fa' },
                lineStyle: { width: 1, type: 'dashed', color: '#60a5fa' } 
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
                    itemStyle: { color: val >= 0 ? '#ef4444' : '#10b981' }
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
