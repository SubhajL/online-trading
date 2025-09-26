"""
Storage backends for chart snapshots.
"""

import os
import logging
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

import aiofiles

try:
    import aiobotocore.session
    from botocore.exceptions import ClientError
    HAS_S3_SUPPORT = True
except ImportError:
    HAS_S3_SUPPORT = False
    ClientError = Exception  # Dummy for type hints

logger = logging.getLogger(__name__)


class SnapshotStorage:
    """Base class for snapshot storage backends."""

    def __init__(self, cdn_url: Optional[str] = None, bucket: Optional[str] = None):
        """Initialize storage backend.

        Args:
            cdn_url: Optional CDN URL for serving snapshots
            bucket: Bucket or container name
        """
        self.cdn_url = cdn_url
        self.bucket = bucket

    async def store_snapshot(self, signal_id: str, image_data: bytes) -> str:
        """Store snapshot and return URL.

        Args:
            signal_id: Unique signal identifier
            image_data: PNG image data

        Returns:
            URL to access the snapshot
        """
        raise NotImplementedError

    def get_snapshot_url(
        self,
        signal_id: str,
        ttl: Optional[int] = None,
        signed: bool = False
    ) -> str:
        """Get URL for a stored snapshot.

        Args:
            signal_id: Signal identifier
            ttl: Time-to-live in seconds for signed URLs
            signed: Whether to generate a signed URL

        Returns:
            Snapshot URL
        """
        if self.cdn_url:
            base_url = f"{self.cdn_url}/{self.bucket}/{signal_id}.png"
        else:
            base_url = f"/{self.bucket}/{signal_id}.png"

        if signed and ttl:
            # Add expiration timestamp for signed URLs
            expires = int((datetime.now() + timedelta(seconds=ttl)).timestamp())
            return f"{base_url}?expires={expires}"

        return base_url


class LocalSnapshotStorage(SnapshotStorage):
    """Local file system storage for snapshots."""

    def __init__(self, base_path: str = "./snapshots"):
        """Initialize local storage.

        Args:
            base_path: Base directory for storing snapshots
        """
        super().__init__()
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Local snapshot storage initialized at: {self.base_path}")

    async def store_snapshot(self, signal_id: str, image_data: bytes) -> str:
        """Store snapshot to local file system.

        Args:
            signal_id: Unique signal identifier
            image_data: PNG image data

        Returns:
            File path to the stored snapshot
        """
        # Create subdirectory based on date
        date_dir = datetime.now().strftime("%Y/%m/%d")
        full_dir = self.base_path / date_dir
        full_dir.mkdir(parents=True, exist_ok=True)

        # Save file
        filename = f"{signal_id}.png"
        file_path = full_dir / filename

        try:
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(image_data)

            logger.info(f"Stored snapshot locally: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Failed to store snapshot locally: {e}")
            raise

    def get_snapshot_path(self, signal_id: str) -> str:
        """Get local file path for a snapshot.

        Args:
            signal_id: Signal identifier

        Returns:
            Local file path
        """
        # Search for the file in date directories
        for date_path in sorted(self.base_path.rglob(f"{signal_id}.png"), reverse=True):
            if date_path.exists():
                return str(date_path)

        return str(self.base_path / f"{signal_id}.png")


class S3SnapshotStorage(SnapshotStorage):
    """AWS S3 storage for snapshots."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "signals/",
        region: str = "us-east-1",
        cdn_url: Optional[str] = None
    ):
        """Initialize S3 storage.

        Args:
            bucket: S3 bucket name
            prefix: Key prefix for organizing snapshots
            region: AWS region
            cdn_url: Optional CloudFront URL
        """
        if not HAS_S3_SUPPORT:
            raise ImportError(
                "S3 support requires aiobotocore. Install with: pip install aiobotocore"
            )

        super().__init__(cdn_url, bucket)
        self.prefix = prefix
        self.region = region
        self.session = aiobotocore.session.AioSession()
        logger.info(f"S3 snapshot storage initialized: s3://{bucket}/{prefix}")

    async def store_snapshot(self, signal_id: str, image_data: bytes) -> str:
        """Store snapshot to S3.

        Args:
            signal_id: Unique signal identifier
            image_data: PNG image data

        Returns:
            S3 URL or CDN URL
        """
        # Generate S3 key with date prefix
        date_prefix = datetime.now().strftime("%Y/%m/%d")
        key = f"{self.prefix}{date_prefix}/{signal_id}.png"

        try:
            async with self.session.create_client(
                's3',
                region_name=self.region
            ) as client:
                # Upload to S3
                result = await client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=image_data,
                    ContentType='image/png',
                    CacheControl='max-age=31536000',  # Cache for 1 year
                    Metadata={
                        'signal_id': signal_id,
                        'uploaded_at': datetime.now().isoformat()
                    }
                )

                logger.info(f"Stored snapshot to S3: s3://{self.bucket}/{key}")

                # Return CDN URL if configured, otherwise S3 URL
                if self.cdn_url:
                    return f"{self.cdn_url}/{key}"
                else:
                    return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"

        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            raise

    async def generate_presigned_url(
        self,
        signal_id: str,
        ttl: int = 3600
    ) -> str:
        """Generate presigned URL for secure access.

        Args:
            signal_id: Signal identifier
            ttl: URL validity in seconds

        Returns:
            Presigned URL
        """
        # Find the key (need to search with date prefix)
        key = await self._find_signal_key(signal_id)
        if not key:
            raise FileNotFoundError(f"Snapshot not found: {signal_id}")

        try:
            async with self.session.create_client(
                's3',
                region_name=self.region
            ) as client:
                url = await client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.bucket,
                        'Key': key
                    },
                    ExpiresIn=ttl
                )

                return url

        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    async def _find_signal_key(self, signal_id: str) -> Optional[str]:
        """Find S3 key for a signal ID.

        Args:
            signal_id: Signal identifier

        Returns:
            S3 key if found
        """
        try:
            async with self.session.create_client(
                's3',
                region_name=self.region
            ) as client:
                # List objects with the signal_id
                paginator = client.get_paginator('list_objects_v2')

                async for page in paginator.paginate(
                    Bucket=self.bucket,
                    Prefix=self.prefix
                ):
                    for obj in page.get('Contents', []):
                        if signal_id in obj['Key']:
                            return obj['Key']

                return None

        except ClientError as e:
            logger.error(f"S3 list failed: {e}")
            return None