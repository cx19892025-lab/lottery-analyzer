"""
六合彩数据分析工具 - Flask 主应用
提供 Web 界面 + RESTful API
"""
import base64
from flask import Flask, render_template, jsonify, request
from database import init_db, generate_simulated_data, get_all_results
from analyzer import (
    frequency_analysis, hot_cold_numbers, missing_values,
    odd_even_analysis, big_small_analysis, sum_analysis,
    tail_number_analysis, consecutive_analysis,
    smart_recommend, get_dashboard_data
)
from decoder import get_all_categories, decode_elements, quick_decode
from vision import analyze_image, map_vision_to_decoder_selections, HAS_KAGGLE

app = Flask(__name__)


# ==================== 页面路由 ====================

@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


# ==================== 数据 API ====================

@app.route("/api/dashboard")
def api_dashboard():
    """仪表盘汇总数据"""
    return jsonify(get_dashboard_data())


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


# ==================== 智能选号 API ====================

@app.route("/api/recommend")
def api_recommend():
    """智能选号推荐"""
    strategy = request.args.get("strategy", "balanced")
    return jsonify(smart_recommend(strategy))


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
    if not HAS_KAGGLE:
        return jsonify({"error": "AI 视觉模型未配置，请检查 Kaggle 环境"}), 503

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
    return jsonify({"available": HAS_KAGGLE})


# ==================== 启动 ====================

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    print("[INFO] Lottery Analyzer starting...")
    init_db()
    generate_simulated_data()
    print("[INFO] Server ready: http://localhost:5000")
    app.run(debug=True, port=5000)
