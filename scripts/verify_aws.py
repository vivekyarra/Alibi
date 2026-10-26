"""Check the AWS prerequisites of H1 with the `gridprint` profile (SPEC 4: V5, V6, V12)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    import boto3
    import botocore.exceptions

    cfg = yaml.safe_load((ROOT / "config/default.yaml").read_text())
    region, profile = cfg["aws"]["region"], cfg["aws"]["profile"]
    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        ident = session.client("sts").get_caller_identity()
    except (botocore.exceptions.ProfileNotFound, botocore.exceptions.NoCredentialsError,
            botocore.exceptions.ClientError) as e:
        print(f"AWS FAIL: {e}")
        return 1
    print(f"AWS OK account={ident['Account']} region={region}")
    ok = True
    model_id = cfg["bedrock"]["model_id"]
    try:
        br = session.client("bedrock-runtime")
        resp = br.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "Reply with the word ok."}]}],
            inferenceConfig={"maxTokens": 5},
        )
        print(f"BEDROCK OK {model_id} stop={resp.get('stopReason')}")
    except botocore.exceptions.ClientError as e:
        print(f"BEDROCK FAIL {model_id}: {e}")
        ok = False
    ami = cfg["aws"].get("cool_ami_id")
    if ami:
        imgs = session.client("ec2").describe_images(ImageIds=[ami]).get("Images", [])
        if imgs:
            print(f"COOL AMI OK {ami} {json.dumps(imgs[0].get('Name'))} arch={imgs[0].get('Architecture')}")
        else:
            print(f"COOL AMI FAIL {ami} not visible")
            ok = False
    else:
        print("COOL AMI FAIL aws.cool_ami_id not set (H1 step 7)")
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
