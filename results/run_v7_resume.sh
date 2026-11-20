#!/bin/bash
# resume after a container restart: gear campaign (small), then the chute + cup runs
cd "$(dirname "$0")/.."
python3 -m sim.campaign v2_v7_module_gear --pills small --trials 200 --workers 4 --resume >> results/v7_module_gear.log 2>&1
python3 -m sim.v7_drop --chute --pills iron small --trials 200 --workers 4 > results/v7_drop_chute.log 2>&1
python3 -m sim.v7_drop --chute --dose 4 --pills iron small --trials 200 --workers 4 > results/v7_drop_chute_dose4.log 2>&1
