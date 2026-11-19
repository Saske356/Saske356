// Конвертер данных: таблицы игры и тексты RU/EN из веб-версии -> assets/data.json для Rust.
// Функции-шаблоны текстов превращаются в строки с {0},{1},{2}.
const {chromium}=require('playwright'), fs=require('fs'), path=require('path');
const ROOT=path.resolve(__dirname,'..');
(async()=>{const b=await chromium.launch();const p=await b.newPage();const errs=[];p.on('pageerror',e=>errs.push(e.message));
await p.goto('file://'+path.resolve(ROOT,'../game/index.html'));await p.waitForTimeout(5000);
const out=await p.evaluate(()=>{const s=__SB,D=s.DATA();
  const tmpl=v=>{if(typeof v==='function'){try{return {tpl:String(v('{0}','{1}','{2}'))};}catch(e){return {tpl:'?'};}} return v;};
  const walk=o=>{if(typeof o==='function')return tmpl(o);if(Array.isArray(o))return o.map(walk);if(o&&typeof o==='object'){const r={};for(const k in o)r[k]=walk(o[k]);return r;}return o;};
  return walk({CFG:s.CFG,ET:s.ET,UPG:s.UPG,SHOP:s.SHOP,...D});});
fs.writeFileSync(path.join(ROOT,'assets','data.json'),JSON.stringify(out,null,1));
console.log('keys',Object.keys(out).join(','),'errors',errs);await b.close();})();
