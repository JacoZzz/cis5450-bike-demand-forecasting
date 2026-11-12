# NYC bike-share demand forecasting

This CIS 5450 project forecasts the number of departures and arrivals at each station in the next hour. A secondary analysis compares member and casual rides. The working dataset covers the January–December 2025 NYC Citi Bike monthly releases, extending the six-month window in the proposal.

The repository includes the scripts, audit reports, EDA figures and their summary tables. To review the findings immediately after cloning, open the [EDA notes](docs/eda.md). To work with individual rides or station-hours, generate the local Parquet files using the commands below.

## Which file should I use?

| File | Unit | Use |
| --- | --- | --- |
| `data/clean/station_hour_clean.parquet` | Station × hour | Departure and arrival counts, including inferred quiet hours. Filter on `eligible_at_hour_start` for forecasting. |
| `data/clean/trips_clean.parquet` | Ride | All 13 original fields, normalized station text and coordinate ranges, plus duration and clock flags. Use `duration_eligible` for analyses that depend on ride length. |
| `data/clean/audit.json` | Annual totals | Counts after cleaning, excluded clock hours and panel coverage. |
| `data/prepared/audit.json` | Source files and annual totals | Row counts, field missingness, bike types and rider categories before cleaning. |

Each hourly row describes the interval **beginning** at its timestamp. Use `hour_utc` to align lags by elapsed time and `hour_local` for New York calendar features. Build predictors from information available at the start of the target interval. Weather, holidays, forecast features and fitted models are outside this cleaning stage.

## Reproduce the data

Run from the project root with Python and enough space for the archives (8.93 GB), both Parquet stages and temporary processing. The following commands use a macOS/Linux shell. Skip the download if the twelve archives are already present.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install duckdb==2.0.0
mkdir -p data/raw
curl --fail --location --retry 3 --parallel --parallel-max 3 \
  -o 'data/raw/2025#1-citibike-tripdata.zip' \
  'https://s3.amazonaws.com/tripdata/2025[01-12]-citibike-tripdata.zip'
python scripts/prepare_2025.py
python scripts/clean_2025.py
```

If the prepared files already exist, run only the final Python command in the configured environment. The preparation script checks the published archive sizes for this snapshot and reads every CSV member. Review the source manifest if the publisher revises an archive.

## Inspect the forecast population

```python
import duckdb

print(duckdb.sql("""
    SELECT station_id, hour_local, departures, arrivals, inferred_zero
    FROM 'data/clean/station_hour_clean.parquet'
    WHERE eligible_at_hour_start
    ORDER BY hour_utc, station_id
    LIMIT 10
""").fetchall())
```

The [cleaning walkthrough](docs/data-cleaning.md) explains the population, assumptions and validation results. The [Citi Bike system data page](https://citibikenyc.com/system-data) provides source information and links to the data-use policy.

## Exploratory analysis

To regenerate the figures and CSV summaries after cleaning, run these commands in the same environment.

```sh
python -m pip install matplotlib numpy
python scripts/eda_2025.py
```

See the [January–July EDA and check-in notes](docs/eda.md) for the four figures, denominators and findings.
