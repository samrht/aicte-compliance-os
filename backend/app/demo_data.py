"""Synthetic evidence: campus photos with GPS, faculty rosters, financial PDFs.

All institutions, people and figures are fictional. The generators are
seeded so a reset reproduces the same demo world.
"""
from __future__ import annotations

import csv
import io
import math
import random
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from app.verify.photos import write_gps

FIRST = ["Aarav", "Vivaan", "Aditi", "Ishaan", "Kavya", "Rohan", "Meera", "Arjun", "Sneha", "Kabir",
         "Ananya", "Vikram", "Pooja", "Rahul", "Nisha", "Siddharth", "Priya", "Manish", "Divya",
         "Harsh", "Neha", "Karan", "Ritika", "Amit", "Shruti", "Yash", "Tanvi", "Nikhil", "Isha", "Varun"]
LAST = ["Sharma", "Verma", "Iyer", "Nair", "Reddy", "Gupta", "Patel", "Joshi", "Rao", "Kulkarni",
        "Menon", "Das", "Mishra", "Pillai", "Chauhan", "Bhat", "Saxena", "Pandey", "Ghosh", "Mehta"]
DESIGNATIONS = ["Professor", "Associate Professor", "Assistant Professor", "Assistant Professor",
                "Assistant Professor"]


def person(rng: random.Random) -> dict:
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    pan = "".join(rng.choice(letters) for _ in range(3)) + "P" + rng.choice(letters) + \
        f"{rng.randint(1000, 9999)}" + rng.choice(letters)
    dob = f"{rng.randint(1, 28):02d}-{rng.randint(1, 12):02d}-{rng.randint(1962, 1994)}"
    return {"name": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "pan": pan, "dob": dob}


def roster(rng: random.Random, n: int, phd_share: float, borrowed: list[dict] | None = None) -> list[dict]:
    rows = []
    for i in range(n):
        p = person(rng)
        desig = DESIGNATIONS[min(i % 7, 4)] if i else "Professor"
        qual = "PhD" if rng.random() < phd_share else rng.choice(["M.Tech", "M.E.", "M.Tech"])
        rows.append(p | {"designation": desig, "qualification": qual})
    for b in borrowed or []:
        rows[rng.randrange(len(rows))] = b
    return rows


def roster_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["name", "pan", "dob", "designation", "qualification"])
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


# --- Photos -------------------------------------------------------------------------

SKIES = [((120, 170, 230), (210, 230, 250)), ((250, 190, 140), (255, 230, 200)),
         ((90, 130, 190), (180, 205, 235)), ((170, 190, 210), (225, 230, 235))]
WALLS = [(205, 92, 70), (230, 214, 180), (180, 180, 190), (240, 236, 225), (196, 140, 100),
         (150, 170, 190), (220, 190, 120)]


def campus_photo(rng: random.Random, w: int = 640, h: int = 420) -> Image.Image:
    """A procedurally drawn campus scene, different enough per seed to hash apart."""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    top, bottom = rng.choice(SKIES)
    horizon = int(h * rng.uniform(0.35, 0.7))
    for y in range(horizon):
        t = y / max(1, horizon)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    ground = rng.choice([(110, 140, 80), (150, 140, 110), (120, 120, 120), (95, 125, 70)])
    d.rectangle([0, horizon, w, h], fill=ground)
    # Big blocks placed at random so the low-frequency layout (what pHash sees) varies.
    for _ in range(rng.randint(2, 5)):
        bw, bh = rng.randint(80, 300), rng.randint(60, int(horizon * 0.95))
        x = rng.randint(-40, w - 40)
        wall = rng.choice(WALLS)
        d.rectangle([x, horizon - bh, x + bw, horizon + rng.randint(0, 25)], fill=wall)
        dark = tuple(max(0, c - 90) for c in wall)
        for wy in range(horizon - bh + 12, horizon - 10, rng.randint(18, 30)):
            for wx in range(x + 8, x + bw - 14, rng.randint(18, 30)):
                d.rectangle([wx, wy, wx + 9, wy + 11], fill=dark)
    for _ in range(rng.randint(3, 10)):
        cx, cy, r = rng.randint(0, w), horizon + rng.randint(-10, 30), rng.randint(14, 48)
        d.ellipse([cx - r, cy - 2 * r, cx + r, cy], fill=(40 + rng.randint(0, 50), 100 + rng.randint(0, 60), 40))
    if rng.random() < 0.6:   # a path or road
        x0 = rng.randint(0, w)
        d.polygon([(x0, horizon), (x0 + 30, horizon), (rng.randint(0, w), h), (rng.randint(0, w) - 200, h)],
                  fill=(185, 180, 170))
    return img.filter(ImageFilter.GaussianBlur(0.6))


def offset_point(lat: float, lon: float, km: float, bearing_deg: float) -> tuple[float, float]:
    dlat = km / 111.0 * math.cos(math.radians(bearing_deg))
    dlon = km / (111.0 * math.cos(math.radians(lat))) * math.sin(math.radians(bearing_deg))
    return lat + dlat, lon + dlon


def save_photo(img: Image.Image, path: Path, lat: float | None, lon: float | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if lat is None:
        img.save(path, "JPEG", quality=88)
    else:
        img.save(path, "JPEG", quality=88, exif=write_gps(img, lat, lon))


def recycle(src: Path, dst: Path, lat: float, lon: float) -> None:
    """What a cheating college does: crop a little, brighten, re-save with new GPS."""
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        im = im.crop((8, 6, w - 6, h - 8)).resize((720, 470))
        im = ImageEnhance.Brightness(im).enhance(1.08)
        save_photo(im, dst, lat, lon)


# --- Financial statement ------------------------------------------------------------------

def financial_pdf(path: Path, name: str, revenue: float, expenditure: float, corpus: float,
                  year: str = "2025-26") -> None:
    salaries = round(expenditure * 0.58, 2)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Audited Statement of Income and Expenditure, FY {year}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Prepared under the AICTE Approval Process Handbook financial disclosure format.",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    lines = [
        ("Tuition and fee receipts", revenue * 0.86),
        ("Grants and other income", revenue * 0.14),
        ("Total Revenue", revenue),
        ("Salaries", salaries),
        ("Infrastructure and maintenance", expenditure * 0.27),
        ("Other operating expenses", expenditure - salaries - expenditure * 0.27),
        ("Total Expenditure", expenditure),
        ("Corpus Fund (FDR)", corpus),
    ]
    for label, value in lines:
        bold = label.startswith("Total") or label.startswith("Corpus")
        pdf.set_font("Helvetica", "B" if bold else "", 11)
        pdf.cell(120, 8, f"{label} (Rs. lakh):")
        pdf.cell(50, 8, f"{value:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 6, "Certified by the statutory auditor. Figures in Rs. lakh.", new_x="LMARGIN", new_y="NEXT")
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
