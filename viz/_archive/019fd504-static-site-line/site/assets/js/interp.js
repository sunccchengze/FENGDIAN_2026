// 浏览器内插值（对应仓库 surrogate_model.py 的 predict_power / find_yaw_for_target）
// 纯表格双线性插值，无需任何后端。未来替换真实模型时只改这两个函数体即可。
(function(){
  const W = window.WIND_DATA;
  const lerp = (a,b,t)=>a+(b-a)*t;

  function bilinear(gx, gy, mat, x, y){
    x = Math.max(gx[0], Math.min(gx[gx.length-1], x));
    y = Math.max(gy[0], Math.min(gy[gy.length-1], y));
    let i=0; while(i<gx.length-1 && gx[i+1] < x) i++;
    let j=0; while(j<gy.length-1 && gy[j+1] < y) j++;
    const x0=gx[i], x1=gx[Math.min(i+1,gx.length-1)];
    const y0=gy[j], y1=gy[Math.min(j+1,gy.length-1)];
    const tx = (x1===x0)?0:(x-x0)/(x1-x0);
    const ty = (y1===y0)?0:(y-y0)/(y1-y0);
    const v00=mat[i][j], v01=mat[i][j+1], v10=mat[Math.min(i+1,gx.length-1)][j], v11=mat[Math.min(i+1,gx.length-1)][j+1];
    return lerp(lerp(v00,v01,ty), lerp(v10,v11,ty), tx);
  }

  // 接口契约：predict_power(yaw_angle, U_inf) -> (P1, P2) kW
  function predict_power(yaw, U){
    const m = W.multi;
    const p1 = bilinear(m.wind_speeds, m.yaw_angles, m.p1, U, yaw);
    const p2 = bilinear(m.wind_speeds, m.yaw_angles, m.p2, U, yaw);
    const ptot = bilinear(m.wind_speeds, m.yaw_angles, m.ptot, U, yaw);
    return {p1, p2, ptot};
  }

  // 接口契约：find_yaw_for_target(target_power, U_inf) -> (best_yaw, actual_power, error_pct)
  function find_yaw_for_target(target, U){
    const m = W.multi;
    const ys = m.yaw_angles;
    const pts = ys.map(y=>bilinear(m.wind_speeds, ys, m.ptot, U, y));
    const base = bilinear(m.wind_speeds, ys, m.ptot, U, 0);
    let best=ys[0], bestErr=Infinity;
    for(let k=0;k<ys.length;k++){
      const e=Math.abs(pts[k]-target);
      if(e<bestErr){bestErr=e;best=ys[k];}
    }
    const actual = bilinear(m.wind_speeds, ys, m.ptot, U, best);
    const error = base>0 ? (actual-target)/target*100 : 0;
    return {yaw:best, ptot:actual, error, base};
  }

  window.SURROGATE = {predict_power, find_yaw_for_target, bilinear};
})();
