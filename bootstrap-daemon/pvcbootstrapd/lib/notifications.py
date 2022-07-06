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

    if not config['notifications_enabled']:
        return

    logger.debug(f"Sending notification to {config['notifications_uri']}")

    # Get the body data
    body = config['notifications_body']
    formatted_body = dict()
    for element, value in body.items():
        formatted_body[element] = value.format(
            icon=config['notifications_icons'][status],
            message=message
        )
    data = json.dumps(formatted_body)
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
    action = config['notifications_action']

    result = requests_actions[action](config['notifications_uri'], headers=headers, data=data)

    logger.debug(f"Result: {result}")
