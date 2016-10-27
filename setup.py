#!/usr/bin/env python
"""
sentry-telegram
============

An extension for `Sentry <https://getsentry.com>`_ which posts notifications
to `Telegram <https://slack.com>`_.

:copyright: (c) 2015 by the Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""
from setuptools import setup, find_packages


install_requires = [
    'sentry>=7.0.0',
]

tests_require = [
    'exam',
    'flake8>=2.0,<2.1',
    'responses',
]

setup(
    name='sentry-telegram',
    version='0.0.1.dev0',
    author='Matt Robenolt',
    author_email='matt@ydekproductons.com',
    url='https://github.com/getsentry/sentry-slack',
    description='A Sentry extension which posts notifications to Slack (https://slack.com/).',
    long_description=open('README.rst').read(),
    license='BSD',
    package_dir={'': 'src'},
    packages=find_packages('src'),
    zip_safe=False,
    install_requires=install_requires,
    extras_require={
        'tests': tests_require,
    },
    include_package_data=True,
    entry_points={
        'sentry.apps': [
            'telegram = sentry_telegram',
        ],
        'sentry.plugins': [
            'telegram = sentry_telegram.plugin:TelegramPlugin',
        ]
    },
    classifiers=[
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Operating System :: OS Independent',
        'Topic :: Software Development'
    ],
)
