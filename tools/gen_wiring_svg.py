#!/usr/bin/env python3
"""Generate docs/wiring.svg from the pin map (keep in sync with include/pins.h).

Run:  python3 tools/gen_wiring_svg.py
Layout: power distribution across the top, the HUZZAH32 in the middle,
peripherals left/right with every signal wire labelled GPIO + net name.
Power pins connect to coloured vertical rails at the left and right edges.
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "docs" / "wiring.svg"

COL = {
    "12V": "#d62728", "5V": "#ff7f0e", "3V3": "#1a9641", "GND": "#111111",
    "sig": "#1f5fbf", "ana": "#7b3fbf", "mot": "#8c564b", "box": "#444444",
}

# Each pin: (label, kind, data, note)
#   kind "sig": data = (gpio, net)     -> wire to the Feather
#   kind "pwr": data = rail name        -> wire to the side rail
#   kind "txt": data = free text        -> short stub with text (load cell, motor leads)
LEFT = [
    ("10k potentiometer (panel)", [
        ("WIPER", "sig", (32, "POT (ADC1_CH4)"), "analog 0-3.3 V", "ana"),
        ("END 1", "pwr", "3V3", None, None),
        ("END 2", "pwr", "GND", None, None)]),
    ("Select button (GPTS203211B)", [
        ("NO", "sig", (15, "BTN_SELECT"), "internal pull-up", None),
        ("COM", "pwr", "GND", None, None)]),
    ("Back button (GPTS203211B)", [
        ("NO", "sig", (19, "BTN_BACK"), "internal pull-up", None),
        ("COM", "pwr", "GND", None, None)]),
    ("Home switch (roller microswitch)", [
        ("NO", "sig", (39, "HOME_SW"), "10k pull-up to 3V3 + 100nF to GND", None),
        ("COM", "pwr", "GND", None, None)]),
    ("Beam-break receiver (Adafruit 2167)", [
        ("WHITE", "sig", (16, "BEAM"), "10k pull-up to 3V3; LOW = blocked", None),
        ("RED", "pwr", "3V3", None, None),
        ("BLACK", "pwr", "GND", None, None)]),
    ("Beam-break emitter (Adafruit 2167)", [
        ("RED", "pwr", "3V3", None, None),
        ("BLACK", "pwr", "GND", None, None)]),
    ("Piezo buzzer + NPN (2N3904)", [
        ("BASE via 1k", "sig", (25, "BUZZER"), "2.7 kHz LEDC tone", None),
        ("PIEZO +", "pwr", "5V", None, None),
        ("EMITTER", "pwr", "GND", None, None)]),
    ("Status LED", [
        ("ANODE via 330R", "sig", (12, "LED"), "strap pin: LED load keeps it LOW at reset", None),
        ("CATHODE", "pwr", "GND", None, None)]),
]

RIGHT = [
    ("2.8in TFT ILI9341 (Adafruit 1770)", [
        ("CLK", "sig", (5, "TFT_SCK"), None, None),
        ("MOSI", "sig", (18, "TFT_MOSI"), None, None),
        ("CS", "sig", (17, "TFT_CS"), None, None),
        ("D/C", "sig", (13, "TFT_DC"), "also on-board red LED", None),
        ("VIN", "pwr", "5V", None, None),
        ("GND", "pwr", "GND", None, None),
        ("RST, MISO, LITE", "txt", "not connected", None, None)]),
    ("RTC DS3231 (Adafruit 3013, CR1220)", [
        ("SDA", "sig", (23, "I2C_SDA"), "breakout 10k pull-ups", None),
        ("SCL", "sig", (22, "I2C_SCL"), None, None),
        ("VIN", "pwr", "3V3", None, None),
        ("GND", "pwr", "GND", None, None)]),
    ("Load-cell amp HX711 (SparkFun)", [
        ("DAT", "sig", (36, "HX_DAT"), "10k pull-up to 3V3 (input-only pin)", None),
        ("CLK", "sig", (4, "HX_SCK"), None, None),
        ("VCC + VDD", "pwr", "3V3", None, None),
        ("GND", "pwr", "GND", None, None),
        ("E+ E- A+ A-", "txt", "TAL221 100 g: red, black, green, white", None, None)]),
    ("Motor driver TB6612FNG (Adafruit, ch. A)", [
        ("STBY", "sig", (26, "MOTOR_EN"), "10k pull-down to GND: off during reset", None),
        ("AIN1", "sig", (27, "AIN1"), None, None),
        ("AIN2", "sig", (33, "AIN2"), None, None),
        ("PWMA", "sig", (21, "PWMA"), "20 kHz PWM", None),
        ("VM (100uF + 0.1uF)", "pwr", "12V", None, None),
        ("VCC", "pwr", "3V3", None, None),
        ("GND", "pwr", "GND", None, None),
        ("AO1 / AO2", "txt", "motor M1 / M2 (BIN*, PWMB to GND)", None, None)]),
    ("Gearmotor encoder (Pololu 5229, 12 CPR)", [
        ("A (yellow)", "sig", (34, "ENC_A"), "input-only; encoder pull-ups", None),
        ("B (white)", "sig", (14, "ENC_B"), None, None),
        ("VCC (blue)", "pwr", "3V3", None, None),
        ("GND (green)", "pwr", "GND", None, None),
        ("M1 / M2", "txt", "to TB6612 AO1 / AO2", None, None)]),
]

SILK = {32: "32/A7", 15: "15/A8", 19: "MI/19", 39: "A3/39", 16: "RX/16", 25: "A1/25",
        12: "12/A11", 5: "SCK/5", 18: "MO/18", 17: "TX/17", 13: "13/A12", 23: "SDA/23",
        22: "SCL/22", 36: "A4/36", 4: "A5/4", 26: "A0/26", 27: "27/A10", 33: "33/A9",
        21: "21", 34: "A2/34", 14: "14/A6"}

W, ROW, GAP = 1720, 26, 22
TOP = 380                      # first component row
LBOX = (150, 430)              # left component box x-range
RBOX = (1290, 1570)
FEATHER = (735, 985)
LRAIL = {"3V3": 40, "5V": 62, "GND": 84}
RRAIL = {"12V": W - 40, "5V": W - 62, "3V3": W - 84, "GND": W - 106}
BUS_Y = {"12V": 236, "5V": 258, "3V3": 280}

svg = []


def t(x, y, s, size=13, anchor="start", weight="normal", fill="#111", italic=False):
    st = ' font-style="italic"' if italic else ""
    svg.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
               f'font-weight="{weight}" fill="{fill}"{st}>{escape(s)}</text>')


def line(x1, y1, x2, y2, c, w=2.2):
    svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="{w}" '
               f'stroke-linecap="round"/>')


def dot(x, y, c):
    svg.append(f'<circle cx="{x}" cy="{y}" r="3.6" fill="{c}"/>')


def box(x1, y1, x2, y2, fill="#f7f7f7", stroke=COL["box"], rx=6):
    svg.append(f'<rect x="{x1}" y="{y1}" width="{x2 - x1}" height="{y2 - y1}" rx="{rx}" '
               f'fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')


def layout(comps, side):
    """Place components top-down; return (feather pins, rail taps, max y)."""
    y = TOP
    fpins, taps = [], []
    x1, x2 = LBOX if side == "L" else RBOX
    for title, pins in comps:
        inner = [p for p in pins if p[1] in ("sig", "txt")]
        outer = [p for p in pins if p[1] == "pwr"]
        heights = [ROW + (14 if p[3] else 0) for p in inner]
        top = y
        h = 30 + max(sum(heights), len(outer) * ROW)
        box(x1, top, x2, top + h)
        t((x1 + x2) / 2, top + 19, title, 13.5, "middle", "bold")
        acc = 0
        for i, (name, kind, data, note, col) in enumerate(inner):
            py = top + 30 + acc + ROW / 2
            acc += heights[i]
            ex = x2 if side == "L" else x1
            t(ex + (-8 if side == "L" else 8), py + 4, name, 12, "end" if side == "L" else "start")
            if kind == "sig":
                fpins.append((py, data, note, col or "sig", ex))
            else:
                fx = FEATHER[0] - 12 if side == "L" else FEATHER[1] + 12
                c = COL["mot"]
                line(ex, py, ex + (40 if side == "L" else -40), py, c, 2)
                t(ex + (46 if side == "L" else -46), py + 4, data, 11.5,
                  "start" if side == "L" else "end", fill=c, italic=True)
        for i, (name, kind, rail, note, _) in enumerate(outer):
            py = top + 30 + i * ROW + ROW / 2
            ex = x1 if side == "L" else x2
            t(ex + (8 if side == "L" else -8), py + 4, name, 12, "start" if side == "L" else "end")
            rx = (LRAIL if side == "L" else RRAIL)[rail]
            line(ex, py, rx, py, COL[rail])
            dot(rx, py, COL[rail])
            lab = rail if not note else f"{rail}  ({note})"
            mid = (ex + rx) / 2 if side == "L" else ex + 8
            if side == "L":
                t(ex - 6, py - 5, rail, 10.5, "end", fill=COL[rail], weight="bold")
            else:
                t(ex + 6, py - 5, lab, 10.5, "start", fill=COL[rail], weight="bold")
            taps.append((rail, py))
        y = top + h + GAP
    return fpins, taps, y


svg_head = []
lf, ltaps, ly = layout(LEFT, "L")
rf, rtaps, ry = layout(RIGHT, "R")
H = int(max(ly, ry) + 120)
GND_Y = H - 50

# Feather box spanning all pins.
fy1 = TOP - 80
fy2 = max(ly, ry) - GAP + 10
box(FEATHER[0], fy1, FEATHER[1], fy2, fill="#eef3fb", stroke="#1f3f7f", rx=10)
t((FEATHER[0] + FEATHER[1]) / 2, fy1 + 22, "Adafruit HUZZAH32", 16, "middle", "bold", "#1f3f7f")
t((FEATHER[0] + FEATHER[1]) / 2, fy1 + 40, "ESP32 Feather (3591, original)", 12, "middle", fill="#1f3f7f")

for side, pins in (("L", lf), ("R", rf)):
    for py, (gpio, net), note, colkey, ex in pins:
        fx = FEATHER[0] if side == "L" else FEATHER[1]
        c = COL[colkey]
        line(ex, py, fx, py, c)
        dot(fx, py, c)
        dot(ex, py, c)
        mid = (ex + fx) / 2
        t(mid, py - 6, f"GPIO{gpio}  {net}", 12, "middle", "bold", c)
        if note:
            t(mid, py + 15, note, 10.5, "middle", fill="#555", italic=True)
        inside = fx + 8 if side == "L" else fx - 8
        t(inside, py + 4, SILK[gpio], 12, "start" if side == "L" else "end", fill="#1f3f7f")

# Feather power pins (top edge) and GND (bottom edge).
fusb, f3v, fgnd = FEATHER[0] + 60, FEATHER[0] + 170, (FEATHER[0] + FEATHER[1]) / 2
line(fusb, BUS_Y["5V"], fusb, fy1, COL["5V"]); dot(fusb, BUS_Y["5V"], COL["5V"])
t((FEATHER[0] + FEATHER[1]) / 2, fy1 + 58, "USB pin: 5 V in via Schottky", 11, "middle", fill=COL["5V"], weight="bold")
line(f3v, BUS_Y["3V3"], f3v, fy1, COL["3V3"]); dot(f3v, BUS_Y["3V3"], COL["3V3"])
t((FEATHER[0] + FEATHER[1]) / 2, fy1 + 74, "3V pin: 3.3 V out (AP2112K 600 mA)", 11, "middle", fill=COL["3V3"], weight="bold")
line(fgnd, fy2, fgnd, GND_Y, COL["GND"]); dot(fgnd, GND_Y, COL["GND"])
t(fgnd + 6, fy2 + 18, "GND", 11, fill=COL["GND"], weight="bold")

# Vertical rails.
for rail, x in LRAIL.items():
    ys = [py for r, py in ltaps if r == rail]
    if not ys:
        continue
    y_top = BUS_Y.get(rail, None)
    if rail == "GND":
        line(x, min(ys), x, GND_Y, COL[rail], 3)
    else:
        line(x, y_top, x, max(ys), COL[rail], 3)
        dot(x, y_top, COL[rail])
for rail, x in RRAIL.items():
    ys = [py for r, py in rtaps if r == rail]
    if not ys:
        continue
    if rail == "GND":
        line(x, min(ys), x, GND_Y, COL[rail], 3)
    else:
        line(x, BUS_Y[rail], x, max(ys), COL[rail], 3)
        dot(x, BUS_Y[rail], COL[rail])

# Horizontal buses.
line(LRAIL["3V3"], BUS_Y["3V3"], RRAIL["3V3"], BUS_Y["3V3"], COL["3V3"], 3)
line(LRAIL["5V"], BUS_Y["5V"], RRAIL["5V"], BUS_Y["5V"], COL["5V"], 3)
line(560, BUS_Y["12V"], RRAIL["12V"], BUS_Y["12V"], COL["12V"], 3)
line(LRAIL["GND"], GND_Y, RRAIL["GND"], GND_Y, COL["GND"], 3)
t(LRAIL["3V3"] + 8, BUS_Y["3V3"] + 15, "3.3 V rail (Feather 3V pin)", 11.5, fill=COL["3V3"], weight="bold")
t(LRAIL["5V"] + 120, BUS_Y["5V"] - 6, "5 V rail", 11.5, fill=COL["5V"], weight="bold")
t(RRAIL["12V"] - 10, BUS_Y["12V"] - 6, "12 V rail (motor only)", 11.5, "end", fill=COL["12V"], weight="bold")
t(W / 2, GND_Y + 20, "COMMON GROUND (star point at the 5 V regulator GND; logic, motor and supply grounds all joined)",
  11.5, "middle", fill=COL["GND"], weight="bold")

# Power supply panel (top).
t(40, 34, "Pill dispenser wiring (system pin map, include/pins.h)", 20, weight="bold")
t(40, 56, "Generated by tools/gen_wiring_svg.py. Original HUZZAH32 GPIO numbers; all logic is 3.3 V.", 12, fill="#555")
box(150, 90, 380, 190, fill="#fff5f5", stroke=COL["12V"])
t(265, 112, "12 V adapter", 14, "middle", "bold")
t(265, 130, "Mean Well GST90A12 (7.5 A)", 11.5, "middle")
t(265, 148, "barrel jack + power switch", 11.5, "middle")
box(430, 120, 540, 170, fill="#fff5f5", stroke=COL["12V"])
t(485, 141, "Fuse 2 A", 13, "middle", "bold")
t(485, 158, "slow-blow, inline", 10.5, "middle")
line(380, 145, 430, 145, COL["12V"]); t(405, 138, "+12V", 10.5, "middle", fill=COL["12V"], weight="bold")
line(540, 145, 560, 145, COL["12V"]); line(560, 145, 560, BUS_Y["12V"], COL["12V"])
dot(560, BUS_Y["12V"], COL["12V"])
line(265, 190, 265, 214, COL["GND"]); t(272, 210, "GND -> common ground", 10.5, fill=COL["GND"])
box(1000, 90, 1250, 190, fill="#fff8f0", stroke=COL["5V"])
t(1125, 112, "5 V regulator", 14, "middle", "bold")
t(1125, 130, "Pololu #4085 (12 V -> 5 V)", 11.5, "middle")
t(1125, 148, "VIN / GND / VOUT", 11.5, "middle")
line(1040, 190, 1040, BUS_Y["12V"], COL["12V"]); dot(1040, BUS_Y["12V"], COL["12V"])
t(1046, 214, "VIN", 10.5, fill=COL["12V"], weight="bold")
line(1210, 190, 1210, BUS_Y["5V"], COL["5V"]); dot(1210, BUS_Y["5V"], COL["5V"])
t(1216, 214, "VOUT 5V", 10.5, fill=COL["5V"], weight="bold")
line(1125, 190, 1125, 204, COL["GND"]); t(1131, 204, "GND", 10.5, fill=COL["GND"])

# Legend.
lx, ly0 = 1290, 40
for i, (k, name) in enumerate((("12V", "12 V (motor supply)"), ("5V", "5 V (regulator out)"),
                               ("3V3", "3.3 V (Feather 3V)"), ("GND", "Ground"),
                               ("sig", "Digital signal"), ("ana", "Analog signal"),
                               ("mot", "Motor / bridge leads"))):
    yy = ly0 + i * 18
    line(lx, yy, lx + 34, yy, COL[k], 3)
    t(lx + 42, yy + 4, name, 11.5)

body = "\n".join(svg)
OUT.write_text(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
    f'font-family="Helvetica, Arial, sans-serif">\n'
    f'<rect width="{W}" height="{H}" fill="#ffffff"/>\n{body}\n</svg>\n')
print(f"wrote {OUT} ({W}x{H})")
