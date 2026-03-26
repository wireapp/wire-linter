"""Main runner orchestration class.

Loads config, discovers targets, filters by pattern, executes each target,
writes JSONL output, and prints the final summary.

When you run with --parallel N where N > 1, targets run in a thread pool.
Each target gets its own BufferedTerminal to collect output independently,
then flushes atomically when done. This keeps output clean while letting
I/O-bound targets (SSH, HTTP, kubectl) overlap.
"""

from __future__ import annotations

# External
import concurrent.futures
import os
import threading
import time
from dataclasses import asdict
from typing import Any

# Ours
from src.lib.config import load_config, ConfigError, Config
from src.lib.dry_run import CommandRecord, format_dry_run_table
from src.lib.terminal import Terminal, BufferedTerminal, Verbosity
from src.lib.logger import Logger, LogLevel
from src.lib.output import JsonlWriter
from src.lib.base_target import BaseTarget, TargetResult
from src.lib.per_host_target import PerHostTarget
from src.lib.preflight import PreflightChecker, PreflightResult
from src.lib.target_discovery import discover_targets, filter_targets, DiscoveredTarget
from src.lib.wire_service_helpers import clear_pod_cache


class Runner:
    """Main runner that orchestrates target execution.

    Flow: load config, discover targets, filter by pattern, execute them,
    write results to JSONL, then print a summary.

    In parallel mode, targets run in a thread pool with each getting its own
    BufferedTerminal. When a target finishes, its output flushes atomically
    to the real terminal. The JSONL writer uses a lock to stay thread-safe.
    """

    def __init__(
        self,
        config_path:        str,
        output_path:        str,
        target_pattern:     str      = "*",
        verbosity:          Verbosity = Verbosity.NORMAL,
        use_color:          bool     = True,
        gathered_from:      str      = "admin-host",
        only_through_kubernetes: bool = False,
        parallel:           int      = 1,
        only_preflight:     bool     = False,
        force_no_preflight: bool     = False,
        network_name:       str      = "",
        source_type:        str      = "backend",
        cluster_type:       str      = "both",
        kubeconfig_path:    str      = "",
        dry_run:            bool     = False,
    ) -> None:
        """Initialize the runner.

        Args:
            config_path:        Path to the YAML config file.
            output_path:        Path to the JSONL output file (unused when only_preflight).
            target_pattern:     Target filter pattern (default '*' = all).
            verbosity:          Terminal output detail level.
            use_color:          Whether to use ANSI colors in output.
            gathered_from:      'admin-host' (on the Wire deploy host),
                                'ssh-into-admin-host' (SSH from remote machine), or
                                'client' (client-side probe — no SSH/kubectl).
            only_through_kubernetes: When True, skip targets that need SSH and only
                                run kubectl-based targets. For deployments where only
                                Kubernetes access is available.
            parallel:           Number of targets to run concurrently. 1 = sequential.
            only_preflight:     Run only pre-flight checks and exit without collecting targets.
                                Handy for validating config before a full run.
            force_no_preflight: Skip pre-flight checks and go straight to collection.
                                Use when you know connectivity is good or pre-flight is slow.
            network_name:       Human-readable label for this runner invocation.
            source_type:        'backend' or 'client', derived from gathered_from.
            cluster_type:       'both', 'main', or 'calling'. Controls which targets
                                run based on their cluster affinity.
            kubeconfig_path:    Path to kubeconfig file (empty = use default).
            dry_run:            When True, no commands execute. Instead, each target
                                records what it would have done, and a summary table
                                is printed at the end.
        """
        self.config_path:        str      = config_path
        self.output_path:        str      = output_path
        self.target_pattern:     str      = target_pattern
        self.verbosity:          Verbosity = verbosity
        self.use_color:          bool     = use_color
        self.gathered_from:      str      = gathered_from
        self.only_through_kubernetes: bool = only_through_kubernetes
        self.parallel:           int      = parallel
        self.only_preflight:     bool     = only_preflight
        self.force_no_preflight: bool     = force_no_preflight
        self.network_name:       str      = network_name
        self.source_type:        str      = source_type
        self.cluster_type:       str      = cluster_type
        self.kubeconfig_path:    str      = kubeconfig_path
        self.dry_run:            bool     = dry_run

        # Create terminal and logger instances for use throughout run()
        self.terminal: Terminal = Terminal(verbosity=verbosity, use_color=use_color)
        self.logger: Logger = Logger(
            level=LogLevel.DEBUG if verbosity == Verbosity.VERBOSE else LogLevel.INFO
        )

    def run(self) -> int:
        """Execute the full runner workflow.

        Exit codes:
            0 all targets passed (or pre-flight passed when only_preflight=True)
            1 one or more targets failed to collect data
            2 config file could not be loaded or validated
            3 pre-flight connectivity checks failed

        Returns:
            Exit code as described above.
        """
        # Print the banner header
        self.terminal.header('Wire Fact Gathering Tool')

        # Load and validate the config file
        try:
            config: Config = load_config(self.config_path, gathered_from=self.gathered_from)
        except ConfigError as error:
            # Show all validation errors at once so the user can fix them together
            for err in error.errors:
                self.terminal.error(err)
            return 2

        # Add the CLI-specified source context (not stored in YAML)
        config.gathered_from = self.gathered_from
        config.only_through_kubernetes = self.only_through_kubernetes
        config.network_name = self.network_name
        config.source_type = self.source_type
        config.cluster_type = self.cluster_type
        config.dry_run = self.dry_run

        # Print config summary after successful loading
        if self.gathered_from == 'client':
            # client mode: minimal summary (no admin host info)
            self.terminal.info(
                f"Config loaded: cluster domain: {config.cluster.domain}"
            )
        else:
            self.terminal.info(
                f"Config loaded: {config.admin_host.user}@{config.admin_host.ip}, "
                f"cluster: {config.cluster.domain}"
            )

        self.terminal.info(f"Source: {config.gathered_from} ({config.source_type})")

        if self.network_name:
            self.terminal.info(f"Network name: {self.network_name}")

        if config.cluster_type != 'both':
            self.terminal.info(f"Cluster type: {config.cluster_type}")

        if config.only_through_kubernetes:
            self.terminal.info("Mode: kubernetes-only (SSH targets will be skipped)")

        # Show kubeconfig information for backend mode
        if self.gathered_from != 'client':
            if self.kubeconfig_path:
                self.terminal.info(f"Kubeconfig: {self.kubeconfig_path}")
            else:
                # Show what default kubeconfig path is being used.
                # On Wire-managed admin hosts, the real kubeconfig is typically at
                # ~/wire-server-deploy/ansible/inventory/kubeconfig.dec (not ~/.kube/config).
                # When running in Docker mode, the runner mounts wire-server-deploy into the
                # container and the image finds it automatically.
                default_kube: str = os.environ.get('KUBECONFIG', '')
                if default_kube:
                    self.terminal.info(f"No --kubeconfig specified. KUBECONFIG env var: {default_kube}")
                else:
                    self.terminal.info(
                        "No --kubeconfig specified. kubectl will use its default context. "
                        "In Docker mode, the kubeconfig is found automatically via the "
                        "wire-server-deploy volume mount."
                    )

        if self.dry_run:
            self.terminal.info("Mode: dry run (no commands will be executed)")
        elif not self.only_preflight:
            self.terminal.info(f"Output: {self.output_path}")

        self.terminal.blank_line()

        # Dry-run mode: skip preflight, go straight to target discovery and recording
        if self.dry_run:
            return self._run_dry_run(config)

        # Client mode skips preflight entirely — no SSH or kubectl to check
        if self.gathered_from == 'client':
            self.terminal.info(
                "Client mode: skipping preflight checks (no SSH/kubectl in client mode)."
            )
            self.terminal.blank_line()
        elif self.only_preflight and self.force_no_preflight:
            # Contradictory flags: the operator asked for preflight-only but also told
            # the runner to skip preflight entirely. Honour the safer intent (no full run)
            # and exit with a clear error rather than silently running a full collection.
            self.terminal.error(
                "--only-preflight and --force-no-preflight-checks are contradictory: "
                "cannot run preflight-only mode when preflight checks are disabled. "
                "Remove one of the two flags and re-run."
            )
            return 1
        elif self.force_no_preflight:
            # User skipped pre-flight warn and continue
            self.terminal.warning(
                "Pre-flight checks skipped (--force-no-preflight-checks). "
                "Connectivity is not verified - targets may fail if credentials "
                "or hosts are misconfigured."
            )
            self.terminal.blank_line()
        else:
            # Explain what's about to happen
            self.terminal.info(
                "Running pre-flight checks to verify that the configuration is "
                "correct and all targets are reachable before collecting data. "
                "This catches SSH key problems, unreachable hosts, and Kubernetes "
                "connectivity issues early so they do not silently corrupt the results."
            )
            self.terminal.blank_line()

            preflight: PreflightChecker = PreflightChecker(config, self.terminal, self.logger)
            preflight_results: list[PreflightResult] = preflight.run_checks()

            # Any check that is not skipped and not successful is a hard blocker
            preflight_failed: list[PreflightResult] = [
                r for r in preflight_results if not r.success and not r.skipped
            ]

            if self.only_preflight:
                # Pre-flight-only mode exit here with the appropriate code
                return 0 if not preflight_failed else 3

            if preflight_failed:
                # Explain what failed and offer the bypass option
                self.terminal.error(
                    "Not collecting data because the pre-flight checks above failed. "
                    "Fix the connectivity issues and re-run, or use "
                    "--force-no-preflight-checks to bypass these checks and collect anyway."
                )
                return 3

            # All checks passed moving on to collection
            self.terminal.info(
                "Configuration verified - all targets are reachable. Collecting data now."
            )
            self.terminal.blank_line()

        # Clear class-level caches so consecutive runs in the same process
        # (tests, REPL, library usage) don't leak values from a prior cluster.
        BaseTarget.reset_caches()
        clear_pod_cache()

        # Find the targets directory
        targets_dir: str = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'targets'
        )

        # Scan for all available targets
        discovered: list[DiscoveredTarget] = discover_targets(targets_dir)
        self.terminal.info(f"Discovered {len(discovered)} targets")

        # Apply the user's target pattern
        try:
            targets: list[DiscoveredTarget] = filter_targets(
                discovered, self.target_pattern
            )
            self.terminal.info(
                f"Running {len(targets)} targets (pattern: '{self.target_pattern}')"
            )
        except ValueError as error:
            self.terminal.error(str(error))
            return 1

        # Show worker count when parallel
        if self.parallel > 1:
            self.terminal.info(f"Parallel workers: {self.parallel}")

        # Context manager ensures the file is closed even if write_config or targets raise
        with JsonlWriter(self.output_path) as writer:

            # Write the full config (including credentials) as the first line so the
            # report UI can reference it. Credentials in the JSONL output are intentional:
            # the file is used by operators and support teams who already have access to
            # these credentials, and the UI needs them for live diagnostic probes.
            config_dict: dict[str, Any] = asdict(config)
            # raw is the unparsed YAML dict redundant with the structured fields
            del config_dict['raw']
            writer.write_config(config_dict)

            # Track start time and results
            start_time: float = time.monotonic()
            all_results: list[TargetResult] = []

            if self.parallel > 1:
                all_results = self._run_parallel(targets, config, writer)
            else:
                all_results = self._run_sequential(targets, config, writer)

        # Print the summary table with wall-clock time (not sum of durations)
        elapsed: float = time.monotonic() - start_time
        self.terminal.summary(all_results, runtime_seconds=elapsed)

        # Return 1 if nothing was collected
        if not all_results:
            return 1

        # Return 0 if all passed, 1 if any failed
        return 0 if all(r.success for r in all_results) else 1

    def _run_sequential(
        self,
        targets: list[DiscoveredTarget],
        config: Config,
        writer: JsonlWriter,
    ) -> list[TargetResult]:
        """Execute targets one at a time, printing directly to the terminal.

        Args:
            targets: Discovered targets to execute.
            config: Validated runner configuration.
            writer: JSONL output writer.

        Returns:
            List of all target results.
        """
        all_results: list[TargetResult] = []

        for discovered_target in targets:
            # Create the target instance
            target_instance = discovered_target.target_class(
                config, self.terminal, self.logger
            )

            # Store the target's path
            target_instance._path = discovered_target.path

            # Per-host targets generate multiple results, others generate one
            if discovered_target.is_per_host:
                results: list[TargetResult] = target_instance.execute_all()
            else:
                result: TargetResult = target_instance.execute()
                results = [result]

            # Write results to JSONL
            for target_result in results:
                if target_result.data_point is not None:
                    writer.write(target_result.data_point)

            # Accumulate results
            all_results.extend(results)

            # Blank line between targets
            self.terminal.blank_line()

        return all_results

    def _run_parallel(
        self,
        targets: list[DiscoveredTarget],
        config: Config,
        writer: JsonlWriter,
    ) -> list[TargetResult]:
        """Execute targets concurrently using a thread pool.

        Each target gets its own BufferedTerminal to capture output independently.
        When a target finishes, its buffered output flushes atomically to the real
        terminal. JSONL writes happen incrementally in the main thread via
        as_completed, so partial results survive a crash. The summary uses indexed
        storage to preserve submission order.

        Args:
            targets: Discovered targets to execute.
            config: Validated runner configuration.
            writer: JSONL output writer.

        Returns:
            List of all target results in the same order as the input targets.
        """
        # Lock keeps terminal output flushes atomic across worker threads
        output_lock: threading.Lock = threading.Lock()

        def execute_target(
            discovered_target: DiscoveredTarget,
        ) -> list[TargetResult]:
            """Run a single target with a buffered terminal, then flush its output.

            Runs in a worker thread. Creates its own BufferedTerminal and Logger
            so output is isolated. After execution, acquires the lock and flushes
            the buffer atomically.

            Args:
                discovered_target: The target to execute.

            Returns:
                List of results from this target.
            """
            # Each worker gets its own buffered terminal and logger
            buffered_terminal: BufferedTerminal = BufferedTerminal(
                verbosity=self.verbosity,
                use_color=self.use_color,
            )
            target_logger: Logger = Logger(
                level=LogLevel.DEBUG
                if self.verbosity == Verbosity.VERBOSE
                else LogLevel.INFO
            )

            # Create the target instance with the buffered terminal
            target_instance = discovered_target.target_class(
                config, buffered_terminal, target_logger
            )
            target_instance._path = discovered_target.path

            # Execute output goes to the buffer
            if discovered_target.is_per_host:
                results: list[TargetResult] = target_instance.execute_all()
            else:
                single_result: TargetResult = target_instance.execute()
                results = [single_result]

            # Flush terminal output atomically under the lock
            with output_lock:
                buffered_terminal.flush_to(self.terminal)

                # Blank line between targets
                self.terminal.blank_line()

            return results

        # Indexed storage so we can return results in submission order
        indexed_results: list[list[TargetResult] | None] = [None] * len(targets)

        # Map each future back to its submission index and target
        future_to_index: dict[concurrent.futures.Future[list[TargetResult]], int] = {}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.parallel,
        ) as executor:
            # Submit all targets to the thread pool (targets are I/O-bound)
            for index, discovered_target in enumerate(targets):
                future: concurrent.futures.Future[list[TargetResult]] = (
                    executor.submit(execute_target, discovered_target)
                )
                future_to_index[future] = index

            # Write JSONL as each future completes so partial results survive a crash
            for future in concurrent.futures.as_completed(future_to_index):
                idx: int = future_to_index[future]
                try:
                    results: list[TargetResult] = future.result()

                    # Persist to JSONL immediately (flush happens inside writer.write)
                    for target_result in results:
                        if target_result.data_point is not None:
                            writer.write(target_result.data_point)

                    indexed_results[idx] = results
                except Exception as error:
                    # Safety net: execute() should catch exceptions internally.
                    # Create a synthetic error result so the target is not silently
                    # omitted from the summary and JSONL output.
                    # Buffer the error message and flush under the lock so the main
                    # thread never writes to the terminal concurrently with a worker.
                    error_terminal: BufferedTerminal = BufferedTerminal(
                        verbosity=self.verbosity,
                        use_color=self.use_color,
                    )
                    error_terminal.error(
                        f"Unexpected parallel execution error in "
                        f"{targets[idx].path}: {error}"
                    )
                    with output_lock:
                        error_terminal.flush_to(self.terminal)
                    error_result: TargetResult = TargetResult(
                        data_point=None,
                        success=False,
                        error=str(error),
                        duration_seconds=0.0,
                    )
                    indexed_results[idx] = [error_result]

        # Flatten in submission order for a deterministic summary
        all_results: list[TargetResult] = []
        for result_group in indexed_results:
            if result_group is not None:
                all_results.extend(result_group)

        return all_results

    def _run_dry_run(self, config: Config) -> int:
        """Execute targets in dry-run mode: record commands without running them.

        Discovers and filters targets normally, then runs each target sequentially
        with a quiet terminal. No commands are actually executed (the execution
        methods in BaseTarget check config.dry_run and record instead). At the
        end, prints a table of all commands that would have been run.

        Always runs sequentially since there is no I/O to overlap.

        Args:
            config: Validated runner configuration (with dry_run=True).

        Returns:
            Exit code: 0 always (dry-run cannot fail).
        """
        # Clear class-level caches (same as normal run)
        BaseTarget.reset_caches()
        clear_pod_cache()

        # Find and filter targets
        targets_dir: str = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'targets'
        )

        discovered: list[DiscoveredTarget] = discover_targets(targets_dir)
        self.terminal.info(f"Discovered {len(discovered)} targets")

        try:
            targets: list[DiscoveredTarget] = filter_targets(
                discovered, self.target_pattern
            )
            self.terminal.info(
                f"Analyzing {len(targets)} targets (pattern: '{self.target_pattern}')"
            )
        except ValueError as error:
            self.terminal.error(str(error))
            return 1

        self.terminal.blank_line()

        # Use a quiet terminal for target execution so collect() errors
        # don't flood the output. The only output we want is the final table.
        quiet_terminal: Terminal = Terminal(
            verbosity=Verbosity.QUIET, use_color=self.use_color,
        )
        quiet_logger: Logger = Logger(level=LogLevel.INFO)

        # Execute each target sequentially, collecting dry-run records
        all_records: list[CommandRecord] = []
        has_iterable_targets: bool = False

        for discovered_target in targets:
            target_instance = discovered_target.target_class(
                config, quiet_terminal, quiet_logger,
            )
            target_instance._path = discovered_target.path

            # Run the target (all execution methods will record instead of executing)
            if discovered_target.is_per_host:
                target_instance.execute_all()
                has_iterable_targets = True
            else:
                target_instance.execute()

            # Collect any recorded commands
            all_records.extend(target_instance._dry_run_records)

        # Print the dry-run summary table
        self.terminal._print(f"\033[1m\u2550\u2550\u2550 Dry Run: {len(all_records)} commands would be executed \u2550\u2550\u2550\033[0m"
                             if self.use_color
                             else f"=== Dry Run: {len(all_records)} commands would be executed ===")
        self.terminal._print("")

        table: str = format_dry_run_table(all_records, use_color=self.use_color)
        self.terminal._print(table)

        # Note about dynamically-discovered targets
        if has_iterable_targets:
            self.terminal._print("")
            note_color: str = "\033[90m" if self.use_color else ""
            reset: str = "\033[0m" if self.use_color else ""
            self.terminal._print(
                f"{note_color}Note: Some targets iterate over hosts or services "
                f"discovered at runtime (e.g. via kubectl get nodes).{reset}"
            )
            self.terminal._print(
                f"{note_color}Per-item commands for those targets cannot be fully shown "
                f"without running the discovery commands first.{reset}"
            )

        self.terminal._print("")

        return 0

