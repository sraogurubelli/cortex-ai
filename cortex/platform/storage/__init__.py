"""
Storage abstraction for document files.

Provides multiple backend implementations:
- FilesystemStorage: Local filesystem
- S3Storage: AWS S3

Usage:
    from cortex.platform.storage import FilesystemStorage, StorageResult

    storage = FilesystemStorage(base_path="./uploads")
    result = await storage.store_file(file_content, "doc.pdf", org_id=1)
    print(result.file_url, result.file_hash)
"""

from cortex.platform.storage.base_storage import BaseStorage, StorageResult
from cortex.platform.storage.filesystem_storage import FilesystemStorage

# S3Storage requires boto3 (optional dependency)
try:
    from cortex.platform.storage.s3_storage import S3Storage
except ImportError:
    S3Storage = None  # type: ignore

__all__ = [
    "BaseStorage",
    "StorageResult",
    "FilesystemStorage",
    "S3Storage",
]
