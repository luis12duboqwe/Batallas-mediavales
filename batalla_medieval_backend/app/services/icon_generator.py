"""SVG icon generator for troops, buildings, resources, and alliance banners."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict

import svgwrite

PALETTE = {
    "gold": "#d4af37",
    "iron_gray": "#4a4a4a",
    "red": "#8b1e1e",
    "dark_green": "#2e5a3a",
    "royal_blue": "#1e3a8a",
}


def _base_canvas(size: int) -> svgwrite.Drawing:
    dwg = svgwrite.Drawing(size=(size, size))
    dwg.add(
        dwg.rect(
            insert=(0, 0),
            size=(size, size),
            rx=size * 0.08,
            ry=size * 0.08,
            fill=PALETTE["iron_gray"],
        )
    )
    dwg.add(
        dwg.rect(
            insert=(size * 0.04, size * 0.04),
            size=(size * 0.92, size * 0.92),
            rx=size * 0.06,
            ry=size * 0.06,
            fill=PALETTE["royal_blue"],
            stroke=PALETTE["gold"],
            stroke_width=size * 0.02,
        )
    )
    return dwg


def _troop_icon(subtype: str, size: int) -> svgwrite.Drawing:
    dwg = _base_canvas(size)

    shield = dwg.polygon(
        points=[
            (size * 0.5, size * 0.18),
            (size * 0.72, size * 0.34),
            (size * 0.72, size * 0.64),
            (size * 0.5, size * 0.82),
            (size * 0.28, size * 0.64),
            (size * 0.28, size * 0.34),
        ],
        fill=PALETTE["dark_green"],
        stroke=PALETTE["gold"],
        stroke_width=size * 0.02,
    )
    dwg.add(shield)

    subtype = subtype.lower()
    if subtype in {"lancero", "lanza", "spear", "spearman"}:
        dwg.add(
            dwg.line(
                start=(size * 0.24, size * 0.78),
                end=(size * 0.76, size * 0.22),
                stroke=PALETTE["gold"],
                stroke_width=size * 0.05,
                stroke_linecap="round",
            )
        )
        dwg.add(
            dwg.polygon(
                points=[
                    (size * 0.74, size * 0.16),
                    (size * 0.86, size * 0.22),
                    (size * 0.78, size * 0.32),
                ],
                fill=PALETTE["red"],
                stroke=PALETTE["gold"],
                stroke_width=size * 0.014,
            )
        )
    elif subtype in {"arquero", "archer", "arco"}:
        bow_path = dwg.path(
            d=(
                f"M {size * 0.32},{size * 0.18} "
                f"Q {size * 0.16},{size * 0.50} {size * 0.32},{size * 0.82}"
            ),
            fill="none",
            stroke=PALETTE["gold"],
            stroke_width=size * 0.045,
            stroke_linecap="round",
        )
        dwg.add(bow_path)
        dwg.add(
            dwg.line(
                start=(size * 0.32, size * 0.22),
                end=(size * 0.32, size * 0.78),
                stroke=PALETTE["gold"],
                stroke_width=size * 0.018,
            )
        )
        dwg.add(
            dwg.polygon(
                points=[
                    (size * 0.32, size * 0.20),
                    (size * 0.44, size * 0.24),
                    (size * 0.32, size * 0.28),
                ],
                fill=PALETTE["red"],
            )
        )
    else:
        dwg.add(
            dwg.rect(
                insert=(size * 0.46, size * 0.2),
                size=(size * 0.08, size * 0.5),
                fill=PALETTE["gold"],
                rx=size * 0.02,
            )
        )
        dwg.add(
            dwg.rect(
                insert=(size * 0.38, size * 0.34),
                size=(size * 0.24, size * 0.34),
                fill=PALETTE["red"],
                stroke=PALETTE["gold"],
                stroke_width=size * 0.014,
                rx=size * 0.04,
            )
        )
    dwg.add(
        dwg.circle(
            center=(size * 0.5, size * 0.34),
            r=size * 0.06,
            fill=PALETTE["gold"],
        )
    )
    return dwg


def _building_icon(subtype: str, size: int) -> svgwrite.Drawing:
    dwg = _base_canvas(size)

    base = dwg.rect(
        insert=(size * 0.18, size * 0.46),
        size=(size * 0.64, size * 0.36),
        fill=PALETTE["iron_gray"],
        stroke=PALETTE["gold"],
        stroke_width=size * 0.02,
        rx=size * 0.04,
    )
    dwg.add(base)

    for i in range(3):
        tower_x = size * (0.20 + i * 0.25)
        dwg.add(
            dwg.rect(
                insert=(tower_x, size * 0.26),
                size=(size * 0.18, size * 0.24),
                fill=PALETTE["dark_green"],
                stroke=PALETTE["gold"],
                stroke_width=size * 0.018,
            )
        )
        battlement = dwg.rect(
            insert=(tower_x, size * 0.22),
            size=(size * 0.18, size * 0.06),
            fill=PALETTE["red"],
        )
        dwg.add(battlement)

    gate = dwg.rect(
        insert=(size * 0.44, size * 0.56),
        size=(size * 0.12, size * 0.18),
        fill=PALETTE["royal_blue"],
        stroke=PALETTE["gold"],
        stroke_width=size * 0.012,
        rx=size * 0.02,
    )
    dwg.add(gate)

    if subtype.lower() in {"barracas", "barracks", "cuartel"}:
        dwg.add(
            dwg.polyline(
                points=[
                    (size * 0.18, size * 0.46),
                    (size * 0.5, size * 0.26),
                    (size * 0.82, size * 0.46),
                ],
                fill="none",
                stroke=PALETTE["gold"],
                stroke_width=size * 0.028,
                stroke_linejoin="round",
            )
        )
    else:
        dwg.add(
            dwg.rect(
                insert=(size * 0.22, size * 0.32),
                size=(size * 0.56, size * 0.12),
                fill=PALETTE["royal_blue"],
                rx=size * 0.02,
            )
        )
    return dwg


def _resource_icon(subtype: str, size: int) -> svgwrite.Drawing:
    dwg = _base_canvas(size)
    subtype = subtype.lower()

    if subtype in {"wood", "madera"}:
        dwg.add(
            dwg.rect(
                insert=(size * 0.32, size * 0.46),
                size=(size * 0.36, size * 0.28),
                fill="#5a381e",
                stroke=PALETTE["gold"],
                stroke_width=size * 0.016,
                rx=size * 0.06,
            )
        )
        dwg.add(
            dwg.rect(
                insert=(size * 0.26, size * 0.30),
                size=(size * 0.18, size * 0.38),
                fill="#6d4523",
                rx=size * 0.06,
            )
        )
    elif subtype in {"stone", "piedra"}:
        dwg.add(
            dwg.polygon(
                points=[
                    (size * 0.30, size * 0.64),
                    (size * 0.46, size * 0.34),
                    (size * 0.70, size * 0.40),
                    (size * 0.78, size * 0.62),
                    (size * 0.52, size * 0.78),
                ],
                fill="#6f6f6f",
                stroke=PALETTE["gold"],
                stroke_width=size * 0.016,
            )
        )
    else:
        dwg.add(
            dwg.circle(
                center=(size * 0.44, size * 0.56),
                r=size * 0.18,
                fill=PALETTE["gold"],
                stroke=PALETTE["red"],
                stroke_width=size * 0.02,
            )
        )
        dwg.add(
            dwg.polygon(
                points=[
                    (size * 0.56, size * 0.28),
                    (size * 0.70, size * 0.54),
                    (size * 0.54, size * 0.54),
                ],
                fill=PALETTE["red"],
                stroke=PALETTE["gold"],
                stroke_width=size * 0.012,
            )
        )
    return dwg


def _alliance_icon(subtype: str, size: int) -> svgwrite.Drawing:
    dwg = _base_canvas(size)
    pole = dwg.rect(
        insert=(size * 0.22, size * 0.20),
        size=(size * 0.08, size * 0.64),
        fill=PALETTE["iron_gray"],
        stroke=PALETTE["gold"],
        stroke_width=size * 0.014,
        rx=size * 0.02,
    )
    dwg.add(pole)

    banner = dwg.polygon(
        points=[
            (size * 0.30, size * 0.24),
            (size * 0.76, size * 0.24),
            (size * 0.76, size * 0.62),
            (size * 0.54, size * 0.54),
            (size * 0.30, size * 0.62),
        ],
        fill=PALETTE["red"],
        stroke=PALETTE["gold"],
        stroke_width=size * 0.018,
    )
    dwg.add(banner)

    emblem = dwg.circle(
        center=(size * 0.53, size * 0.42),
        r=size * 0.10,
        fill=PALETTE["gold"],
        stroke=PALETTE["iron_gray"],
        stroke_width=size * 0.014,
    )
    dwg.add(emblem)
    dwg.add(
        dwg.rect(
            insert=(size * 0.46, size * 0.36),
            size=(size * 0.14, size * 0.12),
            fill=PALETTE["royal_blue"],
            rx=size * 0.02,
        )
    )
    return dwg


_ICON_BUILDERS: Dict[str, Callable[[str, int], svgwrite.Drawing]] = {
    "troop": _troop_icon,
    "building": _building_icon,
    "resource": _resource_icon,
    "alliance": _alliance_icon,
}


def _output_path(icon_type: str, subtype: str) -> Path:
    base_dir = Path(__file__).resolve().parent.parent / "static" / "icons"
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{icon_type}_{subtype}.svg"
    return base_dir / filename


def _mirror_frontend(icon_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    frontend_dir = root / "batalla_medieval_frontend" / "src" / "assets" / "icons" / "autogen"
    frontend_dir.mkdir(parents=True, exist_ok=True)
    mirror_path = frontend_dir / icon_path.name
    mirror_path.write_bytes(icon_path.read_bytes())


def generate_icon(icon_type: str, subtype: str, size: int = 128) -> Path:
    """Generate an SVG icon and return the path to the saved file."""
    icon_type = icon_type.lower()
    subtype = subtype.lower()

    if size < 32 or size > 512:
        raise ValueError("size must be between 32 and 512")

    if icon_type not in _ICON_BUILDERS:
        raise ValueError(f"Unsupported icon type: {icon_type}")

    drawing = _ICON_BUILDERS[icon_type](subtype, size)
    icon_path = _output_path(icon_type, subtype)
    drawing.saveas(str(icon_path))
    _mirror_frontend(icon_path)
    return icon_path
