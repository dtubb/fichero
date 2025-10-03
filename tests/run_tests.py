"""
Test runner for Fichero

Runs all tests in the new modular test structure.
Can run specific test categories or all tests.
"""

import unittest
import sys
import os
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def run_unit_tests():
    """Run unit tests"""
    print("Running unit tests...")
    loader = unittest.TestLoader()
    start_dir = Path(__file__).parent / "unit"
    suite = loader.discover(str(start_dir), pattern='test_*.py')

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


def run_integration_tests():
    """Run integration tests"""
    print("Running integration tests...")
    loader = unittest.TestLoader()
    start_dir = Path(__file__).parent / "integration"
    suite = loader.discover(str(start_dir), pattern='test_*.py')

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


def run_all_tests():
    """Run all tests"""
    print("Running all tests...")

    # Run unit tests
    unit_success = run_unit_tests()
    print()

    # Run integration tests
    integration_success = run_integration_tests()
    print()

    # Summary
    if unit_success and integration_success:
        print("✅ All tests passed!")
        return True
    else:
        print("❌ Some tests failed!")
        if not unit_success:
            print("  - Unit tests failed")
        if not integration_success:
            print("  - Integration tests failed")
        return False


def run_specific_test(test_path):
    """Run a specific test file"""
    print(f"Running specific test: {test_path}")

    # Convert path to module format
    test_module = test_path.replace('/', '.').replace('.py', '')

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(test_module)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


def main():
    """Main test runner"""
    import argparse

    parser = argparse.ArgumentParser(description="Run Fichero tests")
    parser.add_argument('test_type', nargs='?', default='all',
                       choices=['all', 'unit', 'integration', 'console'],
                       help='Type of tests to run')
    parser.add_argument('--file', help='Run specific test file')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')

    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    success = False

    if args.file:
        success = run_specific_test(args.file)
    elif args.test_type == 'unit':
        success = run_unit_tests()
    elif args.test_type == 'integration':
        success = run_integration_tests()
    elif args.test_type == 'console':
        # Run just the console interface test
        success = run_specific_test('integration.test_console_interface')
    elif args.test_type == 'all':
        success = run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()