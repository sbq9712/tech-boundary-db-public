#!/usr/bin/env python3
"""Import RSS source metadata from chatbot_integration_package into sources table.

Usage:
    python scripts/import_rss_sources.py

Environment:
    DATABASE_URL: PostgreSQL connection string (default from docker-compose)
"""
import json
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Adjust import path if running from container
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from app.models.source import Source

DATABASE_URL = "postgresql+psycopg2://tech:tech@db:5432/tech_intel"
DATA_SOURCE_PATH = Path(__file__).parent.parent / "data_sources" / "tech_kb_builder_2025w41" / "indexes" / "source_index.jsonl"


def import_sources(dry_run: bool = False):
    engine = create_engine(DATABASE_URL)
    
    if not DATA_SOURCE_PATH.exists():
        print(f"❌ source_index.jsonl not found at {DATA_SOURCE_PATH}")
        return
    
    print(f"📂 Reading {DATA_SOURCE_PATH}")
    
    with Session(engine) as session:
        # Check existing external_refs to avoid duplicates
        existing_refs = set(session.scalars(select(Source.external_ref).where(Source.external_ref.isnot(None))).all())
        print(f"🔍 Found {len(existing_refs)} existing sources with external_ref")
        
        to_import = []
        skipped = 0
        
        with open(DATA_SOURCE_PATH, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if i % 5000 == 0:
                    print(f"   ... processing line {i}")
                
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                source_id = record.get("source_id")
                if not source_id:
                    continue
                
                # Skip if already imported
                if source_id in existing_refs:
                    skipped += 1
                    continue
                
                # Map source_type
                st = record.get("source_type", "unknown")
                if st == "literature_summary":
                    source_type = "journal_rss"
                elif st == "news_original":
                    source_type = "news_rss"
                elif st == "wechat_article":
                    source_type = "wechat"
                else:
                    source_type = st
                
                # Parse published_at if present
                pub_at = None
                if record.get("publish_date"):
                    try:
                        pub_at = datetime.fromisoformat(record["publish_date"].replace("Z", "+00:00"))
                    except:
                        pass
                
                source = Source(
                    id=uuid.uuid4(),
                    external_ref=source_id,  # Keep original src_ prefix
                    source_type=source_type,
                    title=record.get("title"),
                    url_or_path=record.get("url"),
                    source_name=record.get("source_name"),  # Journal/website name
                    published_at=pub_at,
                    captured_at=datetime.utcnow(),
                    access_level="public",
                    reliability_rating="low",  # All RSS sources start as low
                    domain=record.get("domain"),
                    subdomain=record.get("subdomain"),
                    needs_reclassification=True,  # All need manual review
                    notes=f"Imported from tech_kb_builder_2025w41, file_name={record.get('file_name')}",
                )
                to_import.append(source)
        
        print(f"\n📊 Statistics:")
        print(f"   Total lines processed: {i}")
        print(f"   Skipped (already imported): {skipped}")
        print(f"   Ready to import: {len(to_import)}")
        
        if dry_run:
            print("\n🔍 DRY RUN - No changes made")
            if to_import:
                print("\n Sample of first 3 sources:")
                for s in to_import[:3]:
                    print(f"   {s.external_ref}: {s.title[:80]}... | {s.source_type} | {s.domain}/{s.subdomain}")
            return
        
        if not to_import:
            print("✓ Nothing to import")
            return
        
        print("\n💾 Importing sources...")
        session.add_all(to_import)
        session.commit()
        print(f"✅ Successfully imported {len(to_import)} sources")
        
        # Verify
        total = session.scalar(select(func.count(Source.id)))
        print(f"📈 Total sources in DB: {total}")


if __name__ == "__main__":
    import sys
    from sqlalchemy import func
    
    dry_run = "--dry-run" in sys.argv
    import_sources(dry_run=dry_run)
