"""
Wikidata source — entity nodes and property triples for the knowledge graph.

Streams the Wikidata JSON dump and yields Triple objects directly to the graph store.
Does NOT produce CanonicalQA records (Wikidata is used for entity linking, not QA).
"""
from __future__ import annotations

import bz2
import json
import logging
import uuid
from pathlib import Path
from typing import Generator

import httpx

from ..base import (
    AbstractDataSource,
    AbstractDownloader,
    AbstractMapper,
    AbstractParser,
)
from ...schema.canonical import CanonicalQA
from ...schema.graph import Entity, Triple
from ...schema.provenance import PredicateType, SourceName

logger = logging.getLogger(__name__)


class WikidataDownloader(AbstractDownloader):
    def download(self) -> list[Path]:
        base_url = self.config.get("dump_base_url", "https://dumps.wikimedia.org/wikidatawiki/entities")
        filename = self.config.get("dump_filename", "latest-all.json.bz2")
        url = f"{base_url}/{filename}"
        dest = self.raw_dir / filename

        if dest.exists():
            logger.info("[Wikidata] Dump already exists, skipping download.")
            return [dest]

        logger.info("[Wikidata] Downloading %s (this is ~100 GB, be patient)…", url)
        tmp = dest.with_suffix(".part")
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=None) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            tmp.rename(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return [dest]


class WikidataTripleStream:
    """
    Streams Wikidata JSON dump and yields (Entity, list[Triple]) pairs.
    Filters items per config (min_sitelinks, require_english_label, properties).
    """

    def __init__(self, raw_dir: Path, config: dict) -> None:
        self.raw_dir = raw_dir
        self.config = config

    def iter_entities(self, limit: int = 0) -> Generator[tuple[Entity, list[Triple]], None, None]:
        dump_path = self.raw_dir / self.config.get("dump_filename", "latest-all.json.bz2")
        if not dump_path.exists():
            logger.error("[Wikidata] Dump not found: %s", dump_path)
            return

        min_sitelinks = self.config.get("min_sitelinks", 1)
        require_en = self.config.get("require_english_label", True)
        props_to_extract: set[str] = set(self.config.get("properties_to_extract", []))
        skip_entities = max(0, int(self.config.get("skip_rows", 0)))
        eligible_skipped = 0

        yielded = 0
        with bz2.open(dump_path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if item.get("type") != "item":
                    continue

                qid = item.get("id", "")
                labels = item.get("labels", {})
                en_label = labels.get("en", {}).get("value", "")
                if require_en and not en_label:
                    continue

                sitelinks = item.get("sitelinks", {})
                if len(sitelinks) < min_sitelinks:
                    continue

                descriptions = item.get("descriptions", {})
                en_desc = descriptions.get("en", {}).get("value", "")

                entity = Entity(
                    entity_id=qid,
                    entity_type="wikidata_item",
                    label=en_label or qid,
                    description=en_desc or None,
                    wikidata_id=qid,
                    source=SourceName.WIKIDATA,
                )

                triples: list[Triple] = []
                claims = item.get("claims", {})
                for prop_id, statements in claims.items():
                    if props_to_extract and prop_id not in props_to_extract:
                        continue
                    predicate = _prop_to_predicate(prop_id)
                    if predicate is None:
                        continue
                    for stmt in statements:
                        mainsnak = stmt.get("mainsnak", {})
                        if mainsnak.get("snaktype") != "value":
                            continue
                        datavalue = mainsnak.get("datavalue", {})
                        obj_id = _extract_object_id(datavalue)
                        if obj_id is None:
                            continue
                        triples.append(
                            Triple(
                                triple_id=str(uuid.uuid4()),
                                subject_id=qid,
                                subject_type="wikidata_item",
                                predicate=predicate,
                                object_id=obj_id,
                                object_type="wikidata_item",
                                source=SourceName.WIKIDATA,
                            )
                        )

                if eligible_skipped < skip_entities:
                    eligible_skipped += 1
                    continue

                yield entity, triples
                yielded += 1
                if limit and yielded >= limit:
                    logger.info("[Wikidata] Reached entity limit=%d", limit)
                    break


class _NoopParser(AbstractParser):
    """Wikidata does not map to CanonicalQA; graph stream is handled separately."""

    def parse(self):
        if False:
            yield {}


class _NoopMapper(AbstractMapper):
    """Wikidata does not emit CanonicalQA records."""

    def map(self, raw: dict) -> CanonicalQA | None:
        return None


class WikidataSource(AbstractDataSource):
    """
    Adapter to expose Wikidata to SOURCE_REGISTRY/CLI commands.

    Note: `iter_canonical()` intentionally yields nothing. Use
    `iter_entities_triples()` for graph ingestion.
    """

    name = "wikidata"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self._downloader = WikidataDownloader(raw_dir, config)
        self._parser = _NoopParser(raw_dir, config)
        self._mapper = _NoopMapper(config)
        self._stream = WikidataTripleStream(raw_dir, config)

    @property
    def downloader(self) -> AbstractDownloader:
        return self._downloader

    @property
    def parser(self) -> AbstractParser:
        return self._parser

    @property
    def mapper(self) -> AbstractMapper:
        return self._mapper

    def iter_entities_triples(self, limit: int = 0) -> Generator[tuple[Entity, list[Triple]], None, None]:
        if not self._downloader.is_downloaded():
            self._downloader.download()
        yield from self._stream.iter_entities(limit=limit)


def _prop_to_predicate(prop_id: str) -> PredicateType | None:
    mapping = {
        "P31": PredicateType.INSTANCE_OF,
        "P279": PredicateType.SUBCLASS_OF,
        "P460": PredicateType.SAME_AS,
    }
    return mapping.get(prop_id)


def _extract_object_id(datavalue: dict) -> str | None:
    dtype = datavalue.get("type")
    val = datavalue.get("value")
    if dtype == "wikibase-entityid" and isinstance(val, dict):
        return val.get("id")
    if dtype == "string" and isinstance(val, str):
        return val
    return None
