// Бот-симулятор: играет в настоящую игру на перемотке (без отрисовки), печатает итоги забегов.
// node bot.js [file] [runs] [shop: 0|max] [skill: 0..1]
const {chromium}=require('playwright');
const file=process.argv[2]||'/home/user/Saske356/game/index.html', RUNS=+(process.argv[3]||4), SHOPMODE=process.argv[4]||'0', SKILL=+(process.argv[5]||0.6);
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:390,height:844}});
const errs=[];p.on('pageerror',e=>errs.push(e.message));
await p.addInitScript(h=>{window.__HARD=h;},process.env.HARD==='1');await p.goto('file://'+file);await p.waitForTimeout(6000);
const results=[];
for(let run=0;run<RUNS;run++){
  await p.evaluate(([shop])=>{const s=__SB;s.S.seenIntro=1;s.S.tut=1;s.S.seenHow=1;
    for(const it of s.SHOP) s.S.shop[it.id]= shop==='max'?it.max:0;
    s.setQuality('low'); s.S.set.hard=(window.__HARD?1:0); s.S.wins=window.__HARD?1:s.S.wins; s.startRun(); s.G.state='play';
    window.__bot={t:0,minHp:1,hits:0,deathT:0,deathZ:0,bosses:[],done:false,lvls:0,lastHp:s.P.hp};
  },[SHOPMODE]);
  let finished=false, guard=0;
  while(!finished && guard++<400){
    finished=await p.evaluate(([SKILL])=>{const s=__SB,G=s.G,P=s.P,B=window.__bot,dt=1/60;
      for(let i=0;i<60*20;i++){
        if(G.state==='levelup'){const ch=s.rollChoices();s.takeUpgrade(ch[(Math.random()*ch.length)|0]);B.lvls++;continue;}
        if(G.state==='revive'||G.state==='over'||P.dead||G.dying>0){B.done=true;B.deathT=G.runT;B.deathZ=G.zone;return true;}
        if(G.state==='ending'||G.victory||G.endingT>0){B.done=true;B.win=true;B.deathT=G.runT;B.deathZ=G.zone;return true;}
        if(G.state!=='play'){G.state='play';}
        // --- управление: отталкивание от врагов и пуль, тяга к опыту и к центру
        let fx=0,fy=0; const it=s.enemies.items; let nearB=1e9;
        for(let k=0;k<s.enemies.n;k++){const e=it[k];if(e.dead)continue;const dx=P.x-e.x,dy=P.y-e.y,d2=dx*dx+dy*dy+1,R=(e.r+60)*(s.ET[e.type].boss?2.2:1);
          if(d2<R*R*9){const w=R*R/d2;fx+=dx/Math.sqrt(d2)*w;fy+=dy/Math.sqrt(d2)*w;}}
        const eb=s.ebul.items;for(let k=0;k<s.ebul.n;k++){const q=eb[k];if(q.dead)continue;const dx=P.x-q.x,dy=P.y-q.y,d2=dx*dx+dy*dy+1;
          if(d2<160*160){ // уклон поперёк полёта пули
            const vl=Math.hypot(q.vx,q.vy)+1e-3, px=-q.vy/vl, py=q.vx/vl, side=(dx*px+dy*py)>=0?1:-1, w=SKILL*2600/d2;
            fx+=px*side*w*40; fy+=py*side*w*40; if(d2<nearB)nearB=d2;}}
        const pk=s.picks.items;let best=null,bd=1e9;for(let k=0;k<s.picks.n;k++){const q=pk[k];const d=Math.hypot(q.x-P.x,q.y-P.y);if(d<bd){bd=d;best=q;}}
        if(best&&bd<400){fx+=(best.x-P.x)/bd*0.35;fy+=(best.y-P.y)/bd*0.35;}
        const cd=Math.hypot(P.x,P.y); if(cd>s.CFG.ARENA_R*0.6){fx-=P.x/cd*(cd/s.CFG.ARENA_R);fy-=P.y/cd*(cd/s.CFG.ARENA_R);}
        // неидеальная реакция: часть кадров бот «тупит»
        if(Math.random()>SKILL*0.9+0.1){fx*=0.3;fy*=0.3;}
        const m=Math.hypot(fx,fy); s.Input.jx=m>0.05?fx/m:0; s.Input.jy=m>0.05?fy/m:0;
        s.Input.dashQ = nearB<45*45 && Math.random()<SKILL;
        s.Input.flareQ = P.flare>=100;
        if(P.hp<B.lastHp)B.hits++; B.lastHp=P.hp; B.minHp=Math.min(B.minHp,P.hp/P.maxHp);
        if(G.boss&&!B.bosses.includes(G.boss.type+'@'+Math.round(G.runT)))B.cur=G.boss.type;
        if(B.cur&&!G.boss){B.bosses.push(B.cur+'@'+Math.round(G.runT/6)/10+'м');B.cur=null;}
        s.updateRun(dt,dt); B.t+=dt;
      }
      return false;},[SKILL]);
  }
  const r=await p.evaluate(()=>{const B=window.__bot,G=__SB.G,P=__SB.P;return {win:!!B.win,min:+(B.deathT/60).toFixed(1),depth:B.deathZ*100,lvl:P.level,hits:B.hits,minHp:+B.minHp.toFixed(2),bosses:B.bosses.join(' ')}});
  results.push(r); console.log(JSON.stringify(r));
}
console.log('errors',errs.slice(0,3));await b.close();})();
