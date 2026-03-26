/**
 * Base class for all foundation checkers.
 *
 * Each checker takes one or more data points (targets) from the JSONL output
 * and evaluates one aspect of deployment health. Checkers can mix data from
 * different targets to produce a single verdict. The checker's path is totally
 * separate from target paths.
 *
 * Every checker owns its own metadata: the explanation (why this check exists)
 * is a required property on the class, and the check result carries the status
 * assessment, fix instructions, and recommendation. DataPoint-level metadata
 * (commands, timestamps, health_info) lives on the DataPoints themselves and
 * is visible through the "Data points used" section in the details panel.
 *
 * All text fields (explanation, status_reason, fix_hint) are Handlebars
 * templates in Markdown format. The registry renders templates via Handlebars
 * using template_data, then the UI converts the Markdown to HTML.
 */

// Ours
import type { DataLookup } from './data_lookup'
import type { DataPoint } from '../sample-data'

export type CheckInterest = 'Health' | 'Setup' | 'Health, Setup'

// Use a named type so you can reference it directly. Beats using CheckResult['status'],
// which the TS language server can sometimes mess up from cached type inference.
export type CheckStatus = 'healthy' | 'warning' | 'unhealthy' | 'not_applicable' | 'gather_failure'

export interface CheckResult {
    status: CheckStatus

    // What we found — a brief explanation of WHY we arrived at this verdict.
    // Handlebars + Markdown template. Must be set on every code path so the
    // user always understands the reasoning.
    // Examples: "All 3 nodes are Up/Normal.", "Disk at **{{usage}}%**, above the 85% threshold."
    status_reason: string

    // How to fix this — actionable steps the operator should take.
    // Handlebars + Markdown template. Optional for healthy/not_applicable status;
    // should be present and detailed for unhealthy, warning, and gather_failure.
    fix_hint?: string

    recommendation?: string

    // What goes in the report (checker decides what matters)
    display_value?: string | number | boolean
    display_unit?: string

    // Raw output from consumed targets, shown in the details panel
    raw_output?: string
    // Actionable remediation steps shown in the details panel, may contain
    // Handlebars expressions rendered via template_data
    fix_hint?: string
    // Key-value context for Handlebars template rendering in status_reason,
    // fix_hint, etc. Every return path should include this so template-aware
    // features can operate on the result consistently.
    template_data?: Record<string, unknown>
    // For ConfigMap validation checkers, the actual service config (YAML/JSON)
    // from the configmap's data key, rendered in the ConfigMap panel with syntax highlighting
    configmap_data?: string

    // Variables for Handlebars template rendering. Keys are available as
    // {{variable_name}} in status_reason, fix_hint, and the checker's explanation.
    // The registry's run_checks() renders all templates automatically.
    template_data?: Record<string, unknown>
}

export interface CheckOutput extends CheckResult {
    // Checker identity
    path: string
    name: string
    category: string
    interest: CheckInterest

    // Why this check exists — always present, comes from the checker class.
    // Rendered Markdown (Handlebars already applied by run_checks).
    explanation: string

    // Collection context from the primary DataPoint (when, how long, where)
    collected_at?: string
    duration_seconds?: number
    gathered_from?: string

    // Commands the gatherer ran to collect the primary DataPoint
    commands?: string[]

    // DataPoints the checker accessed during evaluation, for the details panel
    data_points_used?: DataPoint[]
}

export abstract class BaseChecker {
    // Hierarchical path for this checker (e.g., «host_admin/load_average»)
    abstract readonly path: string

    // Label shown in the «What to look at» column
    abstract readonly name: string

    // Groups checkers, matches the categories in foundation-checks.html
    abstract readonly category: string

    // Which area does this matter for: Health, Setup, or both
    abstract readonly interest: CheckInterest

    // Why this check exists — shown in the details panel under "Why this check
    // exists". Every checker MUST provide a clear, user-facing explanation.
    abstract readonly explanation: string

    // True for checkers that depend on data from SSH-based targets (databases,
    // VMs, admin host). When only_through_kubernetes is set in the gathering
    // config, these checkers are automatically marked not_applicable.
    readonly requires_ssh: boolean = false

    // True for checkers that depend on data gathered from outside the cluster
    // (e.g. port reachability, SFTd HTTPS). When only_through_kubernetes is
    // set, these checkers are automatically marked not_applicable because
    // external-access targets are not collected in that mode.
    readonly requires_external_access: boolean = false

    // DataPoint path for collection context auto-attach. When a checker's
    // identity path differs from the target path it consumes, set this so
    // run_checks() finds the right DataPoint for commands and timestamps.
    readonly data_path?: string

    // Evaluate health by running the checker against the collected data
    abstract check(data: DataLookup): CheckResult
}
