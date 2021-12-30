# PVC Bootstrap System

The PVC bootstrap system provides a convenient way to deploy PVC clusters. Rather than manual node installation, this system provides a fully-automated deployment from node powering to cluster readiness, based on pre-configured values. It is useful if an administrator will deploy several PVC clusters or for repeated re-deployment for testing purposes.

## Setup

Setting up the PVC bootstrap system manually is very complicated, and has thus been automated with an installer script instead of providing a Debian or PIP package.

### Preparing to use the PVC Bootstrap system

1. Prepare a Git repository to store cluster configurations. This can be done automatically with the `create-local-repo.sh` script in the [PVC Ansible](https://github.com/parallelvirtualcluster/pvc-ansible) repository.

1. Create `group_vars` for each cluster you plan to bootstrap. Additionally, ensure you configure the `bootstrap.yml` file for each cluster with the relevant details of the hardware you will be using. This step can be repeated for each cluster in the future as new clusters are required, and the system will automatically pull changes to the local PVC repository once configured.

### Preparing a PVC Bootstrap host

1. The recommended OS for a PVC Bootstrap host is Debian GNU/Linux 10+. In terms of hardware, there are several supported options:

   i) A small single-board computer with wired Ethernet like a Raspberry Pi on `aarch64` (32-bit ARM not supported); at least a Pi model 4 or similar modern system is required; Pi models 1-3 do not support `aarch64` or are extremely slow in comparison, especially when building the initial TFTP installer root.

   ii) A small desktop computer on `amd64` with at least one wired Ethernet port.

   iii) A VM on `amd64` or `aarch64` connected to the required networks.

1. Set up a basic outbound network with Internet access; as detailed below, the installer will take care of the internal bootstrap network, either on a dedicated NIC or vLAN, with this host providing NAT'd access out.

1. Clone this repository somewhere on the host, for instance to `/srv` or `/home`.

1. Run the `./install-pvcbootstrapd.sh` script from the root of the repository to install the PVC Bootstrap system on the host. It will prompt for several configuration parameters. The final steps will take some time (up to 2 hours on a Raspberry Pi 4B) so be patient.

### Networking for Bootstrap

When using the pvcbootstrapd system, a dedicated network is required to provide bootstrap DHCP and TFTP to the cluster. This network can either have a dedicated, upstream router that does not provide DHCP, or the network can be routed with network address translation (NAT) through the bootstrap host. By default, the installer will configure the latter automatically using a second NIC separate from the upstream NIC of the bootstrap host, or via a vLAN on top of the single NIC.

In bootstrap mode (as opposed to manual install mode), new nodes are configured with their interfaces as follows:

  * BMC: bootstrap
  * Interface 1 (first among all LOM ports): bootstrap
  * Interface 2+ (all other ports): LACP (802.3ad) bond0

The Bootstrap interfaces do DHCP from the bootstrap host, and are thus responsible for autoconfiguration. The remaining interfaces, in an LACP bond, are used to underlay the various standard PVC networks.

Care must therefore be taken to ensure that the BMC and *first* lan-on-motherboard interface are connected as vLAN access ports in the bootstrap network, and that the remaining ports have some connectivity along the various configured PVC networks, before proceeding.

Consider the following diagram for reference:

![Per-Node Physical Connections](/docs/images/pvcbootstrapd-phy.png)

![Overall Network Topology](/docs/images/pvcbootstrapd-net.png)

### Deploying a Cluster with PVC Bootstrap - Redfish

Redfish is an industry-standard RESTful API for interfacing with the BMC (baseband management controller, or out-of-band network management system) on modern (post ~2015) servers from most vendors, including Dell iDRAC, HP iLO, Cisco CIMC, Lenovo XCC, and Supermicro X10 and newer BMCs. Redfish allows remote management, data collection, and configuration from the BMC in a standardized way across server vendors.

The PVC Bootstrap system is designed to heavily leverage Redfish in its automation. With Redfish, cluster deployment is plug-and-play, with no human input after committing the required configuration and connecting the servers. The steps are thus:

1. Ensure the cluster configuration `hosts` entries and `group_vars` are committed to the local PVC repository, including the BMC MAC addresses, default IPMI credentials, and desired hooks (`bootstrap.yml`), and all other cluster configurations (`base.yml` and `pvc.yml`). Generated configurations (e.g. `files`) will be automatically committed to the repository.

1. Connect the network ports as outlined in the above diagrams.

1. Connect power to the servers, but do not manually power on the servers - Redfish will handle this aspect after characterizing each host, as well as manage boot, RAID array creation (as documented in `bootstrap.yml`), BIOS configuration, etc.

1. Wait for the cluster bootstrapping to complete; you can watch the output of the `pvcbootstrapd` and `pvcbootstrapd-worker` services on the Bootstrap host to see progress. If supported, the indicator LEDs of the nodes will be lit during setup and will be disabled upon completion to provide a physical indication of the process.

1. Verify and power off the servers and put them into production; you may need to complete several post-install tasks (for instance setting the production BMC networking via `sudo ifup ipmi` on each node) before the cluster is completely finished.

### Deploying a Cluster with PVC Bootstrap - Non-Redfish

The PVC Bootstrap system can still handle nodes without Redfish support, for instance older servers or those from non-compliant vendors. There is however more manual setup in the process. The steps are thus:

1. Ensure the cluster configuration `hosts` entries and `group_vars` are committed to the local PVC repository, including the BMC MAC addresses, default IPMI credentials, and desired hooks (`bootstrap.yml`), and all other cluster configurations (`base.yml` and `pvc.yml`). Generated configurations (e.g. `files`) will be automatically committed to the repository. Ensure you set `redfish: no` in the appropriate section of the `bootstrap.yml` file; the BMC credentials can be empty but the variables must exist.

1. Do not (yet) connect network ports.

1. Connect power to the servers and power them on.

1. Perform any required configuration of BIOS settings, hardware RAID arrays for the system disk, etc.

1. Power off the servers.

1. Create a set of host configuration files in the TFTP `host` directory on the PVC controller, by default at `/srv/pvc/tftp/host`, one per node. You will need to know the MAC address of the first ethernet (bootstrap network) port of each node to correctly set the filename. Some example contents for the two files are shown below.

1. Connect the network ports as outlined in the above diagrams.

1. Power on the servers and set them to boot temporarily (one time) from PXE.

1. Wait for the cluster bootstrapping to complete; you can watch the output of the `pvcbootstrapd` and `pvcbootstrapd-worker` services on the Bootstrap host to see progress. If supported, the indicator LEDs of the nodes will be lit during setup and will be disabled upon completion to provide a physical indication of the process.

1. Verify and power off the servers and put them into production; you may need to complete several post-install tasks (for instance setting the production BMC networking via `sudo ifup ipmi` on each node) before the cluster is completely finished.

#### `host-MAC.ipxe`

```
#1ipxe

# The name of this file is "host-123456abcdef.ipxe", where "123456abcdef" is the MAC address of the
# server's Bootstrap Ethernet port (on-motherboard port 1), without spaces or punctuation.

# ARGUMENTS are any additional kernel command line arguments that might be needed for installer boot
# For instance, on an HP DL360 G6 the serial console is ttyS1 at 115200 baud, so the line would be:
#   set imgargs-host console=ttyS1,115200n

# If no additional arguments are required, then this file is optional, or you can set an empty
# imaargs-host value.

set imgargs-host ARGUMENTS
```

#### `host-MAC.preseed`

```
# The name of this file is "host-123456abcdef.preseed", where "123456abcdef" is the MAC address of the
# server's Bootstrap Ethernet port (on-motherboard port 1), without spaces or punctuation.

# This file defines the various configuration options to preseed the installer. An example here shows
# the various options, but what to put depends on the exact configuration of pvcbootstrapd. This
# information is, under Redfish, populated automatically based on the information provided in the
# cluster "bootstrap.yml" group vars file.

# Any option not set explicitly here is not set by the bootstrap system by default and should not need
# to be changed by the administrator.

# This BASH-compliant variables file is Loaded during PXE installs to preseed the environment.
# During normal usage, the pvcbootstrapd will load this file, adjust it according to its needs,
# and write out one instance per node to be installed.
#
# This file is thus not designed to be used by humans, and its values are seeded via options in
# the cluster-local Ansible group_vars, though it can be used as a manual template if required.

###
### General definitions/overrides
###
# The Debian release to use (overrides the default)
debrelease="bullseye"

# The Debian mirror to use (overrides the default)
debmirror="http://ftp.debian.org/debian"

# Additional packages (comma-separated) to install in the base system
addpkglist="ca-certificates"

# Alternate filesystem for system volumes (/, /var/lib/ceph, /var/lib/zookeeper)
filesystem="ext4"


###
### Per-host definitions (required)
###

# The hostname of the system (set per-run)
target_hostname="hv1.example.tld"

# The target system disk path
target_disk="detect:LOGICAL:146GB:0"

# SSH key method (usually tftp)
target_keys_method="tftp"

# SSH key path (usually keys.txt)
target_keys_path="keys.txt"

# Deploy username (usually deploy)
target_deploy_user="deploy"

# Consoles to use by the inital boot process; these are normally set automatically
# based on the TTYs found by the installer, and are later overridden by the Ansible
# playbooks based on the hardware configuration. It is best to leave this commented
# unless you know that you need it.
#target_consoles="console=tty1 console=ttyS1,115200"

# Modules to blacklist from the installed system; we include hpwdt (HP Proliant
# watchdog) by default since this is known to cause kernel panics on boot with this
# hardware. Add others here too if you wish to add more to the default.
#target_module_blacklist=( "hpwdt" )

# Installer checkin URI (provided by pvcbootstrapd)
pvcbootstrapd_checkin_uri="http://10.255.255.1:9999/checkin/host"
```
