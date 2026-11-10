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


# A loop rather than two statements on two lines, and the difference is the
# whole detector: two lines are two call paths and no N+1, while a loop is one
# path executed twice and therefore a finding. The inner test knows none of
# that -- it just expects one query and does two.
_TWO_QUERIES_ONE_EXPECTED = """
    import pytest
    from django.db import connection

    @pytest.mark.django_db
    def test_counts(django_assert_num_queries):
        with django_assert_num_queries(1):
            with connection.cursor() as cursor:
                for _ in range(2):
                    cursor.execute("SELECT 1")
"""

# Two statements on two lines, which is the other half of the pair above: two
# call paths, so no repetition, so no finding -- and the section still has to
# name where the extra statement came from.
_TWO_LINES_ONE_EXPECTED = """
    import pytest
    from django.db import connection

    @pytest.mark.django_db
    def test_counts(django_assert_num_queries):
        with django_assert_num_queries(1):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.execute("SELECT 2")
"""

_A_LOOP = """
    import pytest
    from django.db import connection

    @pytest.mark.django_db
    def test_loops():
        with connection.cursor() as cursor:
            for _ in range(3):
                cursor.execute("SELECT 1")
"""


def test_a_failed_count_assertion_gains_a_diagnosis(django_pytester: pytest.Pytester) -> None:
    """The whole seam: their assertion fails, our paragraph appears underneath it."""
    django_pytester.makepyfile(_TWO_QUERIES_ONE_EXPECTED)
    result = django_pytester.runpytest_subprocess()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*Expected to perform 1 queries but 2 were done*",
            "*django-query-contract*",
            "*2 statements captured: 2 on 'default'.*",
            "*N+1 -- one statement shape, executed more than once from one call path:*",
            "*2 x  from *test_a_failed_count_assertion_gains_a_diagnosis.py:*",
            "*queries #0, #1*",
        ]
    )


def test_a_failure_with_no_n_plus_one_still_names_the_lines(
    django_pytester: pytest.Pytester,
) -> None:
    """Two statements from two lines: no call path repeated, so no finding at all."""
    django_pytester.makepyfile(_TWO_LINES_ONE_EXPECTED)
    result = django_pytester.runpytest_subprocess()

    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*django-query-contract*",
            "*2 statements captured: 2 on 'default'.*",
            "*No N+1: no statement shape repeated from a single call path.*",
            "*2 statement(s) were not repeated from any one call path. They came from:*",
            "*1 x  from *test_a_failure_with_no_n_plus_one_still_names_the_lines.py:*",
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
    """Depth one keeps only the innermost frame, which is inside Django."""
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
    result.stdout.fnmatch_lines(
        ["*from no frame outside Django (the capture*s stack depth did not reach one)*"]
    )


def test_a_block_above_the_ceiling_warns_even_when_it_passes(
    django_pytester: pytest.Pytester,
) -> None:
    """The case the warning exists for: a green test whose count was never real."""
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

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(
        ["*QueryLogCeilingWarning: *5 statements ran on connection 'default'*reports 0 *"]
    )


def test_one_test_filling_the_log_does_not_make_the_next_one_warn(
    django_pytester: pytest.Pytester,
) -> None:
    """The leak this package closes, and the whole of what closing it changes."""
    django_pytester.makeconftest(
        """
        from collections import deque

        import pytest
        from django.db import connection


        @pytest.fixture(autouse=True, scope="session")
        def small_query_log(django_db_setup):
            connection.queries_limit = 5
            connection.queries_log = deque(maxlen=5)
            connection.force_debug_cursor = True
        """
    )
    django_pytester.makepyfile(
        """
        import pytest
        from django.db import connection

        @pytest.mark.django_db
        def test_fills_the_log():
            with connection.cursor() as cursor:
                for _ in range(6):
                    cursor.execute("SELECT 1")

        def test_is_innocent(django_db_blocker):
            with django_db_blocker.unblock(), connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        """
    )
    result = django_pytester.runpytest_subprocess()

    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(["*QueryLogCeilingWarning: *test_fills_the_log: 6 statements ran*"])
    result.stdout.no_fnmatch_line("*test_is_innocent: 1 statements ran*")


def test_the_inner_runs_collect_no_coverage(django_pytester: pytest.Pytester) -> None:
    """The fix above, asserted rather than assumed."""
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


def test_the_flag_lists_what_the_run_found(django_pytester: pytest.Pytester) -> None:
    """The listing, and the fact that asking for it changes no outcome."""
    django_pytester.makepyfile(_A_LOOP)
    result = django_pytester.runpytest_subprocess("--n-plus-one")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(
        [
            "*django-query-contract*",
            "*1 N+1 finding(s), most repeated first:*",
            "*3 x  from *test_the_flag_lists_what_the_run_found.py:*",
            "*in test_the_flag_lists_what_the_run_found.py::test_loops*",
        ]
    )


def test_the_flag_says_so_when_the_run_found_nothing(django_pytester: pytest.Pytester) -> None:
    """No N+1 anywhere is the answer somebody ran this to get."""
    django_pytester.makepyfile(
        """
        import pytest
        from django.db import connection

        @pytest.mark.django_db
        def test_one_query():
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        """
    )
    result = django_pytester.runpytest_subprocess("--n-plus-one")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*No N+1: no statement shape repeated from a single call path.*"])


def test_without_the_flag_the_run_says_nothing(django_pytester: pytest.Pytester) -> None:
    """A passing suite full of N+1s prints not one word about them unless asked."""
    django_pytester.makepyfile(_A_LOOP)
    result = django_pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)
    assert "N+1" not in result.stdout.str()


_A_PLAN_TEST = """
    import pytest
    from django.db import connection

    @pytest.mark.django_db
    def test_plans(query_plans):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
"""


def test_a_plan_test_on_sqlite_skips_with_the_reason_rather_than_passing(
    django_pytester: pytest.Pytester,
) -> None:
    """The whole "never pass vacuously" claim, in a real run rather than in prose."""
    django_pytester.makepyfile(_A_PLAN_TEST)
    result = django_pytester.runpytest_subprocess("-rs")

    result.assert_outcomes(skipped=1, passed=0, failed=0)
    result.stdout.fnmatch_lines(["*Plan capture needs PostgreSQL*"])
