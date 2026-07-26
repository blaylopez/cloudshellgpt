"""Tests async para serve_mcp() — protocol compliance básico.

Verifica que el MCP server:
- Levanta sin error con streams in-memory.
- Responde correctamente al handshake initialize (protocol compliance).
- No crashea ante input inesperado.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import anyio
import pytest
from mcp.shared.session import SessionMessage
from mcp.types import (
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)

from cloudshellgpt.mcp_server import server

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_initialize_request(request_id: int | str = 1) -> SessionMessage:
    """Construye un mensaje MCP initialize válido.

    Args:
        request_id: ID del request JSON-RPC.

    Returns:
        SessionMessage con el request initialize.
    """
    req = JSONRPCRequest(
        method="initialize",
        params={
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0.1.0"},
        },
        jsonrpc="2.0",
        id=request_id,
    )
    return SessionMessage(message=JSONRPCMessage(root=req))


def _build_initialized_notification() -> SessionMessage:
    """Construye la notificación notifications/initialized.

    Returns:
        SessionMessage con la notificación initialized.
    """
    notif = JSONRPCNotification(
        method="notifications/initialized",
        jsonrpc="2.0",
    )
    return SessionMessage(message=JSONRPCMessage(root=notif))


# ---------------------------------------------------------------------------
# Tests: serve_mcp() levanta sin error
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_server_starts_and_responds_to_initialize() -> None:
    """El server MCP levanta sin error y responde al initialize con result válido."""
    send_to_server, recv_from_us = anyio.create_memory_object_stream[SessionMessage | Exception](10)
    send_from_server, recv_from_server = anyio.create_memory_object_stream[SessionMessage](10)

    # Enviar initialize + initialized notification + cerrar stream
    await send_to_server.send(_build_initialize_request(request_id=1))
    await send_to_server.send(_build_initialized_notification())
    await send_to_server.aclose()

    init_options = server.create_initialization_options()

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await server.run(recv_from_us, send_from_server, init_options)

        tg.start_soon(run_server)

        # Leer respuesta del server
        response = await recv_from_server.receive()

        # Verificar que es una respuesta JSON-RPC válida
        assert isinstance(response, SessionMessage)
        root = response.message.root
        assert isinstance(root, JSONRPCResponse)
        assert root.id == 1
        assert root.jsonrpc == "2.0"

        # Cancelar task group (el server se queda escuchando indefinidamente)
        tg.cancel_scope.cancel()


@pytest.mark.unit
async def test_server_initialize_response_contains_server_info() -> None:
    """La respuesta initialize contiene serverInfo con nombre 'cloudshellgpt'."""
    send_to_server, recv_from_us = anyio.create_memory_object_stream[SessionMessage | Exception](10)
    send_from_server, recv_from_server = anyio.create_memory_object_stream[SessionMessage](10)

    await send_to_server.send(_build_initialize_request(request_id=42))
    await send_to_server.send(_build_initialized_notification())
    await send_to_server.aclose()

    init_options = server.create_initialization_options()

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await server.run(recv_from_us, send_from_server, init_options)

        tg.start_soon(run_server)

        response = await recv_from_server.receive()
        result: dict[str, Any] = response.message.root.result  # type: ignore[union-attr]

        # Verificar serverInfo
        assert "serverInfo" in result
        assert result["serverInfo"]["name"] == "cloudshellgpt"

        # Verificar protocolVersion
        assert "protocolVersion" in result
        assert result["protocolVersion"] == "2024-11-05"

        tg.cancel_scope.cancel()


@pytest.mark.unit
async def test_server_initialize_response_advertises_tools_capability() -> None:
    """La respuesta initialize anuncia capabilities con 'tools'."""
    send_to_server, recv_from_us = anyio.create_memory_object_stream[SessionMessage | Exception](10)
    send_from_server, recv_from_server = anyio.create_memory_object_stream[SessionMessage](10)

    await send_to_server.send(_build_initialize_request(request_id=2))
    await send_to_server.send(_build_initialized_notification())
    await send_to_server.aclose()

    init_options = server.create_initialization_options()

    async with anyio.create_task_group() as tg:

        async def run_server() -> None:
            await server.run(recv_from_us, send_from_server, init_options)

        tg.start_soon(run_server)

        response = await recv_from_server.receive()
        result: dict[str, Any] = response.message.root.result  # type: ignore[union-attr]

        # Verificar que anuncia tools capability
        assert "capabilities" in result
        assert "tools" in result["capabilities"]

        tg.cancel_scope.cancel()


# ---------------------------------------------------------------------------
# Tests: protocol compliance — manejo de input inesperado
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_server_handles_stream_close_without_crash() -> None:
    """El server no crashea si el stream se cierra antes de recibir mensajes."""
    send_to_server, recv_from_us = anyio.create_memory_object_stream[SessionMessage | Exception](10)
    send_from_server, recv_from_server = anyio.create_memory_object_stream[SessionMessage](10)

    # Cerrar inmediatamente sin enviar nada
    await send_to_server.aclose()

    init_options = server.create_initialization_options()

    # El server debe terminar gracefully sin lanzar excepciones
    await server.run(recv_from_us, send_from_server, init_options)


@pytest.mark.unit
async def test_serve_mcp_calls_asyncio_run_with_stdio_server() -> None:
    """serve_mcp() llama asyncio.run() y usa stdio_server como transport.

    Dado que serve_mcp() invoca asyncio.run() (bloqueante), mockeamos
    asyncio.run para capturar la coroutine que se le pasa y ejecutarla
    nosotros mismos dentro del event loop ya activo del test.
    """

    from cloudshellgpt.mcp_server import serve_mcp

    captured_coro: list[Any] = []

    def fake_asyncio_run(coro: Any) -> None:
        """Captura la coroutine en vez de llamar asyncio.run() real."""
        captured_coro.append(coro)

    with (
        patch("asyncio.run", side_effect=fake_asyncio_run),
        patch("cloudshellgpt.mcp_server.stdio_server") as mock_stdio,
        patch("cloudshellgpt.mcp_server.server") as mock_server,
    ):
        # Configurar mock de stdio_server como async context manager
        mock_read = AsyncMock()
        mock_write = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_stdio.return_value = mock_cm

        # Mock server.run como coroutine
        mock_server.run = AsyncMock()
        mock_server.create_initialization_options = lambda: {"test": True}

        # Ejecutar serve_mcp — captura la coroutine via fake_asyncio_run
        serve_mcp()

        # Verificar que asyncio.run fue llamado con una coroutine
        assert len(captured_coro) == 1

        # Ejecutar la coroutine capturada dentro de nuestro event loop
        await captured_coro[0]

        # Verificar que stdio_server se usó
        mock_stdio.assert_called_once()

        # Verificar que server.run se llamó con los streams correctos
        mock_server.run.assert_awaited_once_with(
            mock_read,
            mock_write,
            {"test": True},
        )
