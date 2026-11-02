"""
六合彩数据分析工具 - AI 视觉识别模块

通过任意 OpenAI 兼容接口识别图片中的元素。
接口地址 / API Key / 模型名全部由用户在「设置」页自行填写，
不再依赖本机任何外部脚本，也不再写死模型名。

未配置时 analyze_image() 返回结构化错误，由前端提示用户去设置页填写。
"""
import base64
import json
import os
import re

import settings as settings_mod


# 视觉识别提示词
VISION_SYSTEM_PROMPT = """你是一位六合彩玄机图解码专家。用户会给你一张图片，请你仔细观察并识别出以下元素：

1. **动物**：列出图中所有动物（如虎、龙、蛇、马、鸡等，特别注意十二生肖动物）
2. **颜色**：主要色调（红、蓝、绿、金、黑、白等）
3. **自然元素**：水、火、树木、山、金属等（对应五行）
4. **方位线索**：东南西北方位暗示
5. **数字**：直接出现的数字或可能暗示数字的物品数量
6. **其他物件**：刀剑、铜钱、灯笼、花草等有象征意义的物品

请严格按以下 JSON 格式输出，不要输出任何其他内容：
{
  "animals": ["识别到的动物列表"],
  "colors": ["主要颜色列表"],
  "elements": ["自然元素/五行相关"],
  "directions": ["方位线索"],
  "numbers": [直接看到的数字],
  "objects": ["其他物件"],
  "description": "一句话概述图片内容"
}

如果某个类别没有识别到，用空数组[]。"""


VISION_USER_PROMPT = "请仔细分析这张玄机图，识别其中所有可能与六合彩选号相关的元素。"


def _get_client():
    """
    按用户配置创建 OpenAI 兼容客户端。
    返回 (client, model)；未配置或缺少依赖时抛 RuntimeError。
    """
    cfg = settings_mod.get_ai_config()

    if not cfg["base_url"] or not cfg["model"]:
        raise RuntimeError("尚未配置 AI 接口，请到「设置」页填写接口地址与模型名")

    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("缺少 openai 依赖，请执行：pip install openai")

    client = OpenAI(
        api_key=cfg["api_key"] or "not-needed",  # 本地 Ollama 等无需 Key
        base_url=cfg["base_url"].rstrip("/"),
        timeout=cfg.get("timeout", 60),
    )
    return client, cfg["model"]


def analyze_image(image_data_b64: str, mime_type: str = "image/png") -> dict:
    """
    使用用户配置的 AI 视觉模型分析图片中的元素

    参数:
        image_data_b64: Base64 编码的图片数据
        mime_type: 图片 MIME 类型

    返回:
        识别到的元素字典；失败时含 "error" 字段
    """
    empty = {
        "animals": [], "colors": [], "elements": [],
        "directions": [], "numbers": [], "objects": [],
    }

    try:
        client, model = _get_client()
    except RuntimeError as e:
        return {**empty, "error": str(e), "description": "AI 未配置"}

    cfg = settings_mod.get_ai_config()
    max_tokens = cfg.get("max_tokens", 1024)

    try:
        messages = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {"role": "user", "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_data_b64}"
                    }
                },
                {
                    "type": "text",
                    "text": VISION_USER_PROMPT
                }
            ]}
        ]

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )

        raw_content = response.choices[0].message.content or ""
        return _parse_json_response(raw_content)

    except Exception as e:
        return {
            **empty,
            "error": _friendly_error(e),
            "description": f"AI 分析失败: {_friendly_error(e)}",
        }


def _friendly_error(e) -> str:
    """把常见报错翻译成用户能看懂的话"""
    msg = str(e)
    if "not found" in msg and "model" in msg.lower():
        return f"模型不存在，请检查「设置」页的模型名是否正确（原始报错：{msg[:160]}）"
    if "401" in msg or "Unauthorized" in msg or "invalid_api_key" in msg.lower():
        return f"API Key 无效或已过期，请到「设置」页重新填写（原始报错：{msg[:160]}）"
    if "403" in msg:
        return f"该 Key 无权访问此模型，请确认账号权限（原始报错：{msg[:160]}）"
    if "429" in msg:
        return f"请求过于频繁或额度用尽，请稍后再试（原始报错：{msg[:160]}）"
    if "timed out" in msg.lower() or "timeout" in msg.lower():
        return f"请求超时，可在「设置」页调大超时时间（原始报错：{msg[:160]}）"
    if "Connection" in msg or "getaddrinfo" in msg or "SSL" in msg:
        return f"无法连接接口地址，请检查网络与 Base URL（原始报错：{msg[:160]}）"
    return msg[:300]


def _parse_json_response(raw_text: str) -> dict:
    """从 AI 回复中提取 JSON"""
    # 移除 markdown code block
    cleaned = re.sub(r'```json\s*', '', raw_text)
    cleaned = re.sub(r'```\s*', '', cleaned)
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
        return result
    except json.JSONDecodeError:
        # 尝试在文本中找 JSON
        match = re.search(r'\{[\s\S]*\}', raw_text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

    # 解析失败，返回原文作为描述
    return {
        "animals": [], "colors": [],
        "elements": [], "directions": [],
        "numbers": [], "objects": [],
        "description": raw_text[:200],
        "raw_response": raw_text
    }


def map_vision_to_decoder_selections(vision_result: dict) -> dict:
    """
    将 AI 视觉识别结果映射为解码器的 selections 格式

    将识别到的动物映射到生肖、颜色映射到色波、自然元素映射到五行等
    """
    selections = {
        "zodiac": [],
        "wuxing": [],
        "color": [],
        "direction": [],
        "keywords": []
    }

    # 动物 → 生肖
    ANIMAL_TO_ZODIAC = {
        "鼠": "鼠", "老鼠": "鼠", "耗子": "鼠",
        "牛": "牛", "水牛": "牛", "黄牛": "牛",
        "虎": "虎", "老虎": "虎", "猛虎": "虎",
        "兔": "兔", "兔子": "兔", "白兔": "兔",
        "龙": "龙", "神龙": "龙", "飞龙": "龙",
        "蛇": "蛇", "青蛇": "蛇", "灵蛇": "蛇",
        "马": "马", "骏马": "马", "奔马": "马",
        "羊": "羊", "山羊": "羊", "绵羊": "羊",
        "猴": "猴", "猴子": "猴", "灵猴": "猴",
        "鸡": "鸡", "公鸡": "鸡", "凤凰": "鸡",
        "狗": "狗", "犬": "狗", "猎犬": "狗",
        "猪": "猪", "野猪": "猪",
    }

    for animal in vision_result.get("animals", []):
        for key, zodiac in ANIMAL_TO_ZODIAC.items():
            if key in animal:
                if zodiac not in selections["zodiac"]:
                    selections["zodiac"].append(zodiac)

    # 颜色 → 色波
    COLOR_TO_WAVE = {
        "红": "红波", "朱": "红波", "赤": "红波", "粉红": "红波", "橙": "红波",
        "蓝": "蓝波", "青": "蓝波", "紫": "蓝波",
        "绿": "绿波", "翠": "绿波",
    }

    for color in vision_result.get("colors", []):
        for key, wave in COLOR_TO_WAVE.items():
            if key in color:
                if wave not in selections["color"]:
                    selections["color"].append(wave)

    # 自然元素 → 五行
    ELEMENT_TO_WUXING = {
        "金": "金", "银": "金", "铜": "金", "铁": "金", "刀": "金", "剑": "金", "金属": "金",
        "木": "木", "树": "木", "森": "木", "竹": "木", "花": "木", "草": "木", "林": "木",
        "水": "水", "河": "水", "海": "水", "湖": "水", "雨": "水", "泉": "水", "冰": "水", "雪": "水",
        "火": "火", "焰": "火", "烛": "火", "灯": "火", "日": "火", "太阳": "火",
        "土": "土", "山": "土", "石": "土", "沙": "土", "地": "土", "岩": "土",
    }

    for elem in vision_result.get("elements", []):
        for key, wuxing in ELEMENT_TO_WUXING.items():
            if key in elem:
                if wuxing not in selections["wuxing"]:
                    selections["wuxing"].append(wuxing)

    # 方位
    DIRECTION_ALIASES = {
        "东": "东", "左": "东",
        "南": "南", "下": "南",
        "西": "西", "右": "西",
        "北": "北", "上": "北",
    }

    for direction in vision_result.get("directions", []):
        for key, d in DIRECTION_ALIASES.items():
            if key in direction:
                if d not in selections["direction"]:
                    selections["direction"].append(d)

    # 其他物件作为关键词
    for obj in vision_result.get("objects", []):
        selections["keywords"].append(obj)

    return selections


if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    cfg = settings_mod.get_ai_config()
    print("AI 配置状态:", "已配置" if settings_mod.is_configured() else "未配置")
    print("  Base URL:", cfg["base_url"] or "(空)")
    print("  模型名  :", cfg["model"] or "(空)")
    print("  API Key :", settings_mod.mask_key(cfg["api_key"]) or "(空)")
    if not settings_mod.is_configured():
        print("\n请启动应用后到「设置」页填写接口地址与模型名。")
