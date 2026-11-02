"""
六合彩数据分析工具 - 图猜码解码引擎
基于生肖、五行、色波等传统映射体系，将图像元素转换为号码推荐
"""
import json
import os
from collections import Counter

MAPPINGS_PATH = os.path.join(os.path.dirname(__file__), "data", "mappings.json")

# ==================== 核心映射知识库 ====================

# 2024年甲辰年 生肖对应号码（每年会轮转，此为示例）
ZODIAC_MAP = {
    "鼠": [2, 14, 26, 38],
    "牛": [1, 13, 25, 37, 49],
    "虎": [12, 24, 36, 48],
    "兔": [11, 23, 35, 47],
    "龙": [10, 22, 34, 46],
    "蛇": [9, 21, 33, 45],
    "马": [8, 20, 32, 44],
    "羊": [7, 19, 31, 43],
    "猴": [6, 18, 30, 42],
    "鸡": [5, 17, 29, 41],
    "狗": [4, 16, 28, 40],
    "猪": [3, 15, 27, 39],
}

# 五行对应号码
WUXING_MAP = {
    "金": [2, 3, 10, 11, 24, 25, 32, 33, 40, 41],
    "木": [6, 7, 14, 15, 22, 23, 36, 37, 44, 45],
    "水": [8, 9, 16, 17, 30, 31, 38, 39, 46, 47],
    "火": [4, 5, 18, 19, 26, 27, 34, 35, 42, 43],
    "土": [1, 12, 13, 20, 21, 28, 29, 48, 49],
}

# 色波对应号码
COLOR_MAP = {
    "红波": [1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46],
    "蓝波": [3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48],
    "绿波": [5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49],
}

# 常见物件/元素 → 生肖/五行 的映射
ELEMENT_HINTS = {
    # 动物 → 生肖
    "老鼠": "鼠", "耗子": "鼠",
    "牛": "牛", "水牛": "牛", "黄牛": "牛",
    "老虎": "虎", "猛虎": "虎", "虎": "虎",
    "兔子": "兔", "白兔": "兔", "月兔": "兔",
    "龙": "龙", "神龙": "龙", "飞龙": "龙",
    "蛇": "蛇", "青蛇": "蛇", "灵蛇": "蛇",
    "马": "马", "骏马": "马", "奔马": "马",
    "羊": "羊", "山羊": "羊", "绵羊": "羊",
    "猴子": "猴", "灵猴": "猴", "猴": "猴",
    "鸡": "鸡", "公鸡": "鸡", "凤凰": "鸡",
    "狗": "狗", "犬": "狗", "猎犬": "狗",
    "猪": "猪", "野猪": "猪",

    # 自然元素 → 五行
    "金属": "金", "刀剑": "金", "铜钱": "金", "金子": "金", "银": "金",
    "树": "木", "森林": "木", "竹子": "木", "花草": "木", "木头": "木",
    "水": "水", "河流": "水", "大海": "水", "雨": "水", "湖泊": "水", "瀑布": "水",
    "火": "火", "太阳": "火", "火焰": "火", "蜡烛": "火", "灯笼": "火",
    "山": "土", "土地": "土", "石头": "土", "城墙": "土", "大地": "土",

    # 颜色 → 色波
    "红色": "红波", "红": "红波", "朱": "红波", "赤": "红波",
    "蓝色": "蓝波", "蓝": "蓝波", "青": "蓝波",
    "绿色": "绿波", "绿": "绿波", "翠": "绿波",
}

# 方位 → 号码区间
DIRECTION_MAP = {
    "东": list(range(1, 13)),     # 1-12
    "南": list(range(13, 25)),    # 13-24
    "西": list(range(25, 37)),    # 25-36
    "北": list(range(37, 50)),    # 37-49
}

# 数字谐音/暗示
NUMBER_HINTS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "双": 2, "对": 2, "半": 5, "满": 10,
}


def get_all_categories():
    """返回所有可选的解码分类及其选项"""
    return {
        "zodiac": {
            "name": "十二生肖",
            "options": list(ZODIAC_MAP.keys()),
            "icon": "🐾"
        },
        "wuxing": {
            "name": "五行",
            "options": list(WUXING_MAP.keys()),
            "icon": "☯️"
        },
        "color": {
            "name": "色波",
            "options": list(COLOR_MAP.keys()),
            "icon": "🎨"
        },
        "direction": {
            "name": "方位",
            "options": list(DIRECTION_MAP.keys()),
            "icon": "🧭"
        }
    }


def decode_elements(selections):
    """
    根据用户选择的元素进行多维交叉解码

    参数 selections: {
        "zodiac": ["龙", "虎"],       # 可选
        "wuxing": ["水"],             # 可选
        "color": ["红波"],            # 可选
        "direction": ["东"],          # 可选
        "keywords": ["老虎", "河流"]  # 文字关键词，可选
    }

    返回: {
        "all_candidates": [所有候选号码及权重],
        "recommended": [推荐号码Top7],
        "decode_trace": [解码过程说明]
    }
    """
    # 号码权重计数器
    score = Counter()
    trace = []

    # 1. 处理生肖
    for z in selections.get("zodiac", []):
        if z in ZODIAC_MAP:
            nums = ZODIAC_MAP[z]
            for n in nums:
                score[n] += 3  # 生肖权重最高
            trace.append(f"🐾 生肖【{z}】→ 号码 {nums}")

    # 2. 处理五行
    for w in selections.get("wuxing", []):
        if w in WUXING_MAP:
            nums = WUXING_MAP[w]
            for n in nums:
                score[n] += 2
            trace.append(f"☯️ 五行【{w}】→ 号码 {nums}")

    # 3. 处理色波
    for c in selections.get("color", []):
        if c in COLOR_MAP:
            nums = COLOR_MAP[c]
            for n in nums:
                score[n] += 2
            trace.append(f"🎨 色波【{c}】→ 号码 {nums}")

    # 4. 处理方位
    for d in selections.get("direction", []):
        if d in DIRECTION_MAP:
            nums = DIRECTION_MAP[d]
            for n in nums:
                score[n] += 1
            trace.append(f"🧭 方位【{d}】→ 号码 {nums}")

    # 5. 处理关键词（自动映射）
    for kw in selections.get("keywords", []):
        if kw in ELEMENT_HINTS:
            mapped = ELEMENT_HINTS[kw]
            # 判断映射到哪个维度
            if mapped in ZODIAC_MAP:
                nums = ZODIAC_MAP[mapped]
                for n in nums:
                    score[n] += 3
                trace.append(f"🔍 关键词【{kw}】→ 生肖{mapped} → {nums}")
            elif mapped in WUXING_MAP:
                nums = WUXING_MAP[mapped]
                for n in nums:
                    score[n] += 2
                trace.append(f"🔍 关键词【{kw}】→ 五行{mapped} → {nums}")
            elif mapped in COLOR_MAP:
                nums = COLOR_MAP[mapped]
                for n in nums:
                    score[n] += 2
                trace.append(f"🔍 关键词【{kw}】→ {mapped} → {nums}")

    if not score:
        return {
            "all_candidates": [],
            "recommended": [],
            "decode_trace": ["⚠️ 未选择任何解码元素"]
        }

    # 按权重排序
    sorted_candidates = sorted(score.items(), key=lambda x: x[1], reverse=True)

    # 取 Top 7（6正码 + 1特码）
    top_nums = [n for n, _ in sorted_candidates[:7]]
    recommended = {
        "main": sorted(top_nums[:6]),
        "special": top_nums[6] if len(top_nums) > 6 else sorted_candidates[-1][0]
    }

    return {
        "all_candidates": [{"number": n, "score": s} for n, s in sorted_candidates],
        "recommended": recommended,
        "decode_trace": trace
    }


def quick_decode(keyword):
    """
    快速解码 - 输入一个关键词，直接返回关联号码
    """
    if keyword in ELEMENT_HINTS:
        mapped = ELEMENT_HINTS[keyword]
        for source_name, source_map in [
            ("生肖", ZODIAC_MAP),
            ("五行", WUXING_MAP),
            ("色波", COLOR_MAP)
        ]:
            if mapped in source_map:
                return {
                    "keyword": keyword,
                    "mapped_to": f"{source_name}·{mapped}",
                    "numbers": source_map[mapped]
                }

    # 直接匹配生肖/五行/色波
    for source_name, source_map in [
        ("生肖", ZODIAC_MAP),
        ("五行", WUXING_MAP),
        ("色波", COLOR_MAP)
    ]:
        if keyword in source_map:
            return {
                "keyword": keyword,
                "mapped_to": f"{source_name}·{keyword}",
                "numbers": source_map[keyword]
            }

    return {"keyword": keyword, "mapped_to": None, "numbers": []}
