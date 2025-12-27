#!/usr/bin/env python3
"""Script to sync documents from docs/ directory to Google Gemini File Search Store.

Usage:
    python scripts/sync_filesearch.py [--docs-dir PATH]

File naming conventions for item_id extraction:
    - item_12345.txt -> item_id = "12345"
    - item_12345_description.md -> item_id = "12345"
    - faq.txt -> general document (no item_id)
    - delivery_terms.md -> general document (no item_id)

Alternatively, create a .meta.json file alongside the document:
    docs/product.txt
    docs/product.txt.meta.json  -> {"item_id": "12345", "category": "electronics"}

Supported formats: txt, docx, pdf, md, json

Requirements: 4.1, 4.2, 4.3, 4.4
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.rag.file_search_client import FileSearchClient


# Pattern to extract item_id from filename: item_12345.txt or item_12345_description.md
ITEM_ID_PATTERN = re.compile(r"^item[_-](\d+)", re.IGNORECASE)


def extract_item_id_from_filename(filename: str) -> str | None:
    """Extract item_id from filename if it follows the naming convention.
    
    Args:
        filename: Name of the file (without path)
        
    Returns:
        item_id string if found, None otherwise
    """
    match = ITEM_ID_PATTERN.match(filename)
    if match:
        return match.group(1)
    return None


def load_metadata_file(doc_path: Path) -> dict | None:
    """Load metadata from companion .meta.json file if exists.
    
    Args:
        doc_path: Path to the document file
        
    Returns:
        Metadata dict if file exists, None otherwise
    """
    meta_path = doc_path.with_suffix(doc_path.suffix + ".meta.json")
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  ⚠️  Ошибка чтения {meta_path.name}: {e}")
    return None


def discover_documents(docs_dir: Path) -> list[Path]:
    """Discover all supported documents in the directory.
    
    Args:
        docs_dir: Directory to scan
        
    Returns:
        List of document paths
    """
    supported = FileSearchClient.SUPPORTED_FORMATS
    documents = []
    
    for ext in supported:
        documents.extend(docs_dir.glob(f"*{ext}"))
        documents.extend(docs_dir.glob(f"**/*{ext}"))
    
    # Filter out meta files and duplicates
    documents = [
        p for p in documents 
        if not p.name.endswith(".meta.json")
    ]
    
    return sorted(set(documents))


async def sync_documents(docs_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    """Sync all documents from directory to File Search Store.
    
    Args:
        docs_dir: Directory containing documents
        dry_run: If True, only show what would be uploaded
        
    Returns:
        Tuple of (success_count, error_count)
    """
    try:
        settings = get_settings()
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        print("\nУбедитесь, что файл .env содержит:")
        print("  - GEMINI_API_KEY")
        print("  - FILE_SEARCH_STORE_NAME")
        return 0, 1

    # Initialize File Search client
    client = FileSearchClient(
        api_key=settings.gemini_api_key,
        store_name=settings.file_search_store_name,
    )

    # Discover documents
    documents = discover_documents(docs_dir)
    
    if not documents:
        print(f"📂 Документы не найдены в {docs_dir}")
        print(f"\nПоддерживаемые форматы: {', '.join(FileSearchClient.SUPPORTED_FORMATS)}")
        return 0, 0

    print(f"📂 Найдено документов: {len(documents)}")
    print(f"🗄️  File Search Store: {settings.file_search_store_name}")
    
    if dry_run:
        print("\n🔍 Режим предпросмотра (--dry-run):\n")
    else:
        print("\n⏳ Загрузка документов...\n")
        # Ensure store exists
        await client.ensure_store_exists()

    success_count = 0
    error_count = 0

    for doc_path in documents:
        relative_path = doc_path.relative_to(docs_dir)
        
        # Try to get item_id from metadata file first
        metadata = load_metadata_file(doc_path)
        item_id = None
        
        if metadata:
            item_id = metadata.pop("item_id", None)
        else:
            # Try to extract from filename
            item_id = extract_item_id_from_filename(doc_path.name)
            metadata = {}

        # Determine document type
        doc_type = "📦 item-specific" if item_id else "📚 general"
        item_info = f"item_id={item_id}" if item_id else "no item_id"

        if dry_run:
            print(f"  {doc_type}: {relative_path} ({item_info})")
            success_count += 1
            continue

        try:
            doc_id = await client.upload_document(
                file_path=doc_path,
                item_id=item_id,
                metadata=metadata if metadata else None,
            )
            print(f"  ✅ {relative_path} ({item_info})")
            success_count += 1
            
        except Exception as e:
            print(f"  ❌ {relative_path}: {e}")
            error_count += 1

    return success_count, error_count


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Синхронизация документов в Google Gemini File Search Store",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python scripts/sync_filesearch.py
  python scripts/sync_filesearch.py --docs-dir ./my_docs
  python scripts/sync_filesearch.py --dry-run

Соглашения об именовании файлов:
  item_12345.txt          -> item_id = "12345" (товар-специфичный)
  item_12345_desc.md      -> item_id = "12345" (товар-специфичный)
  faq.txt                 -> общий документ
  delivery_terms.md       -> общий документ

Метаданные через .meta.json:
  docs/product.txt
  docs/product.txt.meta.json  -> {"item_id": "12345"}
        """
    )
    
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("docs"),
        help="Директория с документами (по умолчанию: docs/)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать, что будет загружено, без фактической загрузки"
    )

    args = parser.parse_args()

    print("\n🚀 Avito AI Auto-Responder - Синхронизация File Search\n")
    print("=" * 60)

    if not args.docs_dir.exists():
        print(f"❌ Директория не найдена: {args.docs_dir}")
        print(f"\nСоздайте директорию и добавьте документы:")
        print(f"  mkdir -p {args.docs_dir}")
        sys.exit(1)

    success, errors = asyncio.run(sync_documents(args.docs_dir, args.dry_run))

    print("\n" + "=" * 60)
    print(f"📊 Результат: {success} успешно, {errors} ошибок")
    
    if not args.dry_run and success > 0:
        print("""
📋 Следующие шаги:
1. Проверьте загруженные документы в Google AI Studio
2. Протестируйте поиск через API
3. Отправьте тестовое сообщение в Avito чат
        """)

    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
