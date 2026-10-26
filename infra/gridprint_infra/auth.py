"""Auth stack: Cognito user pool with the `reviewer` group (SPEC 10.1, 10.6, Part 13)."""

from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_cognito as cognito
from constructs import Construct

REVIEWER_GROUP = "reviewer"


class AuthStack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)
        # Reviewers are created by an administrator (no self sign-up). TOTP MFA is required because
        # reviewers approve CONTRADICTED verdicts (R3).
        self.user_pool = cognito.UserPool(
            self, "Reviewers",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            mfa=cognito.Mfa.REQUIRED,
            mfa_second_factor=cognito.MfaSecondFactor(otp=True, sms=False),
            password_policy=cognito.PasswordPolicy(min_length=12, require_digits=True, require_lowercase=True,
                                                   require_uppercase=True, require_symbols=True),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.reviewer_group = cognito.CfnUserPoolGroup(
            self, "ReviewerGroup",
            user_pool_id=self.user_pool.user_pool_id,
            group_name=REVIEWER_GROUP,
            description="Can see the review queue and approve or reject verdicts",
        )
        # Public SPA client (no secret). The API verifies Cognito JWTs and checks `cognito:groups`.
        self.web_client = self.user_pool.add_client(
            "WebClient",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True),
            prevent_user_existence_errors=True,
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(1),
        )
