"""Real-service prerequisite. Full E5→Qdrant→LTR test is in test_search_loop.py."""

import pytest


@pytest.mark.integration
def test_local_qdrant_is_reachable():
    from qdrant_client import QdrantClient

    client = QdrantClient(url="http://127.0.0.1:6333", timeout=3)
    try:
        assert client.get_collections() is not None
    finally:
        client.close()
