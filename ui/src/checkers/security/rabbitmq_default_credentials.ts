/**
 * Verifies RabbitMQ is not using default guest/guest credentials.
 *
 * Looks at the security/rabbitmq_default_credentials target (boolean).
 * Default credentials are a huge risk: any pod in the cluster can access
 * the message broker without proper auth.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class RabbitmqDefaultCredentialsChecker extends BaseChecker {
    readonly path: string = 'security/rabbitmq_default_credentials'
    readonly name: string = 'RabbitMQ credentials are non-default'
    readonly category: string = 'Security / Hardening'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Detects whether RabbitMQ is still using the default **guest/guest** credentials. Default credentials let any pod in the cluster access the message broker **without proper authentication**.'

    check(data: DataLookup): CheckResult {
        const point = data.get('security/rabbitmq_default_credentials')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Target data for `security/rabbitmq_default_credentials` was not collected by the gatherer.',
                fix_hint: '1. Verify the gatherer has access to the RabbitMQ management API or pod\n2. Check that `rabbitmqctl list_users` runs successfully\n3. Review the gatherer logs for connection errors or timeouts',
                recommendation: 'RabbitMQ default credentials check data not collected.',
            }
        }

        // Gatherer reached RabbitMQ but returned no value (e.g. connection error during collection)
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'RabbitMQ default credentials check data was collected but contained no value.',
                recommendation: 'Re-run the gatherer to collect RabbitMQ credential data.',
                raw_output: point.raw_output,
            }
        }

        // Normalize string booleans ("true"/"false") to actual booleans before comparison
        const val = coerce_boolean(point.value)

        // true means creds are non-default (good)
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'RabbitMQ credentials are **non-default**.',
                display_value: 'non-default',
                raw_output: point.raw_output,
            }
        }

        // false means creds are default (bad)
        if (val === false) {
            return {
                status: 'unhealthy',
                status_reason: 'RabbitMQ is still using the default **guest/guest** credentials.',
                fix_hint: '1. Change the default RabbitMQ password immediately:\n   ```\n   rabbitmqctl change_password guest <new-secure-password>\n   ```\n2. Better yet, delete the default `guest` user: `rabbitmqctl delete_user guest`\n3. Create a new admin user with a strong password:\n   ```\n   rabbitmqctl add_user <username> <password>\n   rabbitmqctl set_user_tags <username> administrator\n   rabbitmqctl set_permissions -p / <username> \".*\" \".*\" \".*\"\n   ```\n4. Update the RabbitMQ connection strings in your Wire helm values',
                recommendation: 'RabbitMQ is running with default guest/guest credentials. Any pod can access the broker. Set strong, unique credentials immediately.',
                display_value: 'default (guest/guest)',
                raw_output: point.raw_output,
            }
        }

        // String value that coerce_boolean could not convert: if it says "default", that's unhealthy
        const raw = point.value as string
        if (typeof raw === 'string' && raw.toLowerCase().includes('default')) {
            return {
                status: 'unhealthy',
                status_reason: `RabbitMQ is using default credentials: ${raw}.`,
                recommendation: 'RabbitMQ is running with default credentials. Any pod can access the broker. Set strong, unique credentials immediately.',
                display_value: raw,
                raw_output: point.raw_output,
                template_data: { credential_info: val },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'RabbitMQ credentials are non-default.',
            display_value: typeof raw === 'string' ? raw : 'non-default',
            raw_output: point.raw_output,
        }
    }
}

export default RabbitmqDefaultCredentialsChecker
