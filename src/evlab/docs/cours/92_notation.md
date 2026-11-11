# Notation : cours ↔ application

Le cours écrit le schéma équivalent dans la notation du Pr Boughrara. L'application, ses
écrans et ses fichiers utilisent des noms plus courts. Voici la correspondance.

## Éléments du schéma équivalent

| Cours (Pr Boughrara) | Application | Signification | Unité |
|---|---|---|---|
| R_s | R1 | résistance d'une phase du stator | Ω |
| R_μ | Rf | résistance de pertes fer | Ω |
| X_μ | Xm | réactance magnétisante | Ω |
| l_s'ω_s | X | réactance de fuites totale ramenée au stator | Ω |
| R_r' | R'2 | résistance du rotor ramenée au stator | Ω |
| I_s | I1 | courant d'une phase du stator | A |
| I_r' | I'2 | courant du rotor ramené au stator | A |
| g | g | glissement | — |
| V_s | V (tension simple) | tension d'une phase | V |
| Γ | T (couple) | couple | N·m |

Dans le code (`core/session.py`, `MotorParams`), les mêmes grandeurs s'appellent `r1`, `r_fe`,
`x_m`, `x_leak`, `r2p` ; les tensions sont `v_phase`, les fréquences `f_rated`.

## Les deux dispositions du schéma

**Figure 7 du cours = disposition « Bornes ».** Pour simplifier les calculs, le cours déplace la
branche rotorique R_r'/g + j·l_s'ω_s en aval de la branche magnétisante (MAS A §6, p. 94) : la
branche R_μ ∥ X_μ se retrouve directement aux bornes, sous la tension V_s, et R_s passe en série
avec la branche rotorique. C'est la disposition « Bornes » de l'application. Elle donne les
formules du cours : I_r' = V_s/|R_s + R_r'/g + j·l_s'ω_s|, p_fer = 3·V_s²/R_μ,
g_c = R_r'/√(R_s² + (l_s'ω_s)²).

**Disposition par défaut (R1 en premier).** L'application place par défaut R_s en tête, traversée
par tout le courant I_s, puis la branche magnétisante, puis la branche rotorique : c'est l'ordre
physique du moteur, et c'est la disposition dans laquelle l'essai à vide se dépouille en retirant
3·R_s·I_0². La branche magnétisante voit alors E = V_s − R_s·I_s, et la branche rotorique voit la
source équivalente V_th = V_s·Z_μ/(R_s + Z_μ), Z_th = R_s ∥ Z_μ.

**Quand R_s = 0**, les deux dispositions sont identiques : c'est le cas du moteur de référence
(g_c = {{ex:ref_gc}}, Γ_max = {{ex:ref_tmax:4}} N·m dans les deux).

On choisit la disposition à l'onglet 1 (liste « Schéma »).

## Parties du cours

| Citation | Partie du cours | Pages du PDF |
|---|---|---|
| Notions A | machines à courant alternatif : champ tournant, bobinages, FMM | 4–27 |
| Synchrone B, C | machine synchrone : principe, f.é.m., diagrammes, caractéristiques | 28–81 |
| MAS A | moteur asynchrone : principe, schéma équivalent, couple | 82–98 |
| MAS B | diagramme du cercle, caractéristiques, effet de R_r', de V_s et de f | 99–119 |
| MAS C | essais, bilan de puissance, démarrage, freinage | 120–135 |

## Autres conventions

- Couplage étoile, grandeurs par phase ; les puissances sont triphasées.
- Unités SI dans les calculs ; tr/min, km/h et °C seulement à l'affichage.
- Virgule décimale dans tous les nombres affichés.

[→ Ouvrir l'onglet 1](evlab://onglet/identification)
