# django-query-contract

A query-capture engine for Django, and a pytest plugin over it.

See the [README](https://github.com/Artui/django-query-contract#readme) for the
overview, [N+1 detection](n-plus-one.md) for the detector and how a finding is
defined, [growth assertions](growth.md) for asserting a count is `O(1)` rather
than `O(N)`, [call-site attribution](attribution.md) for asking any statement
where it came from, [plan capture](plans.md) for what PostgreSQL did with a
statement and what it got wrong about it, and the
[API reference](reference.md) for the capture record.
