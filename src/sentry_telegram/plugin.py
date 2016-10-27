"""
sentry_telegram.plugin
~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2015 by Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""
import re
import operator
import sentry_telegram
import time

from django import forms
from django.core.urlresolvers import reverse
from django.db.models import Q

from sentry import http
from sentry.models import TagKey, TagValue
from sentry.plugins.bases import notify
from sentry.utils.http import absolute_uri

BOT_TELEGRAM_URL_TEMPLATE = 'https://api.telegram.org/bot{token}/sendMessage'

LEVEL_TO_COLOR = {
    'debug': 'cfd3da',
    'info': '2788ce',
    'warning': 'f18500',
    'error': 'f43f20',
    'fatal': 'd20f2a',
}

CONTENT_TEMPLATE = """
# [{title}]({title_link})

*** Level: {level} ***

** Project: {project} **

** Culprit: {culprit} **

{triggers}

{tags}
"""


def validate_user_group_channel_id(id):
    return re.match('@[a-zA-Z0-9]{5,}', id) or re.match('-?[0-9]+', id)


# Project.get_full_name backported from v8.0
def get_project_full_name(project):
    if project.team.name not in project.name:
        return '%s %s' % (project.team.name, project.name)
    return project.name


class TelegramOptionsForm(notify.NotificationConfigurationForm):
    # webhook = forms.URLField(
    #     help_text='Your custom Slack webhook URL',
    #     widget=forms.URLInput(attrs={'class': 'span8'})
    # )
    bot_name = forms.CharField(
        label='Bot Name',
        help_text='The name that will be displayed by your bot messages.',
        widget=forms.TextInput(attrs={'class': 'span8'}),
        initial='Sentry',
        required=False
    )

    token = forms.CharField(
        label='Bot Token',
        help_text='The token of your Telegram Bot.',
        widget=forms.TextInput(attrs={'class': 'span8'})
    )

    chat_id = forms.CharField(
        label='Chat IDs',
        help_text='@publicchannelname or chat id',
        widget=forms.TextInput(attrs={
            'class': 'span8',
            'placeholder': 'e.g. @channel or -123456 or 1234567, seperated by spaces'
        }),
    )

    icon_url = forms.URLField(
        label='Icon URL',
        help_text='The url of the icon to appear beside your bot (32px png), '
                  'leave empty for none.<br />You may use '
                  'http://myovchev.github.io/sentry-slack/images/logo32.png',
        widget=forms.URLInput(attrs={'class': 'span8'}),
        required=False
    )

    include_tags = forms.BooleanField(
        help_text='Include tags with notifications',
        required=False,
    )
    included_tag_keys = forms.CharField(
        help_text='Only include these tags (comma separated list),'
                  'leave empty to include all',
        required=False,
    )
    excluded_tag_keys = forms.CharField(
        help_text='Exclude these tags (comma separated list)',
        required=False,
    )
    include_rules = forms.BooleanField(
        help_text='Include triggering rules with notifications',
        required=False,
    )


class TelegramPlugin(notify.NotificationPlugin):
    author = 'Sentry Team'
    author_url = 'https://github.com/getsentry'
    resource_links = (
        ('Bug Tracker', 'https://github.com/getsentry/sentry-slack/issues'),
        ('Source', 'https://github.com/getsentry/sentry-slack'),
    )

    title = 'Telegram'
    slug = 'telegram'
    description = 'Post notifications to a Telegram channel, group or user.'
    conf_key = 'telegram'
    version = sentry_telegram.VERSION
    project_conf_form = TelegramOptionsForm

    def is_configured(self, project):
        return all((self.get_option(k, project) for k in ('token', 'chat_id')))

    def color_for_event(self, event):
        return '#' + LEVEL_TO_COLOR.get(event.get_tag('level'), 'error')

    def _get_tags(self, event):
        # TODO(dcramer): we want this behavior to be more accessible in sentry
        tag_list = event.get_tags()
        if not tag_list:
            return ()

        key_labels = {
            o.key: o.get_label()
            for o in TagKey.objects.filter(
                project=event.project,
                key__in=[t[0] for t in tag_list],
            )
        }
        value_labels = {
            (o.key, o.value): o.get_label()
            for o in TagValue.objects.filter(
                reduce(operator.or_, (Q(key=k, value=v) for k, v in tag_list)),
                project=event.project,
            )
        }
        return (
            (key_labels.get(k, k), value_labels.get((k, v), v))
            for k, v in tag_list
        )

    def get_tag_list(self, name, project):
        option = self.get_option(name, project)
        if not option:
            return None
        return set(tag.strip().lower() for tag in option.split(','))

    def _make_alert(self, notification):
        event = notification.event
        group = event.group
        project = group.project

        title = event.message_short.encode('utf-8')
        # TODO(dcramer): we'd like this to be the event culprit, but Sentry
        # does not currently retain itname
        if group.culprit:
            culprit = group.culprit.encode('utf-8')
        else:
            culprit = None

        project_name = get_project_full_name(project).encode('utf-8')
        if culprit:
            if title == culprit:
                culprit = "same as title"
        else:
            culprit = '<empty>'

        triggers = ''
        tags = ''

        if self.get_option('include_rules', project):
            rules = []
            for rule in notification.rules:
                rule_link = reverse('sentry-edit-project-rule', args=[
                    group.organization.slug, project.slug, rule.id
                ])
                # Make sure it's an absolute uri since we're sending this
                # outside of Sentry into Slack
                rule_link = absolute_uri(rule_link)
                rules.append((rule_link, rule.label.encode('utf-8')))

            if rules:
                triggers = 'Triggered By: ' + ' '.join('[%s](%s)' % (label, link) for label, link in rules)

        if self.get_option('include_tags', project):
            included_tags = set(self.get_tag_list('included_tag_keys', project) or [])
            excluded_tags = set(self.get_tag_list('excluded_tag_keys', project) or [])

            tag_list = []

            for tag_key, tag_value in self._get_tags(event):
                lower_key = tag_key.lower()
                std_key = TagKey.get_standardized_key(lower_key)
                if included_tags and lower_key not in included_tags and std_key not in included_tags:
                    continue
                if excluded_tags and (lower_key in excluded_tags or std_key in excluded_tags):
                    continue
                tag_list.append((tag_key.encode('utf-8'), tag_value.encode('utf-8')))

            if tag_list:
                tags = 'Tags: \n%s' % ('\n'.join(['*%s %s*' % (key, value) for key, value in tag_list]))

        return CONTENT_TEMPLATE.format(title=title, title_link=group.get_absolute_url(), level=event.get_tag('level'),
                                       culprit=culprit, project=project_name, triggers=triggers,
                                       tags=tags).strip()



    def notify(self, notification):
        event = notification.event
        group = event.group
        project = group.project

        if not self.is_configured(project):
            return

        token = (self.get_option('token', project) or '').strip()
        webhook_url = BOT_TELEGRAM_URL_TEMPLATE.format(token=token)

        # bot_name = (self.get_option('bot_name', project) or 'Sentry').strip()
        # icon_url = self.get_option('icon_url', project)
        chat_id = (self.get_option('chat_id', project) or '').strip()

        alert = self._make_alert(notification)
        alerts = []
        len_alert = len(alert)
        num_of_page = len_alert // 3072 + 1
        for i in range(num_of_page):
            si = 3072 * i
            ei = 3072 * (i + 1)
            if ei >= len_alert:
                ei = len_alert
            content = alert[si:ei]
            if num_of_page > 1:
                content += '\n(Page %s/%s)' % (i + 1, num_of_page)
            alerts.append(content)

        result = None
        users = chat_id.split()
        for user in users:
            if validate_user_group_channel_id(user):
                payload = {
                    'chat_id': user,
                    'parse_mode': 'Markdown'
                }
                for alert in alerts:
                    print(alert)
                    payload['text'] = alert
                    result = http.safe_urlopen(webhook_url, method='POST', data=payload)
                    time.sleep(1)

        return result
