Attribute VB_Name = "ExportFalcon"
' =====================================================================
' FALCON — export des feuilles vers les CSV que `falcon composer` lit.
'
' CE MODULE EST VOLONTAIREMENT BETE.
'
' Il ecrit quatre fichiers et ne valide RIEN. Toute la validation vit dans
' `falcon/tableur/`, qui est teste ; ce code-ci ne l'est pas, et ne peut pas
' l'etre — aucune machine de ce projet n'execute Excel.
'
' C'est la parade, et elle est architecturale : une macro fausse produit un
' CSV que `falcon composer` REFUSE, avec un message qui nomme le fichier et la
' ligne. Elle ne peut pas produire un YAML plausible et faux. Si ce module
' faisait la moindre validation, une erreur ici deviendrait une pipeline qui
' se charge et fait autre chose.
'
' Deux choses qu'il fait quand meme, parce qu'elles portent sur le FORMAT du
' fichier et pas sur son contenu :
'   - il ecrit en UTF-8 (avec BOM), sinon les accents des motifs se perdent ;
'   - il delimite par « ; », ce qu'un Excel francais produit et relit.
' =====================================================================
Option Explicit

Private Const DELIMITEUR As String = ";"

' Les feuilles, et le fichier que chacune produit.
Private Const F_PIPELINE As String = "Pipeline"
Private Const F_ETAPES As String = "Etapes"
Private Const F_DEROGATIONS As String = "Derogations"
Private Const F_DONNEES As String = "Donnees"


' ---------------------------------------------------------------------
' Le point d'entree. C'est ce bouton qu'on branche.
' ---------------------------------------------------------------------
Public Sub ExporterTout()
    Dim dossier As String
    dossier = ChoisirDossier()
    If dossier = "" Then Exit Sub

    ' L'en-tete est en ligne 2 : la ligne 1 porte l'aide.
    EcrireFeuille F_PIPELINE, dossier & "\pipeline.csv", 2
    EcrireFeuille F_ETAPES, dossier & "\etapes.csv", 2
    EcrireFeuille F_DEROGATIONS, dossier & "\derogations.csv", 2
    EcrireFeuille F_DONNEES, dossier & "\jeu.csv", 2

    MsgBox "Quatre fichiers ecrits dans :" & vbCrLf & dossier & vbCrLf & _
           vbCrLf & _
           "Puis, dans un terminal :" & vbCrLf & _
           "    python -m falcon composer """ & dossier & """ -o pipeline.yaml" & _
           vbCrLf & vbCrLf & _
           "FALCON relit le YAML qu'il produit et n'ecrit le fichier que " & _
           "s'il le recharge sans rien refuser.", _
           vbInformation, "FALCON"
End Sub


' ---------------------------------------------------------------------
' Une feuille -> un CSV. Rien d'autre.
' ---------------------------------------------------------------------
Private Sub EcrireFeuille(nomFeuille As String, chemin As String, _
                          ligneEntete As Long)
    Dim ws As Worksheet
    Dim flux As Object
    Dim derniereLigne As Long, derniereColonne As Long
    Dim ligne As Long, colonne As Long
    Dim morceaux() As String
    Dim vide As Boolean

    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets(nomFeuille)
    On Error GoTo 0
    If ws Is Nothing Then
        MsgBox "Feuille introuvable : " & nomFeuille, vbCritical, "FALCON"
        Exit Sub
    End If

    derniereColonne = ws.Cells(ligneEntete, ws.Columns.Count).End(xlToLeft).Column
    derniereLigne = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    If derniereLigne < ligneEntete Then derniereLigne = ligneEntete

    ' ADODB.Stream plutot que `Print #` : c'est ce qui permet l'UTF-8. Sans
    ' lui, VBA ecrit dans la page de codes du poste, et un motif accentue
    ' revient mange — or le motif est ce qu'on relira le jour ou le lot sera
    ' conteste.
    Set flux = CreateObject("ADODB.Stream")
    flux.Type = 2                        ' texte
    flux.Charset = "UTF-8"
    flux.Open

    For ligne = ligneEntete To derniereLigne
        ReDim morceaux(1 To derniereColonne)
        vide = True
        For colonne = 1 To derniereColonne
            morceaux(colonne) = Echapper(CStr(ws.Cells(ligne, colonne).Text))
            If Len(Trim$(ws.Cells(ligne, colonne).Text)) > 0 Then vide = False
        Next colonne

        ' Une ligne entierement vide au milieu du tableau est sautee : c'est
        ' ce qu'un tableur laisse trainer, et FALCON les ignore de toute
        ' facon. Une ligne de COMMENTAIRE (« # ... ») aussi.
        If Not vide And Left$(Trim$(CStr(ws.Cells(ligne, 1).Text)), 1) <> "#" Then
            flux.WriteText Join(morceaux, DELIMITEUR) & vbCrLf
        End If
    Next ligne

    EnregistrerUtf8 flux, chemin
    flux.Close
End Sub


' ---------------------------------------------------------------------
' Echappement CSV. La regle est celle de RFC 4180, et elle tient en trois
' lignes : on entoure de guillemets des qu'un separateur, un guillemet ou
' un retour a la ligne apparait, et on double les guillemets internes.
' ---------------------------------------------------------------------
Private Function Echapper(valeur As String) As String
    Dim v As String
    v = valeur
    If InStr(v, """") > 0 Or InStr(v, DELIMITEUR) > 0 _
       Or InStr(v, vbLf) > 0 Or InStr(v, vbCr) > 0 Then
        v = """" & Replace(v, """", """""") & """"
    End If
    Echapper = v
End Function


' ---------------------------------------------------------------------
' Ecrit le flux en UTF-8 AVEC BOM.
'
' `ADODB.Stream` en UTF-8 pose deja le BOM ; on passe par un flux binaire
' pour rester explicite sur ce qu'on ecrit. Le BOM n'est pas decoratif :
' sans lui, Excel relit le fichier en ANSI la prochaine fois.
' ---------------------------------------------------------------------
Private Sub EnregistrerUtf8(flux As Object, chemin As String)
    flux.SaveToFile chemin, 2            ' 2 = ecrase
End Sub


' ---------------------------------------------------------------------
' Le dossier de sortie. Par defaut celui du classeur.
' ---------------------------------------------------------------------
Private Function ChoisirDossier() As String
    Dim boite As FileDialog
    Set boite = Application.FileDialog(msoFileDialogFolderPicker)
    boite.Title = "Ou ecrire les quatre CSV ?"
    boite.InitialFileName = ThisWorkbook.Path
    If boite.Show = -1 Then
        ChoisirDossier = boite.SelectedItems(1)
    Else
        ChoisirDossier = ""
    End If
End Function
