#!/usr/bin/env python3

# host.py - PVC Cluster Auto-bootstrap host libraries
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

import pvcbootstrapd.lib.db as db

from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


def installer_init(config, cspec, data):
    bmc_macaddr = data["bmc_macaddr"]
    bmc_ipaddr = data["bmc_ipaddr"]
    host_macaddr = data["host_macaddr"]
    host_ipaddr = data["host_ipaddr"]
    cspec_cluster = cspec["bootstrap"][bmc_macaddr]["node"]["cluster"]
    cspec_hostname = cspec["bootstrap"][bmc_macaddr]["node"]["hostname"]

    cluster = db.get_cluster(config, name=cspec_cluster)
    if cluster is None:
        cluster = db.add_cluster(config, cspec, cspec_cluster, "provisioning")
    logger.debug(cluster)

    db.update_node_addresses(
        config,
        cspec_cluster,
        cspec_hostname,
        bmc_macaddr,
        bmc_ipaddr,
        host_macaddr,
        host_ipaddr,
    )
    db.update_node_state(config, cspec_cluster, cspec_hostname, "installing")
    node = db.get_node(config, cspec_cluster, name=cspec_hostname)
    logger.debug(node)


def installer_complete(config, cspec, data):
    bmc_macaddr = data["bmc_macaddr"]
    cspec_hostname = cspec["bootstrap"][bmc_macaddr]["node"]["hostname"]
    cspec_cluster = cspec["bootstrap"][bmc_macaddr]["node"]["cluster"]

    db.update_node_state(config, cspec_cluster, cspec_hostname, "installed")
    node = db.get_node(config, cspec_cluster, name=cspec_hostname)
    logger.debug(node)


def set_boot_state(config, cspec, data, state):
    bmc_macaddr = data["bmc_macaddr"]
    bmc_ipaddr = data["bmc_ipaddr"]
    host_macaddr = data["host_macaddr"]
    host_ipaddr = data["host_ipaddr"]
    cspec_cluster = cspec["bootstrap"][bmc_macaddr]["node"]["cluster"]
    cspec_hostname = cspec["bootstrap"][bmc_macaddr]["node"]["hostname"]

    db.update_node_addresses(
        config,
        cspec_cluster,
        cspec_hostname,
        bmc_macaddr,
        bmc_ipaddr,
        host_macaddr,
        host_ipaddr,
    )
    db.update_node_state(config, cspec_cluster, cspec_hostname, state)
    node = db.get_node(config, cspec_cluster, name=cspec_hostname)
    logger.debug(node)


def set_completed(config, cspec, cluster):
    nodes = list()
    for bmc_macaddr in cspec["bootstrap"]:
        if cspec["bootstrap"][bmc_macaddr]["node"]["cluster"] == cluster:
            nodes.append(cspec["bootstrap"][bmc_macaddr])
    for node in nodes:
        cspec_cluster = node["node"]["cluster"]
        cspec_hostname = node["node"]["hostname"]
        db.update_node_state(config, cspec_cluster, cspec_hostname, "completed")
        node = db.get_node(config, cspec_cluster, name=cspec_hostname)
        logger.debug(node)
