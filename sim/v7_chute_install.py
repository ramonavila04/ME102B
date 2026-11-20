"""Can the chute be put into the V7 enclosure? (run from the repo root:
    python sim/v7_chute_install.py [chute folder, default cad/variants/v2_v7_module/chute])

The chute's lip sits under the enclosure's front window lintel and its sides under ribs, so it
cannot be lowered straight into place. Checked path, with the deck off and the brackets and
front panel already fitted: hold the chute OFFSET mm behind its final position, lower it
straight down from above the rim, then slide it forward OFFSET mm onto the brackets.
The chute is split into exact convex pieces; obstacle surfaces are sampled every ~0.5 mm and
must stay MARGIN mm outside every piece. Exit status 1 if any step is blocked.
"""
import sys
import numpy as np
import trimesh
sys.path.insert(0,'.')
from sim.convexify import decompose_file
D=(sys.argv[1].rstrip('/') + '/') if len(sys.argv) > 1 else 'cad/variants/v2_v7_module/chute/'   # folder with chute.stl and the brackets
pcs=decompose_file(D+'chute.stl', tol=0.1, min_cell=1.0)
hulls=[]
for p in pcs:
    Hh=trimesh.Trimesh(np.asarray(p.vertices)).convex_hull; hulls.append((Hh.face_normals,(Hh.face_normals*Hh.triangles[:,0]).sum(1),Hh.bounds))
cb=trimesh.load(D+'chute.stl').bounds
obs={}
src=[('enclosure','sim/.cache/v7_parts/Enclosure.stl'),('funnel_mounts','sim/.cache/v7_parts/Funnel_mounts.stl'),
     ('station','sim/.cache/v7_parts/Weighing_station.stl'),('front_panel','sim/.cache/v7_parts/Front_panel_controls.stl')]+\
    [(n,D+n+'.stl') for n in ['bracket_right','bracket_left','bracket_front']]
for k,f in src:
    m=trimesh.load(f); c=m.triangles_center
    keep=(abs(c[:,0])<70)&(c[:,1]>cb[0][1]-15)&(c[:,1]<cb[1][1]+90)&(c[:,2]>cb[0][2]-5)&(c[:,2]<-5.2)
    if not keep.any(): continue
    sub=m.submesh([np.where(keep)[0]],append=True)
    p,_=trimesh.sample.sample_surface(sub,min(int(sub.area/0.25)+1,300000)); obs[k]=np.vstack([p,sub.vertices])

def hits(off,margin=0.25):
    res={}
    for k,p in obs.items():
        q=p-off
        q=q[(q[:,2]>cb[0][2]-1)&(q[:,2]<cb[1][2]+1)&(q[:,1]>cb[0][1]-1)&(q[:,1]<cb[1][1]+1)]
        pts=[]
        for A,b,bb in hulls:
            r=q[(q[:,0]>bb[0][0])&(q[:,0]<bb[1][0])&(q[:,1]>bb[0][1])&(q[:,1]<bb[1][1])&(q[:,2]>bb[0][2])&(q[:,2]<bb[1][2])]
            if len(r): pts.append(r[((r@A.T)-b < -margin).all(1)])
        pts=np.vstack(pts) if pts else np.zeros((0,3))
        if len(pts): res[k]=pts+off
    return res
OFFSET, MARGIN = 40.0, 0.25
steps = [(OFFSET, dz) for dz in (140, 130, 120, 110, 100, 95, 90, 80, 64, 48, 32, 16, 8, 4, 2, 0)] + \
        [(dy, 0.0) for dy in np.arange(OFFSET, -0.1, -2.5)]
bad = 0
for dy, dz in steps:
    h = hits(np.array([0, dy, dz], float), MARGIN)
    if h:
        bad += 1
        print(f"blocked at back {dy:5.1f} up {dz:5.1f}:", {k: len(v) for k, v in h.items()})
print(f"{len(steps)} steps, {bad} blocked:", "PASS" if not bad else "FAIL")
sys.exit(1 if bad else 0)
