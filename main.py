import argparse
import csv
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Any

from mapper import mapper
from metrics import ShotMetrics
from reducer import reducer
from visualization import save_hotzone_html


def read_csv_rows(path: str) -> Iterable[Dict[str, str]]:
    with open(path, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def mapreduce_hotzones(
    csv_path: str,
    group_by: Optional[Sequence[str]] = None,
    x_bins: int = 12,
    y_bins: int = 8,
) -> Dict[Tuple[Any, ...], ShotMetrics]:
    if group_by is None:
        group_by = ["zone"]

    mapped = mapper(read_csv_rows(csv_path), group_by, x_bins, y_bins)
    reduced = reducer(mapped)
    return reduced


def format_result(
    aggregation: Dict[Tuple[Any, ...], ShotMetrics],
    group_by: Sequence[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for key, metrics in aggregation.items():
        row: Dict[str, Any] = {}
        for field, value in zip(group_by, key):
            if field == "zone":
                row["zone_x"], row["zone_y"] = value
            else:
                row[field] = value
        row.update(
            {
                "shots": metrics.shots,
                "goals": metrics.goals,
                "misses": metrics.misses,
                "xg_sum": round(metrics.xg_sum, 6),
                "goal_rate": round(metrics.goals / metrics.shots, 4) if metrics.shots else 0.0,
                "avg_xg": round(metrics.xg_sum / metrics.shots, 6) if metrics.shots else 0.0,
            }
        )
        rows.append(row)
    return rows


def parse_filter_args(filter_args: Optional[List[str]]) -> Dict[str, str]:
    filters: Dict[str, str] = {}
    if not filter_args:
        return filters
    for item in filter_args:
        if "=" not in item:
            raise ValueError(f"Filtro inválido: {item}. Use clave=valor")
        key, value = item.split("=", 1)
        filters[key.strip()] = value.strip()
    return filters


def apply_filters(rows: List[Dict[str, Any]], filters: Dict[str, str]) -> List[Dict[str, Any]]:
    if not filters:
        return rows
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        if all(str(row.get(key, "")) == value for key, value in filters.items()):
            filtered.append(row)
    return filtered


def build_sqlite_db(csv_path: str, db_path: str = "shots_summary.db", x_bins: int = 12, y_bins: int = 8) -> None:
    import sqlite3
    
    print("Iniciando MapReduce para generar la base de datos...")
    group_by = ["league", "team", "player", "season", "situation", "shot_type", "zone"]
    # Run mapreduce
    result = mapreduce_hotzones(csv_path, group_by, x_bins, y_bins)
    rows = format_result(result, group_by)
    print(f"MapReduce finalizado. Insertando {len(rows)} filas agregadas en SQLite...")
    
    # Connect to SQLite
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Drop existing table if exists to regenerate fresh
    cursor.execute("DROP TABLE IF EXISTS shots")
    
    # Create table
    cursor.execute("""
        CREATE TABLE shots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league TEXT,
            team TEXT,
            player TEXT,
            season TEXT,
            situation TEXT,
            shot_type TEXT,
            zone_x INTEGER,
            zone_y INTEGER,
            shots INTEGER,
            goals INTEGER,
            misses INTEGER,
            xg_sum REAL
        )
    """)
    
    # Insert data
    insert_query = """
        INSERT INTO shots (league, team, player, season, situation, shot_type, zone_x, zone_y, shots, goals, misses, xg_sum)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    db_rows = []
    for r in rows:
        db_rows.append((
            r.get("league", ""),
            r.get("team", ""),
            r.get("player", ""),
            r.get("season", ""),
            r.get("situation", ""),
            r.get("shot_type", ""),
            r.get("zone_x", 0),
            r.get("zone_y", 0),
            r.get("shots", 0),
            r.get("goals", 0),
            r.get("misses", 0),
            r.get("xg_sum", 0.0)
        ))
        
    cursor.executemany(insert_query, db_rows)
    
    # Create indexes for fast querying
    print("Creando índices para optimizar consultas...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_shots_lookup ON shots(league, team, player)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_shots_filters ON shots(season, situation, shot_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_shots_zones ON shots(zone_x, zone_y)")
    
    conn.commit()
    conn.close()
    print(f"Base de datos generada exitosamente en {db_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Procesa un dataset de disparos y agrupa hotzones con MapReduce local."
    )
    parser.add_argument("csv_path", help="Ruta al archivo CSV de disparos")
    parser.add_argument(
        "--build-db",
        action="store_true",
        help="Genera la base de datos SQLite 'shots_summary.db' a partir de los datos MapReduce.",
    )
    parser.add_argument(
        "--group-by",
        nargs="*",
        default=["league", "player", "zone"],
        help="Campos para agrupar antes de construir hotzones. Use 'zone' para la celda de pitch.",
    )
    parser.add_argument("--x-bins", type=int, default=12, help="Número de celdas horizontales")
    parser.add_argument("--y-bins", type=int, default=8, help="Número de celdas verticales")
    parser.add_argument(
        "--metric",
        default="shots",
        choices=["shots", "goals", "xg_sum", "goal_rate", "avg_xg"],
        help="Métrica a visualizar en la hotzone.",
    )
    parser.add_argument(
        "--html-output",
        default=None,
        help="Ruta del archivo HTML donde guardar la hotzone.",
    )
    parser.add_argument(
        "--filter",
        nargs="*",
        default=None,
        help="Filtro opcional en formato clave=valor para seleccionar un solo grupo antes de graficar.",
    )
    args = parser.parse_args()

    if args.build_db:
        build_sqlite_db(args.csv_path, x_bins=args.x_bins, y_bins=args.y_bins)
        import sys
        sys.exit(0)

    group_by = list(args.group_by)
    if args.html_output and "zone" not in group_by:
        group_by.append("zone")

    result = mapreduce_hotzones(args.csv_path, group_by, args.x_bins, args.y_bins)
    rows = format_result(result, group_by)
    print(f"Filas agregadas: {len(rows)}")
    for row in rows[:20]:
        print(row)

    if args.html_output:
        filters = parse_filter_args(args.filter)
        rows = apply_filters(rows, filters)
        if not rows:
            raise SystemExit("No se encontraron filas para el filtro aplicado.")
        save_hotzone_html(
            rows,
            args.html_output,
            metric=args.metric,
            title=f"Hotzone: {args.metric}",
            x_bins=args.x_bins,
            y_bins=args.y_bins,
        )
        print(f"Hotzone guardada en {args.html_output}")
