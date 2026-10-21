/* oxlint-disable react/immutability -- 纹理工件初始化与 uniforms 帧循环 mutate（docs/08 D2） */
import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { makeSkyCanvas } from './skyTexture'
import { skyState } from './lightState'
import { phaseT } from './freeze.ts'

const VERT = /* glsl */ `
varying vec3 vDir;
void main() {
  vDir = normalize(position);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`

// 任务#6 天空层：星野/银河由种子化程序纹理工件（skyTexture.ts，canvas 烘焙，
// 完全可复现，不再依赖位图资产）提供；着色器层负责地平线冰青、极光与昼夜过渡
// （uDay/uSunDir 由 LightRig 的 skyState 驱动：白天星光/极光淡出 + 日轮）。
const FRAG = /* glsl */ `
precision highp float;
varying vec3 vDir;
uniform float uTime;
uniform float uDay;
uniform vec3 uSunDir;
uniform vec3 uMoonDir;
uniform vec3 uFogColor;
uniform sampler2D uSkyTex;
uniform float uWarmF; // R37 太阳色温（0=白 1=红，仰角连续）：日轮/暖晕共用

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
             mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 4; i++) { v += a * noise(p); p *= 2.03; a *= 0.52; }
  return v;
}
float fbm3(vec2 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 3; i++) { v += a * noise(p); p *= 2.03; a *= 0.52; }
  return v / 0.876;
}

void main() {
  vec3 d = normalize(vDir);
  float h = d.y;                       // 仰角 sin
  float az = atan(d.x, -d.z);          // 方位：北=0、东=+π/2（屏幕右）

  // 原图底色：地平线青霭 → 高天深蓝
  vec3 col = mix(vec3(0.062, 0.175, 0.230), vec3(0.010, 0.042, 0.075), smoothstep(0.0, 0.16, h));
  col = mix(col, vec3(0.002, 0.008, 0.018), smoothstep(0.12, 0.55, h));

  // 真实天空纹理：球面方向 → 2:1 equirectangular UV。
  // 只在上半球混入，地平线仍由原图冰青雾化层控制，保证色调不漂移。
  vec2 skyUv = vec2(0.5 + atan(d.x, -d.z) / 6.28318530718,
                    0.5 - asin(clamp(d.y, -1.0, 1.0)) / 3.14159265359);
  vec3 photoSky = texture2D(uSkyTex, skyUv).rgb;
  photoSky *= vec3(0.82, 0.91, 1.0);
  float photoMask = smoothstep(0.075, 0.30, h) * (1.0 - uDay * 0.78);
  col = mix(col, photoSky, photoMask * 0.86);

  // 地平线宽亮带（原图发光地平线：亮核 + 宽裙）
  // R37b：带色在太阳方位扇区让位于太阳色温——低空气溶胶的前向散射随光源颜色，
  // 日出时太阳扇区的地平带应暖化而非冰青；否则冰青带在红日下方叠出 G/B 削顶，
  // 把初升红日洗成白斑（5:30 取证：日轮区 G/B 双通道 1.0 饱和）。离开太阳扇区
  // 或正午（uWarmF=0）时与原带完全一致，冰青审美零改动。
  float band1 = pow(clamp(1.0 - abs(h), 0.0, 1.0), 13.0);
  float band2 = pow(clamp(1.0 - abs(h), 0.0, 1.0), 5.0);
  vec2 sdHxz = normalize(uSunDir.xz + vec2(1e-5, 0.0));
  float azCone = pow(clamp(dot(normalize(d.xz + vec2(1e-5, 0.0)), sdHxz), 0.0, 1.0), 3.0);
  float wAz = uWarmF * azCone; // 1 = 日出时刻正对太阳的地平扇区
  col += mix(vec3(0.16, 0.44, 0.55) * 1.35, vec3(0.72, 0.26, 0.08) * 0.90, wAz) * band1;
  col += mix(vec3(0.05, 0.16, 0.22) * 0.55, vec3(0.55, 0.20, 0.07) * 0.55, wAz) * band2;

  // 左上冷光辉（基准图左侧天际亮斑，含月亮意象，克制）。
  // 必须限制在上半球：无人机俯冲时会看到天空球内侧的下半球，
  // 若直接 exp(-h) 会在 h<0 时指数爆炸，产生异常白色光团。
  float upperHemisphere = smoothstep(-0.04, 0.10, h);
  float glowL = exp(-pow((az + 0.42) * 3.4, 2.0)) * exp(-max(h, 0.0) * 14.0) * upperHemisphere;
  col += vec3(0.55, 0.72, 0.85) * glowL * 0.14;

  // 顶部全宽柔光（原图标题后背景亮青雾），同样只作用于上半球。
  col += vec3(0.06, 0.17, 0.24) * pow(clamp(1.0 - abs(h), 0.0, 1.0), 3.0) * exp(-max(h, 0.0) * 2.4) * upperHemisphere * 0.38;

  // 极光带：保留原图方向与冰青色，只作为真实云银河纹理之上的动态叠层
  // 夜间生机增强：极光随夜色呼吸，强度 ×(1-uDay)，并加入慢速正弦呼吸
  float night = 1.0 - uDay;
  float sect = smoothstep(0.22, 0.86, cos(az - 0.72));
  float bandC = 0.08 + 0.036 * (az - 0.62);
  float band = smoothstep(0.075, 0.008, abs(h - bandC));
  float rays = fbm(vec2(az * 17.0, h * 42.0 - uTime * 0.06));
  float drift = fbm(vec2(az * 3.0 + uTime * 0.015, h * 4.0));
  float breathe = 0.85 + 0.35 * sin(uTime * 0.08 + az * 2.3) + 0.15 * sin(uTime * 0.21 + az * 5.7);
  float aur = band * sect * smoothstep(0.26, 0.70, drift) * (0.36 + 1.05 * rays) * breathe;
  // 夜间极光强度提升，白天几乎消失
  aur *= (0.25 + 0.85 * night);
  vec3 aurCol = mix(vec3(0.40, 0.84, 0.95), vec3(0.14, 0.48, 0.84), clamp((h - 0.02) * 10.0, 0.0, 1.0));
  // 夜间再叠一层更冷的青白，呼吸感更强
  vec3 aurColNight = mix(aurCol, vec3(0.55, 0.92, 1.0), 0.35 * night * (0.6 + 0.4 * sin(uTime * 0.12)));
  col += aurColNight * aur * (1.45 + night * 0.9);
  col += aurCol * sect * exp(-abs(h) * 11.0) * (0.16 + night * 0.22) * breathe;

  // 纹理自带真实星场，保留少量动态星点让数字孪生画面仍有呼吸感
  // 夜间生机：星点闪烁更快、更多层次，且随夜色呼吸亮度
  vec2 sp = d.xz / max(0.18, d.y + 0.28);
  vec2 cell = floor(sp * 300.0);
  float star = step(0.9880, hash(cell));
  float tw = 0.55 + 0.45 * sin(uTime * (1.6 + night * 0.8) + hash(cell + 7.7) * 40.0);
  col += vec3(0.70, 0.86, 1.0) * star * tw * smoothstep(0.03, 0.22, h) * (0.20 + night * 0.18) * (1.0 - uDay * 0.3);
  // 第二层更密更暗的微星：夜空星辰数量增加，但单颗更弱，不抢线稿
  vec2 cell2 = floor(sp * 620.0 + 31.7);
  float star2 = step(0.9915, hash(cell2));
  float tw2 = 0.5 + 0.5 * sin(uTime * (1.1 + night * 0.7) + hash(cell2 + 3.3) * 55.0);
  col += vec3(0.66, 0.82, 1.0) * star2 * tw2 * smoothstep(0.02, 0.20, h) * (0.11 + night * 0.12) * (1.0 - uDay * 0.2);
  // 第三层：夜间极稀疏高亮星，偶发闪烁，增加“生机”
  vec2 cell3 = floor(sp * 180.0 + 9.3);
  float star3 = step(0.9965, hash(cell3));
  float tw3 = pow(0.5 + 0.5 * sin(uTime * 2.4 + hash(cell3 + 19.1) * 70.0), 3.0);
  col += vec3(0.85, 0.95, 1.0) * star3 * tw3 * smoothstep(0.04, 0.24, h) * 0.32 * night;

  // 极光带整体随白昼淡出（物理上不严格，但"克制"优先：白天不抢戏）
  col -= col * 0.0; // no-op 保持行号稳定
  // 白天：冰青天幕渐变 + 日轮与晕（不引入新色相）
  vec3 dayCol = mix(vec3(0.086, 0.165, 0.239), vec3(0.290, 0.451, 0.565), smoothstep(0.02, 0.55, h));
  col = mix(col, dayCol, uDay * 0.86);
  // —— R37b 视差修正：日/月盘的视方向 = 相机沿真方向的球面命中点 ——
  // 天体在无穷远，但天空球只有 6800m 且以世界原点定向：旧版盘心画在
  // 「原点→天体」方向上，相机离原心 1~4.6km 时视位置偏移可达 ~12°，
  // 日轮/月轮会跑出锁定机位画面（太阳锁定机位实测拍不到日轮的根因）。
  vec3 sdSun = normalize(uSunDir);
  float bS = dot(cameraPosition, sdSun);
  float tS = sqrt(max(bS * bS - dot(cameraPosition, cameraPosition) + 46240000.0, 0.0)) - bS; // 6800²
  vec3 sunDirV = normalize(cameraPosition + sdSun * tS);
  vec3 sdMoon = normalize(uMoonDir);
  float bM = dot(cameraPosition, sdMoon);
  float tM = sqrt(max(bM * bM - dot(cameraPosition, cameraPosition) + 46240000.0, 0.0)) - bM;
  vec3 moonDirV = normalize(cameraPosition + sdMoon * tM);
  float sunDot = clamp(dot(d, sunDirV), 0.0, 1.0);
  // —— R37 日轮色温（连续物理）：初升红彤彤 → 金 → 白 ——
  // v1 的「白色日轮 + 时间窗暖晕」是错的：真实日轮颜色由仰角连续决定
  // （大气路径长 → 瑞利散射吃蓝 → 红）。uWarmF 随仰角连续变化，无开关。
  // 亮度门 sGate（太阳在地平线上）与 dayF 解耦：日轮是全天空最亮天体，
  // 刚跃出地平线时就应清晰可见（旧 ×uDay 在日出时刻只有 0.3，红日几乎不可见）；
  // 日落后 sGate→0，不会在夜间地平线残留鬼影。
  float sUp = normalize(uSunDir).y;
  float sGate = smoothstep(-0.017, 0.035, sUp);
  vec3 sunDiscCol = mix(vec3(0.92, 0.97, 1.0), vec3(1.08, 0.40, 0.15), uWarmF);
  col += sunDiscCol * pow(sunDot, 1400.0) * 1.35 * (1.0 - 0.28 * uWarmF) * sGate;
  col += vec3(0.32, 0.46, 0.58) * pow(sunDot, 14.0) * 0.16 * uDay;
  // 低角度大气消光暖晕：宽晕 + 内晕，随 uWarmF 连续（正午自动为 0，无需门）
  col += vec3(1.02, 0.50, 0.20) * pow(sunDot, 5.0) * uWarmF * 0.30 * (0.30 + 0.70 * sGate);
  col += vec3(0.95, 0.44, 0.17) * pow(sunDot, 24.0) * uWarmF * 0.22 * (0.30 + 0.70 * sGate);

  // —— 明月（C3）：月轮 + 晕 + 远辉，随夜色渐显（night 门控，昼夜连续不断裂）——
  vec3 md = moonDirV; // R37b 视差修正后的月盘方向
  float moonDot = clamp(dot(d, md), 0.0, 1.0);
  float mDisc = smoothstep(0.99980, 0.99995, moonDot); // 月面（~0.6°）
  float limb = 0.75 + 0.25 * smoothstep(0.99980, 1.0, moonDot); // 临边昏暗
  vec3 moonWhite = vec3(0.92, 0.96, 1.0);
  col += moonWhite * mDisc * limb * 2.4 * night; // 明盘
  // 月海：两块暗斑（程序写意，不求精确环形山）
  float maria = smoothstep(0.45, 0.9, fbm(d.xy * 900.0 + md.xy * 130.0));
  col -= moonWhite * mDisc * maria * 0.35 * night;
  col += vec3(0.55, 0.70, 0.85) * pow(moonDot, 900.0) * 0.9 * night; // 内晕
  col += vec3(0.35, 0.52, 0.68) * pow(moonDot, 90.0) * 0.22 * night; // 外晕
  col += vec3(0.20, 0.32, 0.44) * pow(moonDot, 9.0) * 0.10 * night; // 远辉（月出月落的地平气息）

  // —— R39 · T4：云的绘制次序与日月统一 ——
  // R38 裁决：旧版「日轮在云之前（云掩日）、月盘在云之后（不掩月）」自相矛盾。
  // 统一为：日月都先画、云最后画 → **云可遮日月**（物理上云在前，法线朝向无关）；
  // 夜间云几乎不可见（×uDay），星野/极光/月盘不受影响。
  // —— R36 · 白昼薄卷云（coastal_3d_v2 sky.ts 云层投影的克制版）——
  // 虚拟平面投影 + 双尺度 fbm + 向阳采样 shading（云不是贴片，有受光方向）；
  // 覆盖率低、昼间渐显、夜间几乎不可见（不抢星野/极光/日轮）。
  if (h > 0.035) {
    vec2 cuv = d.xz / (h + 0.10) * 0.55 + vec2(uTime * 0.0045, uTime * 0.0016);
    float c1 = fbm(cuv * 1.15);
    float c2 = fbm3(cuv * 3.4 + 11.0);
    float cov = smoothstep(0.55, 0.78, c1 * 0.72 + c2 * 0.38);
    float c1s = fbm(cuv * 1.15 + normalize(uSunDir).xz * 0.10); // 向太阳采样
    float shade = clamp((c1s - c1) * 5.0, -1.0, 1.0);
    vec3 cloudCol = mix(vec3(0.50, 0.60, 0.68), vec3(0.76, 0.84, 0.90), 0.5 + 0.5 * shade);
    cloudCol += vec3(0.55, 0.52, 0.47) * pow(sunDot, 10.0) * 0.25; // 云际微暖反光（极弱）
    float hf = smoothstep(0.035, 0.16, h); // 地平线附近淡出，不糊极光带
    col = mix(col, cloudCol, cov * hf * uDay * 0.42);
  }

  // —— R36 · 下半球融雾：地平线以下渐变到场景雾色 ——
  // 海面已在 4420m 外全雾（WorldTerrain 远海收边）；天空下半球以同色接住，
  // 两侧同色 → 9200m 平面边缘不可见（消灭「第二地平线」亮带）。
  // 只作用 h<0.02，不影响上半球极光/星野/日轮/月轮。
  col = mix(col, uFogColor, 1.0 - smoothstep(-0.07, 0.02, h));

  gl_FragColor = vec4(col, 1.0);
}
`

export default function SkyAurora() {
  const mat = useRef<THREE.ShaderMaterial>(null!)
  const skyTexture = useMemo(() => {
    const tx = new THREE.CanvasTexture(makeSkyCanvas())
    tx.colorSpace = THREE.SRGBColorSpace
    tx.anisotropy = 4
    tx.wrapS = THREE.RepeatWrapping
    return tx
  }, [])
  const uniforms = useMemo(() => ({
    uTime: { value: 0 }, uDay: { value: 0 },
    uSunDir: { value: new THREE.Vector3(0, 1, 0) },
    uMoonDir: { value: new THREE.Vector3(0, 1, 0) },
    uFogColor: { value: new THREE.Color('#040911') },
    uSkyTex: { value: skyTexture },
    uWarmF: { value: 0 },
  }), [skyTexture])

  useFrame((state) => {
    if (!mat.current) return
    const u = mat.current.uniforms
    u.uTime.value = phaseT(state.clock.elapsedTime)
    u.uDay.value = skyState.dayF
    u.uSunDir.value.copy(skyState.sunDir)
    u.uMoonDir.value.copy(skyState.moonDir)
    u.uWarmF.value = skyState.warmF
    // R36：下半球融雾与场景雾同色（LightRig 逐帧驱动 scene.fog）
    const fog = state.scene.fog
    if (fog && (fog as THREE.FogExp2).isFogExp2) {
      ;(u.uFogColor.value as THREE.Color).copy((fog as THREE.FogExp2).color)
    }
  })

  return (
    <mesh frustumCulled={false}>
      <sphereGeometry args={[6800, 48, 28]} />
      <shaderMaterial
        ref={mat}
        vertexShader={VERT}
        fragmentShader={FRAG}
        uniforms={uniforms}
        side={THREE.BackSide}
        depthWrite={false}
        fog={false}
      />
    </mesh>
  )
}
