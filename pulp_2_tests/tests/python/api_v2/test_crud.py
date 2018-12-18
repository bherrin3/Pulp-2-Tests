# coding=utf-8
"""Tests that CRUD Python repositories."""
import pytest

from pulp_smash import utils
from pulp_smash.pulp2.utils import BaseAPICrudTestCase

from pulp_2_tests.tests.python.api_v2.utils import gen_repo
from pulp_2_tests.tests.python.utils import set_up_module as setUpModule  # pylint:disable=unused-import

PYTESTMARK = pytest.mark.random_order(disabled=True)


class CRUDTestCase(BaseAPICrudTestCase):
    """Test that one can create, update, read and delete a test case."""

    @staticmethod
    def create_body():
        """Return a dict for creating a repository."""
        return gen_repo()

    @staticmethod
    def update_body():
        """Return a dict for creating a repository."""
        return {'delta': {'display_name': utils.uuid4()}}
