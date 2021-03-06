# -*- coding: utf-8 -*-

import os
import sys
import signal
import tempfile
import testing.redis
from mock import patch
from redis import Redis
from time import sleep
from shutil import rmtree

if sys.version_info < (2, 7):
    import unittest2 as unittest
else:
    import unittest


class TestRedisServer(unittest.TestCase):
    def test_basic(self):
        # start redis server
        redis = testing.redis.RedisServer()
        self.assertIsNotNone(redis)
        self.assertEqual(redis.dsn(),
                         dict(host='127.0.0.1', port=redis.redis_conf['port'], db=0))

        # connect to redis
        r = Redis(**redis.dsn())
        self.assertIsNotNone(r)

        pid = redis.server_pid
        self.assertTrue(redis.is_alive())

        # shutting down
        redis.stop()
        sleep(1)

        self.assertFalse(redis.is_alive())
        with self.assertRaises(OSError):
            os.kill(pid, 0)  # process is down

    def test_stop(self):
        # start redis server
        redis = testing.redis.RedisServer()
        self.assertTrue(os.path.exists(redis.base_dir))
        self.assertTrue(redis.is_alive())  # process is alive

        # call stop()
        redis.stop()
        self.assertFalse(os.path.exists(redis.base_dir))
        self.assertFalse(redis.is_alive())  # process is down

        # call stop() again
        redis.stop()
        self.assertFalse(os.path.exists(redis.base_dir))
        self.assertFalse(redis.is_alive())  # process is down

        # delete redis object after stop()
        del redis

    def test_with_redis(self):
        with testing.redis.RedisServer() as redis:
            self.assertIsNotNone(redis)

            # connect to redis
            r = Redis(**redis.dsn())
            self.assertIsNotNone(r)

            self.assertTrue(redis.is_alive())  # process is alive

        self.assertFalse(redis.is_alive())  # process is down

    def test_multiple_redis(self):
        redis1 = testing.redis.RedisServer()
        redis2 = testing.redis.RedisServer()
        self.assertNotEqual(redis1.server_pid, redis2.server_pid)

        self.assertTrue(redis1.is_alive())  # process is alive
        self.assertTrue(redis2.is_alive())  # process is alive

    @patch("testing.redis.get_path_of")
    def test_redis_is_not_found(self, get_path_of):
        get_path_of.return_value = None

        with self.assertRaises(RuntimeError):
            testing.redis.RedisServer()

    def test_fork(self):
        redis = testing.redis.RedisServer()
        if os.fork() == 0:
            del redis
            redis = None
            os.kill(os.getpid(), signal.SIGTERM)  # exit tests FORCELY
        else:
            os.wait()
            sleep(1)
            self.assertTrue(redis.is_alive())  # process is alive (delete mysqld obj in child does not effect)

    def test_stop_on_child_process(self):
        redis = testing.redis.RedisServer()
        if os.fork() == 0:
            redis.stop()
            os.kill(redis.server_pid, 0)  # process is alive (calling stop() is ignored)
            os.kill(os.getpid(), signal.SIGTERM)  # exit tests FORCELY
        else:
            os.wait()
            sleep(1)
            self.assertTrue(redis.is_alive())  # process is alive (delete mysqld obj in child does not effect)

    def test_copy_data_from(self):
        try:
            tmpdir = tempfile.mkdtemp()

            # create new database
            with testing.redis.RedisServer(base_dir=tmpdir, redis_conf={'save': '900 1'}) as redis:
                r = Redis(**redis.dsn())
                r.set('scott', '1')
                r.set('tiger', '2')

            # create another database from first one
            data_dir = os.path.join(tmpdir, 'data')
            with testing.redis.RedisServer(copy_data_from=data_dir) as redis:
                r = Redis(**redis.dsn())

                self.assertEqual('1', r.get('scott').decode('utf-8'))
                self.assertEqual('2', r.get('tiger').decode('utf-8'))
        finally:
            rmtree(tmpdir)

    def test_skipIfNotInstalled_found(self):
        @testing.redis.skipIfNotInstalled
        def testcase():
            pass

        self.assertEqual(False, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(False, hasattr(testcase, '__unittest_skip_why__'))

    @patch("testing.redis.get_path_of")
    def test_skipIfNotInstalled_notfound(self, get_path_of):
        get_path_of.return_value = None

        @testing.redis.skipIfNotInstalled
        def testcase():
            pass

        self.assertEqual(True, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(True, hasattr(testcase, '__unittest_skip_why__'))
        self.assertEqual(True, testcase.__unittest_skip__)
        self.assertEqual("redis-server not found", testcase.__unittest_skip_why__)

    def test_skipIfNotInstalled_with_args_found(self):
        redis_server = testing.redis.get_path_of('redis-server')

        @testing.redis.skipIfNotInstalled(redis_server)
        def testcase():
            pass

        self.assertEqual(False, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(False, hasattr(testcase, '__unittest_skip_why__'))

    def test_skipIfNotInstalled_with_args_notfound(self):
        @testing.redis.skipIfNotInstalled("/path/to/anywhere")
        def testcase():
            pass

        self.assertEqual(True, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(True, hasattr(testcase, '__unittest_skip_why__'))
        self.assertEqual(True, testcase.__unittest_skip__)
        self.assertEqual("redis-server not found", testcase.__unittest_skip_why__)

    def test_skipIfNotFound_found(self):
        @testing.redis.skipIfNotFound
        def testcase():
            pass

        self.assertEqual(False, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(False, hasattr(testcase, '__unittest_skip_why__'))

    @patch("testing.redis.get_path_of")
    def test_skipIfNotFound_notfound(self, get_path_of):
        get_path_of.return_value = None

        @testing.redis.skipIfNotFound
        def testcase():
            pass

        self.assertEqual(True, hasattr(testcase, '__unittest_skip__'))
        self.assertEqual(True, hasattr(testcase, '__unittest_skip_why__'))
        self.assertEqual(True, testcase.__unittest_skip__)
        self.assertEqual("redis-server not found", testcase.__unittest_skip_why__)

    def test_RedisServerFactory(self):
        RedisServer = testing.redis.RedisServerFactory(cache_initialized_db=True)
        with RedisServer() as pgsql1:
            self.assertTrue(pgsql1.settings['copy_data_from'])
            copy_data_from1 = pgsql1.settings['copy_data_from']
            self.assertTrue(os.path.exists(copy_data_from1))
        with RedisServer() as pgsql2:
            self.assertEqual(copy_data_from1, pgsql2.settings['copy_data_from'])
        RedisServer.clear_cache()
        self.assertFalse(os.path.exists(copy_data_from1))

    def test_RedisServerFactory_with_initialized_handler(self):
        def handler(redis):
            r = Redis(**redis.dsn())
            r.config_set('save', '900 1')
            r.set('scott', '1')
            r.set('tiger', '2')

        RedisServer = testing.redis.RedisServerFactory(cache_initialized_db=True,
                                                       on_initialized=handler)
        try:
            with RedisServer() as redis:
                r = Redis(**redis.dsn())

                self.assertEqual('1', r.get('scott').decode('utf-8'))
                self.assertEqual('2', r.get('tiger').decode('utf-8'))
        finally:
            RedisServer.clear_cache()
