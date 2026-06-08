#!/usr/bin/env python3
"""Export member_sales.db to compact JSON for frontend consumption."""

import json
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "member_sales.db")
OUT_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_PATH = os.path.join(OUT_DIR, "store_daily.json")


def round2(v):
    return round(v, 2) if isinstance(v, float) else v


def build_addr(addr1, addr2, addr3):
    parts = [p for p in (addr1, addr2, addr3) if p]
    return "".join(parts) if parts else ""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # --- store_daily ---
    rows = conn.execute(
        "SELECT * FROM store_daily WHERE shop_code IS NOT NULL AND shop_code != '' ORDER BY biz_date, shop_code"
    ).fetchall()

    store_daily = []
    for r in rows:
        store_daily.append({
            "d": r["biz_date"],
            "sc": r["shop_code"],
            "st": r["store_type"],
            "sn": r["shop_name"],
            "ta": round2(r["total_amount"]),
            "ma": round2(r["member_amount"]),
            "mr": round2(r["member_ratio"]),
            "oc": r["order_count"],
            "lat": round2(r["lat"]),
            "lon": round2(r["lon"]),
            "addr": build_addr(r["addr1"], r["addr2"], r["addr3"]),
        })

    # --- overall_daily ---
    rows = conn.execute("SELECT * FROM overall_daily ORDER BY biz_date").fetchall()
    overall_daily = []
    for r in rows:
        overall_daily.append({
            "d": r["biz_date"],
            "ta": round2(r["total_amount"]),
            "ma": round2(r["member_amount"]),
            "mr": round2(r["member_ratio"]),
            "oc": r["order_count"],
        })

    # --- meta ---
    dates = [r["d"] for r in store_daily]
    shops = {r["sc"] for r in store_daily}
    meta = {
        "min_date": min(dates) if dates else None,
        "max_date": max(dates) if dates else None,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "store_count": len(shops),
        "day_count": len(set(dates)),
    }

    conn.close()

    payload = {"meta": meta, "store_daily": store_daily, "overall_daily": overall_daily}
    json_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(json_str)

    # Also write JS wrapper for file:// protocol support
    js_path = OUT_PATH.replace(".json", ".js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("window.__STORE_DAILY_DATA__ = ")
        f.write(json_str)
        f.write(";")

    size = os.path.getsize(OUT_PATH)
    print(f"Exported {len(store_daily)} store_daily rows, {len(overall_daily)} overall_daily rows")
    print(f"  → {OUT_PATH}  ({size/1024:.1f} KB / {size/1024/1024:.2f} MB)")
    print(f"  → {js_path}  (JS wrapper for file:// protocol)")


if __name__ == "__main__":
    main()
