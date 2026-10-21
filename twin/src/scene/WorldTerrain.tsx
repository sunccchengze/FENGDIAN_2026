/* oxlint-disable react/immutability -- 帧循环内 mutate mat.userData/uniform 为 R3F 标准模式（docs/08 D2） */
import { useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { terrainSurfaceY, landMask, coastT, shoreSigned, FARM_CENTER, bakeHeightGrid } from './terrainUtil'
import { skyState } from './lightState'
import { windAt } from '../data/farmSim'
import { useSim } from '../state/simStore'
import { phaseT } from './freeze.ts'

// ============================================================
// 海洋地面（第 32 轮 A 重构 v4：六类生物群系 + 岩雪山体 + 海面克制化）
// ------------------------------------------------------------
// 诉求校正：
//   · 海陆交界要精细、陆地明显高于海 → 海盆半径扩大，海岸带陡升（terrainUtil）；
//   · 风机全在海中央、距海岸遥远   → 由 terrainUtil 地形函数保证；
//   · 海水不真实、格子重复感严重   → 顶点位移只留「大尺度涌浪」，所有细碎
//     波光由片元解析法线(waveHeight 梯度 + 分形噪声) + 片元浪尖层次生成，
//     不依赖网格分辨率 → 无格子；
//   · 太湛蓝刺眼 → 回到系统一贯「暗调冰青 + 低饱和莫兰迪灰调」，克制不惹眼。
//
// 保持：贴地基准 = terrainSurfaceY（风机/升压站/电缆/星光零回归），
//       波浪位移仅为顶点着色器运行时副作用。
// ============================================================

const VERT = /* glsl */ `
varying float vWater;
varying vec3 vWPos;
varying vec3 vWN;
varying float vLand;
varying float vH;
varying float vCoast;
varying float vShore;
attribute float aLand;
attribute float aCoast;
attribute float aShore;
uniform float uTime;
uniform vec2 uWind;
uniform vec2 uCenter;

float hash21(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }

// —— Gerstner 波（trochoidal）：steepness=波陡，wavelength=波长 ——
vec3 gerstner(vec2 pos, vec2 dir, float steepness, float wavelength, float time,
              inout vec3 tangent, inout vec3 binormal) {
  float k = 6.28318530718 / wavelength;
  float c = sqrt(9.8 / k);
  vec2 d = normalize(dir);
  float f = k * (dot(d, pos) - c * time);
  float a = steepness / k;
  tangent += vec3(
    -d.x * d.x * steepness * sin(f),
     d.x * steepness * cos(f),
    -d.x * d.y * steepness * sin(f));
  binormal += vec3(
    -d.x * d.y * steepness * sin(f),
     d.y * steepness * cos(f),
    -d.y * d.y * steepness * sin(f));
  return vec3(d.x * a * cos(f), a * sin(f), d.y * a * cos(f));
}

void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vWPos = wp.xyz;

  // 基底高度（海底）：position.y 来自 terrainSurfaceY（世界真值）
  float baseY = position.y;
  // 水陆 mask：aLand≈0 → 开放海(1)；aLand>0 → 陆地(0)。
  // 用 land 权重作主判据，避免「海岸低海拔沙带被误判为水」。
  float water = 1.0 - smoothstep(0.0, 0.02, aLand);
  vWater = water;
  vLand = aLand;
  vH = baseY;
  vCoast = aCoast;
  vShore = aShore;

  // R36 · 浅水波幅阻尼（coastal_3d_v2 ocean.ts 口径）：aShore 为带符号最近岸距
  // （负=海侧离岸米数）。涌浪贴岸衰减 → 岸线不再被大涌切出硬边、浪不爬坡。
  float shoreDamp = 0.16 + 0.84 * smoothstep(0.0, 260.0, -aShore);

  // 近场收敛：离场心越近波浪越收敛（塔基贴地、风场稳定）
  float d = length(wp.xz - uCenter);
  float amp = mix(0.5, 1.0, smoothstep(180.0, 2000.0, d)) * shoreDamp;

  // 顶点位移只保留「大尺度平缓涌浪」（波长远大于网格 ~30m），
  // 短波细碎波光全部交给片元解析法线 → 粗网格无块状格子感。
  vec2 wdir = normalize(uWind + vec2(0.0001, 0.0));
  vec2 d2 = normalize(vec2(-uWind.y, uWind.x));
  vec3 tangent = vec3(1.0, 0.0, 0.0);
  vec3 binormal = vec3(0.0, 0.0, 1.0);
  vec3 disp = vec3(0.0);
  vec2 p = wp.xz;
  disp += gerstner(p, wdir, 0.06, 2400.0, uTime * 0.35,          tangent, binormal);
  disp += gerstner(p, d2,   0.045, 1500.0, uTime * 0.50 + 2.1,   tangent, binormal);
  disp *= amp;

  // 波浪只在海上位移；陆地保持原始剪影
  float lift = water;
  vec3 newPos = vec3(wp.x, baseY + disp.y * lift, wp.z);
  newPos.xz += disp.xz * lift * 0.75;

  // R36 · swash 水线爬升：贴岸 0~32m 水面小幅正弦抬升（浪舌舔滩，随岸线噪声相位）
  float swash = (1.0 - smoothstep(0.0, 32.0, -aShore)) * water;
  newPos.y += swash * 0.20 * sin(uTime * 0.8 + wp.x * 0.011 + wp.z * 0.014);

  // 法线：海水用大尺度 Gerstner 法线；陆地用真实几何法线（computeVertexNormals），
  // 山体明暗/雪沟/裸岩全靠它 —— 此前陆地近似上向是“盐堆”感的根因（round4 修复）
  vec3 gNorm = normalize(cross(binormal, tangent));
  // R39 · T4：法线也吃同一个包络。位移乘了 amp（场心收敛 × 浅水阻尼），
  // 而 tangent/binormal 是在 gerstner 内部按未衰减的陡度累加的 —— 不修则近岸/塔基
  // 会出现「水面几乎不动、法线却在大幅摇摆」的自相矛盾。按 amp 把法线回归 up。
  gNorm = normalize(mix(vec3(0.0, 1.0, 0.0), gNorm, clamp(amp, 0.0, 1.0)));
  vec3 n = normalize(mix(normal, gNorm, water));
  vWN = n;

  gl_Position = projectionMatrix * modelViewMatrix * vec4(newPos, 1.0);
}
`

const FRAG = /* glsl */ `
precision highp float;
varying float vWater;
varying vec3 vWPos;
varying vec3 vWN;
varying float vLand;
varying float vH;
varying float vCoast;
varying float vShore;
uniform float uTime;
uniform float uDayF;
uniform float uGlow;
uniform vec3 uSunDir;
uniform vec3 uFogColor;
uniform float uFogDensity;
uniform vec2 uWind; // Step B：泡沫顺风拉丝用风向（uniforms 本就有，FRAG 补声明）
uniform vec2 uCenter; // R39 · T4：涌浪包络的场心收敛（与 VERT 同式，FRAG 补声明）
uniform sampler2D uHeightTex; // Step C1：烘焙高度图（512²，uv = xz/9200+0.5）
uniform vec3 uMoonDir; // Step C3：月光方向（地形月夜漫反射 + 水面月路）
uniform float uWarmF; // R37 太阳色温（0=白 1=红，仰角连续）：雪冠/岩脊/晨光波光共用

float hash21(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f*f*(3.0-2.0*f);
  return mix(mix(hash21(i), hash21(i+vec2(1.0,0.0)), u.x),
             mix(hash21(i+vec2(0.0,1.0)), hash21(i+vec2(1.0,1.0)), u.x), u.y);
}
float fbm(vec2 p){
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 4; i++) { v += a * vnoise(p); p *= 2.02; a *= 0.5; }
  return v;
}

// —— R39 · T4「波系同源」：片元解析波高与 VERT 的 Gerstner 【同方向/同波长/同相位/同幅值】——
// 旧版这里是与顶点几何**毫无关系**的 5 条等幅正弦（λ≈436m/280m/…，方向/相位各自为政）：
// 泡沫、浪尖、高光全都骑在另一套波上，几何浪峰与着色浪峰错位（round38 §一 判定为真缺陷）。
// 现在涌浪项由下面两个函数给出，公式逐项镜像 VERT 的 gerstner：
//   f = k·(dot(dir,p) − c·(t·coef + phase)),  c = √(9.8/k),  a = steepness/k
// ⚠ 改 VERT 的 gerstner 参数（方向/波长/陡度/时间系数/相位）必须同步改这里 ——
//   selftest R39 逐项对表（波长/陡度/时间系数/相位四个数都在断言里）。
float swellN(vec2 p) {
  vec2 wdir = normalize(uWind + vec2(0.0001, 0.0));
  vec2 d2 = normalize(vec2(-uWind.y, uWind.x));
  float t = uTime;
  float k1 = 6.28318530718 / 2400.0;
  float k2 = 6.28318530718 / 1500.0;
  float a1 = 0.06 / k1;   // = 22.9m，与 VERT 第 1 条 Gerstner 的 a = steepness/k 同
  float a2 = 0.045 / k2;  // = 10.7m，同上
  float s1 = sin(k1 * (dot(wdir, p) - sqrt(9.8 / k1) * (t * 0.35)));
  float s2 = sin(k2 * (dot(d2,  p) - sqrt(9.8 / k2) * (t * 0.50 + 2.1)));
  return (a1 * s1 + a2 * s2) / (a1 + a2); // 归一化相位包络 ∈[-1,1]（幅值比=几何的 0.68:0.32）
}
// 与 VERT 的 amp 同式（场心收敛 × 浅水阻尼）：几何收的地方，着色浪尖也要跟着收。
// 用 varying vShore / vWPos（不是参数 p）——包络在米级尺度上是平滑量，与差分点无关。
float swellEnv() {
  float dc = length(vWPos.xz - uCenter);
  return mix(0.5, 1.0, smoothstep(180.0, 2000.0, dc)) * (0.16 + 0.84 * smoothstep(0.0, 260.0, -vShore));
}
// 次网格细节：λ≈230m 以下（网格 23m 解析不了这些波，顶点不位移它们），
// 只进法线/浪尖 —— 沿用 R36 之前就有的这三项 + 分形涟漪，手感不变。
float rippleHeight(vec2 p) {
  float t = uTime;
  float h = sin(dot(p, vec2( 0.0220,  0.0160)) * 1.0 + t * 1.10 + 3.3) * 0.46;
  h += sin(dot(p, vec2( 0.0180, -0.0140)) * 1.0 + t * 1.35 + 5.1) * 0.38;
  h += sin(dot(p, vec2(-0.0160,  0.0180)) * 1.0 + t * 1.60 + 7.4) * 0.30;
  h += (fbm(p * 0.06 + uTime * 0.03) - 0.5) * 0.7;
  return h;
}
// 解析波高（**着色口径**，与 R36 前的量级刻意保持一致：涌浪 0.72 + 细节 1.14 + 分形），
// 这样 crest 阈值（smoothstep 0.25/0.85）与泡沫/浪尖的统计口径不变，
// 变的只是「涌浪项的相位」—— 从与几何无关变成与几何同源。
float waveHeight(vec2 p) {
  return 0.72 * swellN(p) * swellEnv() + rippleHeight(p);
}
// 水体法线 = 顶点 Gerstner 几何法线（真实涌浪斜率，已吃 amp 包络）
//          + 次网格细碎波梯度（着色细节，几何不位移）
// 旧版直接丢弃几何法线、只解析算 5 条正弦 → 浪形与着色脱节（本项要修的根因）。
vec3 waterNormal(vec3 gN, vec2 p, float fade) {
  float e = 1.0; // 差分步长（米）
  float hL = rippleHeight(p - vec2(e, 0.0));
  float hR = rippleHeight(p + vec2(e, 0.0));
  float hD = rippleHeight(p - vec2(0.0, e));
  float hU = rippleHeight(p + vec2(0.0, e));
  // 0.5 = 与旧式 normalize(vec3(hL−hR, 2e, hD−hU)) 等价的比例（2e=2）——斜率口径不变
  vec3 n = normalize(gN + vec3((hL - hR) * 0.5, 0.0, (hD - hU) * 0.5));
  // 弱分形微细节：细碎波光、无格子（振幅压低，避免散射成灰雾）
  float nA = fbm(p * 0.05 + uTime * 0.05);
  float nB = fbm(p * 0.11 - uTime * 0.09);
  n += vec3((nA - 0.5) * 0.20 * fade, 0.0, (nB - 0.5) * 0.20 * fade);
  return normalize(n);
}

// —— 地形投影（Step C1）：沿太阳方向 march 高度图 ——
// 10 步、近密远疏（40m→~3000m），软半影；返回 1=全亮、0=全影。
// 调用方以 shadowAmt 按太阳高度连续渐隐；域外视为无遮挡。
float terrainShadow(vec3 p, vec3 sunDir) {
  float res = 1.0;
  float t = 40.0;
  for (int i = 0; i < 10; i++) {
    vec3 tp = p + sunDir * t;
    vec2 suv = tp.xz / 9200.0 + 0.5;
    if (suv.x > 0.001 && suv.x < 0.999 && suv.y > 0.001 && suv.y < 0.999) {
      float th = texture2D(uHeightTex, suv).r;
      res = min(res, 8.0 * (tp.y - th + 1.5) / t);
    }
    t *= 1.55;
  }
  float sh = clamp(res, 0.0, 1.0);
  return sh * sh * (3.0 - 2.0 * sh);
}

// —— R39 · T4「真天空反射」：在反射方向上采样与 SkyAurora **同源**的解析天幕 ——
// 旧版 skyRef 是「与视角、太阳方位、月相全都无关」的两个常数色（mix(暗, 亮, uDayF)）——
// 海面反射着一个天上并不存在的颜色（round38 §一 判定为真缺陷）。
// 这里逐项镜像 SkyAurora 的解析层：冰青渐变 → 地平亮带（太阳方位扇区随 uWarmF 暖化）→
// 日轮/冷晕/暖晕 → 月盘/月晕 → 下半球融雾（uFogColor）。
// **不含**：照片星野纹理、极光带、星点、程序云（云影扫海另议，见 docs/11 §四）。
// ⚠ 改 SkyAurora 的色板必须同步改这里（selftest R39 锁同源：uWarmF/uFogColor/uSunDir 都必须被消费）。
vec3 seaSky(vec3 R, float sGate) {
  float h = clamp(R.y, -1.0, 1.0);
  float night = 1.0 - uDayF;
  vec3 col = mix(vec3(0.062, 0.175, 0.230), vec3(0.010, 0.042, 0.075), smoothstep(0.0, 0.16, h));
  col = mix(col, vec3(0.002, 0.008, 0.018), smoothstep(0.12, 0.55, h));
  vec3 dayCol = mix(vec3(0.086, 0.165, 0.239), vec3(0.290, 0.451, 0.565), smoothstep(0.02, 0.55, h));
  col = mix(col, dayCol, uDayF * 0.86);
  // 地平线宽亮带（与 SkyAurora 同式：R37b 的太阳扇区暖化也一并镜像）
  float band1 = pow(clamp(1.0 - abs(h), 0.0, 1.0), 13.0);
  float band2 = pow(clamp(1.0 - abs(h), 0.0, 1.0), 5.0);
  vec2 sdHxz = normalize(uSunDir.xz + vec2(1e-5, 0.0));
  float azCone = pow(clamp(dot(normalize(R.xz + vec2(1e-5, 0.0)), sdHxz), 0.0, 1.0), 3.0);
  float wAz = uWarmF * azCone;
  col += mix(vec3(0.16, 0.44, 0.55) * 1.35, vec3(0.72, 0.26, 0.08) * 0.90, wAz) * band1;
  col += mix(vec3(0.05, 0.16, 0.22) * 0.55, vec3(0.55, 0.20, 0.07) * 0.55, wAz) * band2;
  // 左上冷光辉 + 顶部全宽柔光（SkyAurora 的两项解析层，同样只在上半球）
  float az = atan(R.x, -R.z);
  float upper = smoothstep(-0.04, 0.10, h);
  col += vec3(0.55, 0.72, 0.85) * exp(-pow((az + 0.42) * 3.4, 2.0)) * exp(-max(h, 0.0) * 14.0) * upper * 0.14;
  col += vec3(0.06, 0.17, 0.24) * pow(clamp(1.0 - abs(h), 0.0, 1.0), 3.0) * exp(-max(h, 0.0) * 2.4) * upper * 0.38;
  // 日轮 + 冷晕 + 暖晕（亮度门 sGate 由调用方按 SkyAurora 同式给出）
  float sunDot = clamp(dot(R, normalize(uSunDir)), 0.0, 1.0);
  vec3 sunDiscCol = mix(vec3(0.92, 0.97, 1.0), vec3(1.08, 0.40, 0.15), uWarmF);
  col += sunDiscCol * pow(sunDot, 1400.0) * 1.35 * (1.0 - 0.28 * uWarmF) * sGate;
  col += vec3(0.32, 0.46, 0.58) * pow(sunDot, 14.0) * 0.16 * uDayF;
  col += vec3(1.02, 0.50, 0.20) * pow(sunDot, 5.0) * uWarmF * 0.30 * (0.30 + 0.70 * sGate);
  // 月盘 + 内晕 + 外晕（夜间月光在海面反射里的分量）
  float moonDot = clamp(dot(R, normalize(uMoonDir)), 0.0, 1.0);
  col += vec3(0.92, 0.96, 1.0) * smoothstep(0.99980, 0.99995, moonDot) * 2.4 * night;
  col += vec3(0.55, 0.70, 0.85) * pow(moonDot, 900.0) * 0.9 * night;
  col += vec3(0.35, 0.52, 0.68) * pow(moonDot, 90.0) * 0.22 * night;
  // 下半球融雾：与 SkyAurora / 场景雾同色（远海收边两侧同色，接缝不可见）
  return mix(col, uFogColor, 1.0 - smoothstep(-0.07, 0.02, h));
}

void main() {
  float night = 1.0 - uDayF;
  vec3 V = normalize(cameraPosition - vWPos);
  float camDist = length(cameraPosition - vWPos);
  // R36 · 微细节距离衰减（120→1500m 归零）：远处高频法线欠采样 → 波光闪烁
  float rippleFade = 1.0 - smoothstep(120.0, 1500.0, camDist);

  // 法线：海上 = 顶点 Gerstner 几何法线（真实涌浪斜率）× 次网格解析细碎波（R39 · T4）；
  // 陆上退回顶点法线（山体明暗/雪沟/裸岩全靠它）
  vec3 N = mix(normalize(vWN), waterNormal(normalize(vWN), vWPos.xz, rippleFade), vWater);
  N = normalize(N);
  vec3 Ns = N;
  float ndv = max(dot(N, V), 0.0);

  // 浪尖层次：片元内用解析波高现算（摆脱顶点网格 → 消除条带/格子感）
  float wh = waveHeight(vWPos.xz);
  float crest = smoothstep(0.25, 0.85, wh); // 归一化波高 → 0..1 浪尖
  // Step B1：打散浪尖云斑 —— 高频 breakup 把正弦干涉的 200m+ 亮斑撕碎，
  // 提亮不同步下调（0.55→0.42），海面不再“长癣”
  float breakup = fbm(vWPos.xz * 0.020 + vec2(uTime * 0.05, -uTime * 0.03));
  crest *= 0.45 + 0.55 * smoothstep(0.25, 0.75, breakup);

  // —— Fresnel 菲涅尔：贴水面反射天空；用「面朝上」gate 掉陡岸坡发白 ——
  float upness = smoothstep(0.36, 0.72, N.y);
  float fres = pow(1.0 - ndv, 3.4) * upness;

  // —— 配色：系统一贯「暗调冰青 + 低饱和莫兰迪灰调」，克制不惹眼 ——
  // 参照用户原图：海底深青黑，浪尖点缀青白，整体暗、不刺眼。
  vec3 deepCol  = mix(vec3(0.008, 0.022, 0.038), vec3(0.050, 0.115, 0.185), uDayF); // 浪谷（深青黑）
  vec3 shallowCol = mix(vec3(0.024, 0.055, 0.082), vec3(0.150, 0.310, 0.420), uDayF); // 浪尖（低饱和青蓝）
  vec3 waterCol = mix(deepCol, shallowCol, crest * 0.42);

  // 天空反射（R39 · T4 重做）：反射方向上真采一次天幕（与 SkyAurora 同源），
  // 不再是与视角无关的平涂色。权重维持 R36 口径（新反射色本身比旧平涂更准，
  // 不需要靠提高权重去"补色"；若观感需要再走 A/B，见 docs/research/round39）。
  // R 的 y 夹到 ≥0.02：水面反射只取上半球，避免掠射时反射到地平线以下（融雾带）。
  vec3 Rr = reflect(-V, N);
  Rr.y = max(Rr.y, 0.02);
  float sunUpNow = normalize(uSunDir).y;
  float sGateNow = smoothstep(-0.017, 0.035, sunUpNow); // 与 SkyAurora 同式：日轮亮度门
  vec3 skyRef = seaSky(Rr, sGateNow);
  waterCol = mix(waterCol, skyRef, clamp(fres, 0.0, 1.0) * (0.045 + 0.07 * uDayF));

  // —— R36 · 背光浪尖透射（SSS）：逆光时浪尖微透青绿（coastal_3d_v2 sss 的暗调版）——
  // 只在白天、且视线朝向太阳时出现；强度压低，不引入新色相（沿用冰青）
  float sss = pow(max(dot(V, -uSunDir), 0.0), 3.0) * crest;
  waterCol += vec3(0.040, 0.190, 0.185) * sss * uDayF * 0.40;

  // —— 太阳/月亮镜面高光：细碎点状波光（点状，克制，不高亮成云斑）——
  // R36：镜面指数随距离升高（远处的耀斑收窄成点 → 远海不糊成一片亮）
  vec3 halfV = normalize(V + uSunDir);
  float specExp = 620.0 + night * 320.0 + 480.0 * smoothstep(0.0, 2500.0, camDist);
  float spec = pow(max(dot(Ns, halfV), 0.0), specExp);
  float sparkle = fbm(vWPos.xz * 0.12 + uTime * 0.8) * fbm(vWPos.xz * 0.35 - uTime * 0.5);
  spec *= (0.10 + 0.90 * sparkle);
  vec3 sunCol = mix(vec3(0.11, 0.26, 0.38), vec3(0.80, 0.80, 0.78), uDayF);
  // R37 晨昏波光：日出/日落时镜面高光是太阳的倒影，理应同色温（红金）；
  // uWarmF 由仰角连续驱动，正午自动回白，海面本身的暗调冰青口径不变。
  sunCol = mix(sunCol, vec3(1.00, 0.52, 0.24), uWarmF * 0.45);
  waterCol += sunCol * spec * (uDayF * 0.72 + night * 0.13);
  // R36 · 宽瓣高光：锐瓣外围一圈柔晕（真实水面耀斑的双瓣结构），克制低强度
  float specBroad = pow(max(dot(Ns, halfV), 0.0), 56.0);
  waterCol += sunCol * specBroad * uDayF * 0.10 * (0.3 + 0.7 * sparkle);

  // —— 波峰泡沫（Step B2）：顺风拉丝 + 米级碎点 + 三重稀疏门 ——
  // 各向异性坐标把各向同性云斑拉成风纹碎浪，随风漂移；只在最碎的浪尖出现
  vec2 wdirF = normalize(uWind + vec2(0.0001, 0.0));
  vec2 wperpF = vec2(-wdirF.y, wdirF.x);
  float alongW = dot(vWPos.xz, wdirF);
  float acroW = dot(vWPos.xz, wperpF);
  float foamStreak = fbm(vec2(alongW * 0.045 - uTime * 0.25, acroW * 0.20) + crest * 2.0);
  float foamFleck = vnoise(vWPos.xz * 0.9 + uTime * 0.4); // 米级碎点
  float foamMask = smoothstep(0.78, 0.97, crest)
    * smoothstep(0.55, 0.85, foamStreak)
    * (0.35 + 0.65 * smoothstep(0.55, 0.9, foamFleck));
  vec3 foam = mix(vec3(0.028, 0.06, 0.09), vec3(0.50, 0.63, 0.68), uDayF); // 更低饱淡青白
  waterCol = mix(waterCol, foam, foamMask * (0.03 + uDayF * 0.09));
  // —— 水侧水线（Step B3）+ R36 拍岸碎浪带 ——
  // 紧贴岸线的海侧碎浪（与陆侧 foamDot 合成完整水线）；
  // 水像素中 vLand∈(0,0.02) 即岸线外 15~40m；环岸/环岛/环柱自动出现，机组区 vLand=0 不受影响
  float surfBand = smoothstep(0.0, 0.004, vLand) * (1.0 - smoothstep(0.004, 0.02, vLand));
  float surfN = 0.35 + 0.65 * fbm(vWPos.xz * 0.30 + vec2(-uTime * 0.35, uTime * 0.2));
  // 周期性向岸推进的碎浪带：离岸 0~300m、带间隔 ~114m、向岸传播，
  // 相位用 fbm 扰动 → 不是机械平行弧线（coastal_3d_v2 rolling surf 的暗调版）
  float dShore = -vShore;
  float shoreBand = 1.0 - smoothstep(0.0, 300.0, dShore);
  float rollPh = -dShore * 0.055 - uTime * 1.35 + fbm(vWPos.xz * 0.02) * 5.5;
  float rollB = sin(rollPh) * 0.5 + 0.5;
  float surfRoll = shoreBand * smoothstep(0.45, 0.78,
    rollB * 0.62 + shoreBand * 0.30 + (fbm(vWPos.xz * 0.09 - uTime * 0.10) - 0.5) * 0.4);
  float foamAmt = max(surfBand * surfN, surfRoll) * (0.10 + uDayF * 0.30) * vWater;
  waterCol = mix(waterCol, foam, foamAmt);

  // —— 月路（C3）：明月在水面的镜面光路 + 月照涌动 ——
  // 旧版用太阳方向算夜高光，夜里太阳在地平线下故恒≈0（“夜里没光”的另一半根因）
  vec3 halfVM = normalize(V + normalize(uMoonDir));
  float moonSpec = pow(max(dot(Ns, halfVM), 0.0), 220.0);
  waterCol += vec3(0.38, 0.56, 0.70) * moonSpec * night * (0.25 + uGlow) * 1.1;
  waterCol += vec3(0.05, 0.12, 0.18) * crest * night * (0.25 + uGlow) * 0.55;

  // —— 陆地 v4（六类生物群系 + 岩雪山体，第 32 轮 A）——
  // 与 CPU 端 biomeWeights() 同式；L = vLand（0 海 → 1 内陆）。
  float L = vLand;
  // 岸线破碎（round5）：渲染级高频扰动，沙/潮带按扰动后的 Lp 落位，水线参差 ——
  // CPU 端 biomeWeights 仍用平滑 L（草地散布不需要 40m 级参差），此处分歧是渲染级细节。
  float shoreN = fbm(vWPos.xz * 0.025 + 11.3);
  float Lp = L + (shoreN - 0.5) * 0.16;
  float wSand   = 1.0 - smoothstep(0.06, 0.16, Lp);
  float wTidal  = smoothstep(0.05, 0.12, Lp) * (1.0 - smoothstep(0.16, 0.28, Lp));
  float wGrass  = smoothstep(0.14, 0.30, L) * (1.0 - smoothstep(0.45, 0.62, L));
  float wForest = smoothstep(0.38, 0.55, L) * (1.0 - smoothstep(0.68, 0.82, L));
  float wHill   = smoothstep(0.60, 0.75, L) * (1.0 - smoothstep(0.85, 0.95, L));
  float wMtn    = smoothstep(0.82, 0.93, L);
  float wSandE = pow(wSand, 1.25); float wTidalE = pow(wTidal, 1.25); float wGrassE = pow(wGrass, 1.25);
  float wForestE = pow(wForest, 1.25); float wHillE = pow(wHill, 1.25); float wMtnE = pow(wMtn, 1.25);
  float wSum = wSandE + wTidalE + wGrassE + wForestE + wHillE + wMtnE + 1e-5;
  wSand = wSandE / wSum; wTidal = wTidalE / wSum; wGrass = wGrassE / wSum;
  wForest = wForestE / wSum; wHill = wHillE / wSum; wMtn = wMtnE / wSum;

  // 日间群系色（A-round2：拉开色相/明度距离，分层可辨；仍压住饱和，克制不刺眼）
  vec3 cSand   = vec3(0.450, 0.360, 0.240); // 干沙（暖亮）
  vec3 cTidal  = vec3(0.160, 0.130, 0.090); // 潮间湿沙（深，湿润感）
  vec3 cGrass  = vec3(0.135, 0.235, 0.095); // 草原（压暗，远观不晃眼）
  vec3 cForest = vec3(0.070, 0.160, 0.100); // 林地（深绿）
  vec3 cHill   = vec3(0.230, 0.200, 0.130); // 缓丘（棕橄榄，与林地区分）
  vec3 cRock   = vec3(0.110, 0.120, 0.140); // 山岩（深灰）

  // 细节噪声：草原/林地高频斑驳、沙粒微粒、山岩分形
  float g1 = vnoise(vWPos.xz * 0.020);
  float g2 = vnoise(vWPos.xz * 0.055 + 7.3);
  float grassN = g1 * 0.65 + g2 * 0.35;
  float sandN = vnoise(vWPos.xz * 0.11 + 3.1);
  float rockN = fbm(vWPos.xz * 0.008 + 1.7);
  float ribs = fbm(vec2(vWPos.x * 0.020 + vWPos.z * 0.013, vWPos.z * 0.031 - vWPos.x * 0.007)); // 沟脊（雪沟/岩脊/AO共用）
  float crownN = g1 * 0.5 + fbm(vWPos.xz * 0.030) * 0.5;

  vec3 landDay = cSand * (0.92 + 0.16 * sandN) * wSand
               + cTidal * wTidal
               + cGrass * (0.78 + 0.44 * grassN) * wGrass
               + cForest * (0.78 + 0.44 * crownN) * wForest
               + cHill * (0.85 + 0.30 * rockN) * wHill
               + cRock * (0.80 + 0.40 * rockN) * wMtn;
  // 陆地起伏漫反射（只作用陆地；雪有自己的日光模型，不在此重复压暗）
  float landDiff = 0.70 + 0.30 * clamp(dot(N, uSunDir) * 0.5 + 0.5, 0.0, 1.0);
  landDay *= mix(1.0, landDiff, 1.0 - vWater);
  // 湿沙带：紧贴水线压暗（退潮湿润感），只作用沙/潮带 —— 岸线“镶边”，破画笔渐变
  float wetBand = (1.0 - smoothstep(0.015, 0.10, Lp)) * clamp(wSand + wTidal, 0.0, 1.0);
  landDay *= 1.0 - wetBand * 0.45;

  // —— 细节法线（round4）：高频起伏扰动，只用于雪/岩光照，制造嶙峋光影 ——
  float eD = 6.0;
  float dHx = fbm(vWPos.xz * 0.045 + 3.7) - fbm(vWPos.xz * 0.045 - vec2(eD * 0.045, 0.0) + 3.7);
  float dHz = fbm(vWPos.xz * 0.045 + 3.7) - fbm(vWPos.xz * 0.045 - vec2(0.0, eD * 0.045) + 3.7);
  vec3 Ndet = normalize(N + vec3(-dHx * 2.2, 0.0, -dHz * 2.2));
  // 微起伏（round8）：米级地表凹凸进法线，近看有“颗粒”，远处衰减防闪烁
  float microFade = exp(-camDist / 380.0);
  if (microFade > 0.01) {
    float m1 = fbm(vWPos.xz * 0.55 + 7.1);
    float m2 = fbm(vWPos.xz * 0.55 + vec2(2.5, 0.0) + 7.1);
    float m3 = fbm(vWPos.xz * 0.55 + vec2(0.0, 2.5) + 7.1);
    Ndet = normalize(Ndet + vec3((m1 - m2) * 1.6, 0.0, (m1 - m3) * 1.6) * microFade);
  }
  float fade2 = exp(-camDist / 500.0); // 反照率微细节衰减（比法线稍远）

  // 山脊裸岩：坡陡处露出山岩（细节法线让岩壁有明暗皴擦，谷地留绿）
  float steep = 1.0 - Ndet.y;
  float rockExp = smoothstep(0.42, 0.72, steep) * clamp(wHill + wMtn, 0.0, 1.0);
  landDay = mix(landDay, cRock * (0.85 + 0.30 * rockN), clamp(rockExp, 0.0, 1.0) * 0.85);

  // —— 雪冠 v2（round4）：岩脊雪沟 + 日光质感，告别“盐堆” ——
  // 沟留雪、脊露岩：高频脊线 + 雪线扰动打破“一刀切”（雪线 380/460，与 CPU SNOW_LINE 同值）
  float snow = smoothstep(380.0, 460.0, vH + (ribs - 0.5) * 90.0);
  float slopeGate = smoothstep(0.35, 0.70, Ndet.y); // 陡壁挂不住雪（窄脊主峰正需要）
  float ribGate = 0.50 + 0.50 * smoothstep(0.30, 0.70, ribs); // 沟雪脊岩
  snow *= (0.25 + 0.75 * slopeGate) * ribGate;
  snow *= 0.35 + 0.65 * wMtn;
  float snowM = clamp(snow, 0.0, 1.0);
  // 雪的日光：向阳暖白 / 背阴冷蓝（整块平板白的根因在此）
  float sunDiff = clamp(dot(Ndet, uSunDir) * 0.5 + 0.5, 0.0, 1.0);
  vec3 snowCol = mix(vec3(0.42, 0.50, 0.66), vec3(1.02, 1.00, 0.97), sunDiff);
  // 风蚀纹（sastrugi）：拉伸条纹明暗，近看有“风雕”质感
  float sast = fbm(vec2((vWPos.x + vWPos.z) * 0.06, (vWPos.x - vWPos.z) * 0.012));
  snowCol *= 0.88 + 0.24 * sast;
  // 雪晶闪光：只在向阳面星星点点（白天反光强度的来源，克制）
  vec3 Vv = normalize(cameraPosition - vWPos);
  vec3 Hv = normalize(Vv + uSunDir);
  float glint = pow(max(dot(Ndet, Hv), 0.0), 60.0);
  float glintN = fbm(vWPos.xz * 0.12 + uTime * 0.05);
  snowCol += vec3(1.0, 0.98, 0.94) * glint * smoothstep(0.50, 0.9, glintN) * uDayF * 4.0 * sunDiff;
  // —— R37 日照金山 v2（仰角连续）：雪冠朝阳面红→金→随白昼退去 ——
  // pow(sunDiff,2.2)：只有朝阳坡吃色，背阴面保持冷蓝雪 —— 金山的核心是方向性。
  // 强度与色相都由 uWarmF 连续驱动：日出红金（warm≈1）→ 上午淡金（0.3）
  // → 正午纯白雪（0）；日落对称再来一遍。海面 vWater 路径不消费本项。
  float alpen = uWarmF * pow(sunDiff, 2.2);
  vec3 alpenCol = mix(vec3(1.06, 0.72, 0.40), vec3(1.05, 0.44, 0.22), uWarmF * 0.45);
  vec3 snowGold = mix(snowCol, alpenCol, alpen * 0.88);
  landDay = mix(landDay, snowGold, snowM);
  // 岩石质感（round5）：层理 + 碎石颗粒 + 凹缝 AO，杀“塑料黏土”；
  // round10 起只给高山 + 陡壁（丘陵带保持干净植被，不再整片压灰）
  float strata = sin(vH * 0.33 + rockN * 5.0 + Ndet.x * 2.0);
  float rockGrain = vnoise(vWPos.xz * 0.06) * 0.6 + vnoise(vWPos.xz * 0.17 + 4.2) * 0.4;
  float crevAO = 0.70 + 0.30 * smoothstep(0.25, 0.75, ribs * 0.5 + rockGrain * 0.5);
  float rockZone = clamp(wMtn + rockExp, 0.0, 1.0);
  float rockTex = (0.88 + 0.12 * strata) * (0.78 + 0.44 * rockGrain) * crevAO;
  landDay *= mix(1.0, rockTex, (1.0 - snowM) * clamp(rockZone, 0.0, 1.0));
  // R37 日照金山 v2：裸岩山脊吃一线暖色（比雪弱，只勾山脊棱线；仰角连续）
  landDay *= mix(vec3(1.0), vec3(1.22, 0.94, 0.68),
    uWarmF * pow(sunDiff, 2.5) * clamp(rockZone, 0.0, 1.0) * 0.45);
  // 微反照率（round8）：厘米~米级地表质感，放大看的本钱；植被（草/树）不管，只做地
  if (fade2 > 0.02) {
    // 沙：风成波纹（定向）+ 散布卵石
    float ripple = sin(dot(vWPos.xz, vec2(0.9, 0.45)) * 2.2 + fbm(vWPos.xz * 0.15) * 9.0);
    float pebble = step(0.965, hash21(floor(vWPos.xz * 2.6) + 1.0));
    float sandZone = clamp(wSand + wTidal, 0.0, 1.0);
    landDay *= 1.0 + (ripple * 0.10 + (fbm(vWPos.xz * 2.3) - 0.5) * 0.25) * sandZone * fade2;
    landDay *= 1.0 - pebble * 0.35 * sandZone * fade2;
    // 草地：丛块浓淡（不是草叶，是地被斑驳；种草另起）
    float tuft = fbm(vWPos.xz * 0.9 + 2.2);
    landDay *= 1.0 + (tuft - 0.5) * 0.35 * clamp(wGrass + wForest * 0.5, 0.0, 1.0) * fade2;
    // 岩：裂隙网（深色脉）+ 碎石灰点
    float crack = 1.0 - abs(2.0 * fbm(vWPos.xz * 0.33 + 5.5) - 1.0);
    crack = pow(crack, 3.0);
    float scree = step(0.975, hash21(floor(vWPos.xz * 3.1) + 7.0));
    float bareRock = clamp(rockZone, 0.0, 1.0) * (1.0 - snowM);
    landDay *= 1.0 - crack * 0.40 * bareRock * fade2;
    landDay *= 1.0 + scree * 0.30 * bareRock * fade2;
    // 水线：泡沫碎点（陆侧水线镶边，水体泡沫归 Step B）
    float foamDot = step(0.93, hash21(floor(vWPos.xz * 1.4) + 3.0)) * (1.0 - smoothstep(0.005, 0.05, Lp));
    landDay = mix(landDay, vec3(0.75, 0.82, 0.84), foamDot * 0.7 * fade2);
  }

  float lm = vnoise(vWPos.xz * 0.0021);
  lm += 0.5 * vnoise(vWPos.xz * 0.0055);

  // —— 昼夜（R36c 重做）：夜间陆地不再「灰白」——
  // 旧版 = 平乘 0.19~0.23 + 【加性】wrap 月光 vec3(0.30,0.42,0.58)×0.35（与反照率
  // 无关，沙/岩/雪全被抬到同一灰蓝平台 → 灰白抹灰感；雪冠反照率≈1 最受害）。
  // 真实月夜（3 张实拍对拍：均值 0.04~0.22、只朝阳坡亮、坡向明暗差 2~4×）：
  //   ① 夜底乘压到星光/气辉量级（≈0.05），不再 0.2 级平台；
  //   ② 月光改【乘性方向塑形】：朝阳坡银灰、背阳坡近黑（对比出山体体积）；
  //   ③ 月高度门 moonGate：月落山后陆地沉入更黑的夜（连续，无开关跳变）。
  // 白天路径逐字不变（全部改动按 night=1-uDayF 门控）；海面 vWater 路径不碰。
  float moonUp = clamp(normalize(uMoonDir).y, 0.0, 1.0);
  float moonGate = night * moonUp;
  vec3 nightBase = vec3(0.045, 0.055, 0.075) * (0.55 + 0.45 * moonUp);
  float moonWrap = clamp(dot(Ndet, normalize(uMoonDir)) * 0.5 + 0.5, 0.0, 1.0);
  float moonSlope = pow(moonWrap, 1.7); // 朝阳坡亮、背阳坡暗（明暗差 ~3×）
  vec3 nightMult = nightBase + vec3(0.62, 0.78, 1.00) * (0.16 * moonSlope) * moonGate;
  // R37 晨昏修正：太阳一旦升到地平线上（warm>0），其直射光已点亮山体，
  // 夜乘数须让位 —— 否则日出瞬间的红金雪冠被 ~0.1 的夜乘数压成近黑
  //（物理上「日照金山」恰发生在太阳 1-2° 时）。深夜 warm=0，夜乘数原样。
  float nightEff = night * (1.0 - 0.85 * uWarmF);
  vec3 landCol = landDay * mix(vec3(1.0), nightMult, nightEff);
  landCol += (lm - 0.5) * mix(0.012, 0.04, uDayF);     // 斑驳：白天严格=旧值 0.04，夜间减到 0.012
  landCol += vec3(0.012, 0.040, 0.060) * uDayF * 0.45; // 白天冷调补光（不变）

  // —— 投影落位（Step C1/C2）：只作用陆地；影里留 30% 天光 + 透冷调 ——
  // C2：①加重（0.38→0.30）；②随太阳高度渐显渐隐 —— 日出日落阴影淡入淡出。
  // 硬门限（uSunDir.y>0.02）是昼夜交替“啪”地开关的根因，改连续 fade。
  float shadowAmt = smoothstep(-0.01, 0.10, uSunDir.y) * step(0.005, uDayF);
  if (vWater < 0.5 && shadowAmt > 0.002) {
    float sh = terrainShadow(vWPos, uSunDir);
    landCol *= mix(1.0, mix(0.30, 1.0, sh), shadowAmt);
    landCol += vec3(0.010, 0.025, 0.045) * (1.0 - sh) * uDayF * shadowAmt; // 阴影透天光冷调
  }

  vec3 col = mix(landCol, waterCol, vWater);

  // —— 空气透视（指数雾）：海水轻吃雾保色，远山吃雾显空气感 ——
  // R36 · 远海收边：海面在到达 9200m 平面边缘（±4600m）前渐进融进雾色
  //（2600→4420m 到全雾），与 SkyAurora 下半球融雾两侧同色 —— 消灭
  //「海面切边 + 边缘外露亮青」的地平线假缝；近场水色不变。
  float dist = camDist;
  float fogF = 1.0 - exp(-uFogDensity * uFogDensity * dist * dist);
  float seaFar = smoothstep(2600.0, 4420.0, dist);
  float fogMix = mix(fogF, mix(fogF * 0.30, 1.0, seaFar), vWater);
  col = mix(col, uFogColor, clamp(fogMix, 0.0, 1.0));

  gl_FragColor = vec4(col, 1.0);
}
`

export default function WorldTerrain() {
  const { geo, mat } = useMemo(() => {
    const SIZE = 9200
    const SEG = 400 // round8：23m 单元（160k 顶点，启动多 ~2s，换近岸轮廓）
    const g = new THREE.PlaneGeometry(SIZE, SIZE, SEG, SEG)
    g.rotateX(-Math.PI / 2)
    const pos = g.attributes.position as THREE.BufferAttribute
    const land = new Float32Array(pos.count)
    const coast = new Float32Array(pos.count)
    const shore = new Float32Array(pos.count)
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i)
      const z = pos.getZ(i)
      const y = terrainSurfaceY(x, z)
      pos.setY(i, y)
      land[i] = landMask(x, z)
      coast[i] = coastT(x, z)
      // R36 岸距场：带符号最近岸距（负=海侧米数）。近岸阻尼/碎浪带/水线爬升共用；
      // 夹取 [-700,120]：只消费近岸段，内陆大值无意义且省精度。
      shore[i] = Math.max(-700, Math.min(120, shoreSigned(x, z)))
    }
    g.setAttribute('aLand', new THREE.BufferAttribute(land, 1))
    g.setAttribute('aCoast', new THREE.BufferAttribute(coast, 1))
    g.setAttribute('aShore', new THREE.BufferAttribute(shore, 1))
    g.computeVertexNormals()

    // Step C1 高度纹理：256² 烘焙（半浮点最近邻采样，所有 WebGL2 / WebGL1 硬件通用，消除启动 1.5s 阻塞）
    const hg = bakeHeightGrid(256, SIZE)
    const hdata = new Uint16Array(hg.size * hg.size)
    for (let k = 0; k < hdata.length; k++) hdata[k] = THREE.DataUtils.toHalfFloat(hg.data[k])
    const htex = new THREE.DataTexture(hdata, hg.size, hg.size, THREE.RedFormat, THREE.HalfFloatType)
    htex.magFilter = THREE.NearestFilter
    htex.minFilter = THREE.NearestFilter
    htex.wrapS = htex.wrapT = THREE.ClampToEdgeWrapping
    htex.needsUpdate = true

    const u = {
      uTime: { value: 0 },
      uWind: { value: new THREE.Vector2(0, 1) },
      uCenter: { value: new THREE.Vector2(FARM_CENTER.x, FARM_CENTER.z) },
      uDayF: { value: 1 },
      uGlow: { value: 1 },
      uSunDir: { value: new THREE.Vector3(0, 1, 0) },
      uFogColor: { value: new THREE.Color('#040911') },
      uFogDensity: { value: 0.00013 }, // C4：默认值随 App 场景雾（逐帧覆盖，此处仅首帧）
      uHeightTex: { value: htex },
      uMoonDir: { value: new THREE.Vector3(0, 1, 0) },
      uWarmF: { value: 0 },
    }

    const m = new THREE.ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      uniforms: u,
      side: THREE.FrontSide,
      transparent: false,
      depthWrite: true,
      fog: false,
    })
    m.customProgramCacheKey = () => 'terrain-ocean-v5-r36'
    ;(m.userData as any).u = u
    return { geo: g, mat: m }
  }, [])

  useFrame((state) => {
    const uu = (mat.userData as any).u as {
      uTime: { value: number }
      uWind: { value: THREE.Vector2 }
      uDayF: { value: number }
      uGlow: { value: number }
      uSunDir: { value: THREE.Vector3 }
      uMoonDir: { value: THREE.Vector3 }
      uWarmF: { value: number }
      uFogColor: { value: THREE.Color }
      uFogDensity: { value: number }
    }
    uu.uTime.value = phaseT(state.clock.elapsedTime)
    const t = phaseT(state.clock.elapsedTime)
    const dayF = skyState.dayF
    const night = 1 - dayF
    const breathe = 0.5 + 0.5 * Math.sin(t * 0.55)
    const nightGlow = 0.14 + 0.10 * breathe
    uu.uGlow.value = dayF * 0.6 + night * nightGlow
    uu.uDayF.value = dayF
    uu.uSunDir.value.copy(skyState.sunDir)
    uu.uWarmF.value = skyState.warmF
    uu.uMoonDir.value.copy(skyState.moonDir)
    const { fromDeg } = windAt(useSim.getState().tHours)
    const th = (fromDeg * Math.PI) / 180
    uu.uWind.value.set(Math.sin(th), Math.cos(th))
    const scene = state.scene
    if (scene.fog && (scene.fog as THREE.FogExp2).isFogExp2) {
      uu.uFogColor.value.copy((scene.fog as THREE.FogExp2).color)
      uu.uFogDensity.value = (scene.fog as THREE.FogExp2).density
    }
  })

  return <mesh geometry={geo} material={mat} />
}
