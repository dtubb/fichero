"""
Search Service for Fichero Library

Provides full-text search using SQLite FTS5 with BM25 ranking, plus structured
metadata filtering and faceted search.
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result"""
    metadata_id: str
    collection_id: str
    item_id: Optional[str]
    schema_type: str
    source_label: str
    version: int
    content: str
    rank: float  # BM25 rank (lower is better)
    snippet: Optional[str] = None  # Highlighted snippet


@dataclass
class SearchResponse:
    """Complete search response with results and metadata"""
    results: List[SearchResult] = field(default_factory=list)
    total_count: int = 0
    query: str = ""
    took_ms: float = 0.0
    facets: Dict[str, Dict[str, int]] = field(default_factory=dict)


class SearchService:
    """Full-text search service using SQLite FTS5"""

    def __init__(self, db_path: Path):
        """Initialize search service

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path

    def search(self,
               query: str,
               collection_ids: List[str] = None,
               schema_types: List[str] = None,
               source_labels: List[str] = None,
               metadata_filters: Dict[str, Any] = None,
               limit: int = 20,
               offset: int = 0,
               include_snippets: bool = True) -> SearchResponse:
        """
        Perform full-text search with BM25 ranking and metadata filtering

        Args:
            query: Search query (supports FTS5 syntax)
            collection_ids: Filter by collection IDs
            schema_types: Filter by schema types
            source_labels: Filter by source labels
            metadata_filters: Filter by metadata fields (e.g., {"language": "es", "confidence": ">0.8"})
            limit: Maximum results to return
            offset: Offset for pagination
            include_snippets: Whether to include highlighted snippets

        Returns:
            SearchResponse with ranked results

        Query Examples:
            - Simple: "John Smith"
            - Phrase: "\"John Smith\""
            - Boolean: "John AND Smith"
            - Prefix: "archiv*"
            - Exclude: "document NOT draft"

        Metadata Filter Examples:
            - Exact match: {"language": "es"}
            - Comparison: {"confidence": ">=0.8"}
            - Multiple: {"language": "es", "word_count": ">100"}
        """
        import time
        start_time = time.time()

        response = SearchResponse(query=query)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Build FTS5 query
                fts_query = self._build_fts_query(query)

                # Build WHERE clause for filters
                where_clauses = []
                params = [fts_query]

                # Add metadata join if we need to filter by metadata fields
                needs_metadata_join = metadata_filters is not None and len(metadata_filters) > 0

                if collection_ids:
                    placeholders = ','.join('?' * len(collection_ids))
                    where_clauses.append(f"si.collection_id IN ({placeholders})")
                    params.extend(collection_ids)

                if schema_types:
                    placeholders = ','.join('?' * len(schema_types))
                    where_clauses.append(f"si.schema_type IN ({placeholders})")
                    params.extend(schema_types)

                if source_labels:
                    placeholders = ','.join('?' * len(source_labels))
                    where_clauses.append(f"si.source_label IN ({placeholders})")
                    params.extend(source_labels)

                # Add metadata field filters
                if needs_metadata_join:
                    metadata_clauses, metadata_params = self._build_metadata_filters(metadata_filters)
                    where_clauses.extend(metadata_clauses)
                    params.extend(metadata_params)

                where_sql = " AND " + " AND ".join(where_clauses) if where_clauses else ""

                # Build FROM clause with optional metadata join
                if needs_metadata_join:
                    from_sql = """
                        search_index si
                        INNER JOIN extracted_metadata em ON si.metadata_id = em.id
                    """
                else:
                    from_sql = "search_index si"

                # Get total count (without limit/offset)
                count_sql = f"""
                    SELECT COUNT(*)
                    FROM {from_sql}
                    WHERE si.content MATCH ?{where_sql}
                """
                cursor.execute(count_sql, params)
                response.total_count = cursor.fetchone()[0]

                # Get ranked results with BM25 scoring
                # FTS5 rank is negative (better matches are more negative)
                results_sql = f"""
                    SELECT
                        si.metadata_id,
                        si.collection_id,
                        si.item_id,
                        si.schema_type,
                        si.source_label,
                        si.version,
                        si.content,
                        si.rank
                    FROM {from_sql}
                    WHERE si.content MATCH ?{where_sql}
                    ORDER BY si.rank
                    LIMIT ? OFFSET ?
                """

                cursor.execute(results_sql, params + [limit, offset])

                for row in cursor.fetchall():
                    result = SearchResult(
                        metadata_id=row[0],
                        collection_id=row[1],
                        item_id=row[2],
                        schema_type=row[3],
                        source_label=row[4],
                        version=row[5],
                        content=row[6],
                        rank=row[7]
                    )

                    # Generate snippet if requested
                    if include_snippets:
                        result.snippet = self._generate_snippet(
                            row[6], query, max_length=200
                        )

                    response.results.append(result)

        except Exception as e:
            logger.error(f"Search failed: {e}")

        response.took_ms = (time.time() - start_time) * 1000
        return response

    def search_facets(self,
                     query: str,
                     collection_ids: List[str] = None,
                     facet_fields: List[str] = None) -> Dict[str, Dict[str, int]]:
        """
        Get facet counts for search results

        Args:
            query: Search query
            collection_ids: Filter by collection IDs
            facet_fields: Fields to facet on (schema_type, source_label, collection_id)

        Returns:
            Dict mapping facet field to value counts
        """
        facets = {}
        if not facet_fields:
            facet_fields = ['schema_type', 'source_label']

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                fts_query = self._build_fts_query(query)

                where_clauses = []
                params = [fts_query]

                if collection_ids:
                    placeholders = ','.join('?' * len(collection_ids))
                    where_clauses.append(f"collection_id IN ({placeholders})")
                    params.extend(collection_ids)

                where_sql = " AND " + " AND ".join(where_clauses) if where_clauses else ""

                for facet_field in facet_fields:
                    sql = f"""
                        SELECT {facet_field}, COUNT(*) as count
                        FROM search_index
                        WHERE content MATCH ?{where_sql}
                        GROUP BY {facet_field}
                        ORDER BY count DESC
                    """
                    cursor.execute(sql, params)
                    facets[facet_field] = dict(cursor.fetchall())

        except Exception as e:
            logger.error(f"Facet search failed: {e}")

        return facets

    def _build_fts_query(self, query: str) -> str:
        """
        Build FTS5 query from user query

        Handles:
        - Phrase queries: "exact phrase"
        - Boolean: AND, OR, NOT
        - Prefix: term*
        - Column filters: schema_type:transcription

        Args:
            query: User query string

        Returns:
            FTS5-formatted query
        """
        # FTS5 uses AND by default, so just pass through
        # Users can use: AND, OR, NOT, "phrase", term*
        return query.strip()

    def _generate_snippet(self, content: str, query: str, max_length: int = 200) -> str:
        """
        Generate highlighted snippet from content

        Args:
            content: Full content text
            query: Search query
            max_length: Maximum snippet length

        Returns:
            Snippet with query terms highlighted
        """
        # Simple implementation - find first occurrence of query term
        # and return surrounding context
        query_terms = query.lower().replace('"', '').split()
        content_lower = content.lower()

        # Find first term position
        positions = []
        for term in query_terms:
            term_clean = term.rstrip('*').strip()
            if not term_clean:
                continue
            pos = content_lower.find(term_clean)
            if pos >= 0:
                positions.append(pos)

        if not positions:
            # No match found, return start of content
            return content[:max_length] + ('...' if len(content) > max_length else '')

        # Use earliest match position
        match_pos = min(positions)

        # Calculate snippet bounds
        context_before = 80
        context_after = max_length - context_before

        start = max(0, match_pos - context_before)
        end = min(len(content), match_pos + context_after)

        snippet = content[start:end]

        # Add ellipsis if truncated
        if start > 0:
            snippet = '...' + snippet
        if end < len(content):
            snippet = snippet + '...'

        # Simple highlighting (wrap matches in **term**)
        for term in query_terms:
            term_clean = term.rstrip('*').strip()
            if not term_clean:
                continue
            # Case-insensitive replace
            import re
            pattern = re.compile(re.escape(term_clean), re.IGNORECASE)
            snippet = pattern.sub(lambda m: f"**{m.group()}**", snippet)

        return snippet

    def suggest_completions(self, prefix: str, limit: int = 10) -> List[str]:
        """
        Suggest query completions based on indexed content

        Args:
            prefix: Query prefix to complete
            limit: Maximum suggestions

        Returns:
            List of suggested completions
        """
        suggestions = []

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Use FTS5 prefix query
                cursor.execute("""
                    SELECT DISTINCT content
                    FROM search_index
                    WHERE content MATCH ?
                    LIMIT ?
                """, (f"{prefix}*", limit))

                # Extract words starting with prefix
                import re
                for row in cursor.fetchall():
                    words = re.findall(r'\b\w+\b', row[0].lower())
                    for word in words:
                        if word.startswith(prefix.lower()) and word not in suggestions:
                            suggestions.append(word)
                            if len(suggestions) >= limit:
                                return suggestions

        except Exception as e:
            logger.error(f"Suggestion failed: {e}")

        return suggestions

    def _build_metadata_filters(self, metadata_filters: Dict[str, Any]) -> Tuple[List[str], List[Any]]:
        """
        Build SQL WHERE clauses for metadata field filtering

        Supports operators:
        - Exact match: {"language": "es"}
        - Greater than: {"confidence": ">0.8"} or {"confidence": ">=0.8"}
        - Less than: {"word_count": "<100"} or {"word_count": "<=100"}
        - Not equal: {"status": "!=failed"}
        - In list: {"language": ["es", "en", "fr"]}

        Args:
            metadata_filters: Dict of field name to filter value

        Returns:
            Tuple of (where_clauses, params)
        """
        where_clauses = []
        params = []

        for field_name, filter_value in metadata_filters.items():
            # Handle list values (IN operator)
            if isinstance(filter_value, list):
                placeholders = ','.join('?' * len(filter_value))
                # Need to subquery to find metadata with matching key and value
                where_clauses.append(f"""
                    si.metadata_id IN (
                        SELECT id FROM extracted_metadata
                        WHERE key = ? AND value IN ({placeholders})
                    )
                """)
                params.append(field_name)
                params.extend([str(v) for v in filter_value])
                continue

            # Parse operator from string value
            operator = "="
            value = filter_value

            if isinstance(filter_value, str):
                # Check for operator prefix
                if filter_value.startswith(">="):
                    operator = ">="
                    value = filter_value[2:].strip()
                elif filter_value.startswith("<="):
                    operator = "<="
                    value = filter_value[2:].strip()
                elif filter_value.startswith("!="):
                    operator = "!="
                    value = filter_value[2:].strip()
                elif filter_value.startswith(">"):
                    operator = ">"
                    value = filter_value[1:].strip()
                elif filter_value.startswith("<"):
                    operator = "<"
                    value = filter_value[1:].strip()

            # For numeric comparisons, try to convert value
            if operator in [">", ">=", "<", "<="]:
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    pass  # Keep as string

            # Build subquery for this field
            where_clauses.append(f"""
                si.metadata_id IN (
                    SELECT id FROM extracted_metadata
                    WHERE key = ? AND CAST(value AS REAL) {operator} ?
                )
            """)
            params.append(field_name)
            params.append(value)

        return where_clauses, params
