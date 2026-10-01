# splat-tools

Hulpcontainers voor een lokale Gaussian splatting-workflow:
video → frames → (COLMAP) → training → bekijken/opschonen.

Elke map bevat één image met een eigen GitHub Actions-workflow. De workflows
bouwen altijd uit de officiële broncode van de nieuwste stabiele release, checken
elke maandag of er een nieuwe release is, en hebben een **force**-optie om dezelfde
versie opnieuw te bouwen. Images komen in GHCR met de releaseversie en `latest` als tag.

| Map | Image | Bron | GPU |
|---|---|---|---|
| `supersplat/` | `ghcr.io/<owner>/supersplat` | [playcanvas/supersplat](https://github.com/playcanvas/supersplat) (MIT) | nee |
| `splat-prep/` | `ghcr.io/<owner>/splat-prep` | [colmap/colmap](https://github.com/colmap/colmap) (BSD) + ffmpeg + Python | ja |

## supersplat

SuperSplat (de splat-editor van PlayCanvas) als statische site in een kleine
nginx-container. Het renderen gebeurt in de browser, de container heeft geen GPU nodig.

SuperSplat heeft WebGPU nodig, en browsers geven dat alleen vrij op HTTPS (of
`localhost`). De container serveert daarom via HTTPS met een self-signed certificaat.
Dat wordt bij de eerste start aangemaakt in `/certs`; mount die map als volume, dan
blijft het bewaard en klik je de certificaatwaarschuwing maar één keer per browser weg.

De splats-map wordt alleen-lezen gemount en geserveerd onder `/splats/`, zodat een
splat direct te openen is:

```
https://<server>:<poort>/?load=/splats/<scene>/lfs-output/<bestand>.ply
```

Bewerkingen sla je op via de browser (exporteren/downloaden); de container schrijft
niets in de splats-map.

Zie `supersplat/docker-compose.example.yml`.

## splat-prep

Gebouwd op COLMAP (met CUDA). De workflow bouwt eerst COLMAP's eigen officiële
Dockerfile voor de nieuwste release, met **Caspar** (GPU bundle adjustment) aangezet en
GPU-architecturen 75/86/89. Daarbovenop komen ffmpeg (met NVDEC), Python, cuDNN (voor
ALIKED/LightGlue op de GPU), de scripts `frames` en `colmap-run`, en de modellen die
COLMAP anders bij het eerste gebruik downloadt (ALIKED, LightGlue, vocabulary trees).
De container heeft geen netwerk, daarom zijn die ingebakken; `fetch_models.py` haalt ze
tijdens de build op uit de COLMAP-broncode van dezelfde release, met controlesom.
Het image-label is de COLMAP-versie.

Elke GPU-stap valt automatisch terug op de CPU als de GPU-route mislukt; het overzicht
aan het eind laat per stap zien welke route gebruikt is.

### Mapindeling per scene

```
<scene>/
  input/        video('s)
  images/       frames; na colmap-run de rechtgetrokken versie
  images_raw/   originele frames            (colmap-run, na rechttrekken)
  masks/        optionele maskers           (zelf, voor colmap-run --masks)
  database.db   COLMAP-database             (colmap-run)
  sparse/0/     camera-posities             (colmap-run)
  lfs-output/   trainingsresultaat
```

### frames

```
docker exec splat-prep frames /workspace/<scene> [--fps N] [--hdr] [--cpu]
```

| Optie | Betekenis | Standaard |
|---|---|---|
| `--fps N` | behouden frames per seconde (uithalen gebeurt op 2×) | 3 |
| `--hdr` | HDR-video (HLG/PQ, bijv. iPhone) omzetten naar SDR | uit |
| `--cpu` | niet op de GPU decoderen | GPU (NVDEC) |

1. Haalt frames uit op 2× de doel-fps, gedecodeerd op de GPU (NVDEC), anders CPU.
2. Meet van elk frame de scherpte (variantie van de Laplaciaan).
3. Houdt per groepje van 2 opeenvolgende frames het scherpste.
4. Zet de behouden frames als JPG van hoge kwaliteit in `images/`.
5. Schrijft `frames-report.csv` en toont behouden frames die duidelijk onscherper zijn
   dan de rest (minder dan 50% van de mediaan); die blijven staan.

Video's moeten direct in `input/` staan (geen submappen). Meerdere video's worden op
naam gesorteerd en doorlopend genummerd. Is `images/` niet leeg, dan stopt het script.

### colmap-run

```
docker exec splat-prep colmap-run /workspace/<scene> [opties]
```

| Optie | Betekenis | Standaard |
|---|---|---|
| `--camera-model M` | `SIMPLE_RADIAL`, `OPENCV`, `PINHOLE`, `SIMPLE_PINHOLE`, `RADIAL`, `FULL_OPENCV` | `SIMPLE_RADIAL` |
| `--camera-params P` | bekende lensgegevens, komma-gescheiden in de volgorde van het model | geschat |
| `--mapper global\|incremental` | snelle global mapper of klassieke incremental mapper | `global` |
| `--no-calibrate` | brandpunt-schatting (`view_graph_calibrator`) overslaan | aan bij global |
| `--features sift\|aliked` | SIFT of ALIKED met LightGlue | `sift` |
| `--matcher sequential\|exhaustive` | buren vergelijken (video) of alles met alles (foto's) | `sequential` |
| `--overlap N` | aantal buren per frame (alleen sequential) | 10 |
| `--loop` | loop-detectie (alleen sequential) | uit |
| `--max-image-size N` | langste zijde voor kenmerken zoeken | COLMAP-standaard |
| `--max-features N` | maximaal aantal kenmerken per frame | COLMAP-standaard |
| `--masks` | maskers uit `<scene>/masks/` gebruiken | uit |
| `--no-undistort` | niet rechttrekken (alleen voor LichtFeld met `--gut` of `--undistort`) | rechttrekken aan |
| `--cpu` | alles op de CPU | GPU |

Stappen en route:

| Stap | GPU | Terugval |
|---|---|---|
| Kenmerken zoeken (`feature_extractor`) | SIFT of ALIKED op de GPU | CPU |
| Vergelijken (`sequential_matcher` / `exhaustive_matcher`) | GPU | CPU |
| Brandpunt schatten (`view_graph_calibrator`, alleen global) | — | CPU; bij mislukken overgeslagen |
| Reconstructie (`global_mapper` / `mapper`) | bundle adjustment via Caspar | Ceres op de CPU |
| Rechttrekken (`image_undistorter`) | — (CPU) | bij mislukken stopt het script |

Caspar ondersteunt alleen `SIMPLE_RADIAL` en `PINHOLE`; met een ander lensmodel draait de
bundle adjustment op de CPU. Global positioning (onderdeel van de global mapper) draait
altijd op de CPU. `--camera-params` slaat de brandpunt-schatting automatisch over.

Maskers: per frame een PNG in `masks/` met de naam van het frame plus `.png`
(bijv. `frame_00001.jpg.png`); zwart = negeren.

Rechttrekken: LichtFeld traint standaard alleen op camera's zonder lensvervorming
(`PINHOLE` / `SIMPLE_PINHOLE`); anders vraagt het om `--undistort` of `--gut`. Daarom
trekt `colmap-run` na de reconstructie de beelden recht naar `PINHOLE`: de
rechtgetrokken beelden komen in `images/`, de originele frames in `images_raw/`, en
het script controleert in `cameras.bin` dat het model `PINHOLE` is. Aan de randen gaan
daarbij wat pixels verloren. Met `--camera-model PINHOLE` of `SIMPLE_PINHOLE` is
rechttrekken niet nodig en wordt het overgeslagen.

Gebruik per scene één camera. Is `sparse/` niet leeg, dan stopt het script. Is het
leeg en staat `images_raw/` er nog, dan zet het script eerst de originele frames terug
naar `images/`; een oude `database.db` wordt opnieuw aangemaakt. `frames` weigert zolang
`images_raw/` bestaat.

### Voortgang in de containerlog

De container start met `sleep infinity` en doet niets tot je er een commando in
uitvoert. Op de achtergrond draaien en via de containerlog volgen:

```
docker exec -d splat-prep sh -c 'colmap-run /workspace/<scene> > /proc/1/fd/1 2>&1'
```

Zie `splat-prep/docker-compose.example.yml`. Voor GPU-decodering in `frames` moet
`NVIDIA_DRIVER_CAPABILITIES` ook `video` bevatten.

### Na een wijziging aan een script

De wekelijkse check bouwt alleen bij een nieuwe COLMAP-release. Na een wijziging aan
een script of de Dockerfile: start de workflow handmatig met **force** aangevinkt.

## Licenties

SuperSplat (MIT) en COLMAP (BSD) vallen onder hun eigen licenties.
