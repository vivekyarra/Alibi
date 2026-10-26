"""Provision one GRIDPRINT Node in AWS IoT Core (human task H2, step 4).

Creates (or reuses) the IoT thing `<node_id>` with attribute `zone` (thing type `gridprint-node` when the
infra IoT stack exists), creates a new key pair and certificate, attaches the stack policy
`gridprint-node` (or, without the stack, a policy `gridprint-node-<node_id>` scoped to this node) to the
certificate, and attaches the certificate to the thing. Writes to node/firmware/certs/ (git-ignored):
    device.pem.crt, private.pem.key, endpoint.txt, certificate_arn.txt
The Amazon Root CA 1 file (AmazonRootCA1.pem) is NOT downloaded by this script; see FLASHING.md.

Either policy allows only: connect with client id <node_id>, publish to gridprint/<zone>/<node_id>.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CERT_DIR = Path(__file__).resolve().parent / "firmware" / "certs"
STACK_POLICY = "gridprint-node"  # created by infra/gridprint_infra/iot.py
THING_TYPE = "gridprint-node"


def policy_document(region: str, account: str, zone: str, node_id: str) -> dict[str, Any]:
    base = f"arn:aws:iot:{region}:{account}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "iot:Connect", "Resource": f"{base}:client/{node_id}"},
            {"Effect": "Allow", "Action": "iot:Publish",
             "Resource": f"{base}:topic/gridprint/{zone}/{node_id}"},
        ],
    }


def _exists(call: Any, missing_code: str = "ResourceNotFoundException") -> bool:
    try:
        call()
        return True
    except Exception as e:  # botocore ClientError
        if getattr(e, "response", {}).get("Error", {}).get("Code") == missing_code:
            return False
        raise


def provision(iot: Any, sts: Any, region: str, zone: str, node_id: str,
              out_dir: Path = CERT_DIR) -> dict[str, str]:
    account = sts.get_caller_identity()["Account"]
    # Prefer the shared policy and thing type of the infra IoT stack (thing policy variables);
    # fall back to a policy scoped to this one node when the stack is not deployed.
    if _exists(lambda: iot.get_policy(policyName=STACK_POLICY)):
        policy_name = STACK_POLICY
    else:
        policy_name = f"gridprint-node-{node_id}"
        if not _exists(lambda: iot.get_policy(policyName=policy_name)):
            iot.create_policy(policyName=policy_name,
                              policyDocument=json.dumps(policy_document(region, account, zone, node_id)))
    if not _exists(lambda: iot.describe_thing(thingName=node_id)):
        kw: dict[str, Any] = {"thingName": node_id,
                              "attributePayload": {"attributes": {"zone": zone, "app": "gridprint"}}}
        if _exists(lambda: iot.describe_thing_type(thingTypeName=THING_TYPE)):
            kw["thingTypeName"] = THING_TYPE
        iot.create_thing(**kw)
    cert = iot.create_keys_and_certificate(setAsActive=True)
    iot.attach_policy(policyName=policy_name, target=cert["certificateArn"])
    iot.attach_thing_principal(thingName=node_id, principal=cert["certificateArn"])
    endpoint = iot.describe_endpoint(endpointType="iot:Data-ATS")["endpointAddress"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "device.pem.crt").write_text(cert["certificatePem"])
    (out_dir / "private.pem.key").write_text(cert["keyPair"]["PrivateKey"])
    (out_dir / "endpoint.txt").write_text(endpoint + "\n")
    (out_dir / "certificate_arn.txt").write_text(cert["certificateArn"] + "\n")
    return {"thing": node_id, "policy": policy_name, "certificate_arn": cert["certificateArn"],
            "endpoint": endpoint, "topic": f"gridprint/{zone}/{node_id}", "cert_dir": str(out_dir)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--node-id", required=True)
    ap.add_argument("--zone", required=True)
    ap.add_argument("--region", default=None, help="default: the profile's region")
    ap.add_argument("--out", type=Path, default=CERT_DIR)
    a = ap.parse_args(argv)
    import boto3

    s = boto3.Session(profile_name=a.profile, region_name=a.region)
    region = s.region_name
    if not region:
        sys.exit("no region: pass --region or set one in the AWS profile")
    r = provision(s.client("iot"), s.client("sts"), region, a.zone, a.node_id, a.out)
    print(json.dumps(r, indent=1))
    print("Next: put AmazonRootCA1.pem in the cert directory and follow node/firmware/FLASHING.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
