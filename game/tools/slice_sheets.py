import sys, numpy as np
from PIL import Image
from collections import deque
U='/root/.claude/uploads/eb06db2a-9880-59bb-bb8f-e7633a189756/'
SHEETS=[('7c696f83-image.png',['lumen','drifter','dart','jelly','urchin']),
        ('8014f6f6-image.png',['eel_head','eel_seg','squid','crab','crab_bare']),
        ('bc3dbf87-image.png',['mender','bomber','spikelet','chest','crystal']),
        ('c286e5f1-image.png',['boss1','boss2','boss3','boss4','x_plant']),
        ('5850ee34-image.png',['d_kelp','d_anemone','d_coral','d_rock','d_shell','d_vent']),
        ('3cde16ee-image.png',['d_pillar','d_ribs','d_skull','d_ice','d_shroom'])]
out=sys.argv[1]
def comps(mask):
    h,w=mask.shape; lab=np.zeros((h,w),int); n=0; res=[]
    for y in range(h):
        for x in range(w):
            if mask[y,x] and not lab[y,x]:
                n+=1; q=deque([(y,x)]); lab[y,x]=n; ys=[];xs=[]
                while q:
                    cy,cx=q.popleft(); ys.append(cy); xs.append(cx)
                    for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
                        ny,nx=cy+dy,cx+dx
                        if 0<=ny<h and 0<=nx<w and mask[ny,nx] and not lab[ny,nx]: lab[ny,nx]=n; q.append((ny,nx))
                res.append((len(ys),min(xs),min(ys),max(xs),max(ys),n))
    return lab,res
for f,names in SHEETS:
    im=Image.open(U+f).convert('RGBA'); a=np.array(im); al=a[...,3]
    K=6; small=al[::K,::K]>90
    # лёгкое расширение маски, чтобы плавники/щупальца не отрывались
    m=small.copy()
    for _ in range(2): m=m|np.roll(m,1,0)|np.roll(m,-1,0)|np.roll(m,1,1)|np.roll(m,-1,1)
    lab,res=comps(m)
    res=[r for r in res if r[0]>150]; res.sort(key=lambda r:-r[0]); res=res[:len(names)]
    # порядок: сверху вниз рядами, слева направо
    res.sort(key=lambda r:((r[2]+r[4])/2//(1254/K/3.2), r[1]))
    for name,r in zip(names,res):
        _,x0,y0,x1,y1,n=r
        X0,Y0,X1,Y1=max(0,x0*K-8),max(0,y0*K-8),min(1254,(x1+1)*K+8),min(1254,(y1+1)*K+8)
        crop=a[Y0:Y1,X0:X1].copy()
        # оставить только свой объект (без соседей), убрать пёстрый мусор по краям
        cm=(lab[Y0//K:(Y1+K-1)//K, X0//K:(X1+K-1)//K]==n)
        cm=np.kron(cm,np.ones((K,K),bool))[:crop.shape[0],:crop.shape[1]]
        A=crop[...,3].astype(float); A[~cm]=0
        A=np.clip((A-45)/(255-45),0,1)*255   # срезаем полупрозрачную «пыль»
        crop[...,3]=A.astype(np.uint8)
        Image.fromarray(crop).save(f'{out}/{name}.png'); print(name, crop.shape[1],'x',crop.shape[0])
