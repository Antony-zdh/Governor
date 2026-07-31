# TJE top-1 through top-6 threshold readout bank

This experiment varies the TJE stopping threshold over the highest one through
six official confidence classes. The faithful TJE baseline stops only at
`Almost certain` (top-1). The additional policies accept the first label in:

| Policy | Lowest accepted label |
|---|---|
| top-1 | Almost certain |
| top-2 | Highly likely |
| top-3 | Very good chance |
| top-4 | Likely |
| top-5 | Better than even |
| top-6 | Less than even |

TJE has no DEER-style maximum of ten Wait probes. Its primary trigger policy
checks every whole-word `Wait` and the final `</think>`. The faithful artifacts
already contain every confidence label before the first `Almost certain`, or
all labels if that level is never reached. Lower thresholds therefore require
no new confidence queries. The GPU experiment generates only the missing final
readout at each distinct first-crossing position and reuses the faithful
top-1 readout whenever possible.

Across two models, three benchmarks, six seeds, and both full/test scopes, the
bank covers 3,420 trajectories and expects 4,366 new unique readouts. Every
confidence probe and generated readout output token is charged during replay.
The result is a discrete TJE frontier; it does not change the immutable
faithful TJE point.
