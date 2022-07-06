#!/usr/bin/env python3

# notifications.py - PVC Cluster Auto-bootstrap Notifications library
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

import json
import requests

from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


def send_webhook(config, status, message):
    """
    Send an notification webhook
    """

    if not config.get('notifications', None) or not config['notifications']['enabled']:
        return

    logger.debug(f"Sending notification to {config['notifications']['uri']}")

    # Get the body data
    data = json.dumps(config['notifications']['body']).format(
        icon=config['notifications']['icons'][status],
        message=message
    )
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
    action = config['notifications']["action"]

    result = requests_actions[action](config['notifications']["uri"], headers=headers, data=data)

    logger.debug(f"Result: {result}")
