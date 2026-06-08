# Export latest data to JSON (for GitHub Pages)

python3 sync_mysql_to_sqlite.py && python3 export_to_json.py

# For live MySQL queries, run on your PC:

python3 api_server.py

# Then click ⚡ Live button in the frontend
