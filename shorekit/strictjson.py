"""Strict JSON: printable ASCII, no backslash escapes, no floats, no duplicate keys, bounded size
and depth. Canonical form: sorted keys, no whitespace."""
import json
import re

from .errors import ShoreError

# Bytes a document may contain: printable ASCII except the backslash, plus tab, LF and CR.
_ALLOWED = bytes(b for b in range(0x20, 0x7F) if b != 0x5C) + b"\t\n\r"
_STRUCT = re.compile(rb'[\[\]{}"]')
MAX_INT_DIGITS = 15


class _Reject(Exception):
    pass


def _no_float(s):
    raise ShoreError("E_PARSE", "number %s is not an integer (no decimals or exponents)" % s[:24])


def _no_constant(s):
    raise ShoreError("E_PARSE", "%s is not allowed" % s)


def _int(s):
    digits = s[1:] if s[:1] == "-" else s
    if len(digits) > MAX_INT_DIGITS:
        raise ShoreError("E_PARSE", "integer with %d digits, max %d" % (len(digits), MAX_INT_DIGITS))
    return int(s)


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ShoreError("E_PARSE", 'duplicate key "%s"' % k[:40])
        out[k] = v
    return out


def _check_depth(data, max_depth, what):
    depth = 0
    in_str = False
    for m in _STRUCT.finditer(data):
        c = m.group()
        if c == b'"':
            in_str = not in_str
        elif in_str:
            continue
        elif c in (b"[", b"{"):
            depth += 1
            if depth > max_depth:
                raise ShoreError("E_PARSE", "%s nests deeper than %d at offset %d" % (what, max_depth, m.start()))
        else:
            depth -= 1


def loads(data, limit, max_depth, what="document"):
    """Parse `data` (bytes) as a strict JSON object. Raises ShoreError E_PARSE."""
    if type(data) is not bytes:
        raise ShoreError("E_PARSE", "%s must be bytes" % what)
    if len(data) > limit:
        raise ShoreError("E_PARSE", "%s is %d bytes, max %d" % (what, len(data), limit))
    bad = data.translate(None, _ALLOWED)
    if bad:
        pos = data.index(bad[:1])
        raise ShoreError("E_PARSE", "%s has byte 0x%02x at offset %d (printable ASCII only, no backslash escapes)"
                         % (what, bad[0], pos))
    _check_depth(data, max_depth, what)
    try:
        obj = json.loads(data.decode("ascii"), object_pairs_hook=_pairs, parse_float=_no_float,
                         parse_constant=_no_constant, parse_int=_int)
    except ShoreError:
        raise
    except json.JSONDecodeError as e:
        raise ShoreError("E_PARSE", "%s: %s at line %d column %d" % (what, e.msg, e.lineno, e.colno))
    except (ValueError, RecursionError) as e:
        raise ShoreError("E_PARSE", "%s: %s" % (what, str(e)[:80]))
    if type(obj) is not dict:
        raise ShoreError("E_PARSE", "%s must be a JSON object" % what)
    return obj


def canonical(obj):
    """Canonical bytes: sorted keys, separators without spaces, ASCII."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def is_int(v):
    return type(v) is int


def is_str(v):
    return type(v) is str
