import json
import os
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from master import run_distributed_mapreduce_background, job_status

class ShotVisualizerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Prevent console spam with static file requests
        pass

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        # Flatten query params (parse_qs returns lists of values)
        params = {k: v[0] for k, v in query_params.items() if v}
        
        if path == "/api/filters":
            self.handle_api_filters()
        elif path == "/api/teams":
            self.handle_api_teams(params)
        elif path == "/api/players":
            self.handle_api_players(params)
        elif path == "/api/data":
            self.handle_api_data(params)
        elif path == "/api/start_job":
            self.handle_api_start_job(params)
        elif path == "/api/job_status":
            self.handle_api_job_status()
        elif path == "/api/job_result":
            self.handle_api_job_result()
        else:
            # Serve static files from the 'web' directory
            self.handle_static_files(path)

    def handle_static_files(self, path):
        # Default to index.html
        if path == "/" or path == "":
            path = "/index.html"
            
        clean_path = path.lstrip("/")
        file_path = os.path.join("web", clean_path)
        
        # Security check: resolve to absolute paths and check boundary
        abs_web_dir = os.path.abspath("web")
        abs_file_path = os.path.abspath(file_path)
        
        if not abs_file_path.startswith(abs_web_dir):
            self.send_error(403, "Access Denied")
            return
            
        if not os.path.exists(file_path) or os.path.isdir(file_path):
            self.send_error(404, "File Not Found")
            return
            
        # Determine content type
        content_type = "text/html"
        if file_path.endswith(".css"):
            content_type = "text/css"
        elif file_path.endswith(".js"):
            content_type = "application/javascript"
        elif file_path.endswith(".json"):
            content_type = "application/json"
        elif file_path.endswith(".png"):
            content_type = "image/png"
        elif file_path.endswith(".svg"):
            content_type = "image/svg+xml"
            
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(os.path.getsize(file_path)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

    def handle_api_filters(self):
        db_path = "shots_summary.db"
        if not os.path.exists(db_path):
            self.send_error(500, "Database not generated. Run main.py --build-db first.")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Leagues
        cursor.execute("SELECT DISTINCT league FROM shots WHERE league != '' ORDER BY league")
        leagues = [row[0] for row in cursor.fetchall()]
        
        # Seasons
        cursor.execute("SELECT DISTINCT season FROM shots WHERE season != '' ORDER BY season DESC")
        seasons = [row[0] for row in cursor.fetchall()]
        
        # Situations
        cursor.execute("SELECT DISTINCT situation FROM shots WHERE situation != '' ORDER BY situation")
        situations = [row[0] for row in cursor.fetchall()]
        
        # Shot Types
        cursor.execute("SELECT DISTINCT shot_type FROM shots WHERE shot_type != '' ORDER BY shot_type")
        shot_types = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        response = {
            "leagues": leagues,
            "seasons": seasons,
            "situations": situations,
            "shot_types": shot_types
        }
        self.send_json_response(response)

    def handle_api_teams(self, params):
        league = params.get("league")
        db_path = "shots_summary.db"
        if not os.path.exists(db_path):
            self.send_error(500, "Database not found.")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        if league:
            cursor.execute("SELECT DISTINCT team FROM shots WHERE league = ? AND team != '' ORDER BY team", (league,))
        else:
            cursor.execute("SELECT DISTINCT team FROM shots WHERE team != '' ORDER BY team")
            
        teams = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        self.send_json_response({"teams": teams})

    def handle_api_players(self, params):
        league = params.get("league")
        team = params.get("team")
        db_path = "shots_summary.db"
        if not os.path.exists(db_path):
            self.send_error(500, "Database not found.")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        conditions = []
        sql_params = []
        
        if league:
            conditions.append("league = ?")
            sql_params.append(league)
        if team:
            conditions.append("team = ?")
            sql_params.append(team)
            
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"SELECT DISTINCT player FROM shots WHERE {where_clause} AND player != '' ORDER BY player"
        cursor.execute(query, tuple(sql_params))
        players = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        self.send_json_response({"players": players})

    def handle_api_data(self, params):
        db_path = "shots_summary.db"
        if not os.path.exists(db_path):
            self.send_error(500, "Database not found.")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        conditions = []
        sql_params = []
        
        for field in ["league", "team", "player", "season", "situation", "shot_type"]:
            val = params.get(field)
            if val:
                conditions.append(f"{field} = ?")
                sql_params.append(val)
                
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # 1. Query Grid data
        grid_query = f"""
            SELECT zone_x, zone_y, SUM(shots), SUM(goals), SUM(misses), SUM(xg_sum)
            FROM shots
            WHERE {where_clause}
            GROUP BY zone_x, zone_y
        """
        cursor.execute(grid_query, tuple(sql_params))
        grid_rows = cursor.fetchall()
        
        # 2. Query Global statistics
        stats_query = f"""
            SELECT SUM(shots), SUM(goals), SUM(misses), SUM(xg_sum)
            FROM shots
            WHERE {where_clause}
        """
        cursor.execute(stats_query, tuple(sql_params))
        stats_row = cursor.fetchone()
        total_shots = stats_row[0] or 0
        total_goals = stats_row[1] or 0
        total_misses = stats_row[2] or 0
        total_xg = stats_row[3] or 0.0
        
        # 3. Query Top Players
        top_players_query = f"""
            SELECT player, SUM(shots) as p_shots, SUM(goals) as p_goals, SUM(xg_sum) as p_xg
            FROM shots
            WHERE {where_clause}
            GROUP BY player
            ORDER BY p_goals DESC, p_shots DESC
            LIMIT 10
        """
        cursor.execute(top_players_query, tuple(sql_params))
        top_players_rows = cursor.fetchall()
        
        top_players = []
        for row in top_players_rows:
            top_players.append({
                "player": row[0],
                "shots": row[1],
                "goals": row[2],
                "xg": round(row[3], 4),
                "goal_rate": round(row[2]/row[1], 4) if row[1] else 0.0
            })
            
        # 4. Query Shot Type breakdown
        shot_type_query = f"""
            SELECT shot_type, SUM(shots) as t_shots
            FROM shots
            WHERE {where_clause}
            GROUP BY shot_type
            ORDER BY t_shots DESC
        """
        cursor.execute(shot_type_query, tuple(sql_params))
        shot_types = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 5. Query Situation breakdown
        situation_query = f"""
            SELECT situation, SUM(shots) as s_shots
            FROM shots
            WHERE {where_clause}
            GROUP BY situation
            ORDER BY s_shots DESC
        """
        cursor.execute(situation_query, tuple(sql_params))
        situations = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        # Process grid rows
        grid_data = []
        for row in grid_rows:
            zx, zy, shots, goals, misses, xg_sum = row
            grid_data.append({
                "zone_x": zx,
                "zone_y": zy,
                "shots": shots,
                "goals": goals,
                "misses": misses,
                "xg_sum": round(xg_sum, 4),
                "goal_rate": round(goals/shots, 4) if shots else 0.0,
                "avg_xg": round(xg_sum/shots, 4) if shots else 0.0
            })
            
        response = {
            "grid": grid_data,
            "summary": {
                "total_shots": total_shots,
                "total_goals": total_goals,
                "total_misses": total_misses,
                "total_xg": round(total_xg, 4),
                "goal_rate": round(total_goals/total_shots, 4) if total_shots else 0.0,
                "avg_xg": round(total_xg/total_shots, 4) if total_shots else 0.0
            },
            "top_players": top_players,
            "breakdowns": {
                "shot_types": shot_types,
                "situations": situations
            }
        }
        self.send_json_response(response)

    def send_json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def handle_api_start_job(self, params):
        filters = {k: v for k, v in params.items() if v}
        success = run_distributed_mapreduce_background(
            csv_path="shots_dataset_cleaned.csv",
            filters=filters
        )
        if success:
            self.send_json_response({"status": "started"})
        else:
            self.send_error(400, "Job is already running or in error state")

    def handle_api_job_status(self):
        self.send_json_response(job_status.to_dict())

    def handle_api_job_result(self):
        if job_status.final_result:
            self.send_json_response(job_status.final_result)
        else:
            self.send_error(404, "Job result not available yet.")

def run_server(port=8080):
    # Ensure static web dir exists
    if not os.path.exists("web"):
        os.makedirs("web")
        
    server_address = ("", port)
    httpd = HTTPServer(server_address, ShotVisualizerHandler)
    print(f"Servidor iniciado en http://localhost:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
