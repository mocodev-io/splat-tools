# splat-prep - frames uit video halen (en later COLMAP) voor Gaussian splatting.
# Basis: COLMAP, gebouwd uit de officiele broncode met COLMAP's eigen Dockerfile
# (https://github.com/colmap/colmap/tree/main/docker). De workflow bouwt die eerst
# lokaal voor de nieuwste release en geeft hem hier mee via BASE_IMAGE.

ARG BASE_IMAGE

FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive

# ffmpeg voor het uithalen van frames, Python + numpy/Pillow voor de scherptemeting
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        python3 python3-numpy python3-pil \
    && rm -rf /var/lib/apt/lists/*

COPY frames.py /usr/local/bin/frames
RUN chmod +x /usr/local/bin/frames

WORKDIR /workspace
CMD ["sleep", "infinity"]
