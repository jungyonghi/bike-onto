# Timestamp: 2026-05-19 19:52:00

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _point(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[int, int]:
    eased = t * t * (3 - 2 * t)
    return int(_lerp(a[0], b[0], eased)), int(_lerp(a[1], b[1], eased))


def _cursor_layer(size: tuple[int, int], xy: tuple[int, int], *, scale: float = 1.0, click: float = 0.0) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y = xy
    s = scale
    # Windows 11-like white arrow cursor with black outline and soft shadow.
    pts = [
        (x, y),
        (x, y + 46 * s),
        (x + 12 * s, y + 34 * s),
        (x + 21 * s, y + 56 * s),
        (x + 31 * s, y + 52 * s),
        (x + 22 * s, y + 31 * s),
        (x + 39 * s, y + 31 * s),
    ]
    shadow = [(px + 4 * s, py + 5 * s) for px, py in pts]
    draw.polygon(shadow, fill=(0, 0, 0, 70))
    draw.line(shadow + [shadow[0]], fill=(0, 0, 0, 85), width=max(2, int(3 * s)), joint="curve")
    draw.polygon(pts, fill=(255, 255, 255, 255))
    draw.line(pts + [pts[0]], fill=(24, 24, 27, 255), width=max(2, int(2.6 * s)), joint="curve")
    draw.line([(x + 6 * s, y + 9 * s), (x + 6 * s, y + 32 * s), (x + 13 * s, y + 25 * s)], fill=(255, 255, 255, 255), width=max(1, int(1.2 * s)))

    if click > 0:
        cx, cy = x + int(8 * s), y + int(8 * s)
        radius = int((18 + click * 34) * s)
        alpha = int(180 * (1 - click))
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(37, 99, 235, alpha), width=max(3, int(5 * s)))
        inner = int(8 * s)
        draw.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=(37, 99, 235, int(90 * (1 - click))))
    return layer.filter(ImageFilter.GaussianBlur(0.1))


def _compose(bg: Image.Image, cursor_xy: tuple[int, int], *, cursor_scale: float = 1.0, click: float = 0.0) -> Image.Image:
    frame = bg.convert("RGBA")
    frame.alpha_composite(_cursor_layer(frame.size, cursor_xy, scale=cursor_scale, click=click))
    return frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=160)


def build_gif(tree_png: Path, radial_png: Path, output: Path, *, scale: float = 0.55) -> None:
    tree = Image.open(tree_png).convert("RGB")
    radial = Image.open(radial_png).convert("RGB")
    size = (int(tree.width * scale), int(tree.height * scale))
    tree = tree.resize(size, Image.Resampling.LANCZOS)
    radial = radial.resize(size, Image.Resampling.LANCZOS)

    # Coordinates are authored on the original 2300x1120 screenshots and then scaled.
    def sp(x: float, y: float) -> tuple[int, int]:
        return int(x * scale), int(y * scale)

    answer_entity = sp(155, 638)
    tree_button = sp(1830, 54)
    radial_button = sp(1938, 54)
    radial_focus = sp(1505, 630)

    frames: list[Image.Image] = []
    durations: list[int] = []

    # Hover over answer/candidate entity.
    for _ in range(8):
        frames.append(_compose(tree, answer_entity, cursor_scale=1.0, click=0.0))
        durations.append(90)
    # Click answer entity.
    for i in range(8):
        frames.append(_compose(tree, answer_entity, cursor_scale=1.0, click=i / 7))
        durations.append(70)
    # Move to tree/radial toggle area.
    for i in range(14):
        pos = _point(answer_entity, radial_button, i / 13)
        frames.append(_compose(tree, pos, cursor_scale=1.0, click=0.0))
        durations.append(55)
    # Small hover on buttons, then click Radial Map.
    for _ in range(4):
        frames.append(_compose(tree, radial_button, cursor_scale=1.0, click=0.0))
        durations.append(80)
    for i in range(8):
        frames.append(_compose(tree, radial_button, cursor_scale=1.0, click=i / 7))
        durations.append(65)
    # Radial map appears; keep cursor near active button.
    for _ in range(8):
        frames.append(_compose(radial, radial_button, cursor_scale=1.0, click=0.0))
        durations.append(85)
    # Move into the circular graph.
    for i in range(12):
        pos = _point(radial_button, radial_focus, i / 11)
        frames.append(_compose(radial, pos, cursor_scale=1.0, click=0.0))
        durations.append(55)
    for _ in range(10):
        frames.append(_compose(radial, radial_focus, cursor_scale=1.0, click=0.0))
        durations.append(95)

    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build animated GIF for OBYBK clickable ontology visual demo.")
    parser.add_argument("--tree-png", required=True, type=Path)
    parser.add_argument("--radial-png", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scale", type=float, default=0.55)
    args = parser.parse_args(list(argv) if argv is not None else None)
    build_gif(args.tree_png, args.radial_png, args.output, scale=args.scale)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
