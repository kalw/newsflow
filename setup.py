import ez_setup
ez_setup.use_setuptools()

from setuptools import setup

setup(name='newsflow',
      version='1.1',
      packages=['newsflow'],
      scripts=[
        'scripts/newsflow-www',
        'scripts/newsflow-cron',
        'scripts/newsflow-producer-scraper',
        'scripts/newsflow-consumer-download',
        'scripts/newsflow-consumer-index',
      ],
      dependency_links=[
        'http://github.com/synack/newsflow/downloads',
      ],
      install_requires=[
        'yenc>=0.3',
        'simplejson>=2.0.9',
        'redis>=2.0.0',
        'bottle>=0.8.3',
        'Jinja2>=2.1.1',
      ])
