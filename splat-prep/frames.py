#!/usr/bin/env python3
"""Frames uit video halen voor Gaussian splatting.

Gebruik:  frames <scene-map> [--fps N] [--hdr] [--cpu]

Verwacht in de scene-map een map input/ met een of meer video's.
Stappen:
  1. ffmpeg haalt frames uit op 2x de doel-fps (standaard 6 fps).
     De video wordt op de GPU gedecodeerd (NVDEC); lukt dat niet, dan
     automatisch opnieuw op de CPU. Met --cpu altijd op de CPU.
     Met --hdr wordt HDR-video (HLG/PQ, bijvoorbeeld van een iPhone) eerst
     omgezet naar normaal SDR-beeld, anders worden de frames flets.
  2. Van elk frame wordt de scherpte gemeten (variantie van de Laplaciaan).
  3. Per groepje van 2 opeenvolgende frames blijft het scherpste over
     (standaard dus 3 fps).
  4. De behouden frames (JPG, hoge kwaliteit) gaan naar images/.
  5. Een overzicht komt in frames-report.csv en op het scherm, inclusief
     behouden frames die duidelijk onscherper zijn dan de rest.
"""

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mts", ".m2ts", ".mxf", ".webm"}
OVERSAMPLE = 2            # frames uithalen op OVERSAMPLE x doel-fps
MEASURE_WIDTH = 1024      # scherpte meten op een verkleinde versie
BLURRY_FACTOR = 0.5       # behouden frame < 50% van de mediaan = onscherp

# HDR (HLG/PQ) naar SDR (bt709) met tonemapping
HDR_TO_SDR = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)


def fail(msg):
    print(f"Fout: {msg}", file=sys.stderr)
    sys.exit(1)


def sharpness(path):
    """Variantie van de Laplaciaan op een grijze, verkleinde versie."""
    with Image.open(path) as im:
        im = im.convert("L")
        if im.width > MEASURE_WIDTH:
            h = round(im.height * MEASURE_WIDTH / im.width)
            im = im.resize((MEASURE_WIDTH, h), Image.BILINEAR)
        a = np.asarray(im, dtype=np.float32)
    lap = (a[1:-1, :-2] + a[1:-1, 2:] + a[:-2, 1:-1] + a[2:, 1:-1]
           - 4.0 * a[1:-1, 1:-1])
    return float(lap.var())


def run_ffmpeg(video, out_dir, vf, gpu):
    """ffmpeg draaien; met gpu=True wordt op de GPU gedecodeerd (NVDEC)."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats"]
    if gpu:
        cmd += ["-hwaccel", "cuda"]
    cmd += [
        "-i", str(video),
        "-vf", vf,
        "-qscale:v", "2",
        str(out_dir / "%06d.jpg"),
    ]
    return subprocess.run(cmd).returncode == 0


def extract(video, out_dir, fps, hdr, cpu_only):
    """Frames uit een video halen als JPG van hoge kwaliteit.

    Geeft de frames terug en de gebruikte route ("GPU" of "CPU")."""
    vf = f"fps={fps}"
    if hdr:
        vf += "," + HDR_TO_SDR

    if not cpu_only:
        if run_ffmpeg(video, out_dir, vf, gpu=True):
            return sorted(out_dir.glob("*.jpg")), "GPU"
        print("  GPU-decodering mislukt, opnieuw op de CPU")

    if not run_ffmpeg(video, out_dir, vf, gpu=False):
        fail(f"ffmpeg kon {video.name} niet verwerken")
    return sorted(out_dir.glob("*.jpg")), "CPU"


def main():
    p = argparse.ArgumentParser(description="Scherpste frames uit video halen.")
    p.add_argument("scene", type=Path, help="scene-map met input/")
    p.add_argument("--fps", type=float, default=3.0,
                   help="aantal behouden frames per seconde (standaard 3)")
    p.add_argument("--hdr", action="store_true",
                   help="HDR-video (HLG/PQ) omzetten naar SDR")
    p.add_argument("--cpu", action="store_true",
                   help="niet op de GPU decoderen")
    args = p.parse_args()

    if args.fps <= 0:
        fail("--fps moet groter dan 0 zijn")

    scene = args.scene.resolve()
    input_dir = scene / "input"
    images_dir = scene / "images"
    tmp_dir = scene / ".frames-tmp"
    report_path = scene / "frames-report.csv"

    if not input_dir.is_dir():
        fail(f"{input_dir} bestaat niet")
    videos = sorted(f for f in input_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in VIDEO_EXT)
    if not videos:
        fail(f"geen video gevonden in {input_dir}")
    if images_dir.exists() and any(images_dir.iterdir()):
        fail(f"{images_dir} is niet leeg; leeg of verwijder hem eerst")
    if (scene / "images_raw").exists():
        fail(f"{scene / 'images_raw'} bestaat nog van een eerdere colmap-run; "
             "verwijder die eerst")

    for sub in ("images", "sparse", "lfs-output"):
        (scene / sub).mkdir(exist_ok=True)
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)

    extract_fps = args.fps * OVERSAMPLE
    rows = []          # (video, bronframe, score, behouden, uitvoernaam)
    routes = []        # (video, route)
    counter = 0

    try:
        for vi, video in enumerate(videos, 1):
            mode = ", HDR naar SDR" if args.hdr else ""
            print(f"[{vi}/{len(videos)}] {video.name}: frames uithalen op {extract_fps:g} fps{mode}")
            frames, route = extract(video, tmp_dir / f"v{vi}", extract_fps,
                                    args.hdr, args.cpu)
            routes.append((video.name, route))
            if not frames:
                print(f"  geen frames uit {video.name}, overgeslagen")
                continue

            print(f"  scherpte meten van {len(frames)} frames")
            scores = []
            for i, f in enumerate(frames, 1):
                scores.append(sharpness(f))
                if i % 50 == 0 or i == len(frames):
                    print(f"    {i}/{len(frames)}", end="\r", flush=True)
            print()

            # per groepje opeenvolgende frames het scherpste houden
            for start in range(0, len(frames), OVERSAMPLE):
                group = range(start, min(start + OVERSAMPLE, len(frames)))
                best = max(group, key=lambda i: scores[i])
                for i in group:
                    name = ""
                    if i == best:
                        counter += 1
                        name = f"frame_{counter:05d}.jpg"
                        shutil.move(str(frames[i]), str(images_dir / name))
                    rows.append((video.name, frames[i].name, scores[i], i == best, name))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    kept = [r for r in rows if r[3]]
    if not kept:
        fail("geen frames behouden")

    median = float(np.median([r[2] for r in kept]))
    blurry = [r for r in kept if r[2] < median * BLURRY_FACTOR]
    blurry_names = {r[4] for r in blurry}

    with open(report_path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["video", "bronframe", "scherpte", "status", "bestand"])
        for video, src, score, keep, name in rows:
            if not keep:
                status = "weg"
            elif name in blurry_names:
                status = "onscherp"
            else:
                status = "behouden"
            w.writerow([video, src, f"{score:.1f}", status, name])

    print()
    for name, route in routes:
        print(f"Decodering {name}: {route}")
    print(f"Uitgehaald:  {len(rows)} frames")
    print(f"Behouden:    {len(kept)} frames in {images_dir}")
    print(f"Mediaan scherpte behouden frames: {median:.1f}")
    if blurry:
        print(f"Onscherp ({len(blurry)}, scherpte < {BLURRY_FACTOR:.0%} van mediaan) - "
              "staan wel in images/, eventueel zelf verwijderen:")
        for r in blurry:
            print(f"  {r[4]}  ({r[2]:.1f})")
    else:
        print("Geen opvallend onscherpe frames.")
    print(f"Overzicht:   {report_path}")


if __name__ == "__main__":
    main()
