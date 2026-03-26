"""Checks deeplink.json has all required keys.

Mobile clients refuse to connect if any key is missing. Required:
backendURL, backendWSURL, teamsURL, accountsURL, blackListURL, websiteURL, title.
"""

from __future__ import annotations

# External
import json

# Ours
from src.lib.base_target import BaseTarget
from src.lib.shell_safety import validate_domain_for_shell


# Keys that must be present in deeplink.json for mobile clients
_REQUIRED_KEYS: list[str] = [
    "backendURL",
    "backendWSURL",
    "teamsURL",
    "accountsURL",
    "blackListURL",
    "websiteURL",
    "title",
]


class DeeplinkJson(BaseTarget):
    """Checks deeplink.json completeness.

    Fetches from nginz-https endpoint and verifies all required keys.
    """

    # Uses SSH to admin host for curl checks
    requires_ssh: bool = True

    @property
    def description(self) -> str:
        """What this target checks."""
        return "deeplink.json completeness for mobile clients"

    @property
    def explanation(self) -> str:
        """Why this matters."""
        return (
            "Mobile clients refuse to connect if any required key is missing. "
            "Healthy when all keys present."
        )

    def _fetch_deeplink(self, domain: str) -> tuple[str, str]:
        """Fetch deeplink.json, falling back to NodePort if direct URL fails.

        Tries the standard URL first (https://nginz-https.<domain>/deeplink.json).
        If that fails with connection error (HTTP 0 / empty body), falls back
        to curling a kube node on the ingress NodePort with the correct Host
        header. This handles offline/private deployments where the domain
        resolves to an IP that isn't reachable from the admin host.

        Args:
            domain: Cluster domain.

        Returns:
            Tuple of (body, status_code) from the successful attempt.

        Raises:
            RuntimeError: If deeplink.json can't be fetched from either route.
        """
        validate_domain_for_shell(domain)
        url: str = f"https://nginz-https.{domain}/deeplink.json"

        self.terminal.step(f"Fetching {url}...")

        # -w appends status code so we can tell error from no response
        result = self.run_ssh(
            self.config.admin_host.ip,
            f"curl -s --max-time 10 -w '\\n%{{http_code}}' '{url}'",
        )

        body, status_code = self._parse_curl_output(result.stdout)

        # Connection failed — try the NodePort fallback before giving up
        if not body:
            nodeport: int = self.discover_ingress_https_nodeport()
            kube_ip: str = self.get_first_kube_node_ip()

            if nodeport and kube_ip:
                self.terminal.step(
                    f"Standard URL unreachable, trying NodePort {nodeport} "
                    f"on kube node {kube_ip}..."
                )
                fallback_url: str = f"https://{kube_ip}:{nodeport}/deeplink.json"
                fallback_result = self.run_ssh(
                    self.config.admin_host.ip,
                    f"curl -sk --max-time 10 -w '\\n%{{http_code}}' "
                    f"-H 'Host: nginz-https.{domain}' '{fallback_url}'",
                )
                body, status_code = self._parse_curl_output(fallback_result.stdout)

        if not body:
            raise RuntimeError(
                f"Can't fetch deeplink.json from {url} "
                f"(HTTP {status_code or 'no response'})"
            )

        if status_code and not status_code.startswith("2"):
            raise RuntimeError(
                f"deeplink.json fetch returned HTTP {status_code}: {body[:200]}"
            )

        return body, status_code

    @staticmethod
    def _parse_curl_output(raw_output: str) -> tuple[str, str]:
        """Split curl output into body and status code.

        Args:
            raw_output: Raw stdout from curl -w '\\n%{http_code}'.

        Returns:
            Tuple of (body, status_code).
        """
        raw: str = raw_output.strip()
        if "\n" in raw:
            body, status_code = raw.rsplit("\n", 1)
        else:
            body, status_code = raw, ""
        return body.strip(), status_code

    def collect(self) -> bool:
        """Fetch and validate deeplink.json.

        Returns:
            True if all keys present, False otherwise.

        Raises:
            RuntimeError: If deeplink.json can't be fetched or parsed.
        """
        domain: str = self.config.cluster.domain
        body, _status_code = self._fetch_deeplink(domain)

        try:
            deeplink: dict = json.loads(body)
        except json.JSONDecodeError:
            raise RuntimeError(f"deeplink.json is not valid JSON: {body[:200]}")

        # Keys may be nested under «endpoints» or «custom»
        data_to_check: dict = deeplink

        if "endpoints" in deeplink:
            data_to_check = deeplink["endpoints"]
            if data_to_check is None:
                data_to_check = {}
        elif "custom" in deeplink:
            data_to_check = deeplink.get("custom", {})
            if data_to_check is None:
                data_to_check = {}

        present: list[str] = []
        missing: list[str] = []

        for key in _REQUIRED_KEYS:
            if key in data_to_check:
                present.append(key)
            else:
                missing.append(key)

        all_present: bool = len(missing) == 0

        if all_present:
            self._health_info = f"All {len(_REQUIRED_KEYS)} required keys present"
        else:
            self._health_info = f"Missing keys: {', '.join(missing)}"

        return all_present
