"""AI assistant: retrieval-augmented, document-grounded question answering.

How it works (all local, no external AI service, so documents never leave the server):
  1. Index    - each processed document's cleaned text is split into chunks and the
                chunks are stored in the database (`chunks` table).
  2. Embed    - chunks are turned into TF-IDF vectors (a sparse vector space). This is
                lexical retrieval, not neural embeddings.
  3. Retrieve - the question is vectorised and compared to every chunk by cosine
                similarity. The vector index is cached and rebuilt only when the stored
                chunks change.
  4. Ground   - the answer is built ONLY from lines of the retrieved chunks, with the
                supporting document and chunk listed as sources.
  5. Refuse   - if the best match is weak, or too few of the question's terms occur in
                the documents, the assistant says the available documents do not contain
                enough information. Every question (answered or not) is logged.
"""
import logging
import re
import threading

import config
import database as db

log = logging.getLogger(__name__)

NOT_ENOUGH = "The available documents do not contain enough information to answer this question."

STOP = {"the", "an", "is", "are", "was", "were", "of", "for", "to", "in", "on", "and", "or", "what", "which",
        "who", "whom", "how", "does", "do", "did", "this", "that", "with", "from", "by", "at", "be", "it",
        "its", "as", "me", "my", "there", "any", "tell", "show", "give", "list", "has", "have", "had", "can",
        "please", "all", "about", "their", "them", "these", "those", "when", "where",
        "document", "documents", "file", "files", "mention", "mentions", "mentioned", "contain", "contains",
        "which", "every", "each", "both"}


_PHONE = re.compile(r"\+\d[\d\s().-]{6,}\d|\(\d{3}\)\s*\d{3}[-\s]\d{4}|\b\d{3}[-\s]\d{3}[-\s]\d{4}\b")


def tokenize(text: str) -> list:
    """Lower-case words. Values that appear without a label also get a type word
    (an address with '@' counts as 'email', a phone-shaped number as 'phone'), so
    'What is X's email?' can find the line even when the document has no 'Email:' label."""
    text = text or ""
    tokens = [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1 and t not in STOP]
    if "@" in text:
        tokens.append("email")
    if _PHONE.search(text):
        tokens.append("phone")
    return tokens


# ----------------------------------------------------------------- chunking
def chunk_text(text: str, size: int = None, keep_lines: int = 1) -> list:
    """Split text into line-aligned chunks of about `size` characters.

    The last `keep_lines` lines of a chunk are repeated at the start of the next,
    so a value is never separated from its label.
    """
    size = size or config.CHUNK_CHARS
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    chunks, cur, n = [], [], 0
    for line in lines:
        if len(cur) > keep_lines and n + len(line) + 1 > size:
            chunks.append("\n".join(cur))
            cur = cur[-keep_lines:] if keep_lines else []
            n = sum(len(x) + 1 for x in cur)
        cur.append(line)
        n += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def index_document(doc_id: int, text: str) -> int:
    """Store the chunks of a document for retrieval. Returns the number of chunks."""
    chunks = chunk_text(text)
    db.replace_chunks(doc_id, chunks)
    return len(chunks)


# ------------------------------------------------------------ vector index
_lock = threading.Lock()
_index = {"key": None, "vec": None, "matrix": None, "rows": [], "idf": {}, "max_idf": 1.0}
stats = {"builds": 0, "searches": 0}


def reset_index() -> None:
    """Drop the cached index (simulates a fresh start; it is rebuilt from the database)."""
    with _lock:
        _index.update(key=None, vec=None, matrix=None, rows=[], idf={}, max_idf=1.0)


def _get_index():
    key = (config.DB_PATH, db.chunk_stamp())
    with _lock:
        if _index["key"] == key:
            return _index
        rows = db.eligible_chunks()
        vec = matrix = None
        idf, max_idf = {}, 1.0
        if rows:
            from sklearn.feature_extraction.text import TfidfVectorizer
            vec = TfidfVectorizer(tokenizer=tokenize, lowercase=False, token_pattern=None,
                                  ngram_range=(1, 2), sublinear_tf=True)
            try:
                matrix = vec.fit_transform([r["text"] for r in rows])
                idf = {t: float(vec.idf_[i]) for t, i in vec.vocabulary_.items() if " " not in t}
                max_idf = float(vec.idf_.max())
            except ValueError:  # no usable words in any chunk
                vec = matrix = None
        _index.update(key=key, vec=vec, matrix=matrix, rows=rows, idf=idf, max_idf=max_idf)
        stats["builds"] += 1
        return _index


def search(question: str, k: int = None):
    """Return (hits, coverage). Each hit has document/chunk info and a cosine score."""
    k = k or config.RAG_TOP_K
    idx = _get_index()
    stats["searches"] += 1
    q_tokens = set(tokenize(question))
    if idx["vec"] is None or not q_tokens:
        return [], 0.0
    weights = {t: idx["idf"].get(t, idx["max_idf"]) for t in q_tokens}  # unseen words weigh the most
    coverage = sum(w for t, w in weights.items() if t in idx["idf"]) / sum(weights.values())
    sims = (idx["matrix"] @ idx["vec"].transform([question]).T).toarray().ravel()
    order = sims.argsort()[::-1][:k]
    hits = []
    for i in order:
        if sims[i] <= 0:
            break
        row = idx["rows"][i]
        hits.append({"document_id": row["document_id"], "filename": row["filename"], "status": row["status"],
                     "chunk_index": row["chunk_index"], "text": row["text"], "score": round(float(sims[i]), 3)})
    return hits, round(coverage, 3)


def _best_lines(text: str, q_tokens: set, idf: dict, max_idf: float, n: int = 3) -> list:
    """Pick up to n lines that together cover the most (rarity-weighted) question words."""
    lines = [(pos, ln.strip(), set(tokenize(ln))) for pos, ln in enumerate(text.splitlines()) if ln.strip()]
    uncovered, chosen = set(q_tokens), []
    while uncovered and len(chosen) < n:
        best, best_gain = None, 0.0
        for item in lines:
            if item in chosen:
                continue
            gain = sum(idf.get(t, max_idf) for t in uncovered & item[2])
            if gain > best_gain:
                best, best_gain = item, gain
        if best is None:
            break
        chosen.append(best)
        uncovered -= best[2]
    return [ln for _, ln, _ in sorted(chosen)]  # keep the original document order


_MULTI = re.compile(r"\b(which|list|all|every|each|both)\b", re.I)
# "ACME Trading and Bluebird Supplies": two capitalised names joined by 'and', '&' or a comma
_ENTITY_LIST = re.compile(r"\b[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*\s*(?:,|\band\b|&)\s*[A-Z]")


def ask(question: str) -> dict:
    """Answer a question from the stored documents.

    Returns {"answer", "grounded", "sources", "top_score", "coverage", "reason"}.
    """
    question = (question or "").strip()
    if len(question) < 3:
        return {"answer": "Please type a question.", "grounded": False, "sources": [],
                "top_score": 0.0, "coverage": 0.0, "reason": "question too short"}
    multi = bool(_MULTI.search(question) or _ENTITY_LIST.search(question))  # question may span several documents
    hits, coverage = search(question, k=config.RAG_TOP_K * 3 if multi else None)
    best = hits[0]["score"] if hits else 0.0

    if not hits or best < config.RAG_MIN_SCORE or coverage < config.RAG_MIN_COVERAGE:
        reason = ("no documents are indexed yet" if _index["vec"] is None else
                  f"best match {best:.2f} (needs {config.RAG_MIN_SCORE:.2f}), "
                  f"question terms found {coverage:.0%} (needs {config.RAG_MIN_COVERAGE:.0%})")
        _log(question, False, best, coverage, [])
        return {"answer": NOT_ENOUGH, "grounded": False, "sources": [], "top_score": best,
                "coverage": coverage, "reason": reason}

    q_tokens = set(tokenize(question))
    idx = _index
    ratio = 0.3 if multi else 0.8
    keep = [h for h in hits if h["score"] >= max(config.RAG_MIN_SCORE * 0.5, ratio * best)]
    per_doc, sources = {}, []
    for h in keep:
        lines = _best_lines(h["text"], q_tokens, idx["idf"], idx["max_idf"])
        if not lines:
            continue
        if multi:  # in a wide search keep a document only if it matches a distinctive word of the question
            matched = q_tokens & {t for ln in lines for t in tokenize(ln)}
            if not any(idx["idf"].get(t, 0) >= 0.5 * idx["max_idf"] for t in matched):
                continue
        per_doc.setdefault(h["document_id"], {"filename": h["filename"], "lines": []})
        for ln in lines:
            if ln not in per_doc[h["document_id"]]["lines"]:
                per_doc[h["document_id"]]["lines"].append(ln)
        sources.append({"document_id": h["document_id"], "filename": h["filename"], "status": h["status"],
                        "chunk_index": h["chunk_index"], "score": h["score"],
                        "snippet": h["text"][:200]})
    if not per_doc:  # matched words only in headings we could not quote
        _log(question, False, best, coverage, [])
        return {"answer": NOT_ENOUGH, "grounded": False, "sources": [], "top_score": best,
                "coverage": coverage, "reason": "no supporting lines found in the matched chunks"}

    if len(per_doc) == 1:
        d = next(iter(per_doc.values()))
        answer = f"According to **{d['filename']}**: " + "; ".join(d["lines"])
    else:
        answer = "Found in several documents:\n" + "\n".join(
            f"- **{d['filename']}**: " + "; ".join(d["lines"]) for d in per_doc.values())
    _log(question, True, best, coverage, [s["document_id"] for s in sources])
    return {"answer": answer, "grounded": True, "sources": sources, "top_score": best,
            "coverage": coverage, "reason": "answered from retrieved document text"}


def _log(question, grounded, top_score, coverage, source_ids) -> None:
    try:
        db.log_question(question, grounded, top_score, coverage, source_ids)
    except db.DatabaseError:
        log.warning("Could not record assistant question")
