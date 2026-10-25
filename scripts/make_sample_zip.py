"""Download random photos and pack them into ZIPs for testing bulk mode.

usage: python scripts/make_sample_zip.py --count 20
creates samples/images/*.jpg, samples/bulk_<count>.zip and samples/bulk_with_bad_files.zip
"""
import argparse
import urllib.request
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, default=20)
parser.add_argument("--out", default="samples")
args = parser.parse_args()

img_dir = Path(args.out) / "images"
img_dir.mkdir(parents=True, exist_ok=True)

for i in range(1, args.count + 1):
    path = img_dir / f"photo_{i:03d}.jpg"
    if path.exists():
        continue
    url = f"https://picsum.photos/seed/caption{i}/800/600"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        path.write_bytes(resp.read())
    print("downloaded", path.name)

images = sorted(img_dir.glob("*.jpg"))[: args.count]

zip_path = Path(args.out) / f"bulk_{args.count}.zip"
with zipfile.ZipFile(zip_path, "w") as zf:
    for p in images:
        zf.write(p, p.name)
print("created", zip_path)

# second zip with junk files to show error handling and skipped-file metrics
bad_path = Path(args.out) / "bulk_with_bad_files.zip"
with zipfile.ZipFile(bad_path, "w") as zf:
    for p in images[:5]:
        zf.write(p, p.name)
    zf.writestr("notes.txt", "not an image")
    zf.writestr("corrupt.jpg", b"this is not really a jpeg")
    zf.writestr(".hidden.png", b"hidden")
    zf.writestr("__MACOSX/._photo_001.jpg", b"mac junk")
print("created", bad_path)
