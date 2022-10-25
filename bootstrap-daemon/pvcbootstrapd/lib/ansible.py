#!/usr/bin/env python3

# ansible.py - PVC Cluster Auto-bootstrap Ansible libraries
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
import pvcbootstrapd.lib.git as git

import ansible_runner
import tempfile

from time import sleep
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


def run_bootstrap(config, cspec, cluster, nodes):
    """
    Run an Ansible bootstrap against a cluster
    """
    logger.debug(nodes)

    # Construct our temporary INI inventory string
    logger.info("Constructing virtual Ansible inventory")
    base_yaml = cspec["clusters"][cluster.name]["base_yaml"]
    local_domain = base_yaml.get("local_domain")
    inventory = [f"""[{cluster.name}]"""]
    for node in nodes:
        inventory.append(
            f"""{node.name}.{local_domain} ansible_host={node.host_ipaddr}"""
        )
    inventory = "\n".join(inventory)
    logger.debug(inventory)

    # Waiting 30 seconds to ensure everything is booted an stabilized
    logger.info("Waiting 60s before starting Ansible bootstrap.")
    sleep(60)

    logger.info("Starting Ansible bootstrap of cluster {cluster.name}")
    notifications.send_webhook(config, "begin", f"Cluster {cluster.name}: Starting Ansible bootstrap")

    # Run the Ansible playbooks
    with tempfile.TemporaryDirectory(prefix="pvc-ansible-bootstrap_") as pdir:
        try:
            r = ansible_runner.run(
                private_data_dir=f"{pdir}",
                inventory=inventory,
                limit=f"{cluster.name}",
                playbook=f"{config['ansible_path']}/pvc.yml",
                extravars={
                    "ansible_ssh_private_key_file": config["ansible_key_file"],
                    "bootstrap": "yes",
                },
                forks=len(nodes),
                verbosity=2,
            )
            logger.info("Final status:")
            logger.info("{}: {}".format(r.status, r.rc))
            logger.info(r.stats)
            if r.rc == 0:
                git.commit_repository(config)
                git.push_repository(config)
                notifications.send_webhook(config, "success", f"Cluster {cluster.name}: Completed Ansible bootstrap")
            else:
                notifications.send_webhook(config, "failure", f"Cluster {cluster.name}: Failed Ansible bootstrap; check pvcbootstrapd logs")
        except Exception as e:
            logger.warning(f"Error: {e}")
            notifications.send_webhook(config, "failure", f"Cluster {cluster.name}: Failed Ansible bootstrap with error '{e}'; check pvcbootstrapd logs")
