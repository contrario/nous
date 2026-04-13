"""
Noesis PDF Ingestion — Phase 7
==============================
Extracts text from PDF files and feeds into the Noesis lattice.
Supports single files, directories (recursive), and page-range filtering.

Dependencies: pip install pymupdf
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("noesis.pdf")


@dataclass
class PDFPage:
    file_path: str
    page_num: int
    text: str
    char_count: int


@dataclass
class PDFDocument:
    file_path: str
    file_name: str
    file_size: int
    page_count: int
    pages: list[PDFPage] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    text_hash: str = ""


@dataclass
class PDFIngestResult:
    files_scanned: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    pages_total: int = 0
    sentences_extracted: int = 0
    atoms_created: int = 0
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0


class PDFExtractor:

    MIN_LINE_LENGTH: int = 10
    MAX_LINE_LENGTH: int = 5000
    MIN_PAGE_CHARS: int = 20

    def __init__(self) -> None:
        try:
            import fitz
            self._fitz = fitz
        except ImportError:
            raise ImportError(
                "pymupdf required for PDF ingestion. "
                "Install: pip install pymupdf"
            )

    def extract_file(
        self,
        file_path: str | Path,
        page_start: int = 0,
        page_end: Optional[int] = None,
    ) -> Optional[PDFDocument]:
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"PDF not found: {file_path}")
            return None
        if not file_path.suffix.lower() == ".pdf":
            logger.warning(f"Not a PDF: {file_path}")
            return None

        try:
            doc = self._fitz.open(str(file_path))
        except Exception as e:
            logger.error(f"Cannot open PDF {file_path}: {e}")
            return None

        try:
            meta = {}
            if doc.metadata:
                for k in ("title", "author", "subject", "keywords", "creator"):
                    v = doc.metadata.get(k, "")
                    if v:
                        meta[k] = v

            end = page_end if page_end is not None else doc.page_count
            end = min(end, doc.page_count)

            pages: list[PDFPage] = []
            all_text_parts: list[str] = []

            for i in range(page_start, end):
                page = doc.load_page(i)
                text = page.get_text("text")
                text = self._clean_text(text)
                if len(text) < self.MIN_PAGE_CHARS:
                    continue
                pages.append(PDFPage(
                    file_path=str(file_path),
                    page_num=i + 1,
                    text=text,
                    char_count=len(text),
                ))
                all_text_parts.append(text)

            full_text = "\n".join(all_text_parts)
            text_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()[:16]

            pdf_doc = PDFDocument(
                file_path=str(file_path),
                file_name=file_path.name,
                file_size=file_path.stat().st_size,
                page_count=doc.page_count,
                pages=pages,
                metadata=meta,
                text_hash=text_hash,
            )
            return pdf_doc

        finally:
            doc.close()

    def _clean_text(self, text: str) -> str:
        text = text.replace("\x00", "")
        text = re.sub(r"[ \t]+", " ", text)
        lines = text.split("\n")
        cleaned: list[str] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if len(line) < 3:
                continue
            if re.match(r"^[\d\s\-\.]+$", line):
                continue
            if re.match(r"^(page|σελίδα)\s*\d+", line, re.IGNORECASE):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def extract_sentences(self, doc: PDFDocument) -> list[str]:
        sentences: list[str] = []
        for page in doc.pages:
            page_sentences = self._split_sentences(page.text)
            for s in page_sentences:
                s = s.strip()
                if len(s) < self.MIN_LINE_LENGTH:
                    continue
                if len(s) > self.MAX_LINE_LENGTH:
                    s = s[:self.MAX_LINE_LENGTH]
                sentences.append(s)
        return sentences

    def _split_sentences(self, text: str) -> list[str]:
        text = re.sub(r"\n(?=[a-zα-ω])", " ", text)
        text = re.sub(r"\n{2,}", "\n\n", text)
        paragraphs = text.split("\n\n")
        sentences: list[str] = []
        for para in paragraphs:
            para = para.replace("\n", " ").strip()
            if not para:
                continue
            parts = re.split(r"(?<=[.!?;·])\s+(?=[A-ZΑ-Ω0-9])", para)
            sentences.extend(parts)
        return sentences


class PDFIngestor:

    DEDUP_FILE: str = "noesis_pdf_hashes.json"

    def __init__(
        self,
        engine: object,
        base_dir: str = ".",
        source_tag: str = "pdf",
    ) -> None:
        self.engine = engine
        self.base_dir = Path(base_dir)
        self.extractor = PDFExtractor()
        self.source_tag = source_tag
        self._seen_hashes: set[str] = set()
        self._load_hashes()

    def _hash_path(self) -> Path:
        return self.base_dir / self.DEDUP_FILE

    def _load_hashes(self) -> None:
        hp = self._hash_path()
        if hp.exists():
            try:
                data = json.loads(hp.read_text(encoding="utf-8"))
                self._seen_hashes = set(data.get("hashes", []))
                logger.info(f"Loaded {len(self._seen_hashes)} PDF hashes")
            except Exception as e:
                logger.warning(f"Cannot load PDF hashes: {e}")
                self._seen_hashes = set()

    def _save_hashes(self) -> None:
        hp = self._hash_path()
        try:
            hp.write_text(
                json.dumps({"hashes": sorted(self._seen_hashes)}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Cannot save PDF hashes: {e}")

    def ingest_file(
        self,
        file_path: str | Path,
        page_start: int = 0,
        page_end: Optional[int] = None,
        force: bool = False,
    ) -> PDFIngestResult:
        result = PDFIngestResult()
        result.files_scanned = 1
        t0 = time.time()

        doc = self.extractor.extract_file(file_path, page_start, page_end)
        if doc is None:
            result.files_failed = 1
            result.errors.append(f"Failed to extract: {file_path}")
            result.duration_s = time.time() - t0
            return result

        if not force and doc.text_hash in self._seen_hashes:
            result.files_skipped = 1
            logger.info(f"Skipping already-ingested PDF: {doc.file_name}")
            result.duration_s = time.time() - t0
            return result

        sentences = self.extractor.extract_sentences(doc)
        result.pages_total = len(doc.pages)
        result.sentences_extracted = len(sentences)

        if not sentences:
            result.files_skipped = 1
            logger.warning(f"No extractable text in: {doc.file_name}")
            result.duration_s = time.time() - t0
            return result

        atoms_before = len(self.engine.lattice.atoms) if hasattr(self.engine, "lattice") else 0

        source_label = f"pdf:{doc.file_name}"
        for sentence in sentences:
            try:
                self.engine.learn(sentence, source=source_label)
            except Exception as e:
                result.errors.append(f"Learn error: {e}")

        atoms_after = len(self.engine.lattice.atoms) if hasattr(self.engine, "lattice") else 0
        result.atoms_created = atoms_after - atoms_before
        result.files_processed = 1

        self._seen_hashes.add(doc.text_hash)
        self._save_hashes()

        logger.info(
            f"PDF ingested: {doc.file_name} | "
            f"{len(doc.pages)} pages | "
            f"{len(sentences)} sentences | "
            f"{result.atoms_created} atoms"
        )

        result.duration_s = time.time() - t0
        return result

    def ingest_directory(
        self,
        dir_path: str | Path,
        recursive: bool = True,
        force: bool = False,
    ) -> PDFIngestResult:
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            r = PDFIngestResult()
            r.errors.append(f"Not a directory: {dir_path}")
            return r

        total = PDFIngestResult()
        t0 = time.time()

        pattern = "**/*.pdf" if recursive else "*.pdf"
        pdf_files = sorted(dir_path.glob(pattern))
        total.files_scanned = len(pdf_files)

        if not pdf_files:
            logger.info(f"No PDFs found in: {dir_path}")
            total.duration_s = time.time() - t0
            return total

        logger.info(f"Found {len(pdf_files)} PDFs in: {dir_path}")

        for pdf_file in pdf_files:
            r = self.ingest_file(pdf_file, force=force)
            total.files_processed += r.files_processed
            total.files_skipped += r.files_skipped
            total.files_failed += r.files_failed
            total.pages_total += r.pages_total
            total.sentences_extracted += r.sentences_extracted
            total.atoms_created += r.atoms_created
            total.errors.extend(r.errors)

        total.duration_s = time.time() - t0
        return total

    def scan_for_pdfs(self, dir_path: str | Path, recursive: bool = True) -> list[dict[str, object]]:
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            return []
        pattern = "**/*.pdf" if recursive else "*.pdf"
        results: list[dict[str, object]] = []
        for f in sorted(dir_path.glob(pattern)):
            already = False
            try:
                doc = self.extractor.extract_file(f)
                if doc and doc.text_hash in self._seen_hashes:
                    already = True
                pages = doc.page_count if doc else 0
                size_kb = f.stat().st_size / 1024
            except Exception:
                pages = 0
                size_kb = 0
            results.append({
                "path": str(f),
                "name": f.name,
                "size_kb": round(size_kb, 1),
                "pages": pages,
                "already_ingested": already,
            })
        return results


def main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Noesis PDF Ingestion")
    parser.add_argument("path", help="PDF file or directory path")
    parser.add_argument("--lattice", default="noesis_lattice.json", help="Lattice file path")
    parser.add_argument("--force", action="store_true", help="Re-ingest already-seen PDFs")
    parser.add_argument("--scan", action="store_true", help="Scan only, don't ingest")
    parser.add_argument("--no-recursive", action="store_true", help="Don't recurse into subdirs")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from noesis_engine import NoesisEngine

    engine = NoesisEngine()
    lattice_path = Path(args.lattice)
    if lattice_path.exists():
        engine.load(lattice_path)
        logger.info(f"Loaded lattice: {len(engine.lattice.atoms)} atoms")

    ingestor = PDFIngestor(engine, base_dir=str(Path(__file__).parent))

    target = Path(args.path)

    if args.scan:
        if target.is_dir():
            pdfs = ingestor.scan_for_pdfs(target, recursive=not args.no_recursive)
        else:
            pdfs = ingestor.scan_for_pdfs(target.parent, recursive=False)
            pdfs = [p for p in pdfs if p["name"] == target.name]
        print(f"\n{'='*60}")
        print(f"PDF Scan: {target}")
        print(f"{'='*60}")
        for p in pdfs:
            status = "✓ ingested" if p["already_ingested"] else "○ new"
            print(f"  {status} | {p['name']} | {p['pages']} pages | {p['size_kb']} KB")
        print(f"\nTotal: {len(pdfs)} PDFs, {sum(1 for p in pdfs if not p['already_ingested'])} new")
        return

    if target.is_dir():
        result = ingestor.ingest_directory(target, recursive=not args.no_recursive, force=args.force)
    elif target.is_file():
        result = ingestor.ingest_file(target, force=args.force)
    else:
        print(f"Path not found: {target}")
        sys.exit(1)

    engine.save(lattice_path)

    print(f"\n{'='*60}")
    print(f"PDF Ingestion Complete")
    print(f"{'='*60}")
    print(f"  Files scanned:  {result.files_scanned}")
    print(f"  Files processed: {result.files_processed}")
    print(f"  Files skipped:   {result.files_skipped}")
    print(f"  Files failed:    {result.files_failed}")
    print(f"  Pages total:     {result.pages_total}")
    print(f"  Sentences:       {result.sentences_extracted}")
    print(f"  Atoms created:   {result.atoms_created}")
    print(f"  Duration:        {result.duration_s:.2f}s")
    if result.errors:
        print(f"  Errors ({len(result.errors)}):")
        for e in result.errors[:10]:
            print(f"    - {e}")


if __name__ == "__main__":
    main()
