#!/bin/bash
# V8 housing pill-drop verification (single pills, then 4-pill doses)
cd "$(dirname "$0")/.."
python3 -m sim.v8_drop --pills iron small --trials 200 --workers 4 > results/v8_drop.log 2>&1
python3 -m sim.v8_drop --pills iron small --trials 50 --workers 4 --dose 4 > results/v8_drop_dose4.log 2>&1
