#!/usr/bin/env python3
# -*- coding: utf8 -*-

import logging
from .QRadarConnector import QRadarConnector

class Actuator:
    'Actuator class to group all possible actions following a listened webhook'

    def __init__(self, cfg):
        """
            Class constructor

            :param cfg: Synapse's config
            :type cfg: ConfigParser

            :return: Object Actuator
            :rtype: Actuator
        """

        self.logger = logging.getLogger('workflows.' + __name__)
        self.qradarConnector = QRadarConnector(cfg)

    def closeOffense(self, offenseId):
        """
            Close an offense in QRadar given a specific offenseId
        """

        self.logger.info('%s.closeOffense starts', __name__)
        try:
            if self.qradarConnector.offenseIsOpen(offenseId):
                self.qradarConnector.closeOffense(offenseId)
            else:
                self.logger.info('Offense %s already closed', offenseId)
        except Exception as e:
            self.logger.error('Failed to close offense %s', offenseId, exc_info=True)
            raise
