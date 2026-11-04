"""
六合彩数据分析工具 - 真实历史数据采集

数据源策略（2026-11 调研结论，均为国内可直连）：
  HKJC 官方接口 bet.hkjc.com 本机直连超时（被墙），不可用；
  改用第三方镜像 / GitHub 上由 CI 自动同步 HKJC 官方数据的开源数据集：

  1) icelam/mark-six-data-visualization  data/all.json
     覆盖 1993-01 ~ 2025-12（源自 HKJC 官方 JSON），用作全量种子
  2) stevetsang852/marksix-rd            data/processed/draws.json
     覆盖 2002-07 ~ 至今，GitHub Actions 每日同步 HKJC，用作增量更新
     ⚠ 其 CI 自 2026-10-29 起 "Commit snapshots" 步骤失败（仓库 Workflow 权限只读），
       数据停在 2026-10-03，不可靠
  3) renavon.com  /data/hkjc/hkjc_marksix_results/download/csv
     覆盖 1993-01 ~ 至今，每期开奖后更新，实测可直连（需浏览器 UA），
     用作**首选增量源**

  三源期号统一为 YYYYSSS，按期号合并去重；重叠期若号码不一致
  以 icelam 为准（更早入库、来源为官方历史缓存），冲突数会在结果中报告。
  实测：Renavon 与库内 4393 期重叠部分零冲突、零日期差异。

公开接口：
  import_all(clear=True)  全量导入（种子 + 增量源合并）
  sync_latest()           增量同步最新开奖（增量源合并，INSERT OR IGNORE）
  data_status()           本地库数据概况
"""
import urllib.request
import gzip
import csv
import io
import json

from database import (
    insert_result, insert_many, get_all_results, get_raw_results,
    get_results_count, clear_results,
)

# 数据源地址（raw.githubusercontent.com / renavon.com 国内可直连）
SEED_URL = "https://raw.githubusercontent.com/icelam/mark-six-data-visualization/master/data/all.json"
LATEST_URL = "https://raw.githubusercontent.com/stevetsang852/marksix-rd/main/data/processed/draws.json"
RENAVON_URL = "https://renavon.com/data/hkjc/hkjc_marksix_results/download/csv"

REQUEST_TIMEOUT = 30  # 秒

# 浏览器 UA：renavon 对非浏览器 UA 会返回 403
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _fetch_json(url):
    """抓取 URL 并解析 JSON（带 UA，raw.githubusercontent 对无 UA 请求偶尔 403）"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "lottery-analyzer/1.0 (+local tool)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_renavon_csv():
    """
    抓取 Renavon 的开奖结果 CSV。
    响应体实测为 gzip 压缩但未声明 Content-Encoding，故按魔数自行判断。
    """
    req = urllib.request.Request(RENAVON_URL, headers={
        "User-Agent": _BROWSER_UA,
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read()
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    # utf-8-sig：文件带 BOM，否则第一个列名会变成 "﻿draw_record_id"
    return body.decode("utf-8-sig", "replace")



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


def _normalize_renavon(csv_text):
    """
    Renavon CSV → 统一结构
    列: draw_year, draw_number_in_year, draw_date, ball_1..ball_6, extra_ball
    draw_date 形如 "2026-10-31+08:00"，需去掉时区后缀
    """
    out = []
    for r in csv.DictReader(io.StringIO(csv_text)):
        # 只取已开奖的期次
        if r.get("has_results") != "1":
            continue
        try:
            year = int(r["draw_year"])
            seq = int(r["draw_number_in_year"])
            draw_date = r["draw_date"].split("+")[0].split("T")[0]
            numbers = sorted(int(r[f"ball_{i}"]) for i in range(1, 7))
            special = int(r["extra_ball"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append({
            "period": f"{year:04d}{seq:03d}",
            "draw_date": draw_date,
            "numbers": numbers,
            "special": special,
            "source": "renavon",
        })
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


def _fetch_optional_sources():
    """
    抓取两个增量源。任一源失败不影响另一个（降级而非整体报错）。
    返回: (list of (source_name, draws), list of (source_name, error_message))
    """
    results, errors = [], []

    try:
        results.append(("renavon", _normalize_renavon(_fetch_renavon_csv())))
    except Exception as e:
        errors.append(("renavon", f"{type(e).__name__}: {e}"))

    try:
        results.append(("marksix-rd", _normalize_marksix_rd(_fetch_json(LATEST_URL))))
    except Exception as e:
        errors.append(("marksix-rd", f"{type(e).__name__}: {e}"))

    return results, errors


def fetch_real_data():
    """
    抓取并合并多源真实开奖数据（不写库）
    种子源（icelam）失败会抛异常——没有它就没有历史；
    增量源失败只记录在 stats 里，不影响导入。
    返回: {"draws": [...], "stats": {...}}
    """
    seed_draws = _normalize_icelam(_fetch_json(SEED_URL))
    incremental, errors = _fetch_optional_sources()

    # 增量源内部再合并一次（renavon 优先，marksix-rd 补充）
    merged, conflicts = _dedupe_merge(seed_draws, [])
    for _name, draws in incremental:
        merged, conflicts2 = _dedupe_merge(merged, draws)
        conflicts.extend(conflicts2)

    valid, skipped = [], []
    for d in merged:
        reason = _validate(d)
        (skipped.append({"period": d["period"], "reason": reason}) if reason
         else valid.append(d))

    stats = {
        "seed_count": len(seed_draws),
        "source_counts": {name: len(draws) for name, draws in incremental},
        "source_errors": [{"source": n, "error": e} for n, e in errors],
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
    增量同步：拉取两个增量源（Renavon 优先、marksix-rd 兜底），
    INSERT OR IGNORE 补新期。已存在的期号不会改动，
    因此旧的（可能经种子修正过的）数据不会被覆盖。
    """
    incremental, errors = _fetch_optional_sources()
    if not incremental:
        raise RuntimeError("所有增量源均不可用：" + "；".join(
            f"{n}: {e}" for n, e in errors))

    merged, _conflicts = _dedupe_merge([], [])
    for _name, draws in incremental:
        merged, _ = _dedupe_merge(merged, draws)

    valid, skipped = [], []
    for d in merged:
        reason = _validate(d)
        (skipped.append({"period": d["period"], "reason": reason}) if reason
         else valid.append(d))

    # 用 get_raw_results：判断"期号是否已存在"必须看全部原始记录。
    # 若用 get_all_results（已排除早期数据），1993~2002 的期号会被误判为"新期"，
    # 导致每次同步都把 old periods 报成新增。
    existing = {r["period"] for r in get_raw_results()}
    inserted = insert_many(valid)
    new_periods = sorted(d["period"] for d in valid if d["period"] not in existing)[-10:]

    return {
        "ok": True,
        "inserted": inserted,
        "source_count": len(valid),
        "source_counts": {name: len(draws) for name, draws in incremental},
        "source_errors": [{"source": n, "error": e} for n, e in errors],
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
            "latest": RENAVON_URL,
            "fallback": LATEST_URL,
        },
    }


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    summary = import_all(clear=True)
    print(json.dumps(summary["fetched"], ensure_ascii=False, indent=2))
    print(f"inserted={summary['inserted']} total={summary['total_periods']}")
