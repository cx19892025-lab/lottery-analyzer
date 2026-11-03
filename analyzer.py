"""
六合彩数据分析工具 - 统计分析引擎
提供频率分析、冷热号、遗漏值、奇偶比、大小比、和值分析、连号统计、尾数分布等
"""
import pandas as pd
import numpy as np
from collections import Counter
from datetime import date
from database import get_all_results
from decoder import COLOR_MAP, ZODIAC_ORDER, zodiac_of_number

NUM_RANGE = range(1, 50)  # 1-49

# 号码→波色 反查表（与解码器共用同一份口径，避免两处不一致）
COLOR_OF_NUMBER = {n: c for c, ns in COLOR_MAP.items() for n in ns}


def _load_dataframe(limit=None):
    """将开奖记录加载为 DataFrame"""
    results = get_all_results(limit)
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    return df


def _extract_all_numbers(df, include_special=True):
    """从 DataFrame 中提取所有出现的号码（平铺为一维列表）"""
    if df.empty:
        return []
    cols = [f"num{i}" for i in range(1, 7)]
    if include_special:
        cols.append("special")
    # astype(int) 避免 numpy.int64 泄漏到 JSON 响应
    return df[cols].to_numpy().ravel().astype(int).tolist()


def frequency_analysis(limit=None):
    """
    号码频率分析
    返回: {number: count} 字典，覆盖 1-49 所有号码
    """
    df = _load_dataframe(limit)
    if df.empty:
        return {}
    all_nums = _extract_all_numbers(df)
    counter = Counter(all_nums)
    # 确保 1-49 都有值
    result = {n: counter.get(n, 0) for n in NUM_RANGE}
    return result


def hot_cold_numbers(recent_n=30, top_k=10):
    """
    冷热号分析
    recent_n: 取最近N期
    top_k: 取前/后 k 个
    返回: {"hot": [(num, count), ...], "cold": [(num, count), ...]}
    """
    freq = frequency_analysis(limit=recent_n)
    if not freq:
        return {"hot": [], "cold": []}

    # 次数相同的号码按号码本身升序，保证结果可复现（回测依赖确定性）
    sorted_nums = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return {
        "hot": sorted_nums[:top_k],
        "cold": sorted_nums[-top_k:]
    }


def missing_values(limit=None):
    """
    遗漏值分析 - 每个号码已连续多少期未出现
    limit: 只统计最近 limit 期（None = 全部）
    返回: {number: missing_count}
    """
    df = _load_dataframe(limit)
    if df.empty:
        return {}

    # 按期号升序
    df = df.sort_values("period", ascending=True)
    total_periods = len(df)

    # 向量化：一次性取出每期的 7 个号码，避免逐期 iterrows 的巨额开销
    num_cols = [f"num{i}" for i in range(1, 7)] + ["special"]
    matrix = df[num_cols].to_numpy()  # shape: (期数, 7)

    result = {}
    for num in NUM_RANGE:
        # 从最近一期往回找第一个出现该号码的期，其距离即遗漏值
        hits = np.where((matrix == num).any(axis=1))[0]
        # int() 避免 numpy.int64 泄漏到 JSON 响应
        result[num] = int(total_periods - 1 - hits[-1]) if len(hits) else int(total_periods)

    return result


def odd_even_analysis(limit=None):
    """
    奇偶比分析（仅正码）
    返回每期的奇偶比分布统计
    """
    df = _load_dataframe(limit)
    if df.empty:
        return []

    ratios = []
    for _, row in df.iterrows():
        nums = [row[f"num{i}"] for i in range(1, 7)]
        odd_count = sum(1 for n in nums if n % 2 == 1)
        even_count = 6 - odd_count
        ratios.append({
            "period": row["period"],
            "odd": odd_count,
            "even": even_count,
            "ratio": f"{odd_count}:{even_count}"
        })

    # 汇总分布
    ratio_counter = Counter(r["ratio"] for r in ratios)
    return {
        "detail": ratios[:50],  # 只返回最近50期明细
        "distribution": dict(sorted(ratio_counter.items()))
    }


def big_small_analysis(limit=None):
    """
    大小比分析（1-24为小，25-49为大）
    """
    df = _load_dataframe(limit)
    if df.empty:
        return []

    ratios = []
    for _, row in df.iterrows():
        nums = [row[f"num{i}"] for i in range(1, 7)]
        big_count = sum(1 for n in nums if n >= 25)
        small_count = 6 - big_count
        ratios.append({
            "period": row["period"],
            "big": big_count,
            "small": small_count,
            "ratio": f"{big_count}:{small_count}"
        })

    ratio_counter = Counter(r["ratio"] for r in ratios)
    return {
        "detail": ratios[:50],
        "distribution": dict(sorted(ratio_counter.items()))
    }


def sum_analysis(limit=None):
    """
    和值分析 - 6个正码之和的分布
    """
    df = _load_dataframe(limit)
    if df.empty:
        return {}

    sums = []
    for _, row in df.iterrows():
        nums = [row[f"num{i}"] for i in range(1, 7)]
        total = sum(nums)
        sums.append({
            "period": row["period"],
            "sum": total
        })

    values = [s["sum"] for s in sums]
    return {
        "detail": sums[:50],
        "min": int(min(values)),
        "max": int(max(values)),
        # float() 避免 numpy.float64 泄漏到 JSON 响应
        "avg": round(float(np.mean(values)), 1),
        "median": int(np.median(values)),
        "distribution": _histogram(values, bins=10)
    }


def _histogram(values, bins=10):
    """生成直方图数据"""
    counts, edges = np.histogram(values, bins=bins)
    return [
        {"range": f"{int(edges[i])}-{int(edges[i+1])}", "count": int(counts[i])}
        for i in range(len(counts))
    ]


def tail_number_analysis(limit=None):
    """
    尾数分布（个位数 0-9）
    """
    df = _load_dataframe(limit)
    if df.empty:
        return {}

    all_nums = _extract_all_numbers(df)
    tails = [n % 10 for n in all_nums]
    counter = Counter(tails)
    return {t: counter.get(t, 0) for t in range(10)}


def consecutive_analysis(limit=None):
    """
    连号分析 - 统计每期中出现连号的情况
    """
    df = _load_dataframe(limit)
    if df.empty:
        return {}

    results = {"has_consecutive": 0, "no_consecutive": 0, "detail": []}

    for _, row in df.iterrows():
        nums = sorted([row[f"num{i}"] for i in range(1, 7)])
        consecutive_pairs = []
        for i in range(len(nums) - 1):
            if nums[i + 1] - nums[i] == 1:
                consecutive_pairs.append((nums[i], nums[i + 1]))

        if consecutive_pairs:
            results["has_consecutive"] += 1
        else:
            results["no_consecutive"] += 1

        if len(results["detail"]) < 50:
            results["detail"].append({
                "period": row["period"],
                "nums": nums,
                "consecutive": consecutive_pairs
            })

    total = results["has_consecutive"] + results["no_consecutive"]
    results["consecutive_rate"] = round(
        results["has_consecutive"] / total * 100, 1
    ) if total > 0 else 0

    return results


def special_stats(limit=None):
    """
    特码单独统计：号码频次、生肖分布、波色分布。
    生肖按各期开奖日期的农历年表换算（生肖表每年轮换，跨年不能套同一张表）。
    """
    results = get_all_results(limit)
    total = len(results)
    if total == 0:
        return {}

    freq = {n: 0 for n in NUM_RANGE}
    zodiac = Counter()
    color = Counter()

    for r in results:
        sp = int(r["special"])
        freq[sp] += 1
        zodiac[zodiac_of_number(sp, date.fromisoformat(r["draw_date"]))] += 1
        color[COLOR_OF_NUMBER[sp]] += 1

    ranked = sorted(NUM_RANGE, key=lambda n: (-freq[n], n))
    return {
        "total": total,
        "frequency": freq,
        "expected_per_number": round(total / 49, 2),
        "top_numbers": [[n, freq[n]] for n in ranked[:5]],
        "bottom_numbers": [[n, freq[n]] for n in ranked[-5:]][::-1],
        "zodiac": {a: zodiac.get(a, 0) for a in ZODIAC_ORDER},
        "zodiac_pct": {a: round(zodiac.get(a, 0) / total * 100, 2) for a in ZODIAC_ORDER},
        "color": {c: color.get(c, 0) for c in ("红波", "蓝波", "绿波")},
        "color_pct": {c: round(color.get(c, 0) / total * 100, 2) for c in ("红波", "蓝波", "绿波")},
        "color_of_number": COLOR_OF_NUMBER,
    }


def main_zodiac_stats(limit=None):
    """
    正码（6 个主号）的生肖分布。
    每期按该期开奖日期的生肖表换算，再做全窗口汇总。
    """
    results = get_all_results(limit)
    if not results:
        return {}

    counts = Counter()
    for r in results:
        d = date.fromisoformat(r["draw_date"])
        for i in range(1, 7):
            counts[zodiac_of_number(int(r[f"num{i}"]), d)] += 1

    total_numbers = 6 * len(results)
    return {
        "total_numbers": total_numbers,
        "counts": {a: counts.get(a, 0) for a in ZODIAC_ORDER},
        "pct": {a: round(counts.get(a, 0) / total_numbers * 100, 2) for a in ZODIAC_ORDER},
        # 12 生肖均分时的期望值，供前端画参考线
        "expected": round(total_numbers / 12, 2),
    }


def smart_recommend(strategy="balanced", limit=None, recent_n=30):
    """
    智能选号推荐
    策略:
      - "hot": 偏向热号
      - "cold": 偏向冷号（博冷）
      - "balanced": 热冷均衡
      - "random": 纯随机
    limit: 只使用最近 limit 期数据做分析（None = 全部）。
           **回测时必须传入**，否则会看到未来数据，回测结果失真。
    recent_n: 冷热号统计窗口
    返回: {"main": [6个正码], "special": 特码, "strategy": 策略说明}
    """
    import random as rnd

    if strategy == "random":
        all_nums = rnd.sample(range(1, 50), 7)
        return {
            "main": sorted(all_nums[:6]),
            "special": all_nums[6],
            "strategy": "纯随机选号",
            "reason": "完全随机，每个号码概率相等"
        }

    freq = frequency_analysis(limit)
    miss = missing_values(limit)
    hc = hot_cold_numbers(recent_n=recent_n, top_k=15)

    if strategy == "hot":
        # 从热号池中加权随机选
        hot_nums = [n for n, _ in hc["hot"]]
        pool = hot_nums if len(hot_nums) >= 7 else list(range(1, 50))
        selected = rnd.sample(pool, min(7, len(pool)))
        while len(selected) < 7:
            extra = rnd.choice([n for n in range(1, 50) if n not in selected])
            selected.append(extra)
        return {
            "main": sorted(selected[:6]),
            "special": selected[6],
            "strategy": "热号优先",
            "reason": f"从近30期高频号中选取：{hot_nums[:6]}"
        }

    elif strategy == "cold":
        # 从冷号/高遗漏号中选
        sorted_miss = sorted(miss.items(), key=lambda x: x[1], reverse=True)
        cold_nums = [n for n, _ in sorted_miss[:15]]
        pool = cold_nums if len(cold_nums) >= 7 else list(range(1, 50))
        selected = rnd.sample(pool, min(7, len(pool)))
        while len(selected) < 7:
            extra = rnd.choice([n for n in range(1, 50) if n not in selected])
            selected.append(extra)
        return {
            "main": sorted(selected[:6]),
            "special": selected[6],
            "strategy": "冷号博回",
            "reason": f"选取高遗漏值号码，期待回补"
        }

    else:  # balanced
        # 3热 + 2冷 + 2随机
        hot_nums = [n for n, _ in hc["hot"][:10]]
        cold_nums = [n for n, _ in hc["cold"][:10]]

        selected = []
        selected += rnd.sample(hot_nums, min(3, len(hot_nums)))
        remaining_cold = [n for n in cold_nums if n not in selected]
        selected += rnd.sample(remaining_cold, min(2, len(remaining_cold)))

        remaining_all = [n for n in range(1, 50) if n not in selected]
        selected += rnd.sample(remaining_all, max(0, 7 - len(selected)))

        return {
            "main": sorted(selected[:6]),
            "special": selected[6],
            "strategy": "均衡策略",
            "reason": "3个热号 + 2个冷号 + 2个随机号，攻守兼备"
        }


def get_dashboard_data(window=500):
    """
    获取仪表盘汇总数据（一次性返回所有分析结果）
    window: 统计窗口，只分析最近 N 期（真实数据 4400+ 期，全量统计太慢且
            远期号码对选号参考价值有限）。None/0 表示全量。
    total_periods 始终返回库内全部期数，前端可区分"已加载"与"统计窗口"。
    """
    limit = int(window) if window else None
    return {
        "window": limit,
        "frequency": frequency_analysis(limit),
        "hot_cold": hot_cold_numbers(),
        "missing": missing_values(limit),
        "odd_even": odd_even_analysis(limit),
        "big_small": big_small_analysis(limit),
        "sum": sum_analysis(limit),
        "tail": tail_number_analysis(limit),
        "consecutive": consecutive_analysis(limit),
        "special_stats": special_stats(limit),
        "main_zodiac": main_zodiac_stats(limit),
        "total_periods": len(get_all_results()),
    }
