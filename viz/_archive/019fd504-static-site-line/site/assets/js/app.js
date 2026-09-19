(function(){
  const W = window.WIND_DATA;
  const S = window.SURROGATE;
  const C = window.CHARTS;
  const bestIdx = a=>{let i=0;a.forEach((v,k)=>{if(v>a[i])i=k;});return i;};

  // ---- 01 功率-偏航曲线 ----
  const powerU=document.getElementById("powerU");
  let curU = W.multi.wind_speeds[1]; // 默认 8 m/s
  W.multi.wind_speeds.forEach(u=>{
    const b=document.createElement("button");
    b.className="btn"+(u===curU?" active":"");b.textContent=u+" m/s";
    b.onclick=()=>{curU=u;[...powerU.children].forEach(x=>x.classList.remove("active"));b.classList.add("active");renderPower();};
    powerU.appendChild(b);
  });
  function renderPower(){
    const m=W.multi,i=m.wind_speeds.indexOf(curU),xs=m.yaw_angles;
    C.lineChart(document.getElementById("powerChart"),{
      xs, series:[
        {name:"P1",color:"#4a9eff",data:m.p1[i]},
        {name:"P2",color:"#27ae60",data:m.p2[i]},
        {name:"Ptot",color:"#f5a623",data:m.ptot[i]},
      ],
      marks:[{x:xs[bestIdx(m.ptot[i])],color:"#e74c3c",label:"最优"}]
    });
    const bi=bestIdx(m.ptot[i]),b0=m.ptot[i][xs.indexOf(0)];
    document.getElementById("powerNote").innerHTML=
      `风速 ${curU} m/s：最优偏航角 ≈ <b>${xs[bi]}°</b>，全场功率 ≈ <b>${Math.round(m.ptot[i][bi])} kW</b>`+
      `（基准 0° 为 ${Math.round(b0)} kW，增益 ${m.gain[i][bi].toFixed(1)}%）`;
  }
  renderPower();

  // ---- 02 偏航寻优 ----
  const optU=document.getElementById("optU"),optT=document.getElementById("optT");
  function renderOpt(){
    const U=+optU.value||8,T=+optT.value||0;
    const r=S.find_yaw_for_target(T,U);
    const maxv=Math.max(r.ptot,r.base)*1.15||1;
    C.gauge(document.getElementById("optGauge"),{value:r.ptot,min:0,max:maxv,target:T,label:"实际总功率",unit:"kW",color:"#27ae60"});
    document.getElementById("oS-yaw").textContent=r.yaw+"°";
    document.getElementById("oS-pow").textContent=Math.round(r.ptot);
    document.getElementById("oS-err").textContent=(r.error>=0?"+":"")+r.error.toFixed(1)+"%";
    document.getElementById("oS-base").textContent=Math.round(r.base);
    document.getElementById("optNote").innerHTML=
      `风速 ${U} m/s：基准(0°)≈${Math.round(r.base)} kW，推荐偏航 <b>${r.yaw}°</b> 后≈<b>${Math.round(r.ptot)} kW</b>。`;
  }
  optU.oninput=renderOpt;optT.oninput=renderOpt;renderOpt();

  // ---- 03 阵列优化 ----
  function renderArray(){
    const a=W.array_opt;
    C.barChart(document.getElementById("arrayBar"),{
      labels:["基准(0°)","统一偏航","独立偏航"],
      values:[a.power_none,a.power_unified,a.power_independent],
      colors:["#9fb3d4","#4a9eff","#27ae60"]});
    document.getElementById("arrayNote").innerHTML=
      `3×3 阵列：统一偏航 +<b>${a.gain_unified_pct.toFixed(1)}%</b>，独立偏航 +<b class="good">${a.gain_independent_pct.toFixed(1)}%</b>。`;
    C.arrayLayout(document.getElementById("arrayLayout"),{yaws:a.greedy_yaws,powers:a.turbine_powers_independent});
  }
  renderArray();

  // ---- 04 风玫瑰 ----
  function renderRose(){
    const map={};W.windrose_opt.forEach(r=>{(map[r.wind_direction]=map[r.wind_direction]||[]).push(r.gain_pct);});
    const angles=Object.keys(map).map(Number).sort((a,b)=>a-b);
    const values=angles.map(d=>{const a=map[d];return a.reduce((x,y)=>x+y,0)/a.length;});
    C.polarRose(document.getElementById("roseChart"),{angles,values});
    const maxG=Math.max(...values),maxD=angles[values.indexOf(maxG)];
    document.getElementById("roseNote").innerHTML=
      `各风向平均增益：最高约 <b class="good">${maxG.toFixed(1)}%</b>（风向 ${maxD}°）。`;
  }
  renderRose();
})();
