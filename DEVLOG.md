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
│ 数据生成   │ 10项指标  │ 交叉推导  │ 接口用户自配置  │
└────────────┴──────────┴───────────┴────────────────┘
```

### 模块职责

| 模块 | 文件 | 职责 | 对外接口 |
|---|---|---|---|
| 数据层 | `database.py` | SQLite 建表、CRUD、模拟数据生成 | `get_all_results()`, `insert_result()` |
| 分析引擎 | `analyzer.py` | 频率、冷热号、遗漏值、奇偶比等统计 | `get_dashboard_data()`, `smart_recommend()` |
| 解码引擎 | `decoder.py` | 生肖/五行/色波/方位映射 + 多维交叉推导 | `decode_elements()`, `quick_decode()` |
| 回测引擎 | `backtest.py` | 策略历史命中率回测（无未来数据泄露） | `run_backtest()` |
| 配置管理 | `settings.py` | AI 接口配置读写 + Key 脱敏 | `load_settings()`, `public_settings()` |
| 视觉识别 | `vision.py` | 图片→AI分析→元素提取→映射转换（接口可自配） | `analyze_image()`, `map_vision_to_decoder_selections()` |
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

### V1.3 — AI 接口改为用户自配置，彻底移除 Kaggle 依赖 (2026-11-02 23:20)
- **负责智能体**：DeepSeek
- **工作分支**：feature/deepseek/configurable-ai-settings
- **触发问题**（用户提问"现在有用到 AI 吗"→ 排查发现 AI 功能实际是坏的）：
  1. `vision.py` 写死 `resolve_model("gemini-3.7")` → `google/gemini-3.7-flash`，
     而该模型在 Kaggle 代理上**不存在**，实测返回 `404 The requested model was not found`。
     即：图猜码的 AI 识图**一直是失效的**，只是失败被 try/except 吞掉、只在前端显示一句含糊报错。
  2. 逐个探测 Kaggle 别名表发现：`gemini-3.7`、`gemini-3.5` 均已 404，
     实际可用的只有 `google/gemini-3-flash-preview` 与 `google/gemini-3.1-flash-lite-preview`。
  3. 用户明确要求："那个 API 删除吧，要翻墙才能用不实在"。
- **修改目标**：
  1. 删除对 Kaggle 模型代理与本机外部脚本的全部依赖
  2. 新增「⚙️ 设置」页，让用户自己填写 Base URL / API Key / 模型名
  3. 未配置时优雅降级：图猜码禁用上传并引导去设置，**手动选元素解码照常可用**
- **核心改动文件**：
  - `settings.py`（新增，150 行）：AI 配置读写
    - 配置存 `data/settings.json`，**已加入 .gitignore**
    - `mask_key()` 脱敏，`public_settings()` 保证接口永不返回明文 Key
    - `save_settings()` 中 `api_key` 留空 = 保持原值（前端不回显，避免误清空）
    - 内置 7 个服务商预设（DeepSeek / 阿里百炼 / 智谱 / Moonshot / 硅基流动 / OpenAI / 本地 Ollama）
  - `vision.py`：
    - **删除** `sys.path.insert(r"c:\Users\10397\antigravity\kind-hubble")` 与 `kaggle_llm` 导入
    - **删除** `HAS_KAGGLE` 标志，改为 `_get_client()` 按用户配置构造 OpenAI 兼容客户端
    - 新增 `_friendly_error()`，把 401/403/404/429/超时/连不上翻译成中文可操作提示
  - `app.py`：
    - 新增 `GET/POST /api/settings`、`POST /api/settings/test`
    - `/api/decoder/vision` 未配置时返回 503 + 明确指引；AI 失败返回 502 + 可读原因
    - `/api/vision/status` 改为返回配置状态（不再依赖 HAS_KAGGLE）
  - `templates/index.html`：新增「⚙️ 设置」Tab（预设卡片 + 表单 + 测试按钮 + 安全说明）；
    图猜码页新增未配置警告条
  - `static/js/main.js`：设置页逻辑 + `refreshAiStatus()` 驱动图猜码降级
  - `static/css/style.css`：设置页样式
  - `requirements.txt`：补 `openai>=1.0`（原先靠外部脚本隐式带入，属于隐藏依赖）
- **自测验证结果**：
  - **安全（重点）**：保存含 Key 的配置后，POST/GET 响应体中**均不含明文 Key**；
    GET 返回字段确认无 `api_key`，只有 `api_key_masked`；`git check-ignore` 确认
    `data/settings.json` 被忽略，`git add -A` 后**未进入暂存区** ✅
  - **留空保持**：`api_key: ""` 提交后 Key 保留（末 4 位不变），base_url/model 正常更新 ✅
  - **持久化**：磁盘文件字段正确，`timeout` 以 int 落盘 ✅
  - **健壮性**：`timeout:"abc"`、`max_tokens:null`、未知字段、空 body 均不崩溃且不写坏配置 ✅
  - **错误可读**：假地址 → "无法连接接口地址"；错误模型名 → 404 提示；真实调用智谱 → 返回其原始中文报错"令牌已过期或验证不正确" ✅
  - **端到端（本地 mock OpenAI 服务）**：配置 → 测试连接 → 上传图片 → AI 识别 → 元素映射 → 出号，
    全链路打通；UI 实测上传后自动识别并输出「2 7 8 12 24 36 + 30」，控制台零报错 ✅
  - **降级**：未配置时警告条显示、上传区禁用且点击被拦下并引导，手动解码仍正常出号 ✅
  - **布局**：1500/1024/390 三种宽度无横向溢出，7 张预设卡无重叠，输入框均可用 ✅
  - **回归**：9 个既有端点全部 200 ✅
  - **残留检查**：全项目已无 `kaggle` / `HAS_KAGGLE` / `kind-hubble` 引用 ✅
- **遗留注意事项 / 给下一位 Agent 的说明**：
  1. **模型必须支持图片输入**。用户若填纯文本模型（如 `deepseek-chat`），接口能连通但识图会失败——
     预设里给 DeepSeek 填的是 `deepseek-chat` 仅作占位，实际识图建议用 `qwen-vl-max`、`glm-4v-flash`
     等视觉模型。这是当前最容易让用户困惑的点。
  2. `data/settings.json` **含明文 Key**。已在 .gitignore 中，但若将来加导出/备份功能，
     务必排除该文件；也不要把它打进任何发布包。
  3. `_friendly_error()` 目前按关键字匹配报错文本，各家服务商措辞不同，可能漏判；
     兜底会返回原始报错（截断 300 字符），不会吞掉信息。
  4. `POST /api/settings/test` 会发一条真实的 1x1 图片请求来验证**多模态**能力，
     因此会产生极小额度消耗；这是有意设计——只测文本无法确认能否识图。
  5. 本地 Ollama 无需 Key，`_get_client()` 在 Key 为空时传 `"not-needed"` 占位。

---

### V1.3.1 — 测试连接改为分阶段诊断 + 可读取模型列表 (2026-11-02 23:43)
- **负责智能体**：DeepSeek
- **工作分支**：fix/deepseek/ai-error-diagnostics
- **问题现象**（用户截图反馈"失败"）：
  - 用户填了中转站 `https://api-top.com/v1` + 模型名 `gemini-3.8-flash-high`，点「测试连接」后
    状态框里**原样抛出一大坨英文报错**：
    `Error code: 400 - {'error': {'code': 'upstream_unavailable', 'message': '服务暂时不可用，请稍后重试。'...}}`
  - 用户完全无法判断：是自己的 Key 错？地址错？模型名错？还是对方服务故障？
- **定位过程**：
  - 用不带 Key 的请求探测 `https://api-top.com/v1/models` → 返回 **401**，
    说明地址正确、接口存在，**不是网络或路径问题**。
  - 结合报错里的 `upstream_unavailable` 判定为**中转站上游故障**，
    与用户配置无关。但旧 `_friendly_error()` 只匹配 401/403/404/429/超时，
    **400 与 upstream 类报错完全没覆盖**，所以直接落了兜底原文。
- **修改目标**：
  1. 把 400 / upstream_unavailable / 5xx 等纳入中文翻译
  2. 测试不再是"一个笼统的成败"，而是**分阶段定位**：接口连通 → 文本对话 → 图片对话
  3. 新增「读取可用模型」，直接从 `/v1/models` 拉列表供点选，避免用户盲填模型名
- **核心改动文件**：
  - `vision.py` → `_friendly_error()` 重写
    - 新增 `upstream_unavailable` / `server_error` / "服务暂时不可用" → 明确告知"是服务商侧故障，不是你配错了"
    - 新增 400 兜底 → 提示"模型名不被支持，或该模型不支持图片"
    - 模型不存在判断补充 `does not exist` / `no such model` / `model_not_found` 三种措辞
  - `app.py`
    - 抽出 `_trial_config()` / `_build_trial_client()`，供测试与列模型复用
    - 新增 `POST /api/settings/models`：拉取 `/v1/models`；
      接口未实现（404）时提示"请手动填写"，不算配置错误
    - `/api/settings/test` 重写为**三阶段诊断**，返回 `stages[]`（每阶段 ok/detail），
      整体 `ok` 要求"接口通 + 文本通 + **图片也通**"（图猜码的硬性前提）
  - `templates/index.html`：模型名输入框旁新增「📋 读取可用模型」按钮与模型 chip 列表容器
  - `static/js/main.js`
    - `renderTestStages()` 渲染三阶段结果（✅/❌/⚠️ 分色）
    - `listModels()` / `pickModel()` 拉取并点选模型名
    - **修复一个真实的竞态 bug**：`loadSettings()` 是异步的，若用户在面板刚打开时就开始输入，
      请求返回后会把刚输入的内容覆盖掉。新增 `settingsDirty` 脏标记 + 二次校验，
      只在用户未改动时才回填；「重新载入」按钮走 `force=true` 强制覆盖
  - `static/css/style.css`：`.stage-row` / `.model-list` / `.model-chip` 样式
- **自测验证结果**（用三个不同端口的 mock 服务分别模拟故障）：
  - **场景 A upstream 故障**（精确复现用户报错）→
    结论「上游服务暂时不可用（服务商或中转站侧故障，不是你的配置写错了）」，
    阶段显示 `接口连通 OK / 文本对话 FAIL / 图片 SKIP` ✅
  - **场景 B 读取模型**：返回 3 个模型，UI 点选后正确填入输入框并高亮 ✅
  - **场景 C 模型名错误** → 「模型不存在，请检查模型名（可点读取可用模型查看）」，
    且阶段一同时提示"未找到你填的模型名" ✅
  - **场景 D 纯文本模型** → 「该模型不支持图片输入，图猜码将无法识图。请换用 qwen-vl-max、glm-4v-flash」，
    阶段显示 `连通 OK / 文本 OK / 图片 FAIL` —— 精确定位到问题层 ✅
  - **场景 E 全通** → 「连接成功，且该模型支持看图」 ✅
  - **UI**：1500/1024/390 三种宽度均为 3 条阶段记录、无横向溢出、无行内溢出、控制台零报错 ✅
  - **竞态修复**：打开面板后 60ms 内立刻输入，等异步结束，输入内容完整保留 ✅
  - **回归**：9 个既有端点全部 200；`data/settings.json` 仍被 gitignore ✅
- **遗留注意事项 / 给下一位 Agent 的说明**：
  1. 三段测试中**只有第三段（图片对话）失败**时，说明模型本身可用但**不支持视觉**——
     这是最常见的坑。用户常拿 `deepseek-chat`、`gpt-4o-mini` 之类来试，能连通但不能识图。
  2. `/models` 不是 OpenAI 规范强制接口，部分中转站不提供。此时会返回 404，
     代码按"跳过、不算失败"处理，并提示手动填写——**不要**把它当成配置错误。
  3. `_friendly_error()` 仍是关键字匹配，各家措辞千差万别；
     兜底返回原始报错（截断 300 字符），保证信息不被吞。
  4. 用户遇到的 `api-top.com` 是第三方中转站，其可用模型名与官方并不一致，
     这也是加「读取可用模型」的直接原因。**建议用户优先用官方或大厂直连接口。**
  5. 三阶段测试会产生 2~3 次真实调用（含一次图片请求），有极小额度消耗；
     这是有意的——只测文本无法确认能否识图。

### V1.4 — 真实历史数据爬虫：接入 1993 年至今 4393 期官方开奖 (2026-11-03 11:00)
- **负责智能体**：GLM
- **工作分支**：feature/glm/real-data-crawler
- **修改目标**：
  1. 用真实开奖数据替换 300 期模拟数据（用户确认：清空后导入，不并存）
  2. 统计窗口机制：真实数据 4400+ 期，Dashboard 默认统计近 500 期、可切换（用户确认方案）
  3. 不翻墙、零成本：HKJC 官方接口本机直连超时（实测被墙），改走 GitHub 开源数据集
- **数据源调研结论**（全部本机实测）：
  - ❌ `bet.hkjc.com/marksix/getJSON.aspx` — 直连超时（被墙），放弃
  - ❌ Renavon 数据集 — 下载链路被 Cloudflare 盾拦（403），无法自动化
  - ❌ 国内聚合站（78554.cc 等）— SPA 跳转 / 静态资源 502 / 域名不稳，放弃
  - ✅ **种子源** `icelam/mark-six-data-visualization` `data/all.json`：1993-01 ~ 2025-12，4288 期（源自 HKJC 官方）
  - ✅ **增量源** `stevetsang852/marksix-rd` `data/processed/draws.json`：2002-07 ~ 至今，GitHub Actions 每日同步 HKJC
  - 两源重叠 3277 期**零冲突**，交叉验证通过；合并后 **4393 期（1993-01-05 ~ 2026-10-03）**
- **核心改动文件**：
  - `crawler.py`（新增，246 行）：`fetch_real_data()` 双源抓取→归一化（期号 `25/134`→`2025134`）→按期号合并去重→合法性校验（1-49 范围、正码互异、特码不与正码重复——Mark Six 七球同机无放回摇出）；`import_all()` 全量导入、`sync_latest()` 增量（INSERT OR IGNORE 不覆盖已有期号）、`data_status()`
  - `database.py`：新增 `insert_many()`（executemany，返回真实新增条数）、`clear_results()`；**新增只读内存缓存**（写操作统一失效），解决真实数据量下回测反复全表查询的性能瓶颈
  - `analyzer.py`：`get_dashboard_data(window=500)` 支持统计窗口，`total_periods` 始终返回库内全量期数
  - `app.py`：新增 `GET /api/data/status`、`POST /api/data/import`（body 可选 `clear`，默认 true）、`POST /api/data/sync`；`/api/dashboard` 接受 `window` 参数（默认 500，0=全量）；**启动不再自动生成模拟数据**（空库时由设置页引导导入真实数据）
  - `templates/index.html`：仪表盘新增统计窗口下拉框（100/300/500/1000/全部）；设置页新增「🗄️ 数据管理」卡片（库内状态 + 导入/同步/刷新按钮，导入有 confirm 防误触）
  - `static/js/main.js`：窗口切换联动重载；`loadDataStatus()` / `importRealData()` / `syncLatestData()`；导入/同步成功后自动刷新仪表盘
  - `static/css/style.css`：`.dashboard-toolbar` / `.window-picker` / `.data-status-row` 样式（600px 以下工具栏纵向排列）
- **自测验证结果**：
  - **数据正确性**：抽检 2025-12-28 期与 icelam 原始 JSON 逐号一致；期号唯一、降序有序、范围 1993001→2026105 ✅
  - **交叉验证**：icelam 与 marksix-rd 重叠 3277 期号码零冲突；0 期跳过 ✅
  - **性能**：Dashboard window=500 **0.14s**、全量 0.90s；回测 200 期 44.5s → **14.6s**（缓存优化，3 倍提速），且优化前后同 seed 结果**逐值一致** ✅
  - **API 回归**：17 个端点（含 3 个新增）全部 HTTP 200 ✅
  - **前端实测**（Playwright）：窗口切换刷新正常、数据管理卡片显示正确、1600/390px 无横向溢出、控制台零报错 ✅
- **关键发现（重要，给下一位 Agent）**：
  1. **增量源 CI 目前是坏的**：marksix-rd 仓库的 `ingest-hkjc-daily` Actions 自 2026-10-29 起连续 failure——但失败的只是最后「Commit snapshots」步骤（git 提交，疑似仓库 Workflow permissions 设为只读），**「Fetch official candidates + parse」一直是 success**，即 HKJC 抓取链路仍正常。因此当前数据停在 2026-10-03（今天 2026-11-03，滞后约 1 个月）。恢复方案：用户 fork 该仓库 → Settings → Actions → Workflow permissions 改为 "Read and write" → 手动触发 workflow_dispatch 即可恢复每日同步；届时本项目无需改代码，`sync_latest()` 拉的就是自己 fork 的地址（改 `crawler.LATEST_URL` 指向 fork）。
     > **已由 V1.4.4 解决**：不再依赖该仓库，改用 Renavon CSV 作首选增量源（marksix-rd 退为兜底）。上文的 fork 方案**无需执行**。
  2. **生肖映射是静态表（已知大坑，下版本处理）**：真实六合彩每年生肖↔号码对应随农历年变化，`decoder.py` 目前是静态映射，接入真实数据后「图猜码」的生肖推导会失准。五行/色波/方位映射不受影响。建议下版本做「按开奖年份的动态生肖表」（每年以冬至/立春为界有不同派别，需先与用户确认口径）。
  3. `get_all_results()` 现在返回**缓存列表的切片/引用**，调用方不得原地修改返回的 dict，否则会污染缓存（当前所有调用方均只读）。
  4. 回测耗时随库内期数增长（每期分析要扫全部历史），200 期 14.6s 可接受；若用户跑全量 4300+ 期回测预计需数分钟，属预期行为。
  5. 特码与正码可能同号在模拟数据中出现过，真实数据中七球互异——校验规则以此为准，若未来数据源违反该规则会被跳过并报告。
  6. **数据源现状（V1.4.4 后）**：`crawler.py` 三源 —— 种子 `icelam`（全量历史）+ 增量首选 `renavon`（每期开奖后更新）+ 增量兜底 `marksix-rd`（CI 坏了，仅作冗余）。新增/改动数据源时记得同步更新本条与 `data_status()` 的 `sources` 字段。

### V1.4.1 — 修复生肖映射（静态表→按农历年动态表） (2026-11-03 11:30)
- **负责智能体**：DeepSeek
- **修改目标**：`decoder.py` 的生肖↔号码表原是**静态硬编码**，且注释标"2024年甲辰年"而实际内容为 **2021 辛丑牛年**的表（牛=1,13,25,37,49），接入真实数据后图猜码的生肖推导一直失准。改为按日期动态生成。
- **口径确认（用户已拍板）**：
  1. **分配规则**：当年生肖 = 1/13/25/37/49，其余号码按生肖逆序轮排（标准 HKJC 生肖表）
  2. **换表界点**：农历正月初一（非立春、非公历 1 月 1 日）
- **实现**：
  - `decoder.py`：移除 `ZODIAC_MAP`，新增 `ZODIAC_ORDER`、`lunar_year_of()`、`year_zodiac()`、`get_zodiac_map(d)`、`zodiac_info(d)`；用 `lunardate` 做农历换算，`@lru_cache` 缓存各年表
  - 全部 4 处引用点改为 `get_zodiac_map()`（`get_all_categories` / `decode_elements` ×2 / `quick_decode` ×2）
  - `decode_elements` 返回体新增 `zodiac_table`；`decode_trace` 首行标注所用年份表，如「🐾 生肖【马】→ 号码 [1,13,25,37,49]（2026 马年表）」
  - 前端：生肖分类下新增提示条「当前生效：农历 2026 马年表（2026-02-17 起…）」，避免跨年时用户误以为号码错了
  - `requirements.txt` 新增 `lunardate>=0.2`（纯 Python 无额外依赖）
- **自测验证**：2024 龙年/2026 马年/2021 牛年三张表与标准表逐项一致；1-49 每号唯一归属、覆盖完整；2026-02-16（蛇年）→ 2026-02-17（马年）界点切换正确；`/api/decoder/decode` 传 `{"zodiac":["马"]}` 返回 1,13,25,37,49；前端提示条渲染正常、真实点击选项可正常选中（先前浏览器测试报的"点击无效"是测试脚本误点提示文字+重复点击取消选中所致，非代码缺陷）
- **对 V1.4 遗留事项 2 的更新**：该项已完成，不再需要下版本处理
- **关于统计窗口（用户决定）**：实测 150 期 32ms、500 期 132ms、全量 4393 期 872ms；用户选择**保持默认 500 期**，下拉选项不变（100/300/500/1000/全部）

### V1.4.2 — 特码专项统计 + 正码生肖分布 (2026-11-03 13:40)
- **负责智能体**：GLM
- **修改目标**（用户提出）：1) 特码单独统计（数字、生肖、波色）；2) 主号（6 个正码）的生肖分布情况。
- **实现**：
  - `analyzer.py`：新增 `special_stats(limit)` —— 特码号码频次（1-49）、期望值（总期数/49）、冷热 Top/Bottom、生肖分布（含百分比）、波色分布（含百分比）；新增 `main_zodiac_stats(limit)` —— 6 个正码的生肖分布与百分比、期望值（总号码数/12）。
  - **生肖按各期开奖日期所属农历年换算**（复用 V1.4.1 的动态生肖表），因此特码/正码生肖分布与「图猜码」推导口径完全一致；波色反查表 `COLOR_OF_NUMBER` 由 `decoder.COLOR_MAP` 生成，避免两处各写一份。
  - `app.py`：`get_dashboard_data()` 新增 `special_stats` / `main_zodiac` 两个键；**并新增 `app.json.sort_keys = False`** —— Flask 默认按字母重排 JSON key，会把生肖顺序打乱导致图表横轴变成 虎/狗/虎…，必须保留插入顺序。
  - `templates/index.html`：新增 4 张图表卡片（特码频次 / 特码波色 / 特码生肖 / 正码生肖），各带 `.chart-note` 说明（"按各期开奖日期所属农历年的生肖表换算"、"虚线为 12 生肖均分的期望值"）。
  - `static/js/main.js`：新增 `WAVE_COLORS` 与 `renderSpecialFreqChart()` / `renderSpecialColorChart()` / `renderSpecialZodiacChart()` / `renderMainZodiacChart()`，在 `loadDashboard()` 中联动渲染。
- **自测验证**：特码频次合计 = 总期数、生肖合计 = 总期数、波色合计 = 总期数（守恒校验通过）；独立重算波色与实现一致；两个函数各约 4ms，不影响 Dashboard 响应时间 ✅
- **注意**：所有统计都跟随仪表盘的**统计窗口**（默认近 500 期）联动，不是全库口径。

### V1.4.3 — 修复「图片包含敏感内容」误报 (2026-11-03 14:20)
- **负责智能体**：GLM
- **问题现象**：用户上传玄机图识图，报「图片包含敏感内容」（HTTP 400，`sensitive_words_detected`）。
- **根因（8 组对照实验确认）**：**与图片内容无关**。服务商的审核网关是按**整次请求的文本**（system + user prompt）判定，与图片字节无关。实验记录：

  | system 提示词 | user 文本 | 带图 | 结果 |
  |---|---|---|---|
  | 无 | 短（"回复两个字：可用"） | 是 | 200 ✅ |
  | 识图 | 短 | 是 | 200 ✅ |
  | 无 | 识图提示词 | 是 | **400 sensitive** ❌ |
  | 无 | 中性长描述 | 是 | **400 sensitive** ❌ |
  | 中性「图像助手」 | 中性描述 | 否 | **400 sensitive** ❌ |
  | 识图 | 识图提示词 | 否 | 200 ✅ |

  即：纯数字图、甚至 1×1 像素图会被拦；而含「必中 / 投注 / 特码」字样的图反而 200 通过 —— 属服务商侧规则误伤。
- **修复**：
  1. `vision.py` 的 `_friendly_error()` 新增 `sensitive_words_detected` 分支：明确告知用户这是网关对**请求文本**的判定、与图片无关，并给出「稍后重试 / 换模型 / 保持内置提示词」的建议，而不是含糊地说"图片有问题"。
  2. `app.py` 设置页「🔌 测试连接」第③步「图片对话」**改为复用真实识图的 `VISION_SYSTEM_PROMPT` + `VISION_USER_PROMPT`**，`max_tokens` 16→512。原先用另写的一套中性探测提示词，会出现「探测失败但实际识图可用」的假阴性（现已通过真实提示词复测：三阶段全绿）。
  3. `vision.py` 的 `analyze_image()`：`content` 为空时回退去解析 `reasoning_content` —— ⚠️ **此做法在 V1.4.5 被推翻**，理由见下。
- **模型兼容性结论（服务端 autodl.art，实测）**：
  - ✅ `DeepSeek-V4.1-Flash-1017`
  - ✅ `qwen3-vl-plus`（**已切换为当前默认模型**）、✅ `qwen3.6-plus`（返回内容带 ```json 围栏，解析器已兼容）
  - ❌ `qwen3.7-max`：不支持 `image_url` 格式，报 `invalid_parameter_error`（"Unexpected item type in content"）
- **顺带修掉「测试连接」第③步的假阴性**：原来用 **1×1 像素 PNG** 探测，而 `qwen3-vl-plus` 等模型要求宽高都 > 10px，会返回 `invalid_parameter_error` → 被误报成「该模型不支持图片输入」。已改为 **64×64 探测图**（`_PROBE_PNG`），改后三阶段全绿。
- **自测验证**（模型 `qwen3-vl-plus`）：
  - 真实识图路径（红底白椭圆 PNG）返回 `colors: ['红','白']`、`elements: ['火','金']`、`directions: ['南']`，无 error ✅
  - `/api/decoder/vision` 全链路返回候选 37 个号码、推荐 `main=[2,18,19,24,34,35] special=40` ✅
  - `/api/settings/test` 三阶段全绿（模型列表 42 个命中 ✓ / 文本对话 ✓ / 图片对话 ✓）✅

### V1.4.5 — 两个视觉模型实测对比 + 修掉 3 个真实崩溃点 (2026-11-03 16:10)
- **负责智能体**：GLM
- **背景**：用户问「DeepSeek-V4.1-Flash-1017 和 qwen3-vl-plus 哪个效果更好」，遂用同一张水墨玄机图（金虎/竹林/溪流/紅灯笼/「龍」字石碑）做 5~6 次重复实测。
- **实测结论**：

  | 指标 | DeepSeek-V4.1-Flash-1017 | qwen3-vl-plus |
  |---|---|---|
  | 可用率（识别出生肖） | **5/6** | **6/6** |
  | 平均耗时 | 13.8s | 6.5~16.6s |
  | 输入 token | 1295 | 2779（图片占 2496） |
  | 输出 token | ~900（含长思考） | ~150 |
  | 识图质量 | 虎+龙 都识别，描述详尽 | 虎+龙 都识别，描述详尽 |
  | 稳定性 | **会输出散文/空内容** | **稳定遵守 JSON 格式** |

  → **推荐 `qwen3-vl-plus` 作为默认**：格式稳定、失败率低、输出更省 token。DeepSeek 也能用，但需注意下面的坑。
- **顺带发现并修复 3 个真实 bug**（都在 V1.4.3 引入的兜底逻辑周围）：
  1. **`AttributeError: 'list' object has no attribute 'get'`（DeepSeek 下 2/5 必崩）**
     根因链：DeepSeek 是推理型模型，会先输出 800~3800 字符的 `reasoning_content` 思考过程 → `max_tokens=1024` 时思考吃光预算 → `content` 为空、`finish_reason='length'` → V1.4.3 的兜底去解析 `reasoning_content`（自然语言）→ 正则从思考过程里误匹配出 JSON 片段 → `json.loads` 解析成 **list** → 上层 `.get()` 崩溃。
     **修复**：`finish_reason == 'length'` 且 content 为空时，**加大 max_tokens 重试**（×4，至少 4096）；**彻底不解析 reasoning_content**。
  2. **`_parse_json_response` 可能返回 list/None** → 改为内部 `_coerce()` 统一收敛成 dict（list 取首个 dict 元素，无 dict 则当 objects 列表）。
  3. **`decoder.decode_elements()` 的 `recommended` 字段类型不一致** —— 正常是 dict，无元素时却是 `[]`（list）→ 调用方 `.get()` 崩溃。已改为**始终返回 `{"main": [...], "special": ...}`**。
- **另外两个健壮性改进**：
  - 重试后仍无内容 → **显式报错**（原来静默返回空，前端只显示「未识别到明显元素」，用户看不到原因）。
  - 模型未按 JSON 格式回答（DeepSeek 偶尔输出散文）→ 显式报错并附原文摘要，不再静默。
- **自测验证**：
  - `_parse_json_response` 对 6 种输入（dict/含 dict 的 list/纯 list/字符串/非 JSON/夹带文本）**全部返回 dict** ✓
  - DeepSeek 6 次真实调用：5 次可用，1 次返回明确的 502 中文错误（不再崩溃）✓
  - qwen3-vl-plus 6 次真实调用：6/6 可用 ✓
  - 20 个 API 端点全部 200 ✓；`decode_elements` 在 5 种入参下 `recommended` 恒为 dict ✓
- **默认模型保持 `qwen3-vl-plus`**

### V1.4.6 — 视觉模型选型横评（站内外比价）+ 分辨率成本曲线 (2026-11-03 17:40)
- **负责智能体**：GLM
- **背景**：用户问「除了 DeepSeek 和 qwen3-vl-plus，还有什么更便宜或效果更好的推荐，不限中转站」。
- **中转站全量模型清单（42 个）**：`/v1/models` 实测只有 `qwen3-vl-plus` 明确带 VL 标记；`glm-4.6v-flash` / `glm-4.6v-flashx` / `qwen3-vl-flash` / `qwen3-vl-8b` **均返回 503「模型不存在或已被删除」**（中转站不透传智谱视觉型号）。
- **中转站横评（同一张水墨玄机图：虎+竹林+溪流+红灯笼+「龍」字石碑）**：

  | 模型 | 结果 | 输入 tok（图片） | 输出 tok | 耗时 |
  |---|---|---|---|---|
  | **qwen3-vl-plus** | ✅ 虎+龙 | 2779（2496） | 163 | 17.0s |
  | Kimi-K2.6 | ✅ 虎+龙 | 4408（4146） | 127 | 8.8s |
  | Qwen3.5-397B-A17B | ✅ 虎+龙 | 2777（2496） | 1336 | 42.8s |
  | qwen3.6-plus | ✅ 虎+龙 | 2777（2496） | 2000 | 43.2s |
  | GLM-5.3-flash | ✅ 虎+龙 | 5076（4800） | 530 | 24.2s |
  | gpt-5.6-luna | ⚠️ 只认出虎（**漏「龍」**） | 3671 | 337 | 21.1s |
  | MiniMax-M3.1-Flash / hy4-preview | ❌ finish=length 输出散文 | 4324 / 278 | 1024 | 34.8s / 59.6s |
  | claude-sonnet-4-6 | ❌ 被网关拒（"I can't discuss that."） | 0 | 18 | 10.9s |
  | GLM-5.3 | ❌ 400 内部 MaaS 拒绝 | — | — | — |

  → **中转站内 qwen3-vl-plus 仍是唯一「最便宜 + 最稳」的选择**：会员价 输入 ￥0.500/M、输出 ￥5.000/M；Kimi 快但图片 token 翻倍，GLM-5.3-flash 图片 token 4800（约为 qwen 的 2 倍）。
- **站外更优选项（价格查自官方定价页）**：

  | 厂商 / 模型 | 输入 | 输出 | 备注 |
  |---|---|---|---|
  | **智谱 GLM-4.6V-Flash** | **免费** | **免费** | 缓存也免费；128K 上下文；OpenAI 兼容端点 `https://open.bigmodel.cn/api/paas/v4/` |
  | 智谱 GLM-4.6V-FlashX | ￥0.15/M | ￥1.5/M | 9B 轻量高速 |
  | 智谱 GLM-5.3-Flash | ￥0.8/M | ￥2.8/M | 限时五折 ￥0.4/￥1.4 |
  | 阿里云百炼 qwen3-vl-plus | ￥3/M | ￥30/M | 比中转站会员价贵 6 倍；新用户有免费 token 额度 |
  | 硅基流动 GLM-4.5V | ￥1/M | ￥6/M | |
  | Kimi 官方 kimi-k2.6 | ￥6.5/M | ￥27/M | 12 月底下线；kimi-k3.1-pro ￥13/￥68 更贵 |
  | OpenRouter 免费视觉 | $0 | $0 | 仅 11 个（gemma-4-31b-it / nemotron-3.5-super-vl 等），质量未验证 |

  → **唯一实质性更便宜的选项是智谱 GLM-4.6V-Flash（完全免费）**；其余站外大厂单价均高于中转站会员价。
- **端点可达性（国内直连探测，无 Key）**：Google AI Studio / 智谱 / 百炼 / 硅基流动 / 火山方舟 / 腾讯混元 / DeepSeek 官方 / Moonshot / OpenRouter 全部返回 401/403（非超时）→ **均可在大陆直连**。
- **分辨率 → token 成本曲线（新增实测，用于成本优化）**：

  | 分辨率 | qwen3-vl-plus 输入 tok | 单次成本 | GLM-5.3-flash 输入 tok | 单次成本 |
  |---|---|---|---|---|
  | 2240×1680（原图） | 2510 | ￥0.001535 | 4820 | ￥0.003046 |
  | 1600×1200 | 1916 | ￥0.001238 | 2514 | ￥0.001710 |
  | 1280×960 | 1216 | ￥0.000893 | 1630 | ￥0.001197 |
  | 1024×768 | 784 | ￥0.000672 | 1056 | ￥0.000921 |
  | 800×600 | 491 | ￥0.000516 | 658 | ￥0.000727 |

  → **图片 token 随像素近似线性下降**，压缩是最有效的成本杠杆。
- **压缩不损识别（关键验证）**：用真实 `VISION_SYSTEM_PROMPT` 在 5 档分辨率下重跑，**全部 5 档都同时认出「虎」和「龍」**（800×600 那档甚至把「龍」直接列进了 `animals`）。→ 上传前压到 1024×768 可把成本砍掉约 55% 且不牺牲识别率。
- **本次改动**：仅更新 `settings.py` 的 `PROVIDER_PRESETS`（3 处过期信息）——
  - 智谱预设 `glm-4v-flash` → **`glm-4.6v-flash`**（前者已下线；新模型输入/输出/缓存全免）
  - 百炼预设 `qwen-vl-max` → **`qwen3-vl-plus`**（当前主力 VL 型号），note 补上官方单价
  - Moonshot 预设 `moonshot-v1-8k-vision-preview` → **`kimi-k2.6`**（前者 2026-08-31 已下线）
- **未改动**：默认模型仍是 `qwen3-vl-plus`；图片压缩**尚未**接入前端（等用户确认后再做，避免无谓改动）。

### V1.4.7 — GLM-4.6V-Flash 免费模型的真实限制（查证，不改代码） (2026-11-03 18:20)
- **负责智能体**：GLM
- **背景**：用户追问「GLM-4.6V-Flash 虽然完全免费但有没有别的限制」。以下是**官方文档查证结果**（非推测）。
- **结论：免费 ≠ 无限制，共 6 条真实约束**：

  | # | 限制 | 官方依据 | 对本项目的影响 |
  |---|---|---|---|
  | 1 | **并发数受限，且免费模型通常更严** | 速率限制文档：按「用户权益等级 × 模型维度」限制**在途请求数**；错误码 **1302** = 触发用户速率限制，**1305** = 平台服务过载 | 单人手动使用无碍；**不可用于并发/批量场景** |
  | 2 | **权益等级 V0 起步** | 积分区间 V0=[0,2000) 仅「基础服务」；并发靠消耗现金余额累积积分升级 | 新注册即 V0，不充值就长期低并发；**充值反而会降级到付费模型更划算** |
  | 3 | **高峰期动态限流 + 平台级过载** | 「若某一模型短时间内整体访问量激增 / 底层算力高负载」→ 触发**平台级保护机制**（1305） | 免费模型是过载时**优先被挤掉的一档**，稳定性差于付费模型 |
  | 4 | **上下文长度未标注** | 官方定价表 GLM-4.6V-Flash 的「上下文」列为 **`—`**（未标注）；模型概览页标注 128K | 实际可用上限需实测确认，勿当 128K 用 |
  | 5 | **思考模式可开关 → 会产生 reasoning_content** | 模型页明示「支持开启或关闭思考模式」；流式示例中 `delta.reasoning_content` 与 `delta.content` 是**两个独立字段** | **正是 V1.4.5 踩过的坑**：思考吃光 `max_tokens` → content 空 → `finish_reason='length'`。本项目 `vision.py` 已有重试兜底，但**若接智谱应在请求里显式传 `thinking: {"type":"disabled"}`**（通过 `extra_body`），避免白白浪费 |
  | 6 | **模型能力有上限** | 9B 版本 GLM-4.6V-Flash「整体表现超过 Qwen3-VL-**8B**」；106B 的 GLM-4.6V 才「比肩 2 倍参数量的 Qwen3-VL-235B」 | **9B ≠ qwen3-vl-plus 的水平**。玄机图识别要「龙」字石碑这种细节，准确率大概率**低于** qwen3-vl-plus |

- **附带确认（接入可行性）**：
  - 智谱 OpenAI 兼容端点 `https://open.bigmodel.cn/api/paas/v4/` **确实支持 `image_url` + base64 data URI**，官方示例：`{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,{...}"}}` → **本项目 `vision.py` 的现有请求体可直接复用，零代码改动** ✅
  - 官方定价表确认 GLM-4.6V-Flash：输入 **免费**、输出 **免费**、缓存命中 **免费**（付费的 GLM-4.6V-FlashX 是 ￥0.15/￥1.5）。
- **给用户的最终建议（分场景）**：
  - **日常自用、愿意注册智谱** → 用 GLM-4.6V-Flash，成本归零；但需接受「9B 模型精度可能略逊 + 高峰期可能限流」。
  - **要最高识图成功率** → 留在中转站 `qwen3-vl-plus`（实测 6/6 稳定），**单次成本仅 ￥0.0009~0.0015**，即使日用 100 次也只有 ￥0.1 左右；这个价位没必要为省这点钱牺牲成功率。
  - **两者可并存**：设置页填智谱（免费）+ 保留中转站（备用），识图失败时手动切换。

### V1.4.9 — 推荐理由可解释化：每个号码「为什么是它」 (2026-11-03 20:30)
- **负责智能体**：GLM
- **起因（用户提问）**：「输出结果能不能补一下说明（结果的理由呢？）」
- **问题**：解码器原来只输出**总分**（`all_candidates: [{number, score}]`）。用户看到「推荐 8、3、15…」但完全不知道依据 —— 而玄机图这类内容天生需要"解读"才可信，光给号码等于黑箱。

- **改动 1 · `decoder.py` 记录命中线索**：新增 `reasons` 结构，`decode_elements` 现在返回
  ```python
  "reasons": {
      "8": [{"dim": "数字", "label": "8", "weight": 5, "desc": "图上直接出现数字「8」"},
            {"dim": "生肖", "label": "龙", "weight": 3, "desc": "图上刻字「龙」"}],
      ...
  }
  ```
  - 打分从 `score[n] += w` 改为统一的 `_add(n, w, dim, label, desc)`，权重与理由**同时**写入，保证两者永远一致。
  - 单元测试断言「每个号码 reasons 的权重之和 == 该号码总分」，杜绝账实不符。

- **改动 2 · `vision.py` 记录图上证据（evidence）**：光说「命中生肖龙」还不够，用户仍不知道是**画的龙**还是**刻的「龍」字**。`map_vision_to_decoder_selections` 新增 `evidence` 字段：
  ```python
  "evidence": {"zodiac": {"龙": ["图上刻字「龙」"]},
                "wuxing": {"木": ["图中元素「竹林(木)」"]},
                "color":  {"红波": ["图中颜色为「淡红」"]},
                "direction": {"西": ["图中位置「右上-三盏红灯笼」"]}}
  ```
  decoder 优先用 evidence 作为理由文案，缺失时才回退到「生肖命中：龙」这种笼统说法。

- **改动 3 · 前端展示**（`main.js` + `style.css`）：
  - 新增 `renderReasonList()`：推荐号码下方渲染「💡 推荐理由」区块，按维度分色展示色块（生肖红 / 五行绿 / 色波橙 / 方位紫 / 数字黄），每行显示 **号码 + 总权重 + 各维度线索**，鼠标悬浮看「图上什么导致这条线索」。
  - 新增 `reasonTooltip()`：候选号码权重排行的 title 从「权重: 9」升级为「权重 9｜生肖·马(+3)，色波·红波(+2)」。
  - AI 识图路径与手动解码路径**两条**都接上（此前只有前者有 trace 展示）。

- **验证**：
  - 后端单元测试 11 项全过（含「理由权重和 == 总分」「reasons 覆盖全部候选」「空结果 reasons 为空 dict」）。
  - 前端用 Node 抽出两个新函数喂真实 API 数据跑通，覆盖边界：reasons 缺失 / 空对象 / 空号码数组 / special 为 null，**均无异常**。
  - 线上自测：`POST /api/decoder/decode` 返回体已含 `reasons` 键。

- **⚠️ 一次"报错"的排查结论（重要，避免下次重复排查）**：
  用户贴出错误串 `4351215203264907:76290bd0bdbf45d792590b2d2352747e_...:TraeWork CN.3.4.13.no_sid.no_ppe.T(2026/11/3 16:43:57)`。
  - **这不是本项目的报错**，而是 **Trae 客户端自身的错误上报签名**：结构为 `<错误ID>:<哈希链>:<客户端标识>`，其中 `TraeWork CN.3.4.13` 是 IDE 版本、`no_sid` 表示未登录会话、`no_ppe` 表示未启用企业策略、`T` 为类型前缀。
  - **排查方式**：不必逐字解读那串哈希。正确做法是**直接验证项目自身是否健康**：
    1. `python -c "import app"` → 导入正常（无语法/循环依赖错误）
    2. 起服务后探测 `GET /` 与 `/static/js/main.js`、`/static/css/style.css` → 全部 200
    3. `POST /api/decoder/decode` → 返回体含 `reasons`，业务逻辑正常
    4. `node --check static/js/main.js` → 语法通过
    5. 前端新函数用 Node 单测喂真实数据 → 无异常
  - 结论：**项目侧无任何问题**，该错误来自 IDE 客户端，与代码改动无关。
  - **教训**：以后再遇到 `TraeWork CN.x.x.x` 开头的错误串，直接按上面 5 步验证项目即可，不要花时间逆向那串哈希。

### V1.4.8 — 玄机图「拆解能力」增强：提示词三步化 + 解码维度补全 (2026-11-03 19:40)
- **负责智能体**：GLM
- **起因（用户提问）**：「一般图纸都是云里雾里需要解读和拆解，这样的情况用 VL 模型足够吗？」
- **结论**：**足够 —— 瓶颈不在模型，在提示词和本地映射层。** 用 PIL 合成一张"云里雾里"的模糊玄机图（1000×750，宣纸底 + 墨晕 + 竹林 + 溪流 + 三盏红灯笼 + 石碑刻「龍」和 8 + 马 + 羊，叠 3.2px 高斯模糊 + 26% 白雾），真值已知，同模型 `qwen3-vl-plus` A/B 两组提示词各跑 3 次：

  | 要素 | 【A】旧提示词（只描述） | 【B】新提示词（扫描→拆解→输出） |
  |---|---|---|
  | 马 / 红 / 灯笼 / 竹 / 水 / 龍 / 8 / 三 | 3/3 | 3/3 |
  | **羊（半透明背景那只）** | **0/3** | **3/3** |
  | 方位 | **「东（竹林常象征东方，青龙位）」= 凭空编造** | 「右上-三盏红灯笼」「中央-石碑」= 真实位置 |
  | 平均耗时 / token | 7.2s，in 998 / out 163 | 9.8s，in 1408 / out 353 |

  成本影响：单次从约 ￥0.0013 → ￥0.0025（会员价），仍可忽略。

- **改动 1 · `vision.py` 提示词三步化**：从「列出看到什么」改为 **扫描 → 拆解 → 输出**，并强制产出 `characters`（图上汉字）/ `counts`（数量线索）/ `numbers`（图中数字）三个独立字段 —— 这三个正是解码器真正吃得下的线索。
- **改动 2 · 解码维度补全**（旧解码器**压根不读**新字段，所以光换提示词没用）：

  | 维度 | 旧 | 新 |
  |---|---|---|
  | 直接数字（石碑刻 8） | 不支持 | **权重 +5** |
  | 数量线索（三盏灯笼 → 3） | 不支持 | **权重 +2** |
  | 图上汉字（龍） | 只当普通物件 | 映射到生肖 / 五行 |
  | 繁体字 | 原样输出「龍」→ 匹配失败 | `_TRAD_SIMP` 归一 |
  | 关键词匹配 | 精确匹配 → 几乎全灭 | **子串匹配**（「红灯笼」→ 火 + 红波） |

- **改动 3 · 修了 5 个真实 bug**（都是这轮实测暴露的）：
  1. **方位别名子串匹配"爆炸"**：一条描述遍历整张别名表且不 break，「右上-红灯笼」同时命中「右(西)」和「上(北)」，多条叠加集齐东南西北 = 覆盖 1-49 → 方位维度给所有号码加同一个 +1，**完全失效**。改为按优先级排序的列表 + `break`（一条描述只取一个方位）。
  2. **`numbers` / `counts` 字段无人消费**：AI 明明给出 `numbers=['8']` 也被丢弃 → selections 新增 `numbers` / `count_numbers`。
  3. **objects 精确匹配几乎全灭**：AI 返回「红灯笼」「竹林」「石碑」这类带修饰词的字符串，全部未命中 → 改子串匹配。
  4. **繁体字导致生肖线索整条丢失**：石碑刻「龍」，模型原样输出「龍」，映射表里只有「龙」→ 加 `_TRAD_SIMP` 归一。
  5. **「直接数字」被「数量线索」抢走权重**：提示词里 `numbers` 定义为「图中数字**以及由数量推出的数字**」，模型会把数出来的 3 也填进去 → 3 拿到 +5 的"直接暗示"权重。改为：`counts` 只认**开头的中文数量词**（排除引号内引用的字面数字），与 `counts` 重复的数字一律降级为数量线索。

- **改动 4 · 维度护栏（通用化）**：**同一维度若多个分类的号码并集覆盖全部 1-49，该维度就被中和** —— 每个号码拿到同样加分，等于没有信息。
  - 踩过三次：方位集齐东南西北 / 五行同时识别出木火金水土（各 10 个，合计 49）/ 生肖若 12 个全被识别。
  - 现在由 `decoder._apply_dimension()` 统一检查并整维丢弃，同时写进 trace（不静默丢弃）。**方位/五行/色波/生肖四维全部走这条护栏。**
  - 顺带修了 trace 丢失：所有维度都被丢弃时 `score` 为空会提前 return，原实现把 trace 整个丢掉，用户只看到「未选择任何解码元素」，完全不知道发生了什么。

- **改动 5 · 前端补展示** `characters` / `counts` 两个新字段（`main.js` + `style.css` 新增 `.vision-tag.character` / `.vision-tag.count`）。

- **验证**：
  - **单元测试** 28 项全过（中文数字解析、数量线索只认前缀、繁体归一、方位单象限、四维护栏、关键词子串、权重 5 vs 2）。
  - **端到端回归**：`la_hazy.jpg` 真值已知 → 生肖马/羊/龙全中、8 进直接线索、3 进数量线索、8 与 3 都进推荐号码。
  - **稳定性**：同图连跑 5 次，9 项关键指标 **全部 5/5**（生肖马/羊/龙、直接数字 8、数量 3、五行火、红波、8 进推荐、3 进推荐）。

- **未接入（已实测，待用户确认）**：上传前用 canvas 压到最大边 1280、JPEG 质量 0.85，可砍约 **55%** 成本且 5 档分辨率下识别率**无损**（800×600 那档甚至把「龍」直接列进了 `animals`）。

### V1.4.4 — 恢复开奖数据增量同步（新增 Renavon 源） (2026-11-03 15:20)
- **负责智能体**：GLM
- **问题**：`marksix-rd` 增量源自 2026-10-29 起 CI 失败，数据停在 2026-10-03，库内比实际落后约一个月。
- **解决**：实测发现 **Renavon 的 CSV 导出可直连**（`https://renavon.com/data/hkjc/hkjc_marksix_results/download/csv`），覆盖 1993-01 ~ 至今、每期开奖后更新，成为**首选增量源**。
  - 三个坑：① 需要**浏览器 UA**（默认 UA 返回 403）；② 响应体是 gzip 但**未声明 `Content-Encoding`**，须按魔数 `1f 8b` 自行解压；③ 文件带 **UTF-8 BOM**，须用 `utf-8-sig` 解码，否则首列名变成 `﻿draw_record_id`。
- **实现**（`crawler.py`）：
  - 新增 `_fetch_renavon_csv()`（浏览器 UA + gzip 自解 + BOM 处理）与 `_normalize_renavon()`（CSV → 统一结构，期号由 `draw_year` + `draw_number_in_year` 拼成 `YYYYSSS`）。
  - 新增 `_fetch_optional_sources()`：两个增量源**独立降级**，任一失败不影响另一个，错误写入 `stats.source_errors` 而非中断导入。
  - `fetch_real_data()` / `sync_latest()` 改为多源合并；`sync_latest()` 在所有增量源都不可用时抛出带各源错误明细的 `RuntimeError`。
  - `data_status()` 的 `sources` 字段改为 `seed` / `latest`（Renavon）/ `fallback`（marksix-rd）。
  - 前端同步结果提示追加「部分数据源不可用」警告。
- **数据校验**：
  - Renavon 与库内 **4393 期重叠部分：号码零冲突、日期零差异** ✅
  - 与 Renavon 原始 CSV **全量 4404 期逐期比对：零不一致** ✅
  - 期号唯一、降序有序、七号互异且均在 1-49、正码升序存储 ✅
  - 新增的 11 期（2026106 ~ 2026116）开奖日期全部落在周二/四/六 ✅
  - 全量导入路径：4404 期、`conflict_count=0`、`skipped=0` ✅
  - 降级路径（模拟 renavon 抛错）：marksix-rd 仍供数，导入不中断，`source_errors` 正确上报；两源全挂时给出明确错误 ✅
  - 19 个 API 端点全部 200 ✅
- **库内现状**：**4404 期（1993-01-05 ~ 2026-10-31）**
- **注意**：香港赛马会偶尔有非周二/四/六的特殊开期（如 2026-02-15、2026-05-10、2026-06-14、2026-06-28、2026-07-05），属正常现象，不是数据错误。

### V1.4.10 — 修复「特码与正码撞号」+ `numbers` 传字符串导致 500 (2026-11-03 18:55)
- **负责智能体**：DeepSeek
- **工作分支**：fix/deepseek/decoder-special-dup-and-type
- **起因**：审阅 V1.4.x 改动时实测发现两个真实缺陷（均非本次新引入，属历史遗留）。

- **缺陷 1 · 推荐的特码与正码重复（逻辑错误，用户可见）**
  - **现象**：
    ```
    生肖马 → 正码 [1,13,25,37,49]  特码 49   ← 49 重复
    生肖虎 → 正码 [5,17,29,41]     特码 41   ← 41 重复
    ```
  - **为什么是错的**：六合彩是**七球同机无放回**摇出，七个号码必然互不相同；
    本项目 `crawler.py` 的数据校验恰恰在检查这条规则（V1.4 遗留事项 5），
    而解码器自己却给出自相矛盾的推荐。
  - **根因**：`decode_elements()` 取 top7 后，
    `"special": top_nums[6] if len(top_nums) > 6 else sorted_candidates[-1][0]`——
    候选不足 7 个时回退到**排序最末位**的号码，而它早已被选进正码。
  - **修复**：正码取前 6 后，特码从**剩余未用号码**中取第一个；
    一个都不剩时返回 `None`（宁可不给特码，也绝不重复）。
  - **前端配套**：新增 `renderBallsRow()` 统一渲染推荐号码行，
    `special == null` 时显示「候选号码不足 7 个，暂无特码推荐」，
    不再画出 `+ null` 这种球（原实现两处渲染点都是无条件 `createBall(rec.special, true)`）。
    新增 `.no-special` 样式。

- **缺陷 2 · `/api/decoder/decode` 传字符串数字直接 500**
  - **现象**：`{"numbers": ["8"]}` → `TypeError: '<=' not supported between instances of 'int' and 'str'`（HTTP 500）；
    `{"numbers": [8]}` 正常。
  - **影响面**：AI 识图路径不受影响（`vision._numbers_in()` 已转 int），
    但 `decode_elements` 是对外 API，前端或第三方直接调用会炸。
    V1.4.8 新增的 `numbers` / `count_numbers` 两个维度使这个入口更容易被触达。
  - **修复**：新增 `_iter_numbers()` 统一收敛：接受 int / float（仅整数值）/ 字符串（含前后空格、
    `"8.0"`、`"1e1"`）/ 裸标量；越界（<1 或 >49）、`bool`、非数字文本、`None`、容器元素一律**跳过而不抛异常**。
    两处消费点改为 `for n in _iter_numbers(...)`，并移除原先就地做的范围判断。

- **验证**：
  - **缺陷 1**：8 组常见选择组合 + 12 生肖 + 3 色波共 **26 项断言全过**，撞号 0 组；
    「虎+红波」这类候选充足的场景特码仍正常给出（7，且不在正码内）✅
  - **缺陷 2**：`_iter_numbers()` **24 项边界用例全过**（含 `[8.0]`→8、`[8.5]`→忽略、`[True]`→忽略、`[0]/[50]/-1`→忽略）；
    字符串与整数入参结果**逐值一致**；真实 HTTP 复测原 500 请求现返回 **200** ✅
  - **前端**（Playwright）：生肖马/生肖虎显示「暂无特码推荐」且无 `null` 球；
    虎+红波/绿波/东方位正常显示 `+ 特码`，推荐行号码**去重后数量与球数一致**（无重复）✅
  - **回归**：10 个端点全部 200；Python + Node 语法检查通过；
    回测同 seed 两次结果**逐值一致**（未影响可复现性）✅

- **遗留注意事项 / 给下一位 Agent 的说明**：
  1. **`recommended.special` 现在可能是 `null`**，任何消费该字段的代码（前端/新接口）
     都必须容忍 `None`，不要再假设它一定是数字。前端请复用 `renderBallsRow()`。
  2. **未修复（已知，待用户拍板）**：解码器仍是**加权求和**而非**求交集**，
     即「生肖虎 + 红波」会推荐出非红波的 5、17、41（它们只是生肖权重高）。
     改成「交集优先、不足再补位」会改变现有出号逻辑，且与 V1.4.8 的
     「维度护栏」存在交互，**需先确认口径再动**。
  3. `_iter_numbers()` 是纯函数，改动号码线索解析逻辑时请一并跑它的边界用例。

---

### V1.5 — 打包为 Windows 可执行程序（可分享给他人） (2026-11-03 22:00)
- **负责智能体**：DeepSeek
- **工作分支**：feature/deepseek/windows-exe-packaging
- **起因（用户需求）**：「能不能变成 .exe，不然怎么分享给别人」
- **交付形态**：**文件夹版（onedir）**，不是单文件。
  - 理由：启动快（约 2 秒 vs 单文件 5~15 秒）、杀软误报明显更少。
  - 产物：`dist/六合彩分析工具/`（102 MB）+ `dist/六合彩分析工具.zip`（51 MB）
  - 对方解压后双击 `六合彩分析工具.exe`，自动起服务并打开浏览器。

- **核心技术问题：exe 目录只读**
  - 打包后程序所在目录不可写，而数据库与 `settings.json` 必须可写
    （用户要「同步最新数据」、要改 API Key）。
  - 新增 `paths.py` 统一解析两类路径：
    - `resource_path()` → 只读资源（templates / static / 包内初始数据）
    - `user_data_path()` → 可写数据（`%APPDATA%\LotteryAnalyzer`）
    - `exe_dir()` → exe 同级目录（放"给用户看的" data/）
  - **源码运行时两者都指向项目目录**，开发习惯不受影响（实测确认）。
  - 首次运行 `ensure_user_data()` 把初始数据复制到用户目录；
    seed 查找顺序：**exe 同级 data/ 优先**，包内次之——
    这样用户可以直接编辑 exe 旁边那份配置。

- **改动文件**：
  - `paths.py`（新增）：路径解析 + 首次运行数据播种
  - `build_exe.py`（新增）：打包脚本，`--no-key` 可打安全版
  - `app.py`：Flask 显式指定 `template_folder`/`static_folder`（打包后必须）；
    启动块重写——打包时不启用 debug/reloader（reloader 会 fork 成两个进程抢端口），
    自动延迟 1.5 秒打开浏览器，启动时打印数据目录与播种结果
  - `database.py` / `settings.py`：路径改走 `paths.py`
  - `decoder.py`：删除死代码 `MAPPINGS_PATH`（该文件从未存在过）
  - `templates/index.html` + `main.js` + `style.css`：新增「分享版 Key」提示条
  - `.gitignore`：补 `data/SHARED_BUILD`、`*.spec`

- **打包体积优化（重要）**：
  - 首次打包**误用 `--collect-submodules=pandas/numpy`**，把
    `pandas.tests.*` 上千个测试模块拖进来；本机又装了 torch / transformers /
    playwright，PyInstaller 顺着依赖图全打了进去，构建卡在 20 万行日志。
  - 修正：去掉 `--collect-submodules`，改为显式 `--exclude-module` 排除
    torch / transformers / playwright / scipy / matplotlib / bokeh / panel /
    openpyxl / lxml / PIL / numpy.tests / pandas.tests 等。
  - 结果：构建时间 74 秒，体积 **102 MB**（未优化前会到 GB 级）。
  - **验证过排除是安全的**：用 `builtins.__import__` 钩子模拟"这些包都不存在"，
    全部模块仍可导入且 `get_dashboard_data()` 正常。

- **分享版 API Key 的处理（用户明确要求带上）**：
  - 用户要求预置自己的 Key，让收到的人开箱即用识图；已知悉风险
    （对方可明文看到、会消耗分享者额度），并会通过"超额停 Key + 给授权者换新 Key"管控。
  - 实现：打包时把当前 `data/settings.json` 写入 `dist/.../data/settings.json`，
    并写一个 `SHARED_BUILD` 标记文件。
  - 设置页据此显示醒目提示：「当前使用的是分享者提供的 API Key，额度由分享者承担」，
    **用户保存过一次自己的配置后标记被删除，提示不再出现**。
  - `build_exe.py --no-key` 可打出不含 Key 的安全版。

- **自测验证（全部在真实 exe 上做，不是源码）**：
  - **首次运行**（先删干净 `%APPDATA%\LotteryAnalyzer`）：
    自动生成 `lottery.db` / `settings.json` / `SHARED_BUILD` 三个文件 ✅
  - **配置传递**：`base_url`、`model`、Key（脱敏显示末 4 位）全部正确带入，
    `borrowed_key=True` ✅
  - **10 个端点**全部 HTTP 200；数据 4404 期、最新 2026116 ✅
  - **前端**（Playwright）：13 张图正常渲染、分享版提示条可见、
    数据管理卡片显示正确、**控制台零报错** ✅
  - **使用者换自己的 Key**：保存后 `borrowed_key` 变 `False`，提示条消失 ✅
  - **点「同步最新数据」**：真实网络请求成功（inserted=0，数据本就是最新）✅
  - **AI 三阶段测试**：接口连通 ✓ / 文本对话 ✓ / 图片对话 ✓，模型 `qwen3-vl-plus` ✅
  - **完整交付链路**：把 zip 解压到临时目录再运行，配置与数据均正常 ✅
  - **源码模式回归**：`py_compile` 与 `node --check` 通过，路径仍指向项目 data/ ✅

- **遗留注意事项 / 给下一位 Agent 的说明**：
  1. **打包命令就是 `python build_exe.py`**，产物在 `dist/`，已被 gitignore。
     `dist/`、`build/`、`*.spec` 都不要提交。
  2. **不要给打包命令加 `--collect-submodules=pandas` / `numpy`**，
     会把测试套件全拖进来（见上文体积优化）。当前 `build_exe.py` 的排除清单
     是按本机环境调的，换机器打包前先确认没有新增的大包被误收。
  3. **`paths.py` 是打包正确性的关键**：新增任何需要读写的文件时，
     只读资源用 `resource_path()`，可写数据用 `user_data_path()`，
     不要再用 `os.path.dirname(__file__)`。
  4. **`recommended.special` 可能为 `None`**（见 V1.4.10），前端已用
     `renderBallsRow()` 兼容；打包不改变这一点。
  5. **exe 内嵌了分享者的 API Key**，这是用户明确要求并知情的选择。
     若日后要公开发布，务必改用 `python build_exe.py --no-key`。
  6. 杀软误报：本次产物未触发 Defender；若对方反馈"打不开/被删"，
     优先怀疑杀软隔离，让用户加白名单，而不是怀疑程序本身。
  7. 端口固定 5000，可用环境变量 `LOTTERY_PORT` 覆盖。

---

### V1.5.1 — 独立窗口模式：双击即出原生窗口，无控制台黑框 (2026-11-03 22:45)
- **负责智能体**：DeepSeek
- **工作分支**：feature/deepseek/standalone-window
- **起因（用户反馈）**：「这个软件不能自己独立开是吗？能不能改成独立开的」
  - 现象：双击 exe 后弹出一个**带地址栏和标签页的浏览器窗口**，背后还挂着一个**黑色控制台**，
    观感不像独立软件。用户同时确认了关心点：「还要依赖 Python 是吗？电脑没装 Python 就打不开？」

- **先回答「是否依赖 Python」——不依赖，并做了实测**：
  - exe 内已内嵌 Python 运行时：`python313.dll`(5.8MB)、`python3.dll`、
    `base_library.zip`(1.3MB 标准库)、`VCRUNTIME140.dll` 等。
  - **实测方法**：把 `PATH` 压到只剩 `C:\Windows\system32;C:\Windows`，
    并清空 `PYTHONHOME`/`PYTHONPATH`（此时 `python` 命令完全不可用），再运行 exe：
    数据、配置、界面全部正常。
  - 这就是分发包有 102MB 的原因——整个 Python 运行时都在里面。

- **独立窗口的实现**：
  - 新增 `window.py`：用 Chromium 系的 `--app=<url>` 模式启动 Edge/Chrome。
    该模式**没有地址栏、没有标签页、没有书签栏**，外观就是一个独立应用窗口。
  - **不打包 Chromium**：那会让包从 102MB 涨到 250-400MB。Win10/11 自带 Edge，
    实测覆盖目标机器，代价几乎为零。
  - `--user-data-dir` 指向 `%APPDATA%\LotteryAnalyzer\browser_profile`：
    用**独立 profile**，避免与用户日常浏览器会话混在一起导致窗口行为不可控。
  - **关窗即退出**：`--app` 模式没有窗口关闭回调，用轮询浏览器进程是否存活来判断，
    进程退出即调用 `os._exit(0)` 结束程序并释放端口。
  - **找不到浏览器时回退**：`find_browser()` 返回空则改用系统默认浏览器打开，
    功能不受影响。**绝不因为找不到 Edge 就让程序打不开。**

- **去掉控制台黑框**：
  - 打包参数 `--console` → `--windowed`。
  - 代价是看不到 `print`，因此 `app.py` 新增 `_setup_logging()`：
    把 stdout/stderr 重定向到 `%APPDATA%\LotteryAnalyzer\startup.log`（每次启动覆盖）。
    **无控制台时 `sys.stdout` 可能是 `None`，直接 print 会抛异常导致静默退出**，这里统一兜住。
  - 致命错误（如端口被占用、服务启动超时）改用系统弹窗 `MessageBoxW` 告知，
    不再依赖控制台输出。

- **改动文件**：
  - `window.py`（新增）：浏览器探测、独立窗口启动、关窗监听、回退逻辑
  - `app.py`：`_setup_logging()` / `_shutdown()`；启动流程改为
    「等服务就绪 → 开独立窗口 → 关窗即退出」，失败则回退默认浏览器
  - `build_exe.py`：`--console` → `--windowed`

- **自测验证（全部在真实 exe 上，且在无 Python 环境下）**：
  - **无 Python 环境**：`PATH` 清空后 exe 正常运行，数据/配置/界面全部正常 ✅
  - **无控制台**：`AttachConsole` 检测该进程无关联控制台窗口 ✅
  - **独立窗口**：窗口 1297×817，**非客户区仅 7px**（普通 Edge 窗口因有标签栏+地址栏
    通常在 130px 以上），菜单句柄为 0 → 确认为无边框应用窗口 ✅
  - **profile 隔离**：`browser_profile` 目录内 Preferences 只出现 `127.0.0.1`，
    无任何外部网址，证明未复用用户浏览器会话 ✅
  - **关窗即退出**：关闭窗口后程序在数秒内自行退出，端口 5000 释放 ✅
  - **回退逻辑**：模拟找不到浏览器，`find_browser()` 返回 `(None, None)`，
    调用方正确回退到默认浏览器 ✅
  - **界面回归**：13 张图渲染、6 个标签页可切换、分享版 Key 提示可见、
    图猜码解码正常且无 null 球、**控制台零报错** ✅
  - **源码模式未受影响**：仍是控制台 + debug，且**不会**误开独立窗口（实测 0 个 --app 进程）✅

- **遗留注意事项 / 给下一位 Agent 的说明**：
  1. **打包版没有控制台，排错一律看 `%APPDATA%\LotteryAnalyzer\startup.log`**。
     用户报"打不开"时，先让他把这个文件发来。
  2. **独立窗口依赖系统 Edge/Chrome**。若目标机器两者都没有（如精简版 Win7），
     程序会回退到默认浏览器，功能正常但观感退回旧样式。要彻底摆脱浏览器依赖
     只能打包 Chromium（体积代价 250-400MB），当前认为不划算。
  3. **不要改回 `--console`**：那会重新引入黑框；若确实需要调试输出，
     用环境变量或临时改 `_setup_logging()`，不要把 `--windowed` 去掉。
  4. `browser_profile` 目录会随使用增长（缓存），用户数据目录里看到它属正常现象；
     删除它不影响数据，下次启动会自动重建。
  5. 关窗检测是**轮询进程存活**（1 秒间隔）。如果未来 Edge 改变了 `--app` 的进程模型
     （例如把窗口合并进已有进程而不新开进程），这个检测可能失效，
     届时需要改用窗口句柄监听。

---

## 四、待开发 (Backlog)

### P2 — 下一批迭代
- [x] **真实历史数据爬虫**：三源接入 1993 年至今 4404 期官方开奖，替换模拟数据（V1.4 完成；增量源 V1.4.4 改为 Renavon 首选 + marksix-rd 兜底）
- [x] **动态生肖映射表**：按农历年份的生肖↔号码对应（V1.4.1 完成，口径：当年生肖=1，农历正月初一换表）
- [x] **历史命中率回测**：各策略的历史"命中"表现统计（V1.2 完成）
- [x] **AI 解读玄机图**：AI 识别图片元素→映射→出号（V1.1 实现，V1.3 改为用户自配置接口；原"AI 生成每日玄机图"需求由用户确认为解读方向，不再做生图）
- [ ] **移动端适配**：响应式布局优化（用户确认延后，随 P3 一并考虑）

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
pip install openai               # AI 识图（可选，需自备接口）
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
       ──→ vision.py     (AI 视觉，依赖 decoder + settings)
       ──→ settings.py   (AI 配置读写，独立)
```

### AI 视觉模块注意事项（V1.3 起）
- **不再依赖任何外部脚本或第三方内置密钥**。接口地址 / API Key / 模型名全部由用户在「⚙️ 设置」页填写。
- 配置存放于 `data/settings.json`（含明文 Key，已 gitignore）。**不要提交、不要打包、不要分享该文件。**
- 必须使用**支持图片输入**的模型，纯文本模型无法识图。
- 未配置时：图猜码禁用上传并引导去设置，**手动选元素解码不受影响**。
- 排错顺序：设置页「🔌 测试连接」→ 看返回的中文提示（已覆盖 401/403/404/429/超时/连不上）。
- **遇到 `sensitive_words_detected`（"图片包含敏感内容"）**：这是**服务商审核网关按请求文本**误判，与图片内容无关（详见 V1.4.3）。对策：稍后重试、换模型（`qwen3-vl-plus` / `qwen3.6-plus` 可用，`qwen3.7-max` 不支持 `image_url` 格式），不要随意改写内置识图提示词（改了反而可能触发审核）。
- 识图提示词 `VISION_SYSTEM_PROMPT` / `VISION_USER_PROMPT` 被「测试连接」第③步与真实识图**共用**，改一处即可同时生效，不要另写探测提示词。
- 「测试连接」第③步的探测图是 **64×64**（`_PROBE_PNG`），不要改回 1×1 —— 部分视觉模型要求宽高 > 10px，否则会被误报成「不支持看图」。
