"""
Local filesystem storage implementation.

Stores files in a local directory structure organized by organization.
"""

import logging
import os
from pathlib import Path

from cortex.platform.storage.base_storage import BaseStorage, StorageResult

logger = logging.getLogger(__name__)


class FilesystemStorage(BaseStorage):
    """
    Local filesystem storage backend.

    Stores files in directory structure:
    {base_path}/org_{org_id}/{hash}_{filename}

    Example:
        ./uploads/org_1/abc123_document.pdf
    """

    def __init__(self, base_path: str = "./uploads"):
        """
        Initialize filesystem storage.

        Args:
            base_path: Base directory for file storage (default: ./uploads)
        """
        self.base_path = Path(base_path)

        # Create base directory if it doesn't exist
        self.base_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"FilesystemStorage initialized at: {self.base_path.absolute()}")

    async def store_file(
        self,
        file_content: bytes,
        filename: str,
        organization_id: int,
    ) -> StorageResult:
        """
        Store file in local filesystem.

        Args:
            file_content: File content as bytes
            filename: Original filename
            organization_id: Organization ID

        Returns:
            StorageResult with local file path

        Raises:
            ValueError: If file is invalid
            OSError: If write fails
        """
        # Validate inputs
        self.validate_filename(filename)
        self.validate_file_size(len(file_content))

        # Calculate file hash
        file_hash = self.calculate_file_hash(file_content)

        # Create organization directory
        org_dir = self.base_path / f"org_{organization_id}"
        org_dir.mkdir(parents=True, exist_ok=True)

        # Generate storage path
        storage_path = self.generate_storage_path(organization_id, file_hash, filename)
        full_path = self.base_path / storage_path

        # Write file
        try:
            full_path.write_bytes(file_content)
            logger.info(f"Stored file: {full_path}")

            return StorageResult(
                success=True,
                file_url=str(full_path),
                file_hash=file_hash,
                file_size=len(file_content),
            )

        except OSError as e:
            logger.error(f"Failed to write file {full_path}: {e}")
            raise

    async def retrieve_file(self, file_path: str) -> bytes:
        """
        Retrieve file content from filesystem.

        Args:
            file_path: Local file path

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file does not exist
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            content = path.read_bytes()
            logger.debug(f"Retrieved file: {file_path} ({len(content)} bytes)")
            return content

        except OSError as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            raise

    async def delete_file(self, file_path: str) -> bool:
        """
        Delete file from filesystem.

        Args:
            file_path: Local file path

        Returns:
            True if deleted, False if not found
        """
        path = Path(file_path)

        if not path.exists():
            logger.debug(f"File not found for deletion: {file_path}")
            return False

        try:
            path.unlink()
            logger.info(f"Deleted file: {file_path}")
            return True

        except OSError as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            raise

    async def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists.

        Args:
            file_path: Local file path

        Returns:
            True if file exists
        """
        return Path(file_path).exists()

    def get_storage_stats(self) -> dict[str, int]:
        """
        Get storage statistics.

        Returns:
            Dict with total_files and total_size_bytes
        """
        total_files = 0
        total_size = 0

        for root, dirs, files in os.walk(self.base_path):
            for file in files:
                total_files += 1
                file_path = Path(root) / file
                total_size += file_path.stat().st_size

        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
        }
