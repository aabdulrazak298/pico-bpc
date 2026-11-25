#!/usr/bin/env python3
"""Desktop test: check timecode.frame() (BPC) against datetime.

1. Wikipedia's 2014 reference decode: 07:34:00 CST on Sun 2014-12-28,
   block pairs s1..s10 = 00 00 01 11 10 00 10 01 11 00.
2. Field sweep: every 7th minute of 2026-2027 (plus dense edge cases)
   re-decoded back and compared against datetime UTC+8.
"""

import datetime as dt
import timecode

CST = dt.timezone(dt.timedelta(hours=8), "CST")


def pairs(frame):
    return [{0: "M", 100: "00", 200: "01", 300: "10", 400: "11"}[ms] for ms in frame]


def structure(frame):
    for s, ms in enumerate(frame):
        assert ms in (0, 100, 200, 300, 400), ("dip", s, ms)
        assert (ms == 0) == (s in timecode.MARKERS), ("marker", s, ms)


def check(t):
    epoch = int(t.timestamp())
    frame = timecode.frame(epoch)
    structure(frame)
    local = t.astimezone(CST)
    got = timecode.decode(frame)
    want = (local.minute, local.hour, local.day, local.month, local.year % 100,
            local.weekday() + 1)  # BPC carries year % 100; the watch's perpetual
                                   # calendar supplies the century (valid to 2100)
    assert got == want, (t, got, want)
    return frame


# --- 1. the 2014 reference sample -------------------------------------------
t = dt.datetime(2014, 12, 27, 23, 34, 0, tzinfo=dt.timezone.utc)
fr = check(t)
want = ["00", "00", "01", "11", "10", "00", "10", "01", "11", "00"]
got = pairs(fr)[1:11]
assert got == want, (got, want)
print("2014 sample OK:", " ".join(got))

# --- 2. sweep ---------------------------------------------------------------
STEP = dt.timedelta(minutes=7)
starts = [dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)]
n = 0
t = starts[0]
while t.year < 2028:
    check(t)
    n += 1
    t += STEP
print("OK: %d frames match" % n)

# --- 3. dense edge cases ----------------------------------------------------
edges = []
# every minute across CST midnight and the UTC-day/CST-day relationship
for day in (dt.datetime(2026, 2, 28, tzinfo=dt.timezone.utc),
            dt.datetime(2028, 2, 28, tzinfo=dt.timezone.utc),
            dt.datetime(2100, 2, 28, tzinfo=dt.timezone.utc)):
    for m in range(150):
        edges.append(day + dt.timedelta(hours=15, minutes=m))  # CST 23:00-01:29
# every minute across the 15:59->16:00 UTC boundary (CST midnight) already
# covered; every hour on 2027-12-31 and 2028-01-01, all days of Nov/Dec 2026
for h in range(48):
    edges.append(dt.datetime(2027, 12, 31, tzinfo=dt.timezone.utc) + dt.timedelta(hours=h))
t = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
while t < dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc):
    edges.append(t)
    t += dt.timedelta(minutes=31)
# second-field sanity: blocks at :20/:40 are exercised every check() already
for t in edges:
    fr = check(t)
    assert pairs(fr)[21] in ("00", "01", "10") and pairs(fr)[41] in ("00", "01", "10")
print("OK: %d edge-case frames match" % len(edges))

# --- 4. parity tamper detection ---------------------------------------------
try:
    bad = list(timecode.frame(1_800_000_000))
    bad[3] = 100 if bad[3] != 100 else 200  # flip a bit inside block 1
    timecode.decode(bad)
    raise SystemExit("FAIL: tampered frame passed decode")
except ValueError:
    print("OK: tampered frame rejected")

print("ALL PASS")
