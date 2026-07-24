"""AWS CDK Stack for CloudShellGPT — production infrastructure.

This stack creates the serverless backend for CloudShellGPT's cloud features:
- Audit log persistence (DynamoDB)
- Translation cache (DynamoDB + TTL)
- Observability (CloudWatch + X-Ray)
- Optional API Gateway for hosted mode
"""

from __future__ import annotations

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_apigatewayv2 as apigw,
)
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_s3 as s3,
)
from constructs import Construct


class CloudShellGPTStack(Stack):
    """Main stack for CloudShellGPT infrastructure."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment: str = "prod",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============================================================
        # DynamoDB Tables
        # ============================================================

        # Audit log table
        self.audit_table = dynamodb.Table(
            self,
            "AuditLogTable",
            table_name=f"csgpt-audit-{environment}",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True,
            removal_policy=RemovalPolicy.RETAIN if environment == "prod" else RemovalPolicy.DESTROY,
        )

        # Translation cache table
        self.cache_table = dynamodb.Table(
            self,
            "TranslationCacheTable",
            table_name=f"csgpt-cache-{environment}",
            partition_key=dynamodb.Attribute(
                name="intent_hash", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ============================================================
        # S3 Bucket — for analytics and aggregations
        # ============================================================

        self.analytics_bucket = s3.Bucket(
            self,
            "AnalyticsBucket",
            bucket_name=f"csgpt-analytics-{environment}-{self.account}-{self.region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="archive-old-data",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(90),
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(365),
                        ),
                    ],
                ),
            ],
            removal_policy=RemovalPolicy.RETAIN if environment == "prod" else RemovalPolicy.DESTROY,
        )

        # ============================================================
        # Lambda Functions
        # ============================================================

        # Shared execution role for Lambdas
        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSXRayDaemonWriteAccess"),
            ],
        )

        # Bedrock access policy
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
                ],
            )
        )

        # Cost Explorer access
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ce:GetCostAndUsage", "ce:GetCostForecast"],
                resources=["*"],
            )
        )

        # DynamoDB access
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query"],
                resources=[self.audit_table.table_arn, self.cache_table.table_arn],
            )
        )

        # S3 access
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:PutObject", "s3:GetObject"],
                resources=[self.analytics_bucket.arn_for_objects("*")],
            )
        )

        # Translator Lambda
        self.translator_fn = lambda_.Function(
            self,
            "TranslatorFunction",
            function_name=f"csgpt-translator-{environment}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            handler="handler.main",
            code=lambda_.Code.from_asset("../src/cloudshellgpt/lambda_translator"),
            role=lambda_role,
            memory_size=1024,
            timeout=Duration.seconds(30),
            environment={
                "AUDIT_TABLE": self.audit_table.table_name,
                "CACHE_TABLE": self.cache_table.table_name,
                "BEDROCK_MODEL_ID": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "ENVIRONMENT": environment,
            },
            tracing=lambda_.Tracing.ACTIVE,
            log_retention=logs.RetentionDays.ONE_MONTH
            if environment == "prod"
            else logs.RetentionDays.ONE_WEEK,
            reserved_concurrent_executions=100 if environment == "prod" else 10,
        )

        # ============================================================
        # API Gateway (HTTP API for hosted mode)
        # ============================================================

        self.http_api = apigw.HttpApi(
            self,
            "CloudShellGPTApi",
            api_name=f"csgpt-api-{environment}",
            description="CloudShellGPT hosted mode API",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[apigw.CorsHttpMethod.POST, apigw.CorsHttpMethod.GET],
                allow_headers=["*"],
            ),
        )

        # Add routes
        self.http_api.add_routes(
            path="/translate",
            methods=[apigw.HttpMethod.POST],
            integration=apigw.HttpLambdaIntegration(
                "TranslateIntegration", handler=self.translator_fn
            ),
        )

        self.http_api.add_routes(
            path="/execute",
            methods=[apigw.HttpMethod.POST],
            integration=apigw.HttpLambdaIntegration(
                "ExecuteIntegration", handler=self.translator_fn
            ),
        )

        # ============================================================
        # CloudWatch Dashboard
        # ============================================================

        self.dashboard = cloudwatch.Dashboard(
            self,
            "CloudShellGPTDashboard",
            dashboard_name=f"csgpt-{environment}",
        )

        # Latency widget
        self.dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="API Latency (ms)",
                left=[
                    self.translator_fn.metric_duration(statistic="p50", label="P50"),
                    self.translator_fn.metric_duration(statistic="p95", label="P95"),
                    self.translator_fn.metric_duration(statistic="p99", label="P99"),
                ],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="Invocations & Errors",
                left=[
                    self.translator_fn.metric_invocations(label="Invocations"),
                ],
                right=[
                    self.translator_fn.metric_errors(label="Errors"),
                ],
                width=12,
            ),
        )

        # ============================================================
        # Outputs
        # ============================================================

        CfnOutput(
            self,
            "ApiUrl",
            value=self.http_api.api_endpoint,
            description="HTTP API endpoint",
            export_name=f"csgpt-api-url-{environment}",
        )

        CfnOutput(
            self,
            "AuditTableName",
            value=self.audit_table.table_name,
            description="Audit log table name",
        )

        CfnOutput(
            self,
            "AnalyticsBucketName",
            value=self.analytics_bucket.bucket_name,
            description="Analytics bucket name",
        )


class CloudShellGPTDevStack(Stack):
    """Development environment stack — minimal, cost-optimized."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Just the audit table and a tiny Lambda for testing
        self.audit_table = dynamodb.Table(
            self,
            "DevAuditTable",
            table_name="csgpt-audit-dev",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        CfnOutput(self, "DevTableName", value=self.audit_table.table_name)
