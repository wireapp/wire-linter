/**
 * Shows you how many certificate resources are in the cluster.
 * This is just informational it always comes back healthy.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { parse_number, type DataLookup } from '../data_lookup'

export class CertificateCountChecker extends BaseChecker {
    readonly path: string = 'kubernetes/certificate_count'
    readonly name: string = 'Certificate count'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Reports the number of **cert-manager Certificate resources** in the cluster. Provides a quick inventory to verify all expected certificates are provisioned.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/certificates/count')

        // Didn't manage to get the data
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Certificate count data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/certificates/count\n   ```\n3. Manually check: `kubectl get certificates -A`',
                recommendation: 'Couldn\'t collect certificate count data.',
            }
        }

        const count = parse_number(point)

        // Value couldn't be parsed as a number
        if (count === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Certificate count value could not be parsed as a number.',
                recommendation: 'The gathered certificate count data was not in a recognized numeric format.',
                raw_output: point.raw_output,
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Found **{{count}}** cert-manager Certificate resource(s) in the cluster.',
            display_value: count,
            display_unit: 'certs',
            raw_output: point.raw_output,
            template_data: { count },
        }
    }
}

export default CertificateCountChecker
