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

import pvcbootstrapd.lib.notifications as notifications
import pvcbootstrapd.lib.db as db
import pvcbootstrapd.lib.git as git
import pvcbootstrapd.lib.redfish as redfish
import pvcbootstrapd.lib.host as host
import pvcbootstrapd.lib.ansible as ansible
import pvcbootstrapd.lib.hooks as hooks

from time import sleep
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


#
# Worker Functions - Checkins (Celery root tasks)
#
def dnsmasq_checkin(config, data):
    """
    Handle checkins from DNSMasq
    """
    logger.debug(f"data = {data}")

    # This is an add event; what we do depends on some stuff
    if data["action"] in ["add"]:
        logger.info(
            f"Receiving 'add' checkin from DNSMasq for MAC address '{data['macaddr']}'"
        )
        cspec = git.load_cspec_yaml(config)
        is_in_bootstrap_map = True if data["macaddr"] in cspec["bootstrap"] else False
        try:
            if is_in_bootstrap_map:
                cspec_cluster = cspec["bootstrap"][data["macaddr"]]["node"]["cluster"]
                is_registered = True if data["macaddr"] in [x.bmc_macaddr for x in db.get_nodes_in_cluster(config, cspec_cluster)] else False
            else:
                is_registered = False
        except Exception:
            is_registered = False

        if not is_in_bootstrap_map:
            logger.warn(f"Device '{data['macaddr']}' not in bootstrap map; ignoring.")
            return

        if is_registered:
            logger.info(f"Device '{data['macaddr']}' has already been bootstrapped; ignoring.")
            return

        notifications.send_webhook(config, "info", f"New host checkin from MAC {data['macaddr']} as host {cspec['bootstrap'][data['macaddr']]['node']['fqdn']} in cluster {cspec['bootstrap'][data['macaddr']]['node']['cluster']}")
        if (
            cspec["bootstrap"][data["macaddr"]]["bmc"].get("redfish", None)
            is not None
        ):
            if cspec["bootstrap"][data["macaddr"]]["bmc"]["redfish"]:
                is_redfish = True
            else:
                is_redfish = False
        else:
            is_redfish = redfish.check_redfish(config, data)

        logger.info(f"Is device '{data['macaddr']}' Redfish capable? {is_redfish}")
        if is_redfish:
            redfish.redfish_init(config, cspec, data)

        return

    # This is a tftp event; a node installer has booted
    if data["action"] in ["tftp"]:
        logger.info(
            f"Receiving 'tftp' checkin from DNSMasq for IP address '{data['destaddr']}'"
        )
        return


def host_checkin(config, data):
    """
    Handle checkins from the PVC node
    """
    logger.info(f"Registering checkin for {data['bmc_macaddr']}")
    logger.debug(f"data = {data}")
    cspec = git.load_cspec_yaml(config)
    bmc_macaddr = data["bmc_macaddr"]
    cspec_cluster = cspec["bootstrap"][bmc_macaddr]["node"]["cluster"]
    cspec_fqdn = cspec["bootstrap"][bmc_macaddr]["node"]["fqdn"]

    if data["action"] in ["install-start"]:
        # Node install has started
        logger.info(f"Registering install start for host {cspec_fqdn}")
        notifications.send_webhook(config, "begin", f"Cluster {cspec_cluster}: Base install starting for host {cspec_fqdn}")
        host.installer_init(config, cspec, data)

    elif data["action"] in ["install-complete"]:
        # Node install has finished
        logger.info(f"Registering install complete for host {cspec_fqdn}")
        notifications.send_webhook(config, "success", f"Cluster {cspec_cluster}: Base install completed for host {cspec_fqdn}")
        host.installer_complete(config, cspec, data)

    elif data["action"] in ["system-boot_initial"]:
        # Node has booted for the first time and can begin Ansible runs once all nodes up
        logger.info(f"Registering first boot for host {cspec_fqdn}")
        notifications.send_webhook(config, "info", f"Cluster {cspec_cluster}: Registering first boot for host {cspec_fqdn}")
        target_state = "booted-initial"

        host.set_boot_state(config, cspec, data, target_state)
        sleep(1)

        all_nodes = db.get_nodes_in_cluster(config, cspec_cluster)
        ready_nodes = [node for node in all_nodes if node.state == target_state]

        # Continue once all nodes are in the booted-initial state
        logger.info(f"Ready: {len(ready_nodes)}  All: {len(all_nodes)}")
        if len(ready_nodes) >= len(all_nodes):
            cluster = db.update_cluster_state(config, cspec_cluster, "ansible-running")

            ansible.run_bootstrap(config, cspec, cluster, ready_nodes)

    elif data["action"] in ["system-boot_configured"]:
        # Node has been booted after Ansible run and can begin hook runs
        logger.info(f"Registering post-Ansible boot for host {cspec_fqdn}")
        notifications.send_webhook(config, "info", f"Cluster {cspec_cluster}: Registering post-Ansible boot for host {cspec_fqdn}")
        target_state = "booted-configured"

        host.set_boot_state(config, cspec, data, target_state)
        sleep(1)

        all_nodes = db.get_nodes_in_cluster(config, cspec_cluster)
        ready_nodes = [node for node in all_nodes if node.state == target_state]

        # Continue once all nodes are in the booted-configured state
        logger.info(f"Ready: {len(ready_nodes)}  All: {len(all_nodes)}")
        if len(ready_nodes) >= len(all_nodes):
            cluster = db.update_cluster_state(config, cspec_cluster, "hooks-running")

            hooks.run_hooks(config, cspec, cluster, ready_nodes)

            host.set_completed(config, cspec, cspec_cluster)

            # Hosts will now power down ready for real activation in production
            sleep(300)
            cluster = db.update_cluster_state(config, cspec_cluster, "completed")
            notifications.send_webhook(config, "completed", f"Cluster {cspec_cluster}: PVC bootstrap deployment completed")
