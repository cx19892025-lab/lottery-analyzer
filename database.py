"""
六合彩数据分析工具 - 数据库层
SQLite 存储历史开奖记录，提供增删查接口
"""
import sqlite3
import random
import os

from paths import user_data_path, ensure_user_data

# 打包成 exe 后程序目录只读，数据库必须落在用户目录（见 paths.py）。
# 首次运行会把包内的 4404 期初始数据复制到用户目录。
DB_PATH = user_data_path("lottery.db")


def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构（打包运行时先把包内初始数据复制到用户目录）"""
    ensure_user_data("lottery.db")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lottery_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT UNIQUE NOT NULL,       -- 期号，如 "2024001"
            draw_date TEXT NOT NULL,           -- 开奖日期 "YYYY-MM-DD"
            num1 INTEGER NOT NULL,
            num2 INTEGER NOT NULL,
            num3 INTEGER NOT NULL,
            num4 INTEGER NOT NULL,
            num5 INTEGER NOT NULL,
            num6 INTEGER NOT NULL,
            special INTEGER NOT NULL           -- 特码
        )
    """)
    conn.commit()
    conn.close()


def insert_result(period, draw_date, numbers, special):
    """
    插入一条开奖记录
    numbers: [n1, n2, n3, n4, n5, n6] 已排序的6个正码
    special: 特码
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO lottery_results
            (period, draw_date, num1, num2, num3, num4, num5, num6, special)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (period, draw_date, *numbers, special))
        conn.commit()
        _invalidate_cache()
    finally:
        conn.close()


def insert_many(draws):
    """
    批量插入开奖记录（爬虫导入用）
    draws: [{"period","draw_date","numbers","special"}, ...]
    返回实际新插入的条数（重复期号被忽略）
    """
    conn = get_connection()
    try:
        before = conn.total_changes
        conn.executemany("""
            INSERT OR IGNORE INTO lottery_results
            (period, draw_date, num1, num2, num3, num4, num5, num6, special)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(d["period"], d["draw_date"], *d["numbers"], d["special"])
              for d in draws])
        conn.commit()
        _invalidate_cache()
        return conn.total_changes - before
    finally:
        conn.close()


def clear_results():
    """清空全部开奖记录（导入真实数据前清除模拟数据用）"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM lottery_results")
        conn.commit()
        _invalidate_cache()
    finally:
        conn.close()


# 只读内存缓存：真实数据 4400+ 期，回测每期每策略都会调 get_all_results，
# 重复查 SQLite 是最大开销。写操作统一走 _invalidate_cache()。
_result_cache = []

# 回测用的"历史截止期号"。
#
# 背景：analyzer 里十几个统计函数都直接调 get_all_results(limit)，
# 而 limit 的语义是"全库最新的 N 期"。回测时这会把未来数据喂给策略
# （例如预测 1994 年那一期时取到 2025 年的数据），造成严重泄露。
#
# 与其给每个统计函数加一个 before_period 参数（容易漏改），
# 这里用一个进程内的截止期号：回测循环在每期开始前设置它，
# get_all_results 统一遵守。这样 analyzer 无需任何改动。
_history_cutoff = None


def set_history_cutoff(period):
    """
    设置历史截止期号：之后 get_all_results 只返回期号 < period 的记录。
    period=None 表示取消限制（恢复正常全库读取）。
    """
    global _history_cutoff
    _history_cutoff = period


def get_history_cutoff():
    return _history_cutoff


def _invalidate_cache():
    global _result_cache
    _result_cache = []


# ============================================================================
# 数据质量下限：期号早于该值的数据**号码缺失**，不能参与统计。
#
# 问题（2026-11 发现）：数据源 icelam 在 2002-07 之前只记录了 1~47 号，
# 48/49 号被系统性漏掉。实测前 1013 期（1993-01 ~ 2002-07）里：
#     48 号出现 0 次，49 号出现 1 次
#     同期其他号码平均出现 150.9 次
# 后果：48/49 号在"冷热号/遗漏排行/频率"里被严重低估，
#      会出现"48 号最长连续 1013 期未出"这种荒谬结论
#      （独立随机下 4404 期的理论最长遗漏仅约 66 期）。
#
# 从 2002053（2002-07-04）起 48/49 号分布恢复正常，故以该期为统计起点。
#
# 注意：这是**统计**下限，不是数据删除——原始记录仍完整保留，
#      「开奖记录」页签照样能看到全部 4404 期。
# ============================================================================
STATS_MIN_PERIOD = "2002053"


def get_all_results(limit=None, before_period=None):
    """
    获取开奖记录，按期号降序（带内存缓存，写操作自动失效）。

    limit: 只取最新的 N 期（在已应用的历史截止期号之内）。
    before_period: 只取期号严格小于该值的记录（显式指定，优先级高于全局截止）。

    回测防泄露：由 set_history_cutoff() 设置的截止期号会自动生效，
    analyzer 里的统计函数无需感知。

    **统计口径**：默认排除 STATS_MIN_PERIOD 之前的缺失数据。
    需要完整原始记录（如"开奖记录"列表）时传 include_early=True。
    """
    global _result_cache
    if not _result_cache:
        conn = get_connection()
        _result_cache = [dict(r) for r in conn.execute(
            "SELECT * FROM lottery_results ORDER BY period DESC").fetchall()]
        conn.close()

    rows = _result_cache

    # 数据质量下限：排除 48/49 号缺失的早期数据（见 STATS_MIN_PERIOD 说明）。
    rows = [r for r in rows if r["period"] >= STATS_MIN_PERIOD]

    # 显式参数优先，其次用全局截止（回测时设置）
    cutoff = before_period if before_period is not None else _history_cutoff
    if cutoff is not None:
        rows = [r for r in rows if r["period"] < cutoff]

    return rows[:limit] if limit else rows


def get_raw_results(limit=None):
    """
    取**完整**原始记录（不过滤数据质量下限），供"开奖记录"页签展示。

    与 get_all_results 的区别：这里会返回 1993~2002 那些 48/49 号缺失的期，
    因为用户看历史开奖时应该看到全部记录，而不是被统计口径悄悄砍掉。
    """
    global _result_cache
    if not _result_cache:
        conn = get_connection()
        _result_cache = [dict(r) for r in conn.execute(
            "SELECT * FROM lottery_results ORDER BY period DESC").fetchall()]
        conn.close()
    return _result_cache[:limit] if limit else _result_cache


def get_results_count():
    """获取记录总数"""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM lottery_results").fetchone()[0]
    conn.close()
    return count


def generate_simulated_data(num_periods=300):
    """
    生成模拟历史开奖数据 (300期)
    规则：从1-49中随机选6个正码 + 1个特码
    """
    if get_results_count() > 0:
        return  # 已有数据则跳过

    from datetime import datetime, timedelta

    base_date = datetime(2024, 1, 2)  # 起始日期
    draw_days = [1, 2, 4]  # 每周二、三、六开奖（简化）

    current_date = base_date
    period_num = 1

    for i in range(num_periods):
        # 生成号码
        all_nums = random.sample(range(1, 50), 7)
        main_nums = sorted(all_nums[:6])
        special = all_nums[6]

        period = f"2024{period_num:03d}"
        draw_date = current_date.strftime("%Y-%m-%d")

        insert_result(period, draw_date, main_nums, special)

        # 推进日期（约每2-3天一期）
        current_date += timedelta(days=random.choice([2, 3, 4]))
        period_num += 1

    print(f"[OK] Generated {num_periods} simulated lottery records")


if __name__ == "__main__":
    init_db()
    generate_simulated_data()
    results = get_all_results(5)
    for r in results:
        nums = [r[f"num{i}"] for i in range(1, 7)]
        print(f"第{r['period']}期: {nums} + 特码{r['special']}")
