#!/usr/bin/env python3
"""
Simple test runner for the graph_builder tests
"""

import sys
import os

# Add the current directory to the path so we can import the test module
sys.path.insert(0, os.path.dirname(__file__))

if __name__ == '__main__':
    print("Running graph_builder tests...")
    print("=" * 50)
    
    try:
        # Import and run the tests
        from test_graph_builder import TestGraphBuilder
        import unittest
        
        # Create test suite
        suite = unittest.TestLoader().loadTestsFromTestCase(TestGraphBuilder)
        
        # Run tests with verbose output
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        # Print summary
        print("\n" + "=" * 50)
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  {test}: {traceback}")
        
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  {test}: {traceback}")
        
        # Exit with appropriate code
        if result.wasSuccessful():
            print("\n✅ All tests passed!")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed!")
            sys.exit(1)
            
    except ImportError as e:
        print(f"Error importing test module: {e}")
        print("Make sure you're in the correct directory and all dependencies are installed.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
