from __future__ import annotations

import struct
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
GIF_SIGNATURES = {b"GIF87a", b"GIF89a"}


def read_png_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """Return the pixel dimensions from a PNG IHDR without decoding the image."""
    if len(image_bytes) < 24 or image_bytes[:8] != PNG_SIGNATURE:
        raise ValueError("The image is not a valid PNG file.")
    if image_bytes[12:16] != b"IHDR":
        raise ValueError("The PNG file does not begin with an IHDR chunk.")
    width, height = struct.unpack(">II", image_bytes[16:24])
    if width < 1 or height < 1:
        raise ValueError("The PNG dimensions are invalid.")
    return width, height


def scaled_dimensions(
    width: int,
    height: int,
    *,
    max_width: int | None = None,
    max_height: int | None = None,
) -> tuple[int, int]:
    """Scale display dimensions proportionally without resampling the source pixels."""
    width = max(1, int(width))
    height = max(1, int(height))
    width_limit = max(1, int(max_width)) if max_width else width
    height_limit = max(1, int(max_height)) if max_height else height
    scale = min(1.0, width_limit / width, height_limit / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def write_png_icon(source_png: Path, destination: Path) -> Path:
    """Wrap one PNG image in the Windows ICO container using only stdlib code."""
    source_path = Path(source_png).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    image_bytes = source_path.read_bytes()
    width, height = read_png_dimensions(image_bytes)
    if width > 256 or height > 256:
        raise ValueError("PNG icons must be 256 by 256 pixels or smaller.")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    icon_header = struct.pack("<HHH", 0, 1, 1)
    directory_entry = struct.pack(
        "<BBBBHHII",
        0 if width == 256 else width,
        0 if height == 256 else height,
        0,
        0,
        1,
        32,
        len(image_bytes),
        22,
    )
    destination_path.write_bytes(icon_header + directory_entry + image_bytes)
    return destination_path


def read_gif_frame_durations(path: Path) -> list[int]:
    """Read GIF frame delays in milliseconds without decoding image pixels."""
    data = Path(path).read_bytes()
    if len(data) < 13 or data[:6] not in GIF_SIGNATURES:
        raise ValueError("The animation is not a valid GIF file.")

    position = 13
    logical_screen_flags = data[10]
    if logical_screen_flags & 0x80:
        position += 3 * (2 ** ((logical_screen_flags & 0x07) + 1))

    durations: list[int] = []
    pending_duration = 100
    while position < len(data):
        marker = data[position]
        position += 1
        if marker == 0x3B:
            break
        if marker == 0x21:
            if position >= len(data):
                raise ValueError("The GIF extension block is incomplete.")
            label = data[position]
            position += 1
            if label == 0xF9:
                if position >= len(data):
                    raise ValueError("The GIF control block is incomplete.")
                block_size = data[position]
                position += 1
                block = data[position : position + block_size]
                position += block_size
                if block_size != 4 or len(block) != 4:
                    raise ValueError("The GIF control block has an invalid size.")
                if position >= len(data) or data[position] != 0:
                    raise ValueError("The GIF control block is missing its terminator.")
                position += 1
                delay_ms = int.from_bytes(block[1:3], "little") * 10
                pending_duration = delay_ms or 100
            else:
                position = _skip_gif_subblocks(data, position)
            continue
        if marker != 0x2C:
            raise ValueError(f"Unsupported GIF block marker 0x{marker:02X}.")
        if position + 9 > len(data):
            raise ValueError("The GIF image descriptor is incomplete.")
        image_flags = data[position + 8]
        position += 9
        if image_flags & 0x80:
            position += 3 * (2 ** ((image_flags & 0x07) + 1))
        if position >= len(data):
            raise ValueError("The GIF image data is incomplete.")
        position += 1  # LZW minimum code size
        position = _skip_gif_subblocks(data, position)
        durations.append(pending_duration)
        pending_duration = 100

    if not durations:
        raise ValueError("The GIF contains no image frames.")
    return durations


def _skip_gif_subblocks(data: bytes, position: int) -> int:
    while position < len(data):
        block_size = data[position]
        position += 1
        if block_size == 0:
            return position
        position += block_size
        if position > len(data):
            raise ValueError("The GIF data sub-block is incomplete.")
    raise ValueError("The GIF data sub-block is missing its terminator.")
