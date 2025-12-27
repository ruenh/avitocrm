"""Google Gemini File Search client for RAG operations."""

import logging
from pathlib import Path
from typing import Optional

import google.generativeai as genai
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RetrievedChunk(BaseModel):
    """Represents a retrieved chunk from File Search."""

    text: str
    source_file: str
    relevance_score: float
    metadata: dict


class SearchResult(BaseModel):
    """Result of a File Search query."""

    found: bool
    chunks: list[RetrievedChunk]


class FileSearchClient:
    """Client for Google Gemini File Search API.
    
    Handles document upload, store management, and semantic search
    with optional item_id filtering for product-specific queries.
    """

    SUPPORTED_FORMATS = {".txt", ".docx", ".pdf", ".md", ".json"}

    def __init__(self, api_key: str, store_name: str):
        """Initialize the File Search client.
        
        Args:
            api_key: Google Gemini API key
            store_name: Name of the File Search Store to use/create
        """
        self.api_key = api_key
        self.store_name = store_name
        self._store_id: Optional[str] = None
        
        # Configure the Gemini API
        genai.configure(api_key=api_key)

    async def ensure_store_exists(self) -> str:
        """Create or get existing File Search Store.
        
        Returns:
            The store ID (corpus name) for the File Search Store.
        """
        if self._store_id:
            return self._store_id

        try:
            # List existing corpora to find our store
            corpora = list(genai.list_corpora())
            
            for corpus in corpora:
                if corpus.display_name == self.store_name:
                    self._store_id = corpus.name
                    logger.info(f"Found existing File Search Store: {self._store_id}")
                    return self._store_id

            # Create new corpus if not found
            corpus = genai.create_corpus(display_name=self.store_name)
            self._store_id = corpus.name
            logger.info(f"Created new File Search Store: {self._store_id}")
            return self._store_id

        except Exception as e:
            logger.error(f"Error ensuring store exists: {e}")
            raise

    async def upload_document(
        self,
        file_path: Path,
        item_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> str:
        """Upload a document to the File Search Store.
        
        Args:
            file_path: Path to the document file
            item_id: Optional item ID for product-specific documents
            metadata: Optional additional metadata
            
        Returns:
            The document ID in the store.
            
        Raises:
            ValueError: If file format is not supported
            FileNotFoundError: If file does not exist
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported file format: {suffix}. "
                f"Supported: {self.SUPPORTED_FORMATS}"
            )

        # Ensure store exists
        store_id = await self.ensure_store_exists()

        try:
            # Build custom metadata
            custom_metadata = metadata.copy() if metadata else {}
            if item_id:
                custom_metadata["item_id"] = item_id
            else:
                custom_metadata["is_general"] = "true"

            # Create document in corpus
            document = genai.create_document(
                corpus=store_id,
                display_name=file_path.name,
                custom_metadata=[
                    genai.protos.CustomMetadata(key=k, string_value=str(v))
                    for k, v in custom_metadata.items()
                ]
            )

            # Upload file content as chunks
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Create chunk with the document content
            genai.create_chunk(
                document=document.name,
                data=genai.protos.ChunkData(string_value=content)
            )

            logger.info(
                f"Uploaded document: {file_path.name} "
                f"(item_id={item_id}, doc_id={document.name})"
            )
            return document.name

        except Exception as e:
            logger.error(f"Error uploading document {file_path}: {e}")
            raise

    async def search(
        self,
        query: str,
        item_id: Optional[str] = None
    ) -> SearchResult:
        """Search in File Search Store with optional item_id filter.
        
        Args:
            query: The search query text
            item_id: Optional item ID to filter results
            
        Returns:
            SearchResult with found status and retrieved chunks.
        """
        try:
            store_id = await self.ensure_store_exists()

            # Build metadata filter if item_id provided
            metadata_filter = None
            if item_id:
                metadata_filter = [
                    genai.protos.MetadataFilter(
                        key="item_id",
                        conditions=[
                            genai.protos.Condition(
                                operation=genai.protos.Condition.Operator.EQUAL,
                                string_value=item_id
                            )
                        ]
                    )
                ]

            # Query the corpus
            results = genai.query_corpus(
                corpus=store_id,
                query=query,
                metadata_filters=metadata_filter,
                results_count=5
            )

            chunks = []
            for result in results:
                # Extract chunk data
                chunk_text = ""
                if hasattr(result, "chunk") and result.chunk:
                    if hasattr(result.chunk, "data"):
                        chunk_text = result.chunk.data.string_value or ""

                # Extract source file from document name
                source_file = "unknown"
                if hasattr(result, "chunk") and hasattr(result.chunk, "name"):
                    # Parse document name from chunk name
                    parts = result.chunk.name.split("/")
                    if len(parts) >= 4:
                        # Try to get document display name
                        source_file = parts[3] if len(parts) > 3 else "unknown"

                # Extract relevance score
                relevance = 0.0
                if hasattr(result, "relevance_score"):
                    relevance = float(result.relevance_score)

                # Extract metadata
                chunk_metadata = {}
                if hasattr(result.chunk, "custom_metadata"):
                    for meta in result.chunk.custom_metadata:
                        chunk_metadata[meta.key] = meta.string_value

                if chunk_text:
                    chunks.append(RetrievedChunk(
                        text=chunk_text,
                        source_file=source_file,
                        relevance_score=relevance,
                        metadata=chunk_metadata
                    ))

            found = len(chunks) > 0
            logger.info(
                f"Search query='{query[:50]}...' item_id={item_id} "
                f"found={found} chunks={len(chunks)}"
            )

            return SearchResult(found=found, chunks=chunks)

        except Exception as e:
            logger.error(f"Error searching: {e}")
            # Return empty result on error
            return SearchResult(found=False, chunks=[])
