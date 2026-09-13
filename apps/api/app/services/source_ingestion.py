"""Source Ingestion Service for Repurposing Mode.

Ingests source documents from:
- Web article URLs
- Raw text transcripts (podcasts, YouTube, speeches)
- Markdown / Research papers / PDFs
Extracts cleaned text, metadata, and structural segments.
"""

import re
import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SourceType(str):
    ARTICLE_URL = "article_url"
    YOUTUBE_TRANSCRIPT = "youtube_transcript"
    PODCAST_AUDIO = "podcast_audio"
    PDF_DOCUMENT = "pdf_document"
    RAW_TEXT = "raw_text"


class SourceDocument(BaseModel):
    id: str = Field(default_factory=lambda: f"src_{uuid.uuid4().hex[:8]}")
    title: str
    source_type: str
    source_uri: Optional[str] = None
    raw_text: str
    word_count: int
    key_entities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SourceIngestionService:
    @staticmethod
    def clean_text(text: str) -> str:
        """Strip excess whitespace, HTML tags, and non-printable characters."""
        # Remove simple HTML tags
        clean = re.sub(r"<[^>]+>", " ", text)
        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def ingest_text(
        title: str,
        text: str,
        source_type: str = SourceType.RAW_TEXT,
        source_uri: Optional[str] = None,
    ) -> SourceDocument:
        """Ingest raw transcript or article text."""
        cleaned = SourceIngestionService.clean_text(text)
        words = cleaned.split()
        return SourceDocument(
            title=title,
            source_type=source_type,
            source_uri=source_uri,
            raw_text=cleaned,
            word_count=len(words),
        )

    @staticmethod
    def chunk_document(doc: SourceDocument, max_words_per_chunk: int = 400) -> List[str]:
        """Break document into semantic chapters/chunks for LLM reasoning."""
        words = doc.raw_text.split()
        if not words:
            return []
        chunks = []
        for i in range(0, len(words), max_words_per_chunk):
            chunk = " ".join(words[i:i + max_words_per_chunk])
            chunks.append(chunk)
        return chunks
