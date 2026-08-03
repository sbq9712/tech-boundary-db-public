# Canonical QA asset contract

The portal repository does not store the large QA model or indexes. They are
delivered inside `techdb-canonical-qa:0801` on the `docker-images` branch and
run on the same server and Docker network as the portal.

Pinned sources:

- upstream repository commit: `fdffba1ba6b8dc40e5927bf3d301dec144012bc4`
- BAAI/bge-m3 revision: `5617a9f61b028005a4858fdac845db406aefb181`
- records rebuilt by the upstream shard script: 59,717
- vector index metadata: 24,091 records, 1,024 dimensions
- BM25 metadata: 24,091 records

The release image contains and verifies:

- `bge-m3-model/pytorch_model.bin` and tokenizer/configuration files
- `vector_index_v2.pkl` and `bm25_index.pkl`
- `jieba_custom_dict.txt` and `graph-export.json`
- generated `all-records-lite.json`
- `qa-assets-manifest.json` with exact sizes and SHA-256 values

The shard-rebuilt record order differs from the order used to build the
indexes. The release service therefore remaps index metadata at startup and
reports `index_mapping_ready=true`; deployment must fail if this check does
not pass.

Do not run the upstream `setup.sh` on the company server. Production must not
download from Hugging Face, access a developer workstation, or use a
Cloudflare tunnel. The QA container performs retrieval only; answer generation
remains in the portal API and uses the configured company intranet gateway.
