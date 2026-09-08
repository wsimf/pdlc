"""All package modules must remain importable after provider moves."""

import importlib
import pkgutil
import unittest

import pdlc


class PackageLayoutTests(unittest.TestCase):
    def test_import_every_package_module(self):
        for module in pkgutil.walk_packages(pdlc.__path__, prefix="pdlc."):
            with self.subTest(module=module.name):
                importlib.import_module(module.name)
