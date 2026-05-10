```markdown
# second-brain Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches the core development patterns and conventions used in the `second-brain` Python repository. You'll learn how to structure files, write code, follow commit conventions, and organize tests as practiced in this codebase. The repository uses Python without a specific framework, and emphasizes clarity, modularity, and maintainability.

## Coding Conventions

### File Naming
- Use **camelCase** for file names.
  - Example: `noteManager.py`, `dataLoader.py`

### Import Style
- Use **relative imports** for modules within the project.
  - Example:
    ```python
    from .utils import parseData
    ```

### Export Style
- Use **named exports** (i.e., explicitly define what is exported from a module).
  - Example:
    ```python
    def processNote(note):
        # logic here
        return processed

    __all__ = ['processNote']
    ```

### Commit Messages
- Follow the **Conventional Commits** style.
- Use the `feat` prefix for new features.
- Keep commit messages concise (average ~76 characters).
  - Example:
    ```
    feat: add support for tagging notes with multiple labels
    ```

## Workflows

### Feature Development
**Trigger:** When adding a new feature or module  
**Command:** `/feature-development`

1. Create a new file using camelCase naming.
2. Implement the feature using relative imports for dependencies.
3. Export functions or classes using named exports.
4. Write or update corresponding test files (`*.test.*`).
5. Commit changes using the `feat:` prefix and a concise message.

### Testing
**Trigger:** When writing or running tests  
**Command:** `/run-tests`

1. Create test files following the `*.test.*` pattern (e.g., `noteManager.test.py`).
2. Write test cases for each exported function or class.
3. Run tests using the project's preferred test runner (framework not specified; use `pytest` or `unittest` as appropriate).

## Testing Patterns

- Test files are named with the `*.test.*` pattern.
  - Example: `noteManager.test.py`
- Each test file should target a specific module or feature.
- The testing framework is not specified; use standard Python testing practices.
- Example test structure:
  ```python
  import unittest
  from .noteManager import processNote

  class TestProcessNote(unittest.TestCase):
      def test_basic(self):
          note = "Sample note"
          result = processNote(note)
          self.assertIsNotNone(result)

  if __name__ == '__main__':
      unittest.main()
  ```

## Commands
| Command              | Purpose                                 |
|----------------------|-----------------------------------------|
| /feature-development | Start a new feature/module workflow     |
| /run-tests           | Run all tests in the repository         |
```