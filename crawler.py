"""
六合彩数据分析工具 - 真实历史数据采集

数据源策略（2026-11 调研结论，均为国内可直连）：
  HKJC 官方接口 bet.hkjc.com 本机直连超时（被墙），不可用；
  改用第三方镜像 / GitHub 上由 CI 自动同步 HKJC 官方数据的开源数据集：

  1) icelam/mark-six-data-visualization  data/all.json
     覆盖 1993-01 ~ 2025-12（源自 HKJC 官方 JSON），用作全量种子
  2) lottery.hk  /en/mark-six/results/{年份}
     覆盖 1993 ~ 至今，**每期开奖后当天更新**，用作**首选增量源**
     （V1.8.3 新增。此前 renavon 是最新源，但实测滞后达 6 天，
       用户报"昨天有开奖但同步不到"；lottery.hk 次日即可拿到）
     已交叉验证：与本地库重叠 664 期**零不一致**
  3) renavon.com  /data/hkjc/hkjc_marksix_results/download/csv
     覆盖 1993-01 ~ 至今，实测可直连（需浏览器 UA），作为备用增量源
     ⚠ 实测更新滞后较多（2026-11-06 时最新仍为 10-31），故降为备用
  4) stevetsang852/marksix-rd            data/processed/draws.json
     覆盖 2002-07 ~ 至今，但其 CI 自 2026-10-29 起失败，
     数据停在 2026-10-03，**基本不可用**，仅作最后兜底

  各源期号统一为 YYYYSSS，按期号合并去重；重叠期若号码不一致
  以 icelam 为准（更早入库、来源为官方历史缓存），冲突数会在结果中报告。

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
import re
import time

from database import (
    insert_result, insert_many, get_all_results, get_raw_results,
    get_results_count, clear_results,
)

# 数据源地址（均为国内可直连）
SEED_URL = "https://raw.githubusercontent.com/icelam/mark-six-data-visualization/master/data/all.json"
LATEST_URL = "https://raw.githubusercontent.com/stevetsang852/marksix-rd/main/data/processed/draws.json"
RENAVON_URL = "https://renavon.com/data/hkjc/hkjc_marksix_results/download/csv"
LOTTERY_HK_BASE = "https://lottery.hk/en/mark-six/results"

REQUEST_TIMEOUT = 30  # 秒

# 浏览器 UA：renavon 对非浏览器 UA 会返回 403
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _describe_error(e):
    """
    把网络异常转成可读的中文说明。

    背景（V1.8.2）：用户报「同步失败：renavon: URLError: ；marksix-rd: URLError:」
    ——两个源后面都是**空的**，完全看不出发生了什么。

    原因：urllib 的 URLError 在网络不可达时 str() 可能为空字符串，
    而原来的 `f"{type(e).__name__}: {e}"` 就会产出 "URLError: "。
    必须往下看 e.reason 才能拿到真实原因。

    这里把它翻译成用户能据此行动的描述（超时？断网？DNS？代理？）。
    """
    import socket
    from urllib.error import URLError

    reason = getattr(e, "reason", None)
    detail = str(reason) if reason is not None else str(e)
    detail = (detail or "").strip()

    low = detail.lower()
    if isinstance(reason, socket.timeout) or "timed out" in low:
        return "连接超时（网络慢或被墙）"
    if isinstance(reason, socket.gaierror) or "getaddrinfo" in low or "name or service" in low:
        return "域名解析失败（DNS 问题或断网）"
    if "connection refused" in low:
        return "连接被拒绝（对方服务器不可用）"
    if "connection reset" in low or "aborted" in low:
        return "连接被重置（可能被网络中间设备拦截）"
    if "certificate" in low or "ssl" in low:
        return "TLS/证书错误（可能有代理拦截）"
    if "unreachable" in low:
        return "网络不可达（检查是否断网）"

    # 兜底：连 reason 都拿不到时，至少说明"网络层失败"而非"没抓到数据"
    if not detail:
        return f"网络请求失败（{type(e).__name__}，无详细信息）"
    return f"{type(e).__name__}: {detail}"


def _fetch_with_retry(make_request, attempts=3, backoff=1.5):
    """
    带重试的抓取。网络抖动导致的瞬时失败不该直接报给用户。

    背景：用户遇到过一次同步失败，但几分钟后同样的操作就成功了
    ——典型的瞬时网络抖动。原实现只试一次，一失败就报错。

    策略：最多 attempts 次，间隔 backoff * 2^n 秒递增（1.5s / 3s / 6s）。
    只对网络层异常重试；HTTP 4xx（如 403）重试也没用，直接抛出。
    """
    from urllib.error import HTTPError

    last = None
    for i in range(attempts):
        try:
            return make_request()
        except HTTPError:
            # 4xx/5xx 是服务端明确回应，重试无意义（除非 5xx，但这里从简）
            raise
        except Exception as e:
            last = e
            if i < attempts - 1:
                time.sleep(backoff * (2 ** i))
    raise last


def _fetch_json(url):
    """抓取 URL 并解析 JSON（带 UA，raw.githubusercontent 对无 UA 请求偶尔 403）"""
    def _once():
        req = urllib.request.Request(url, headers={
            "User-Agent": "lottery-analyzer/1.0 (+local tool)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    return _fetch_with_retry(_once)


def _fetch_renavon_csv():
    """
    抓取 Renavon 的开奖结果 CSV。
    响应体实测为 gzip 压缩但未声明 Content-Encoding，故按魔数自行判断。
    """
    def _once():
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
    return _fetch_with_retry(_once)



def _fetch_lottery_hk(year=None):
    """
    抓取 lottery.hk 的开奖结果页并解析。

    year=None  →  /results/          列表页（最近约 1 年，含最新一期）
    year=2026  →  /results/2026      整年

    页面是服务端渲染的静态 HTML，结构稳定：
      <td>26/117</td><td><span class="date">05/11/2026</span></td>
      <td><ul class="balls">
            <li class="-green">11</li> ... <li class="-red -plus">46</li>
          </ul></td>

    前 6 个 li 是正码，带 -plus 的那个是特码。

    为什么选它：实测每期开奖后**当天/次日**即更新，
    而 renavon 滞后可达 6 天（用户报"昨天有开奖但同步不到"）。
    已交叉验证与本地库重叠 664 期零不一致。
    """
    url = f"{LOTTERY_HK_BASE}/{year}" if year else f"{LOTTERY_HK_BASE}/"

    def _once():
        req = urllib.request.Request(url, headers={
            "User-Agent": _BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")

    html = _fetch_with_retry(_once)
    return _parse_lottery_hk(html)


def _parse_lottery_hk(html):
    """把 lottery.hk 的 HTML 解析成统一格式的开奖记录列表"""
    draws = []
    pattern = re.compile(
        r'<td>(\d{2}/\d{3})</td>\s*'
        r'<td><span class="date">(\d{2}/\d{2}/\d{4})</span></td>\s*'
        r'<td>\s*<ul class="balls">(.*?)</ul>',
        re.S,
    )
    for m in pattern.finditer(html):
        issue, date_str, balls_html = m.group(1), m.group(2), m.group(3)
        balls = re.findall(r'<li class="([^"]*)">\s*(\d{1,2})\s*</li>', balls_html)
        main = [int(v) for c, v in balls if "-plus" not in c]
        special = [int(v) for c, v in balls if "-plus" in c]
        if len(main) != 6 or len(special) != 1:
            continue

        day, mon, year4 = date_str.split("/")
        yy, seq = issue.split("/")
        yy = int(yy)
        year = 1900 + yy if yy >= 50 else 2000 + yy
        period = f"{year}{int(seq):03d}"

        draws.append({
            "period": period,
            "draw_date": f"{year4}-{mon}-{day}",
            "numbers": sorted(main),
            "special": special[0],
            "source": "lottery.hk",
        })
    return draws


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
    抓取各增量源。任一源失败不影响其他源（降级而非整体报错）。
    返回: (list of (source_name, draws), list of (source_name, error_message))

    顺序即优先级：合并时靠前的源覆盖靠后的（见 _dedupe_merge）。
    lottery.hk 放第一，因为它实测更新最快（开奖当天/次日）。
    """
    results, errors = [], []

    # 首选：lottery.hk（更新最快，已交叉验证 664 期零不一致）
    try:
        results.append(("lottery.hk", _fetch_lottery_hk()))
    except Exception as e:
        errors.append(("lottery.hk", _describe_error(e)))

    # 备用：renavon（覆盖全，但实测滞后较多）
    try:
        results.append(("renavon", _normalize_renavon(_fetch_renavon_csv())))
    except Exception as e:
        errors.append(("renavon", _describe_error(e)))

    # 最后兜底：marksix-rd（CI 已失效，数据停在 2026-10-03）
    try:
        results.append(("marksix-rd", _normalize_marksix_rd(_fetch_json(LATEST_URL))))
    except Exception as e:
        errors.append(("marksix-rd", _describe_error(e)))

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


def next_draw_info():
    """
    推算下一期开奖日期 —— 只读本地库，**不联网**。

    用途：开奖记录页顶部显示"下一期预计何时开"，
    省得用户自己去猜（用户明确要求过）。

    依据：香港六合彩固定**周二 / 周四 / 周六**开奖
    （本项目 4404 期实测，各年一致；偶有周日/周五的特别场次）。

    ⚠️ 这是**按规律推算**，不是官方公告：
      历史上确实出现过整期跳过（见 DEVLOG V1.7.3），
      所以文案用「预计」，不能写成确定日期。

    返回：
      {
        "date": "2026-11-07",          下一期预计日期
        "weekday": "周六",
        "days_until": 0,               距今几天（0=今天）
        "is_today": True,
        "latest_period": "2026117",    当前库内最新期号
        "latest_date": "2026-11-05",
        "next_period": "2026118",      预计期号（仅当年序号+1 的推算）
        "note": "..."                  给用户看的说明
      }
    """
    from datetime import date, timedelta

    DRAW_WEEKDAYS = (1, 3, 5)          # 周一=0 → 周二/四/六
    WEEK_CN = "一二三四五六日"

    raw = get_raw_results()
    if not raw:
        return {"known": False}

    latest_date = date.fromisoformat(raw[0]["draw_date"][:10])
    latest_period = raw[0]["period"]
    today = date.today()

    # 从「库内最新一期的次日」开始找第一个应开日。
    # 用最新一期而非今天作为起点：即使库内数据落后，
    # 也能算出"紧接着的那一期"，符合用户直觉。
    cur = latest_date + timedelta(days=1)
    for _ in range(14):                # 最多找两周，必然命中
        if cur.weekday() in DRAW_WEEKDAYS:
            break
        cur += timedelta(days=1)

    days_until = (cur - today).days

    # 期号推算：同一年内序号 +1；跨年则回到 001。
    # 这只是"预计"，因为可能跳期，仅供参考。
    try:
        year, seq = int(latest_period[:4]), int(latest_period[4:])
        if cur.year == year:
            next_period = f"{year}{seq + 1:03d}"
        else:
            next_period = f"{cur.year}001"
    except (ValueError, IndexError):
        next_period = None

    if days_until > 0:
        note = f"预计 {days_until} 天后开奖"
    elif days_until == 0:
        note = "预计今晚开奖（通常 21:15 截止投注后）"
    else:
        note = "按规律该期已过，可能已跳期或数据源尚未更新"

    return {
        "known": True,
        "date": cur.isoformat(),
        "weekday": f"周{WEEK_CN[cur.weekday()]}",
        "days_until": days_until,
        "is_today": days_until == 0,
        "latest_period": latest_period,
        "latest_date": latest_date.isoformat(),
        "next_period": next_period,
        "note": note,
    }


def data_freshness():
    """
    数据新鲜度检查 —— 只读本地库，**不联网**。

    用途：软件启动时判断"库里的数据是不是可能已经过时了"，
    以便在界面顶部提示用户去同步，而不是让用户自己记得点。

    为什么需要它：同步是手动触发的（有意设计，避免软件偷偷联网）。
    但用户容易忘记点，看到旧数据却毫无察觉。

    判断依据：香港六合彩固定**周二 / 周四 / 周六**开奖
    （本项目 4404 期数据实测，各年均如此；偶有周日/周五的特别场次）。
    从"库内最新一期"到"今天"之间，数一数有多少个应开日，
    减去 1 天的宽限期（当晚 21:15 才截止投注、之后才开奖，
    且数据源由 CI 每天更新一次，存在滞后）。

    注意：**本函数不做任何网络请求**，纯本地计算。
    它只能说"可能缺了 N 期"，无法确认那期究竟开没开
    （历史上确实存在整期跳过的情况，见 DEVLOG V1.7.3）。
    """
    from datetime import date, timedelta

    raw = get_raw_results()
    if not raw:
        return {"known": False, "stale": False}

    latest_date = date.fromisoformat(raw[0]["draw_date"][:10])
    today = date.today()
    days_behind = (today - latest_date).days

    # 数出 (latest_date, today] 之间落在 周二/四/六 的天数
    DRAW_WEEKDAYS = (1, 3, 5)          # 周一=0
    missed = []
    cur = latest_date + timedelta(days=1)
    while cur <= today:
        if cur.weekday() in DRAW_WEEKDAYS:
            missed.append(cur)
        cur += timedelta(days=1)

    # 宽限：最新一期开奖当晚数据源可能还没更新，留 1 天余量
    GRACE_DAYS = 1
    pending = [d for d in missed if (today - d).days > GRACE_DAYS]

    return {
        "known": True,
        "latest_period": raw[0]["period"],
        "latest_date": raw[0]["draw_date"][:10],
        "today": today.isoformat(),
        "days_behind": days_behind,
        # stale：有超过宽限期的应开日没数据 → 值得提示用户同步
        "stale": len(pending) > 0,
        "missed_count": len(pending),
        "missed_dates": [d.isoformat() for d in pending][-5:],
        "missed_labels": [
            f"{d.isoformat()}（周{'一二三四五六日'[d.weekday()]}）"
            for d in pending
        ][-5:],
    }


def sync_latest():
    """
    增量同步：拉取各增量源（lottery.hk 优先，renavon 备用，marksix-rd 兜底），
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

    # 同步成功但没新增时，用户最想知道的是「到底是没开奖，还是源没更新」。
    # 这里直接比对：库内最新日期 vs 源内最新日期。
    #
    # 注意 db_latest 必须在 insert_many **之后**重新读，
    # 否则刚写入的新期不算数，会误报"源落后于库"。
    source_latest = max((d["draw_date"] for d in valid), default=None)
    db_latest = (get_raw_results(1) or [{}])[0].get("draw_date")
    behind = bool(source_latest and db_latest and source_latest < db_latest)

    return {
        "ok": True,
        "inserted": inserted,
        "source_count": len(valid),
        "source_counts": {name: len(draws) for name, draws in incremental},
        "source_errors": [{"source": n, "error": e} for n, e in errors],
        "new_periods": new_periods,
        "total_periods": get_results_count(),
        # —— 诊断字段：解释"为什么没有新增" ——
        "db_latest_date": db_latest,
        "source_latest_date": source_latest,
        # 源内最新 **早于** 库内最新 → 源尚未收录新一期（不是程序问题）。
        # 用严格小于：两者相等说明已同步到源的最新，不算"落后"。
        "source_behind": behind,
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
            "primary": f"{LOTTERY_HK_BASE}/",
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
