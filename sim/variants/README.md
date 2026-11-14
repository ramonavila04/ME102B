# Variant contract

A variant is two files:

1. `cad/variants/<variant>/build.py` — a CadQuery script, parameterised by pill
   (`sim/pills.py`). `python cad/variants/<variant>/build.py [pill ...]` writes, for
   each pill, `cad/variants/<variant>/<pill>/`:
   - one `.step` and one `.stl` per printed part, **in assembled position**
     (millimetres, +z up, gravity −z);
   - `manifest.json` for `cad/check_printability.py`:
     `{"variant", "pill", "parts": [{"name", "stl", "print_rotation": [rx, ry, rz]}],
       "clearances": [{"a", "b", "min": 0.3, "what"}], "params": {...}}`.
   Parts that are the same for every pill (housing, hopper) may be exported once
   and referenced with a relative path.
2. `sim/variants/<variant>.py` with `spec(pill_id) -> dict`. It calls the build
   (or reads its outputs) and returns:

| key | meaning |
| --- | --- |
| `name` | display name |
| `parts` | list of `{name, stl, body: "static"\|"rotor", crop: ((x0,y0,z0),(x1,y1,z1)) or None, tol: hull tolerance mm (0.05 near pills, ≤0.25 for hopper walls)}` |
| `joint` | `{"type": "hinge", "axis": (x,y,z), "pos": (x,y,z)}` or `{"type": "slide", "axis": ..., "crank_r": mm}` (scotch yoke: x = r·sin θ) |
| `rotor_mass_kg` | moving-part mass (PLA 1.24 g/cm³) |
| `drive` | `{index_deg, rpm, dir, accel_s, settle_s, start_deg, max_steps}`. One dispense = up to `max_steps` index moves of `index_deg`, stopping once the chute sensor sees a pill (this is what the firmware does). |
| `spawn` | `{x: (lo,hi), y: ..., z: ..., accept: f(x,y,z,r)->bool}` region where pill centres are dropped in at random |
| `fill` | `(min, max)` pills in the hopper per trial |
| `exit` | `{z, x: (lo,hi), y: (lo,hi)}` — a pill centre below `z` inside the x/y box is a dispensed pill (the beam-break plane). Put it ≤ 15 mm below where the pill leaves the mechanism. |
| `loss_z` | a pill below this z and outside the exit box has fallen somewhere it shouldn't |
| `fill_s`, `settle_s` | damped fill time, then undamped settle before cycle 1 |
| `site_namer(part, pos_mm) -> str` | optional readable jam-site label |
| `flaps` | optional compliant brush (see v0) |

## Rules (never loosen these)

- Run: `python -m sim.campaign <variant> --trials 200` (all four pills). A variant
  **passes only with zero jam, double, miss, lost and leak outcomes in every cycle
  of every trial**, and no crashed trials.
- `unstable_trials` counts trials where MuJoCo hit a NaN and reset (outcome meaningless). `anomaly_trials` counts trials where a pill exceeded 2.5 m/s (a soft-contact
  blow-up). A passing variant must have zero of both; if it has any,
  investigate, don't ignore.
- Don't change `sim/engine.py` thresholds, friction ranges, tolerances or the
  motor model to make a variant pass. Change the geometry.
- CAD rules: walls ≥ 1.2 mm; ≥ 0.3 mm clearance per sliding pair (0.4 mm
  preferred); print orientation without supports; `cad/check_printability.py` must
  pass for every pill.
- Motor: Pololu 1000:1 micro gearmotor, ~35 rpm no-load, 3 mm D-shaft. Keep
  `rpm` ≤ 30 (it's under load). Housings mount it with 2× M2 screws (Pololu
  bracket #989 or a printed clamp).

## CPU etiquette

The machine has 4 cores shared by everyone. For iteration use
`--trials 10 --workers 1`. Before a 200-trial campaign, take the lock so only one
big run happens at a time:

    flock /tmp/me102b_campaign.lock python -m sim.campaign <variant> --trials 200 --workers 3
