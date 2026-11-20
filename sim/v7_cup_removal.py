"""Can the pill cup be taken out of the V7 window? Checks a removal path against the
enclosure, weighing station, front panel and chute (run from the repo root:
python sim/v7_cup_removal.py). The cup is split into exact convex pieces; obstacle
surfaces are sampled every ~0.4 mm and must stay `margin` mm outside every piece."""
import sys, trimesh, numpy as np
sys.path.insert(0,'.')
from sim.convexify import decompose_file
pieces=decompose_file('cad/variants/v2_v7_module/chute/pill_cup.stl', tol=0.1, min_cell=1.0)
hulls=[]
for p in pieces:
    v=np.asarray(p.vertices if hasattr(p,'vertices') else p['vertices'] if isinstance(p,dict) else p[0])
    H=trimesh.Trimesh(v).convex_hull; hulls.append((H.face_normals,(H.face_normals*H.triangles[:,0]).sum(1)))
print('pieces',len(hulls),flush=True)
def crop(m):
    c=m.triangles_center; k=(abs(c[:,0])<70)&(c[:,1]<-80)&(c[:,2]>-145)&(c[:,2]<-30)
    return m.submesh([np.where(k)[0]],append=True)
obs={}
for k,f in [('enclosure','sim/.cache/v7_parts/Enclosure.stl'),('station','sim/.cache/v7_parts/Weighing_station.stl'),
            ('front_panel','sim/.cache/v7_parts/Front_panel_controls.stl'),('chute','cad/variants/v2_v7_module/chute/chute.stl')]:
    m=crop(trimesh.load(f)); p,_=trimesh.sample.sample_surface(m,min(int(m.area/0.15)+1,400000)); obs[k]=np.vstack([p,m.vertices])
def hit(off,margin=0.3):
    res={}
    for k,p in obs.items():
        q=p-off; box=(q[:,0]>-26)&(q[:,0]<26)&(q[:,1]>-138)&(q[:,1]<-113)&(q[:,2]>-136)&(q[:,2]<-114); q=q[box]
        n=0
        for A,b in hulls: n+=int(((q@A.T)-b < -margin).all(1).sum())
        if n: res[k]=n
    return res
path=[(0,0),(-3,0),(-6,1)]+[(-6-1.2*i,1+1.6*i) for i in range(1,11)]+[(-20,17),(-30,17),(-45,17),(-60,17)]
for m in [0.3,0.6,1.0]:
    bad=[(round(dy,1),round(dz,1),h) for dy,dz in path if (h:=hit(np.array([0,dy,dz]),margin=m))]
    print('margin',m,'blocked at',bad,flush=True)
