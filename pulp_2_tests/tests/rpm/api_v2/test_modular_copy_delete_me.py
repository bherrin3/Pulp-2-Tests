# coding=utf-8
"""Test cases that copy content units."""
import os
import time
import unittest
from urllib.parse import urljoin

from packaging.version import Version
from pulp_smash import api, cli, config, selectors, utils
from pulp_smash.pulp2.constants import REPOSITORY_PATH, ORPHANS_PATH
from pulp_smash.pulp2.utils import (
    publish_repo,
    search_units,
    sync_repo,
    upload_import_unit,
)

from pulp_2_tests.constants import (
    RPM_NAMESPACES,
    RPM_SIGNED_URL,
    RPM_UNSIGNED_FEED_URL,
    RPM_UPDATED_INFO_FEED_URL,
    RPM_WITH_OLD_MODULAR_VERSION_URL,
    RPM_YUM_METADATA_FILE,
    RPM_WITH_MODULES_FEED_URL,
)
from pulp_2_tests.tests.rpm.api_v2.utils import (
    gen_distributor,
    gen_repo,
    get_repodata_repomd_xml,
)
from pulp_2_tests.tests.rpm.utils import set_up_module as setUpModule  # pylint:disable=unused-import

_PATH = '/var/lib/pulp/published/yum/https/repos/'

@unittest.skip("need to investigate if this is a valid case")
class CopyErrataRecursiveTestCase(unittest.TestCase):
    """Test that recursive copy of erratas copies RPM packages."""

    def test_all(self):
        """Test that recursive copy of erratas copies RPM packages.

        This test targets the following issues:

        * `Pulp Smash #769 <https://github.com/PulpQE/pulp-smash/issues/769>`_
        * `Pulp #3004 <https://pulp.plan.io/issues/3004>`_

        Do the following:

        1. Create and sync a repository with errata, and RPM packages.
        2. Create second repository.
        3. Copy units from from first repository to second repository
           using ``recursive`` as true, and filter  ``type_id`` as
           ``erratum``.
        4. Assert that RPM packages were copied.
        """
        cfg = config.get_config()
        if not selectors.bug_is_fixed(3004, cfg.pulp_version):
            self.skipTest('https://pulp.plan.io/issues/3004')

        repos = []
        client = api.Client(cfg, api.json_handler)
        body = gen_repo()
        body['importer_config']['feed'] = RPM_WITH_MODULES_FEED_URL
        body['distributors'] = [gen_distributor()]
        repos.append(client.post(REPOSITORY_PATH, body))
        self.addCleanup(client.delete, repos[0]['_href'])
        sync_repo(cfg, repos[0])

        # Create a second repository.
        repos.append(client.post(REPOSITORY_PATH, gen_repo()))
        self.addCleanup(client.delete, repos[1]['_href'])

        # Copy data to second repository.
        client.post(urljoin(repos[1]['_href'], 'actions/associate/'), {
            'source_repo_id': repos[0]['id'],
            'override_config': {'recursive': True},
            'criteria': {'filters': {}, 'type_ids': ['rpm']},
        })

        # Assert that RPM packages were copied.
        units = search_units(cfg, repos[1], {'type_ids': ['rpm']})
        self.assertGreater(len(units), 0)

class CopyConservativeTestCase(unittest.TestCase):
    """Test ``recursive`` and ``recursive_conservative`` flags during copy.

    RPM packages used in this test case::

        duck
        └── walrus

    duck has dependencies: walrus RPM packages.

    walrus package has 2 different versions:  ``0.71`` and ``5.21``.

    duck package has 3 different versions:  ``0.6``,``0.7`` and ``0.8``.

    This test targets the following issues:

    * `Pulp #4152 <https://pulp.plan.io/issues/3740>`_
    * `Pulp #4269 <https://pulp.plan.io/issues/4364>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        if cls.cfg.pulp_version < Version('2.19'):
            raise unittest.SkipTest('This test requires Pulp 2.19 or newer.')
        cls.client = api.Client(cls.cfg, api.json_handler)
        skipIt = False

    def test_recursive_noconservative_nodependency(self):
        """Recursive, non-conservative, and no old dependency.

        Do the following:

        1. Copy ``duck`` RPM package from repository A to B using:
           ``recursive`` as True, ``recursive_conservative`` as False, and no
           older version of walrus package is present on the repo B before
           the copy.
        2. Assert that total number of RPM of units copied is equal to ``5``,
           and the walrus package version is equal to ``5.21``.
        """
        repo = self.copy_units(True, False, False)
        versions = [
            unit['metadata']['version']
            for unit in search_units(self.cfg, repo, {'type_ids': ['rpm']})
            if unit['metadata']['name'] == 'walrus'
        ]
        self.assertEqual(len(versions), 1, versions)
        self.assertEqual(versions[0], '5.21', versions)

        dst_unit_ids = [
            unit['metadata']['name']
            for unit in search_units(self.cfg, repo, {'type_ids': ['rpm']})
        ]
        self.assertEqual(len(dst_unit_ids), 5, dst_unit_ids)

    def test_recursive_conservative_nodepdendency(self):
        """Recursive, conservative, and no old dependency.

        Do the following:

        1. Copy ``chimpanzee`` RPM package from repository A to B using:
           ``recursive`` as True, ``recursive_conservative`` as True, and no
           older version of walrus package is present on the repo B before
           the copy.
        2. Assert that total number of RPM of units copied is equal to ``5``,
           and the walrus package version is equal to ``5.21``.
        """
        repo = self.copy_units(True, True, False)
        versions = [
            unit['metadata']['version']
            for unit in search_units(self.cfg, repo, {'type_ids': ['rpm']})
            if unit['metadata']['name'] == 'walrus'
        ]
        self.assertEqual(len(versions), 1, versions)
        self.assertEqual(versions[0], '5.21', versions)

        dst_unit_ids = [
            unit['metadata']['name']
            for unit in search_units(self.cfg, repo, {'type_ids': ['rpm']})
        ]
        self.assertEqual(len(dst_unit_ids), 5, dst_unit_ids)

    @unittest.skip("need to investigate if this is a valid case")
    def test_recursive_conservative_dependency(self):
        """Recursive, conservative and with old dependency.

        Do the following:

        1. Copy ``chimpanzee`` RPM package from repository A to B using:
           ``recursive`` as True, ``recursive_conservative`` as True, and an
           older version of walrus package is present on the repo B before
           the copy.
        2. Assert that total number of RPM of units is equal to ``5``
           and the walrus package version is equal to ``0.71``.
        """
        repo = self.copy_units(True, True, True)
        versions = [
            unit['metadata']['version']
            for unit in search_units(self.cfg, repo, {'type_ids': ['rpm']})
            if unit['metadata']['name'] == 'walrus'
        ]
        self.assertEqual(len(versions), 1, versions)
        self.assertEqual(versions[0], '0.71', versions)

        dst_unit_ids = [
            unit['metadata']['name']
            for unit in search_units(self.cfg, repo, {'type_ids': ['rpm']})
        ]
        self.assertEqual(len(dst_unit_ids), 5, dst_unit_ids)

    @unittest.skip("need to investigate if this is a valid case")
    def test_norecursive_conservative_dependency(self):
        """Non-recursive, conservative, with old dependency.

        Do the following:

        1. Copy ``chimpanzee`` RPM package from repository A to B using:
           ``recursive`` as False, ``recursive_conservative`` as True, and
           an older version of walrus package is present on the repo B
           before the copy.
        2. Assert that total number of RPM of units is equal to ``5``,
           and the walrus package version is equal to ``0.71``.
        """
        repo = self.copy_units(False, True, True)
        versions = [
            unit['metadata']['version']
            for unit in search_units(self.cfg, repo, {'type_ids': ['rpm']})
            if unit['metadata']['name'] == 'walrus'
        ]
        self.assertEqual(len(versions), 1, versions)
        self.assertEqual(versions[0], '0.71', versions)

        dst_unit_ids = [
            unit['metadata']['name']
            for unit in search_units(self.cfg, repo, {'type_ids': ['rpm']})
        ]
        self.assertEqual(len(dst_unit_ids), 5, dst_unit_ids)

    def test_norecursive_noconservative_nodependency(self):
        """Non-recursive, non-conservative, and no old dependency.

        Do the following:

        1. Copy ``chimpanzee`` RPM package from repository A to B using:
           ``recursive`` as False, ``recursive_conservative`` as False, and no
           older version of walrus package is present on the repo B before
           the copy.
        2. Assert that total number of RPM of units copied is equal to ``1``.
        """
        repo = self.copy_units(False, False, False)
        dst_unit_ids = [
            unit['metadata']['name']
            for unit in search_units(self.cfg, repo, {'type_ids': ['rpm']})
        ]
        self.assertEqual(len(dst_unit_ids), 1, dst_unit_ids)

    def copy_units(self, recursive, recursive_conservative, old_dependency):
        """Copy units using ``recursive`` and  ``recursive_conservative``."""
        repos = []
        body = gen_repo(
            importer_config={'feed': RPM_WITH_MODULES_FEED_URL},
            distributors=[gen_distributor()]
        )
        repos.append(self.client.post(REPOSITORY_PATH, body))
        self.addCleanup(self.client.delete, repos[0]['_href'])
        sync_repo(self.cfg, repos[0])
        repos.append(self.client.post(REPOSITORY_PATH, gen_repo()))
        self.addCleanup(self.client.delete, repos[1]['_href'])

        # `old_dependency` will import an older version, `0.71` of walrus to
        # the destiny repostiory.
        if old_dependency:
            rpm = utils.http_get(RPM_WITH_OLD_MODULAR_VERSION_URL)
            upload_import_unit(
                self.cfg,
                rpm,
                {'unit_type_id': 'modular'}, repos[1]
            )
            units = search_units(self.cfg, repos[1], {'type_ids': ['rpm']})
            self.assertEqual(len(units), 1, units)

        self.client.post(urljoin(repos[1]['_href'], 'actions/associate/'), {
            'source_repo_id': repos[0]['id'],
            'override_config': {
                'recursive': recursive,
                'recursive_conservative': recursive_conservative,
            },
            'criteria': {
                'filters': {'unit': {'name': 'duck'}},
                'type_ids': ['rpm'],
            },
        })
        return self.client.get(repos[1]['_href'], params={'details': True})
