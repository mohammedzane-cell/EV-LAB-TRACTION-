# EV-Traction Lab — Guide d'utilisation

Mini-projet ME3 — ENP Alger, Machines électriques.

Ce guide présente l'application onglet par onglet. Les captures d'écran
(1280 × 800, `docs/images/`) suivent le parcours de démonstration : fichiers démo,
« Comparer les deux », réglages par défaut.
Les nombres affichés utilisent la virgule décimale ; toutes les valeurs « démo »
sont signalées par une pastille ou la mention « (démo) ».

---

## 0. Démarrage

![Capture — fenêtre principale](images/00_fenetre.png)

*Fenêtre au démarrage : moteur TD5 Ex 1, aucun essai chargé ; huit onglets, un bouton « ? » sur chacun des sept premiers.*

- **Version Windows** : ouvrir le dossier `EVLab` et lancer `EVLab.exe`. Aucune
  installation de Python n'est nécessaire. Le dossier `EVLab\data` contient les
  fichiers démo ; y déposer les fichiers WLTC officiels (`wltc_class1.csv`,
  `wltc_class3.csv`) quand ils sont disponibles.
- **Depuis les sources** : `python -m evlab`.
- **Auto-test** (sans interaction) : `EVLab.exe --smoke dossier` écrit
  `dossier\smoke.log` (12 vérifications « ok », dont l'onglet 8 et le PDF du cours).
- **Jeux de test** : `EVLab\data\tests\` contient trois moteurs, trois cycles et quatre
  fichiers volontairement erronés, tous synthétiques (voir `data/tests/README.md`).

**Principe : un moteur, une chaîne.** Le moteur identifié dans l'onglet 1 (par
défaut TD5 Ex 1) est celui de tous les autres onglets. La barre d'état indique
toujours le moteur utilisé (« Moteur : … (démo) ») et l'environnement
(« Python 3 · PySide6 »). Les calculs longs tournent en arrière-plan : une barre
de progression s'affiche, l'interface reste utilisable.

**Menu Fichier** : *Exporter PDF…* (rapport A4 de 2 à 3 pages, sections 1 à 6,
encadré des hypothèses, pied de page listant les valeurs démo) et *Exporter
Excel…* (une feuille par module, tableaux bruts en unités SI). Les résultats non
encore calculés sont calculés pour l'export ; l'optimisation est notée « non
calculée » tant qu'elle n'a pas été lancée. *Exporter le cours en PDF…* écrit le cours
de l'onglet 8 (voir la section 8).

**Aide et cours** : chaque onglet 1 à 7 porte un bouton **?** qui ouvre sa page du cours
(onglet 8) ; **F1** fait de même pour l'onglet affiché. Menu **Aide** : *Cours*
(introduction) et *Cours de l'onglet affiché* (F1).

**Menu Affichage** : *Thème clair* (par défaut) ou *Thème sombre* ; le choix est
appliqué tout de suite et retenu au prochain démarrage. Les pastilles ambre
signalent les valeurs démo (le survol liste lesquelles), les pastilles rouges
une alerte (« R1 ≈ 0 … »). Le rapport PDF est toujours en thème clair.

---

## 1. Identification

![Capture — onglet 1](images/01_identification.png)

*Après « Charger la démo » et « Comparer les deux ».*

**But** : obtenir le schéma équivalent en Γ (Rf, Xm, X, R'2, R1, p_méc) à partir
des essais TP3 / TD5.

**Entrées**
- *Machine* : tension simple, fréquence, paires de pôles, R1 (DC) et sa
  température, schéma (« TP3 (R1 en tête) » ou « Bornes »). La vitesse nominale
  est lue dans le fichier (plaque signalétique), elle n'est pas saisie.
- *Essais (CSV)* : fichier d'essais (DC, à vide, rotor bloqué) et fichier de
  points en charge, chacun avec *Charger…* et *Aperçu*. Le bouton
  *Charger la démo (TD5 Ex 1, bruit 2,5 %)* charge les deux fichiers démo.
- *Méthode* : Formules classiques, Optimisation (scipy), Comparer les deux.

**Action** : *Identifier*. Le moteur obtenu est publié pour les onglets 2 à 7
(le résultat de l'optimisation s'il existe, sinon celui des formules classiques).

**Sorties** : quatre courbes, couple–vitesse | couple–glissement en haut et
courant–vitesse | courant–glissement en bas (modèle et points d'essai sur les quatre,
C_max et g_c sur couple–glissement, légende commune en tête), tableau Référence / Formules classiques / Optimisation avec l'écart en %
(l'infobulle donne l'intervalle de confiance à 95 % de l'optimisation).

**À vérifier** : les formules classiques sous-estiment R'2 (rotor bloqué : la
branche magnétisante est négligée, hypothèse A9) ; l'optimisation retrouve la
référence à quelques % près. Un avertissement « paramètres mal séparés » apparaît
si deux paramètres sont trop corrélés (|ρ| > 0,95).

---

## 2. Enveloppe

![Capture — onglet 2](images/02_enveloppe.png)

*Enveloppe du moteur identifié, trois zones.*

![Capture — onglet 2 après chargement du design optimal](images/02b_enveloppe_design.png)

*Après « Charger ce design dans tous les onglets » (onglet 7) : boost 4,3 V, avertissement de flux d'entrefer E/f = 1,07 × En/fn (circuit magnétique linéaire, A33).*

**But** : enveloppe couple–vitesse du moteur sous loi V/f puis défluxage.

**Entrées** (*Variateur*, valeurs démo, A16) : courant max, boost basse vitesse,
marge par rapport au décrochage, fréquence max. Le cadre *Moteur (onglet 1)*
rappelle le moteur utilisé.

**Action** : recalcul automatique à chaque changement (ou *Calculer l'enveloppe*).

**Sorties** : quatre tuiles (vitesse de base, fin de puissance constante, P max,
couple à vitesse max) ; courbes couple et puissance avec les trois zones
(couple constant, puissance constante, limitée par le décrochage).

**À vérifier** : la vitesse de base est voisine de la vitesse nominale ; au-delà,
la puissance reste à peu près constante puis décroît quand le décrochage limite.

---

## 3. Rendement

![Capture — onglet 3](images/03_rendement.png)

*Carte de rendement avec les points du cycle.*

**But** : carte de rendement η(C, n) à partir des pertes du circuit.

**Entrées** (*Pertes*) : pertes mécaniques de l'essai à vide (case à cocher),
pertes onduleur (démo, fixe + proportionnelle), exposant β du fer (Steinmetz,
A19), température du bobinage (correction de R1), part des frottements (A20).
*Grille et affichage* : nombre de points en couple et en vitesse, affichage des
points du cycle.

**Action** : *Calculer la carte* ; *Exporter PNG*.

**Sorties** : courbes de niveau du rendement (en %), enveloppe en couple à
l'arbre, point de meilleur rendement, points du cycle de l'onglet 4.

**À vérifier** : à 50 Hz la carte redonne exactement le rendement du circuit ; le
rendement chute à faible couple (pertes fer et onduleur fixes).

---

## 4. Véhicule & WLTC

![Capture — onglet 4](images/04_vehicule.png)

*Cycle démo simulé, classe WLTC 1.*

**But** : véhicule dimensionné pour ce moteur, consommation sur cycle.

**Entrées** (*Véhicule (quadricycle léger, démo)*, A22) : masse, Cx·S, Crr, rayon
de roue, rendement de transmission, auxiliaires, pente, rapport G (*Proposer*
calcule le rapport qui garde tout le cycle dans l'enveloppe) ; *Freinage
récupératif*. *Classe WLTC et cycle* : classe déduite du rapport puissance/masse
(≤ 22 W/kg → classe 1, ≤ 34 W/kg → 2, au-delà → 3), *Cycle de la classe* ou
*Charger un cycle CSV…*.

**Action** : *Simuler le cycle*.

**Sorties** : tuiles distance, énergie batterie, consommation (Wh/km), énergie
récupérée (%) ; courbes vitesse et puissance batterie ; avertissement rouge si
un point du cycle sort de l'enveloppe.

**À vérifier** : sans les fichiers WLTC officiels, l'onglet utilise le cycle
urbain synthétique `cycle_demo.csv` et l'indique (démo, A25).

---

## 5. Thermique

![Capture — onglet 5](images/05_thermique.png)

*Dix cycles enchaînés, classe F.*

**But** : échauffement du bobinage sur cycles enchaînés et durée de vie de
l'isolation.

**Entrées** (*Réseau thermique (démo)*, A26) : capacité du bobinage, capacité
fer/carcasse, résistances bobinage → fer et carcasse → air, température
ambiante (les deux constantes de temps sont affichées). *Essai* : classe
d'isolation, nombre de cycles enchaînés, intégrateur (Euler implicite ou RK45).

**Action** : *Calculer les températures*.

**Sorties** : T(t) du bobinage et de la carcasse avec la limite de classe ;
tuiles T max bobinage, T moyenne (dernier cycle), marge à la classe, durée de vie
de l'isolation (ordre de grandeur, règle des 10 K, A28).

**À vérifier** : les pertes cuivre sont recalculées avec R1(T) ; la durée de vie
n'est qu'un ordre de grandeur loin de la température de classe.

---

## 6. Bobinage

![Capture — onglet 6](images/06_bobinage.png)

![Capture — animation FEM](images/06b_fem.png)

*36 encoches, 4 pôles, pas y = 7 ; en dessous, la fenêtre « Animation FEM » (résultats pré-calculés, acier M-19, 7,07 A crête).*

**But** : bobinage triphasé double couche, facteurs, FMM, champ tournant, f.é.m.

**Entrées** : encoches Z, pôles 2p, phases m, pas y en nombre entier d'encoches
(un pas « 5/6 » est refusé pour 36 encoches / 4 pôles, avec les deux pas entiers
les plus proches) ; *Force électromotrice* : spires par bobine, fréquence, flux
par pôle.

**Sorties** : tableau des encoches (couches haute et basse), facteurs de
bobinage kd, kp, kw (y = τ et y choisi), spectre de la FMM d'une phase, f.é.m.
E = 4,44·f·N·kw1·Φ, FMM d'entrefer tournante animée (*▶ Lecture*, curseur de
vitesse).

**Animation FEM (FEMM)** : *Ouvrir l'animation FEM…*. Avec pyfemm et FEMM 4.2,
*Calculer avec FEMM* résout le stator (géométrie démo, A32) ; sinon la fenêtre
rejoue les « résultats FEM pré-calculés ». Les courants sont des valeurs
**crête** (« 7,07 A crête (5,00 A eff) ») ; par défaut I_µ = V/Xm du moteur de
l'onglet 1. Rotor lisse sans barres = état magnétisant (à vide) : un courant élevé
est une surexcitation, pas un point en charge.

**À vérifier** : y = 9 → kw1 = 0,9598 ; y = 7 → kw1 = 0,9019, kw5 = −0,0378,
kw7 = −0,1359.

---

## 7. Optimisation

![Capture — onglet 7](images/07_optimisation.png)

*Démo rapide (3 points × 300 évaluations), point de consommation minimale sélectionné.*

**But** : choisir rapport G, boost V/f, marge de défluxage et rebobinage k_N pour
minimiser la consommation et le temps 0–50 km/h, sur les modèles testés.

**Entrées** : *Bornes des variables* (min = max fixe la variable ; k_N multiplie
les spires à section de cuivre constante : toutes les impédances × k_N²).
*Budget (évolution différentielle)* : points de Pareto, population, évaluations
par point (1500 par défaut, quel que soit le nombre de variables libres),
processus, graine.

**Contraintes** : tout le cycle dans l'enveloppe, T max bobinage ≤ classe − 20 K,
courant ≤ limite de l'onduleur, 50 km/h atteignable.

**Action** : *Lancer l'optimisation* (progression, *Annuler*). Cliquer un point du
front le sélectionne ; *Charger ce design dans tous les onglets* charge le moteur
rebobiné, la loi V/f (onglet 2) et le rapport G (onglet 4), et tous les onglets se
recalculent.

**Sorties** : front de Pareto consommation vs 0–50 km/h avec la base et toutes
les évaluations admissibles ; tableau *Base vs design sélectionné* avec le gain
en % par indicateur (écart de température en K). La capture est une démo rapide
(3 points × 300 évaluations) ; le calcul complet utilise 1500 évaluations par point.

---

## 8. Cours

![Capture — onglet 8, thème clair](images/08_cours.png)

![Capture — onglet 8, thème sombre](images/08_cours_sombre.png)

*Bouton « ? » de l'onglet 1 : page « 1 · Identification », loi « Rotor bloqué : inversion
exacte du schéma » ; en haut thème clair, en bas thème sombre.*

**But** : énoncer et expliquer chaque loi que l'application utilise, onglet par onglet,
dans la notation du cours du Pr Boughrara (R_s, R_μ, X_μ, l_s'ω_s, R_r', I_s, I_r', g).
L'onglet n'ajoute aucun calcul : il explique ceux des onglets 1 à 7.

**Pages** : introduction, une page par onglet 1 à 7, puis *Hypothèses et limites*,
*Glossaire des symboles*, *Notation : cours ↔ application* (R_s ↔ R1, R_μ ↔ Rf, …),
*Validation* et *Bibliographie*.

**Plan d'une page d'onglet** : *Ce que fait cet onglet* ; *Lois et explications*, groupées
par thème (onglet 1 : Essais · Schéma équivalent · Couple et puissances · Ajustement par
moindres carrés), chaque loi avec son équation, le tableau de ses symboles, une
explication, « Ce que ça montre », la fonction du code qui la calcule (« Dans
l'application »), un **Exemple** et la référence au cours (« Cours Pr Boughrara, MAS A
§5.2, p. 94 », ou « hors cours ») ; *Hypothèses* ; *Avec votre moteur* ; trois questions
(*Voir la réponse* / *Masquer la réponse*) ; un lien vers l'onglet.

**Les nombres** : tous sont calculés par l'application. Chaque exemple dit sur quelles
données il est calculé : « moteur de référence, sans bruit » ou « fichiers démo bruités
(R1 = 0,40 Ω) ». *Avec votre moteur* donne les valeurs du moteur utilisé par la chaîne
en ce moment (« moteur de référence » tant qu'aucun moteur n'est identifié) et se met à
jour à chaque identification ou chargement d'un design.

**Navigation** : la table des matières (à gauche) ouvre une page, une section ou un groupe
de lois. La recherche ignore les accents et les majuscules (« decrochage » trouve
« décrochage ») : elle garde les pages qui contiennent tous les mots et surligne les
occurrences. Les liens « Ouvrir l'onglet » changent d'onglet.

**Export** : *Fichier → Exporter le cours en PDF…* écrit tout le cours (page de titre,
sommaire, une page par feuille, réponses imprimées sous les questions), toujours en thème
clair, nom proposé `cours_EV-Traction_Lab.pdf`.

**À vérifier** : page 1, l'inversion exacte donne R_r' = 1,77 Ω sur les fichiers démo
bruités et 2,000 Ω sur les mêmes fichiers sans bruit : l'écart vient du bruit, pas de la
méthode.
