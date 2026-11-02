"""
六合彩数据分析工具 - AI 视觉识别模块
使用 Kaggle 免费模型 (Gemini 3.7 Flash) 识别图片中的元素
"""
import base64
import json
import sys
import os
import re

# 添加 kaggle_llm 路径
sys.path.insert(0, r"c:\Users\10397\antigravity\kind-hubble")

try:
    from kaggle_llm import get_client, resolve_model
    HAS_KAGGLE = True
except ImportError:
    HAS_KAGGLE = False


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


def analyze_image(image_data_b64: str, mime_type: str = "image/png") -> dict:
    """
    使用 AI 视觉模型分析图片中的元素

    参数:
        image_data_b64: Base64 编码的图片数据
        mime_type: 图片 MIME 类型

    返回:
        识别到的元素字典
    """
    if not HAS_KAGGLE:
        return {"error": "Kaggle AI 模型未配置", "animals": [], "colors": [],
                "elements": [], "directions": [], "numbers": [], "objects": [],
                "description": "AI 模型不可用"}

    try:
        client, _ = get_client()
        # 使用 Gemini 3.7 Flash（支持视觉，免费）
        target_model = resolve_model("gemini-3.7")

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
            model=target_model,
            messages=messages,
            max_tokens=1024
        )

        raw_content = response.choices[0].message.content or ""

        # 尝试解析 JSON
        result = _parse_json_response(raw_content)
        return result

    except Exception as e:
        return {
            "error": str(e),
            "animals": [], "colors": [],
            "elements": [], "directions": [],
            "numbers": [], "objects": [],
            "description": f"AI 分析失败: {str(e)}"
        }


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
    # 测试：检查模块是否可用
    print(f"Kaggle AI available: {HAS_KAGGLE}")
    if HAS_KAGGLE:
        print("Vision module ready!")
