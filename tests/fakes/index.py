"""A fixed estate INDEX for the reverse direction, reachable as a --dependents-resolver.

``fakes.estate`` answers "what is this member?"; this answers the other direction, "what
depends on this resource?". The CLI's door takes MODULE:FUNC, so exercising it end to end
needs a resolver that can be IMPORTED by name rather than passed in as a callable - which
is the whole point of the flag, and the reason a gathered bundle has to record what it
answered.

Deliberately narrow: it covers one FILE the appregn deck defines and nothing else. A name
it does not cover returns None - NOT ANSWERED - which is what keeps the three answers
distinguishable in a test.
"""

#: Keyed (name, kind) exactly as the lookup asks - the manifest kind, not the CSD word.
INDEX = {
    ("CUSTMAS", "file"): [
        {"name": "CUSTINQ1", "kind": "PROGRAM", "via": "READ FILE",
         "match_strength": "qualified", "detail": "one site, in the inquiry transaction"},
    ],
}


def dependents(name, kind=None):
    """What the index says depends on ``name``, or None for a name it does not cover."""
    return INDEX.get((name, kind))
