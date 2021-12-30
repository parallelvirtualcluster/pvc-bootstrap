#!/usr/bin/env python3

# dnsmasq-lease.py - DNSMasq lease interface for pvcnodedprov
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

from os import environ
from sys import argv
from requests import post
from json import dumps

# Request log
# dnsmasq-dhcp[877466]: 2067194916 available DHCP range: 10.199.199.10 -- 10.199.199.19
# dnsmasq-dhcp[877466]: 2067194916 DHCPDISCOVER(ens8) 52:54:00:34:36:40
# dnsmasq-dhcp[877466]: 2067194916 tags: ens8
# dnsmasq-dhcp[877466]: 2067194916 DHCPOFFER(ens8) 10.199.199.14 52:54:00:34:36:40
# dnsmasq-dhcp[877466]: 2067194916 requested options: 1:netmask, 28:broadcast, 2:time-offset, 3:router,
# dnsmasq-dhcp[877466]: 2067194916 requested options: 15:domain-name, 6:dns-server, 12:hostname
# dnsmasq-dhcp[877466]: 2067194916 next server: 10.199.199.1
# dnsmasq-dhcp[877466]: 2067194916 sent size:  1 option: 53 message-type  2
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 54 server-identifier  10.199.199.1
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 51 lease-time  1h
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 58 T1  30m
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 59 T2  52m30s
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option:  1 netmask  255.255.255.0
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 28 broadcast  10.199.199.255
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option:  3 router  10.199.199.1
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option:  6 dns-server  10.199.199.1
# dnsmasq-dhcp[877466]: 2067194916 sent size:  8 option: 15 domain-name  test.com
# dnsmasq-dhcp[877466]: 2067194916 available DHCP range: 10.199.199.10 -- 10.199.199.19
# dnsmasq-dhcp[877466]: 2067194916 DHCPREQUEST(ens8) 10.199.199.14 52:54:00:34:36:40
# dnsmasq-dhcp[877466]: 2067194916 tags: ens8
# dnsmasq-dhcp[877466]: 2067194916 DHCPACK(ens8) 10.199.199.14 52:54:00:34:36:40
# dnsmasq-dhcp[877466]: 2067194916 requested options: 1:netmask, 28:broadcast, 2:time-offset, 3:router,
# dnsmasq-dhcp[877466]: 2067194916 requested options: 15:domain-name, 6:dns-server, 12:hostname
# dnsmasq-dhcp[877466]: 2067194916 next server: 10.199.199.1
# dnsmasq-dhcp[877466]: 2067194916 sent size:  1 option: 53 message-type  5
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 54 server-identifier  10.199.199.1
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 51 lease-time  1h
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 58 T1  30m
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 59 T2  52m30s
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option:  1 netmask  255.255.255.0
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option: 28 broadcast  10.199.199.255
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option:  3 router  10.199.199.1
# dnsmasq-dhcp[877466]: 2067194916 sent size:  4 option:  6 dns-server  10.199.199.1
# dnsmasq-dhcp[877466]: 2067194916 sent size:  8 option: 15 domain-name  test.com
# dnsmasq-script[877466]: ['/var/home/joshua/dnsmasq-lease.py', 'add', '52:54:00:34:36:40', '10.199.199.14']
# dnsmasq-script[877466]: environ({'DNSMASQ_INTERFACE': 'ens8', 'DNSMASQ_LEASE_EXPIRES': '1638422308', 'DNSMASQ_REQUESTED_OPTIONS': '1,28,2,3,15,6,12', 'DNSMASQ_TAGS': 'ens8', 'DNSMASQ_TIME_REMAINING': '3600', 'DNSMASQ_LOG_DHCP': '1', 'LC_CTYPE': 'C.UTF-8'})

# Renew log
# dnsmasq-dhcp[877466]: 1471211555 available DHCP range: 10.199.199.10 -- 10.199.199.19
# dnsmasq-dhcp[877466]: 1471211555 DHCPREQUEST(ens8) 10.199.199.14 52:54:00:34:36:40
# dnsmasq-dhcp[877466]: 1471211555 tags: ens8
# dnsmasq-dhcp[877466]: 1471211555 DHCPACK(ens8) 10.199.199.14 52:54:00:34:36:40
# dnsmasq-dhcp[877466]: 1471211555 requested options: 1:netmask, 28:broadcast, 2:time-offset, 3:router,
# dnsmasq-dhcp[877466]: 1471211555 requested options: 15:domain-name, 6:dns-server, 12:hostname
# dnsmasq-dhcp[877466]: 1471211555 next server: 10.199.199.1
# dnsmasq-dhcp[877466]: 1471211555 sent size:  1 option: 53 message-type  5
# dnsmasq-dhcp[877466]: 1471211555 sent size:  4 option: 54 server-identifier  10.199.199.1
# dnsmasq-dhcp[877466]: 1471211555 sent size:  4 option: 51 lease-time  1h
# dnsmasq-dhcp[877466]: 1471211555 sent size:  4 option: 58 T1  30m
# dnsmasq-dhcp[877466]: 1471211555 sent size:  4 option: 59 T2  52m30s
# dnsmasq-dhcp[877466]: 1471211555 sent size:  4 option:  1 netmask  255.255.255.0
# dnsmasq-dhcp[877466]: 1471211555 sent size:  4 option: 28 broadcast  10.199.199.255
# dnsmasq-dhcp[877466]: 1471211555 sent size:  4 option:  3 router  10.199.199.1
# dnsmasq-dhcp[877466]: 1471211555 sent size:  4 option:  6 dns-server  10.199.199.1
# dnsmasq-dhcp[877466]: 1471211555 sent size:  8 option: 15 domain-name  test.com
# dnsmasq-script[877466]: ['/var/home/joshua/dnsmasq-lease.py', 'old', '52:54:00:34:36:40', '10.199.199.14']
# dnsmasq-script[877466]: environ({'DNSMASQ_INTERFACE': 'ens8', 'DNSMASQ_LEASE_EXPIRES': '1638422371', 'DNSMASQ_REQUESTED_OPTIONS': '1,28,2,3,15,6,12', 'DNSMASQ_TAGS': 'ens8', 'DNSMASQ_TIME_REMAINING': '3600', 'DNSMASQ_LOG_DHCP': '1', 'LC_CTYPE': 'C.UTF-8'})

action = argv[1]

api_uri = environ.get("API_URI", "http://127.0.0.1:9999/checkin/dnsmasq")
api_headers = {"ContentType": "application/json"}

print(environ)

if action in ["add"]:
    macaddr = argv[2]
    ipaddr = argv[3]
    api_data = dumps(
        {
            "action": action,
            "macaddr": macaddr,
            "ipaddr": ipaddr,
            "hostname": environ.get("DNSMASQ_SUPPLIED_HOSTNAME"),
            "client_id": environ.get("DNSMASQ_CLIENT_ID"),
            "expiry": environ.get("DNSMASQ_LEASE_EXPIRES"),
            "vendor_class": environ.get("DNSMASQ_VENDOR_CLASS"),
            "user_class": environ.get("DNSMASQ_USER_CLASS0"),
        }
    )
    post(api_uri, headers=api_headers, data=api_data, verify=False)

elif action in ["tftp"]:
    size = argv[2]
    destaddr = argv[3]
    filepath = argv[4]
    api_data = dumps(
        {"action": action, "size": size, "destaddr": destaddr, "filepath": filepath}
    )
    post(api_uri, headers=api_headers, data=api_data, verify=False)

exit(0)
