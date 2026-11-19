#!/usr/bin/env python3
"""apple-touch-icon.png (180x180) を標準ライブラリだけで生成: 紺地に白いコート図と先発の丸6つ。"""
import struct, zlib, math
W = 180
NAVY, WHITE, ORANGE = (20, 40, 75), (255, 255, 255), (224, 128, 43)
px = [[NAVY] * W for _ in range(W)]
def rect(x0, y0, x1, y1, c):
    for y in range(y0, y1):
        for x in range(x0, x1):
            px[y][x] = c
def circle(cx, cy, r, c):
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                px[y][x] = c
rect(30, 40, 150, 140, WHITE)          # コート
rect(34, 44, 146, 136, NAVY)
rect(34, 88, 146, 92, WHITE)            # ネット側の区切り
for i, cx in enumerate((58, 90, 122)):
    circle(cx, 66, 11, WHITE); circle(cx, 114, 11, WHITE)
circle(122, 114, 11, ORANGE)           # サーブ位置(P1=右下)
raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in px)
def chunk(t, d):
    c = struct.pack(">I", len(d)) + t + d
    return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, W, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
open("apple-touch-icon.png", "wb").write(png)
print("apple-touch-icon.png", len(png), "bytes")
