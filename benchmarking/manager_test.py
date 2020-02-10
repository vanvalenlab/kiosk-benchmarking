# Copyright 2016-2019 The Van Valen Lab at the California Institute of
# Technology (Caltech), with support from the Paul Allen Family Foundation,
# Google, & National Institutes of Health (NIH) under Grant U24CA224309-01.
# All rights reserved.
#
# Licensed under a modified Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.github.com/vanvalenlab/kiosk-benchmarking/LICENSE
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
# ============================================================================
"""Tests for JobManager classes"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import random
import tempfile

from PIL import Image
from twisted.internet import defer

import pytest
import pytest_twisted

from benchmarking import manager
from benchmarking import settings


class TestJobManager(object):

    def test_init(self):
        mgr = manager.JobManager(
            host='localhost',
            model_name='m',
            model_version='0',
            data_scale='1',
            data_label='1')

        # test bad data_scale value
        with pytest.raises(ValueError):
            mgr = manager.JobManager(
                host='localhost',
                model_name='m',
                model_version='0',
                data_scale='one',
                data_label='1')
        # test bad data_label value
        with pytest.raises(ValueError):
            mgr = manager.JobManager(
                host='localhost',
                model_name='m',
                model_version='0',
                data_scale='1',
                data_label='1.3')

    def test_make_job(self):
        mgr = manager.JobManager(
            host='localhost',
            model_name='m',
            model_version='0',
            data_scale='1',
            data_label='0')

        j1 = mgr.make_job('test.png', original_name=None)
        j2 = mgr.make_job('test.png', original_name='test.png')

        assert j1.data_scale == mgr.data_scale == j2.data_scale
        assert j1.data_label == mgr.data_label == j2.data_label

        assert j1.json() == j2.json()

    def test_get_completed_job_count(self):
        mgr = manager.JobManager(
            host='localhost',
            model_name='m',
            model_version='0')

        j1 = mgr.make_job('test.png', original_name=None)
        j2 = mgr.make_job('test.png', original_name='test.png')

        mgr.all_jobs = [j1, j2]

        j1.status = 'new'
        j2.status = 'new'
        assert mgr.get_completed_job_count() == 0

        j1.status = 'done'
        j2.status = 'failed'
        assert mgr.get_completed_job_count() == 0

        def fake_restart(delay):
            return None

        j1.failed = True
        j1.restart = fake_restart
        j1.is_expired = True
        assert mgr.get_completed_job_count() == 1

    def test_summarize(self):

        # pylint: disable=unused-argument
        def fake_upload_file(filepath, hash_filename, prefix):
            return filepath

        def fake_upload_file_bad(filepath, hash_filename, prefix):
            return 1 / 0

        with tempfile.TemporaryDirectory() as tempdir:
            settings.OUTPUT_DIR = tempdir

            mgr = manager.JobManager(
                host='localhost',
                model_name='m',
                model_version='0')

            # monkey-patches for testing
            mgr.cost_getter.finish = lambda: (1, 2, 3)
            mgr.upload_file = fake_upload_file
            mgr.summarize()

            # test Exceptions
            mgr.cost_getter.finish = lambda: 0 / 1
            mgr.upload_file = fake_upload_file_bad
            mgr.summarize()

    @pytest_twisted.inlineCallbacks
    def test_check_job_status(self):
        mgr = manager.JobManager(
            host='localhost',
            model_name='m',
            model_version='0',
            refresh_rate=0)

        mgr.all_jobs = list(range(5))

        global _is_stopped
        _is_stopped = False

        @pytest_twisted.inlineCallbacks
        def dummy_stop():
            global _is_stopped
            _is_stopped = True
            yield defer.returnValue(_is_stopped)

        global _status_counter
        _status_counter = 0

        def get_completed_job_count():
            global _status_counter
            _status_counter += 1
            return _status_counter

        mgr.get_completed_job_count = get_completed_job_count
        mgr._stop = dummy_stop
        mgr.summarize = lambda: True

        _ = yield mgr.check_job_status()
        assert _status_counter == len(mgr.all_jobs)
        assert _is_stopped


class TestBenchmarkingJobManager(object):

    def test_run(self):
        mgr = manager.BenchmarkingJobManager(
            host='localhost',
            model_name='m',
            model_version='0')

        # pylint: disable=unused-argument
        def dummy_upload_file(filepath, **kwargs):
            return filepath

        def dummy_start(delay):
            return True

        def make_job(*args, **kwargs):
            m = manager.BatchProcessingJobManager(
                host='localhost',
                model_name='m',
                model_version='0')

            j = m.make_job(*args, **kwargs)
            j.start = dummy_start
            return j

        mgr.check_job_status = lambda: True
        mgr.upload_file = dummy_upload_file
        mgr.make_job = make_job
        mgr.sleep = lambda x: True
        mgr.get_completed_job_count = lambda: True

        with tempfile.TemporaryDirectory() as tempdir:
            valid_image = os.path.join(tempdir, 'image.png')
            img = Image.new('RGB', (800, 1280), (255, 255, 255))
            img.save(valid_image, 'PNG')

            list(mgr.run(valid_image, count=2, upload=True))
            list(mgr.run(valid_image, count=2, upload=False))


class TestBatchProcessingJobManager(object):

    def test_run(self):
        mgr = manager.BatchProcessingJobManager(
            host='localhost',
            model_name='m',
            model_version='0')

        # pylint: disable=unused-argument
        def dummy_upload_file(filepath, **kwargs):
            return filepath

        def dummy_start(delay):
            return True

        def make_job(*args, **kwargs):
            m = manager.BatchProcessingJobManager(
                host='localhost',
                model_name='m',
                model_version='0')

            j = m.make_job(*args, **kwargs)
            j.start = dummy_start
            return j

        mgr.check_job_status = lambda: True
        mgr.upload_file = dummy_upload_file
        mgr.make_job = make_job

        with tempfile.TemporaryDirectory() as tempdir:
            num = random.randint(1, 5)
            imagename = lambda x: 'image%s.png' % x

            valid_images = []
            for i in range(num):
                valid_image = os.path.join(tempdir, imagename(i))
                img = Image.new('RGB', (800, 1280), (255, 255, 255))
                img.save(valid_image, 'PNG')
                valid_images.append(valid_image)

            list(mgr.run(tempdir))
