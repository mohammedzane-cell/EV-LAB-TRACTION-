# Jeux de données de test (data/tests/)

**Avertissement : « fichiers synthétiques, pas des mesures ».** Tous sont générés par l'application
elle-même (`python -m evlab.io.demo_data --tests`, fonctions de `evlab/io/demo_data.py`),
donc leur format est exactement celui que lisent les chargeurs. Chaque fichier commence
par une ligne `# démo: …` : l'application les affiche avec la mention « démo ». Le test
`tests/test_datasets.py` vérifie que les fichiers sont identiques à la sortie du
générateur, que les bons fichiers s'identifient dans les bornes ci-dessous et que les
mauvais donnent un message d'erreur clair en français.

Pour les utiliser : onglet 1, *Charger…* (essais), *Charger…* (points en charge),
méthode *Comparer les deux*, *Identifier* ; onglet 4, *Charger un cycle CSV…*. Dans la
version Windows, ils sont dans `EVLab\data\tests\`.

## 1. Trois moteurs (essais + points en charge)

Fichiers `bench_tests_<nom>.csv` (essai DC à 20 °C, 8 essais à vide de 0,4 à 1,1·Un,
un essai rotor bloqué à 0,25·Un, bobinage à 75 °C) et `load_points_<nom>.csv`
(10 points en charge, g = 0,01 à 0,08, tension et glissement exacts).

Mesures calculées avec le circuit en Γ (schéma TP3) du moteur de référence, puis bruit
gaussien relatif de 2,5 % sur chaque lecture, graine fixe (2101, 2102, 2103). Valeurs
choisies pour ces fichiers (synthétiques) : R1 est la valeur à 75 °C (l'essai DC à 20 °C
lit donc R1·254,5/309,5) ; p_méc = 1 % de la puissance nominale ; la vitesse
nominale de la plaque est celle où le circuit donne la puissance nominale à l'arbre.

| Fichier | V (V) | f (Hz) | p | R1 (Ω, 75 °C) | Rf (Ω) | Xm (Ω) | X (Ω) | R'2 (Ω) | P_n | p_méc | Vitesse nominale |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `*_petit_1.5kW.csv` | 230 | 50 | 2 | 4,0 | 1000 | 115 | 10,0 | 3,6 | 1,5 kW | 15 W | 1440 tr/min |
| `*_moyen_4kW.csv` | 230 | 50 | 2 | 1,6 | 900 | 75 | 6,5 | 1,4 | 4 kW | 40 W | 1436 tr/min |
| `*_grand_7.5kW.csv` | 230 | 50 | 2 | 0,75 | 600 | 45 | 4,2 | 0,7 | 7,5 kW | 75 W | 1440 tr/min |

### Résultat attendu dans l'onglet 1 (tel que l'application l'affiche)

Méthode *Comparer les deux*, schéma TP3. Valeur identifiée (écart à la référence).
R1 (DC) affichée à 20 °C.

**petit_1.5kW** — R1 (DC) = 3,1009 Ω à 20 °C, vitesse nominale 1440 tr/min

| Méthode | Rf (Ω) | Xm (Ω) | X fuites (Ω) | R'2 (Ω) |
|---|---|---|---|---|
| Référence | 1000 | 115 | 10,0 | 3,60 |
| Formules classiques | 889 (-11,1 %) | 118 (+3,0 %) | 9,33 (-6,7 %) | 3,65 (+1,3 %) |
| Optimisation | 889 (-11,1 %) | 114 (-0,8 %) | 9,64 (-3,6 %) | 3,65 (+1,3 %) |

Intervalle de confiance à 95 % de X (optimisation) : [6,797 ; 12,49] Ω.

**moyen_4kW** — R1 (DC) = 1,3226 Ω à 20 °C, vitesse nominale 1436 tr/min

| Méthode | Rf (Ω) | Xm (Ω) | X fuites (Ω) | R'2 (Ω) |
|---|---|---|---|---|
| Référence | 900 | 75,0 | 6,50 | 1,40 |
| Formules classiques | 813 (-9,7 %) | 73,6 (-1,9 %) | 5,85 (-9,9 %) | 1,20 (-14,1 %) |
| Optimisation | 813 (-9,7 %) | 75,0 (+0,0 %) | 6,57 (+1,1 %) | 1,40 (+0,1 %) |

Intervalle de confiance à 95 % de X (optimisation) : [5,833 ; 7,310] Ω.

**grand_7.5kW** — R1 (DC) = 0,6054 Ω à 20 °C, vitesse nominale 1440 tr/min

| Méthode | Rf (Ω) | Xm (Ω) | X fuites (Ω) | R'2 (Ω) |
|---|---|---|---|---|
| Référence | 600 | 45,0 | 4,20 | 0,700 |
| Formules classiques | 568 (-5,4 %) | 45,0 (+0,1 %) | 3,85 (-8,4 %) | 0,664 (-5,1 %) |
| Optimisation | 568 (-5,4 %) | 46,3 (+3,0 %) | 4,44 (+5,7 %) | 0,698 (-0,2 %) |

Intervalle de confiance à 95 % de X (optimisation) : [4,020 ; 4,855] Ω.

Dans les trois cas, le moteur publié pour les onglets 2 à 7 est celui de
l'optimisation : « Moteur : Identification TP3 · optimisation (démo) ».

### Ce que ces fichiers testent

- La chaîne complète : essai DC → R1 à chaud, séparation de p_méc à vide, Rf et Xm,
  rotor bloqué, puis ajustement de Xm, X, R'2 sur les points en charge.
- La différence entre méthodes : la formule classique du rotor bloqué néglige la branche
  magnétisante (R'2 −14,1 % sur le moteur moyen) ; l'ajustement retrouve R'2 à 0,2 % près.
- Les limites de l'identification avec 2,5 % de bruit et des points en charge
  faible (g ≤ 0,08, loin du décrochage g_c ≈ 0,17 à 0,36) :
  - **Rf** vient d'un seul point à vide, après soustraction des pertes cuivre et de
    p_méc : sur 300 tirages de bruit, 95 % des cas sont à moins de 16 % (médiane 5 %).
  - **X** est peu visible loin du décrochage : 95 % des cas à moins de 24 % (petit),
    13 % (moyen), 8 % (grand) ; l'intervalle de confiance à 95 % le dit.
  - **Xm et R'2** sont bien déterminés : 95 % des cas à moins de 4,1 % et 1,9 %.
  - Sans bruit, les mêmes fichiers redonnent tous les paramètres à moins de 1 % près.
- Critères du test automatique : Xm et R'2 à moins de 5 % ; X de référence dans
  l'intervalle de confiance à 95 % ; Rf à moins de ±16 %.

## 2. Trois cycles de conduite synthétiques (PAS des cycles WLTC)

Colonnes `t [s]`, `v [km/h]`, pas de 1 s. Chaque démarrage et chaque arrêt suit une
rampe en cosinus surélevé : l'accélération varie sans à-coup et ne dépasse jamais 1,2 m/s².

| Fichier | Durée | Distance | v max | Accélération max | Trajets |
|---|---|---|---|---|---|
| `cycle_urbain.csv` | 895 s | 5,77 km | 50 km/h | 1,0 m/s² | 10 |
| `cycle_route.csv` | 1142 s | 17,4 km | 80 km/h | 0,8 m/s² | 4 |
| `cycle_mixte.csv` | 1190 s | 13,4 km | 80 km/h | 1,1 m/s² | 9 |

Ce qu'ils testent : le chargement et le rééchantillonnage d'un cycle utilisateur
(onglet 4, *Charger un cycle CSV…*), la consommation et la récupération sur des profils
urbain, routier et mixte, et le contrôle « points hors enveloppe » (80 km/h demande un
rapport G adapté). Ils ne remplacent pas les fichiers WLTC officiels.

## 3. Fichiers erronés (messages d'erreur)

Chacun est une copie d'un bon fichier avec une seule erreur volontaire. L'application doit
refuser le fichier et afficher le message ci-dessous (onglet 1 ou 4, ligne d'état du fichier).

| Fichier | Erreur volontaire | Message attendu |
|---|---|---|
| `bench_tests_bad_negative.csv` | puissance négative sur le 1er essai à vide | `bench_tests_bad_negative.csv, ligne 20 (vide) : la puissance P doit être > 0 W (valeur lue : « -49.4431 »)` |
| `load_points_bad_slip.csv` | un point avec g = 1,2 | `load_points_bad_slip.csv, ligne 23 : glissement g = « 1.2 » hors de ]0 ; 1[ (un essai en charge est en fonctionnement moteur : 0 < g < 1)` |
| `cycle_bad_time.csv` | le temps revient de 99 s à 95 s | `cycle_bad_time.csv, ligne 104 : le temps doit être strictement croissant (99 s puis 95 s)` |
| `cycle_bad_header.csv` | en-têtes « temps », « vitesse » | `cycle_bad_header.csv : colonne(s) manquante(s) : « t », « v »` |

Les valeurs lues dans le fichier sont citées telles quelles (point décimal du CSV).
