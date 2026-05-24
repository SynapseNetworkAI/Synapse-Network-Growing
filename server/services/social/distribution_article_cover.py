"""Pure-Python cover image generation for X Article packs."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

RGB = tuple[int, int, int]

FONT_5X7 = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "|": ("00100", "00100", "00100", "00100", "00100", "00100", "00100"),
}


def write_article_cover_png(path: Path) -> None:
    width, height = 1200, 675
    pixels = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            _set_pixel(pixels, width, x, y, _cover_pixel_rgb(x, y, width, height))

    _draw_text(pixels, width, 96, 245, "SYNAPSE NETWORK", 8, (245, 255, 251))
    _draw_text(pixels, width, 96, 325, "PAYMENT RAILS FOR AI AGENTS", 4, (24, 230, 197))
    _draw_text(
        pixels,
        width,
        96,
        410,
        "DISCOVER SERVICES | PAY METERED APIS | KEEP RECEIPTS",
        3,
        (185, 207, 203),
    )

    rows = [
        b"\x00" + bytes(pixels[y * width * 3 : (y + 1) * width * 3])
        for y in range(height)
    ]
    png = b"\x89PNG\r\n\x1a\n" + _png_chunk(
        b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    )
    png += _png_chunk(b"IDAT", zlib.compress(b"".join(rows), level=9))
    png += _png_chunk(b"IEND", b"")
    path.write_bytes(png)


def _draw_text(
    pixels: bytearray,
    width: int,
    x: int,
    y: int,
    text: str,
    scale: int,
    color: RGB,
) -> None:
    cursor = x
    for char in text.upper():
        if char == " ":
            cursor += scale * 4
            continue
        glyph = FONT_5X7.get(char)
        if glyph is None:
            cursor += scale * 4
            continue
        _draw_glyph(pixels, width, cursor, y, glyph, scale, color)
        cursor += scale * 6


def _draw_glyph(
    pixels: bytearray,
    width: int,
    x: int,
    y: int,
    glyph: tuple[str, ...],
    scale: int,
    color: RGB,
) -> None:
    for row_index, row in enumerate(glyph):
        for col_index, bit in enumerate(row):
            if bit != "1":
                continue
            _fill_rect(
                pixels,
                width,
                x + col_index * scale,
                y + row_index * scale,
                scale,
                scale,
                color,
            )


def _fill_rect(
    pixels: bytearray, width: int, x: int, y: int, w: int, h: int, color: RGB
) -> None:
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            _set_pixel(pixels, width, xx, yy, color)


def _set_pixel(pixels: bytearray, width: int, x: int, y: int, color: RGB) -> None:
    offset = (y * width + x) * 3
    pixels[offset : offset + 3] = bytes(color)


def _cover_pixel_rgb(x: int, y: int, width: int, height: int) -> RGB:
    glow = int(50 * (x / width) + 35 * (1 - y / height))
    if 92 < x < 1120 and 120 < y < 128:
        return (21, 230, 190)
    if 92 < x < 760 and 555 < y < 562:
        return (211, 169, 76)
    if 860 < x < 1120 and 150 < y < 500:
        return (10, 85 + glow, 76 + glow)
    if 80 < x < 1120 and 120 < y < 555:
        return (5, 39 + glow // 2, 36 + glow // 3)
    return (2, 8 + glow // 3, 10 + glow // 4)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )
