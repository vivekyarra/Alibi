"""API stack: FastAPI on Fargate linux/arm64 behind an internal ALB (SPEC 10.1, 10.6).

Choice (docs/agent_notes/infra.md): Fargate service + ALB. The ALB is internal (private subnets) and
CloudFront reaches it through a CloudFront VPC origin (Web stack), so the API is only reachable through
CloudFront and its WAF web ACL.
"""

from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnOutput, Duration, IgnoreMode, Stack
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_integrations as apigw_int
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_logs as logs
from constructs import Construct

from .auth import AuthStack
from .compute import API_CONTEXT, METRIC_NAMESPACE, ComputeStack, container_image
from .config import REPO, InfraConfig, prebuilt_image
from .data import DataStack
from .runtime_env import API_COMMAND, service_env
from .storage import StorageStack

API_PORT = 8000


class ApiStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: InfraConfig, vpc: ec2.IVpc, storage: StorageStack,
                 data: DataStack, compute: ComputeStack, auth: AuthStack, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        prebuilt = prebuilt_image("api_arm64")
        image = None if prebuilt else ecr_assets.DockerImageAsset(
            self, "ApiImageArm64",
            directory=str(REPO),
            file=str(Path("infra") / "docker" / "api.Dockerfile"),
            platform=ecr_assets.Platform.LINUX_ARM64,
            exclude=API_CONTEXT,
            ignore_mode=IgnoreMode.DOCKER,
        )
        self.log_group = logs.LogGroup(self, "ApiLogs", retention=logs.RetentionDays.ONE_MONTH)
        self.service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "Api",
            cluster=compute.cluster,
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            public_load_balancer=False,
            open_listener=False,
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            runtime_platform=ecs.RuntimePlatform(cpu_architecture=ecs.CpuArchitecture.ARM64,
                                                 operating_system_family=ecs.OperatingSystemFamily.LINUX),
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=container_image(self, "ApiRepo", prebuilt, image),
                container_port=API_PORT,
                log_driver=ecs.LogDrivers.aws_logs(stream_prefix="api", log_group=self.log_group,
                                                   mode=ecs.AwsLogDriverMode.NON_BLOCKING),
                command=API_COMMAND,
                environment={
                    **service_env(cfg, storage, data, compute.queue, auth),
                    "GRIDPRINT_METRIC_NAMESPACE": METRIC_NAMESPACE,
                },
            ),
        )
        self.service.target_group.configure_health_check(path="/v1/health", interval=Duration.seconds(30),
                                                         healthy_http_codes="200")
        # Only clients inside the VPC (CloudFront VPC origin ENIs) can reach the internal ALB.
        self.service.load_balancer.connections.allow_from(ec2.Peer.ipv4(vpc.vpc_cidr_block), ec2.Port.tcp(80),
                                                          "CloudFront VPC origin inside the VPC")

        # Public HTTPS entry point without CloudFront (D-025): API Gateway HTTP API → VPC link → internal ALB.
        # The VPC link ENIs sit inside the VPC, so the CIDR rule above admits them. Stage throttling limits
        # abuse of anonymous upload creation (WAF cannot attach to HTTP APIs).
        self.http_api = apigw.HttpApi(
            self, "PublicApi",
            default_integration=apigw_int.HttpAlbIntegration("AlbIntegration", self.service.listener),
        )
        stage = self.http_api.default_stage.node.default_child  # type: ignore[union-attr]
        stage.default_route_settings = apigw.CfnStage.RouteSettingsProperty(  # type: ignore[union-attr]
            throttling_burst_limit=cfg.waf_job_create_limit_5min * 2, throttling_rate_limit=10)
        CfnOutput(self, "PublicEndpoint", value=self.http_api.api_endpoint)

        role = self.service.task_definition.task_role
        storage.uploads.grant_put(role)
        storage.uploads.grant_read(role)
        storage.results.grant_read(role)
        data.jobs.grant_read_write_data(role)
        data.reviews.grant_read_write_data(role)
        data.trace_index.grant_read_data(role)
        data.gridlog.grant_read_data(role)
        compute.queue.grant_send_messages(role)
