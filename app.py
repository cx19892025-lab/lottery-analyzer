"""
六合彩数据分析工具 - Flask 主应用
提供 Web 界面 + RESTful API
"""
import base64
import os
import sys
import threading
import time
import webbrowser
from datetime import date

from flask import Flask, render_template, jsonify, request, send_file
from paths import resource_path, is_frozen, user_data_dir, ensure_user_data
from database import init_db, get_all_results, get_raw_results, get_results_count
from analyzer import (
    frequency_analysis, hot_cold_numbers, missing_values,
    main_number_stats, number_attributes, special_stats,
    number_tracker, missing_leaderboard, zodiac_missing_leaderboard,
    cold_chase_backtest, smart_recommend, get_dashboard_data
)
from backtest import run_backtest, STRATEGIES, MIN_HISTORY
from decoder import (
    get_all_categories, decode_elements, quick_decode, zodiac_of_number
)
from vision import analyze_image, map_vision_to_decoder_selections
from crawler import import_all, sync_latest, data_status, data_freshness
import settings as settings_mod

# 打包成 exe 后，模板与静态文件在 PyInstaller 的解压目录里，
# 必须显式告诉 Flask 去哪里找，否则打包后首页 500。
app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)
# 保持字典插入顺序：生肖等分布数据依赖固定顺序（鼠牛虎兔…），
# Flask 默认会按字母重排 JSON key，导致图表横轴乱序
app.json.sort_keys = False


# ==================== 页面路由 ====================

@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


# ==================== 数据 API ====================

@app.route("/api/dashboard")
def api_dashboard():
    """
    仪表盘汇总数据
    window: 统计窗口（最近 N 期），默认 500；0 表示全量。
            真实数据 4400+ 期，全量统计慢且远期参考价值低。
    """
    window = request.args.get("window", 500, type=int)
    return jsonify(get_dashboard_data(window=window or None))


@app.route("/api/history")
def api_history():
    """
    历史开奖记录。

    用 get_raw_results 而非 get_all_results：这里要展示**全部**原始记录，
    包括 1993~2002 那段 48/49 号缺失的期（统计时会排除，但列表应如实呈现）。

    V1.9.2：每条记录附带每个号码的**生肖**。
    ⚠️ 生肖表按农历年轮换，所以必须用**该期自己的开奖日期**换算，
       不能拿今天的表套历史数据（否则跨年那几期会算错）。
       实测 2026 年 1 月的开奖仍属上一生肖年。
    """
    limit = request.args.get("limit", 50, type=int)
    results = get_raw_results(limit)

    out = []
    for r in results:
        d = date.fromisoformat(r["draw_date"][:10])
        item = dict(r)
        item["zodiacs"] = [
            zodiac_of_number(int(r[f"num{i}"]), d) for i in range(1, 7)
        ]
        item["special_zodiac"] = zodiac_of_number(int(r["special"]), d)
        out.append(item)
    return jsonify(out)


@app.route("/api/frequency")
def api_frequency():
    """号码频率"""
    limit = request.args.get("limit", None, type=int)
    return jsonify(frequency_analysis(limit))


@app.route("/api/special")
def api_special():
    """
    特码专项统计（猜特码玩法，赔率最高）
    limit: 统计窗口（最近 N 期），不传表示全量。
    """
    limit = request.args.get("limit", None, type=int)
    return jsonify(special_stats(limit))


@app.route("/api/missing_board")
def api_missing_board():
    """连续不出期数实时榜单（追冷号玩法的入口）"""
    top_k = request.args.get("top", 10, type=int)
    return jsonify(missing_leaderboard(top_k))


@app.route("/api/zodiac_board")
def api_zodiac_board():
    """
    生肖连续不出榜单 —— 正码与特码分开统计。
    两者每期开出的位置数不同（6 vs 1），概率差一个数量级，必须分开看。
    """
    top_k = request.args.get("top", 10, type=int)
    return jsonify(zodiac_missing_leaderboard(top_k))


@app.route("/api/cold_chase")
def api_cold_chase():
    """
    验证「追冷号」策略：机械地每期押当前最久没出的 K 个号，看命中率。
    与理论值 14.29% 对比，供用户自己判断这个直觉靠不靠谱。
    """
    top_k = request.args.get("top", 10, type=int)
    max_periods = request.args.get("max_periods", None, type=int)
    return jsonify(cold_chase_backtest(top_k, max_periods=max_periods))


@app.route("/api/tracker")
def api_tracker():
    """
    单号跟踪：当前遗漏、续期概率曲线、未来 K 期命中概率、年度分布。
    number: 1-49；limit: 统计窗口（不传为全量）
    """
    number = request.args.get("number", 1, type=int)
    limit = request.args.get("limit", None, type=int)
    if not (1 <= number <= 49):
        return jsonify({"error": "号码必须在 1-49 之间"}), 400
    return jsonify(number_tracker(number, limit))


@app.route("/api/hot_cold")
def api_hot_cold():
    """冷热号"""
    recent_n = request.args.get("recent", 30, type=int)
    return jsonify(hot_cold_numbers(recent_n))


@app.route("/api/missing")
def api_missing():
    """遗漏值"""
    return jsonify(missing_values())


@app.route("/api/main_numbers")
def api_main_numbers():
    """正码单号统计（猜正码玩法）"""
    return jsonify(main_number_stats())


@app.route("/api/attributes")
def api_attributes():
    """号码属性表（生肖/波色/五行/奇偶/大小）"""
    return jsonify(number_attributes())


# ==================== 数据管理 API ====================

@app.route("/api/data/import", methods=["POST"])
def api_data_import():
    """
    全量导入真实历史数据（1993 年至今，多源合并去重）。
    默认清空现有数据（用于替换模拟数据）；clear=false 时仅追加不存在的期号。
    注意：涉及多个外部抓取 + 批量写库，响应需数秒。
    """
    body = request.get_json(silent=True) or {}
    clear = body.get("clear", True)
    try:
        result = import_all(clear=bool(clear))
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "error": f"导入失败：{e}",
            "hint": "请检查网络能否访问 raw.githubusercontent.com 与 renavon.com"
                    "（国内一般可直连，若失败可稍后重试或配置代理后重试）"
        }), 502


@app.route("/api/data/status")
def api_data_status():
    """
    数据状态。除库内期数外，附带 fresh 字段（新鲜度检查，纯本地计算不联网），
    供前端在顶部提示"数据可能已过时"。
    """
    st = data_status()
    try:
        st["fresh"] = data_freshness()
    except Exception as e:
        st["fresh"] = {"known": False, "error": str(e)}
    return jsonify(st)


@app.route("/api/data/sync", methods=["POST"])
def api_data_sync():
    """
    增量同步最新开奖（拉增量源，INSERT OR IGNORE 补新期号）。
    开奖一般在周二/四/六晚，Renavon 源一般当晚更新，marksix-rd 源滞后数小时。
    """
    try:
        return jsonify(sync_latest())
    except Exception as e:
        return jsonify({"error": f"同步失败：{e}"}), 502


# ==================== 智能选号 API ====================

@app.route("/api/recommend")
def api_recommend():
    """
    智能选号推荐。

    strategy 必须是 STRATEGIES 之一，否则返回 400。
    （V1.8.4 修复：此前非法策略名会被静默当作 balanced 处理，
      返回 200 且看不出参数有误，调用方无从发现自己传错了。）
    """
    strategy = request.args.get("strategy", "balanced")
    if strategy not in STRATEGIES:
        return jsonify({
            "error": f"未知策略：{strategy}",
            "valid": STRATEGIES,
        }), 400
    return jsonify(smart_recommend(strategy))


# ==================== 历史回测 API ====================

@app.route("/api/backtest")
def api_backtest():
    """
    历史命中率回测

    参数:
      strategies: 逗号分隔的策略名，默认全部（balanced,hot,cold,random）
      min_history: 前 N 期只作历史数据，默认 30
      max_periods: 最多回测期数，默认 200（限制耗时）
      recent_n: 冷热号窗口，默认 30
      seed: 随机种子，给定则结果可复现
    """
    raw = request.args.get("strategies", "")
    strategies = [s.strip() for s in raw.split(",") if s.strip()] or None
    invalid = [s for s in (strategies or []) if s not in STRATEGIES]
    if invalid:
        return jsonify({
            "error": f"未知策略: {', '.join(invalid)}",
            "available": STRATEGIES
        }), 400

    min_history = request.args.get("min_history", MIN_HISTORY, type=int)
    max_periods = request.args.get("max_periods", 200, type=int)
    recent_n = request.args.get("recent_n", 30, type=int)
    seed = request.args.get("seed", None, type=int)

    result = run_backtest(
        strategies=strategies,
        min_history=max(10, min_history),
        max_periods=max_periods,
        recent_n=recent_n,
        seed=seed,
    )
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ==================== 图猜码 API ====================

@app.route("/api/decoder/categories")
def api_decoder_categories():
    """获取解码分类"""
    return jsonify(get_all_categories())


@app.route("/api/decoder/decode", methods=["POST"])
def api_decoder_decode():
    """解码"""
    selections = request.get_json()
    result = decode_elements(selections)
    return jsonify(result)


@app.route("/api/decoder/export", methods=["POST"])
def api_decoder_export():
    """
    导出解码记录为 Word / Excel（含图）。

    请求体：{"items": [ ...解码记录... ]}，格式见 exporters.py 顶部说明。
    查询参数：format = word | excel

    前端把 800px 的存档图一并传过来，后端用 python-docx / openpyxl
    组装成文件流返回，避免浏览器端再引入几百 KB 的 Office 库。
    """
    # 注意：不能用 `request.args.get("format") or "word"`——
    # 传 ?format=（空串）时会静默回退成 word，调用方以为参数生效了。
    # 只有完全不传 format 才用默认值。
    fmt = request.args.get("format", "word").lower()
    if fmt not in ("word", "excel"):
        return jsonify({"error": f"不支持的导出格式：{fmt}（可选 word / excel）"}), 400

    body = request.get_json(silent=True) or {}
    items = body.get("items")
    if not isinstance(items, list) or not items:
        return jsonify({"error": "没有可导出的记录"}), 400

    # 防止误传超大数组把内存打爆（正常最多 50 条）
    if len(items) > 500:
        return jsonify({"error": f"一次最多导出 500 条，当前 {len(items)} 条"}), 400

    try:
        import exporters
        if fmt == "word":
            buf = exporters.build_word(items)
            mime = ("application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document")
            ext = "docx"
        else:
            buf = exporters.build_excel(items)
            mime = ("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet")
            ext = "xlsx"
    except ImportError as e:
        return jsonify({
            "error": f"缺少导出依赖：{e}",
            "hint": "请执行 pip install python-docx openpyxl",
        }), 500
    except Exception as e:
        return jsonify({"error": f"生成文件失败：{e}"}), 500

    stamp = time.strftime("%Y%m%d")
    filename = f"decode_records_{stamp}.{ext}"
    return send_file(
        buf,
        mimetype=mime,
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/decoder/quick")
def api_decoder_quick():
    """快速解码"""
    keyword = request.args.get("keyword", "")
    return jsonify(quick_decode(keyword))


@app.route("/api/decoder/vision", methods=["POST"])
def api_decoder_vision():
    """AI 视觉识别解码 - 上传图片自动分析"""
    if not settings_mod.is_configured():
        return jsonify({
            "error": "尚未配置 AI 接口，请先到「设置」页填写接口地址与模型名"
        }), 503

    data = request.get_json()
    image_b64 = data.get("image", "")
    mime_type = data.get("mime_type", "image/png")

    if not image_b64:
        return jsonify({"error": "未收到图片数据"}), 400

    # 去除 data:image/... 前缀
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]

    # 1. AI 识别图片元素
    vision_result = analyze_image(image_b64, mime_type)

    # AI 调用失败时直接回传原因，前端展示可读提示
    if vision_result.get("error"):
        return jsonify({"error": vision_result["error"], "vision": vision_result}), 502

    # 2. 映射为解码器格式
    selections = map_vision_to_decoder_selections(vision_result)

    # 3. 用解码器推导号码
    decode_result = decode_elements(selections)

    return jsonify({
        "vision": vision_result,
        "selections": selections,
        "decode": decode_result
    })


@app.route("/api/vision/status")
def api_vision_status():
    """检查 AI 视觉功能是否可用"""
    s = settings_mod.load_settings()
    return jsonify({
        "available": settings_mod.is_configured(s),
        "base_url": s["base_url"],
        "model": s["model"],
        "has_api_key": bool(s["api_key"]),
    })


# ==================== 设置 API ====================

@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    """读取 AI 配置（API Key 一律脱敏返回）"""
    return jsonify(settings_mod.public_settings())


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    """
    保存 AI 配置
    api_key 留空表示保持原值不变（前端不回显 Key，避免误清空）
    """
    data = request.get_json(silent=True) or {}
    settings_mod.save_settings(data)
    return jsonify({"ok": True, "settings": settings_mod.public_settings()})


def _trial_config(data):
    """把请求里的临时值合并到已存配置上，便于「未保存先测试」"""
    trial = dict(settings_mod.load_settings())
    for k in ("base_url", "model"):
        if data.get(k):
            trial[k] = str(data[k]).strip()
    if data.get("api_key"):
        trial["api_key"] = str(data["api_key"]).strip()
    return trial


def _build_trial_client(trial):
    """按试运行配置构造 OpenAI 兼容客户端"""
    from openai import OpenAI
    return OpenAI(
        api_key=trial["api_key"] or "not-needed",
        base_url=trial["base_url"].rstrip("/"),
        timeout=trial.get("timeout", 60),
    )

# 64x64 白色 PNG，用来验证接口是否真的支持图片输入。
# 不能用 1x1 图：部分视觉模型（如 qwen3-vl-plus）要求宽高都 > 10px，
# 否则会报 invalid_parameter_error，被误判成「模型不支持看图」。
_PROBE_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAfElEQVR4nNXO"
              "QREAIADDsFL/nocIHlyjIGcbZRIncRIncRIncRIncRIncRIncRIncRIncRIncRIncRInc"
              "RIncRIncRIncRIncRIncRIncRIncRIncRIncRIncRIncRIncRIncRIncRIncRIncRIncR"
              "IncRIncRIncf4OvLpyqgN9ZSiDcwAAAABJRU5ErkJggg==")


@app.route("/api/settings/models", methods=["POST"])
def api_settings_models():
    """
    读取该接口上可用的模型列表。
    很多中转站的模型名与官方并不一致，让用户手填很容易填错，
    这里直接把 /v1/models 拉回来给他挑。
    """
    data = request.get_json(silent=True) or {}
    trial = _trial_config(data)

    if not trial["base_url"]:
        return jsonify({"ok": False, "error": "请先填写接口地址"}), 400

    try:
        client = _build_trial_client(trial)
        models = client.models.list()
        ids = sorted({m.id for m in models if getattr(m, "id", None)})
        return jsonify({"ok": True, "models": ids, "count": len(ids)})
    except Exception as e:
        from vision import _friendly_error
        msg = _friendly_error(e)
        # 有些中转站不实现 /models，这不算配置错误，提示换成手动填写即可
        if "404" in str(e) or "not found" in str(e).lower():
            msg = "该接口没有提供 /models 列表接口，请手动填写模型名。" + msg
        return jsonify({"ok": False, "error": msg}), 502


@app.route("/api/settings/test", methods=["POST"])
def api_settings_test():
    """
    分阶段诊断 AI 连接，逐步定位问题出在哪一层：
      ① 模型列表  —— 验证地址与 Key 是否有效（部分接口无此能力，跳过不算失败）
      ② 文本对话  —— 验证模型名是否真实可用
      ③ 图片对话  —— 验证该模型是否支持看图（图猜码的硬性前提）
    只需返回整体结论，同时把每一阶段的结果带上，便于用户判断该改哪一项。
    """
    data = request.get_json(silent=True) or {}
    trial = _trial_config(data)

    if not trial["base_url"] or not trial["model"]:
        return jsonify({"ok": False, "error": "请先填写接口地址与模型名"}), 400

    try:
        from vision import _friendly_error
        client = _build_trial_client(trial)
    except ImportError:
        return jsonify({"ok": False, "error": "缺少 openai 依赖，请执行：pip install openai"}), 500

    stages = []

    # ① 模型列表
    try:
        models = client.models.list()
        ids = sorted({m.id for m in models if getattr(m, "id", None)})
        hit = trial["model"] in ids
        stages.append({
            "name": "接口连通 / Key 校验",
            "ok": True,
            "detail": f"读取到 {len(ids)} 个模型" + ("，模型名在列表中 ✓" if hit else "，但未找到你填的模型名"),
            "models": ids[:60],
            "model_found": hit,
        })
    except Exception as e:
        msg = str(e)
        if "404" in msg or "not found" in msg.lower():
            stages.append({"name": "接口连通 / Key 校验", "ok": None,
                           "detail": "该接口不提供 /models，跳过此项（不代表配置有错）"})
        else:
            stages.append({"name": "接口连通 / Key 校验", "ok": False,
                           "detail": _friendly_error(e)})

    # ② 文本对话
    text_ok = False
    try:
        resp = client.chat.completions.create(
            model=trial["model"],
            messages=[{"role": "user", "content": "回复两个字：可用"}],
            max_tokens=16,
        )
        reply = (resp.choices[0].message.content or "").strip()
        text_ok = True
        stages.append({"name": "文本对话", "ok": True, "detail": f"模型已响应：{reply[:40]}"})
    except Exception as e:
        stages.append({"name": "文本对话", "ok": False, "detail": _friendly_error(e)})

    # ③ 图片对话（图猜码的前提）
    # 必须复用真实识图所用的提示词：服务商侧的内容审核对措辞极其敏感，
    # 另写一套探测提示词会出现「探测失败但实际识图可用」的假阴性
    if text_ok:
        try:
            from vision import VISION_SYSTEM_PROMPT, VISION_USER_PROMPT
            resp = client.chat.completions.create(
                model=trial["model"],
                messages=[
                    {"role": "system", "content": VISION_SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{_PROBE_PNG}"}},
                        {"type": "text", "text": VISION_USER_PROMPT},
                    ]},
                ],
                max_tokens=512,
            )
            reply = (resp.choices[0].message.content or "").strip()
            if not reply:
                reply = (getattr(resp.choices[0].message, "reasoning_content", "") or "").strip()
            stages.append({"name": "图片对话（识图必需）", "ok": True,
                           "detail": f"该模型支持看图，已响应：{reply[:40]}"})
        except Exception as e:
            m = str(e)
            low_m = m.lower()
            if ("does not support image" in low_m or "image" in low_m
                    or "vision" in low_m or "multimodal" in low_m):
                detail = ("该模型不支持图片输入，图猜码将无法识图。"
                          "请换用支持视觉的模型（如 qwen-vl-max、glm-4v-flash）。")
            else:
                detail = "图片对话失败：" + _friendly_error(e)
            stages.append({"name": "图片对话（识图必需）", "ok": False, "detail": detail})
    else:
        stages.append({"name": "图片对话（识图必需）", "ok": None,
                       "detail": "文本对话未通过，跳过图片测试"})

    all_ok = all(s["ok"] is not False for s in stages)
    vision_ok = any(s["name"].startswith("图片对话") and s["ok"] is True for s in stages)

    result = {
        "ok": all_ok and vision_ok,
        "stages": stages,
        "model": trial["model"],
    }
    if result["ok"]:
        result["message"] = "连接成功，且该模型支持看图，图猜码可以正常使用。"
    elif all_ok and not vision_ok:
        result["error"] = "接口与模型都正常，但该模型不支持图片输入，图猜码需要换成支持视觉的模型。"
    else:
        failed = [s for s in stages if s["ok"] is False]
        result["error"] = failed[0]["detail"] if failed else "连接失败"

    return jsonify(result), (200 if result["ok"] else 502)


# ==================== 启动 ====================

HOST = "127.0.0.1"
PORT = int(os.environ.get("LOTTERY_PORT", "5000"))

# 打包后隐藏控制台：所有 print 落到日志文件，出问题时可回查
_LOG_FILE = None


def _setup_logging():
    """
    打包运行时把 stdout/stderr 重定向到日志文件。

    打包版用 --windowed 启动（无控制台），此时 sys.stdout 可能是 None，
    直接 print 会抛异常导致程序静默退出。这里统一兜住。
    日志位置：用户数据目录/startup.log
    """
    global _LOG_FILE
    try:
        log_path = os.path.join(user_data_dir(), "startup.log")
        os.makedirs(user_data_dir(), exist_ok=True)
        # 每次启动覆盖，避免无限增长
        _LOG_FILE = open(log_path, "w", encoding="utf-8", errors="replace")
        sys.stdout = _LOG_FILE
        sys.stderr = _LOG_FILE
    except Exception:
        # 日志写不了也不能让程序起不来
        if sys.stdout is None:
            import io
            sys.stdout = io.StringIO()
        if sys.stderr is None:
            sys.stderr = io.StringIO()


def _shutdown(server=None):
    """关窗即退出：直接终止进程，避免 Flask 线程残留导致端口占用"""
    try:
        if _LOG_FILE:
            _LOG_FILE.flush()
    except Exception:
        pass
    os._exit(0)


def main():
    """
    启动入口。

    打包成 exe 后：
      - 不开 debug（reloader 会把进程 fork 成两份，导致端口冲突）
      - 用 Edge/Chrome 的 --app 模式开**独立窗口**，没有地址栏与标签页
      - 关掉窗口即退出整个程序
      - 找不到浏览器时回退到系统默认浏览器，功能不受影响
    """
    frozen = is_frozen()
    if frozen:
        _setup_logging()
    elif sys.stdout is not None and hasattr(sys.stdout, "buffer"):
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    init_db()
    url = f"http://{HOST}:{PORT}"

    print("=" * 58)
    print("  六合彩数据分析工具")
    print("=" * 58)
    print(f"  界面地址：{url}")
    print(f"  数据目录：{user_data_dir()}")
    if frozen:
        print("  （数据库与 API 配置都保存在上面的目录里）")
        seeded = ensure_user_data("lottery.db", "settings.json", "SHARED_BUILD")
        for name, state in seeded.items():
            if state == "copied":
                print(f"    · 已初始化 {name}")
            elif state == "missing":
                print(f"    · [警告] 未找到初始 {name}")
            elif not state.startswith("exists"):
                print(f"    · [警告] {name}: {state}")
    print("=" * 58)
    sys.stdout.flush()

    if frozen:
        # 后台线程：等服务就绪 → 开独立窗口 → 窗口关闭则退出程序
        def _launch():
            import window
            if not window.wait_for_server(url):
                window._show_error_dialog(
                    f"服务启动超时，未能监听 {url}。\n"
                    f"可能端口被占用。\n\n日志：{os.path.join(user_data_dir(), 'startup.log')}"
                )
                _shutdown()
            ok, info = window.launch_window(url, on_close=_shutdown)
            if not ok:
                # 没有 Edge/Chrome：回退到默认浏览器，功能不受影响
                print(f"[回退] {info}，改用系统默认浏览器打开")
                sys.stdout.flush()
                try:
                    webbrowser.open(url)
                except Exception as e:
                    window._show_error_dialog(
                        f"未能打开界面窗口：{info}\n\n"
                        f"请手动在浏览器访问：{url}"
                    )

        threading.Thread(target=_launch, daemon=True).start()
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
    else:
        # 源码运行保持 debug，便于开发
        app.run(host=HOST, port=PORT, debug=True)


if __name__ == "__main__":
    main()
