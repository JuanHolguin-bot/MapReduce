import logging
from typing import Any, Dict, List
from collections import defaultdict

from fastapi import FastAPI
from pydantic import BaseModel

from mapper import mapper
from reducer import reducer
from metrics import ShotMetrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MapReduce Worker")

class MapRequest(BaseModel):
    chunk: List[Dict[str, str]]
    filters: Dict[str, str] = {}
    x_bins: int = 12
    y_bins: int = 8

class MappedItem(BaseModel):
    key: List[Any]
    metrics: Dict[str, Any]

class MapResponse(BaseModel):
    mapped: List[MappedItem]

class ReduceRequest(BaseModel):
    mapped_data: List[MappedItem]

class ReduceResponseItem(BaseModel):
    key: List[Any]
    metrics: Dict[str, Any]

class ReduceResponse(BaseModel):
    reduced: List[ReduceResponseItem]


def make_serializable(k):
    if isinstance(k, tuple):
        return [make_serializable(i) for i in k]
    return k

def reconstruct_tuple(k):
    if isinstance(k, list):
        return tuple(reconstruct_tuple(i) for i in k)
    return k


@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.post("/map", response_model=MapResponse)
def run_map(req: MapRequest):
    logger.info(f"Received MAP request for {len(req.chunk)} rows with filters {req.filters}.")
    
    # 1. Run local mapper
    mapped_gen = mapper(req.chunk, req.filters, req.x_bins, req.y_bins)
    
    # 2. Local Combiner (optimization to reduce network traffic)
    combiner = defaultdict(ShotMetrics)
    for key, metrics in mapped_gen:
        combiner[key].merge(metrics)
        
    # 3. Serialize to JSON
    mapped_list = []
    for key, metrics in combiner.items():
        json_key = [make_serializable(k) for k in key]
        mapped_list.append(MappedItem(
            key=json_key,
            metrics={
                "shots": metrics.shots,
                "goals": metrics.goals,
                "misses": metrics.misses,
                "xg_sum": metrics.xg_sum
            }
        ))
        
    logger.info(f"MAP completed. Emitting {len(mapped_list)} combined keys.")
    return MapResponse(mapped=mapped_list)


@app.post("/reduce", response_model=ReduceResponse)
def run_reduce(req: ReduceRequest):
    logger.info(f"Received REDUCE request with {len(req.mapped_data)} items.")
    
    # 1. Deserialize from JSON
    mapped_for_reducer = []
    for item in req.mapped_data:
        key_tuple = tuple(reconstruct_tuple(k) for k in item.key)
        m = ShotMetrics(
            shots=item.metrics["shots"],
            goals=item.metrics["goals"],
            misses=item.metrics["misses"],
            xg_sum=item.metrics["xg_sum"]
        )
        mapped_for_reducer.append((key_tuple, m))
        
    # 2. Run global reducer
    reduced_dict = reducer(mapped_for_reducer)
    
    # 3. Serialize results
    result = []
    for key, metrics in reduced_dict.items():
        json_key = [make_serializable(k) for k in key]
        result.append(ReduceResponseItem(
            key=json_key,
            metrics={
                "shots": metrics.shots,
                "goals": metrics.goals,
                "misses": metrics.misses,
                "xg_sum": metrics.xg_sum
            }
        ))
        
    logger.info(f"REDUCE completed. Emitting {len(result)} reduced keys.")
    return ReduceResponse(reduced=result)
