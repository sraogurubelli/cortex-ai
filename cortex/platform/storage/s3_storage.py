"""
AWS S3 storage implementation.

Stores files in S3 bucket organized by organization.
"""

import logging
from typing import Any

from cortex.platform.storage.base_storage import BaseStorage, StorageResult

logger = logging.getLogger(__name__)

# Optional S3 dependency
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    logger.warning("boto3 not installed. Install with: pip install boto3")


class S3Storage(BaseStorage):
    """
    AWS S3 storage backend.

    Stores files in S3 bucket with key structure:
    org_{org_id}/{hash}_{filename}

    Example:
        s3://my-bucket/org_1/abc123_document.pdf
    """

    def __init__(
        self,
        bucket_name: str,
        region: str = "us-east-1",
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ):
        """
        Initialize S3 storage.

        Args:
            bucket_name: S3 bucket name
            region: AWS region (default: us-east-1)
            aws_access_key_id: AWS access key (or use env var AWS_ACCESS_KEY_ID)
            aws_secret_access_key: AWS secret key (or use env var AWS_SECRET_ACCESS_KEY)

        Raises:
            ImportError: If boto3 is not installed
        """
        if not S3_AVAILABLE:
            raise ImportError(
                "boto3 is required for S3Storage. Install with: pip install boto3"
            )

        self.bucket_name = bucket_name
        self.region = region

        # Initialize S3 client
        session_kwargs: dict[str, Any] = {"region_name": region}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs["aws_access_key_id"] = aws_access_key_id
            session_kwargs["aws_secret_access_key"] = aws_secret_access_key

        self.s3_client = boto3.client("s3", **session_kwargs)

        logger.info(f"S3Storage initialized for bucket: {bucket_name} ({region})")

    async def store_file(
        self,
        file_content: bytes,
        filename: str,
        organization_id: int,
    ) -> StorageResult:
        """
        Store file in S3.

        Args:
            file_content: File content as bytes
            filename: Original filename
            organization_id: Organization ID

        Returns:
            StorageResult with S3 URL

        Raises:
            ValueError: If file is invalid
            ClientError: If S3 upload fails
        """
        # Validate inputs
        self.validate_filename(filename)
        self.validate_file_size(len(file_content))

        # Calculate file hash
        file_hash = self.calculate_file_hash(file_content)

        # Generate S3 key
        s3_key = self.generate_storage_path(organization_id, file_hash, filename)

        # Upload to S3
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_content,
                ContentLength=len(file_content),
            )

            # Generate S3 URL
            file_url = f"s3://{self.bucket_name}/{s3_key}"

            logger.info(f"Stored file in S3: {file_url}")

            return StorageResult(
                success=True,
                file_url=file_url,
                file_hash=file_hash,
                file_size=len(file_content),
            )

        except NoCredentialsError as e:
            logger.error(f"AWS credentials not found: {e}")
            raise

        except ClientError as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise

    async def retrieve_file(self, file_path: str) -> bytes:
        """
        Retrieve file content from S3.

        Args:
            file_path: S3 URL (s3://bucket/key) or S3 key

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file does not exist
            ClientError: If download fails
        """
        # Parse S3 URL
        s3_key = self._parse_s3_url(file_path)

        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            content = response["Body"].read()

            logger.debug(f"Retrieved file from S3: {s3_key} ({len(content)} bytes)")
            return content

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found in S3: {s3_key}")
            else:
                logger.error(f"Failed to retrieve from S3: {e}")
                raise

    async def delete_file(self, file_path: str) -> bool:
        """
        Delete file from S3.

        Args:
            file_path: S3 URL or S3 key

        Returns:
            True if deleted, False if not found
        """
        # Parse S3 URL
        s3_key = self._parse_s3_url(file_path)

        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"Deleted file from S3: {s3_key}")
            return True

        except ClientError as e:
            logger.error(f"Failed to delete from S3: {e}")
            raise

    async def file_exists(self, file_path: str) -> bool:
        """
        Check if file exists in S3.

        Args:
            file_path: S3 URL or S3 key

        Returns:
            True if file exists
        """
        s3_key = self._parse_s3_url(file_path)

        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError:
            return False

    def _parse_s3_url(self, file_path: str) -> str:
        """
        Parse S3 URL to extract key.

        Args:
            file_path: S3 URL (s3://bucket/key) or key

        Returns:
            S3 key (path within bucket)
        """
        if file_path.startswith("s3://"):
            # Remove s3://bucket/ prefix
            parts = file_path[5:].split("/", 1)
            if len(parts) == 2:
                return parts[1]
            else:
                raise ValueError(f"Invalid S3 URL: {file_path}")
        else:
            # Assume it's already a key
            return file_path

    def get_presigned_url(self, file_path: str, expiration: int = 3600) -> str:
        """
        Generate presigned URL for file download.

        Args:
            file_path: S3 URL or key
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL for direct download
        """
        s3_key = self._parse_s3_url(file_path)

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": s3_key},
                ExpiresIn=expiration,
            )
            logger.debug(f"Generated presigned URL for {s3_key} (expires in {expiration}s)")
            return url

        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
