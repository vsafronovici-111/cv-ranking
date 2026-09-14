from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

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
    return parse_cv_bytes(file_path.name, file_path.read_bytes(), file_path=file_path)


def parse_cv_bytes(filename: str, data: bytes, file_path: Path | None = None) -> ParsedCV:
    """Parse CV content held in memory (e.g. loaded from a DB blob).

    `file_path` is optional metadata retained on `ParsedCV` for callers that
    still want a `Path`-shaped result; when omitted a synthetic `Path(filename)`
    is used so downstream code (which reads `.name`) keeps working.
    """
    path = file_path if file_path is not None else Path(filename)
    suffix = path.suffix.lower()
    warnings: list[str] = []

    if suffix in {".txt", ".md"}:
        text = data.decode("utf-8", errors="ignore")
        return ParsedCV(file_path=path, text=text, warnings=[])

    if suffix == ".docx":
        try:
            text = _parse_docx_bytes(data)
            return ParsedCV(file_path=path, text=text, warnings=[])
        except Exception as exc:  # noqa: BLE001 - pragma: no cover - any docx-parsing failure degrades to a warning
            warnings.append(f"DOCX parse failed: {exc}")
            return ParsedCV(file_path=path, text="", warnings=warnings)

    if suffix == ".pdf":
        try:
            text = _parse_pdf_bytes_with_pypdf(data)
            return ParsedCV(file_path=path, text=text, warnings=[])
        except Exception as exc:  # noqa: BLE001 - any pdf-parsing failure degrades to a warning, not a crash
            warnings.append(f"PDF parse failed. Install optional dependency 'pypdf' for PDF support. Details: {exc}")
            return ParsedCV(file_path=path, text="", warnings=warnings)

    return ParsedCV(file_path=path, text="", warnings=[f"Unsupported extension: {suffix}"])


def _parse_docx_bytes(data: bytes) -> str:
    with zipfile.ZipFile(BytesIO(data)) as archive:
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


def _parse_pdf_bytes_with_pypdf(data: bytes) -> str:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(BytesIO(data))
    pages = [(page.extract_text() or "") for page in reader.pages]
    text = "\n".join(pages)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
