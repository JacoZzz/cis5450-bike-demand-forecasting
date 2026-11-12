# Data cleaning walkthrough

## 1. Establish the unit and time window

A ride contributes a departure at its start station and an arrival at its end station. Aggregating both events by the ride's start hour would misplace arrivals in time and space. Use the event's own local timestamp to define the 2025 window. The monthly releases contain 207 rides that began in 2024. Their in-year arrivals still count. The trip table keeps source membership in the release, so analyses of rides *starting* in 2025 should apply their own date filter.

## 2. Validate the release and normalize fields

The preparation stage checks archive sizes, CSV headers, data types, row counts and ride IDs. The cleaning stage requires a unique, non-null ID on every ride. Station IDs are text to preserve suffixes and leading zeros. Trim station IDs and names and turn blank strings into nulls. Keep separate IDs when names match. Coordinates outside the physical latitude or longitude range become null. A physically valid coordinate alone does not establish that a station is in NYC. The population follows the NYC release, including any cross-system or operational station IDs in those files. A borough-specific study requires a separate geographic filter.

## 3. Retain valid endpoints independently

A missing end station leaves the departure usable, and vice versa. Before excluding clock anomalies, the endpoint aggregation yields 45,750,624 departures and 45,640,770 arrivals. Keep trips with missing locations for analyses that only need rider and bike type. For straight-line distance, require both complete coordinate pairs.

## 4. Resolve elapsed time and flag questionable durations

The source timestamps are local wall times without UTC offsets. Use America/New_York rules for rides spanning a clock change. Mark an endpoint in the nonexistent spring hour or repeated fall hour as clock-uncertain. Elapsed time is unknown for these trips. The 482 nonpositive raw wall-clock durations all begin on the fall transition date.

The trip output adds `clock_uncertain`, `duration_seconds` and `duration_eligible`. The eligibility flag requires a known duration greater than zero and at most 24 hours. The upper bound is an analytical choice for typical ride duration. Retain the original timestamps and the ride for endpoint counts. Report how duration-based conclusions change if longer rides are included.

## 5. Define which station-hours can enter a forecast

Generate an hourly grid in UTC. At each hour start, look back 24 elapsed hours for at least one recorded departure or arrival at that station. A recent event makes the hour eligible. If an eligible hour has no recorded events, assign zero to both counts and set `inferred_zero`. An observed hour after a long gap stays in the table for reconciliation, with `eligible_at_hour_start = false`. Its activity can establish eligibility for later forecasts. Long silent stretches outside the lookback are omitted.

The 24-hour rule approximates station activity using information available at prediction time. It can include temporary outages and miss operating low-volume stations. Interpret forecast scores as applying to recently observed stations. Compare coverage and baseline error with a longer window, such as 48 hours, during validation. Inventory and historical station status would improve the eligibility definition.

Exclude both occurrences of the repeated fall hour from forecast targets because their event counts cannot be separated. The UTC grid skips the nonexistent spring hour. Use exact UTC timestamp joins for lag features because excluded hours and long gaps interrupt the series. For a same-weekday, same-local-hour feature, align by local calendar time and explicitly handle missing clock hours.

## 6. Verify the published files

The script checks trip-row preservation, uniqueness of each station and UTC hour, consistency of inferred zeros and reconciliation of departures and arrivals to the prepared endpoint totals after accounting for excluded clock hours. The machine-readable counts are in [the cleaning audit](../data/clean/audit.json).

| Check | 2025 result |
| --- | ---: |
| Unique rides retained | 45,771,102 |
| Rides with an uncertain local clock time | 4,829 |
| Known elapsed durations above 24 hours | 9,091 |
| Rides eligible for duration analysis | 45,757,182 |
| Observed station-hours excluded for clock issues | 1,460 |
| Departures / arrivals in those excluded hours | 4,123 / 4,537 |
| Clean station-hours across 2,428 stations | 18,996,578 |
| Eligible forecast hours | 18,981,354 |
| Inferred zero-flow hours within the eligible population | 7,022,125 |
| Observed hours retained only for reconciliation and future history | 15,224 |
| Departures / arrivals retained in the hourly table | 45,746,501 / 45,636,233 |

The initial audit identified 9,066 apparent durations over 24 hours by subtracting local timestamps. The cleaned-duration count uses elapsed time across clock transitions and excludes ambiguous endpoints, which explains the difference in definitions.
