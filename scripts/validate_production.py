#!/usr/bin/env python3
"""
Validate production server at http://167.172.28.21/ is functioning correctly.

Checks:
- Health endpoint accessibility
- Chat UI loads
- WebSocket connection
- Database accessibility (via SSH)
- Service status (via SSH)
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import aiohttp
except ImportError:
    print("aiohttp not installed. Run: pip install aiohttp")
    sys.exit(1)


class ProductionValidator:
    def __init__(self):
        self.base_url = "http://167.172.28.21"
        self.ssh_key = Path.home() / ".ssh/amiga_deploy_ed25519"
        self.ssh_user = "amiga"
        self.results = []

    async def check_health_endpoint(self, session):
        """Verify /health endpoint responds."""
        try:
            async with session.get(f"{self.base_url}/health", timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.log_success("Health endpoint", f"Status: {data.get('status')}")
                    return True
                else:
                    self.log_failure("Health endpoint", f"HTTP {resp.status}")
                    return False
        except Exception as e:
            self.log_failure("Health endpoint", str(e))
            return False

    async def check_chat_ui(self, session):
        """Verify chat UI loads."""
        try:
            async with session.get(self.base_url, timeout=10) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    if "root" in html:  # React app mounts to #root
                        self.log_success("Chat UI", "Loads correctly")
                        return True
                    else:
                        self.log_failure("Chat UI", "Missing React root element")
                        return False
                else:
                    self.log_failure("Chat UI", f"HTTP {resp.status}")
                    return False
        except Exception as e:
            self.log_failure("Chat UI", str(e))
            return False

    async def check_websocket(self, session):
        """Verify Socket.IO endpoint is accessible."""
        try:
            # Socket.IO uses polling by default, check the endpoint is accessible
            socketio_url = f"{self.base_url}/socket.io/?EIO=4&transport=polling"
            async with session.get(socketio_url, timeout=10) as resp:
                if resp.status == 200:
                    self.log_success("Socket.IO", "Endpoint accessible")
                    return True
                else:
                    self.log_failure("Socket.IO", f"HTTP {resp.status}")
                    return False
        except Exception as e:
            self.log_failure("Socket.IO", str(e))
            return False

    async def check_ssh_access(self):
        """Verify SSH access and service status."""
        if not self.ssh_key.exists():
            self.log_failure("SSH access", f"Key not found: {self.ssh_key}")
            return False

        try:
            # Check service status
            proc = await asyncio.create_subprocess_exec(
                "ssh",
                "-i",
                str(self.ssh_key),
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=10",
                f"{self.ssh_user}@167.172.28.21",
                "sudo systemctl is-active amiga",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0 and stdout.decode().strip() == "active":
                self.log_success("SSH & Service", "Service is active")
                return True
            else:
                self.log_failure("SSH & Service", f"Service inactive: {stdout.decode().strip()}")
                return False
        except Exception as e:
            self.log_failure("SSH & Service", str(e))
            return False

    async def check_database_access(self):
        """Verify database is accessible via SSH."""
        if not self.ssh_key.exists():
            self.log_failure("Database", "SSH key not found")
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                "ssh",
                "-i",
                str(self.ssh_key),
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=10",
                f"{self.ssh_user}@167.172.28.21",
                "sqlite3 /opt/amiga/data/agentlab.db 'SELECT COUNT(*) FROM tasks;'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                count = stdout.decode().strip()
                self.log_success("Database", f"Accessible ({count} tasks)")
                return True
            else:
                self.log_failure("Database", stderr.decode().strip())
                return False
        except Exception as e:
            self.log_failure("Database", str(e))
            return False

    def log_success(self, check, message):
        """Log successful check."""
        self.results.append({"check": check, "status": "✓", "message": message})
        print(f"✓ {check}: {message}")

    def log_failure(self, check, message):
        """Log failed check."""
        self.results.append({"check": check, "status": "✗", "message": message})
        print(f"✗ {check}: {message}")

    async def run_all_checks(self):
        """Run all validation checks."""
        print(f"Validating production server: {self.base_url}\n")

        async with aiohttp.ClientSession() as session:
            # HTTP checks
            await self.check_health_endpoint(session)
            await self.check_chat_ui(session)
            await self.check_websocket(session)

        # SSH checks
        await self.check_ssh_access()
        await self.check_database_access()

        # Summary
        passed = sum(1 for r in self.results if r["status"] == "✓")
        total = len(self.results)
        print(f"\n{'=' * 50}")
        print(f"Results: {passed}/{total} checks passed")
        print(f"{'=' * 50}")

        return passed == total


async def main():
    validator = ProductionValidator()
    success = await validator.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
