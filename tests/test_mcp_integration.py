#!/usr/bin/env python3
# REQ-007: Tests de integración end-to-end para servidor MCP
import unittest
import subprocess
import json
import os
import sys
import time
from typing import Any, cast


class TestMCPIntegrationE2E(unittest.TestCase):
    """Tests de integración real contra servidor MCP vía stdio."""

    script_path: str
    process: subprocess.Popen[str]

    @classmethod
    def setUpClass(cls):
        cls.script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'mcp_server.py'
        )
        cls.process = subprocess.Popen(
            [sys.executable, cls.script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        # Esperar a que el servidor inicie
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        if cls.process.poll() is None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait()

    def send_rpc(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Envía un request JSON-RPC y retorna la respuesta parseada."""
        raw_json = json.dumps(payload)
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(raw_json + '\n')
        self.process.stdin.flush()
        response_line = self.process.stdout.readline()
        if not response_line:
            return None
        return cast(dict[str, Any], json.loads(response_line))

    def test_initialize_handshake(self):
        """Verifica handshake initialize del protocolo MCP."""
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "e2e_test", "version": "1.0"}}
        }
        res = self.send_rpc(req)
        self.assertIsNotNone(res, "No hubo respuesta del servidor")
        self.assertEqual(res.get("id"), 1)
        self.assertIn("result", res)
        self.assertIn("capabilities", res["result"])
        self.assertIn("tools", res["result"]["capabilities"])

    def test_tools_list(self):
        """Verifica que tools/list retorna las herramientas esperadas."""
        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        res = self.send_rpc(req)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("id"), 2)
        self.assertIn("result", res)
        self.assertIn("tools", res["result"])
        tools = res["result"]["tools"]
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)
        # Verificar herramientas conocidas
        tool_names = {t["name"] for t in tools}
        expected = {"search_knowledge", "read_requirement", "validate_requirements", "create_lesson"}
        self.assertTrue(expected.issubset(tool_names), f"Faltan herramientas: {expected - tool_names}")

    def test_call_tool_search_knowledge(self):
        """Verifica llamada real a search_knowledge."""
        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_knowledge",
                "arguments": {"query": "gobernanza", "k": 3}
            }
        }
        res = self.send_rpc(req)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("id"), 3)
        self.assertIn("result", res)
        self.assertIn("content", res["result"])
        content = res["result"]["content"]
        self.assertIsInstance(content, list)
        self.assertGreater(len(content), 0)

    def test_call_tool_read_requirement(self):
        """Verifica llamada real a read_requirement."""
        req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "read_requirement",
                "arguments": {"id": "REQ-001"}
            }
        }
        res = self.send_rpc(req)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("id"), 4)
        self.assertIn("result", res)
        self.assertFalse(res["result"].get("isError"))
        self.assertIn("REQ-001", res["result"]["content"][0]["text"])

    def test_call_tool_unknown(self):
        """Verifica respuesta de error para herramienta inexistente."""
        req = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "herramienta_inexistente", "arguments": {}}
        }
        res = self.send_rpc(req)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("id"), 5)
        self.assertIn("result", res)
        self.assertTrue(res["result"].get("isError"))
        self.assertIn("tool desconocida", res["result"]["content"][0]["text"])

    def test_invalid_json_rpc_payload(self):
        """Verifica que JSON inválido no crashea el servidor (se ignora y logea)."""
        self.process.stdin.write('JSON_CORRUPTO_O_INVALIDO\n')
        self.process.stdin.flush()
        # El servidor ignora líneas JSON inválidas (logea y continúa)
        # Verificar que sigue respondiendo
        req2 = {"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}}
        res = self.send_rpc(req2)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("id"), 99)
        self.assertIn("result", res)

    def test_notifications_initialized(self):
        """Verifica notificación initialized (sin id)."""
        req = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        raw_json = json.dumps(req)
        self.process.stdin.write(raw_json + '\n')
        self.process.stdin.flush()
        # Las notificaciones no tienen respuesta, pero el servidor no debe crashear
        # Verificar que sigue respondiendo
        req2 = {"jsonrpc": "2.0", "id": 6, "method": "tools/list", "params": {}}
        res = self.send_rpc(req2)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("id"), 6)


if __name__ == "__main__":
    unittest.main()
