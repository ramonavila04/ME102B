#!/bin/sh
# Runs every campaign one after another; safe to rerun (each step resumes where it stopped).
cd /home/user/me102b
python3 -m sim.campaign v2_inclined_disc --trials 200 --workers 4 --resume >> results/v2_campaign.log 2>&1
python3 -m sim.campaign v0_original --trials 200 --workers 4 --resume >> results/v0_campaign.log 2>&1
python3 -m sim.campaign v1_fixed_rotor --trials 200 --workers 4 --resume >> results/v1_campaign.log 2>&1
python3 -m sim.campaign v3_shuttle --trials 200 --workers 4 --resume >> results/v3_campaign.log 2>&1
