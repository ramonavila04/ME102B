#!/bin/bash
# after run_v7_verify.sh: final chute + pill cup checks
cd "$(dirname "$0")/.."
while pgrep -f run_v7_verify.sh >/dev/null; do sleep 30; done
python3 -m sim.v7_drop --chute --pills iron small --trials 200 --workers 4 > results/v7_drop_chute.log 2>&1
python3 -m sim.v7_drop --chute --dose 4 --pills iron small --trials 200 --workers 4 > results/v7_drop_chute_dose4.log 2>&1
