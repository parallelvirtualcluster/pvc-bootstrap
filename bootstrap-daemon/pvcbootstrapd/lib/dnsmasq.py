#!/usr/bin/env python3

# dnsmasq.py - PVC Cluster Auto-bootstrap DNSMasq instance
# Part of the Parallel Virtual Cluster (PVC) system
#
#    Copyright (C) 2018-2021 Joshua M. Boniface <joshua@boniface.me>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
###############################################################################

import os
import subprocess
import signal

from threading import Thread


class DNSMasq:
    """
    Implementes a daemonized instance of DNSMasq for providing DHCP and TFTP services

    The DNSMasq instance listens on the configured 'dhcp_address', and instead of a "real"
    leases database forwards requests to the 'dnsmasq-lease.py' script. This script will
    then hit the pvcbootstrapd '/checkin' API endpoint to perform actions.

    TFTP is provided to automate the bootstrap of a node, providing the pvc-installer
    over TFTP as well as a seed configuration which is created by the API.
    """

    def __init__(self, config):
        self.environment = {
            "API_URI": f"http://{config['api_address']}:{config['api_port']}/checkin/dnsmasq"
        }
        self.dnsmasq_cmd = [
            "/usr/sbin/dnsmasq",
            "--bogus-priv",
            "--no-hosts",
            "--dhcp-authoritative",
            "--filterwin2k",
            "--expand-hosts",
            "--domain-needed",
            f"--domain={config['dhcp_domain']}",
            f"--local=/{config['dhcp_domain']}/",
            "--log-facility=-",
            "--log-dhcp",
            "--keep-in-foreground",
            f"--dhcp-script={os.getcwd()}/pvcbootstrapd/dnsmasq-lease.py",
            "--bind-interfaces",
            f"--listen-address={config['dhcp_address']}",
            f"--dhcp-option=3,{config['dhcp_gateway']}",
            f"--dhcp-range={config['dhcp_lease_start']},{config['dhcp_lease_end']},{config['dhcp_lease_time']}",
            "--enable-tftp",
            f"--tftp-root={config['tftp_root_path']}/",
            # This block of dhcp-match, tag-if, and dhcp-boot statements sets the following TFTP setup:
            #   If the machine sends client-arch 0, and is not tagged iPXE, load undionly.kpxe (chainload)
            #   If the machine sends client-arch 7 or 9, and is not tagged iPXE, load ipxe.efi (chainload)
            #   If the machine sends the iPXE option, load boot.ipxe (iPXE boot configuration)
            "--dhcp-match=set:o_bios,option:client-arch,0",
            "--dhcp-match=set:o_uefi,option:client-arch,7",
            "--dhcp-match=set:o_uefi,option:client-arch,9",
            "--dhcp-match=set:ipxe,175",
            "--tag-if=set:bios,tag:!ipxe,tag:o_bios",
            "--tag-if=set:uefi,tag:!ipxe,tag:o_uefi",
            "--dhcp-boot=tag:bios,undionly.kpxe",
            "--dhcp-boot=tag:uefi,ipxe.efi",
            "--dhcp-boot=tag:ipxe,boot.ipxe",
        ]
        if config["debug"]:
            self.dnsmasq_cmd.append("--leasefile-ro")

        print(self.dnsmasq_cmd)
        self.stdout = subprocess.PIPE

    def execute(self):
        self.proc = subprocess.Popen(
            self.dnsmasq_cmd,
            env=self.environment,
        )

    def start(self):
        self.thread = Thread(target=self.execute, args=())
        self.thread.start()

    def stop(self):
        self.proc.send_signal(signal.SIGTERM)

    def reload(self):
        self.proc.send_signal(signal.SIGHUP)
