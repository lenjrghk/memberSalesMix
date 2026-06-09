# Export latest data to JSON (for GitHub Pages)

```bash
# Incremental sync (only fetches new data since last sync)
python3 01_sync_mysql_to_sqlite.py && python3 02_export_to_json.py

# Force full sync from 2026-01-01
python3 01_sync_mysql_to_sqlite.py --full && python3 02_export_to_json.py

# Sync specific date range
python3 01_sync_mysql_to_sqlite.py --from 2026-06-01 --to 2026-06-09 && python3 02_export_to_json.py
```

# For live MySQL queries, run on your PC:

python3 api_server.py

# Then click ⚡ Live button in the frontend
