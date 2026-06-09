import csv
import json
import logging
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import requests

from main import format_result
from metrics import ShotMetrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKERS_ENV = os.getenv("WORKERS", "http://localhost:8001,http://localhost:8002,http://localhost:8003")
WORKERS = [w.strip() for w in WORKERS_ENV.split(",") if w.strip()]

class JobStatus:
    def __init__(self):
        self.state = "idle"  # idle, mapping, shuffling, reducing, saving, finished, error
        self.progress = 0.0
        self.worker_status = {w: "idle" for w in WORKERS}
        self.message = "Ready to start."
        self.final_result = None

    def to_dict(self):
        return {
            "state": self.state,
            "progress": round(self.progress, 2),
            "worker_status": self.worker_status,
            "message": self.message
        }

job_status = JobStatus()

def read_csv_chunks(path: str, chunk_size: int = 30000):
    chunk = []
    with open(path, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
    if chunk:
        yield chunk

def map_task(worker_url: str, chunk: List[Dict[str, str]], filters: Dict[str, str], x_bins: int, y_bins: int):
    try:
        job_status.worker_status[worker_url] = f"mapping chunk ({len(chunk)} rows)"
        payload = {
            "chunk": chunk,
            "filters": filters,
            "x_bins": x_bins,
            "y_bins": y_bins
        }
        resp = requests.post(f"{worker_url}/map", json=payload)
        resp.raise_for_status()
        job_status.worker_status[worker_url] = "idle"
        return resp.json()["mapped"]
    except Exception as e:
        logger.error(f"Error in map_task on {worker_url}: {e}")
        job_status.worker_status[worker_url] = "error"
        raise

def reduce_task(worker_url: str, mapped_data: List[Dict[str, Any]]):
    try:
        job_status.worker_status[worker_url] = f"reducing ({len(mapped_data)} keys)"
        payload = {
            "mapped_data": mapped_data
        }
        resp = requests.post(f"{worker_url}/reduce", json=payload)
        resp.raise_for_status()
        job_status.worker_status[worker_url] = "idle"
        return resp.json()["reduced"]
    except Exception as e:
        logger.error(f"Error in reduce_task on {worker_url}: {e}")
        job_status.worker_status[worker_url] = "error"
        raise

def run_distributed_mapreduce_background(csv_path: str, filters: Dict[str, str], x_bins: int = 12, y_bins: int = 8):
    if job_status.state not in ["idle", "finished", "error"]:
        return False
    thread = threading.Thread(target=run_distributed_mapreduce, args=(csv_path, filters, x_bins, y_bins))
    thread.daemon = True
    thread.start()
    return True

def run_distributed_mapreduce(csv_path: str, filters: Dict[str, str], x_bins: int = 12, y_bins: int = 8):
    global job_status
    try:
        job_status.state = "mapping"
        job_status.progress = 0.0
        job_status.message = f"Reading CSV and dispatching MAP tasks with filters: {filters}"
        job_status.final_result = None
        for w in WORKERS:
            job_status.worker_status[w] = "idle"
            
        # 1. Map Phase
        mapped_results = []
        chunks = list(read_csv_chunks(csv_path, chunk_size=40000))
        total_chunks = len(chunks)
        
        with ThreadPoolExecutor(max_workers=len(WORKERS)) as executor:
            future_to_worker = {}
            for i, chunk in enumerate(chunks):
                worker_url = WORKERS[i % len(WORKERS)]
                future = executor.submit(map_task, worker_url, chunk, filters, x_bins, y_bins)
                future_to_worker[future] = worker_url
                
            completed = 0
            for future in as_completed(future_to_worker):
                mapped_results.extend(future.result())
                completed += 1
                job_status.progress = (completed / total_chunks) * 50.0  # Map is 50%
                
        # 2. Shuffle Phase
        job_status.state = "shuffling"
        job_status.message = f"Shuffling {len(mapped_results)} mapped items..."
        
        partitions = [[] for _ in range(len(WORKERS))]
        for item in mapped_results:
            key_str = json.dumps(item["key"])
            p_idx = hash(key_str) % len(WORKERS)
            partitions[p_idx].append(item)
            
        # 3. Reduce Phase
        job_status.state = "reducing"
        job_status.message = "Dispatching REDUCE tasks to workers..."
        reduced_results = []
        
        with ThreadPoolExecutor(max_workers=len(WORKERS)) as executor:
            future_to_worker = {}
            for i, p_data in enumerate(partitions):
                if not p_data:
                    continue
                worker_url = WORKERS[i]
                future = executor.submit(reduce_task, worker_url, p_data)
                future_to_worker[future] = worker_url
                
            completed = 0
            for future in as_completed(future_to_worker):
                reduced_results.extend(future.result())
                completed += 1
                job_status.progress = 50.0 + (completed / len(WORKERS)) * 40.0  # Reduce is 40%
                
        # 4. Save to DB
        job_status.state = "saving"
        job_status.message = "Assembling Final JSON Payload..."
        
        grid_data = []
        top_players_raw = []
        shot_types = {}
        situations = {}
        summary = {
            "total_shots": 0, "total_goals": 0, "total_misses": 0, "total_xg": 0.0,
            "goal_rate": 0.0, "avg_xg": 0.0
        }
        
        for item in reduced_results:
            k = item["key"]
            m = item["metrics"]
            m["goal_rate"] = round(m["goals"] / m["shots"], 4) if m["shots"] else 0.0
            m["avg_xg"] = round(m["xg_sum"] / m["shots"], 4) if m["shots"] else 0.0
            
            if k[0] == "grid":
                grid_data.append({
                    "zone_x": k[1],
                    "zone_y": k[2],
                    **m
                })
            elif k[0] == "player":
                top_players_raw.append({
                    "player": k[1],
                    "shots": m["shots"],
                    "goals": m["goals"],
                    "xg": round(m["xg_sum"], 4),
                    "goal_rate": m["goal_rate"]
                })
            elif k[0] == "shot_type":
                shot_types[k[1]] = m["shots"]
            elif k[0] == "situation":
                situations[k[1]] = m["shots"]
            elif k[0] == "global":
                summary = {
                    "total_shots": m["shots"],
                    "total_goals": m["goals"],
                    "total_misses": m["misses"],
                    "total_xg": round(m["xg_sum"], 4),
                    "goal_rate": m["goal_rate"],
                    "avg_xg": m["avg_xg"]
                }
                
        # Sort top players
        top_players_raw.sort(key=lambda x: (x["goals"], x["shots"]), reverse=True)
        top_players = top_players_raw[:10]
        
        final_result = {
            "grid": grid_data,
            "summary": summary,
            "top_players": top_players,
            "breakdowns": {
                "shot_types": shot_types,
                "situations": situations
            }
        }
        
        job_status.final_result = final_result
        
        job_status.state = "finished"
        job_status.progress = 100.0
        job_status.message = f"Job completed successfully. {len(reduced_results)} keys reduced."
        for w in WORKERS:
            job_status.worker_status[w] = "idle"
            
    except Exception as e:
        logger.error(f"Job failed: {e}")
        job_status.state = "error"
        job_status.message = f"Error: {str(e)}"
