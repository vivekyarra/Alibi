"""Build the container images in AWS (CodeBuild on Graviton) and push them to ECR.

Used by `make deploy` when no local Docker engine is available. The images are built from the committed tree
(`git archive HEAD`), so what runs in AWS is exactly what is in the repository.

    python infra/build_images.py            # builds linux/arm64 engine + api images, prints their URIs
    python infra/build_images.py --amd64    # also builds the linux/amd64 engine image (bench baseline A)

Writes `infra/image_uris.json` (git-ignored); `infra/app.py` passes these URIs to the stacks.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import boto3
import yaml

REPO = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((REPO / "config" / "default.yaml").read_text())
PREFIX = CFG["aws"].get("resource_prefix", "gridprint")
IMAGES = {"engine": "infra/docker/engine.Dockerfile", "api": "infra/docker/api.Dockerfile"}
ARM_IMAGE = "aws/codebuild/amazonlinux-aarch64-standard:3.0"  # listed by list-curated-environment-images
X86_IMAGE = "aws/codebuild/amazonlinux2-x86_64-standard:5.0"

BUILDSPEC = """version: 0.2
phases:
  pre_build:
    commands:
      - aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $REGISTRY
  build:
    commands:
      - docker build -f $DOCKERFILE -t $REPO_URI:$TAG .
      - docker push $REPO_URI:$TAG
"""


def session() -> boto3.Session:
    return boto3.Session(profile_name=CFG["aws"]["profile"], region_name=CFG["aws"]["region"])


def ensure_repo(ecr, name: str) -> str:  # type: ignore[no-untyped-def]
    try:
        r = ecr.describe_repositories(repositoryNames=[name])["repositories"][0]
    except ecr.exceptions.RepositoryNotFoundException:
        r = ecr.create_repository(repositoryName=name, imageScanningConfiguration={"scanOnPush": True},
                                  encryptionConfiguration={"encryptionType": "AES256"})["repository"]
    return str(r["repositoryUri"])


def ensure_bucket(s3, name: str) -> None:  # type: ignore[no-untyped-def]
    try:
        s3.head_bucket(Bucket=name)
    except Exception:
        s3.create_bucket(Bucket=name)
        s3.put_public_access_block(Bucket=name, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True})
        s3.put_bucket_lifecycle_configuration(Bucket=name, LifecycleConfiguration={"Rules": [
            {"ID": "expire-sources", "Status": "Enabled", "Filter": {"Prefix": ""}, "Expiration": {"Days": 7}}]})


def ensure_role(iam, account: str, bucket: str) -> str:  # type: ignore[no-untyped-def]
    name = f"{PREFIX}-image-build"
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {
        "Service": "codebuild.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
    try:
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
    except iam.exceptions.NoSuchEntityException:
        arn = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
        time.sleep(10)  # IAM propagation before CodeBuild can assume the role
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
         "Resource": f"arn:aws:logs:*:{account}:log-group:/aws/codebuild/{PREFIX}-*"},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion"], "Resource": f"arn:aws:s3:::{bucket}/*"},
        {"Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
        {"Effect": "Allow", "Action": ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload",
                                       "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
                                       "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
         "Resource": f"arn:aws:ecr:*:{account}:repository/{PREFIX}-*"}]}
    iam.put_role_policy(RoleName=name, PolicyName="build", PolicyDocument=json.dumps(policy))
    return str(arn)


def source_zip() -> bytes:
    return subprocess.run(["git", "archive", "--format=zip", "HEAD"], cwd=REPO, capture_output=True,
                          check=True).stdout


def build(arch: str, tag: str, account: str) -> dict[str, str]:
    s = session()
    ecr, s3, iam, cb = s.client("ecr"), s.client("s3"), s.client("iam"), s.client("codebuild")
    bucket = f"{PREFIX}-build-{account}"
    ensure_bucket(s3, bucket)
    role = ensure_role(iam, account, bucket)
    key = f"src/{tag}.zip"
    s3.upload_fileobj(io.BytesIO(source_zip()), bucket, key)
    registry = f"{account}.dkr.ecr.{s.region_name}.amazonaws.com"
    uris: dict[str, str] = {}
    for name, dockerfile in IMAGES.items():
        if arch == "amd64" and name != "engine":
            continue
        repo = ensure_repo(ecr, f"{PREFIX}-{name}")
        project = f"{PREFIX}-{name}-{arch}"
        env = {"type": "ARM_CONTAINER" if arch == "arm64" else "LINUX_CONTAINER",
               "image": ARM_IMAGE if arch == "arm64" else X86_IMAGE, "computeType": "BUILD_GENERAL1_LARGE",
               "privilegedMode": True}
        args = {"name": project, "source": {"type": "S3", "location": f"{bucket}/{key}", "buildspec": BUILDSPEC},
                "artifacts": {"type": "NO_ARTIFACTS"}, "environment": env, "serviceRole": role,
                "timeoutInMinutes": 60}
        try:
            cb.create_project(**args)
        except cb.exceptions.ResourceAlreadyExistsException:
            cb.update_project(**args)
        img_tag = f"{tag}-{arch}"
        b = cb.start_build(projectName=project, environmentVariablesOverride=[
            {"name": "DOCKERFILE", "value": dockerfile}, {"name": "REPO_URI", "value": repo},
            {"name": "TAG", "value": img_tag}, {"name": "REGISTRY", "value": registry}])["build"]
        print(f"{project}: build {b['id']} started", flush=True)
        while True:
            st = cb.batch_get_builds(ids=[b["id"]])["builds"][0]
            if st["buildStatus"] != "IN_PROGRESS":
                break
            time.sleep(20)
        print(f"{project}: {st['buildStatus']} ({st.get('currentPhase')})", flush=True)
        if st["buildStatus"] != "SUCCEEDED":
            logs = st.get("logs", {}).get("deepLink")
            raise SystemExit(f"image build failed: {project}; logs: {logs}")
        uris[f"{name}_{arch}"] = f"{repo}:{img_tag}"
    return uris


USER_DATA = """#!/bin/bash
set -x
exec > /var/log/image-build.log 2>&1
dnf install -y docker unzip
systemctl start docker
aws s3 cp s3://{bucket}/{key} /tmp/src.zip && mkdir -p /src && cd /src && unzip -q /tmp/src.zip
aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {registry}
ok=1
docker build -f infra/docker/engine.Dockerfile -t {engine}:{tag} . && docker push {engine}:{tag} || ok=0
docker build -f infra/docker/api.Dockerfile -t {api}:{tag} . && docker push {api}:{tag} || ok=0
aws s3 cp /var/log/image-build.log s3://{bucket}/logs/{tag}.log
if [ $ok = 1 ]; then echo ok > /tmp/status; else echo failed > /tmp/status; fi
aws s3 cp /tmp/status s3://{bucket}/logs/{tag}.status
shutdown -h now
"""


def ensure_instance_profile(iam, account: str, bucket: str) -> str:  # type: ignore[no-untyped-def]
    name = f"{PREFIX}-image-build-ec2"
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"},
                                                     "Action": "sts:AssumeRole"}]}
    try:
        iam.get_role(RoleName=name)
    except iam.exceptions.NoSuchEntityException:
        iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust))
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": f"arn:aws:s3:::{bucket}/*"},
        {"Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
        {"Effect": "Allow", "Action": ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload",
                                       "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
                                       "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
         "Resource": f"arn:aws:ecr:*:{account}:repository/{PREFIX}-*"}]}
    iam.put_role_policy(RoleName=name, PolicyName="build", PolicyDocument=json.dumps(policy))
    try:
        iam.get_instance_profile(InstanceProfileName=name)
    except iam.exceptions.NoSuchEntityException:
        iam.create_instance_profile(InstanceProfileName=name)
        iam.add_role_to_instance_profile(InstanceProfileName=name, RoleName=name)
        time.sleep(15)  # instance profile propagation
    return name


def build_ec2(tag: str, account: str) -> dict[str, str]:
    """arm64 images built on a short-lived Graviton instance that terminates itself."""
    s = session()
    ecr, s3, iam, ec2, ssm = (s.client(n) for n in ("ecr", "s3", "iam", "ec2", "ssm"))
    bucket = f"{PREFIX}-build-{account}"
    ensure_bucket(s3, bucket)
    profile = ensure_instance_profile(iam, account, bucket)
    key = f"src/{tag}.zip"
    s3.upload_fileobj(io.BytesIO(source_zip()), bucket, key)
    repos = {n: ensure_repo(ecr, f"{PREFIX}-{n}") for n in IMAGES}
    img_tag = f"{tag}-arm64"
    ud = USER_DATA.format(bucket=bucket, key=key, region=s.region_name, tag=img_tag,
                          registry=f"{account}.dkr.ecr.{s.region_name}.amazonaws.com", engine=repos["engine"],
                          api=repos["api"])
    ami = ssm.get_parameter(Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64")
    for _ in range(6):
        try:
            inst = ec2.run_instances(
                ImageId=ami["Parameter"]["Value"], InstanceType="c8g.xlarge", MinCount=1, MaxCount=1, UserData=ud,
                IamInstanceProfile={"Name": profile}, InstanceInitiatedShutdownBehavior="terminate",
                BlockDeviceMappings=[{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 40, "VolumeType": "gp3"}}],
                MetadataOptions={"HttpTokens": "required"},
                TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name",
                                                                          "Value": f"{PREFIX}-image-build"}]}])
            break
        except ec2.exceptions.ClientError as e:  # instance profile may still be propagating
            if "iamInstanceProfile" not in str(e):
                raise
            time.sleep(10)
    iid = inst["Instances"][0]["InstanceId"]
    print(f"build instance {iid} started", flush=True)
    status_key = f"logs/{img_tag}.status"
    for _ in range(180):  # up to 60 minutes
        time.sleep(20)
        try:
            body = s3.get_object(Bucket=bucket, Key=status_key)["Body"].read().decode().strip()
            break
        except s3.exceptions.NoSuchKey:
            continue
    else:
        raise SystemExit(f"image build timed out; instance {iid}")
    print(f"build status: {body}; log s3://{bucket}/logs/{img_tag}.log", flush=True)
    if body != "ok":
        raise SystemExit("image build failed; see the log above")
    return {f"{n}_arm64": f"{repos[n]}:{img_tag}" for n in IMAGES}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--amd64", action="store_true")
    ap.add_argument("--backend", choices=["codebuild", "ec2"], default="ec2")
    a = ap.parse_args()
    account = session().client("sts").get_caller_identity()["Account"]
    tag = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO, capture_output=True, text=True,
                         check=True).stdout.strip()
    out = REPO / "infra" / "image_uris.json"
    uris = json.loads(out.read_text()) if out.exists() else {}
    uris.update(build_ec2(tag, account) if a.backend == "ec2" else build("arm64", tag, account))
    if a.amd64:
        uris.update(build("amd64", tag, account))
    out.write_text(json.dumps(uris, indent=1))
    print(json.dumps(uris, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
