"""Cascading retrieval strategy for RAG operations."""

import logging
from typing import Literal, Optional

from pydantic import BaseModel

from app.rag.file_search_client import FileSearchClient, RetrievedChunk

logger = logging.getLogger(__name__)


class RetrievalResult(BaseModel):
    """Result of cascading retrieval operation."""

    found: bool
    chunks: list[RetrievedChunk]
    search_strategy: Literal["item_specific", "general", "cascaded"]


class CascadingRetrieval:
    """Implements cascading search strategy for RAG.
    
    Search strategy:
    1. If item_id is provided, first search in item-specific documents
    2. If no results found (or no item_id), search in general documents
    3. Return combined results with strategy indicator
    """

    def __init__(self, file_search_client: FileSearchClient):
        """Initialize cascading retrieval.
        
        Args:
            file_search_client: The File Search client to use for queries
        """
        self.file_search_client = file_search_client

    async def retrieve(
        self,
        query: str,
        item_id: Optional[str] = None
    ) -> RetrievalResult:
        """Perform cascading retrieval for a query.
        
        Args:
            query: The search query text
            item_id: Optional item ID for product-specific search
            
        Returns:
            RetrievalResult with found status, chunks, and strategy used.
        """
        # If no item_id, search only in general documents
        if not item_id:
            logger.info(f"No item_id provided, searching general documents only")
            result = await self.file_search_client.search(query, item_id=None)
            return RetrievalResult(
                found=result.found,
                chunks=result.chunks,
                search_strategy="general"
            )

        # Step 1: Search in item-specific documents
        logger.info(f"Searching item-specific documents for item_id={item_id}")
        item_result = await self.file_search_client.search(query, item_id=item_id)

        if item_result.found and item_result.chunks:
            logger.info(
                f"Found {len(item_result.chunks)} chunks in item-specific docs"
            )
            return RetrievalResult(
                found=True,
                chunks=item_result.chunks,
                search_strategy="item_specific"
            )

        # Step 2: Cascade to general documents
        logger.info(
            f"No item-specific results, cascading to general documents"
        )
        general_result = await self.file_search_client.search(query, item_id=None)

        if general_result.found and general_result.chunks:
            logger.info(
                f"Found {len(general_result.chunks)} chunks in general docs"
            )
            return RetrievalResult(
                found=True,
                chunks=general_result.chunks,
                search_strategy="cascaded"
            )

        # No results found anywhere
        logger.info("No results found in any documents")
        return RetrievalResult(
            found=False,
            chunks=[],
            search_strategy="cascaded"
        )
