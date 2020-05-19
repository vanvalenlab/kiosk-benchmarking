# Copyright 2016-2020 The Van Valen Lab at the California Institute of
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
"""Manager class used to create and manage jobs"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import logging
import os
import timeit
import uuid

from google.cloud import storage as google_storage
from twisted.internet import defer, reactor
from twisted.web.client import HTTPConnectionPool

from benchmarking.job import Job
from benchmarking.utils import iter_image_files, sleep
from benchmarking import settings

from benchmarking.cost import CostGetter


class JobManager(object):
    """Manages many DeepCell Kiosk jobs.

    Args:
        host (str): public IP address of the DeepCell Kiosk cluster.
        model (str): model name and version, e.g. "model_name:version".
        upload_prefix (str): upload all files to this folder in the bucket.
        refresh_rate (int): how often the manager checks the status, in seconds.
        update_interval (int): how often each job its statuses, in seconds.
        expire_time (int): time until finished jobs are expired, in seconds.
        start_delay (int): delay between each job, in seconds.
    """

    def __init__(self, host, model, **kwargs):
        self.logger = logging.getLogger(str(self.__class__.__name__))
        self.created_at = timeit.default_timer()
        self.all_jobs = []

        host = str(host)
        if not any(host.startswith(x) for x in ('http://', 'https://')):
            host = 'http://{}'.format(host)

        self.host = host

        try:
            model_name, model_version = str(model).split(':')
        except Exception as err:
            self.logger.error('Invalid model name, must be of the form '
                              '"ModelName:Version", for example "model:0".')
            raise err

        self.model_name = model_name
        self.model_version = model_version

        data_scale = str(kwargs.get('data_scale', ''))
        if data_scale:
            try:
                data_scale = float(data_scale)
            except ValueError:
                raise ValueError('data_scale must be a number.')
        self.data_scale = data_scale

        data_label = str(kwargs.get('data_label', ''))
        if data_label:
            try:
                data_label = int(data_label)
            except ValueError:
                raise ValueError('data_label must be an integer.')
        self.data_label = data_label

        self.job_type = kwargs.get('job_type', 'segmentation')
        self.preprocess = kwargs.get('preprocess', '')
        self.postprocess = kwargs.get('postprocess', '')
        self.upload_prefix = kwargs.get('upload_prefix', 'uploads')
        self.refresh_rate = int(kwargs.get('refresh_rate', 10))
        self.update_interval = kwargs.get('update_interval', 10)
        self.expire_time = kwargs.get('expire_time', 3600)
        self.start_delay = kwargs.get('start_delay', 0.1)

        # initializing cost estimation workflow
        self.cost_getter = CostGetter()

        self.sleep = sleep  # allow monkey-patch

        # twisted configuration
        self.pool = HTTPConnectionPool(reactor, persistent=True)
        self.pool.maxPersistentPerHost = settings.CONCURRENT_REQUESTS_PER_HOST
        self.pool.retryAutomatically = False

    def upload_file(self, filepath, acl='publicRead',
                    hash_filename=True, prefix=None):
        prefix = self.upload_prefix if prefix is None else prefix
        start = timeit.default_timer()
        storage_client = google_storage.Client()

        self.logger.debug('Uploading %s.', filepath)
        if hash_filename:
            _, ext = os.path.splitext(filepath)
            dest = '{}{}'.format(uuid.uuid4().hex, ext)
        else:
            dest = os.path.basename(filepath)

        bucket = storage_client.get_bucket(settings.STORAGE_BUCKET)
        blob = bucket.blob(os.path.join(prefix, dest))
        blob.upload_from_filename(filepath, predefined_acl=acl)
        self.logger.debug('Uploaded %s to %s in %s seconds.',
                          filepath, dest, timeit.default_timer() - start)
        return dest

    def make_job(self, filepath, original_name=None):
        original_name = original_name if original_name else filepath
        return Job(filepath=filepath,
                   host=self.host,
                   model_name=self.model_name,
                   model_version=self.model_version,
                   job_type=self.job_type,
                   data_scale=self.data_scale,
                   data_label=self.data_label,
                   postprocess=self.postprocess,
                   upload_prefix=self.upload_prefix,
                   original_name=original_name,
                   update_interval=self.update_interval,
                   expire_time=self.expire_time,
                   pool=self.pool)

    def get_completed_job_count(self):
        created, complete, failed, expired = 0, 0, 0, 0

        statuses = {}

        for j in self.all_jobs:
            expired += int(j.is_expired)  # true mark of being done
            complete += int(j.is_summarized)
            created += int(j.job_id is not None)

            if j.status is not None:
                if j.status not in statuses:
                    statuses[j.status] = 1
                else:
                    statuses[j.status] += 1

            if j.failed:
                j.restart(delay=self.start_delay * failed)

            # # TODO: patched! "done" jobs can get stranded before summarization
            # if j.status == 'done' and not j.is_summarized:
            #     j.summarize()
            #
            # # TODO: patched! sometimes jobs don't get expired?
            # elif j.status == 'done' and j.is_summarized and not j.is_expired:
            #     j.expire()

        self.logger.info('%s created; %s finished; %s summarized; '
                         '%s; %s jobs total', created, expired, complete,
                         '; '.join('%s %s' % (v, k)
                                   for k, v in statuses.items()),
                         len(self.all_jobs))

        if len(self.all_jobs) - expired <= 25:
            for j in self.all_jobs:
                if not j.is_expired:
                    self.logger.info('Waiting on key `%s` with status %s',
                                     j.job_id, j.status)

        return expired

    @defer.inlineCallbacks
    def _stop(self):
        yield reactor.stop()  # pylint: disable=no-member

    @defer.inlineCallbacks
    def check_job_status(self):
        complete = -1  # initialize comparison value

        while complete != len(self.all_jobs):
            yield self.sleep(self.refresh_rate)

            complete = self.get_completed_job_count()  # synchronous

        self.summarize()  # synchronous

        yield self._stop()

    def summarize(self):
        time_elapsed = timeit.default_timer() - self.created_at
        self.logger.info('Finished %s jobs in %s seconds.',
                         len(self.all_jobs), time_elapsed)

        # add cost and timing data to json output
        try:
            cpu_cost, gpu_cost, total_cost = self.cost_getter.finish()
        except Exception as err:
            self.logger.error('Encountered %s while getting cost data: %s',
                              type(err).__name__, err)
            cpu_cost, gpu_cost, total_cost = '', '', ''

        jsondata = {
            'cpu_node_cost': cpu_cost,
            'gpu_node_cost': gpu_cost,
            'total_node_and_networking_costs': total_cost,
            'start_delay': self.start_delay,
            'num_jobs': len(self.all_jobs),
            'time_elapsed': time_elapsed,
            'job_data': [j.json() for j in self.all_jobs]
        }

        output_filepath = os.path.join(
            settings.OUTPUT_DIR,
            '{}gpu_{}delay_{}jobs_{}.json'.format(
                settings.NUM_GPUS, self.start_delay,
                len(self.all_jobs), uuid.uuid4().hex))

        with open(output_filepath, 'w') as jsonfile:
            json.dump(jsondata, jsonfile, indent=4)

            self.logger.info('Wrote job data as JSON to %s.', output_filepath)

        try:
            _ = self.upload_file(output_filepath,
                                 hash_filename=False,
                                 prefix='output')
        except Exception as err:  # pylint: disable=broad-except
            self.logger.error('Could not upload output file to bucket. '
                              'Copy this file from the docker container to '
                              'keep the data.')

    def run(self, *args, **kwargs):
        raise NotImplementedError


class BenchmarkingJobManager(JobManager):
    # pylint: disable=arguments-differ

    @defer.inlineCallbacks
    def run(self, filepath, count, upload=False):
        self.logger.info('Benchmarking %s jobs of file `%s`', count, filepath)

        for i in range(count):

            if upload:
                dest = self.upload_file(filepath, hash_filename=False)
                job = self.make_job(dest, original_name=filepath)
            else:
                job = self.make_job(filepath)

            self.all_jobs.append(job)

            # stagger the delay seconds; if upload it will be staggered already
            job.start(delay=self.start_delay * i * int(not upload))

            yield self.sleep(self.start_delay * upload)

            if upload:
                self.get_completed_job_count()  # log during uploading

        yield self.check_job_status()


class BatchProcessingJobManager(JobManager):
    # pylint: disable=arguments-differ

    @defer.inlineCallbacks
    def run(self, filepath):
        self.logger.info('Benchmarking all image/zip files in `%s`', filepath)

        for i, f in enumerate(iter_image_files(filepath)):

            dest = self.upload_file(f, hash_filename=True)

            job = self.make_job(dest, original_name=f)
            self.all_jobs.append(job)
            job.start(delay=self.start_delay * i)  # stagger the delay seconds

        yield self.check_job_status()
