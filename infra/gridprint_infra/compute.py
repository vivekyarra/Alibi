"""Compute stack: ECS cluster on Graviton c8g (EC2 Auto Scaling capacity provider), SQS jobs queue
with DLQ, engine worker service (linux/arm64), scaling on queue depth (SPEC Part 5, 10.6).

Host AMI:
- `aws.cool_ami_id` set in config -> the COOL Marketplace AMI (Ubuntu 24.04). User data installs Docker
  and the Amazon ECS container agent (deb from the regional `amazon-ecs-agent-<region>` bucket, per the
  ECS developer guide). The worker container mounts the host COOL install read-only and puts its
  Python bindings first on PYTHONPATH.
- not set -> the ECS-optimized Amazon Linux 2023 arm64 AMI, stock OpenCV from the image (no COOL claim).
"""

from __future__ import annotations

from pathlib import Path

from aws_cdk import Duration, IgnoreMode, Stack
from aws_cdk import aws_applicationautoscaling as appscaling
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from .ai import AiStack
from .auth import AuthStack
from .config import PREFIX, REPO, InfraConfig
from .data import DataStack
from .runtime_env import WORKER_COMMAND, service_env
from .storage import StorageStack

# Docker build contexts are allow-lists (.dockerignore semantics): everything at the repo root is
# excluded, then only the paths each image needs are added back. This keeps asset staging fast, keeps
# secrets and transient files (logs, results, data) out of images, and makes the context reproducible.
_ALWAYS_EXCLUDE = ["**/__pycache__", "**/*.pyc", "**/*.pem", "**/*.key"]


def docker_context(dockerfile: str, paths: list[str]) -> list[str]:
    return ["*", f"!infra/docker/{dockerfile}", "!pyproject.toml", "!uv.lock",
            *[f"!{p}" for p in paths], *_ALWAYS_EXCLUDE]


ENGINE_CONTEXT = docker_context("engine.Dockerfile",
                                ["config", "engine", "agent", "mcp_server", "api", "models"])
API_CONTEXT = docker_context("api.Dockerfile", ["config", "engine", "api"])

# Engineering constants for the worker task on c8g.2xlarge (8 vCPU, 16 GiB). Headroom is left for the
# ECS agent and the OS. Documented in docs/agent_notes/infra.md.
WORKER_CPU_UNITS = 7168
WORKER_MEMORY_MIB = 13312
JOB_VISIBILITY_TIMEOUT_S = 1800   # > limits.decode_timeout_s plus analysis time
DLQ_MAX_RECEIVES = 3
METRIC_NAMESPACE = PREFIX.capitalize()
ARM64_CONSTRAINT = "attribute:ecs.cpu-architecture == arm64"


def engine_image(scope: Construct, cid: str, platform: ecr_assets.Platform) -> ecr_assets.DockerImageAsset:
    return ecr_assets.DockerImageAsset(
        scope, cid,
        directory=str(REPO),
        file=str(Path("infra") / "docker" / "engine.Dockerfile"),
        platform=platform,
        exclude=ENGINE_CONTEXT,
        ignore_mode=IgnoreMode.DOCKER,
    )


def ubuntu_ecs_agent_user_data(region: str) -> list[str]:
    """Commands from the ECS developer guide, 'Installing the Amazon ECS container agent on a
    non-Amazon Linux EC2 instance' (deb, arm64). ECS_CLUSTER is appended later by the cluster."""
    deb = f"https://s3.{region}.amazonaws.com/amazon-ecs-agent-{region}/amazon-ecs-init-latest.arm64.deb"
    return [
        # No `set -e`: later lines added by the ECS cluster (iptables save) are Amazon Linux specific.
        "set -x",
        "export DEBIAN_FRONTEND=noninteractive",
        "apt-get update",
        "apt-get install -y docker.io curl",
        f"curl -fsSL -o /tmp/amazon-ecs-init.deb {deb}",
        "dpkg -i /tmp/amazon-ecs-init.deb",
        "sed -i '/^\\[Unit\\]/a After=cloud-final.service' /lib/systemd/system/ecs.service",
        "mkdir -p /etc/ecs",
    ]


class ComputeStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: InfraConfig, vpc: ec2.IVpc,
                 storage: StorageStack, data: DataStack, ai: AiStack, auth: AuthStack, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        self.uses_cool_ami = cfg.cool_ami_id is not None

        self.dlq = sqs.Queue(self, "JobsDlq", retention_period=Duration.days(14),
                             encryption=sqs.QueueEncryption.SQS_MANAGED, enforce_ssl=True)
        self.queue = sqs.Queue(
            self, "JobsQueue",
            visibility_timeout=Duration.seconds(JOB_VISIBILITY_TIMEOUT_S),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl=True,
            dead_letter_queue=sqs.DeadLetterQueue(queue=self.dlq, max_receive_count=DLQ_MAX_RECEIVES),
        )

        self.cluster = ecs.Cluster(self, "Cluster", vpc=vpc, enable_fargate_capacity_providers=True,
                                   container_insights_v2=ecs.ContainerInsights.ENABLED)

        if cfg.cool_ami_id:
            machine_image: ec2.IMachineImage = ec2.MachineImage.generic_linux({cfg.region: cfg.cool_ami_id})
            user_data = ec2.UserData.for_linux()
            user_data.add_commands(*ubuntu_ecs_agent_user_data(cfg.region))
        else:
            machine_image = ecs.EcsOptimizedImage.amazon_linux2023(ecs.AmiHardwareType.ARM)
            user_data = ec2.UserData.for_linux()

        self.host_sg = ec2.SecurityGroup(self, "WorkerHostSg", vpc=vpc, allow_all_outbound=True,
                                         description=f"{PREFIX} worker hosts: no inbound")
        launch_template = ec2.LaunchTemplate(
            self, "WorkerLaunchTemplate",
            instance_type=ec2.InstanceType(cfg.worker_instance_type),
            machine_image=machine_image,
            user_data=user_data,
            role=iam.Role(self, "WorkerInstanceRole",
                          assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                          managed_policies=[
                              iam.ManagedPolicy.from_aws_managed_policy_name(
                                  "service-role/AmazonEC2ContainerServiceforEC2Role"),
                              iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                          ]),
            security_group=self.host_sg,
            require_imdsv2=True,
            # Root volume size/encryption only for the known AL2023 root device; the COOL AMI keeps its own.
            block_devices=None if cfg.cool_ami_id else [ec2.BlockDevice(
                device_name="/dev/xvda", volume=ec2.BlockDeviceVolume.ebs(60, encrypted=True))],
        )
        self.asg = autoscaling.AutoScalingGroup(
            self, "WorkerAsg",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            launch_template=launch_template,
            min_capacity=0,
            max_capacity=cfg.worker_max_instances,
        )
        self.capacity_provider = ecs.AsgCapacityProvider(
            self, "GravitonCapacity",
            auto_scaling_group=self.asg,
            enable_managed_scaling=True,
            enable_managed_termination_protection=False,
            machine_image_type=ecs.MachineImageType.AMAZON_LINUX_2,
        )
        self.cluster.add_asg_capacity_provider(self.capacity_provider)
        if cfg.cool_ami_id:
            # Start the agent after ECS_CLUSTER is written; --no-block avoids the cloud-init deadlock.
            self.asg.add_user_data("systemctl enable --now --no-block ecs.service")

        # ---- worker task (linux/arm64) ----
        self.log_group = logs.LogGroup(self, "WorkerLogs", retention=logs.RetentionDays.ONE_MONTH)
        self.task_role = iam.Role(self, "WorkerTaskRole",
                                  assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"))
        # CDK rejects runtimePlatform on EC2-compatible task definitions, so linux/arm64 is enforced with
        # the built-in ECS placement attribute `ecs.cpu-architecture` (and the image is built for arm64).
        self.task_def = ecs.Ec2TaskDefinition(
            self, "WorkerTask",
            # Bridge mode: the worker needs no inbound traffic and bridge mode needs no task ENI support on
            # the Ubuntu-based COOL AMI. Container access to instance metadata is blocked by the cluster.
            network_mode=ecs.NetworkMode.BRIDGE,
            placement_constraints=[ecs.PlacementConstraint.member_of(ARM64_CONSTRAINT)],
            task_role=self.task_role,
        )
        env = service_env(cfg, storage, data, self.queue, auth)
        env["GRIDPRINT_METRIC_NAMESPACE"] = METRIC_NAMESPACE
        env["GRIDPRINT_COOL_HOST"] = "1" if self.uses_cool_ami else "0"
        if self.uses_cool_ami:
            env["PYTHONPATH"] = f"{cfg.cool_pythonpath}:/app:/app/engine"
            env["LD_LIBRARY_PATH"] = cfg.cool_ld_library_path
        self.worker_image = engine_image(self, "EngineImageArm64", ecr_assets.Platform.LINUX_ARM64)
        container = self.task_def.add_container(
            "engine",
            image=ecs.ContainerImage.from_docker_image_asset(self.worker_image),
            command=WORKER_COMMAND,
            cpu=WORKER_CPU_UNITS,
            memory_limit_mib=WORKER_MEMORY_MIB,
            environment=env,
            readonly_root_filesystem=False,
            logging=ecs.LogDrivers.aws_logs(stream_prefix="worker", log_group=self.log_group,
                                            mode=ecs.AwsLogDriverMode.NON_BLOCKING),
        )
        if self.uses_cool_ami:
            for i, host_path in enumerate(cfg.cool_host_paths):
                name = f"cool{i}"
                self.task_def.add_volume(name=name, host=ecs.Host(source_path=host_path))
                container.add_mount_points(ecs.MountPoint(container_path=host_path, source_volume=name,
                                                          read_only=True))

        # Least privilege for the worker.
        storage.uploads.grant_read_write(self.task_role)
        storage.results.grant_read_write(self.task_role)
        for table in data.tables:
            table.grant_read_write_data(self.task_role)
        self.queue.grant_consume_messages(self.task_role)
        self.task_role.add_managed_policy(ai.invoke_policy)

        self.service = ecs.Ec2Service(
            self, "WorkerService",
            cluster=self.cluster,
            task_definition=self.task_def,
            desired_count=0,
            capacity_provider_strategies=[ecs.CapacityProviderStrategy(
                capacity_provider=self.capacity_provider.capacity_provider_name, weight=1)],
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            min_healthy_percent=0,
            max_healthy_percent=100,
        )

        # Scale on queue depth: visible + in-flight messages. In-flight jobs keep their task alive.
        backlog = cw.MathExpression(
            expression="visible + inflight",
            using_metrics={
                "visible": self.queue.metric_approximate_number_of_messages_visible(
                    period=Duration.minutes(1), statistic="Maximum"),
                "inflight": self.queue.metric_approximate_number_of_messages_not_visible(
                    period=Duration.minutes(1), statistic="Maximum"),
            },
            period=Duration.minutes(1),
            label="Jobs backlog",
        )
        scaling = self.service.auto_scale_task_count(min_capacity=0, max_capacity=cfg.worker_max_instances)
        scaling.scale_on_metric(
            "QueueDepthScaling",
            metric=backlog,
            scaling_steps=[
                appscaling.ScalingInterval(upper=0, change=-cfg.worker_max_instances),
                appscaling.ScalingInterval(lower=1, change=+1),
                appscaling.ScalingInterval(lower=5, change=+2),
            ],
            adjustment_type=appscaling.AdjustmentType.CHANGE_IN_CAPACITY,
            cooldown=Duration.minutes(2),
            evaluation_periods=2,
        )
