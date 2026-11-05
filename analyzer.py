"""
六合彩数据分析工具 - 统计分析引擎
提供频率分析、冷热号、遗漏值、奇偶比、大小比、和值分析、连号统计、尾数分布等
"""
import pandas as pd
import numpy as np
from collections import Counter
from datetime import date
from database import get_all_results, get_raw_results, STATS_MIN_PERIOD
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


def hot_cold_numbers(recent_n=None, top_k=10, limit=None):
    """
    冷热号分析（按出现次数排序取前后各 k 个）。

    ⚠️ 窗口口径（V1.8.1 修正）：
      这里曾经默认 recent_n=30，而仪表盘的「统计窗口」选的是 100~1000 期，
      结果冷热号卡片**永远只看最近 30 期**，与页面上其他卡片口径不一致，
      用户看到"两个期数不一样"却无从判断哪个生效。

      现在改为：优先用 limit（跟随仪表盘统计窗口），
      未传 limit 时才退回 recent_n（单独调用本函数的场景）。
    """
    window = limit if limit else recent_n
    freq = frequency_analysis(limit=window)
    if not freq:
        return {"hot": [], "cold": [], "window": window}

    # 次数相同的号码按号码本身升序，保证结果可复现（回测依赖确定性）
    sorted_nums = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return {
        "hot": sorted_nums[:top_k],
        "cold": sorted_nums[-top_k:],
        "window": window,
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


def missing_leaderboard(top_k=10):
    """
    连续不出期数实时榜单（前 K 名）。

    这是"追冷号"玩法的入口：列出当前最久没出的号码。
    同时给出每个号码**在历史上处于相同遗漏档位时，下一期实际开出的概率**，
    让用户自己判断"追冷号"值不值得。

    注意：榜单本身只是排序，不含任何预测。冷热与下一期概率无关，
    这一点由同档位的历史命中率直接体现（应恒为 ~14.29%）。
    """
    results = get_all_results()          # 降序：results[0] 最新
    if not results:
        return {"total_periods": 0, "board": []}

    asc = list(reversed(results))
    total = len(asc)

    # 每个号码：当前遗漏 + 历史同档位命中率
    rows = []
    for n in NUM_RANGE:
        seq = []
        for r in asc:
            hit = (n in [int(r[f"num{i}"]) for i in range(1, 7)]
                   or int(r["special"]) == n)
            seq.append(1 if hit else 0)

        # 当前遗漏
        cur = 0
        for v in reversed(seq):
            if v == 0:
                cur += 1
            else:
                break

        # 历史上"已连续未出 >= cur 期"时，下一期开出的次数
        # （即：处在当前这种"很久没出"的状态下，下一期命中的历史频率）
        same_tot = same_hit = 0
        miss = 0
        for v in seq:
            if miss >= cur and cur > 0:
                same_tot += 1
                same_hit += v
            if v == 0:
                miss += 1
            else:
                miss = 0

        rows.append({
            "number": n,
            "missing": cur,
            # 历史同档位（遗漏 >= 当前值）时下一期的实际命中率
            "same_state_rate": round(same_hit / same_tot * 100, 2) if same_tot >= 30 else None,
            "same_state_samples": same_tot,
            "total_hits": sum(seq),
            "zodiac": zodiac_of_number(n, date.today()),
            "color": COLOR_OF_NUMBER[n],
        })

    rows.sort(key=lambda x: (-x["missing"], x["number"]))
    return {
        "total_periods": total,
        "latest_period": results[0]["period"],
        "latest_date": results[0]["draw_date"],
        "expected_rate": round(7 / 49 * 100, 2),
        "board": rows[:top_k],
        "all": rows,
    }


def zodiac_missing_leaderboard(top_k=10):
    """
    生肖连续不出期数榜单 —— 正码与特码**分开统计**。

    为什么要分开：
      正码每期开 6 个，某个生肖出现的机会大得多（生肖通常含 4~5 个号码，
      每期 6 个正码里几乎必然覆盖多个生肖）；
      特码每期只开 1 个，某个生肖不出的概率高得多。
      两者概率差一个数量级，混在一起算"连续不出"没有意义。

    生肖表按**农历年**轮换，因此每期都用**该期自己的开奖日期**换算
    （见 zodiac_of_number），不能拿今天的表套历史数据。

    返回每个生肖的：
      - 当前连续多少期没在正码 / 特码里出现
      - 理论期望（该生肖号码数 × 每期位置数 / 49）
      - 历史同档位命中率（处在同样久没出的状态时，下一期出现的频率）
    """
    results = get_all_results()
    if not results:
        return {"total_periods": 0, "main": [], "special": []}

    asc = list(reversed(results))
    total = len(asc)

    # 每期每个生肖是否出现（正码 / 特码 分开）
    main_seq = {a: [] for a in ZODIAC_ORDER}
    spec_seq = {a: [] for a in ZODIAC_ORDER}
    # 该生肖当期的号码数（生肖表随年份变化，号码数可能不同）
    zodiac_size = {a: 0 for a in ZODIAC_ORDER}

    for r in asc:
        d = date.fromisoformat(r["draw_date"])
        main_z = set(zodiac_of_number(int(r[f"num{i}"]), d) for i in range(1, 7))
        spec_z = zodiac_of_number(int(r["special"]), d)
        for a in ZODIAC_ORDER:
            main_seq[a].append(1 if a in main_z else 0)
            spec_seq[a].append(1 if a == spec_z else 0)

    # 用最后一期的生肖表统计各生肖号码数（用于算期望）
    last_d = date.fromisoformat(results[0]["draw_date"])
    from decoder import get_zodiac_map
    zmap = get_zodiac_map(last_d)
    for a in ZODIAC_ORDER:
        zodiac_size[a] = len(zmap.get(a, []))

    def build(seq_map, positions, label):
        rows = []
        for a in ZODIAC_ORDER:
            seq = seq_map[a]
            # 当前连续未出
            cur = 0
            for v in reversed(seq):
                if v == 0:
                    cur += 1
                else:
                    break

            # 历史同档位命中率（遗漏 >= 当前值时，下一期出现频率）
            same_tot = same_hit = 0
            miss = 0
            for v in seq:
                if cur > 0 and miss >= cur:
                    same_tot += 1
                    same_hit += v
                miss = miss + 1 if v == 0 else 0

            # 理论单期出现概率：该生肖号码数 × 位置数 / 49
            p_theory = zodiac_size[a] * positions / 49

            rows.append({
                "zodiac": a,
                "missing": cur,
                "numbers": zodiac_size[a],
                "expected_pct": round(p_theory * 100, 2),
                # 历史同档位命中率：衡量"欠久了会不会补"
                "same_state_rate": (round(same_hit / same_tot * 100, 2)
                                    if same_tot >= 30 else None),
                "same_state_samples": same_tot,
                "total_hits": sum(seq),
                "expected_hits": round(total * p_theory, 1),
            })

        rows.sort(key=lambda x: (-x["missing"], x["zodiac"]))
        return rows

    main_rows = build(main_seq, 6, "正码")
    spec_rows = build(spec_seq, 1, "特码")

    return {
        "total_periods": total,
        "latest_period": results[0]["period"],
        "latest_date": results[0]["draw_date"],
        "zodiac_size": zodiac_size,
        "main": main_rows,
        "special": spec_rows,
        "main_top": main_rows[:top_k],
        "special_top": spec_rows[:top_k],
    }



def cold_chase_backtest(top_k=10, min_missing=0, max_periods=None):
    """
    验证「追冷号」策略：每期押"当前最久没出的 K 个号"，看命中率。

    与 smart_recommend 不同，这里不挑号码、不做任何优化，
    就是**机械地照榜单下注**——目的正是检验这个直觉本身。

    返回每期的命中情况与汇总命中率，和理论值 14.29% 对比。
    """
    results = get_all_results()          # 降序
    if not results:
        return {"periods": 0}

    asc = list(reversed(results))
    total = len(asc)
    start = max(60, total - int(max_periods)) if max_periods else 60

    hits = 0
    played = 0
    detail = []
    for t in range(start, total):
        # 用第 t 期**之前**的历史算遗漏（防未来数据泄露）
        window = asc[:t]
        missing = {}
        for n in NUM_RANGE:
            cur = 0
            for r in reversed(window):
                if (n in [int(r[f"num{i}"]) for i in range(1, 7)]
                        or int(r["special"]) == n):
                    break
                cur += 1
            missing[n] = cur

        picks = sorted(missing, key=lambda n: (-missing[n], n))[:top_k]
        picks = [n for n in picks if missing[n] >= min_missing]
        if not picks:
            continue

        actual = asc[t]
        drawn = set(int(actual[f"num{i}"]) for i in range(1, 7))
        drawn.add(int(actual["special"]))

        # 命中数：K 个号里有几个开出来了
        hit_nums = [n for n in picks if n in drawn]
        played += 1
        hits += len(hit_nums)

        if len(detail) < 200:
            detail.append({
                "period": actual["period"],
                "date": actual["draw_date"],
                "picks": picks,
                "hits": hit_nums,
            })

    # 每期押 K 个号：命中数 / (期数 × K) 即单号命中率
    rate = hits / (played * top_k) * 100 if played else 0
    return {
        "top_k": top_k,
        "periods": played,
        "total_bets": played * top_k,
        "total_hits": hits,
        "hit_rate": round(rate, 2),
        "expected_rate": round(7 / 49 * 100, 2),
        "detail": detail[-60:],
    }


def _histogram(values, bins=10):
    """生成直方图数据"""
    counts, edges = np.histogram(values, bins=bins)
    return [
        {"range": f"{int(edges[i])}-{int(edges[i+1])}", "count": int(counts[i])}
        for i in range(len(counts))
    ]


# ---------------------------------------------------------------------------
# 说明（V1.6 起）：
#   本工具的玩法是**猜单个号码**——猜特码（赔率高）或猜正码（赔率低），
#   猜中一个就有奖励，可以反复下注。因此统计口径只关心"某个号码会不会出"。
#
#   原先的 和值 / 连号 / 奇偶比 / 大小比 / 尾数 都是"7 个号码合起来"的形态统计，
#   与单号投注无关，已于 V1.6 移除（函数保留历史记录见 DEVLOG）。
#   保留并强化的都是"单个号码"维度：频次、冷热、遗漏、生肖、波色。
# ---------------------------------------------------------------------------


def main_number_stats(limit=None, recent_n=30):
    """
    正码（6 个主号）的**单号**统计 —— 猜正码玩法的核心视图。

    与 frequency_analysis 的区别：
      frequency_analysis 把正码+特码混在一起数（用于看整体冷热），
      这里**只统计正码**，因为猜正码与猜特码是两个独立玩法、赔率不同。

    返回每个号码的：出现次数、占比、理论期望、偏离度、当前遗漏、近 N 期次数。
    """
    results = get_all_results(limit)
    total = len(results)
    if total == 0:
        return {}

    counts = Counter()
    recent_counts = Counter()
    last_seen = {}          # 号码 -> 距今多少期没出（遗漏）
    recent_window = results[:recent_n]

    for idx, r in enumerate(results):
        for i in range(1, 7):
            n = int(r[f"num{i}"])
            counts[n] += 1
            if n not in last_seen:
                last_seen[n] = idx

    for r in recent_window:
        for i in range(1, 7):
            recent_counts[int(r[f"num{i}"])] += 1

    total_draws = total * 6                 # 正码总出现次数
    expected = total_draws / 49             # 每个号码的理论期望
    expected_pct = 6 / 49 * 100             # ≈ 12.24%

    rows = []
    for n in NUM_RANGE:
        c = counts.get(n, 0)
        rows.append({
            "number": n,
            "count": c,
            "pct": round(c / total_draws * 100, 2) if total_draws else 0,
            "expected": round(expected, 1),
            # 偏离度：实际/期望，1.0 = 完全符合理论
            "ratio": round(c / expected, 3) if expected else 0,
            "missing": last_seen.get(n, total),   # 从未出现则记为全部期数
            "recent": recent_counts.get(n, 0),
        })

    return {
        "total_periods": total,
        "total_draws": total_draws,
        "expected_per_number": round(expected, 1),
        "expected_pct": round(expected_pct, 2),
        "numbers": rows,
        # 按出现次数排序，方便直接看"哪些号码出得多"
        "hottest": sorted(rows, key=lambda x: (-x["count"], x["number"]))[:10],
        "coldest": sorted(rows, key=lambda x: (x["count"], x["number"]))[:10],
        # 遗漏最久（最久没出）的号码
        "most_missing": sorted(rows, key=lambda x: (-x["missing"], x["number"]))[:10],
    }


def number_attributes():
    """
    号码属性速查表：每个号码的生肖、波色、五行、奇偶、大小。

    用途：选定号码时一眼看到它的全部属性，便于按"生肖/波色"筛选下注。
    生肖随农历年轮换，这里返回**当前生效**的表，并附带生效日期供前端标注。
    """
    from decoder import get_zodiac_map, WUXING_MAP, zodiac_info

    zmap = get_zodiac_map()
    num_to_zodiac = {n: a for a, ns in zmap.items() for n in ns}
    num_to_wuxing = {n: w for w, ns in WUXING_MAP.items() for n in ns}
    num_to_color = COLOR_OF_NUMBER

    rows = []
    for n in NUM_RANGE:
        rows.append({
            "number": n,
            "zodiac": num_to_zodiac.get(n, ""),
            "color": num_to_color.get(n, ""),
            "wuxing": num_to_wuxing.get(n, ""),
            "odd_even": "奇" if n % 2 else "偶",
            "big_small": "大" if n >= 25 else "小",
        })

    info = zodiac_info()
    return {
        "numbers": rows,
        # 生肖表按农历年轮换，必须让用户知道当前用的是哪一年的表
        "zodiac_lunar_year": info["lunar_year"],
        "zodiac_animal": info["animal"],
        "zodiac_effective_from": info["effective_from"],
    }


def special_stats(limit=None):
    """
    特码专项统计 —— 猜特码玩法（赔率最高）的核心视图。

    特码每期只开 1 个，与正码是**两个独立玩法**，因此单独成表：
    号码频次与偏离度、当前遗漏、生肖分布、波色分布。

    生肖按各期开奖日期的农历年表换算（生肖表每年轮换，跨年不能套同一张表）。
    """
    results = get_all_results(limit)
    total = len(results)
    if total == 0:
        return {}

    freq = {n: 0 for n in NUM_RANGE}
    zodiac = Counter()
    color = Counter()
    last_seen = {}

    for idx, r in enumerate(results):
        sp = int(r["special"])
        freq[sp] += 1
        zodiac[zodiac_of_number(sp, date.fromisoformat(r["draw_date"]))] += 1
        color[COLOR_OF_NUMBER[sp]] += 1
        if sp not in last_seen:
            last_seen[sp] = idx

    ranked = sorted(NUM_RANGE, key=lambda n: (-freq[n], n))
    expected = total / 49          # 每个号码的理论期望次数
    expected_pct = 1 / 49 * 100    # ≈ 2.04%

    # 每个号码的明细：次数、占比、偏离度、遗漏
    rows = []
    for n in NUM_RANGE:
        c = freq[n]
        rows.append({
            "number": n,
            "count": c,
            "pct": round(c / total * 100, 2),
            "expected": round(expected, 2),
            # 偏离度：实际/期望。长期应趋近 1.0，明显偏离多为随机波动
            "ratio": round(c / expected, 3) if expected else 0,
            "missing": last_seen.get(n, total),
            "zodiac": zodiac_of_number(n, date.today()),
            "color": COLOR_OF_NUMBER[n],
        })

    return {
        "total": total,
        "frequency": freq,
        "expected_per_number": round(expected, 2),
        "expected_pct": round(expected_pct, 2),
        "top_numbers": [[n, freq[n]] for n in ranked[:5]],
        "bottom_numbers": [[n, freq[n]] for n in ranked[-5:]][::-1],
        "numbers": rows,
        # 遗漏最久的特码（最久没开出的）
        "most_missing": sorted(rows, key=lambda x: (-x["missing"], x["number"]))[:10],
        "zodiac": {a: zodiac.get(a, 0) for a in ZODIAC_ORDER},
        "zodiac_pct": {a: round(zodiac.get(a, 0) / total * 100, 2) for a in ZODIAC_ORDER},
        # 12 生肖均分时的期望占比（约 8.33%），供前端画参考线
        "zodiac_expected_pct": round(100 / 12, 2),
        "color": {c: color.get(c, 0) for c in ("红波", "蓝波", "绿波")},
        "color_pct": {c: round(color.get(c, 0) / total * 100, 2) for c in ("红波", "蓝波", "绿波")},
        # 波色号码数量不等（红17/蓝16/绿16），期望占比因此不同
        "color_expected_pct": {
            "红波": round(17 / 49 * 100, 2),
            "蓝波": round(16 / 49 * 100, 2),
            "绿波": round(16 / 49 * 100, 2),
        },
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


def zodiac_hot_cold(limit=None, recent_n=30, top_k=3):
    """
    生肖冷热统计。

    重要：生肖表按**农历年**轮换，同一个号码在不同年份属于不同生肖，
    因此必须用**每期自己的开奖日期**去换算，不能拿今天的表套历史数据。

    返回 {
      "counts": {生肖: 次数},        # 窗口内各生肖出现次数（正码+特码）
      "hot": [(生肖, 次数), ...],     # 出现最多的
      "cold": [(生肖, 次数), ...],    # 出现最少的
      "window": 实际统计期数,
      "expected": 每个生肖的理论期望次数,
    }
    """
    results = get_all_results(recent_n if limit is None else min(recent_n, limit))
    if not results:
        return {"counts": {}, "hot": [], "cold": [], "window": 0, "expected": 0}

    counts = Counter()
    for r in results:
        d = date.fromisoformat(r["draw_date"])
        for i in range(1, 7):
            counts[zodiac_of_number(int(r[f"num{i}"]), d)] += 1
        counts[zodiac_of_number(int(r["special"]), d)] += 1

    # 每期 7 个号码，12 生肖均分
    expected = round(len(results) * 7 / 12, 2)
    ranked = sorted(ZODIAC_ORDER, key=lambda a: (-counts.get(a, 0), a))
    return {
        "counts": {a: counts.get(a, 0) for a in ZODIAC_ORDER},
        "hot": [(a, counts.get(a, 0)) for a in ranked[:top_k]],
        "cold": [(a, counts.get(a, 0)) for a in ranked[-top_k:]][::-1],
        "window": len(results),
        "expected": expected,
    }


def _numbers_of_zodiac(animal, d):
    """某生肖在指定日期生效的号码列表"""
    from decoder import get_zodiac_map
    return list(get_zodiac_map(d).get(animal, []))


def smart_recommend(strategy="balanced", limit=None, recent_n=30):
    """
    智能选号推荐
    策略:
      - "hot": 偏向热号
      - "cold": 偏向冷号（博冷）
      - "balanced": 热冷均衡
      - "random": 纯随机
      - "zodiac_hot": 热生肖（近期出现最多的生肖所辖号码）
      - "zodiac_cold": 冷生肖（近期出现最少的生肖所辖号码）
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

    # 生肖策略：先看历史里哪个生肖最热/最冷，再从该生肖的号码池里选
    if strategy in ("zodiac_hot", "zodiac_cold"):
        zc = zodiac_hot_cold(limit=limit, recent_n=recent_n, top_k=3)
        if not zc["hot"]:
            # 历史不足，退化为纯随机，保证回测不中断
            all_nums = rnd.sample(range(1, 50), 7)
            return {
                "main": sorted(all_nums[:6]),
                "special": all_nums[6],
                "strategy": "生肖策略（数据不足，退化为随机）",
                "reason": "历史样本不足，无法统计生肖冷热"
            }

        # 取最热/最冷的 2 个生肖，合并其号码池
        picked = zc["hot"] if strategy == "zodiac_hot" else zc["cold"]
        animals = [a for a, _ in picked[:2]]

        # 生肖表按农历年轮换：用**历史窗口内最新一期**的开奖日期取表。
        #
        # 注意两点：
        #  1. 不要用 get_all_results(1)：那返回的是**全库最新**一期，
        #     回测时属于"未来数据"，会造成泄露。
        #  2. get_all_results 是 ORDER BY period DESC（新的在前），
        #     所以窗口内最新一期是 hist[0]，不是 hist[-1]。
        hist = get_all_results(limit)
        ref_date = date.fromisoformat(hist[0]["draw_date"]) if hist else date.today()

        pool = []
        for a in animals:
            for n in _numbers_of_zodiac(a, ref_date):
                if n not in pool:
                    pool.append(n)

        if len(pool) < 7:
            # 生肖号码池不足 7 个（正常情况 4~5 个/生肖，两个生肖约 8~10 个）
            extra = [n for n in range(1, 50) if n not in pool]
            rnd.shuffle(extra)
            pool += extra[: 7 - len(pool)]

        selected = rnd.sample(pool, min(7, len(pool)))
        while len(selected) < 7:
            extra = rnd.choice([n for n in range(1, 50) if n not in selected])
            selected.append(extra)

        label = "热生肖" if strategy == "zodiac_hot" else "冷生肖"
        detail = "、".join(f"{a}({c}次)" for a, c in picked[:2])
        return {
            "main": sorted(selected[:6]),
            "special": selected[6],
            "strategy": f"{label}优先",
            "reason": f"近{recent_n}期{label}：{detail}，从这些生肖的号码中选取"
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


def number_tracker(number, limit=None):
    """
    单个号码的跟踪分析 —— 回答"它多久没出了，还该不该等"。

    用户关心的核心问题：「连续 N 期没出，是不是快出了？」
    这个函数同时给出**两个视角**，正是这个问题的两面：

      视角一（单期独立）：下一期出的概率恒为 7/49 = 14.29%，
                        与已遗漏多少期**无关**。
      视角二（打包未来）：未来 K 期内至少出一次的概率随 K 增大而升高，
                        这才是"迟早会出"的真实来源。

    再叠加**年度分布**：每号每年的出现次数应落在理论区间内，
    用来判断"今年这个号偏少"是否属于正常波动。

    返回结构见下方 return。
    """
    import math

    results = get_all_results(limit)
    total = len(results)
    if total == 0 or not (1 <= number <= 49):
        return {}

    # ---------- 1. 出现序列（按期号升序，便于算遗漏） ----------
    asc = list(reversed(results))
    seq = []
    for r in asc:
        hit = (number in [int(r[f"num{i}"]) for i in range(1, 7)]
               or int(r["special"]) == number)
        seq.append(1 if hit else 0)

    total_hits = sum(seq)
    p = 7 / 49

    # ---------- 2. 当前遗漏 ----------
    current_missing = 0
    for v in reversed(seq):
        if v == 0:
            current_missing += 1
        else:
            break

    # ---------- 3. 历史遗漏段（把"连续不出"当整体看） ----------
    runs = []
    cur = 0
    for v in seq:
        if v == 0:
            cur += 1
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)

    runs_sorted = sorted(runs)
    longest = max(runs) if runs else 0
    # 当前这段在历史中处于什么水平（百分位）
    pct = (sum(1 for r in runs if r <= current_missing) / len(runs) * 100) if runs else 0

    # ---------- 4. 续期概率曲线：已遗漏 k 期 → 下一期仍不出 ----------
    # 理论恒为 q；实际值由数据统计得出，供对照
    q = 1 - p
    bucket_tot = Counter()
    bucket_cont = Counter()
    miss = 0
    for v in seq:
        bucket_tot[miss] += 1
        if v == 0:
            bucket_cont[miss] += 1
            miss += 1
        else:
            miss = 0

    renew_curve = []
    for k in range(0, min(41, longest + 1)):
        t = bucket_tot.get(k, 0)
        if t >= 30:
            renew_curve.append({
                "missing": k,
                "observed": round(bucket_cont[k] / t, 4),
                "theory": round(q, 4),
                "samples": t,
            })

    # ---------- 5. "未来 K 期内至少出一次" ----------
    horizon = []
    for k in [1, 5, 10, 20, 30, 50, 100]:
        horizon.append({
            "periods": k,
            "prob": round((1 - q ** k) * 100, 4),
        })

    # ---------- 6. 年度分布 ----------
    by_year = {}
    for r in asc:
        by_year.setdefault(r["draw_date"][:4], []).append(r)

    yearly = []
    for y in sorted(by_year):
        rs = by_year[y]
        n = len(rs)
        if n < 20:
            continue
        cnt = 0
        for r in rs:
            if (number in [int(r[f"num{i}"]) for i in range(1, 7)]
                    or int(r["special"]) == number):
                cnt += 1
        exp = n * p
        sd = math.sqrt(n * p * q)
        yearly.append({
            "year": y,
            "periods": n,
            "count": cnt,
            "expected": round(exp, 1),
            "lo": round(max(0, exp - 1.96 * sd), 1),
            "hi": round(exp + 1.96 * sd, 1),
            # 是否落在 95% 正常波动区间内
            "normal": (exp - 1.96 * sd) <= cnt <= (exp + 1.96 * sd),
        })

    # ---------- 7. 续期曲线的合并版本（样本更多，线更稳） ----------
    # 单档样本太少时（默认窗口 500 期，每档只有几十个），曲线会剧烈抖动，
    # 反而看不出"平线"这个关键结论。这里把相邻档位合并成更大的桶。
    #
    # 注意：续期曲线必须用**全历史**算，否则窗口一小就只剩两三个点，
    # 根本画不出"平线"这个核心结论（而它恰恰是本功能最想展示的东西）。
    q_tot = Counter()
    q_cont = Counter()
    q_miss = 0
    for r in list(reversed(get_all_results())):
        hit = (number in [int(r[f"num{i}"]) for i in range(1, 7)]
               or int(r["special"]) == number)
        q_tot[q_miss] += 1
        if not hit:
            q_cont[q_miss] += 1
            q_miss += 1
        else:
            q_miss = 0

    merged = []
    step = 3
    k = 0
    while k <= max(q_tot) if q_tot else False:
        t = sum(q_tot.get(i, 0) for i in range(k, k + step))
        c_ = sum(q_cont.get(i, 0) for i in range(k, k + step))
        if t >= 100:
            merged.append({
                "missing": k,
                "label": f"{k}-{k+step-1}",
                "observed": round(c_ / t, 4),
                "theory": round(q, 4),
                "samples": t,
            })
        k += step

    # 全历史单档（样本够大时也可展示）
    renew_all = []
    for k in sorted(q_tot):
        if q_tot[k] >= 100:
            renew_all.append({
                "missing": k,
                "observed": round(q_cont[k] / q_tot[k], 4),
                "theory": round(q, 4),
                "samples": q_tot[k],
            })

    # ---------- 8. 全历史年度分布（不受统计窗口限制） ----------
    # "以一年为周期看波动"是长期问题，用全部历史才有意义。
    all_results = get_all_results()
    ay = {}
    for r in all_results:
        ay.setdefault(r["draw_date"][:4], []).append(r)
    yearly_all = []
    for y in sorted(ay):
        rs = ay[y]
        n = len(rs)
        if n < 20:
            continue
        cnt = sum(1 for r in rs
                  if number in [int(r[f"num{i}"]) for i in range(1, 7)]
                  or int(r["special"]) == number)
        exp = n * p
        sd = math.sqrt(n * p * q)
        yearly_all.append({
            "year": y, "periods": n, "count": cnt,
            "expected": round(exp, 1),
            "lo": round(max(0, exp - 1.96 * sd), 1),
            "hi": round(exp + 1.96 * sd, 1),
            "normal": (exp - 1.96 * sd) <= cnt <= (exp + 1.96 * sd),
        })

    return {
        "number": number,
        "total_periods": total,
        "total_hits": total_hits,
        "expected_hits": round(total * p, 1),
        "single_period_prob": round(p * 100, 2),      # 14.29%
        "current_missing": current_missing,
        # 当前遗漏在历史所有遗漏段中的百分位：越高说明"越久没出"
        "missing_percentile": round(pct, 1),
        "longest_missing": longest,
        "avg_missing": round(sum(runs) / len(runs), 1) if runs else 0,
        "runs_count": len(runs),
        "renew_curve": renew_curve,
        "renew_merged": merged,
        "renew_all": renew_all,
        "horizon": horizon,
        "yearly": yearly,
        "yearly_all": yearly_all,
        "zodiac": zodiac_of_number(number, date.today()),
        "color": COLOR_OF_NUMBER[number],
    }


def get_dashboard_data(window=500):
    """
    获取仪表盘汇总数据（一次性返回所有分析结果）

    window: 统计窗口，只分析最近 N 期（真实数据 4400+ 期，全量统计太慢且
            远期号码对选号参考价值有限）。None/0 表示全量。

    total_periods / stats_periods 的区别：
      total_periods  库内**全部**原始期数（含 1993~2002 那段数据缺失期）
      stats_periods  实际参与统计的期数（已排除缺失期）
    前端据此提示用户"为什么统计基数小于总期数"。

    V1.6 起口径调整：玩法是猜**单个号码**（特码/正码），
    因此只保留单号维度统计，移除了和值/连号/奇偶比/大小比/尾数
    这些"7 个号码合起来"的形态统计。

    V1.6.1：排除 STATS_MIN_PERIOD（2002053）之前的缺失数据，
    否则 48/49 号会被严重低估（详见 database.STATS_MIN_PERIOD 说明）。
    """
    limit = int(window) if window else None
    stats_rows = get_all_results()
    return {
        "window": limit,
        # —— 单号维度：整体频率与冷热（正码+特码混合，用于看全局）——
        "frequency": frequency_analysis(limit),
        "hot_cold": hot_cold_numbers(limit=limit),
        "missing": missing_values(limit),
        # —— 正码单号专项（猜正码玩法）——
        "main_numbers": main_number_stats(limit),
        # —— 特码专项（猜特码玩法，赔率最高，单独成表）——
        "special_stats": special_stats(limit),
        # —— 生肖 / 波色（按生肖、波色下注时的依据）——
        "main_zodiac": main_zodiac_stats(limit),
        "attributes": number_attributes(),
        # 统计口径说明：前端用它提示"总期数 vs 参与统计期数"
        "total_periods": len(get_raw_results()),
        "stats_periods": len(stats_rows),
        "stats_min_period": STATS_MIN_PERIOD,
    }
