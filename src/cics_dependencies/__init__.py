"""cics-dependencies - the definition side of the mainframe dependency family.

The COBOL says what a program does, the JCL says which dataset a batch ddname is, the
Easytrieve says which bytes become which, the assembler says what a module calls - and
this says what the CICS region wires those names to: which program a transaction runs,
which VSAM dataset is behind a file name, which queue write starts a task.

Five peers. They share only ``mainframe_artifacts`` and meet at plain manifest dicts;
this package imports none of the others, and ``tests/test_boundaries.py`` enforces it.

Library logging contract, same as the rest of the family: a no-op handler on this
package's logger, so importing it never writes to stderr on its own.
"""

import logging as _logging

_logging.getLogger(__name__).addHandler(_logging.NullHandler())

__version__ = "0.1.0"

#: The shape of the manifest this package hands a COBOL or assembler front-end when it
#: closes their unresolved CICS rows (``views.bind_program_artifacts``). Their side
#: checks it at import time: a skewed pair fails INVISIBLY otherwise, because a manifest
#: nobody managed to bind looks exactly like one nobody tried to bind.
PROGRAM_BINDING_API_VERSION = 1

#: The shape of the JCL lineage view this package reads to recover a macro-era file's
#: dataset and the region's DFHRPL (``views.bind_jcl_region``). Same reasoning.
JCL_BINDING_API_VERSION = 1

__all__ = ["PROGRAM_BINDING_API_VERSION", "JCL_BINDING_API_VERSION", "__version__"]
