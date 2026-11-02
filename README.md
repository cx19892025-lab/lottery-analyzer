# 🎰 六合彩数据分析工具 (Lottery Analyzer)

> ⚠️ **免责声明**：本工具仅供数据分析学习与娱乐参考，不构成任何投注建议。彩票开奖为独立随机事件，历史数据不代表未来结果。

## 功能概览

| 模块 | 说明 |
|---|---|
| 📊 数据仪表盘 | 号码频率、热力图、冷热号、遗漏值、奇偶比、大小比、和值、尾数、连号等 10+ 项统计 |
| 📋 开奖记录 | 带色波彩球的历史开奖数据展示 |
| 🎲 智能选号 | 均衡 / 热号优先 / 冷号博回 / 纯随机 四种策略推荐 |
| 🖼️ 图猜码解码器 | 上传玄机图 → AI 视觉识别 → 多维交叉推导 → 自动出号 |

## 技术栈

- **后端**：Python 3 + Flask
- **数据分析**：pandas + numpy
- **数据库**：SQLite（零配置）
- **前端**：HTML + CSS + JavaScript + ECharts
- **AI 视觉**：Kaggle Gemini 3.7 Flash（免费额度）

## 快速开始

```bash
# 1. 安装依赖
pip install flask pandas numpy

# 2. 启动服务
cd lottery-analyzer
python app.py

# 3. 浏览器打开
# http://localhost:5000
```

首次启动会自动生成 300 期模拟数据。

## 项目结构

```
lottery-analyzer/
├── app.py              # Flask 主应用 + API 路由
├── database.py         # SQLite 数据层 + 模拟数据生成
├── analyzer.py         # 统计分析引擎（10项分析）
├── decoder.py          # 图猜码解码引擎（生肖/五行/色波/方位映射）
├── vision.py           # AI 视觉识别模块（Kaggle Gemini）
├── requirements.txt    # Python 依赖
├── data/               # 运行时数据库（git ignored）
├── static/
│   ├── css/style.css   # 暗色主题样式
│   └── js/
│       ├── main.js     # 前端交互逻辑 + ECharts 图表
│       └── echarts.min.js  # ECharts 本地副本
├── templates/
│   └── index.html      # 单页应用模板
├── DEVLOG.md           # 设计日志与迭代记录
└── README.md           # 本文件
```

## API 接口

| 路由 | 方法 | 说明 |
|---|---|---|
| `/api/dashboard` | GET | 仪表盘全量数据 |
| `/api/history?limit=50` | GET | 历史开奖记录 |
| `/api/frequency` | GET | 号码频率 |
| `/api/hot_cold?recent=30` | GET | 冷热号 |
| `/api/missing` | GET | 遗漏值 |
| `/api/recommend?strategy=balanced` | GET | 智能选号 |
| `/api/decoder/categories` | GET | 解码分类 |
| `/api/decoder/decode` | POST | 元素解码 |
| `/api/decoder/vision` | POST | AI 图片解码 |
| `/api/vision/status` | GET | AI 功能状态 |

## 协作指南

本项目使用 Git 管理，并引入了严密的**多智能体协作守则**。其他 Agent 协作时请遵守：

1. **阅读准则**：开发前**必须**通读 [`AGENT_COLLABORATION_RULES.md`](./AGENT_COLLABORATION_RULES.md) 和 [`DEVLOG.md`](./DEVLOG.md)
2. **分支管理**：新特性开发必须开辟分支 `feature/<agent_name>/<task>`，禁止直接污染 `main`
3. **改动留痕**：完成编码后必须在 `DEVLOG.md` 按照标准模板登记改动说明
4. **提交规范**：严格遵循 Conventional Commits（`feat:`, `fix:`, `docs:`, 等）
5. **分支清理**：合并回 `main` 后立即清理临时分支，保持分支树整洁

## License

个人学习项目，仅供参考。
