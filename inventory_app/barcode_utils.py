from __future__ import annotations

import html
import os
import re
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

from .config import APP_TITLE


CODE39_PATTERNS = {
    "0": "nnnwwnwnn",
    "1": "wnnwnnnnw",
    "2": "nnwwnnnnw",
    "3": "wnwwnnnnn",
    "4": "nnnwwnnnw",
    "5": "wnnwwnnnn",
    "6": "nnwwwnnnn",
    "7": "nnnwnnwnw",
    "8": "wnnwnnwnn",
    "9": "nnwwnnwnn",
    "A": "wnnnnwnnw",
    "B": "nnwnnwnnw",
    "C": "wnwnnwnnn",
    "D": "nnnnwwnnw",
    "E": "wnnnwwnnn",
    "F": "nnwnwwnnn",
    "G": "nnnnnwwnw",
    "H": "wnnnnwwnn",
    "I": "nnwnnwwnn",
    "J": "nnnnwwwnn",
    "K": "wnnnnnnww",
    "L": "nnwnnnnww",
    "M": "wnwnnnnwn",
    "N": "nnnnwnnww",
    "O": "wnnnwnnwn",
    "P": "nnwnwnnwn",
    "Q": "nnnnnnwww",
    "R": "wnnnnnwwn",
    "S": "nnwnnnwwn",
    "T": "nnnnwnwwn",
    "U": "wwnnnnnnw",
    "V": "nwwnnnnnw",
    "W": "wwwnnnnnn",
    "X": "nwnnwnnnw",
    "Y": "wwnnwnnnn",
    "Z": "nwwnwnnnn",
    "-": "nwnnnnwnw",
    ".": "wwnnnnwnn",
    " ": "nwwnnnwnn",
    "$": "nwnwnwnnn",
    "/": "nwnwnnnwn",
    "+": "nwnnnwnwn",
    "%": "nnnwnwnwn",
    "*": "nwnnwnwnn",
}

LETTER_WIDTH = 612.0
LETTER_HEIGHT = 792.0
POINTS_PER_INCH = 72.0
SHEET_TEMPLATE_CODE = "PLS892"
LABEL_COLUMNS = 4
LABEL_ROWS = 10
LABEL_WIDTH = 2.0 * POINTS_PER_INCH
LABEL_HEIGHT = 1.0 * POINTS_PER_INCH
PAGE_MARGIN_X = (LETTER_WIDTH - (LABEL_COLUMNS * LABEL_WIDTH)) / 2.0
PAGE_MARGIN_Y = (LETTER_HEIGHT - (LABEL_ROWS * LABEL_HEIGHT)) / 2.0
LABEL_GAP_X = 0.0
LABEL_GAP_Y = 0.0
BARCODE_QUIET_ZONE = 9.0


def normalize_token(value: str, fallback: str = "STD") -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().upper())
    token = re.sub(r"-{2,}", "-", token).strip("-")
    return token or fallback


def compose_barcode(category: str, variant: str, item_type: str, sequence: int) -> str:
    del category, variant, item_type
    if sequence < 1 or sequence > 9_999_999:
        raise ValueError("A.C.E. barcode sequence must be between 1 and 9,999,999.")
    return f"A{sequence:07d}"


def compact_wings_barcode(item_no: str) -> str:
    """Represent a numeric WINGS identifier in a short scanner-friendly base-36 value."""
    cleaned = str(item_no).strip()
    if not cleaned.isdigit() or int(cleaned) < 1:
        raise ValueError("WINGS item number must be a positive number.")
    number = int(cleaned)
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    encoded = ""
    while number:
        number, remainder = divmod(number, 36)
        encoded = alphabet[remainder] + encoded
    return f"W{encoded.zfill(7)}"


def barcode_svg(barcode_value: str, *, height: int = 60, module_width: int = 2) -> str:
    bars, total_width = barcode_bars(barcode_value, module_width=module_width)
    rects = [
        f'<rect x="{x + 10}" y="0" width="{width}" height="{height}" fill="#111827" />'
        for x, width in bars
    ]
    text_y = height + 18
    escaped_value = html.escape(barcode_value)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width + 20}" height="{height + 28}" '
        f'viewBox="0 0 {total_width + 20} {height + 28}">'
        f'{"".join(rects)}'
        f'<text x="{(total_width + 20) / 2}" y="{text_y}" text-anchor="middle" '
        f'font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="#111827">{escaped_value}</text>'
        "</svg>"
    )


def barcode_bars(barcode_value: str, *, module_width: float = 1.0) -> tuple[list[tuple[float, float]], float]:
    encoded = f"*{barcode_value.upper()}*"
    x_position = 0.0
    bars: list[tuple[float, float]] = []

    for character in encoded:
        pattern = CODE39_PATTERNS.get(character)
        if pattern is None:
            raise ValueError(f"Character {character!r} cannot be encoded in Code 39.")

        is_bar = True
        for marker in pattern:
            width = module_width * (3 if marker == "w" else 1)
            if is_bar:
                bars.append((x_position, width))
            x_position += width
            is_bar = not is_bar
        x_position += module_width

    return bars, x_position


def build_label_sheet_html(records: list[dict[str, Any]], org_name: str) -> str:
    pages: list[str] = []
    labels_per_page = LABEL_COLUMNS * LABEL_ROWS
    for start_index in range(0, len(records), labels_per_page):
        page_cards = []
        for record in records[start_index : start_index + labels_per_page]:
            page_cards.append(
                """
                <article class="label">
                    <div class="top">
                        <div class="name">{item_name}</div>
                        <div class="qty">Qty {units}</div>
                    </div>
                    <div class="meta">{category} | {variant} | {item_type}</div>
                    <div class="barcode">{barcode}</div>
                </article>
                """.format(
                    item_name=html.escape(str(record["item_name"])),
                    category=html.escape(str(record["category"])),
                    variant=html.escape(str(record["variant"])),
                    item_type=html.escape(str(record["item_type"])),
                    barcode=barcode_svg(str(record["barcode_id"]), height=22, module_width=1),
                    units=html.escape(str(record["total_quantity"])),
                )
            )
        pages.append(f'<section class="sheet">{"".join(page_cards)}</section>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Barcode Label Sheet</title>
    <style>
        @page {{ size: Letter; margin: 0; }}
        body {{
            margin: 0;
            padding: 0;
            font-family: "Segoe UI", Arial, sans-serif;
            color: #111827;
            background: white;
        }}
        .sheet {{
            display: grid;
            grid-template-columns: repeat({LABEL_COLUMNS}, 2in);
            grid-template-rows: repeat({LABEL_ROWS}, 1in);
            width: 8.5in;
            min-height: 11in;
            box-sizing: border-box;
            padding: {PAGE_MARGIN_Y / POINTS_PER_INCH:.3f}in {PAGE_MARGIN_X / POINTS_PER_INCH:.3f}in;
            page-break-after: always;
        }}
        .label {{
            width: 2in;
            height: 1in;
            box-sizing: border-box;
            padding: 0.06in 0.08in;
            break-inside: avoid;
        }}
        .top {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 8px;
        }}
        .name {{
            font-size: 9px;
            font-weight: 700;
            line-height: 1.1;
            max-width: 1.3in;
            overflow: hidden;
        }}
        .qty {{
            font-size: 7px;
            font-weight: 700;
            white-space: nowrap;
        }}
        .meta {{
            font-size: 6px;
            margin-top: 0.03in;
            color: #334155;
            line-height: 1.1;
            white-space: nowrap;
            overflow: hidden;
        }}
        .barcode {{
            margin-top: 0.06in;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden;
        }}
        .barcode svg {{
            width: 100%;
            height: auto;
        }}
    </style>
</head>
<body>
    {''.join(pages)}
</body>
</html>
"""


def write_label_sheet(path: Path, records: list[dict[str, Any]], org_name: str) -> Path:
    path.write_text(build_label_sheet_html(records, org_name), encoding="utf-8")
    return path


def write_label_pdf(path: Path, records: list[dict[str, Any]], org_name: str, *, title: str) -> Path:
    if not records:
        raise ValueError("At least one barcode record is required to build a label PDF.")

    pages = _build_pdf_pages(records, org_name)
    pdf_bytes = _assemble_pdf(pages, title=title)
    path.write_bytes(pdf_bytes)
    return path


def write_direct_label_pdf(
    path: Path,
    records: list[dict[str, Any]],
    org_name: str,
    *,
    title: str,
) -> Path:
    """Write one exact 2 x 1-inch thermal label per PDF page."""
    if not records:
        raise ValueError("At least one barcode record is required to build a label PDF.")

    pages = [
        "".join(_label_commands(record, org_name, 0.0, LABEL_HEIGHT, LABEL_WIDTH, LABEL_HEIGHT))
        for record in records
    ]
    pdf_bytes = _assemble_pdf(
        pages,
        title=title,
        page_width=LABEL_WIDTH,
        page_height=LABEL_HEIGHT,
    )
    path.write_bytes(pdf_bytes)
    return path


def open_file(path: Path) -> None:
    try:
        os.startfile(path)  # type: ignore[attr-defined]
        return
    except AttributeError:
        pass
    except OSError:
        pass

    try:
        webbrowser.open(path.as_uri())
    except Exception:
        subprocess.Popen([str(path)], shell=True)


def _build_pdf_pages(records: list[dict[str, Any]], org_name: str) -> list[str]:
    commands_by_page: list[str] = []

    for start_index in range(0, len(records), LABEL_COLUMNS * LABEL_ROWS):
        page_records = records[start_index : start_index + (LABEL_COLUMNS * LABEL_ROWS)]
        commands: list[str] = []
        for label_index, record in enumerate(page_records):
            row = label_index // LABEL_COLUMNS
            col = label_index % LABEL_COLUMNS
            x = PAGE_MARGIN_X + (col * (LABEL_WIDTH + LABEL_GAP_X))
            y_top = LETTER_HEIGHT - PAGE_MARGIN_Y - (row * (LABEL_HEIGHT + LABEL_GAP_Y))
            commands.extend(_label_commands(record, org_name, x, y_top, LABEL_WIDTH, LABEL_HEIGHT))
        commands_by_page.append("".join(commands))

    return commands_by_page


def _label_commands(record: dict[str, Any], org_name: str, x: float, y_top: float, width: float, height: float) -> list[str]:
    y_bottom = y_top - height
    commands: list[str] = []
    inner_padding_x = 6.0
    name_text_y = y_top - 10.0
    qty_text_y = y_top - 10.0
    meta_text_y = y_top - 19.0
    barcode_height = 28.0
    barcode_x = x + BARCODE_QUIET_ZONE
    barcode_y = y_bottom + 12.0
    barcode_draw_width = width - (2 * BARCODE_QUIET_ZONE)
    qty_text = f"Qty {record['total_quantity']}"
    item_name_text = _fit_text(str(record["item_name"]), max_width=width - 48.0, size=7.0)
    meta_text = _fit_text(
        f"{record['category']} | {record['variant']} | {record['item_type']}",
        max_width=width - (2 * inner_padding_x),
        size=4.5,
    )

    commands.extend(
        [
            _text_command(item_name_text, x + inner_padding_x, name_text_y, "F2", 7.0, color=(0.07, 0.11, 0.17)),
            _text_command(
                meta_text,
                x + inner_padding_x,
                meta_text_y,
                "F1",
                4.5,
                color=(0.20, 0.28, 0.39),
            ),
            _text_command(
                qty_text,
                x + width - inner_padding_x - _pdf_text_width(qty_text, size=5.0),
                qty_text_y,
                "F1",
                5.0,
                color=(0.20, 0.28, 0.39),
            ),
        ]
    )

    commands.extend(_barcode_pdf_commands(str(record["barcode_id"]), barcode_x, barcode_y, barcode_draw_width, barcode_height))
    return commands


def _barcode_pdf_commands(barcode_value: str, x: float, y: float, width: float, height: float) -> list[str]:
    bars, raw_width = barcode_bars(barcode_value, module_width=1.0)
    scale = width / max(raw_width, 1.0)
    commands = [_fill_color(0.07, 0.11, 0.17)]
    for bar_x, bar_width in bars:
        commands.append(f"{x + (bar_x * scale):.2f} {y:.2f} {bar_width * scale:.2f} {height:.2f} re f\n")
    commands.append(
        _text_command(
            barcode_value,
            x + (width / 2.0),
            y - 7,
            "F1",
            5.5,
            color=(0.07, 0.11, 0.17),
            centered=True,
        )
    )
    return commands


def _assemble_pdf(
    page_contents: list[str],
    *,
    title: str,
    page_width: float = LETTER_WIDTH,
    page_height: float = LETTER_HEIGHT,
) -> bytes:
    objects: list[bytes] = []

    def add_object(content: str | bytes) -> int:
        payload = content if isinstance(content, bytes) else content.encode("latin-1")
        objects.append(payload)
        return len(objects)

    pages_object_id = add_object("<< /Type /Pages /Kids [] /Count 0 >>")
    font_regular_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    page_ids: list[int] = []
    for content in page_contents:
        content_bytes = content.encode("latin-1")
        content_id = add_object(
            b"<< /Length "
            + str(len(content_bytes)).encode("ascii")
            + b" >>\nstream\n"
            + content_bytes
            + b"\nendstream"
        )
        page_id = add_object(
            (
                f"<< /Type /Page /Parent {pages_object_id} 0 R "
                f"/MediaBox [0 0 {page_width:.0f} {page_height:.0f}] "
                f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            )
        )
        page_ids.append(page_id)

    add_object(
        f"<< /Type /Catalog /Pages {pages_object_id} 0 R /ViewerPreferences << /DisplayDocTitle true >> >>"
    )
    catalog_id = len(objects)
    title_id = add_object(
        f"<< /Title ({_pdf_escape(title)}) /Producer ({_pdf_escape(APP_TITLE)}) >>"
    )

    pages_kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_object_id - 1] = (
        f"<< /Type /Pages /Kids [{pages_kids}] /Count {len(page_ids)} >>".encode("latin-1")
    )

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, payload in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(payload)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R /Info {title_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("ascii")
    )
    return bytes(pdf)


def _rounded_rect(x: float, y: float, width: float, height: float, radius: float, *, fill: bool) -> str:
    k = 0.5522847498
    op = "b" if fill else "s"
    return (
        f"{x + radius:.2f} {y:.2f} m\n"
        f"{x + width - radius:.2f} {y:.2f} l\n"
        f"{x + width - radius + (radius * k):.2f} {y:.2f} "
        f"{x + width:.2f} {y + radius - (radius * k):.2f} "
        f"{x + width:.2f} {y + radius:.2f} c\n"
        f"{x + width:.2f} {y + height - radius:.2f} l\n"
        f"{x + width:.2f} {y + height - radius + (radius * k):.2f} "
        f"{x + width - radius + (radius * k):.2f} {y + height:.2f} "
        f"{x + width - radius:.2f} {y + height:.2f} c\n"
        f"{x + radius:.2f} {y + height:.2f} l\n"
        f"{x + radius - (radius * k):.2f} {y + height:.2f} "
        f"{x:.2f} {y + height - radius + (radius * k):.2f} "
        f"{x:.2f} {y + height - radius:.2f} c\n"
        f"{x:.2f} {y + radius:.2f} l\n"
        f"{x:.2f} {y + radius - (radius * k):.2f} "
        f"{x + radius - (radius * k):.2f} {y:.2f} "
        f"{x + radius:.2f} {y:.2f} c\n"
        f"{op}\n"
    )


def _text_command(
    text: str,
    x: float,
    y: float,
    font: str,
    size: float,
    *,
    color: tuple[float, float, float],
    centered: bool = False,
) -> str:
    escaped = _pdf_escape(text)
    if centered:
        width = _pdf_text_width(text, size=size)
        x -= width / 2.0
    return (
        _fill_color(*color)
        + f"BT /{font} {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({escaped}) Tj ET\n"
    )


def _pdf_text_width(text: str, *, size: float) -> float:
    average_character_width = 0.54
    return len(text) * size * average_character_width


def _fit_text(text: str, *, max_width: float, size: float) -> str:
    normalized = " ".join(str(text).split())
    if _pdf_text_width(normalized, size=size) <= max_width:
        return normalized

    truncated = normalized
    while truncated and _pdf_text_width(f"{truncated}...", size=size) > max_width:
        truncated = truncated[:-1].rstrip()
    return f"{truncated}..." if truncated else normalized[:1]


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _stroke_color(red: float, green: float, blue: float) -> str:
    return f"{red:.3f} {green:.3f} {blue:.3f} RG\n"


def _fill_color(red: float, green: float, blue: float) -> str:
    return f"{red:.3f} {green:.3f} {blue:.3f} rg\n"
