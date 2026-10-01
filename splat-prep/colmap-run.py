#!/usr/bin/env python3
"""Camera-posities berekenen met COLMAP voor Gaussian splatting.

Gebruik:  colmap-run <scene-map> [opties]

Verwacht in de scene-map een map images/ met frames (bijvoorbeeld van `frames`).
Stappen:
  1. Kenmerken zoeken      (feature_extractor)     GPU, anders CPU
  2. Frames vergelijken    (sequential/exhaustive) GPU, anders CPU
  3. Brandpunt schatten    (view_graph_calibrator) alleen bij global mapper
  4. Reconstructie         (global_mapper/mapper)  bundle adjustment op de GPU
                                                    via Caspar, anders CPU
  5. Rechttrekken          (image_undistorter)     CPU; naar PINHOLE, want
                                                    LichtFeld traint standaard
                                                    niet op vervormde camera's
Mislukt een GPU-stap, dan wordt die stap automatisch opnieuw op de CPU gedaan.
Na stap 5 staan de rechtgetrokken beelden in images/ en de originele frames in
images_raw/. Bij opnieuw draaien worden de originelen eerst teruggezet.
Aan het eind een overzicht: welke route per stap, en hoeveel frames een
camera-positie hebben gekregen. Het resultaat (images/ + sparse/0/, PINHOLE)
kan direct naar LichtFeld, zonder --undistort of --gut.
"""

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png"}
CAMERA_MODELS = ["SIMPLE_RADIAL", "OPENCV", "PINHOLE", "SIMPLE_PINHOLE",
                 "RADIAL", "FULL_OPENCV"]
CASPAR_MODELS = {"SIMPLE_RADIAL", "PINHOLE"}   # GPU bundle adjustment (Caspar)
NO_DISTORTION = {"PINHOLE", "SIMPLE_PINHOLE"}  # hoeven niet rechtgetrokken
PINHOLE_IDS = {0: "SIMPLE_PINHOLE", 1: "PINHOLE"}  # COLMAP model-id's
FEATURES = {
    # naam: (extractor-type, matcher-type, opties-prefix, vocab-tree-patroon)
    "sift":   ("SIFT", "SIFT_BRUTEFORCE", "SiftExtraction", "*words256K.bin"),
    "aliked": ("ALIKED_N16ROT", "ALIKED_LIGHTGLUE", "AlikedExtraction",
               "*aliked_n16rot.bin"),
}
MODEL_CACHE = Path.home() / ".cache" / "colmap"   # ingebakken modellen


def fail(msg):
    print(f"Fout: {msg}", file=sys.stderr)
    sys.exit(1)


def colmap(args):
    return subprocess.run(["colmap"] + args).returncode == 0


def step(nr, total, title, gpu_args, cpu_args, cleanup=None):
    """Stap draaien: eerst GPU (als gpu_args), bij mislukken opnieuw op CPU."""
    print(f"\n[{nr}/{total}] {title}", flush=True)
    if gpu_args is not None:
        if colmap(gpu_args):
            return "GPU"
        print(f"\n[{nr}/{total}] GPU-route mislukt, opnieuw op de CPU", flush=True)
        if cleanup:
            cleanup()
    if not colmap(cpu_args):
        fail(f"stap '{title}' is ook op de CPU mislukt")
    return "CPU"


def camera_model_id(model_dir):
    """Model-id van de eerste camera in cameras.bin."""
    with open(model_dir / "cameras.bin", "rb") as fh:
        n = struct.unpack("<Q", fh.read(8))[0]
        if n == 0:
            return None
        _camera_id, model_id = struct.unpack("<iI", fh.read(8))
        return model_id


def registered_images(model_dir):
    """Aantal frames met een camera-positie, uit images.bin."""
    with open(model_dir / "images.bin", "rb") as fh:
        return struct.unpack("<Q", fh.read(8))[0]


def main():
    p = argparse.ArgumentParser(description="COLMAP draaien op images/.")
    p.add_argument("scene", type=Path, help="scene-map met images/")
    p.add_argument("--camera-model", default="SIMPLE_RADIAL",
                   choices=CAMERA_MODELS,
                   help="lensmodel (standaard SIMPLE_RADIAL; GPU-BA alleen "
                        "met SIMPLE_RADIAL of PINHOLE)")
    p.add_argument("--camera-params",
                   help="bekende lensgegevens, komma-gescheiden in de volgorde "
                        "van het lensmodel (bijv. SIMPLE_RADIAL: f,cx,cy,k)")
    p.add_argument("--mapper", default="global", choices=["global", "incremental"],
                   help="global (snel, standaard) of incremental (klassiek)")
    p.add_argument("--no-calibrate", action="store_true",
                   help="brandpunt-schatting overslaan (alleen bij global)")
    p.add_argument("--features", default="sift", choices=list(FEATURES),
                   help="sift (standaard) of aliked (met LightGlue)")
    p.add_argument("--matcher", default="sequential",
                   choices=["sequential", "exhaustive"],
                   help="sequential (video, standaard) of exhaustive (losse foto's)")
    p.add_argument("--overlap", type=int,
                   help="aantal buren per frame bij sequential (COLMAP-standaard 10)")
    p.add_argument("--loop", action="store_true",
                   help="loop-detectie bij sequential (terugkeer naar eerder punt)")
    p.add_argument("--max-image-size", type=int,
                   help="langste zijde in pixels voor kenmerken zoeken")
    p.add_argument("--max-features", type=int,
                   help="maximaal aantal kenmerken per frame")
    p.add_argument("--masks", action="store_true",
                   help="maskers uit <scene>/masks/ gebruiken")
    p.add_argument("--no-undistort", action="store_true",
                   help="niet rechttrekken (alleen voor LichtFeld met --gut "
                        "of --undistort)")
    p.add_argument("--cpu", action="store_true",
                   help="alles op de CPU (geen GPU)")
    args = p.parse_args()

    scene = args.scene.resolve()
    images_dir = scene / "images"
    raw_dir = scene / "images_raw"
    undistort_tmp = scene / ".undistort-tmp"
    masks_dir = scene / "masks"
    sparse_dir = scene / "sparse"
    database = scene / "database.db"
    db = ["--database_path", str(database)]

    # --- controles ---------------------------------------------------------
    if sparse_dir.exists() and any(sparse_dir.iterdir()):
        fail(f"{sparse_dir} is niet leeg; leeg of verwijder hem eerst")
    if raw_dir.is_dir():
        # eerdere run: rechtgetrokken beelden weg, originele frames terug
        if images_dir.exists():
            shutil.rmtree(images_dir)
        raw_dir.rename(images_dir)
        print("Originele frames uit images_raw/ teruggezet naar images/")
    if undistort_tmp.exists():
        shutil.rmtree(undistort_tmp)
    if not images_dir.is_dir():
        fail(f"{images_dir} bestaat niet; draai eerst frames")
    n_images = sum(1 for f in images_dir.iterdir()
                   if f.is_file() and f.suffix.lower() in IMAGE_EXT)
    if n_images == 0:
        fail(f"geen frames gevonden in {images_dir}")
    if args.masks and not masks_dir.is_dir():
        fail(f"{masks_dir} bestaat niet")
    if args.loop and args.matcher != "sequential":
        fail("--loop werkt alleen met --matcher sequential")
    if args.overlap is not None and args.matcher != "sequential":
        fail("--overlap werkt alleen met --matcher sequential")

    ext_type, match_type, ext_prefix, vocab_pattern = FEATURES[args.features]
    vocab_tree = None
    if args.loop:
        found = sorted(MODEL_CACHE.glob(vocab_pattern))
        if not found:
            fail(f"vocabulary tree voor {args.features} niet gevonden in {MODEL_CACHE}")
        vocab_tree = found[0]

    sparse_dir.mkdir(exist_ok=True)
    if database.exists():
        print(f"Oude {database.name} van een eerdere poging verwijderd")
        database.unlink()

    calibrate = (args.mapper == "global" and not args.no_calibrate
                 and not args.camera_params)
    caspar = args.camera_model in CASPAR_MODELS
    undistort = not args.no_undistort and args.camera_model not in NO_DISTORTION
    total = 3 + calibrate + undistort

    print(f"{n_images} frames in {images_dir}")
    print(f"Lensmodel: {args.camera_model}"
          + (f" ({args.camera_params})" if args.camera_params else ""))
    print(f"Kenmerken: {args.features}, matcher: {args.matcher}, "
          f"mapper: {args.mapper}" + (", loop-detectie" if args.loop else "")
          + (", maskers" if args.masks else ""))
    if args.no_undistort and args.camera_model not in NO_DISTORTION:
        print("Let op: niet rechtgetrokken; LichtFeld heeft dan --undistort of --gut nodig")
    if args.cpu:
        print("Modus: alles op de CPU (--cpu)")
    elif not caspar:
        print(f"Let op: {args.camera_model} wordt niet door Caspar ondersteund; "
              "bundle adjustment draait op de CPU")

    routes = []

    # --- 1. kenmerken zoeken ----------------------------------------------
    def extract_args(gpu):
        a = ["feature_extractor"] + db + [
            "--image_path", str(images_dir),
            "--ImageReader.single_camera", "1",
            "--ImageReader.camera_model", args.camera_model,
            "--FeatureExtraction.type", ext_type,
            "--FeatureExtraction.use_gpu", "1" if gpu else "0",
        ]
        if args.camera_params:
            a += ["--ImageReader.camera_params", args.camera_params]
        if args.masks:
            a += ["--ImageReader.mask_path", str(masks_dir)]
        if args.max_image_size:
            a += ["--FeatureExtraction.max_image_size", str(args.max_image_size)]
        if args.max_features:
            a += [f"--{ext_prefix}.max_num_features", str(args.max_features)]
        return a

    def reset_database():
        if database.exists():
            database.unlink()

    routes.append(("Kenmerken zoeken", step(
        1, total, "Kenmerken zoeken (feature_extractor)",
        None if args.cpu else extract_args(True), extract_args(False),
        cleanup=reset_database)))

    # --- 2. frames vergelijken --------------------------------------------
    def match_args(gpu):
        a = [f"{args.matcher}_matcher"] + db + [
            "--FeatureMatching.type", match_type,
            "--FeatureMatching.use_gpu", "1" if gpu else "0",
        ]
        if args.overlap is not None:
            a += ["--SequentialMatching.overlap", str(args.overlap)]
        if vocab_tree:
            a += ["--SequentialMatching.loop_detection", "1",
                  "--SequentialMatching.vocab_tree_path", str(vocab_tree)]
        return a

    routes.append(("Frames vergelijken", step(
        2, total, f"Frames vergelijken ({args.matcher}_matcher)",
        None if args.cpu else match_args(True), match_args(False))))

    # --- 3. brandpunt schatten (alleen global) ----------------------------
    nr = 3
    if calibrate:
        print(f"\n[{nr}/{total}] Brandpunt schatten (view_graph_calibrator)", flush=True)
        if colmap(["view_graph_calibrator"] + db):
            routes.append(("Brandpunt schatten", "CPU"))
        else:
            print("Brandpunt schatten mislukt; verder zonder", flush=True)
            routes.append(("Brandpunt schatten", "overgeslagen (mislukt)"))
        nr += 1

    # --- 4. reconstructie -------------------------------------------------
    def clear_sparse():
        for child in sparse_dir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()

    common = db + ["--image_path", str(images_dir), "--output_path", str(sparse_dir)]
    if args.mapper == "global":
        def mapper_args(gpu):
            return ["global_mapper"] + common + [
                "--GlobalMapper.ba_backend", "CASPAR" if gpu else "CERES",
                "--GlobalMapper.ba_ceres_use_gpu", "0",
                "--GlobalMapper.gp_use_gpu", "0",
            ]
        title = "Reconstructie (global_mapper)"
    else:
        def mapper_args(gpu):
            backend = "CASPAR" if gpu else "CERES"
            return ["mapper"] + common + [
                "--Mapper.ba_use_gpu", "1" if gpu else "0",
                "--Mapper.ba_global_backend", backend,
                "--Mapper.ba_local_backend", backend,
            ]
        title = "Reconstructie (mapper, incremental)"

    use_gpu_ba = not args.cpu and caspar
    route = step(nr, total, title,
                 mapper_args(True) if use_gpu_ba else None, mapper_args(False),
                 cleanup=clear_sparse)
    routes.append(("Reconstructie", "GPU (Caspar)" if route == "GPU" else "CPU"))

    models = sorted(d for d in sparse_dir.iterdir()
                    if d.is_dir() and (d / "images.bin").exists())
    if not models:
        fail("COLMAP heeft geen reconstructie gemaakt")
    model0 = sparse_dir / "0"
    if not (model0 / "images.bin").exists():
        fail("sparse/0 ontbreekt; COLMAP heeft geen hoofdreconstructie gemaakt")
    n_registered = {m.name: registered_images(m) for m in models}

    # --- 5. rechttrekken naar PINHOLE -----------------------------------
    if undistort:
        nr += 1
        print(f"\n[{nr}/{total}] Rechttrekken naar PINHOLE (image_undistorter)", flush=True)
        ok = colmap([
            "image_undistorter",
            "--image_path", str(images_dir),
            "--input_path", str(model0),
            "--output_path", str(undistort_tmp),
            "--output_type", "COLMAP",
            "--jpeg_quality", "95",
        ])
        out_images, out_sparse = undistort_tmp / "images", undistort_tmp / "sparse"
        if not ok or not (out_sparse / "cameras.bin").exists():
            shutil.rmtree(undistort_tmp, ignore_errors=True)
            fail("rechttrekken mislukt; sparse/0 is nog vervormd. Opnieuw proberen, "
                 "of in LichtFeld --undistort gebruiken")
        model_id = camera_model_id(out_sparse)
        if model_id not in PINHOLE_IDS:
            shutil.rmtree(undistort_tmp, ignore_errors=True)
            fail(f"rechtgetrokken camera is geen PINHOLE (model-id {model_id})")
        # originelen opzij, rechtgetrokken beelden en model op hun plek
        images_dir.rename(raw_dir)
        out_images.rename(images_dir)
        for f in model0.iterdir():
            f.unlink()
        for f in out_sparse.iterdir():
            f.rename(model0 / f.name)
        shutil.rmtree(undistort_tmp)
        routes.append(("Rechttrekken", f"CPU, {PINHOLE_IDS.get(model_id)}"))

    # --- overzicht --------------------------------------------------------
    print("\n=== Overzicht ===")
    for name, r in routes:
        print(f"{name:<20} {r}")
    print()
    for m in models:
        n = n_registered[m.name]
        print(f"sparse/{m.name}: {n} van {n_images} frames met camera-positie "
              f"({n / n_images:.0%})")
    if len(models) > 1:
        print("Let op: COLMAP heeft de scene in meerdere losse delen gereconstrueerd. "
              "LichtFeld gebruikt sparse/0. Probeer --mapper incremental, --loop, "
              "of een opname met meer overlap.")
    if undistort and len(models) > 1:
        print("Alleen sparse/0 is rechtgetrokken; de andere delen horen bij images_raw/.")
    cam = PINHOLE_IDS.get(camera_model_id(model0), "vervormd model")
    print(f"Lensmodel sparse/0: {cam}")
    if undistort:
        print("Originele frames staan in images_raw/.")
    print(f"Klaar. images/ en sparse/0/ in {scene} kunnen naar LichtFeld.")


if __name__ == "__main__":
    main()
