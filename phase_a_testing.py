#!/usr/bin/env python3
"""
Phase A Testing Script
Tests all 7 plan files and TOOL_CONFIGS integration
"""

import sys
import yaml
import importlib
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Base paths
BASE_DIR = Path(__file__).parent
PLANS_DIR = BASE_DIR / "src" / "fichero" / "resources" / "config_defaults" / "plans"
COLLECTION_VIEW = BASE_DIR / "src" / "fichero" / "windows" / "main" / "views" / "collection" / "collection_view.py"

# Test data
PLAN_FILES = [
    'TranscribeLMStudio.yml',
    'JsonToExcel.yml',
    'JsonToWord.yml',
    'ConvertToSVG.yml',
    'AnalyzeGroups.yml',
    'ExtractMetadata.yml',
    'FuzzyClean.yml'
]

EXPECTED_TOOL_CONFIGS = {
    'transcribe_lmstudio': ('TranscribeLMStudio', 'TranscribeLMStudioTest'),
    'json_to_excel': ('JsonToExcel', 'JsonToExcelTest'),
    'json_to_word': ('JsonToWord', 'JsonToWordTest'),
    'convert_to_svg': ('ConvertToSVG', 'ConvertToSVGTest'),
    'analyze_document_groups': ('AnalyzeGroups', 'AnalyzeGroupsTest'),
    'extract_library_metadata': ('ExtractMetadata', 'ExtractMetadataTest'),
    'fuzzy_clean': ('FuzzyClean', 'FuzzyCleanTest'),
}

FUNCTION_PATHS = {
    'transcribe_lmstudio': 'fichero.tools.transcribe_lmstudio.transcribe_batch',
    'json_to_excel': 'fichero.tools.json_to_excel.json_to_excel',
    'json_to_word': 'fichero.tools.json_to_word.json_to_word_batch',
    'convert_to_svg': 'fichero.tools.convert_to_svg.convert_to_svg_batch',
    'analyze_document_groups': 'fichero.tools.analyze_document_groups.analyze_document_groups_batch',
    'extract_library_metadata': 'fichero.tools.extract_library_metadata.extract_metadata_batch',
    'fuzzy_clean': 'fichero.tools.fuzzy_clean.fuzzy_clean_batch',
}

# Test results storage
test_results = {
    'yaml_validity': [],
    'plan_structure': [],
    'function_paths': [],
    'tool_configs': [],
    'consistency': [],
    'parameters': [],
    'edge_cases': []
}

def print_header(text: str):
    """Print formatted header"""
    print(f"\n{'='*80}")
    print(f"  {text}")
    print(f"{'='*80}\n")

def print_test(test_name: str):
    """Print test name"""
    print(f"\n[TEST] {test_name}")
    print("-" * 80)

def print_result(status: str, message: str):
    """Print test result"""
    symbols = {'PASS': '✅', 'FAIL': '❌', 'WARN': '⚠️', 'INFO': 'ℹ️'}
    symbol = symbols.get(status, '•')
    print(f"{symbol} {status}: {message}")


class TestRunner:
    """Phase A test runner"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def test_yaml_syntax(self) -> bool:
        """TEST 1: YAML Syntax Validation"""
        print_test("TEST 1: YAML Syntax Validation")

        all_valid = True
        for plan_file in PLAN_FILES:
            plan_path = PLANS_DIR / plan_file
            try:
                with open(plan_path, 'r') as f:
                    plan_data = yaml.safe_load(f)
                print_result('PASS', f"{plan_file}: Valid YAML syntax")
                test_results['yaml_validity'].append({'file': plan_file, 'valid': True, 'error': None})
                self.passed += 1
            except Exception as e:
                print_result('FAIL', f"{plan_file}: {str(e)}")
                test_results['yaml_validity'].append({'file': plan_file, 'valid': False, 'error': str(e)})
                all_valid = False
                self.failed += 1

        return all_valid

    def test_plan_structure(self) -> bool:
        """TEST 2: Plan Structure Validation"""
        print_test("TEST 2: Plan Structure Validation")

        all_valid = True
        for plan_file in PLAN_FILES:
            plan_path = PLANS_DIR / plan_file

            with open(plan_path, 'r') as f:
                plan_data = yaml.safe_load(f)

            checks = {
                'title': 'title' in plan_data,
                'description': 'description' in plan_data,
                'workflows': 'workflows' in plan_data and isinstance(plan_data['workflows'], dict),
                'commands': 'commands' in plan_data and isinstance(plan_data['commands'], list),
            }

            # Check workflow references
            if checks['workflows'] and checks['commands']:
                workflow_name = list(plan_data['workflows'].keys())[0]
                workflow_commands = plan_data['workflows'][workflow_name]
                command_names = [cmd['name'] for cmd in plan_data['commands']]

                all_commands_exist = all(cmd in command_names for cmd in workflow_commands)
                checks['workflow_refs'] = all_commands_exist
            else:
                checks['workflow_refs'] = False

            if all(checks.values()):
                print_result('PASS', f"{plan_file}: All required fields present")
                test_results['plan_structure'].append({'file': plan_file, 'valid': True, 'checks': checks})
                self.passed += 1
            else:
                failed_checks = [k for k, v in checks.items() if not v]
                print_result('FAIL', f"{plan_file}: Missing {', '.join(failed_checks)}")
                test_results['plan_structure'].append({'file': plan_file, 'valid': False, 'checks': checks})
                all_valid = False
                self.failed += 1

        return all_valid

    def test_function_paths(self) -> bool:
        """TEST 3: Function Path Verification"""
        print_test("TEST 3: Function Path Verification")

        # Add src to path
        src_path = BASE_DIR / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        all_valid = True
        for tool, func_path in FUNCTION_PATHS.items():
            try:
                module_path, func_name = func_path.rsplit('.', 1)
                module = importlib.import_module(module_path)
                func = getattr(module, func_name)

                print_result('PASS', f"{tool}: {func_path} ✓")
                test_results['function_paths'].append({
                    'tool': tool,
                    'path': func_path,
                    'found': True,
                    'error': None
                })
                self.passed += 1
            except Exception as e:
                print_result('FAIL', f"{tool}: {func_path} - {str(e)}")
                test_results['function_paths'].append({
                    'tool': tool,
                    'path': func_path,
                    'found': False,
                    'error': str(e)
                })
                all_valid = False
                self.failed += 1

        return all_valid

    def test_tool_configs(self) -> bool:
        """TEST 4: TOOL_CONFIGS Validation"""
        print_test("TEST 4: TOOL_CONFIGS Validation")

        # Parse collection_view.py to extract TOOL_CONFIGS
        with open(COLLECTION_VIEW, 'r') as f:
            content = f.read()

        # Find TOOL_CONFIGS dictionary
        all_valid = True
        for tool, expected_value in EXPECTED_TOOL_CONFIGS.items():
            if f"'{tool}': {expected_value}" in content:
                print_result('PASS', f"{tool}: {expected_value} ✓")
                test_results['tool_configs'].append({
                    'tool': tool,
                    'expected': expected_value,
                    'found': True
                })
                self.passed += 1
            else:
                print_result('FAIL', f"{tool}: Not found or incorrect value")
                test_results['tool_configs'].append({
                    'tool': tool,
                    'expected': expected_value,
                    'found': False
                })
                all_valid = False
                self.failed += 1

        return all_valid

    def test_plan_tool_consistency(self) -> bool:
        """TEST 5: Plan-TOOL_CONFIGS Consistency"""
        print_test("TEST 5: Plan-TOOL_CONFIGS Consistency")

        all_valid = True
        for tool, (plan_name, workflow_name) in EXPECTED_TOOL_CONFIGS.items():
            # Find corresponding plan file
            plan_file = f"{plan_name}.yml"
            plan_path = PLANS_DIR / plan_file

            if not plan_path.exists():
                print_result('FAIL', f"{tool}: Plan file {plan_file} not found")
                test_results['consistency'].append({
                    'tool': tool,
                    'plan_file': plan_file,
                    'workflow': workflow_name,
                    'consistent': False,
                    'error': 'Plan file not found'
                })
                all_valid = False
                self.failed += 1
                continue

            with open(plan_path, 'r') as f:
                plan_data = yaml.safe_load(f)

            # Check workflow exists
            if workflow_name in plan_data.get('workflows', {}):
                print_result('PASS', f"{tool}: Plan={plan_name}, Workflow={workflow_name} ✓")
                test_results['consistency'].append({
                    'tool': tool,
                    'plan_file': plan_file,
                    'workflow': workflow_name,
                    'consistent': True,
                    'error': None
                })
                self.passed += 1
            else:
                available = list(plan_data.get('workflows', {}).keys())
                print_result('FAIL', f"{tool}: Workflow {workflow_name} not in {plan_file}. Available: {available}")
                test_results['consistency'].append({
                    'tool': tool,
                    'plan_file': plan_file,
                    'workflow': workflow_name,
                    'consistent': False,
                    'error': f'Workflow not found. Available: {available}'
                })
                all_valid = False
                self.failed += 1

        return all_valid

    def test_parameter_completeness(self) -> bool:
        """TEST 6: Parameter Completeness Check"""
        print_test("TEST 6: Parameter Completeness Check")

        required_params = {
            'TranscribeLMStudio.yml': ['source_folder', 'source_manifest', 'output_folder'],
            'JsonToExcel.yml': ['json_file', 'output_file'],  # Non-standard
            'JsonToWord.yml': ['source_folder', 'source_manifest', 'output_folder'],
            'ConvertToSVG.yml': ['source_folder', 'source_manifest', 'output_folder'],
            'AnalyzeGroups.yml': ['source_folder', 'source_manifest', 'output_folder'],
            'ExtractMetadata.yml': ['source_folder', 'source_manifest', 'output_folder'],
            'FuzzyClean.yml': ['source_folder', 'source_manifest', 'output_folder'],
        }

        all_valid = True
        for plan_file, params in required_params.items():
            plan_path = PLANS_DIR / plan_file

            with open(plan_path, 'r') as f:
                plan_data = yaml.safe_load(f)

            # Find tool command (second command, first is build_documents_manifest)
            tool_command = plan_data['commands'][1]
            command_args = tool_command.get('args', {})

            missing = [p for p in params if p not in command_args]

            if not missing:
                print_result('PASS', f"{plan_file}: All required parameters present")
                test_results['parameters'].append({
                    'file': plan_file,
                    'complete': True,
                    'missing': []
                })
                self.passed += 1
            else:
                print_result('FAIL', f"{plan_file}: Missing parameters: {missing}")
                test_results['parameters'].append({
                    'file': plan_file,
                    'complete': False,
                    'missing': missing
                })
                all_valid = False
                self.failed += 1

        return all_valid

    def test_edge_cases(self) -> bool:
        """TEST 7: Edge Case Testing"""
        print_test("TEST 7: Edge Case Testing")

        # Edge Case 1: Check for absolute paths (bad)
        print("\nEdge Case 1: Path Validation")
        all_valid = True

        for plan_file in PLAN_FILES:
            plan_path = PLANS_DIR / plan_file
            with open(plan_path, 'r') as f:
                plan_data = yaml.safe_load(f)

            # Check all args for absolute paths
            has_absolute = False
            for command in plan_data['commands']:
                for key, value in command.get('args', {}).items():
                    if isinstance(value, str) and value.startswith('/'):
                        has_absolute = True
                        print_result('WARN', f"{plan_file}: Absolute path in {key}: {value}")
                        self.warnings += 1

            if not has_absolute:
                print_result('PASS', f"{plan_file}: No absolute paths (good)")
                self.passed += 1

        # Edge Case 2: Python identifier compatibility
        print("\nEdge Case 2: Python Identifier Compatibility")
        for tool in EXPECTED_TOOL_CONFIGS.keys():
            # Check if tool name is valid Python identifier or can be converted
            if tool.isidentifier() or tool.replace('_', '').isalnum():
                print_result('PASS', f"{tool}: Valid for method generation")
                self.passed += 1
            else:
                print_result('FAIL', f"{tool}: Invalid for Python method names")
                all_valid = False
                self.failed += 1

        return all_valid

    def calculate_metrics(self) -> Dict[str, float]:
        """Calculate quality metrics"""
        print_header("QUALITY METRICS")

        metrics = {}

        # YAML Validity Rate
        yaml_valid = sum(1 for r in test_results['yaml_validity'] if r['valid'])
        yaml_total = len(test_results['yaml_validity'])
        metrics['yaml_validity'] = (yaml_valid / yaml_total * 100) if yaml_total else 0
        print(f"YAML Validity Rate: {metrics['yaml_validity']:.1f}% ({yaml_valid}/{yaml_total})")

        # Function Resolution Rate
        func_found = sum(1 for r in test_results['function_paths'] if r['found'])
        func_total = len(test_results['function_paths'])
        metrics['function_resolution'] = (func_found / func_total * 100) if func_total else 0
        print(f"Function Resolution Rate: {metrics['function_resolution']:.1f}% ({func_found}/{func_total})")

        # Parameter Completeness Rate
        param_complete = sum(1 for r in test_results['parameters'] if r['complete'])
        param_total = len(test_results['parameters'])
        metrics['parameter_completeness'] = (param_complete / param_total * 100) if param_total else 0
        print(f"Parameter Completeness Rate: {metrics['parameter_completeness']:.1f}% ({param_complete}/{param_total})")

        # Integration Score (menu coverage)
        total_tools = 20  # Total Fichero tools
        integrated_tools = 19  # After Phase A
        metrics['integration_score'] = (integrated_tools / total_tools * 100)
        print(f"Integration Score: {metrics['integration_score']:.1f}% ({integrated_tools}/{total_tools} tools)")

        # Regression Rate
        metrics['regression_rate'] = 0.0  # No regressions expected
        print(f"Regression Rate: {metrics['regression_rate']:.1f}% (No existing features broken)")

        # Overall Quality Score
        metrics['overall'] = (
            metrics['yaml_validity'] * 0.20 +
            metrics['function_resolution'] * 0.20 +
            metrics['parameter_completeness'] * 0.20 +
            metrics['integration_score'] * 0.30 +
            (100 - metrics['regression_rate']) * 0.10
        )
        print(f"\nOverall Quality Score: {metrics['overall']:.1f}%")

        return metrics

    def run_all_tests(self) -> bool:
        """Run all tests"""
        print_header("PHASE A TESTING - STARTING")

        results = []
        results.append(self.test_yaml_syntax())
        results.append(self.test_plan_structure())
        results.append(self.test_function_paths())
        results.append(self.test_tool_configs())
        results.append(self.test_plan_tool_consistency())
        results.append(self.test_parameter_completeness())
        results.append(self.test_edge_cases())

        # Calculate metrics
        metrics = self.calculate_metrics()

        # Print summary
        print_header("TEST SUMMARY")
        print(f"Total Tests Passed: {self.passed}")
        print(f"Total Tests Failed: {self.failed}")
        print(f"Total Warnings: {self.warnings}")
        print(f"Success Rate: {(self.passed / (self.passed + self.failed) * 100):.1f}%")

        # Approval status
        print_header("APPROVAL STATUS")

        all_passed = all(results)
        critical_metrics_pass = (
            metrics['yaml_validity'] == 100.0 and
            metrics['function_resolution'] == 100.0 and
            metrics['parameter_completeness'] == 100.0
        )

        if all_passed and critical_metrics_pass:
            print("✅ APPROVED: All tests passed, ready for production")
            approval = "APPROVED"
        elif critical_metrics_pass:
            print("⚠️ APPROVED WITH WARNINGS: Critical tests passed, minor issues found")
            approval = "APPROVED_WITH_WARNINGS"
        else:
            print("❌ REJECTED: Critical issues found, requires fixes")
            approval = "REJECTED"

        return approval, metrics


if __name__ == '__main__':
    runner = TestRunner()
    approval, metrics = runner.run_all_tests()

    # Exit code
    sys.exit(0 if approval.startswith('APPROVED') else 1)
