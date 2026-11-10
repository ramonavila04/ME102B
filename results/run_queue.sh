#!/bin/sh
# Runs the remaining campaigns one after another; safe to rerun (every step resumes).
cd /home/user/me102b
python3 -m sim.campaign v2_inclined_disc --trials 200 --workers 4 --resume >> results/v2_campaign.log 2>&1
python3 -m sim.campaign v3_shuttle --trials 200 --workers 4 --resume >> results/v3_campaign.log 2>&1
python3 -m sim.campaign v0_original --pills caplet cap0 --trials 200 --workers 4 --resume >> results/v0_campaign3.log 2>&1
