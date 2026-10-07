"""
Stack Exchange XML parser — extracts Posts, PostLinks, and Tags from 7z archives.

Uses SAX-style iterparse (low memory) and streams rows as dicts.
Each site's archive is processed independently and yields a merged stream.
"""
from __future__ import annotations

import logging
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Generator, Union

import py7zr

from ..base import AbstractParser

logger = logging.getLogger(__name__)


def _parse_posts_xml(source: Union[Path, str]) -> Generator[dict, None, None]:
    """Parse Posts.xml file and yield row dicts for questions and answers."""
    for _event, elem in ET.iterparse(str(source), events=("end",)):
        if elem.tag != "row":
            continue
        attrib = elem.attrib
        post_type = attrib.get("PostTypeId")
        if post_type not in ("1", "2"):  # 1=Question, 2=Answer
            elem.clear()
            continue
        yield {
            "Id": attrib.get("Id"),
            "PostTypeId": post_type,
            "AcceptedAnswerId": attrib.get("AcceptedAnswerId"),
            "ParentId": attrib.get("ParentId"),
            "CreationDate": attrib.get("CreationDate"),
            "Score": attrib.get("Score", "0"),
            "ViewCount": attrib.get("ViewCount"),
            "Body": attrib.get("Body", ""),
            "OwnerUserId": attrib.get("OwnerUserId"),
            "Title": attrib.get("Title", ""),
            "Tags": attrib.get("Tags", ""),
            "AnswerCount": attrib.get("AnswerCount", "0"),
            "LastEditDate": attrib.get("LastEditDate"),
        }
        elem.clear()


def _parse_post_links_xml(source: Union[Path, str]) -> Generator[dict, None, None]:
    """Parse PostLinks.xml (duplicate/related links between questions)."""
    for _event, elem in ET.iterparse(str(source), events=("end",)):
        if elem.tag != "row":
            continue
        yield {
            "PostId": elem.attrib.get("PostId"),
            "RelatedPostId": elem.attrib.get("RelatedPostId"),
            "LinkTypeId": elem.attrib.get("LinkTypeId"),  # 1=linked, 3=duplicate
        }
        elem.clear()


class StackExchangeParser(AbstractParser):
    """
    Parses all 7z archives in raw_dir and yields merged post dicts.

    Each dict has an extra `_site` key set to the archive's site name.
    PostLinks are yielded as dicts with `_record_type: "post_link"`.
    """

    def parse(self) -> Generator[dict, None, None]:
        archives = sorted(self.raw_dir.glob("*.7z"))
        if not archives:
            logger.warning("[SE] No .7z archives found in %s", self.raw_dir)
            return

        for archive_path in archives:
            site_name = archive_path.stem  # e.g. "stackoverflow.com" → "stackoverflow"
            if site_name.endswith(".com"):
                site_name = site_name[: -len(".com")]
            logger.info("[SE] Parsing archive: %s", archive_path.name)
            yield from self._parse_archive(archive_path, site_name)

    def _parse_archive(self, archive_path: Path, site: str) -> Generator[dict, None, None]:
        try:
            with py7zr.SevenZipFile(archive_path, mode="r") as z:
                names = z.getnames()
                target_files = [n for n in names if n in ("Posts.xml", "PostLinks.xml")]
                if not target_files:
                    logger.warning("[SE] No Posts.xml in %s", archive_path.name)
                    return

            # py7zr 1.x removed read(); extract to a temp dir and parse from disk.
            # This also avoids loading potentially multi-GB XML into memory at once.
            with tempfile.TemporaryDirectory() as tmp_dir:
                with py7zr.SevenZipFile(archive_path, mode="r") as z:
                    z.extract(path=tmp_dir, targets=target_files)

                posts_path = Path(tmp_dir) / "Posts.xml"
                if posts_path.exists():
                    logger.info("[SE] Streaming Posts.xml for %s…", site)
                    for row in _parse_posts_xml(posts_path):
                        row["_site"] = site
                        yield row

                links_path = Path(tmp_dir) / "PostLinks.xml"
                if links_path.exists():
                    for row in _parse_post_links_xml(links_path):
                        row["_site"] = site
                        row["_record_type"] = "post_link"
                        yield row

        except Exception as exc:
            logger.error("[SE] Failed to parse %s: %s", archive_path.name, exc)
