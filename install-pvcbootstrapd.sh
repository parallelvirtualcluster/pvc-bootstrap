#!/usr/bin/env bash

# PVC Bootstrap system installer

username="${USER}"

echo "Welcome to the PVC bootstrap installer. This will guide you through the setup process."
echo
echo "The PVC bootstrap system will be installed as user: ${username}"
echo
echo "Please enter the bootstrap root directory; all components will be installed here:"
echo -n "[/srv/pvc] > "
read root_directory
if [[ -z ${root_directory} ]]; then
    root_directory="/srv/pvc"
fi
echo

echo "Please enter the IP network for the Bootstrap network (MUST be an RFC1918 /24):"
echo -n "[10.255.255.0/24] > "
read bootstrap_network
if [[ -z ${bootstrap_network} ]]; then
    bootstrap_network="10.255.255.0/24"
fi
echo

echo "Will the bootstrap interface be a vLAN? Note: It should not be configured yet if so!"
echo -n "[y/N] > "
read is_bootstrap_interface_vlan
case ${is_bootstrap_interface_vlan} in
    y|Y|yes|Yes|YES) is_bootstrap_interface_vlan="yes" ;;
    *) is_bootstrap_interface_vlan="no" ;;
esac
echo

all_interfaces=( $(
    ip address | grep '^[0-9]' | grep 'bond\|eth\|eno\|enp\|ens\|wlan\|wlp' | awk '{ print $2 }' | tr -d ':'
) )

if [[ "${is_bootstrap_interface_vlan}" == "yes" ]]; then
echo "Please enter the underlying device for the Bootstrap network vLAN:"
else
echo "Please enter the Bootstrap network interface:"
fi
echo "Available interfaces: ${all_interfaces[@]}"
bootstrap_interface=""
while true; do
    echo -n "> "
    read bootstrap_interface
    if [[ -n ${bootstrap_interface} && "${all_interfaces[@]}" =~ "${bootstrap_interface}" ]]; then
        break
    fi
done
echo

if [[ "${is_bootstrap_interface_vlan}" == "yes" ]]; then
echo "Please enter the Bootstrap network vLAN ID:"
echo -n "> "
read bootstrap_vlan
echo
fi

echo "Please enter the upstream network interface for outbound NAT:"
echo "Available interfaces: ${all_interfaces[@]}"
upstream_interface=""
while true; do
    echo -n "> "
    read upstream_interface
    if [[ -n ${upstream_interface} && "${all_interfaces[@]}" =~ "${upstream_interface}" ]]; then
        break
    fi
done
echo

echo "Please enter the Git remote (SSH-only) for your local PVC repository:"
while [[ -z ${git_remote} ]]; do
echo -n "> "
read git_remote
done
echo

echo "Please enter the branch to use from the local PVC repository:"
echo -n "[master] > "
read git_branch
if [[ -z ${git_branch} ]]; then
    git_branch="master"
fi
echo

echo "Please enter a username for Ansible management of the clusters:"
echo -n "[deploy] > "
read deploy_username
if [[ -z ${deploy_username} ]]; then
    deploy_username="deploy"
fi
echo

echo "Please enter an upstream Debian mirror (hostname+directory without scheme) to use (e.g. ftp.debian.org/debian):"
echo -n "[ftp.debian.org/debian] > "
read upstream_mirror
if [[ -z ${upstream_mirror} ]]; then
    upstream_mirror="ftp.debian.org/debian"
fi
echo

echo "Please enter the default Debian release for new clusters (e.g. 'bullseye', 'bookworm'):"
echo -n "[bookworm] > "
read debian_release
if [[ -z ${debian_release} ]]; then
    debian_release="bookworm"
fi
echo

echo "Proceeding with setup!"
echo

echo "Installing APT dependencies..."
sudo apt-get update
sudo apt-get install --yes vlan iptables dnsmasq redis python3 python3-pip python3-requests python3-git sqlite3 celery pxelinux syslinux-common live-build debootstrap uuid-runtime qemu-user-static apt-cacher-ng

echo "Configuring apt-cacher-ng..."
sudo systemctl enable --now apt-cacher-ng
if ! grep -q ${upstream_mirror} /etc/apt-cacher-ng/backends_debian; then
    echo "http://${upstream_mirror}" | sudo tee /etc/apt-cacher-ng/backends_debian &>/dev/null
    sudo systemctl restart apt-cacher-ng
fi

echo "Configuring dnsmasq..."
sudo systemctl disable --now dnsmasq
# Required to permit non-root running of dnsmasq
sudo chmod +s /usr/sbin/dnsmasq

echo "Creating root directory..."
sudo mkdir -p ${root_directory}
sudo chown $USER ${root_directory}

echo "Installing pvcbootstrapd..."
cp -a bootstrap-daemon ${root_directory}/pvcbootstrapd

echo "Installing PIP dependencies..."
sudo pip3 install -r ${root_directory}/pvcbootstrapd/requirements.txt

echo "Determining IP addresses..."
bootstrap_address="$( awk -F'.' '{ print $1"."$2"."$3".1" }' <<<"${bootstrap_network}" )"
bootstrap_dhcpstart="$( awk -F'.' '{ print $1"."$2"."$3".100" }' <<<"${bootstrap_network}" )"
bootstrap_dhcpend="$( awk -F'.' '{ print $1"."$2"."$3".199" }' <<<"${bootstrap_network}" )"

echo "Creating configuration..."
cp ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml.template ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
sed -i "s|DEPLOY_USERNAME|${deploy_username}|" ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
sed -i "s|ROOT_DIRECTORY|${root_directory}|" ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
sed -i "s|BOOTSTRAP_ADDRESS|${bootstrap_address}|" ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
sed -i "s|BOOTSTRAP_DHCPSTART|${bootstrap_dhcpstart}|" ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
sed -i "s|BOOTSTRAP_DHCPEND|${bootstrap_dhcpend}|" ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
sed -i "s|GIT_REMOTE|${git_remote}|" ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
sed -i "s|GIT_BRANCH|${git_branch}|" ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
sed -i "s|UPSTREAM_MIRROR|${upstream_mirror}|" ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
sed -i "s|DEBIAN_RELEASE|${debian_release}|" ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml

echo "Creating network configuration for interface ${bootstrap_interface} (is vLAN? ${is_bootstrap_interface_vlan})..."
if [[ "${is_bootstrap_interface_vlan}" == "yes" ]]; then
cat <<EOF | sudo tee /etc/network/interfaces.d/bootstrapnet &>/dev/null
auto vlan${bootstrap_vlan}
iface vlan${bootstrap_vlan} inet static
    vlan_raw_device ${bootstrap_interface}
    address ${bootstrap_address}
    netmask 255.255.255.0
    post-up echo 1 > /proc/sys/net/ipv4/ip_forward
    post-up iptables -A FORWARD -i \$IFACE -j ACCEPT
    post-up iptables -A FORWARD -o \$IFACE -m state --state ESTABLISHED,RELATED -j ACCEPT
    post-up iptables -t nat -A POSTROUTING -o ${upstream_interface} -j MASQUERADE
EOF
else
cat <<EOF | sudo tee /etc/network/interfaces.d/bootstrapnet &>/dev/null
auto ${bootstrap_interface}
iface ${bootstrap_interface} inet static
    address ${bootstrap_address}
    netmask 255.255.255.0
    post-up echo 1 > /proc/sys/net/ipv4/ip_forward
    post-up iptables -A FORWARD -i \$IFACE -j ACCEPT
    post-up iptables -A FORWARD -o \$IFACE -m state --state ESTABLISHED,RELATED -j ACCEPT
    post-up iptables -t nat -A POSTROUTING -o ${upstream_interface} -j MASQUERADE
EOF
fi

echo "Installing service units..."
cat <<EOF | sudo tee /etc/systemd/system/pvcbootstrapd.service &>/dev/null
# Parallel Virtual Cluster Bootstrap API daemon unit file

[Unit]
Description = Parallel Virtual Cluster Bootstrap API daemon
After = network-online.target

[Service]
Type = simple
User = ${username}
WorkingDirectory = ${root_directory}/pvcbootstrapd
Environment = PYTHONUNBUFFERED=true
Environment = PVCD_CONFIG_FILE=${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
ExecStart = ${root_directory}/pvcbootstrapd/pvcbootstrapd.py
Restart = on-failure

[Install]
WantedBy = multi-user.target
EOF
sudo systemctl enable pvcbootstrapd.service

cat <<EOF | sudo tee /etc/systemd/system/pvcbootstrapd-worker.service &>/dev/null
# Parallel Virtual Cluster Provisioner API provisioner worker unit file

[Unit]
Description = Parallel Virtual Cluster Bootstrap API worker
After = network-online.target

[Service]
Type = simple
User = ${username}
WorkingDirectory = ${root_directory}/pvcbootstrapd
Environment = PYTHONUNBUFFERED=true
Environment = PVCD_CONFIG_FILE=${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
ExecStart = ${root_directory}/pvcbootstrapd/pvcbootstrapd-worker.sh
Restart = on-failure

[Install]
WantedBy = multi-user.target
EOF
sudo systemctl enable pvcbootstrapd-worker.service

sudo systemctl daemon-reload

if [[ ! -f ${root_directory}/id_ed25519 ]]; then
    echo "Generating SSH keypair..."
    ssh-keygen -t ed25519 -C "pvcbootstrapd@$(hostname)" -N "" -f ${root_directory}/id_ed25519
fi
echo
echo "Before proceeding, add the following SSH key as a writable deploy key to your local PVC repository."
echo "This will allow both repository cloning and push of committed changes to the remote repository."
echo "This key will also be used for ${deploy_username} user Ansible access when configuring clusters."
echo
echo -n " "
cat ${root_directory}/id_ed25519.pub
echo
echo -n "Press <Enter> once completed to continue. "
read
echo

echo "Edit configuration before proceeding? (Note: to enable notifications do so now)"
echo -n "[y/N] > "
read edit_flag
case ${edit_flag} in
    y|Y|yes|Yes|YES)
        vim ${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml
    ;;
    *)
        true
    ;;
esac
echo

echo "Start the pvcbootstrapd process manually for initialization (this will take quite some time)?"
echo -n "[Y/n] > "
read start_flag
case ${start_flag} in
    n|N|no|No|NO)
        true
    ;;
    *)
        echo
        export PVCD_CONFIG_FILE="${root_directory}/pvcbootstrapd/pvcbootstrapd.yaml"
        ${root_directory}/pvcbootstrapd/pvcbootstrapd.py --init-only
    ;;
esac
echo

echo "Restart system to finalize installation?"
echo -n "[Y/n] > "
read reboot_flag
case ${reboot_flag} in
    n|N|no|No|NO)
        true
    ;;
    *)
        sudo reboot
    ;;
esac

# Done
exit 0
