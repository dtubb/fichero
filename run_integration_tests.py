#!/usr/bin/env python3
"""
Integration Test Runner for Director-Library Integration

Runs comprehensive integration tests to validate the complete director-library flow.
This includes all phases of improvements:
- Phase 1: Data Flow Investigation
- Phase 2: Manifest Ingestion Fixes
- Phase 3: Metadata Architecture Enhancement (leaf vs node level)
- Phase 4: Smart Output Processing (plan-aware validation)

Usage:
    python run_integration_tests.py [--verbose] [--pattern PATTERN]

Examples:
    python run_integration_tests.py
    python run_integration_tests.py --verbose
    python run_integration_tests.py --pattern "*single_file*"
    python run_integration_tests.py --pattern "*error*"
"""

import sys
import unittest
import argparse
from pathlib import Path

# Add src directory to Python path
src_dir = Path(__file__).parent / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

def run_integration_tests(verbose: bool = False, pattern: str = None):
    """
    Run integration tests for director-library integration

    Args:
        verbose: Whether to run with verbose output
        pattern: Optional pattern to filter test methods

    Returns:
        True if all tests pass, False otherwise
    """
    # Discover tests
    loader = unittest.TestLoader()

    if pattern:
        # Load specific test pattern
        suite = loader.loadTestsFromName(f'tests.integration.test_director_library_integration.TestDirectorLibraryIntegration.{pattern}')
    else:
        # Load all integration tests
        suite = loader.discover('tests/integration', pattern='test_*.py')

    # Run tests
    verbosity = 2 if verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity, buffer=True)

    print("=" * 80)
    print("FICHERO DIRECTOR-LIBRARY INTEGRATION TESTS")
    print("=" * 80)
    print()
    print("Testing complete end-to-end flow:")
    print("• Director Processing → WorkflowManifest → Ingestion → Database")
    print("• ProcessingOutput records → ExtractedMetadata → Query/Display")
    print("• File-level (leaf) vs Collection-level (node) metadata distinction")
    print("• Plan-aware output validation and error recovery")
    print("• Preview/Adjust view integration")
    print()
    print("=" * 80)
    print()

    result = runner.run(suite)

    print()
    print("=" * 80)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 80)

    if result.wasSuccessful():
        print("✅ ALL INTEGRATION TESTS PASSED!")
        print()
        print("The director-library integration system is working correctly:")
        print("• End-to-end processing flows validated")
        print("• Metadata architecture (leaf/node levels) functional")
        print("• Plan-aware validation working as expected")
        print("• Error recovery mechanisms tested")
        print("• Database integration confirmed")
        print("• View layer integration verified")
        return True
    else:
        print("❌ SOME INTEGRATION TESTS FAILED")
        print()
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        print()
        print("Failed test details:")
        for test, error in result.failures + result.errors:
            print(f"• {test}: {error.split(chr(10))[0]}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run Fichero director-library integration tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Coverage:
• test_single_file_processing_end_to_end - File-level processing flow
• test_single_folder_processing_end_to_end - Folder-level processing flow
• test_mixed_collection_processing - Combined file/folder processing
• test_plan_aware_output_validation - Different plan validations
• test_error_recovery_scenarios - Error handling from all phases
• test_metadata_extraction_leaf_node_distinction - Phase 3 improvements
• test_preview_view_database_integration - Preview view loading
• test_adjust_view_metadata_loading - Adjust view loading
• test_performance_realistic_workload - Performance testing
• test_backward_compatibility - Legacy data handling

Examples:
    python run_integration_tests.py
    python run_integration_tests.py --verbose
    python run_integration_tests.py --pattern test_single_file_processing_end_to_end
    python run_integration_tests.py --pattern test_error_recovery_scenarios
        """
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Run tests with verbose output'
    )

    parser.add_argument(
        '--pattern', '-p',
        type=str,
        help='Run only tests matching this pattern (e.g., test_single_file_processing_end_to_end)'
    )

    args = parser.parse_args()

    success = run_integration_tests(verbose=args.verbose, pattern=args.pattern)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()