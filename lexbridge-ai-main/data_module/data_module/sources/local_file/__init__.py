"""
Local file ingest — CSV and JSON dropped into data/raw/local_file/ (or seeded from repo).

Maps rows/objects to CanonicalQA using configurable column/key names.
"""
from __future__ import annotations

import csv
import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Generator

from ..base import AbstractDataSource, AbstractDownloader, AbstractMapper, AbstractParser
from ...schema.canonical import CanonicalAnswer, CanonicalQA
from ...schema.provenance import License, SourceName

logger = logging.getLogger(__name__)


def _package_root() -> Path:
    """Installed `data_module` package directory (optional bundled sample_data/)."""
    return Path(__file__).resolve().parents[2]


def _resolve_import_path(raw: str, config: dict) -> Path:
    """Resolve a path from YAML: absolute, or relative to _config_file_parent."""
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.resolve()
    base = config.get("_config_file_parent")
    if base:
        return (Path(base) / p).resolve()
    return p.resolve()


class LocalFileDownloader(AbstractDownloader):
    """
    Copies seed files from the repo into raw_dir. No network.

    If raw_dir already contains .csv or .json, download is skipped unless
    `force_reseed: true` in config.
    """

    def is_downloaded(self) -> bool:
        if self.config.get("force_reseed", False):
            return False
        if not self.raw_dir.exists():
            return False
        return bool(list(self.raw_dir.glob("*.csv")) or list(self.raw_dir.glob("*.json")))

    def download(self) -> list[Path]:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        pkg = _package_root()
        for rel in self.config.get("seed_files", []):
            src = (pkg / rel).resolve()
            if not src.is_file():
                logger.warning("[local_file] seed file missing, skip: %s", src)
                continue
            dest = self.raw_dir / src.name
            shutil.copy2(src, dest)
            saved.append(dest)
            logger.info("[local_file] Seeded %s → %s", src.name, dest)

        for raw_path in self.config.get("extra_import", []):
            src = _resolve_import_path(str(raw_path), self.config)
            if not src.is_file():
                logger.warning("[local_file] extra_import missing, skip: %s", src)
                continue
            dest = self.raw_dir / src.name
            shutil.copy2(src, dest)
            saved.append(dest)
            logger.info("[local_file] Imported %s → %s", src.name, dest)
        return saved


class LocalFileParser(AbstractParser):
    """Yield one dict per CSV row or JSON object (array / JSONL / single object)."""

    def parse(self) -> Generator[dict[str, Any], None, None]:
        skip_rows = int(self.config.get("skip_rows", 0))
        only = self.config.get("only_files")
        if only:
            names = {str(n).lower() for n in only}
        else:
            names = None

        if not self.raw_dir.exists():
            logger.warning("[local_file] raw_dir does not exist: %s", self.raw_dir)
            return
        yield from self._iter_csv(names, skip_rows)
        yield from self._iter_json(names, skip_rows)

    def _iter_csv(
        self, only_names: set[str] | None, skip_rows: int
    ) -> Generator[dict[str, Any], None, None]:
        for path in sorted(self.raw_dir.glob("*.csv")):
            if only_names and path.name.lower() not in only_names:
                continue
            with open(path, newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    continue
                for i, row in enumerate(reader):
                    if i < skip_rows:
                        continue
                    rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                    rec["_source_file"] = path.name
                    yield rec

    def _iter_json(
        self, only_names: set[str] | None, skip_rows: int
    ) -> Generator[dict[str, Any], None, None]:
        for path in sorted(self.raw_dir.glob("*.json")):
            if only_names and path.name.lower() not in only_names:
                continue
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            items: list[dict[str, Any]] = []
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    items = [x for x in parsed if isinstance(x, dict)]
                elif isinstance(parsed, dict):
                    items = [parsed]
            except json.JSONDecodeError:
                for ln in text.splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict):
                        items.append(obj)

            for i, obj in enumerate(items):
                if i < skip_rows:
                    continue
                if not isinstance(obj, dict):
                    continue
                obj = dict(obj)
                obj["_source_file"] = path.name
                yield obj


class LocalFileMapper(AbstractMapper):
    """Map a flat dict (CSV row / JSON object) to CanonicalQA."""

    def map(self, raw: dict[str, Any]) -> CanonicalQA | None:
        m = self.config.get("column_mapping") or {}
        id_key = m.get("id_column", "id")
        title_key = m.get("title_column", "title")
        body_key = m.get("body_column", "body")
        answer_key = m.get("answer_column", "answer")
        answers_key = m.get("answers_column")  # optional list in JSON

        def g(key: str) -> str:
            v = raw.get(key, "")
            if v is None:
                return ""
            return str(v).strip()

        sid = g(id_key) or str(uuid.uuid4())
        title = g(title_key)
        body = g(body_key)
        if not title and body:
            title = body[:120] + ("…" if len(body) > 120 else "")
        if not title:
            return None

        canonical_answers: list[CanonicalAnswer] = []
        if answers_key and raw.get(answers_key) is not None:
            ans_val = raw[answers_key]
            if isinstance(ans_val, list):
                for j, a in enumerate(ans_val):
                    t = str(a).strip() if a is not None else ""
                    if not t:
                        continue
                    aid = str(
                        uuid.uuid5(uuid.NAMESPACE_URL, f"local_file:{sid}:ans{j}:{t[:80]}")
                    )
                    canonical_answers.append(
                        CanonicalAnswer(answer_id=aid, body=t, score=1, is_accepted=(j == 0))
                    )
        else:
            ans = g(answer_key)
            if ans:
                aid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"local_file:{sid}:a"))
                canonical_answers.append(
                    CanonicalAnswer(answer_id=aid, body=ans, score=1, is_accepted=True)
                )

        if not canonical_answers:
            return None

        tags: list[str] = []
        for col in m.get("tag_columns", []) or []:
            t = g(str(col))
            if t:
                tags.append(t)
        kw_col = m.get("keywords_column")
        if kw_col:
            for part in g(str(kw_col)).split(","):
                p = part.strip()
                if p and p not in tags:
                    tags.append(p)

        meta_keys = {
            id_key,
            title_key,
            body_key,
            answer_key,
            answers_key,
            "_source_file",
            *(m.get("tag_columns") or []),
            kw_col,
        }
        extra = {k: v for k, v in raw.items() if k not in meta_keys and k is not None}

        try:
            lic = License(self.config.get("license", "unknown"))
        except ValueError:
            lic = License.UNKNOWN

        cid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"local_file:{sid}"))

        return CanonicalQA(
            id=cid,
            source=SourceName.LOCAL_FILE,
            source_id=sid,
            title=title,
            body=body or title,
            answers=canonical_answers,
            accepted_answer_id=canonical_answers[0].answer_id,
            tags=tags,
            language=self.config.get("language", "en"),
            score=1,
            answer_count=len(canonical_answers),
            source_url=self.config.get("source_url"),
            license=lic,
            extra=extra,
        )


class LocalFileSource(AbstractDataSource):
    name = "local_file"

    def __init__(self, raw_dir: Path, config: dict) -> None:
        super().__init__(raw_dir, config)
        self._downloader = LocalFileDownloader(raw_dir, config)
        self._parser = LocalFileParser(raw_dir, config)
        self._mapper = LocalFileMapper(config)

    @property
    def downloader(self) -> AbstractDownloader:
        return self._downloader

    @property
    def parser(self) -> AbstractParser:
        return self._parser

    @property
    def mapper(self) -> AbstractMapper:
        return self._mapper
