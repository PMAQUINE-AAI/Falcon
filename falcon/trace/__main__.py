"""Point d'entree du paquet : `python -m falcon.trace <trace.vbs>`.

Module separe plutot que `python -m falcon.trace.inventaire` : executer un
sous-module d'un paquet qui l'importe deja fait charger ce module deux fois,
et Python le signale par un avertissement a l'execution. Un outil de
diagnostic qui commence par un avertissement inspire mal confiance.
"""

from __future__ import annotations

from .inventaire import main

raise SystemExit(main())
