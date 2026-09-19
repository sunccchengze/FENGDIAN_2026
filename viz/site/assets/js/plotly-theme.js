/* 全站 Plotly 精密浅色主题：与尾流页灰阶和本地 Geist 字体同源。 */
(function () {
  window.WF = {
    bg: "#fafafa", plotBg: "#ffffff", card: "#ffffff",
    txt: "#171717", sub: "#4d4d4d", grid: "#ebebeb", axis: "#a1a1a1",
    blue: "#0070f3", blueDeep: "#0761d1", blueSoft: "#d3e5ff",
    sage: "#66c2a4", sageDeep: "#276c55",
    clay: "#ab570a", lavender: "#7928ca", gold: "#f5a623", rose: "#c50000"
  };

  window.PD = {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: WF.plotBg,
    font: {
      color: WF.txt,
      family: '"Geist","DengXian","等线","PingFang SC","Microsoft YaHei",sans-serif',
      size: 12
    },
    margin: { l: 55, r: 20, t: 15, b: 45 },
    legend: {
      orientation: "h", y: -0.18, x: 0,
      font: { size: 11, color: WF.sub }, bgcolor: "rgba(0,0,0,0)"
    },
    hoverlabel: {
      bgcolor: "#171717", bordercolor: "#171717",
      font: { color: "#ffffff", size: 12 }
    }
  };
  window.PAx = {
    color: WF.sub, gridcolor: WF.grid, linecolor: WF.axis, zerolinecolor: WF.axis,
    tickfont: { color: WF.sub, size: 11 }, title: { font: { color: WF.sub, size: 12 } }
  };

  // 精密浅色蓝阶：用于非速度场的连续量。
  window.BlueSeq = [
    [0, "#f5f9ff"], [0.2, "#d3e5ff"], [0.4, "#9bc5ff"],
    [0.6, "#5aa0f8"], [0.8, "#1877d8"], [1, "#0758a8"]
  ];
  window.BlueSeqMid = [
    [0, "#f5f9ff"], [0.5, "#8fc9ba"], [1, "#276c55"]
  ];

  // ColorBrewer BuGn 9-class reversed。低速尾流用森林绿，高速清洁来流用浅薄荷。
  window.FieldSeq = [
    [0.000, "#00441b"], [0.125, "#006d2c"], [0.250, "#238b45"],
    [0.375, "#41ae76"], [0.500, "#66c2a4"], [0.625, "#99d8c9"],
    [0.750, "#ccece6"], [0.875, "#e5f5f9"], [1.000, "#f7fcfd"]
  ];

  // 正增益为顺序量，使用白到深蓝；零值不会被误读成负值。
  window.GainSeq = [
    [0, "#f5f9ff"], [0.25, "#d3e5ff"], [0.5, "#8bbcff"],
    [0.75, "#3d8dea"], [1, "#0758a8"]
  ];

  // 体渲染沿用同一低饱和绿阶，避免二维、三维速度语义分裂。
  window.VolumeSeq = window.FieldSeq.slice();

  WF.FieldSeq = window.FieldSeq;
  WF.GainSeq = window.GainSeq;
  WF.BlueSeq = window.BlueSeq;
  WF.BlueSeqMid = window.BlueSeqMid;
  WF.VolumeSeq = window.VolumeSeq;

  function ml(o) {
    var b = JSON.parse(JSON.stringify({
      paper_bgcolor: PD.paper_bgcolor, plot_bgcolor: PD.plot_bgcolor,
      font: PD.font, margin: PD.margin, legend: PD.legend, hoverlabel: PD.hoverlabel,
      xaxis: Object.assign({}, PAx), yaxis: Object.assign({}, PAx)
    }));
    (function d(t, s) {
      for (var k in s) {
        if (typeof s[k] === "object" && s[k] && !Array.isArray(s[k])) {
          t[k] = t[k] || {};
          d(t[k], s[k]);
        } else {
          t[k] = s[k];
        }
      }
    })(b, o);
    return b;
  }
  window.ml = ml;

  window.pr = function (id, tr, ly, cfg) {
    Plotly.newPlot(id, tr, ml(ly), Object.assign({
      responsive: true, displayModeBar: "hover",
      modeBarButtonsToRemove: ["lasso2d", "select2d"]
    }, cfg || {}));
  };
})();
