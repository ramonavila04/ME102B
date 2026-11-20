# Pill shapes for the dispenser

Three generalized shapes cover most pills people take every day: **round tablets**, **oval
or oblong tablets (caplets)**, and **two-piece hard capsules**. This page gives the
dimensions to design for, where each figure comes from, and how well the V2 dispenser
handles each shape today.

## Why these three

- The five most prescribed drugs in the US in 2023 were atorvastatin, metformin,
  levothyroxine, lisinopril and amlodipine ([ClinCalc Top 300 of 2023][clincalc]).
  These are all tablets: round (lisinopril), oval (atorvastatin) or oblong (metformin).
- Common over-the-counter pills fall in the same shapes: low-dose aspirin and ibuprofen are
  round tablets, and Tylenol Extra Strength is an oblong caplet.
- Capsules are the other everyday form, for example omeprazole and gabapentin.
- I found no published share of the market by tablet shape, so "most common" here means
  the shapes of the most prescribed and best-known products, not a measured percentage.

Out of scope: **softgels** (soft, deformable and often tacky; e.g. fish oil, liquid-gel
pain relievers), chewable and orally disintegrating tablets (fragile), and powders or liquids.

## Measured sizes of everyday products

Largest dimension as listed by the Drugs.com pill identifier. These databases list one size
only; **thickness and width are not published**, which is why section 4 says to measure.

| Product | Shape | Largest dimension | Source |
| --- | --- | --- | --- |
| Aspirin 81 mg, enteric coated | Round | 6–7 mm | [Drugs.com "L"][asp6], [Drugs.com "Heart"][asp7] |
| Lisinopril 10 mg | Round | 6–8 mm | [Drugs.com "LI 10"][lis6], [Drugs.com "LUPIN 10"][lis8] |
| Ibuprofen 200 mg | Round | 10 mm | [Drugs.com "114"][ibu] |
| Nature Made Iron 65 mg (team test pill) | Round | about 9.5 mm (estimate, not measured) | ASSUMPTIONS A2 |
| Atorvastatin 20 mg | Oval | 11–12 mm | [Drugs.com "20"][ator11], [Drugs.com "ATO 20"][ator12] |
| Metformin ER 500 mg | Oblong | 16–19 mm | [Drugs.com "LA20"][met16], [Drugs.com "G7"][met18], [Drugs.com "Logo 500"][met19] |
| Tylenol Extra Strength 500 mg | Oblong caplet | 19 mm | [Drugs.com "TYLENOL 500"][tyl] |
| Omeprazole 20 mg | Capsule | 17–18 mm | [Drugs.com "R644"][ome17], [Drugs.com "OM 20"][ome18] |
| Gabapentin 300 mg | Capsule | 19–21 mm | [Drugs.com "SG 180"][gab19], [Drugs.com "IG322"][gab21] |

The same drug and strength varies by 1–3 mm between manufacturers, so a dispenser set up
for "lisinopril 10 mg" may not fit every refill.

## The three design shapes

### 1. Round biconvex tablet

| | Value |
| --- | --- |
| Design range | Ø6–10 mm |
| Thickness | about 0.45–0.55 × diameter (from the two kits below; **assumed, not sourced**) |
| Faces | Domed, with a straight band at the edge; cup depth is typically 0.13–0.2 × diameter ([patent CA 2557377][cup1], [Chem. Pharm. Bull.][cup2]) |
| Kits modelled | `small` Ø6.0 × 2.8 mm, 0.10 g; `iron` Ø9.5 × 5.0 mm, 0.40 g |
| V2 status | **Passes**: 200/200 trials, 600/600 dispenses for both kits, shaft-drive design |

The pocket type depends on thickness ÷ diameter. A thin tablet (below about 0.5) can stand
on edge beside a second one in an open notch, so `build.py` gives it a closed pocket and a
rib liner; a thick one gets an open notch. A new round tablet needs its own disc, back
plate and hopper built from its measured size.

### 2. Oval or oblong tablet (caplet)

| | Value |
| --- | --- |
| Design range | 11–19 mm long; oval shapes sit at the short end, caplets at the long end |
| Width and thickness | not published for any product found; the kit below assumes 8.5 × 6.5 mm |
| Kit modelled | `caplet` 19.0 × 8.5 × 6.5 mm, 1.20 g (largest common size) |
| V2 status | **Experimental, not passing.** Small targeted tests are clean (24/24 at 4 loaded, 23/24 at 10 loaded), but the 200-trial campaign has not run |

An 11–12 mm oval such as atorvastatin is between the round and caplet kits and has not been
modelled. Long pills stand on end, pair up in one pocket and lock each other when only a few
are left; `cad/variants/v2_inclined_disc/DESIGN.md` lists what was tried.

### 3. Two-piece hard capsule

Standard sizes are set by the capsule makers, so these are the best-defined numbers here.

| Size | Closed length (mm) | Cap diameter (mm) | Example |
| --- | ---: | ---: | --- |
| 00 | 23.3 | 8.53 | Largest size FDA recommends for generics ([FDA guidance summary][fda]) |
| 0 | 21.7 | 7.64 | Matches gabapentin 300 mg (19–21 mm) |
| 1 | 19.4 | 6.91 | |
| 2 | 18.0 | 6.35 | Matches omeprazole 20 mg (17–18 mm) |
| 3 | 15.9 | 5.82 | |

Sizes from [Medisca Coni-Snap chart][medisca] and [Wikipedia capsule table][wiki]; length
tolerance is about ±0.3 mm ([pharmacy text, Capsugel data][capsugel]).

| | Value |
| --- | --- |
| Design range | sizes 2 to 0 (18.0–21.7 mm long, 6.35–7.64 mm diameter) |
| Kit modelled | `cap0` size 0, 21.7 × Ø7.65 mm |
| V2 status | **Experimental, not passing.** 24/24 at 4 loaded with the latest revision; full campaign not run |

## Other factors that matter

| Factor | Why it matters for this dispenser | What to do |
| --- | --- | --- |
| **Size limits** | FDA recommends generic tablets stay at or under 22 mm in any dimension and capsules at or under size 00 ([FDA guidance summary][fda]) | No pocket ever needs to exceed 22 × 8.5 mm |
| **Variation between makers** | The same drug varies 1–3 mm in size by manufacturer (table above) | Measure the actual pills on hand; rebuild the kit if they differ by more than 0.15 mm |
| **Thickness** | Sets pocket depth and whether two can stack; never published in pill databases | Measure 10 pills with calipers |
| **Coating and friction** | Film-coated and enteric-coated tablets slide differently from uncoated ones; the simulation covers friction 0.2–0.6 | Test the real pill on a PLA slope before building |
| **Mass** | Capsules are light (often under 0.5 g) and can float on static or air; the load cell must see them | Check the load cell resolves the lightest pill |
| **Humidity** | Gelatin capsules soften and get tacky in humid air; coated tablets less so | Keep the hopper covered; note it in testing |
| **Score lines and chips** | A scored tablet can break at the score; broken halves change the shape | Use whole, unscored pills for testing |
| **Dust** | Uncoated tablets shed powder that collects in pockets | Clean the disc between test sessions |
| **Orientation** | Round tablets work in any rotation; caplets and capsules must lie lengthwise in the pocket | This is why long pills are harder (shape 2 and 3 status) |

## What this means for the project

- **Shape 1 (round tablets) is ready.** Build the iron or small-tablet kit; for another
  round pill, measure it, add it to `sim/pills.py`, rebuild and rerun the campaign.
- **Shapes 2 and 3 need more work** before they can be claimed. The caplet and capsule kits
  exist in CAD but have not passed the 200-trial test.
- **Thicknesses and widths in this page are estimates** except the capsule sizes. Measure
  real pills before relying on them (BUILD.md section 2).

[clincalc]: https://clincalc.com/drugstats/Top300Drugs.aspx
[asp6]: https://www.drugs.com/imprints/l-36276.html
[asp7]: https://www.drugs.com/imprints/heart-11363.html
[lis6]: https://www.drugs.com/imprints/li-10-24512.html
[lis8]: https://www.drugs.com/imprints/lupin-10-6431.html
[ibu]: https://www.drugs.com/imprints/114-17925.html
[ator11]: https://www.drugs.com/imprints/20-21779.html
[ator12]: https://www.drugs.com/imprints/ato-20-30795.html
[met16]: https://www.drugs.com/imprints/la20-35276.html
[met18]: https://www.drugs.com/imprints/g7-27221.html
[met19]: https://www.drugs.com/imprints/logo-500-16041.html
[tyl]: https://www.drugs.com/imprints/tylenol-500-20079.html
[ome17]: https://www.drugs.com/imprints/omeprazole-20-mg-r644-23393.html
[ome18]: https://www.drugs.com/imprints/om-20-26372.html
[gab19]: https://www.drugs.com/imprints/sg-180-24312.html
[gab21]: https://www.drugs.com/imprints/ig322-300-mg-16226.html
[cup1]: https://brevets-patents.ic.gc.ca/opic-cipo/cpd/eng/patent/2557377/summary.html
[cup2]: https://www.jstage.jst.go.jp/article/cpb/73/3/73_c24-00675/_html/-char/en
[fda]: https://www.raps.org/resource/fda-to-generic-sponsors-physical-attributes-shoul.html
[medisca]: https://files.medisca.com/NDCSpecs/MUS/1112/Downloads/Coni-Snap%20Capsule%20Sizes%20Chart.pdf
[wiki]: https://en.wikipedia.org/wiki/Capsule_(pharmacy)
[capsugel]: https://ssinhacollege.co.in/images/econtent/vocational%20courses/Bpharma/B.%20Pharm.%20(1st%20Year)_(Topic-%20Capsules%20Text).pdf
