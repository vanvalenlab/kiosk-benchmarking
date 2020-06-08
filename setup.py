# Copyright 2016-2020 The Van Valen Lab at the California Institute of
# Technology (Caltech), with support from the Paul Allen Family Foundation,
# Google, & National Institutes of Health (NIH) under Grant U24CA224309-01.
# All rights reserved.
#
# Licensed under a modified Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.github.com/vanvalenlab/kiosk-client/LICENSE
#
# The Work provided may be used for non-commercial academic purposes only.
# For any other use of the Work, including commercial use, please contact:
# vanvalenlab@gmail.com
#
# Neither the name of Caltech nor the names of its contributors may be used
# to endorse or promote products derived from this software without specific
# prior written permission.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
from setuptools import setup
from setuptools import find_packages

setup(name='Kiosk_Client',
      version='0.6.0',
      description='ClI client for the DeepCell Kiosk.',
      author='Van Valen Lab',
      author_email='vanvalenlab@gmail.com',
      url='https://github.com/vanvalenlab/kiosk-client',
      download_url='https://github.com/vanvalenlab/'
                   'kiosk-client/tarball/0.6.0',
      license='LICENSE',
      install_requires=['boto3',
                        'google-cloud-storage',
                        'Pillow',
                        'python-decouple',
                        'python-dateutil==2.8.0',
                        'treq==20.3.0',
                        'twisted>=20.3.0'],
      extras_require={
          'tests': ['pytest',
                    'pytest-twisted',
                    'pytest-pep8',
                    'pytest-cov',
                    'requests-mock',
                    'attrs>=19.2.0'],
      },
      packages=find_packages())
