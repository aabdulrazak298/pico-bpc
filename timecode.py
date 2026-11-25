"""
timecode.py — BPC (China, 68.5 kHz) amplitude time code.

Integer math only, so it runs on MicroPython and desktop Python alike.
Port of the WWVB module in geerlingguy/Pico-WWVB: same frame() contract
(one reduced-carrier duration in ms per second of a minute), different
carrier and code layout.

Layout (per Wikipedia "BPC time signal", verified against the 2014
reference decode of 07:34:00 CST on 2014-12-28, a Sunday):

  The minute is three identical 20-second blocks starting at :00, :20,
  :40. Each block encodes China Standard Time (UTC+8) of the block's
  first second. Second 0 of a block carries NO dip (it marks the block);
  the other 19 seconds carry two bits each (MSb, LSb) encoded as:
  100 ms = 00, 200 ms = 01, 300 ms = 10, 400 ms = 11.

  Block-second: field
    0  marker            (full power, all second)
    1  seconds 00/20/40  (bits 40, 20 -> block index 0, 1, 2)
    2  unused (0, 0)
    3-4   hour, 12-hour 00-11 (8, 4, 2, 1)
    5-7   minute 00-59        (32, 16, 8, 4, 2, 1)
    8     unused 0, day of week 4
    9     day of week 2, 1    (1=Monday .. 7=Sunday)
    10    PM flag (0=AM), P1 = even parity over seconds 1-9
    11    unused 0, day of month 16
    12-13 day of month 8, 4, 2, 1  (01-31)
    14-15 month 8, 4, 2, 1         (01-12)
    16-18 year 32, 16, 8, 4, 2, 1  (year % 100)
    19    year 64, P2 = even parity over seconds 11-18

Bits sent in the same second as a parity bit are not parity-checked.
"""

CST = 8 * 3600  # China Standard Time offset, no DST

MARKERS = (0, 20, 40)  # seconds with a no-dip block marker


def days_from_civil(y, m, d):
    """Days since 1970-01-01 (Howard Hinnant's algorithm)."""
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * ((m + 9) % 12) + 2) // 5 + d - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def civil_from_days(z):
    """Inverse of days_from_civil: (y, m, d) from days since 1970-01-01."""
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    y = yoe + era * 400 + (1 if m <= 2 else 0)  # doy runs from March 1
    return y, m, d


def _bit(value, weight):
    return 1 if value & weight else 0


def frame(epoch_s):
    """Reduced-carrier time in ms for each second of the minute starting
    at epoch_s (UTC): 0 = marker, 100 = 00, 200 = 01, 300 = 10, 400 = 11.
    The encoded wall-clock time is China Standard Time (UTC + 8)."""
    t = epoch_s + CST
    day, secs = divmod(t, 86400)
    y, mo, d = civil_from_days(day)
    hr, mn = secs // 3600, secs // 60 % 60
    dow = (day + 3) % 7 + 1  # 1970-01-01 (day 0) was a Thursday
    h12 = hr % 12
    pm = 1 if hr >= 12 else 0

    out = [100] * 60
    for blk in range(3):
        pairs = [
            None,                          # marker, no dip
            (_bit(blk, 2), _bit(blk, 1)),  # seconds field: 00 / 20 / 40
            (0, 0),                        # unused
            (_bit(h12, 8), _bit(h12, 4)),
            (_bit(h12, 2), _bit(h12, 1)),
            (_bit(mn, 32), _bit(mn, 16)),
            (_bit(mn, 8), _bit(mn, 4)),
            (_bit(mn, 2), _bit(mn, 1)),
            (0, _bit(dow, 4)),             # unused, day of week 4
            (_bit(dow, 2), _bit(dow, 1)),
            (pm, 0),                       # PM flag; P1 recomputed below
            (0, _bit(d, 16)),              # unused, day of month 16
            (_bit(d, 8), _bit(d, 4)),
            (_bit(d, 2), _bit(d, 1)),
            (_bit(mo, 8), _bit(mo, 4)),
            (_bit(mo, 2), _bit(mo, 1)),
            (_bit(y % 100, 32), _bit(y % 100, 16)),
            (_bit(y % 100, 8), _bit(y % 100, 4)),
            (_bit(y % 100, 2), _bit(y % 100, 1)),
            (_bit(y % 100, 64), 0),        # year 64; P2 recomputed below
        ]
        ones = sum(p[0] + p[1] for p in pairs[1:10])
        pairs[10] = (pm, ones % 2)  # even parity over seconds 1-9
        ones = sum(p[0] + p[1] for p in pairs[11:19])
        pairs[19] = (pairs[19][0], ones % 2)  # even parity over seconds 11-18
        for p in range(20):
            s = blk * 20 + p
            if p == 0:
                out[s] = 0
            else:
                msb, lsb = pairs[p]
                out[s] = 100 * (2 * msb + lsb + 1)
    return out


def decode(frame):
    """Read a frame back: (minute, hour, day, month, year % 100, day of week).
    Hour is 24-hour CST. All three blocks must agree; parity and the
    seconds field are checked, raising ValueError on any failure."""
    blocks = []
    for blk in range(3):
        pairs = []
        for p in range(20):
            ms = frame[blk * 20 + p]
            if p == 0:
                if ms != 0:
                    raise ValueError("missing block marker at :%02d" % (blk * 20))
                pairs.append(None)
            elif ms not in (100, 200, 300, 400):
                raise ValueError("bad dip %d ms at :%02d" % (ms, blk * 20 + p))
            else:
                pairs.append(((ms - 100) // 200, (ms - 100) % 200 // 100))

        def b(sec, which):  # which: 0 = MSb, 1 = LSb
            return pairs[sec][which]

        minute = (b(5, 0) * 32 + b(5, 1) * 16 + b(6, 0) * 8 + b(6, 1) * 4 +
                  b(7, 0) * 2 + b(7, 1))
        h12 = b(3, 0) * 8 + b(3, 1) * 4 + b(4, 0) * 2 + b(4, 1)
        hour = h12 + (12 if b(10, 0) else 0)
        day = (b(11, 1) * 16 + b(12, 0) * 8 + b(12, 1) * 4 +
               b(13, 0) * 2 + b(13, 1))
        month = b(14, 0) * 8 + b(14, 1) * 4 + b(15, 0) * 2 + b(15, 1)
        year = (b(19, 0) * 64 + b(16, 0) * 32 + b(16, 1) * 16 +
                b(17, 0) * 8 + b(17, 1) * 4 + b(18, 0) * 2 + b(18, 1))
        dow = b(8, 1) * 4 + b(9, 0) * 2 + b(9, 1)

        p1 = sum(b(s, w) for s in range(1, 10) for w in (0, 1))
        p2 = sum(b(s, w) for s in range(11, 19) for w in (0, 1))
        if p1 % 2 != b(10, 1) or p2 % 2 != b(19, 1):
            raise ValueError("parity failure in block starting :%02d" % (blk * 20))
        if pairs[1][0] * 2 + pairs[1][1] != blk:
            raise ValueError("seconds field mismatch in block starting :%02d"
                             % (blk * 20))
        blocks.append((minute, hour, day, month, year, dow))
    if blocks[0] != blocks[1] or blocks[0] != blocks[2]:
        raise ValueError("blocks disagree: %r" % (blocks,))
    return blocks[0]
