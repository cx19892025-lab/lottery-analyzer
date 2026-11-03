"""
六合彩数据分析工具 - 真实历史数据采集

数据源策略（2026-11 调研结论，均为国内可直连）：
  HKJC 官方接口 bet.hkjc.com 本机直连超时（被墙），不可用；
  改用 GitHub 上由 CI 自动同步 HKJC 官方数据的开源数据集，
  经 raw.githubusercontent.com 拉取（已实测本机直连 200）：

  1) icelam/mark-six-data-visualization  data/all.json
     覆盖 1993-01 ~ 2025-12（源自 HKJC 官方 JSON），用作全量种子
  2) stevetsang852/marksix-rd            data/processed/draws.json
     覆盖 2002-07 ~ 至今，GitHub Actions 每日同步 HKJC，用作增量更新

  两源期号格式一致（YY/SSS），按期号合并去重；重叠期若号码不一致
  以 icelam 为准（更早入库、来源为官方历史缓存），冲突数会在结果中报告。

公开接口：
  import_all(clear=True)  全量导入（种子 + 增量源合并）
  sync_latest()           增量同步最新开奖（仅增量源，INSERT OR IGNORE）
  data_status()           本地库数据概况
"""
import urllib.request
import json

from database import (
    insert_result, insert_many, get_all_results,
    get_results_count, clear_results,
)

# 数据源地址（raw.githubusercontent.com 国内可直连）
SEED_URL = "https://raw.githubusercontent.com/icelam/mark-six-data-visualization/master/data/all.json"
LATEST_URL = "https://raw.githubusercontent.com/stevetsang852/marksix-rd/main/data/processed/draws.json"

REQUEST_TIMEOUT = 30  # 秒


def _fetch_json(url):
    """抓取 URL 并解析 JSON（带 UA，raw.githubusercontent 对无 UA 请求偶尔 403）"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "lottery-analyzer/1.0 (+local tool)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _yy_to_year(yy):
    """两位年份转四位：>=50 视为 19xx，否则 20xx（Mark Six 数据起点 1993）"""
    yy = int(yy)
    return 1900 + yy if yy >= 50 else 2000 + yy


def _make_period(id_str):
    """'93/002' → '1993002'；'25/134' → '2025134'，与库内 YYYYSSS 格式兼容"""
    yy, seq = str(id_str).split("/")
    return f"{_yy_to_year(yy)}{int(seq):03d}"


def _validate(draw):
    """
    校验单期数据合法性，合法返回 None，非法返回原因文字。
    规则：6 个正码均在 1-49 且互不相同；特码 1-49 且不与正码重复
    （Mark Six 七个球同一摇奖机无放回开出，七号必互异）。
    """
    mains, special = draw["numbers"], draw["special"]
    if len(mains) != 6:
        return f"正码数量 {len(mains)} != 6"
    if any(not (1 <= n <= 49) for n in mains):
        return "正码存在超出 1-49 范围"
    if len(set(mains)) != 6:
        return "正码存在重复"
    if not (1 <= special <= 49):
        return f"特码 {special} 超出 1-49 范围"
    if special in mains:
        return f"特码 {special} 与正码重复"
    return None


def _normalize_icelam(records):
    """
    icelam data/all.json 记录 → 统一结构
    原始: {"id":"93/002","date":"1993-01-07","no":["6",...],"sno":"37", ...}
    """
    out = []
    for r in records:
        try:
            out.append({
                "period": _make_period(r["id"]),
                "draw_date": r["date"],
                "numbers": sorted(int(n) for n in r["no"]),
                "special": int(r["sno"]),
                "source": "icelam",
            })
        except (KeyError, ValueError, TypeError):
            continue  # 脏数据直接跳过，统计到 skipped
    return out


def _normalize_marksix_rd(records):
    """
    marksix-rd data/processed/draws.json 记录 → 统一结构
    原始: {"issue":"26/105","date":"2026-10-03","n1":8,...,"special":48, ...}
    """
    out = []
    for r in records:
        try:
            out.append({
                "period": _make_period(r["issue"]),
                "draw_date": r["date"],
                "numbers": sorted(int(r[f"n{i}"]) for i in range(1, 7)),
                "special": int(r["special"]),
                "source": "marksix-rd",
            })
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _dedupe_merge(seed_draws, latest_draws):
    """
    按期号合并两源：
      - 冲突（同期号但号码不同）以种子源为准，计数报告
      - 增量源仅补种子缺失的期号（典型为 2026 年新数据）
    返回 (merged list 按期号升序, conflict list)
    """
    by_period = {d["period"]: d for d in seed_draws}
    conflicts = []
    for d in latest_draws:
        existing = by_period.get(d["period"])
        if existing is None:
            by_period[d["period"]] = d
        elif (existing["numbers"] != d["numbers"]
              or existing["special"] != d["special"]):
            conflicts.append({
                "period": d["period"],
                "seed": {"numbers": existing["numbers"], "special": existing["special"]},
                "latest": {"numbers": d["numbers"], "special": d["special"]},
            })
    merged = sorted(by_period.values(), key=lambda x: x["period"])
    return merged, conflicts


def fetch_real_data():
    """
    抓取并合并两源真实开奖数据（不写库）
    返回: {"draws": [...], "stats": {...}}；抓取失败抛出异常由路由层翻译
    """
    seed_raw = _fetch_json(SEED_URL)
    latest_raw = _fetch_json(LATEST_URL)

    seed_draws = _normalize_icelam(seed_raw)
    latest_draws = _normalize_marksix_rd(latest_raw)

    merged, conflicts = _dedupe_merge(seed_draws, latest_draws)

    valid, skipped = [], []
    for d in merged:
        reason = _validate(d)
        (skipped.append({"period": d["period"], "reason": reason}) if reason
         else valid.append(d))

    stats = {
        "seed_count": len(seed_draws),
        "latest_count": len(latest_draws),
        "merged_count": len(merged),
        "valid_count": len(valid),
        "conflict_count": len(conflicts),
        "conflicts_sample": conflicts[:5],
        "skipped": skipped[:10],
        "earliest": valid[0] if valid else None,
        "latest": valid[-1] if valid else None,
    }
    return {"draws": valid, "stats": stats}


def import_all(clear=True):
    """
    全量导入真实历史数据（先抓取两源合并，再写库）
    clear: 写入前是否清空现有数据（默认是——用于清除模拟数据/整体重建）
    返回写入摘要 dict
    """
    fetched = fetch_real_data()
    draws = fetched["draws"]

    if clear:
        clear_results()

    inserted = insert_many(draws)
    return {
        "ok": True,
        "inserted": inserted,
        "fetched": fetched["stats"],
        "total_periods": get_results_count(),
    }


def sync_latest():
    """
    增量同步：仅拉取 marksix-rd 的最新数据，INSERT OR IGNORE 补新期。
    已存在的期号不会改动，因此旧的（可能经种子修正过的）数据不会被覆盖。
    """
    latest_raw = _fetch_json(LATEST_URL)
    draws = _normalize_marksix_rd(latest_raw)

    valid, skipped = [], []
    for d in draws:
        reason = _validate(d)
        (skipped.append({"period": d["period"], "reason": reason}) if reason
         else valid.append(d))

    existing = {r["period"] for r in get_all_results()}
    inserted = insert_many(valid)
    new_periods = sorted(d["period"] for d in valid if d["period"] not in existing)[-10:]

    return {
        "ok": True,
        "inserted": inserted,
        "source_count": len(valid),
        "new_periods": new_periods,
        "total_periods": get_results_count(),
    }


def data_status():
    """本地库数据概况（快速，只查本地库不发网络请求）"""
    results = get_all_results(1)  # 最新一期
    total = get_results_count()
    latest = results[0] if results else None
    return {
        "total_periods": total,
        "latest_period": latest["period"] if latest else None,
        "latest_date": latest["draw_date"] if latest else None,
        "sources": {
            "seed": SEED_URL,
            "latest": LATEST_URL,
        },
    }


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    summary = import_all(clear=True)
    print(json.dumps(summary["fetched"], ensure_ascii=False, indent=2))
    print(f"inserted={summary['inserted']} total={summary['total_periods']}")
