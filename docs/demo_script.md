# Démonstration en 5 minutes — EV-Traction Lab

Fil conducteur : **un moteur, une chaîne**. Le moteur identifié à l'onglet 1 est
celui de tous les autres onglets. Les chiffres ci-dessous sont ceux qu'affiche
l'application en suivant exactement ce parcours (fichiers démo, réglages par
défaut, graine 0). Ils ont été relevés sur l'application elle-même.

**Avant de commencer** : lancer `EVLab.exe` (ou `python -m evlab`), fenêtre
maximisée, onglet 1 ouvert. Prévoir environ 15 s de calcul à l'onglet 7
(4 cœurs, démo rapide). Captures de chaque étape : `docs/images/`.

**Ordre impératif : onglet 1 « Identifier » d'abord.** Le moteur de départ
(TD5 Ex 1) a R1 = 0, donc aucune perte cuivre stator : les onglets 5 et 7
affichent alors la pastille rouge « R1 ≈ 0 : pas de pertes cuivre stator —
lancez l'identification (onglet 1) » et leurs résultats thermiques ne sont pas
significatifs. Après l'identification (R1 ≈ 0,40 Ω à 20 °C), la pastille
disparaît. Les pastilles « démo » listent, au survol, les valeurs démo
utilisées par l'onglet (champ par champ : I max, boost, marge, f max ; pertes
onduleur ; C_w, C_s, R_ws, R_sa ; véhicule ; cycle).

---

## 0:00 – 0:30 · Ouverture

- **Montrer** la barre d'état : « Moteur : TD5 Ex 1 » et « Python 3 · PySide6 »
  (`00_fenetre.png`).
- **Dire** : « Sept onglets, un seul moteur. Au démarrage, c'est le schéma en Γ du
  TD5 Ex 1 : Rf = 230 Ω, Xm = 46 Ω, X = 4 Ω, R'2 = 2 Ω, R1 = 0. Il donne
  g_c = R'2/X = 0,5 et T_max = 3pV²/(2Xω) = 126,3 N·m, nos valeurs de référence
  testées. Nous allons le remplacer par un moteur identifié à partir d'essais. »

## 0:30 – 1:30 · Onglet 1 — Identification

- **Cliquer** *Charger la démo (TD5 Ex 1, bruit 2,5 %)*, puis *Comparer les deux*,
  puis *Identifier*.
- **Dire** : « Les essais sont synthétiques et signalés "démo" : le circuit du TD5,
  plus R1 = 0,5 Ω et p_méc = 60 W, avec 2,5 % de bruit. On a un essai DC, huit
  essais à vide et un essai rotor bloqué, comme au TP3. »
- **Montrer** le tableau (Référence 230 / 46 / 4 / 2 Ω) :

  | | Rf | Xm | X | R'2 |
  |---|---|---|---|---|
  | Formules classiques | 225 Ω (−2,0 %) | 44,9 Ω (−2,4 %) | 3,56 Ω (−10,9 %) | 1,54 Ω (−22,9 %) |
  | Optimisation | 225 Ω (−2,0 %) | 46,5 Ω (+1,1 %) | 4,08 Ω (+1,9 %) | 1,99 Ω (−0,6 %) |

- **Dire** : « La formule classique du rotor bloqué néglige la branche
  magnétisante : sur les données sans bruit elle sous-estime déjà R'2 de 13 %.
  L'ajustement sur les points en charge retrouve R'2 à 0,6 % près. » Survoler
  R'2 (optimisation) : intervalle à 95 % de [1,95 ; 2,03] Ω.
- **Montrer** la barre d'état : « Moteur : Identification TP3 · optimisation
  (démo) ». R1 = 0,40 Ω mesurée à 20 °C (essai DC), soit 0,49 Ω à 75 °C, la
  température du bobinage pendant l'essai. Le couple maximal tombe alors à
  C_max = 109,4 N·m (g_c = 0,48, affichés sur la courbe) : c'est la chute de tension
  dans R1.
- **Montrer** la note sous *Schéma* : le choix TP3 / bornes ne change pas les
  formules classiques, il fixe le circuit de l'optimisation et des onglets 2 à 7.

## 1:30 – 2:10 · Onglet 2 — Enveloppe

- **Montrer** les tuiles : vitesse de base **1253 tr/min**, fin de puissance
  constante **1695 tr/min**, P max **9,05 kW**, couple à vitesse max **23,0 N·m**.
- **Dire** : « Loi V/f jusqu'à 50 Hz, puis défluxage à tension constante. Les trois
  zones se lisent sur la courbe : couple constant jusqu'à 1253 tr/min, puissance
  constante jusqu'à 1695 tr/min, puis limitation par le décrochage jusqu'à
  2648 tr/min. Le variateur (20 A, boost 0 V, marge 80 %, 100 Hz) est une
  hypothèse démo » : survoler la pastille « démo » (réglages variateur I max,
  boost, marge, f max, A16).

## 2:10 – 2:40 · Onglet 3 — Rendement

- **Montrer** la carte η(C, n) et le point de meilleur rendement :
  **78,3 %** à 20,8 N·m et 2273 tr/min.
- **Dire** : « La carte commence à couple nul : c'est la ligne des pertes à vide
  (fer, onduleur, mécanique) comptées en roue libre à l'onglet 4. Chaque point
  respecte aussi I1 ≤ 20 A et la marge au décrochage avec R1 à 75 °C. »
- **Dire** : « Chaque point est un point de fonctionnement du même circuit : cuivre
  avec R1(T), fer par Steinmetz (β = 1,5), mécanique à partir du p_méc de
  l'onglet 1, onduleur démo. À 50 Hz la carte redonne exactement le rendement du
  circuit, c'est testé. »

## 2:40 – 3:20 · Onglet 4 — Véhicule & WLTC

- **Montrer** : 9,0 kW pour 600 kg → **15,0 W/kg → classe WLTC 1**, rapport proposé
  **G = 3,53**.
- **Dire** : « Le véhicule est dimensionné pour ce moteur : quadricycle léger
  (démo). Les fichiers WLTC officiels ne sont pas encore fournis, donc le cycle
  est le cycle urbain synthétique, signalé démo. »
- **Montrer** les tuiles : **3,73 km**, **75,4 Wh/km**, **9,7 %** d'énergie
  récupérée, aucun point hors enveloppe.

## 3:20 – 3:50 · Onglet 5 — Thermique

- **Montrer** : T max bobinage **61,4 °C**, T moyenne (dernier cycle) **60,8 °C**,
  classe F (155 °C), marge **93,6 K**, durée de vie **≈ 10⁷ h**. Pas de pastille
  « R1 ≈ 0 » : le moteur identifié a R1 = 0,49 Ω à 75 °C.
- **Dire** : « Réseau à deux nœuds alimenté par les pertes du cycle. R1 est
  recalculée à chaque pas avec la température. Les paramètres du réseau sont
  démo, faute de relevés de refroidissement au TP3. La durée de vie n'est qu'un
  ordre de grandeur, calculé sur le vieillissement moyen du dernier cycle
  (règle des 10 K appliquée au taux, pas à la température moyenne) : ici
  l'isolation n'est pas une limite. »

## 3:50 – 4:20 · Onglet 6 — Bobinage

- **Montrer** les facteurs : pas diamétral y = 9 : kw1 = **0,9598**,
  kw5 = 0,2176, kw7 = 0,1774 ; pas raccourci y = 7 : kw1 = **0,9019**,
  kw5 = **−0,0378**, kw7 = **−0,1359**.
- **Dire** : « Raccourcir de 2 encoches coûte 6 % sur le fondamental mais divise
  l'harmonique 5 par six. Un pas "5/6" est impossible : 7,5 encoches. »
  **Cliquer** *▶ Lecture* : champ tournant à 2πf/p.
- *(Optionnel, 10 s)* *Ouvrir l'animation FEM…* : « résultats FEM pré-calculés »
  avec FEMM, B₁ = 0,734 T contre 0,816 T analytique (−10 %, encoches et début
  de saturation), géométrie démo.

## 4:20 – 5:00 · Onglet 7 — Optimisation

- **Régler** *Points de Pareto* = 3, *Évaluations / point* = 300, *Processus* = 4
  (900 évaluations, ≈ 17 s), puis *Lancer l'optimisation*.
- **Dire** : « Démo rapide ; calcul complet : 1500 évaluations par point »
  (réglage par défaut : 6 points × 1500 = 9000 évaluations, environ 3 min sur
  4 cœurs). Les chiffres ci-dessous sont ceux de la démo rapide ; le calcul
  complet peut trouver un front un peu meilleur.
- **Dire** : « Quatre variables : rapport G, boost V/f, marge de défluxage et
  rebobinage k_N. Deux objectifs : Wh/km et 0–50 km/h. Les contraintes sont
  l'enveloppe, T bobinage ≤ classe − 20 K, le courant onduleur et le flux
  d'entrefer E/f ≤ 1,10 × En/fn (circuit magnétique linéaire, A33). Aucune
  physique nouvelle ici : chaque évaluation enchaîne les modèles déjà testés. »
- **Cliquer** le point le plus à gauche du front (consommation minimale) et
  montrer le tableau :

  | | Base | Design | Gain |
  |---|---|---|---|
  | Consommation | 75,4 Wh/km | 73,4 Wh/km | −2,7 % |
  | 0–50 km/h | 12,2 s | 11,2 s | −8,0 % |
  | T max bobinage | 61,5 °C | 57,2 °C | −4,3 K |
  | E/f max (× En/fn) | 1,00 | 1,07 | +7,3 % |
  | G / boost / marge / k_N | 3,53 / 0 V / 0,80 / 1,000 | 4,21 / 4,3 V / 0,88 / 1,026 | |

- **Dire** : « Ce design domine la base : il consomme moins et accélère mieux.
  Sans la contrainte de flux, l'optimiseur prenait 7,3 V de boost (10,9 s) :
  1,16 × En/fn à faible charge, hors du domaine du modèle linéaire. »
  **Cliquer** *Charger ce design dans tous les onglets* : les onglets 2 à 5 se
  recalculent avec ce moteur. À l'onglet 2, montrer l'avertissement rouge :
  « Boost : E/f atteint 1,07 × En/fn à 0 tr/min — surexcitation, saturation non
  modélisée (circuit magnétique linéaire, A33) » (`02b_enveloppe_design.png`).
  **Dire** : « E/f, c'est le flux d'entrefer : V moins la chute R1·I1. 7 %
  au-dessus du nominal, sous la limite de 10 % imposée à l'optimisation, mais le
  modèle ne sature pas : le gain à basse vitesse reste un peu optimiste. »
  Nouvelles tuiles : base 1238 tr/min, fin de puissance constante 1808 tr/min,
  P max 8,90 kW.
- **Conclure** : *Fichier → Exporter PDF…* : rapport de 2 à 3 pages, sections 1
  à 6, hypothèses, et pied de page listant ce qui est démo.

---

**Si une question porte sur la validation** : renvoyer au tableau « What is
validated / what is démo » du README (circuit TD5, facteurs de bobinage,
bilans d'énergie, comparaison avec un balayage exhaustif à 1 % près, 554 tests).
