"""Learning mode — interactive tutorials and command explanations."""

from __future__ import annotations

import boto3
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt


class TutorialRunner:
    """Runs interactive tutorials for AWS services."""

    TUTORIALS: dict[str, list[dict[str, str]]] = {
        "s3": [
            {
                "title": "S3 — Tu primer bucket",
                "command": "aws s3 mb s3://mi-primer-bucket-unico-12345",
                "explanation": "Crea un bucket. Los nombres son únicos globalmente.",
            },
            {
                "title": "S3 — Subir un archivo",
                "command": "aws s3 cp archivo.txt s3://mi-primer-bucket-unico-12345/",
                "explanation": "Copia un archivo local al bucket.",
            },
            {
                "title": "S3 — Listar contenido",
                "command": "aws s3 ls s3://mi-primer-bucket-unico-12345/ --recursive --human-readable",
                "explanation": "Lista archivos con tamaño legible.",
            },
        ],
        "ec2": [
            {
                "title": "EC2 — Listar instancias",
                "command": "aws ec2 describe-instances --query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType]' --output table",
                "explanation": "Lista instancias con ID, estado y tipo.",
            },
        ],
        "lambda": [
            {
                "title": "Lambda — Crear función",
                "command": "aws lambda create-function --function-name mi-funcion --runtime python3.12 --role arn:aws:iam::ACCOUNT:role/lambda-role --handler index.handler --zip-file fileb://function.zip",
                "explanation": "Crea Lambda. Necesitas un IAM role y un ZIP con tu código.",
            },
        ],
    }

    def __init__(self, topic: str) -> None:
        self.topic = topic
        self.console = Console()

    def run(self) -> None:
        """Run the tutorial interactively."""
        if self.topic not in self.TUTORIALS:
            available = ", ".join(self.TUTORIALS.keys())
            self.console.print(f"[red]Unknown topic: {self.topic}[/red]")
            self.console.print(f"[yellow]Available: {available}[/yellow]")
            return

        self.console.print(
            Panel(
                f"[bold]Tutorial: {self.topic.upper()}[/bold]\n"
                f"Aprenderás {len(self.TUTORIALS[self.topic])} comandos esenciales.",
                border_style="cyan",
            )
        )

        for i, step in enumerate(self.TUTORIALS[self.topic], 1):
            self.console.print(
                Panel(
                    f"[bold]{step['title']}[/bold]\n\n"
                    f"[cyan]{step['command']}[/cyan]\n\n"
                    f"{step['explanation']}",
                    title=f"Step {i}/{len(self.TUTORIALS[self.topic])}",
                    border_style="blue",
                )
            )
            action = Prompt.ask(
                "Press Enter to continue, 'r' to run, 'q' to quit",
                default="",
            )
            if action == "q":
                break
            elif action == "r":
                # Optionally execute via executor
                self.console.print(f"[dim]Would execute: {step['command']}[/dim]")


class Explainer:
    """Explains what AWS CLI commands do in detail."""

    MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    REGION = "us-east-1"

    EXPLAIN_SYSTEM_PROMPT = (
        "Explain AWS CLI commands in detail. For each command, break down:\n"
        "1. What service and operation it uses\n"
        "2. Each non-obvious flag and its purpose\n"
        "3. The expected output format\n"
        "4. Common pitfalls\n"
        "5. Link to relevant AWS docs (markdown format)\n\n"
        "Provide a clear, educational explanation. Use markdown."
    )

    def __init__(self, region: str = REGION) -> None:
        self.console = Console()
        self.bedrock = boto3.client("bedrock-runtime", region_name=region)

    def explain_sync(self, command: str) -> str:
        """Generate a detailed explanation of a command (sync, for MCP).

        Args:
            command: The AWS CLI command to explain.

        Returns:
            A markdown-formatted explanation string.
        """
        try:
            response = self.bedrock.converse(
                modelId=self.MODEL_ID,
                messages=[{"role": "user", "content": [{"text": command}]}],
                system=[{"text": self.EXPLAIN_SYSTEM_PROMPT}],
                inferenceConfig={"maxTokens": 1024, "temperature": 0.3},
            )
            result: str = response["output"]["message"]["content"][0]["text"]
            return result
        except Exception as e:
            return f"Error explaining command: {e}"

    def explain(self, command: str) -> None:
        """Explain a command interactively."""
        explanation = self.explain_sync(command)
        self.console.print(
            Panel(explanation, title="[bold]Explanation[/bold]", border_style="green")
        )

    def explain_last(self) -> None:
        """Explain the last command from audit log."""
        from cloudshellgpt.audit import AuditLogger

        audit = AuditLogger()
        entries = audit.tail(1)
        if not entries:
            self.console.print("[yellow]No previous commands found[/yellow]")
            return

        last_command = entries[-1]["command"]
        self.explain(str(last_command))
