# InfluxDB: Biddulph Road history moved to its own database (10 Nov 2026, from the home-assistant repo)

- Biddulph Road history now lives in the InfluxDB database **`biddulph_road`** (26 weeks), not `homeassistant`.
  `homeassistant` is now a 2-day landing area: Home Assistant writes there and Kapacitor copies every point unchanged
  (same measurement names, tags, fields and nanosecond timestamps) into `biddulph_road`.
- History since 8 Nov 23:36 was copied across (6,846 points, counts identical per measurement).
- `~/.influx_bm` on the Mac was changed to `database=biddulph_road` (backup `~/.influx_bm.bak-20261110`), so
  `scripts/export_influx.py` needs no code change. Checked: the read-only user reads all 41 measurements; writes are refused.
- Anything here that hard-codes `homeassistant` as the database (docs, examples, the test fixture in
  `tests/test_export_influx.py` is only a parsing test) should say `biddulph_road`. An export pointed at `homeassistant`
  would now see only the last 2 days.
- A sensor added to Behaviour Monitor must now also be added to the one Kapacitor routing list (`route_ha`) (home-assistant repo,
  `docs/influxdb-history.md`, "Layout since 10 Nov 2026").
