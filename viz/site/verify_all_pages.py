#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态站质量门禁。

覆盖 15 个现役页面及站内附加 HTML，检查本地资源、链接/锚点、重复 ID、
基础可访问性、统一导航、JavaScript 语法、关键交互运行桩、离线依赖、安全头、
已删除模块残留、已知伪数据和关键页面的最终布局契约。
"""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
CORE_PAGES = [
    "index.html", "wake.html", "optimization.html", "solver.html",
    "dashboard.html", "array.html", "heatmap.html", "pod.html",
    "model.html", "power_tracking.html", "3d_farm.html",
    "3d_surface.html", "3d_volume.html", "interface.html", "overview.html",
]
EXPECTED_NAV = CORE_PAGES[:-1] + ["overview.html"]
EXTRA_PAGES = ["index_v2.html", "slides_823.html"]
BANNED_TEXT = {
    "aerodynamic_demo.html": "已删除模块残留",
    "windrose.html": "已下线风玫瑰页面残留",
    "7000吨": "无来源碳减排旧文案",
    "340万元": "无来源金额旧文案",
    "42.5%": "已废弃阵列占位值",
    "PPO多种子MAE稳定性": "未执行多模型种子评测",
    "5种子 MAE": "未执行多模型种子评测",
}
BANNED_CODE = {
    "i < 3 ? 1460": "3D 风场硬编码伪功率",
    "920 : 660": "3D 风场硬编码伪功率",
    "type: 'path'": "Plotly 非法仪表路径",
    'type: "path"': "Plotly 非法仪表路径",
}


class RefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.ids = []
        self.accessibility_issues = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if "id" in attr:
            self.ids.append(attr["id"])
        if tag == "img" and not attr.get("alt", "").strip():
            self.accessibility_issues.append(f"img 缺少非空 alt：{attr.get('src', '<unknown>')}")
        if tag == "iframe" and not attr.get("title", "").strip():
            self.accessibility_issues.append(f"iframe 缺少 title：{attr.get('src', '<unknown>')}")
        if tag == "a" and attr.get("target") == "_blank" and "noopener" not in attr.get("rel", "").split():
            self.accessibility_issues.append(f"target=_blank 缺少 rel=noopener：{attr.get('href', '<unknown>')}")
        for key in ("href", "src", "poster"):
            if key in attr:
                self.refs.append((tag, key, attr[key]))


def clean_ref(ref):
    return ref.split("#", 1)[0].split("?", 1)[0]


def is_ignored_ref(ref):
    return not ref or ref.startswith(("#", "data:", "mailto:", "javascript:"))


def node_check(source, label, module=False):
    suffix = ".mjs" if module else ".js"
    with tempfile.NamedTemporaryFile("w", suffix=suffix, encoding="utf-8", delete=False) as fh:
        fh.write(source)
        temp = Path(fh.name)
    try:
        result = subprocess.run(["node", "--check", str(temp)], capture_output=True, text=True)
    finally:
        temp.unlink(missing_ok=True)
    if result.returncode:
        return f"{label} JavaScript 语法错误：{result.stderr.strip()}"
    return None


def main():
    errors = []
    warnings = []
    print("=" * 68)
    print("风电场偏航优化静态站质量门禁")
    print("=" * 68)

    for name in CORE_PAGES + EXTRA_PAGES:
        if not (SITE / name).exists():
            errors.append(f"缺少页面：{name}")

    # 全部 HTML 的 href/src/poster 与离线依赖。
    for path in sorted(SITE.glob("*.html")):
        content = path.read_text(encoding="utf-8")
        parser = RefParser()
        parser.feed(content)
        duplicate_ids = sorted(key for key, count in Counter(parser.ids).items() if count > 1)
        if duplicate_ids:
            errors.append(f"{path.name} 含重复 id：{duplicate_ids}")
        for issue in parser.accessibility_issues:
            errors.append(f"{path.name} 可访问性错误：{issue}")
        required_metadata = {
            '<html lang="zh-CN">': "html lang=zh-CN",
            'name="viewport"': "viewport",
            'charset="UTF-8"': "UTF-8 charset",
        }
        for token, label in required_metadata.items():
            if token not in content:
                errors.append(f"{path.name} 缺少页面元数据：{label}")
        if not re.search(r"<title>\s*\S.*?</title>", content, re.S | re.I):
            errors.append(f"{path.name} 缺少非空 title")
        for tag, attr, ref in parser.refs:
            if attr == "href" and "#" in ref and not ref.startswith(
                ("http://", "https://", "mailto:", "javascript:")
            ):
                base, fragment = ref.split("#", 1)
                fragment = unquote(fragment)
                target = (path.parent / (clean_ref(base) or path.name)).resolve()
                if fragment and target.suffix.lower() in {".html", ".htm"} and target.exists():
                    target_ids = set(re.findall(r'\bid=["\']([^"\']+)["\']', target.read_text(encoding="utf-8")))
                    if fragment not in target_ids:
                        errors.append(f"{path.name} 的页内锚点失效：{ref}")
            if is_ignored_ref(ref):
                continue
            if ref.startswith(("http://", "https://")):
                errors.append(f"{path.name} 仍依赖外部资源：{ref}")
                continue
            target = (SITE / clean_ref(ref)).resolve()
            if not target.exists():
                errors.append(f"{path.name} 的 {tag}[{attr}] 死链：{ref}")

        if path.name in CORE_PAGES + ["index_v2.html"] and 'css/unified-glass.css' not in content:
            errors.append(f"{path.name} 未加载全站精密玻璃母版")

        for text, reason in BANNED_TEXT.items():
            if text in content:
                errors.append(f"{path.name} 含 {reason}：{text}")
        if re.search(r"[\U0001F300-\U0001FAFF▶⏸✓✅⚠❌⟳]", content):
            errors.append(f"{path.name} 含装饰性 Emoji 或播放符号")

        illegal_latex = set(re.findall(r"\\(?:nwarrow|nearrow|le|text|gamma|approx)\b", content))
        if illegal_latex:
            warnings.append(f"{path.name} 发现未编译 LaTeX：{sorted(illegal_latex)}")

        # 仅检查无 src、无特殊 MIME type 的内联 JavaScript。
        scripts = re.findall(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", content, re.S | re.I)
        for index, (attrs, body) in enumerate(scripts, 1):
            if re.search(r"\bsrc\s*=", attrs, re.I):
                continue
            type_match = re.search(r"\btype\s*=\s*['\"]([^'\"]+)", attrs, re.I)
            script_type = type_match.group(1).lower() if type_match else ""
            if script_type in {"importmap", "application/json"} or not body.strip():
                continue
            issue = node_check(body, f"{path.name} 内联脚本 #{index}", module=script_type == "module")
            if issue:
                errors.append(issue)

    # 15 页统一导航：顺序、数量和目标必须完全一致。
    for name in CORE_PAGES:
        content = (SITE / name).read_text(encoding="utf-8")
        nav_match = re.search(r'<div class="t-nav-links".*?</div>\s*</div>', content, re.S)
        if not nav_match:
            errors.append(f"{name} 缺少统一模块导航")
            continue
        links = re.findall(r'href="([^"]+\.html)"', nav_match.group(0))
        if links != EXPECTED_NAV:
            errors.append(f"{name} 导航集合或顺序不一致：{links}")

    # 外部项目脚本语法；vendor 库只校验文件存在与固定版本。
    for path in sorted((SITE / "assets" / "js").glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for text, reason in BANNED_CODE.items():
            if text in source:
                errors.append(f"{path.relative_to(SITE)} 含 {reason}：{text}")
        issue = node_check(source, str(path.relative_to(SITE)), module=path.name == "farm.js")
        if issue:
            errors.append(issue)

    # 关键交互运行桩：首页数字风洞鼠标耦合，以及尾流 0°/+25° 数据与三幅 Plotly 图。
    runtime_checks = (
        ("首页数字风洞", SITE / "test_home_runtime.js"),
        ("尾流交互", SITE / "test_wake_runtime.js"),
    )
    for label, script in runtime_checks:
        runtime = subprocess.run(["node", str(script)], capture_output=True, text=True)
        if runtime.returncode:
            errors.append(f"{label}运行桩失败：" + (runtime.stderr.strip() or runtime.stdout.strip()))

    # CSS 的 url() 资源与远程 @import。
    for path in sorted((SITE / "css").glob("*.css")):
        content = path.read_text(encoding="utf-8")
        if re.search(r"https?://", content):
            errors.append(f"{path.relative_to(SITE)} 仍含远程 CSS 依赖")
        for ref in re.findall(r"url\(['\"]?([^)'\"]+)", content):
            if is_ignored_ref(ref) or ref.startswith(("http://", "https://")):
                continue
            if not (path.parent / clean_ref(ref)).resolve().exists():
                errors.append(f"{path.relative_to(SITE)} 的 url() 死链：{ref}")

    # 尾流页必须保持“控制在上、三张动态图同排、Nature 图沉底”。
    wake = (SITE / "wake.html").read_text(encoding="utf-8")
    order_tokens = ['id="yawSlider"', 'id="fieldPlot"', 'fig1_tandem_yaw.png']
    positions = [wake.find(token) for token in order_tokens]
    if any(p < 0 for p in positions) or positions != sorted(positions):
        errors.append(f"wake.html 动静态顺序错误：{dict(zip(order_tokens, positions))}")
    glass_css = (SITE / "css" / "unified-glass.css").read_text(encoding="utf-8")
    for token in ("grid-template-columns: repeat(3, minmax(0, 1fr))", "#00441b", "#f7fcfd"):
        if token not in glass_css and token not in wake:
            errors.append(f"尾流统一布局或绿色色阶缺失：{token}")

    # 首页主标题两行只以颜色区分，必须共用全站宋体标题栈。
    for name in ("index.html", "index_v2.html"):
        homepage = (SITE / name).read_text(encoding="utf-8")
        if '--v-display: "Songti SC Black"' not in homepage:
            errors.append(f"{name} 主标题变量未使用 Songti SC Black 字体栈")
        if not re.search(
            r"\.hero-title span\.hl\s*\{[^}]*font-family:\s*var\(--v-display\)",
            homepage,
            re.S,
        ):
            errors.append(f"{name} 蓝色主标题行未继承统一标题字体")
        for token in (
            "rgba(138,214,190,0.24)",
            "rgba(194,232,216,0.34)",
            "rgba(140,211,188,0.20)",
            "'104,176,151' : '128,183,168'",
        ):
            if token not in homepage:
                errors.append(f"{name} 缺少清新薄荷 Hero 光效：{token}")
        for stale_tone in ("168,120,23", "168, 120, 23", "45,117,105", "45, 117, 105"):
            if stale_tone in homepage:
                errors.append(f"{name} 仍含偏褐或过暗的旧 Hero 光效：{stale_tone}")
        for token in (
            'id="windStage"',
            'id="farm-stage-canvas"',
            'class="stage-flow-rail"',
            "stage.addEventListener('pointermove', setPointer)",
            "function turbinePositions(sceneBottom)",
            "prefers-reduced-motion: reduce",
        ):
            if token not in homepage:
                errors.append(f"{name} 缺少数字风洞样板或鼠标耦合：{token}")
        if 'class="terminal-panel"' in homepage or "Math.max(320, power)" in homepage:
            errors.append(f"{name} 仍含旧遥测卡片或无来源动态功率读数")
    for token in (".hero-title .hl", "font-family: var(--shell-serif) !important"):
        if token not in glass_css:
            errors.append(f"首页主标题共享字体覆盖缺失：{token}")

    # 逐页审计全部 Nature 出版证据：桌面同页横排、统一图窗等高，窄屏再响应式回落。
    nature_layouts = {
        "wake.html": (2, 2),
        "heatmap.html": (2, 2),
        "power_tracking.html": (2, 2),
        "pod.html": (3, 3),
        "array.html": (4, 4),
        "model.html": (1, 1),
        "overview.html": (1, 1),
    }
    for name, (expected_images, columns) in nature_layouts.items():
        page = (SITE / name).read_text(encoding="utf-8")
        image_tags = re.findall(r'<img\b[^>]*src=["\'][^"\']*assets/img/nature/[^"\']+\.png["\'][^>]*>', page)
        card_count = len(re.findall(r'class=["\'][^"\']*\bnature-card\b[^"\']*["\']', page))
        if len(image_tags) != expected_images or card_count != expected_images:
            errors.append(
                f"{name} Nature 图/卡数量应为 {expected_images}，实际图片 {len(image_tags)}、卡片 {card_count}"
            )
        if f"nature-row--{columns}" not in page:
            errors.append(f"{name} 缺少桌面 {columns} 列 Nature 横排容器")
        if any("style=" in tag for tag in image_tags):
            errors.append(f"{name} Nature 图片仍有覆盖统一等高规则的内联样式")

    for token in (
        ".nature-row",
        ".nature-card > img",
        "height: var(--nature-media-height) !important",
        "object-fit: contain",
        "grid-template-columns: repeat(4, minmax(0, 1fr))",
        ".nature-row--3, .nature-row--4",
        ".dir-grid",
    ):
        if token not in glass_css:
            errors.append(f"Nature 等高横排或首页等宽网格样式缺失：{token}")

    # Dashboard FIG.C / FIG.D 同高，且不再混入无关控制室配图。
    dashboard = (SITE / "dashboard.html").read_text(encoding="utf-8")
    if dashboard.count('class="dash-panel"') != 2 or "wind_farm_control.jpg" in dashboard:
        errors.append("dashboard.html FIG.C/FIG.D 未完成等高双栏或仍含多余配图")
    if 'height: 300px; max-height: none' not in dashboard:
        errors.append("dashboard.html FIG.D JSON 主视窗高度未与 FIG.C 对齐")

    # 下线页面专用的前端数据和站点图片副本不得重新混入发布包；根目录科研留档不受影响。
    site_data = (SITE / "assets/data.js").read_text(encoding="utf-8")
    for retired_key in ('"windrose_opt"', '"array_rose"'):
        if retired_key in site_data:
            errors.append(f"data.js 仍含下线页面专用前端导出：{retired_key}")
    for retired_asset in (
        SITE / "assets/img/nature/fig7_windrose.png",
        SITE / "assets/img/nature/fig7_windrose.pdf",
    ):
        if retired_asset.exists():
            errors.append(f"下线页面专用站点副本仍存在：{retired_asset.relative_to(ROOT)}")

    # 已无页面消费的旧卡片图表、背景探测和样式文件不得重新进入发布包。
    obsolete_frontend_files = (
        SITE / "assets/js/app.js",
        SITE / "assets/js/bg-video.js",
        SITE / "assets/js/charts.js",
        SITE / "css/dashboard.css",
        SITE / "css/media.css",
    )
    for obsolete in obsolete_frontend_files:
        if obsolete.exists():
            errors.append(f"发布包仍含无入口旧前端文件：{obsolete.relative_to(ROOT)}")

    # 模型验证主图收窄、残差证据放大，并由统计卡填满等高内容区。
    model_page = (SITE / "model.html").read_text(encoding="utf-8")
    for token in (
        "grid-template-columns: minmax(0, 2fr) minmax(0, 3fr)",
        'class="plot-column plot-primary"',
        'class="plot-column plot-residual"',
        ".plot-residual .stat-grid",
    ):
        if token not in model_page:
            errors.append(f"model.html FIG.A/FIG.B 协调比例样式缺失：{token}")

    # 尾流页标题必须复用其余子页的统一玻璃 Hero，并与 1240px 正文网格居中对齐。
    if '<header class="v-pg-hero t-container">' not in wake or 'class="wake-hero"' in wake:
        errors.append("wake.html 大标题区域未与其余子页统一")
    for token in ("margin: 0 auto !important", "padding-left: 32px", "padding-right: 32px"):
        if token not in glass_css:
            errors.append(f"统一 Hero 容器未与正文网格居中对齐：{token}")

    # 依赖必须本地锁定。
    required_vendor = [
        SITE / "assets/vendor/plotly/plotly-2.35.2.min.js",
        SITE / "assets/vendor/three/three.module.js",
        SITE / "assets/vendor/three/addons/controls/OrbitControls.js",
        SITE / "assets/fonts/geist/Geist-Variable.woff2",
        SITE / "assets/fonts/geist/GeistMono-Variable.woff2",
    ]
    for path in required_vendor:
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"缺少本地离线依赖：{path.relative_to(ROOT)}")

    # Cloudflare Pages 基础安全响应头与固定版本依赖缓存策略。
    headers_path = SITE / "_headers"
    if not headers_path.exists():
        errors.append("缺少 Cloudflare Pages 安全响应头文件：site/_headers")
    else:
        headers = headers_path.read_text(encoding="utf-8")
        for token in (
            "X-Content-Type-Options: nosniff",
            "Referrer-Policy: strict-origin-when-cross-origin",
            "Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()",
            "X-Frame-Options: SAMEORIGIN",
            "Cache-Control: public, max-age=31536000, immutable",
        ):
            if token not in headers:
                errors.append(f"site/_headers 缺少安全或缓存规则：{token}")

    print(f"扫描完成：{len(errors)} 个阻断错误，{len(warnings)} 个警告。")
    for message in warnings:
        print("警告：" + message)
    for message in errors:
        print("错误：" + message)
    if errors:
        print("=" * 68)
        print("质量门禁失败。")
        return 1
    print("15 个现役页面及附加页面通过资源、导航、脚本和离线检查。")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
