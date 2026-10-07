import hashlib
import math
import re
from collections import Counter

TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.%-]*|[\u4e00-\u9fff]")
INJECTION_PATTERNS = (
    re.compile(r"ignore (all |any )?(previous|above) instructions?", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"忽略.{0,8}(之前|以上|系统).{0,8}(指令|提示)"),
    re.compile(r"(泄露|输出).{0,8}(系统提示词|system prompt)", re.I),
)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def hash_embedding(text: str, dimensions: int = 256) -> list[float]:
    """Dependency-free feature hashing used as a deterministic local fallback."""
    vector = [0.0] * dimensions
    counts = Counter(tokenize(text))
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest, "big") % dimensions
        sign = 1 if digest[0] & 1 else -1
        vector[bucket] += sign * (1 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def contains_prompt_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in INJECTION_PATTERNS)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ").replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        pieces = _split_long_text(paragraph, chunk_size)
        for piece in pieces:
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if len(candidate) <= chunk_size:
                current = candidate
                continue
            if current:
                chunks.append(current)
                prefix = current[-overlap:] if overlap else ""
                current = f"{prefix}\n{piece}".strip()
            else:
                chunks.append(piece)
    if current:
        chunks.append(current)
    return chunks


def _split_long_text(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    sentences = re.split(r"(?<=[。！？.!?；;])", text)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > size:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(sentence[index : index + size] for index in range(0, len(sentence), size))
        elif len(current) + len(sentence) <= size:
            current += sentence
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces

