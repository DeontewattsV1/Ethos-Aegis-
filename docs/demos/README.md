# Ethos Aegis recorded walkthroughs

Each MP4 is a branded walkthrough rendered from the actual stdout of a local
Python command. Synthetic inputs are labeled on every scene. These are neither
live upstream tool scans nor recordings of the illustrative 4D board.

| Recording | Demonstrates | Reproduce |
|---|---|---|
| [Toolkit](toolkit.mp4) | Five evidence imports, provenance, raw-secret omission, scope denial and execution default-off | `python -m ethos_aegis.security_toolkit demo --scenario toolkit` |
| [Immune](immune.mp4) | Normal input, injection verdict, Unicode purification and a vitality report | `python -m ethos_aegis.security_toolkit demo --scenario immune` |
| [VeriFlow](veriflow.mp4) | Boolean simplification, fitted formula evidence and aggregate reasoning | `python -m ethos_aegis.security_toolkit demo --scenario veriflow` |

The `.txt` files contain full unedited stdout. The manifest records input/recording
hashes and commands. Videos present the captured lines progressively for reading;
the reveal timing is editorial, not a latency measurement.

GitHub READMEs render GIF previews. MP4 links open the full recordings; they do not
embed an executable UI. To regenerate, install Pillow and ffmpeg separately and
run `python scripts/render-security-demos.py` from the repository root.

Brand palette and geometry follow [BRAND.md](../../BRAND.md). Source code and
transcripts remain authoritative for feature behavior and support limits.
