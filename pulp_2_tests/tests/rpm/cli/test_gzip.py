# coding=utf-8
"""Tests for Pulp's download policies, such as "background" and "on demand".

Beware that the test cases for the "on demand" download policy will fail if
Pulp's Squid server is not configured to return an appropriate hostname or IP
when performing redirection.
"""
import hashlib
import unittest
from urllib.parse import urljoin

from packaging.version import Version
from pulp_smash import api, cli, config, selectors, utils
from pulp_smash.pulp2.constants import REPOSITORY_PATH
from pulp_smash.pulp2.utils import (
    BaseAPITestCase,
    reset_pulp,
    reset_squid,
    sync_repo,
)

from pulp_2_tests.constants import (
    RPM,
    RPM_DATA,
    RPM_UNSIGNED_FEED_URL,
    RPM_UNSIGNED_URL,
    RPM_KICKSTART_FEED_URL,
)
from pulp_2_tests.tests.rpm.api_v2.utils import (
    gen_distributor,
    gen_repo,
)


class GZipTestCase(unittest.TestCase):
    """Test"""

    @classmethod
    def setUpClass(cls):
        """Create class-wide config."""
        cls.cfg = config.get_config()
        if cls.cfg.pulp_version < Version('2.19'):
            raise unittest.SkipTest('This test requires Pulp 2.19 or newer.')

    def test_do(self):
        """Test"""
        # Create, sync and publish a repository.
        # resources = set()
        # body = gen_repo()
        # body['importer_config']['download_policy'] = 'on_demand'
        # body['importer_config']['feed'] = 'https://repos.fedorapeople.org/pulp/pulp/fixtures/rpm-kickstart/'
        # distributor = gen_distributor()
        # distributor['auto_publish'] = True
        # distributor['distributor_config']['relative_url'] = body['id']
        # body['distributors'] = [distributor]
        # repo = api.Client(self.cfg, api.json_handler).post(REPOSITORY_PATH, body)
        # sync_repo(self.cfg, repo)

        GZIP_FILE = "https://localhost/pulp/repos/pulp/pulp/fixtures/rpm-kickstart/images/pxeboot/vmlinuz"

        # Download the file
        client = cli.Client(self.cfg)
        gzip = client.run(('mktemp','--suffix=.gz')).stdout.strip()
        self.addCleanup(client.run, ('rm', gzip))
        client.run(('curl', '--output', gzip, GZIP_FILE))

        # Run gzip test
        response = client.run(('gunzip', gzip)) 

        
        for stream in (response.stdout, response.stderr):
            self.assertIn('gzip', stream)
