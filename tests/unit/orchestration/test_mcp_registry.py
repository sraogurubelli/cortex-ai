"""Tests for MCPServerRegistry."""

import json
import os

import pytest

from cortex.orchestration.mcp.config import HTTPMCPConfig, MCPAuth, STDIOMCPConfig
from cortex.orchestration.mcp.registry import MCPServerRegistry


@pytest.fixture
def registry():
    """Fresh registry (not the singleton)."""
    reg = MCPServerRegistry()
    return reg


@pytest.mark.unit
class TestMCPServerRegistry:
    """Tests for the MCP server registry."""

    def test_register_and_get(self, registry: MCPServerRegistry):
        config = HTTPMCPConfig(name="test-server", url="http://localhost:8080")
        registry.register(config)

        assert "test-server" in registry
        assert registry.get_config("test-server") is config

    def test_list_servers(self, registry: MCPServerRegistry):
        registry.register(HTTPMCPConfig(name="a", url="http://a"))
        registry.register(HTTPMCPConfig(name="b", url="http://b"))

        servers = registry.list_servers()
        assert set(servers) == {"a", "b"}

    def test_get_config_raises_on_missing(self, registry: MCPServerRegistry):
        with pytest.raises(KeyError, match="not found"):
            registry.get_config("nonexistent")

    def test_remove_server(self, registry: MCPServerRegistry):
        registry.register(HTTPMCPConfig(name="removable", url="http://r"))
        assert registry.remove("removable") is True
        assert "removable" not in registry
        assert registry.remove("removable") is False

    def test_clear(self, registry: MCPServerRegistry):
        registry.register(HTTPMCPConfig(name="x", url="http://x"))
        registry.clear()
        assert len(registry) == 0

    def test_len_and_contains(self, registry: MCPServerRegistry):
        assert len(registry) == 0
        registry.register(HTTPMCPConfig(name="s", url="http://s"))
        assert len(registry) == 1
        assert "s" in registry
        assert "nope" not in registry

    def test_env_loading(self, monkeypatch):
        servers = [
            {"name": "http-srv", "transport": "http", "url": "http://tools:8080"},
            {
                "name": "stdio-srv",
                "transport": "stdio",
                "command": "./server",
                "args": ["stdio"],
            },
        ]
        monkeypatch.setenv("CORTEX_MCP_SERVERS", json.dumps(servers))

        reg = MCPServerRegistry()
        reg._load_from_env()

        assert len(reg) == 2
        assert "http-srv" in reg
        assert "stdio-srv" in reg

        http_cfg = reg.get_config("http-srv")
        assert isinstance(http_cfg, HTTPMCPConfig)
        assert http_cfg.url == "http://tools:8080"

        stdio_cfg = reg.get_config("stdio-srv")
        assert isinstance(stdio_cfg, STDIOMCPConfig)
        assert stdio_cfg.command == "./server"

    def test_env_loading_invalid_json(self, monkeypatch):
        monkeypatch.setenv("CORTEX_MCP_SERVERS", "not-json")
        reg = MCPServerRegistry()
        reg._load_from_env()
        assert len(reg) == 0

    def test_env_loading_not_array(self, monkeypatch):
        monkeypatch.setenv("CORTEX_MCP_SERVERS", '{"name": "x"}')
        reg = MCPServerRegistry()
        reg._load_from_env()
        assert len(reg) == 0

    def test_env_with_auth(self, monkeypatch):
        servers = [
            {
                "name": "auth-srv",
                "transport": "http",
                "url": "http://auth:8080",
                "token": "my-token",
            },
        ]
        monkeypatch.setenv("CORTEX_MCP_SERVERS", json.dumps(servers))

        reg = MCPServerRegistry()
        reg._load_from_env()

        cfg = reg.get_config("auth-srv")
        assert cfg.auth_type == MCPAuth.BEARER_TOKEN
        assert cfg.token == "my-token"
