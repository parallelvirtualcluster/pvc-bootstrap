#!/usr/bin/env python3

# tftp.py - PVC Cluster Auto-bootstrap TFTP preparation libraries
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
import shutil
from subprocess import run

import pvcbootstrapd.lib.notifications as notifications


def build_tftp_repository(config):
    # Generate an installer config
    build_cmd = [ f"{config['ansible_path']}/pvc-installer/buildpxe.sh", "-o", config['tftp_root_path'], "-u", config['deploy_username'], "-m", config["repo_mirror"] ]
    print(f"Building TFTP contents via pvc-installer command: {' '.join(build_cmd)}")
    notifications.send_webhook(config, "begin", f"Building TFTP contents via pvc-installer command: {' '.join(build_cmd)}")
    ret = run(build_cmd)
    return True if ret.returncode == 0 else False


def init_tftp(config):
    """
    Prepare a TFTP root
    """
    if not os.path.exists(config["tftp_root_path"]):
        print("First run: building TFTP root and contents - this will take some time!")
        notifications.send_webhook(config, "begin", "First run: building TFTP root and contents")
        os.makedirs(config["tftp_root_path"])
        os.makedirs(config["tftp_host_path"])
        shutil.copyfile(
            f"{config['ansible_key_file']}.pub", f"{config['tftp_root_path']}/keys.txt"
        )

        result = build_tftp_repository(config)
        if result:
            print("First run: successfully initialized TFTP root and contents")
            notifications.send_webhook(config, "success", "First run: successfully initialized TFTP root and contents")
        else:
            print("First run: failed initialized TFTP root and contents; see logs above")
            notifications.send_webhook(config, "failure", "First run: failed initialized TFTP root and contents; check pvcbootstrapd logs")
