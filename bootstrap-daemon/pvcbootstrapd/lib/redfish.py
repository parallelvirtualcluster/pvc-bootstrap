#!/usr/bin/env python3

# redfish.py - PVC Cluster Auto-bootstrap Redfish libraries
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

# Refs:
# https://downloads.dell.com/manuals/all-products/esuprt_software/esuprt_it_ops_datcentr_mgmt/dell-management-solution-resources_white-papers11_en-us.pdf
# https://downloads.dell.com/solutions/dell-management-solution-resources/RESTfulSerConfig-using-iDRAC-REST%20API%28DTC%20copy%29.pdf

import requests
import urllib3
import json
import re
import math
from time import sleep
from celery.utils.log import get_task_logger

import pvcbootstrapd.lib.notifications as notifications
import pvcbootstrapd.lib.installer as installer
import pvcbootstrapd.lib.db as db


logger = get_task_logger(__name__)


#
# Helper Classes
#
class AuthenticationException(Exception):
    def __init__(self, error=None, response=None):
        if error is not None:
            self.short_message = error
        else:
            self.short_message = "Generic authentication failure"

        if response is not None:
            rinfo = response.json()["error"]["@Message.ExtendedInfo"][0]
            if rinfo.get("Message") is not None:
                self.full_message = rinfo["Message"]
                self.res_message = rinfo["Resolution"]
                self.severity = rinfo["Severity"]
                self.message_id = rinfo["MessageId"]
            else:
                self.full_message = ""
                self.res_message = ""
                self.severity = "Fatal"
                self.message_id = rinfo["MessageId"]
            self.status_code = response.status_code
        else:
            self.status_code = None

    def __str__(self):
        if self.status_code is not None:
            message = f"{self.short_message}: {self.full_message} {self.res_message} (HTTP Code: {self.status_code}, Severity: {self.severity}, ID: {self.message_id})"
        else:
            message = f"{self.short_message}"
        return str(message)


class RedfishSession:
    def __init__(self, host, username, password):
        # Disable urllib3 warnings
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # Perform login
        login_payload = {"UserName": username, "Password": password}
        login_uri = f"{host}/redfish/v1/Sessions"
        login_headers = {"content-type": "application/json"}

        self.host = None
        login_response = None

        tries = 1
        max_tries = 61
        while tries < max_tries:
            logger.info(f"Trying to log in to Redfish ({tries}/{max_tries - 1})...")
            try:
                login_response = requests.post(
                    login_uri,
                    data=json.dumps(login_payload),
                    headers=login_headers,
                    verify=False,
                    timeout=5,
                )
                break
            except Exception:
                sleep(2)
                tries += 1

        if login_response is None:
            logger.error("Failed to log in to Redfish")
            return

        if login_response.status_code not in [200, 201]:
            raise AuthenticationException("Login failed", response=login_response)
        logger.info(f"Logged in to Redfish at {host} successfully")

        self.host = host
        self.token = login_response.headers.get("X-Auth-Token")
        self.headers = {"content-type": "application/json", "x-auth-token": self.token}

        logout_uri = login_response.headers.get("Location")
        if re.match(r"^/", logout_uri):
            self.logout_uri = f"{host}{logout_uri}"
        else:
            self.logout_uri = logout_uri

    def __del__(self):
        if self.host is None:
            return

        logout_headers = {
            "Content-Type": "application/json",
            "X-Auth-Token": self.token,
        }

        logout_response = requests.delete(
            self.logout_uri, headers=logout_headers, verify=False, timeout=15
        )

        if logout_response.status_code not in [200, 201]:
            raise AuthenticationException("Logout failed", response=logout_response)
        logger.info(f"Logged out of Redfish at {self.host} successfully")

    def get(self, uri):
        url = f"{self.host}{uri}"

        response = requests.get(url, headers=self.headers, verify=False)

        if response.status_code in [200, 201]:
            return response.json()
        else:
            rinfo = response.json()["error"]["@Message.ExtendedInfo"][0]
            if rinfo.get("Message") is not None:
                message = f"{rinfo['Message']} {rinfo['Resolution']}"
                severity = rinfo["Severity"]
                message_id = rinfo["MessageId"]
            else:
                message = rinfo
                severity = "Error"
                message_id = "N/A"
            logger.warn(f"! Error: GET request to {url} failed")
            logger.warn(
                f"! HTTP Code: {response.status_code}   Severity: {severity}   ID: {message_id}"
            )
            logger.warn(f"! Details: {message}")
            return None

    def delete(self, uri):
        url = f"{self.host}{uri}"

        response = requests.delete(url, headers=self.headers, verify=False)

        if response.status_code in [200, 201]:
            return response.json()
        else:
            rinfo = response.json()["error"]["@Message.ExtendedInfo"][0]
            if rinfo.get("Message") is not None:
                message = f"{rinfo['Message']} {rinfo['Resolution']}"
                severity = rinfo["Severity"]
                message_id = rinfo["MessageId"]
            else:
                message = rinfo
                severity = "Error"
                message_id = "N/A"

            logger.warn(f"! Error: DELETE request to {url} failed")
            logger.warn(
                f"! HTTP Code: {response.status_code}   Severity: {severity}   ID: {message_id}"
            )
            logger.warn(f"! Details: {message}")
            return None

    def post(self, uri, data):
        url = f"{self.host}{uri}"
        payload = json.dumps(data)

        logger.debug(f"POST payload: {payload}")

        response = requests.post(url, data=payload, headers=self.headers, verify=False)

        if response.status_code in [200, 201, 204]:
            try:
                return response.json()
            except json.decoder.JSONDecodeError as e:
                return {"json_err": e}
        else:
            try:
                rinfo = response.json()["error"]["@Message.ExtendedInfo"][0]
            except json.decoder.JSONDecodeError:
                logger.debug(response)
                raise

            if rinfo.get("Message") is not None:
                message = f"{rinfo['Message']} {rinfo['Resolution']}"
                severity = rinfo["Severity"]
                message_id = rinfo["MessageId"]
            else:
                message = rinfo
                severity = "Error"
                message_id = "N/A"

            logger.warn(f"! Error: POST request to {url} failed")
            logger.warn(
                f"! HTTP Code: {response.status_code}   Severity: {severity}   ID: {message_id}"
            )
            logger.warn(f"! Details: {message}")
            return None

    def put(self, uri, data):
        url = f"{self.host}{uri}"
        payload = json.dumps(data)

        logger.debug(f"PUT payload: {payload}")

        response = requests.put(url, data=payload, headers=self.headers, verify=False)

        if response.status_code in [200, 201]:
            return response.json()
        else:
            rinfo = response.json()["error"]["@Message.ExtendedInfo"][0]
            if rinfo.get("Message") is not None:
                message = f"{rinfo['Message']} {rinfo['Resolution']}"
                severity = rinfo["Severity"]
                message_id = rinfo["MessageId"]
            else:
                message = rinfo
                severity = "Error"
                message_id = "N/A"

            logger.warn(f"! Error: PUT request to {url} failed")
            logger.warn(
                f"! HTTP Code: {response.status_code}   Severity: {severity}   ID: {message_id}"
            )
            logger.warn(f"! Details: {message}")
            return None

    def patch(self, uri, data):
        url = f"{self.host}{uri}"
        payload = json.dumps(data)

        logger.debug(f"PATCH payload: {payload}")

        response = requests.patch(url, data=payload, headers=self.headers, verify=False)

        if response.status_code in [200, 201]:
            return response.json()
        else:
            rinfo = response.json()["error"]["@Message.ExtendedInfo"][0]
            if rinfo.get("Message") is not None:
                message = f"{rinfo['Message']} {rinfo['Resolution']}"
                severity = rinfo["Severity"]
                message_id = rinfo["MessageId"]
            else:
                message = rinfo
                severity = "Error"
                message_id = "N/A"

            logger.warn(f"! Error: PATCH request to {url} failed")
            logger.warn(
                f"! HTTP Code: {response.status_code}   Severity: {severity}   ID: {message_id}"
            )
            logger.warn(f"! Details: {message}")
            return None


#
# Helper functions
#
def format_bytes_tohuman(databytes):
    """
    Format a string of bytes into a human-readable value (using base-1000)
    """
    # Matrix of human-to-byte values
    byte_unit_matrix = {
        "B": 1,
        "KB": 1000,
        "MB": 1000 * 1000,
        "GB": 1000 * 1000 * 1000,
        "TB": 1000 * 1000 * 1000 * 1000,
        "PB": 1000 * 1000 * 1000 * 1000 * 1000,
        "EB": 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
    }

    datahuman = ""
    for unit in sorted(byte_unit_matrix, key=byte_unit_matrix.get, reverse=True):
        if unit in ["TB", "PB", "EB"]:
            # Handle the situation where we might want to round to integer values
            # for some entries (2TB) but not others (e.g. 1.92TB). We round if the
            # result is within +/- 2% of the integer value, otherwise we use two
            # decimal places.
            new_bytes = databytes / byte_unit_matrix[unit]
            new_bytes_plustwopct = new_bytes * 1.02
            new_bytes_minustwopct = new_bytes * 0.98
            cieled_bytes = int(math.ceil(databytes / byte_unit_matrix[unit]))
            rounded_bytes = round(databytes / byte_unit_matrix[unit], 2)
            if (
                cieled_bytes > new_bytes_minustwopct
                and cieled_bytes < new_bytes_plustwopct
            ):
                new_bytes = cieled_bytes
            else:
                new_bytes = rounded_bytes

        # Round up if 5 or more digits
        if new_bytes > 999:
            # We can jump down another level
            continue
        else:
            # We're at the end, display with this size
            datahuman = "{}{}".format(new_bytes, unit)

    return datahuman


def get_system_drive_target(session, cspec_node, storage_root):
    """
    Determine the system drive target for the installer
    """
    # Handle an invalid >2 number of system disks, use only first 2
    if len(cspec_node["config"]["system_disks"]) > 2:
        cspec_drives = cspec_node["config"]["system_disks"][0:2]
    else:
        cspec_drives = cspec_node["config"]["system_disks"]

    # If we have no storage root, we just return the first entry from
    # the cpsec_drives as-is and hope the administrator has the right
    # format here.
    if storage_root is None:
        return cspec_drives[0]
    # We proceed with Redfish configuration to determine the disks
    else:
        storage_detail = session.get(storage_root)

        # Grab a full list of drives
        drive_list = list()
        for storage_member in storage_detail["Members"]:
            storage_member_root = storage_member["@odata.id"]
            storage_member_detail = session.get(storage_member_root)
            for drive in storage_member_detail["Drives"]:
                drive_root = drive["@odata.id"]
                drive_detail = session.get(drive_root)
                drive_list.append(drive_detail)

        system_drives = list()

        # Iterate through each drive and include those that match
        for cspec_drive in cspec_drives:
            if re.match(r"^\/dev", cspec_drive) or re.match(r"^detect:", cspec_drive):
                # We only match the first drive that has these conditions for use in the preseed config
                logger.info(
                    "Found a drive with a 'detect:' string or Linux '/dev' path, using it for bootstrap."
                )
                return cspec_drive

            # Match any chassis-ID spec drives
            for drive in drive_list:
                # Like "Disk.Bay.2:Enclosure.Internal.0-1:RAID.Integrated.1-1"
                drive_name = drive["Id"].split(":")[0]
                # Craft up the cspec version of this
                cspec_drive_name = f"Drive.Bay.{cspec_drive}"
                if drive_name == cspec_drive_name:
                    system_drives.append(drive)

        # We found a single drive, so determine its actual detect string
        if len(system_drives) == 1:
            logger.info(
                "Found a single drive matching the requested chassis ID, using it as the system disk."
            )

            # Get the model's first word
            drive_model = system_drives[0].get("Model", "INVALID").split()[0]
            # Get and convert the size in bytes value to human
            drive_size_bytes = system_drives[0].get("CapacityBytes", 0)
            drive_size_human = format_bytes_tohuman(drive_size_bytes)
            # Get the drive ID out of all the valid entries
            # How this works is that, for each non-array disk, we must find what position our exact disk is
            # So for example, say we want disk 3 out of 4, and all 4 are the same size and model and not in
            # another (RAID) volume. This will give us an index of 2. Then in the installer this will match
            # the 3rd list entry from "lsscsi". This is probably an unneccessary hack, since people will
            # probably just give the first disk if they want one, or 2 disks if they want a RAID-1, but this
            # is here just in case
            idx = 0
            for drive in drive_list:
                list_drive_model = drive.get("Model", "INVALID").split()[0]
                list_drive_size_bytes = drive.get("CapacityBytes", 0)
                list_drive_in_array = (
                    False
                    if drive.get("Links", {})
                    .get("Volumes", [""])[0]
                    .get("@odata.id")
                    .split("/")[-1]
                    == drive.get("Id")
                    else True
                )
                if (
                    drive_model == list_drive_model
                    and drive_size_bytes == list_drive_size_bytes
                    and not list_drive_in_array
                ):
                    index = idx
                    idx += 1
            drive_id = index

            # Create the target string
            system_drive_target = f"detect:{drive_model}:{drive_size_human}:{drive_id}"

        # We found two drives, so create a RAID-1 array then determine the volume's detect string
        elif len(system_drives) == 2:
            logger.info(
                "Found two drives matching the requested chassis IDs, creating a RAID-1 and using it as the system disk."
            )

            drive_one = system_drives[0]
            drive_one_id = drive_one.get("Id", "INVALID")
            drive_one_path = drive_one.get("@odata.id", "INVALID")
            drive_one_controller = drive_one_id.split(":")[-1]
            drive_two = system_drives[1]
            drive_two_id = drive_two.get("Id", "INVALID")
            drive_two_path = drive_two.get("@odata.id", "INVALID")
            drive_two_controller = drive_two_id.split(":")[-1]

            # Determine that the drives are on the same controller
            if drive_one_controller != drive_two_controller:
                logger.error(
                    "Two drives are not on the same controller; this should not happen"
                )
                return None

            # Get the controller details
            controller_root = f"{storage_root}/{drive_one_controller}"
            controller_detail = session.get(controller_root)

            # Get the name of the controller (for crafting the detect string)
            controller_name = controller_detail.get("Name", "INVALID").split()[0]

            # Get the volume root for the controller
            controller_volume_root = controller_detail.get("Volumes", {}).get(
                "@odata.id"
            )

            # Get the pre-creation list of volumes on the controller
            controller_volumes_pre = [
                volume["@odata.id"]
                for volume in session.get(controller_volume_root).get("Members", [])
            ]

            # Create the RAID-1 volume
            payload = {
                "VolumeType": "Mirrored",
                "Drives": [
                    {"@odata.id": drive_one_path},
                    {"@odata.id": drive_two_path},
                ],
            }
            session.post(controller_volume_root, payload)

            # Wait for the volume to be created
            new_volume_list = []
            while len(new_volume_list) < 1:
                sleep(5)
                controller_volumes_post = [
                    volume["@odata.id"]
                    for volume in session.get(controller_volume_root).get("Members", [])
                ]
                new_volume_list = list(
                    set(controller_volumes_post).difference(controller_volumes_pre)
                )
            new_volume_root = new_volume_list[0]

            # Get the IDX of the volume out of any others
            volume_id = 0
            for idx, volume in enumerate(controller_volumes_post):
                if volume == new_volume_root:
                    volume_id = idx
                    break

            # Get and convert the size in bytes value to human
            volume_detail = session.get(new_volume_root)
            volume_size_bytes = volume_detail.get("CapacityBytes", 0)
            volume_size_human = format_bytes_tohuman(volume_size_bytes)

            # Create the target string
            system_drive_target = (
                f"detect:{controller_name}:{volume_size_human}:{volume_id}"
            )

        # We found too few or too many drives, error
        else:
            system_drive_target = None

    return system_drive_target


#
# Redfish Task functions
#
def set_indicator_state(session, system_root, redfish_vendor, state):
    """
    Set the system indicator LED to the desired state (on/off)
    """
    state_values_write = {
        "Dell": {
            "on": "Blinking",
            "off": "Lit",
        },
        "default": {
            "on": "Lit",
            "off": "Off",
        },
    }

    state_values_read = {
        "Dell": {
            "on": "Blinking",
            "off": "Lit",
        },
        "default": {
            "on": "Lit",
            "off": "Off",
        },
    }

    try:
        # Allow vendor-specific overrides
        if redfish_vendor not in state_values_write:
            redfish_vendor = "default"
        # Allow nice names ("on"/"off")
        if state in state_values_write[redfish_vendor]:
            state = state_values_write[redfish_vendor][state]

        # Get current state
        system_detail = session.get(system_root)
        current_state = system_detail["IndicatorLED"]
    except KeyError:
        return False

    try:
        state_read = state
        # Allow vendor-specific overrides
        if redfish_vendor not in state_values_read:
            redfish_vendor = "default"
        # Allow nice names ("on"/"off")
        if state_read in state_values_read[redfish_vendor]:
            state_read = state_values_read[redfish_vendor][state]

        if state_read == current_state:
            return False
    except KeyError:
        return False

    session.patch(system_root, {"IndicatorLED": state})

    return True


def set_power_state(session, system_root, redfish_vendor, state):
    """
    Set the system power state to the desired state
    """
    state_values = {
        "default": {
            "on": "On",
            "off": "ForceOff",
        },
    }

    try:
        # Allow vendor-specific overrides
        if redfish_vendor not in state_values:
            redfish_vendor = "default"
        # Allow nice names ("on"/"off")
        if state in state_values[redfish_vendor]:
            state = state_values[redfish_vendor][state]

        # Get current state, target URI, and allowable values
        system_detail = session.get(system_root)
        current_state = system_detail["PowerState"]
        power_root = system_detail["Actions"]["#ComputerSystem.Reset"]["target"]
        power_choices = system_detail["Actions"]["#ComputerSystem.Reset"][
            "ResetType@Redfish.AllowableValues"
        ]
    except KeyError:
        return False

    # Remap some namings so we can check the current state against the target state
    if state in ["ForceOff"]:
        target_state = "Off"
    else:
        target_state = state

#    if target_state == current_state:
#        return False

#    if state not in power_choices:
#        return False

    session.post(power_root, {"ResetType": state})

    return True


def set_boot_override(session, system_root, redfish_vendor, target):
    """
    Set the system boot override to the desired target
    """
    try:
        system_detail = session.get(system_root)
        boot_targets = system_detail["Boot"]["BootSourceOverrideSupported"]
    except KeyError:
        return False

    if target not in boot_targets:
        return False

    session.patch(system_root, {"Boot": {"BootSourceOverrideTarget": target}})

    return True


def check_redfish(config, data):
    """
    Validate that a BMC is Redfish-capable
    """
    headers = {"Content-Type": "application/json"}
    logger.info("Checking for Redfish response...")
    count = 0
    while True:
        try:
            count += 1
            if count > 30:
                retcode = 500
                logger.warn("Aborted after 300s; device too slow or not booting.")
                break
            resp = requests.get(
                f"https://{data['ipaddr']}/redfish/v1",
                headers=headers,
                verify=False,
                timeout=10,
            )
            retcode = resp.retcode
            break
        except Exception:
            logger.info(f"Attempt {count}...")
            continue

    if retcode == 200:
        return True
    else:
        return False


#
# Entry function
#
def redfish_init(config, cspec, data):
    """
    Initialize a new node with Redfish
    """
    bmc_ipaddr = data["ipaddr"]
    bmc_macaddr = data["macaddr"]
    bmc_host = f"https://{bmc_ipaddr}"

    cspec_node = cspec["bootstrap"][bmc_macaddr]
    logger.debug(f"cspec_node = {cspec_node}")

    bmc_username = cspec_node["bmc"]["username"]
    bmc_password = cspec_node["bmc"]["password"]

    host_macaddr = ""
    host_ipaddr = ""

    cspec_cluster = cspec_node["node"]["cluster"]
    cspec_hostname = cspec_node["node"]["hostname"]
    cspec_fqdn = cspec_node["node"]["fqdn"]

    notifications.send_webhook(config, "begin", f"Cluster {cspec_cluster}: Beginning Redfish initialization of host {cspec_fqdn}")

    cluster = db.get_cluster(config, name=cspec_cluster)
    if cluster is None:
        cluster = db.add_cluster(config, cspec, cspec_cluster, "provisioning")

    logger.debug(cluster)

    db.update_node_state(config, cspec_cluster, cspec_hostname, "characterizing")
    db.update_node_addresses(
        config,
        cspec_cluster,
        cspec_hostname,
        bmc_macaddr,
        bmc_ipaddr,
        host_macaddr,
        host_ipaddr,
    )
    node = db.get_node(config, cspec_cluster, name=cspec_hostname)
    logger.debug(node)

    # Create the session and log in
    session = RedfishSession(bmc_host, bmc_username, bmc_password)
    if session.host is None:
        logger.info("Aborting Redfish configuration; reboot BMC to try again.")
        del session
        return

    logger.info("Characterizing node...")
    # Get Refish bases
    logger.debug("Getting redfish bases")
    redfish_base_root = "/redfish/v1"
    redfish_base_detail = session.get(redfish_base_root)

    redfish_vendor = list(redfish_base_detail["Oem"].keys())[0]
    redfish_name = redfish_base_detail["Name"]
    redfish_version = redfish_base_detail["RedfishVersion"]

    managers_base_root = redfish_base_detail["Managers"]["@odata.id"].rstrip("/")
    managers_base_detail = session.get(managers_base_root)
    manager_root = managers_base_detail["Members"][0]["@odata.id"].rstrip("/")

    systems_base_root = redfish_base_detail["Systems"]["@odata.id"].rstrip("/")
    systems_base_detail = session.get(systems_base_root)
    system_root = systems_base_detail["Members"][0]["@odata.id"].rstrip("/")

    # Force off the system and turn on the indicator
    logger.debug("Force off the system and turn on the indicator")
    set_power_state(session, system_root, redfish_vendor, "off")
    set_indicator_state(session, system_root, redfish_vendor, "on")

    logger.info("Waiting 60 seconds for system normalization")
    sleep(60)

    # Get the system details
    logger.debug("Get the system details")
    system_detail = session.get(system_root)

    system_sku = system_detail["SKU"].strip()
    system_serial = system_detail["SerialNumber"].strip()
    system_power_state = system_detail["PowerState"].strip()
    system_indicator_state = system_detail["IndicatorLED"].strip()
    system_health_state = system_detail["Status"]["Health"].strip()

    # Walk down the EthernetInterfaces construct to get the bootstrap interface MAC address
    logger.debug("Walk down the EthernetInterfaces construct to get the bootstrap interface MAC address")
    try:
        ethernet_root = system_detail["EthernetInterfaces"]["@odata.id"].rstrip("/")
        ethernet_detail = session.get(ethernet_root)
        embedded_ethernet_detail_members = [e for e in ethernet_detail["Members"] if "Embedded" in e["@odata.id"]]
        embedded_ethernet_detail_members.sort(key = lambda k: k["@odata.id"])
        first_interface_root = embedded_ethernet_detail_members[0]["@odata.id"].rstrip("/")
        first_interface_detail = session.get(first_interface_root)
    # Something went wrong, so fall back
    except KeyError:
        first_interface_detail = dict()

    # Try to get the MAC address directly from the interface detail (Redfish standard)
    logger.debug("Try to get the MAC address directly from the interface detail (Redfish standard)")
    if first_interface_detail.get("MACAddress") is not None:
        bootstrap_mac_address = first_interface_detail["MACAddress"].strip().lower()
    # Try to get the MAC address from the HostCorrelation->HostMACAddress (HP DL360x G8)
    elif len(system_detail.get("HostCorrelation", {}).get("HostMACAddress", [])) > 0:
        bootstrap_mac_address = (
            system_detail["HostCorrelation"]["HostMACAddress"][0].strip().lower()
        )
    # We can't find it, so use a dummy value
    else:
        logger.error("Could not find a valid MAC address for the bootstrap interface.")
        return

    # Display the system details
    logger.info("Found details from node characterization:")
    logger.info(f"> System Manufacturer: {redfish_vendor}")
    logger.info(f"> System Redfish Version: {redfish_version}")
    logger.info(f"> System Redfish Name: {redfish_name}")
    logger.info(f"> System SKU: {system_sku}")
    logger.info(f"> System Serial: {system_serial}")
    logger.info(f"> Power State: {system_power_state}")
    logger.info(f"> Indicator LED: {system_indicator_state}")
    logger.info(f"> Health State: {system_health_state}")
    logger.info(f"> Bootstrap NIC MAC: {bootstrap_mac_address}")

    # Update node host MAC address
    host_macaddr = bootstrap_mac_address
    node = db.update_node_addresses(
        config,
        cspec_cluster,
        cspec_hostname,
        bmc_macaddr,
        bmc_ipaddr,
        host_macaddr,
        host_ipaddr,
    )
    logger.debug(node)

    logger.info("Determining system disk...")
    storage_root = system_detail.get("Storage", {}).get("@odata.id")
    system_drive_target = get_system_drive_target(session, cspec_node, storage_root)
    if system_drive_target is None:
        logger.error(
            "No valid drives found; configure a single system drive as a 'detect:' string or Linux '/dev' path instead and try again."
        )
        return
    logger.info(f"Found system disk {system_drive_target}")

    # Create our preseed configuration
    logger.info("Creating node boot configurations...")
    installer.add_pxe(config, cspec_node, host_macaddr)
    installer.add_preseed(config, cspec_node, host_macaddr, system_drive_target)

    # Adjust any BIOS settings
    logger.info("Adjusting BIOS settings...")
    bios_root = system_detail.get("Bios", {}).get("@odata.id")
    if bios_root is not None:
        bios_detail = session.get(bios_root)
        bios_attributes = list(bios_detail["Attributes"].keys())
        for setting, value in cspec_node["bmc"].get("bios_settings", {}).items():
            if setting not in bios_attributes:
                continue

            payload = {"Attributes": {setting: value}}
            session.patch(f"{bios_root}/Settings", payload)

    # Adjust any Manager settings
    logger.info("Adjusting Manager settings...")
    mgrattribute_root = f"{manager_root}/Attributes"
    mgrattribute_detail = session.get(mgrattribute_root)
    mgrattribute_attributes = list(mgrattribute_detail["Attributes"].keys())
    for setting, value in cspec_node["bmc"].get("manager_settings", {}).items():
        if setting not in bios_attributes:
            continue

        payload = {"Attributes": {setting: value}}
        session.patch(mgrattribute_root, payload)

    # Set boot override to Pxe for the installer boot
    logger.info("Setting temporary PXE boot...")
    set_boot_override(session, system_root, redfish_vendor, "Pxe")

    notifications.send_webhook(config, "success", f"Cluster {cspec_cluster}: Completed Redfish initialization of host {cspec_fqdn}")

    # Turn on the system
    logger.info("Powering on node...")
    set_power_state(session, system_root, redfish_vendor, "on")
    notifications.send_webhook(config, "info", f"Cluster {cspec_cluster}: Powering on host {cspec_fqdn}")

    node = db.update_node_state(config, cspec_cluster, cspec_hostname, "pxe-booting")

    logger.info("Waiting for completion of node and cluster installation...")
    # Wait for the system to install and be configured
    while node.state != "booted-completed":
        sleep(60)
        # Keep the Redfish session alive
        session.get(redfish_base_root)
        # Refresh our node state
        node = db.get_node(config, cspec_cluster, name=cspec_hostname)

    # Graceful shutdown of the machine
    notifications.send_webhook(config, "info", f"Cluster {cspec_cluster}: Powering off host {cspec_fqdn}")
    set_power_state(session, system_root, redfish_vendor, "GracefulShutdown")
    system_power_state = "On"
    while system_power_state != "Off":
        sleep(5)
        # Refresh our power state from the system details
        system_detail = session.get(system_root)
        system_power_state = system_detail["PowerState"].strip()

    # Turn off the indicator to indicate bootstrap has completed
    set_indicator_state(session, system_root, redfish_vendor, "off")

    # We must delete the session
    del session
    return
