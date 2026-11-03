"""
六合彩数据分析工具 - Flask 主应用
提供 Web 界面 + RESTful API
"""
import base64
from flask import Flask, render_template, jsonify, request
from database import init_db, get_all_results
from analyzer import (
    frequency_analysis, hot_cold_numbers, missing_values,
    odd_even_analysis, big_small_analysis, sum_analysis,
    tail_number_analysis, consecutive_analysis,
    smart_recommend, get_dashboard_data
)
from backtest import run_backtest, STRATEGIES, MIN_HISTORY
from decoder import get_all_categories, decode_elements, quick_decode
from vision import analyze_image, map_vision_to_decoder_selections
from crawler import import_all, sync_latest, data_status
import settings as settings_mod

app = Flask(__name__)
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
    """历史开奖记录"""
    limit = request.args.get("limit", 50, type=int)
    results = get_all_results(limit)
    return jsonify(results)


@app.route("/api/frequency")
def api_frequency():
    """号码频率"""
    limit = request.args.get("limit", None, type=int)
    return jsonify(frequency_analysis(limit))


@app.route("/api/hot_cold")
def api_hot_cold():
    """冷热号"""
    recent_n = request.args.get("recent", 30, type=int)
    return jsonify(hot_cold_numbers(recent_n))


@app.route("/api/missing")
def api_missing():
    """遗漏值"""
    return jsonify(missing_values())


@app.route("/api/odd_even")
def api_odd_even():
    """奇偶比"""
    return jsonify(odd_even_analysis())


@app.route("/api/big_small")
def api_big_small():
    """大小比"""
    return jsonify(big_small_analysis())


@app.route("/api/sum")
def api_sum():
    """和值分析"""
    return jsonify(sum_analysis())


@app.route("/api/tail")
def api_tail():
    """尾数分布"""
    return jsonify(tail_number_analysis())


@app.route("/api/consecutive")
def api_consecutive():
    """连号分析"""
    return jsonify(consecutive_analysis())


# ==================== 数据管理 API ====================

@app.route("/api/data/status")
def api_data_status():
    """本地开奖库概况（期数、最新期号/日期、数据源地址）"""
    return jsonify(data_status())


@app.route("/api/data/import", methods=["POST"])
def api_data_import():
    """
    全量导入真实历史数据（1993 年至今，双源合并去重）。
    默认清空现有数据（用于替换模拟数据）；clear=false 时仅追加不存在的期号。
    注意：涉及两个外部抓取 + 批量写库，响应需数秒。
    """
    body = request.get_json(silent=True) or {}
    clear = body.get("clear", True)
    try:
        result = import_all(clear=bool(clear))
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "error": f"导入失败：{e}",
            "hint": "请检查网络能否访问 raw.githubusercontent.com（国内一般可直连，"
                    "若失败可稍后重试或配置代理后重试）"
        }), 502


@app.route("/api/data/sync", methods=["POST"])
def api_data_sync():
    """
    增量同步最新开奖（仅拉增量源，INSERT OR IGNORE 补新期号）。
    开奖一般在周二/四/六晚，开奖后增量源 CI 需要一段时间才更新。
    """
    try:
        return jsonify(sync_latest())
    except Exception as e:
        return jsonify({"error": f"同步失败：{e}"}), 502


# ==================== 智能选号 API ====================

@app.route("/api/recommend")
def api_recommend():
    """智能选号推荐"""
    strategy = request.args.get("strategy", "balanced")
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

# 1x1 透明 PNG，用来验证接口是否真的支持图片输入
_TINY_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42m"
             "P8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=")


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
                         "image_url": {"url": f"data:image/png;base64,{_TINY_PNG}"}},
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

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    print("[INFO] Lottery Analyzer starting...")
    init_db()
    # 不再自动生成模拟数据：真实数据请到「设置 → 数据管理」一键导入
    print("[INFO] Server ready: http://localhost:5000")
    app.run(debug=True, port=5000)
