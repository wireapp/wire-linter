/**
 * Checks if Kubernetes internal certificates are about to expire.
 *
 * Kubeadm creates certificates that last 1 year. These don't renew automatically,
 * so when they expire the whole control plane (apiserver, scheduler, controller-manager)
 * stops working. We get the expiration data from the tls/kubeadm_cert_expiration target
 * which tells us how many days are left.
 */

// Ours
import { BaseChecker, type CheckResult } from '../base_checker'
import type { DataLookup } from '../data_lookup'

export class KubeadmCertExpirationChecker extends BaseChecker {
    readonly path: string = 'tls/kubeadm_cert_expiration'
    readonly name: string = 'Kubernetes internal certificate expiration'
    readonly category: string = 'TLS / Certificates'
    readonly interest = 'Health' as const

    readonly requires_ssh: boolean = true
    readonly explanation: string = 'Monitors **kubeadm-managed internal certificates** that expire after one year and do not auto-renew. If missed, the entire Kubernetes control plane (`apiserver`, `scheduler`, `controller-manager`) stops functioning.'

    check(data: DataLookup): CheckResult {
        const point = data.get('tls/kubeadm_cert_expiration')

        // We didn't get any data for this check
        if (!point) {
            return {
                status: 'gather_failure',
                status_reason: 'Kubernetes internal certificate expiration data was not collected.',
                fix_hint: '1. Ensure the gatherer has **SSH access** to a control-plane node.\n2. Re-run the gatherer targeting this check:\n   ```\n   python3 src/script/runner.py --target tls/kubeadm_cert_expiration\n   ```\n3. On the control-plane node, verify `kubeadm` is available:\n   ```\n   kubeadm certs check-expiration\n   ```',
                recommendation: 'Kubernetes internal certificate expiration data not collected.',
            }
        }

        // Collection ran but the command failed
        if (point.value === null) {
            return {
                status: 'gather_failure',
                status_reason: 'Kubeadm certificate expiration data was collected but contained no value.',
                recommendation: point.metadata?.error ?? 'Kubeadm certificate expiration target ran but returned no result.',
                raw_output: point.raw_output,
            }
        }

        const val: string | number | boolean = point.value

        // If we got a number, it's how many days until the cert expires
        if (typeof val === 'number') {
            // Less than 30 days and we have a real problem
            if (val < 30) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Kubeadm certificates expire in **{{val}}** days, which is below the **30-day** critical threshold.',
                    fix_hint: '1. Renew kubeadm certificates **immediately** on the control-plane node:\n   ```\n   kubeadm certs renew all\n   ```\n2. Restart the control-plane static pods to pick up new certificates:\n   ```\n   crictl pods --name kube-apiserver -q | xargs -I{} crictl stopp {}\n   crictl pods --name kube-controller-manager -q | xargs -I{} crictl stopp {}\n   crictl pods --name kube-scheduler -q | xargs -I{} crictl stopp {}\n   ```\n3. Verify the renewed certificates:\n   ```\n   kubeadm certs check-expiration\n   ```\n4. If running multiple control-plane nodes, repeat on **each** node.',
                    recommendation: `Kubernetes internal certificates expire in ${val} days. These expire after 1 year and if missed the entire K8s control plane dies. Run kubeadm certs renew.`,
                    display_value: val,
                    display_unit: 'days',
                    raw_output: point.raw_output,
                    template_data: { val },
                }
            }

            // Less than 90 days means we should plan the renewal soon
            if (val < 90) {
                return {
                    status: 'warning',
                    status_reason: 'Kubeadm certificates expire in **{{val}}** days, which is below the **90-day** warning threshold.',
                    fix_hint: '1. Plan certificate renewal within the next **{{val}}** days.\n2. Check current expiration dates:\n   ```\n   kubeadm certs check-expiration\n   ```\n3. When ready, renew all certificates:\n   ```\n   kubeadm certs renew all\n   ```\n4. After renewal, restart the control-plane static pods to pick up new certificates.',
                    recommendation: `Kubernetes internal certificates expire in ${val} days. Plan renewal with kubeadm certs renew.`,
                    display_value: val,
                    display_unit: 'days',
                    raw_output: point.raw_output,
                    template_data: { val },
                }
            }

            // Still have plenty of time
            return {
                status: 'healthy',
                status_reason: 'Kubeadm certificates expire in **{{val}}** days, well above the **90-day** warning threshold.',
                display_value: val,
                display_unit: 'days',
                raw_output: point.raw_output,
                template_data: { val },
            }
        }

        // Sometimes we get a string. Check if it says the cert is expired
        if (typeof val === 'string') {
            if (val.toLowerCase().includes('expired')) {
                return {
                    status: 'unhealthy',
                    status_reason: 'Kubeadm certificate status indicates expiration: "{{val}}".',
                    fix_hint: '1. Kubeadm certificates have **expired**. The control plane is likely non-functional.\n2. Renew all certificates immediately:\n   ```\n   kubeadm certs renew all\n   ```\n3. Restart the control-plane static pods:\n   ```\n   crictl pods --name kube-apiserver -q | xargs -I{} crictl stopp {}\n   crictl pods --name kube-controller-manager -q | xargs -I{} crictl stopp {}\n   crictl pods --name kube-scheduler -q | xargs -I{} crictl stopp {}\n   ```\n4. Verify the cluster recovers: `kubectl get nodes`\n5. Check renewed certificate dates: `kubeadm certs check-expiration`',
                    recommendation: 'Kubernetes internal certificates have expired. The K8s control plane is likely non-functional. Run kubeadm certs renew immediately.',
                    display_value: val,
                    raw_output: point.raw_output,
                    template_data: { val },
                }
            }

            // Some other message that doesn't say expired. Call it healthy
            return {
                status: 'healthy',
                status_reason: 'Kubeadm certificate status reported as: "{{val}}".',
                display_value: val,
                raw_output: point.raw_output,
                template_data: { val },
            }
        }

        // If it's a boolean true, certs are fine
        if (val === true) {
            return {
                status: 'healthy',
                status_reason: 'Kubeadm certificate check returned **true**, indicating valid certificates.',
                display_value: val,
                raw_output: point.raw_output,
            }
        }

        // Boolean false means something went wrong with the check
        return {
            status: 'unhealthy',
            status_reason: 'Kubeadm certificate check returned **false**, indicating invalid or expired certificates.',
            fix_hint: '1. Investigate the certificate status on the control-plane node:\n   ```\n   kubeadm certs check-expiration\n   ```\n2. If certificates are expired or invalid, renew them:\n   ```\n   kubeadm certs renew all\n   ```\n3. Restart control-plane static pods after renewal.\n4. Verify the cluster is functional: `kubectl get nodes`',
            recommendation: 'Kubernetes internal certificate check returned false. Investigate with kubeadm certs check-expiration.',
            display_value: val,
            raw_output: point.raw_output,
        }
    }
}

export default KubeadmCertExpirationChecker
