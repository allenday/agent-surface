# Releasing

Releases use PyPI Trusted Publisher authentication. Do not create GitHub secrets for PyPI tokens.

## One-time setup

Create GitHub environments named `testpypi` and `pypi`. Require a manual approver for `pypi`.

Register a pending Trusted Publisher on both package indexes with these values:

| Field | TestPyPI | PyPI |
| --- | --- | --- |
| Owner | `allenday` | `allenday` |
| Repository | `agent-surface` | `agent-surface` |
| Workflow | `release.yml` | `release.yml` |
| Environment | `testpypi` | `pypi` |

- TestPyPI: <https://test.pypi.org/manage/account/publishing/>
- PyPI: <https://pypi.org/manage/account/publishing/>

The two accounts are separate. Pending publishers can create the project during the first trusted
publication if the name remains available.

## Test publication

1. Open **Actions → Release → Run workflow**.
2. Run it from the commit containing the version in `pyproject.toml`.
3. Confirm the `testpypi` environment deployment.
4. Install from TestPyPI in a clean venv and run a smoke import.

## Production publication

1. Ensure `make check` passes and the version is not already present on PyPI.
2. Create and publish a GitHub Release tagged `v<version>` from the verified commit.
3. Approve the `pypi` environment deployment.
4. Verify the PyPI project and install the released wheel in a clean Python 3.12+ venv.

The release workflow builds one wheel and source distribution, then passes those immutable
artifacts to the appropriate publishing job. Only publishing jobs receive `id-token: write`.
