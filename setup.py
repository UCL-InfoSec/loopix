#!/usr/bin/env python

from setuptools import setup

import loopix

setup(name='loopix',
      version=loopix.VERSION,
      description='The Loopix mix system.',
      author='Ania Piotrowska (UCL Information Security)',
      author_email='anna.piotrowska.15@ucl.ac.uk',
      url=r'https://pypi.python.org/pypi/loopix/',
      packages=['loopix'],
      license="2-clause BSD",
      long_description="""The Loopix mix system for anonymous communications.""",
      # setup_requires=["pytest >= 2.6.4"],
      install_requires=[
            #"future >= 0.14.3",
            #"pytest >= 2.6.4",
            "twisted >= 15.5.0",
            "msgpack-python >= 0.4.6",
            "petlib >= 0.0.34"
      ],
      zip_safe=False,
)