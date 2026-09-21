import { TinyAudio } from './audio.js';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

/* ---------- audio ---------- */
const audio = new TinyAudio();
let soundOn = true;
try{ const p=JSON.parse(localStorage.getItem('scz-orbit-prefs')||'{}'); if(typeof p.soundOn==='boolean') soundOn=p.soundOn; }catch{}
audio.enabled = soundOn;
$('#btn-sound').textContent = soundOn ? '声音开 · WebAudio 合成' : '声音关';
$('#btn-sound').setAttribute('aria-pressed', String(soundOn));
$('#btn-sound').addEventListener('click', ()=>{
  soundOn=!soundOn; audio.enabled=soundOn;
  $('#btn-sound').textContent = soundOn ? '声音开 · WebAudio 合成' : '声音关';
  $('#btn-sound').setAttribute('aria-pressed', String(soundOn));
  persistPrefs(); if(soundOn) audio.click();
});
function persistPrefs(){
  try{ const cur=JSON.parse(localStorage.getItem('scz-orbit-prefs')||'{}'); cur.soundOn=soundOn; localStorage.setItem('scz-orbit-prefs', JSON.stringify(cur)); }catch{}
}

/* ---------- countdown & telemetry ---------- */
const target = new Date('2027-03-15T00:00:00+08:00').getTime();
function tick(){
  const now = Date.now();
  const diff = Math.max(0, target-now);
  const d=Math.floor(diff/86400000), h=Math.floor(diff%86400000/3600000), m=Math.floor(diff%3600000/60000), s=Math.floor(diff%60000/1000);
  $('#cd-d').textContent=String(d).padStart(3,'0');
  $('#cd-h').textContent=String(h).padStart(2,'0');
  $('#cd-m').textContent=String(m).padStart(2,'0');
  $('#cd-s').textContent=String(s).padStart(2,'0');
  $('#telemetry-countdown').textContent=`距 2027-03-15 还有 ${d} 天`;
  const dt=new Date();
  const w=['周日','周一','周二','周三','周四','周五','周六'][dt.getDay()];
  $('#telemetry-time').textContent=`${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')} ${String(dt.getHours()).padStart(2,'0')}:${String(dt.getMinutes()).padStart(2,'0')} · ${w} · 轨道正常`;
  $('#orbit-date').textContent=`${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')} · ${w}`;
}
tick(); setInterval(tick,1000);

/* ---------- reveal ---------- */
const io=new IntersectionObserver(es=>es.forEach(e=>{ if(e.isIntersecting) e.target.classList.add('in'); }),{threshold:0.12});
$$('.reveal').forEach(el=>io.observe(el));

/* ---------- heuristics ---------- */
const HEUR=[
  '先预测再动手','拿不准就问','AI 多轮校对','情绪上头不承诺','80% 就交','选让我变强的','现在就开始','先给人挑毛病','翻译话外音','保护独处专注','要么拍板要么听','装备先行','队友不给力自己扛',
];
const heurEl=$('#heuristics');
HEUR.forEach((h,i)=>{
  const s=document.createElement('span');
  s.textContent=`${String(i+1).padStart(2,'0')} ${h}`;
  if([2,4,9].includes(i)) s.className='hl';
  heurEl.appendChild(s);
});

/* ---------- checklist ---------- */
const TASKS=[
  {id:'read', title:'精读综述 p.47→62', note:'ML in Aero Shape Opt. · 手写费曼卡 1 张', tip:'今天先推最硬的 5 页'},
  {id:'guo', title:'Mr.GUO 白皮书分篇 5', note:'燃气轮机智能设计 · 713KB 第5章', tip:'把一节转成自己的话'},
  {id:'pod', title:'手搓 POD 重构 1 小时', note:'8192→2 模态 97.97% · WASM 想一想', tip:'均值+模态×系数'},
  {id:'run', title:'4×2km 周跑 · 今日 2km', note:'彭康操场 · 跑完回弹更快', tip:'跑完再捏风场，手感更软'},
  {id:'eng', title:'英语 40′ · 精读 + 听写', note:'六级 561→ 雅思在路上 · 每日 40′', tip:'读文献靠翻译，先读中文再对原文'},
  {id:'music', title:'梁博《日落大道》练唱 15′', note:'电子琴/吉他 · 宿舍哼唱 · SCZ 彩蛋', tip:'唱完给自己一个小惊喜'},
];
const listEl=$('#checklist');
const progEl=$('#prog'), progText=$('#prog-text'), kpiOrbit=$('#kpi-orbit'), kpiOrbitSub=$('#kpi-orbit-sub'), orbitTip=$('#orbit-tip');
let checks={};
try{ checks=JSON.parse(localStorage.getItem('scz-orbit-checks')||'{}'); }catch{}
const todayKey = new Date().toISOString().slice(0,10);
let todayChecks = checks[todayKey] || {};
function renderChecks(){
  listEl.innerHTML='';
  TASKS.forEach(t=>{
    const li=document.createElement('li');
    li.className='check-item'+(todayChecks[t.id] ? ' done':'');
    li.dataset.id=t.id;
    li.innerHTML=`<span class="check-box">${todayChecks[t.id]?'✓':''}</span><span class="check-text">${t.title}<small>${t.note}</small></span>`;
    li.addEventListener('click',()=>{
      todayChecks[t.id]=!todayChecks[t.id];
      checks[todayKey]=todayChecks;
      try{ localStorage.setItem('scz-orbit-checks', JSON.stringify(checks)); }catch{}
      renderChecks(); audio.click(); updateRisks();
    });
    listEl.appendChild(li);
  });
  const done= TASKS.filter(t=>todayChecks[t.id]).length;
  const pct= Math.round(done/TASKS.length*100);
  progEl.style.width=pct+'%';
  progText.textContent=`${done}/${TASKS.length}`;
  kpiOrbit.textContent=`${done}/${TASKS.length}`;
  kpiOrbitSub.textContent = done===0?'先做最硬的那一块': done<TASKS.length?'轨道校准中 · 已推进 '+pct+'%':'今日轨道闭环 · 去记一笔打脸吧';
  const tips=TASKS.filter(t=>!todayChecks[t.id]).map(t=>t.tip);
  orbitTip.textContent = tips[0] ? `下一步：${tips[0]}` : '今日 6 项已闭环 · 明天 6:50 再见';
}
renderChecks();

/* ---------- risks ---------- */
function updateRisks(){
  const done= TASKS.filter(t=>todayChecks[t.id]).length;
  const hour=new Date().getHours();
  const isEvening = hour>=21;
  const manyUndone = TASKS.length - done >=4;
  // 1情绪：若今日待做多且晚间 -> 高
  const r1 = isEvening && manyUndone;
  // 2完美：若已做一半却还在打磨风场间距滑得过于频繁 ->  we track slider moves
  // 3大局：若连续两天完成<2 ->  check yesterday
  let yesterdayDone=0;
  try{
    const y=new Date(Date.now()-86400000).toISOString().slice(0,10);
    const ychecks=checks[y]||{};
    yesterdayDone = TASKS.filter(t=>ychecks[t.id]).length;
  }catch{}
  const r3 = yesterdayDone<=2 && done<=2;
  // 4刷手机：若当前时间在 22:00-01:00 且今日进度<50% -> 警报
  const r4 = (hour>=22 || hour<=1) && done/TASKS.length <0.5;
  // 2完美主义：若 done>=3 但用户仍在反复调风场 ->  will be set by slider frequency
  setRisk('risk-1', r1);
  setRisk('risk-3', r3);
  setRisk('risk-4', r4);
  // guard advice
  let adv='按 13 条过一遍，再让 AI 多轮校对一遍，确认万无一失再执行。—— M3 AI 校准';
  if(r1) adv='检测到晚间积压：先做 1 项“最硬的”闭环，不扩大战场。—— 启发式 #5 / 风险 #1';
  else if(r4) adv='第 4 灯亮：放下手机 50 分钟，合上盖子去图书馆，回弹更快。—— 风险 #4';
  else if(r3) adv='连续两天轨道偏低：别盯局部细节，先把整体时间线拉直。—— 风险 #3 大局';
  else if(done===TASKS.length) adv='今日闭环完成，去“打脸账本”记一笔：错误比成功更深刻。—— M1';
  $('#guard-advice').textContent=adv;
}
function setRisk(id, on){
  const el=document.getElementById(id);
  el.className='risk '+(on?'on':'off');
}
updateRisks();
setInterval(updateRisks, 30000);

/* slider frequency for risk2 */
let sliderMoves=0, sliderTimer=null;
function bumpSliderMoves(){
  sliderMoves++;
  clearTimeout(sliderTimer);
  sliderTimer=setTimeout(()=>{ sliderMoves=0; setRisk('risk-2', false); }, 8000);
  if(sliderMoves>12){ setRisk('risk-2', true); }
}

/* ---------- ledger ---------- */
const histEl=$('#ledger-history');
function loadLedger(){
  let arr=[]; try{ arr=JSON.parse(localStorage.getItem('scz-orbit-ledger')||'[]'); }catch{}
  histEl.innerHTML='';
  if(arr.length===0){ histEl.innerHTML='<div class="mini" style="text-align:center;padding:8px">暂无记录 · 先写下今天的一个预测吧</div>'; return; }
  arr.slice().reverse().forEach(e=>{
    const d=document.createElement('div');
    d.className='ledger-entry';
    d.innerHTML=`<b>${e.date} · ${e.pred.slice(0,18)}</b><small style="float:right">${e.date}</small><p>预测：${e.pred}\n实验：${e.exp}\n打脸：${e.slap}\n重构：${e.recon}</p>`;
    histEl.appendChild(d);
  });
}
loadLedger();
$('#btn-save-ledger').addEventListener('click', ()=>{
  const pred=$('#f-pred').value.trim(), exp=$('#f-exp').value.trim(), slap=$('#f-slap').value.trim(), recon=$('#f-recon').value.trim();
  if(!pred || !exp){ audio.tone(300,0.12,'sine',0.08); alert('至少填“预测”和“实验”——可证伪才可打脸。'); return; }
  let arr=[]; try{ arr=JSON.parse(localStorage.getItem('scz-orbit-ledger')||'[]'); }catch{}
  arr.push({date:new Date().toLocaleDateString('zh-CN'), pred, exp, slap, recon});
  try{ localStorage.setItem('scz-orbit-ledger', JSON.stringify(arr)); }catch{}
  ['#f-pred','#f-exp','#f-slap','#f-recon'].forEach(s=>$(s).value='');
  loadLedger(); audio.success();
});

/* ---------- p read ---------- */
let pRead = Number(localStorage.getItem('scz-orbit-p')) || 47;
$('#p-read').textContent=pRead;
$('#p-read').addEventListener('click',()=>{
  pRead = Math.min(103, pRead+5);
  localStorage.setItem('scz-orbit-p', String(pRead));
  $('#p-read').textContent=pRead;
  todayChecks['read']=true; checks[todayKey]=todayChecks; try{localStorage.setItem('scz-orbit-checks',JSON.stringify(checks));}catch{} renderChecks();
});

/* ---------- modal ---------- */
const modal=$('#modal');
function openLetter(){ modal.classList.add('open'); modal.setAttribute('aria-hidden','false'); document.body.style.overflow='hidden'; audio.success(); }
function closeLetter(){ modal.classList.remove('open'); modal.setAttribute('aria-hidden','true'); document.body.style.overflow=''; }
$('#btn-open-letter').addEventListener('click', openLetter);
$('#btn-open-letter-2').addEventListener('click', openLetter);
$('#btn-close').addEventListener('click', closeLetter);
modal.addEventListener('click', e=>{ if(e.target===modal) closeLetter(); });
document.addEventListener('keydown', e=>{ if(e.key==='Escape' && modal.classList.contains('open')) closeLetter(); });
$('#btn-copy-letter').addEventListener('click', async()=>{
  const txt=document.querySelector('.letter-body').innerText;
  try{ await navigator.clipboard.writeText(txt); audio.success(); alert('已复制信件全文'); }catch{ alert(txt.slice(0,200)+'...'); }
});
$('#btn-start-orbit').addEventListener('click', ()=>{
  closeLetter();
  document.getElementById('farm-card').scrollIntoView({behavior:'smooth', block:'start'});
  setTimeout(()=>audio.tone(660,0.12,'sine',0.1), 300);
});
$('#btn-focus-farm').addEventListener('click', ()=> document.getElementById('farm-card').scrollIntoView({behavior:'smooth', block:'start'}));

/* ---------- farm soft physics ---------- */
const canvas=$('#farm'), fx=$('#fx'), fctx=fx.getContext('2d');
const ctx=canvas.getContext('2d');
let W=860,H=440, DPR=Math.min(2, window.devicePixelRatio||1);
function resizeCanvas(){
  const rect=canvas.getBoundingClientRect();
  W=Math.round(rect.width); H=Math.round(rect.height);
  [canvas,fx].forEach(c=>{
    c.width=Math.round(W*DPR); c.height=Math.round(H*DPR);
    c.style.width=W+'px'; c.style.height=H+'px';
    c.getContext('2d').setTransform(DPR,0,0,DPR,0,0);
  });
}
resizeCanvas();
window.addEventListener('resize', resizeCanvas);

// state
let yaws = [0,0,0]; // row1,2,3
let windSpeed=8, spacingD=5;
let mode='squish';
const hintMap={squish:'按住捏一捏，松手回弹，试试双指拉长它', stretch:'捏住任意一点往外拉，松手就会弹回来', tickle:'在肚子上轻轻来回挪动，听它咕叽笑', toss:'抓住往上甩一下，看看它怎么软软落地'};
$$('.tool').forEach(b=>b.addEventListener('click',()=>{
  $$('.tool').forEach(x=>x.classList.remove('active'));
  b.classList.add('active'); mode=b.dataset.mode;
  $('#stage-hint').textContent=hintMap[mode]; audio.click();
}));

$('#r1').addEventListener('input', e=>{ yaws[0]=Number(e.target.value); $('#v-r1').textContent=yaws[0]>0?`+${yaws[0]}°`:yaws[0]+'°'; updatePower(); bumpSliderMoves(); });
$('#r2').addEventListener('input', e=>{ yaws[1]=Number(e.target.value); $('#v-r2').textContent=yaws[1]>0?`+${yaws[1]}°`:yaws[1]+'°'; updatePower(); bumpSliderMoves(); });
$('#r3').addEventListener('input', e=>{ yaws[2]=Number(e.target.value); $('#v-r3').textContent=yaws[2]>0?`+${yaws[2]}°`:yaws[2]+'°'; updatePower(); bumpSliderMoves(); });
$('#r-wind').addEventListener('input', e=>{ windSpeed=Number(e.target.value); bumpSliderMoves(); updateEnv(); updatePower(); });
$('#r-D').addEventListener('input', e=>{ spacingD=Number(e.target.value); bumpSliderMoves(); updateEnv(); });
function updateEnv(){
  $('#v-env').textContent=`${windSpeed.toFixed(1)} m/s · ${spacingD.toFixed(1)}D`;
  $('#wind-dir').textContent=`270°`;
}

// power model: anchor table from cases_array.csv + independent
const anchor = {
  unified: { y:30, total:9299.05 },
  row2: { y:[30,30,0], total:9934.99 },
  indep: { y:[30,20,0], total:10041.46 },
  base:8095.15,
  // per yaw single array: cases_array.csv totals
  table:{
    '-30':9102.39,'-25':9061.13,'-20':8875.4,'-15':8646.65,'-10':8376.21,'-5':8150.26,'0':8095.15,'5':8255.09,'10':8547.62,'15':8844.04,'20':9098.82,'25':9272.89,'30':9299.05
  }
};
// Row powers for independent etc from json
const rowPowers={
  base: [1753.95*3, (436.44+436.85+437.0), (507.16+507.99+507.83)],
  unified: [1339.86*3, (1023.43+1050.19+1058.13),(708.31+723.16+716.27)],
  indep: [1339.86*3, (909.38+935.11+942.75),(1060.49+1087.76+1086.41)],
  row2: [1339.86*3, (766.27+790.73+797.98),(1171.26+1194.07+1195.11)]
};
function interpPower(y1,y2,y3){
  // If y1=y2=y3 => single table
  if(y1===y2 && y2===y3){
    return anchor.table[String(y1)] || 8095.15;
  }
  // If y1=30,y2=20,y3=0 -> indep exact
  if(y1===30 && y2===20 && y3===0) return 10041.46;
  if(y1===30 && y2===30 && y3===0) return 9934.99;
  if(y1===30 && y2===0 && y3===0) return 9299.05;
  // Otherwise approximate: weighted blend + yaw loss
  // Row1 loss cos^1.88
  const cos = d=> Math.pow(Math.cos(d*Math.PI/180),1.88);
  const baseRow1=1753.95*3, baseRow2=436.76*3, baseRow3=507.66*3; // approx
  // Simple model: Row1 = base*cos, Row2 recovery depends on y1 deflection, Row3 on y1+y2
  // Use empirical: for y1=30, Row2 gain ~2.34x, Row3 gain ~1.41 (unified) or 2.13 (row2-30) or 2.13 (indep)
  // Interpolate linearly between anchors for intermediate yaws
  // Approximate total by blending between base and anchor curves
  let t1 = Math.abs(y1)/30, t2=Math.abs(y2)/30, t3=Math.abs(y3)/30;
  // Row1 linear between base and unified row1
  let r1 = baseRow1 * (0.765 + 0.235*(1 - t1*0.235)) ; // but better cos
  r1 = baseRow1 * cos(y1);
  // Row2: interpolate between base row2 and unified row2 based on y1, and between unified and indep based on y2
  let r2_base = baseRow2, r2_unified_for_y1 = baseRow2 + (rowPowers.unified[1]-baseRow2)*(t1);
  let r2 = r2_unified_for_y1 * ( y2===0 ? 1 : (0.88 + 0.12*t2) ); // small tweak for y2
  // For y1=30,y2=20 case, r2 should be ~2787 vs unified 3131 -> ratio 0.89
  // Row3 similarly
  let r3_unified = baseRow3 + (rowPowers.unified[2]-baseRow3)*t1;
  let r3_row2 = baseRow3 + (rowPowers.row2[2]-baseRow3)* (t1*0.5 + t2*0.5);
  let r3_indep = rowPowers.indep[2];
  let r3 = r3_unified;
  if(y1===30 && y2>=15) r3 = r3_unified + (r3_row2 - r3_unified)* ( (y2-0)/30 );
  if(y1===30 && y2===20 && y3===0) r3 = r3_indep;
  // If general, blend
  if(!(y1===30 && y2===20 && y3===0) && !(y1===30 && y2===30 && y3===0)){
    // fallback interpolate total via table + offset
    let unifiedTotal = anchor.table[String(y1)] || 8095;
    let extra = (y2>0 ? y2*8 : 0) + (y3>0 ? y3*2 : 0); // small bonus for downstream yaw
    // but downstream yaw alone without upstream is not beneficial, so penalize if y1 small
    if(Math.abs(y1)<10) extra *=0.2;
    let tot = unifiedTotal + extra;
    // clamp to plausible max 10060
    tot = Math.min(10060, Math.max(8095, tot));
    // adjust for independent optimum
    if(y1===30 && y2===20) tot = 10041.46 - Math.abs(y3)*2;
    return tot;
  }
  return r1+r2+r3;
}
function computePowers(){
  const total = yaws[0]===30 && yaws[1]===20 && yaws[2]===0 ? 10041.46 : (yaws[0]===30 && yaws[1]===30 && yaws[2]===0 ? 9934.99 : interpPower(yaws[0],yaws[1],yaws[2]));
  // Row estimates for display
  const cos = d=> Math.pow(Math.cos(d*Math.PI/180),1.88);
  const baseRow1=1753.95*3, baseRow2=1310.29, baseRow3=1522.98;
  let r1 = baseRow1 * cos(yaws[0]);
  // distribute deficit/gain empirically: if total known, derive r1,r2,r3 proportionally to anchors
  let r1e, r2e, r3e;
  if(yaws[0]===0 && yaws[1]===0 && yaws[2]===0){ r1e=baseRow1; r2e=baseRow2; r3e=baseRow3; }
  else if(yaws[0]===30 && yaws[1]===20 && yaws[2]===0){ r1e=4019.58; r2e=2787.24; r3e=3234.66; }
  else if(yaws[0]===30 && yaws[1]===30 && yaws[2]===0){ r1e=4019.58; r2e=2355; r3e=3560.44; }
  else if(yaws[0]===30 && yaws[1]===0 && yaws[2]===0){ r1e=4019.58; r2e=3131.75; r3e=2147.74; }
  else {
    // approximate per-row: r1 as above, r2 gets recovery proportional to y1, r3 gets remainder
    r1e=r1;
    const t1=Math.abs(yaws[0])/30;
    r2e=baseRow2 + (3131.75-baseRow2)*t1 * (0.9 + 0.1*Math.abs(yaws[1])/30);
    r3e= total - r1e - r2e;
  }
  return {total, r1:r1e, r2:r2e, r3:r3e};
}
function updatePower(){
  const {total,r1,r3}=computePowers();
  const gain=((total-8095.15)/8095.15*100);
  $('#s-total').textContent=Math.round(total).toString();
  $('#s-gain').textContent=(gain>=0?'+':'')+gain.toFixed(2)+'%';
  $('#s-r1').textContent=Math.round(r1).toString();
  $('#s-r3').textContent=Math.round(r3).toString();
  $('#kpi-total').innerHTML=Math.round(total)+' <small>kW</small>';
  $('#kpi-gain').textContent=(gain>=0?'+':'')+gain.toFixed(2)+'% · Row1 '+yaws[0]+'° Row2 '+yaws[1]+'° Row3 '+yaws[2]+'°';
  // trust domain
  const out = yaws.some(y=>Math.abs(y)>30) || windSpeed<6 || windSpeed>12;
  const sGainEl=$('#s-gain');
  if(out || spacingD<5 || spacingD>7){ sGainEl.style.color='#ef4444'; } else { sGainEl.style.color=''; }
}

updatePower(); updateEnv();

/* ---------- soft farm rendering ---------- */
// 9 turbines positions: 3 rows x 3 cols, spacing = D*126m but mapped to canvas
const cols=3, rows=3;
let turbines=[]; // {x,y,tx,ty,yaw,sx,sy,vx,vy}
let particles=[]; // wind particles
let wobblePhase=0;
let isDragging=false, dragId=null, lastMouse={x:0,y:0}, holdTimer=null, isHolding=false;
let stageWobble={x:0,y:0, sx:1, sy:1, rot:0, vx:0, vy:0, vsx:0, vsy:0, vrot:0};

function initTurbines(){
  turbines=[];
  const marginX=80, marginY=60;
  const usableW= W - marginX*2, usableH= H - marginY*2;
  const colStep = usableW/(cols-1);
  const rowStep = usableH/(rows-1);
  for(let r=0;r<rows;r++){
    for(let c=0;c<cols;c++){
      const x= marginX + c*colStep;
      const y= marginY + r*rowStep; // r0 top (upstream)
      turbines.push({x,y, tx:x, ty:y, yaw:0, sx:1, sy:1, vx:0, vy:0, vsx:0, vsy:0, r:r, c:c});
    }
  }
}
initTurbines();
window.addEventListener('resize', ()=>{ initTurbines(); });

function lerp(a,b,t){ return a+(b-a)*t; }

// particles for wind
function spawnParticles(){
  if(particles.length>220) return;
  const y = 30 + Math.random()*(H-60);
  particles.push({x:-10, y, vx: 1.2 + Math.random()*0.8 + windSpeed*0.08, vy:(Math.random()-0.5)*0.3, life:1, rot:Math.random()*360});
}
function updateParticles(dt){
  // spawn rate
  for(let i=0;i<3;i++) spawnParticles();
  particles.forEach(p=>{
    p.x+=p.vx*dt*60;
    // deflect by turbines' yaw: if near turbine downstream
    turbines.forEach(t=>{
      const dx=p.x - t.x, dy=p.y - t.y;
      if(dx>0 && dx< 180 && Math.abs(dy)<34){
        const yawRad = t.yaw * Math.PI/180;
        const deflection = Math.sin(yawRad)* 28 * Math.exp(-dx/120);
        p.y += deflection*0.04;
        p.vy += Math.sin(yawRad)*0.02;
        p.vx *= 0.998;
      }
    });
    p.y+=p.vy;
    p.life -=0.0015;
  });
  particles = particles.filter(p=>p.x < W+20 && p.y>0 && p.y<H && p.life>0);
}

// spring update
function updateTurbines(dt){
  const spring=0.18, damp=0.82, scaleSpring=0.22, scaleDamp=0.78;
  // stage wobble spring
  stageWobble.vx += (0-stageWobble.x)*0.08;
  stageWobble.vy += (0-stageWobble.y)*0.08;
  stageWobble.vsx += (1-stageWobble.sx)*0.10;
  stageWobble.vsy += (1-stageWobble.sy)*0.10;
  stageWobble.vrot += (0-stageWobble.rot)*0.08;
  stageWobble.vx*=0.88; stageWobble.vy*=0.88; stageWobble.vsx*=0.80; stageWobble.vsy*=0.80; stageWobble.vrot*=0.88;
  stageWobble.x+=stageWobble.vx; stageWobble.y+=stageWobble.vy; stageWobble.sx+=stageWobble.vsx; stageWobble.sy+=stageWobble.vsy; stageWobble.rot+=stageWobble.vrot;

  // spacing stretch affects target x spacing
  const marginX=80, marginY=60;
  const usableW= W - marginX*2, usableH= H - marginY*2;
  const colStep = usableW/(cols-1) * (spacingD/5);
  const rowStep = usableH/(rows-1);
  // center to keep centered: compute offset
  const totalW = colStep*(cols-1);
  const offsetX = (W - totalW)/2;
  turbines.forEach(t=>{
    const wantX = offsetX + t.c*colStep;
    const wantY = marginY + t.r*rowStep;
    t.tx = wantX; t.ty = wantY;
    // map row yaw
    t.yaw = yaws[t.r];
    // spring
    t.vx += (t.tx - t.x)*spring;
    t.vy += (t.ty - t.y)*spring;
    t.vx*=damp; t.vy*=damp;
    t.x+=t.vx*dt*60*0.16;
    t.y+=t.vy*dt*60*0.16;
    // scale spring back
    t.vsx += (1 - t.sx)*scaleSpring;
    t.vsy += (1 - t.sy)*scaleSpring;
    t.vsx*=scaleDamp; t.vsy*=scaleDamp;
    t.sx+=t.vsx; t.sy+=t.vsy;
    // small idle wobble
    if(!isDragging && !isHolding){
      t.sx += Math.sin(wobblePhase + t.r*0.9 + t.c*0.6)*0.002;
      t.sy += Math.cos(wobblePhase*0.9 + t.r*0.7)*0.002;
    }
  });
}

function draw(){
  ctx.clearRect(0,0,W,H);
  // background grid + creamy
  ctx.fillStyle='#fcfdfd';
  ctx.fillRect(0,0,W,H);
  // subtle grid lines 48px
  ctx.strokeStyle='rgba(30,41,59,0.05)';
  ctx.lineWidth=1;
  for(let x=0;x<W;x+=48){ ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
  for(let y=0;y<H;y+=48){ ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }
  // wind direction arrow
  ctx.fillStyle='rgba(95,214,255,0.12)';
  ctx.fillRect(0,0,W,1.5);
  // draw wake ribbons behind each turbine (from upstream to downstream)
  turbines.forEach(t=>{
    if(t.r===2) return; // last row no downstream wake needed? but still draw
    const yawRad = t.yaw*Math.PI/180;
    const len = 140 + windSpeed*6; // wind speed affects wake length
    const deflection = Math.sin(yawRad)* 42;
    const wTop= 18, wBottom= 44;
    const x1=t.x, y1=t.y;
    const x2=t.x+len, y2=t.y+deflection;
    // gradient from forest low to ice high? Use BuGn reversed: low = forest, high = light mint
    // wake = low speed = forest green translucent
    const grad=ctx.createLinearGradient(x1,y1,x2,y2);
    grad.addColorStop(0,'rgba(45,117,105,0.22)');
    grad.addColorStop(0.5,'rgba(45,117,105,0.14)');
    grad.addColorStop(1,'rgba(95,214,255,0.06)');
    ctx.fillStyle=grad;
    ctx.beginPath();
    ctx.moveTo(x1, y1 - wTop/2 * t.sy);
    ctx.lineTo(x2, y2 - wBottom/2 * t.sy);
    ctx.lineTo(x2, y2 + wBottom/2 * t.sy);
    ctx.lineTo(x1, y1 + wTop/2 * t.sy);
    ctx.closePath();
    ctx.fill();
    // centerline
    ctx.strokeStyle='rgba(45,117,105,0.18)';
    ctx.setLineDash([6,6]);
    ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
    ctx.setLineDash([]);
    // CVP small vortices at wake edge for tickle mode hint
    if(mode==='tickle'){
      ctx.fillStyle='rgba(95,214,255,0.18)';
      ctx.beginPath(); ctx.arc(x2-10, y2 - wBottom*0.36, 4,0,Math.PI*2); ctx.fill();
      ctx.fillStyle='rgba(201,74,44,0.16)';
      ctx.beginPath(); ctx.arc(x2-10, y2 + wBottom*0.36, 4,0,Math.PI*2); ctx.fill();
    }
  });
  // particles
  fctx.clearRect(0,0,W,H);
  // draw particles on fx layer? Actually draw on ctx for simplicity, but we have fctx separate
  // we'll draw particles on ctx as small dots with motion blur
  ctx.fillStyle='rgba(95,214,255,0.9)';
  particles.forEach(p=>{
    ctx.beginPath();
    ctx.arc(p.x, p.y, 1.4, 0, Math.PI*2); ctx.fill();
    // trail
    ctx.fillStyle='rgba(95,214,255,0.22)';
    ctx.fillRect(p.x-8, p.y-0.5, 8,1);
    ctx.fillStyle='rgba(95,214,255,0.9)';
  });

  // draw turbines
  ctx.save();
  // apply stage wobble at center
  ctx.translate(W/2, H/2);
  ctx.rotate(stageWobble.rot*0.008);
  ctx.scale(stageWobble.sx, stageWobble.sy);
  ctx.translate(-W/2 + stageWobble.x, -H/2 + stageWobble.y);
  turbines.forEach(t=>{
    ctx.save();
    ctx.translate(t.x, t.y);
    ctx.scale(t.sx, t.sy);
    ctx.rotate(t.yaw * Math.PI/180 * 0.18); // nacelle subtle rotation, not full

    // shadow
    ctx.fillStyle='rgba(30,41,59,0.06)';
    ctx.beginPath(); ctx.ellipse(0, 18, 18,6,0,0,Math.PI*2); ctx.fill();
    // tower
    ctx.fillStyle='#2d3a4a';
    ctx.fillRect(-2, -2, 4, 18);
    // nacelle
    ctx.fillStyle='#1e293b';
    ctx.beginPath(); ctx.roundRect(-14, -8, 28, 12, 6); ctx.fill();
    // hub
    ctx.fillStyle='#0f172a';
    ctx.beginPath(); ctx.arc(0, -2, 5,0,Math.PI*2); ctx.fill();
    ctx.fillStyle='#5fd6ff';
    ctx.beginPath(); ctx.arc(0,-2,2,0,Math.PI*2); ctx.fill();
    // blades (3)
    const spin = wobblePhase*2.2 + t.r*0.7 + t.c*0.4; // continuous rotation
    for(let i=0;i<3;i++){
      const a = spin + i*120*Math.PI/180;
      ctx.save(); ctx.rotate(a);
      ctx.fillStyle='rgba(255,255,255,0.96)';
      ctx.strokeStyle='rgba(30,41,59,0.14)';
      ctx.lineWidth=1;
      ctx.beginPath();
      // blade shape: rounded rect
      ctx.roundRect(2, -2, 18, 4, 2); ctx.fill(); ctx.stroke();
      ctx.restore();
    }
    // row label small
    ctx.fillStyle='rgba(100,116,139,0.9)';
    ctx.font='600 8px DM Mono, monospace';
    ctx.textAlign='center';
    ctx.fillText(`R${t.r+1}·C${t.c+1}`,0,30);
    ctx.restore();
  });
  ctx.restore();

  // spacing annotation
  ctx.fillStyle='rgba(100,116,139,0.7)';
  ctx.font='600 10px DM Mono, monospace';
  ctx.fillText(`D = ${spacingD.toFixed(1)}×126m  ·  9 涡轮 · 软体间距可拉`, W-12, H-10);
  ctx.textAlign='right';
}

let last=performance.now();
function loop(now){
  const dt=Math.min(0.05, (now-last)/1000); last=now;
  wobblePhase+=dt*1.2;
  updateTurbines(dt);
  updateParticles(dt);
  draw();
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

/* ---------- interactions ---------- */
function pos(e){
  const rect=canvas.getBoundingClientRect();
  const src = e.touches? e.touches[0] : e;
  return {x:(src.clientX-rect.left), y:(src.clientY-rect.top)};
}
function nearestTurbine(x,y){
  let best=null, bd=1e9;
  turbines.forEach(t=>{ const d=Math.hypot(t.x-x,t.y-y); if(d<bd){ bd=d; best=t; }});
  return bd<52? best:null;
}
canvas.addEventListener('pointerdown', e=>{
  canvas.setPointerCapture(e.pointerId);
  isDragging=true;
  const p=pos(e);
  lastMouse=p;
  const near=nearestTurbine(p.x,p.y);
  if(mode==='squish'){
    // squish nearest or all if none
    if(near){
      near.sx=0.82; near.sy=0.74; near.vsx=-0.08; near.vsy=-0.08;
    } else {
      turbines.forEach(t=>{ t.sx=0.88; t.sy=0.90; });
    }
    audio.squish(); $('#speech').textContent='咕叽，被你捏扁了一点';
    holdTimer=setTimeout(()=>{
      isHolding=true;
      turbines.forEach(t=>{ t.sx=0.72; t.sy=0.68; });
      $('#speech').textContent='正在融化…再等一下，涡轮在打盹';
    }, 2500);
  } else if(mode==='stretch'){
    // start stretching spacing
  } else if(mode==='tickle'){
    audio.tickle();
  } else if(mode==='toss'){
    audio.toss();
  }
  updateRisks();
});
canvas.addEventListener('pointermove', e=>{
  if(!isDragging) {
    // hover wobble hint
    return;
  }
  const p=pos(e);
  const dx=p.x-lastMouse.x, dy=p.y-lastMouse.y;
  if(mode==='stretch'){
    // drag horizontally changes spacing
    spacingD = Math.max(5, Math.min(7, spacingD + dx*0.02));
    $('#r-D').value=spacingD; updateEnv();
    // vertical drag also nudges stage
    stageWobble.x += dx*0.14; stageWobble.y += dy*0.08;
  } else if(mode==='tickle'){
    // create turbulence ripples
    for(let i=0;i<2;i++) particles.push({x:p.x, y:p.y+(Math.random()-0.5)*18, vx:1.5+Math.random()*1.2, vy:(Math.random()-0.5)*1.4, life:1});
    stageWobble.x += (Math.random()-0.5)*1.2;
    if(Math.random()<0.12) audio.tickle();
  } else if(mode==='squish'){
    // drag squishes nearest
    const near=nearestTurbine(p.x,p.y);
    if(near){ near.sx = Math.max(0.72, Math.min(1.08, near.sx - dx*0.004)); near.sy = Math.max(0.68, Math.min(1.08, near.sy - dy*0.004)); }
  } else if(mode==='toss'){
    stageWobble.vx += dx*0.18; stageWobble.vy += dy*0.18;
    stageWobble.vrot += dx*0.04;
  }
  lastMouse=p;
});
canvas.addEventListener('pointerup', e=>{
  isDragging=false; isHolding=false;
  clearTimeout(holdTimer);
  canvas.releasePointerCapture(e.pointerId);
  // spring back
  turbines.forEach(t=>{ t.sx=1; t.sy=1; });
  if(mode==='toss'){
    // fling stage
    const p=pos(e);
    const vx=(p.x-lastMouse.x), vy=(p.y-lastMouse.y);
    stageWobble.vx+= vx*0.3; stageWobble.vy+= vy*0.3; stageWobble.vrot+= vx*0.06;
    audio.toss();
    $('#speech').textContent='接住我，我把信任都给你了';
  } else if(mode==='squish'){
    $('#speech').textContent='慢慢回弹，回到了自己的轨道';
    audio.tone(520,0.08,'sine',0.07);
  }
  setTimeout(()=>{ $('#speech').textContent='双击有惊喜 · 长按会融化'; }, 1800);
});
canvas.addEventListener('pointercancel', ()=>{ isDragging=false; clearTimeout(holdTimer); });

// double click surprise
let lastTap=0;
canvas.addEventListener('click', ()=>{
  const now=Date.now();
  if(now-lastTap<300){
    // double
    audio.success();
    showToast('✦ 今日收藏卡已生成 · 9 颗涡轮都在对你笑');
    // generate card
    generateCard();
    // show brother easter
    setTimeout(()=>showBrother(), 420);
  }
  lastTap=now;
});
function showToast(msg){
  const s=$('#speech');
  s.textContent=msg; s.style.background='#1e293b'; s.style.color='#fff'; s.style.borderColor='#1e293b';
  setTimeout(()=>{ s.style.background='#fff'; s.style.color='#1e293b'; s.style.borderColor='rgba(30,41,59,0.11)'; s.textContent='戳一下认识 9 颗涡轮，双击有隐藏彩蛋'; }, 2200);
}
function generateCard(){
  // create canvas card snapshot
  const c=document.createElement('canvas'); c.width=720; c.height=420; const x=c.getContext('2d');
  x.fillStyle='#f7f3ec'; x.fillRect(0,0,720,420);
  x.strokeStyle='rgba(30,41,59,0.08)'; for(let i=0;i<720;i+=48){ x.beginPath(); x.moveTo(i,0); x.lineTo(i,420); x.stroke(); }
  x.fillStyle='#1e293b'; x.font='800 22px Songti SC, serif'; x.fillText('今日收藏卡 · SCZ Pocket Orbit', 28, 44);
  x.fillStyle='#64748b'; x.font='600 11px DM Mono, monospace'; x.fillText(`${new Date().toLocaleDateString('zh-CN')} · 9 涡轮软体阵列 · ${Math.round(computePowers().total)} kW · +${((computePowers().total-8095.15)/8095.15*100).toFixed(2)}%`, 28, 66);
  x.fillStyle='#ffffff'; x.strokeStyle='rgba(30,41,59,0.12)'; x.lineWidth=1;
  // draw mini farm
  const sx=28, sy=96, w=320, h=200;
  x.fillStyle='#ffffff'; x.strokeStyle='rgba(30,41,59,0.11)'; x.beginPath(); x.roundRect(sx,sy,w,h,12); x.fill(); x.stroke();
  // turbines dots
  for(let r=0;r<3;r++) for(let c2=0;c2<3;c2++){
    const tx=sx+60+c2*100, ty=sy+40+r*60;
    x.fillStyle='#1e293b'; x.beginPath(); x.arc(tx,ty,7,0,Math.PI*2); x.fill();
    x.fillStyle='#5fd6ff'; x.beginPath(); x.arc(tx,ty,2.5,0,Math.PI*2); x.fill();
    // wake tiny
    x.fillStyle='rgba(45,117,105,0.18)'; x.fillRect(tx+8, ty-2, 36,4);
  }
  x.fillStyle='#1e293b'; x.font='700 12px Manrope, sans-serif'; x.fillText('把今天，捏软一点。', 400, 140);
  x.fillStyle='#64748b'; x.font='600 11px DM Mono, monospace'; x.fillText('不把风场当数据，把风场当手感。', 400, 162);
  x.fillText('— 承泽轨道站 · 07:00 已就位', 400, 182);
  const url=c.toDataURL('image/png');
  const w2=window.open('');
  if(w2){ w2.document.write(`<title>收藏卡</title><img src="${url}" style="max-width:100%">`); }
}
function showBrother(){
  $('#speech').textContent='🐱 弟弟的小猫跳伞游戏已藏在控制台 · 输入 SCZ 试试';
}

// keyboard SCZ
let keys='';
window.addEventListener('keydown', e=>{
  keys=(keys+e.key).slice(-12);
  if(keys.toLowerCase().includes('scz')){
    audio.tone(330,0.18,'sine',0.09); setTimeout(()=>audio.tone(440,0.18,'sine',0.09),180); setTimeout(()=>audio.tone(550,0.28,'sine',0.08),380);
    showToast('♫ 梁博《日落大道》— “出现又离开” 送给你');
    keys='';
  }
});

// initial speech
setTimeout(()=>{ $('#speech').textContent='试试把 Row1 拉到 +30°，Row2 到 +20°，看 10041 的那一跳'; }, 2200);

