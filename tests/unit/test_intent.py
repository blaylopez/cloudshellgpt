"""Unit tests for IntentParser module."""

from __future__ import annotations

import pytest

from cloudshellgpt.intent import IntentParser


@pytest.fixture
def parser() -> IntentParser:
    """Create an IntentParser instance for testing."""
    return IntentParser()


class TestACBasicIntentParsing:
    """AC-1.1: Basic intent parsing."""

    def test_lista_los_buckets_de_s3(self, parser: IntentParser) -> None:
        """Given 'lista los buckets de S3', should return list/s3/confidence>0.85."""
        result = parser.parse("lista los buckets de S3")
        assert result.action == "list"
        assert result.service == "s3"
        assert result.confidence > 0.85
        assert result.clarification_needed is False

    def test_list_all_ec2_instances(self, parser: IntentParser) -> None:
        """English: list EC2 instances."""
        result = parser.parse("list all EC2 instances in us-east-1")
        assert result.action == "list"
        assert result.service == "ec2"
        assert result.confidence > 0.85

    def test_create_lambda_function(self, parser: IntentParser) -> None:
        """English: create Lambda function."""
        result = parser.parse("create a new Lambda function called my-handler")
        assert result.action == "create"
        assert result.service == "lambda"
        assert result.confidence > 0.85

    def test_delete_dynamodb_table(self, parser: IntentParser) -> None:
        """English: delete DynamoDB table."""
        result = parser.parse("delete the DynamoDB table named users")
        assert result.action == "delete"
        assert result.service == "dynamodb"
        assert result.confidence > 0.85


class TestACMultiLanguageSupport:
    """AC-1.2: Multi-language support."""

    @pytest.mark.parametrize(
        ("text", "expected_lang"),
        [
            ("por favor lista todos los buckets disponibles en mi cuenta de Amazon S3", "es"),
            ("list all S3 buckets in my AWS account please", "en"),
            ("listar todos os buckets do S3 na minha conta AWS", "pt"),
            ("afficher tous les buckets S3 dans mon compte AWS", "fr"),
            ("zeige alle S3 Buckets in meinem AWS Konto an", "de"),
        ],
    )
    def test_language_detection(self, parser: IntentParser, text: str, expected_lang: str) -> None:
        """Verifies langdetect correctly identifies each language."""
        result = parser.parse(text)
        assert result.detected_language == expected_lang
        # All should detect s3 + list action regardless of language
        assert result.service == "s3"
        assert result.action == "list"
        assert result.confidence > 0.85

    @pytest.mark.parametrize(
        ("text", "expected_service", "expected_action"),
        [
            # PT
            ("criar uma nova instância EC2 do tipo t3.micro", "ec2", "create"),
            ("excluir o banco de dados RDS chamado producao", "rds", "delete"),
            # FR
            ("créer un nouveau bucket S3 pour les backups", "s3", "create"),
            ("supprimer la fonction Lambda obsolète", "lambda", "delete"),
            # DE
            ("erstelle eine neue EC2 Instanz in Frankfurt", "ec2", "create"),
            ("lösche die DynamoDB Tabelle mit alten Daten", "dynamodb", "delete"),
        ],
    )
    def test_multilang_service_action_detection(
        self, parser: IntentParser, text: str, expected_service: str, expected_action: str
    ) -> None:
        """Verifies service and action detection works across languages."""
        result = parser.parse(text)
        assert result.service == expected_service
        assert result.action == expected_action
        assert result.confidence > 0.85


class TestACAmbiguityHandling:
    """AC-1.3: Ambiguity handling."""

    def test_ambiguous_input_muestrame_las_cosas(self, parser: IntentParser) -> None:
        """Ambiguous 'muéstrame las cosas' → confidence < 0.7, clarification needed."""
        result = parser.parse("muéstrame las cosas")
        assert result.confidence < 0.7
        assert result.clarification_needed is True
        assert result.clarification_question is not None
        assert len(result.clarification_question) > 10

    def test_ambiguous_input_help_me(self, parser: IntentParser) -> None:
        """Completely ambiguous input with no service or action keywords."""
        result = parser.parse("ayudame con algo de la nube")
        assert result.confidence < 0.7
        assert result.clarification_needed is True

    def test_partial_ambiguity_action_only(self, parser: IntentParser) -> None:
        """When only action is detected, confidence is 0.5 (< 0.7)."""
        result = parser.parse("por favor lista todo lo que tengo disponible")
        assert result.action == "list"
        assert result.service == "unknown"
        assert result.confidence == 0.5
        assert result.clarification_needed is True


class TestEdgeCases:
    """Edge case handling for IntentParser."""

    def test_empty_input(self, parser: IntentParser) -> None:
        """Empty string returns confidence 0, clarification needed."""
        result = parser.parse("")
        assert result.confidence == 0.0
        assert result.clarification_needed is True
        assert result.action == "unknown"
        assert result.service == "unknown"

    def test_whitespace_only_input(self, parser: IntentParser) -> None:
        """Whitespace-only input returns confidence 0."""
        result = parser.parse("   \t\n  ")
        assert result.confidence == 0.0
        assert result.clarification_needed is True

    def test_very_long_input(self, parser: IntentParser) -> None:
        """Input > 500 chars is truncated but still processes."""
        long_text = "lista los buckets de S3 " * 100  # ~2400 chars
        result = parser.parse(long_text)
        assert result.raw_input == long_text  # raw_input preserves original
        assert result.service == "s3"
        assert result.action == "list"

    def test_unicode_emoji_input(self, parser: IntentParser) -> None:
        """Input with emojis doesn't crash."""
        result = parser.parse("🚀 lista los buckets de S3 📦")
        assert result.service == "s3"
        assert result.action == "list"

    def test_mixed_language_es_en(self, parser: IntentParser) -> None:
        """Mixed ES+EN input still detects service and action."""
        result = parser.parse("list los buckets de S3 in my account")
        assert result.service == "s3"
        assert result.action == "list"
        assert result.confidence > 0.85

    def test_region_passed_through(self, parser: IntentParser) -> None:
        """Region parameter is correctly stored in Intent."""
        result = parser.parse("list S3 buckets", region="eu-west-1")
        assert result.region == "eu-west-1"


class TestServiceDetection:
    """Verifies detection of all 10 supported AWS services."""

    @pytest.mark.parametrize(
        ("text", "expected_service"),
        [
            ("list the S3 buckets", "s3"),
            ("show EC2 instances", "ec2"),
            ("describe Lambda functions", "lambda"),
            ("list DynamoDB tables", "dynamodb"),
            ("show IAM users", "iam"),
            ("describe RDS databases", "rds"),
            ("list VPC subnets", "vpc"),
            ("show CloudFront distributions", "cloudfront"),
            ("list SNS topics", "sns"),
            ("show SQS queues", "sqs"),
        ],
    )
    def test_service_keyword_detection(
        self, parser: IntentParser, text: str, expected_service: str
    ) -> None:
        """Each service is correctly identified by its keywords."""
        result = parser.parse(text)
        assert result.service == expected_service


class TestActionDetection:
    """Verifies detection of all 6 action types."""

    @pytest.mark.parametrize(
        ("text", "expected_action"),
        [
            ("list S3 buckets", "list"),
            ("create a new EC2 instance", "create"),
            ("delete the Lambda function", "delete"),
            ("update the IAM policy", "update"),
            ("describe the RDS instance details", "describe"),
            ("invoke the Lambda function", "invoke"),
        ],
    )
    def test_action_keyword_detection(
        self, parser: IntentParser, text: str, expected_action: str
    ) -> None:
        """Each action type is correctly identified."""
        result = parser.parse(text)
        assert result.action == expected_action


@pytest.mark.unit
@pytest.mark.persona1
class TestLanguageDetection:
    """Comprehensive parametrized tests for IntentParser language detection.

    Validates that langdetect correctly identifies each of the 6 supported
    languages from realistic AWS-related sentences. Minimum 5 inputs per
    language = 30+ total cases.
    """

    @pytest.mark.parametrize(
        ("text", "expected_lang"),
        [
            # --- Spanish (es) ---
            (
                "necesito listar todas las instancias de EC2 en la región de Virginia",
                "es",
            ),
            (
                "por favor crea un nuevo bucket de S3 para almacenar los respaldos diarios",
                "es",
            ),
            (
                "eliminar la tabla de DynamoDB que ya no se utiliza en producción",
                "es",
            ),
            (
                "quiero ver los roles de IAM configurados en mi cuenta de Amazon",
                "es",
            ),
            (
                "actualizar la función Lambda para que use la nueva versión del runtime",
                "es",
            ),
            (
                "mostrar las distribuciones de CloudFront activas en mi cuenta",
                "es",
            ),
            # --- English (en) ---
            (
                "please list all the EC2 instances running in the production account",
                "en",
            ),
            (
                "create a new S3 bucket with versioning enabled for backup storage",
                "en",
            ),
            (
                "delete the old Lambda function that is no longer being invoked",
                "en",
            ),
            (
                "show me the IAM policies attached to the admin role in this account",
                "en",
            ),
            (
                "update the DynamoDB table to increase the read capacity units",
                "en",
            ),
            (
                "describe the RDS database instance running PostgreSQL in production",
                "en",
            ),
            # --- Portuguese (pt) ---
            (
                "listar todas as instâncias EC2 que estão em execução na minha conta",
                "pt",
            ),
            (
                "criar um novo bucket no S3 para armazenar os arquivos de backup",
                "pt",
            ),
            (
                "excluir a função Lambda que não está sendo mais utilizada",
                "pt",
            ),
            (
                "mostrar os usuários do IAM que têm permissões de administrador",
                "pt",
            ),
            (
                "atualizar a tabela do DynamoDB para adicionar um novo índice global",
                "pt",
            ),
            (
                "descrever os detalhes do banco de dados RDS na região de São Paulo",
                "pt",
            ),
            # --- French (fr) ---
            (
                "lister toutes les instances EC2 en cours d'exécution dans mon compte",
                "fr",
            ),
            (
                "créer un nouveau bucket S3 pour stocker les sauvegardes quotidiennes",
                "fr",
            ),
            (
                "supprimer la fonction Lambda qui n'est plus utilisée en production",
                "fr",
            ),
            (
                "afficher les rôles IAM configurés dans le compte principal",
                "fr",
            ),
            (
                "mettre à jour la table DynamoDB pour augmenter la capacité de lecture",
                "fr",
            ),
            (
                "décrire les détails de la base de données RDS dans la région de Paris",
                "fr",
            ),
            # --- German (de) ---
            (
                "alle EC2 Instanzen auflisten die in meinem Konto laufen",
                "de",
            ),
            (
                "einen neuen S3 Bucket erstellen um die täglichen Backups zu speichern",
                "de",
            ),
            (
                "die alte Lambda Funktion löschen die nicht mehr verwendet wird",
                "de",
            ),
            (
                "zeige mir die IAM Benutzer die Administratorrechte in diesem Konto haben",
                "de",
            ),
            (
                "die DynamoDB Tabelle aktualisieren um einen neuen Index hinzuzufügen",
                "de",
            ),
            (
                "beschreibe die Details der RDS Datenbank in der Region Frankfurt",
                "de",
            ),
            # --- Chinese zh-cn ---
            (
                "请列出我账户中所有正在运行的EC2实例的详细信息",
                "zh-cn",
            ),
            (
                "创建一个新的S3存储桶用于存储每日备份文件",
                "zh-cn",
            ),
            (
                "请删除那些不再使用的旧版Lambda函数来释放账户中的资源配额",
                "zh-cn",
            ),
            (
                "显示当前账户中配置的所有IAM角色和权限策略",
                "zh-cn",
            ),
            (
                "更新DynamoDB数据库表的读取容量以处理更多请求",
                "zh-cn",
            ),
            (
                "描述生产环境中运行的RDS数据库实例的配置详情",
                "zh-cn",
            ),
        ],
        ids=[
            "es-list-ec2",
            "es-create-s3",
            "es-delete-dynamodb",
            "es-list-iam",
            "es-update-lambda",
            "es-list-cloudfront",
            "en-list-ec2",
            "en-create-s3",
            "en-delete-lambda",
            "en-list-iam",
            "en-update-dynamodb",
            "en-describe-rds",
            "pt-list-ec2",
            "pt-create-s3",
            "pt-delete-lambda",
            "pt-list-iam",
            "pt-update-dynamodb",
            "pt-describe-rds",
            "fr-list-ec2",
            "fr-create-s3",
            "fr-delete-lambda",
            "fr-list-iam",
            "fr-update-dynamodb",
            "fr-describe-rds",
            "de-list-ec2",
            "de-create-s3",
            "de-delete-lambda",
            "de-list-iam",
            "de-update-dynamodb",
            "de-describe-rds",
            "zh-list-ec2",
            "zh-create-s3",
            "zh-delete-lambda",
            "zh-list-iam",
            "zh-update-dynamodb",
            "zh-describe-rds",
        ],
    )
    def test_detected_language_matches_expected(
        self, parser: IntentParser, text: str, expected_lang: str
    ) -> None:
        """Verifies langdetect correctly identifies the language of AWS sentences.

        Args:
            parser: IntentParser fixture.
            text: Natural language AWS-related sentence.
            expected_lang: Expected ISO 639-1 language code.
        """
        result = parser.parse(text)
        assert result.detected_language == expected_lang, (
            f"Expected '{expected_lang}' but got '{result.detected_language}' "
            f"for text: '{text[:50]}...'"
        )


@pytest.mark.unit
@pytest.mark.persona1
class TestServiceDetectionParametrized:
    """Tests parametrizados para detección de servicio en IntentParser.

    Valida que cada uno de los 10 servicios AWS soportados se detecta
    correctamente con al menos 3 inputs distintos en múltiples idiomas
    (ES, EN, PT, FR, DE, ZH). Total: 40 casos (4 por servicio).
    """

    @pytest.mark.parametrize(
        ("text", "expected_service"),
        [
            # --- S3 (almacenamiento de objetos) ---
            ("lista los buckets de S3 disponibles", "s3"),
            ("quiero ver el almacenamiento en la nube", "s3"),
            ("show me the S3 bucket named backups", "s3"),
            ("zeige mir den Speicher in meinem Konto", "s3"),
            # --- EC2 (instancias de cómputo) ---
            ("create a new EC2 instance in us-west-2", "ec2"),
            ("necesito crear un servidor para producción", "ec2"),
            ("criar uma nova instância do tipo t3.large", "ec2"),
            ("démarrer un nouveau serveur virtuel", "ec2"),
            # --- Lambda (funciones serverless) ---
            ("invoke my Lambda function called processor", "lambda"),
            ("quiero crear una función nueva para procesar eventos", "lambda"),
            ("executar a função que processa os pedidos", "lambda"),
            ("eine neue Funktion erstellen für die Datenverarbeitung", "lambda"),
            # --- DynamoDB (base de datos NoSQL) ---
            ("list all DynamoDB tables in this region", "dynamodb"),
            ("crear una tabla para almacenar los pedidos", "dynamodb"),
            ("mostrar as tabelas disponíveis na minha conta", "dynamodb"),
            ("afficher le tableau des utilisateurs actifs", "dynamodb"),
            # --- IAM (gestión de identidades) ---
            ("show all IAM users in my account", "iam"),
            ("crear un nuevo usuario con permisos de lectura", "iam"),
            ("listar os usuários que têm permissão de admin", "iam"),
            ("die Rolle für den neuen Entwickler erstellen", "iam"),
            # --- RDS (bases de datos relacionales) ---
            ("describe the RDS database in production", "rds"),
            ("crear una base de datos PostgreSQL nueva", "rds"),
            ("excluir o banco de dados de teste antigo", "rds"),
            ("die Datenbank in Frankfurt beschreiben", "rds"),
            # --- VPC (redes virtuales) ---
            ("list all VPC subnets in this region", "vpc"),
            ("crear una subred nueva para el entorno de staging", "vpc"),
            ("mostrar a rede principal da minha conta", "vpc"),
            ("das Netzwerk für die Produktionsumgebung anzeigen", "vpc"),
            # --- CloudFront (distribución de contenido) ---
            ("show CloudFront distributions", "cloudfront"),
            ("crear una distribución CDN para el sitio web", "cloudfront"),
            ("listar a distribuição de conteúdo principal", "cloudfront"),
            ("die Verteilung für die statische Website erstellen", "cloudfront"),
            # --- SNS (notificaciones) ---
            ("list all SNS topics available", "sns"),
            ("crear una notificación para alertas de errores", "sns"),
            ("criar um novo tópico para alertas do sistema", "sns"),
            ("我想查看 SNS 通知主题列表", "sns"),
            # --- SQS (colas de mensajes) ---
            ("show all SQS queues in the account", "sqs"),
            ("crear una cola para procesar pedidos", "sqs"),
            ("listar todas as filas de mensagens ativas", "sqs"),
            ("die Warteschlange für Bestellungen anzeigen", "sqs"),
        ],
        ids=[
            # S3
            "s3-es-buckets",
            "s3-es-almacenamiento",
            "s3-en-bucket-name",
            "s3-de-speicher",
            # EC2
            "ec2-en-create-instance",
            "ec2-es-servidor",
            "ec2-pt-instancia",
            "ec2-fr-serveur",
            # Lambda
            "lambda-en-invoke",
            "lambda-es-funcion",
            "lambda-pt-funcao",
            "lambda-de-funktion",
            # DynamoDB
            "dynamodb-en-tables",
            "dynamodb-es-tabla",
            "dynamodb-pt-tabelas",
            "dynamodb-fr-tableau",
            # IAM
            "iam-en-users",
            "iam-es-usuario-permisos",
            "iam-pt-usuarios-permissao",
            "iam-de-rolle",
            # RDS
            "rds-en-describe",
            "rds-es-base-de-datos",
            "rds-pt-banco-de-dados",
            "rds-de-datenbank",
            # VPC
            "vpc-en-subnets",
            "vpc-es-subred",
            "vpc-pt-rede",
            "vpc-de-netzwerk",
            # CloudFront
            "cloudfront-en-distributions",
            "cloudfront-es-distribucion-cdn",
            "cloudfront-pt-distribuicoes",
            "cloudfront-de-verteilung",
            # SNS
            "sns-en-topics",
            "sns-es-notificacion",
            "sns-pt-topico",
            "sns-zh-tongzhi",
            # SQS
            "sqs-en-queues",
            "sqs-es-cola",
            "sqs-pt-filas",
            "sqs-de-warteschlange",
        ],
    )
    def test_service_detection_multilang(
        self, parser: IntentParser, text: str, expected_service: str
    ) -> None:
        """Verifica que el servicio se detecta correctamente en múltiples idiomas.

        Args:
            parser: Fixture de IntentParser.
            text: Entrada en lenguaje natural.
            expected_service: Servicio AWS esperado.
        """
        result = parser.parse(text)
        assert result.service == expected_service, (
            f"Esperado '{expected_service}' pero se obtuvo '{result.service}' "
            f"para texto: '{text[:60]}...'"
        )


@pytest.mark.unit
@pytest.mark.persona1
class TestActionDetectionParametrized:
    """Tests parametrizados para detección de acción en IntentParser.

    Valida que cada una de las 6 acciones soportadas (list, create, delete,
    update, describe, invoke) se detecta correctamente con al menos 3 inputs
    distintos en múltiples idiomas (ES, EN, PT, FR, DE, ZH).
    Total: 24 casos (4 por acción).
    """

    @pytest.mark.parametrize(
        ("text", "expected_action"),
        [
            # --- list ---
            ("lista todos los buckets de S3 disponibles en mi cuenta", "list"),
            ("show me all EC2 instances running in production", "list"),
            ("exibir todas as funções Lambda ativas na minha conta", "list"),
            ("afficher les tables DynamoDB dans cette région", "list"),
            # --- create ---
            ("crea un nuevo bucket de S3 para los backups del proyecto", "create"),
            ("create a new Lambda function for processing events", "create"),
            ("criar uma nova instância EC2 do tipo t3.micro na região", "create"),
            ("erstelle einen neuen S3 Bucket für die Produktionsdaten", "create"),
            # --- delete ---
            ("elimina la función Lambda que ya no se usa en staging", "delete"),
            ("delete the old DynamoDB table from the test environment", "delete"),
            ("excluir o bucket S3 que contém dados temporários antigos", "delete"),
            ("supprimer la fonction Lambda obsolète du compte principal", "delete"),
            # --- update ---
            ("actualiza la política IAM del rol de administrador", "update"),
            ("update the EC2 instance type to t3.large for better performance", "update"),
            ("atualizar a tabela DynamoDB para aumentar a capacidade de leitura", "update"),
            ("ändern Sie die Konfiguration der Lambda Funktion im Konto", "update"),
            # --- describe ---
            ("describe los detalles de la instancia RDS en producción", "describe"),
            ("get the details of the S3 bucket named company-backups", "describe"),
            ("descrever a configuração da função Lambda de processamento", "describe"),
            ("beschreiben Sie die Details der EC2 Instanz in Frankfurt", "describe"),
            # --- invoke ---
            ("ejecuta la función Lambda que procesa los pedidos nuevos", "invoke"),
            ("invoke the Lambda function called order-processor now", "invoke"),
            ("executar a função Lambda de envio de notificações agora", "invoke"),
            ("aufrufen der Lambda Funktion zur Verarbeitung der Bestellungen", "invoke"),
        ],
        ids=[
            # list
            "list-es-buckets-s3",
            "list-en-ec2-instances",
            "list-pt-lambda-funcoes",
            "list-fr-dynamodb-tables",
            # create
            "create-es-bucket-s3",
            "create-en-lambda-function",
            "create-pt-ec2-instancia",
            "create-de-s3-bucket",
            # delete
            "delete-es-lambda-funcion",
            "delete-en-dynamodb-table",
            "delete-pt-s3-bucket",
            "delete-fr-lambda-fonction",
            # update
            "update-es-iam-politica",
            "update-en-ec2-instance",
            "update-pt-dynamodb-tabela",
            "update-de-lambda-config",
            # describe
            "describe-es-rds-detalles",
            "describe-en-s3-bucket",
            "describe-pt-lambda-config",
            "describe-de-ec2-instanz",
            # invoke
            "invoke-es-lambda-ejecuta",
            "invoke-en-lambda-invoke",
            "invoke-pt-lambda-executar",
            "invoke-de-lambda-aufrufen",
        ],
    )
    def test_action_detection_multilang(
        self, parser: IntentParser, text: str, expected_action: str
    ) -> None:
        """Verifica que la acción se detecta correctamente en múltiples idiomas.

        Args:
            parser: Fixture de IntentParser.
            text: Entrada en lenguaje natural con una acción AWS implícita.
            expected_action: Tipo de acción esperado (list, create, delete, update, describe, invoke).
        """
        result = parser.parse(text)
        assert result.action == expected_action, (
            f"Esperado '{expected_action}' pero se obtuvo '{result.action}' "
            f"para texto: '{text[:60]}...'"
        )


@pytest.mark.unit
@pytest.mark.persona1
class TestEdgeCasesParametrized:
    """Tests parametrizados para edge cases del IntentParser.

    Valida comportamiento ante entradas atípicas: vacías, solo espacios,
    unicode inusual, texto largo (> MAX_INPUT_LENGTH), idioma mixto ES+EN,
    y emojis en distintas posiciones.
    """

    # --- 1. Empty input ---
    @pytest.mark.parametrize(
        "text",
        [
            "",
        ],
        ids=["empty-string"],
    )
    def test_empty_input_returns_unknown(self, parser: IntentParser, text: str) -> None:
        """Empty input produces action=unknown, service=unknown, confidence=0.0.

        Args:
            parser: IntentParser fixture.
            text: Empty string input.
        """
        result = parser.parse(text)
        assert result.action == "unknown"
        assert result.service == "unknown"
        assert result.confidence == 0.0
        assert result.clarification_needed is True

    # --- 2. Whitespace-only input ---
    @pytest.mark.parametrize(
        "text",
        [
            "   ",
            "\t\t\t",
            "\n\n\n",
            "  \t  \n  ",
            " \t \n \r ",
        ],
        ids=[
            "spaces-only",
            "tabs-only",
            "newlines-only",
            "mixed-whitespace",
            "whitespace-with-cr",
        ],
    )
    def test_whitespace_only_returns_unknown(self, parser: IntentParser, text: str) -> None:
        """Whitespace-only input produces action=unknown, service=unknown, confidence=0.0.

        Args:
            parser: IntentParser fixture.
            text: Whitespace-only string.
        """
        result = parser.parse(text)
        assert result.action == "unknown"
        assert result.service == "unknown"
        assert result.confidence == 0.0
        assert result.clarification_needed is True

    # --- 3. Unusual unicode characters ---
    @pytest.mark.parametrize(
        "text",
        [
            # Arabic script
            "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645",
            # Thai script
            "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35\u0e0a\u0e32\u0e27\u0e42\u0e25\u0e01",
            # Cyrillic script
            "\u041f\u0440\u0438\u0432\u0435\u0442 \u043c\u0438\u0440",
            # Combining characters (e with combining acute accent)
            "e\u0301 lista los buckets",
            # Zero-width characters (zero-width space + zero-width joiner)
            "lista\u200b\u200clos\u200dbuckets",
            # Mixed diacritics and combining marks
            "a\u0308\u0301o\u0303u\u0302",
        ],
        ids=[
            "arabic-script",
            "thai-script",
            "cyrillic-script",
            "combining-characters",
            "zero-width-chars",
            "mixed-diacritics",
        ],
    )
    def test_unicode_does_not_crash(self, parser: IntentParser, text: str) -> None:
        """Parser handles unusual unicode without raising exceptions.

        Args:
            parser: IntentParser fixture.
            text: Input with unusual unicode characters.
        """
        result = parser.parse(text)
        # Must not crash — returns a valid Intent
        assert result.action in (
            "list",
            "create",
            "delete",
            "update",
            "describe",
            "invoke",
            "unknown",
        )
        assert isinstance(result.service, str)
        assert 0.0 <= result.confidence <= 1.0
        assert result.raw_input == text

    # --- 4. Text longer than 500 characters (MAX_INPUT_LENGTH) ---
    @pytest.mark.parametrize(
        ("text", "expected_service", "expected_action"),
        [
            # Keywords at the start (within first 500 chars) → detected
            ("lista los buckets de S3 " + "x" * 500, "s3", "list"),
            # Pure filler > 500 chars → no service/action detected
            ("a" * 600, "unknown", "unknown"),
            # Keywords repeated so they appear within first 500 chars
            ("create a new Lambda function " + "padding text " * 50, "lambda", "create"),
        ],
        ids=[
            "long-text-keywords-at-start",
            "long-text-no-keywords",
            "long-text-keywords-with-padding",
        ],
    )
    def test_long_input_preserves_raw_and_processes(
        self, parser: IntentParser, text: str, expected_service: str, expected_action: str
    ) -> None:
        """Input > 500 chars: raw_input preserves original, parser processes truncated.

        Args:
            parser: IntentParser fixture.
            text: Input string longer than MAX_INPUT_LENGTH (500).
            expected_service: Expected detected service.
            expected_action: Expected detected action.
        """
        assert len(text) > 500
        result = parser.parse(text)
        # raw_input always preserves the full original text
        assert result.raw_input == text
        assert len(result.raw_input) > 500
        # Parser still detects service/action from truncated version
        assert result.service == expected_service
        assert result.action == expected_action

    # --- 5. Mixed language input (Spanish + English) ---
    @pytest.mark.parametrize(
        ("text", "expected_service", "expected_action"),
        [
            ("list los buckets de S3 in my account", "s3", "list"),
            ("create una instancia EC2 in us-east-1 region", "ec2", "create"),
            ("delete la función Lambda called processor", "lambda", "delete"),
            ("show me las tablas de DynamoDB disponibles", "dynamodb", "list"),
            ("quiero update the IAM policy del administrador", "iam", "update"),
            ("describe los detalles de la base de datos RDS en producción", "rds", "describe"),
        ],
        ids=[
            "mixed-list-s3",
            "mixed-create-ec2",
            "mixed-delete-lambda",
            "mixed-show-dynamodb",
            "mixed-update-iam",
            "mixed-describe-rds",
        ],
    )
    def test_mixed_es_en_detects_service_and_action(
        self, parser: IntentParser, text: str, expected_service: str, expected_action: str
    ) -> None:
        """Mixed ES+EN input still detects service and action correctly.

        Args:
            parser: IntentParser fixture.
            text: Input mixing Spanish and English words.
            expected_service: Expected detected AWS service.
            expected_action: Expected detected action type.
        """
        result = parser.parse(text)
        assert result.service == expected_service
        assert result.action == expected_action
        assert result.confidence > 0.85

    # --- 6. Emojis in various positions ---
    @pytest.mark.parametrize(
        ("text", "expected_service", "expected_action"),
        [
            # Emoji at start
            ("\U0001f680 lista los buckets de S3", "s3", "list"),
            # Emoji in middle
            ("lista los \U0001f4e6 buckets de S3", "s3", "list"),
            # Emoji at end
            ("lista los buckets de S3 \u2728", "s3", "list"),
            # Multiple emojis surrounding keywords
            ("\U0001f525\U0001f525 create EC2 instance \U0001f680\U0001f4a5", "ec2", "create"),
            # Emoji-only (no AWS keywords) → no crash, unknown
            ("\U0001f600\U0001f609\U0001f60d\U0001f92f\U0001f47d\U0001f680", "unknown", "unknown"),
            # Emoji mixed with service keyword
            ("delete \U0001f5d1\ufe0f Lambda function", "lambda", "delete"),
        ],
        ids=[
            "emoji-at-start",
            "emoji-in-middle",
            "emoji-at-end",
            "multiple-emojis-surrounding",
            "emoji-only-no-keywords",
            "emoji-mixed-with-keyword",
        ],
    )
    def test_emojis_handled_gracefully(
        self, parser: IntentParser, text: str, expected_service: str, expected_action: str
    ) -> None:
        """Parser handles emojis gracefully, detecting service/action when keywords present.

        Args:
            parser: IntentParser fixture.
            text: Input containing emojis in various positions.
            expected_service: Expected detected service (or 'unknown' for emoji-only).
            expected_action: Expected detected action (or 'unknown' for emoji-only).
        """
        result = parser.parse(text)
        assert result.service == expected_service
        assert result.action == expected_action
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0


@pytest.mark.unit
@pytest.mark.persona1
class TestConfidenceAmbiguousInputs:
    """Tests parametrizados para verificar confidence < 0.7 con inputs ambiguos.

    Valida que el IntentParser asigna baja confianza (< 0.7) a entradas
    ambiguas donde no se puede determinar claramente el servicio y/o la
    acción AWS deseada. Cada caso también verifica que clarification_needed
    es True y que clarification_question tiene contenido significativo.
    """

    @pytest.mark.parametrize(
        ("text", "category"),
        [
            # 1. Vague requests with no AWS keywords
            ("ayúdame con algo", "vague-no-keywords"),
            ("necesito hacer algo importante hoy", "vague-no-keywords"),
            # 2. Only action detected, no service
            ("borra todo lo viejo", "action-only"),
            ("por favor lista todo lo que tengo disponible", "action-only"),
            # 3. Only service detected, no action (uses semantic keywords)
            ("algo con S3", "service-only"),
            ("tengo un problema con mi base de datos", "service-only"),
            # 4. Metaphorical/indirect language
            ("quiero ahorrar dinero en la nube", "metaphorical"),
            ("necesito que las cosas vayan más rápido", "metaphorical"),
            # 5. Conversational/social language
            ("hola, qué tal", "conversational"),
            ("buenos días, cómo estás", "conversational"),
            # 6. Questions without clear intent
            ("¿cuánto cuesta esto?", "question-no-intent"),
            ("¿qué puedo hacer aquí?", "question-no-intent"),
            # 7. Multiple services mentioned without clear action
            ("algo entre S3 y DynamoDB", "multiple-services-no-action"),
            # 8. Technical jargon without AWS specifics
            ("necesito más memoria", "tech-jargon-no-aws"),
            ("el rendimiento está muy bajo últimamente", "tech-jargon-no-aws"),
            # 9. Typos/misspellings preventing keyword matching
            ("lsta los bkts de ese tres", "typos"),
            # 10. Unsupported/rare language lacking keyword coverage
            ("tafadhali nisaidie na kitu", "unsupported-language"),
            ("kérem segítsen valamiben", "unsupported-language"),
        ],
        ids=[
            "vague-ayudame-con-algo",
            "vague-algo-importante",
            "action-only-borra-viejo",
            "action-only-lista-disponible",
            "service-only-algo-s3",
            "service-only-base-de-datos",
            "metaphorical-ahorrar-dinero",
            "metaphorical-mas-rapido",
            "conversational-hola",
            "conversational-buenos-dias",
            "question-cuanto-cuesta",
            "question-que-puedo-hacer",
            "multiple-services-s3-dynamodb",
            "tech-jargon-memoria",
            "tech-jargon-rendimiento",
            "typos-lsta-bkts",
            "unsupported-swahili",
            "unsupported-hungarian",
        ],
    )
    def test_ambiguous_input_has_low_confidence(
        self, parser: IntentParser, text: str, category: str
    ) -> None:
        """Verifica que inputs ambiguos producen confidence < 0.7.

        Args:
            parser: Fixture de IntentParser.
            text: Entrada ambigua en lenguaje natural.
            category: Categoría de ambigüedad (solo para documentación).
        """
        result = parser.parse(text)
        assert result.confidence < 0.7, (
            f"[{category}] Esperado confidence < 0.7 pero se obtuvo "
            f"{result.confidence} para: '{text}'"
        )
        assert result.clarification_needed is True, (
            f"[{category}] clarification_needed debería ser True para: '{text}'"
        )
        assert result.clarification_question is not None, (
            f"[{category}] clarification_question no debería ser None para: '{text}'"
        )
        assert len(result.clarification_question) > 10, (
            f"[{category}] clarification_question debería tener contenido "
            f"significativo (len > 10) para: '{text}'"
        )
