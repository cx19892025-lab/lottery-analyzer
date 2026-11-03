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
#
# 设计要点（V1.4.8 实测得出，勿轻易简化为"只描述"）：
# 玄机图通常是水墨/剪纸/云雾缭绕的**弱化**图像，元素被刻意淡化、遮挡、变形。
# 早期版本只要求"列出看到什么"，模型就只做表面描述——实测漏掉了半透明背景里的羊，
# 还凭空编出「东（竹林常象征东方，青龙位）」这种根本不存在的方位。
# 现在改为「扫描 → 拆解 → 输出」三步，并强制产出**数量 / 汉字 / 数字**这三个
# 独立字段：它们是解码器真正吃得下的线索（见 map_vision_to_decoder_selections）。
VISION_SYSTEM_PROMPT = """你是一位六合彩玄机图解码专家。你看到的通常是水墨、剪纸或云雾缭绕的"玄机图"，画面元素被**刻意弱化、遮挡、半透明化**。你的任务不是描述画面，而是**主动拆解出隐藏的选号线索**。

请在内部按三步思考，**最终只输出 JSON**：

**第一步 · 逐区域扫描**：从上到下、从左到右，一块块检查。特别注意：
- 被雾气遮挡的
- 半透明、颜色很淡的
- 轮廓模糊、藏在其他物体后面的
- 背景里对比度很低的小尺寸元素

**第二步 · 逐项拆解**，这些线索最容易漏：
- **动物**：必须分辨到**具体物种**（马/羊/虎/龙/蛇/猪/狗/鸡/兔/鼠/牛/猴），并把所有动物都找出来，包括背景里的
- **数量**：同一元素出现几次？「三盏灯笼」里的"三"本身就是数字线索，要单独记下来
- **汉字**：图上刻的字、写的字、印章里的字（哪怕只露半笔、很淡、被压住）
- **数字**：直接出现的数字，包括刻在物体上的
- **方位**：某个主体在画面的位置，写成「方位-主体」，如「右上-红灯笼」「中央-石碑」
- **颜色**：以画面主色为准；淡雅的水墨色也算（墨黑→金/水、赭石→土、青灰→金）
- **五行归属**：给每个自然元素标注五行（竹林→木、溪流→水、山石→土、铜钱→金、灯笼→火）
- **象征物**：物体常暗含生肖或五行。灯笼/烛/炉→火，龟→水，葫芦→木，钱币→金，山石/城墙→土，红绳→火

**第三步 · 输出**，严格使用以下 JSON。所有字段值用**中文**，数组元素用简短名词短语：
{
  "animals": ["具体物种，如 马/羊/虎/龙/蛇/猪/狗/鸡/兔/鼠/牛/猴"],
  "colors": ["主要颜色，含淡雅水墨色"],
  "elements": ["自然元素及五行归属，如 竹林(木)、溪流(水)、红灯笼(火)、山石(土)"],
  "directions": ["方位线索，写成『方位-主体』，如 右上-红灯笼、中央-石碑"],
  "numbers": ["图中出现的数字，以及由数量推出的数字，如 三、8"],
  "objects": ["其他物件，含文字载体，如 石碑、灯笼、印章、铜钱"],
  "characters": ["图上出现的汉字，逐字列出，如 龍"],
  "counts": ["数量线索，如 三盏灯笼、两只羊、一匹马"],
  "description": "一句话概述画面"
}

没有的类别用空数组 []。**宁可多报可疑项，也不要漏掉**；不确定的也写进对应数组，并在 description 里说明。**不要编造方位**——只写画面里真实存在的位置。"""


VISION_USER_PROMPT = ("这是一张云雾缭绕的六合彩玄机图，元素被刻意弱化和遮挡。"
                     "请逐区域仔细扫描并主动拆解，把动物、数量、汉字、数字、方位、五行全部提取出来。")


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
        "characters": [], "counts": [],
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

        choice = response.choices[0]
        msg = choice.message
        raw_content = msg.content or ""
        finish = getattr(choice, "finish_reason", "") or ""

        # 推理型模型（如 DeepSeek）会先输出一大段思考过程（reasoning_content）。
        # 若 max_tokens 偏小，思考就把预算吃光，content 为空且 finish_reason='length'。
        # 此时**不能**拿 reasoning_content 当结果——那是自然语言思考过程，
        # 正则会从中误匹配出 JSON 片段、json.loads 解析成 list，导致上层崩溃。
        # 正确做法是加大 max_tokens 重试。
        if not raw_content.strip() and finish == "length":
            retry_tokens = max(max_tokens * 4, 4096)
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=retry_tokens,
            )
            choice = response.choices[0]
            raw_content = choice.message.content or ""

        # 重试后仍无内容：明确报错，别让前端只看到"未识别到明显元素"
        if not raw_content.strip():
            return {
                **empty,
                "error": ("模型返回了空内容（推理型模型的思考过程可能占满了输出预算）。"
                          "请重试，或改用非推理型视觉模型如 qwen3-vl-plus。"),
                "description": "AI 未返回可解析的结果",
            }

        parsed = _parse_json_response(raw_content)

        # 模型没按 JSON 格式回答（如 DeepSeek 有时输出散文），别让前端只显示
        # "未识别到明显元素" 而看不到原因
        if parsed.get("parse_failed"):
            return {
                **empty,
                "error": ("模型没有按要求的 JSON 格式返回结果，无法解析。"
                          "请重试，或改用 qwen3-vl-plus 等格式更稳定的视觉模型。"),
                "description": "AI 返回格式无法解析",
                "raw_response": parsed.get("raw_response", "")[:500],
            }

        return parsed

    except Exception as e:
        return {
            **empty,
            "error": _friendly_error(e),
            "description": f"AI 分析失败: {_friendly_error(e)}",
        }


def _friendly_error(e) -> str:
    """把常见报错翻译成用户能看懂的话"""
    msg = str(e)
    low = msg.lower()
    tail = f"（原始报错：{msg[:200]}）"

    # 服务商侧内容审核网关拦截：整次请求被判敏感，并非图片里某块内容有问题
    if "sensitive_words_detected" in low or "sensitive" in low:
        return ("请求被服务商的内容审核拦截（错误码 sensitive_words_detected）。"
                "这是服务商网关对**整次请求文本**的判定，与图片里的具体内容无关"
                "（实测纯数字图、甚至 1×1 像素图也可能被拦，含『必中/投注』字样的图反而能通过）。"
                "建议：稍后重试、换一个模型（如 qwen3-vl-plus），"
                "并保持内置的识图提示词不变。" + tail)

    # 中转站/服务商上游故障：常以 400 或 5xx 出现，报错体里带 upstream_unavailable
    if ("upstream_unavailable" in low or "server_error" in low
            or "服务暂时不可用" in msg or "upstream" in low):
        return ("上游服务暂时不可用（服务商或中转站侧故障，不是你的配置写错了）。"
                "可稍后重试、换一个模型，或换一家服务商。" + tail)

    if ("does not exist" in low or "no such model" in low
            or "model_not_found" in low
            or ("not found" in low and "model" in low)):
        return f"模型不存在，请检查「设置」页的模型名是否正确（可点「读取可用模型」查看）{tail}"
    if "401" in msg or "unauthorized" in low or "invalid_api_key" in low:
        return f"API Key 无效或已过期，请到「设置」页重新填写{tail}"
    if "403" in msg:
        return f"该 Key 无权访问此模型，请确认账号权限{tail}"
    if "429" in msg or "rate limit" in low or "quota" in low:
        return f"请求过于频繁或额度用尽，请稍后再试{tail}"
    if "timed out" in low or "timeout" in low:
        return f"请求超时，可在「设置」页调大超时时间{tail}"
    if "connection" in low or "getaddrinfo" in low or "ssl" in low:
        return f"无法连接接口地址，请检查网络与 Base URL{tail}"

    # 400 通常是「接口不支持你发的这个请求」，最常见的两个原因是模型名不对或不支持图片
    if "400" in msg:
        return ("请求被拒绝（400）。常见原因：该模型名不被此接口支持，"
                "或该模型不支持图片输入。可点「读取可用模型」核对模型名。" + tail)

    return msg[:300]


def _parse_json_response(raw_text: str) -> dict:
    """从 AI 回复中提取 JSON。始终返回 dict，绝不返回 list/None。"""
    # 移除 markdown code block
    cleaned = re.sub(r'```json\s*', '', raw_text)
    cleaned = re.sub(r'```\s*', '', cleaned)
    cleaned = cleaned.strip()

    def _coerce(obj):
        """AI 可能返回 JSON 数组或标量，统一收敛成 dict"""
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            # 取第一个 dict 元素；数组本身当作 objects 列表
            for item in obj:
                if isinstance(item, dict):
                    return item
            return {"objects": [str(x) for x in obj]}
        return None

    try:
        coerced = _coerce(json.loads(cleaned))
        if coerced is not None:
            return coerced
    except json.JSONDecodeError:
        pass

    # 尝试在文本中找 JSON
    match = re.search(r'\{[\s\S]*\}', raw_text)
    if match:
        try:
            coerced = _coerce(json.loads(match.group()))
            if coerced is not None:
                return coerced
        except json.JSONDecodeError:
            pass

    # 解析失败，返回原文作为描述
    return {
        "animals": [], "colors": [],
        "elements": [], "directions": [],
        "numbers": [], "objects": [],
        "characters": [], "counts": [],
        "description": raw_text[:200],
        "raw_response": raw_text,
        "parse_failed": True,
    }


# 繁体 → 简体。玄机图的石碑、印章、书法题字普遍用繁体，
# 模型会原样转写（输出「龍」而不是「龙」），不做归一这条线索就废了。
# 只列「繁简不同」的字符；同形字（虎/蛇/鼠/猴/狗/牛/羊/兔）无需处理。
_TRAD_SIMP = {
    "龍": "龙", "馬": "马", "雞": "鸡", "鷄": "鸡",
    "豬": "猪", "豶": "猪", "龜": "龟", "鳳": "凤",
    "魚": "鱼", "獅": "狮",
}

# 中文数字 → 阿拉伯数字
_CN_NUM = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _cn_to_int(text: str):
    """把「三」「十」「八」这类中文数字转成整数；无法解析返回 None。"""
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CN_NUM:
        return _CN_NUM[text]
    # 十几 / 几十：如「十二」「二十」
    if "十" in text:
        parts = text.split("十")
        head = parts[0]
        tail = parts[1] if len(parts) > 1 else ""
        if head == "":
            tens, ones = 1, (_CN_NUM.get(tail, 0) if tail else 0)
        elif head in _CN_NUM and (tail == "" or tail in _CN_NUM):
            tens, ones = _CN_NUM[head], (_CN_NUM.get(tail, 0) if tail else 0)
        else:
            return None
        return tens * 10 + ones
    return None


# 中文数字连续片段（如「三」「十二」）
_CN_NUM_RE = re.compile(r"[零一二两三四五六七八九十]+")

# 引号（含中英文）及其内容。counts 里常有「一个数字'8'」这种
# **引用**字面数字的写法，不能当成数量线索。
_QUOTED_RE = re.compile(r"[“”‘’\"'「」『』《》].*?[“”‘’\"'「」『』《》]")

# 数量词前缀：「三盏灯笼」「两只羊」
_COUNT_PREFIX_RE = re.compile(r"^\s*([0-9]+|[零一二两三四五六七八九十]+)")


def _numbers_in(text: str):
    """
    从一段文字里抽出所有数字。

    阿拉伯数字直接取；中文数字按**连续片段**整体解析，
    这样「十二」= 12 而不是被逐字拆成 1 和 2（拆开会凭空多出无关号码）。
    """
    out = []
    s = str(text)
    for m in re.findall(r"\d+", s):
        out.append(int(m))
    for m in _CN_NUM_RE.findall(s):
        n = _cn_to_int(m)
        if n is not None:
            out.append(n)
    return out


def _count_number(text: str):
    """
    从一条数量描述里取出**计数的那个数字**。

    与 _numbers_in 的区别：
    - 「三盏灯笼」→ 3（计数）
    - 「一个数字'8'」→ 1（这里 8 是引用的字面数字，不是计数）
    - 「石碑上有数字8」→ None（这是描述，不是计数）

    规则：**只认开头的中文/阿拉伯数量词**。
    若退化去全文解析，「石碑上有数字8」会被误当成"数了 8 个"，
    从而把本该是直接暗示的 8 降级成数量线索，丢掉 +5 的强权重。
    """
    s = _QUOTED_RE.sub("", str(text)).strip()
    if not s:
        return None

    m = _COUNT_PREFIX_RE.match(s)
    if not m:
        return None
    return _cn_to_int(m.group(1))


def _extract_numbers(numbers_field, counts_field, characters_field):
    """
    从 AI 的 numbers / counts / characters 里抽出号码线索。

    返回 (direct_numbers, count_numbers)：
    - direct_numbers：图上**直接写出的数字**（如石碑刻的 8）→ 强线索
    - count_numbers：由**数量**推出的数字（如「三盏灯笼」→ 3）→ 弱线索

    注意：提示词里 numbers 字段是「图中出现的数字，**以及由数量推出的数字**」，
    模型会把数出来的 3 也填进 numbers。若不处理，3 会拿到"直接暗示"的 +5 权重，
    而它其实只是"三盏灯笼"数出来的，权重应当低一档。
    因此：同一个数字若同时出现在数量描述里，一律按数量线索处理。
    """
    direct = []
    count = []

    def _add(bucket, n):
        if n is not None and 1 <= n <= 49 and n not in bucket:
            bucket.append(n)

    # counts 字段：「三盏灯笼」→ 3。注意必须**先算数量**，才能回头降级 numbers。
    for item in counts_field or []:
        _add(count, _count_number(item))

    # numbers 字段：模型已明确标为「图中数字」，按直接线索处理
    for item in numbers_field or []:
        for n in _numbers_in(item):
            _add(direct, n)

    # characters 里可能混着数字，如「8」
    for item in characters_field or []:
        for n in _numbers_in(item):
            _add(direct, n)

    # 数字 1 不作为有效线索（图中随处可见，无信息量）
    direct = [n for n in direct if n != 1]
    count = [n for n in count if n != 1]

    # 与数量线索重复的数字 → 降级为数量线索（它其实是数出来的，不是写出来的）
    direct = [n for n in direct if n not in count]
    return direct, count


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
        "keywords": [],
        "numbers": [],
        "count_numbers": [],
        # evidence[维度][线索] = 该线索**来自图上什么**的证据描述。
        # 没有它，前端只能说「命中生肖龙」，用户仍不知道是画的龙还是刻的「龍」字。
        "evidence": {"zodiac": {}, "wuxing": {}, "color": {}, "direction": {}},
    }

    def _ev(dim, value, text):
        """记录某条线索的图上证据（同一线索多次命中时合并去重）。"""
        bucket = selections["evidence"][dim]
        bucket.setdefault(value, [])
        if text not in bucket[value]:
            bucket[value].append(text)

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

    def _norm(text):
        """繁体→简体归一。玄机图石碑/印章常用繁体字（「龍」「馬」「雞」「豬」），
        不归一就会导致生肖线索整条丢失（模型原样输出「龍」，映射表里只有「龙」）。"""
        for trad, simp in _TRAD_SIMP.items():
            text = text.replace(trad, simp)
        return text

    for animal in vision_result.get("animals", []):
        animal = _norm(str(animal))
        for key, zodiac in ANIMAL_TO_ZODIAC.items():
            if key in animal:
                if zodiac not in selections["zodiac"]:
                    selections["zodiac"].append(zodiac)
                _ev("zodiac", zodiac, f"图中出现「{animal}」")

    # 颜色 → 色波
    COLOR_TO_WAVE = {
        "红": "红波", "朱": "红波", "赤": "红波", "粉红": "红波", "橙": "红波",
        "蓝": "蓝波", "青": "蓝波", "紫": "蓝波",
        "绿": "绿波", "翠": "绿波",
    }

    for color in vision_result.get("colors", []):
        color = _norm(str(color))
        for key, wave in COLOR_TO_WAVE.items():
            if key in color:
                if wave not in selections["color"]:
                    selections["color"].append(wave)
                _ev("color", wave, f"图中颜色为「{color}」")

    # 自然元素 → 五行
    ELEMENT_TO_WUXING = {
        "金": "金", "银": "金", "铜": "金", "铁": "金", "刀": "金", "剑": "金", "金属": "金",
        "木": "木", "树": "木", "森": "木", "竹": "木", "花": "木", "草": "木", "林": "木",
        "水": "水", "河": "水", "海": "水", "湖": "水", "雨": "水", "泉": "水", "冰": "水", "雪": "水",
        "火": "火", "焰": "火", "烛": "火", "灯": "火", "日": "火", "太阳": "火",
        "土": "土", "山": "土", "石": "土", "沙": "土", "地": "土", "岩": "土",
    }

    for elem in vision_result.get("elements", []):
        elem = _norm(str(elem))
        for key, wuxing in ELEMENT_TO_WUXING.items():
            if key in elem:
                if wuxing not in selections["wuxing"]:
                    selections["wuxing"].append(wuxing)
                _ev("wuxing", wuxing, f"图中元素「{elem}」")

    # 方位
    #
    # 注意：这里做的是**逐条字符串**判定，一条描述只应产出一个象限。
    # 早期实现对每条描述遍历整个别名表，「右上-红灯笼」会同时命中「右(西)」和
    # 「上(北)」，多��描述叠加后集齐东南西北 = 覆盖 1-49 全部号码，
    # 方位维度等于给每个号码都加了同一个 +1，完全失效。
    # 现在：一条描述取「最具体」的那个方位词；并集若已覆盖全部四象限，
    # 说明这张图本来就没有方位暗示，整体丢弃该维度（留 trace 说明）。
    DIRECTION_ALIASES = [
        # (关键词, 象限) —— 按优先级从高到低，"东南"这类复合词优先于单字
        ("东北", "北"), ("东南", "东"), ("西南", "西"), ("西北", "北"),
        ("东", "东"), ("南", "南"), ("西", "西"), ("北", "北"),
        ("左上", "东"), ("右上", "西"), ("左下", "东"), ("右下", "西"),
        ("左", "东"), ("右", "西"), ("上", "北"), ("下", "南"),
    ]

    for direction in vision_result.get("directions", []):
        direction = _norm(str(direction))
        for key, d in DIRECTION_ALIASES:
            if key in direction:
                if d not in selections["direction"]:
                    selections["direction"].append(d)
                _ev("direction", d, f"图中位置「{direction}」")
                break  # 一条描述只取一个方位

    # 注意：方位若集齐四象限（覆盖全部 1-49），该维度会被中和。
    # 这里**不做清空**——清空会让解码器看不出发生了什么。
    # 交给 decoder 的维度护栏统一处理并写进 trace（见 decode_elements._apply_dimension）。

    # 图上的汉字 → 生肖 / 五行 / 色波
    # 「龍」这类刻字在玄机图里是最直接的生肖暗示，但模型常只把它写进 objects，
    # 所以这里对 characters 单独做映射。
    CHAR_TO_ZODIAC = {
        "鼠": "鼠", "牛": "牛", "虎": "虎", "兔": "兔", "龙": "龙",
        "蛇": "蛇", "马": "马", "羊": "羊", "猴": "猴", "鸡": "鸡",
        "狗": "狗", "猪": "猪",
    }
    CHAR_TO_WUXING = {"金": "金", "木": "木", "水": "水", "火": "火", "土": "土"}

    for ch in vision_result.get("characters", []):
        ch = _norm(str(ch))
        for key, zodiac in CHAR_TO_ZODIAC.items():
            if key in ch:
                if zodiac not in selections["zodiac"]:
                    selections["zodiac"].append(zodiac)
                _ev("zodiac", zodiac, f"图上刻字「{ch}」")
        for key, wuxing in CHAR_TO_WUXING.items():
            if key in ch:
                if wuxing not in selections["wuxing"]:
                    selections["wuxing"].append(wuxing)
                _ev("wuxing", wuxing, f"图上刻字「{ch}」")

    # 数字线索 → 具体号码
    #
    # 「石上刻着 8」这类是**直接号码暗示**，比生肖/五行更具体，权重更高。
    # 「三盏灯笼」的数量也是号码线索，但更间接，权重低一档。
    direct_numbers, count_numbers = _extract_numbers(
        vision_result.get("numbers", []),
        vision_result.get("counts", []),
        vision_result.get("characters", []),
    )
    selections["numbers"] = direct_numbers
    selections["count_numbers"] = count_numbers

    # 其他物件作为关键词
    for obj in vision_result.get("objects", []):
        selections["keywords"].append(_norm(str(obj)))

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
