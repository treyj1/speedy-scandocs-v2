"""Makes packaging/icon.icns from GDJ Logo.png. Rerun only if the logo changes.

Mac icons sit on a rounded tile, 824 pixels of a 1024 pixel square. The tile also keeps the blue
logo readable in a dark Dock. Windows uses GDJ Logo.ico as it is.
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
TILE = 824
LOGO = 640
RADIUS = 185
SMOOTH = 4       # draw the tile large, then shrink it, for clean corners

here = Path(__file__).resolve().parent
logo = Image.open(here.parent / "GDJ Logo.png").convert("RGBA")
logo = logo.crop(logo.getchannel("A").getbbox())
logo.thumbnail((LOGO, LOGO), Image.LANCZOS)

inset = (SIZE - TILE) // 2
tile = Image.new("RGBA", (SIZE * SMOOTH, SIZE * SMOOTH), (0, 0, 0, 0))
ImageDraw.Draw(tile).rounded_rectangle(
    (inset * SMOOTH, inset * SMOOTH, (inset + TILE) * SMOOTH - 1, (inset + TILE) * SMOOTH - 1),
    radius=RADIUS * SMOOTH, fill="white")
icon = tile.resize((SIZE, SIZE), Image.LANCZOS)
icon.alpha_composite(logo, ((SIZE - logo.width) // 2, (SIZE - logo.height) // 2))
icon.save(here / "icon.icns")
