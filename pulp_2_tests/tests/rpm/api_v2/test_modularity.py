# coding=utf-8
"""Tests that perform actions over RPM modular repositories."""
import gzip
import io
import unittest
from urllib.parse import urljoin
from xml.etree import ElementTree

from packaging.version import Version
from pulp_smash import api, cli, config, selectors, utils
from pulp_smash.pulp2.constants import REPOSITORY_PATH
from pulp_smash.pulp2.utils import (
    publish_repo,
    search_units,
    sync_repo,
    upload_import_unit,
)

from pulp_2_tests.constants import (
    MODULE_FIXTURES_PACKAGES,
    MODULE_FIXTURES_PACKAGE_STREAM,
    RPM_NAMESPACES,
    RPM_UNSIGNED_FEED_COUNT,
    RPM_UNSIGNED_FEED_URL,
    RPM_WITH_MODULES_FEED_URL,
    RPM_WITH_MODULES_SHA1_FEED_URL,
    RPM_WITH_OLD_VERSION_URL,
)
from pulp_2_tests.tests.rpm.api_v2.utils import (
    gen_distributor,
    gen_repo,
    get_repodata,
    get_repodata_repomd_xml,
)
from pulp_2_tests.tests.rpm.utils import (
    check_issue_4405,
    gen_yum_config_file,
    os_support_modularity,
)
from pulp_2_tests.tests.rpm.utils import set_up_module


def setUpModule():  # pylint:disable=invalid-name
    """Possibly skip the tests in this module.

    Skip tests if `Pulp #4405 <https://pulp.plan.io/issues/4405>`_ affects us.
    """
    set_up_module()
    if check_issue_4405(config.get_config()):
        raise unittest.SkipTest('https://pulp.plan.io/issues/4405')

def tearDownModule():  # pylint:disable=invalid-name
    """Delete the orphans created by testing."""
    cli.Client(config.get_config()).run((
        'pulp-admin', 'orphan', 'remove', '--all'
    ))

class ManageModularContentTestCase(unittest.TestCase):
    """Manage modular content tests cases.

    Modules and RPM packages used in this test case::

    Modules:
    [walrus-0.71]
    └── walrus-0.71
    
    Dependent RPMs of the provided RPM from ``walrus-0.71``
    walrus-0.71
    └── whale
           ├── shark
           └── stork

    [walrus-5.21]
    └── walrus-5.21

    The RPM ``walrus-5.21`` has no dependencies.

    This test targets the following issue:

    `Pulp Smash #1122 <https://github.com/PulpQE/pulp-smash/issues/1122>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class wide variables."""
        cls.cfg = config.get_config()
        if cls.cfg.pulp_version < Version('2.17'):
            raise unittest.SkipTest('This test requires Pulp 2.17 or newer.')
        cls.client = api.Client(cls.cfg, api.json_handler)

    def test_copy_modulemd_nonrecursive_nonconservative(self):
        """Test copy of modulemd in RPM repository in non recursive mode."""
        criteria = {
            'filters': {'unit': {
                'name': MODULE_FIXTURES_PACKAGE_STREAM['name'],
                'stream': MODULE_FIXTURES_PACKAGE_STREAM['stream']
            }},
            'type_ids': ['modulemd'],
        }
        repo = self.copy_content_between_repos(False, criteria, False)
        self.assertEqual(
            repo['content_unit_counts']['modulemd'],
            1,
            repo['content_unit_counts']['modulemd']
        )
        self.assertEqual(
            repo['total_repository_units'],
            1,
            repo['total_repository_units']
        )
        self.assertNotIn('rpm', repo['content_unit_counts'])

    def test_copy_modulemd_recursive_nonconservative(self):
        """Test copy of modulemd in RPM repository in recursive mode."""
        criteria = {
            'filters': {'unit': {
                'name': MODULE_FIXTURES_PACKAGE_STREAM['name'],
                'stream': MODULE_FIXTURES_PACKAGE_STREAM['stream']
            }},
            'type_ids': ['modulemd'],
        }
        repo = self.copy_content_between_repos(True, criteria, False)
        self.assertEqual(repo['content_unit_counts']['modulemd'], 1)
        self.assertEqual(
            repo['content_unit_counts']['rpm'],
            MODULE_FIXTURES_PACKAGE_STREAM['rpm_count'],
            repo['content_unit_counts']['rpm']
        )
        self.assertEqual(
            repo['total_repository_units'],
            MODULE_FIXTURES_PACKAGE_STREAM['total_available_units'],
            repo['total_repository_units']
        )

    def test_copy_modulemd_nonrecursive_conservative(self):
        """Test copy of modulemd in RPM repository in non recursive mode."""
        criteria = {
            'filters': {'unit': {
                'name': MODULE_FIXTURES_PACKAGE_STREAM['name'],
                'stream': MODULE_FIXTURES_PACKAGE_STREAM['stream']
            }},
            'type_ids': ['modulemd'],
        }
        repo = self.copy_content_between_repos(False, criteria, True)
        self.assertEqual(
            repo['content_unit_counts']['rpm'],
            MODULE_FIXTURES_PACKAGE_STREAM['rpm_count'],
            repo['content_unit_counts']['rpm']
        )
        self.assertEqual(
            repo['total_repository_units'],
            MODULE_FIXTURES_PACKAGE_STREAM['total_available_units'],
            repo['total_repository_units']
        )

    def test_copy_modulemd_recursive_conservative(self):
        """Test copy of modulemd in RPM repository in recursive mode."""
        criteria = {
            'filters': {'unit': {
                'name': MODULE_FIXTURES_PACKAGE_STREAM['name'],
                'stream': MODULE_FIXTURES_PACKAGE_STREAM['stream']
            }},
            'type_ids': ['modulemd'],
        }
        repo = self.copy_content_between_repos(True, criteria, True)
        self.assertEqual(repo['content_unit_counts']['modulemd'], 1)
        self.assertEqual(
            repo['content_unit_counts']['rpm'],
            MODULE_FIXTURES_PACKAGE_STREAM['rpm_count'],
            repo['content_unit_counts']['rpm']
        )
        self.assertEqual(
            repo['total_repository_units'],
            MODULE_FIXTURES_PACKAGE_STREAM['total_available_units'],
            repo['total_repository_units']
        )

    def test_copy_modulemd_recursive_nonconservative_dependency(self):
        """Test copy of modulemd in RPM repository in recursive mode."""
        criteria = {
            'filters': {'unit': {
                'name': MODULE_FIXTURES_PACKAGE_STREAM['name'],
                'stream': MODULE_FIXTURES_PACKAGE_STREAM['stream']
            }},
            'type_ids': ['modulemd'],
        }
        repo = self.copy_content_between_repos(True, criteria, False, True)
        self.assertEqual(repo['content_unit_counts']['modulemd'], 1)
        self.assertEqual(
            repo['content_unit_counts']['rpm'],
            MODULE_FIXTURES_PACKAGE_STREAM['rpm_count'],
            repo['content_unit_counts']['rpm']
        )
        self.assertEqual(
            repo['total_repository_units'],
            MODULE_FIXTURES_PACKAGE_STREAM['total_available_units'],
            repo['total_repository_units']
        )

    def test_copy_modulemd_defaults(self):
        """Test copy of modulemd_defaults in RPM repository."""
        criteria = {
            'filters': {},
            'type_ids': ['modulemd_defaults'],
        }
        repo = self.copy_content_between_repos(True, criteria, False)
        self.assertEqual(
            repo['content_unit_counts']['modulemd_defaults'],
            3,
            repo['content_unit_counts'])
        self.assertEqual(
            repo['total_repository_units'],
            3,
            repo['total_repository_units']
        )
        self.assertNotIn('rpm', repo['content_unit_counts'])

    def test_remove_modulemd(self):
        """Test sync and remove modular RPM repository."""
        if not selectors.bug_is_fixed(3985, self.cfg.pulp_version):
            raise unittest.SkipTest('https://pulp.plan.io/issues/3985')
        repo_initial = self.create_sync_modular_repo()
        criteria = {
            'filters': {'unit': {
                'name': MODULE_FIXTURES_PACKAGE_STREAM['name'],
                'stream': MODULE_FIXTURES_PACKAGE_STREAM['stream']
            }},
            'type_ids': ['modulemd'],
        }
        repo = self.remove_module_from_repo(repo_initial, criteria)
        self.assertEqual(
            repo['content_unit_counts']['modulemd'],
            repo_initial['content_unit_counts']['modulemd'] - 1,
            repo['content_unit_counts'])
        # after removing a module 'X', the number of RPMS in the repo should
        # decrease by the number of RPMS present in 'X'.
        self.assertEqual(
            repo['content_unit_counts']['rpm'],
            repo_initial['content_unit_counts']['rpm'] - 1,
            repo['content_unit_counts'])
        self.assertIsNotNone(
            repo['last_unit_removed'],
            repo['last_unit_removed']
        )

    def test_remove_modulemd_defaults(self):
        """Test sync and remove modular RPM repository."""
        repo_initial = self.create_sync_modular_repo()
        criteria = {
            'filters': {},
            'type_ids': ['modulemd_defaults'],
        }
        repo = self.remove_module_from_repo(repo_initial, criteria)
        self.assertNotIn(
            'modulemd_defaults',
            repo['content_unit_counts'],
            repo['content_unit_counts'])

        self.assertEqual(
            repo['total_repository_units'],
            (repo_initial['total_repository_units'] -
             repo_initial['content_unit_counts']['modulemd_defaults']),
            repo['total_repository_units']
        )
        self.assertIsNotNone(
            repo['last_unit_removed'],
            repo['last_unit_removed']
        )

    def test_sync_publish_repo(self):
        """Test sync and publish modular RPM repository."""
        repo = self.create_sync_modular_repo()
        # Assert that `modulemd` and `modulemd_defaults` are present on the
        # repository.
        self.assertIsNotNone(repo['content_unit_counts']['modulemd'])
        self.assertIsNotNone(repo['content_unit_counts']['modulemd_defaults'])

        publish_repo(self.cfg, repo)

        get_repodata(
            self.cfg,
            repo['distributors'][0],
            'modules',
            api.safe_handler,
        )

    def copy_content_between_repos(self, recursive, criteria, recursive_conservative, old_dependency=False):
        """Create two repositories and copy content between them."""
        # repo1
        repo1 = self.create_sync_modular_repo()

        # repo2
        body = gen_repo()
        repo2 = self.client.post(REPOSITORY_PATH, body)
        self.addCleanup(self.client.delete, repo2['_href'])
        repo2 = self.client.get(repo2['_href'], params={'details': True})
        # `old_dependency` will import an older version, `0.71` of walrus to
        # the destiny repostiory.
        if old_dependency:
            rpm = utils.http_get(RPM_WITH_OLD_VERSION_URL)
            upload_import_unit(
                self.cfg,
                rpm,
                {'unit_type_id': 'rpm'}, repo2
            )
            units = search_units(self.cfg, repo2, {'type_ids': ['rpm']})
            self.assertEqual(len(units), 1, units)

        # Copy repo1 to repo2
        self.client.post(
            urljoin(repo2['_href'], 'actions/associate/'),
            {
                'source_repo_id': repo1['id'],
                'override_config': {
                    'recursive': recursive,
                    'recursive_conservative': recursive_conservative
                    },
                'criteria': criteria
            }
        )
        return self.client.get(repo2['_href'], params={'details': True})

    def create_sync_modular_repo(self):
        """Create a repo with feed pointing to modular data and sync it.

        :returns: repo data that is created and synced with modular content.
        """
        body = gen_repo()
        body['importer_config']['feed'] = RPM_WITH_MODULES_FEED_URL
        body['distributors'] = [gen_distributor()]
        repo = self.client.post(REPOSITORY_PATH, body)
        self.addCleanup(self.client.delete, repo['_href'])
        sync_repo(self.cfg, repo)
        return self.client.get(repo['_href'], params={'details': True})

    def remove_module_from_repo(self, repo, criteria):
        """Remove modules from repo."""
        self.client.post(
            urljoin(repo['_href'], 'actions/unassociate/'),
            {'criteria': criteria}
        )
        return self.client.get(repo['_href'], params={'details': True})


class PackageManagerModuleListTestCase(unittest.TestCase):
    """Package manager can read module list from a Pulp repository."""

    def test_all(self):
        """Package manager can read module list from a Pulp repository."""
        cfg = config.get_config()
        if cfg.pulp_version < Version('2.17'):
            raise unittest.SkipTest('This test requires Pulp 2.17 or newer.')
        if not os_support_modularity(cfg):
            raise unittest.SkipTest(
                'This test requires an OS that supports modularity.'
            )
        client = api.Client(cfg, api.json_handler)
        body = gen_repo(
            importer_config={'feed': RPM_WITH_MODULES_FEED_URL},
            distributors=[gen_distributor()]
        )

        repo = client.post(REPOSITORY_PATH, body)
        self.addCleanup(client.delete, repo['_href'])
        repo = client.get(repo['_href'], params={'details': True})
        sync_repo(cfg, repo)
        publish_repo(cfg, repo)
        repo = client.get(repo['_href'], params={'details': True})
        repo_path = gen_yum_config_file(
            cfg,
            baseurl=urljoin(cfg.get_base_url(), urljoin(
                'pulp/repos/',
                repo['distributors'][0]['config']['relative_url']
            )),
            name=repo['_href'],
            repositoryid=repo['id']
        )
        cli_client = cli.Client(cfg)
        self.addCleanup(cli_client.run, ('rm', repo_path), sudo=True)
        lines = cli_client.run((
            ('dnf', 'module', 'list', '--all')
        ), sudo=True).stdout.splitlines()
        for key, value in MODULE_FIXTURES_PACKAGES.items():
            with self.subTest(package=key):
                module = [line for line in lines if key in line]
                self.assertEqual(len(module), value, module)


class UploadModuleTestCase(unittest.TestCase):
    """Upload a module.yaml file and test upload import in Pulp repository."""

    @classmethod
    def setUpClass(cls):
        """Create class wide variables."""
        cls.cfg = config.get_config()
        if cls.cfg.pulp_version < Version('2.17'):
            raise unittest.SkipTest('This test requires Pulp 2.17 or newer.')
        cls.client = api.Client(cls.cfg, api.json_handler)

    def test_upload_module(self):
        """Verify whether uploaded module.yaml is updated in the pulp repo."""
        # Create a normal repo without any data.
        body = gen_repo(
            importer_config={'feed': RPM_UNSIGNED_FEED_URL},
            distributors=[gen_distributor()]
        )
        repo = self.client.post(REPOSITORY_PATH, body)
        repo = self.client.get(repo['_href'], params={'details': True})
        self.addCleanup(self.client.delete, repo['_href'])
        sync_repo(self.cfg, repo)

        # download modules.yaml and upload it to pulp_repo
        unit = self._get_module_yaml_file(RPM_WITH_MODULES_FEED_URL)
        upload_import_unit(self.cfg, unit, {
            'unit_key': {},
            'unit_type_id': 'modulemd',
        }, repo)
        repo = self.client.get(repo['_href'], params={'details': True})

        # Assert that `modulemd` and `modulemd_defaults` are present on the
        # repository.
        self.assertIsNotNone(repo['content_unit_counts']['modulemd'])
        self.assertIsNotNone(repo['content_unit_counts']['modulemd_defaults'])

    def test_one_default_per_repo(self):
        """Verify changing the modules default content of modules.yaml.

        Do not modifies the repo.
        """
        # create repo
        body = gen_repo(
            importer_config={'feed': RPM_WITH_MODULES_FEED_URL},
            distributors=[gen_distributor()]
        )
        repo = self.client.post(REPOSITORY_PATH, body)
        repo = self.client.get(repo['_href'], params={'details': True})
        self.addCleanup(self.client.delete, repo['_href'])
        sync_repo(self.cfg, repo)

        # Modify Modules.yaml and upload
        unit = self._get_module_yaml_file(RPM_WITH_MODULES_FEED_URL)
        unit_string = unit.decode('utf-8')
        unit_string = unit_string.replace(
            'stream: {}'.format(MODULE_FIXTURES_PACKAGE_STREAM['stream']),
            'stream: {}'.format(MODULE_FIXTURES_PACKAGE_STREAM['new_stream'])
        )
        unit = unit_string.encode()
        upload_import_unit(self.cfg, unit, {
            'unit_key': {},
            'unit_type_id': 'modulemd',
        }, repo)
        repo = self.client.get(repo['_href'], params={'details': True})
        self.assertEqual(
            repo['content_unit_counts']['modulemd_defaults'],
            3,
            repo['content_unit_counts'])

    @staticmethod
    def _get_module_yaml_file(path):
        """Return the path to ``modules.yaml``, relative to repository root.

        Given a detailed dict of information about a published repository,
        parse that repository's ``repomd.xml`` file and tell the path to the
        repository's ``[…]-modules.yaml`` file. The path is likely to be in the
        form ``repodata/[…]-modules.yaml.gz``.
        """
        repo_path = urljoin(path, 'repodata/repomd.xml')
        response = utils.http_get(repo_path)
        root_elem = ElementTree.fromstring(response)

        # <ns0:repomd xmlns:ns0="http://linux.duke.edu/metadata/repo">
        #     <ns0:data type="modules">
        #         <ns0:checksum type="sha256">[…]</ns0:checksum>
        #         <ns0:location href="repodata/[…]-modules.yaml.gz" />
        #         …
        #     </ns0:data>
        #     …

        xpath = '{{{}}}data'.format(RPM_NAMESPACES['metadata/repo'])
        data_elements = [
            elem for elem in root_elem.findall(xpath)
            if elem.get('type') == 'modules'
        ]
        xpath = '{{{}}}location'.format(RPM_NAMESPACES['metadata/repo'])
        relative_path = data_elements[0].find(xpath).get('href')
        unit = utils.http_get(urljoin(path, relative_path))
        with io.BytesIO(unit) as compressed:
            with gzip.GzipFile(fileobj=compressed) as decompressed:
                unit = decompressed.read()
        return unit


class CheckIsModularFlagTestCase(unittest.TestCase):
    """Check is_modular flag unit is present after syncing."""

    def test_all(self):
        """Verify whether the is_modular flag is present in rpm units.

        This test does the following:

        1. Create and sync a modular repo
        2. Filter the modular and non_modular units using
           :meth:`pulp_smash.pulp2.utils.search_units`
        3. Check whether the modular and non_modular units returned
           by this filter is accurate.

        This test case targets:

        * `Pulp #4049 <https://pulp.plan.io/issues/4049>`_.
        * `Pulp #4146 <https://pulp.plan.io/issues/4146>`_.
        """
        cfg = config.get_config()
        if cfg.pulp_version < Version('2.18'):
            raise unittest.SkipTest('This test requires Pulp 2.18 or newer.')
        client = api.Client(cfg, api.json_handler)
        body = gen_repo(
            importer_config={'feed': RPM_WITH_MODULES_FEED_URL},
            distributors=[gen_distributor()]
        )
        repo = client.post(REPOSITORY_PATH, body)
        self.addCleanup(client.delete, repo['_href'])
        sync_repo(cfg, repo)
        repo = client.get(repo['_href'], params={'details': True})
        modular_units = search_units(
            cfg, repo, {
                'filters': {'unit': {'is_modular': True}},
                'type_ids': ['rpm'],
            }
        )
        non_modular_units = search_units(
            cfg, repo, {
                'filters': {'unit': {'is_modular': False}},
                'type_ids': ['rpm'],
            }
        )
        # Check the number of modular units returned by `is_modular` as True.
        self.assertEqual(
            len(modular_units),
            sum(MODULE_FIXTURES_PACKAGES.values()),
            modular_units
        )
        # Check the number of modular units returned by `is_modular` as False.
        self.assertEqual(
            len(non_modular_units),
            RPM_UNSIGNED_FEED_COUNT - sum(MODULE_FIXTURES_PACKAGES.values()),
            non_modular_units
        )


class CheckModulesYamlTestCase(unittest.TestCase):
    """Check whether modules.yaml is available if appropriate."""

    @classmethod
    def setUpClass(cls):
        """Create class wide variables."""
        cls.cfg = config.get_config()
        if cls.cfg.pulp_version < Version('2.18.1'):
            raise unittest.SkipTest('This test requires Pulp 2.18.1 or newer.')
        cls.client = api.Client(cls.cfg, api.json_handler)

    def test_no_modules_yaml_generated_non_modular(self):
        """Verify no ``modules.yaml`` is generated for non modular content.

        This test does the following

        1. Create and sync a non-modular content.
        2. Publish the synced content.
        3. Check whether no modules.yaml is generated for published content.

        This test case targets:

        * `Pulp #4252 <https://pulp.plan.io/issues/4252>`_.
        * `Pulp #4350 <https://pulp.plan.io/issues/4350>`_.
        """
        body = gen_repo(
            importer_config={'feed': RPM_UNSIGNED_FEED_URL},
            distributors=[gen_distributor(auto_publish=True)]
        )
        # Step 1 and 2
        repo = self.client.post(REPOSITORY_PATH, body)
        self.addCleanup(self.client.delete, repo['_href'])
        sync_repo(self.cfg, repo)
        repo = self.client.get(repo['_href'], params={'details': True})
        # Step 3
        files = self.list_repo_data_files(self.cfg, repo)
        # check no modules.yaml.gz is found
        self.assertFalse(bool(files))
        modules_elements = self.get_modules_elements_repomd(
            self.cfg,
            repo['distributors'][0]
        )
        self.assertFalse(bool(modules_elements))

    def test_sha1_modules_yaml(self):
        """Verify whether the published modular content has appropriate sha.

        This test does the following:

        1. Create and sync a modular content with sha1 checksum.
        2. Publish the synced content
        3. Check whether the modules.yaml is sha1 checked.

        This test targets the following:

        * `Pulp #4351 <https://pulp.plan.io/issues/4351>`_.
        """
        body = gen_repo(
            importer_config={'feed': RPM_WITH_MODULES_SHA1_FEED_URL},
            distributors=[gen_distributor(auto_publish=True)]
        )
        # Step 1 and 2
        repo = self.client.post(REPOSITORY_PATH, body)
        self.addCleanup(self.client.delete, repo['_href'])
        sync_repo(self.cfg, repo)
        repo = self.client.get(repo['_href'], params={'details': True})
        module_file = self.list_repo_data_files(self.cfg, repo)[0]
        sha_vals = self.get_sha1_vals_file(self.cfg, module_file)
        # sha_vals[0] contains the sha1 checksum of the file
        # sha_vals[1] contains the filepath containing the checked file
        self.assertIn(sha_vals[0], sha_vals[1])

    @staticmethod
    def list_repo_data_files(cfg, repo):
        """Return a list of all the files present inside repodata dir."""
        return cli.Client(cfg).run((
            'find',
            '/var/lib/pulp/published/yum/master/yum_distributor/{}/'.format(
                repo['id']
            ),
            '-type',
            'f',
            '-name',
            '*modules.yaml.gz'
        ), sudo=True).stdout.splitlines()

    @staticmethod
    def get_modules_elements_repomd(cfg, distributor):
        """Return a list of elements present inside the repomd.xml."""
        repomd_xml = get_repodata_repomd_xml(cfg, distributor)
        xpath = (
            "{{{namespace}}}data[@type='{type_}']".format(
                namespace=RPM_NAMESPACES['metadata/repo'],
                type_='modules'
            )
        )
        return repomd_xml.findall(xpath)

    @staticmethod
    def get_sha1_vals_file(cfg, filepath):
        """Return a list containing sha1 checksum of the file and the filepath."""
        return cli.Client(cfg).run((
            'sha1sum',
            filepath
        ), sudo=True).stdout.split()
