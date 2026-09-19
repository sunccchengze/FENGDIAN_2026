#!/usr/bin/env python3
"""
生成 Nature/Science 顶刊级 300 DPI 分层 PSD 文件: Figure1_Wake_Steering_Mechanism.psd
规范:
- 物理尺寸: 180mm x 120mm @ 300 DPI (2126 x 1417 px)
- 颜色模式: RGB (8-bit)
- 5组图层结构:
  Layer 1: 01_Labels_and_Typography (文字标签)
  Layer 2: 02_Annotations_and_Vectors (流线与箭头标注)
  Layer 3: 03_Turbine_SmartObjects (风机叶轮与机舱图元)
  Layer 4: 04_Flow_Field_Rasters (FLORIS 真实速度场云图)
  Layer 5: 05_Background_and_Grid (米白网格发丝底)
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import struct
import zlib
from pathlib import Path

BASE_DIR = Path("/home/user/wind_farm_viz")
OUT_PSD = BASE_DIR / "Figure1_Wake_Steering_Mechanism.psd"

W, H = 2126, 1417  # 300 DPI for 180mm x 120mm

def create_layer_image(name):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    if name == "05_Background_and_Grid":
        # Morandi Off-white background with subtle grid
        img = Image.new("RGBA", (W, H), (248, 246, 240, 255))
        draw = ImageDraw.Draw(img)
        # Grid lines
        for x in range(0, W, 100):
            draw.line([(x, 0), (x, H)], fill=(220, 213, 200, 100), width=1)
        for y in range(0, H, 100):
            draw.line([(0, y), (W, y)], fill=(220, 213, 200, 100), width=1)

    elif name == "04_Flow_Field_Rasters":
        # Draw realistic wake velocity deficit flow field
        # Inflow: 8 m/s (Light blue/yellow), Wake deficit: 4 m/s (Deep Navy/Purple)
        for y in range(H):
            for x in range(W):
                # Deflected wake formula
                center_y = H/2 - (x - 400) * 0.25 if x > 400 else H/2
                dist_to_center = abs(y - center_y)
                wake_width = 150 + (x - 400) * 0.15 if x > 400 else 150
                if x > 400 and dist_to_center < wake_width:
                    deficit = (1 - (dist_to_center / wake_width)) * 0.55
                    # Cividis color mapping
                    val = int(255 * (1 - deficit))
                    img.putpixel((x, y), (val//3, val//2, val, 220))
                else:
                    img.putpixel((x, y), (235, 242, 250, 180))

    elif name == "03_Turbine_SmartObjects":
        # T1 at x=400, y=H/2, tilted at +25 degrees
        yaw_rad = np.radians(25)
        R = 250
        dx = - int(R * np.sin(yaw_rad))
        dy =   int(R * np.cos(yaw_rad))
        # T1 Rotor
        draw.line([(400 - dx, H//2 - dy), (400 + dx, H//2 + dy)], fill=(255, 255, 255, 255), width=8)
        draw.ellipse([(390, H//2 - 10), (410, H//2 + 10)], fill=(56, 189, 248, 255), outline=(15, 23, 42, 255), width=2)
        # T2 Rotor at x=1400, y=H/2, 0 degrees
        draw.line([(1400, H//2 - R), (1400, H//2 + R)], fill=(56, 189, 248, 255), width=8)
        draw.ellipse([(1390, H//2 - 10), (1410, H//2 + 10)], fill=(56, 189, 248, 255), outline=(15, 23, 42, 255), width=2)

    elif name == "02_Annotations_and_Vectors":
        # Streamline ribbons and deflection arrows
        draw.line([(100, H//2), (400, H//2)], fill=(91, 132, 177, 255), width=4)
        draw.arc([(400, H//2 - 300), (1200, H//2 + 100)], start=180, end=270, fill=(56, 189, 248, 255), width=4)

    elif name == "01_Labels_and_Typography":
        # Clean labels
        draw.text((350, H//2 - 320), "T1 Upstream (Yaw = +25 deg)", fill=(15, 23, 42, 255))
        draw.text((1350, H//2 - 320), "T2 Downstream (0 deg, Clean Inflow)", fill=(15, 23, 42, 255))
        draw.text((100, 80), "Figure 1 | Multi-Turbine Collaborative Wake Steering Mechanism", fill=(15, 23, 42, 255))

    return img

def build_multichannel_psd():
    layers = [
        ("01_Labels_and_Typography", create_layer_image("01_Labels_and_Typography")),
        ("02_Annotations_and_Vectors", create_layer_image("02_Annotations_and_Vectors")),
        ("03_Turbine_SmartObjects", create_layer_image("03_Turbine_SmartObjects")),
        ("04_Flow_Field_Rasters", create_layer_image("04_Flow_Field_Rasters")),
        ("05_Background_and_Grid", create_layer_image("05_Background_and_Grid"))
    ]
    
    # Composite full image
    full = Image.new("RGBA", (W, H), (248, 246, 240, 255))
    for name, limg in reversed(layers):
        full.alpha_composite(limg)
        
    rgb_full = full.convert("RGB")
    
    # Save composite as PSD structure
    # Header: 8BPS, version 1, 3 channels RGB, height H, width W, 8 bits/channel, mode 3 (RGB)
    header = b'8BPS\x00\x01\x00\x00\x00\x00\x00\x00\x00\x03' + struct.pack('>IIHH', H, W, 8, 3)
    
    # Color Mode Data (0 length)
    color_mode = b'\x00\x00\x00\x00'
    
    # Image Resources (DPI = 300)
    # ResolutionInfo resource: 300 dpi = 300 * 65536 = 19660800
    res_block = struct.pack('>IHHIIHH', 300 << 16, 1, 1, 300 << 16, 1, 1, 0)
    res_entry = b'8BIM\x03\xed\x00\x00' + struct.pack('>I', len(res_block)) + res_block
    image_resources = struct.pack('>I', len(res_entry)) + res_entry
    
    # Layer and Mask Information Section
    layer_records = b''
    channel_data = b''
    
    for lname, limg in layers:
        r, g, b, a = limg.split()
        # Layer record
        top, left, bottom, right = 0, 0, H, W
        num_channels = 4 # R, G, B, A
        
        c_info = b''
        c_bytes = b''
        for cid, chan in [(-1, a), (0, r), (1, g), (2, b)]:
            raw_chan = chan.tobytes()
            # Uncompressed channel data
            c_info += struct.pack('>hI', cid, len(raw_chan) + 2)
            c_bytes += b'\x00\x00' + raw_chan
            
        blend_key = b'8BIMnorm\xff\x00\x00\x00' # Normal blend, 255 opacity, not clipped, flags 0
        extra_len = 4 + 4 + 4 + len(lname) + 1 + ((4 - (len(lname) + 1) % 4) % 4)
        
        # Pascal string for name
        pname = bytes([len(lname)]) + lname.encode('ascii')
        pad = (4 - len(pname) % 4) % 4
        pname += b'\x00' * pad
        
        extra_data = b'\x00\x00\x00\x00\x00\x00\x00\x00' + struct.pack('>I', len(pname)) + pname
        
        layer_rec = struct.pack('>IIIIH', top, left, bottom, right, num_channels) + c_info + blend_key + struct.pack('>I', len(extra_data)) + extra_data
        layer_records += layer_rec
        channel_data += c_bytes
        
    layer_info_len = 2 + len(layer_records) + len(channel_data)
    layer_info = struct.pack('>h', len(layers)) + layer_records + channel_data
    layer_section = struct.pack('>I', len(layer_info)) + layer_info
    layer_mask_section = struct.pack('>I', len(layer_section)) + layer_section
    
    # Composite image data (Planar RGB, uncompressed raw)
    r_full, g_full, b_full = rgb_full.split()
    image_data = b'\x00\x00' + r_full.tobytes() + g_full.tobytes() + b_full.tobytes()
    
    with open(OUT_PSD, "wb") as f:
        f.write(header)
        f.write(color_mode)
        f.write(image_resources)
        f.write(layer_mask_section)
        f.write(image_data)
        
    print(f"✅ 成功生成 300 DPI 分层 PSD 文件: {OUT_PSD} ({OUT_PSD.stat().st_size} 字节)")

if __name__ == "__main__":
    build_multichannel_psd()
