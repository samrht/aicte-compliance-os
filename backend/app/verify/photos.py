"""Campus photo checks: where was it taken, and has anyone submitted it before?

GPS comes from the photo's EXIF block; a phone camera writes it at capture
time. The perceptual hash (pHash) survives re-encoding, resizing and small
colour edits, so a lab photo lifted from another college's submission still
matches even when its bytes differ.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

GPS_IFD = 0x8825


@dataclass
class PhotoInfo:
    filename: str
    phash: str
    lat: float | None
    lon: float | None


def _dms(value, ref: str) -> float:
    d, m, s = (float(x) for x in value)
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W") else deg


def read_gps(img: Image.Image) -> tuple[float, float] | None:
    gps = img.getexif().get_ifd(GPS_IFD)
    if not gps or 2 not in gps or 4 not in gps:
        return None
    return _dms(gps[2], gps.get(1, "N")), _dms(gps[4], gps.get(3, "E"))


_N = 32
# DCT-II basis; scale is irrelevant because bits compare against the median.
_DCT = np.cos(np.pi * np.outer(np.arange(_N), 2 * np.arange(_N) + 1) / (2 * _N))


def phash(img: Image.Image) -> str:
    """64-bit perceptual hash: low 8x8 DCT frequencies of a 32x32 greyscale thumbnail vs their median."""
    px = np.asarray(img.convert("L").resize((_N, _N), Image.LANCZOS), dtype=float)
    low = (_DCT @ px @ _DCT.T)[:8, :8]
    bits = (low > np.median(low)).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def inspect(path: Path | None = None, data: bytes | None = None, filename: str | None = None) -> PhotoInfo:
    src = io.BytesIO(data) if data is not None else path
    with Image.open(src) as img:
        gps = read_gps(img)
        h = phash(img)
    lat, lon = gps if gps else (None, None)
    return PhotoInfo(filename or path.name, h, lat, lon)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def write_gps(img: Image.Image, lat: float, lon: float) -> Image.Exif:
    """EXIF carrying a GPS fix, for generating demo photos."""
    def dms(x: float):
        x = abs(x)
        d = int(x)
        m = int((x - d) * 60)
        s = round(((x - d) * 60 - m) * 60, 4)
        return (float(d), float(m), float(s))

    exif = img.getexif()
    exif.get_ifd(GPS_IFD).update({
        1: "N" if lat >= 0 else "S", 2: dms(lat),
        3: "E" if lon >= 0 else "W", 4: dms(lon),
    })
    return exif
