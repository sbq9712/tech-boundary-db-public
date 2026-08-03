# Canonical QA assets

This directory is a deployment contract, not an asset bundle. The `0801`
release does not rebuild or fabricate missing retrieval assets.

Verified upstream state at commit
`fdffba1ba6b8dc40e5927bf3d301dec144012bc4`:

- `vector_index_v2.pkl.gz` exists upstream (93,358,971 bytes)
- `bm25_index.pkl.gz` exists upstream (56,236,343 bytes)
- `jieba_custom_dict.txt` and `graph-export.json` exist upstream
- `bge-m3` is still downloaded separately by upstream `setup.sh`
- `data/processed/all-records-lite.json` is not committed at the raw GitHub path,
  but the 30 committed `lite-part-*.js` shards and the official
  `scripts/rebuild_lite_from_shards.py` reproduce it (verified: 59,717 records)
- upstream `config.py` still reads a Z.AI-specific key file at import time
- upstream `qa.js` still hard-codes a temporary `trycloudflare.com` URL

The internal `sbq9712/tech-db` retrieval service must be hydrated with the
existing compatible set supplied by the owner:

- `vector_index_v2.pkl` or `vector_index.pkl`
- `bm25_index.pkl`
- `jieba_custom_dict.txt`
- generated `all-records-lite.json` (run the upstream shard script; do not
  rebuild the embedding index)
- complete `bge-m3` model directory
- optional `graph-export.json` for the relationship graph

Configure the running service URL through `TECHDB_QA_SERVICE_URL`. These files
must stay outside Git and must not be copied into the portal web image.

Do not run upstream `setup.sh` unchanged on the company server. It assumes
Hugging Face access, Z.AI credentials, a user-home key file, and a temporary
Cloudflare workflow. The company
deployment must receive the complete model and record assets first, then use
the company API configuration. Until that happens, no QA service image is a
valid 0801 deliverable.
