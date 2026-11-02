# 📒 DEVLOG — 设计日志与迭代记录

> 本文档记录项目的设计思路、架构决策、每次迭代的修改内容和技术要点。  
> 供后续接手的开发者或协作 Agent 快速理解项目全貌。

---

## 一、项目起源与定位

### 需求背景
用户（Sonny）希望做一个六合彩数据分析工具，包含：
- 历史开奖数据的统计分析（频率、冷热号、遗漏值等）
- 类似"曾大仙图猜码"的图片解码功能——用户上传一张"玄机图"，系统自动识别其中的动物、颜色、物件等元素，映射到号码

### 核心设计原则
1. **诚实定位**：彩票开奖是独立随机事件，本工具定位为"统计分析 + 趣味解码"，非真正预测
2. **零成本**：全部使用免费工具和 API（Python + SQLite + Kaggle 免费 AI 额度）
3. **快速交付**：MVP 优先，先跑通再打磨
4. **模块化**：后端按职责拆分（database / analyzer / decoder / vision），方便多 Agent 协作

### 六合彩基本规则
- 号码范围：**1-49**
- 每期开出：**6 个正码** + **1 个特码**
- 色波分类：红波 / 蓝波 / 绿波（固定映射）
- 文化符号体系：十二生肖、五行、方位等与号码有约定俗成的对应关系

---

## 二、架构设计

### 整体架构

```
┌───────────────────────────────────────────────────┐
│                    浏览器前端                       │
│   HTML + CSS(暗色主题) + JS + ECharts(本地)        │
│                                                    │
│   Tab1: 仪表盘  Tab2: 记录  Tab3: 选号  Tab4: 图猜码│
└────────────────────┬──────────────────────────────┘
                     │ HTTP / JSON
┌────────────────────▼──────────────────────────────┐
│              Flask API 网关 (app.py)               │
│         路由分发 + 请求参数处理 + JSON 响应          │
├────────────┬──────────┬───────────┬────────────────┤
│ database.py│analyzer.py│decoder.py │  vision.py     │
│ SQLite CRUD│ 统计分析  │ 符号映射  │ AI 视觉识别    │
│ 数据生成   │ 10项指标  │ 交叉推导  │ Kaggle Gemini  │
└────────────┴──────────┴───────────┴────────────────┘
```

### 模块职责

| 模块 | 文件 | 职责 | 对外接口 |
|---|---|---|---|
| 数据层 | `database.py` | SQLite 建表、CRUD、模拟数据生成 | `get_all_results()`, `insert_result()` |
| 分析引擎 | `analyzer.py` | 频率、冷热号、遗漏值、奇偶比等统计 | `get_dashboard_data()`, `smart_recommend()` |
| 解码引擎 | `decoder.py` | 生肖/五行/色波/方位映射 + 多维交叉推导 | `decode_elements()`, `quick_decode()` |
| 回测引擎 | `backtest.py` | 策略历史命中率回测（无未来数据泄露） | `run_backtest()` |
| 视觉识别 | `vision.py` | 图片→AI分析→元素提取→映射转换 | `analyze_image()`, `map_vision_to_decoder_selections()` |
| 路由网关 | `app.py` | Flask 路由 + 模块调度 | 所有 `/api/*` 路由 |

### 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 前端框架 | 无框架（原生 HTML/CSS/JS） | MVP 不需要，减少复杂度 |
| 图表库 | ECharts | 生态好，中文支持强，文档全 |
| ECharts 加载方式 | 本地文件 | CDN 在线加载容易因网络卡死页面（V2 修复） |
| 数据库 | SQLite | 零配置，Python 内置，单文件 |
| AI 视觉模型 | Kaggle Gemini 3.7 Flash | 免费每日 $10 额度，支持多模态 |
| API 风格 | REST + JSON | 简单直观，前后端分离 |
| 色球渲染 | CSS 渐变 + 阴影 | 不用图片资源，纯 CSS 实现 3D 球效果 |

---

## 三、迭代记录

### V1.0 — MVP 初版 (2026-11-02 12:30)

**目标**：跑通核心功能闭环

**完成内容**：
- [x] 项目骨架搭建（Flask + 目录结构）
- [x] SQLite 数据库 + 300 期模拟开奖数据生成
- [x] 统计分析引擎（10 项分析指标）
  - 号码频率分析
  - 冷热号（近 N 期高频/低频）
  - 遗漏值（每个号码连续未出现期数）
  - 奇偶比分布
  - 大小比分布（1-24小 / 25-49大）
  - 和值分析（6 正码之和的区间分布）
  - 尾数分布（个位数 0-9）
  - 连号分析（是否出现相邻号码）
- [x] 智能选号推荐（4 种策略：均衡 / 热号 / 冷号 / 随机）
- [x] 图猜码解码引擎 V1（手动文字输入模式）
  - 生肖→号码映射表
  - 五行→号码映射表
  - 色波→号码映射表
  - 方位→号码区间映射
  - 关键词→生肖/五行自动匹配
  - 多维交叉权重推导
- [x] 前端暗色主题 UI
- [x] ECharts 图表（柱状图、饼图、热力图）
- [x] 色波彩球 CSS 渲染

**遇到的问题**：
1. **GBK 编码错误**：`print()` 中的 emoji 在 Windows cmd 下报 `UnicodeEncodeError`
   - 修复：启动时 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")`
2. **Playwright CSS 选择器转义**：PowerShell 传参时双引号嵌套被吞
   - 修复：改用独立 `.py` 脚本文件执行

---

### V1.1 — 性能修复 + AI 视觉 (2026-11-02 17:00)

**触发问题**：
1. 用户反馈页面"卡住"——排查发现 Dashboard API 响应仅 0.09s，瓶颈在前端 ECharts CDN 加载
2. 用户希望图猜码支持**直接上传图片**自动识别，而非手动输入文字

**修改 1：ECharts 本地化**
```
- <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js">
+ <script src="/static/js/echarts.min.js">
```
下载 ECharts 到 `static/js/echarts.min.js`，彻底消除外部 CDN 依赖。

**修改 2：新增 `vision.py` — AI 视觉识别模块**

核心流程：
```
用户拖拽上传图片
    ↓ Base64 编码
Flask 接收 → vision.analyze_image()
    ↓ OpenAI multimodal content 格式
Kaggle Gemini 3.7 Flash (免费视觉模型)
    ↓ 结构化 JSON 输出
vision.map_vision_to_decoder_selections()
    ↓ 动物→生肖 / 颜色→色波 / 元素→五行
decoder.decode_elements(selections)
    ↓ 多维交叉权重推导
返回推荐号码 + 解码过程 + AI 识别详情
```

关键技术点：
- **提示词设计**：系统提示词要求 AI 输出严格 JSON 格式，分 7 个维度（animals/colors/elements/directions/numbers/objects/description）
- **容错解析**：`_parse_json_response()` 支持提取 markdown code block 中的 JSON、文本中的 JSON 片段
- **双层映射**：vision.py 做 AI→标准化映射，decoder.py 做标准化→号码映射，职责清晰

**修改 3：前端图片上传 UI**
- 拖拽上传区（drag & drop + click to select）
- 上传后即时预览
- AI 分析过程中显示 loading 动画
- 识别结果用彩色标签展示（动物红/颜色黄/五行绿/方位紫/物件粉）
- AI 结果自动同步到手动选择面板的高亮状态
- 用户可在 AI 基础上手动补选/修正

**新增 API**：
- `POST /api/decoder/vision` — 图片上传解码
- `GET /api/vision/status` — AI 功能可用性检查

---

### V1.2 — 历史命中率回测 (2026-11-02 20:55)
- **负责智能体**：DeepSeek
- **工作分支**：feature/deepseek/hit-rate-backtest
- **修改目标**：
  1. 实现四种选号策略的**无未来数据泄露**历史回测，回答"热号/冷号/遗漏值是否真的比随机强"
  2. 修复 `smart_recommend()` 的回测可用性缺陷（原先只读全库，回测必然泄露未来数据）
  3. 顺带修复 `analyzer.py` 中 numpy 标量泄漏导致的 JSON 序列化隐患，并做性能优化
- **核心改动文件**：
  - `backtest.py`（新增，281 行）：回测引擎
    - `run_backtest(strategies, min_history, max_periods, recent_n, seed)` 主入口
    - 对第 i 期预测时传 `limit=i`，**只用前 i 期历史**，绝不触碰当期及未来
    - `_evaluate()` 命中判定：正码命中数 / 特码命中 / 任意命中数（7 个号码内）
    - `_random_baseline()` 超几何理论基准：正码 6×6/49≈0.735，特码 1/49≈2.04%
    - `_build_verdict()` 生成诚实结论，不吹嘘策略有效性
  - `analyzer.py`：
    - `smart_recommend()` 新增 `limit` / `recent_n` 参数（**回测必需**）
    - `missing_values()` 新增 `limit` 参数；改用 numpy 向量化（22s → 5s，快 4.4 倍）
    - `hot_cold_numbers()` 同频次按号码升序排序，保证回测可复现
    - `odd_even_analysis()` / `big_small_analysis()` 分布改为按 key 排序，消除字典顺序抖动
    - 修复 `_extract_all_numbers()` / `missing_values()` / `sum_analysis()` 的 `numpy.int64`/`float64` 泄漏
  - `app.py`：新增 `GET /api/backtest`（支持 strategies / min_history / max_periods / recent_n / seed 参数，非法策略返回 400）
  - `templates/index.html`：新增「📈 策略回测」Tab（参数控件 + 结论框 + 3 图表 + 明细表）
  - `static/js/main.js`：新增回测渲染逻辑（4 个渲染函数 + 柱状图随机基准 markLine）
  - `static/css/style.css`：新增 `.backtest-*` / `.verdict-*` 样式
- **自测验证结果**：
  - **可复现性**：同一 seed 跨进程两次运行结果完全一致 ✅
  - **无未来泄露**：`frequency_analysis(k)` / `missing_values(k)` 与"仅取最近 k 期手工统计"逐值一致；打桩验证 `limit=k` 的推荐 == 仅用最近 k 期数据的推荐 ✅
  - **命中核对**：手工复算某一期的正码/特码命中数，与引擎输出一致 ✅
  - **统计自洽**：命中个数分布求和 == 回测期数 ✅
  - **优化等价性**：向量化前后 `get_dashboard_data()` 输出 **逐字节相同** ✅
  - **边界**：`min_history` 超过总期数时返回明确 error ✅
  - **回归**：19 个既有 API 端点全部 HTTP 200，仪表盘数值正常 ✅
  - **前端**：Playwright 实测 — 1600/1024/390 三种宽度均无横向溢出，3 个图表正常渲染，参数重跑与 Tab 切换无控制台报错 ✅
  - **性能**：200 期全策略回测 22.7s → **5.3s**
- **关键发现（重要）**：
  - 单次回测（seed=42，270 期）会显示"热号优先 0.8 vs 基准 0.735"，看似有优势；
    但**跑 10 个不同 seed 后，四种策略均值全部收敛到基准**：
    `balanced 0.735 / hot 0.738 / cold 0.722 / random 0.725`（z 值均 < 0.5）
  - 结论：所谓"热号/冷号/遗漏值"在统计上**与随机无显著差异**，这符合六合彩独立随机的本质。
    前端结论框已如实说明，避免误导用户。**请勿在后续迭代中把这种噪声包装成"预测能力"。**
- **遗留注意事项 / 给下一位 Agent 的说明**：
  1. `smart_recommend(strategy, limit=...)` 的 `limit` 语义是**"取最近 N 期"**（因为 `get_all_results(limit)` 是 `ORDER BY period DESC LIMIT n`）。回测里传 `limit=i` 表示"第 i 期之前的 i 期"，务必不要改成升序取前 i 期，否则会泄露未来数据。
  2. 回测随机性通过 `random.seed()` + `getstate/setstate` 控制，使各策略消耗同一段随机序列、保证横向可比。改动 `smart_recommend` 的随机调用顺序会影响回测数值。
  3. 回测耗时随期数线性增长（每期每策略一次全量分析）。默认 `max_periods=200` 以控制响应时间；若后续要跑全量 300 期，建议加缓存或改用增量统计。
  4. `analyzer.py` 用 pandas/numpy 计算后**必须显式 `int()` / `float()` 转换**，否则 numpy 标量会导致 Flask `jsonify` 抛 `TypeError: Object of type int64 is not JSON serializable`（本次已踩坑）。
  5. 数据源仍是 300 期模拟数据。接入真实数据后，回测结论可能变化，但"独立随机"的预期不变。

---

### V1.2.1 — 修复热力图配色错乱（颜色跟着号码而非次数走）(2026-11-02 21:46)
- **负责智能体**：DeepSeek
- **工作分支**：fix/deepseek/heatmap-color-mapping
- **问题现象**（用户反馈）：
  - "热力图看不懂，有些次数多颜色也是冷色调"
  - 实测：号码 1 出现 **46 次**（高频）却显示深蓝冷色；号码 44 出现 36 次（偏低）反而是紫色中间色；
    整个 7×7 网格呈现一条**由下至上、随号码递增**的平滑渐变（1-7 深蓝 → 43-49 粉红），
    与真实出现次数完全无关。
- **根本原因**：
  - `renderHeatmap()` 把数据项写成了 `[col, row, 出现次数, 号码]` 四元组，
    而 `visualMap` **未指定 `dimension`**（诊断确认 `dimension: None`），
    ECharts 于是按**最后一个维度**上色 —— 那个维度恰好是号码本身。
- **修改目标**：
  1. 让颜色真正跟随出现次数（高频=暖色、低频=冷色）
  2. 让用户不依赖猜测就能看懂：显示图例 + 格子里直接标次数
- **核心改动文件**：
  - `static/js/main.js` → `renderHeatmap()`
    - 数据项改为三元组 `[col, row, 次数]`，去掉会误导 visualMap 的号码维度
    - `visualMap` 显式声明 `dimension: 2`，并 `show: true` 显示横向图例（`少（冷）`↔`多（热）`，`calculable: true` 可拖动）
    - `min`/`max` 改用实际次数区间（31–52）而非 `0–max`，冷热对比更明显
    - 格子标签改为两行：大字号码 + 小字出现次数（窄屏 `< 460px` 自动只显示号码）
    - 号码改由坐标反推 `row*7 + col + 1`，tooltip 与标签共用同一逻辑
    - `grid.bottom` 16 → 46，为底部图例留出空间
- **自测验证结果**：
  - **配色相关性**（canvas 像素采样，49 格全采）：
    - 修复前：R 通道 vs 号码 **+0.398**，vs 次数 **+0.010** → 颜色跟着号码走
    - 修复后：R 通道 vs 号码 **−0.085**，vs 次数 **+0.906** → 颜色跟着次数走 ✅
  - **端点核对**：最高频号码 18（52 次）→ RGB `#e94560`（暖红）；最低频号码 21（31 次）→ RGB `#1e293b`（冷暗） ✅
  - **标签/tooltip 正确性**：逐个调用 formatter 校验 49 格，号码与次数**不匹配数 = 0** ✅
  - **tooltip 实测**：`号码 18：出现 52 次` ✅
  - **回归**：仪表盘 9 张图全部正常绘制（逐图取样非空），控制台零报错 ✅
  - **响应式**：1560 / 1024 / 390 三种宽度均无横向溢出；390px 自动切换紧凑模式（12px 只显示号码） ✅
- **遗留注意事项 / 给下一位 Agent 的说明**：
  1. **ECharts heatmap 的 `data` 只放 `[x, y, value]` 三元组**。多塞一个维度（比如号码标签）且不写 `dimension`，
     就会重演本次事故 —— 颜色跟着标签维度走。要显示号码请用 `formatter` 由坐标反推。
  2. `visualMap` 在 `orient: "horizontal"` 下会**互换 `itemWidth`/`itemHeight`** 的语义。
     本次显式设 `140x12` 反而得到一根竖条压住中间格子，最终删除这两个参数、改用默认值才正常。
  3. `compact` 判断只在图表初始化时取 `clientWidth`，窗口从宽拖窄不会重新判定字号（仅影响字号，不影响正确性）。
  4. 热力图 tooltip 的 DOM 节点挂在 `document.body` 上、不在图表容器内；
     且 ECharts 隐藏元素用 `innerText` 取到的是空串，断言时请用 `textContent`（排查时踩过）。

---

## 四、待开发 (Backlog)

### P2 — 下一批迭代
- [ ] **真实历史数据爬虫**：对接开奖数据源，替换模拟数据
- [x] **历史命中率回测**：各策略的历史"命中"表现统计（V1.2 完成）
- [ ] **AI 生成每日玄机图**：用 AI 生图模型每天生成一张趣味玄机图
- [ ] **移动端适配**：响应式布局优化

### P3 — 远期
- [ ] **社区功能**：用户分享解码、评论互动
- [ ] **走势图**：号码随期号的时间序列走势
- [ ] **条件筛选**：按生肖、色波、区间等条件过滤历史记录
- [ ] **多彩种支持**：双色球、大乐透等

---

## 五、协作 Agent 快速上手

### 环境准备
```bash
pip install flask pandas numpy   # 核心依赖
pip install openai python-dotenv  # AI 视觉（可选）
```

### 本地运行
```bash
cd "e:\AI work\软件设计\lottery-analyzer"
python app.py
# → http://localhost:5000
```

### 开发约定
1. **新功能开分支**：`git checkout -b feature/xxx`
2. **Python 风格**：函数用蛇形命名，有 docstring
3. **前端无框架**：保持原生 JS，不引入 React/Vue
4. **API 向后兼容**：新增 OK，不改现有接口的入参/出参结构
5. **提交规范**：`feat:` / `fix:` / `refactor:` / `docs:` / `style:`

### 模块依赖关系
```
app.py ──→ database.py   (数据读写)
       ──→ analyzer.py   (统计分析，依赖 database)
       ──→ decoder.py    (解码推导，独立)
       ──→ backtest.py   (回测，依赖 analyzer + database)
       ──→ vision.py     (AI 视觉，依赖 decoder + kaggle_llm 外部)
```

### AI 视觉模块注意事项
- `vision.py` 依赖用户本机的 `c:\Users\10397\antigravity\kind-hubble\kaggle_llm.py`
- 如果部署到其他机器，需要配置 Kaggle 模型代理的认证
- `HAS_KAGGLE` 标志会在模块加载时自动检测，不可用时 graceful 降级
