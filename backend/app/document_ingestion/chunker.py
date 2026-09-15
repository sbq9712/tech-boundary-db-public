"""Docling native semantic chunking with the same tokenizer family as canonical bge-m3."""

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def chunker():
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import (
        HuggingFaceTokenizer,
    )
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        os.getenv("TECHDB_DOCUMENT_TOKENIZER", "BAAI/bge-m3")
    )
    return HybridChunker(
        tokenizer=HuggingFaceTokenizer(
            tokenizer=tokenizer,
            max_tokens=int(os.getenv("TECHDB_DOCUMENT_CHUNK_TOKENS", "512")),
        ),
        merge_peers=True,
    )


def chunks_for(
    document, document_id: str, source_file: str, checksum: str
) -> list[dict]:
    from .metadata import chunk_record

    engine = chunker()
    return [
        chunk_record(
            chunk,
            engine.contextualize(chunk),
            document_id,
            source_file,
            checksum,
            index,
        )
        for index, chunk in enumerate(engine.chunk(dl_doc=document))
        if chunk.text.strip()
    ]
