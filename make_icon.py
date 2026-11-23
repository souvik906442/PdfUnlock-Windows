"""Generates icon.png and icon.ico (same design as the Android app icon).
Run once:  pip install pillow  &&  python make_icon.py
"""
from PIL import Image, ImageDraw, ImageFilter

S = 1024
K = 1.32  # scale the artwork up for a desktop icon
BLUE = (10, 132, 255)


def P(x, y):
    return ((x - 54) * K + 54) * S / 108, ((y - 54) * K + 54) * S / 108


def L(v):
    return v * K * S / 108


# gradient background (blue -> indigo) in a rounded square
bg = Image.new("RGB", (S, S))
px = bg.load()
c1, c2 = BLUE, (0x5E, 0x5C, 0xE6)
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S - 2)
        px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.225), fill=255)
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
img.paste(bg, (0, 0), mask)

# soft shadow under the page
sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle((*P(32, 29), *P(76, 83)), radius=L(6), fill=(0, 0, 40, 70))
img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(S * 0.012)))
d = ImageDraw.Draw(img)

# white page, then repaint the top-right corner with the background (cut corner)
d.rounded_rectangle((*P(32, 26), *P(76, 80)), radius=L(6), fill="white")
tri = Image.new("L", (S, S), 0)
ImageDraw.Draw(tri).polygon([P(60, 26), P(76.5, 26), P(76.5, 42.5)], fill=255)
img.paste(bg, (0, 0), Image.composite(tri, Image.new("L", (S, S), 0), mask))
d = ImageDraw.Draw(img)
d.polygon([P(60, 26), P(76, 42), P(66, 42), P(60, 36)], fill=(185, 216, 255))  # folded corner

# open padlock: shackle
w = int(L(3.4))
cx, cy = P(52.75, 49.5)
r = L(6.9)
d.arc((cx - r, cy - r, cx + r, cy + r), 167.5, 347.5, fill=BLUE, width=w)
d.line([P(46, 57), P(46, 51)], fill=BLUE, width=w)
for pt in (P(46, 57), P(59.5, 48)):
    d.ellipse((pt[0] - w / 2, pt[1] - w / 2, pt[0] + w / 2, pt[1] + w / 2), fill=BLUE)
# body + keyhole
d.rounded_rectangle((*P(42, 57), *P(64, 73)), radius=L(3), fill=BLUE)
kc = P(53, 62)
kr = L(2.4)
d.ellipse((kc[0] - kr, kc[1] - kr, kc[0] + kr, kc[1] + kr), fill="white")
d.rectangle((*P(52, 63), *P(54, 68)), fill="white")

img.resize((256, 256), Image.LANCZOS).save("icon.png")
img.save("icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
