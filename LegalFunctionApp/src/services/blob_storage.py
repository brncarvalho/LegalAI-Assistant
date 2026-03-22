"""
Azure Blob Storage service wrapper.

Why a class?
BlobServiceClient.from_connection_string(settings.azure_web_jobs_storage)
appeared 5 times in function_app.py — each time creating a new connection
from the same connection string. This class:

1. Holds the connection once (shared state = class)
2. Exposes domain-specific methods (download_json, upload_json, upload_file)
   instead of repeating container/blob boilerplate
3. Makes the code in function_app.py read like business logic, not Azure SDK calls
"""

import json

from azure.storage.blob import BlobServiceClient


class BlobStorageService:
    """
    Simplified interface to Azure Blob Storage for the Norma pipeline.

    Usage:
        storage = BlobStorageService(connection_string)
        data = storage.download_json("output", "contract.json")
        storage.upload_json("reviewed-clauses", "result.json", data)
    """

    def __init__(self, connection_string: str):
        self._client = BlobServiceClient.from_connection_string(connection_string)

    def download_blob_bytes(self, container_name: str, blob_name: str) -> bytes:
        """Download a blob and return its raw bytes."""
        container = self._client.get_container_client(container_name)
        return container.download_blob(blob_name).readall()

    def download_json(self, container_name: str, blob_name: str):
        """Download a JSON blob and parse it into a Python object."""
        data = self.download_blob_bytes(container_name, blob_name)
        return json.loads(data)

    def upload_json(self, container_name: str, blob_name: str, data) -> None:
        """Serialize data as JSON and upload to a blob."""
        container = self._client.get_container_client(container_name)
        container.upload_blob(
            name=blob_name,
            data=json.dumps(data, ensure_ascii=False),
            overwrite=True,
        )

    def upload_file(self, container_name: str, blob_name: str, file_path: str) -> None:
        """Upload a local file to a blob."""
        container = self._client.get_container_client(container_name)
        with open(file_path, "rb") as f:
            container.upload_blob(name=blob_name, data=f, overwrite=True)
