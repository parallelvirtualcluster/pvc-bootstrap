#!/usr/bin/env python3

# lib.py - PVC Cluster Auto-bootstrap libraries
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

from jinja2 import Template


#
# Worker Functions - PXE/Installer Per-host Templates
#
def add_pxe(config, cspec_node, host_macaddr):
    # Generate a per-client iPXE configuration for this host
    destination_filename = (
        f"{config['tftp_host_path']}/mac-{host_macaddr.replace(':', '')}.ipxe"
    )
    template_filename = f"{config['tftp_root_path']}/host-ipxe.j2"

    with open(template_filename, "r") as tfh:
        template = Template(tfh.read())

    imgargs_host_list = cspec_node.get("config", {}).get("kernel_options")
    if imgargs_host_list is not None:
        imgargs_host = " ".join(imgargs_host_list)
    else:
        imgargs_host = None

    rendered = template.render(imgargs_host=imgargs_host)

    with open(destination_filename, "w") as dfh:
        dfh.write(rendered)
        dfh.write("\n")


def add_preseed(config, cspec_node, host_macaddr, system_drive_target):
    # Generate a per-client Installer configuration for this host
    destination_filename = (
        f"{config['tftp_host_path']}/mac-{host_macaddr.replace(':', '')}.preseed"
    )
    template_filename = f"{config['tftp_root_path']}/host-preseed.j2"

    with open(template_filename, "r") as tfh:
        template = Template(tfh.read())

    add_packages_list = cspec_node.get("config", {}).get("packages")
    if add_packages_list is not None:
        add_packages = ",".join(add_packages_list)
    else:
        add_packages = None

    # We use the dhcp_address here to allow the listen_address to be 0.0.0.0
    rendered = template.render(
        debrelease=cspec_node.get("config", {}).get("release"),
        debmirror=config.get("repo_mirror"),
        addpkglist=add_packages,
        filesystem=cspec_node.get("config", {}).get("filesystem"),
        skip_blockcheck=False,
        fqdn=cspec_node["node"]["fqdn"],
        target_disk=system_drive_target,
        pvcbootstrapd_checkin_uri=f"http://{config['dhcp_address']}:{config['api_port']}/checkin/host",
    )

    with open(destination_filename, "w") as dfh:
        dfh.write(rendered)
        dfh.write("\n")
