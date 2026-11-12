"""Prepare the 2025 NYC Citi Bike archives. Requires Python and DuckDB."""
import csv
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import duckdb

root = Path(__file__).resolve().parents[1]
raw = root / "data/raw"
out = root / "data/prepared"
trips = out / "trips"
trips.mkdir(parents=True, exist_ok=True)
sizes = [414213312,396008433,618260276,727249076,844446636,929043436,
         973875638,1000258641,1032411368,924115389,667113932,407790791]
fields = "ride_id rideable_type started_at ended_at start_station_name start_station_id end_station_name end_station_id start_lat start_lng end_lat end_lng member_casual".split()
types = {f: "timestamp" if f.endswith("_at") else "double" if f.endswith(("_lat","_lng")) else "varchar" for f in fields}

def path_sql(p):
    return "'" + str(p).replace("'", "''") + "'"

db = duckdb.connect()
db.execute("set memory_limit='3GB'")
db.execute("set threads=4")
with tempfile.TemporaryDirectory(dir=out) as tmp:
    tmp = Path(tmp)
    db.execute("set temp_directory=" + path_sql(tmp / "spill"))
    manifest = []
    for month, size in enumerate(sizes, 1):
        ym = f"2025{month:02}"
        archive = raw / f"{ym}-citibike-tripdata.zip"
        assert archive.stat().st_size == size, archive
        with zipfile.ZipFile(archive) as z:
            members = sorted(n for n in z.namelist() if n.endswith(".csv") and not any(p.startswith((".", "__MACOSX")) for p in Path(n).parts))
            assert members, archive
            for i, name in enumerate(members, 1):
                part = trips / f"{ym}-{i:02}.parquet"
                source = tmp / "part.csv"
                with z.open(name) as fin, source.open("wb") as fout:
                    shutil.copyfileobj(fin, fout, length=1024*1024)
                with source.open(encoding="utf-8-sig") as f:
                    assert next(csv.reader(f)) == fields, name
                db.execute(f"copy (select * from read_csv({path_sql(source)},header=true,columns={types})) to {path_sql(part)} (format parquet, compression zstd)")
                rows = db.execute(f"select count(*) from {path_sql(part)}").fetchone()[0]
                manifest.append(dict(month=ym, source=name, rows=rows, csv_bytes=source.stat().st_size))
        print(ym, "verified and prepared", flush=True)
    db.execute(f"create view rides as select * from read_parquet({path_sql(trips / '*.parquet')})")
    def records(sql):
        r = db.execute(sql)
        names = [c[0] for c in r.description]
        return [dict(zip(names,row)) for row in r.fetchall()]
    audit = records("""select count(*) as rows, count(distinct ride_id) as distinct_ids,
      count(*) filter(where ended_at <= started_at) as nonpositive_duration,
      count(*) filter(where ended_at-started_at > interval '24 hours') as over_24h,
      count(*) filter(where ended_at >= timestamp '2026-01-01') as arrivals_after_year
      from rides""")[0]
    audit["missing"] = records("select "+",".join(f"count(*)-count({f}) as {f}" for f in fields)+" from rides")[0]
    audit["bike_and_rider"] = records("select rideable_type,member_casual,count(*) as rides from rides group by all order by all")
    # Exclude every occurrence of ambiguous IDs from the hourly table; retain source rows for review.
    db.execute("create temp table repeated as select ride_id from rides where ride_id is not null group by ride_id having count(*)>1")
    db.execute("create view usable as select * from rides anti join repeated using(ride_id) where rides.ride_id is not null")
    def flows(side):
        t = "started_at" if side=="start" else "ended_at"
        return f"""select {side}_station_id station_id,date_trunc('hour',{t}) hour_local,count(*) n
        from usable where {side}_station_id is not null and {t} >= '2025-01-01' and {t} < '2026-01-01'
        group by all"""
    hourly = out / "station_hour_observed.parquet"
    db.execute(f"""copy (select station_id,hour_local,coalesce(s.n,0)::integer departures,
      coalesce(e.n,0)::integer arrivals from ({flows('start')}) s full join ({flows('end')}) e
      using(station_id,hour_local) order by hour_local,station_id) to {path_sql(hourly)} (format parquet, compression zstd)""")
    audit["station_hour"] = records(f"select count(*) observed_hours,count(distinct station_id) stations,sum(departures) departures,sum(arrivals) arrivals from {path_sql(hourly)}")[0]
    assert audit["rows"] == sum(p["rows"] for p in manifest)
    for side, t, key in [("start","started_at","departures"),("end","ended_at","arrivals")]:
        total = db.execute(f"select count(*) from usable where {side}_station_id is not null and {t}>='2025-01-01' and {t}<'2026-01-01'").fetchone()[0]
        assert total == audit["station_hour"][key]
    (out/"audit.json").write_text(json.dumps(dict(summary=audit,files=manifest),indent=2))
    print(json.dumps(audit), flush=True)
