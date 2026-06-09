from typing import Any, Dict, Iterable, List, Sequence, Tuple

from metrics import ShotMetrics


def parse_shot_row(row: Dict[str, str]) -> Dict[str, Any]:
    return {
        "player": row.get("player", ""),
        "player_id": int(row.get("player_id", "0")) if row.get("player_id") else None,
        "league": row.get("lega", ""),
        "season": row.get("season", ""),
        "match_id": row.get("match_id", ""),
        "team": row.get("h_team") if row.get("h_a") == "h" else row.get("a_team"),
        "home_away": row.get("h_a", ""),
        "situation": row.get("situation", ""),
        "shot_type": row.get("shotType", ""),
        "preferred_foot": row.get("Preffered_Foot", ""),
        "result": int(row.get("result", "0")) if row.get("result") else 0,
        "xg": float(row.get("xG Understat", "0")) if row.get("xG Understat") else 0.0,
        "x": float(row.get("X", "0")) if row.get("X") else 0.0,
        "y": float(row.get("Y", "0")) if row.get("Y") else 0.0,
        "date": row.get("date", ""),
    }


def pitch_zone(x: float, y: float, x_bins: int = 12, y_bins: int = 8) -> Tuple[int, int]:
    zone_x = min(max(int(x * x_bins), 0), x_bins - 1)
    zone_y = min(max(int(y * y_bins), 0), y_bins - 1)
    return zone_x, zone_y


def build_group_key(
    shot: Dict[str, Any],
    group_by: Sequence[str],
    x_bins: int = 12,
    y_bins: int = 8,
) -> Tuple[Any, ...]:
    key_parts: List[Any] = []
    for field in group_by:
        if field == "zone":
            key_parts.append(pitch_zone(shot["x"], shot["y"], x_bins, y_bins))
        else:
            key_parts.append(shot.get(field, ""))
    return tuple(key_parts)


def passes_filters(shot: Dict[str, Any], filters: Dict[str, str]) -> bool:
    if not filters:
        return True
    for k, v in filters.items():
        if not v:
            continue
        if str(shot.get(k, "")) != str(v):
            return False
    return True


def mapper(
    rows: Iterable[Dict[str, str]],
    filters: Dict[str, str] = None,
    x_bins: int = 12,
    y_bins: int = 8,
) -> Iterable[Tuple[Tuple[Any, ...], ShotMetrics]]:
    if filters is None:
        filters = {}
        
    for raw_row in rows:
        shot = parse_shot_row(raw_row)
        if not passes_filters(shot, filters):
            continue
            
        metrics = ShotMetrics()
        metrics.update(shot["result"], shot["xg"])
        
        # Emit 1: Grid Zones
        zx, zy = pitch_zone(shot["x"], shot["y"], x_bins, y_bins)
        yield ("grid", zx, zy), metrics
        
        # Emit 2: Top Players
        yield ("player", shot["player"]), metrics
        
        # Emit 3: Shot Types
        yield ("shot_type", shot["shot_type"]), metrics
        
        # Emit 4: Situations
        yield ("situation", shot["situation"]), metrics
        
        # Emit 5: Global Summary
        yield ("global", "summary"), metrics
