#!/usr/bin/env python3

# hooks.py - PVC Cluster Auto-bootstrap Hook libraries
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

import json
import tempfile
import paramiko
import contextlib
import requests

from re import match
from time import sleep
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


@contextlib.contextmanager
def run_paramiko(config, node_address):
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_client.connect(
        hostname=node_address,
        username=config["deploy_username"],
        key_filename=config["ansible_key_file"],
    )
    yield ssh_client
    ssh_client.close()


def run_hook_osddb(config, targets, args):
    """
    Add an OSD DB defined by args['disk']
    """
    for node in targets:
        node_name = node.name
        node_address = node.host_ipaddr

        device = args["disk"]

        logger.info(f"Creating OSD DB on node {node_name} device {device}")

        # Using a direct command on the target here is somewhat messy, but avoids many
        # complexities of determining a valid API listen address, etc.
        pvc_cmd_string = f"pvc storage osd create-db-vg --yes {node_name} {device}"

        with run_paramiko(config, node_address) as c:
            stdin, stdout, stderr = c.exec_command(pvc_cmd_string)
            logger.debug(stdout.readlines())
            logger.debug(stderr.readlines())


def run_hook_osd(config, targets, args):
    """
    Add an OSD defined by args['disk'] with weight args['weight']
    """
    for node in targets:
        node_name = node.name
        node_address = node.host_ipaddr

        device = args["disk"]
        weight = args.get("weight", 1)
        ext_db_flag = args.get("ext_db", False)
        ext_db_ratio = args.get("ext_db_ratio", 0.05)

        logger.info(f"Creating OSD on node {node_name} device {device} weight {weight}")

        # Using a direct command on the target here is somewhat messy, but avoids many
        # complexities of determining a valid API listen address, etc.
        pvc_cmd_string = (
            f"pvc storage osd add --yes {node_name} {device} --weight {weight}"
        )
        if ext_db_flag:
            pvc_cmd_string = f"{pvc_cmd_string} --ext-db --ext-db-ratio {ext_db_ratio}"

        with run_paramiko(config, node_address) as c:
            stdin, stdout, stderr = c.exec_command(pvc_cmd_string)
            logger.debug(stdout.readlines())
            logger.debug(stderr.readlines())


def run_hook_pool(config, targets, args):
    """
    Add an pool defined by args['name'] on device tier args['tier']
    """
    for node in targets:
        node_name = node.name
        node_address = node.host_ipaddr

        name = args["name"]
        pgs = args.get("pgs", "64")
        tier = args.get("tier", "default")  # Does nothing yet
        replcfg = args.get("replcfg", "copies=3,mincopies=2")

        logger.info(
            f"Creating storage pool on node {node_name} name {name} pgs {pgs} tier {tier} replcfg {replcfg}"
        )

        # Using a direct command on the target here is somewhat messy, but avoids many
        # complexities of determining a valid API listen address, etc.
        pvc_cmd_string = f"pvc storage pool add {name} {pgs} --replcfg {replcfg}"

        with run_paramiko(config, node_address) as c:
            stdin, stdout, stderr = c.exec_command(pvc_cmd_string)
            logger.debug(stdout.readlines())
            logger.debug(stderr.readlines())

        # This only runs once on whatever the first node is
        break


def run_hook_network(config, targets, args):
    """
    Add an network defined by args (many)
    """
    for node in targets:
        node_name = node.name
        node_address = node.host_ipaddr

        vni = args["vni"]
        description = args["description"]
        nettype = args["type"]
        mtu = args.get("mtu", None)

        pvc_cmd_string = (
            f"pvc network add {vni} --description {description} --type {nettype}"
        )

        if mtu is not None and mtu not in ["auto", "default"]:
            pvc_cmd_string = f"{pvc_cmd_string} --mtu {mtu}"

        if nettype == "managed":
            domain = args["domain"]
            pvc_cmd_string = f"{pvc_cmd_string} --domain {domain}"

            dns_servers = args.get("dns_servers", [])
            for dns_server in dns_servers:
                pvc_cmd_string = f"{pvc_cmd_string} --dns-server {dns_server}"

            is_ip4 = args.get("ip4", False)
            if is_ip4:
                ip4_network = args["ip4_network"]
                pvc_cmd_string = f"{pvc_cmd_string} --ipnet {ip4_network}"

                ip4_gateway = args["ip4_gateway"]
                pvc_cmd_string = f"{pvc_cmd_string} --gateway {ip4_gateway}"

                ip4_dhcp = args.get("ip4_dhcp", False)
                if ip4_dhcp:
                    pvc_cmd_string = f"{pvc_cmd_string} --dhcp"
                    ip4_dhcp_start = args["ip4_dhcp_start"]
                    ip4_dhcp_end = args["ip4_dhcp_end"]
                    pvc_cmd_string = f"{pvc_cmd_string} --dhcp-start {ip4_dhcp_start} --dhcp-end {ip4_dhcp_end}"
                else:
                    pvc_cmd_string = f"{pvc_cmd_string} --no-dhcp"

            is_ip6 = args.get("ip6", False)
            if is_ip6:
                ip6_network = args["ip6_network"]
                pvc_cmd_string = f"{pvc_cmd_string} --ipnet6 {ip6_network}"

                ip6_gateway = args["ip6_gateway"]
                pvc_cmd_string = f"{pvc_cmd_string} --gateway6 {ip6_gateway}"

        logger.info(f"Creating network on node {node_name} VNI {vni} type {nettype}")

        with run_paramiko(config, node_address) as c:
            stdin, stdout, stderr = c.exec_command(pvc_cmd_string)
            logger.debug(stdout.readlines())
            logger.debug(stderr.readlines())

        # This only runs once on whatever the first node is
        break


def run_hook_copy(config, targets, args):
    """
    Copy a file from the local machine to the target(s)
    """
    for node in targets:
        node_name = node.name
        node_address = node.host_ipaddr

        source = args.get("source", [])
        destination = args.get("destination", [])
        mode = args.get("mode", [])

        logger.info(f"Copying file {source} to node {node_name}:{destination}")

        with run_paramiko(config, node_address) as c:
            for sfile, dfile, dmode in zip(source, destination, mode):
                if not match(r"^/", sfile):
                    sfile = f"{config['ansible_path']}/{sfile}"
                tc = c.open_sftp()
                tc.put(sfile, dfile)
                tc.chmod(dfile, int(dmode, 8))
                tc.close()


def run_hook_script(config, targets, args):
    """
    Run a script on the targets
    """
    for node in targets:
        node_name = node.name
        node_address = node.host_ipaddr

        script = args.get("script", None)
        source = args.get("source", None)
        path = args.get("path", None)
        arguments = args.get("arguments", [])
        use_sudo = args.get("use_sudo", False)

        logger.info(f"Running script on node {node_name}")

        with run_paramiko(config, node_address) as c:
            if script is not None:
                remote_path = "/tmp/pvcbootstrapd.hook"
                with tempfile.NamedTemporaryFile(mode="w") as tf:
                    tf.write(script)
                    tf.seek(0)

                    # Send the file to the remote system
                    tc = c.open_sftp()
                    tc.put(tf.name, remote_path)
                    tc.chmod(remote_path, 0o755)
                    tc.close()
            elif source == "local":
                if not match(r"^/", path):
                    path = config["ansible_path"] + "/" + path

                remote_path = "/tmp/pvcbootstrapd.hook"
                if path is None:
                    continue

                tc = c.open_sftp()
                tc.put(path, remote_path)
                tc.chmod(remote_path, 0o755)
                tc.close()
            elif source == "remote":
                remote_path = path

            if len(arguments) > 0:
                remote_command = f"{remote_path} {' '.join(arguments)}"
            else:
                remote_command = remote_path

            if use_sudo:
                remote_command = f"sudo {remote_command}"

            stdin, stdout, stderr = c.exec_command(remote_command)
            logger.debug(stdout.readlines())
            logger.debug(stderr.readlines())


def run_hook_webhook(config, targets, args):
    """
    Send an HTTP requests (no targets)
    """
    logger.info(f"Running webhook against {args['uri']}")

    # Get the body data
    data = json.dumps(args["body"])
    headers = {"content-type": "application/json"}

    # Craft up a Requests endpoint set for this
    requests_actions = {
        "get": requests.get,
        "post": requests.post,
        "put": requests.put,
        "patch": requests.patch,
        "delete": requests.delete,
        "options": requests.options,
    }
    action = args["action"]

    result = requests_actions[action](args["uri"], headers=headers, data=data)

    logger.info(f"Result: {result}")


hook_functions = {
    "osddb": run_hook_osddb,
    "osd": run_hook_osd,
    "pool": run_hook_pool,
    "network": run_hook_network,
    "copy": run_hook_copy,
    "script": run_hook_script,
    "webhook": run_hook_webhook,
}


def run_hooks(config, cspec, cluster, nodes):
    """
    Run an Ansible bootstrap against a cluster
    """
    # Waiting 30 seconds to ensure everything is booted an stabilized
    logger.info("Waiting 300s before starting hook run.")
    sleep(300)

    notifications.send_webhook(config, "begin", f"Cluster {cluster.name}: Running post-setup hook tasks")

    cluster_hooks = cspec["hooks"][cluster.name]

    cluster_nodes = db.get_nodes_in_cluster(config, cluster.name)

    for hook in cluster_hooks:
        hook_target = hook.get("target", "all")
        hook_name = hook.get("name")
        logger.info(f"Running hook on {hook_target}: {hook_name}")

        if "all" in hook_target:
            target_nodes = cluster_nodes
        else:
            target_nodes = [node for node in cluster_nodes if node.name in hook_target]

        hook_type = hook.get("type")
        hook_args = hook.get("args")

        if hook_type is None or hook_args is None:
            logger.warning("Invalid hook: missing required configuration")
            continue

        # Run the hook function
        try:
            notifications.send_webhook(config, "begin", f"Cluster {cluster.name}: Running hook task '{hook_name}'")
            hook_functions[hook_type](config, target_nodes, hook_args)
            notifications.send_webhook(config, "success", f"Cluster {cluster.name}: Completed hook task '{hook_name}'")
        except Exception as e:
            logger.warning(f"Error running hook: {e}")
            notifications.send_webhook(config, "failure", f"Cluster {cluster.name}: Failed hook task '{hook_name}' with error '{e}'")

        # Wait 5s between hooks
        sleep(5)

    notifications.send_webhook(config, "success", f"Cluster {cluster.name}: Completed post-setup hook tasks")
