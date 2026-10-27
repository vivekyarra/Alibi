"""Synthesize the CDK app and check key resources (SPEC 10.6). Skipped when aws_cdk is not installed.

Synthesis needs no AWS credentials and no Docker (Docker builds happen only at deploy time).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("aws_cdk")

from aws_cdk.assertions import Match, Template  # noqa: E402

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))

from gridprint_infra import config as cfgmod  # noqa: E402
from gridprint_infra.app import build_app  # noqa: E402
from gridprint_infra.config import PREFIX  # noqa: E402

P = PREFIX.capitalize()

ACCOUNT = "123456789012"


def _templates(app: Any) -> dict[str, Template]:
    out: dict[str, Template] = {}
    for child in app.node.children:
        name = getattr(child, "stack_name", None)
        if name:
            out[name] = Template.from_stack(child)
    return out


@pytest.fixture(scope="module")
def stacks(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Template]:
    out = tmp_path_factory.mktemp("cdkout")
    return _templates(build_app(account=ACCOUNT, outdir=str(out)))


@pytest.fixture(scope="module")
def cool_stacks(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Template]:
    cfg_dir = tmp_path_factory.mktemp("cfg")
    src = (cfgmod.CONFIG_DIR / "default.yaml").read_text(encoding="utf-8")
    (cfg_dir / "default.yaml").write_text(
        src.replace("aws:\n", "aws:\n  cool_ami_id: ami-0123456789abcdef0\n", 1), encoding="utf-8")
    out = tmp_path_factory.mktemp("cdkout_cool")
    return _templates(build_app(account=ACCOUNT, config_dir=cfg_dir, outdir=str(out),
                                context={"bench": "true"}))


def test_docker_context_is_allow_list(tmp_path_factory: pytest.TempPathFactory,
                                      stacks: dict[str, Template]) -> None:
    from gridprint_infra.compute import API_CONTEXT, ENGINE_CONTEXT

    assert ENGINE_CONTEXT[0] == "*" and API_CONTEXT[0] == "*"
    assert "!infra/docker/engine.Dockerfile" in ENGINE_CONTEXT
    assert "!api" in ENGINE_CONTEXT and "!agent" in ENGINE_CONTEXT
    assert "!agent" in API_CONTEXT and "!node" in API_CONTEXT  # the API imports the worker (agent) and node adapters


def test_all_stacks_present(stacks: dict[str, Template]) -> None:
    for name in ["Network", "Storage", "Data", "Compute", "Api", "Iot", "Auth", "Web", "Observability", "Ai"]:
        assert f"{P}{name}" in stacks


def test_vpc_gateway_endpoints(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Network"]
    t.resource_count_is("AWS::EC2::VPCEndpoint", 2)
    t.has_resource_properties("AWS::EC2::VPCEndpoint", {"VpcEndpointType": "Gateway"})


def test_buckets_kms_tls_public_block_and_lifecycle(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Storage"]
    buckets = t.find_resources("AWS::S3::Bucket")
    assert len(buckets) == 2
    cfg = cfgmod.load()
    expirations = set()
    for b in buckets.values():
        props = b["Properties"]
        sse_cfg = props["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]
        sse = sse_cfg["ServerSideEncryptionByDefault"]
        assert sse["SSEAlgorithm"] == "aws:kms"
        assert "KMSMasterKeyID" in sse
        assert props["PublicAccessBlockConfiguration"] == {
            "BlockPublicAcls": True, "BlockPublicPolicy": True,
            "IgnorePublicAcls": True, "RestrictPublicBuckets": True}
        expirations.add(props["LifecycleConfiguration"]["Rules"][0]["ExpirationInDays"])
    assert expirations == {cfg.upload_retention_days, cfg.results_retention_days}
    policies = json.dumps(t.find_resources("AWS::S3::BucketPolicy"))
    assert "aws:SecureTransport" in policies
    t.has_resource_properties("AWS::KMS::Key", {"EnableKeyRotation": True})


def test_four_tables_with_pitr_and_gridlog_keys(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Data"]
    t.resource_count_is("AWS::DynamoDB::Table", 4)
    for name in ["Jobs", "Reviews", "GridLog", "TraceIndex"]:
        t.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": f"{PREFIX}-{name}",
            "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        })
    t.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": f"{PREFIX}-GridLog",
        "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "t", "KeyType": "RANGE"}],
        "AttributeDefinitions": Match.array_with([{"AttributeName": "t", "AttributeType": "N"}]),
    })


def test_lead_key_schema_for_jobs_reviews_trace(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Data"]
    for name in ["Jobs", "Reviews", "TraceIndex"]:
        t.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": f"{PREFIX}-{name}",
            "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
            "BillingMode": "PAY_PER_REQUEST",
        })


ENV_KEYS = ["GRIDPRINT_MODE", "JOBS_TABLE", "REVIEWS_TABLE", "TRACE_TABLE", "GRIDLOG_TABLE", "RESULTS_BUCKET",
            "UPLOADS_BUCKET", "JOBS_QUEUE_URL", "COGNITO_REGION", "COGNITO_USER_POOL_ID", "COGNITO_CLIENT_ID"]


def _container(t: Template) -> dict:
    td = next(iter(t.find_resources("AWS::ECS::TaskDefinition").values()))
    return td["Properties"]["ContainerDefinitions"][0]


@pytest.mark.parametrize("stack,command", [
    (f"{P}Api", ["uvicorn", "api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]),
    (f"{P}Compute", ["python", "-m", "api.worker", "--sqs"]),
])
def test_container_command_and_env(stacks: dict[str, Template], stack: str, command: list[str]) -> None:
    c = _container(stacks[stack])
    assert c["Command"] == command
    names = {e["Name"] for e in c["Environment"]}
    assert set(ENV_KEYS) <= names
    mode = next(e["Value"] for e in c["Environment"] if e["Name"] == "GRIDPRINT_MODE")
    assert mode == "aws"


def test_uploads_cors_put_from_cloudfront(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Web"]
    cr = json.dumps(t.find_resources("Custom::AWS"))
    assert "putBucketCors" in cr
    assert "PUT" in cr
    assert "DomainName" in cr   # origin is built from the distribution domain
    storage_buckets = stacks[f"{P}Storage"].find_resources("AWS::S3::Bucket")
    assert all("CorsConfiguration" not in b["Properties"] for b in storage_buckets.values())


def test_worker_can_put_uploads_and_write_all_tables(stacks: dict[str, Template]) -> None:
    pols = json.dumps(stacks[f"{P}Compute"].find_resources("AWS::IAM::Policy"))
    for action in ["s3:PutObject", "s3:GetObject*", "dynamodb:PutItem", "sqs:ReceiveMessage",
                   "sqs:DeleteMessage"]:
        assert action in pols
    for table in ["Jobs", "Reviews", "GridLog", "TraceIndex"]:
        assert f"{P}Data:ExportsOutputFnGetAtt{table}" in pols


def test_cognito_reviewer_group(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Auth"]
    t.has_resource_properties("AWS::Cognito::UserPoolGroup", {"GroupName": "reviewer"})
    t.has_resource_properties("AWS::Cognito::UserPool", {"MfaConfiguration": "ON"})


def test_waf_rate_rules_on_cloudfront(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Web"]
    t.has_resource_properties("AWS::WAFv2::WebACL", {
        "Scope": "CLOUDFRONT",
        "Rules": Match.array_with([Match.object_like({
            "Statement": {"RateBasedStatement": Match.object_like({"AggregateKeyType": "IP"})}})]),
    })
    t.resource_count_is("AWS::CloudFront::OriginAccessControl", 1)
    t.resource_count_is("AWS::CloudFront::VpcOrigin", 1)


def test_arm64_task_definitions(stacks: dict[str, Template]) -> None:
    worker = stacks[f"{P}Compute"]
    worker.has_resource_properties("AWS::ECS::TaskDefinition", {
        "RequiresCompatibilities": ["EC2"],
        "PlacementConstraints": [{"Type": "memberOf",
                                  "Expression": "attribute:ecs.cpu-architecture == arm64"}],
    })
    worker.has_resource_properties("AWS::ECS::Service", {"CapacityProviderStrategy": Match.any_value()})
    api = stacks[f"{P}Api"]
    api.has_resource_properties("AWS::ECS::TaskDefinition", {
        "RequiresCompatibilities": ["FARGATE"],
        "RuntimePlatform": {"CpuArchitecture": "ARM64", "OperatingSystemFamily": "LINUX"},
    })
    api.has_resource_properties("AWS::ElasticLoadBalancingV2::LoadBalancer", {"Scheme": "internal"})


def test_graviton_capacity_and_queue(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Compute"]
    t.has_resource_properties("AWS::EC2::LaunchTemplate", {
        "LaunchTemplateData": Match.object_like({"InstanceType": "c8g.2xlarge"})})
    t.resource_count_is("AWS::ECS::CapacityProvider", 1)
    t.resource_count_is("AWS::SQS::Queue", 2)
    t.has_resource_properties("AWS::SQS::Queue", {"RedrivePolicy": Match.object_like({"maxReceiveCount": 3})})
    t.has_resource_properties("AWS::ApplicationAutoScaling::ScalingPolicy", {"PolicyType": "StepScaling"})
    # Default (no cool_ami_id): ECS-optimized AL2023 arm64 AMI from SSM.
    params = json.dumps(t.to_json().get("Parameters", {}))
    assert "/aws/service/ecs/optimized-ami/amazon-linux-2023/arm64" in params


def test_bedrock_policy_is_pinned(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Ai"]
    pol = next(iter(t.find_resources("AWS::IAM::ManagedPolicy").values()))
    stmts = pol["Properties"]["PolicyDocument"]["Statement"]
    assert len(stmts) == 1
    assert sorted(stmts[0]["Action"]) == ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    text = json.dumps(stmts[0]["Resource"])
    model = cfgmod.foundation_model_id(cfgmod.load().bedrock_model_id)
    assert f"foundation-model/{model}" in text
    assert "inference-profile/" in text
    assert '"*"' not in text


def test_iot_policy_topic_and_arm64_lambda(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Iot"]
    doc = json.dumps(t.find_resources("AWS::IoT::Policy"))
    assert f"topic/{PREFIX}/${{iot:Connection.Thing.Attributes[zone]}}/${{iot:Connection.Thing.ThingName}}" in doc
    t.has_resource_properties("AWS::Lambda::Function",
                              {"Architectures": ["arm64"], "Handler": "handler.handler"})
    t.resource_count_is("AWS::IoT::TopicRule", 1)
    t.resource_count_is("AWS::IoT::ThingType", 1)


def test_observability_alarms(stacks: dict[str, Template]) -> None:
    t = stacks[f"{P}Observability"]
    t.resource_count_is("AWS::CloudWatch::Dashboard", 1)
    limit = cfgmod.load().freshness_limit_s
    t.has_resource_properties("AWS::CloudWatch::Alarm", {
        "MetricName": "NodeFreshnessSeconds", "Threshold": limit, "TreatMissingData": "breaching"})


def test_cool_ami_variant(cool_stacks: dict[str, Template]) -> None:
    t = cool_stacks[f"{P}Compute"]
    lt = json.dumps(t.find_resources("AWS::EC2::LaunchTemplate"))
    assert "amazon-ecs-init-latest.arm64.deb" in lt
    t.has_resource_properties("AWS::ECS::TaskDefinition", {
        "ContainerDefinitions": [Match.object_like({
            "MountPoints": Match.array_with(
                [Match.object_like({"ContainerPath": "/opt/cool", "ReadOnly": True})]),
        })],
    })
    assert f"{P}BenchImages" in cool_stacks
