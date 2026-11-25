"""
main.py — sync time over NTP and transmit BPC (China, 68.5 kHz, UTC+8).
Settings are in config.py; progress prints to the USB serial console
(`mpremote repl`).
"""

import time
import machine
import network

import config
import ntp
import timecode
import transmitter

RESYNC_MS = 3_600_000  # hourly, to cancel crystal drift
RETRY_MS = 30_000

led = machine.Pin("LED", machine.Pin.OUT)
led_on = None
failed = False
shown = None  # (epoch, second) last printed to the console
SYMBOL = {0: "M", 100: "00", 200: "01", 300: "10", 400: "11"}
DOW = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def log(*args):
    if shown and shown[1] != 59:
        print()  # end the time code line first
    print(*args)


def show(epoch, sec, frame):
    # Two bits per transmitted second (M marks a block start); the minute's
    # decoded CST time after :59.
    global shown
    shown = (epoch, sec)
    if frame[sec] == 0:
        print(" M" if sec else "M", end="")
    else:
        print(SYMBOL[frame[sec]], end="")
    if sec == 59:
        mn, hr, day, mo, year, dow = timecode.decode(frame)
        print("  %02d:%02d CST, %04d-%02d-%02d %s" % (hr, mn, 2000 + year, mo, day, DOW[dow - 1]))


def blink(_):
    # Solid: syncing. Lit while the carrier is reduced: transmitting. Fast blink: sync failed.
    global led_on
    pos = transmitter.position()
    if pos:
        epoch, start, frame = pos
        ms = time.ticks_diff(time.ticks_us(), start) // 1000
        on = ms < 0 or (ms < 60_000 and ms % 1000 < frame[ms // 1000])
        if 0 <= ms < 60_000 and shown != (epoch, ms // 1000):
            show(epoch, ms // 1000, frame)
    else:
        on = not failed or time.ticks_ms() // 100 % 2 == 0
    if on != led_on:  # the LED is on the Wi-Fi chip, so skip redundant writes
        led.value(on)
        led_on = on


def fmt(epoch_s):
    return "%04d-%02d-%02d %02d:%02d:%02d UTC" % time.gmtime(epoch_s)[:6]


def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return
    wlan.active(True)
    wlan.config(pm=network.WLAN.PM_NONE)  # power saving adds NTP jitter
    log("Connecting to", config.WIFI_SSID)
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    for _ in range(30):
        if wlan.isconnected():
            log("Wi-Fi connected:", wlan.ifconfig()[0])
            return
        time.sleep(1)
    raise OSError("Wi-Fi connect timed out")


def sync():
    """Fresh NTP anchor, or None on failure."""
    global failed
    try:
        wifi_connect()
        anchor = ntp.query(config.NTP_SERVER)
    except Exception as e:
        log("NTP sync failed:", e)
        failed = True
        return None
    failed = False
    log("NTP sync:", fmt(ntp.now_us(anchor) // 1_000_000), "(rtt %.1f ms)" % (anchor[2] / 1000))
    return anchor


def start(anchor):
    # Next minute at least 0.2 s away, leaving time to set up the PIO.
    epoch = ((ntp.now_us(anchor) + 200_000) // 60_000_000 + 1) * 60
    transmitter.start(epoch, ntp.ticks_at(anchor, epoch * 1_000_000))
    log("Transmitting BPC from", fmt(epoch))


def correct_drift(anchor, position):
    # How far the current minute's actual start is from where NTP says it should be.
    epoch, ticks, _ = position
    delta = time.ticks_diff(ntp.ticks_at(anchor, epoch * 1_000_000), ticks)
    transmitter.adjust(delta)
    log("Drift correction: %+.1f ms" % (delta / 1000))


def main():
    global failed
    timer = machine.Timer(period=20, callback=blink)
    if not config.WIFI_SSID:
        failed = True
        raise SystemExit("Set WIFI_SSID and WIFI_PASSWORD in config.py")
    while True:
        anchor = sync()
        position = transmitter.position()
        if anchor and position:
            correct_drift(anchor, position)
        elif anchor and not transmitter.running():
            start(anchor)
        time.sleep_ms(RESYNC_MS if transmitter.running() else RETRY_MS)


if __name__ == "__main__":
    main()
