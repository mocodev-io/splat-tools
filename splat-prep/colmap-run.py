#!/usr/bin/env python3
"""Camera-posities berekenen met COLMAP voor Gaussian splatting.

Gebruik:  colmap-run <scene-map>

Verwacht in de scene-map een map images/ met frames (bijvoorbeeld van `frames`).
Stappen:
  1. feature_extractor  - kenmerken zoeken in elk frame (GPU), een gedeelde
                          camera met model OPENCV (lensvervorming wordt meegeschat).
  2. sequential_matcher - frames vergelijken met hun buren (GPU), past bij video.
  3. global_mapper      - reconstructie, resultaat in sparse/0/.
Daarna een overzicht: hoeveel frames een camera-positie hebben gekregen.

Het resultaat (images/ + sparse/0/) kan direct naar LichtFeld.
"""

import argparse
import struct
import subprocess
import sys
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def fail(msg):
    print(f"Fout: {msg}", file=sys.stderr)
    sys.exit(1)


def run(step, total, title, args):
    print(f"\n[{step}/{total}] {title}", flush=True)
    if subprocess.run(["colmap"] + args).returncode != 0:
        fail(f"COLMAP-stap '{args[0]}' is mislukt")


def registered_images(model_dir):
    """Aantal frames met een camera-positie, uit images.bin."""
    with open(model_dir / "images.bin", "rb") as fh:
        return struct.unpack("<Q", fh.read(8))[0]


def main():
    p = argparse.ArgumentParser(description="COLMAP draaien op images/.")
    p.add_argument("scene", type=Path, help="scene-map met images/")
    args = p.parse_args()

    scene = args.scene.resolve()
    images_dir = scene / "images"
    sparse_dir = scene / "sparse"
    database = scene / "database.db"

    if not images_dir.is_dir():
        fail(f"{images_dir} bestaat niet; draai eerst frames")
    n_images = sum(1 for f in images_dir.iterdir()
                   if f.is_file() and f.suffix.lower() in IMAGE_EXT)
    if n_images == 0:
        fail(f"geen frames gevonden in {images_dir}")
    if sparse_dir.exists() and any(sparse_dir.iterdir()):
        fail(f"{sparse_dir} is niet leeg; leeg of verwijder hem eerst")

    sparse_dir.mkdir(exist_ok=True)
    if database.exists():
        print(f"Oude {database.name} van een eerdere poging verwijderd")
        database.unlink()

    print(f"{n_images} frames in {images_dir}")

    run(1, 3, "Kenmerken zoeken (feature_extractor)", [
        "feature_extractor",
        "--database_path", str(database),
        "--image_path", str(images_dir),
        "--ImageReader.single_camera", "1",
        "--ImageReader.camera_model", "OPENCV",
        "--FeatureExtraction.use_gpu", "1",
    ])

    run(2, 3, "Frames vergelijken (sequential_matcher)", [
        "sequential_matcher",
        "--database_path", str(database),
        "--FeatureMatching.use_gpu", "1",
    ])

    run(3, 3, "Reconstructie (global_mapper)", [
        "global_mapper",
        "--database_path", str(database),
        "--image_path", str(images_dir),
        "--output_path", str(sparse_dir),
    ])

    models = sorted(d for d in sparse_dir.iterdir()
                    if d.is_dir() and (d / "images.bin").exists())
    if not models:
        fail("COLMAP heeft geen reconstructie gemaakt")

    print()
    for m in models:
        n = registered_images(m)
        print(f"sparse/{m.name}: {n} van {n_images} frames met camera-positie "
              f"({n / n_images:.0%})")
    if len(models) > 1:
        print("Let op: COLMAP heeft de scene in meerdere losse delen gereconstrueerd. "
              "LichtFeld gebruikt sparse/0. Vaak helpt een opname met meer overlap "
              "tussen de beelden.")
    print(f"Klaar. images/ en sparse/0/ in {scene} kunnen naar LichtFeld.")


if __name__ == "__main__":
    main()
