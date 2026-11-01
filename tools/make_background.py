"""Сгенерировать фон OBNOVA: тёмная сеть узлов с бирюзовым свечением.

Рисуется локально (PIL), без внешних сервисов. Результат — RGBA 720x540,
затем уменьшается до размера окна (360x270) для чёткости.
"""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 720, 540
OUT = Path("img/background.png")

random.seed(20261031)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# 1. Фон: вертикальный градиент от почти чёрного к тёмно-синему
base = Image.new("RGB", (W, H), (2, 6, 15))
draw = ImageDraw.Draw(base)
top = (2, 6, 15)
bottom = (7, 26, 52)
for y in range(H):
    draw.line([(0, y), (W, y)], fill=lerp(top, bottom, y / H))

# 2. Центральное свечение (левее центра, как на референсе)
glow = Image.new("L", (W, H), 0)
gdraw = ImageDraw.Draw(glow)
cx, cy = int(W * 0.42), int(H * 0.5)
for r in range(250, 0, -8):
    alpha = int(150 * (1 - r / 250) ** 2)
    gdraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=alpha)
glow = glow.filter(ImageFilter.GaussianBlur(40))
base = Image.composite(Image.new("RGB", (W, H), (90, 205, 255)), base, glow.point(lambda v: v // 2))

# 3. Сеть узлов
nodes = []
for _ in range(190):
    x = random.uniform(0, W)
    y = random.uniform(0, H)
    # плотнее к центру свечения
    d = math.hypot(x - cx, y - cy)
    if d > 260 and random.random() < 0.45:
        continue
    nodes.append((x, y))

lines = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ldraw = ImageDraw.Draw(lines)
for i, (x1, y1) in enumerate(nodes):
    for x2, y2 in nodes[i + 1:]:
        d = math.hypot(x2 - x1, y2 - y1)
        if d < 120:
            a = int(150 * (1 - d / 120))
            ldraw.line([(x1, y1), (x2, y2)], fill=(120, 200, 255, a), width=1)
lines = lines.filter(ImageFilter.GaussianBlur(0.6))
base = Image.alpha_composite(base.convert("RGBA"), lines)

# 4. Узлы: свечение + яркое ядро
halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
hdraw = ImageDraw.Draw(halo)
cores = Image.new("RGBA", (W, H), (0, 0, 0, 0))
cdraw = ImageDraw.Draw(cores)
for x, y in nodes:
    r = random.uniform(1.2, 3.2)
    hdraw.ellipse([x - r * 4, y - r * 4, x + r * 4, y + r * 4], fill=(80, 190, 255, 70))
    cdraw.ellipse([x - r, y - r, x + r, y + r], fill=(210, 240, 255, 235))
halo = halo.filter(ImageFilter.GaussianBlur(3))
base = Image.alpha_composite(base, halo)
base = Image.alpha_composite(base, cores)

# 5. Мягкие боке-точки на периферии
bokeh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
bdraw = ImageDraw.Draw(bokeh)
for _ in range(26):
    x = random.uniform(0, W)
    y = random.uniform(0, H)
    r = random.uniform(6, 26)
    bdraw.ellipse([x - r, y - r, x + r, y + r], fill=(40, 120, 220, 18))
bokeh = bokeh.filter(ImageFilter.GaussianBlur(6))
base = Image.alpha_composite(base, bokeh)

# 6. Затемнение под текст интерфейса и уменьшение до окна
shade = Image.new("RGBA", (W, H), (2, 8, 18, 70))
base = Image.alpha_composite(base, shade)
final = base.convert("RGB").resize((360, 270), Image.LANCZOS).convert("RGBA")

OUT.parent.mkdir(parents=True, exist_ok=True)
final.save(OUT, "PNG")
print("saved", OUT, final.size)
