"""Hand-built PNGs for tests: any colour type, any filter per row, any chunk order."""
import struct
import zlib

SIG = b"\x89PNG\r\n\x1a\n"


def chunk(kind, data, crc=None):
    c = zlib.crc32(kind + data) & 0xFFFFFFFF if crc is None else crc
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", c)


def ihdr(w, h, depth=8, ctype=6, comp=0, filt=0, inter=0):
    return chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, comp, filt, inter))


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def filter_rows(rows, bpp, filters):
    """rows: list of bytes (unfiltered). filters: one filter type per row (cycled)."""
    out = bytearray()
    prev = bytes(len(rows[0]))
    for y, row in enumerate(rows):
        f = filters[y % len(filters)]
        out.append(f)
        for i in range(len(row)):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            pred = (0, a, b, (a + b) >> 1, _paeth(a, b, c))[f]
            out.append((row[i] - pred) & 0xFF)
        prev = row
    return bytes(out)


def png(w, h, rows, ctype=6, filters=(0,), plte=None, trns=None, extra=(), idat_split=1):
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    data = zlib.compress(filter_rows(rows, bpp, filters))
    parts = [SIG, ihdr(w, h, ctype=ctype)]
    if plte is not None:
        parts.append(chunk(b"PLTE", plte))
    if trns is not None:
        parts.append(chunk(b"tRNS", trns))
    parts += list(extra)
    step = max(1, -(-len(data) // idat_split))
    for i in range(0, len(data), step):
        parts.append(chunk(b"IDAT", data[i:i + step]))
    parts.append(chunk(b"IEND", b""))
    return b"".join(parts)


def rgba_rows(pixels, w):
    """pixels: list of (r,g,b,a) row-major."""
    return [bytes(c for p in pixels[y * w:(y + 1) * w] for c in p) for y in range(len(pixels) // w)]
