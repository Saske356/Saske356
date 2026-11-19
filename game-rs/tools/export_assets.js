// Конвертер: выгружает из веб-версии все спрайты, свечения, иконки улучшений и текстуры дна в PNG для Rust-версии.
// node game-rs/tools/export_assets.js
const {chromium}=require('playwright'), fs=require('fs'), path=require('path');
const ROOT=path.resolve(__dirname,'..'), OUT=path.join(ROOT,'assets');
(async()=>{const b=await chromium.launch();const p=await b.newPage();const errs=[];p.on('pageerror',e=>errs.push(e.message));
await p.goto('file://'+path.resolve(ROOT,'../game/index.html'));await p.waitForTimeout(6000);
const data=await p.evaluate(()=>{const s=__SB,out={spr:{},meta:{},glow:[],soft:[],bul:[],icon:{},ground:[]};
  const png=c=>c.toDataURL('image/png');
  for(const k in s.SPR){const sp=s.SPR[k];out.spr[k]=png(sp.img);out.meta[k]={h:sp.h,r:sp.r||sp.h*0.7,art:!!sp.art,fl:!!sp.fl,anim:s.animOf(k)||null,live:!!sp.live,w:sp.img.width};}
  for(let i=0;i<s.PAL.length;i++){out.glow.push(png(s.GLOW[i]));out.soft.push(png(s.SOFT[i]));out.bul.push(png(s.BUL[i]));}
  const ids=[...s.UPG.map(u=>u.id),'heal'];for(const id of ids){const u=s.UPG.find(x=>x.id===id)||{col:s.C.EMER};const c=document.createElement('canvas');c.width=c.height=128;s.drawIcon(c,id,u.col);out.icon[id]=png(c);}
  for(let z=0;z<15;z++){s.buildGround(z);out.ground.push(png(s.getGround()));}
  out.pal=s.PAL;out.zoneCols=s.ZONE_COLS;out.zoneAcc=s.ZONE_ACCENTS;return out;});
const w=(f,d)=>{fs.mkdirSync(path.dirname(f),{recursive:true});fs.writeFileSync(f,Buffer.from(d.split(',')[1],'base64'));};
for(const k in data.spr) w(path.join(OUT,'spr',k+'.png'),data.spr[k]);
data.glow.forEach((d,i)=>w(path.join(OUT,'fx','glow'+i+'.png'),d));data.soft.forEach((d,i)=>w(path.join(OUT,'fx','soft'+i+'.png'),d));data.bul.forEach((d,i)=>w(path.join(OUT,'fx','bul'+i+'.png'),d));
for(const k in data.icon) w(path.join(OUT,'icon',k+'.png'),data.icon[k]);
data.ground.forEach((d,i)=>w(path.join(OUT,'ground','g'+i+'.png'),d));
fs.writeFileSync(path.join(OUT,'manifest.json'),JSON.stringify({meta:data.meta,pal:data.pal,zoneCols:data.zoneCols,zoneAcc:data.zoneAcc},null,0));
console.log('sprites',Object.keys(data.spr).length,'icons',Object.keys(data.icon).length,'errors',errs);await b.close();})();
