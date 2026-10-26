"""Observability stack: CloudWatch dashboard and alarms (SPEC 10.6).

Application metrics are custom metrics in namespace `GRIDPRINT`, written as CloudWatch Embedded Metric
Format (EMF) lines in the structured JSON logs. Metric contract (emitters live in api/, agent/, node/ingest/):

| Metric               | Unit         | Dimensions   | Emitted by           |
|----------------------|--------------|--------------|----------------------|
| JobsCreated          | Count        | (none)       | API                  |
| JobsCompleted        | Count        | (none)       | worker               |
| StageLatencyMs       | Milliseconds | Stage        | worker (S1..S15)     |
| VerdictCount         | Count        | Verdict      | worker               |
| AgentIterations      | Count        | (none)       | worker (per job)     |
| Errors               | Count        | Service      | API, worker, ingest  |
| NodeFreshnessSeconds | Seconds      | Zone         | ingest Lambda        |

NodeFreshnessSeconds = ingest time minus the sample's t_utc_s. Missing data counts as breaching, so a
silent Node raises the alarm.
"""

from __future__ import annotations

from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_sns as sns
from constructs import Construct

from .api import ApiStack
from .compute import METRIC_NAMESPACE, ComputeStack
from .config import PREFIX, InfraConfig
from .iot import IotStack

STAGES = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11", "S12", "S13", "S14", "S15"]
VERDICTS = ["VERIFIED", "CONTRADICTED", "INCONCLUSIVE"]
SERVICES = ["api", "worker", "ingest"]


def m(name: str, stat: str = "Sum", period_min: int = 5, **dims: str) -> cw.Metric:
    return cw.Metric(namespace=METRIC_NAMESPACE, metric_name=name, statistic=stat,
                     period=Duration.minutes(period_min), dimensions_map=dims or None)


class ObservabilityStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: InfraConfig, compute: ComputeStack, api: ApiStack,
                 iot: IotStack, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        # Subscriptions (email of the on-call person) are added by a human (H1).
        self.alarm_topic = sns.Topic(self, "Alarms", display_name=f"{PREFIX} alarms",
                                     enforce_ssl=True)
        action = cw_actions.SnsAction(self.alarm_topic)

        errors = cw.MathExpression(
            expression=" + ".join(f"FILL(e{i}, 0)" for i in range(len(SERVICES))),
            using_metrics={f"e{i}": m("Errors", Service=s) for i, s in enumerate(SERVICES)},
            period=Duration.minutes(5), label="App errors")
        alarms: list[cw.Alarm] = []
        alarms.append(cw.Alarm(self, "AppErrors", metric=errors, threshold=0, evaluation_periods=1,
                               comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                               treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
                               alarm_description="Application errors reported in GRIDPRINT/Errors"))
        alarms.append(cw.Alarm(self, "IngestLambdaErrors", metric=iot.ingest_fn.metric_errors(),
                               threshold=0, evaluation_periods=1,
                               comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                               treat_missing_data=cw.TreatMissingData.NOT_BREACHING))
        alb5xx = api.service.load_balancer.metrics.http_code_target(
            code=elbv2.HttpCodeTarget.TARGET_5XX_COUNT, period=Duration.minutes(5), statistic="Sum")
        alarms.append(cw.Alarm(self, "ApiTarget5xx", metric=alb5xx, threshold=0, evaluation_periods=1,
                               comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                               treat_missing_data=cw.TreatMissingData.NOT_BREACHING))
        alarms.append(cw.Alarm(
            self, "DlqDepth",
            metric=compute.dlq.metric_approximate_number_of_messages_visible(period=Duration.minutes(5),
                                                                             statistic="Maximum"),
            threshold=0, evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
            alarm_description="Jobs failed DLQ_MAX_RECEIVES times and moved to the dead-letter queue"))
        for zone in cfg.node_zones:
            alarms.append(cw.Alarm(
                self, f"NodeFreshness{zone.replace('-', '')}",
                metric=m("NodeFreshnessSeconds", stat="Maximum", period_min=1, Zone=zone),
                threshold=cfg.freshness_limit_s, evaluation_periods=3,
                comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
                treat_missing_data=cw.TreatMissingData.BREACHING,
                alarm_description=f"Node data for zone {zone} older than grid.freshness_limit_s or missing"))
        for a in alarms:
            a.add_alarm_action(action)
        self.alarms = alarms

        dash = cw.Dashboard(self, "Dashboard", dashboard_name=PREFIX)
        dash.add_widgets(
            cw.GraphWidget(title="Jobs", left=[m("JobsCreated"), m("JobsCompleted")],
                           right=[compute.queue.metric_approximate_number_of_messages_visible(),
                                  compute.dlq.metric_approximate_number_of_messages_visible()], width=12),
            cw.GraphWidget(title="Verdict counts", left=[m("VerdictCount", Verdict=v) for v in VERDICTS],
                           stacked=True, width=12),
        )
        dash.add_widgets(
            cw.GraphWidget(title="Stage latency p95 (ms)",
                           left=[m("StageLatencyMs", stat="p95", Stage=s) for s in STAGES], width=12),
            cw.GraphWidget(title="Agent iterations per job",
                           left=[m("AgentIterations", stat="Average"), m("AgentIterations", stat="Maximum")],
                           width=12),
        )
        dash.add_widgets(
            cw.GraphWidget(title="Errors", left=[errors, iot.ingest_fn.metric_errors(), alb5xx], width=12),
            cw.GraphWidget(title="Node freshness (s)",
                           left=[m("NodeFreshnessSeconds", stat="Maximum", period_min=1, Zone=z)
                                 for z in cfg.node_zones],
                           left_annotations=[cw.HorizontalAnnotation(value=cfg.freshness_limit_s,
                                                                     label="freshness limit")],
                           width=12),
        )
        dash.add_widgets(cw.AlarmStatusWidget(title="Alarms", alarms=alarms, width=24))
