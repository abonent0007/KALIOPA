"""Generate KALIOPA icon (rounded network mark) as a multi-size Windows ICO.

The mark mirrors the Route Lab header: dark rounded square, mint border, two mint
nodes and one amber node connected by diagonal links. Pure PIL so the icon is
reproducible and needs no external artwork.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT_ICO = ROOT / "icon.ico"
OUT_PNG = ROOT / "docs" / "assets" / "kaliopa-icon.png"
SIZE = 1024
MINT = (108, 245, 205, 255)
MINT_SOFT = (43, 214, 173, 255)
AMBER = (255, 189, 107, 255)
INK = (7, 20, 28, 255)
BORDER = (43, 214, 173, 255)


def rounded_square(draw: ImageDraw.ImageDraw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def build() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Outer tile with a mint rim, then a softer inner rim for depth.
    rounded_square(draw, (58, 58, SIZE - 58, SIZE - 58), 224, fill=INK, outline=BORDER, width=28)
    rounded_square(draw, (96, 96, SIZE - 96, SIZE - 96), 196, outline=(108, 245, 205, 72), width=7)

    # Network nodes: top-left, bottom-right and the amber centre node.
    nodes = {
        "a": (318, 318),
        "b": (706, 706),
        "c": (452, 616),
    }
    links = (("a", "c"), ("c", "b"), ("a", "b"))

    # Glow layer first: wide translucent strokes and halos.
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for start, end in links:
        gdraw.line((nodes[start], nodes[end]), fill=(108, 245, 205, 42), width=34)
    for name, (x, y) in nodes.items():
        colour = AMBER if name == "c" else MINT
        radius = 86 if name == "c" else 112
        gdraw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour[:3] + (45,))
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    image = Image.alpha_composite(image, glow)
    draw = ImageDraw.Draw(image)

    # Crisp links.
    for start, end in links:
        draw.line((nodes[start], nodes[end]), fill=MINT_SOFT, width=18)

    # Crisp nodes with a dark inner hole, like circuit pads.
    for name, (x, y) in nodes.items():
        outer = 96 if name == "c" else 120
        inner = 44 if name == "c" else 52
        colour = AMBER if name == "c" else MINT
        draw.ellipse((x - outer, y - outer, x + outer, y + outer), fill=colour)
        draw.ellipse((x - inner, y - inner, x + inner, y + inner), fill=INK)
        draw.ellipse((x - inner + 10, y - inner + 10, x + inner - 10, y + inner - 10),
                     outline=colour, width=6)

    return image


def main() -> None:
    image = build()
    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUT_ICO, format="ICO", sizes=[(256, 256), (128, 128), (64, 64),
                                             (48, 48), (32, 32), (24, 24), (16, 16)])
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    image.resize((256, 256), Image.LANCZOS).save(OUT_PNG, format="PNG")
    print("saved", OUT_ICO, OUT_ICO.stat().st_size, "bytes")
    print("saved", OUT_PNG, OUT_PNG.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
