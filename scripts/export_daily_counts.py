"""Export the daily rider-type counts used in the hypothesis tests.

Run from the project root after scripts/clean_2025.py. Both outputs cover rides that
started from January 1 through July 31, 2025 (New York local time), the same window as
the EDA, and are written to data/clean/, which Git ignores.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
TRIPS = ROOT / "data/clean/trips_clean.parquet"
OUT = ROOT / "data/clean"
WINDOW = "started_at >= '2025-01-01' AND started_at < '2025-08-01'"

db = duckdb.connect()

# One row per day and rider type. Includes rides without a start station.
db.execute(f"""COPY (
    SELECT CAST(started_at AS DATE) AS day, member_casual,
           COUNT(*) AS rides,
           COUNT_IF(rideable_type = 'electric_bike') AS electric
    FROM '{TRIPS}'
    WHERE {WINDOW}
    GROUP BY 1, 2 ORDER BY 1, 2
) TO '{OUT / "daily_rider_counts.csv"}' (HEADER)""")

# One row per day, start station and rider type. Used for the stratified tests.
db.execute(f"""COPY (
    SELECT CAST(started_at AS DATE) AS day, start_station_id, member_casual,
           COUNT(*) AS rides,
           COUNT_IF(rideable_type = 'electric_bike') AS electric
    FROM '{TRIPS}'
    WHERE {WINDOW} AND start_station_id IS NOT NULL
    GROUP BY 1, 2, 3
) TO '{OUT / "daily_station_rider_counts.parquet"}' (FORMAT parquet)""")

print("Wrote daily_rider_counts.csv and daily_station_rider_counts.parquet to", OUT)
