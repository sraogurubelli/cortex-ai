"""
Base storage abstraction for document file storage.

Provides abstract interface for file storage backends (filesystem, S3, etc.).
"""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


@dataclass
class StorageResult:
    """
    Result of file storage operation.

    Attributes:
        success: Whether storage operation succeeded
        file_url: URL or path to stored file
        file_hash: SHA256 hash of file content
        file_size: Size of file in bytes
    """

    success: bool
    file_url: str
    file_hash: str
    file_size: int


class BaseStorage(ABC):
    """
    Abstract base class for file storage backends.

    Implementations:
    - FilesystemStorage: Local filesystem storage
    - S3Storage: AWS S3 storage
    """

    @abstractmethod
    async def store_file(
        self,
        file_content: bytes,
        filename: str,
        organization_id: int,
    ) -> StorageResult:
        """
        Store file and return storage metadata.

        Args:
            file_content: File content as bytes
            filename: Original filename
            organization_id: Organization ID for scoping

        Returns:
            StorageResult with file URL, hash, and size

        Raises:
            ValueError: If file is invalid or too large
            OSError: If storage operation fails
        """
        pass

    @abstractmethod
    async def retrieve_file(self, file_path: str) -> bytes:
        """
        Retrieve file content by path.

        Args:
            file_path: File path or URL returned from store_file()

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file does not exist
            OSError: If retrieval fails
        """
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """
        Delete file from storage.

        Args:
            file_path: File path or URL

        Returns:
            True if deleted, False if not found

        Raises:
            OSError: If deletion fails
        """
        pass

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists in storage.

        Args:
            file_path: File path or URL

        Returns:
            True if file exists, False otherwise
        """
        pass

    def calculate_file_hash(self, content: bytes) -> str:
        """
        Calculate SHA256 hash of file content.

        Args:
            content: File content as bytes

        Returns:
            Hex-encoded SHA256 hash
        """
        return hashlib.sha256(content).hexdigest()

    def validate_filename(self, filename: str) -> None:
        """
        Validate filename for security.

        Args:
            filename: Filename to validate

        Raises:
            ValueError: If filename is invalid
        """
        # Check for directory traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise ValueError(f"Invalid filename: {filename}")

        # Check for suspicious extensions
        suspicious_exts = [".exe", ".bat", ".cmd", ".sh", ".ps1"]
        if any(filename.lower().endswith(ext) for ext in suspicious_exts):
            raise ValueError(f"Suspicious file extension: {filename}")

        # Check length
        if len(filename) > 255:
            raise ValueError("Filename too long (max 255 chars)")

    def validate_file_size(self, size: int, max_size: int = 100 * 1024 * 1024) -> None:
        """
        Validate file size.

        Args:
            size: File size in bytes
            max_size: Maximum allowed size (default: 100 MB)

        Raises:
            ValueError: If file is too large
        """
        if size > max_size:
            raise ValueError(f"File too large: {size} bytes (max: {max_size})")

    def generate_storage_path(
        self,
        organization_id: int,
        file_hash: str,
        filename: str,
    ) -> str:
        """
        Generate storage path for file.

        Uses pattern: org_{org_id}/{hash}_{filename}

        Args:
            organization_id: Organization ID
            file_hash: SHA256 hash of file
            filename: Original filename

        Returns:
            Storage path (relative or S3 key)
        """
        return f"org_{organization_id}/{file_hash}_{filename}"
