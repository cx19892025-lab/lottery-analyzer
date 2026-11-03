"""
六合彩数据分析工具 - 图猜码解码引擎
基于生肖、五行、色波等传统映射体系，将图像元素转换为号码推荐
"""
import json
import os
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache

from lunardate import LunarDate

MAPPINGS_PATH = os.path.join(os.path.dirname(__file__), "data", "mappings.json")

# ==================== 核心映射知识库 ====================

# 十二生肖固定顺序（也是轮转的依据）
ZODIAC_ORDER = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

# (农历年 % 12) -> 生肖，已用 2020 庚子鼠年、2026 丙午马年验证
_ZODIAC_BY_MOD = {
    4: "鼠", 5: "牛", 6: "虎", 7: "兔", 8: "龙", 9: "蛇",
    10: "马", 11: "羊", 0: "猴", 1: "鸡", 2: "狗", 3: "猪",
}


def lunar_year_of(d=None):
    """公历日期所属农历年（以农历正月初一为界）"""
    return _lunar_year_of(d or date.today())


@lru_cache(maxsize=1024)
def _lunar_year_of(d):
    return LunarDate.from_solar_date(d.year, d.month, d.day).year


def year_zodiac(lunar_year):
    """农历年对应的生肖"""
    return _ZODIAC_BY_MOD[int(lunar_year) % 12]


@lru_cache(maxsize=16)
def _zodiac_map_for(lunar_year):
    """
    构造某农历年的生肖→号码表（缓存）
    规则：当年生肖 = 1/13/25/37/49，其余号码按生肖逆序轮排。
    例 2026 马年：马=1,13,25,37,49；蛇=2,14,…；龙=3,15,…；…；羊=12,24,…
    """
    idx = ZODIAC_ORDER.index(year_zodiac(lunar_year))
    mapping = {a: [] for a in ZODIAC_ORDER}
    for n in range(1, 50):
        mapping[ZODIAC_ORDER[(idx - (n - 1)) % 12]].append(n)
    return mapping


def get_zodiac_map(d=None):
    """
    取指定日期（默认今天）生效的生肖→号码表。
    生肖表在农历正月初一换新，因此同一公历年 1~2 月的开奖可能仍属上一生肖年。
    """
    return dict(_zodiac_map_for(lunar_year_of(d)))


@lru_cache(maxsize=16)
def _inverse_zodiac_for(lunar_year):
    """号码→生肖的反查表（按农历年缓存）"""
    return {n: a for a, ns in _zodiac_map_for(lunar_year).items() for n in ns}


def zodiac_of_number(number, d=None):
    """
    某号码在指定日期（默认今天）生肖表中的生肖。
    历史统计须传入该期的开奖日期，否则跨年数据会算错。
    """
    return _inverse_zodiac_for(lunar_year_of(d))[int(number)]


def zodiac_info(d=None):
    """当前生效生肖表的元信息（供前端展示，避免用户误读）"""
    d = d or date.today()
    ly = lunar_year_of(d)
    cny = LunarDate(ly, 1, 1).to_solar_date()
    return {
        "lunar_year": ly,
        "animal": year_zodiac(ly),
        "effective_from": cny.strftime("%Y-%m-%d"),
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
    "树": "木", "森林": "木", "竹子": "木", "竹林": "木", "花草": "木", "木头": "木",
    "水": "水", "河流": "水", "溪流": "水", "大海": "水", "雨": "水", "湖泊": "水", "瀑布": "水",
    "火": "火", "太阳": "火", "火焰": "火", "蜡烛": "火", "灯笼": "火",
    "山": "土", "土地": "土", "石头": "土", "石碑": "土", "山石": "土",
    "城墙": "土", "大地": "土",

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
            "options": ZODIAC_ORDER,
            "icon": "🐾",
            # 提醒前端：生肖表随农历年轮转，需标明当前用的是哪一年的表
            "table_info": zodiac_info(),
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


def _iter_numbers(raw):
    """
    把外部传入的号码线索统一收敛成 1-49 的整数。

    `decode_elements` 是对外 API，`numbers` / `count_numbers` 可能来自
    前端或第三方调用，值可能是 int（8）、字符串（"8"）、带空格的字符串（" 8 "）
    甚至非数字文本。原实现直接做 `1 <= n <= 49`，遇到字符串会抛
    `TypeError: '<=' not supported between instances of 'int' and 'str'`
    导致整个接口 500。这里统一转换，非法值直接跳过（不抛异常）。
    """
    if raw is None:
        return
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]
    for item in raw:
        if isinstance(item, bool):
            continue
        n = None
        if isinstance(item, int):
            n = item
        elif isinstance(item, float):
            # 8.0 视为 8；8.5 这类非整数一律忽略
            if item.is_integer():
                n = int(item)
        else:
            text = str(item).strip()
            try:
                n = int(text)
            except ValueError:
                try:
                    f = float(text)
                except ValueError:
                    continue
                if f.is_integer():
                    n = int(f)
        if n is not None and 1 <= n <= 49:
            yield n


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
        "decode_trace": [解码过程说明],
        "reasons": {号码: [该号码被命中的线索及权重]},
        "zodiac_table": {当前生效的生肖表信息}
    }
    """
    # 号码权重计数器
    score = Counter()
    # reasons[n] = 号码 n 被哪些线索命中，形如
    #   [{"dim": "生肖", "label": "龙", "weight": 3, "desc": "..."}, ...]
    # 有了它才能给用户解释「为什么推荐这个号码」，而不只是甩一个总分。
    reasons = defaultdict(list)
    trace = []
    zmap = get_zodiac_map()          # 当前农历年生效的生肖表
    zinfo = zodiac_info()

    def _add(n, w, dim, label, desc):
        """给号码 n 加权 w 分，并记下这条线索（供前端展示理由）。"""
        score[n] += w
        reasons[n].append({
            "dim": dim,
            "label": label,
            "weight": w,
            "desc": desc,
        })

    # 1~4. 生肖 / 五行 / 色波 / 方位
    #
    # 【护栏】同一维度若多个分类的号码并集覆盖全部 1-49，该维度就**被中和**了——
    # 每个号码都拿到同样的加分，等于没有信息。
    # 实测踩过三次：
    #   - 方位集齐东南西北（覆盖 49）→ 方位维度失效
    #   - 五行同时识别出木火金水土（各 10 个，合计 49）→ 五行维度同样失效
    #   - 生肖若 12 个全被识别，同样覆盖 49
    # 所以这里统一检查并集大小，覆盖满 49 就整维丢弃，并在 trace 里说明。
    def _apply_dimension(dim_name, values, mapping, weight, icon, note="", item_note=""):
        """按维度给号码加分；若该维度覆盖全部号码则整维作废。返回是否生效。"""
        hit = [v for v in values if v in mapping]
        if not hit:
            return False
        covered = set()
        for v in hit:
            covered.update(mapping[v])
        if len(covered) >= 49:
            trace.append(
                f"{icon} {dim_name}维度覆盖了全部 1-49 个号码，等同没有{dim_name}暗示，已忽略该维度"
                + (f"（{note}）" if note else "")
            )
            return False
        # evidence[维度][线索] = 该线索来自图上什么（由 vision.map_vision_to_decoder_selections 提供）
        evidence = (selections.get("evidence") or {}).get(_dim_key(dim_name), {})
        for v in hit:
            nums = mapping[v]
            descs = evidence.get(v) or []
            desc = "；".join(descs) if descs else f"{dim_name}命中：{v}"
            for n in nums:
                _add(n, weight, dim_name, v, desc)
            trace.append(f"{icon} {dim_name}【{v}】→ 号码 {nums}"
                         + (f"（{item_note}）" if item_note else ""))
        return True

    def _dim_key(dim_name):
        """维度中文名 → evidence 字典的键（生肖/五行/色波/方位）。"""
        return {"生肖": "zodiac", "五行": "wuxing", "色波": "color", "方位": "direction"}.get(
            dim_name, dim_name
        )

    _apply_dimension("生肖", selections.get("zodiac", []), zmap, 3, "🐾",
                     note=f"{zinfo['lunar_year']} {zinfo['animal']}年表",
                     item_note=f"{zinfo['lunar_year']} {zinfo['animal']}年表")
    _apply_dimension("五行", selections.get("wuxing", []), WUXING_MAP, 2, "☯️")
    _apply_dimension("色波", selections.get("color", []), COLOR_MAP, 2, "🎨")
    _apply_dimension("方位", selections.get("direction", []), DIRECTION_MAP, 1, "🧭")

    # 5. 处理关键词（自动映射）
    #
    # 用**子串匹配**而非精确匹配：AI 返回的物件名常带修饰词
    # （「红灯笼」「三只羊」「石碑上的字」），精确匹配几乎全灭。
    # 一个关键词可能同时命中多个线索（如「红灯笼」→ 灯笼=火、红=红波），全部计入。
    for kw in selections.get("keywords", []):
        matched = [k for k in ELEMENT_HINTS if k in kw]
        if not matched:
            continue
        for key in matched:
            mapped = ELEMENT_HINTS[key]
            # 判断映射到哪个维度
            if mapped in zmap:
                nums = zmap[mapped]
                for n in nums:
                    _add(n, 3, "生肖", mapped, f"图中「{kw}」指向生肖{mapped}")
                trace.append(f"🔍 关键词【{kw}】→ 生肖{mapped} → {nums}")
            elif mapped in WUXING_MAP:
                nums = WUXING_MAP[mapped]
                for n in nums:
                    _add(n, 2, "五行", mapped, f"图中「{kw}」指向五行{mapped}")
                trace.append(f"🔍 关键词【{kw}】→ 五行{mapped} → {nums}")
            elif mapped in COLOR_MAP:
                nums = COLOR_MAP[mapped]
                for n in nums:
                    _add(n, 2, "色波", mapped, f"图中「{kw}」指向{mapped}")
                trace.append(f"🔍 关键词【{kw}】→ {mapped} → {nums}")

    # 6. 处理图上直接写出的数字（强线索，权重 5）
    #    「石碑上刻着 8」这类是玄机图里最直接的号码暗示，比生肖/五行更具体。
    for n in _iter_numbers(selections.get("numbers")):
        _add(n, 5, "数字", str(n), f"图上直接出现数字「{n}」")
        trace.append(f"🔢 图上数字【{n}】→ 号码 {n}（直接暗示，权重 +5）")

    # 7. 处理数量推出的数字（弱线索，权重 2）
    #    「三盏灯笼」→ 3，间接但仍是线索。
    for n in _iter_numbers(selections.get("count_numbers")):
        _add(n, 2, "数量", str(n), f"图中元素数量为「{n}」")
        trace.append(f"🔢 数量线索【{n}】→ 号码 {n}（数量推出，权重 +2）")

    # 方位维度若因覆盖全部号码而失效，已由 _apply_dimension 写进 trace，此处不再重复

    if not score:
        # recommended 始终是 dict（main/special），避免调用方拿到 list 而崩。
        # 注意：必须保留已有 trace——否则所有维度都被护栏丢弃时，
        # 用户只能看到"未选择任何解码元素"，完全不知道发生了什么。
        return {
            "all_candidates": [],
            "recommended": {"main": [], "special": None},
            "decode_trace": trace + ["⚠️ 未选择任何解码元素"],
            "reasons": {},
            "zodiac_table": zinfo,
        }

    # 按权重排序
    sorted_candidates = sorted(score.items(), key=lambda x: x[1], reverse=True)

    # 取 Top 7（6正码 + 1特码）。
    # 六合彩是七球同机无放回摇出，**七个号码必然互不相同**，
    # 因此特码绝不能与正码重复（原实现在候选不足 7 个时回退成
    # sorted_candidates[-1]，会与正码撞号，例如「生肖马」给出正码含 49、特码也是 49）。
    top_nums = [n for n, _ in sorted_candidates[:7]]
    main = sorted(top_nums[:6])
    rest = [n for n in top_nums if n not in main]
    recommended = {
        "main": main,
        # 候选不足 7 个时宁可不给特码，也不重复正码
        "special": rest[0] if rest else None,
    }

    return {
        "all_candidates": [{"number": n, "score": s} for n, s in sorted_candidates],
        "recommended": recommended,
        "decode_trace": trace,
        # 每个号码的命中线索，按权重从高到低 —— 前端据此展示"推荐理由"
        "reasons": {
            str(n): sorted(reasons[n], key=lambda r: -r["weight"])
            for n in score
        },
        "zodiac_table": zinfo,
    }


def quick_decode(keyword):
    """
    快速解码 - 输入一个关键词，直接返回关联号码
    """
    if keyword in ELEMENT_HINTS:
        mapped = ELEMENT_HINTS[keyword]
        for source_name, source_map in [
            ("生肖", get_zodiac_map()),
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
        ("生肖", get_zodiac_map()),
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
