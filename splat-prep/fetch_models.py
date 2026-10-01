#!/usr/bin/env python3
"""Modellen ophalen die COLMAP anders bij het eerste gebruik zou downloaden.

Gebruik:  fetch_models.py <colmap-broncode> <uitvoermap>

Leest de download-adressen en SHA256-controlesommen uit de COLMAP-broncode van
de release die gebouwd wordt, zodat ze altijd bij die versie passen. Elk bestand
wordt gecontroleerd en opgeslagen als <sha256>-<naam>, de vorm die COLMAP in
~/.cache/colmap verwacht. De container heeft geen netwerk, dus zonder deze
bestanden werken ALIKED/LightGlue en loop-detectie niet.
"""

import hashlib
import re
import sys
import urllib.request
from pathlib import Path

# (bronbestand in COLMAP, naam van de constante)
MODELS = [
    ("src/colmap/retrieval/resources.h", "kDefaultSiftVocabTreeUri"),
    ("src/colmap/retrieval/resources.h", "kDefaultAlikedN16RotVocabTreeUri"),
    ("src/colmap/feature/resources.h", "kDefaultAlikedN16RotFeatureExtractorUri"),
    ("src/colmap/feature/resources.h", "kDefaultAlikedLightGlueFeatureMatcherUri"),
]


def read_uri(source, const):
    """Samengevoegde string-literal van een constante uit een header lezen."""
    text = source.read_text()
    m = re.search(rf"{const}\s*=\s*((?:\s*\"[^\"]*\")+)\s*;", text)
    if not m:
        sys.exit(f"Fout: {const} niet gevonden in {source}")
    uri = "".join(re.findall(r"\"([^\"]*)\"", m.group(1)))
    parts = uri.split(";")
    if len(parts) != 3 or len(parts[2]) != 64:
        sys.exit(f"Fout: onverwachte vorm van {const}: {uri}")
    return parts  # url, naam, sha256


def main():
    if len(sys.argv) != 3:
        sys.exit("Gebruik: fetch_models.py <colmap-broncode> <uitvoermap>")
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)

    for header, const in MODELS:
        url, name, sha = read_uri(src / header, const)
        target = out / f"{sha}-{name}"
        print(f"{name}: ophalen", flush=True)
        with urllib.request.urlopen(url) as r:
            data = r.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != sha:
            sys.exit(f"Fout: controlesom van {name} klopt niet ({digest})")
        target.write_bytes(data)
        print(f"  {len(data) / 1e6:.1f} MB, controlesom klopt", flush=True)


if __name__ == "__main__":
    main()
