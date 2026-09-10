"""Producing a capture: what ran, where it came from, and what it cost to plan.

Everything that rides on ``connection.execute_wrapper`` lives here, together
with the fingerprint the wrapper computes per statement and the two classes the
capture raises -- a refusal when a plan could not mean anything, and a warning
when Django's own query log stopped being able to count.
"""
