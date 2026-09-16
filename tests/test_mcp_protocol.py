import asyncio
import unittest

from fusion_flow import mcp_server


class McpProtocolTests(unittest.TestCase):
    def test_initialized_notification_has_no_jsonrpc_response(self):
        response = asyncio.run(
            mcp_server.dispatch(
                {"jsonrpc": "2.0", "method": "notifications/initialized"}
            )
        )
        self.assertIsNone(response)

