#!/usr/bin/env python3
"""
Test script to verify transcription provider refactoring.

This script tests that:
1. All providers can be imported
2. Providers can be instantiated
3. Provider interface is consistent
4. Factory pattern works correctly
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test that all providers can be imported"""
    print("=" * 60)
    print("Testing Imports")
    print("=" * 60)

    try:
        from fichero.tools.transcribe_providers.base_provider import BaseTranscriptionProvider
        print("✅ BaseTranscriptionProvider imported")
    except Exception as e:
        print(f"❌ Failed to import BaseTranscriptionProvider: {e}")
        return False

    try:
        from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider
        print("✅ DashScopeProvider imported")
    except Exception as e:
        print(f"❌ Failed to import DashScopeProvider: {e}")
        return False

    try:
        from fichero.tools.transcribe_providers.openai_provider import OpenAIProvider
        print("✅ OpenAIProvider imported")
    except Exception as e:
        print(f"❌ Failed to import OpenAIProvider: {e}")
        return False

    try:
        from fichero.tools.transcribe_providers.lmstudio_provider import LMStudioProvider
        print("✅ LMStudioProvider imported")
    except Exception as e:
        print(f"❌ Failed to import LMStudioProvider: {e}")
        return False

    try:
        from fichero.tools.transcribe import ProviderFactory
        print("✅ ProviderFactory imported")
    except Exception as e:
        print(f"❌ Failed to import ProviderFactory: {e}")
        return False

    return True

def test_provider_instantiation():
    """Test that providers can be instantiated"""
    print("\n" + "=" * 60)
    print("Testing Provider Instantiation")
    print("=" * 60)

    from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider
    from fichero.tools.transcribe_providers.openai_provider import OpenAIProvider
    from fichero.tools.transcribe_providers.lmstudio_provider import LMStudioProvider

    # Test DashScope
    try:
        provider = DashScopeProvider(
            api_key="test-key",
            model="qwen-vl-max"
        )
        print(f"✅ DashScopeProvider instantiated: {provider.name}")
        print(f"   - Model: {provider.model}")
        print(f"   - Parallel support: {provider.supports_parallel}")
        print(f"   - Max file size: {provider.max_file_size_mb}MB")
        provider.cleanup()
    except Exception as e:
        print(f"❌ Failed to instantiate DashScopeProvider: {e}")
        return False

    # Test OpenAI
    try:
        provider = OpenAIProvider(
            api_key="test-key",
            model="qwen-vl-ocr"
        )
        print(f"✅ OpenAIProvider instantiated: {provider.name}")
        print(f"   - Model: {provider.model}")
        print(f"   - Parallel support: {provider.supports_parallel}")
        print(f"   - Max file size: {provider.max_file_size_mb}MB")
        provider.cleanup()
    except Exception as e:
        print(f"❌ Failed to instantiate OpenAIProvider: {e}")
        return False

    # Test LMStudio
    try:
        provider = LMStudioProvider(
            model_name="test-model"
        )
        print(f"✅ LMStudioProvider instantiated: {provider.name}")
        print(f"   - Model: {provider.model}")
        print(f"   - Parallel support: {provider.supports_parallel}")
        print(f"   - Max file size: {provider.max_file_size_mb}MB")
        provider.cleanup()
    except Exception as e:
        print(f"❌ Failed to instantiate LMStudioProvider: {e}")
        return False

    return True

def test_factory():
    """Test provider factory"""
    print("\n" + "=" * 60)
    print("Testing Provider Factory")
    print("=" * 60)

    from fichero.tools.transcribe import ProviderFactory

    # Test DashScope factory
    try:
        provider = ProviderFactory.create(
            "dashscope",
            api_key="test-key",
            model="qwen-vl-max"
        )
        print(f"✅ Factory created DashScope provider: {provider.name}")
        provider.cleanup()
    except Exception as e:
        print(f"❌ Factory failed for dashscope: {e}")
        return False

    # Test OpenAI factory
    try:
        provider = ProviderFactory.create(
            "openai",
            api_key="test-key",
            model="qwen-vl-ocr"
        )
        print(f"✅ Factory created OpenAI provider: {provider.name}")
        provider.cleanup()
    except Exception as e:
        print(f"❌ Factory failed for openai: {e}")
        return False

    # Test LMStudio factory
    try:
        provider = ProviderFactory.create(
            "lmstudio",
            model_name="test-model"
        )
        print(f"✅ Factory created LMStudio provider: {provider.name}")
        provider.cleanup()
    except Exception as e:
        print(f"❌ Factory failed for lmstudio: {e}")
        return False

    # Test invalid provider
    try:
        provider = ProviderFactory.create("invalid_provider")
        print("❌ Factory should have raised ValueError for invalid provider")
        return False
    except ValueError as e:
        print(f"✅ Factory correctly raised ValueError for invalid provider: {e}")

    return True

def test_interface_consistency():
    """Test that all providers implement the required interface"""
    print("\n" + "=" * 60)
    print("Testing Interface Consistency")
    print("=" * 60)

    from fichero.tools.transcribe_providers.base_provider import BaseTranscriptionProvider
    from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider
    from fichero.tools.transcribe_providers.openai_provider import OpenAIProvider
    from fichero.tools.transcribe_providers.lmstudio_provider import LMStudioProvider

    providers = [
        DashScopeProvider(api_key="test", model="qwen-vl-max"),
        OpenAIProvider(api_key="test", model="qwen-vl-ocr"),
        LMStudioProvider(model_name="test-model")
    ]

    required_methods = ["process_image", "validate_config", "cleanup"]
    required_properties = ["name", "model", "supports_parallel", "max_file_size_mb", "supported_formats"]

    all_pass = True
    for provider in providers:
        print(f"\nChecking {provider.__class__.__name__}...")

        # Check inheritance
        if not isinstance(provider, BaseTranscriptionProvider):
            print(f"  ❌ Does not inherit from BaseTranscriptionProvider")
            all_pass = False
        else:
            print(f"  ✅ Inherits from BaseTranscriptionProvider")

        # Check methods
        for method in required_methods:
            if not hasattr(provider, method):
                print(f"  ❌ Missing method: {method}")
                all_pass = False
            else:
                print(f"  ✅ Has method: {method}")

        # Check properties
        for prop in required_properties:
            if not hasattr(provider, prop):
                print(f"  ❌ Missing property: {prop}")
                all_pass = False
            else:
                try:
                    value = getattr(provider, prop)
                    print(f"  ✅ Has property: {prop} = {value}")
                except Exception as e:
                    print(f"  ❌ Property {prop} raised error: {e}")
                    all_pass = False

        provider.cleanup()

    return all_pass

def main():
    """Run all tests"""
    print("\n" + "🧪" * 30)
    print(" " * 15 + "PROVIDER REFACTORING TESTS")
    print("🧪" * 30 + "\n")

    tests = [
        ("Imports", test_imports),
        ("Provider Instantiation", test_provider_instantiation),
        ("Provider Factory", test_factory),
        ("Interface Consistency", test_interface_consistency)
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n🎉 All tests passed! Provider refactoring is ready.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
