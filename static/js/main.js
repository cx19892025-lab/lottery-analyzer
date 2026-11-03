/**
 * 六合彩数据分析工具 - 前端主逻辑
 * ECharts 图表渲染 + API 交互 + 图猜码解码
 */

// ==================== 全局状态 ====================
let dashboardData = null;
let currentStrategy = "balanced";
let decoderSelections = { zodiac: [], wuxing: [], color: [], direction: [], keywords: [] };

// 色波映射 (用于球的颜色)
const BALL_COLOR_MAP = {
    red: [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46],
    blue: [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48],
    green: [5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49],
};

function getBallColor(num) {
    if (BALL_COLOR_MAP.red.includes(num)) return "red";
    if (BALL_COLOR_MAP.blue.includes(num)) return "blue";
    return "green";
}

function createBall(num, isSpecial = false) {
    const color = getBallColor(num);
    const cls = isSpecial ? `ball ${color} special` : `ball ${color}`;
    return `<span class="${cls}">${num}</span>`;
}

// ==================== 标签页切换 ====================
document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");

        // 懒加载
        if (btn.dataset.tab === "history") loadHistory();
        if (btn.dataset.tab === "decoder") loadDecoderCategories();
        if (btn.dataset.tab === "backtest") loadBacktestTab();
        if (btn.dataset.tab === "settings") { loadSettings(); loadDataStatus(); }
    });
});

// ==================== 页面初始化 ====================
document.addEventListener("DOMContentLoaded", () => {
    loadDashboard();
    refreshAiStatus();   // 启动即探测 AI 是否已配置，用于图猜码页的降级提示
    loadDataStatus();    // 设置页数据管理区块的状态（惰性显示，切换到设置页时也会刷新）
});

// ==================== 仪表盘 ====================
async function loadDashboard() {
    try {
        const win = document.getElementById("windowSelect").value;
        const res = await fetch(`/api/dashboard?window=${win}`);
        dashboardData = await res.json();

        const winText = dashboardData.window ? `近${dashboardData.window}期` : "全部数据";
        document.getElementById("dataInfo").textContent =
            `已加载 ${dashboardData.total_periods} 期数据，当前统计：${winText}`;
        document.getElementById("dashboardLoading").style.display = "none";
        document.getElementById("dashboardContent").style.display = "block";

        renderStatCards();
        renderFrequencyChart();
        renderHeatmap();
        renderHotColdChart();
        renderMissingChart();
        renderOddEvenChart();
        renderBigSmallChart();
        renderTailChart();
        renderSumChart();
        renderConsecutiveChart();
        renderSpecialFreqChart();
        renderSpecialColorChart();
        renderSpecialZodiacChart();
        renderMainZodiacChart();
    } catch (e) {
        document.getElementById("dashboardLoading").innerHTML =
            `<span style="color:#ef4444;">❌ 加载失败: ${e.message}</span>`;
    }
}

function renderStatCards() {
    const d = dashboardData;
    const freq = d.frequency;
    const maxNum = Object.entries(freq).reduce((a, b) => b[1] > a[1] ? b : a);
    const minNum = Object.entries(freq).reduce((a, b) => b[1] < a[1] ? b : a);

    const html = `
        <div class="stat-card">
            <div class="value">${d.total_periods}</div>
            <div class="label">总期数</div>
        </div>
        <div class="stat-card">
            <div class="value">${maxNum[0]}</div>
            <div class="label">最高频号码 (${maxNum[1]}次)</div>
        </div>
        <div class="stat-card">
            <div class="value">${minNum[0]}</div>
            <div class="label">最低频号码 (${minNum[1]}次)</div>
        </div>
        <div class="stat-card">
            <div class="value">${d.consecutive.consecutive_rate}%</div>
            <div class="label">连号出现率</div>
        </div>
        <div class="stat-card">
            <div class="value">${d.sum.avg}</div>
            <div class="label">平均和值</div>
        </div>
    `;
    document.getElementById("statCards").innerHTML = html;
}

// ==================== 图表渲染 ====================

function renderFrequencyChart() {
    const chart = echarts.init(document.getElementById("chartFrequency"));
    const freq = dashboardData.frequency;
    const nums = Object.keys(freq).map(Number).sort((a, b) => a - b);
    const values = nums.map(n => freq[n]);
    const colors = nums.map(n => {
        const c = getBallColor(n);
        return c === "red" ? "#ef4444" : c === "blue" ? "#3b82f6" : "#22c55e";
    });

    chart.setOption({
        tooltip: { trigger: "axis" },
        xAxis: {
            type: "category",
            data: nums,
            axisLabel: { color: "#94a3b8", fontSize: 10 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar",
            data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
            barWidth: "60%",
        }],
        grid: { left: 40, right: 16, top: 16, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderHeatmap() {
    const el = document.getElementById("chartHeatmap");
    const chart = echarts.init(el);
    const freq = dashboardData.frequency;
    // 窄屏时只显示号码，避免"号码+次数"两行字挤在一起
    const compact = el.clientWidth < 460;

    // 7 行 7 列布局：第 0 行在最底部（ECharts 类目 y 轴自下而上），号码 = row*7 + col + 1
    //
    // 【重要】数据项必须是 [x, y, value] 三元组。
    // 这里曾经写成 [x, y, 次数, 号码]，而 visualMap 未指定 dimension，
    // ECharts 就按"最后一个维度"上色 —— 那个维度恰好是号码本身，
    // 导致颜色跟着号码大小走、而不是跟着出现次数走：
    // 出现 46 次的高频号 1 显示成深蓝冷色，出现 36 次的 44 号反而是中间色。
    const data = [];
    let minVal = Infinity, maxVal = -Infinity;
    for (let n = 1; n <= 49; n++) {
        const row = Math.floor((n - 1) / 7);
        const col = (n - 1) % 7;
        const cnt = freq[n] || 0;
        data.push([col, row, cnt]);
        if (cnt < minVal) minVal = cnt;
        if (cnt > maxVal) maxVal = cnt;
    }
    if (!isFinite(minVal)) { minVal = 0; maxVal = 1; }

    // 由格子坐标反推号码
    const numOf = p => p.data[1] * 7 + p.data[0] + 1;

    chart.setOption({
        tooltip: {
            formatter: p => `号码 <b>${numOf(p)}</b>：出现 <b>${p.data[2]}</b> 次`
        },
        xAxis: { type: "category", data: Array(7).fill(""), show: false },
        yAxis: { type: "category", data: Array(7).fill(""), show: false },
        visualMap: {
            // 用实际次数区间做映射，冷热对比更明显
            min: minVal,
            max: maxVal,
            dimension: 2,   // 关键：明确按第 3 个维度（出现次数）上色
            inRange: { color: ["#1e293b", "#0ea5e9", "#f59e0b", "#e94560"] },
            orient: "horizontal",
            left: "center",
            bottom: 2,
            // 不指定 itemWidth/itemHeight：横向模式下 ECharts 会自行互换两者，
            // 显式设成 140x12 反而得到一根竖条并压住中间格子。用默认值即可。
            text: ["多（热）", "少（冷）"],
            textStyle: { color: "#94a3b8", fontSize: 11 },
            calculable: true,
        },
        series: [{
            type: "heatmap",
            data: data,
            label: {
                show: true,
                formatter: p => compact
                    ? `${numOf(p)}`
                    : `{n|${numOf(p)}}\n{c|${p.data[2]}}`,
                rich: {
                    n: { color: "#ffffff", fontSize: 14, fontWeight: "bold", lineHeight: 17 },
                    c: { color: "rgba(255,255,255,0.72)", fontSize: 10, lineHeight: 12 },
                },
                color: "#ffffff",
                fontSize: compact ? 12 : 14,
                fontWeight: "bold",
            },
            itemStyle: { borderColor: "#0f0f1a", borderWidth: 3, borderRadius: 6 },
        }],
        grid: { left: 16, right: 16, top: 16, bottom: 46 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderHotColdChart() {
    const chart = echarts.init(document.getElementById("chartHotCold"));
    const hc = dashboardData.hot_cold;

    const hotNums = hc.hot.map(h => h[0]);
    const hotVals = hc.hot.map(h => h[1]);
    const coldNums = hc.cold.map(h => h[0]);
    const coldVals = hc.cold.map(h => h[1]);

    chart.setOption({
        tooltip: { trigger: "axis" },
        legend: { data: ["🔥 热号", "❄️ 冷号"], textStyle: { color: "#94a3b8" }, top: 0 },
        xAxis: {
            type: "category",
            data: [...hotNums, ...coldNums],
            axisLabel: { color: "#94a3b8" },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [
            {
                name: "🔥 热号", type: "bar",
                data: [...hotVals, ...new Array(coldNums.length).fill(0)],
                itemStyle: { color: "#ef4444" }
            },
            {
                name: "❄️ 冷号", type: "bar",
                data: [...new Array(hotNums.length).fill(0), ...coldVals],
                itemStyle: { color: "#3b82f6" }
            }
        ],
        grid: { left: 40, right: 16, top: 40, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderMissingChart() {
    const chart = echarts.init(document.getElementById("chartMissing"));
    const miss = dashboardData.missing;

    const sorted = Object.entries(miss).sort((a, b) => b[1] - a[1]).slice(0, 15);
    const nums = sorted.map(s => s[0]);
    const vals = sorted.map(s => s[1]);

    chart.setOption({
        tooltip: { trigger: "axis" },
        xAxis: {
            type: "category",
            data: nums,
            axisLabel: { color: "#94a3b8" },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            name: "遗漏期数",
            nameTextStyle: { color: "#94a3b8" },
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar",
            data: vals,
            itemStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: "#f59e0b" },
                    { offset: 1, color: "#d97706" }
                ])
            }
        }],
        grid: { left: 50, right: 16, top: 30, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderOddEvenChart() {
    const chart = echarts.init(document.getElementById("chartOddEven"));
    const dist = dashboardData.odd_even.distribution;

    chart.setOption({
        tooltip: { trigger: "item" },
        series: [{
            type: "pie",
            radius: ["40%", "70%"],
            data: Object.entries(dist).map(([k, v]) => ({
                name: `奇偶 ${k}`,
                value: v
            })),
            label: { color: "#e2e8f0", fontSize: 12 },
            emphasis: { itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.5)" } }
        }],
        color: ["#e94560", "#0ea5e9", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#06b6d4"],
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderBigSmallChart() {
    const chart = echarts.init(document.getElementById("chartBigSmall"));
    const dist = dashboardData.big_small.distribution;

    chart.setOption({
        tooltip: { trigger: "item" },
        series: [{
            type: "pie",
            radius: ["40%", "70%"],
            data: Object.entries(dist).map(([k, v]) => ({
                name: `大小 ${k}`,
                value: v
            })),
            label: { color: "#e2e8f0", fontSize: 12 },
        }],
        color: ["#f59e0b", "#3b82f6", "#ef4444", "#22c55e", "#a855f7", "#ec4899", "#06b6d4"],
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderTailChart() {
    const chart = echarts.init(document.getElementById("chartTail"));
    const tail = dashboardData.tail;
    const tails = Object.keys(tail).sort((a, b) => a - b);

    chart.setOption({
        tooltip: { trigger: "axis" },
        xAxis: {
            type: "category",
            data: tails,
            axisLabel: { color: "#94a3b8" },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar",
            data: tails.map(t => tail[t]),
            itemStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: "#10b981" },
                    { offset: 1, color: "#059669" }
                ])
            },
            barWidth: "50%"
        }],
        grid: { left: 40, right: 16, top: 16, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderSumChart() {
    const chart = echarts.init(document.getElementById("chartSum"));
    const sumData = dashboardData.sum;
    const dist = sumData.distribution;

    chart.setOption({
        tooltip: { trigger: "axis" },
        xAxis: {
            type: "category",
            data: dist.map(d => d.range),
            axisLabel: { color: "#94a3b8", rotate: 30 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar",
            data: dist.map(d => d.count),
            itemStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: "#8b5cf6" },
                    { offset: 1, color: "#6d28d9" }
                ])
            },
            barWidth: "60%"
        }],
        grid: { left: 40, right: 16, top: 16, bottom: 50 },
        graphic: [{
            type: "text",
            left: "center", bottom: 60,
            style: {
                text: `均值: ${sumData.avg}  |  中位数: ${sumData.median}  |  范围: ${sumData.min}-${sumData.max}`,
                fill: "#94a3b8", fontSize: 12
            }
        }]
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderConsecutiveChart() {
    const chart = echarts.init(document.getElementById("chartConsecutive"));
    const con = dashboardData.consecutive;

    chart.setOption({
        tooltip: { trigger: "item" },
        series: [{
            type: "pie",
            radius: ["45%", "70%"],
            data: [
                { name: "有连号", value: con.has_consecutive, itemStyle: { color: "#e94560" } },
                { name: "无连号", value: con.no_consecutive, itemStyle: { color: "#334155" } },
            ],
            label: {
                color: "#e2e8f0",
                formatter: "{b}: {c}期 ({d}%)"
            },
        }],
        graphic: [{
            type: "text",
            left: "center",
            top: "center",
            style: {
                text: `${con.consecutive_rate}%`,
                fill: "#e94560",
                fontSize: 28,
                fontWeight: "bold"
            }
        }]
    });
    window.addEventListener("resize", () => chart.resize());
}

// ==================== 特码 / 生肖专项统计 ====================

const WAVE_COLORS = { "红波": "#ef4444", "蓝波": "#3b82f6", "绿波": "#22c55e" };

function renderSpecialFreqChart() {
    const chart = echarts.init(document.getElementById("chartSpecialFreq"));
    const s = (dashboardData.special_stats || {});
    if (!s.frequency) return;

    const nums = Object.keys(s.frequency).map(Number).sort((a, b) => a - b);
    const values = nums.map(n => s.frequency[n]);
    const colors = nums.map(n => WAVE_COLORS[s.color_of_number[n]] || "#334155");

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => `${p[0].axisValue} 号<br/>开奖 ${p[0].value} 次`
                + `（期望 ${s.expected_per_number}）`
        },
        xAxis: {
            type: "category",
            data: nums,
            axisLabel: { color: "#94a3b8", fontSize: 10 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar",
            data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
            barWidth: "60%",
            markLine: {
                silent: true,
                symbol: "none",
                lineStyle: { color: "#f59e0b", type: "dashed", width: 1 },
                label: { color: "#f59e0b", formatter: "期望 {c}", fontSize: 10 },
                data: [{ yAxis: s.expected_per_number }]
            }
        }],
        grid: { left: 40, right: 16, top: 16, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderSpecialColorChart() {
    const chart = echarts.init(document.getElementById("chartSpecialColor"));
    const s = (dashboardData.special_stats || {});
    if (!s.color) return;

    chart.setOption({
        tooltip: { trigger: "item" },
        legend: {
            bottom: 0,
            textStyle: { color: "#94a3b8", fontSize: 11 },
            itemWidth: 10, itemHeight: 10,
        },
        series: [{
            type: "pie",
            radius: ["40%", "62%"],
            center: ["50%", "45%"],
            data: Object.keys(s.color).map(c => ({
                name: c,
                value: s.color[c],
                itemStyle: { color: WAVE_COLORS[c] },
            })),
            label: { color: "#e2e8f0", formatter: "{b}\n{d}%" },
        }],
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderSpecialZodiacChart() {
    const chart = echarts.init(document.getElementById("chartSpecialZodiac"));
    const s = (dashboardData.special_stats || {});
    if (!s.zodiac) return;

    const animals = Object.keys(s.zodiac);
    const avg = s.total / 12;

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => {
                const a = p[0].axisValue;
                return `${a}<br/>特码出现 ${p[0].value} 次（${s.zodiac_pct[a]}%）`;
            }
        },
        xAxis: {
            type: "category",
            data: animals,
            axisLabel: { color: "#e2e8f0", fontSize: 12 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar",
            data: animals.map(a => s.zodiac[a]),
            barWidth: "55%",
            itemStyle: { color: "#e94560" },
            markLine: {
                silent: true,
                symbol: "none",
                lineStyle: { color: "#f59e0b", type: "dashed", width: 1 },
                label: { color: "#f59e0b", formatter: "期望 {c}", fontSize: 10 },
                data: [{ yAxis: Number(avg.toFixed(1)) }]
            }
        }],
        grid: { left: 40, right: 16, top: 16, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderMainZodiacChart() {
    const chart = echarts.init(document.getElementById("chartMainZodiac"));
    const m = (dashboardData.main_zodiac || {});
    if (!m.counts) return;

    const animals = Object.keys(m.counts);
    const maxKey = animals.reduce((a, b) => m.counts[b] > m.counts[a] ? b : a);

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => {
                const a = p[0].axisValue;
                return `${a}<br/>正码出现 ${p[0].value} 次（${m.pct[a]}%）<br/>期望 ${m.expected} 次`;
            }
        },
        xAxis: {
            type: "category",
            data: animals,
            axisLabel: { color: "#e2e8f0", fontSize: 12 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar",
            data: animals.map(a => ({
                value: m.counts[a],
                itemStyle: { color: a === maxKey ? "#e94560" : "#3b82f6" },
            })),
            barWidth: "55%",
            markLine: {
                silent: true,
                symbol: "none",
                lineStyle: { color: "#f59e0b", type: "dashed", width: 1 },
                label: { color: "#f59e0b", formatter: "期望 {c}", fontSize: 10 },
                data: [{ yAxis: m.expected }]
            }
        }],
        grid: { left: 46, right: 16, top: 16, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

// ==================== 开奖记录 ====================
async function loadHistory() {
    const body = document.getElementById("historyBody");
    if (body.children.length > 0) return; // 已加载

    const res = await fetch("/api/history?limit=100");
    const data = await res.json();

    body.innerHTML = data.map(r => {
        const nums = [r.num1, r.num2, r.num3, r.num4, r.num5, r.num6];
        return `<tr>
            <td style="font-weight:600;">${r.period}</td>
            <td style="color:var(--text-secondary);">${r.draw_date}</td>
            ${nums.map(n => `<td>${createBall(n)}</td>`).join("")}
            <td>${createBall(r.special, true)}</td>
        </tr>`;
    }).join("");
}

// ==================== 智能选号 ====================
document.querySelectorAll(".strategy-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".strategy-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentStrategy = btn.dataset.strategy;
    });
});

async function generateNumbers() {
    const display = document.getElementById("recommendResult");
    display.innerHTML = '<div class="loading"><div class="spinner"></div> 计算中...</div>';

    const res = await fetch(`/api/recommend?strategy=${currentStrategy}`);
    const data = await res.json();

    // 逐个显示球的动画
    const balls = data.main.map((n, i) =>
        `<span class="ball ${getBallColor(n)}" style="animation: fadeIn 0.3s ease ${i * 0.15}s both;">${n}</span>`
    ).join("");

    const specialBall = `<span class="ball ${getBallColor(data.special)} special" style="animation: fadeIn 0.3s ease 1s both;">${data.special}</span>`;

    display.innerHTML = `
        <div class="label">${data.strategy}</div>
        <div class="balls-row">
            ${balls}
            <span class="ball plus">+</span>
            ${specialBall}
        </div>
        <div class="reason">💡 ${data.reason}</div>
    `;
}

// ==================== 策略回测 ====================
let backtestData = null;
let backtestLoaded = false;

const STRATEGY_COLORS = {
    balanced: "#0ea5e9",
    hot: "#ef4444",
    cold: "#3b82f6",
    random: "#a855f7",
};

function loadBacktestTab() {
    // 首次进入自动跑一次回测
    if (!backtestLoaded) {
        backtestLoaded = true;
        runBacktest();
    }
}

async function runBacktest() {
    const statusDiv = document.getElementById("backtestStatus");
    const contentDiv = document.getElementById("backtestContent");
    const btn = document.getElementById("btRunBtn");

    const periods = document.getElementById("btPeriods").value;
    const minHistory = document.getElementById("btMinHistory").value;
    const recentN = document.getElementById("btRecentN").value;
    const seed = document.getElementById("btSeed").value;

    btn.disabled = true;
    contentDiv.style.display = "none";
    statusDiv.innerHTML = '<div class="loading"><div class="spinner"></div> 正在逐期回测，请稍候...</div>';

    const params = new URLSearchParams({
        min_history: minHistory,
        recent_n: recentN,
        max_periods: periods === "0" ? "100000" : periods,
    });
    if (seed !== "") params.set("seed", seed);

    try {
        const res = await fetch(`/api/backtest?${params}`);
        const data = await res.json();

        if (!res.ok || data.error) {
            statusDiv.innerHTML = `<div class="result-display"><div class="label" style="color:#ef4444;">❌ ${data.error || "回测失败"}</div></div>`;
            btn.disabled = false;
            return;
        }

        backtestData = data;
        statusDiv.innerHTML = "";
        contentDiv.style.display = "block";

        renderBtStatCards();
        renderBtVerdict();
        renderBtMainHitsChart();
        renderBtSpecialChart();
        renderBtDistributionChart();
        renderBtTable();
    } catch (e) {
        statusDiv.innerHTML = `<div class="result-display"><div class="label" style="color:#ef4444;">❌ 网络错误: ${e.message}</div></div>`;
    }
    btn.disabled = false;
}

function renderBtStatCards() {
    const d = backtestData;
    const meta = d.meta;

    // 找出平均正码命中最好的策略
    const entries = Object.entries(d.strategies);
    const best = entries.reduce((a, b) =>
        b[1].avg_main_hits > a[1].avg_main_hits ? b : a);
    const totalSpecial = entries.reduce((s, [, v]) => s + v.special_hit_count, 0);

    document.getElementById("btStatCards").innerHTML = `
        <div class="stat-card">
            <div class="value">${meta.periods_backtested}</div>
            <div class="label">回测期数</div>
        </div>
        <div class="stat-card">
            <div class="value">${d.baseline.avg_main_hits}</div>
            <div class="label">随机基准（平均正码命中）</div>
        </div>
        <div class="stat-card">
            <div class="value" style="color:${STRATEGY_COLORS[best[0]]};">${best[1].avg_main_hits}</div>
            <div class="label">最优策略：${meta.strategy_names[best[0]]}</div>
        </div>
        <div class="stat-card">
            <div class="value">${totalSpecial}</div>
            <div class="label">全策略特码命中次数</div>
        </div>
        <div class="stat-card">
            <div class="value">${meta.min_history}</div>
            <div class="label">历史预热期数</div>
        </div>
    `;
}

function renderBtVerdict() {
    document.getElementById("btVerdict").innerHTML =
        `<div class="verdict-title">🔎 回测结论</div><div class="verdict-text">${backtestData.verdict}</div>`;
}

function renderBtMainHitsChart() {
    const el = document.getElementById("chartBtMainHits");
    const chart = echarts.init(el);
    const d = backtestData;

    const names = Object.keys(d.strategies);
    const labels = names.map(n => d.meta.strategy_names[n]);
    const values = names.map(n => d.strategies[n].avg_main_hits);
    const baseline = d.baseline.avg_main_hits;

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => {
                const i = p[0].dataIndex;
                const diff = (values[i] - baseline).toFixed(3);
                const sign = diff >= 0 ? "+" : "";
                return `${labels[i]}<br/>平均命中 ${values[i]} 个正码<br/>对比随机基准 ${sign}${diff}`;
            }
        },
        xAxis: {
            type: "category",
            data: labels,
            axisLabel: { color: "#94a3b8", fontSize: 11, interval: 0 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            name: "个/期",
            nameTextStyle: { color: "#94a3b8" },
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar",
            data: values.map((v, i) => ({
                value: v,
                itemStyle: { color: STRATEGY_COLORS[names[i]] }
            })),
            barWidth: "45%",
            markLine: {
                silent: true,
                symbol: "none",
                data: [{
                    yAxis: baseline,
                    lineStyle: { color: "#f59e0b", type: "dashed", width: 2 },
                    label: {
                        formatter: `随机基准 ${baseline}`,
                        color: "#f59e0b",
                        position: "insideEndTop"
                    }
                }]
            }
        }],
        grid: { left: 50, right: 20, top: 30, bottom: 40 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderBtSpecialChart() {
    const chart = echarts.init(document.getElementById("chartBtSpecial"));
    const d = backtestData;

    const names = Object.keys(d.strategies);
    const labels = names.map(n => d.meta.strategy_names[n]);
    const values = names.map(n => d.strategies[n].special_hit_rate);
    const baseline = d.baseline.special_hit_rate;

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => {
                const i = p[0].dataIndex;
                const s = d.strategies[names[i]];
                return `${labels[i]}<br/>特码命中 ${s.special_hit_count} 次<br/>命中率 ${values[i]}%`;
            }
        },
        xAxis: {
            type: "category",
            data: labels,
            axisLabel: { color: "#94a3b8", fontSize: 11, interval: 0 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            name: "%",
            nameTextStyle: { color: "#94a3b8" },
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar",
            data: values.map((v, i) => ({
                value: v,
                itemStyle: { color: STRATEGY_COLORS[names[i]] }
            })),
            barWidth: "45%",
            markLine: {
                silent: true,
                symbol: "none",
                data: [{
                    yAxis: baseline,
                    lineStyle: { color: "#f59e0b", type: "dashed", width: 2 },
                    label: {
                        formatter: `随机基准 ${baseline}%`,
                        color: "#f59e0b",
                        position: "insideEndTop"
                    }
                }]
            }
        }],
        grid: { left: 50, right: 20, top: 30, bottom: 40 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderBtDistributionChart() {
    const chart = echarts.init(document.getElementById("chartBtDistribution"));
    const d = backtestData;
    const names = Object.keys(d.strategies);

    // x 轴：命中 0-6 个正码
    const buckets = ["0", "1", "2", "3", "4", "5", "6"];

    chart.setOption({
        tooltip: { trigger: "axis" },
        legend: {
            data: names.map(n => d.meta.strategy_names[n]),
            textStyle: { color: "#94a3b8" },
            top: 0
        },
        xAxis: {
            type: "category",
            data: buckets,
            name: "命中正码个数",
            nameTextStyle: { color: "#94a3b8" },
            axisLabel: { color: "#94a3b8" },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            name: "期数",
            nameTextStyle: { color: "#94a3b8" },
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: names.map(n => ({
            name: d.meta.strategy_names[n],
            type: "bar",
            data: buckets.map(b => d.strategies[n].hit_distribution[b] || 0),
            itemStyle: { color: STRATEGY_COLORS[n] },
        })),
        grid: { left: 50, right: 20, top: 50, bottom: 40 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderBtTable() {
    const d = backtestData;
    const names = Object.keys(d.strategies);

    const head = `
        <thead>
            <tr>
                <th>策略</th>
                <th>平均正码命中</th>
                <th>平均总命中</th>
                <th>命中≥1个正码</th>
                <th>特码命中</th>
                <th>特码命中率</th>
                <th>单期最佳</th>
                <th>对比随机</th>
            </tr>
        </thead>`;

    const baseline = d.baseline.avg_main_hits;
    const rows = names.map(n => {
        const s = d.strategies[n];
        const diff = s.avg_main_hits - baseline;
        const sign = diff >= 0 ? "+" : "";
        const color = diff >= 0 ? "#22c55e" : "#ef4444";
        return `<tr>
            <td style="font-weight:600; color:${STRATEGY_COLORS[n]};">${d.meta.strategy_names[n]}</td>
            <td>${s.avg_main_hits}</td>
            <td>${s.avg_any_hits}</td>
            <td>${s.main_hit_rate}%</td>
            <td>${s.special_hit_count} 次</td>
            <td>${s.special_hit_rate}%</td>
            <td>${s.best_main_hits} 个</td>
            <td style="color:${color};">${sign}${diff.toFixed(3)}</td>
        </tr>`;
    }).join("");

    document.getElementById("btTable").innerHTML = head + `<tbody>${rows}</tbody>`;
}

// ==================== 设置页 ====================
let settingsLoaded = false;
let settingsDirty = false;   // 用户是否已手动改动过表单
let aiStatus = { available: false };

async function refreshAiStatus() {
    try {
        const res = await fetch("/api/vision/status");
        aiStatus = await res.json();
    } catch (e) {
        aiStatus = { available: false };
    }
    applyAiStatusToDecoder();
    return aiStatus;
}

function applyAiStatusToDecoder() {
    const warn = document.getElementById("aiWarning");
    const zone = document.getElementById("uploadZone");
    if (!warn || !zone) return;

    if (aiStatus.available) {
        warn.style.display = "none";
        zone.classList.remove("disabled");
    } else {
        warn.style.display = "flex";
        zone.classList.add("disabled");
    }
}

function onUploadZoneClick() {
    if (!aiStatus.available) {
        // 未配置时不弹文件框，直接引导去设置页
        gotoDecoderHint();
        return;
    }
    document.getElementById("imageInput").click();
}

function gotoDecoderHint() {
    const box = document.getElementById("decodeResult");
    if (box) {
        box.innerHTML = `<div class="result-display">
            <div class="label" style="color:#f59e0b;">⚠️ AI 识图尚未启用</div>
            <div class="label">请先到「⚙️ 设置」页填写接口地址与模型名，<br/>或直接在左侧手动选择元素后解码。</div>
        </div>`;
    }
}

function gotoSettings() {
    const btn = document.querySelector('.tab-btn[data-tab="settings"]');
    if (btn) btn.click();
}

async function loadSettings(force) {
    // 用户在表单里已经动过手时，不要用服务端值覆盖（否则切页/慢请求会把正在输入的内容抹掉）
    if (settingsDirty && !force) return;

    const res = await fetch("/api/settings");
    const s = await res.json();

    // 二次确认：请求期间若用户开始输入，同样放弃覆盖
    if (settingsDirty && !force) return;

    document.getElementById("setBaseUrl").value = s.base_url || "";
    document.getElementById("setModel").value = s.model || "";
    document.getElementById("setTimeout").value = s.timeout;
    document.getElementById("setMaxTokens").value = s.max_tokens;
    // Key 永不回显明文
    document.getElementById("setApiKey").value = "";
    document.getElementById("keyStatusHint").textContent = s.has_api_key
        ? `已保存 Key：${s.api_key_masked}（留空提交即保持不变）`
        : "尚未保存任何 Key";

    renderPresets(s.presets || []);
    settingsLoaded = true;
    settingsDirty = false;
}

function renderPresets(presets) {
    const box = document.getElementById("presetGrid");
    if (!box) return;
    box.innerHTML = presets.map(p => `
        <button type="button" class="preset-card" onclick="applyPreset('${p.id}')" data-preset="${p.id}">
            <div class="preset-name">${p.name}</div>
            <div class="preset-model">${p.model}</div>
            <div class="preset-note">${p.note}</div>
        </button>
    `).join("");
    box._presets = presets;
}

function applyPreset(id) {
    const box = document.getElementById("presetGrid");
    const p = (box._presets || []).find(x => x.id === id);
    if (!p) return;

    document.getElementById("setBaseUrl").value = p.base_url;
    document.getElementById("setModel").value = p.model;
    settingsDirty = true;
    document.querySelectorAll(".preset-card").forEach(el => {
        el.classList.toggle("active", el.dataset.preset === id);
    });
    showSettingsStatus("info", `已填入「${p.name}」的地址与模型名，请补上 API Key 后保存。`);
}

// 用户开始编辑就置脏，避免异步 loadSettings 把正在输入的内容冲掉
function markSettingsDirty() {
    settingsDirty = true;
    const listBox = document.getElementById("modelListBox");
    if (listBox) listBox.style.display = "none";
}

["setBaseUrl", "setApiKey", "setModel", "setTimeout", "setMaxTokens"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", markSettingsDirty);
});

function toggleKeyVisibility() {
    const input = document.getElementById("setApiKey");
    const btn = document.getElementById("toggleKeyBtn");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.textContent = show ? "隐藏" : "显示";
}

function resetSettingsForm() {
    settingsDirty = false;
    loadSettings(true);   // 强制用已保存的值覆盖
    showSettingsStatus("info", "已重新载入已保存的配置。");
}

function showSettingsStatus(kind, msg) {
    const box = document.getElementById("settingsStatus");
    const color = kind === "ok" ? "#22c55e" : (kind === "err" ? "#ef4444" : "#f59e0b");
    const icon = kind === "ok" ? "✅" : (kind === "err" ? "❌" : "ℹ️");
    box.innerHTML = `<div class="settings-status" style="border-color:${color}; color:${color};">
        ${icon} ${msg}
    </div>`;
}

function collectSettingsForm() {
    return {
        base_url: document.getElementById("setBaseUrl").value.trim(),
        api_key: document.getElementById("setApiKey").value.trim(),
        model: document.getElementById("setModel").value.trim(),
        timeout: document.getElementById("setTimeout").value,
        max_tokens: document.getElementById("setMaxTokens").value,
    };
}

async function saveSettings() {
    const btn = document.getElementById("saveSettingsBtn");
    const payload = collectSettingsForm();

    if (!payload.base_url || !payload.model) {
        showSettingsStatus("err", "接口地址与模型名都必须填写。");
        return;
    }

    btn.disabled = true;
    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
            showSettingsStatus("err", data.error || "保存失败");
            return;
        }
        showSettingsStatus("ok", "设置已保存到 data/settings.json");
        settingsDirty = false;
        await loadSettings(true);   // 保存后以服务端为准刷新（会清空 Key 输入框）
        await refreshAiStatus();
    } catch (e) {
        showSettingsStatus("err", `保存失败：${e.message}`);
    } finally {
        btn.disabled = false;
    }
}

async function testSettings() {
    const btn = document.getElementById("testSettingsBtn");
    const payload = collectSettingsForm();

    if (!payload.base_url || !payload.model) {
        showSettingsStatus("err", "请先填写接口地址与模型名。");
        return;
    }

    btn.disabled = true;
    showSettingsStatus("info", "正在分阶段测试连接，请稍候...");
    try {
        const res = await fetch("/api/settings/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        renderTestStages(data);
    } catch (e) {
        showSettingsStatus("err", `测试失败：${e.message}`);
    } finally {
        btn.disabled = false;
    }
}

function renderTestStages(data) {
    const stages = data.stages || [];
    const color = data.ok ? "#22c55e" : "#ef4444";
    const head = data.ok
        ? `✅ ${data.message || "连接成功"}`
        : `❌ ${data.error || "连接失败"}`;

    const rows = stages.map(s => {
        const icon = s.ok === true ? "✅" : (s.ok === false ? "❌" : "⚠️");
        const c = s.ok === true ? "#22c55e" : (s.ok === false ? "#ef4444" : "#f59e0b");
        return `<div class="stage-row">
            <span class="stage-icon" style="color:${c};">${icon}</span>
            <span class="stage-name">${s.name}</span>
            <span class="stage-detail" style="color:${c};">${s.detail || ""}</span>
        </div>`;
    }).join("");

    document.getElementById("settingsStatus").innerHTML = `
        <div class="settings-status" style="border-color:${color}; color:${color};">${head}</div>
        <div class="stage-list">${rows}</div>
    `;
}

async function listModels() {
    const btn = document.getElementById("listModelsBtn");
    const box = document.getElementById("modelListBox");
    const payload = collectSettingsForm();

    if (!payload.base_url) {
        showSettingsStatus("err", "请先填写接口地址。");
        return;
    }

    btn.disabled = true;
    btn.textContent = "读取中...";
    try {
        const res = await fetch("/api/settings/models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (!data.ok) {
            box.style.display = "none";
            showSettingsStatus("err", data.error || "读取模型列表失败");
            return;
        }

        const current = payload.model;
        box.style.display = "block";
        box.innerHTML = `
            <div class="model-list-head">共 ${data.count} 个模型，点击填入：</div>
            <div class="model-list-items">
                ${data.models.map(m => `
                    <span class="model-chip ${m === current ? "active" : ""}"
                          onclick="pickModel(this, '${m.replace(/'/g, "\\'")}')">${m}</span>
                `).join("")}
            </div>`;
        showSettingsStatus("ok", `已读取 ${data.count} 个模型，点选即可填入模型名。`);
    } catch (e) {
        showSettingsStatus("err", `读取失败：${e.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = "📋 读取可用模型";
    }
}

function pickModel(el, name) {
    document.getElementById("setModel").value = name;
    document.querySelectorAll(".model-chip").forEach(c => c.classList.remove("active"));
    el.classList.add("active");
}

// ==================== 图猜码 ====================
let decoderCategoriesLoaded = false;
let uploadedImageB64 = null;

async function loadDecoderCategories() {
    if (decoderCategoriesLoaded) return;
    decoderCategoriesLoaded = true;

    // 初始化拖拽上传
    initDragDrop();

    const res = await fetch("/api/decoder/categories");
    const categories = await res.json();

    const container = document.getElementById("decoderCategories");
    container.innerHTML = Object.entries(categories).map(([key, cat]) => `
        <div class="decode-category">
            <h3>${cat.icon} ${cat.name}</h3>
            ${cat.table_info ? `<div class="decode-table-hint">
                当前生效：农历 ${cat.table_info.lunar_year} ${cat.table_info.animal}年表
                （${cat.table_info.effective_from} 起，生肖表随农历新年轮换）
            </div>` : ""}
            <div class="decode-options">
                ${cat.options.map(opt => `
                    <span class="decode-option" data-category="${key}" data-value="${opt}"
                          onclick="toggleDecodeOption(this)">${opt}</span>
                `).join("")}
            </div>
        </div>
    `).join("");
}

// ========== 图片上传与拖拽 ==========

function initDragDrop() {
    const zone = document.getElementById("uploadZone");
    if (!zone) return;

    zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
    });

    zone.addEventListener("dragleave", () => {
        zone.classList.remove("dragover");
    });

    zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
        if (!aiStatus.available) {
            gotoDecoderHint();
            return;
        }
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith("image/")) {
            processImageFile(files[0]);
        }
    });
}

function handleImageUpload(event) {
    const file = event.target.files[0];
    if (file && file.type.startsWith("image/")) {
        processImageFile(file);
    }
}

function processImageFile(file) {
    if (!aiStatus.available) {
        gotoDecoderHint();
        return;
    }
    const reader = new FileReader();
    reader.onload = async (e) => {
        const dataUrl = e.target.result;
        uploadedImageB64 = dataUrl;

        // 显示预览
        const preview = document.getElementById("uploadPreview");
        const content = document.getElementById("uploadContent");
        const previewImg = document.getElementById("previewImage");
        const zone = document.getElementById("uploadZone");

        previewImg.src = dataUrl;
        preview.style.display = "block";
        content.style.display = "none";
        zone.classList.add("has-image");

        // 自动触发 AI 分析
        await doVisionDecode(dataUrl, file.type);
    };
    reader.readAsDataURL(file);
}

async function doVisionDecode(imageDataUrl, mimeType) {
    const statusDiv = document.getElementById("visionStatus");
    const resultDiv = document.getElementById("decodeResult");
    const traceDiv = document.getElementById("decodeTrace");
    const detailDiv = document.getElementById("visionDetail");
    const detailContent = document.getElementById("visionDetailContent");

    // 显示加载状态
    statusDiv.style.display = "block";
    resultDiv.innerHTML = '<div class="result-display"><div class="loading"><div class="spinner"></div> AI 正在识别图中元素...</div></div>';

    try {
        const res = await fetch("/api/decoder/vision", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                image: imageDataUrl,
                mime_type: mimeType || "image/png"
            })
        });

        statusDiv.style.display = "none";

        if (!res.ok) {
            const err = await res.json();
            const isConfig = res.status === 503;
            resultDiv.innerHTML = `<div class="result-display">
                <div class="label" style="color:#ef4444;">❌ ${err.error || '分析失败'}</div>
                ${isConfig ? '<button type="button" class="mini-btn" onclick="gotoSettings()">去设置</button>' : ''}
            </div>`;
            return;
        }

        const data = await res.json();
        const vision = data.vision;
        const decode = data.decode;
        const selections = data.selections;

        // 显示 AI 识别详情
        detailDiv.style.display = "block";
        let detailHtml = "";

        if (vision.description) {
            detailHtml += `<div class="trace-item">📝 <strong>图片描述：</strong>${vision.description}</div>`;
        }
        if (vision.animals && vision.animals.length > 0) {
            detailHtml += `<div class="trace-item">🐾 <strong>动物：</strong>${vision.animals.map(a => `<span class="vision-tag animal">${a}</span>`).join("")}</div>`;
        }
        if (vision.colors && vision.colors.length > 0) {
            detailHtml += `<div class="trace-item">🎨 <strong>颜色：</strong>${vision.colors.map(c => `<span class="vision-tag color-tag">${c}</span>`).join("")}</div>`;
        }
        if (vision.elements && vision.elements.length > 0) {
            detailHtml += `<div class="trace-item">☯️ <strong>五行元素：</strong>${vision.elements.map(e => `<span class="vision-tag element">${e}</span>`).join("")}</div>`;
        }
        if (vision.directions && vision.directions.length > 0) {
            detailHtml += `<div class="trace-item">🧭 <strong>方位：</strong>${vision.directions.map(d => `<span class="vision-tag direction">${d}</span>`).join("")}</div>`;
        }
        if (vision.objects && vision.objects.length > 0) {
            detailHtml += `<div class="trace-item">📦 <strong>物件：</strong>${vision.objects.map(o => `<span class="vision-tag object">${o}</span>`).join("")}</div>`;
        }
        if (vision.numbers && vision.numbers.length > 0) {
            detailHtml += `<div class="trace-item">🔢 <strong>数字：</strong>${vision.numbers.map(n => `<span class="vision-tag">${n}</span>`).join("")}</div>`;
        }

        detailContent.innerHTML = detailHtml || '<div class="trace-item">未识别到明显元素</div>';

        // 显示解码结果
        if (decode.recommended && decode.recommended.main) {
            const rec = decode.recommended;
            const balls = rec.main.map(n => createBall(n)).join("");
            const specialBall = createBall(rec.special, true);

            resultDiv.innerHTML = `
                <div class="result-display">
                    <div class="label">🔮 AI 图解码推荐号码</div>
                    <div class="balls-row">
                        ${balls}
                        <span class="ball plus">+</span>
                        ${specialBall}
                    </div>
                </div>
            `;

            // 候选号码排行
            if (decode.all_candidates && decode.all_candidates.length > 0) {
                const top15 = decode.all_candidates.slice(0, 15);
                resultDiv.innerHTML += `
                    <div style="margin-top:16px;">
                        <div style="color:var(--text-secondary); font-size:13px; margin-bottom:8px;">📊 候选号码权重排行</div>
                        <div class="balls-row">
                            ${top15.map(c => `
                                <span class="ball ${getBallColor(c.number)}" title="权重: ${c.score}"
                                      style="opacity:${0.4 + c.score / (top15[0].score) * 0.6}">
                                    ${c.number}
                                </span>
                            `).join("")}
                        </div>
                    </div>
                `;
            }

            // 自动同步手动选择状态
            syncManualSelections(selections);
        } else {
            resultDiv.innerHTML = '<div class="result-display"><div class="label">⚠️ 未能从图片中提取到足够的解码元素，请手动补充选择</div></div>';
        }

        // 解码过程
        traceDiv.innerHTML = (decode.decode_trace || []).map(t =>
            `<div class="trace-item">${t}</div>`
        ).join("") || '<div class="trace-item">无解码路径</div>';

    } catch (err) {
        statusDiv.style.display = "none";
        resultDiv.innerHTML = `<div class="result-display"><div class="label" style="color:#ef4444;">❌ 网络错误: ${err.message}</div></div>`;
    }
}

function syncManualSelections(selections) {
    // 把 AI 识别结果同步到手动选择面板的高亮状态
    decoderSelections = { ...selections };

    document.querySelectorAll(".decode-option").forEach(el => {
        const cat = el.dataset.category;
        const val = el.dataset.value;
        if (selections[cat] && selections[cat].includes(val)) {
            el.classList.add("selected");
        }
    });
}

function toggleDecodeOption(el) {
    const cat = el.dataset.category;
    const val = el.dataset.value;

    el.classList.toggle("selected");

    if (el.classList.contains("selected")) {
        if (!decoderSelections[cat]) decoderSelections[cat] = [];
        decoderSelections[cat].push(val);
    } else {
        decoderSelections[cat] = decoderSelections[cat].filter(v => v !== val);
    }
}

async function doDecode() {
    const resultDiv = document.getElementById("decodeResult");
    const traceDiv = document.getElementById("decodeTrace");

    resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div> 解码中...</div>';

    const res = await fetch("/api/decoder/decode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(decoderSelections)
    });
    const data = await res.json();

    if (!data.recommended || !data.recommended.main) {
        resultDiv.innerHTML = '<div class="result-display"><div class="label">⚠️ 请至少选择一个元素</div></div>';
        return;
    }

    const rec = data.recommended;
    const balls = rec.main.map(n => createBall(n)).join("");
    const specialBall = createBall(rec.special, true);

    resultDiv.innerHTML = `
        <div class="result-display">
            <div class="label">🔮 解码推荐号码</div>
            <div class="balls-row">
                ${balls}
                <span class="ball plus">+</span>
                ${specialBall}
            </div>
        </div>
    `;

    // 候选号码排行
    if (data.all_candidates && data.all_candidates.length > 0) {
        const top15 = data.all_candidates.slice(0, 15);
        resultDiv.innerHTML += `
            <div style="margin-top:16px;">
                <div style="color:var(--text-secondary); font-size:13px; margin-bottom:8px;">📊 候选号码权重排行</div>
                <div class="balls-row">
                    ${top15.map(c => `
                        <span class="ball ${getBallColor(c.number)}" title="权重: ${c.score}"
                              style="opacity:${0.4 + c.score / (top15[0].score) * 0.6}">
                            ${c.number}
                        </span>
                    `).join("")}
                </div>
            </div>
        `;
    }

    // 解码过程
    traceDiv.innerHTML = data.decode_trace.map(t =>
        `<div class="trace-item">${t}</div>`
    ).join("");
}

async function quickDecode() {
    const input = document.getElementById("keywordInput");
    const keyword = input.value.trim();
    if (!keyword) return;

    // 添加到 keywords
    if (!decoderSelections.keywords.includes(keyword)) {
        decoderSelections.keywords.push(keyword);
    }

    const res = await fetch(`/api/decoder/quick?keyword=${encodeURIComponent(keyword)}`);
    const data = await res.json();

    const traceDiv = document.getElementById("decodeTrace");

    if (data.numbers && data.numbers.length > 0) {
        traceDiv.innerHTML = `
            <div class="trace-item">🔍 关键词【${data.keyword}】→ ${data.mapped_to}</div>
            <div class="trace-item">📌 关联号码：${data.numbers.map(n => createBall(n)).join("")}</div>
        `;
    } else {
        traceDiv.innerHTML = `<div class="trace-item">⚠️ 未找到【${keyword}】的映射，请尝试其他关键词</div>`;
    }

    input.value = "";
}

// Enter 键触发快速解码
document.addEventListener("keydown", e => {
    if (e.key === "Enter" && document.activeElement.id === "keywordInput") {
        quickDecode();
    }
});


// ==================== 数据管理（真实开奖数据） ====================

function showDataStatus(kind, html) {
    const box = document.getElementById("dataStatusResult");
    const color = kind === "ok" ? "#22c55e" : (kind === "err" ? "#ef4444" : "#f59e0b");
    const icon = kind === "ok" ? "✅" : (kind === "err" ? "❌" : "ℹ️");
    box.innerHTML = `<div class="settings-status" style="border-color:${color}; color:${color};">
        ${icon} ${html}
    </div>`;
}

async function loadDataStatus() {
    const el = document.getElementById("dataStatusText");
    if (!el) return;
    try {
        const res = await fetch("/api/data/status");
        const d = await res.json();
        if (!d.total_periods) {
            el.innerHTML = "⚠️ 本地暂无开奖数据，请先「导入真实历史数据」";
            el.style.color = "#f59e0b";
        } else {
            el.innerHTML = `当前库内 <b>${d.total_periods}</b> 期，最新：第 ${d.latest_period} 期（${d.latest_date}）`;
            el.style.color = "";
        }
    } catch (e) {
        el.textContent = `读取状态失败：${e.message}`;
        el.style.color = "#ef4444";
    }
}

async function importRealData() {
    if (!confirm("导入将清空当前全部开奖数据（含模拟数据），并写入 1993 年至今的真实历史开奖，约需数秒。确定继续？")) {
        return;
    }
    const btn = document.getElementById("importDataBtn");
    btn.disabled = true;
    showDataStatus("info", "正在抓取并导入真实历史数据，请稍候...");
    try {
        const res = await fetch("/api/data/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ clear: true }),
        });
        const d = await res.json();
        if (!res.ok) {
            showDataStatus("err", d.error || "导入失败");
            return;
        }
        const s = d.fetched || {};
        showDataStatus("ok",
            `导入完成：新写入 ${d.inserted} 期，库内共 ${d.total_periods} 期` +
            `（种子源 ${s.seed_count} 期 + 增量源补充，合并去重 ${s.merged_count} 期` +
            `${s.conflict_count ? `，重叠期号码不一致 ${s.conflict_count} 期已按官方缓存为准` : ""}）` +
            (s.latest ? `，最新第 ${s.latest.period} 期（${s.latest.draw_date}）` : ""));
        loadDataStatus();
        loadDashboard();   // 数据变了，仪表盘直接刷新
    } catch (e) {
        showDataStatus("err", `导入失败：${e.message}`);
    } finally {
        btn.disabled = false;
    }
}

async function syncLatestData() {
    const btn = document.getElementById("syncDataBtn");
    btn.disabled = true;
    showDataStatus("info", "正在同步最新开奖...");
    try {
        const res = await fetch("/api/data/sync", { method: "POST" });
        const d = await res.json();
        if (!res.ok) {
            showDataStatus("err", d.error || "同步失败");
            return;
        }
        showDataStatus("ok",
            d.inserted > 0
                ? `同步完成：新增 ${d.inserted} 期（${(d.new_periods || []).join("、")}），库内共 ${d.total_periods} 期`
                : `已是最新：没有新增期号（数据源暂无新开奖，库内共 ${d.total_periods} 期）`);
        loadDataStatus();
        if (d.inserted > 0) loadDashboard();
    } catch (e) {
        showDataStatus("err", `同步失败：${e.message}`);
    } finally {
        btn.disabled = false;
    }
}
