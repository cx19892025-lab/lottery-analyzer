/**
 * 六合彩数据分析工具 - 前端主逻辑
 * ECharts 图表渲染 + API 交互 + 图猜码解码
 */

/**
 * 候选号码的悬浮提示：把该号码的命中线索拼成一行文本。
 * 用于「候选号码权重排行」里的 title 属性。
 */
function reasonTooltip(decode, number, score) {
    const reasons = decode.reasons || {};
    const list = reasons[String(number)] || [];
    if (list.length === 0) return `权重 ${score}`;
    const parts = list.map(r => `${r.dim}·${r.label}(+${r.weight})`);
    return `权重 ${score}｜${parts.join("，")}`;
}

// ==================== 推荐理由渲染 ====================

/**
 * 渲染每个推荐号码的「为什么是它」。
 *
 * 后端 decode_elements 会为每个号码返回 reasons 数组，形如
 *   [{dim:"数字", label:"8", weight:5, desc:"图上直接出现数字「8」"}, ...]
 * 这里按维度分组展示，让用户看懂「8 号为什么被推荐」。
 */
function renderReasonList(decode, numbers) {
    const reasons = decode.reasons;
    if (!reasons || !numbers || numbers.length === 0) return "";

    const scoreOf = {};
    (decode.all_candidates || []).forEach(c => { scoreOf[c.number] = c.score; });

    const rows = numbers.map(n => {
        const list = reasons[String(n)] || reasons[n] || [];
        if (list.length === 0) {
            return `<div class="reason-row">
                <span class="ball ${getBallColor(n)}">${n}</span>
                <div class="reason-body"><span class="reason-empty">无直接线索</span></div>
            </div>`;
        }
        // 按维度归并：同一维度可能命中多次（如两个关键词都指向火）
        const byDim = {};
        list.forEach(r => {
            (byDim[r.dim] = byDim[r.dim] || []).push(r);
        });
        const dimIcons = {
            "数字": "🔢", "数量": "🔢", "生肖": "🐾", "五行": "☯️",
            "色波": "🎨", "方位": "🧭",
        };
        const chips = Object.entries(byDim).map(([dim, rs]) => {
            const icon = dimIcons[dim] || "•";
            const labels = [...new Set(rs.map(r => r.label))].join("/");
            const w = rs.reduce((s, r) => s + r.weight, 0);
            // desc 是「图上什么导致这条线索」，例如「图上刻字「龍」」「图中出现「马」」
            const descs = [...new Set(rs.map(r => r.desc))].filter(Boolean);
            const title = descs.join("；");
            return `<span class="reason-chip dim-${dim}" title="${title}">
                ${icon} ${dim}·${labels} <b>+${w}</b>
            </span>`;
        }).join("");

        return `<div class="reason-row">
            <span class="ball ${getBallColor(n)}">${n}</span>
            <div class="reason-body">
                <div class="reason-score">总权重 ${scoreOf[n] ?? "?"}</div>
                <div class="reason-chips">${chips}</div>
            </div>
        </div>`;
    }).join("");

    return `
        <div class="reason-box">
            <div class="reason-title">💡 推荐理由</div>
            ${rows}
        </div>
    `;
}

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

/**
 * 渲染「正码 + 特码」一行。
 * 解码器在候选不足 7 个时会返回 special = null（六合彩七球互异，
 * 宁可不给特码也不能与正码重复），此时不能画出 "+ null" 这种球。
 */
function renderBallsRow(rec) {
    const balls = (rec.main || []).map(n => createBall(n)).join("");
    if (rec.special == null) {
        return `<div class="balls-row">${balls}
            <span class="no-special">候选号码不足 7 个，暂无特码推荐</span>
        </div>`;
    }
    return `<div class="balls-row">
        ${balls}
        <span class="ball plus">+</span>
        ${createBall(rec.special, true)}
    </div>`;
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
        if (btn.dataset.tab === "tracker") initTracker();
        if (btn.dataset.tab === "recommend") {
            // 每次都重新拉取：连续不出榜单是"实时"数据，
            // 用户同步过新数据后再进来必须看到最新结果。
            // （早期用 boardLoaded 只加载一次，导致榜单永远停在首次进入时的状态）
            loadZodiacBoard();
            loadMissingBoard();
            boardsStale = false;
        }
        if (btn.dataset.tab === "settings") { loadSettings(); loadDataStatus(); }
    });
});

// ==================== 页面初始化 ====================
document.addEventListener("DOMContentLoaded", () => {
    loadDashboard();
    refreshAiStatus();   // 启动即探测 AI 是否已配置，用于图猜码页的降级提示
    loadDataStatus();    // 设置页数据管理区块的状态（惰性显示，切换到设置页时也会刷新）
    initStaleBar();      // 顶部数据过期提示条的按钮绑定

    // 连续不出榜单：进入选号页时加载，也可手动刷新
    const rb = document.getElementById("boardRefreshBtn");
    if (rb) rb.addEventListener("click", loadMissingBoard);
    const cb = document.getElementById("chaseRunBtn");
    if (cb) cb.addEventListener("click", runColdChase);

    // 生肖榜单：正码 / 特码 切换
    const zr = document.getElementById("zodiacRefreshBtn");
    if (zr) zr.addEventListener("click", loadZodiacBoard);
    document.querySelectorAll(".zbtn").forEach(b => {
        b.addEventListener("click", () => {
            document.querySelectorAll(".zbtn").forEach(x => x.classList.remove("active"));
            b.classList.add("active");
            zodiacKind = b.dataset.zkind;
            renderZodiacBoard();
        });
    });
});

// ==================== 数据变化后的统一刷新 ====================
// 同步/导入新数据后调用。凡是"依赖库内数据"的视图都要跟着更新，
// 否则用户会看到旧榜单（历史上就漏了连续不出榜单，只能手动点刷新）。
let boardsStale = false;   // 数据变了但选号页不可见，留待下次进入时补刷

function refreshDataViews() {
    loadDashboard();
    loadDataStatus();
    // 榜单只在对应标签页可见时才刷，避免无谓请求
    const rec = document.querySelector('.tab-btn[data-tab="recommend"]');
    if (rec && rec.classList.contains("active")) {
        loadZodiacBoard();
        loadMissingBoard();
    } else {
        boardsStale = true;     // 下次进入选号页时补刷
    }
    // 跟踪页同理
    const trk = document.querySelector('.tab-btn[data-tab="tracker"]');
    if (trk && trk.classList.contains("active") && trackerInited) {
        loadTracker();
    }
}

// ==================== 统计口径标注 ====================
// 用户反馈：仪表盘上「统计窗口」选的是 500 期，但冷热号卡片写「近30期」，
// 两个期数不一致，不知道每张图到底统计了多少期。
//
// 根因有两层：
//   1) 冷热号真的没用统计窗口（后端硬编码 recent_n=30）——已修
//   2) 即使口径统一了，界面上也没有任何地方说明"这些图都是几期的"
//
// 这里给每个卡片打上口径徽标，并在顶部放一条横幅，统一说明。
function renderScopeBanner(winText) {
    const d = dashboardData;
    const el = document.getElementById("scopeBanner");
    if (!el) return;

    const skipped = (d.total_periods || 0) - (d.stats_periods || 0);
    el.innerHTML = `
        <span class="scope-icon">📐</span>
        <span class="scope-text">
            以下<b>所有图表</b>均基于同一口径：
            <b>${winText}</b>${d.window ? `（实际 ${Math.min(d.window, d.stats_periods)} 期）` : ""}
            ${skipped > 0 ? `　·　统计基数 ${d.stats_periods} 期（已排除 ${skipped} 期早期缺失数据）` : ""}
            <span class="scope-tip">切换上方「统计窗口」可整体改变口径</span>
        </span>
    `;

    // 各卡片的徽标同步
    document.querySelectorAll("#panel-dashboard .card-scope[data-scope='window']")
        .forEach(b => { b.textContent = winText; });
}

// ==================== 仪表盘 ====================
async function loadDashboard() {
    try {
        const win = document.getElementById("windowSelect").value;
        const res = await fetch(`/api/dashboard?window=${win}`);
        dashboardData = await res.json();

        const winText = dashboardData.window ? `近${dashboardData.window}期` : "全部数据";
        // 统计口径提示：1993~2002 的数据源缺失 48/49 号，
        // 参与统计的期数会少于总期数，必须让用户知道为什么。
        const skipped = (dashboardData.total_periods || 0) - (dashboardData.stats_periods || 0);
        const scopeNote = skipped > 0
            ? `<span class="data-scope-note" title="早期数据源缺失 48/49 号，已从统计中排除">`
              + `统计基数 ${dashboardData.stats_periods} 期`
              + `（已排除 ${skipped} 期数据不完整的记录）</span>`
            : "";
        document.getElementById("dataInfo").innerHTML =
            `已加载 ${dashboardData.total_periods} 期数据，当前统计：${winText}`
            + (scopeNote ? `　${scopeNote}` : "");
        document.getElementById("dashboardLoading").style.display = "none";
        document.getElementById("dashboardContent").style.display = "block";

        renderScopeBanner(winText);
        renderStatCards();
        // 单号维度：整体频率与冷热
        renderFrequencyChart();
        renderHeatmap();
        renderHotColdChart();
        renderMissingChart();
        // 特码专项（猜特码玩法）
        renderSpecialFreqChart();
        renderSpecialMissingChart();
        renderSpecialColorChart();
        renderSpecialZodiacChart();
        // 正码单号（猜正码玩法）
        renderMainNumbersChart();
        renderMainZodiacChart();
        // 号码属性速查表
        renderAttributesTable();
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

    // 顶部只放概览。期望值（每号平均次数）属于各图表的基准线，
    // 已并入"特码号码频次"/"正码出现次数"两张图的 tooltip 与副标题，
    // 不在这里重复展示。
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
            formatter: p => {
                const n = p[0].axisValue;
                const c = s.frequency[n];
                const ratio = (c / s.expected_per_number).toFixed(2);
                return `${n} 号<br/>开奖 ${c} 次`
                    + `<br/>每号平均 ${s.expected_per_number} 次（${ratio} 倍）`;
            }
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
                label: { color: "#f59e0b", formatter: "每号平均 {c}", fontSize: 10 },
                data: [{ yAxis: s.expected_per_number }]
            }
        }],
        grid: { left: 40, right: 16, top: 16, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderSpecialMissingChart() {
    // 特码遗漏排行：最久没开出的特码
    const chart = echarts.init(document.getElementById("chartSpecialMissing"));
    const s = (dashboardData.special_stats || {});
    if (!s.most_missing) return;

    // 倒序显示，让"遗漏最久"的排在最上面
    const rows = s.most_missing.slice().reverse();
    const names = rows.map(r => r.number + " 号");
    const values = rows.map(r => r.missing);
    const colors = rows.map(r => WAVE_COLORS[r.color] || "#334155");

    chart.setOption({
        tooltip: {
            trigger: "axis",
            axisPointer: { type: "shadow" },
            formatter: p => {
                const r = rows[p[0].dataIndex];
                return `${r.number} 号（${r.color} / ${r.zodiac}）<br/>`
                    + `已 ${r.missing} 期未开出<br/>`
                    + `历史共开出 ${r.count} 次`;
            }
        },
        xAxis: {
            type: "value",
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        yAxis: {
            type: "category",
            data: names,
            axisLabel: { color: "#94a3b8", fontSize: 11 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        series: [{
            type: "bar",
            data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
            barWidth: "55%",
            label: { show: true, position: "right", color: "#94a3b8", fontSize: 10 }
        }],
        grid: { left: 56, right: 40, top: 12, bottom: 28 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderMainNumbersChart() {
    // 正码单号出现次数（猜正码玩法）
    const chart = echarts.init(document.getElementById("chartMainNumbers"));
    const m = (dashboardData.main_numbers || {});
    if (!m.numbers) return;

    const nums = m.numbers.map(r => r.number);
    const values = m.numbers.map(r => r.count);
    const colors = m.numbers.map(r => {
        const attr = (dashboardData.attributes?.numbers || []).find(a => a.number === r.number);
        return attr ? (WAVE_COLORS[attr.color] || "#334155") : "#334155";
    });

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => {
                const r = m.numbers[p[0].dataIndex];
                return `${r.number} 号<br/>`
                    + `出现 ${r.count} 次（占 ${r.pct}%）<br/>`
                    + `每号平均 ${r.expected} 次（${r.ratio} 倍）<br/>`
                    + `当前遗漏 ${r.missing} 期`;
            }
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
                label: { color: "#f59e0b", formatter: "每号平均 {c}", fontSize: 10 },
                data: [{ yAxis: m.expected_per_number }]
            }
        }],
        grid: { left: 46, right: 16, top: 16, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderAttributesTable() {
    // 号码属性速查表：生肖 / 波色 / 五行
    const a = dashboardData.attributes;
    if (!a || !a.numbers) return;

    const note = document.getElementById("attributesNote");
    if (note) {
        note.innerHTML = `每个号码的生肖 / 波色 / 五行；按生肖或波色下注时用这张表对照。`
            + `<br>当前生肖表：<b>${a.zodiac_lunar_year} 年（${a.zodiac_animal}年）</b>，`
            + `自 ${a.zodiac_effective_from} 起生效 —— 生肖每年轮换，跨年号码归属会变。`;
    }

    const table = document.getElementById("attrTable");
    // 表头：号码 / 生肖 / 波色 / 五行，按 1-49 分行
    let html = "<thead><tr><th>号码</th><th>生肖</th><th>波色</th><th>五行</th>"
        + "<th>奇偶</th><th>大小</th></tr></thead><tbody>";
    a.numbers.forEach(r => {
        const wave = WAVE_COLORS[r.color] || "#94a3b8";
        html += `<tr>
            <td class="attr-num">${r.number}</td>
            <td>${r.zodiac}</td>
            <td style="color:${wave}; font-weight:600;">${r.color}</td>
            <td>${r.wuxing}</td>
            <td>${r.odd_even}</td>
            <td>${r.big_small}</td>
        </tr>`;
    });
    html += "</tbody>";
    table.innerHTML = html;
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
                label: { color: "#f59e0b", formatter: "每号平均 {c}", fontSize: 10 },
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
                return `${a}<br/>正码出现 ${p[0].value} 次（${m.pct[a]}%）<br/>每号平均 ${m.expected} 次`;
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
                label: { color: "#f59e0b", formatter: "每号平均 {c}", fontSize: 10 },
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

// ==================== 生肖连续不出榜单 ====================
let zodiacData = null;
let zodiacKind = "special";

async function loadZodiacBoard() {
    const btn = document.getElementById("zodiacRefreshBtn");
    if (btn) { btn.disabled = true; btn.textContent = "刷新中..."; }
    try {
        const res = await fetch("/api/zodiac_board?top=10");
        zodiacData = await res.json();
        renderZodiacBoard();
    } catch (e) {
        document.getElementById("zodiacMeta").textContent = `加载失败：${e.message}`;
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "🔄 刷新"; }
    }
}

function renderZodiacBoard() {
    if (!zodiacData) return;
    const isSpecial = zodiacKind === "special";
    const rows = isSpecial ? zodiacData.special_top : zodiacData.main_top;

    document.getElementById("zodiacMeta").innerHTML =
        `截至 <b>${zodiacData.latest_period}</b>（${zodiacData.latest_date}），`
        + `统计 ${zodiacData.total_periods} 期`;

    let html = `<thead><tr>
        <th>名次</th><th>生肖</th><th>含号码数</th><th>已连续未出</th>
        <th>理论单期概率</th><th>同档位历史命中率</th><th>样本</th></tr></thead><tbody>`;

    rows.forEach((r, i) => {
        let rateCell = "样本不足";
        if (r.same_state_rate !== null) {
            const diff = r.same_state_rate - r.expected_pct;
            const tone = Math.abs(diff) < 2 ? "#94a3b8"
                : (diff > 0 ? "#ef4444" : "#3b82f6");
            rateCell = `<span style="color:${tone}">${r.same_state_rate}%</span>`
                + `<span style="font-size:11px;color:#64748b"> (${diff >= 0 ? "+" : ""}${diff.toFixed(1)}pp)</span>`;
        }
        const medal = ["🥇", "🥈", "🥉"][i] || (i + 1);
        html += `<tr>
            <td>${medal}</td>
            <td class="board-num">${r.zodiac}</td>
            <td style="color:#64748b">${r.numbers}</td>
            <td><b>${r.missing}</b> 期</td>
            <td style="color:#64748b">${r.expected_pct}%</td>
            <td>${rateCell}</td>
            <td style="color:#64748b">${r.same_state_samples}</td>
        </tr>`;
    });
    html += "</tbody>";
    document.getElementById("zodiacTable").innerHTML = html;

    // 口径说明：两种玩法的量级完全不同，明确提示避免误读
    const top = rows[0];
    document.getElementById("zodiacHint").innerHTML = isSpecial
        ? `特码每期只开 1 个，12 个生肖里 11 个不出，所以「连续 ${top.missing} 期未出」并不稀奇——
           理论单期出现概率约 8~10%，意味着<b>平均 10 期左右才轮到一次</b>。`
        : `正码每期开 6 个，覆盖多个生肖，所以「连续不出」通常只有 <b>几期</b>——
           理论单期出现概率约 49~61%，意味着<b>平均两期就会出现一次</b>。`;
}

// ==================== 连续不出实时榜单 ====================
async function loadMissingBoard() {
    const btn = document.getElementById("boardRefreshBtn");
    if (btn) { btn.disabled = true; btn.textContent = "刷新中..."; }
    try {
        const res = await fetch("/api/missing_board?top=10");
        const d = await res.json();
        renderMissingBoard(d);
    } catch (e) {
        document.getElementById("boardMeta").textContent = `加载失败：${e.message}`;
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = "🔄 刷新"; }
    }
}

function renderMissingBoard(d) {
    document.getElementById("boardMeta").innerHTML =
        `截至 <b>${d.latest_period}</b>（${d.latest_date}），`
        + `统计 ${d.total_periods} 期　理论命中率 ${d.expected_rate}%`;

    let html = `<thead><tr>
        <th>名次</th><th>号码</th><th>已连续未出</th><th>生肖</th><th>波色</th>
        <th>同档位历史命中率</th><th>样本</th></tr></thead><tbody>`;

    d.board.forEach((r, i) => {
        const color = WAVE_COLORS[r.color] || "#94a3b8";
        // 命中率与理论值对比：高于则偏红（提示"看起来更该出"），低于偏蓝
        let rateCell = "样本不足";
        if (r.same_state_rate !== null) {
            const diff = r.same_state_rate - d.expected_rate;
            const tone = Math.abs(diff) < 2 ? "#94a3b8"
                : (diff > 0 ? "#ef4444" : "#3b82f6");
            rateCell = `<span style="color:${tone}">${r.same_state_rate}%</span>`
                + `<span style="font-size:11px;color:#64748b"> (${diff >= 0 ? "+" : ""}${diff.toFixed(1)}pp)</span>`;
        }
        const medal = ["🥇", "🥈", "🥉"][i] || (i + 1);
        html += `<tr>
            <td>${medal}</td>
            <td class="board-num" style="color:${color}">${r.number}</td>
            <td><b>${r.missing}</b> 期</td>
            <td>${r.zodiac}</td>
            <td style="color:${color}">${r.color}</td>
            <td>${rateCell}</td>
            <td style="color:#64748b">${r.same_state_samples}</td>
        </tr>`;
    });
    html += "</tbody>";
    document.getElementById("boardTable").innerHTML = html;
}

async function runColdChase() {
    const k = document.getElementById("chaseK").value;
    const mp = document.getElementById("chasePeriods").value;
    const btn = document.getElementById("chaseRunBtn");
    const box = document.getElementById("chaseResult");
    btn.disabled = true;
    btn.textContent = "验证中...";
    box.innerHTML = '<div class="loading"><div class="spinner"></div> 回测中，期数多时较慢...</div>';
    try {
        const res = await fetch(`/api/cold_chase?top=${k}&max_periods=${mp}`);
        const d = await res.json();
        const diff = d.hit_rate - d.expected_rate;
        const verdict = Math.abs(diff) < 1.0
            ? { text: "与理论值无实质差异 —— 追冷号没有优势", color: "#94a3b8" }
            : (diff > 0
                ? { text: "略高于理论值，但需分段检验才知是否稳定", color: "#f59e0b" }
                : { text: "低于理论值", color: "#3b82f6" });

        box.innerHTML = `
            <div class="chase-grid">
                <div class="chase-cell">
                    <div class="chase-val">${d.periods}</div>
                    <div class="chase-lab">回测期数</div>
                </div>
                <div class="chase-cell">
                    <div class="chase-val">${d.total_bets}</div>
                    <div class="chase-lab">总投注数（每期 ${d.top_k} 个号）</div>
                </div>
                <div class="chase-cell">
                    <div class="chase-val">${d.total_hits}</div>
                    <div class="chase-lab">命中次数</div>
                </div>
                <div class="chase-cell">
                    <div class="chase-val" style="color:${verdict.color}">${d.hit_rate}%</div>
                    <div class="chase-lab">实际命中率</div>
                </div>
                <div class="chase-cell">
                    <div class="chase-val">${d.expected_rate}%</div>
                    <div class="chase-lab">理论命中率</div>
                </div>
                <div class="chase-cell">
                    <div class="chase-val" style="color:${verdict.color}">${diff >= 0 ? "+" : ""}${diff.toFixed(2)}pp</div>
                    <div class="chase-lab">差异</div>
                </div>
            </div>
            <div class="chase-verdict" style="border-left-color:${verdict.color}">
                ${verdict.text}
            </div>
        `;
    } catch (e) {
        box.innerHTML = `<span style="color:#ef4444">验证失败：${e.message}</span>`;
    } finally {
        btn.disabled = false;
        btn.textContent = "开始验证";
    }
}

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
    zodiac_hot: "#f59e0b",
    zodiac_cold: "#14b8a6",
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

    // 特码命中率：六种策略各押 1 个特码，所以命中次数是"策略数 × 期数"里
    // 命中的总数。直接看总次数会被策略数放大，换算成"每个策略"才直观。
    const nStrat = entries.length;
    const periods = meta.periods_backtested || 1;
    const avgSpecialRate = totalSpecial / (nStrat * periods) * 100;

    // 正码命中：把"最优策略 vs 随机"的差距也换算成百分比，避免误读
    const bestDiff = best[1].avg_main_hits - d.baseline.avg_main_hits;

    document.getElementById("btStatCards").innerHTML = `
        <div class="stat-card">
            <div class="value">${periods}</div>
            <div class="label">回测期数</div>
        </div>
        <div class="stat-card">
            <div class="value">${d.baseline.avg_main_hits}</div>
            <div class="label">随机基准（平均每期命中正码数）</div>
        </div>
        <div class="stat-card">
            <div class="value" style="color:${STRATEGY_COLORS[best[0]]};">${best[1].avg_main_hits}</div>
            <div class="label">最优：${meta.strategy_names[best[0]]}
                <span style="color:${bestDiff >= 0 ? '#22c55e' : '#ef4444'}">
                    (${bestDiff >= 0 ? "+" : ""}${bestDiff.toFixed(3)})</span>
            </div>
        </div>
        <div class="stat-card">
            <div class="value">${avgSpecialRate.toFixed(2)}%</div>
            <div class="label">特码平均命中率（理论 ${d.baseline.special_hit_rate}%）</div>
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
            splitLine: { lineStyle: { color: "#1e293b" } },
            // 从 0 起：这几个策略的差异只有零点几个号码，
            // 若让 ECharts 自动缩放会把微小差异放大成"差好几倍"的错觉
            min: 0,
        },
        series: [{
            type: "bar",
            data: values.map((v, i) => ({
                value: v,
                itemStyle: { color: STRATEGY_COLORS[names[i]] }
            })),
            barWidth: "45%",
            label: {
                show: true, position: "top",
                color: "#94a3b8", fontSize: 10,
                formatter: p_ => p_.value.toFixed(3)
            },
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
        grid: { left: 50, right: 20, top: 34, bottom: 40 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderBtSpecialChart() {
    const chart = echarts.init(document.getElementById("chartBtSpecial"));
    const d = backtestData;

    const names = Object.keys(d.strategies);
    const labels = names.map(n => d.meta.strategy_names[n]);
    const values = names.map(n => d.strategies[n].special_hit_rate);
    const counts = names.map(n => d.strategies[n].special_hit_count);
    const baseline = d.baseline.special_hit_rate;

    // 每个策略押 1 个特码、共 periods 期，所以命中数 ~ 二项分布。
    // 标注 95% 正常波动范围，避免把"1 个百分点"读成"差好几倍"：
    //   命中次数少时，±2 个标准差能覆盖几个百分点的抖动，纯属噪声。
    const periods = d.meta.periods_backtested || 1;
    const p = baseline / 100;
    const sd = Math.sqrt(periods * p * (1 - p)) / periods * 100;   // 命中率的标准差(%)
    const lo = Math.max(0, baseline - 1.96 * sd);
    const hi = baseline + 1.96 * sd;

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p_ => {
                const i = p_[0].dataIndex;
                const diff = values[i] - baseline;
                return `${labels[i]}<br/>`
                    + `特码命中 ${counts[i]} 次 / ${periods} 期<br/>`
                    + `命中率 ${values[i]}%　(理论 ${baseline}%)<br/>`
                    + `偏差 ${diff >= 0 ? "+" : ""}${diff.toFixed(2)} 个百分点`;
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
            splitLine: { lineStyle: { color: "#1e293b" } },
            // 从 0 起，避免柱状图把微小差异放大
            min: 0,
        },
        series: [{
            type: "bar",
            data: values.map((v, i) => ({
                value: v,
                itemStyle: { color: STRATEGY_COLORS[names[i]] }
            })),
            barWidth: "45%",
            label: {
                show: true, position: "top",
                color: "#94a3b8", fontSize: 10,
                formatter: p_ => `${p_.value}%`
            },
            markLine: {
                silent: true,
                symbol: "none",
                data: [
                    {
                        yAxis: baseline,
                        lineStyle: { color: "#f59e0b", type: "dashed", width: 2 },
                        label: {
                            formatter: `理论 ${baseline}%`,
                            color: "#f59e0b",
                            position: "insideEndTop"
                        }
                    },
                    // 95% 正常波动上下界：落在这个区间内 = 与随机无区别
                    {
                        yAxis: lo,
                        lineStyle: { color: "#64748b", type: "dotted", width: 1 },
                        label: { formatter: `95%下界 ${lo.toFixed(1)}%`, color: "#64748b",
                                 fontSize: 9, position: "insideStartTop" }
                    },
                    {
                        yAxis: hi,
                        lineStyle: { color: "#64748b", type: "dotted", width: 1 },
                        label: { formatter: `95%上界 ${hi.toFixed(1)}%`, color: "#64748b",
                                 fontSize: 9, position: "insideStartBottom" }
                    },
                ]
            }
        }],
        grid: { left: 50, right: 20, top: 34, bottom: 40 },
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
    const periods = d.meta.periods_backtested || 1;

    const head = `
        <thead>
            <tr>
                <th>策略</th>
                <th>平均正码命中<br/><span class="th-sub">个/期</span></th>
                <th>对比随机<br/><span class="th-sub">个/期</span></th>
                <th>正码命中率<br/><span class="th-sub">至少中 1 个的期数占比</span></th>
                <th>特码命中<br/><span class="th-sub">次数 / 期数</span></th>
                <th>特码命中率<br/><span class="th-sub">理论 ${d.baseline.special_hit_rate}%</span></th>
                <th>单期最佳<br/><span class="th-sub">个正码</span></th>
            </tr>
        </thead>`;

    const baseline = d.baseline.avg_main_hits;
    // 特码命中数近似二项分布：给出 95% 正常波动范围，
    // 便于一眼判断某策略的偏差是否只是噪声（样本小时波动很大）
    const p = d.baseline.special_hit_rate / 100;
    const sd = Math.sqrt(periods * p * (1 - p)) / periods * 100;
    const lo = Math.max(0, d.baseline.special_hit_rate - 1.96 * sd);
    const hi = d.baseline.special_hit_rate + 1.96 * sd;

    const rows = names.map(n => {
        const s = d.strategies[n];
        const diff = s.avg_main_hits - baseline;
        const sign = diff >= 0 ? "+" : "";
        const color = diff >= 0 ? "#22c55e" : "#ef4444";

        // 落在 95% 区间内 = 与随机猜无实质差异，用灰色弱化
        const inRange = s.special_hit_rate >= lo && s.special_hit_rate <= hi;
        const sColor = inRange ? "#94a3b8" : (s.special_hit_rate > hi ? "#22c55e" : "#ef4444");
        const sTag = inRange ? ""
            : ` <span style="font-size:10px">${s.special_hit_rate > hi ? "偏高" : "偏低"}</span>`;

        return `<tr>
            <td style="font-weight:600; color:${STRATEGY_COLORS[n]};">${d.meta.strategy_names[n]}</td>
            <td>${s.avg_main_hits}</td>
            <td style="color:${color};">${sign}${diff.toFixed(3)}</td>
            <td>${s.main_hit_rate}%</td>
            <td>${s.special_hit_count} / ${periods}</td>
            <td style="color:${sColor};">${s.special_hit_rate}%${sTag}</td>
            <td>${s.best_main_hits}</td>
        </tr>`;
    }).join("");

    // 表尾写明判读口径，避免把噪声当规律
    const foot = `<tfoot><tr>
        <td colspan="7" style="text-align:left; color:#64748b; font-size:12px; padding-top:10px;">
            特码命中率的 95% 正常波动范围：
            <b style="color:#94a3b8">${lo.toFixed(2)}% ~ ${hi.toFixed(2)}%</b>
            （${periods} 期样本）。落在此区间内 = 与随机猜没有实质差别。
            单期押 1 个特码的理论命中率是 ${d.baseline.special_hit_rate}%。
        </td>
    </tr></tfoot>`;

    document.getElementById("btTable").innerHTML = head + `<tbody>${rows}</tbody>` + foot;
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

    // 分享版预置的 Key：提示使用者这不是自己的，建议替换
    const notice = document.getElementById("borrowedKeyNotice");
    if (notice) notice.style.display = s.borrowed_key ? "block" : "none";

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
        // characters / counts 是 V1.4.8 新增的两个线索维度：
        // characters = 图上刻的汉字（石碑「龍」→ 生肖龙），counts = 数量线索（「三盏灯笼」→ 3）
        if (vision.characters && vision.characters.length > 0) {
            detailHtml += `<div class="trace-item">✍️ <strong>汉字：</strong>${vision.characters.map(c => `<span class="vision-tag character">${c}</span>`).join("")}</div>`;
        }
        if (vision.counts && vision.counts.length > 0) {
            detailHtml += `<div class="trace-item">🔢 <strong>数量：</strong>${vision.counts.map(c => `<span class="vision-tag count">${c}</span>`).join("")}</div>`;
        }

        detailContent.innerHTML = detailHtml || '<div class="trace-item">未识别到明显元素</div>';

        // 显示解码结果
        if (decode.recommended && decode.recommended.main) {
            const rec = decode.recommended;

            resultDiv.innerHTML = `
                <div class="result-display">
                    <div class="label">🔮 AI 图解码推荐号码</div>
                    ${renderBallsRow(rec)}
                </div>
            `;

            // 推荐理由（每个号码为什么被选中）
            resultDiv.innerHTML += renderReasonList(
                decode, [...rec.main, rec.special].filter(n => n != null)
            );

            // 候选号码排行
            if (decode.all_candidates && decode.all_candidates.length > 0) {
                const top15 = decode.all_candidates.slice(0, 15);
                resultDiv.innerHTML += `
                    <div style="margin-top:16px;">
                        <div style="color:var(--text-secondary); font-size:13px; margin-bottom:8px;">📊 候选号码权重排行</div>
                        <div class="balls-row">
                            ${top15.map(c => `
                                <span class="ball ${getBallColor(c.number)}" title="${reasonTooltip(decode, c.number, c.score)}"
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

    resultDiv.innerHTML = `
        <div class="result-display">
            <div class="label">🔮 解码推荐号码</div>
            ${renderBallsRow(rec)}
        </div>
    `;

    // 推荐理由（每个号码为什么被选中）
    resultDiv.innerHTML += renderReasonList(
        data, [...rec.main, rec.special].filter(n => n != null)
    );

    // 候选号码排行
    if (data.all_candidates && data.all_candidates.length > 0) {
        const top15 = data.all_candidates.slice(0, 15);
        resultDiv.innerHTML += `
            <div style="margin-top:16px;">
                <div style="color:var(--text-secondary); font-size:13px; margin-bottom:8px;">📊 候选号码权重排行</div>
                <div class="balls-row">
                    ${top15.map(c => `
                        <span class="ball ${getBallColor(c.number)}" title="${reasonTooltip(data, c.number, c.score)}"
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
        // 顺带刷新顶部过期提示（status 接口已带 fresh 字段，无需额外请求）
        renderStaleBar(d.fresh);
    } catch (e) {
        el.textContent = `读取状态失败：${e.message}`;
        el.style.color = "#ef4444";
    }
}

// ==================== 数据过期提示条 ====================
// 同步是手动的（有意不自动联网），但用户容易忘记点、看到旧数据却无察觉。
// 这里做纯本地的「应开日 vs 库内最新」比对，落后了就提示一次。
let staleDismissed = false;

function renderStaleBar(fresh) {
    const bar = document.getElementById("staleBar");
    if (!bar) return;
    if (!fresh || !fresh.known || !fresh.stale || staleDismissed) {
        bar.style.display = "none";
        return;
    }
    const dates = (fresh.missed_labels || []).join("、");
    document.getElementById("staleText").innerHTML =
        `数据可能已过时：库内最新为 <b>${fresh.latest_date}</b>，`
        + `其后应有 <b>${fresh.missed_count}</b> 期开奖尚未收录`
        + (dates ? `（${dates}）` : "")
        + `　<button class="stale-link" id="staleLink">前往同步</button>`;
    bar.style.display = "flex";

    const link = document.getElementById("staleLink");
    if (link) link.addEventListener("click", () => {
        document.querySelector('.tab-btn[data-tab="settings"]').click();
    });
}

function initStaleBar() {
    const syncBtn = document.getElementById("staleSyncBtn");
    const closeBtn = document.getElementById("staleCloseBtn");
    if (syncBtn) syncBtn.addEventListener("click", async () => {
        syncBtn.disabled = true;
        syncBtn.textContent = "同步中...";
        try {
            const res = await fetch("/api/data/sync", { method: "POST" });
            const d = await res.json();
            if (d.inserted > 0) {
                staleDismissed = true;
                document.getElementById("staleBar").style.display = "none";
                refreshDataViews();
                alert(`同步完成，新增 ${d.inserted} 期：${(d.new_periods || []).join("、")}`);
            } else {
                // 源里确实还没有新数据 —— 提示但不重复骚扰
                document.getElementById("staleText").innerHTML =
                    `已检查数据源：暂无新期号（库内最新仍为 <b>${d.total_periods}</b> 期对应的最新一期）。`
                    + `可能是该期未开奖或源尚未收录，稍后再试。`;
                syncBtn.style.display = "none";
            }
        } catch (e) {
            document.getElementById("staleText").textContent = `同步失败：${e.message}`;
        } finally {
            syncBtn.disabled = false;
            if (syncBtn.style.display !== "none") syncBtn.textContent = "🔄 立即同步";
        }
    });
    if (closeBtn) closeBtn.addEventListener("click", () => {
        staleDismissed = true;      // 本次会话不再提示
        document.getElementById("staleBar").style.display = "none";
    });
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
        refreshDataViews();   // 数据变了，所有依赖库内数据的视图一起刷新
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
            (d.inserted > 0
                ? `同步完成：新增 ${d.inserted} 期（${(d.new_periods || []).join("、")}），库内共 ${d.total_periods} 期`
                : `已是最新：没有新增期号（数据源暂无新开奖，库内共 ${d.total_periods} 期）`)
            + ((d.source_errors || []).length
                ? `　⚠️ 部分数据源不可用：${d.source_errors.map(e => e.source).join("、")}`
                : ""));
        if (d.inserted > 0) refreshDataViews();
    } catch (e) {
        showDataStatus("err", `同步失败：${e.message}`);
    } finally {
        btn.disabled = false;
    }
}

// ==================== 单号跟踪 ====================
// 回答「它多久没出了，还该不该等」。
// 关键是把两件事分开：
//   下一期的概率  —— 恒为 14.29%，与遗漏多久无关
//   未来K期的概率 —— 随 K 增大，这才是"迟早会出"的来源
let trackerData = null;
let trackerInited = false;

function initTracker() {
    if (trackerInited) return;
    trackerInited = true;

    // 号码下拉：1-49，用球色标记
    const sel = document.getElementById("trackerNumber");
    sel.innerHTML = Array.from({ length: 49 }, (_, i) => i + 1)
        .map(n => `<option value="${n}">${n} 号</option>`).join("");
    sel.value = "48";

    document.getElementById("trackerRunBtn").addEventListener("click", loadTracker);
    sel.addEventListener("change", loadTracker);
    document.getElementById("trackerWindow").addEventListener("change", loadTracker);
    loadTracker();
}

async function loadTracker() {
    const num = document.getElementById("trackerNumber").value;
    const win = document.getElementById("trackerWindow").value;
    const btn = document.getElementById("trackerRunBtn");
    btn.disabled = true;
    btn.textContent = "计算中...";
    try {
        const res = await fetch(`/api/tracker?number=${num}&limit=${win}`);
        trackerData = await res.json();
        document.getElementById("trackerContent").style.display = "block";
        renderTrackerCards();
        renderRenewChart();
        renderYearlyChart();
        renderHorizonChart();
        renderRunsChart();
        renderTrackerHelp();
    } catch (e) {
        document.getElementById("trackerContent").style.display = "none";
        alert(`跟踪失败：${e.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = "开始跟踪";
    }
}

function renderTrackerCards() {
    const t = trackerData;
    const n = t.number;
    const color = WAVE_COLORS[t.color] || "#94a3b8";

    // 当前遗漏在历史遗漏段里的位置：越高说明"这次等得越久"
    const pctText = t.missing_percentile >= 90 ? "偏久"
        : t.missing_percentile >= 70 ? "略久" : "常见范围";

    document.getElementById("trackerCards").innerHTML = `
        <div class="stat-card">
            <div class="value" style="color:${color}">${n}</div>
            <div class="label">${t.zodiac} · ${t.color}</div>
        </div>
        <div class="stat-card">
            <div class="value">${t.current_missing}</div>
            <div class="label">当前已连续未出（期）</div>
        </div>
        <div class="stat-card">
            <div class="value">${t.missing_percentile}%</div>
            <div class="label">比历史 ${t.runs_count} 次遗漏中多久（${pctText}）</div>
        </div>
        <div class="stat-card">
            <div class="value">${t.total_hits}</div>
            <div class="label">窗口内出现次数（期望 ${t.expected_hits}）</div>
        </div>
        <div class="stat-card">
            <div class="value">14.29%</div>
            <div class="label">下一期出现概率（与遗漏无关）</div>
        </div>
    `;
}

function renderRenewChart() {
    const chart = echarts.init(document.getElementById("chartRenew"));
    // 用合并后的桶：单档样本太少会让线剧烈抖动，反而看不出"平线"这个结论
    const c = trackerData.renew_merged || trackerData.renew_curve || [];
    if (!c.length) return;

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => {
                const r = c[p[0].dataIndex];
                const range = r.label ? `已连续未出 ${r.label} 期` : `已连续未出 ${r.missing} 期`;
                return `${range}<br/>`
                    + `下一期仍不出：实际 ${(r.observed * 100).toFixed(2)}%<br/>`
                    + `理论值 ${(r.theory * 100).toFixed(2)}%（样本 ${r.samples}）`;
            }
        },
        legend: { data: ["实际", "理论"], textStyle: { color: "#94a3b8" }, top: 0 },
        xAxis: {
            type: "category",
            name: "已连续未出期数",
            nameTextStyle: { color: "#94a3b8", fontSize: 10 },
            data: c.map(r => r.missing),
            axisLabel: { color: "#94a3b8", fontSize: 10 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            min: 60, max: 100,
            axisLabel: { color: "#94a3b8", formatter: "{value}%" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [
            {
                name: "实际", type: "line", smooth: true, symbolSize: 6,
                data: c.map(r => +(r.observed * 100).toFixed(2)),
                itemStyle: { color: "#0ea5e9" }, lineStyle: { width: 2 }
            },
            {
                name: "理论", type: "line", symbol: "none",
                data: c.map(() => 85.71),
                itemStyle: { color: "#f59e0b" },
                lineStyle: { type: "dashed", width: 1 }
            }
        ],
        grid: { left: 52, right: 16, top: 30, bottom: 42 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderYearlyChart() {
    const chart = echarts.init(document.getElementById("chartYearly"));
    // 用全历史年度数据：只看统计窗口的话期数太少（500 期仅约 3 年）
    const y = trackerData.yearly_all || trackerData.yearly || [];
    if (!y.length) return;

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => {
                const r = y[p[0].dataIndex];
                return `${r.year} 年（${r.periods} 期）<br/>`
                    + `出现 ${r.count} 次<br/>`
                    + `正常区间 ${r.lo} ~ ${r.hi}${r.normal ? "" : "（区间外）"}`;
            }
        },
        xAxis: {
            type: "category",
            data: y.map(r => r.year),
            axisLabel: { color: "#94a3b8", fontSize: 10, rotate: 45 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value",
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [
            {
                name: "出现次数", type: "bar", barWidth: "55%",
                data: y.map(r => ({
                    value: r.count,
                    itemStyle: { color: r.normal ? "#0ea5e9" : "#ef4444" }
                }))
            },
            {
                // 95% 正常波动区间：用两条线夹出灰带
                name: "上界", type: "line", symbol: "none", stack: "band",
                data: y.map(r => r.hi - r.lo),
                lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 },
                areaStyle: { color: "rgba(148,163,184,0.18)" }, silent: true,
                tooltip: { show: false }
            },
            {
                name: "下界", type: "line", symbol: "none",
                data: y.map(r => r.lo),
                lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 },
                silent: true, tooltip: { show: false }
            }
        ],
        grid: { left: 44, right: 16, top: 16, bottom: 52 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderHorizonChart() {
    const chart = echarts.init(document.getElementById("chartHorizon"));
    const h = trackerData.horizon || [];
    if (!h.length) return;

    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => `未来 ${h[p[0].dataIndex].periods} 期内`
                + `<br/>至少出现一次：${h[p[0].dataIndex].prob}%`
        },
        xAxis: {
            type: "category",
            data: h.map(r => r.periods + " 期"),
            axisLabel: { color: "#94a3b8", fontSize: 10 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value", max: 100,
            axisLabel: { color: "#94a3b8", formatter: "{value}%" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar", barWidth: "50%",
            data: h.map(r => r.prob),
            itemStyle: { color: "#22c55e" },
            label: { show: true, position: "top", color: "#94a3b8", fontSize: 10,
                     formatter: p => p.value + "%" }
        }],
        grid: { left: 52, right: 16, top: 24, bottom: 30 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderRunsChart() {
    const chart = echarts.init(document.getElementById("chartRuns"));
    // 用全量单档数据：这张图看的就是"长度分布"，合并会失真
    const c = trackerData.renew_curve || [];
    if (!c.length) return;

    // 用样本量近似展示"遗漏段的长度分布"：每档的样本数即到达该长度的次数
    chart.setOption({
        tooltip: {
            trigger: "axis",
            formatter: p => `连续未出 ${c[p[0].dataIndex].missing} 期`
                + `<br/>出现 ${p[0].value} 次`
        },
        xAxis: {
            type: "category",
            name: "连续未出长度（期）",
            nameTextStyle: { color: "#94a3b8", fontSize: 10 },
            data: c.map(r => r.missing),
            axisLabel: { color: "#94a3b8", fontSize: 10 },
            axisLine: { lineStyle: { color: "#334155" } }
        },
        yAxis: {
            type: "value", name: "次数",
            nameTextStyle: { color: "#94a3b8", fontSize: 10 },
            axisLabel: { color: "#94a3b8" },
            splitLine: { lineStyle: { color: "#1e293b" } }
        },
        series: [{
            type: "bar", barWidth: "60%",
            data: c.map(r => r.samples),
            itemStyle: { color: "#a855f7" }
        }],
        grid: { left: 52, right: 16, top: 28, bottom: 42 },
    });
    window.addEventListener("resize", () => chart.resize());
}

function renderTrackerHelp() {
    const t = trackerData;
    document.getElementById("trackerHelp").innerHTML = `
        <p><b>1. 下一期会不会出？</b>永远是 <b>14.29%</b>（7/49）。
           不管它已经连续 ${t.current_missing} 期没出，还是刚刚出过，都是这个数。
           看「续期概率」那张图——线是<b>平的</b>，就说明"欠久了会补"不成立。</p>
        <p><b>2. 那"迟早会出"是假的吗？</b>不假，但它是<b>另一个问题</b>。
           看「未来 K 期」那张图：10 期 78.6%、30 期 99.0%、50 期 99.96%。
           期数越多越接近必然——靠的是<b>期数多</b>，不是对过去的补偿。</p>
        <p><b>3. 年度次数波动正常吗？</b>正常。一年约 150 期，每号期望 21.4 次，
           正常范围约 13~30 次。落到区间外也不必紧张——49 个号 × 20 多年，
           按 5% 算本来就会有不少落在区间外。</p>
        <p><b>4. 当前遗漏 ${t.current_missing} 期，算久吗？</b>
           它比历史上 ${t.missing_percentile}% 的遗漏段更久
           （历史最长 ${t.longest_missing} 期，平均 ${t.avg_missing} 期）。
           ${t.missing_percentile >= 90
              ? "确实偏久，但下一期概率不变——只是说明这类长遗漏本身会发生。"
              : "属常见范围。"}</p>
        <p class="tracker-caveat">⚠️ 这些图的价值是<b>让你看清规律</b>，不是预测。
           每期独立、号码无记忆，任何"追冷号/追热号"的策略在数据上都不成立。</p>
    `;
}
