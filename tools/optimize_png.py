"""Lossless PNG storage conversion. Reads/writes image bytes, never source paths."""

import io
import struct
import sys

from PIL import Image, PngImagePlugin


def optimize_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Expected PNG input")
    image = Image.open(io.BytesIO(data))
    if any(dimension < 1 or dimension > 4096 for dimension in image.size):
        raise ValueError("PNG dimensions exceed the approved bounds")
    if image.mode not in ("RGB", "RGBA", "P", "L", "LA"):
        raise ValueError("Unsupported PNG precision or mode")
    rgba = image.convert("RGBA")
    metadata = PngImagePlugin.PngInfo()
    offset = 8
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        if kind == b"iCCP":
            raise ValueError("Embedded color profiles require separate metadata review")
        if kind in (b"sRGB", b"gAMA", b"cHRM"):
            metadata.add(kind, payload)
        offset += length + 12
    variants = [rgba]
    if rgba.getextrema()[3] == (255, 255):
        rgb = rgba.convert("RGB")
        variants = [rgb]
        colors = rgb.getcolors(256)
        if colors:
            palette = sorted(color for _, color in colors)
            lookup = {color: index for index, color in enumerate(palette)}
            pixels = rgb.load()
            indexed = Image.frombytes("P", rgb.size, bytes(
                lookup[pixels[x, y]] for y in range(rgb.height) for x in range(rgb.width)
            ))
            indexed.putpalette([channel for color in palette for channel in color])
            variants.append(indexed)
    results = []
    for variant in variants:
        output = io.BytesIO()
        variant.save(output, format="PNG", optimize=True, compress_level=9, pnginfo=metadata)
        encoded = output.getvalue()
        decoded = Image.open(io.BytesIO(encoded))
        if decoded.size != image.size or decoded.convert("RGBA").tobytes() != rgba.tobytes():
            raise ValueError("PNG encoding changed decoded pixels")
        results.append(encoded)
    return min(results, key=len)


if __name__ == "__main__":
    sys.stdout.buffer.write(optimize_png(sys.stdin.buffer.read()))
