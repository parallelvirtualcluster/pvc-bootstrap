#!/usr/bin/env python3

# dataclasses.py - PVC Cluster Auto-bootstrap dataclasses
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

from dataclasses import dataclass


@dataclass
class Cluster:
    """
    An instance of a Cluster
    """

    id: int
    name: str
    state: str


@dataclass
class Node:
    """
    An instance of a Node
    """

    id: int
    cluster: str
    state: str
    name: str
    nid: int
    bmc_macaddr: str
    bmc_iapddr: str
    host_macaddr: str
    host_ipaddr: str
