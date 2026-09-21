import re
from typing import List

# Prototype-level chunking: fixed size with overlap, respects sentences where possible
DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 100
MIN_CHUNK_SIZE = 50


def _validate_text(text: str) -> str:
    if text is None:
        raise ValueError("Document text cannot be None")
    if not isinstance(text, str):
        raise ValueError("Document text must be a string")
    stripped = text.strip()
    if not stripped:
        raise ValueError("Document text cannot be empty")
    return stripped


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> List[str]:
    """Split text into overlapping chunks.

    - Validates input (empty/None/non-string -> ValueError)
    - Uses sentence-aware splitting when possible
    - Ensures overlap < chunk_size

    Args:
        text: input document text (plain text)
        chunk_size: max chars per chunk (default 500)
        overlap: chars overlapped between chunks (default 100)

    Returns:
        List of text chunks
    """
    validated = _validate_text(text)

    if chunk_size < MIN_CHUNK_SIZE:
        raise ValueError(f"chunk_size must be >= {MIN_CHUNK_SIZE}")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >=0 and < chunk_size")

    # If text fits one chunk, return as-is
    if len(validated) <= chunk_size:
        return [validated]

    chunks: List[str] = []
    # Simple sliding window with sentence boundary preference
    start = 0
    text_len = len(validated)

    # Pre-split into sentences for smarter boundaries (keep delimiters)
    # Split on sentence endings followed by space/newline
    sentences = re.split(r'(?<=[.!?])\s+', validated)

    # If splitting fails or one huge sentence, fall back to character window
    if len(sentences) <= 1 and len(validated) > chunk_size * 2:
        # Character window fallback
        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunk = validated[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= text_len:
                break
            start = end - overlap
        return chunks

    # Sentence-aware packing
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        # If adding sentence exceeds chunk_size, flush current
        if current and len(current) + 1 + len(sent) > chunk_size:
            chunks.append(current.strip())
            # Carry overlap: take last overlap chars from current
            if overlap > 0 and len(current) > overlap:
                # Try to start overlap at a word boundary
                overlap_text = current[-overlap:]
                # Find next space to avoid broken word
                space_idx = overlap_text.find(" ")
                if space_idx != -1:
                    overlap_text = overlap_text[space_idx+1:]
                current = overlap_text + " " + sent if overlap_text else sent
                current = current.strip()
                # If still too large (rare), force flush again
                if len(current) > chunk_size:
                    # Need to split this large sentence via char window
                    # Flush what we have without this sentence and handle sentence alone
                    # Remove sentence from current and handle separately
                    if overlap_text:
                        chunks[-1]  # already appended
                        current = sent
                    # If sentence itself > chunk_size, split it
                    if len(sent) > chunk_size:
                        sent_chunks = chunk_text(sent, chunk_size=chunk_size, overlap=overlap)
                        # Replace current with last partial
                        chunks.extend(sent_chunks[:-1])
                        current = sent_chunks[-1]
            else:
                current = sent
        else:
            current = (current + " " + sent).strip() if current else sent

    if current:
        chunks.append(current.strip())

    # Edge: if we produced no chunks due to logic, fallback to char window
    if not chunks:
        return [validated[:chunk_size]]

    return chunks
