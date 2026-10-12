"""Raw-socket SCPI helpers for the RIGOL MSO5104 (port 5555), without pyvisa."""
import json
import os
import pathlib
import socket
import struct
import zlib

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_ADDR = "192.168.137.50"
DEFAULT_PORT = 5555
DEFAULT_BIND = "192.168.137.1"


def default_addr():
    addr = os.environ.get("SCOPE_ADDR")
    if not addr:
        cfg = HERE.parent / "config.json"
        if cfg.exists():
            addr = json.loads(cfg.read_text(encoding="utf-8")).get("addr")
    return addr or DEFAULT_ADDR


def default_bind():
    return os.environ.get("SCOPE_BIND", DEFAULT_BIND)


def connect(addr=None, port=DEFAULT_PORT, bind=None, timeout=8):
    """bind="" skips binding; Windows may otherwise route 192.168.137.x through Wi-Fi."""
    addr = addr or default_addr()
    bind = default_bind() if bind is None else bind
    s = socket.socket()
    s.settimeout(timeout)
    if bind:
        s.bind((bind, 0))
    s.connect((addr, port))
    return s


def write(s, c):
    s.sendall((c + "\n").encode())


def query(s, c):
    s.sendall((c + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        data += chunk
    return data.decode(errors="replace").strip()


def read_block(s, cmd):
    """Read an IEEE block (#N<len><data>). The trailing newline may stay in the socket; see drain()."""
    s.sendall((cmd + "\n").encode())
    buf = b""
    while b"#" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            raise RuntimeError("no block header")
        buf += chunk
    hash_at = buf.index(b"#")
    rest = buf[hash_at + 1 :]
    while len(rest) < 1:
        rest += s.recv(4096)
    nd = int(chr(rest[0]))
    rest = rest[1:]
    while len(rest) < nd:
        rest += s.recv(4096)
    nbytes = int(rest[:nd].decode())
    rest = rest[nd:]
    while len(rest) < nbytes:
        rest += s.recv(nbytes - len(rest))
    return rest[:nbytes]


def drain(s, timeout=0.5, restore=8):
    """Discard the newline left after a large block, or every later query reads one reply behind."""
    s.settimeout(timeout)
    try:
        s.recv(16)
    except socket.timeout:
        pass
    s.settimeout(restore)


def bmp_to_png(bmp: bytes) -> bytes:
    if bmp[:2] != b"BM":
        return bmp
    offset = struct.unpack_from("<I", bmp, 10)[0]
    width = struct.unpack_from("<i", bmp, 18)[0]
    height = struct.unpack_from("<i", bmp, 22)[0]
    bpp = struct.unpack_from("<H", bmp, 28)[0]
    flip = height > 0
    height = abs(height)
    row_raw = width * (bpp // 8)
    row_pad = (row_raw + 3) & ~3
    pixels = bmp[offset:]

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b""
    for y in range(height):
        src = (height - 1 - y) if flip else y
        row = pixels[src * row_pad : src * row_pad + row_raw]
        rgb = bytearray()
        step = bpp // 8
        for i in range(0, width * step, step):
            b, g, r = row[i], row[i + 1], row[i + 2]
            rgb += bytes((r, g, b))
        raw += b"\x00" + bytes(rgb)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def waveform(s, source="CHAN1"):
    write(s, f":WAV:SOUR {source}")
    write(s, ":WAV:MODE NORM")
    write(s, ":WAV:FORM BYTE")
    pre = [float(x) for x in query(s, ":WAV:PRE?").split(",")]
    _fmt, _typ, points, _cnt, xinc, xorig, xref, yinc, yorig, yref = pre
    raw = read_block(s, ":WAV:DATA?")
    vals = [(b - yorig - yref) * yinc for b in raw]
    times = [xorig + (i - xref) * xinc for i in range(len(vals))]
    return times, vals
