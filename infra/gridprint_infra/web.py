"""Web stack: S3 static site + CloudFront (origin access control) + WAF rate limits (SPEC 10.2, 10.6).

CloudFront web ACLs must be created in us-east-1 (scope CLOUDFRONT); config region is us-east-1, so the
web ACL lives in this stack. `/v1/*` goes to the internal API ALB through a CloudFront VPC origin.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_wafv2 as wafv2
from aws_cdk import custom_resources as cr
from constructs import Construct

from .api import ApiStack
from .config import PREFIX, REPO, InfraConfig
from .storage import StorageStack

WEB_DIST = REPO / "web" / "dist"


def rate_rule(name: str, priority: int, limit: int,
              scope_down: wafv2.CfnWebACL.StatementProperty | None = None) -> wafv2.CfnWebACL.RuleProperty:
    return wafv2.CfnWebACL.RuleProperty(
        name=name,
        priority=priority,
        action=wafv2.CfnWebACL.RuleActionProperty(block={}),
        statement=wafv2.CfnWebACL.StatementProperty(
            rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                limit=limit, aggregate_key_type="IP", evaluation_window_sec=300,
                scope_down_statement=scope_down)),
        visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
            cloud_watch_metrics_enabled=True, metric_name=name, sampled_requests_enabled=True),
    )


def job_create_scope_down() -> wafv2.CfnWebACL.StatementProperty:
    """Match POST requests whose path starts with /v1/jobs (anonymous upload creation)."""
    return wafv2.CfnWebACL.StatementProperty(and_statement=wafv2.CfnWebACL.AndStatementProperty(statements=[
        wafv2.CfnWebACL.StatementProperty(byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
            field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(method={}),
            positional_constraint="EXACTLY", search_string="POST",
            text_transformations=[wafv2.CfnWebACL.TextTransformationProperty(priority=0, type="NONE")])),
        wafv2.CfnWebACL.StatementProperty(byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
            field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(uri_path={}),
            positional_constraint="STARTS_WITH", search_string="/v1/jobs",
            text_transformations=[wafv2.CfnWebACL.TextTransformationProperty(priority=0, type="NONE")])),
    ]))


class WebStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, cfg: InfraConfig, api: ApiStack, storage: StorageStack,
                 **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        self.site = s3.Bucket(
            self, "Site",
            # Public static assets only; SSE-S3 keeps OAC simple. Video data never goes here.
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        self.web_acl = wafv2.CfnWebACL(
            self, "WebAcl",
            scope="CLOUDFRONT",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True, metric_name=f"{PREFIX}-web", sampled_requests_enabled=True),
            rules=[
                rate_rule("rate-all-per-ip", 0, cfg.waf_rate_limit_5min),
                rate_rule("rate-job-create-per-ip", 1, cfg.waf_job_create_limit_5min,
                          job_create_scope_down()),
            ],
        )

        api_origin = origins.VpcOrigin.with_application_load_balancer(
            api.service.load_balancer,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            http_port=80,
        )
        self.distribution = cloudfront.Distribution(
            self, "Cdn",
            default_root_object="index.html",
            web_acl_id=self.web_acl.attr_arn,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(self.site),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                "/v1/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                ),
            },
            # No error-response rewrite: it would also turn API 403/404 answers into index.html.
        )

        # Browsers PUT uploads to presigned S3 URLs (ContentType video/mp4). Allow PUT only from the
        # CloudFront origin. Set here because the domain exists only after the distribution is created.
        site_origin = f"https://{self.distribution.distribution_domain_name}"
        cors_call = cr.AwsSdkCall(
            service="S3",
            action="putBucketCors",
            parameters={
                "Bucket": storage.uploads.bucket_name,
                "CORSConfiguration": {"CORSRules": [{
                    "AllowedMethods": ["PUT"],
                    "AllowedOrigins": [site_origin],
                    "AllowedHeaders": ["Content-Type"],
                    "MaxAgeSeconds": 3000,
                }]},
            },
            physical_resource_id=cr.PhysicalResourceId.of(f"{PREFIX}-uploads-cors"),
        )
        cr.AwsCustomResource(
            self, "UploadsCors",
            on_create=cors_call,
            on_update=cors_call,
            policy=cr.AwsCustomResourcePolicy.from_statements([iam.PolicyStatement(
                actions=["s3:PutBucketCORS"], resources=[storage.uploads.bucket_arn])]),
            install_latest_aws_sdk=False,
        )

        if WEB_DIST.is_dir():
            s3deploy.BucketDeployment(
                self, "DeploySite",
                sources=[s3deploy.Source.asset(str(WEB_DIST))],
                destination_bucket=self.site,
                distribution=self.distribution,
                distribution_paths=["/*"],
            )

        CfnOutput(self, "SiteUrl", value=f"https://{self.distribution.distribution_domain_name}")
