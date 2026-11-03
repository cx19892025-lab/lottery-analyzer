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
  2. **生肖映射是静态表（已知大坑，下版本处理）**：真实六合彩每年生肖↔号码对应随农历年变化，`decoder.py` 目前是静态映射，接入真实数据后「图猜码」的生肖推导会失准。五行/色波/方位映射不受影响。建议下版本做「按开奖年份的动态生肖表」（每年以冬至/立春为界有不同派别，需先与用户确认口径）。
  3. `get_all_results()` 现在返回**缓存列表的切片/引用**，调用方不得原地修改返回的 dict，否则会污染缓存（当前所有调用方均只读）。
  4. 回测耗时随库内期数增长（每期分析要扫全部历史），200 期 14.6s 可接受；若用户跑全量 4300+ 期回测预计需数分钟，属预期行为。
  5. 特码与正码可能同号在模拟数据中出现过，真实数据中七球互异——校验规则以此为准，若未来数据源违反该规则会被跳过并报告。

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

---

## 四、待开发 (Backlog)

### P2 — 下一批迭代
- [x] **真实历史数据爬虫**：双源接入 1993 年至今 4393 期官方开奖，替换模拟数据（V1.4 完成；增量恢复方案见 V1.4 遗留事项 1）
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
