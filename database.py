"""
六合彩数据分析工具 - 数据库层
SQLite 存储历史开奖记录，提供增删查接口
"""
import sqlite3
import random
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "lottery.db")


def get_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构"""
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
    finally:
        conn.close()


def get_all_results(limit=None):
    """获取所有开奖记录，按期号降序"""
    conn = get_connection()
    cursor = conn.cursor()
    sql = "SELECT * FROM lottery_results ORDER BY period DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = cursor.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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
