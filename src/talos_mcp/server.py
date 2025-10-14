#!/usr/bin/env python3
"""
Talos MCP Server

An MCP server that provides tools for interacting with Talos Linux clusters via the gRPC API.
"""

import asyncio
import json
import logging
import os
import ssl
from pathlib import Path
from typing import Any, Optional

import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("talos-mcp-server")


class TalosClient:
    """Client for interacting with Talos Linux API"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Talos client with configuration

        Args:
            config_path: Path to talosconfig file. Defaults to ~/.talos/config
        """
        self.config_path = config_path or os.path.expanduser("~/.talos/config")
        self.config = None
        self.current_context = None
        self._load_config()

    def _load_config(self):
        """Load Talos configuration from file"""
        try:
            config_file = Path(self.config_path)
            if config_file.exists():
                with open(config_file, "r") as f:
                    self.config = yaml.safe_load(f)
                    self.current_context = self.config.get("context")
                    logger.info(f"Loaded Talos config with context: {self.current_context}")
            else:
                logger.warning(f"Talos config not found at {self.config_path}")
        except Exception as e:
            logger.error(f"Error loading Talos config: {e}")

    def get_context_info(self) -> dict:
        """Get information about the current context"""
        if not self.config or not self.current_context:
            return {"error": "No Talos configuration loaded"}

        contexts = self.config.get("contexts", {})
        context_data = contexts.get(self.current_context, {})

        return {
            "context": self.current_context,
            "endpoints": context_data.get("endpoints", []),
            "nodes": context_data.get("nodes", []),
        }

    async def execute_talosctl(self, args: list[str]) -> dict[str, Any]:
        """
        Execute talosctl command and return the output

        Args:
            args: List of command arguments to pass to talosctl

        Returns:
            Dictionary with stdout, stderr, and return code
        """
        try:
            # Build the command
            cmd = ["talosctl"] + args

            # Add config file if it exists
            if Path(self.config_path).exists():
                cmd.extend(["--talosconfig", self.config_path])

            logger.info(f"Executing: {' '.join(cmd)}")

            # Execute the command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": stdout.decode("utf-8"),
                "stderr": stderr.decode("utf-8"),
            }

        except Exception as e:
            logger.error(f"Error executing talosctl: {e}")
            return {
                "success": False,
                "error": str(e),
            }


# Initialize the MCP server
app = Server("talos-mcp-server")
talos_client = TalosClient()


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available Talos tools"""
    return [
        Tool(
            name="talos_get_version",
            description="Get Talos Linux version information from nodes",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames (optional)",
                    }
                },
            },
        ),
        Tool(
            name="talos_get_disks",
            description="List all disks on Talos nodes",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames",
                    },
                    "insecure": {
                        "type": "boolean",
                        "description": "Use insecure connection (for initial setup)",
                        "default": False,
                    },
                },
                "required": ["nodes"],
            },
        ),
        Tool(
            name="talos_get_services",
            description="Get status of all services running on Talos nodes",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames (optional)",
                    }
                },
            },
        ),
        Tool(
            name="talos_get_resources",
            description="Get Talos resources (similar to kubectl get). Use 'rd' to list all resource definitions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "description": "Resource type to get (e.g., 'members', 'services', 'rd', 'machineconfig')",
                    },
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames (optional)",
                    },
                    "output": {
                        "type": "string",
                        "description": "Output format: table, json, yaml",
                        "default": "table",
                    },
                },
                "required": ["resource"],
            },
        ),
        Tool(
            name="talos_logs",
            description="Get logs from Talos services or containers",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames",
                    },
                    "service": {
                        "type": "string",
                        "description": "Service name to get logs from (e.g., 'kubelet', 'etcd')",
                    },
                    "kubernetes": {
                        "type": "boolean",
                        "description": "Get logs from kubernetes namespace instead of system",
                        "default": False,
                    },
                    "tail": {
                        "type": "integer",
                        "description": "Number of lines to show from the end",
                        "default": 100,
                    },
                },
                "required": ["nodes", "service"],
            },
        ),
        Tool(
            name="talos_dashboard",
            description="Get a snapshot of the Talos dashboard (resource usage, system info)",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames (optional)",
                    }
                },
            },
        ),
        Tool(
            name="talos_health",
            description="Check health status of Talos cluster",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames (optional)",
                    },
                    "control_plane": {
                        "type": "boolean",
                        "description": "Check control plane specific health",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="talos_list",
            description="List files and directories on Talos nodes",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to list (e.g., /var/log, /dev)",
                        "default": "/",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Directory depth to traverse",
                        "default": 1,
                    },
                },
                "required": ["nodes"],
            },
        ),
        Tool(
            name="talos_read",
            description="Read a file from Talos nodes",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to file to read",
                    },
                },
                "required": ["nodes", "path"],
            },
        ),
        Tool(
            name="talos_etcd_members",
            description="List etcd cluster members",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames (optional)",
                    }
                },
            },
        ),
        Tool(
            name="talos_get_kubeconfig",
            description="Retrieve kubeconfig for the Kubernetes cluster",
            inputSchema={
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "string",
                        "description": "Comma-separated list of node IPs/hostnames (optional)",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force overwrite of existing kubeconfig",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="talos_config_info",
            description="Get information about current Talos configuration and context",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls for Talos operations"""

    try:
        if name == "talos_config_info":
            info = talos_client.get_context_info()
            return [TextContent(type="text", text=json.dumps(info, indent=2))]

        elif name == "talos_get_version":
            args = ["version"]
            if arguments.get("nodes"):
                args.extend(["-n", arguments["nodes"]])

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_get_disks":
            args = ["get", "disks", "-n", arguments["nodes"]]
            if arguments.get("insecure"):
                args.append("--insecure")

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_get_services":
            args = ["services"]
            if arguments.get("nodes"):
                args.extend(["-n", arguments["nodes"]])

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_get_resources":
            args = ["get", arguments["resource"]]
            if arguments.get("nodes"):
                args.extend(["-n", arguments["nodes"]])
            if arguments.get("output"):
                args.extend(["-o", arguments["output"]])

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_logs":
            args = ["logs", arguments["service"], "-n", arguments["nodes"]]
            if arguments.get("kubernetes"):
                args.append("-k")
            if arguments.get("tail"):
                args.extend(["--tail", str(arguments["tail"])])

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_dashboard":
            args = ["dashboard"]
            if arguments.get("nodes"):
                args.extend(["-n", arguments["nodes"]])
            # Use a short interval for a snapshot
            args.extend(["--interval", "1s"])

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_health":
            args = ["health"]
            if arguments.get("nodes"):
                args.extend(["-n", arguments["nodes"]])
            if not arguments.get("control_plane", True):
                args.append("--run-all")

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_list":
            args = ["list", "-n", arguments["nodes"]]
            if arguments.get("path"):
                args.append(arguments["path"])
            if arguments.get("depth"):
                args.extend(["-d", str(arguments["depth"])])

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_read":
            args = ["read", arguments["path"], "-n", arguments["nodes"]]

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_etcd_members":
            args = ["etcd", "members"]
            if arguments.get("nodes"):
                args.extend(["-n", arguments["nodes"]])

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        elif name == "talos_get_kubeconfig":
            args = ["kubeconfig"]
            if arguments.get("nodes"):
                args.extend(["-n", arguments["nodes"]])
            if arguments.get("force"):
                args.append("--force")

            result = await talos_client.execute_talosctl(args)
            return [
                TextContent(
                    type="text",
                    text=result["stdout"] if result["success"] else result.get("stderr", ""),
                )
            ]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server"""
    logger.info("Starting Talos MCP Server")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
