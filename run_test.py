import unittest
import sys

loader = unittest.TestLoader()
suite = loader.loadTestsFromName('tests.test_ecosistema.TestTyDMReview')
runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)