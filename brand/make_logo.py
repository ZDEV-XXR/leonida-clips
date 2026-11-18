"""Leonida Replay brand art: profile picture (IG 1080, YouTube 800, TikTok 720) and a YouTube banner.
Original design: synthwave sunset sun with a circular replay arrow and an LR monogram.
python3 brand/make_logo.py"""
import math, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ANTON = '/usr/share/fonts/truetype/google-fonts/ofl/anton/Anton-Regular.ttf'
S = 2160                                  # draw big, downsample for clean edges
NIGHT, PLUM = (14, 10, 38), (60, 16, 84)
SUN_TOP, SUN_BOT = (255, 214, 92), (255, 46, 136)
TEAL = (38, 232, 214)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgrad(w, h, top, bot):
    im = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bot, y / (h - 1)))
    return im


def sun(size):
    """Gradient disc with the classic horizontal cut stripes in the lower half."""
    disc = vgrad(size, size, SUN_TOP, SUN_BOT)
    mask = Image.new('L', (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, size - 1, size - 1], fill=255)
    y, gap, band = int(size * 0.52), int(size * 0.018), int(size * 0.07)
    while y < size:
        md.rectangle([0, y, size, y + gap], fill=0)
        gap = int(gap * 1.28) + 2
        y += band
        band = max(int(band * 0.82), gap + 6)
    return disc, mask


def avatar():
    im = vgrad(S, S, NIGHT, PLUM)
    # soft glow behind the sun
    glow = Image.new('RGB', (S, S), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([S * .2, S * .2, S * .8, S * .8], fill=(255, 60, 140))
    im = Image.blend(im, glow.filter(ImageFilter.GaussianBlur(S * .08)), 0.35)
    sz = int(S * 0.56)
    disc, mask = sun(sz)
    im.paste(disc, ((S - sz) // 2, (S - sz) // 2), mask)
    d = ImageDraw.Draw(im)
    # replay arrow: 300-degree ring around the sun, arrowhead at the open end
    c, r, w = (S / 2, S / 2), S * .36, int(S * .042)
    box = [c[0] - r, c[1] - r, c[0] + r, c[1] + r]
    d.arc(box, start=-60, end=240, fill=TEAL, width=w)
    a = math.radians(-60)                          # arrow tip end (PIL angles run clockwise from 3 o'clock)
    ex, ey = c[0] + r * math.cos(a), c[1] + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)             # direction of travel (counter-clockwise = rewind)
    tx, ty = -tx, -ty
    nx, ny = math.cos(a), math.sin(a)
    L, Wd = S * .095, S * .065
    tip = (ex + tx * L, ey + ty * L)
    d.polygon([tip, (ex + nx * Wd, ey + ny * Wd), (ex - nx * Wd, ey - ny * Wd)], fill=TEAL)
    # monogram
    f = ImageFont.truetype(ANTON, int(S * .40))
    txt = 'LR'
    bb = d.textbbox((0, 0), txt, font=f)
    x, y = (S - (bb[2] - bb[0])) / 2 - bb[0], S * .50 - (bb[3] - bb[1]) / 2 - bb[1]
    shadow = Image.new('L', (S, S), 0)
    ImageDraw.Draw(shadow).text((x + S * .012, y + S * .016), txt, font=f, fill=200)
    im.paste((10, 6, 30), (0, 0), shadow.filter(ImageFilter.GaussianBlur(S * .01)))
    d.text((x, y), txt, font=f, fill=(255, 255, 255), stroke_width=int(S * .012), stroke_fill=NIGHT)
    return im


def banner():
    W, H = 2560, 1440
    im = vgrad(W, H, NIGHT, PLUM)
    sz = 900
    disc, mask = sun(sz)
    im.paste(disc, ((W - sz) // 2, 300), mask)
    d = ImageDraw.Draw(im)
    im.paste(vgrad(W, H - 900, (24, 8, 46), NIGHT), (0, 900))   # floor hides the sun below the horizon
    for i in range(14):                            # perspective grid floor
        y = 900 + int((i / 13) ** 1.8 * 540)
        d.line([(0, y), (W, y)], fill=lerp(PLUM, TEAL, 0.35), width=3)
    for k in range(-12, 13):
        d.line([(W / 2 + k * 30, 900), (W / 2 + k * 260, H)], fill=lerp(PLUM, TEAL, 0.35), width=3)
    f1, f2 = ImageFont.truetype(ANTON, 200), ImageFont.truetype(ANTON, 64)
    for txt, f, y, col in [('LEONIDA REPLAY', f1, 560, (255, 255, 255)),
                           ('THE BEST GTA VI STREAM MOMENTS  ·  NEW CLIPS DAILY', f2, 800, TEAL)]:
        bb = d.textbbox((0, 0), txt, font=f)
        d.text(((W - (bb[2] - bb[0])) / 2 - bb[0], y - (bb[3] - bb[1]) / 2 - bb[1]), txt, font=f, fill=col,
               stroke_width=6 if f is f1 else 3, stroke_fill=NIGHT)
    return im


if __name__ == '__main__':
    a = avatar()
    for name, px in [('profile_instagram_1080.jpg', 1080), ('profile_youtube_800.png', 800), ('profile_tiktok_720.jpg', 720)]:
        out = a.resize((px, px), Image.LANCZOS)
        out.save(os.path.join(HERE, name), quality=95)
    banner().save(os.path.join(HERE, 'banner_youtube_2560x1440.jpg'), quality=92)
    a.resize((160, 160), Image.LANCZOS).save('/tmp/avatar_small.png')
    print('ok')
