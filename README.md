# Pico-BPC — a Pico-WWVB port for China's BPC 68.5 kHz time signal

Fork of <https://github.com/geerlingguy/Pico-WWVB> (MIT) that transmits
**BPC** (Shangqiu, 68.5 kHz) instead of WWVB, for radio-controlled watches
used in UTC+8 (Malaysia, Singapore, China). Tested against a Citizen
caliber H145 (CB0261-53E), which lists Beijing/BJS under the "China"
signal station.

Why BPC: it broadcasts local time for UTC+8, has no DST, and its code is
just per-second amplitude dips — so the whole WWVB keyer (PIO antiphase
carrier on GP0/GP1, NTP-anchored `ticks_us`) carries over unchanged.

## Wiring (identical to Pico-WWVB)

    GP0 (pin 1) -> 220 ohm -> antenna -> GP1 (pin 2)

Use the **DIY loop** option (20-30 turns, 2-3 cm form): it is
non-resonant and happy at 68.5 kHz. A loop stick tuned for 60 kHz works
but is off its resonance peak.

## Watch setup (Citizen H145)

1. Pull the crown to position 1, turn to **21 = BJS (Beijing, UTC+8)**;
   push crown in. This selects the China station.
2. Summer time: keep **SMT OFF** (China has none; the watch keeps
   standard time with BJS even if SMT is left ON, since BPC carries no
   DST signal).
3. Put the loop against the watch (on top of the case, or beside the
   9-3 o'clock line), press and hold button A 2 s -> "RX". Takes 2-15
   min; the second hand then points OK / NO.

## Deploy

    cp example.config.py config.py   # fill in WIFI_SSID / WIFI_PASSWORD
    uvx mpremote cp main.py transmitter.py timecode.py ntp.py config.py :
    uvx mpremote reset
    uvx mpremote repl                # Ctrl-D to see the output

Console prints the code live as two-bit pairs, `M` at block starts:

    M 00011010...  M 01100100...  M 01011101...  16:47 CST, 2026-11-25 Wed

## What changed vs upstream

- `timecode.py` — rewritten: BPC layout per Wikipedia's "BPC time signal"
  (three 20-second blocks/min, 2 bits/s, 100-400 ms dips, no-dip marker,
  even parity P1 over seconds 1-9 and P2 over 11-18, 12-hour + PM flag,
  Gregorian fields, year % 100). Encodes CST = UTC + 8.
- `transmitter.py` — `CARRIER_HZ = 68_500`. The PIO's 12-bit fractional
  divider hits 68500.0 Hz from both the Pico 2's 150 MHz and the
  Pico W's 125 MHz system clock, so nothing else changes. Marker seconds
  (dip = 0 ms) pass through the keyer untouched.
- `main.py` — BPC symbol map and decoded-time line; "Transmitting BPC".
- `test_bpc.py` — replaces `test_wwvb.py`: Wikipedia's 2014 reference
  decode (07:34:00 CST, Sun 2014-12-28), ~154k frames over 2026-2027 and
  leap/new-year/2100 edge cases checked against `datetime`, plus a
  tamper test proving parity rejects corrupted frames.

## Legality (Malaysia)

This is a near-field inductive coupler, not a broadcast transmitter:
effective range is tens of centimeters (field falls off as 1/r^3) and it
radiates roughly 13 orders of magnitude less power than a proper 68.5 kHz
antenna would. The FCC-equivalent logic in the original README (FCC
Part 15: home-built, unlicensed band, far below emission limits) maps
well onto MCMC/SIRIM rules, but that is not legal advice — keep the loop
small and next to the watch only.

## License

MIT, same as Pico-WWVB (which is based on Longwave Pico by
carter-oswald-dev).
