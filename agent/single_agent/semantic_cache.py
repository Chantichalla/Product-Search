"""
Semantic Cache Module
---------------------
Handles semantic caching using Redis Vector Search and ONNX Embeddings.
Implements:
1. Vector Embeddings (all-MiniLM-L6-v2 via ONNX Runtime, 384-dim)
2. Hybrid Search (Keyword pre-filter + Vector similarity)
3. Content-based TTL assignment
4. Smart storage (caching structured data, not raw HTML)
"""

import json
import time
import numpy as np
from typing import Dict, List, Optional, Any, Union
from redis.commands.search.field import VectorField, TagField, TextField
from redis.commands.search.query import Query
try:
    from redis.commands.search.indexDefinition import IndexDefinition, IndexType
except ImportError:
    # Handle both CamelCase and snake_case in different redis-py versions
    from redis.commands.search.index_definition import IndexDefinition, IndexType
from config.ollama_embeddings import get_embedding_bytes, EMBEDDING_DIMENSION

# Import existing redis connection and TTLs
from cache.redis_cache import redis_client, is_connected, redis_cache

class SemanticCache:
    def __init__(self, index_name: str = "semantic_search_idx"):
        self.index_name = index_name
        self.client = redis_client
        self.DIMENSION = EMBEDDING_DIMENSION  # 768 for nomic-embed-text
        
        if is_connected:
            self._initialize_index()

    def _initialize_index(self):
        """Create Redis Search index if it doesn't exist."""
        try:
            self.client.ft(self.index_name).info()
            # print(f"[SemanticCache] Index '{self.index_name}' already exists.")
        except Exception:
            print(f"[SemanticCache] Creating index '{self.index_name}'...")
            
            # Define schema
            schema = (
                TextField("query_text"),             # Original query (for exact match fallback)
                TagField("query_type"),              # To filter by type (price vs spec)
                VectorField(
                    "embedding",
                    "HNSW", {
                        "TYPE": "FLOAT32",
                        "DIM": self.DIMENSION,
                        "DISTANCE_METRIC": "COSINE"
                    }
                )
            )
            
            # Create index
            definition = IndexDefinition(prefix=["semantic:"], index_type=IndexType.HASH)
            self.client.ft(self.index_name).create_index(schema, definition=definition)
            print("[SemanticCache] Index created successfully.")

    def _get_embedding(self, text: str) -> bytes:
        """Generate vector embedding for text via Ollama."""
        return get_embedding_bytes(text)

    def _get_smart_ttl(self, query_type: str) -> int:
        """Get TTL based on centralized configuration in redis_cache."""
        return redis_cache.get_ttl_for_type(query_type)

    def search(self, query: str, query_type: str, threshold: float = 0.90) -> Optional[Dict]:
        """
        Search for semantically similar cached results.
        
        Args:
            query: User's search query
            query_type: Type of query (used for filtering)
            threshold: Similarity threshold (0.0 to 1.0)
        """
        if not is_connected:
            return None

        try:
            # 1. Generate embedding
            query_vector = self._get_embedding(query)
            
            # 2. Build Query
            # Combine vector search with tag filter (if query_type is strictly relevant)
            # Currently strict filtering might reduce recall, so we use it as a hint or post-filter
            # For now, pure vector search is safer for cross-type hits
            
            # KNNSearch syntax: "*=>[KNN 1 @embedding $vec AS score]"
            q = Query(f"(@query_type:{{{query_type}}})=>[KNN 1 @embedding $vec AS score]")\
                .sort_by("score")\
                .return_fields("score", "response_json", "query_text")\
                .dialect(2)
            
            params = {"vec": query_vector}
            
            # 3. Execute Search
            results = self.client.ft(self.index_name).search(q, query_params=params)
            
            if results.docs:
                top_hit = results.docs[0]
                similarity = 1 - float(top_hit.score)  # Redis returns distance (0=identical)
                
                # print(f"[SemanticCache] Best match: '{top_hit.query_text}' (Sim: {similarity:.2f})")
                
                if similarity >= threshold:
                    print(f"[SemanticCache] 🎯 HIT! Matched '{top_hit.query_text}' ({similarity:.2f})")
                    return json.loads(top_hit.response_json)
                else:
                    print(f"[SemanticCache] Miss (Best match {similarity:.2f} < {threshold})")
            
            return None

        except Exception as e:
            print(f"[SemanticCache] Search error: {e}")
            return None

    def cache_result(self, query: str, query_type: str, result_data: Dict):
        """
        Cache a new result with semantic vector.
        """
        if not is_connected:
            return

        try:
            # 1. Generate embedding
            vector = self._get_embedding(query)
            
            # 2. Prepare Key and TTL
            # Use a hash of the query text for the key ID, but prefix with "semantic:"
            import hashlib
            query_hash = hashlib.md5(query.encode()).hexdigest()
            key = f"semantic:{query_hash}"
            
            ttl = self._get_smart_ttl(query_type)
            
            # 3. Store in Redis (Hash)
            # We strictly limit what we store. NO RAW HTML.
            # If result_data has "raw_search_results", we allow it but stripped? 
            # ideally we only cache the FINAL PROCESSED ANSWER or structured product list.
            
            # For now, we cache the whole result_data dict but warn about size
            json_str = json.dumps(result_data)
            
            self.client.hset(key, mapping={
                "query_text": query,
                "query_type": query_type,
                "embedding": vector,
                "response_json": json_str
            })
            
            # Set TTL
            self.client.expire(key, ttl)
            print(f"[SemanticCache] 💾 Cached '{query[:30]}...' (TTL: {ttl}s)")
            
        except Exception as e:
            print(f"[SemanticCache] Cache write error: {e}")

# Global instance
semantic_cache = SemanticCache()
