# Breadth runtime data

Large runtime files in this directory are intentionally ignored by Git.

For local development, run:

```bash
bash ./start_with_local_ai.sh
```

The startup script hydrates the exact public Tech DB snapshot pinned in
[`breadth/UPSTREAM.md`](../../UPSTREAM.md), validates it, generates the local
alert and category snapshots, and only then rebuilds the web image.

Read-only validation:

```bash
python3 scripts/hydrate_breadth_runtime.py --check
```
