"""IoT stack: Node thing type, device policy, topic rule -> ingest Lambda -> DynamoDB GridLog (SPEC 10.4).

Device identity: each Node is an IoT thing named `<node_id>` with the thing attribute `zone`. Its
X.509 certificate is created by a person (human task H2) and attached to the thing and to this policy.
The policy uses thing policy variables, so a Node can connect only with its own thing name as client ID
and publish only to `gridprint/<zone>/<node_id>`.
"""

from __future__ import annotations

from aws_cdk import Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_iot as iot
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from .compute import METRIC_NAMESPACE
from .config import REPO
from .data import DataStack

TOPIC_PREFIX = "gridprint"
THING_TYPE = "gridprint-node"
INGEST_DIR = REPO / "node" / "ingest"


def node_policy_document(partition: str, region: str, account: str) -> dict:
    thing = "${iot:Connection.Thing.ThingName}"
    zone = "${iot:Connection.Thing.Attributes[zone]}"
    base = f"arn:{partition}:iot:{region}:{account}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "iot:Connect",
                "Resource": f"{base}:client/{thing}",
                "Condition": {"Bool": {"iot:Connection.Thing.IsAttached": "true"}},
            },
            {
                "Effect": "Allow",
                "Action": "iot:Publish",
                "Resource": f"{base}:topic/{TOPIC_PREFIX}/{zone}/{thing}",
            },
        ],
    }


class IotStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, data: DataStack, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        iot.CfnThingType(
            self, "NodeThingType",
            thing_type_name=THING_TYPE,
            thing_type_properties=iot.CfnThingType.ThingTypePropertiesProperty(
                thing_type_description="GRIDPRINT grid-frequency Node (ESP32 + GPS PPS)",
                searchable_attributes=["zone"],
            ),
        )
        self.node_policy = iot.CfnPolicy(
            self, "NodePolicy",
            policy_name="gridprint-node",
            policy_document=node_policy_document(self.partition, self.region, self.account),
        )

        self.ingest_logs = logs.LogGroup(self, "IngestLogs", retention=logs.RetentionDays.ONE_MONTH)
        self.ingest_fn = lambda_.Function(
            self, "IngestFn",
            runtime=lambda_.Runtime.PYTHON_3_11,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(INGEST_DIR),
                                         exclude=["tests", "tests/*", "__pycache__", "*.pyc"]),
            timeout=Duration.seconds(10),
            memory_size=256,
            log_group=self.ingest_logs,
            logging_format=lambda_.LoggingFormat.JSON,
            environment={
                "GRIDPRINT_GRIDLOG_TABLE": data.gridlog.table_name,
                "GRIDPRINT_METRIC_NAMESPACE": METRIC_NAMESPACE,
            },
        )
        data.gridlog.grant_read_write_data(self.ingest_fn)

        self.rule = iot.CfnTopicRule(
            self, "IngestRule",
            topic_rule_payload=iot.CfnTopicRule.TopicRulePayloadProperty(
                sql=(f"SELECT *, topic(2) AS topic_zone, topic(3) AS topic_node "
                     f"FROM '{TOPIC_PREFIX}/+/+'"),
                aws_iot_sql_version="2016-03-23",
                rule_disabled=False,
                actions=[iot.CfnTopicRule.ActionProperty(
                    lambda_=iot.CfnTopicRule.LambdaActionProperty(function_arn=self.ingest_fn.function_arn))],
            ),
        )
        self.ingest_fn.add_permission(
            "AllowIotRule",
            principal=iam.ServicePrincipal("iot.amazonaws.com"),
            source_arn=self.rule.attr_arn,
            source_account=self.account,
        )
