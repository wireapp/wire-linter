/**
 * Makes sure your Kubernetes cluster is running a version that works with Wire.
 *
 * Pulls the kubernetes/nodes/k8s_version target, which gives us something like "v1.29.10".
 * We check the minor version number and flag anything below 1.27 as broken for Wire,
 * and warn you if it's below 1.29 since that's getting pretty old.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class K8sVersionChecker extends BaseChecker {
    readonly path: string = 'kubernetes/k8s_version'
    readonly name: string = 'Kubernetes version'
    readonly category: string = 'Kubernetes'
    readonly interest = 'Setup' as const
    readonly explanation: string = 'Verifies the Kubernetes cluster version is **compatible with Wire**. Versions below **1.27** are incompatible and will cause deployment failures; older versions may lack required API features or security patches.'

    check(data: DataLookup): CheckResult {
        const point = data.get('kubernetes/nodes/k8s_version')

        // Target data was not collected
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Kubernetes version data was not collected.',
                fix_hint: '1. Verify the gatherer has access to the Kubernetes API.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target kubernetes/nodes/k8s_version\n   ```\n3. Manually check: `kubectl version --short`',
                recommendation: 'Kubernetes version data not collected.',
            }
        }

        const version: string = point.value as string

        // Extract major.minor.patch from strings like "v1.29.10" or "1.27.5"
        const match: RegExpMatchArray | null = version.match(/v?(\d+)\.(\d+)\.(\d+)/)
        if (!match) {
            return {
                status: 'warning',
                status_reason: 'Could not parse a minor version number from "{{version}}".',
                fix_hint: '1. The version string **{{version}}** could not be parsed.\n2. Manually verify the Kubernetes version:\n   ```\n   kubectl version --short\n   ```\n3. Ensure nodes report a standard version format (e.g., `v1.29.10`).',
                recommendation: `Could not parse Kubernetes version from "${version}".`,
                display_value: version,
                raw_output: point.raw_output,
                template_data: { version },
            }
        }

        const major: number = parseInt(match[1] ?? '0', 10)
        const minor: number = parseInt(match[2] ?? '0', 10)

        // Only Kubernetes 1.x versions are expected
        if (major !== 1) {
            return {
                status: 'warning',
                status_reason: `Unexpected Kubernetes major version ${major} in "${version}".`,
                recommendation: `Kubernetes ${version} has unexpected major version ${major}. Expected 1.x.`,
                display_value: version,
                raw_output: point.raw_output,
            }
        }

        // Below 1.27 is incompatible with Wire
        if (minor < 27) {
            return {
                status: 'unhealthy',
                status_reason: 'Kubernetes **{{version}}** (minor {{minor}}) is below the minimum required version **1.27**.',
                fix_hint: '1. Kubernetes **{{version}}** is incompatible with Wire. Upgrade to **1.27** or later.\n2. Plan the upgrade path:\n   ```\n   kubeadm upgrade plan\n   ```\n3. Perform the upgrade one minor version at a time (e.g., 1.25 -> 1.26 -> 1.27):\n   ```\n   kubeadm upgrade apply v1.27.x\n   ```\n4. After upgrading the control plane, upgrade each node:\n   ```\n   kubectl drain <node> --ignore-daemonsets\n   # Upgrade kubelet and kubectl on the node\n   kubectl uncordon <node>\n   ```\n5. Verify: `kubectl get nodes`',
                recommendation: `Kubernetes ${version} is outdated. Upgrade to 1.27+ for Wire compatibility.`,
                display_value: version,
                raw_output: point.raw_output,
                template_data: { version, minor },
            }
        }

        // Below 1.29 is aging but still functional
        if (minor < 29) {
            return {
                status: 'warning',
                status_reason: 'Kubernetes **{{version}}** (minor {{minor}}) is approaching end-of-life, below the recommended **1.29**.',
                fix_hint: '1. Consider upgrading to Kubernetes **1.29** or later for continued security patches and support.\n2. Check the upgrade path:\n   ```\n   kubeadm upgrade plan\n   ```\n3. Perform the upgrade one minor version at a time:\n   ```\n   kubeadm upgrade apply v<next-minor>\n   ```\n4. After upgrading the control plane, upgrade each node:\n   ```\n   kubectl drain <node> --ignore-daemonsets\n   # Upgrade kubelet and kubectl on the node\n   kubectl uncordon <node>\n   ```',
                recommendation: `Kubernetes ${version} is approaching end-of-life. Consider upgrading to 1.29+.`,
                display_value: version,
                raw_output: point.raw_output,
                template_data: { version, minor },
            }
        }

        return {
            status: 'healthy',
            status_reason: 'Kubernetes **{{version}}** (minor {{minor}}) meets the recommended version threshold.',
            display_value: version,
            raw_output: point.raw_output,
            template_data: { version, minor },
        }
    }
}

export default K8sVersionChecker
