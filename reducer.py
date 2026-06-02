from collections import defaultdict
from typing import Dict, Iterable, Tuple, Any

from metrics import ShotMetrics


def reducer(
    mapped: Iterable[Tuple[Tuple[Any, ...], ShotMetrics]]
) -> Dict[Tuple[Any, ...], ShotMetrics]:
    aggregation: Dict[Tuple[Any, ...], ShotMetrics] = defaultdict(ShotMetrics)
    for key, metrics in mapped:
        aggregation[key].merge(metrics)
    return aggregation
