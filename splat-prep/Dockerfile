# splat-prep - frames uit video halen en COLMAP draaien voor Gaussian splatting.
# Basis: COLMAP, gebouwd uit de officiele broncode met COLMAP's eigen Dockerfile
# (https://github.com/colmap/colmap/tree/main/docker), met Caspar (GPU bundle
# adjustment) aangezet. De workflow bouwt die eerst lokaal voor de nieuwste
# release en geeft hem hier mee via BASE_IMAGE.

ARG BASE_IMAGE

FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/root

# ffmpeg     frames uithalen (met NVDEC voor GPU-decodering)
# python3    scripts + scherptemeting
# cuDNN      nodig voor ALIKED/LightGlue op de GPU (ONNX Runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        python3 python3-numpy python3-pil \
        libcudnn9-cuda-12 \
    && rm -rf /var/lib/apt/lists/*

# Ingebakken modellen (ALIKED, LightGlue, vocabulary trees), opgehaald door de
# workflow met fetch_models.py. COLMAP zoekt ze in ~/.cache/colmap; de container
# heeft geen netwerk om ze zelf te downloaden.
COPY models/ /root/.cache/colmap/

COPY frames.py /usr/local/bin/frames
COPY colmap-run.py /usr/local/bin/colmap-run
RUN chmod +x /usr/local/bin/frames /usr/local/bin/colmap-run

WORKDIR /workspace
CMD ["sleep", "infinity"]
