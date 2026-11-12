"""Build cleaned trip and station-hour Parquet files from the prepared 2025 release."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "data/prepared"
OUT = ROOT / "data/clean"
OUT.mkdir(exist_ok=True)
db = duckdb.connect()
db.execute("SET threads=4")
db.execute("SET memory_limit='3GB'")
db.execute("SET TimeZone='UTC'")

def quote(path):
    return "'" + str(path).replace("'", "''") + "'"

def summary(query):
    result = db.execute(query)
    return dict(zip([c[0] for c in result.description], result.fetchone()))

def clock_issue(column):
    return f"""({column} >= '2025-03-09 02:00' AND {column} < '2025-03-09 03:00')
        OR ({column} >= '2025-11-02 01:00' AND {column} < '2025-11-02 02:00')"""

with TemporaryDirectory(dir=OUT) as staging:
    stage = Path(staging)
    db.execute("SET temp_directory=" + quote(stage / "spill"))
    db.execute(f"CREATE VIEW source AS SELECT * FROM read_parquet({quote(PREP / 'trips/*.parquet')})")
    audit = {}
    audit["source"] = summary("SELECT count(*) AS rows, count(distinct ride_id) AS unique_ids FROM source")
    assert audit["source"]["rows"] == audit["source"]["unique_ids"]
    trips = stage / "trips_clean.parquet"
    replacements = [f"nullif(trim({c}), '') AS {c}" for c in
                    ("start_station_id","end_station_id","start_station_name","end_station_name")]
    for side in ("start","end"):
        for axis, limit in (("lat",90),("lng",180)):
            c = f"{side}_{axis}"
            replacements.append(f"CASE WHEN {c} BETWEEN -{limit} AND {limit} THEN {c} END AS {c}")
    # Most rides stay on the same side of a clock change; convert only those spanning one.
    crosses = " OR ".join(f"(started_at < '{t}' AND ended_at >= '{t}')" for t in
                          ("2025-03-09 03:00","2025-11-02 02:00"))
    db.execute(f"""COPY (WITH normalized AS (
        SELECT * REPLACE ({', '.join(replacements)}),
          ({clock_issue('started_at')} OR {clock_issue('ended_at')}) AS clock_uncertain
        FROM source), timed AS (
        SELECT *, CASE WHEN clock_uncertain THEN NULL WHEN {crosses}
          THEN epoch(timezone('America/New_York', ended_at)-timezone('America/New_York', started_at))
          ELSE epoch(ended_at-started_at) END AS duration_seconds FROM normalized)
        SELECT *, coalesce(duration_seconds > 0 AND duration_seconds <= 86400,false) AS duration_eligible
        FROM timed) TO {quote(trips)} (FORMAT parquet, COMPRESSION zstd)""")
    db.execute(f"CREATE VIEW trips AS SELECT * FROM {quote(trips)}")
    audit["trips"] = summary("""SELECT count(*) AS rows, countif(clock_uncertain) AS ambiguous_or_invalid_clock,
      countif(duration_seconds>86400) AS over_24h, countif(duration_eligible) AS duration_eligible,
      countif(start_station_id IS NULL) AS missing_start, countif(end_station_id IS NULL) AS missing_end FROM trips""")

    observed = PREP / "station_hour_observed.parquet"
    db.execute(f"""CREATE TEMP TABLE events AS SELECT nullif(trim(station_id),'') station,
      hour_local,sum(departures)::integer dep,sum(arrivals)::integer arr FROM {quote(observed)}
      GROUP BY 1,2""")
    issue = clock_issue("hour_local")
    audit["excluded_clock_hours"] = summary(f"SELECT count(*) AS station_hours,sum(dep) AS departures,sum(arr) AS arrivals FROM events WHERE {issue}")
    hourly = stage / "station_hour_clean.parquet"
    # Keep observed cold starts for reconciliation. Eligibility uses previous hours only.
    db.execute(f"""COPY (WITH valid AS (
        SELECT station,timezone('America/New_York',hour_local) AS t,dep,arr
        FROM events WHERE station IS NOT NULL AND NOT ({issue})),
      bounds AS (SELECT station,min(t) first_t, least(max(t)+interval '24 hours',
        timezone('America/New_York',timestamp '2025-12-31 23:00')) last_t FROM valid GROUP BY station),
      grid AS (SELECT station,unnest(generate_series(first_t,last_t,interval '1 hour')) AS t FROM bounds),
      panel AS (SELECT station,t,dep,arr, count(dep) OVER (PARTITION BY station ORDER BY t
        ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING)>0 AS recent_activity
        FROM grid LEFT JOIN valid USING(station,t))
      SELECT station AS station_id,t AS hour_utc,timezone('America/New_York',t) AS hour_local,
        coalesce(dep,0) AS departures,coalesce(arr,0) AS arrivals,
        dep IS NULL AS inferred_zero,recent_activity AS eligible_at_hour_start
      FROM panel WHERE (recent_activity OR dep IS NOT NULL)
        AND NOT ({clock_issue("timezone('America/New_York',t)")})
      ORDER BY t,station) TO {quote(hourly)} (FORMAT parquet, COMPRESSION zstd)""")
    db.execute(f"CREATE VIEW panel AS SELECT * FROM {quote(hourly)}")
    audit["panel"] = summary("""SELECT count(*) AS rows,count(distinct station_id) stations,
       countif(inferred_zero) inferred_zeros,countif(eligible_at_hour_start) eligible_hours,
       sum(departures) departures,sum(arrivals) arrivals FROM panel""")
    original = json.loads((PREP/"audit.json").read_text())["summary"]
    assert audit["trips"]["rows"] == audit["source"]["rows"] == original["rows"]
    for key in ("departures","arrivals"):
        assert audit["panel"][key]+audit["excluded_clock_hours"][key] == original["station_hour"][key]
    assert db.execute("""SELECT count(*) FROM (SELECT station_id,hour_utc FROM panel GROUP BY ALL
       HAVING count(*)>1)""").fetchone()[0] == 0
    assert db.execute("""SELECT count(*) FROM panel WHERE inferred_zero AND
      (departures<>0 OR arrivals<>0 OR NOT eligible_at_hour_start)""").fetchone()[0] == 0
    (stage/"audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    for p in (trips,hourly,stage/"audit.json"):
        p.replace(OUT/p.name)
    print(json.dumps(audit,indent=2))
