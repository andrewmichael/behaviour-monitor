"""THROWAWAY spike (9 Nov 2026), kept as the reference for the where-is-she design.

Not production code. Reads the Biddulph Road fixture and truth file from exports/
(local only). Run: python docs/superpowers/specs/2026-11-09-where-is-she-spike.py 60 --tv-cap=90 --morning-cap=90
"""
import json, sys, statistics, collections
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import yaml
TZ = ZoneInfo("Europe/London")
FIX = "/Users/abourne/Documents/source/behaviour-monitor/exports/fixture/biddulph_road.jsonl"
TRUTH = "/Users/abourne/Documents/source/behaviour-monitor/exports/fixture/biddulph_road.truth.yaml"
CAP = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
FLOOR = 45.0
USE_TV = "--no-tv" not in sys.argv
PLUGS = {"sensor.kettle_power": 100, "sensor.teas_maid_power": 50, "sensor.smart_plug_power": 20, "sensor.front_bedroom_tv_power": 10}
MORNING_CAP = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--morning-cap=')), 90))
TV_CAP = float(next((a.split('=')[1] for a in sys.argv if a.startswith('--tv-cap=')), 90))
TVS = {"sensor.smart_plug_power": "Back room", "sensor.front_bedroom_tv_power": "Front bedroom"}
DOORS = {"binary_sensor.front_door_door", "binary_sensor.back_door_door", "binary_sensor.side_door_door"}
ROOM = {"binary_sensor.front_room_motion": "Front room", "binary_sensor.back_room_motion": "Back room", "binary_sensor.kitchen_motion_2": "Kitchen",
        "binary_sensor.front_bedroom_motion": "Front bedroom", "binary_sensor.back_bedroom_motion": "Back bedroom", "binary_sensor.bathroom_motion": "Bathroom",
        "binary_sensor.motion_sensor_motion": "Hall", "binary_sensor.motion_sensor_2_motion": "Landing",
        "sensor.kettle_power": "Kitchen", "sensor.teas_maid_power": "Box room", "sensor.smart_plug_power": "Back room", "sensor.front_bedroom_tv_power": "Front bedroom"}
BEDROOMS = {"Front bedroom", "Back bedroom"}

def pt(v):
    t = v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
    return t if t.tzinfo else t.replace(tzinfo=TZ)
truth = []
for r in yaml.safe_load(open(TRUTH)):
    s = pt(r.get("at", r.get("from"))); e = pt(r["to"]) if r.get("to") else (s if "at" in r else datetime(2026, 11, 9, tzinfo=TZ))
    truth.append((s, e, r["what"]))
gaps = [(s, e) for s, e, w in truth if w == "gap"]
def in_gap(t): return any(s <= t <= e for s, e in gaps)

# activity stream: (t, kind, room) kind in motion|door|plug_on|tv_on|tv_off
raw = [json.loads(l) for l in open(FIX)]
acts = []; plug_on = {}
for r in raw:
    t = datetime.fromisoformat(r["t"]).astimezone(TZ); e, s = r["e"], r["s"]
    if e in DOORS and s == "on": acts.append((t, "door", None))
    elif e in ROOM and e.startswith("binary_sensor") and s == "on": acts.append((t, "motion", ROOM[e]))
    elif e in PLUGS:
        try: w = float(s)
        except ValueError: continue
        on = w > PLUGS[e]
        if on and not plug_on.get(e): acts.append((t, "tv_on" if e in TVS else "plug_on", ROOM[e]))
        if not on and plug_on.get(e) and e in TVS: acts.append((t, "tv_off", ROOM[e]))
        plug_on[e] = on
acts.sort(key=lambda a: a[0])
END = acts[-1][0]

def segments(acts):
    """Yield (start, end, state, room, tv) for each quiet interval between activities."""
    tv = set(); last_room = None
    for i, (t, k, room) in enumerate(acts):
        if k == "tv_on": tv.add(room)
        if k == "tv_off": tv.discard(room)
        if room and k in ("motion", "plug_on", "tv_on"): last_room = room
        nxt = acts[i + 1][0] if i + 1 < len(acts) else END
        if k == "tv_off": continue
        if k == "door":
            # out if no indoor motion within 10 min after the door
            following = [a for a in acts[i + 1:i + 40] if a[0] <= t + timedelta(minutes=10)]
            state = "home" if any(a[1] == "motion" for a in following) else "out"
        else:
            state = "home"
        yield t, nxt, state, last_room, bool(tv & {last_room})

SEGS = [s for s in segments(acts) if not any(a <= s[1] and b >= s[0] for a, b in gaps)]

def day_hours():
    return range(7, 22)

def thresholds(before):
    """Learn from segments that ended before `before`."""
    hist = [s for s in SEGS if s[1] < before]
    gaps_by_hour = collections.defaultdict(list); tv_by_hour = collections.defaultdict(list)
    outs = []; wakes = []
    for st, en, state, room, tv in hist:
        mins = (en - st).total_seconds() / 60
        if state == "out": outs.append(mins); continue
        (tv_by_hour if (tv and USE_TV) else gaps_by_hour)[st.hour].append(mins)
    by_day = collections.defaultdict(list)
    for t, k, room in acts:
        if t < before and k == "motion" and t.hour >= 4 and room not in BEDROOMS: by_day[t.date()].append(t)
    for d, ts in by_day.items(): wakes.append(min(ts).hour * 60 + min(ts).minute)
    def q(xs, p): xs = sorted(xs); return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None
    th = {h: max(FLOOR, min(CAP, q(gaps_by_hour[h], 0.995) or CAP)) for h in range(24)}
    th_tv = {h: max(FLOOR, TV_CAP) for h in range(24)}
    return th, th_tv, (max(outs) * 1.25 if outs else 240), (q(wakes, 0.95) if wakes else 9 * 60)

def alert_time(st, en, state, room, tv, th):
    """When (if ever) a quiet interval [st, en) would alert."""
    th_home, th_tv, out_max, wake95 = th
    if state == "out":
        t = st + timedelta(minutes=out_max)
        return t if t < en else None
    # Night: last seen in a bedroom from 20:00 until 05:00 -> wait for usual waking.
    night = room in BEDROOMS and (st.hour >= 20 or st.hour < 5)
    if room in BEDROOMS and 5 <= st.hour < 11 and not night:
        t = st + timedelta(minutes=MORNING_CAP)  # stirred, lying in
        return t if t < en else None
    if night:
        d = st.date() + (timedelta(days=1) if st.hour >= 20 else timedelta())
        t = datetime.combine(d, time(0), TZ) + timedelta(minutes=wake95 + 60)
        return t if t < en else None
    lim = (th_tv if (tv and USE_TV) else th_home)[st.hour]
    t = st + timedelta(minutes=lim)
    if 0 <= t.hour < 6 and room not in BEDROOMS:  # dozing downstairs late: same rule
        pass
    return t if t < en else None

FIRST = acts[0][0]
LEARN = FIRST + timedelta(days=14)
def explained(t):
    return next((w for s, e, w in truth if s <= t <= e and w in ("out", "visitor", "maintenance", "away")), None)

# false alarms on real data (after learning)
alerts = []
cache = {}
for seg in SEGS:
    st = seg[0]
    if st < LEARN: continue
    d = st.date()
    if d not in cache: cache[d] = thresholds(datetime.combine(d, time(0), TZ))
    a = alert_time(*seg, cache[d])
    if a: alerts.append((a, seg))
print(f"CAP={CAP:.0f} min, TV-aware={USE_TV}")
print(f"REAL-DATA ALERTS after learning: {len(alerts)}")
for a, (st, en, state, room, tv) in alerts:
    why = explained(a) or "UNEXPLAINED"
    print(f"  {a:%a %d %b %H:%M}  {state:4} last {room} tv={tv}  quiet {(en-st).total_seconds()/3600:.1f}h  -> {why}")

# injected falls: every hour 08-20 on eligible days
days = sorted({t.date() for t, _, _ in acts if t >= LEARN})[:-1]
lat = collections.defaultdict(list); missed = []
for d in days:
    for h in range(8, 21):
        T = datetime.combine(d, time(h), TZ)
        if any(s <= T + timedelta(hours=6) and e >= T - timedelta(hours=1) for s, e, w in truth): continue
        before = [a for a in acts if a[0] <= T]
        if not before: continue
        sub = before + [(T + timedelta(hours=12), "end", None)]
        th = cache.get(d) or thresholds(datetime.combine(d, time(0), TZ))
        segs = list(segments(sub))
        st, en, state, room, tv = segs[-2] if len(segs) > 1 else segs[-1]
        a = alert_time(st, en, state, room, tv, th)
        if a is None or a < T: missed.append((T, state, room)); continue
        lat[h].append((a - T).total_seconds() / 60)
allv = [v for vs in lat.values() for v in vs]
print(f"\nINJECTED FALLS: {len(allv)} caught, {len(missed)} missed; median {statistics.median(allv):.0f} min, p90 {sorted(allv)[int(.9*len(allv))]:.0f}, worst {max(allv):.0f}")
print("  by hour (median/worst min): " + "  ".join(f"{h}:00 {statistics.median(v):.0f}/{max(v):.0f}" for h, v in sorted(lat.items())))
for T, state, room in missed[:8]: print(f"  missed {T:%a %d %b %H:%M} state={state} last={room}")
