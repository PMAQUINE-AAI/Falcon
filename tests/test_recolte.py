"""La recolte de la taxonomie, de l'inconnu bloquant a l'entree qui le classe.

Ce que ces tests protegent n'est pas une fonction, c'est un PARCOURS. Chaque
morceau existait deja et aucun n'etait relie : `Registre.charger` acceptait des
surcouches qu'aucun appelant de production ne passait, et le dump qui dirait
quoi ecrire dedans n'etait produit que si un appelant fournissait
`dossier_dumps` — ce que ni la console ni la CLI ne faisaient.

Le dernier test de ce fichier est celui qui compte : il deroule le parcours
entier contre le double, et il tomberait si n'importe lequel des maillons se
detachait.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from falcon.couture.double import DriverScripte
from falcon.moteur import executer
from falcon.noyau import Identite, Statut
from falcon.pipeline import charger
from falcon.taxonomie import Registre, RegistreInvalide
from falcon.taxonomie.recolte import (
    MARQUEUR, dumps_de, entree_proposee, lire_dump, surcouche_proposee,
)

IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")

PIPELINE = """version: 1
nom: essai
classe: iterative
cles: [site]
plafond_items: 50
plafond_sauvegardes: 50
etapes:
  - nom: saisir
    action: set
    cible: "wnd[0]/usr/ctxtWERKS-LOW"
    source: {colonne: site}
    ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}
    statut_attendu: "S"
"""


def _dump(dossier: Path, nom: str, **charge) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    chemin.write_text(json.dumps(charge, ensure_ascii=False), encoding="utf-8")
    return chemin


class TestLectureDUnDump(unittest.TestCase):
    """La forme du dump est celle que les gardes ECRIVENT, pas une conjecture.

    La premiere version de ce module lisait `detail["id"]` a plat. La garde de
    statut range le message sous `detail["statut"]`, si bien que tout message
    SAP etait classe sans son identite et nomme « statut » tout court. Le
    defaut a ete trouve en deroulant le parcours, pas en relisant le code —
    d'ou le test de bout en bout plus bas.
    """

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)

    def test_un_message_SAP_rattrape_par_une_garde(self):
        chemin = _dump(
            self.racine, "2026-09-08T10-00-00Z_inconnu.json",
            horodatage="2026-09-08T10:00:00Z", run_id="R1", item_id="i1",
            garde="statut",
            detail={"statut": {"type": "E", "id": "IW", "numero": "010",
                               "texte": "Equipement inexistant"},
                    "attendu": "S", "etape": "saisir"})
        inconnu = lire_dump(chemin)

        self.assertEqual(inconnu.canal, "garde")
        self.assertEqual(inconnu.nom_propose, "statut_iw_010")
        self.assertEqual(inconnu.correspondance["id"], "IW")
        self.assertEqual(inconnu.correspondance["numero"], "010")
        self.assertEqual(inconnu.texte_du_message, "Equipement inexistant")

    def test_l_etape_n_entre_PAS_dans_l_appariement(self):
        """Elle lierait l'entree au nom d'une etape d'une pipeline, alors que
        la meme erreur SAP se produira sous un autre nom ailleurs."""
        chemin = _dump(self.racine, "a.json", garde="statut",
                       detail={"statut": {"id": "IW", "numero": "010"},
                               "etape": "saisir"})
        self.assertNotIn("etape", lire_dump(chemin).correspondance)

    def test_le_LIBELLE_n_entre_pas_non_plus_dans_l_appariement(self):
        """« Equipement 10023456 inexistant » porte la valeur de l'item :
        apparier dessus ferait une entree par item."""
        chemin = _dump(self.racine, "a.json", garde="statut",
                       detail={"statut": {"id": "IW", "numero": "010",
                                          "texte": "Equipement 10023456 absent"}})
        self.assertNotIn("texte", lire_dump(chemin).correspondance)

    def test_le_CANAL_vient_de_la_signature_pas_du_nom_de_la_garde(self):
        """Le defaut le plus couteux de ce module, trouve en le deroulant.

        `garde` porte le NOM de la garde qui a parle, pas le canal. Un message
        `E` sans `statut_attendu` est classe par le registre sur le canal
        `statut`, alors que le dump porte `garde: "statut"`. Deduire le canal
        du nom donnait donc `garde`, et l'entree ecrite d'apres cette
        proposition n'aurait JAMAIS apparie — une recolte qui ne recolte rien,
        et qui en a l'air.
        """
        chemin = _dump(
            self.racine, "a.json", garde="statut",
            signature={"canal": "statut", "type": "E", "id": "IW",
                       "numero": "010", "garde": "statut"},
            detail={"statut": {"type": "E", "id": "IW", "numero": "010"}})
        inconnu = lire_dump(chemin)
        self.assertEqual(inconnu.canal, "statut")
        self.assertNotIn("garde", inconnu.correspondance)

    def test_le_contexte_d_ecran_est_propose_mais_COMMENTE(self):
        """L'activer restreint l'entree a cet ecran : c'est un choix qui
        depend de ce qu'on sait du message, donc il revient a l'humain."""
        chemin = _dump(
            self.racine, "a.json", garde="statut",
            signature={"canal": "garde", "garde": "statut", "id": "IW",
                       "contexte": {"transaction": "IA08",
                                    "programme": "RIPLKO10",
                                    "dynpro": "1000"}},
            detail={})
        texte = entree_proposee(lire_dump(chemin))
        self.assertIn("#   transaction: \"IA08\"", texte)
        self.assertNotIn("contexte:\n      transaction", texte)

    def test_le_canal_PYTHON_apparie_sur_l_exception_comme_com(self):
        """`_apparie` traite `com` et `python` de la meme facon : le nom
        d'exception. Les separer produisait, pour une `action: python` qui
        leve, une correspondance batie sur `garde` — que le comparateur ne
        regarde jamais sur ce canal."""
        chemin = _dump(self.racine, "a.json", garde="python",
                       signature={"canal": "python",
                                  "exception": "RuntimeError",
                                  "texte": "champ introuvable"},
                       detail={"etape": "maison",
                               "exception": "RuntimeError"})
        inconnu = lire_dump(chemin)
        self.assertEqual(inconnu.canal, "python")
        self.assertEqual(inconnu.correspondance, {"exception": "RuntimeError"})
        self.assertNotIn("garde", inconnu.correspondance)
        self.assertEqual(inconnu.nom_propose, "runtimeerror")

    def test_une_exception_COM(self):
        chemin = _dump(self.racine, "a.json", garde="",
                       detail={"exception": "SessionPerdue"})
        inconnu = lire_dump(chemin)
        self.assertEqual(inconnu.canal, "com")
        self.assertEqual(inconnu.correspondance, {"exception": "SessionPerdue"})

    def test_les_dumps_sortent_du_plus_recent_au_plus_ancien(self):
        _dump(self.racine, "2026-09-08T10-00-00Z_a.json", garde="x", detail={})
        _dump(self.racine, "2026-09-08T11-00-00Z_b.json", garde="x", detail={})
        noms = [c.name for c in dumps_de(self.racine)]
        self.assertEqual(noms[0], "2026-09-08T11-00-00Z_b.json")

    def test_un_dossier_absent_ne_leve_pas(self):
        """« Aucun dump » est une bonne nouvelle, pas une panne."""
        self.assertEqual(dumps_de(self.racine / "rien"), [])


class TestEntreeProposee(unittest.TestCase):

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)

    def _inconnu(self, **detail):
        return lire_dump(_dump(self.racine, "a.json",
                               horodatage="2026-09-08T10:00:00Z",
                               garde="statut", detail=detail))

    def test_les_valeurs_sont_TOUJOURS_entre_guillemets(self):
        """Un numero de message « 010 » sans guillemets se relit 8.

        Une proposition destinee a etre collee dans un fichier doit etre
        ecrite comme ce fichier doit l'etre — c'est le sujet de `yaml_strict`,
        et l'endroit ou l'oublier serait le plus couteux.
        """
        texte = entree_proposee(self._inconnu(
            statut={"id": "IW", "numero": "010"}))
        self.assertIn('numero: "010"', texte)

    def test_ce_qui_se_DECIDE_porte_un_marqueur(self):
        texte = entree_proposee(self._inconnu(statut={"id": "IW"}))
        for decision in ("categorie", "poursuivre", "item"):
            with self.subTest(champ=decision):
                ligne = next(l for l in texte.splitlines()
                             if l.strip().startswith(f"{decision}:"))
                self.assertIn(MARQUEUR, ligne)

    def test_l_origine_dit_d_ou_vient_l_entree(self):
        self.assertIn("origine: falcon_observe",
                      entree_proposee(self._inconnu(statut={"id": "IW"})))


class TestLeMarqueurProtege(unittest.TestCase):
    """Une proposition collee sans etre lue ne doit pas devenir une regle."""

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)

    def test_une_surcouche_non_completee_REFUSE_de_charger(self):
        inconnu = lire_dump(_dump(
            self.racine, "a.json", horodatage="2026-09-08T10:00:00Z",
            garde="statut", detail={"statut": {"id": "IW", "numero": "010"},
                                    "attendu": "S", "observe": "E"}))
        chemin = self.racine / "surcouche.yaml"
        chemin.write_text(surcouche_proposee([inconnu]), encoding="utf-8")

        with self.assertRaises(RegistreInvalide) as capture:
            Registre.avec_surcouches(chemin)
        self.assertIn(MARQUEUR, str(capture.exception))

    def test_completer_les_marqueurs_TYPES_ne_suffit_pas(self):
        """Le controle etait implicite : on comptait sur le typage de chaque
        champ pour refuser le marqueur.

        Il a tenu sur `categorie` et `poursuivre`, et laisse passer
        `politique.item` — qui n'etait valide nulle part — et `justification`,
        qui est du texte libre. Une surcouche a moitie completee chargeait
        donc, et `politique.appliquer` ne comparant qu'a « ko », l'item
        continuait : la pipeline enchainait sur l'etape suivante, typiquement
        la sauvegarde, JUSTE APRES un message d'erreur metier.

        Le marqueur est desormais cherche dans le TEXTE : ca ne demande de
        n'oublier aucun champ, ni aujourd'hui ni a chaque champ ajoute.
        """
        inconnu = lire_dump(_dump(
            self.racine, "b.json", horodatage="2026-09-08T10:00:00Z",
            garde="statut",
            signature={"canal": "statut", "id": "IW", "numero": "010"},
            detail={}))
        partiel = surcouche_proposee([inconnu])
        for avant, apres in (
                (f"categorie: {MARQUEUR}        # connue_benigne | connue_fautive",
                 "categorie: connue_fautive"),
                (f"poursuivre: {MARQUEUR}   # true : le lot continue",
                 "poursuivre: true")):
            self.assertIn(avant, partiel, "l'ancre du test n'a pas mordu")
            partiel = partiel.replace(avant, apres)

        chemin = self.racine / "partielle.yaml"
        chemin.write_text(partiel, encoding="utf-8")
        with self.assertRaises(RegistreInvalide) as capture:
            Registre.avec_surcouches(chemin)
        self.assertIn(MARQUEUR, str(capture.exception))


class TestSurcouche(unittest.TestCase):
    """`avec_surcouches` ENRICHIT ; `charger` REMPLACE. Le piege est la."""

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)
        self.surcouche = self.racine / "s.yaml"
        self.surcouche.write_text("""version: 1
entrees:
  - nom: essai_recolte
    categorie: connue_fautive
    canal: garde
    correspondance: {garde: "statut", id: "IW", numero: "010"}
    politique: {poursuivre: true, item: ko}
    origine: falcon_observe
    justification: "Observe sur le systeme de recette."
""", encoding="utf-8")

    def test_une_surcouche_S_AJOUTE_au_registre_livre(self):
        livre = len(Registre.charger().entrees)
        enrichi = Registre.avec_surcouches(self.surcouche)
        self.assertEqual(len(enrichi.entrees), livre + 1)
        self.assertIn("essai_recolte", [e.nom for e in enrichi.entrees])

    def test_charger_avec_un_chemin_REMPLACE_et_c_est_le_piege(self):
        """On epingle la difference plutot que de la laisser se decouvrir.

        `charger(chemin)` est utile pour rejouer un registre entier ; employe
        comme surcouche, il ferait disparaitre les entrees livrees sans un mot.
        """
        self.assertEqual(len(Registre.charger(self.surcouche).entrees), 1)


class TestParcoursComplet(unittest.TestCase):
    """De bout en bout : un lot bloque, on recolte, on complete, ca repart.

    C'est le test qui compte. Chaque maillon existait deja ; aucun n'etait
    relie. Il tomberait si le dump cessait d'etre ecrit par defaut, si la
    proposition cessait de correspondre a ce que le registre sait apparier, ou
    si la surcouche cessait d'etre jointe a l'execution.
    """

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)
        (self.racine / "jeu.csv").write_text("site\n1000\n2000\n",
                                             encoding="utf-8")
        (self.racine / "p.yaml").write_text(PIPELINE, encoding="utf-8")

    def _driver(self) -> DriverScripte:
        """Un SAP qui repond un message d'erreur metier jamais rencontre."""
        pilote = DriverScripte(identite=IA08,
                               valeurs={"wnd[0]/usr/ctxtWERKS-LOW": ""})

        def apres(brut, geste, cible):
            if geste == "write":
                brut.valeurs[cible] = brut.valeurs.get(cible, "")
                brut.statut = Statut(type="E", id="IW", numero="010",
                                     texte="Equipement inexistant")

        pilote.apres_action = apres
        return pilote

    def _executer(self, journal: str, registre=None, mode: str = "run"):
        return executer(charger(self.racine / "p.yaml"),
                        self.racine / "jeu.csv", self._driver(),
                        journal=self.racine / journal, registre=registre,
                        mode=mode)

    def test_le_parcours_entier(self):
        # 1. La REPETITION A BLANC est le premier geste, et c'est elle qui
        #    decouvre l'inconnu — avant d'avoir touche a la production. C'est
        #    tout l'objet de la garde 5.5 : « on ne decouvre pas en production
        #    qu'une cible a change de nom ».
        premier = self._executer("j1.jsonl", mode="dry-run")
        self.assertEqual(premier.etat, "interrompu")
        self.assertEqual(premier.compteurs["ok"], 0)

        # 2. Le dump existe SANS qu'on ait demande de dossier de dumps. C'est
        #    la correction : aucun appelant de production n'en passait, donc
        #    la recolte etait inatteignable.
        chemins = dumps_de(self.racine / "dumps")
        self.assertEqual(len(chemins), 1, "aucun dump : rien a recolter")

        # 3. Le dump porte la SIGNATURE soumise au registre, pas seulement
        #    le detail. Sans elle il faudrait la reconstruire, et la
        #    reconstruction se trompait de canal.
        inconnu = lire_dump(chemins[0])
        self.assertIsNotNone(inconnu.signature,
                             "le dump ne porte pas la signature soumise")
        self.assertEqual(inconnu.signature["canal"], inconnu.canal)
        self.assertEqual(inconnu.signature["id"], "IW")

        # 4. La proposition porte ce qui a ete OBSERVE.
        self.assertEqual(inconnu.nom_propose, "statut_iw_010")

        # 5. Collee sans etre completee, elle refuse de charger.
        brute = self.racine / "brute.yaml"
        brute.write_text(surcouche_proposee([inconnu]), encoding="utf-8")
        with self.assertRaises(RegistreInvalide):
            Registre.avec_surcouches(brute)

        # 6. Completee par un humain, le lot va au bout et classe ses items.
        complete = self.racine / "complete.yaml"
        complete.write_text("""version: 1
entrees:
  - nom: statut_iw_010
    categorie: connue_fautive
    canal: garde
    correspondance:
      garde: "statut"
      attendu: "S"
      observe: "E"
      id: "IW"
      numero: "010"
    politique: {poursuivre: true, item: ko}
    origine: falcon_observe
    justification: >
      SAP a repondu « Equipement inexistant ». L'equipement est hors
      perimetre : l'item part en KO et le lot continue.
""", encoding="utf-8")

        registre = Registre.avec_surcouches(complete)

        # La repetition passe maintenant, puisque l'incident est CLASSE.
        repetition = self._executer("j2.jsonl", registre, mode="dry-run")
        self.assertEqual(repetition.etat, "termine")

        # 7. Et le run, sur le meme journal, va au bout — la garde 5.5 y
        #    trouve la repetition qu'elle exige, sans qu'on ait rien a forcer.
        resultat = self._executer("j2.jsonl", registre)
        self.assertEqual(resultat.etat, "termine")
        self.assertEqual(resultat.compteurs["ko"], 2,
                         "le lot n'est pas alle au bout")


class TestParcoursCanalPython(unittest.TestCase):
    """Le meme parcours, par le chemin du MOTEUR plutot que des gardes.

    `_classer_echec` construisait la signature et la JETAIT : le dump portait
    `signature: null`, et `recolte` retombait sur une deduction du canal a
    partir du champ `garde` — qui vaut « python » et n'est pas un canal. La
    surcouche proposee annoncait donc `canal: com`, et l'entree ecrite d'apres
    elle n'appariait RIEN. Le lot serait retombe au meme endroit
    indefiniment : la seule sortie offerte a un inconnu bloquant produisait
    une entree inerte.
    """

    def setUp(self):
        from falcon.pipeline import oublier_tout
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.addCleanup(oublier_tout)
        self.racine = Path(dossier.name)
        (self.racine / "jeu.csv").write_text("site\nK75\n", encoding="utf-8")
        (self.racine / "p.yaml").write_text("""version: 1
nom: "essai_python"
classe: "iterative"
cles: ["site"]
plafond_items: 5
plafond_sauvegardes: 5
etapes:
  - nom: "maison"
    action: "python"
    fonction: "leve_pour_le_test"
    ecran: {transaction: "IA08", programme: "RIPLKO10", dynpro: "1000"}
""", encoding="utf-8")

    def test_le_parcours_entier_sur_le_canal_python(self):
        from falcon.pipeline import etape_python

        @etape_python("leve_pour_le_test")
        def _leve(poste, item, contexte):
            raise RuntimeError("champ de texte long introuvable")

        pilote = DriverScripte(identite=IA08, valeurs={})
        resultat = executer(charger(self.racine / "p.yaml"),
                            self.racine / "jeu.csv", pilote,
                            journal=self.racine / "j.jsonl", mode="dry-run")
        self.assertEqual(resultat.etat, "interrompu")

        chemins = dumps_de(self.racine / "dumps")
        self.assertEqual(len(chemins), 1)
        inconnu = lire_dump(chemins[0])

        # Le dump porte la signature, donc le canal est LU et non deduit.
        self.assertIsNotNone(inconnu.signature)
        self.assertEqual(inconnu.canal, "python")
        self.assertEqual(inconnu.correspondance, {"exception": "RuntimeError"})

        # Et l'entree, completee, apparie REELLEMENT l'incident dont elle vient.
        complete = self.racine / "s.yaml"
        complete.write_text("""version: 1
entrees:
  - nom: runtimeerror
    categorie: connue_fautive
    canal: python
    correspondance: {exception: "RuntimeError"}
    politique: {poursuivre: true, item: ko}
    origine: falcon_observe
    justification: "Champ absent de cet ecran, observe en recette."
""", encoding="utf-8")
        from falcon.taxonomie import Signature
        verdict = Registre.avec_surcouches(complete).classer(
            Signature(canal="python", exception="RuntimeError",
                      texte="champ de texte long introuvable"))
        self.assertEqual(verdict.categorie, "connue_fautive")
        self.assertFalse(verdict.bloquant,
                         "l'entree recoltee n'apparie pas son propre incident")


if __name__ == "__main__":
    unittest.main()
