"""Download the open datasets used by NemoTwins.

Raw data is never committed. Run ``python -m nemotwins.data.download``.

* CGMacros v1.0.0 (PhysioNet, CC BY-NC-SA 4.0) - fetched from the PhysioNet
  open-data S3 mirror with parallel byte-range requests (much faster than
  physionet.org for the 657 MB zip).
* ShanghaiT1DM/T2DM (figshare 20444397, CC BY 4.0).
"""

from __future__ import annotations

import concurrent.futures as cf
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from nemotwins.config import RAW_DIR

CGMACROS_URL = (
    "https://physionet-open.s3.amazonaws.com/cgmacros/1.0.0/CGMacros_dateshifted365.zip"
)
SHANGHAI_URL = "https://ndownloader.figshare.com/files/38259264"


def _content_length(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])


def _fetch_range(url: str, start: int, end: int, dest: Path) -> Path:
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f, length=1 << 20)
            if dest.stat().st_size == end - start + 1:
                return dest
        except Exception as exc:  # noqa: BLE001 - retry any network error
            print(f"  part {dest.name} attempt {attempt + 1} failed: {exc}", file=sys.stderr)
    raise RuntimeError(f"could not fetch {dest.name}")


def parallel_download(url: str, dest: Path, parts: int = 12) -> Path:
    if dest.exists() and dest.stat().st_size == _content_length(url):
        print(f"{dest.name} already present")
        return dest
    size = _content_length(url)
    chunk = -(-size // parts)
    tmp = [dest.with_suffix(f".part{i}") for i in range(parts)]
    with cf.ThreadPoolExecutor(parts) as ex:
        futs = [
            ex.submit(_fetch_range, url, i * chunk, min(size, (i + 1) * chunk) - 1, tmp[i])
            for i in range(parts)
        ]
        for fut in cf.as_completed(futs):
            fut.result()
    with open(dest, "wb") as out:
        for p in tmp:
            with open(p, "rb") as src:
                shutil.copyfileobj(src, out, length=1 << 22)
            p.unlink()
    print(f"downloaded {dest} ({size / 1e6:.0f} MB)")
    return dest


def download_cgmacros() -> Path:
    target = RAW_DIR / "cgmacros"
    if (target / "bio.csv").exists() or any(target.glob("**/bio.csv")):
        print("CGMacros already extracted")
        return target
    target.mkdir(parents=True, exist_ok=True)
    z = parallel_download(CGMACROS_URL, RAW_DIR / "cgmacros.zip")
    with zipfile.ZipFile(z) as zf:
        zf.extractall(target)
    return target


def download_shanghai() -> Path:
    target = RAW_DIR / "shanghai"
    if any(target.glob("**/Shanghai_T2DM_Summary.xlsx")):
        print("ShanghaiT2DM already extracted")
        return target
    target.mkdir(parents=True, exist_ok=True)
    z = target / "data.zip"
    urllib.request.urlretrieve(SHANGHAI_URL, z)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(target)
    # The archive's top folder name is GBK mojibake; normalise it.
    for d in target.iterdir():
        if d.is_dir() and d.name != "shanghai_data" and (d / "Shanghai_T2DM").exists():
            d.rename(target / "shanghai_data")
    return target


if __name__ == "__main__":
    download_shanghai()
    download_cgmacros()
