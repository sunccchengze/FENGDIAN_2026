// 浏览器内插值（对应仓库 surrogate_model.py 的 predict_power / find_yaw_for_target）
// 纯表格双线性插值，无需任何后端。未来替换真实模型时只改这两个函数体即可。
//
// 可信域优先读取可选的 window.WF_DATA_CONFIG；未配置时直接采用 data.js 的
// 风速与偏航网格边界。越界时返回 outOfRange 与原因，供页面就地提示。
(function () {
  var W = window.WIND_DATA;
  var lerp = function (a, b, t) { return a + (b - a) * t; };

  function trustDomain() {
    var cfg = window.WF_DATA_CONFIG && window.WF_DATA_CONFIG.trustDomain;
    var m = W && W.multi;
    // 优先用配置；没有就从数据本身推断
    if (cfg) return { U: cfg.windSpeed, yaw: cfg.yaw };
    if (m) return {
      U: [m.wind_speeds[0], m.wind_speeds[m.wind_speeds.length - 1]],
      yaw: [m.yaw_angles[0], m.yaw_angles[m.yaw_angles.length - 1]]
    };
    return null;
  }

  function checkRange(U, yaw) {
    var td = trustDomain();
    if (!td) return { outOfRange: false, reasons: [] };
    var reasons = [];
    if (typeof U === "number" && (U < td.U[0] || U > td.U[1])) {
      reasons.push("风速 " + U + " m/s 超出可信域 " + td.U[0] + "–" + td.U[1] + " m/s");
    }
    if (typeof yaw === "number" && (yaw < td.yaw[0] || yaw > td.yaw[1])) {
      reasons.push("偏航 " + yaw + "° 超出可信域 " + td.yaw[0] + "–" + td.yaw[1] + "°");
    }
    return { outOfRange: reasons.length > 0, reasons: reasons };
  }

  function bilinear(gx, gy, mat, x, y) {
    // 夹紧到网格内（网格外无数据；是否外推由 outOfRange 标志告知调用方）
    var cx = Math.max(gx[0], Math.min(gx[gx.length - 1], x));
    var cy = Math.max(gy[0], Math.min(gy[gy.length - 1], y));
    var i = 0; while (i < gx.length - 1 && gx[i + 1] < cx) i++;
    var j = 0; while (j < gy.length - 1 && gy[j + 1] < cy) j++;
    var x0 = gx[i], x1 = gx[Math.min(i + 1, gx.length - 1)];
    var y0 = gy[j], y1 = gy[Math.min(j + 1, gy.length - 1)];
    var tx = (x1 === x0) ? 0 : (cx - x0) / (x1 - x0);
    var ty = (y1 === y0) ? 0 : (cy - y0) / (y1 - y0);
    var v00 = mat[i][j], v01 = mat[i][j + 1],
        v10 = mat[Math.min(i + 1, gx.length - 1)][j],
        v11 = mat[Math.min(i + 1, gx.length - 1)][j + 1];
    return lerp(lerp(v00, v01, ty), lerp(v10, v11, ty), tx);
  }

  // 接口契约：predict_power(yaw_angle, U_inf) -> {p1,p2,ptot,outOfRange,reasons}
  function predict_power(yaw, U) {
    var m = W.multi;
    var p1 = bilinear(m.wind_speeds, m.yaw_angles, m.p1, U, yaw);
    var p2 = bilinear(m.wind_speeds, m.yaw_angles, m.p2, U, yaw);
    var ptot = bilinear(m.wind_speeds, m.yaw_angles, m.ptot, U, yaw);
    var rng = checkRange(U, yaw);
    return { p1: p1, p2: p2, ptot: ptot, outOfRange: rng.outOfRange, reasons: rng.reasons };
  }

  // 接口契约：find_yaw_for_target(target_power, U_inf) -> {yaw,ptot,error,base,outOfRange,reasons}
  // 在离散偏航角中选最接近目标的；不做越界偏航的连续外推。
  function find_yaw_for_target(target, U) {
    var m = W.multi, ys = m.yaw_angles;
    var pts = ys.map(function (y) { return bilinear(m.wind_speeds, ys, m.ptot, U, y); });
    var base = bilinear(m.wind_speeds, ys, m.ptot, U, 0);
    var best = ys[0], bestErr = Infinity;
    for (var k = 0; k < ys.length; k++) {
      var e = Math.abs(pts[k] - target);
      if (e < bestErr) { bestErr = e; best = ys[k]; }
    }
    var actual = bilinear(m.wind_speeds, ys, m.ptot, U, best);
    var error = target > 0 ? (actual - target) / target * 100 : 0;
    var rng = checkRange(U, best);
    // 目标功率超过该风速最大可达功率时，单独标记"不可达"
    var maxP = Math.max.apply(null, pts);
    if (target > maxP) {
      rng.outOfRange = true;
      rng.reasons.push("目标功率 " + Math.round(target) + " kW 超过当前风速可达上限约 " + Math.round(maxP) + " kW");
    }
    return { yaw: best, ptot: actual, error: error, base: base,
             outOfRange: rng.outOfRange, reasons: rng.reasons };
  }

  window.SURROGATE = { predict_power: predict_power, find_yaw_for_target: find_yaw_for_target, bilinear: bilinear, checkRange: checkRange };
})();
