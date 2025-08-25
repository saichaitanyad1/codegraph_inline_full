# Graph Builder Tests

This directory contains comprehensive tests for the `graph_builder.py` module from the codegraph package.

## Test Files

- **`test_graph_builder.py`** - Main test suite with comprehensive test cases
- **`run_tests.py`** - Simple test runner script for easy execution

## Running the Tests

### Option 1: Using the test runner script (Recommended)
```bash
python run_tests.py
```

### Option 2: Using Python's unittest directly
```bash
python -m unittest test_graph_builder.py -v
```

### Option 3: Running the test file directly
```bash
python test_graph_builder.py
```

## Test Coverage

The test suite covers the following functionality:

### `build_graph_from_repo()` function
- ✅ Building graphs from empty directories
- ✅ Processing Java files
- ✅ Processing Python files
- ✅ Automatic language detection
- ✅ Error handling for parse failures
- ✅ Ignoring unsupported file types
- ✅ Integration testing with mocked parsers

### `derive_overrides()` function
- ✅ Simple inheritance relationships
- ✅ Multi-level inheritance chains
- ✅ Method arity matching for overrides
- ✅ No overrides when no inheritance exists

## Test Structure

Each test method follows the Arrange-Act-Assert pattern:
1. **Arrange**: Set up test data and fixtures
2. **Act**: Execute the function being tested
3. **Assert**: Verify the expected outcomes

## Dependencies

The tests use Python's built-in `unittest` module and `unittest.mock` for mocking external dependencies. No additional testing frameworks are required.

## Mocking Strategy

The tests use mocking to isolate the `graph_builder` module from external dependencies:
- `parse_java_source()` is mocked to return predefined nodes and edges
- `parse_python_source()` is mocked to return predefined nodes and edges
- `resolve_calls_java()` is mocked to avoid actual Java resolution logic

This allows testing the graph building logic without requiring actual Java/Python parsing or external tools.

## Adding New Tests

To add new tests:

1. Add new test methods to the `TestGraphBuilder` class
2. Follow the naming convention: `test_<function_name>_<scenario>`
3. Use descriptive docstrings explaining what each test validates
4. Ensure proper setup and teardown in `setUp()` and `tearDown()` methods

## Example Test Method

```python
def test_new_functionality(self):
    """Test description of what this test validates"""
    # Arrange - Set up test data
    test_data = "some test data"
    
    # Act - Execute the function
    result = some_function(test_data)
    
    # Assert - Verify the result
    self.assertEqual(result, expected_value)
```

## Troubleshooting

### Import Errors
If you encounter import errors, make sure:
- You're running the tests from the project root directory
- The `codegraph` package is in your Python path
- All required dependencies are installed

### Test Failures
- Check the test output for detailed error messages
- Verify that the mocked functions return the expected data
- Ensure test data matches the expected graph structure
