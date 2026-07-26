import os
import logging
from pymilvus import MilvusClient, DataType

logger = logging.getLogger(__name__)

VECTOR_DIM = 768

class VectorStoreManager:
    def __init__(self):
        self.behavior_col_name = "behavior_vectors"
        uri = os.getenv("MILVUS_URI", "http://localhost:19530")
        self.client = MilvusClient(uri=uri, secure=False)
        logger.info("MilvusClient initialized at %s", uri)
        self._ensure_collections()

    def _ensure_collections(self):
        """Creates collection and HNSW index if not exists."""
        if not self.client.has_collection(self.behavior_col_name):
            schema = {
                "fields": [
                    {"name": "id", "dtype": DataType.VARCHAR, "is_primary": True, "max_length": 255},
                    {"name": "merchant_name", "dtype": DataType.VARCHAR, "max_length": 255},
                    {"name": "embedding", "dtype": DataType.FLOAT_VECTOR, "dim": VECTOR_DIM},
                ],
                "description": "Semantic embeddings of merchant behaviors"
            }
            self.client.create_collection(self.behavior_col_name, schema)
            logger.info("Created Milvus collection: %s", self.behavior_col_name)

            index_params = {
                "metric_type": "COSINE",
                "index_type": "HNSW",
                "params": {"M": 8, "efConstruction": 200}
            }
            self.client.create_index(self.behavior_col_name, "embedding", index_params)
            logger.info("Created HNSW index on embedding field")

        # Load collection into memory
        self.client.load_collection(self.behavior_col_name)

    def insert_behavior_vector(self, pattern_id: str, merchant_name: str, vector: list[float]):
        """Insert or overwrite a vector in Milvus."""
        data = [
            {"id": pattern_id, "merchant_name": merchant_name, "embedding": vector}
        ]
        self.client.upsert(self.behavior_col_name, data)
        logger.info("Inserted vector for entity: %s", merchant_name)

vector_store = VectorStoreManager()
