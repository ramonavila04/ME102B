#!/bin/sh
# Runs the campaigns one after another; safe to rerun (each step resumes where it stopped).
cd /home/user/me102b
P="--pills iron small"
python3 -m sim.campaign v2_inclined_disc $P --trials 50 --workers 4 --resume --tag recheck >> results/v2_recheck.log 2>&1
python3 -m sim.campaign v0_original $P --trials 200 --workers 4 --resume >> results/v0_campaign.log 2>&1
python3 -m sim.campaign v1_fixed_rotor $P --trials 200 --workers 4 --resume >> results/v1_campaign.log 2>&1
python3 -m sim.campaign v3_shuttle $P --trials 200 --workers 4 --resume >> results/v3_campaign.log 2>&1
python3 -m sim.campaign v0_original --pills caplet cap0 --trials 200 --workers 4 --resume >> results/v0_campaign.log 2>&1
