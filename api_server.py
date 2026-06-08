#!/usr/bin/env python3
"""
Local API server for live MySQL queries from the frontend.
Run this on your PC when you want real-time data.

Usage:
  python3 api_server.py              # Start on port 5050
  python3 api_server.py --port 8080  # Custom port
"""

import argparse
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import pymysql
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

MYSQL_HOST = "34.81.120.135"
MYSQL_PORT = 3306
MYSQL_USER = "readonly_user"
MYSQL_DB = "kiosk"

SQL_EACH_STORE = """
WITH OrderStats AS (
    SELECT
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
    GROUP BY o.shop_code, c.digital, s.shop_name
)
SELECT
    os.shop_code,
    os.storeType,
    os.shop_name,
    os.total_amount,
    os.member_amount,
    os.member_amount_ratio_percent,
    os.order_count,
    sa.area,
    sa.Addr1,
    sa.LON,
    sa.LAT
FROM OrderStats os
LEFT JOIN kiosk.ShopsArea sa ON os.shop_code = sa.shopcode
ORDER BY os.member_amount_ratio_percent
"""

SQL_OVERALL = """
SELECT
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
"""


def to_utc_ts(local_date_str):
    d = datetime.strptime(local_date_str, "%Y-%m-%d")
    return (d - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError


@app.route("/api/query", methods=["POST"])
def query_data():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    password = data.get("password", "")
    date_from = data.get("from", "")
    date_to = data.get("to", "")

    if not password:
        return jsonify({"error": "Password is required"}), 401
    if not date_from or not date_to:
        return jsonify({"error": "from and to dates required"}), 400

    try:
        conn = pymysql.connect(
            host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
            password=password, database=MYSQL_DB,
            charset="utf8mb4", connect_timeout=15, read_timeout=120,
        )
    except (pymysql.err.OperationalError, pymysql.Error) as e:
        return jsonify({"error": f"DB connection failed: {e}"}), 401

    utc_from = to_utc_ts(date_from)
    # date_to is inclusive, so add 1 day for the query
    to_date_obj = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    utc_to = to_utc_ts(to_date_obj.strftime("%Y-%m-%d"))

    try:
        # Per-store query
        with conn.cursor() as cur:
            cur.execute(SQL_EACH_STORE, (utc_from, utc_to))
            store_rows = cur.fetchall()

        stores = []
        for r in store_rows:
            sc = r[0]
            if not sc or not sc.strip():
                continue
            stores.append({
                "sc": sc, "st": str(r[1]) if r[1] else "",
                "sn": r[2] or "", "ta": float(r[3] or 0),
                "ma": float(r[4] or 0), "mr": float(r[5] or 0),
                "oc": int(r[6] or 0),
                "addr": r[8] or "",
                "lon": float(r[9]) if r[9] else None,
                "lat": float(r[10]) if r[10] else None,
            })

        # Overall query
        with conn.cursor() as cur:
            cur.execute(SQL_OVERALL, (utc_from, utc_to))
            overall_row = cur.fetchone()

        overall = {
            "ta": float(overall_row[0] or 0),
            "ma": float(overall_row[1] or 0),
            "mr": float(overall_row[2] or 0),
            "oc": int(overall_row[3] or 0),
        } if overall_row else {}

        conn.close()
        return jsonify({
            "stores": stores,
            "overall": overall,
            "query": {"from": date_from, "to": date_to},
        })

    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()
    print(f"🚀 API server starting on http://localhost:{args.port}")
    print(f"   POST /api/query  — live MySQL query (requires password)")
    print(f"   GET  /api/health — health check")
    app.run(host="0.0.0.0", port=args.port, debug=False)
