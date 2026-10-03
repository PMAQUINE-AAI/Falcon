"""Seul accès COM à SAP GUI. Validé en exécution réelle, pas de test unitaire."""
import logging
from typing import Any

log = logging.getLogger("falcon.sap")


def attacher(connexion: int = 0, session: int = 0) -> "Session":
    import win32com.client  # ici et pas en tête : le module doit s'importer hors Windows

    # GetObject("SAPGUI"), GetScriptingEngine, Children(i) : vus dans la trace.
    moteur = win32com.client.GetObject("SAPGUI").GetScriptingEngine
    brute = moteur.Children(connexion).Children(session)
    log.debug("attacher connexion=%s session=%s", connexion, session)
    return Session(moteur, brute)


class Session:
    def __init__(self, moteur: Any, session: Any):
        self._moteur = moteur
        self._session = session

    def _objet(self, id: str, action: str) -> Any:
        try:
            return self._session.findById(id)
        except Exception as e:
            raise type(e)(f"{action} {id} : {e}") from e

    def _agir(self, id: str, action: str, f) -> Any:
        try:
            return f()
        except Exception as e:
            raise type(e)(f"{action} {id} : {e}") from e

    def objet(self, id: str) -> Any:
        """Objet COM brut, pour la lecture (ex. arborescence)."""
        return self._objet(id, "findById")

    def definir(self, id: str, propriete: str, valeur: Any) -> None:
        log.debug("%s definir %s=%r", id, propriete, valeur)
        o = self._objet(id, "definir")
        self._agir(id, f"definir {propriete}", lambda: setattr(o, propriete, valeur))

    def presser(self, id: str) -> None:
        log.debug("%s presser", id)
        o = self._objet(id, "presser")
        self._agir(id, "presser", o.press)

    def touche(self, n: int, fenetre: str = "wnd[0]") -> None:
        log.debug("%s sendVKey %s", fenetre, n)
        o = self._objet(fenetre, "sendVKey")
        self._agir(fenetre, f"sendVKey {n}", lambda: o.sendVKey(n))

    def appeler(self, id: str, methode: str, *args: Any) -> Any:
        log.debug("%s appeler %s%r", id, methode, args)
        o = self._objet(id, f"appeler {methode}")
        return self._agir(id, f"appeler {methode}", lambda: getattr(o, methode)(*args))

    def statut(self) -> tuple[str, str]:
        # sbar, MessageType, Text : non vérifié sur SAP
        id = "wnd[0]/sbar"
        o = self._objet(id, "statut")
        r = self._agir(id, "statut", lambda: (str(o.MessageType), str(o.Text)))
        log.debug("%s statut %r", id, r)
        return r

    def titre(self, fenetre: str = "wnd[0]") -> str:
        # Text d'une fenêtre : non vérifié sur SAP
        o = self._objet(fenetre, "titre")
        t = self._agir(fenetre, "titre", lambda: str(o.Text))
        log.debug("%s titre %r", fenetre, t)
        return t

    def fenetres(self) -> list[str]:
        # Children d'une session, Id d'un enfant : non vérifié sur SAP
        def lire():
            enfants = self._session.Children
            return [enfants(i).Id for i in range(enfants.Count)]
        ids = self._agir("session", "fenetres", lire)
        log.debug("fenetres %r", ids)
        return [i.rsplit("/", 1)[-1] for i in ids]

    def infos(self) -> dict:
        """Chaque lecture échoue séparément : l'erreur est logguée, pas levée."""
        # Tous ces noms sont non vérifiés sur SAP.
        d: dict = {}
        lectures = {
            "sapgui_version": lambda: "%s.%s.%s" % (
                self._moteur.MajorVersion, self._moteur.MinorVersion,
                self._moteur.Revision),
            "scripting_actif": lambda: self._moteur.Children(0).Parent is not None,
        }
        for champ, attribut in [("systeme", "SystemName"), ("mandant", "Client"),
                                ("utilisateur", "User"), ("transaction", "Transaction"),
                                ("langue", "Language")]:
            lectures[champ] = lambda a=attribut: getattr(self._session.Info, a)
        for champ, f in lectures.items():
            try:
                d[champ] = f()
            except Exception as e:
                d[champ] = None
                log.warning("infos %s illisible : %s", champ, e)
        log.debug("infos %r", d)
        return d
