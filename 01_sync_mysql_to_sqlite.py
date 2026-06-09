#!/usr/bin/env python3
"""
Sync member sales mix data from MySQL (PRD) to local SQLite for offline frontend use.
Fetches daily store-level and overall data for 2026.
Supports incremental sync — automatically detects last synced date and only fetches new data.

Usage:
  python3 sync_mysql_to_sqlite.py                    # Incremental sync (auto-detect last date)
  python3 sync_mysql_to_sqlite.py --full             # Force full sync from 2026-01-01
  python3 sync_mysql_to_sqlite.py --from 2026-06-01  # Sync from specific date
  python3 sync_mysql_to_sqlite.py --from 2026-06-01 --to 2026-06-08
"""

import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta

import pymysql

# MySQL connection info (from sql-MySQL-Connection-Info.txt)
MYSQL_CONFIG = {
    "host": "34.81.120.135",
    "port": 3306,
    "user": "readonly_user",
    "password": "StrongPassword123!",
    "database": "kiosk",
    "charset": "utf8mb4",
    "connect_timeout": 30,
    "read_timeout": 120,
}

SQLITE_DB = "member_sales.db"

# Each store query — daily granularity
# Uses DATE(created_at + INTERVAL 8 HOUR) for Taiwan local date
SQL_EACH_STORE = """
WITH OrderStats AS (
    SELECT
        DATE(o.created_at + INTERVAL 8 HOUR) AS biz_date,
        o.shop_code,
        c.digital AS storeType,
        s.shop_name,
        SUM(o.price) AS total_amount,
        SUM(CASE
            WHEN o.member_id IS NOT NULL AND TRIM(o.member_id) <> ''
            THEN o.price ELSE 0
        END) AS member_amount,
        ROUND(SUM(CASE
            WHEN o.member_id IS NOT NULL AND TRIM(o.member_id) <> ''
            THEN o.price ELSE 0
        END) * 100.0 / SUM(o.price), 2) AS member_amount_ratio_percent,
        COUNT(*) AS order_count
    FROM kiosk.orders o
    LEFT JOIN kiosk.shop s ON o.shop_code = s.shop_code
    LEFT JOIN kiosk.shop_config c ON o.shop_code = c.shop_code
    WHERE
        o.created_at >= %s AND o.created_at < %s
        AND o.status = '20'
        AND o.shop_code <> 'TWI000'
    GROUP BY biz_date, o.shop_code, c.digital, s.shop_name
)
SELECT
    os.biz_date,
    os.shop_code,
    os.storeType,
    os.shop_name,
    os.total_amount,
    os.member_amount,
    os.member_amount_ratio_percent,
    os.order_count,
    sa.area,
    sa.Addr1,
    sa.Addr2,
    sa.Addr3,
    sa.phone,
    sa.openingtime,
    sa.LON,
    sa.LAT,
    sa.isEnable,
    sa.isdelivery,
    sa.SMS_addr
FROM OrderStats os
LEFT JOIN kiosk.ShopsArea sa ON os.shop_code = sa.shopcode
ORDER BY os.biz_date, os.member_amount_ratio_percent
"""

# Overall query — daily granularity
SQL_ALL_STORES = """
SELECT
    DATE(created_at + INTERVAL 8 HOUR) AS biz_date,
    SUM(price) AS total_amount,
    SUM(CASE
        WHEN member_id IS NOT NULL AND TRIM(member_id) <> ''
        THEN price ELSE 0
    END) AS member_amount,
    ROUND(SUM(CASE
        WHEN member_id IS NOT NULL AND TRIM(member_id) <> ''
        THEN price ELSE 0
    END) * 100.0 / SUM(price), 2) AS member_amount_ratio_percent,
    COUNT(*) AS order_count
FROM kiosk.orders
WHERE
    created_at >= %s AND created_at < %s
    AND status = '20'
    AND shop_code <> 'TWI000'
GROUP BY biz_date
ORDER BY biz_date
"""


def init_sqlite(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS store_daily (
            biz_date TEXT NOT NULL,
            shop_code TEXT NOT NULL,
            store_type TEXT,
            shop_name TEXT,
            total_amount REAL,
            member_amount REAL,
            member_ratio REAL,
            order_count INTEGER,
            area TEXT,
            addr1 TEXT,
            addr2 TEXT,
            addr3 TEXT,
            phone TEXT,
            opening_time TEXT,
            lon REAL,
            lat REAL,
            is_enable INTEGER,
            is_delivery INTEGER,
            sms_addr TEXT,
            synced_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (biz_date, shop_code)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS overall_daily (
            biz_date TEXT NOT NULL PRIMARY KEY,
            total_amount REAL,
            member_amount REAL,
            member_ratio REAL,
            order_count INTEGER,
            synced_at TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_start TEXT,
            sync_end TEXT,
            date_from TEXT,
            date_to TEXT,
            store_rows INTEGER,
            overall_rows INTEGER
        )
    """)

    conn.commit()
    return conn


def to_utc_ts(local_date_str):
    """Convert Taiwan local date (YYYY-MM-DD) to UTC timestamp for MySQL query.
    Taiwan is UTC+8, so midnight local = 16:00 previous day UTC.
    """
    d = datetime.strptime(local_date_str, "%Y-%m-%d")
    return (d - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")


def get_last_synced_date(db_path):
    """Return the latest biz_date already in SQLite, or None if empty."""
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT MAX(biz_date) FROM store_daily")
        row = c.fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def sync_data(date_from, date_to):
    utc_from = to_utc_ts(date_from)
    utc_to = to_utc_ts(date_to)

    print(f"📡 Connecting to MySQL {MYSQL_CONFIG['host']}...")
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)

    print(f"📅 Syncing data: {date_from} → {date_to}")
    print(f"   (UTC range: {utc_from} → {utc_to})")

    # Fetch store-level daily data
    print("🔍 Querying per-store daily data...")
    with mysql_conn.cursor() as cur:
        cur.execute(SQL_EACH_STORE, (utc_from, utc_to))
        store_rows = cur.fetchall()
    print(f"   → {len(store_rows)} store-day rows")

    # Fetch overall daily data
    print("🔍 Querying overall daily data...")
    with mysql_conn.cursor() as cur:
        cur.execute(SQL_ALL_STORES, (utc_from, utc_to))
        overall_rows = cur.fetchall()
    print(f"   → {len(overall_rows)} daily rows")

    mysql_conn.close()

    # Write to SQLite
    print(f"💾 Writing to {SQLITE_DB}...")
    sqlite_conn = init_sqlite(SQLITE_DB)
    c = sqlite_conn.cursor()

    # Upsert store daily data
    for row in store_rows:
        biz_date = row[0].strftime("%Y-%m-%d") if isinstance(row[0], date) else str(row[0])
        def to_float(v):
            if v is None:
                return None
            return float(v)

        c.execute("""
            INSERT OR REPLACE INTO store_daily
            (biz_date, shop_code, store_type, shop_name, total_amount, member_amount,
             member_ratio, order_count, area, addr1, addr2, addr3, phone, opening_time,
             lon, lat, is_enable, is_delivery, sms_addr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            biz_date, row[1], row[2], row[3],
            to_float(row[4]), to_float(row[5]), to_float(row[6]), int(row[7]) if row[7] else 0,
            row[8], row[9], row[10], row[11], row[12], row[13],
            to_float(row[14]), to_float(row[15]),
            row[16], row[17], row[18]
        ))

    # Upsert overall daily data
    for row in overall_rows:
        biz_date = row[0].strftime("%Y-%m-%d") if isinstance(row[0], date) else str(row[0])
        c.execute("""
            INSERT OR REPLACE INTO overall_daily
            (biz_date, total_amount, member_amount, member_ratio, order_count)
            VALUES (?, ?, ?, ?, ?)
        """, (biz_date, float(row[1]) if row[1] else 0,
              float(row[2]) if row[2] else 0,
              float(row[3]) if row[3] else 0,
              int(row[4]) if row[4] else 0))

    # Log sync
    c.execute("""
        INSERT INTO sync_log (sync_start, sync_end, date_from, date_to, store_rows, overall_rows)
        VALUES (datetime('now'), datetime('now'), ?, ?, ?, ?)
    """, (date_from, date_to, len(store_rows), len(overall_rows)))

    sqlite_conn.commit()
    sqlite_conn.close()

    print(f"✅ Sync complete! {len(store_rows)} store rows, {len(overall_rows)} overall rows")
    return len(store_rows), len(overall_rows)


def main():
    parser = argparse.ArgumentParser(description="Sync MySQL → SQLite for member sales mix")
    parser.add_argument("--from", dest="date_from", default=None,
                        help="Start date (Taiwan local, YYYY-MM-DD). Default: auto-detect from last synced date")
    parser.add_argument("--to", dest="date_to", default=None,
                        help="End date exclusive (Taiwan local, default: tomorrow)")
    parser.add_argument("--full", action="store_true",
                        help="Force full sync from 2026-01-01 (ignore existing data)")
    args = parser.parse_args()

    date_to = args.date_to or (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    if args.full:
        date_from = args.date_from or "2026-01-01"
        print("🔄 Full sync requested")
    elif args.date_from:
        date_from = args.date_from
    else:
        last_synced = get_last_synced_date(SQLITE_DB)
        if last_synced:
            # Re-sync the last synced date (may have been partial) + new dates
            date_from = last_synced
            print(f"📊 Incremental sync: last synced date = {last_synced}, fetching from {date_from}")
        else:
            date_from = "2026-01-01"
            print("📊 No existing data found, performing full sync")

    sync_data(date_from, date_to)


if __name__ == "__main__":
    main()
