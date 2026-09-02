"""The pytest face, observed from outside a real run.

A report section and a warning only exist in the run that produced them, so
these drive pytest inside pytest. Subprocess rather than in-process: Django's
settings are configured once per interpreter, and an inner run sharing this
one's would be measuring a process that had already been set up.
"""

from __future__ import annotations

import os

import pytest

_SETTINGS = """
SECRET_KEY = "x"
INSTALLED_APPS = ["django.contrib.contenttypes", "django.contrib.auth"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
USE_TZ = True
"""


@pytest.fixture
def isolated_pytester(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> pytest.Pytester:
    """A pytester whose subprocess inherits neither the settings nor the coverage of this run.

    **Django settings.** pytest-django exports ``DJANGO_SETTINGS_MODULE`` into
    the environment, and a subprocess inherits it -- so without this every inner
    run would quietly be configured by the outer one, and the test for a project
    with no Django settings at all would be measuring the opposite of what it
    claims.

    **Coverage.** pytest-cov instruments subprocesses through a ``.pth`` hook
    that reads a ``COV_CORE_*`` environment, and the data those inner runs write
    is unusable here for a reason that is structural rather than incidental:
    ``branch`` is propagated only from the ``--cov-branch`` command-line flag
    (``pytest_cov/engine.py``, ``if self.cov_branch``), and this project
    declares ``branch = true`` in ``pyproject.toml`` instead. The subprocess is
    also pointed at no config file -- ``COV_CORE_CONFIG`` is set to a separator
    when ``.coveragerc`` does not exist -- so it rediscovers configuration from
    its own working directory, which is the pytester temp directory and holds no
    ``pyproject.toml``. Each inner run therefore writes **statement** data into
    the parent's **branch** data file, and the combine at the end of the session
    fails with ``Can't combine statement coverage data with branch data``.

    Clearing the environment is the fix rather than a workaround, and the reason
    is what these runs are for. They exist to prove *behaviour* that only exists
    in a real run -- a report section, a captured warning, a flag that silences
    both. Every branch of every hook is covered in-process by
    ``test_plugin_hooks.py`` with real ``Config``, ``Item``, ``TestReport`` and
    ``pluggy.Result`` objects. Letting a subprocess contribute coverage would
    mean a hook branch could be covered by a run this process cannot introspect,
    so ``test_plugin_hooks.py`` could rot while the number stayed at 100%. The
    gate is stricter without it.
    """
    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
    # By prefix rather than by name: the set of these has changed across
    # pytest-cov releases, and a fix for a floor job must not itself be pinned
    # to a version. COVERAGE_PROCESS_START is coverage's own equivalent hook.
    for name in [key for key in os.environ if key.startswith("COV_CORE_")]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("COVERAGE_PROCESS_START", raising=False)
    return pytester


@pytest.fixture
def django_pytester(isolated_pytester: pytest.Pytester) -> pytest.Pytester:
    """A throwaway project with Django settings and nothing else."""
    isolated_pytester.makepyfile(inner_settings=_SETTINGS)
    isolated_pytester.makeini("[pytest]\nDJANGO_SETTINGS_MODULE = inner_settings\n")
    isolated_pytester.syspathinsert()
    return isolated_pytester


_TWO_QUERIES_ONE_EXPECTED = """
    import pytest
    from django.db import connection

    @pytest.mark.django_db
    def test_counts(django_assert_num_queries):
        with django_assert_num_queries(1):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.execute("SELECT 1")
"""


def test_a_failed_count_assertion_gains_a_diagnosis(django_pytester: pytest.Pytester) -> None:
    """The whole seam: their assertion fails, our paragraph appears underneath it.

    Nothing in the inner test knows this package exists. That is the point --
    the assertion a reader already writes is the one that gets better.
    """
    django_pytester.makepyfile(_TWO_QUERIES_ONE_EXPECTED)
    result = django_pytester.runpytest_subprocess()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*Expected to perform 1 queries but 2 were done*",
            "*django-query-contract*",
            "*2 statements captured: 2 on 'default'.*",
            "*2 x  #0, #1*",
        ]
    )


def test_a_passing_test_gains_nothing(django_pytester: pytest.Pytester) -> None:
    """Capture is silent unless something failed or a ceiling was crossed."""
    django_pytester.makepyfile(
        """
        import pytest
        from django.db import connection

        @pytest.mark.django_db
        def test_counts(django_assert_num_queries):
            with django_assert_num_queries(1):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
        """
    )
    result = django_pytester.runpytest_subprocess("-rA")

    result.assert_outcomes(passed=1)
    assert "statements captured" not in result.stdout.str()


def test_a_failure_with_no_queries_gains_nothing(django_pytester: pytest.Pytester) -> None:
    """A failure unrelated to the database does not acquire a paragraph about it."""
    django_pytester.makepyfile(
        """
        def test_unrelated():
            assert False
        """
    )
    result = django_pytester.runpytest_subprocess()

    result.assert_outcomes(failed=1)
    assert "statements captured" not in result.stdout.str()


def test_the_flag_turns_capture_off_for_one_run(django_pytester: pytest.Pytester) -> None:
    django_pytester.makepyfile(_TWO_QUERIES_ONE_EXPECTED)
    result = django_pytester.runpytest_subprocess("--no-query-contract")

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*Expected to perform 1 queries but 2 were done*"])
    assert "statements captured" not in result.stdout.str()


def test_the_ini_turns_capture_off_for_a_project(django_pytester: pytest.Pytester) -> None:
    django_pytester.makeini(
        "[pytest]\nDJANGO_SETTINGS_MODULE = inner_settings\nquery_contract = false\n"
    )
    django_pytester.makepyfile(_TWO_QUERIES_ONE_EXPECTED)
    result = django_pytester.runpytest_subprocess()

    result.assert_outcomes(failed=1)
    assert "statements captured" not in result.stdout.str()


def test_the_stack_depth_ini_reaches_the_capture(django_pytester: pytest.Pytester) -> None:
    """Depth one keeps only the innermost frame, which is inside Django.

    An indirect assertion, and the only one available from outside: the ini is
    observable purely through what the call site becomes.
    """
    django_pytester.makeini(
        "[pytest]\nDJANGO_SETTINGS_MODULE = inner_settings\nquery_contract_stack_depth = 1\n"
    )
    django_pytester.makepyfile(
        """
        import pytest
        from django.contrib.contenttypes.models import ContentType

        @pytest.mark.django_db
        def test_counts(django_assert_num_queries):
            with django_assert_num_queries(1):
                list(ContentType.objects.all())
                list(ContentType.objects.all())
        """
    )
    result = django_pytester.runpytest_subprocess()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*from no frame outside Django (stack empty or truncated)*"])


def test_a_block_above_the_ceiling_warns_even_when_it_passes(
    django_pytester: pytest.Pytester,
) -> None:
    """The case the warning exists for: a green test whose count was never real.

    ``django_assert_max_num_queries(1)`` passes over five statements, because the
    log it counts through was already full. A report section would not be shown
    for a passing test; a warning is.
    """
    # The log is filled in a fixture, not in the test body: capture opens
    # between setup and the call, so a limit changed inside the test would be
    # read after the ceiling had already been measured. Filling it during setup
    # is also what a real suite does -- an earlier assertion in the same test.
    django_pytester.makeconftest(
        """
        from collections import deque

        import pytest
        from django.db import connection


        @pytest.fixture(autouse=True)
        def full_query_log():
            connection.queries_limit = 3
            connection.queries_log = deque(
                [{"sql": "SELECT 1", "time": "0.000"}] * 3, maxlen=3
            )
            connection.force_debug_cursor = True
        """
    )
    django_pytester.makepyfile(
        """
        import pytest
        from django.db import connection

        @pytest.mark.django_db
        def test_over_the_ceiling(django_assert_max_num_queries):
            with django_assert_max_num_queries(1):
                with connection.cursor() as cursor:
                    for _ in range(5):
                        cursor.execute("SELECT 1")
        """
    )
    result = django_pytester.runpytest_subprocess()

    # Only the outcome is pinned, not the warning count: Django emits one of its
    # own from ``connection.queries`` when the log is full, and whether it does
    # is a detail of a version we support six of.
    result.assert_outcomes(passed=1)
    # One pattern, because the whole warning is one line in the summary.
    result.stdout.fnmatch_lines(
        ["*QueryLogCeilingWarning: *5 statements ran on connection 'default'*reports 0 *"]
    )


def test_the_inner_runs_collect_no_coverage(django_pytester: pytest.Pytester) -> None:
    """The fix above, asserted rather than assumed.

    pytest-cov instruments a subprocess through a ``.pth`` hook keyed on this
    environment, and the data it would write here is statement-only where the
    parent's is branch data -- an unusable combination that surfaced only at the
    declared dependency floor, in a job that runs once per pull request and long
    after the edit that caused it. Checking the environment from inside an inner
    run turns that into a failure in the file that owns the decision.

    By prefix, not by name, for the same reason the fixture clears it that way:
    the set of these variables has changed across pytest-cov releases.
    """
    django_pytester.makepyfile(
        """
        import os

        def test_the_environment_is_clear():
            leaked = sorted(key for key in os.environ if key.startswith("COV_CORE_"))
            assert leaked == [], leaked
            assert "COVERAGE_PROCESS_START" not in os.environ
        """
    )
    result = django_pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)


def test_a_suite_without_django_settings_is_left_alone(
    isolated_pytester: pytest.Pytester,
) -> None:
    """Installed beside a project that does not configure Django, and silent about it."""
    isolated_pytester.makepyfile(
        """
        def test_plain():
            assert 1 + 1 == 2
        """
    )
    result = isolated_pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)
