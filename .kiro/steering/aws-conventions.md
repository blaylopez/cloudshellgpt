# AWS Conventions — CloudShellGPT

## Bedrock Usage

- Model: `anthropic.claude-3-5-sonnet-20241022-v2:0`
- API: Always use the Converse API (`client.converse()`), never the legacy `invoke_model`
- Temperature: 0.2 for translation (precision), 0.3 for explanations (more creative)
- Max tokens: 2048 for translations, 1024 for explanations
- System prompts: defined as class constants, never hardcoded inline
- Always handle `BedrockError` gracefully with user-facing message

## IAM & Credentials

- CloudShellGPT NEVER manages its own credentials — it uses the environment's AWS credentials
- Required permissions are documented, not assumed
- Minimum permissions needed:
  - `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream`
  - `ce:GetCostAndUsage` + `ce:GetCostForecast` (for cost preview)
  - `comprehend:DetectPiiEntities` (optional, opt-in)
- The tool's own permissions are SEPARATE from what the user can do with AWS CLI

## SDK Patterns

- Use `boto3.client()` not `boto3.resource()` (client is more predictable)
- Always specify `region_name` explicitly
- Handle `botocore.exceptions.ClientError` with meaningful error messages
- Retry transient errors (throttling, timeouts) with exponential backoff
- Set timeouts on all API calls

```python
# Good
client = boto3.client("bedrock-runtime", region_name=self.region)

# Bad — relies on implicit default
client = boto3.client("bedrock-runtime")
```

## CDK Conventions

- Stack naming: `CloudShellGPT-{Environment}` (e.g., `CloudShellGPT-Prod`)
- Resource naming: `csgpt-{resource}-{environment}` (e.g., `csgpt-audit-prod`)
- Always set `removal_policy`: RETAIN for prod, DESTROY for dev
- DynamoDB: PAY_PER_REQUEST billing (no provisioned capacity for a hackathon)
- Lambda: ARM_64 architecture, Python 3.12, X-Ray tracing enabled
- All secrets via environment variables, never hardcoded
- Encryption: AWS_MANAGED for DynamoDB, S3_MANAGED for buckets

## Safety Rules for Executor

- ONLY execute commands that start with `aws` (validated in executor.py)
- Timeout: 30s default, configurable
- Dry-run injection for destructive commands
- Never execute commands with `|`, `&&`, `;`, backticks, or `$(...)` (shell injection prevention)
- Audit BEFORE execution (log the intent before running the command)

## Cost Awareness

- Bedrock Claude 3.5 Sonnet: ~$0.003/1K input tokens, ~$0.015/1K output tokens
- Average request cost: ~$0.01-0.02
- Track costs in session via CostTracker
- Warn user if estimated resource cost > $100/month

## Region Strategy

- Default: us-east-1 (where Bedrock Claude is available)
- User can override via `--region` flag or config
- CloudShellGPT's own calls (Bedrock, Cost Explorer) always go to configured region
- User's AWS commands respect their own region (from env or flag)
