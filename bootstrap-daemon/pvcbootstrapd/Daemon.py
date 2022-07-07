#!/usr/bin/env python3

# Daemon.py - PVC HTTP API daemon
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
import yaml
import signal

from sys import argv

import pvcbootstrapd.lib.notifications as notifications
import pvcbootstrapd.lib.dnsmasq as dnsmasqd
import pvcbootstrapd.lib.db as db
import pvcbootstrapd.lib.git as git
import pvcbootstrapd.lib.tftp as tftp

from distutils.util import strtobool as dustrtobool

# Daemon version
version = "0.1"

# API version
API_VERSION = 1.0


##########################################################
# Exceptions
##########################################################


class MalformedConfigurationError(Exception):
    """
    An exception when parsing the PVC daemon configuration file
    """

    def __init__(self, error=None):
        self.msg = f"ERROR: Configuration file is malformed: {error}"

    def __str__(self):
        return str(self.msg)


##########################################################
# Helper Functions
##########################################################


def strtobool(stringv):
    if stringv is None:
        return False
    if isinstance(stringv, bool):
        return bool(stringv)
    try:
        return bool(dustrtobool(stringv))
    except Exception:
        return False


##########################################################
# Configuration Parsing
##########################################################


def get_config_path():
    try:
        return os.environ["PVCD_CONFIG_FILE"]
    except KeyError:
        print('ERROR: The "PVCD_CONFIG_FILE" environment variable must be set.')
        os._exit(1)


def read_config():
    pvcbootstrapd_config_file = get_config_path()

    print(f"Loading configuration from file '{pvcbootstrapd_config_file}'")

    # Load the YAML config file
    with open(pvcbootstrapd_config_file, "r") as cfgfile:
        try:
            o_config = yaml.load(cfgfile, Loader=yaml.SafeLoader)
        except Exception as e:
            print(f"ERROR: Failed to parse configuration file: {e}")
            os._exit(1)

    # Create the configuration dictionary
    config = dict()

    # Get the base configuration
    try:
        o_base = o_config["pvc"]
    except KeyError as k:
        raise MalformedConfigurationError(f"Missing top-level category {k}")

    for key in ["debug", "deploy_username"]:
        try:
            config[key] = o_base[key]
        except KeyError as k:
            raise MalformedConfigurationError(f"Missing first-level key {k}")

    # Get the first-level categories
    try:
        o_database = o_base["database"]
        o_api = o_base["api"]
        o_queue = o_base["queue"]
        o_dhcp = o_base["dhcp"]
        o_tftp = o_base["tftp"]
        o_ansible = o_base["ansible"]
        o_notifications = o_base["notifications"]
    except KeyError as k:
        raise MalformedConfigurationError(f"Missing first-level category {k}")

    # Get the Datbase configuration
    for key in ["path"]:
        try:
            config[f"database_{key}"] = o_database[key]
        except Exception:
            raise MalformedConfigurationError(
                f"Missing second-level key '{key}' under 'database'"
            )

    # Get the API configuration
    for key in ["address", "port"]:
        try:
            config[f"api_{key}"] = o_api[key]
        except Exception:
            raise MalformedConfigurationError(
                f"Missing second-level key '{key}' under 'api'"
            )

    # Get the queue configuration
    for key in ["address", "port", "path"]:
        try:
            config[f"queue_{key}"] = o_queue[key]
        except Exception:
            raise MalformedConfigurationError(
                f"Missing second-level key '{key}' under 'queue'"
            )

    # Get the DHCP configuration
    for key in [
        "address",
        "gateway",
        "domain",
        "lease_start",
        "lease_end",
        "lease_time",
    ]:
        try:
            config[f"dhcp_{key}"] = o_dhcp[key]
        except Exception:
            raise MalformedConfigurationError(
                f"Missing second-level key '{key}' under 'dhcp'"
            )

    # Get the TFTP configuration
    for key in ["root_path", "host_path"]:
        try:
            config[f"tftp_{key}"] = o_tftp[key]
        except Exception:
            raise MalformedConfigurationError(
                f"Missing second-level key '{key}' under 'tftp'"
            )

    # Get the Ansible configuration
    for key in ["path", "keyfile", "remote", "branch", "clusters_file"]:
        try:
            config[f"ansible_{key}"] = o_ansible[key]
        except Exception:
            raise MalformedConfigurationError(
                f"Missing second-level key '{key}' under 'ansible'"
            )

    # Get the second-level categories under Ansible
    try:
        o_ansible_cspec_files = o_ansible["cspec_files"]
    except KeyError as k:
        raise MalformedConfigurationError(
            f"Missing second-level category {k} under 'ansible'"
        )

    # Get the Ansible CSpec Files configuration
    for key in ["base", "pvc", "bootstrap"]:
        try:
            config[f"ansible_cspec_files_{key}"] = o_ansible_cspec_files[key]
        except Exception:
            raise MalformedConfigurationError(
                f"Missing third-level key '{key}' under 'ansible/cspec_files'"
            )

    # Get the Notifications configuration
    for key in ["enabled", "uri", "action", "icons", "body", "completed_triggerword"]:
        try:
            config[f"notifications_{key}"] = o_notifications[key]
        except Exception:
            raise MalformedConfigurationError(
                f"Missing second-level key '{key}' under 'notifications'"
            )

    return config


config = read_config()


##########################################################
# Entrypoint
##########################################################


def entrypoint():
    import pvcbootstrapd.flaskapi as pvcbootstrapd  # noqa: E402

    # Print our startup messages
    print("")
    print("|----------------------------------------------------------|")
    print("|                                                          |")
    print("|           ███████████ ▜█▙      ▟█▛ █████ █ █ █           |")
    print("|                    ██  ▜█▙    ▟█▛  ██                    |")
    print("|           ███████████   ▜█▙  ▟█▛   ██                    |")
    print("|           ██             ▜█▙▟█▛    ███████████           |")
    print("|                                                          |")
    print("|----------------------------------------------------------|")
    print("| Parallel Virtual Cluster Bootstrap API daemon v{0: <9} |".format(version))
    print("| Debug: {0: <49} |".format(str(config["debug"])))
    print("| API version: v{0: <42} |".format(API_VERSION))
    print(
        "| Listen: {0: <48} |".format(
            "{}:{}".format(config["api_address"], config["api_port"])
        )
    )
    print("|----------------------------------------------------------|")
    print("")

    notifications.send_webhook(config, "info", "Initializing pvcbootstrapd")

    # Initialize the database
    db.init_database(config)

    # Initialize the Ansible repository
    git.init_repository(config)

    # Initialize the tftp root
    tftp.init_tftp(config)

    if "--init-only" in argv:
        print("Successfully initialized pvcbootstrapd; exiting.")
        notifications.send_webhook(config, "completed", "Successfully initialized pvcbootstrapd")
        exit(0)

    # Start DNSMasq
    dnsmasq = dnsmasqd.DNSMasq(config)
    dnsmasq.start()

    def cleanup(retcode):
        dnsmasq.stop()
        exit(retcode)

    def term(signum="", frame=""):
        print("Received TERM, exiting.")
        notifications.send_webhook(config, "info", "Received TERM, exiting pvcbootstrapd")
        cleanup(0)

    signal.signal(signal.SIGTERM, term)
    signal.signal(signal.SIGINT, term)
    signal.signal(signal.SIGQUIT, term)

    notifications.send_webhook(config, "info", "Starting up pvcbootstrapd")

    # Start Flask
    pvcbootstrapd.app.run(
        config["api_address"],
        config["api_port"],
        use_reloader=False,
        threaded=False,
        processes=4,
    )
