#!/usr/bin/env python3
"""CDK app entry point for CloudShellGPT infrastructure."""

import os

import aws_cdk as cdk
from cloudshellgpt_stack import CloudShellGPTDevStack, CloudShellGPTStack

app = cdk.App()

environment = app.node.try_get_context("environment") or "prod"
env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

if environment == "dev":
    CloudShellGPTDevStack(app, "CloudShellGPT-Dev", env=env)
else:
    CloudShellGPTStack(
        app,
        f"CloudShellGPT-{environment.title()}",
        environment=environment,
        env=env,
    )

app.synth()
