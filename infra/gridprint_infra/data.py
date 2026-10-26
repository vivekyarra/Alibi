"""Data stack: DynamoDB tables Jobs, Reviews, GridLog, TraceIndex with PITR (SPEC 10.4, 10.6)."""

from __future__ import annotations

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as ddb
from constructs import Construct


class DataStack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)

        def table(name: str, pk: str, sk: tuple[str, ddb.AttributeType] | None = None) -> ddb.Table:
            return ddb.Table(
                self, name,
                table_name=f"gridprint-{name}",
                partition_key=ddb.Attribute(name=pk, type=ddb.AttributeType.STRING),
                sort_key=ddb.Attribute(name=sk[0], type=sk[1]) if sk else None,
                billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
                encryption=ddb.TableEncryption.AWS_MANAGED,
                point_in_time_recovery_specification=ddb.PointInTimeRecoverySpecification(
                    point_in_time_recovery_enabled=True),
                removal_policy=RemovalPolicy.DESTROY,   # `make destroy` removes everything (SPEC 10.6)
            )

        # Key schema set by the lead (2026-10-26): Jobs, Reviews, TraceIndex use `pk` (String) only.
        self.jobs = table("Jobs", "pk")
        self.reviews = table("Reviews", "pk")
        self.trace_index = table("TraceIndex", "pk")
        # GridLog: PK `pk` = "zone#YYYYMMDD", SK `t` = epoch second (SPEC 10.4).
        self.gridlog = table("GridLog", "pk", ("t", ddb.AttributeType.NUMBER))

    @property
    def tables(self) -> list[ddb.Table]:
        return [self.jobs, self.reviews, self.gridlog, self.trace_index]
