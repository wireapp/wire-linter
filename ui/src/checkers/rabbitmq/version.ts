/**
 * Grabs the RabbitMQ version and flags it if it's EOL.
 *
 * Reads databases/rabbitmq/version. RabbitMQ versions have support windows.
 * Old ones stop getting security patches.
 *
 * @see https://www.rabbitmq.com/release-information
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

// EOL versions don't get security patches anymore. Keep this list updated
// as new RabbitMQ releases go EOL.
const _EOL_MAJOR_MINOR: string[] = [
    '3.8',
    '3.9',
    '3.10',
    '3.11',
    '3.12',
]

// Oldest version we still consider acceptable
const _MIN_RECOMMENDED: string = '3.13'

// Pull major.minor out of a version string like "3.9.27"
function extract_major_minor(version: string): string | null {
    const match = version.match(/(\d+\.\d+)/)
    return match ? match[1] ?? null : null
}

export class VersionChecker extends BaseChecker {
    readonly path: string = 'rabbitmq/version'
    readonly name: string = 'RabbitMQ version'
    readonly category: string = 'Data / RabbitMQ'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Identifies the installed **RabbitMQ version** and flags **end-of-life** releases. EOL versions no longer receive security patches, leaving the message broker vulnerable to known exploits.'

    check(data: DataLookup): CheckResult {
        // RabbitMQ is more critical when federation is enabled (async event processing).
        // Without federation, downgrade failures from unhealthy to warning.
        const rmq_failure_severity: 'unhealthy' | 'warning' = (
            data.config?.options?.expect_federation ? 'unhealthy' : 'warning'
        )

        const point = data.get_applicable('databases/rabbitmq/version') ?? data.get('direct/rabbitmq/version')

        // Didn't get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ version data was not collected.',
                fix_hint: '1. Verify connectivity to the RabbitMQ node\n2. Check that `rabbitmqctl version` or `rabbitmqctl status` runs successfully\n3. If using the management API: `curl -u guest:guest http://<host>:15672/api/overview`\n4. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'Couldn\'t collect RabbitMQ version data.',
            }
        }

        const version: string = String(point.value)
        const major_minor: string | null = extract_major_minor(version)

        // Couldn't parse it, just show what we got
        if (!major_minor) {
            return {
                status: 'healthy',
                status_reason: 'RabbitMQ version is `{{version}}` (unable to parse major.minor for EOL check).',
                display_value: version,
                raw_output: point.raw_output,
                template_data: { version },
            }
        }

        // Is this an EOL version?
        if (_EOL_MAJOR_MINOR.includes(major_minor)) {
            return {
                status: 'warning',
                status_reason: 'RabbitMQ `{{version}}` (**{{major_minor}}**) is **end-of-life** and no longer receives security patches.',
                fix_hint: '1. Check current version: `rabbitmqctl version`\n2. Review the [RabbitMQ release information](https://www.rabbitmq.com/release-information) for upgrade paths\n3. Plan an upgrade to **{{min_recommended}}** or later\n4. Follow the [RabbitMQ upgrade guide](https://www.rabbitmq.com/upgrade.html) for your deployment type\n5. After upgrading, verify the cluster is healthy: `rabbitmqctl cluster_status`',
                recommendation: `RabbitMQ ${version} is EOL and doesn't get security patches anymore. Upgrade to ${_MIN_RECOMMENDED}+.`,
                display_value: `${version} (EOL)`,
                raw_output: point.raw_output,
                template_data: { version, major_minor, min_recommended: _MIN_RECOMMENDED },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'RabbitMQ version `{{version}}` is supported and receiving updates.',
            display_value: version,
            raw_output: point.raw_output,
            template_data: { version },
        }
    }
}

export default VersionChecker
