// 零依赖 SVG 图表模块（线图 / 柱图 / 极坐标风玫瑰 / 半圆仪表 / 阵列布局）
(function(){
  const NS="http://www.w3.org/2000/svg";
  function el(tag,attrs){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);return e;}
  function svg(W,H){return el("svg",{viewBox:`0 0 ${W} ${H}`,preserveAspectRatio:"xMidYMid meet"});}
  function polar(cx,cy,r,deg){const a=deg*Math.PI/180;return [cx+r*Math.cos(a), cy-r*Math.sin(a)];}
  function arcPath(cx,cy,r,a0,a1){const [x0,y0]=polar(cx,cy,r,a0),[x1,y1]=polar(cx,cy,r,a1);
    const large=Math.abs(a1-a0)>180?1:0,sweep=a1<a0?1:0;
    return `M${x0} ${y0} A ${r} ${r} 0 ${large} ${sweep} ${x1} ${y1}`;}

  function lineChart(c,opt){
    const W=720,H=380,p={l:54,r:18,t:16,b:42};
    const s=svg(W,H);c.innerHTML="";c.appendChild(s);
    const xs=opt.xs,all=opt.series.flatMap(x=>x.data);
    let ymin=Math.min(...all),ymax=Math.max(...all),yr=(ymax-ymin)||1;
    ymin-=yr*0.08;ymax+=yr*0.08;
    const X=x=>p.l+(x-xs[0])/((xs[xs.length-1]-xs[0])||1)*(W-p.l-p.r);
    const Y=v=>H-p.b-(v-ymin)/((ymax-ymin)||1)*(H-p.t-p.b);
    for(let t=0;t<=5;t++){const v=ymin+(ymax-ymin)*t/5,yy=Y(v);
      s.appendChild(el("line",{class:"grid-line",x1:p.l,x2:W-p.r,y1:yy,y2:yy}));
      const tx=el("text",{class:"tick",x:p.l-8,y:yy+3,"text-anchor":"end"});tx.textContent=Math.round(v);s.appendChild(tx);}
    const step=Math.ceil(xs.length/8);
    for(let i=0;i<xs.length;i+=step){const xx=X(xs[i]);
      const tx=el("text",{class:"tick",x:xx,y:H-p.b+16,"text-anchor":"middle"});tx.textContent=xs[i];s.appendChild(tx);}
    s.appendChild(el("line",{class:"axis",x1:p.l,y1:H-p.b,x2:W-p.r,y2:H-p.b}));
    s.appendChild(el("line",{class:"axis",x1:p.l,y1:p.t,x2:p.l,y2:H-p.b}));
    opt.series.forEach(se=>{let d="";se.data.forEach((v,i)=>{d+=(i?"L":"M")+X(xs[i])+" "+Y(v)+" ";});
      s.appendChild(el("path",{d,fill:"none",stroke:se.color,"stroke-width":2.4,"stroke-linejoin":"round","stroke-linecap":"round"}));
      se.data.forEach((v,i)=>s.appendChild(el("circle",{cx:X(xs[i]),cy:Y(v),r:2.6,fill:se.color})));});
    (opt.marks||[]).forEach(m=>{const xx=X(m.x);
      s.appendChild(el("line",{x1:xx,y1:p.t,x2:xx,y2:H-p.b,stroke:m.color,"stroke-width":1.6,"stroke-dasharray":"5 4"}));
      const tx=el("text",{class:"tick",x:xx,y:p.t+12,"text-anchor":"middle",fill:m.color});tx.textContent=m.label;s.appendChild(tx);});
  }

  function barChart(c,opt){
    const W=520,H=320,p={l:54,r:14,t:20,b:54};
    const s=svg(W,H);c.innerHTML="";c.appendChild(s);
    const vals=opt.values,vmax=Math.max(...vals)*1.12||1;
    const bw=(W-p.l-p.r)/vals.length*0.55;
    const X=i=>p.l+(i+0.5)*(W-p.l-p.r)/vals.length;
    const Y=v=>H-p.b-v/vmax*(H-p.t-p.b);
    for(let t=0;t<=4;t++){const v=vmax*t/4,yy=Y(v);
      s.appendChild(el("line",{class:"grid-line",x1:p.l,x2:W-p.r,y1:yy,y2:yy}));
      const tx=el("text",{class:"tick",x:p.l-8,y:yy+3,"text-anchor":"end"});tx.textContent=Math.round(v);s.appendChild(tx);}
    vals.forEach((v,i)=>{const x=X(i)-bw/2,yy=Y(v);
      s.appendChild(el("rect",{x,y:yy,width:bw,height:(H-p.b-yy),rx:6,fill:opt.colors?opt.colors[i]:"#4a9eff"}));
      const tx=el("text",{class:"tick",x:X(i),y:yy-6,"text-anchor":"middle",fill:"#e8edf5"});tx.textContent=Math.round(v);s.appendChild(tx);
      const lx=el("text",{class:"tick",x:X(i),y:H-p.b+18,"text-anchor":"middle"});lx.textContent=opt.labels[i];s.appendChild(lx);});
    s.appendChild(el("line",{class:"axis",x1:p.l,y1:H-p.b,x2:W-p.r,y2:H-p.b}));
  }

  function polarRose(c,opt){
    const W=520,H=420,cx=W/2,cy=H/2+8,R=158;
    const s=svg(W,H);c.innerHTML="";c.appendChild(s);
    const angs=opt.angles,vals=opt.values,vmax=Math.max(...vals)*1.12||1;
    for(let t=1;t<=4;t++){const rr=R*t/4;
      s.appendChild(el("circle",{cx,cy,r:rr,class:"grid-line",fill:"none"}));
      const tx=el("text",{class:"tick",x:cx+4,y:cy-rr+3});tx.textContent=Math.round(vmax*t/4)+"%";s.appendChild(tx);}
    const pts=angs.map((a,i)=>{const rad=(a-90)*Math.PI/180,rr=R*vals[i]/vmax;return [cx+rr*Math.cos(rad),cy+rr*Math.sin(rad)];});
    let d="M"+pts[0][0]+" "+pts[0][1];for(let i=1;i<pts.length;i++)d+="L"+pts[i][0]+" "+pts[i][1];d+="Z";
    s.appendChild(el("path",{d,fill:"rgba(74,158,255,.28)",stroke:"#4a9eff","stroke-width":1.8}));
    angs.forEach((a,i)=>{if(a%90===0){const rad=(a-90)*Math.PI/180,rr=R+14;
      const tx=el("text",{class:"tick",x:cx+rr*Math.cos(rad),y:cy+rr*Math.sin(rad)+3,"text-anchor":"middle"});tx.textContent=a+"°";s.appendChild(tx);}});
  }

  function gauge(c,opt){
    const W=360,H=200,cx=W/2,cy=H-30,r=130;
    const s=svg(W,H);c.innerHTML="";c.appendChild(s);
    const {min,max,value,target,color}=opt;
    const f=Math.max(0,Math.min(1,(value-min)/((max-min)||1)));
    const fT=Math.max(0,Math.min(1,(target-min)/((max-min)||1)));
    const ang=v=>180-v*180;
    s.appendChild(el("path",{d:arcPath(cx,cy,r,180,0),fill:"none",stroke:"rgba(255,255,255,.12)","stroke-width":16,"stroke-linecap":"round"}));
    s.appendChild(el("path",{d:arcPath(cx,cy,r,180,ang(f)),fill:"none",stroke:color,"stroke-width":16,"stroke-linecap":"round"}));
    const [tx,ty]=polar(cx,cy,r,ang(fT));
    s.appendChild(el("line",{x1:cx,y1:cy,x2:tx,y2:ty,stroke:"#f5a623","stroke-width":2.4}));
    const [nx,ny]=polar(cx,cy,r-10,ang(f));
    s.appendChild(el("line",{x1:cx,y1:cy,x2:nx,y2:ny,stroke:"#fff","stroke-width":3,"stroke-linecap":"round"}));
    s.appendChild(el("circle",{cx,cy,r:6,fill:"#fff"}));
    const t1=el("text",{x:cx,y:cy-46,"text-anchor":"middle",fill:"#fff","font-size":26,"font-weight":800});t1.textContent=Math.round(value);s.appendChild(t1);
    const t2=el("text",{x:cx,y:cy-26,"text-anchor":"middle",fill:"#9fb3d4","font-size":12});t2.textContent=opt.label+" ("+opt.unit+")";s.appendChild(t2);
    const t3=el("text",{x:cx,y:cy+18,"text-anchor":"middle",fill:"#f5a623","font-size":11});t3.textContent="目标 "+Math.round(target);s.appendChild(t3);
  }

  function arrayLayout(c,opt){
    const W=360,H=360,s=svg(W,H);c.innerHTML="";c.appendChild(s);
    const n=3,powers=opt.powers,yaws=opt.yaws;
    const pmax=Math.max(...powers),pmin=Math.min(...powers);
    const cell=W/4,ox=cell,oy=cell,gap=cell*1.0;
    for(let r=0;r<n;r++)for(let col=0;col<n;col++){
      const idx=r*n+col,x=ox+col*gap,y=oy+r*gap;
      const pf=(powers[idx]-pmin)/((pmax-pmin)||1);
      const colr=`rgb(${Math.round(231-(231-39)*pf)},${Math.round(76+(174-76)*pf)},${Math.round(60+(96-60)*pf)})`;
      s.appendChild(el("circle",{cx:x,cy:y,r:20,fill:colr,stroke:"rgba(255,255,255,.25)"}));
      const a=(yaws[idx])*Math.PI/180,ax=x+26*Math.cos(a),ay=y-26*Math.sin(a);
      s.appendChild(el("line",{x1:x,y1:y,x2:ax,y2:ay,stroke:"#fff","stroke-width":2.4}));
      s.appendChild(el("circle",{cx:ax,cy:ay,r:3,fill:"#fff"}));
      const t=el("text",{x:x,y:y+34,"text-anchor":"middle",class:"turb"});t.textContent=Math.round(powers[idx]);s.appendChild(t);
    }
  }

  window.CHARTS={lineChart,barChart,polarRose,gauge,arrayLayout};
})();
