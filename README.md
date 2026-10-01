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

De splats-map wordt alleen-lezen gemount en geserveerd onder `/splats/`, zodat een
splat direct te openen is:

```
http://<server>:<poort>/?load=/splats/<scene>/lfs-output/<bestand>.ply
```

Bewerkingen sla je op via de browser (exporteren/downloaden); de container schrijft
niets in de splats-map.

Zie `supersplat/docker-compose.example.yml`.

## splat-prep

Gebouwd op COLMAP (met CUDA). De workflow bouwt eerst COLMAP's eigen officiële
Dockerfile voor de nieuwste release en zet daar ffmpeg, Python en het `frames`-script
bovenop. Het image-label is de COLMAP-versie.

### Mapindeling per scene

```
<scene>/
  input/        video('s)
  images/       uitgehaalde frames
  sparse/       COLMAP-resultaat (later)
  lfs-output/   trainingsresultaat
```

`frames` maakt `images/`, `sparse/` en `lfs-output/` aan als ze nog niet bestaan.

### frames

```
docker exec splat-prep frames /workspace/<scene>
docker exec splat-prep frames /workspace/<scene> --fps 2
```

1. Haalt frames uit op 2× de doel-fps (standaard 6 fps).
2. Meet van elk frame de scherpte (variantie van de Laplaciaan).
3. Houdt per groepje van 2 opeenvolgende frames het scherpste (standaard 3 fps).
4. Zet de behouden frames als JPG van hoge kwaliteit in `images/`
   (`frame_00001.jpg`, ...).
5. Schrijft `frames-report.csv` met per frame de scherpte en status
   (`behouden`, `weg`, `onscherp`), en toont behouden frames die duidelijk onscherper
   zijn dan de rest (minder dan 50% van de mediaan). Die blijven in `images/` staan;
   verwijder ze zelf als je wilt.

Meerdere video's in `input/` worden op naam gesorteerd en doorlopend genummerd.
Is `images/` niet leeg, dan stopt het script; leeg de map eerst.

Zie `splat-prep/docker-compose.example.yml`. De container start met
`sleep infinity` en doet niets tot je er een commando in uitvoert.

### Na een wijziging aan het script

De wekelijkse check bouwt alleen bij een nieuwe COLMAP-release. Na een wijziging aan
`frames.py` of de Dockerfile: start de workflow handmatig met **force** aangevinkt.

## Licenties

SuperSplat (MIT) en COLMAP (BSD) vallen onder hun eigen licenties.
