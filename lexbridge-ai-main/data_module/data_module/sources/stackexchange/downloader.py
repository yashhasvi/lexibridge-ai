"""
Stack Exchange downloader — streams 7z-compressed XML dumps from Internet Archive.

Uses the April 2024 snapshot which predates Stack Overflow's LLM-training gate.
See: https://archive.org/details/stackexchange
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ..base import AbstractDownloader

logger = logging.getLogger(__name__)

ARCHIVE_BASE = "https://archive.org/download/stackexchange"


class StackExchangeDownloader(AbstractDownloader):
    """
    Downloads per-site 7z archives from the Internet Archive mirror.

    The archive contains one file per site, e.g.:
        stackoverflow.com.7z  (~22 GB)
        unix.stackexchange.com.7z
        ...
    """

    def download(self) -> list[Path]:
        sites: list[str] = self.config.get("sites", [])
        downloaded: list[Path] = []

        for site in sites:
            # Config entries are full hostnames, e.g. "ai.stackexchange.com".
            # archive.org filenames are exactly "{hostname}.7z".
            filename = f"{site}.7z"
            dest = self.raw_dir / filename

            if dest.exists():
                logger.info("[SE] %s already downloaded, skipping.", filename)
                downloaded.append(dest)
                continue

            url = f"{ARCHIVE_BASE}/{filename}"
            logger.info("[SE] Downloading %s …", url)
            self._stream_download(url, dest)
            downloaded.append(dest)

        return downloaded

    def _stream_download(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=None) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1 << 20):  # 1 MB chunks
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded / total * 100
                            if downloaded % (100 << 20) < (1 << 20):  # log every ~100 MB
                                logger.info("  %.1f%%", pct)
            tmp.rename(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
