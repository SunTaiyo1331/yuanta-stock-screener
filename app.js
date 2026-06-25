let cachedData = null;
let currentPendingStrategy = null;

document.addEventListener('DOMContentLoaded', () => {
    // 預先在背景載入資料
    fetchStockData();
});

async function fetchStockData() {
    try {
        const url = 'https://raw.githubusercontent.com/SunTaiyo1331/yuanta-stock-screener/main/data.json?t=' + new Date().getTime();
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        cachedData = await response.json();
        
        // 更新最後更新時間
        if (cachedData.updated_at) {
            document.getElementById('last-updated').textContent = `最後更新時間：${cachedData.updated_at}`;
        }
        
        renderIndices(cachedData.data.indices);
    } catch (error) {
        console.error("無法載入股票資料:", error);
        document.getElementById('last-updated').textContent = `資料載入失敗，請確認網路連線 (${error.message})`;
        const loadingEl = document.getElementById('loading');
        if (loadingEl) {
            loadingEl.textContent = `載入失敗: ${error.message}`;
            loadingEl.classList.remove('hidden');
        }
    }
}

function renderIndices(indices) {
    if (!indices || indices.length === 0) return;
    const ticker = document.getElementById('indices-ticker');
    ticker.innerHTML = '';
    
    let html = '';
    indices.forEach(idx => {
        const isUp = idx.change >= 0;
        const colorClass = isUp ? 'text-danger' : 'text-success'; // 台股紅漲綠跌
        const sign = isUp ? '+' : '';
        html += `
            <div class="flex flex-col items-center justify-center p-4 bg-gray-800/40 border border-gray-700/50 rounded-xl shadow-lg backdrop-blur-md">
                <span class="text-sm text-gray-300 font-semibold mb-1">${idx.name}</span>
                <div class="flex items-center gap-2 font-mono">
                    <span class="text-white font-bold">${idx.price.toLocaleString()}</span>
                    <span class="text-xs ${colorClass}">${sign}${idx.change} (${sign}${idx.change_percent}%)</span>
                </div>
            </div>
        `;
    });
    
    ticker.innerHTML = html;
}

function promptPassword(strategy) {
    currentPendingStrategy = strategy;
    document.getElementById('password-input').value = '';
    document.getElementById('password-error').classList.add('hidden');
    document.getElementById('password-modal').classList.remove('hidden');
    setTimeout(() => document.getElementById('password-input').focus(), 100);
}

function closePasswordModal() {
    document.getElementById('password-modal').classList.add('hidden');
    currentPendingStrategy = null;
}

function handleKeyPress(event) {
    if (event.key === 'Enter') {
        verifyPassword();
    }
}

function verifyPassword() {
    const pwd = document.getElementById('password-input').value;
    
    let isCorrect = false;
    if (currentPendingStrategy === 'advanced' && pwd === '55769+') {
        isCorrect = true;
    } else if (currentPendingStrategy === 'moon' && pwd === '9527+') {
        isCorrect = true;
    }
    
    if (isCorrect) {
        const strategy = currentPendingStrategy;
        closePasswordModal();
        if (strategy === 'advanced') {
            document.getElementById('advanced-menu').classList.remove('hidden');
            // Hide the password button if desired, or just leave it
            document.querySelector('button[onclick="promptPassword(\\\'advanced\\\')"]').classList.add('hidden');
        } else {
            selectStrategy(strategy);
        }
    } else {
        document.getElementById('password-error').classList.remove('hidden');
    }
}

function selectStrategy(strategy) {
    document.getElementById('landing-view').classList.add('hidden');
    document.getElementById('dashboard-view').classList.remove('hidden');
    
    const titleEl = document.getElementById('dashboard-title');
    if (strategy === 'tea') titleEl.textContent = '🍵 茶葉智慧站';
    else if (strategy === 'test') titleEl.textContent = '🧪 測試策略結果';
    else if (strategy === 'moon') titleEl.textContent = '🌙 止月隱藏策略';
    else if (strategy === 'long_etf') titleEl.textContent = '📈 長期ETF區';
    else if (strategy === 'high_div') titleEl.textContent = '💸 高股息ETF區';
    
    if (!cachedData) {
        document.getElementById('loading').classList.remove('hidden');
        document.getElementById('stock-grid').classList.add('hidden');
        document.getElementById('empty-state').classList.add('hidden');
        
        // 如果資料還沒回來，稍微等一下再試
        let waitCount = 0;
        const checkData = setInterval(() => {
            if (cachedData) {
                clearInterval(checkData);
                renderStrategyData(strategy);
            } else {
                waitCount++;
                if (waitCount > 20) { // wait up to 10 seconds
                    clearInterval(checkData);
                    document.getElementById('loading').textContent = '載入逾時，資料可能發生錯誤，請重新整理網頁。';
                }
            }
        }, 500);
    } else {
        renderStrategyData(strategy);
    }
}

function goBackToLanding() {
    document.getElementById('dashboard-view').classList.add('hidden');
    document.getElementById('landing-view').classList.remove('hidden');
}

function renderStrategyData(strategy) {
    document.getElementById('loading').classList.add('hidden');
    const titles = {
        'tea': '茶葉智慧站',
        'test': '測試策略結果',
        'moon': '止月隱藏策略',
        'long_etf': '長期 ETF 區',
        'high_div': '高股息 ETF 區'
    };
    
    document.getElementById('dashboard-title').textContent = titles[strategy];
    document.getElementById('update-time').textContent = cachedData.updated_at;
    
    const stocks = cachedData.data[strategy];
    const grid = document.getElementById('stock-grid');
    const emptyState = document.getElementById('empty-state');
    const tableContainer = document.getElementById('table-container');
    
    grid.innerHTML = ''; // Clear previous content
    
    if (strategy === 'long_etf' || strategy === 'high_div') {
        if (stocks && stocks.length > 0) {
            emptyState.classList.add('hidden');
            tableContainer.classList.remove('hidden');
            grid.classList.remove('hidden');
            renderETFTable(strategy, stocks);
            renderStocks(stocks);
        } else {
            tableContainer.classList.add('hidden');
            grid.classList.add('hidden');
            emptyState.classList.remove('hidden');
        }
    } else {
        tableContainer.classList.add('hidden');
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
        
        card.style.animationDelay = `${(index % 6) * 0.1}s`;
        card.classList.add('animate-slide-up');
        
        clone.querySelector('.stock-name').textContent = stock.name;
        clone.querySelector('.stock-symbol').textContent = stock.symbol;
        
        const formatPrice = (num) => new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num);
        clone.querySelector('.stock-price').textContent = formatPrice(stock.price);
        
        const changeEl = clone.querySelector('.stock-change');
        const changeValueEl = clone.querySelector('.change-value');
        const changePercentEl = clone.querySelector('.change-percent');
        const changeIconEl = clone.querySelector('.change-icon');
        
        if (stock.change > 0) {
            changeEl.classList.add('text-tw-up');
            changePercentEl.classList.add('bg-tw-up');
            changeValueEl.textContent = `+${formatPrice(stock.change)}`;
            changePercentEl.textContent = `+${stock.change_percent}%`;
            changeIconEl.textContent = '▲';
        } else if (stock.change < 0) {
            changeEl.classList.add('text-tw-down');
            changePercentEl.classList.add('bg-tw-down');
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
        
        clone.querySelector('.stock-volume').textContent = new Intl.NumberFormat('en-US').format(stock.volume);
        
        if (stock.suggested_buy_price) {
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

function renderETFTable(strategy, etfs) {
    const thead = document.getElementById('etf-table-head');
    const tbody = document.getElementById('etf-table-body');
    
    thead.innerHTML = '';
    tbody.innerHTML = '';
    
    // Generate headers
    let headerHtml = '<tr><th class="py-4 px-6 text-left">代號</th><th class="py-4 px-6 text-left">名稱</th><th class="py-4 px-6 text-right">股價</th>';
    if (strategy === 'long_etf') {
        headerHtml += '<th class="py-4 px-6 text-right">去年績效</th><th class="py-4 px-6 text-right">本年度迄今績效</th></tr>';
    } else {
        headerHtml += '<th class="py-4 px-6 text-center">配息頻率</th><th class="py-4 px-6 text-right">去年殖利率</th><th class="py-4 px-6 text-right">今年累計殖利率</th><th class="py-4 px-6 text-right">去年績效</th><th class="py-4 px-6 text-right">本年度迄今績效</th></tr>';
    }
    thead.innerHTML = headerHtml;
    
    // Generate rows
    etfs.forEach(etf => {
        let ytdColor = etf.ytd >= 0 ? 'text-danger' : 'text-success';
        let ytdVal = etf.ytd > 0 ? `+${etf.ytd.toFixed(2)}%` : `${etf.ytd.toFixed(2)}%`;
        
        let lastYearColor = etf.last_year_perf >= 0 ? 'text-danger' : 'text-success';
        let lastYearVal = etf.last_year_perf > 0 ? `+${etf.last_year_perf.toFixed(2)}%` : `${etf.last_year_perf.toFixed(2)}%`;
        
        let rowHtml = `<tr class="border-b border-gray-800 hover:bg-white/5 transition-colors">
            <td class="py-4 px-6 font-mono text-gray-400">${etf.symbol}</td>
            <td class="py-4 px-6 font-bold text-white text-lg">${etf.name}</td>
            <td class="py-4 px-6 font-mono text-right text-lg">${etf.price}</td>`;
            
        if (strategy === 'long_etf') {
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${lastYearColor}">${lastYearVal}</td>`;
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${ytdColor}">${ytdVal}</td>`;
        } else {
            let yieldColor = 'text-accent-primary';
            let ytdYieldColor = 'text-pink-400';
            rowHtml += `<td class="py-4 px-6 text-center"><span class="px-3 py-1 rounded-full bg-gray-800 border border-gray-700 text-xs font-semibold tracking-widest">${etf.div_freq}</span></td>`;
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${yieldColor}">${etf.last_year_yield.toFixed(2)}%</td>`;
            // This expects etf.ytd_yield to be populated
            let ytdYieldVal = etf.ytd_yield ? etf.ytd_yield.toFixed(2) : "0.00";
            rowHtml += `<td class="py-4 px-6 font-mono font-bold text-right ${ytdYieldColor}">${ytdYieldVal}%</td>`;
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
    
    const myChart = echarts.init(chartDom);
    
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
            { left: '10%', right: '5%', top: '5%', height: '45%' }, 
            { left: '10%', right: '5%', top: '55%', height: '15%' },
            { left: '10%', right: '5%', top: '75%', height: '20%' }  
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
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#fef08a' },
                lineStyle: { width: 1.5, color: '#fef08a' } 
            },
            {
                name: 'MA10',
                type: 'line',
                data: ma10,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#f472b6' },
                lineStyle: { width: 1.5, color: '#f472b6' } 
            },
            {
                name: 'MA60',
                type: 'line',
                data: ma60,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#0abab5' },
                lineStyle: { width: 1.5, color: '#0abab5' } 
            },
            {
                name: 'MA248',
                type: 'line',
                data: ma248,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#a0522d' },
                lineStyle: { width: 1.5, color: '#a0522d' } 
            },
            {
                name: 'BB Upper',
                type: 'line',
                data: bbUpper,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#9ca3af' },
                lineStyle: { width: 1, type: 'dashed', color: '#9ca3af' }
            },
            {
                name: 'BB Lower',
                type: 'line',
                data: bbLower,
                smooth: true,
                showSymbol: false,
                itemStyle: { color: '#9ca3af' },
                lineStyle: { width: 1, type: 'dashed', color: '#9ca3af' }
            },
            {
                name: '成交量',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: volumes
            },
            {
                name: 'MACD Hist',
                type: 'bar',
                xAxisIndex: 2,
                yAxisIndex: 2,
                data: hist.map(val => ({
                    value: val,
                    itemStyle: { color: val >= 0 ? '#ef4444' : '#10b981' }
                }))
            },
            {
                name: 'DIF',
                type: 'line',
                data: macd,
                xAxisIndex: 2,
                yAxisIndex: 2,
                showSymbol: false,
                itemStyle: { color: '#fb923c' },
                lineStyle: { width: 1, color: '#fb923c' }
            },
            {
                name: 'MACD(Signal)',
                type: 'line',
                data: signal,
                xAxisIndex: 2,
                yAxisIndex: 2,
                showSymbol: false,
                itemStyle: { color: '#38bdf8' },
                lineStyle: { width: 1, color: '#38bdf8' }
            }
        ]
    };
    
    myChart.setOption(option);
    
    window.addEventListener('resize', () => {
        myChart.resize();
    });
}
