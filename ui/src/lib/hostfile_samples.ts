/**
 * Sample Ansible inventory data for testing.
 * Contains examples in both INI and YAML format these get loaded
 * by HostFileStep.vue so users can see the parser in action.
 */

// Sample INI format based on a real Wire multi-node setup
export const SAMPLE_HOSTFILE_INI = `[all]
datanode1 ansible_host=192.168.122.220
datanode2 ansible_host=192.168.122.193
datanode3 ansible_host=192.168.122.189

kubenode1 ansible_host=192.168.122.235 ip=192.168.122.235
kubenode2 ansible_host=192.168.122.202 ip=192.168.122.202
kubenode3 ansible_host=192.168.122.144 ip=192.168.122.144

assethost ansible_host=192.168.122.149

[cassandra]
datanode1
datanode2
datanode3

[cassandra_seed]
datanode1

[elasticsearch]
datanode1
datanode2
datanode3

[elasticsearch_master:children]
elasticsearch

[minio]
datanode1
datanode2
datanode3

[minio:vars]
minio_access_key = "AKIAEXAMPLE123"
minio_secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
prefix = "wire-"
domain = "robot-takeover.com"
deeplink_title = "Wire Example Environment"

[kube-master]
kubenode1
kubenode2
kubenode3

[kube-node]
kubenode1
kubenode2
kubenode3

[etcd]
kubenode1
kubenode2
kubenode3

[k8s-cluster:children]
kube-node
kube-master

[assethost]
assethost

[all:vars]
ansible_ssh_private_key_file = /home/demo/wire-server-deploy/ssh/id_ed25519
ansible_user = demo
ansible_python_interpreter = /usr/bin/python3
is_aws_environment = False
bootstrap_os = ubuntu`

// Sample YAML format from a Wire-in-a-Box staging setup
export const SAMPLE_HOSTFILE_YAML = `wiab-staging:
  hosts:
    deploy_node:
      ansible_host: robot-takeover.com
      ansible_ssh_common_args: '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=60 -o ServerAliveCountMax=3 -o TCPKeepAlive=yes'
      ansible_user: 'demo'
      ansible_ssh_private_key_file: "/home/arthur/.ssh/id_ed25519"
  vars:
    artifact_hash: f1f624256bdab0f9f76158c7f45e0618ee641237`
