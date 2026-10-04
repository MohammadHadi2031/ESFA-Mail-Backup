"""Generate assets/app.ico: the sidebar brand mark (blue gradient tile + envelope with a check).

Needs Pillow (not a runtime dependency):  pip install pillow && python tools/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024  # supersampled canvas
OUT = Path(__file__).resolve().parent.parent / 'assets' / 'app.ico'
WHITE = (255, 255, 255, 255)


def gradient(size: int) -> Image.Image:
    start, end = (0x25, 0x63, 0xEB), (0x0E, 0xA5, 0xE9)  # 135deg: top-left -> bottom-right
    image = Image.new('RGBA', (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            pixels[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(start, end)) + (255,)
    return image


def build() -> Image.Image:
    tile = gradient(S)
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.3), fill=255)
    tile.putalpha(mask)

    mark = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(mark)
    w = int(S * 0.07)
    left, top, right, bottom = int(S * .20), int(S * .29), int(S * .80), int(S * .73)
    d.rounded_rectangle((left, top, right, bottom), radius=int(S * .06), outline=WHITE, width=w)
    d.line([(left + w // 2, top + w // 2 + int(S * .02)), ((left + right) // 2, int(S * .55)),
            (right - w // 2, top + w // 2 + int(S * .02))], fill=WHITE, width=w, joint='curve')
    # check badge, top-right, cut out of the envelope with a tile-coloured ring
    cx, cy, r = int(S * .73), int(S * .31), int(S * .17)
    ring = Image.new('L', (S, S), 0)
    ImageDraw.Draw(ring).ellipse((cx - r - w, cy - r - w, cx + r + w, cy + r + w), fill=255)
    mark.paste((0, 0, 0, 0), mask=ring)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE)
    d.line([(cx - r * .45, cy + r * .02), (cx - r * .1, cy + r * .38), (cx + r * .5, cy - r * .32)],
           fill=(0x25, 0x63, 0xEB, 255), width=int(S * .045), joint='curve')
    tile.alpha_composite(mark)
    return tile


if __name__ == '__main__':
    OUT.parent.mkdir(exist_ok=True)
    build().save(OUT, sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    print(f'wrote {OUT}')
