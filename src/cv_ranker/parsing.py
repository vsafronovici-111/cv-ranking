from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import re
import zipfile
import xml.etree.ElementTree as ET


SUPPORTED_SUFFIXES = {".txt", ".md", ".docx", ".pdf"}


@dataclass
class ParsedCV:
    file_path: Path
    text: str
    warnings: list[str]


def iter_cv_files(folder: Path) -> Iterable[Path]:
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path


def parse_cv_file(file_path: Path) -> ParsedCV:
    suffix = file_path.suffix.lower()
    warnings: list[str] = []

    if suffix in {".txt", ".md"}:
        return ParsedCV(file_path=file_path, text=file_path.read_text(encoding="utf-8", errors="ignore"), warnings=[])

    if suffix == ".docx":
        try:
            text = _parse_docx(file_path)
            return ParsedCV(file_path=file_path, text=text, warnings=[])
        except Exception as exc:  # pragma: no cover - defensive parsing
            warnings.append(f"DOCX parse failed: {exc}")
            return ParsedCV(file_path=file_path, text="", warnings=warnings)

    if suffix == ".pdf":
        try:
            text = _parse_pdf_with_pypdf(file_path)
            return ParsedCV(file_path=file_path, text=text, warnings=[])
        except Exception as exc:
            warnings.append(
                "PDF parse failed. Install optional dependency 'pypdf' for PDF support. "
                f"Details: {exc}"
            )
            return ParsedCV(file_path=file_path, text="", warnings=warnings)

    return ParsedCV(file_path=file_path, text="", warnings=[f"Unsupported extension: {suffix}"])


def _parse_docx(file_path: Path) -> str:
    with zipfile.ZipFile(file_path) as archive:
        xml_bytes = archive.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines: list[str] = []

    for paragraph in root.findall(".//w:p", ns):
        parts: list[str] = []
        for text_node in paragraph.findall(".//w:t", ns):
            if text_node.text:
                parts.append(text_node.text)
        line = "".join(parts).strip()
        if line:
            lines.append(line)

    return "\n".join(lines)


def _parse_pdf_with_pypdf(file_path: Path) -> str:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(str(file_path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    text = "\n".join(pages)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

