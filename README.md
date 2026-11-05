# 🎰 六合彩数据分析工具 (Lottery Analyzer)

> ⚠️ **免责声明**
> 本工具仅供数据分析学习与娱乐参考，**不构成任何投注建议**。
> 彩票开奖为独立随机事件，历史数据不代表未来结果。
> 本项目在文档与代码中**明确记录了"追冷号/追热号"等策略经回测证明无优势**，
> 请勿将其用于任何实际投注决策。

一个用于分析香港六合彩（Mark Six）历史开奖数据的本地工具。
数据来自公开数据集（1993 年至今，4400+ 期），全部统计在**本机**完成，不上传任何数据。

---

## ✨ 功能概览

| 模块 | 说明 |
|---|---|
| 📊 **数据仪表盘** | 号码频率、热力图、冷热号、遗漏值；**特码**与**正码**分开成区 |
| 🎯 **单号跟踪** | 选一个号码，看它遗漏多久、续期概率曲线、25 年年度分布 |
| 📋 **开奖记录** | 带色波彩球的历史开奖数据展示 |
| 🎲 **智能选号** | 六种策略 + 号码/生肖「连续不出」实时榜单 + 追冷号验证 |
| 📈 **策略回测** | 六种策略的历史命中率回测（**无未来数据泄露**） |
| 🖼️ **图猜码** | 上传玄机图 → AI 视觉识别 → 多维交叉推导 → 出号 |
| ⚙️ **设置** | AI 接口配置、数据同步/导入、数据新鲜度检查 |

### 统计口径说明

- **统计基数**：1993~2002 年 7 月前的数据源缺失 48/49 号，
  因此统计类功能默认排除该区间，实际使用 **3393 期**（全库 4404 期）。
- **统计窗口**：仪表盘可切换近 100/300/500/1000 期或全部，
  每张卡片标题右侧都标注了当前口径。
- **生肖**：按**农历年**轮换，每期使用该期开奖日期对应的生肖表。

---

## 🛠 技术栈

- **后端**：Python 3.10+ / Flask
- **数据分析**：pandas + numpy
- **数据库**：SQLite（零配置，单文件）
- **前端**：原生 HTML + CSS + JavaScript + ECharts 5（本地副本，无需 CDN）
- **AI 视觉**：**用户自配置**的 OpenAI 兼容接口（不再依赖任何第三方内置密钥）

---

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动
python app.py

# 3. 浏览器打开
# http://localhost:5000
```

首次启动会自动建库。**数据库默认为空**，需要抓取历史数据：

- 界面「⚙️ 设置 → 🗄️ 数据管理 → 📥 导入真实历史数据」
- 或命令行：`python crawler.py`

### 配置 AI 识图（可选）

「图猜码」的 AI 识别功能需要**你自己的**接口：

1. 打开「⚙️ 设置」
2. 填写 **接口地址 / API Key / 模型名**
3. 点「🔌 测试连接」验证

- 必须使用**支持图片输入**的模型（纯文本模型无法识图）
- 未配置时：图猜码禁用上传，但**手动选元素解码不受影响**
- 配置保存在 `data/settings.json`（含明文 Key，**已 gitignore，请勿分享**）

---

## 📁 项目结构

```
lottery-analyzer/
├── app.py                  # Flask 主应用 + API 路由
├── database.py             # SQLite 数据层（含统计口径过滤）
├── analyzer.py             # 统计分析引擎
├── backtest.py             # 策略回测（无未来数据泄露）
├── crawler.py              # 三源爬虫 + 增量同步 + 数据新鲜度检查
├── decoder.py              # 图猜码解码引擎（生肖/五行/色波映射）
├── vision.py               # AI 视觉识别
├── settings.py             # AI 配置读写
├── paths.py                # 路径解析（源码/打包双模式）
├── window.py               # 独立窗口启动器（内置 Chromium）
├── build_exe.py            # PyInstaller 打包脚本
├── requirements.txt
├── static/
│   ├── css/style.css
│   └── js/
│       ├── main.js
│       └── echarts.min.js  # ECharts 本地副本
├── templates/index.html
├── DEVLOG.md               # 📒 设计日志与迭代记录（推荐阅读）
└── README.md
```

---

## 🔌 API 接口

| 路由 | 方法 | 说明 |
|---|---|---|
| `/api/dashboard?window=500` | GET | 仪表盘全量数据 |
| `/api/history?limit=50` | GET | 历史开奖记录 |
| `/api/frequency` | GET | 号码频率 |
| `/api/hot_cold` | GET | 冷热号 |
| `/api/missing` | GET | 遗漏值 |
| `/api/main_numbers` | GET | 正码单号统计 |
| `/api/special` | GET | 特码专项统计 |
| `/api/attributes` | GET | 号码属性（生肖/波色/五行） |
| `/api/tracker?number=48` | GET | 单号跟踪（遗漏/续期概率/年度分布） |
| `/api/missing_board?top=10` | GET | 号码连续不出榜单 |
| `/api/zodiac_board?top=10` | GET | 生肖连续不出榜单（正码/特码分开） |
| `/api/cold_chase?top=5` | GET | 追冷号策略验证回测 |
| `/api/backtest?max_periods=200` | GET | 策略回测 |
| `/api/recommend?strategy=balanced` | GET | 智能选号 |
| `/api/decoder/*` | GET/POST | 图猜码解码 |
| `/api/vision/status` | GET | AI 功能状态 |
| `/api/settings` | GET/POST | AI 配置读写 |
| `/api/data/status` | GET | 数据状态 + 新鲜度检查 |
| `/api/data/sync` | POST | 增量同步最新开奖 |
| `/api/data/import` | POST | 全量导入历史数据 |

---

## 📦 打包为 Windows 可执行程序

```bash
python build_exe.py            # 含当前 API 配置
python build_exe.py --no-key   # 清空 API Key（安全版）
```

产出 `dist/六合彩分析工具/`（onedir 文件夹版），压缩后约 241 MB。
目标机器**无需安装 Python**，解压双击即可运行。

> **关于体积**：包内含一份独立的 Chromium（约 400 MB，压缩后约 190 MB），
> 用于以独立窗口打开界面。之所以自带而不是借用系统 Edge/Chrome，
> 是因为借用系统浏览器会弹出「登录以同步」引导，
> **存在影响用户账号的风险**（详见 DEVLOG V1.8）。

---

## 📒 关于本项目的诚实结论

本项目在开发过程中做了大量统计检验，结论**记录在 `DEVLOG.md` 中**，包括：

- **「追冷号」策略无效**：全历史命中率 14.37% vs 理论 14.29%，
  分段检验符号翻转（−1.44pp → +1.96pp），属噪声。
- **「追热号」同样无效**：与随机对照无显著差异。
- **单号遗漏无记忆**：续期概率曲线是一条平线（围绕 85.71%），
  「欠久了会补」不成立。
- 本工具的价值在于**数据整理与可视化**，而非预测中奖。

这些结论是刻意保留的——**一个诚实的分析工具，应该告诉你它做不到什么**。

---

## License

个人学习项目，仅供参考。
