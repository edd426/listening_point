"""PNG, three ways, all bounded before anything is inflated.

* write_png: 8-bit greyscale or RGB, filter 0 on every row (the form reference files must take).
* read_import_png: the strict reader for an author's own picture (<=64 KiB, <=64x64, 8-bit,
  non-interlaced; the header is checked before a byte is inflated, inflation is capped at the
  exact size the header implies, and nothing may follow IEND).
* read_reference_png: the bounded reader for the trusted 1280x640 reference images (keepout.png
  and the crops), which accepts only the exact form write_png produces.
"""
import struct
import zlib

from .errors import ShoreError

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}

IMPORT_MAX_BYTES = 65536
IMPORT_MAX_SIDE = 64
IMPORT_MAX_CHUNKS = 64

REF_W, REF_H = 1280, 640
REF_MAX_BYTES = {0: 2 * 1024 * 1024, 2: 8 * 1024 * 1024}


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(width, height, pixels, color_type=2, level=6):
    """pixels: bytes of height*width*channels, rows top to bottom. Returns the PNG bytes."""
    ch = CHANNELS[color_type]
    stride = width * ch
    if color_type not in (0, 2) or len(pixels) != height * stride:
        raise ValueError("write_png: bad pixel buffer")
    raw = bytearray()
    for y in range(height):
        raw += b"\x00"
        raw += pixels[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(raw), level)) + _chunk(b"IEND", b"")


def _chunks(data, err, max_chunks):
    """Yield (type, body, offset) for each chunk, checking lengths and CRCs; stops after IEND."""
    if data[:8] != SIGNATURE:
        raise ShoreError(err, "not a PNG (bad signature)")
    pos = 8
    n = 0
    end = len(data)
    while True:
        if pos + 12 > end:
            raise ShoreError(err, "truncated chunk header at offset %d" % pos)
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        if not all(0x41 <= b <= 0x5A or 0x61 <= b <= 0x7A for b in kind):
            raise ShoreError(err, "bad chunk type at offset %d" % pos)
        if length > end - pos - 12:
            raise ShoreError(err, "chunk %s at offset %d runs past the end of the file" % (kind.decode("ascii"), pos))
        body = data[pos + 8:pos + 8 + length]
        crc = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise ShoreError(err, "chunk %s at offset %d has a bad CRC" % (kind.decode("ascii"), pos))
        n += 1
        if n > max_chunks:
            raise ShoreError(err, "more than %d chunks" % max_chunks)
        yield kind, body, pos
        pos += 12 + length
        if kind == b"IEND":
            if pos != end:
                raise ShoreError(err, "%d bytes follow IEND" % (end - pos))
            return


def _inflate(idat, expected, err):
    d = zlib.decompressobj()
    try:
        out = d.decompress(idat, expected + 1)
    except zlib.error as e:
        raise ShoreError(err, "bad image data (%s)" % str(e)[:60])
    if len(out) != expected:
        raise ShoreError(err, "image data inflates to %s bytes, the header implies %d"
                         % ("more than %d" % expected if len(out) > expected else str(len(out)), expected))
    if not d.eof:
        raise ShoreError(err, "image data does not end where the header says it should")
    if d.unused_data or d.unconsumed_tail:
        raise ShoreError(err, "bytes follow the image data stream")
    return out


def _paeth(a, b, c):
    p = a + b - c
    pa = p - a if p >= a else a - p
    pb = p - b if p >= b else b - p
    pc = p - c if p >= c else c - p
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw, width, height, bpp, err):
    stride = width * bpp
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        f = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if f == 0:
            pass
        elif f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                up_left = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], up_left)) & 0xFF
        else:
            raise ShoreError(err, "row %d has unknown filter type %d" % (y, f))
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def read_import_png(data):
    """Strict reader for an author's own PNG. Returns (width, height, [(r, g, b, a), ...])."""
    err = "E_IMPORT"
    if type(data) is not bytes:
        raise ShoreError(err, "input must be bytes")
    if len(data) > IMPORT_MAX_BYTES:
        raise ShoreError(err, "file is %d bytes, max %d" % (len(data), IMPORT_MAX_BYTES))
    ihdr = None
    plte = None
    trns = None
    idat = []
    idat_state = 0      # 0 before IDAT, 1 inside the run, 2 after it
    seen_iend = False
    for kind, body, pos in _chunks(data, err, IMPORT_MAX_CHUNKS):
        if ihdr is None and kind != b"IHDR":
            raise ShoreError(err, "IHDR must come first, found %s" % kind.decode("ascii"))
        if kind == b"IHDR":
            if ihdr is not None:
                raise ShoreError(err, "second IHDR")
            if len(body) != 13:
                raise ShoreError(err, "IHDR is %d bytes, must be 13" % len(body))
            w, h, depth, ctype, comp, filt, inter = struct.unpack(">IIBBBBB", body)
            if not (1 <= w <= IMPORT_MAX_SIDE and 1 <= h <= IMPORT_MAX_SIDE):
                raise ShoreError(err, "image is %dx%d, max %dx%d" % (w, h, IMPORT_MAX_SIDE, IMPORT_MAX_SIDE))
            if depth != 8:
                raise ShoreError(err, "bit depth %d, must be 8" % depth)
            if ctype not in CHANNELS:
                raise ShoreError(err, "colour type %d is not allowed" % ctype)
            if comp != 0 or filt != 0:
                raise ShoreError(err, "unknown compression or filter method")
            if inter != 0:
                raise ShoreError(err, "interlaced images are not allowed")
            ihdr = (w, h, ctype)
        elif kind == b"PLTE":
            if plte is not None or idat_state:
                raise ShoreError(err, "PLTE out of place")
            if ihdr[2] in (0, 4):
                raise ShoreError(err, "PLTE in a greyscale image")
            if len(body) % 3 or not 3 <= len(body) <= 768:
                raise ShoreError(err, "PLTE must hold 1-256 RGB entries")
            plte = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif kind == b"tRNS":
            if trns is not None or idat_state:
                raise ShoreError(err, "tRNS out of place")
            ct = ihdr[2]
            if ct == 3:
                if plte is None or len(body) > len(plte):
                    raise ShoreError(err, "tRNS longer than PLTE, or before it")
                trns = bytes(body)
            elif ct == 0 and len(body) == 2:
                v = struct.unpack(">H", body)[0]
                if v > 255:
                    raise ShoreError(err, "tRNS grey value out of range")
                trns = (v,)
            elif ct == 2 and len(body) == 6:
                v = struct.unpack(">HHH", body)
                if max(v) > 255:
                    raise ShoreError(err, "tRNS colour out of range")
                trns = v
            else:
                raise ShoreError(err, "tRNS not allowed for colour type %d" % ct)
        elif kind == b"IDAT":
            if idat_state == 2:
                raise ShoreError(err, "IDAT chunks are not consecutive")
            idat_state = 1
            idat.append(body)
        elif kind == b"IEND":
            if body:
                raise ShoreError(err, "IEND carries data")
            seen_iend = True
        else:
            if not 0x61 <= kind[0] <= 0x7A:
                raise ShoreError(err, "unknown critical chunk %s" % kind.decode("ascii"))
            if idat_state == 1:
                idat_state = 2
    if not seen_iend:
        raise ShoreError(err, "no IEND")
    if not idat:
        raise ShoreError(err, "no image data")
    w, h, ctype = ihdr
    if ctype == 3 and plte is None:
        raise ShoreError(err, "palette image without PLTE")
    bpp = CHANNELS[ctype]
    raw = _inflate(b"".join(idat), h * (1 + w * bpp), err)
    px = _unfilter(raw, w, h, bpp, err)
    out = []
    for i in range(w * h):
        if ctype == 6:
            r, g, b, a = px[4 * i:4 * i + 4]
        elif ctype == 2:
            r, g, b = px[3 * i:3 * i + 3]
            a = 0 if trns is not None and (r, g, b) == trns else 255
        elif ctype == 0:
            r = g = b = px[i]
            a = 0 if trns is not None and r == trns[0] else 255
        elif ctype == 4:
            r = g = b = px[2 * i]
            a = px[2 * i + 1]
        else:
            k = px[i]
            if k >= len(plte):
                raise ShoreError(err, "pixel (%d,%d) uses palette index %d of %d" % (i % w, i // w, k, len(plte)))
            r, g, b = plte[k]
            a = trns[k] if trns is not None and k < len(trns) else 255
        out.append((r, g, b, a))
    return w, h, out


def read_reference_png(data, color_type, what):
    """Bounded reader for a trusted 1280x640 reference image written by write_png.

    color_type 0 (keepout.png, values 0 or 255) or 2 (a crop). Returns the pixel bytes."""
    err = "E_REFDATA"
    if type(data) is not bytes:
        raise ShoreError(err, "%s: input must be bytes" % what)
    limit = REF_MAX_BYTES[color_type]
    if len(data) > limit:
        raise ShoreError(err, "%s is %d bytes, max %d" % (what, len(data), limit))
    ihdr = None
    idat = []
    for kind, body, pos in _chunks(data, err, 4096):
        if ihdr is None:
            if kind != b"IHDR" or len(body) != 13:
                raise ShoreError(err, "%s: IHDR must come first" % what)
            w, h, depth, ctype, comp, filt, inter = struct.unpack(">IIBBBBB", body)
            if (w, h) != (REF_W, REF_H):
                raise ShoreError(err, "%s is %dx%d, must be %dx%d" % (what, w, h, REF_W, REF_H))
            if (depth, ctype, comp, filt, inter) != (8, color_type, 0, 0, 0):
                raise ShoreError(err, "%s must be 8-bit, colour type %d, not interlaced" % (what, color_type))
            ihdr = True
        elif kind == b"IDAT":
            idat.append(body)       # any other chunk is refused, so the IDAT run is unbroken
        elif kind == b"IEND":
            if body:
                raise ShoreError(err, "%s: IEND carries data" % what)
        else:
            raise ShoreError(err, "%s: unexpected chunk %s" % (what, kind.decode("ascii")))
    if ihdr is None or not idat:
        raise ShoreError(err, "%s: no image data" % what)
    stride = REF_W * CHANNELS[color_type]
    raw = _inflate(b"".join(idat), REF_H * (1 + stride), err)
    filters = raw[0::stride + 1]
    if filters.count(0) != REF_H:
        raise ShoreError(err, "%s: every row must use filter 0" % what)
    out = bytearray(REF_H * stride)
    for y in range(REF_H):
        out[y * stride:(y + 1) * stride] = raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)]
    if color_type == 0:
        if out.translate(None, b"\x00\xff"):
            raise ShoreError(err, "%s: values must be 0 (open) or 255 (keep-out)" % what)
    return bytes(out)
