"""
六合彩数据分析工具 - 历史命中率回测引擎

对 analyzer.smart_recommend() 的四种选号策略做**无未来数据泄露**的历史回测：
对第 i 期，只用前 i-1 期数据生成推荐，再与该期真实开奖结果比对。

命中定义（业界口径）：
  - 正码命中：推荐的 6 个正码中，落在该期 6 个正码内的个数（0-6）
  - 特码命中：推荐的特码 == 该期特码（0 或 1）
  - 任意命中：推荐号码（7 个）落在该期 7 个开出号码（含特码）内的个数（0-7）

注意：六合彩开奖为独立随机事件。本回测用于**验证策略是否真的比随机更有优势**，
而非用于预测。若各策略命中率无显著差异，说明"热号/冷号"等说法没有统计依据。
"""
import random
from database import get_all_results, set_history_cutoff

STRATEGIES = ["balanced", "hot", "cold", "random", "zodiac_hot", "zodiac_cold"]

STRATEGY_NAMES = {
    "balanced": "⚖️ 均衡策略",
    "hot": "🔥 热号优先",
    "cold": "❄️ 冷号博回",
    "random": "🎰 纯随机",
    "zodiac_hot": "🐲 热生肖",
    "zodiac_cold": "🐉 冷生肖",
}

# 回测开始前至少需要多少期历史数据做分析
MIN_HISTORY = 30


def _get_periods_ascending():
    """按期号升序返回全部开奖记录"""
    return sorted(get_all_results(), key=lambda r: r["period"])


def _draw_numbers(record):
    """该期开出的 7 个号码（6 正码 + 特码）"""
    return [record[f"num{i}"] for i in range(1, 7)] + [record["special"]]


def _evaluate(prediction, actual):
    """比对一次推荐与该期真实结果，返回命中明细"""
    pred_main = set(prediction["main"])
    actual_main = set(actual[f"num{i}"] for i in range(1, 7))

    main_hits = len(pred_main & actual_main)
    special_hit = 1 if prediction["special"] == actual["special"] else 0
    # 任意命中：推荐号码落在该期全部 7 个开出号码中
    any_hits = len((pred_main | {prediction["special"]}) & set(_draw_numbers(actual)))

    return {
        "period": actual["period"],
        "main_hits": main_hits,
        "special_hit": special_hit,
        "any_hits": any_hits,
        "predicted": sorted(pred_main),
        "predicted_special": prediction["special"],
    }


def _summarize(records, min_history, periods_backtested):
    """把逐期命中明细汇总为统计指标"""
    n = len(records)
    if n == 0:
        return {
            "periods_backtested": periods_backtested,
            "min_history": min_history,
            "total_periods": 0,
            "avg_main_hits": 0,
            "avg_any_hits": 0,
            "main_hit_rate": 0,
            "special_hit_count": 0,
            "special_hit_rate": 0,
            "best_main_hits": 0,
            "hit_distribution": {str(i): 0 for i in range(7)},
            "any_distribution": {str(i): 0 for i in range(8)},
            "special_periods": [],
            "recent": [],
        }

    total_main = sum(r["main_hits"] for r in records)
    total_special = sum(r["special_hit"] for r in records)
    total_any = sum(r["any_hits"] for r in records)

    # 命中个数分布
    main_dist = {str(i): 0 for i in range(7)}
    for r in records:
        main_dist[str(r["main_hits"])] += 1

    any_dist = {str(i): 0 for i in range(8)}
    for r in records:
        any_dist[str(r["any_hits"])] += 1

    return {
        "periods_backtested": periods_backtested,
        "min_history": min_history,
        "total_periods": n,
        # 平均每期命中几个正码（随机基准 = 6*6/49 ≈ 0.735）
        "avg_main_hits": round(total_main / n, 3),
        # 至少命中 1 个正码的期数占比
        "main_hit_rate": round(sum(1 for r in records if r["main_hits"] > 0) / n * 100, 1),
        # 平均每期命中几个号码（含特码，随机基准 = 7*7/49 = 1.0）
        "avg_any_hits": round(total_any / n, 3),
        "special_hit_count": total_special,
        # 特码命中率（随机基准 = 1/49 ≈ 2.04%）
        "special_hit_rate": round(total_special / n * 100, 2),
        "best_main_hits": max(r["main_hits"] for r in records),
        "hit_distribution": main_dist,
        "any_distribution": any_dist,
        # 特码命中明细（用于展示"中过特码"的期号）
        "special_periods": [
            {"period": r["period"], "special": r["predicted_special"]}
            for r in records if r["special_hit"]
        ],
        "recent": records[-20:],
    }


def _random_baseline(n):
    """
    理论随机基准（超几何分布期望）
      正码平均命中 = 6 * 6/49 ≈ 0.735
      特码命中率   = 1/49 ≈ 2.04%
      平均总命中   = 7 * 7/49 = 1.0
    """
    return {
        "avg_main_hits": round(6 * 6 / 49, 3),
        "special_hit_rate": round(1 / 49 * 100, 2),
        "avg_any_hits": round(7 * 7 / 49, 3),
        "total_periods": n,
    }


def run_backtest(strategies=None, min_history=MIN_HISTORY, max_periods=None,
                 recent_n=30, seed=None):
    """
    执行历史回测

    strategies: 要回测的策略列表，默认全部四种
    min_history: 前多少期只作为历史数据、不参与回测
    max_periods: 最多回测多少期（None = 全部可用期数）
    recent_n: 冷热号统计窗口，与 smart_recommend 保持一致
    seed: 随机种子。给定则回测结果可复现

    返回: {
      "strategies": {策略: 统计指标},
      "baseline": 随机基准,
      "meta": 回测参数,
      "verdict": 结论文字
    }
    """
    from analyzer import smart_recommend

    if strategies is None:
        strategies = STRATEGIES
    # 保持固定顺序，前端展示稳定
    strategies = [s for s in STRATEGIES if s in strategies]

    periods = _get_periods_ascending()
    total = len(periods)

    if total <= min_history:
        return {
            "error": f"数据不足：共 {total} 期，回测至少需要 {min_history + 1} 期"
        }

    # 可回测的期索引区间
    start = min_history
    if max_periods:
        start = max(min_history, total - int(max_periods))

    # 传给 smart_recommend 的 limit：只要历史足够即可，实际截断由
    # set_history_cutoff 按期号完成（limit 仅限制统计窗口大小）。
    history_limit = None

    results = {s: [] for s in strategies}

    # 全局随机状态：给定 seed 时结果完全可复现。
    # smart_recommend 内部使用全局 random，这里在每次调用前后保存/恢复，
    # 使各策略消耗同一段随机序列，保证横向可比。
    global_state = random.getstate()
    if seed is not None:
        random.seed(seed)
    try:
        for i in range(start, total):
            actual = periods[i]

            # 防未来数据泄露的关键：把历史截止期号设为**当期期号**，
            # 之后所有 get_all_results 调用（包括 analyzer 里十几个统计函数
            # 内部自己发起的）都只能看到这一期之前的数据。
            #
            # 早期版本只传 limit=i 给 smart_recommend，但 limit 的语义是
            # "全库最新的 i 期"，在回测早期会取到未来若干年的数据，
            # 导致回测结果完全失真。现改为按期号截断。
            set_history_cutoff(actual["period"])

            for strategy in strategies:
                saved = random.getstate()
                prediction = smart_recommend(
                    strategy, limit=history_limit, recent_n=recent_n
                )
                random.setstate(saved)  # 回滚，让下一个策略用同一段序列
                results[strategy].append(_evaluate(prediction, actual))
    finally:
        set_history_cutoff(None)
        random.setstate(global_state)

    periods_backtested = total - start
    summary = {
        s: _summarize(results[s], min_history, periods_backtested)
        for s in strategies
    }

    return {
        "strategies": summary,
        "baseline": _random_baseline(periods_backtested),
        "meta": {
            "total_periods": total,
            "min_history": min_history,
            "periods_backtested": periods_backtested,
            "recent_n": recent_n,
            "seed": seed,
            "strategy_names": {s: STRATEGY_NAMES[s] for s in strategies},
        },
        "verdict": _build_verdict(summary, periods_backtested),
    }


def _build_verdict(summary, n):
    """根据回测结果生成诚实结论（不吹嘘、不诱导）"""
    if not summary or n == 0:
        return "回测数据不足，无法给出结论。"

    baseline_main = 6 * 6 / 49
    lines = []

    ranked = sorted(
        summary.items(), key=lambda kv: kv[1]["avg_main_hits"], reverse=True
    )
    best_name, best = ranked[0]

    lines.append(
        f"回测 {n} 期：表现最好的策略是「{STRATEGY_NAMES.get(best_name, best_name)}」，"
        f"平均每期命中 {best['avg_main_hits']} 个正码，"
        f"随机理论基准为 {round(baseline_main, 3)} 个。"
    )

    diff = best["avg_main_hits"] - baseline_main
    if abs(diff) < 0.05:
        lines.append(
            "各策略与随机基准差异极小，说明「热号/冷号/遗漏值」在当前数据上"
            "没有可验证的预测优势——这与六合彩独立随机的本质一致。"
        )
    elif diff > 0:
        lines.append(
            f"该策略比随机基准高 {round(diff, 3)} 个正码。"
            "但样本量有限时，这种差距可能只是随机波动，不能据此认为策略有效。"
        )
    else:
        lines.append(
            f"该策略比随机基准低 {round(abs(diff), 3)} 个正码，未跑赢随机。"
        )

    lines.append(
        "结论：本工具的价值在于数据整理与可视化，而非预测中奖。"
        "请理性对待，量力而行。"
    )
    return " ".join(lines)


if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    report = run_backtest(seed=42)
    if "error" in report:
        print(f"[ERROR] {report['error']}")
        sys.exit(1)

    meta = report["meta"]
    print(f"总期数 {meta['total_periods']}，回测 {meta['periods_backtested']} 期"
          f"（前 {meta['min_history']} 期作为历史）")
    print(f"随机基准：平均命中 {report['baseline']['avg_main_hits']} 个正码，"
          f"特码命中率 {report['baseline']['special_hit_rate']}%\n")

    for key, s in report["strategies"].items():
        print(f"{STRATEGY_NAMES[key]:<14} "
              f"平均正码命中 {s['avg_main_hits']:<6} "
              f"平均总命中 {s['avg_any_hits']:<6} "
              f"特码命中 {s['special_hit_count']} 次 ({s['special_hit_rate']}%) "
              f"最佳 {s['best_main_hits']} 个")

    print(f"\n{report['verdict']}")
