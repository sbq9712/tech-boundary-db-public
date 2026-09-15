"""Stable document/chunk identity and original Docling item references for future KG edges."""

import hashlib
import json
import uuid


def chunk_record(
    chunk, text: str, document_id: str, source_file: str, checksum: str, index: int
) -> dict:
    native = chunk.meta.model_dump(mode="json", by_alias=True, exclude_none=True)
    provenance = [
        {"doc_ref": item.get("self_ref"), "provenance": item.get("prov", [])}
        for item in native.get("doc_items", [])
    ]
    pages = sorted(
        {
            p["page_no"]
            for item in provenance
            for p in item["provenance"]
            if "page_no" in p
        }
    )
    signature = hashlib.sha256(
        json.dumps(
            [checksum, index, text, native], ensure_ascii=False, sort_keys=True
        ).encode()
    ).hexdigest()
    chunk_id = str(uuid.uuid5(uuid.UUID(document_id), signature))
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "text": text,
        "metadata": {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "source_file": source_file,
            "page_number": pages[0] if pages else None,
            "page_numbers": pages,
            "section_title": " / ".join(native.get("headings", [])),
            "chunk_index": index,
            "provenance": provenance,
            "docling": native,
            "original_sha256": checksum,
            "original_url": f"/api/uploads/{document_id}/download",
        },
    }
