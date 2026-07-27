"""Governor v2 related-work baselines (frozen-trajectory reproductions).

Three primary baseline families are implemented here, each replaying its
official probing/readout rule on the frozen Governor v2 development main
trajectories (no main generation is regenerated or modified):

* ``certaindex_mid``  -- CertaIndex faithful ``mid`` (dynasor/core/cot.py).
* ``tje``             -- Think Just Enough frozen-trajectory reproduction.
* ``deer``            -- DEER frozen-trajectory reproduction (iie-ycx/DEER).

The pure decision/parsing/accounting logic lives in each module and is
unit-testable without a GPU or live model endpoint. The live collectors
(openai client + tokenizer) are constructed lazily and only run when an
endpoint URL is provided.

Source pins:
    CertaIndex : in-repo ``dynasor/core/cot.py`` at commit dbe76ad
    TJE        : https://aclanthology.org/2026.findings-eacl.263 (Figure 2 / Section 2.2)
    DEER       : https://github.com/iie-ycx/DEER @ c9dd19fbffa27f841cfe47502d015b63811b4d1b
"""

from __future__ import annotations

from . import common  # noqa: F401
