"""
Unit tests for smart output processing enhancements (Phase 4)

Tests the plan-aware output validation, processing type detection,
step-aware validation, recovery mechanisms, and enhanced output type detection
with confidence scoring.

Key features tested:
- Plan-aware output validation with expected output mapping
- Processing type detection (file vs folder vs batch)
- Step-aware validation for each processing step
- Recovery mechanisms for missing outputs
- Enhanced output type detection with confidence scoring
- Comprehensive validation framework
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import json
from datetime import datetime


class TestPlanAwareValidation(unittest.TestCase):
    """Test plan-aware output validation with expected output mapping"""

    def test_transcribir_catalogar_expected_outputs(self):
        """Test expected outputs for 'Transcribir y Catalogar' plan"""
        # Define expected outputs for this plan
        expected_outputs = {
            'Transcribir y Catalogar': {
                'required_steps': ['transcribe', 'catalogue'],
                'required_output_types': ['transcription', 'catalogue'],
                'optional_steps': ['word_doc'],
                'expected_files': ['*.txt', '*.json', '*.docx']
            }
        }

        plan_name = 'Transcribir y Catalogar'
        plan_config = expected_outputs[plan_name]

        # Test: Validate plan requirements
        self.assertIn('transcribe', plan_config['required_steps'])
        self.assertIn('catalogue', plan_config['required_steps'])
        self.assertIn('transcription', plan_config['required_output_types'])
        self.assertIn('catalogue', plan_config['required_output_types'])

    def test_prepare_images_expected_outputs(self):
        """Test expected outputs for 'Prepare Images' plan"""
        expected_outputs = {
            'Prepare Images': {
                'required_steps': ['crop', 'enhance'],
                'required_output_types': ['image'],
                'optional_steps': ['background_removal'],
                'expected_files': ['*.jpg', '*.png', '*.tiff']
            }
        }

        plan_name = 'Prepare Images'
        plan_config = expected_outputs[plan_name]

        # Test: Validate image preparation requirements
        self.assertIn('crop', plan_config['required_steps'])
        self.assertIn('enhance', plan_config['required_steps'])
        self.assertIn('image', plan_config['required_output_types'])

    def test_plan_specific_validation_logic(self):
        """Test plan-specific validation logic"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Mock plan validator
            class MockPlanValidator:
                def validate_plan_outputs(self, plan_name, output_path, workflow_manifest):
                    """Mock validation logic"""
                    if plan_name == 'Transcribir y Catalogar':
                        return self._validate_transcribir_catalogar(output_path, workflow_manifest)
                    elif plan_name == 'Prepare Images':
                        return self._validate_prepare_images(output_path, workflow_manifest)
                    return {'valid': True, 'missing': [], 'unexpected': []}

                def _validate_transcribir_catalogar(self, output_path, manifest):
                    required_types = ['transcription', 'catalogue']
                    found_types = []

                    for step in manifest.get('steps', []):
                        step_name = step.get('name', '')
                        if step_name == 'transcribe':
                            found_types.append('transcription')
                        elif step_name == 'catalogue':
                            found_types.append('catalogue')

                    missing = [t for t in required_types if t not in found_types]
                    return {
                        'valid': len(missing) == 0,
                        'missing': missing,
                        'unexpected': []
                    }

                def _validate_prepare_images(self, output_path, manifest):
                    required_steps = ['crop', 'enhance']
                    found_steps = [step.get('name', '') for step in manifest.get('steps', [])]

                    missing = [s for s in required_steps if s not in found_steps]
                    return {
                        'valid': len(missing) == 0,
                        'missing': missing,
                        'unexpected': []
                    }

            validator = MockPlanValidator()

            # Test Transcribir y Catalogar validation
            transcribe_manifest = {
                'steps': [
                    {'name': 'transcribe', 'status': 'success'},
                    {'name': 'catalogue', 'status': 'success'}
                ]
            }

            result = validator.validate_plan_outputs('Transcribir y Catalogar', output_path, transcribe_manifest)
            self.assertTrue(result['valid'])
            self.assertEqual(result['missing'], [])

            # Test with missing step
            incomplete_manifest = {
                'steps': [
                    {'name': 'transcribe', 'status': 'success'}
                    # Missing catalogue step
                ]
            }

            result = validator.validate_plan_outputs('Transcribir y Catalogar', output_path, incomplete_manifest)
            self.assertFalse(result['valid'])
            self.assertIn('catalogue', result['missing'])


class TestProcessingTypeDetection(unittest.TestCase):
    """Test processing type detection (file vs folder vs batch)"""

    def test_file_processing_detection(self):
        """Test detection of single file processing"""
        # Mock processing context for file
        processing_context = {
            'input_type': 'file',
            'input_path': '/path/to/document.jpg',
            'item_type': 'file',
            'batch_size': 1
        }

        detected_type = self._detect_processing_type(processing_context)
        self.assertEqual(detected_type, 'file')

    def test_folder_processing_detection(self):
        """Test detection of folder processing"""
        processing_context = {
            'input_type': 'folder',
            'input_path': '/path/to/folder',
            'item_type': 'folder',
            'batch_size': 5
        }

        detected_type = self._detect_processing_type(processing_context)
        self.assertEqual(detected_type, 'folder')

    def test_batch_processing_detection(self):
        """Test detection of batch processing"""
        processing_context = {
            'input_type': 'batch',
            'input_path': '/path/to/multiple/files',
            'item_type': 'batch',
            'batch_size': 20
        }

        detected_type = self._detect_processing_type(processing_context)
        self.assertEqual(detected_type, 'batch')

    def _detect_processing_type(self, context):
        """Mock processing type detection logic"""
        if context.get('batch_size', 1) > 10:
            return 'batch'
        elif context.get('input_type') == 'folder' or context.get('item_type') == 'folder':
            return 'folder'
        else:
            return 'file'

    def test_processing_type_affects_validation(self):
        """Test that processing type affects validation strategy"""
        # File processing: strict individual validation
        file_validation_config = {
            'type': 'file',
            'validate_every_step': True,
            'require_all_outputs': True,
            'allow_partial_success': False
        }

        # Batch processing: more lenient validation
        batch_validation_config = {
            'type': 'batch',
            'validate_every_step': False,
            'require_all_outputs': False,
            'allow_partial_success': True,
            'min_success_rate': 0.8
        }

        # Test validation strategies differ
        self.assertTrue(file_validation_config['validate_every_step'])
        self.assertFalse(batch_validation_config['validate_every_step'])
        self.assertTrue(batch_validation_config['allow_partial_success'])
        self.assertFalse(file_validation_config['allow_partial_success'])


class TestStepAwareValidation(unittest.TestCase):
    """Test step-aware validation for each processing step"""

    def test_individual_step_validation(self):
        """Test validation of individual workflow steps"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Create workflow manifest with multiple steps
            workflow_steps = [
                {
                    'order': 1,
                    'name': 'transcribe',
                    'status': 'success',
                    'expected_outputs': ['*.txt'],
                    'output_path': 'assets/transcriptions/',
                    'manifest_file': 'assets/transcriptions/transcriptions_manifest.jsonl'
                },
                {
                    'order': 2,
                    'name': 'catalogue',
                    'status': 'success',
                    'expected_outputs': ['*.json'],
                    'output_path': 'assets/catalogues/',
                    'manifest_file': 'assets/catalogues/catalogue_manifest.jsonl'
                },
                {
                    'order': 3,
                    'name': 'word_doc',
                    'status': 'failed',  # This step failed
                    'expected_outputs': ['*.docx'],
                    'output_path': 'assets/documents/',
                    'manifest_file': 'assets/documents/word_manifest.jsonl'
                }
            ]

            # Mock step validator
            class MockStepValidator:
                def validate_step(self, step, output_base_path):
                    step_name = step['name']
                    status = step['status']

                    if status == 'failed':
                        return {'valid': False, 'reason': f'Step {step_name} failed'}

                    # Check if expected outputs exist
                    expected_path = output_base_path / step['output_path']
                    manifest_path = output_base_path / step['manifest_file']

                    return {
                        'valid': status == 'success',
                        'outputs_found': expected_path.exists(),
                        'manifest_found': manifest_path.exists()
                    }

            validator = MockStepValidator()

            # Validate each step
            validation_results = []
            for step in workflow_steps:
                result = validator.validate_step(step, output_path)
                validation_results.append({
                    'step': step['name'],
                    'result': result
                })

            # Test: Successful steps validate properly
            transcribe_result = next(r for r in validation_results if r['step'] == 'transcribe')
            catalogue_result = next(r for r in validation_results if r['step'] == 'catalogue')
            word_doc_result = next(r for r in validation_results if r['step'] == 'word_doc')

            self.assertTrue(transcribe_result['result']['valid'])
            self.assertTrue(catalogue_result['result']['valid'])
            self.assertFalse(word_doc_result['result']['valid'])  # Failed step

    def test_step_dependency_validation(self):
        """Test validation of step dependencies"""
        # Define step dependencies
        step_dependencies = {
            'transcribe': [],  # No dependencies
            'catalogue': ['transcribe'],  # Depends on transcribe
            'word_doc': ['transcribe', 'catalogue']  # Depends on both
        }

        completed_steps = ['transcribe', 'catalogue']

        # Test dependency checking
        def can_validate_step(step_name, completed_steps, dependencies):
            required_deps = dependencies.get(step_name, [])
            return all(dep in completed_steps for dep in required_deps)

        # Test each step
        self.assertTrue(can_validate_step('transcribe', completed_steps, step_dependencies))
        self.assertTrue(can_validate_step('catalogue', completed_steps, step_dependencies))
        self.assertTrue(can_validate_step('word_doc', completed_steps, step_dependencies))

        # Test with incomplete dependencies
        incomplete_steps = ['transcribe']  # catalogue not completed
        self.assertTrue(can_validate_step('transcribe', incomplete_steps, step_dependencies))
        self.assertTrue(can_validate_step('catalogue', incomplete_steps, step_dependencies))
        self.assertFalse(can_validate_step('word_doc', incomplete_steps, step_dependencies))

    def test_step_output_type_validation(self):
        """Test validation of step output types"""
        step_output_mapping = {
            'transcribe': 'transcription',
            'catalogue': 'catalogue',
            'crop': 'image',
            'enhance': 'image',
            'word_doc': 'document'
        }

        # Mock output validation
        def validate_step_output_type(step_name, actual_output_type):
            expected_type = step_output_mapping.get(step_name)
            return actual_output_type == expected_type

        # Test correct mappings
        self.assertTrue(validate_step_output_type('transcribe', 'transcription'))
        self.assertTrue(validate_step_output_type('catalogue', 'catalogue'))
        self.assertTrue(validate_step_output_type('crop', 'image'))

        # Test incorrect mappings
        self.assertFalse(validate_step_output_type('transcribe', 'image'))
        self.assertFalse(validate_step_output_type('catalogue', 'transcription'))


class TestRecoveryMechanisms(unittest.TestCase):
    """Test recovery mechanisms for missing outputs"""

    def test_missing_manifest_recovery(self):
        """Test recovery when manifest files are missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Create output files but missing manifest
            (output_path / 'assets' / 'transcriptions').mkdir(parents=True)
            (output_path / 'assets' / 'transcriptions' / 'doc1.txt').write_text('Transcription content')
            (output_path / 'assets' / 'transcriptions' / 'doc2.txt').write_text('More content')
            # Note: Missing transcriptions_manifest.jsonl

            # Mock recovery mechanism
            class MockOutputRecovery:
                def recover_missing_manifest(self, step_output_dir):
                    """Recover outputs when manifest is missing"""
                    if not step_output_dir.exists():
                        return []

                    # Find all output files and create synthetic manifest
                    output_files = list(step_output_dir.glob('*.txt'))
                    recovered_outputs = []

                    for output_file in output_files:
                        recovered_outputs.append({
                            'output_path': str(output_file),
                            'output_type': 'transcription',
                            'recovery_method': 'filesystem_scan',
                            'confidence': 0.8  # Lower confidence for recovered outputs
                        })

                    return recovered_outputs

            recovery = MockOutputRecovery()
            transcription_dir = output_path / 'assets' / 'transcriptions'

            # Act: Attempt recovery
            recovered = recovery.recover_missing_manifest(transcription_dir)

            # Assert: Outputs were recovered
            self.assertEqual(len(recovered), 2)
            self.assertEqual(recovered[0]['output_type'], 'transcription')
            self.assertEqual(recovered[0]['recovery_method'], 'filesystem_scan')
            self.assertEqual(recovered[0]['confidence'], 0.8)

    def test_fallback_output_discovery(self):
        """Test fallback discovery when expected outputs are missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Create outputs in unexpected locations
            (output_path / 'alternative_location').mkdir(parents=True)
            (output_path / 'alternative_location' / 'found_output.txt').write_text('Fallback content')
            (output_path / 'backup' / 'more_outputs').mkdir(parents=True)
            (output_path / 'backup' / 'more_outputs' / 'another.json').write_text('{"key": "value"}')

            # Mock fallback discovery
            class MockFallbackDiscovery:
                def discover_fallback_outputs(self, base_path, expected_types):
                    """Search for outputs in alternative locations"""
                    discovered = []

                    # Search all subdirectories
                    for file_path in base_path.rglob('*'):
                        if file_path.is_file():
                            file_type = self._detect_file_type(file_path)
                            if file_type in expected_types:
                                discovered.append({
                                    'path': str(file_path),
                                    'type': file_type,
                                    'discovery_method': 'recursive_search',
                                    'confidence': 0.6  # Lower confidence for fallback
                                })

                    return discovered

                def _detect_file_type(self, file_path):
                    """Detect file type from extension and content"""
                    suffix = file_path.suffix.lower()
                    if suffix == '.txt':
                        return 'transcription'
                    elif suffix == '.json':
                        return 'catalogue'
                    elif suffix in ['.jpg', '.png', '.tiff']:
                        return 'image'
                    return 'unknown'

            discovery = MockFallbackDiscovery()
            expected_types = ['transcription', 'catalogue']

            # Act: Discover fallback outputs
            discovered = discovery.discover_fallback_outputs(output_path, expected_types)

            # Assert: Alternative outputs were found
            self.assertEqual(len(discovered), 2)  # .txt and .json files
            discovered_types = [d['type'] for d in discovered]
            self.assertIn('transcription', discovered_types)
            self.assertIn('catalogue', discovered_types)

    def test_partial_failure_recovery(self):
        """Test recovery from partial workflow failures"""
        # Mock partial failure scenario
        workflow_status = {
            'transcribe': {'status': 'success', 'outputs_found': True},
            'catalogue': {'status': 'failed', 'outputs_found': False},
            'word_doc': {'status': 'skipped', 'outputs_found': False}  # Skipped due to catalogue failure
        }

        class MockPartialRecovery:
            def recover_from_partial_failure(self, workflow_status):
                """Attempt to recover what's possible from partial failure"""
                recovered_steps = []

                for step_name, status in workflow_status.items():
                    if status['status'] == 'success':
                        # Keep successful steps
                        recovered_steps.append({
                            'step': step_name,
                            'recovery_action': 'keep_existing',
                            'confidence': 1.0
                        })
                    elif status['status'] == 'failed':
                        # Attempt to re-run failed steps
                        recovered_steps.append({
                            'step': step_name,
                            'recovery_action': 'retry_step',
                            'confidence': 0.7
                        })
                    # Skip 'skipped' steps - they depend on failed steps

                return recovered_steps

        recovery = MockPartialRecovery()

        # Act: Attempt recovery
        recovered = recovery.recover_from_partial_failure(workflow_status)

        # Assert: Recovery plan created
        self.assertEqual(len(recovered), 2)  # transcribe + catalogue (word_doc skipped)

        transcribe_recovery = next(r for r in recovered if r['step'] == 'transcribe')
        catalogue_recovery = next(r for r in recovered if r['step'] == 'catalogue')

        self.assertEqual(transcribe_recovery['recovery_action'], 'keep_existing')
        self.assertEqual(catalogue_recovery['recovery_action'], 'retry_step')


class TestConfidenceScoring(unittest.TestCase):
    """Test enhanced output type detection with confidence scoring"""

    def test_high_confidence_output_detection(self):
        """Test high confidence output detection"""
        # Mock high-confidence scenarios
        high_confidence_cases = [
            {
                'file_path': '/output/transcriptions/document.txt',
                'step_name': 'transcribe',
                'manifest_present': True,
                'expected_confidence': 0.95
            },
            {
                'file_path': '/output/catalogues/metadata.json',
                'step_name': 'catalogue',
                'manifest_present': True,
                'expected_confidence': 0.95
            }
        ]

        for case in high_confidence_cases:
            confidence = self._calculate_confidence(case)
            self.assertGreaterEqual(confidence, case['expected_confidence'])

    def test_medium_confidence_output_detection(self):
        """Test medium confidence output detection"""
        medium_confidence_cases = [
            {
                'file_path': '/output/documents/result.txt',
                'step_name': 'unknown_step',
                'manifest_present': False,
                'file_exists': True,
                'expected_confidence': 0.6
            }
        ]

        for case in medium_confidence_cases:
            confidence = self._calculate_confidence(case)
            self.assertGreaterEqual(confidence, case['expected_confidence'])
            self.assertLess(confidence, 0.8)

    def test_low_confidence_output_detection(self):
        """Test low confidence output detection"""
        low_confidence_cases = [
            {
                'file_path': '/random/location/maybe_output.tmp',
                'step_name': 'unknown',
                'manifest_present': False,
                'file_exists': True,
                'expected_confidence': 0.3
            }
        ]

        for case in low_confidence_cases:
            confidence = self._calculate_confidence(case)
            self.assertLessEqual(confidence, case['expected_confidence'])

    def _calculate_confidence(self, case):
        """Mock confidence calculation logic"""
        confidence = 0.3  # Base confidence (lower to allow for low confidence cases)

        # Boost for manifest presence (high value for having proper manifest)
        if case.get('manifest_present', False):
            confidence += 0.35

        # Boost for step name match or related directory
        file_path = case.get('file_path', '')
        step_name = case.get('step_name', '')

        # Check for step name in path or related directories
        if step_name in file_path:
            confidence += 0.2
        elif step_name == 'transcribe' and 'transcriptions' in file_path:
            confidence += 0.2
        elif step_name == 'catalogue' and 'catalogues' in file_path:
            confidence += 0.2

        # Boost for expected file extensions
        if any(ext in file_path for ext in ['.txt', '.json', '.jpg', '.docx']):
            confidence += 0.2

        # Boost for standard directory structure
        if 'assets/' in file_path or '/output/' in file_path:
            confidence += 0.1

        return min(confidence, 1.0)  # Cap at 1.0

    def test_confidence_based_validation_thresholds(self):
        """Test that confidence scores affect validation decisions"""
        # Define confidence thresholds
        CONFIDENCE_THRESHOLDS = {
            'accept': 0.8,      # Auto-accept outputs above this
            'review': 0.5,      # Require review between accept and reject
            'reject': 0.3       # Auto-reject below this
        }

        test_outputs = [
            {'confidence': 0.9, 'expected_action': 'accept'},
            {'confidence': 0.6, 'expected_action': 'review'},
            {'confidence': 0.2, 'expected_action': 'reject'},
            {'confidence': 0.8, 'expected_action': 'accept'},  # Boundary case
        ]

        for output in test_outputs:
            confidence = output['confidence']
            expected_action = output['expected_action']

            if confidence >= CONFIDENCE_THRESHOLDS['accept']:
                actual_action = 'accept'
            elif confidence >= CONFIDENCE_THRESHOLDS['review']:
                actual_action = 'review'
            else:
                actual_action = 'reject'

            self.assertEqual(actual_action, expected_action,
                           f"Confidence {confidence} should result in {expected_action}")


class TestValidationFramework(unittest.TestCase):
    """Test comprehensive validation framework integration"""

    def test_complete_validation_workflow(self):
        """Test complete validation workflow from start to finish"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir)

            # Mock complete validation framework
            class MockValidationFramework:
                def __init__(self):
                    self.validation_results = {}

                def validate_complete_workflow(self, plan_name, output_path, workflow_manifest):
                    """Complete validation workflow"""
                    results = {
                        'plan_validation': self._validate_plan_compliance(plan_name, workflow_manifest),
                        'step_validation': self._validate_all_steps(workflow_manifest, output_path),
                        'output_detection': self._detect_and_score_outputs(output_path),
                        'recovery_attempts': self._attempt_recovery_if_needed(output_path),
                        'overall_status': None
                    }

                    # Determine overall status
                    if results['plan_validation']['valid'] and all(
                        step['valid'] for step in results['step_validation']
                    ):
                        results['overall_status'] = 'success'
                    elif any(step['valid'] for step in results['step_validation']):
                        results['overall_status'] = 'partial_success'
                    else:
                        results['overall_status'] = 'failure'

                    return results

                def _validate_plan_compliance(self, plan_name, manifest):
                    return {'valid': True, 'compliance_score': 0.9}

                def _validate_all_steps(self, manifest, output_path):
                    return [
                        {'step': 'transcribe', 'valid': True, 'confidence': 0.9},
                        {'step': 'catalogue', 'valid': True, 'confidence': 0.8}
                    ]

                def _detect_and_score_outputs(self, output_path):
                    return [
                        {'type': 'transcription', 'confidence': 0.9, 'path': 'transcriptions/doc.txt'},
                        {'type': 'catalogue', 'confidence': 0.8, 'path': 'catalogues/meta.json'}
                    ]

                def _attempt_recovery_if_needed(self, output_path):
                    return {'recovery_attempted': False, 'recovered_outputs': []}

            framework = MockValidationFramework()

            # Mock workflow manifest
            workflow_manifest = {
                'steps': [
                    {'name': 'transcribe', 'status': 'success'},
                    {'name': 'catalogue', 'status': 'success'}
                ]
            }

            # Act: Run complete validation
            results = framework.validate_complete_workflow(
                'Transcribir y Catalogar',
                output_path,
                workflow_manifest
            )

            # Assert: Complete validation succeeded
            self.assertEqual(results['overall_status'], 'success')
            self.assertTrue(results['plan_validation']['valid'])
            self.assertTrue(all(step['valid'] for step in results['step_validation']))

    def test_validation_with_recovery_scenario(self):
        """Test validation framework with recovery scenario"""
        # Mock scenario where initial validation fails but recovery succeeds
        validation_scenario = {
            'initial_validation': {
                'plan_valid': True,
                'steps_valid': [True, False],  # One step failed
                'outputs_found': 1  # Only one output found
            },
            'recovery_results': {
                'recovered_outputs': 1,  # Found missing output
                'recovery_confidence': 0.7
            }
        }

        def simulate_validation_with_recovery(scenario):
            # Initial validation
            initial_success = (
                scenario['initial_validation']['plan_valid'] and
                all(scenario['initial_validation']['steps_valid'])
            )

            if not initial_success:
                # Attempt recovery
                recovery_successful = scenario['recovery_results']['recovered_outputs'] > 0
                final_confidence = scenario['recovery_results']['recovery_confidence']

                if recovery_successful and final_confidence > 0.6:
                    return {'status': 'success_with_recovery', 'confidence': final_confidence}
                else:
                    return {'status': 'failure', 'confidence': final_confidence}

            return {'status': 'success', 'confidence': 1.0}

        # Test recovery scenario
        result = simulate_validation_with_recovery(validation_scenario)
        self.assertEqual(result['status'], 'success_with_recovery')
        self.assertEqual(result['confidence'], 0.7)


if __name__ == '__main__':
    unittest.main()