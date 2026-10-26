"""Optional stack: engine images for the COOL benchmark (SPEC Part 12).

Created only with `-c bench=true`. It publishes the engine image for linux/amd64 (configuration A, the
x86 baseline; never used in production) and linux/arm64 (configurations B and C) to the CDK assets
repository and prints the image URIs.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_ecr_assets as ecr_assets
from constructs import Construct

from .compute import engine_image


class BenchImagesStack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        self.amd64 = engine_image(self, "EngineImageAmd64", ecr_assets.Platform.LINUX_AMD64)
        self.arm64 = engine_image(self, "EngineImageArm64", ecr_assets.Platform.LINUX_ARM64)
        CfnOutput(self, "EngineImageAmd64Uri", value=self.amd64.image_uri)
        CfnOutput(self, "EngineImageArm64Uri", value=self.arm64.image_uri)
