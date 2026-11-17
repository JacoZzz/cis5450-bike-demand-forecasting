# NYC bike-share demand forecasting

This CIS 5450 project forecasts the number of departures and arrivals at each station in the next hour. A secondary analysis compares member and casual rides. The working dataset covers the January–December 2025 NYC Citi Bike monthly releases, extending the six-month window in the proposal.

The repository includes the scripts, audit reports, EDA figures and their summary tables. To review the findings immediately after cloning, open the [EDA notes](docs/eda.md). To work with individual rides or station-hours, generate the local Parquet files using the commands below.

## Project structure

```text
.
├── README.md
├── .gitignore
├── scripts/                         # Reproducible data and EDA workflows
│   ├── prepare_2025.py
│   ├── clean_2025.py
│   ├── eda_2025.py
│   └── export_daily_counts.py
├── notebooks/                       # Modeling and statistical analyses
│   ├── station_hour_demand_modeling.ipynb
│   ├── rider_type_classification.ipynb
│   └── hypothesis_testing.ipynb
├── data/
│   ├── raw/                         # Downloaded ZIP archives (local)
│   ├── prepared/                    # Typed source data and audit
│   └── clean/                       # Cleaned data, daily exports and audit
├── results/
│   ├── eda/                         # EDA figures and summary CSVs
│   ├── demand/                      # Forecast metrics, plots and local checkpoints
│   ├── rider_type/                  # Classification summaries and plots
│   └── hypothesis/                  # Hypothesis-test figures
└── docs/
    ├── proposal/                    # Original project proposal
    ├── data-cleaning.md
    ├── eda.md
    ├── modeling.md
    ├── hypothesis-testing.md
    └── project-management.md
```

The two data audit JSON files are versioned. Raw archives, generated data, model checkpoints and row-level prediction exports are stored locally under the rules in `.gitignore`. Shared figures and small summary tables belong in `results/`.

## Analysis guide

| Task | Entry point | Explanation |
| --- | --- | --- |
| Cleaning | `scripts/prepare_2025.py`, then `scripts/clean_2025.py` | [Cleaning decisions](docs/data-cleaning.md) |
| EDA | `scripts/eda_2025.py` | [Four figures and findings](docs/eda.md) |
| Demand forecasting | [Demand notebook](notebooks/station_hour_demand_modeling.ipynb) | [Model results](docs/modeling.md) |
| Rider classification | [Rider notebook](notebooks/rider_type_classification.ipynb) | [Model results](docs/modeling.md) |
| Hypothesis tests | `scripts/export_daily_counts.py`, then [test notebook](notebooks/hypothesis_testing.ipynb) | [Methods and results](docs/hypothesis-testing.md) |
| Timeline and responsibilities | [Project management](docs/project-management.md) | [Original proposal](docs/proposal/CIS_5450_Final_Project_Proposal.pdf) |

EDA and hypothesis tests use January–July. The existing modeling notebooks use April–July training, August validation and September testing, followed by an April–August refit. These are the periods used for the saved results.

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

## Run the modeling and hypothesis notebooks

After data cleaning, install the analysis dependencies in the same environment and export the daily counts.

```sh
python -m pip install numpy pandas matplotlib scikit-learn joblib pyarrow jupyterlab
python scripts/export_daily_counts.py
jupyter lab
```

Open a notebook under `notebooks/` and run its cells in order. Paths resolve from the project root or a directory inside it. Forecasting and classification can be run independently. The hypothesis notebook requires the daily exports.

Small result tables and figures are versioned in `results/`. Model checkpoints and row-level prediction exports are generated locally. Saved notebook outputs document the previous runs. The directory reorganization updated paths without rerunning model fitting or statistical tests.
