# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, models, tools
from odoo.tools import decode_smtp_header, decode_message_header

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    """ Update MailThread to add the support of bounce management in mass mailing statistics. """
    _inherit = 'mail.thread'

    @api.model
    def message_route(self, message, message_dict, model=None, thread_id=None, custom_values=None):
        """ Override to udpate mass mailing statistics based on bounce emails """
        bounce_alias = self.env['ir.config_parameter'].get_param("mail.bounce.alias")
        email_to = decode_message_header(message, 'To')
        email_to_localpart = (tools.email_split(email_to) or [''])[0].split('@', 1)[0].lower()

        if bounce_alias and bounce_alias in email_to_localpart:
            bounce_re = re.compile("%s\+(\d+)-?([\w.]+)?-?(\d+)?" % re.escape(bounce_alias), re.UNICODE)
            bounce_match = bounce_re.search(email_to)
            if bounce_match:
                bounced_mail_id = bounce_match.group(1)
                self.env['mail.mail.statistics'].set_bounced(mail_mail_ids=[bounced_mail_id])

        return super(MailThread, self).message_route(message, message_dict, model, thread_id, custom_values)

    @api.model
    def message_route_process(self, message, message_dict, routes):
        """ Override to update the parent mail statistics. The parent is found
        by using the References header of the incoming message and looking for
        matching message_id in mail.mail.statistics. """
        if any(routes) and message.get('References'):
            message_ids = [x.strip() for x in decode_smtp_header(message['References']).split()]
            self.env['mail.mail.statistics'].set_replied(mail_message_ids=message_ids)
        return super(MailThread, self).message_route_process(message, message_dict, routes)

    @api.model
    def maillog_process(self, mail_log):
        statistics = self.env['mail.mail.statistics'].search([('message_id', '=', mail_log['message_id'])], limit=1)
        if not statistics or not mail_log['last_status']:
            return

        """ We update email status send/bounced. """
        self.env['mail.mail.statistics'].set_status(message_id=mail_log['message_id'], status=mail_log['last_status'])
        """ This statistic already bounced or this is not bounced email. """
        if statistics.bounced or "bounced" not in mail_log['last_status']:
            return

        self.env['mail.mail.statistics'].set_bounced(mail_message_ids=[mail_log['message_id']])
        bounce_alias = self.env['ir.config_parameter'].get_param("mail.bounce.alias")
        email_from = mail_log['email_from']
        email_from_localpart = (tools.email_split(email_from) or [''])[0].split('@', 1)[0].lower()

        if bounce_alias and bounce_alias in email_from_localpart:
            bounce_re = re.compile("%s\+(\d+)-?([\w.]+)?-?(\d+)?" % re.escape(bounce_alias), re.UNICODE)
            bounce_match = bounce_re.search(email_from)
            if bounce_match:
                bounced_mail_id, bounced_model, bounced_thread_id = bounce_match.group(1), bounce_match.group(
                    2), bounce_match.group(3)
                if bounced_mail_id and bounced_model and bounced_thread_id:
                    super(MailThread, self).maillog_process(mail_log, bounced_mail_id, bounced_model, bounced_thread_id)