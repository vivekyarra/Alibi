"""AI stack: IAM permission for the pinned Bedrock model only (SPEC 10.6, V6).

The policy allows bedrock:InvokeModel, InvokeModelWithResponseStream and Converse (Converse is
authorized through the InvokeModel actions) on:
- the configured inference profile in this account and region, and
- the underlying foundation model the profile routes to. A cross-Region (`global.`/`us.`...) profile
  can route to any Region, so the foundation-model ARN uses a Region wildcard and the global form
  `arn:aws:bedrock:::foundation-model/<id>`. No other model is allowed.
"""

from __future__ import annotations

from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

from .config import InfraConfig, foundation_model_id


def bedrock_resource_arns(stack: Stack, model_id: str) -> list[str]:
    fm = foundation_model_id(model_id)
    arns = [
        f"arn:{stack.partition}:bedrock:*::foundation-model/{fm}",
        f"arn:{stack.partition}:bedrock:::foundation-model/{fm}",
    ]
    if fm != model_id:
        profile = f"arn:{stack.partition}:bedrock:{stack.region}:{stack.account}:inference-profile/{model_id}"
        arns.insert(0, profile)
    return arns


class AiStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: InfraConfig, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        self.invoke_policy = iam.ManagedPolicy(
            self, "BedrockInvokePinnedModel",
            description=f"Invoke only {cfg.bedrock_model_id} and its foundation model",
            statements=[iam.PolicyStatement(
                sid="InvokePinnedModelOnly",
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=bedrock_resource_arns(self, cfg.bedrock_model_id),
            )],
        )
