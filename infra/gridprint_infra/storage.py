"""Storage stack: uploads and results buckets with SSE-KMS and lifecycle rules (SPEC 10.6, Part 13)."""

from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .config import PREFIX, InfraConfig


class StorageStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: InfraConfig, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        self.key = kms.Key(
            self, "DataKey",
            alias=f"alias/{PREFIX}-data",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,   # `make destroy` removes everything (SPEC 10.6)
            pending_window=Duration.days(7),
        )

        common = dict(
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.key,
            bucket_key_enabled=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            minimum_tls_version=1.2,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            versioned=False,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # S3 lifecycle expiration counts whole days. limits.upload_retention_hours is rounded up.
        self.uploads = s3.Bucket(
            self, "Uploads",
            lifecycle_rules=[s3.LifecycleRule(
                id="expire-uploads",
                expiration=Duration.days(cfg.upload_retention_days),
                abort_incomplete_multipart_upload_after=Duration.days(1),
            )],
            # CORS (PUT from the CloudFront origin only) is set by the Web stack once the distribution
            # domain exists; see web.py `UploadsCors`.
            **common,
        )
        self.results = s3.Bucket(
            self, "Results",
            lifecycle_rules=[s3.LifecycleRule(
                id="expire-results",
                expiration=Duration.days(cfg.results_retention_days),
                abort_incomplete_multipart_upload_after=Duration.days(1),
            )],
            **common,
        )
