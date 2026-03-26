"""Tests for the config loader in src/lib/config.py."""

import os
import tempfile
import unittest

from src.lib.config import Config, ConfigError, load_config


def make_valid_config_yaml(ssh_key_path: str) -> str:
    """Build a valid YAML config with the given SSH key path."""
    return f'''admin_host:
  ip: "10.0.0.1"
  user: "wire-admin"
  ssh_key: "{ssh_key_path}"
  ssh_port: 22

cluster:
  domain: "wire.example.com"
  kubernetes_namespace: "wire"

databases:
  cassandra: "10.0.0.10"
  elasticsearch: "10.0.0.11"
  minio: "10.0.0.12"
  postgresql: "10.0.0.13"

options:
  check_kubernetes: true
  check_databases: true
  check_network: true
  check_wire_services: true
  output_format: "jsonl"
  output_file: "results.jsonl"
'''


class TestConfig(unittest.TestCase):
    """Test load_config, ConfigError, and validation."""

    def test_valid_config(self) -> None:
        """Load full valid config without errors."""
        # Create a unique dummy SSH key via mkstemp (deterministic fd close)
        ssh_key_fd, ssh_key_path = tempfile.mkstemp(prefix="test_ssh_key_")
        os.close(ssh_key_fd)

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Write config YAML to temp file
                config_path = os.path.join(tmp_dir, "config.yaml")
                with open(config_path, "w") as f:
                    f.write(make_valid_config_yaml(ssh_key_path))

                config = load_config(config_path)

                # Check admin_host fields
                self.assertEqual(config.admin_host.ip, "10.0.0.1")
                self.assertEqual(config.admin_host.user, "wire-admin")
                self.assertEqual(config.admin_host.ssh_port, 22)
                self.assertIsInstance(config.admin_host.ssh_port, int)

                # Check cluster fields
                self.assertEqual(config.cluster.domain, "wire.example.com")
                self.assertEqual(config.cluster.kubernetes_namespace, "wire")

                # Check databases fields
                self.assertEqual(config.databases.cassandra, "10.0.0.10")

                # Check options fields
                self.assertIs(config.options.check_kubernetes, True)
        finally:
            # Clean up dummy SSH key
            if os.path.exists(ssh_key_path):
                os.remove(ssh_key_path)

    def test_missing_required_fields(self) -> None:
        """Report all missing fields at once."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w") as f:
                f.write("options:\n  check_kubernetes: true\n")

            with self.assertRaises(ConfigError) as ctx:
                load_config(config_path)

            # Expecting multiple errors collected together (admin_host, cluster, databases)
            self.assertGreater(len(ctx.exception.errors), 3)

    def test_invalid_ip_format(self) -> None:
        """Catch invalid IP addresses."""
        # Create a unique dummy SSH key so only the IP validation fails
        ssh_key_fd, ssh_key_path = tempfile.mkstemp(prefix="test_ssh_key_bad_ip_")
        os.close(ssh_key_fd)

        config_with_bad_ip = f'''admin_host:
  ip: "999.0.0.1"
  user: "wire-admin"
  ssh_key: "{ssh_key_path}"
  ssh_port: 22

cluster:
  domain: "wire.example.com"
  kubernetes_namespace: "wire"

databases:
  cassandra: "10.0.0.10"
  elasticsearch: "10.0.0.11"
  minio: "10.0.0.12"
  postgresql: "10.0.0.13"

options:
  check_kubernetes: true
'''

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                config_path = os.path.join(tmp_dir, "config.yaml")
                with open(config_path, "w") as f:
                    f.write(config_with_bad_ip)

                with self.assertRaises(ConfigError) as ctx:
                    load_config(config_path)

                # Check that error mentions IP or the bad address
                self.assertTrue(
                    any("IP" in e or "999.0.0.1" in e for e in ctx.exception.errors)
                )
        finally:
            if os.path.exists(ssh_key_path):
                os.remove(ssh_key_path)

    def test_missing_ssh_key_file(self) -> None:
        """Catch when SSH key file doesn't exist."""
        config_yaml = '''admin_host:
  ip: "10.0.0.1"
  user: "wire-admin"
  ssh_key: "/tmp/this_file_does_not_exist_12345"
  ssh_port: 22

cluster:
  domain: "wire.example.com"
  kubernetes_namespace: "wire"

databases:
  cassandra: "10.0.0.10"
  elasticsearch: "10.0.0.11"
  minio: "10.0.0.12"
  postgresql: "10.0.0.13"

options:
  check_kubernetes: true
'''

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.yaml")
            with open(config_path, "w") as f:
                f.write(config_yaml)

            with self.assertRaises(ConfigError) as ctx:
                load_config(config_path)

            # Error should mention SSH key or file not found
            self.assertTrue(
                any(
                    "ssh_key" in e.lower() or "not found" in e.lower() or "exist" in e.lower()
                    for e in ctx.exception.errors
                )
            )

    def test_ssh_port_range_validation(self) -> None:
        """Reject SSH ports outside 1-65535."""
        # Create a unique dummy SSH key via mkstemp (deterministic fd close)
        ssh_key_fd, ssh_key_path = tempfile.mkstemp(prefix="test_ssh_key_port_")
        os.close(ssh_key_fd)

        config_template = f'''admin_host:
  ip: "10.0.0.1"
  user: "wire-admin"
  ssh_key: "{ssh_key_path}"
  ssh_port: {{port}}

cluster:
  domain: "wire.example.com"
  kubernetes_namespace: "wire"

databases:
  cassandra: "10.0.0.10"
  elasticsearch: "10.0.0.11"
  minio: "10.0.0.12"
  postgresql: "10.0.0.13"

options:
  check_kubernetes: true
'''

        try:
            # Test port 0 (way too low)
            with tempfile.TemporaryDirectory() as tmp_dir:
                config_path = os.path.join(tmp_dir, "config.yaml")
                with open(config_path, "w") as f:
                    f.write(config_template.format(port=0))

                with self.assertRaises(ConfigError) as ctx:
                    load_config(config_path)

                self.assertTrue(
                    any("port" in e.lower() or "0" in e for e in ctx.exception.errors)
                )

            # Test port 70000 (way too high)
            with tempfile.TemporaryDirectory() as tmp_dir:
                config_path = os.path.join(tmp_dir, "config.yaml")
                with open(config_path, "w") as f:
                    f.write(config_template.format(port=70000))

                with self.assertRaises(ConfigError) as ctx:
                    load_config(config_path)

                self.assertTrue(
                    any("port" in e.lower() or "70000" in e for e in ctx.exception.errors)
                )
        finally:
            if os.path.exists(ssh_key_path):
                os.remove(ssh_key_path)

    def test_invalid_database_ip(self) -> None:
        """Should catch invalid database IPs."""
        # Create a unique dummy SSH key via mkstemp (deterministic fd close)
        ssh_key_fd, ssh_key_path = tempfile.mkstemp(prefix="test_ssh_key_db_ip_")
        os.close(ssh_key_fd)

        config_yaml = f'''admin_host:
  ip: "10.0.0.1"
  user: "wire-admin"
  ssh_key: "{ssh_key_path}"
  ssh_port: 22

cluster:
  domain: "wire.example.com"
  kubernetes_namespace: "wire"

databases:
  cassandra: "not-an-ip"
  elasticsearch: "10.0.0.11"
  minio: "10.0.0.12"
  postgresql: "10.0.0.13"

options:
  check_kubernetes: true
'''

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                config_path = os.path.join(tmp_dir, "config.yaml")
                with open(config_path, "w") as f:
                    f.write(config_yaml)

                with self.assertRaises(ConfigError) as ctx:
                    load_config(config_path)

                # Error should mention the bad IP or the cassandra field
                self.assertTrue(
                    any(
                        "not-an-ip" in e or "cassandra" in e.lower()
                        for e in ctx.exception.errors
                    )
                )
        finally:
            if os.path.exists(ssh_key_path):
                os.remove(ssh_key_path)

    def test_config_file_not_found(self) -> None:
        """Should raise when config file doesn't exist."""
        with self.assertRaises((ConfigError, FileNotFoundError)):
            load_config("/nonexistent/config.yaml")


if __name__ == '__main__':
    unittest.main()
