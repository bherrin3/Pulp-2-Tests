# coding=utf-8
"""Test actions over repositories with rich and weak dependencies."""
import unittest
from urllib.parse import urljoin

from packaging.version import Version
from pulp_smash import api, cli, config, utils
from pulp_smash.pulp2.constants import REPOSITORY_PATH
from pulp_smash.pulp2.utils import (
    publish_repo,
    search_units,
    sync_repo,
    upload_import_unit,
)

from pulp_2_tests.constants import (
    RPM_RICH_WEAK,
    RPM_RICH_WEAK_FEED_URL,
    RPM2_RICH_WEAK_DATA,
    SRPM_RICH_WEAK_FEED_URL,
)
from pulp_2_tests.tests.rpm.api_v2.utils import gen_distributor, gen_repo
from pulp_2_tests.tests.rpm.utils import (
    gen_yum_config_file,
    rpm_rich_weak_dependencies,
)
from pulp_2_tests.tests.rpm.utils import set_up_module as setUpModule  # pylint:disable=unused-import


class ModularCopyRecursiveUnitsTestCase(unittest.TestCase):
    """Test copy units for a repository rich/weak dependencies.

    This test targets the following issues:

    * `Pulp Smash #1090 <https://github.com/PulpQE/pulp-smash/issues/1090>`_.
    * `Pulp Smash #1107 <https://github.com/PulpQE/pulp-smash/issues/1107>`_.
    * `Pulp #4152 <https://pulp.plan.io/issues/4152>`_
    * `Pulp #4269 <https://pulp.plan.io/issues/4269>`_
    * `Pulp #4375 <https://pulp.plan.io/issues/4375>`_

    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        if cls.cfg.pulp_version < Version('2.18'):
            raise unittest.SkipTest('This test requires Pulp 2.18 or newer.')
        cls.client = api.Client(cls.cfg, api.json_handler)

    def test_recursive(self):
        """Test recursive copy for a repository with rich/weak dependencies.

        See :meth:`do_test`."
        """
        repo = self.do_test(True, False)
        dst_unit_ids = [
            unit['metadata']['name'] for unit in
            search_units(self.cfg, repo, {'type_ids': ['modular']})
        ]
        self.assertEqual(
            len(dst_unit_ids),
            RPM2_RICH_WEAK_DATA['total_installed_packages'],
            dst_unit_ids
        )

    def test_recursive_conservative(self):
        """Test recursive, conservative copy for rich/weak dependencies.

        See :meth:`do_test`."
        """
        repo = self.do_test(True, True)
        dst_unit_ids = [
            unit['metadata']['name'] for unit in
            search_units(self.cfg, repo, {'type_ids': ['modular']})
        ]
        self.assertEqual(
            len(dst_unit_ids),
            RPM2_RICH_WEAK_DATA['total_installed_packages'],
            dst_unit_ids
        )

    def test_non_recursive(self):
        """Test simple copy for a repository with rich/weak dependencies.

        See :meth:`do_test`."
        """
        repo = self.do_test(False, False)
        dst_unit_ids = [
            unit['metadata']['name'] for unit in
            search_units(self.cfg, repo, {'type_ids': ['modular']})
        ]
        self.assertEqual(len(dst_unit_ids), 1, dst_unit_ids)

    def do_test(self, recursive, recursive_conservative):
        """Copy of units for a repository with rich/weak dependencies."""
        repos = []
        body = gen_repo(
            importer_config={'feed': RPM_RICH_WEAK_FEED_URL},
            distributors=[gen_distributor()]
        )
        repos.append(self.client.post(REPOSITORY_PATH, body))
        self.addCleanup(self.client.delete, repos[0]['_href'])
        sync_repo(self.cfg, repos[0])
        repos.append(self.client.post(REPOSITORY_PATH, gen_repo()))
        self.addCleanup(self.client.delete, repos[1]['_href'])

        # Pulp 2.18.1 introduced a new flag `recursive_conservative`.
        # If true, units are copied together with their
        # dependencies, unless those are already satisfied by the content in
        # the target repository.
        override_config = {'recursive': recursive}
        if self.cfg.pulp_version >= Version('2.18.1'):
            override_config.update(
                {'recursive_conservative': recursive_conservative}
            )
        self.client.post(urljoin(repos[1]['_href'], 'actions/associate/'), {
            'source_repo_id': repos[0]['id'],
            'override_config': override_config,
            'criteria': {
                'filters': {'unit': {'name': RPM2_RICH_WEAK_DATA['name']}},
                'type_ids': ['modular'],
            },
        })
        return self.client.get(repos[1]['_href'], params={'details': True})
