"""Campus photo checks: where was it taken, and has anyone submitted it before?

GPS comes from the photo's EXIF block; a phone camera writes it at capture
time. The perceptual hash (pHash) survives re-encoding, resizing and small
colour edits, so a lab photo lifted from another college's submission still
matches even when its bytes differ.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import imagehash
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


def inspect(path: Path) -> PhotoInfo:
    with Image.open(path) as img:
        gps = read_gps(img)
        h = imagehash.phash(img.convert("RGB"))
    lat, lon = gps if gps else (None, None)
    return PhotoInfo(path.name, str(h), lat, lon)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def hamming(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


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
