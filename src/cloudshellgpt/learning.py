"""Learning mode — interactive tutorials and command explanations."""

from __future__ import annotations

import re

import boto3
from pydantic import BaseModel
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
            {
                "title": "S3 — Generar URL pre-firmada",
                "command": "aws s3 presign s3://mi-primer-bucket-unico-12345/archivo.txt --expires-in 3600",
                "explanation": (
                    "Genera una URL temporal (1 hora) para compartir un objeto privado "
                    "sin cambiar permisos del bucket. Ideal para dar acceso temporal a "
                    "usuarios que no tienen credenciales AWS."
                ),
            },
            {
                "title": "S3 — Configurar política de bucket",
                "command": (
                    "aws s3api put-bucket-policy --bucket mi-primer-bucket-unico-12345 "
                    "--policy file://policy.json"
                ),
                "explanation": (
                    "Aplica una política JSON al bucket para controlar acceso. "
                    "Las políticas de bucket permiten definir reglas granulares: "
                    "quién puede leer, escribir o listar objetos. El archivo policy.json "
                    "debe seguir el formato de IAM Policy."
                ),
            },
        ],
        "ec2": [
            {
                "title": "EC2 — Listar instancias",
                "command": (
                    "aws ec2 describe-instances "
                    "--query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType]' "
                    "--output table"
                ),
                "explanation": (
                    "Lista todas las instancias con su ID, estado y tipo. "
                    "El flag --query usa JMESPath para filtrar la respuesta JSON "
                    "y --output table la muestra en formato tabular legible."
                ),
            },
            {
                "title": "EC2 — Lanzar una instancia",
                "command": (
                    "aws ec2 run-instances --image-id ami-0c02fb55956c7d316 "
                    "--instance-type t2.micro --key-name mi-key-pair "
                    "--security-group-ids sg-0123456789abcdef0 --count 1"
                ),
                "explanation": (
                    "Lanza una instancia EC2. Necesitas: una AMI (imagen base), "
                    "un tipo de instancia (t2.micro es capa gratuita), un key pair "
                    "para acceso SSH y un security group que defina reglas de red."
                ),
            },
            {
                "title": "EC2 — Detener una instancia",
                "command": "aws ec2 stop-instances --instance-ids i-0123456789abcdef0",
                "explanation": (
                    "Detiene una instancia sin terminarla. La instancia conserva "
                    "su volumen EBS y configuración. Dejas de pagar por cómputo "
                    "pero sigues pagando por el almacenamiento EBS asociado."
                ),
            },
            {
                "title": "EC2 — Crear security group",
                "command": (
                    "aws ec2 create-security-group --group-name mi-sg-web "
                    "--description 'Security group para servidor web' "
                    "--vpc-id vpc-0123456789abcdef0"
                ),
                "explanation": (
                    "Crea un security group (firewall virtual). Por defecto permite "
                    "todo el tráfico saliente pero bloquea todo el entrante. "
                    "Después debes agregar reglas de ingreso con "
                    "authorize-security-group-ingress."
                ),
            },
            {
                "title": "EC2 — Crear key pair",
                "command": (
                    "aws ec2 create-key-pair --key-name mi-key-pair "
                    "--query 'KeyMaterial' --output text > mi-key-pair.pem"
                ),
                "explanation": (
                    "Crea un par de claves para acceso SSH a instancias. "
                    "La clave privada solo se muestra una vez al crearla. "
                    "Guárdala en un archivo .pem y protégela con chmod 400."
                ),
            },
        ],
        "lambda": [
            {
                "title": "Lambda — Crear función",
                "command": (
                    "aws lambda create-function --function-name mi-funcion "
                    "--runtime python3.12 --role arn:aws:iam::123456789012:role/lambda-role "
                    "--handler index.handler --zip-file fileb://function.zip"
                ),
                "explanation": (
                    "Crea una función Lambda. Necesitas: un IAM role con permisos "
                    "de ejecución, un runtime (python3.12), un handler (archivo.función) "
                    "y un ZIP con tu código. El role debe tener la política "
                    "AWSLambdaBasicExecutionRole como mínimo."
                ),
            },
            {
                "title": "Lambda — Invocar función",
                "command": (
                    "aws lambda invoke --function-name mi-funcion "
                    '--payload \'{"key": "value"}\' --cli-binary-format raw-in-base64-out '
                    "response.json"
                ),
                "explanation": (
                    "Invoca la función de forma síncrona y guarda la respuesta en un archivo. "
                    "El flag --cli-binary-format raw-in-base64-out permite enviar JSON plano "
                    "sin codificarlo en base64. Útil para probar funciones rápidamente."
                ),
            },
            {
                "title": "Lambda — Actualizar código",
                "command": (
                    "aws lambda update-function-code --function-name mi-funcion "
                    "--zip-file fileb://function.zip --publish"
                ),
                "explanation": (
                    "Actualiza el código de una función existente con un nuevo ZIP. "
                    "El flag --publish crea una nueva versión inmutable, lo que permite "
                    "hacer rollback si algo falla. Sin --publish se actualiza solo $LATEST."
                ),
            },
            {
                "title": "Lambda — Ver logs recientes",
                "command": (
                    "aws logs filter-log-events "
                    "--log-group-name /aws/lambda/mi-funcion "
                    "--start-time $(date -d '10 minutes ago' +%s)000 "
                    "--query 'events[].message' --output text"
                ),
                "explanation": (
                    "Consulta los logs de CloudWatch de tu función Lambda. "
                    "Cada invocación genera logs con START, END y REPORT. "
                    "El REPORT incluye duración, memoria usada y si hubo errores. "
                    "Fundamental para depurar funciones en la nube."
                ),
            },
            {
                "title": "Lambda — Listar funciones",
                "command": (
                    "aws lambda list-functions "
                    "--query 'Functions[].[FunctionName,Runtime,LastModified]' "
                    "--output table"
                ),
                "explanation": (
                    "Lista todas las funciones Lambda en la región actual con su nombre, "
                    "runtime y última modificación. Útil para auditar qué funciones "
                    "tienes desplegadas y cuáles podrían necesitar actualización de runtime."
                ),
            },
        ],
        "dynamodb": [
            {
                "title": "DynamoDB — Crear tabla",
                "command": (
                    "aws dynamodb create-table --table-name mi-tabla "
                    "--attribute-definitions AttributeName=id,AttributeType=S "
                    "--key-schema AttributeName=id,KeyType=HASH "
                    "--billing-mode PAY_PER_REQUEST"
                ),
                "explanation": (
                    "Crea una tabla DynamoDB con clave primaria tipo string (S). "
                    "PAY_PER_REQUEST significa que pagas solo por las lecturas y "
                    "escrituras que hagas, sin provisionar capacidad. Ideal para "
                    "cargas de trabajo impredecibles o en desarrollo."
                ),
            },
            {
                "title": "DynamoDB — Insertar un item",
                "command": (
                    "aws dynamodb put-item --table-name mi-tabla "
                    '--item \'{"id": {"S": "001"}, "nombre": {"S": "Ejemplo"}, '
                    '"activo": {"BOOL": true}}\''
                ),
                "explanation": (
                    "Inserta un item en la tabla. DynamoDB usa un formato JSON especial "
                    "donde cada valor indica su tipo: S (string), N (número), BOOL (booleano), "
                    "L (lista), M (mapa). Si el item con esa clave ya existe, se sobrescribe."
                ),
            },
            {
                "title": "DynamoDB — Obtener un item",
                "command": (
                    "aws dynamodb get-item --table-name mi-tabla "
                    '--key \'{"id": {"S": "001"}}\' '
                    "--consistent-read"
                ),
                "explanation": (
                    "Recupera un item por su clave primaria. El flag --consistent-read "
                    "garantiza leer la versión más reciente (lectura fuertemente consistente). "
                    "Sin ese flag, podrías obtener datos ligeramente desactualizados "
                    "pero con menor latencia y costo."
                ),
            },
            {
                "title": "DynamoDB — Query por clave",
                "command": (
                    "aws dynamodb query --table-name mi-tabla "
                    "--key-condition-expression 'id = :valor' "
                    '--expression-attribute-values \'{":valor": {"S": "001"}}\''
                ),
                "explanation": (
                    "Query busca items por condición de clave. Es eficiente porque "
                    "usa el índice de la tabla. Puedes combinar con --filter-expression "
                    "para filtrar resultados adicionales después de la búsqueda por clave."
                ),
            },
            {
                "title": "DynamoDB — Scan completo",
                "command": ("aws dynamodb scan --table-name mi-tabla --select COUNT"),
                "explanation": (
                    "Scan lee TODOS los items de la tabla. Con --select COUNT solo "
                    "devuelve la cantidad sin los datos. Evita scan en producción: "
                    "es costoso y lento en tablas grandes. Usa query con condiciones "
                    "de clave siempre que sea posible."
                ),
            },
        ],
        "iam": [
            {
                "title": "IAM — Listar usuarios",
                "command": (
                    "aws iam list-users --query 'Users[].[UserName,CreateDate]' --output table"
                ),
                "explanation": (
                    "Lista todos los usuarios IAM de la cuenta con su nombre y fecha "
                    "de creación. Útil para auditar quién tiene acceso a la cuenta. "
                    "Recuerda que el usuario root no aparece aquí."
                ),
            },
            {
                "title": "IAM — Crear usuario",
                "command": "aws iam create-user --user-name nuevo-desarrollador",
                "explanation": (
                    "Crea un nuevo usuario IAM. El usuario se crea sin permisos ni "
                    "credenciales. Después necesitas: 1) Adjuntar una política para "
                    "dar permisos, 2) Crear access keys o contraseña de consola "
                    "según el tipo de acceso que necesite."
                ),
            },
            {
                "title": "IAM — Adjuntar política a usuario",
                "command": (
                    "aws iam attach-user-policy --user-name nuevo-desarrollador "
                    "--policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess"
                ),
                "explanation": (
                    "Adjunta una política administrada al usuario. Las políticas "
                    "administradas por AWS (como ReadOnlyAccess) son mantenidas "
                    "por Amazon. También puedes crear políticas personalizadas. "
                    "Principio de mínimo privilegio: da solo los permisos necesarios."
                ),
            },
            {
                "title": "IAM — Crear rol",
                "command": (
                    "aws iam create-role --role-name mi-rol-lambda "
                    "--assume-role-policy-document file://trust-policy.json"
                ),
                "explanation": (
                    "Crea un rol IAM. Los roles son identidades que los servicios AWS "
                    "(como Lambda o EC2) asumen para obtener permisos temporales. "
                    "El trust-policy.json define QUIÉN puede asumir el rol "
                    "(ej: lambda.amazonaws.com)."
                ),
            },
            {
                "title": "IAM — Listar roles",
                "command": ("aws iam list-roles --query 'Roles[].[RoleName,Arn]' --output table"),
                "explanation": (
                    "Lista todos los roles IAM con su nombre y ARN. "
                    "Los roles son fundamentales en AWS: cada servicio que necesite "
                    "interactuar con otros servicios usa un rol. Revisa periódicamente "
                    "para eliminar roles no utilizados (principio de mínimo privilegio)."
                ),
            },
        ],
        "vpc": [
            {
                "title": "VPC — Listar VPCs existentes",
                "command": (
                    "aws ec2 describe-vpcs "
                    "--query 'Vpcs[].[VpcId,CidrBlock,IsDefault]' --output table"
                ),
                "explanation": (
                    "Lista todas las VPCs de la región con su ID, rango CIDR y si es "
                    "la VPC por defecto. Toda cuenta AWS tiene una VPC default en cada "
                    "región. Las VPCs son redes virtuales aisladas donde viven tus recursos."
                ),
            },
            {
                "title": "VPC — Crear una VPC",
                "command": (
                    "aws ec2 create-vpc --cidr-block 10.0.0.0/16 "
                    "--tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=mi-vpc}]'"
                ),
                "explanation": (
                    "Crea una VPC con un bloque CIDR /16 (65,536 IPs). "
                    "El CIDR define el rango de IPs privadas disponibles. "
                    "Después necesitas crear subnets, un Internet Gateway "
                    "y tablas de ruteo para que los recursos tengan conectividad."
                ),
            },
            {
                "title": "VPC — Crear subnet",
                "command": (
                    "aws ec2 create-subnet --vpc-id vpc-0123456789abcdef0 "
                    "--cidr-block 10.0.1.0/24 --availability-zone us-east-1a"
                ),
                "explanation": (
                    "Crea una subnet dentro de la VPC en una zona de disponibilidad "
                    "específica. Un /24 da 256 IPs (251 usables, AWS reserva 5). "
                    "Las subnets pueden ser públicas (con ruta a Internet Gateway) "
                    "o privadas (sin acceso directo a internet)."
                ),
            },
            {
                "title": "VPC — Crear security group en VPC",
                "command": (
                    "aws ec2 create-security-group --group-name sg-web "
                    "--description 'Permite HTTP y HTTPS' "
                    "--vpc-id vpc-0123456789abcdef0"
                ),
                "explanation": (
                    "Crea un security group asociado a tu VPC. Los security groups "
                    "actúan como firewalls virtuales a nivel de instancia. "
                    "Por defecto permiten todo el tráfico saliente y bloquean "
                    "todo el entrante. Debes agregar reglas de ingreso explícitas."
                ),
            },
            {
                "title": "VPC — Ver security groups",
                "command": (
                    "aws ec2 describe-security-groups "
                    "--filters Name=vpc-id,Values=vpc-0123456789abcdef0 "
                    "--query 'SecurityGroups[].[GroupId,GroupName,Description]' "
                    "--output table"
                ),
                "explanation": (
                    "Lista los security groups de una VPC específica. "
                    "Filtra por vpc-id para ver solo los grupos relevantes. "
                    "Revisa periódicamente las reglas para asegurar que no haya "
                    "puertos innecesariamente abiertos (buena práctica de seguridad)."
                ),
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

    MODEL_ID = "us.anthropic.claude-sonnet-4-6"
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


# ---------------------------------------------------------------------------
# Pydantic models for learning features
# ---------------------------------------------------------------------------


class FlagExplanation(BaseModel):
    """Explanation of a single CLI flag/option."""

    flag: str
    explanation: str


class RelatedSuggestion(BaseModel):
    """A related command suggestion with description."""

    command: str
    description: str


# ---------------------------------------------------------------------------
# PostExecutionTips — rule-based educational tips after command execution
# ---------------------------------------------------------------------------


class PostExecutionTips:
    """Provides educational tips after a command runs.

    Uses a static dictionary of tips keyed by service+action.
    No Bedrock call needed — purely rule-based.
    """

    TIPS: dict[str, str] = {
        # S3
        "s3 ls": ("Tip: Use --human-readable for friendlier sizes"),
        "s3 cp": ("Tip: Use --recursive to copy entire directories"),
        "s3 sync": ("Tip: Use --delete to remove files in dest that don't exist in source"),
        "s3 mb": ("Tip: Bucket names must be globally unique across all AWS accounts"),
        "s3 rb": ("Tip: Use --force to delete a non-empty bucket"),
        "s3 rm": ("Tip: Use --recursive to delete all objects in a prefix"),
        "s3api list-buckets": ("Tip: Use --query 'Buckets[].Name' to get just bucket names"),
        "s3api put-object": ("Tip: Use --server-side-encryption AES256 to encrypt at rest"),
        # EC2
        "ec2 describe-instances": ("Tip: Use --query to filter output with JMESPath"),
        "ec2 run-instances": ("Tip: Use --dry-run first to verify permissions without launching"),
        "ec2 start-instances": (
            "Tip: Use --instance-ids with multiple IDs to start several at once"
        ),
        "ec2 stop-instances": ("Tip: Use --hibernate to save instance memory state"),
        "ec2 terminate-instances": (
            "Tip: Enable termination protection to prevent accidental deletion"
        ),
        "ec2 describe-security-groups": (
            "Tip: Use --filters Name=group-name,Values=my-sg to narrow results"
        ),
        "ec2 create-security-group": (
            "Tip: Remember to add ingress rules — new groups deny all inbound"
        ),
        # Lambda
        "lambda list-functions": ("Tip: Use --query 'Functions[].FunctionName' for just names"),
        "lambda invoke": ("Tip: Use --log-type Tail to see execution logs inline"),
        "lambda create-function": ("Tip: Use --timeout and --memory-size to tune performance"),
        "lambda update-function-code": ("Tip: Use --publish to create a new version on update"),
        # IAM
        "iam list-users": ("Tip: Use --query 'Users[].UserName' for a clean list"),
        "iam create-user": ("Tip: Don't forget to attach a policy — new users have no permissions"),
        "iam list-roles": ("Tip: Use --path-prefix to filter roles by organizational path"),
        # DynamoDB
        "dynamodb list-tables": ("Tip: Use --query 'TableNames' to get just the names"),
        "dynamodb scan": ("Tip: Avoid scan in production — use query with key conditions instead"),
        "dynamodb put-item": (
            "Tip: Use --condition-expression to prevent overwriting existing items"
        ),
        # CloudFormation
        "cloudformation list-stacks": ("Tip: Use --stack-status-filter to show only active stacks"),
        "cloudformation deploy": (
            "Tip: Use --no-execute-changeset to preview changes before applying"
        ),
        # RDS
        "rds describe-db-instances": (
            "Tip: Use --query to extract specific fields like endpoint and status"
        ),
        "rds create-db-instance": ("Tip: Use --multi-az for production workloads"),
    }

    def get_tip(self, command: str) -> str | None:
        """Return a contextual tip for the given command, or None.

        Args:
            command: The AWS CLI command that was executed (e.g. "aws s3 ls ...").

        Returns:
            A tip string if one matches the service+action, otherwise None.
        """
        try:
            normalized = self._extract_service_action(command)
            if normalized:
                return self.TIPS.get(normalized)
        except Exception:
            pass
        return None

    def _extract_service_action(self, command: str) -> str | None:
        """Extract service and action from an AWS CLI command.

        Args:
            command: Full AWS CLI command string.

        Returns:
            A string like "s3 ls" or "ec2 describe-instances", or None.
        """
        # Remove leading "aws " if present
        stripped = command.strip()
        if stripped.startswith("aws "):
            stripped = stripped[4:]

        parts = stripped.split()
        if len(parts) < 2:
            return None

        service = parts[0]
        action = parts[1]

        # Skip if action looks like a flag
        if action.startswith("-"):
            return None

        return f"{service} {action}"


# ---------------------------------------------------------------------------
# FlagExplainer — rule-based explanation of common AWS CLI flags
# ---------------------------------------------------------------------------


class FlagExplainer:
    """Explains each flag/option used in an AWS CLI command.

    Rule-based: uses a dictionary of common AWS CLI flags and their explanations.
    """

    FLAG_DEFINITIONS: dict[str, str] = {
        "--output": "Sets the output format (json, text, table, yaml)",
        "--query": "Filters output using JMESPath expressions",
        "--region": "Overrides the default AWS region for this command",
        "--profile": "Uses a named profile from ~/.aws/credentials",
        "--no-paginate": "Disables automatic pagination of results",
        "--dry-run": "Checks permissions without actually executing the command",
        "--recursive": "Applies the operation to all objects under a prefix",
        "--force": "Skips confirmation prompts and forces the operation",
        "--human-readable": "Displays file sizes in human-readable format (KB, MB, GB)",
        "--filters": "Applies server-side filters to narrow results",
        "--max-items": "Limits the total number of items returned",
        "--page-size": "Controls how many items are fetched per API call",
        "--no-verify-ssl": "Disables SSL certificate verification (not recommended)",
        "--endpoint-url": "Overrides the service endpoint URL",
        "--cli-input-json": "Reads parameters from a JSON file",
        "--cli-input-yaml": "Reads parameters from a YAML file",
        "--generate-cli-skeleton": "Generates a JSON skeleton for the command input",
        "--no-sign-request": "Sends request without signing (for public resources)",
        "--debug": "Enables debug logging for troubleshooting",
        "--color": "Controls colored output (on, off, auto)",
        "--no-cli-pager": "Disables the CLI pager for output",
        "--instance-ids": "Specifies one or more EC2 instance IDs",
        "--function-name": "Specifies the Lambda function name or ARN",
        "--bucket": "Specifies the S3 bucket name",
        "--key": "Specifies the S3 object key",
        "--table-name": "Specifies the DynamoDB table name",
        "--stack-name": "Specifies the CloudFormation stack name",
        "--role-arn": "Specifies the IAM role ARN to assume",
        "--tags": "Adds key-value tags to the resource",
        "--server-side-encryption": "Enables server-side encryption for stored objects",
        "--acl": "Sets the access control list for the resource",
        "--include": "Includes only files matching the pattern",
        "--exclude": "Excludes files matching the pattern",
        "--delete": "Removes files in destination not in source (sync)",
        "--exact-timestamps": "Compares exact timestamps during sync (not just size)",
        "--sse": "Specifies server-side encryption algorithm",
        "--storage-class": "Sets the S3 storage class (STANDARD, IA, GLACIER, etc.)",
        "--content-type": "Sets the MIME type of the uploaded object",
        "--metadata": "Adds custom metadata to the object",
        "--grants": "Sets permissions using grant format",
        "--source-region": "Specifies the source region for cross-region copies",
        "--copy-source": "Specifies the source object for server-side copy",
        "--multi-az": "Enables Multi-AZ deployment for high availability",
        "--publicly-accessible": "Makes the resource accessible from the internet",
        "--no-publicly-accessible": "Blocks public access to the resource",
        "--skip-final-snapshot": "Skips creating a final snapshot before deletion",
        "--force-delete": "Forces deletion without recovery options",
    }

    def explain_flags(self, command: str) -> list[FlagExplanation]:
        """Explain each flag/option in the given AWS CLI command.

        Args:
            command: The AWS CLI command with flags to explain.

        Returns:
            A list of FlagExplanation objects for each recognized flag.
        """
        try:
            flags = self._extract_flags(command)
            explanations: list[FlagExplanation] = []
            for flag in flags:
                definition = self.FLAG_DEFINITIONS.get(flag)
                if definition:
                    explanations.append(FlagExplanation(flag=flag, explanation=definition))
            return explanations
        except Exception:
            return []

    def _extract_flags(self, command: str) -> list[str]:
        """Extract all --flags from a command string.

        Args:
            command: Full AWS CLI command.

        Returns:
            List of unique flag names (e.g. ["--output", "--query"]).
        """
        # Match --flag-name patterns (long flags only)
        matches = re.findall(r"(--[a-zA-Z][a-zA-Z0-9-]*)", command)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for flag in matches:
            if flag not in seen:
                seen.add(flag)
                unique.append(flag)
        return unique


# ---------------------------------------------------------------------------
# RelatedCommands — suggests related commands based on the current one
# ---------------------------------------------------------------------------


class RelatedCommands:
    """Suggests related commands the user might want to run next.

    Rule-based mapping of service+action to related commands.
    """

    RELATED: dict[str, list[RelatedSuggestion]] = {
        # S3
        "s3 ls": [
            RelatedSuggestion(
                command="aws s3 cp",
                description="Copy files to/from S3",
            ),
            RelatedSuggestion(
                command="aws s3 sync",
                description="Sync a local directory with S3",
            ),
            RelatedSuggestion(
                command="aws s3 presign",
                description="Generate a pre-signed URL for temporary access",
            ),
        ],
        "s3 cp": [
            RelatedSuggestion(
                command="aws s3 ls",
                description="List objects to verify the copy",
            ),
            RelatedSuggestion(
                command="aws s3 sync",
                description="Sync entire directories instead of single files",
            ),
        ],
        "s3 sync": [
            RelatedSuggestion(
                command="aws s3 ls",
                description="List objects to verify sync results",
            ),
            RelatedSuggestion(
                command="aws s3 rm --recursive",
                description="Remove all objects under a prefix",
            ),
        ],
        "s3 mb": [
            RelatedSuggestion(
                command="aws s3 ls",
                description="List all buckets to verify creation",
            ),
            RelatedSuggestion(
                command="aws s3 cp",
                description="Upload your first file to the new bucket",
            ),
        ],
        "s3 rb": [
            RelatedSuggestion(
                command="aws s3 ls",
                description="Verify the bucket was removed",
            ),
        ],
        # EC2
        "ec2 describe-instances": [
            RelatedSuggestion(
                command="aws ec2 start-instances",
                description="Start stopped instances",
            ),
            RelatedSuggestion(
                command="aws ec2 stop-instances",
                description="Stop running instances",
            ),
            RelatedSuggestion(
                command="aws ec2 create-tags",
                description="Tag instances for organization",
            ),
        ],
        "ec2 run-instances": [
            RelatedSuggestion(
                command="aws ec2 describe-instances",
                description="Check the status of your new instance",
            ),
            RelatedSuggestion(
                command="aws ec2 create-tags",
                description="Tag the instance for organization",
            ),
            RelatedSuggestion(
                command="aws ec2 describe-security-groups",
                description="Verify security group rules",
            ),
        ],
        "ec2 stop-instances": [
            RelatedSuggestion(
                command="aws ec2 start-instances",
                description="Start the instances again",
            ),
            RelatedSuggestion(
                command="aws ec2 describe-instances",
                description="Verify the instances are stopped",
            ),
        ],
        "ec2 terminate-instances": [
            RelatedSuggestion(
                command="aws ec2 describe-instances",
                description="Verify instances are terminated",
            ),
            RelatedSuggestion(
                command="aws ec2 release-address",
                description="Release any associated Elastic IPs",
            ),
        ],
        "ec2 create-security-group": [
            RelatedSuggestion(
                command="aws ec2 authorize-security-group-ingress",
                description="Add inbound rules to the new group",
            ),
            RelatedSuggestion(
                command="aws ec2 describe-security-groups",
                description="Verify the group was created",
            ),
        ],
        # Lambda
        "lambda list-functions": [
            RelatedSuggestion(
                command="aws lambda invoke",
                description="Invoke a function to test it",
            ),
            RelatedSuggestion(
                command="aws lambda get-function",
                description="Get details about a specific function",
            ),
        ],
        "lambda create-function": [
            RelatedSuggestion(
                command="aws lambda invoke",
                description="Test the new function",
            ),
            RelatedSuggestion(
                command="aws lambda list-functions",
                description="Verify the function appears in the list",
            ),
        ],
        "lambda invoke": [
            RelatedSuggestion(
                command="aws logs filter-log-events",
                description="Check CloudWatch logs for execution details",
            ),
            RelatedSuggestion(
                command="aws lambda update-function-code",
                description="Update the function code",
            ),
        ],
        # IAM
        "iam list-users": [
            RelatedSuggestion(
                command="aws iam list-user-policies",
                description="Check policies attached to a user",
            ),
            RelatedSuggestion(
                command="aws iam create-user",
                description="Create a new IAM user",
            ),
        ],
        "iam create-user": [
            RelatedSuggestion(
                command="aws iam attach-user-policy",
                description="Attach a policy to the new user",
            ),
            RelatedSuggestion(
                command="aws iam create-access-key",
                description="Create access keys for programmatic access",
            ),
        ],
        # DynamoDB
        "dynamodb list-tables": [
            RelatedSuggestion(
                command="aws dynamodb describe-table",
                description="Get details about a specific table",
            ),
            RelatedSuggestion(
                command="aws dynamodb scan",
                description="Read all items from a table",
            ),
        ],
        "dynamodb scan": [
            RelatedSuggestion(
                command="aws dynamodb query",
                description="Query items by key condition (more efficient)",
            ),
            RelatedSuggestion(
                command="aws dynamodb put-item",
                description="Insert a new item into the table",
            ),
        ],
        # RDS
        "rds describe-db-instances": [
            RelatedSuggestion(
                command="aws rds create-db-snapshot",
                description="Create a snapshot for backup",
            ),
            RelatedSuggestion(
                command="aws rds modify-db-instance",
                description="Modify instance settings",
            ),
        ],
    }

    def suggest(self, command: str) -> list[RelatedSuggestion]:
        """Suggest related commands based on the current one.

        Args:
            command: The AWS CLI command that was executed.

        Returns:
            A list of related command suggestions, or an empty list.
        """
        try:
            key = self._extract_service_action(command)
            if key:
                return self.RELATED.get(key, [])
        except Exception:
            pass
        return []

    def _extract_service_action(self, command: str) -> str | None:
        """Extract service and action from an AWS CLI command.

        Args:
            command: Full AWS CLI command string.

        Returns:
            A string like "s3 ls" or "ec2 run-instances", or None.
        """
        stripped = command.strip()
        if stripped.startswith("aws "):
            stripped = stripped[4:]

        parts = stripped.split()
        if len(parts) < 2:
            return None

        service = parts[0]
        action = parts[1]

        if action.startswith("-"):
            return None

        return f"{service} {action}"
