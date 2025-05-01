Implement the following: $ARGUMENTS.

Important: Do not try to run the tests.

Follow these steps:
1. Understand the functional spec and tests described
2. Create the project structure and files
3. Implement a solution that addresses the functional spec
4. Implement tests
5. Prepare a concise PR title and description
6. Create a new branch with the change and make a push to origin

Check the following before push:
- Exclude the `.claude` folder from the commit.
- Decorate fixtures (e.g., `client`) with `@pytest.fixture`.
- Decorate test functions with `@pytest.mark.testcase("test_name_here")`.
- Place all tests inside the `tests/` folder.
- Add a `requirements.txt` without specifying library versions (include test dependencies).
- Default to Python, Flask, and in-memory DB unless otherwise specified.
- Include `azure-pipelines.yml` in the commit.