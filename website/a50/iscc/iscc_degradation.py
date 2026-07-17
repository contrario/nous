#!/usr/bin/env python3
"""
ISCC image content-code degradation measurement.

WHAT THIS MEASURES
  For each source image it computes the ISCC image Content-Code (ISO 24138,
  a similarity-preserving soft hash), applies a fixed set of local
  transformations, recomputes the Content-Code, and reports the binary
  Hamming distance between original and transformed code. Lower distance =
  higher measured similarity. Nothing is uploaded; every step runs locally.

WHAT THIS DOES NOT MEASURE
  - It measures the Content-Code only. The ISCC Data-Code and Instance-Code
    are exact (cryptographic) and change on any re-encode by design; they are
    out of scope here and are not what a durability question is about.
  - It measures benign local transformations, not adversarial attack. A soft
    hash is tunable and can be gamed; a colliding or distance-inflated code
    can be crafted deliberately. These numbers say nothing about that case.
  - It says nothing about whether a file is AI-generated. A Content-Code is a
    content fingerprint, not a provenance claim and not a detector.
  - The grayscale row is expected to read 0: the Content-Code algorithm
    converts to grayscale during preprocessing, so a grayscale input is not
    an independent transformation. It is reported for completeness, not as
    evidence of robustness.

REPRODUCIBILITY
  Distances can vary slightly with the JPEG/WebP encoder (libjpeg / libwebp)
  and Pillow version, because the transformed pixels differ. The exact
  versions used are printed in the environment block. Re-run against those.
"""
import io, sys, json, hashlib, glob, platform
import iscc_core as ic
from PIL import Image, features

TOOL_VERSION = "0.1.0"
BITS = 256

def content_code(img):
    g = img.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    return ic.gen_image_code_v0(list(g.tobytes()), bits=BITS)["iscc"]

def jpeg(img, q):
    b = io.BytesIO(); img.convert("RGB").save(b, "JPEG", quality=q); b.seek(0)
    return Image.open(b)

def webp(img, q):
    b = io.BytesIO(); img.convert("RGB").save(b, "WEBP", quality=q); b.seek(0)
    return Image.open(b)

def resize_rt(img, pct):
    w, h = img.size
    return img.resize((max(1, int(w*pct)), max(1, int(h*pct)))).resize((w, h))

def crop_rt(img, pct):
    w, h = img.size; dx, dy = int(w*pct), int(h*pct)
    return img.crop((dx, dy, w-dx, h-dy)).resize((w, h))

def png_rt(img):
    b = io.BytesIO(); img.save(b, "PNG"); b.seek(0)
    return Image.open(b)

TRANSFORMS = {
    "jpeg_q95":  lambda i: jpeg(i, 95),
    "jpeg_q80":  lambda i: jpeg(i, 80),
    "jpeg_q50":  lambda i: jpeg(i, 50),
    "resize_75": lambda i: resize_rt(i, 0.75),
    "resize_50": lambda i: resize_rt(i, 0.50),
    "crop_5":    lambda i: crop_rt(i, 0.05),
    "crop_10":   lambda i: crop_rt(i, 0.10),
    "png_rt":    lambda i: png_rt(i),
    "webp_q95":  lambda i: webp(i, 95),
    "grayscale": lambda i: i.convert("L").convert("RGB"),
}

def env():
    return {
        "tool_version": TOOL_VERSION,
        "bits": BITS,
        "python": platform.python_version(),
        "iscc_core": ic.__version__,
        "pillow": Image.__version__,
        "libjpeg": features.version("jpg"),
        "libwebp": features.version("webp"),
    }

def main(corpus_dir):
    paths = sorted(glob.glob(f"{corpus_dir}/*.png") + glob.glob(f"{corpus_dir}/*.jpg")
                   + glob.glob(f"{corpus_dir}/*.jpeg"))
    if not paths:
        print(f"no images in {corpus_dir}", file=sys.stderr); sys.exit(2)
    out = {"environment": env(), "transforms": list(TRANSFORMS), "assets": {}}
    for p in paths:
        raw = open(p, "rb").read()
        base = Image.open(io.BytesIO(raw))
        orig = content_code(base)
        name = p.split("/")[-1]
        row = {"sha256": hashlib.sha256(raw).hexdigest(),
               "orig_code": orig, "distances": {}}
        print(f"\n{name}")
        print(f"  sha256 {row['sha256']}")
        print(f"  code   {orig}")
        for tname, fn in TRANSFORMS.items():
            try:
                d = ic.iscc_distance(orig, content_code(fn(base)))
            except Exception as e:
                d = f"ERR:{type(e).__name__}"
            row["distances"][tname] = d
            print(f"  {tname:10} {d}")
        out["assets"][name] = row
    js = json.dumps(out, indent=2, sort_keys=True)
    open("iscc_degradation_result.json", "w").write(js + "\n")
    print("\nenvironment:", json.dumps(out["environment"]))
    print("wrote iscc_degradation_result.json")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/a50_samples")
