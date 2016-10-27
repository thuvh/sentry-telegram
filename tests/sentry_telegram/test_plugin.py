from __future__ import absolute_import

import responses

from exam import fixture
from sentry.models import Rule
from sentry.plugins import Notification
from sentry.testutils import TestCase
from sentry.utils import json
from urlparse import parse_qs

from sentry_telegram.plugin import TelegramPlugin


class TelegramPluginTest(TestCase):
    @fixture
    def plugin(self):
        return TelegramPlugin()

    @responses.activate
    def test_simple_notification(self):
        token = 'x' * 9 + ':' + 'x' * 35 # test bot token
        chat_id = -100000000  # test id
        url = 'https://api.telegram.org/bot%s/sendMessages'

        responses.add('POST', url % (token))
        self.plugin.set_option('token', token, self.project)
        self.plugin.set_option('chat_id', chat_id, self.project)

        group = self.create_group(message='Hello world', culprit='foo.bar')
        event = self.create_event(group=group, message='Hello world', tags={'level': 'warning'})

        rule = Rule.objects.create(project=self.project, label='my rule')

        notification = Notification(event=event, rule=rule)

        with self.options({'system.url-prefix': 'https://api.telegram.org'}):
            self.plugin.notify(notification)

        request = responses.calls[0].request
        payload = json.loads(parse_qs(request.body)['payload'][0])
        assert str(payload['chat_id']) == chat_id

