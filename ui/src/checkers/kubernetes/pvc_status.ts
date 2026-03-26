/**
 * Makes sure all PersistentVolumeClaims are actually bound.
 *
 * If PVCs aren't bound, storage provisioning failed. Services relying
 * on persistent storage will break no silent failures here, they just
 * won't work. Pulls from kubernetes/pvc/all_bound.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import { coerce_boolean, type DataLookup } from '../data_lookup'

export class PvcStatusChecker extends BaseChecker {
    readonly path: string = 'kubernetes/pvc_status'
    readonly name: string = 'PVC status (all Bound)'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Health' as const
    readonly explanation: string = 'Confirms all **PersistentVolumeClaims** are in **Bound** state. Unbound PVCs indicate failed storage provisioning, which silently breaks any service that depends on persistent storage (databases, MinIO, etc.).'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/pvc/all_bound')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'PVC status data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/pvc/all_bound\n   ```\n3. Manually check: `kubectl get pvc -A`',
                recommendation: 'PVC status (all Bound) data not collected.',
            }
        }

        const all_bound = coerce_boolean(point.value)

        // Some PVCs are not bound storage provisioning failed
        if (all_bound === false) {
            return {
                status: 'unhealthy',
                status_reason: 'One or more PersistentVolumeClaims are **not in Bound state**.',
                fix_hint: '1. List all PVCs and their statuses:\n   ```\n   kubectl get pvc -A\n   ```\n2. Describe the unbound PVC(s) for events and conditions:\n   ```\n   kubectl describe pvc <name> -n <namespace>\n   ```\n3. Common causes:\n   - **StorageClass** not available or misconfigured\n   - **Storage provisioner** (e.g., `csi-driver`) not running or unhealthy\n   - **Insufficient disk space** on the storage backend\n   - PVC requesting more storage than available\n4. Check the storage provisioner pods:\n   ```\n   kubectl get pods -A | grep -i csi\n   ```\n5. If the StorageClass is missing: `kubectl get storageclass`',
                recommendation: 'Some PVCs are not in Bound state. Storage provisioning failed, which can silently break services needing persistent storage.',
                display_value: false,
                raw_output: point.raw_output,
            }
        }

        // All PVCs bound
        if (all_bound === true) {
            return {
                status: 'healthy',
                status_reason: 'All PersistentVolumeClaims are in Bound state.',
                display_value: true,
                raw_output: point.raw_output,
            }
        }

        // Value was neither boolean nor boolean-string — unexpected format
        return {
            status: 'gather_failure',
            status_reason: `PVC status data has an unexpected value: ${String(point.value)}`,
            recommendation: 'PVC status (all Bound) returned an unrecognised value.',
            raw_output: point.raw_output,
        }
    }
}

export default PvcStatusChecker
