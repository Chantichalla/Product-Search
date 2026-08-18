"""
Deep Memory Module (Vector Context)
-----------------------------------
Handles long-term conversational memory using Redis Vector Search.
Stores every user/assistant interaction as a vector embedding.

Architecture:
- Index: `deep_memory_idx`
- Model: `all-MiniLM-L6-v2` via ONNX Runtime (384-dim, ~0.5s load, no Ollama)
- Storage: Redis Hash (content + metadata + embedding)
- Retrieval: K-Nearest Neighbors (KNN) semantic search

Note:
 Uses ONNX Runtime — no PyTorch, no HuggingFace pings after first download.
"""

import json
import time
import hashlib
import numpy as np
from typing import List, Dict, Optional
from redis.commands.search.field import VectorField, TagField, TextField, NumericField
from redis.commands.search.query import Query
try:
    from redis.commands.search.indexDefinition import IndexDefinition, IndexType
except ImportError:
    # Handle version differences in redis-py
    from redis.commands.search.index_definition import IndexDefinition, IndexType

from config.ollama_embeddings import get_embedding_bytes, EMBEDDING_DIMENSION

# Shared Redis connection
from cache.redis_cache import redis_client, is_connected

class DeepMemory:
    def __init__(self, index_name: str = "deep_memory_idx"):
        self.index_name = index_name
        self.client = redis_client
        self.DIMENSION = EMBEDDING_DIMENSION  # 768 for nomic-embed-text
        
        if is_connected:
            self._initialize_index()

    def _initialize_index(self):
        """Create Redis Search index for memory."""
        try:
            self.client.ft(self.index_name).info()
        except Exception:
            print(f"[DeepMemory] Creating index '{self.index_name}'...")
            schema = (
                TextField("content"),                # The raw text
                TagField("role"),                    # user vs assistant
                NumericField("timestamp"),           # Unix timestamp
                VectorField(
                    "embedding",
                    "HNSW", {
                        "TYPE": "FLOAT32",
                        "DIM": self.DIMENSION,
                        "DISTANCE_METRIC": "COSINE"
                    }
                )
            )
            definition = IndexDefinition(prefix=["mem:"], index_type=IndexType.HASH)
            self.client.ft(self.index_name).create_index(schema, definition=definition)
            print("[DeepMemory] Index created.")

    def _get_embedding(self, text: str) -> bytes:
        return get_embedding_bytes(text)

    def add_turn(self, role: str, content: str):
        """
        Store a conversation turn in vector memory.
        """
        if not is_connected or not content.strip():
            return

        try:
            vector = self._get_embedding(content)
            
            # Unique ID based on content hash + timestamp to allow duplicates if repeated later
            content_hash = hashlib.md5(content.encode()).hexdigest()
            timestamp = time.time()
            key = f"mem:{content_hash}:{int(timestamp)}"
            
            self.client.hset(key, mapping={
                "role": role,
                "content": content,
                "timestamp": timestamp,
                "embedding": vector
            })
            
            # 30 Day Retention for Memory (Adjust as needed)
            self.client.expire(key, 2592000) 
            # print(f"[DeepMemory] 🧠 Stored turn: {content[:30]}...")
            
        except Exception as e:
            print(f"[DeepMemory] Error adding turn: {e}")

    def search_context(self, query: str, k: int = 3, threshold: float = 0.5) -> List[Dict]:
        """
        Retrieve relevant past conversation turns.
        """
        if not is_connected:
            return []

        try:
            query_vector = self._get_embedding(query)
            
            q = Query(f"*=>[KNN {k} @embedding $vec AS score]")\
                .sort_by("score")\
                .return_fields("score", "content", "role", "timestamp")\
                .dialect(2)
            
            params = {"vec": query_vector}
            results = self.client.ft(self.index_name).search(q, query_params=params)
            
            memory_hits = []
            for doc in results.docs:
                similarity = 1 - float(doc.score)
                if similarity >= threshold:
                    memory_hits.append({
                        "role": doc.role,
                        "content": doc.content,
                        "timestamp": float(doc.timestamp),
                        "similarity": similarity
                    })
                    
            if memory_hits:
                print(f"[DeepMemory] ⚡ Retrieved {len(memory_hits)} context items")
                
            return memory_hits

        except Exception as e:
            print(f"[DeepMemory] Search error: {e}")
            return []

# Global Instance
deep_memory = DeepMemory()
