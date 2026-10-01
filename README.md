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
Dockerfile voor de nieuwste release en zet daar ffmpeg, Python en de scripts `frames`
en `colmap-run` bovenop. Het image-label is de COLMAP-versie.

### Mapindeling per scene

```
<scene>/
  input/        video('s)
  images/       uitgehaalde frames          (frames)
  database.db   COLMAP-database             (colmap-run)
  sparse/0/     camera-posities             (colmap-run)
  lfs-output/   trainingsresultaat
```

`frames` maakt `images/`, `sparse/` en `lfs-output/` aan als ze nog niet bestaan.

### frames

```
docker exec splat-prep frames /workspace/<scene>
docker exec splat-prep frames /workspace/<scene> --fps 2
docker exec splat-prep frames /workspace/<scene> --hdr
```

1. Haalt frames uit op 2× de doel-fps (standaard 6 fps). Met `--hdr` wordt HDR-video
   (HLG/PQ, bijvoorbeeld van een iPhone) omgezet naar SDR; zonder die optie worden
   HDR-frames flets en grauw.
2. Meet van elk frame de scherpte (variantie van de Laplaciaan).
3. Houdt per groepje van 2 opeenvolgende frames het scherpste (standaard 3 fps).
4. Zet de behouden frames als JPG van hoge kwaliteit in `images/`
   (`frame_00001.jpg`, ...).
5. Schrijft `frames-report.csv` met per frame de scherpte en status
   (`behouden`, `weg`, `onscherp`), en toont behouden frames die duidelijk onscherper
   zijn dan de rest (minder dan 50% van de mediaan). Die blijven in `images/` staan;
   verwijder ze zelf als je wilt.

Video's moeten direct in `input/` staan (geen submappen). Meerdere video's worden op
naam gesorteerd en doorlopend genummerd. Is `images/` niet leeg, dan stopt het
script; leeg de map eerst.

### colmap-run

```
docker exec splat-prep colmap-run /workspace/<scene>
```

1. `feature_extractor` op `images/` (GPU): één gedeelde camera met model `OPENCV`,
   zodat de lensvervorming wordt meegeschat.
2. `sequential_matcher` (GPU): vergelijkt frames met hun buren, past bij video.
3. `global_mapper`: reconstructie, resultaat in `sparse/0/`.
4. Overzicht: hoeveel frames een camera-positie hebben gekregen.

Undistorten is niet nodig: LichtFeld leest het `OPENCV`-model direct, dus `images/` en
`sparse/0/` kunnen meteen naar LichtFeld. Gebruik per scene één camera. Is `sparse/`
niet leeg, dan stopt het script; een oude `database.db` wordt opnieuw aangemaakt.

### Voortgang in de containerlog

De container start met `sleep infinity` en doet niets tot je er een commando in
uitvoert. Wil je een commando op de achtergrond draaien en via de containerlog volgen:

```
docker exec -d splat-prep sh -c 'frames /workspace/<scene> > /proc/1/fd/1 2>&1'
```

Zie `splat-prep/docker-compose.example.yml`.

### Na een wijziging aan een script

De wekelijkse check bouwt alleen bij een nieuwe COLMAP-release. Na een wijziging aan
`frames.py`, `colmap-run.py` of de Dockerfile: start de workflow handmatig met
**force** aangevinkt.

## Licenties

SuperSplat (MIT) en COLMAP (BSD) vallen onder hun eigen licenties.
