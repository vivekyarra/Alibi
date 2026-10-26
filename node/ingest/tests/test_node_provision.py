from __future__ import annotations

from botocore.exceptions import ClientError

from node import provision as prov


class FakeIot:
    """Test double for the boto3 IoT client calls made by node/provision.py."""

    def describe_thing(self, thingName):
        raise ClientError({"Error": {"Code": "ResourceNotFoundException", "Message": ""}}, "DescribeThing")

    def __init__(self, stack_deployed=False):
        self.calls = []
        self.stack_deployed = stack_deployed

    def get_policy(self, policyName):
        if self.stack_deployed and policyName == "gridprint-node":
            return {}
        raise ClientError({"Error": {"Code": "ResourceNotFoundException", "Message": ""}}, "GetPolicy")

    def describe_thing_type(self, thingTypeName):
        if self.stack_deployed:
            return {}
        raise ClientError({"Error": {"Code": "ResourceNotFoundException", "Message": ""}},
                          "DescribeThingType")

    def __getattr__(self, name):
        def call(**kw):
            self.calls.append((name, kw))
            if name == "create_keys_and_certificate":
                return {"certificateArn": "arn:cert", "certificatePem": "CERT",
                        "keyPair": {"PrivateKey": "KEY"}}
            if name == "describe_endpoint":
                return {"endpointAddress": "abc-ats.iot.us-east-1.amazonaws.com"}
            return {}
        return call


class FakeSts:
    def get_caller_identity(self):
        return {"Account": "123456789012"}


def test_policy_is_scoped_to_node_topic():
    doc = prov.policy_document("us-east-1", "123456789012", "IN", "node-01")
    res = [s["Resource"] for s in doc["Statement"]]
    assert res == ["arn:aws:iot:us-east-1:123456789012:client/node-01",
                   "arn:aws:iot:us-east-1:123456789012:topic/gridprint/IN/node-01"]


def test_provision_writes_certs(tmp_path):
    iot = FakeIot()
    r = prov.provision(iot, FakeSts(), "us-east-1", "IN", "node-01", tmp_path)
    names = [c[0] for c in iot.calls]
    assert names == ["create_policy", "create_thing", "create_keys_and_certificate", "attach_policy",
                     "attach_thing_principal", "describe_endpoint"]
    assert iot.calls[3][1]["policyName"] == "gridprint-node-node-01"
    assert (tmp_path / "private.pem.key").read_text() == "KEY"
    assert r["topic"] == "gridprint/IN/node-01"


def test_provision_uses_stack_policy_and_thing_type(tmp_path):
    iot = FakeIot(stack_deployed=True)
    r = prov.provision(iot, FakeSts(), "us-east-1", "IN", "node-01", tmp_path)
    calls = dict(iot.calls)
    assert "create_policy" not in calls
    assert calls["create_thing"]["thingTypeName"] == "gridprint-node"
    assert calls["create_thing"]["attributePayload"]["attributes"]["zone"] == "IN"
    assert calls["attach_policy"]["policyName"] == "gridprint-node" and r["policy"] == "gridprint-node"
