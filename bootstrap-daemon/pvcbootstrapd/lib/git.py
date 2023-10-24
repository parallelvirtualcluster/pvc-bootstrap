#!/usr/bin/env python3

# git.py - PVC Cluster Auto-bootstrap Git repository libraries
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

import os.path
import git
import yaml
from filelock import FileLock

import pvcbootstrapd.lib.notifications as notifications

from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


def init_repository(config):
    """
    Clone the Ansible git repository
    """
    try:
        git_ssh_cmd = f"ssh -i {config['ansible_key_file']} -o StrictHostKeyChecking=no"
        if not os.path.exists(config["ansible_path"]):
            print(
                f"First run: cloning repository {config['ansible_remote']} branch {config['ansible_branch']} to {config['ansible_path']}"
            )
            notifications.send_webhook(config, "begin", f"First run: cloning repository {config['ansible_remote']} branch {config['ansible_branch']} to {config['ansible_path']}")
            git.Repo.clone_from(
                config["ansible_remote"],
                config["ansible_path"],
                branch=config["ansible_branch"],
                env=dict(GIT_SSH_COMMAND=git_ssh_cmd),
            )

        g = git.cmd.Git(f"{config['ansible_path']}")
        g.checkout(config["ansible_branch"])
        g.submodule("update", "--init", env=dict(GIT_SSH_COMMAND=git_ssh_cmd))
    except Exception as e:
        print(f"Error: {e}")


def pull_repository(config):
    """
    Pull (with rebase) the Ansible git repository
    """
    with FileLock(config['ansible_lock_file']):
        logger.info(f"Updating local configuration repository {config['ansible_path']}")
        try:
            git_ssh_cmd = f"ssh -i {config['ansible_key_file']} -o StrictHostKeyChecking=no"
            g = git.cmd.Git(f"{config['ansible_path']}")
            logger.debug("Performing git pull")
            g.pull(rebase=True, env=dict(GIT_SSH_COMMAND=git_ssh_cmd))
            logger.debug("Performing git submodule update")
            g.submodule("update", "--init", env=dict(GIT_SSH_COMMAND=git_ssh_cmd))
            g.submodule("update", env=dict(GIT_SSH_COMMAND=git_ssh_cmd))
        except Exception as e:
            logger.warn(e)
            notifications.send_webhook(config, "failure", "Failed to update Git repository")
    logger.info("Completed repository synchonization")


def commit_repository(config, message="Generic commit"):
    """
    Commit uncommitted changes to the Ansible git repository
    """
    with FileLock(config['ansible_lock_file']):
        logger.info(
            f"Committing changes to local configuration repository {config['ansible_path']}"
        )
        try:
            g = git.cmd.Git(f"{config['ansible_path']}")
            g.add("--all")
            commit_env = {
                "GIT_COMMITTER_NAME": "PVC Bootstrap",
                "GIT_COMMITTER_EMAIL": "git@pvcbootstrapd",
            }
            g.commit(
                "-m",
                "Automated commit from PVC Bootstrap Ansible subsystem",
                "-m",
                message,
                author="PVC Bootstrap <git@pvcbootstrapd>",
                env=commit_env,
            )
            notifications.send_webhook(config, "success", "Successfully committed to Git repository")
        except Exception as e:
            logger.warn(e)
            notifications.send_webhook(config, "failure", "Failed to commit to Git repository")


def push_repository(config):
    """
    Push changes to the default remote
    """
    with FileLock(config['ansible_lock_file']):
        logger.info(
            f"Pushing changes from local configuration repository {config['ansible_path']}"
        )
        try:
            git_ssh_cmd = f"ssh -i {config['ansible_key_file']} -o StrictHostKeyChecking=no"
            g = git.Repo(f"{config['ansible_path']}")
            origin = g.remote(name="origin")
            origin.push(env=dict(GIT_SSH_COMMAND=git_ssh_cmd))
            notifications.send_webhook(config, "success", "Successfully pushed Git repository")
        except Exception as e:
            logger.warn(e)
            notifications.send_webhook(config, "failure", "Failed to push Git repository")


def load_cspec_yaml(config):
    """
    Load the bootstrap group_vars for all known clusters
    """
    # Pull down the repository
    pull_repository(config)

    # Load our clusters file and read the clusters from it
    clusters_file = f"{config['ansible_path']}/{config['ansible_clusters_file']}"
    logger.info(f"Loading cluster configuration from file '{clusters_file}'")
    with open(clusters_file, "r") as clustersfh:
        clusters = yaml.load(clustersfh, Loader=yaml.SafeLoader).get("clusters", list())

    # Define a base cpec
    cspec = {
        "bootstrap": dict(),
        "hooks": dict(),
        "clusters": dict(),
    }

    # Read each cluster's cspec and update the base cspec
    logger.info("Loading per-cluster specifications")
    for cluster in clusters:
        cspec["clusters"][cluster] = dict()
        cspec["clusters"][cluster]["bootstrap_nodes"] = list()

        cspec_file = f"{config['ansible_path']}/group_vars/{cluster}/{config['ansible_cspec_files_bootstrap']}"
        if os.path.exists(cspec_file):
            with open(cspec_file, "r") as cpsecfh:
                try:
                    cspec_yaml = yaml.load(cpsecfh, Loader=yaml.SafeLoader)
                except Exception as e:
                    logger.warn(
                        f"Failed to load {config['ansible_cspec_files_bootstrap']} for cluster {cluster}: {e}"
                    )
                    continue

            cspec["clusters"][cluster]["cspec_yaml"] = cspec_yaml

            # Convert the MAC address keys to lowercase
            # DNSMasq operates with lowercase keys, but often these are written with uppercase.
            # Convert them to lowercase to prevent discrepancies later on.
            cspec_yaml["bootstrap"] = {
                k.lower(): v for k, v in cspec_yaml["bootstrap"].items()
            }

            # Load in the YAML for the cluster
            base_yaml = load_base_yaml(config, cluster)
            cspec["clusters"][cluster]["base_yaml"] = base_yaml
            pvc_yaml = load_pvc_yaml(config, cluster)
            cspec["clusters"][cluster]["pvc_yaml"] = pvc_yaml

            # Set per-node values from elsewhere
            for node in cspec_yaml["bootstrap"]:
                cspec["clusters"][cluster]["bootstrap_nodes"].append(
                    cspec_yaml["bootstrap"][node]["node"]["hostname"]
                )

                # Set the cluster value automatically
                cspec_yaml["bootstrap"][node]["node"]["cluster"] = cluster

                # Set the domain value automatically via base config
                cspec_yaml["bootstrap"][node]["node"]["domain"] = base_yaml[
                    "local_domain"
                ]

                # Set the node FQDN value automatically
                cspec_yaml["bootstrap"][node]["node"][
                    "fqdn"
                ] = f"{cspec_yaml['bootstrap'][node]['node']['hostname']}.{cspec_yaml['bootstrap'][node]['node']['domain']}"

            # Append bootstrap entries to the main dictionary
            cspec["bootstrap"] = {**cspec["bootstrap"], **cspec_yaml["bootstrap"]}

            # Append hooks to the main dictionary (per-cluster)
            if cspec_yaml.get("hooks"):
                cspec["hooks"][cluster] = cspec_yaml["hooks"]

    logger.info("Finished loading per-cluster specifications")
    return cspec


def load_base_yaml(config, cluster):
    """
    Load the base.yml group_vars for a cluster
    """
    base_file = f"{config['ansible_path']}/group_vars/{cluster}/{config['ansible_cspec_files_base']}"
    with open(base_file, "r") as varsfile:
        base_yaml = yaml.load(varsfile, Loader=yaml.SafeLoader)

    return base_yaml


def load_pvc_yaml(config, cluster):
    """
    Load the pvc.yml group_vars for a cluster
    """
    pvc_file = f"{config['ansible_path']}/group_vars/{cluster}/{config['ansible_cspec_files_pvc']}"
    with open(pvc_file, "r") as varsfile:
        pvc_yaml = yaml.load(varsfile, Loader=yaml.SafeLoader)

    return pvc_yaml
