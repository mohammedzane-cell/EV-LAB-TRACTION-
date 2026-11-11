# 5 · Échauffement et vieillissement de l'isolant

## Ce que fait cet onglet

L'onglet calcule l'échauffement du bobinage et de la carcasse quand le véhicule enchaîne des
cycles, à partir des pertes du moteur lues sur la carte de l'onglet 3. Le modèle est un réseau
thermique à deux nœuds. L'onglet compare la température maximale du bobinage à la limite de sa
classe d'isolation et en déduit un ordre de grandeur de la durée de vie de l'isolant.

## Lois et explications

### Réseau thermique

#### Réseau à deux nœuds

`C_b·dT_b/dt = P_b(T_b) − (T_b − T_c)/R_bc`
`C_c·dT_c/dt = P_c + (T_b − T_c)/R_bc − (T_c − T_a)/R_ca`

| Symbole | Signification | Unité |
|---|---|---|
| T_b, T_c, T_a | températures du bobinage, de la carcasse (fer) et de l'air ambiant | K |
| C_b, C_c | capacités thermiques du bobinage et du fer avec la carcasse | J/K |
| R_bc, R_ca | résistances thermiques bobinage → carcasse et carcasse → air | K/W |
| P_b, P_c | pertes reçues par chaque nœud | W |

**Explication.** Chaque nœud stocke de la chaleur (C·dT/dt) et en échange avec ses voisins à
travers des résistances thermiques, comme un circuit électrique où la température joue le rôle
de la tension et la puissance celui du courant. Les pertes cuivre du stator chauffent le
bobinage ; les pertes fer et les pertes Joule du rotor chauffent la carcasse, qui évacue tout
vers l'air.

**Ce que ça montre.** Une résistance carcasse → air plus faible (meilleure ventilation) abaisse
toutes les températures.

**Dans l'application.** `core/thermal.py` : `simulate`, `ThermalParams` ; courbes de
température de l'onglet 5.

**Exemple** — réseau démo. C_b = {{ex:th_cw:4}} J/K, C_c = {{ex:th_cs:4}} J/K,
R_bc = {{ex:th_rws}} K/W, R_ca = {{ex:th_rsa}} K/W, air à {{ex:th_ta}} °C.

**Dans le cours.** Hors cours : le cours ne tient pas compte de l'échauffement (MAS A §5.1,
p. 89). Pour aller plus loin : Pyrhönen, « Design of Rotating Electrical Machines ».

### Constantes de temps et régime permanent

#### Constantes de temps du réseau

`τ = −1/λ`, λ valeurs propres de la matrice du réseau

| Symbole | Signification | Unité |
|---|---|---|
| λ | valeurs propres du système linéaire à deux nœuds | 1/s |
| τ_rapide, τ_lent | constantes de temps | s |

**Explication.** Un réseau à deux nœuds a deux constantes de temps. La plus courte décrit
l'échauffement du bobinage par rapport à la carcasse, la plus longue celui de toute la machine
par rapport à l'air. Après un échelon de pertes, la température rejoint son régime permanent en
quelques constantes de temps lentes.

**Ce que ça montre.** Un moteur à grande capacité thermique peut supporter des surcharges brèves
sans dépasser sa limite.

**Dans l'application.** `core/thermal.py` : `time_constants` ; texte « Constantes de temps »
de l'onglet 5.

**Exemple** — réseau démo. τ_rapide = {{ex:tau_rapide_min}} min et τ_lent = {{ex:tau_lent_min}} min.

**Dans le cours.** Hors cours.

#### Régime permanent à pertes constantes

`T_c = T_a + (P_b + P_c)·R_ca`,  `T_b = T_c + P_b·R_bc`

| Symbole | Signification | Unité |
|---|---|---|
| P_b + P_c | pertes totales du moteur | W |

**Explication.** Quand les températures ne varient plus, toute la chaleur traverse les
résistances : la carcasse s'élève au-dessus de l'air de (P_b + P_c)·R_ca, le bobinage au-dessus
de la carcasse de P_b·R_bc. Si les pertes cuivre croissent avec la température plus vite que le
réseau n'évacue la chaleur, il n'y a pas de régime permanent : c'est l'emballement thermique.

**Ce que ça montre.** Le régime permanent donne la température vers laquelle tend un service
continu.

**Dans l'application.** `core/thermal.py` : `steady_state`.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; réseau et cycle démo. Avec les
pertes moyennes du cycle (P_b = {{ex:p_cuivre_moy}} W, P_c = {{ex:p_fer_moy}} W) :
T_c = {{ex:ts_permanent}} °C et T_b = {{ex:tw_permanent}} °C.

**Dans le cours.** Hors cours.

### Pertes du cuivre

#### Pertes cuivre recalculées avec la température

`P_b = P_cu1,carte · (234,5 + T_b) / (234,5 + T_carte)`

| Symbole | Signification | Unité |
|---|---|---|
| P_cu1,carte | pertes cuivre du stator lues sur la carte | W |
| T_carte | température du bobinage pour laquelle la carte a été calculée | °C |

**Explication.** La carte donne les pertes cuivre pour une température de bobinage. Quand le
bobinage chauffe, R_s augmente comme la loi du cuivre (page 1) et les pertes avec elle, à courant
égal. L'application recalcule donc P_b à chaque pas de temps.

**Ce que ça montre.** Un bobinage chaud perd plus : l'échauffement s'amplifie lui-même.

**Dans l'application.** `core/thermal.py` : `simulate`, `cycle_losses`,
`map_copper_temperature`.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; réseau et cycle démo. Sur 10
cycles enchaînés, T_b atteint {{ex:tw_max}} °C (moyenne du dernier cycle {{ex:tw_moy}} °C) ;
marge à la classe F : {{ex:marge_classe}} K.

**Dans le cours.** Hors cours (loi du cuivre : Wildi, « Électrotechnique »).

#### Constante de temps à partir d'un refroidissement

`ln(T − T_a) = ln(T_0 − T_a) − t/τ`

| Symbole | Signification | Unité |
|---|---|---|
| T(t) | température du bobinage lue sur sa résistance pendant le refroidissement | K |
| τ | constante de temps du bobinage | s |

**Explication.** Après l'arrêt, on mesure la résistance du bobinage à plusieurs instants ; la
loi du cuivre la convertit en température. Une décroissance exponentielle donne une droite en
échelle logarithmique, dont la pente donne τ. C'est ainsi qu'on remplacera les valeurs démo du
réseau par des mesures.

**Ce que ça montre.** Quelques mesures de résistance suffisent à identifier la constante de
temps du bobinage.

**Dans l'application.** `core/thermal.py` : `fit_cooling_curve`.

**Exemple** — réseau démo. On laisse refroidir le réseau depuis son régime permanent et on lit la
résistance du bobinage {{ex:essai_n:i}} fois, à partir de {{ex:essai_debut_min:i}} min : l'ajustement
donne τ = {{ex:tau_essai_min}} min, proche de la constante lente du réseau ({{ex:tau_lent_min}} min),
qui domine le refroidissement tardif.

**Dans le cours.** Hors cours.

### Vieillissement de l'isolant

#### Règle des 10 K

`L = L_ref · 2^((T_classe − T)/10)` ;  pour une température variable :
`L = L_ref / moyenne(2^((T_b − T_classe)/10))`

| Symbole | Signification | Unité |
|---|---|---|
| T_classe | température de la classe d'isolation (classe F : 155 °C) | °C |
| L_ref | durée de vie à la température de classe | h |
| L | durée de vie estimée | h |

**Explication.** Les isolants vieillissent par réaction chimique, et la vitesse de ces réactions
double à peu près tous les 10 K : chaque 10 K de plus divise la durée de vie par deux. Quand la
température varie, ce sont les vitesses de vieillissement qui s'additionnent (règle de Miner) ;
les moments les plus chauds pèsent donc plus que la moyenne. Le résultat n'est qu'un ordre de
grandeur : le point le plus chaud du bobinage est plus chaud que sa moyenne calculée ici.

**Ce que ça montre.** Gagner 10 K sur la température du bobinage double la durée de vie de
l'isolant.

**Dans l'application.** `core/thermal.py` : `insulation_life`, `order_of_magnitude` ; tuile
« Durée de vie isolation ».

**Exemple** — classe F. À {{ex:t_classe_ex}} °C, L = {{ex:vie_classe:i}} h ; à {{ex:t_moins_10}} °C,
L = {{ex:vie_moins_10:i}} h ; 10 K au-dessus de la classe, L = {{ex:vie_plus_10:i}} h. Sur le
cycle démo (fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω)), L ≈ {{ex:vie_h:o}} h.

**Dans le cours.** Hors cours. Pour aller plus loin : IEC 60085 (classes thermiques).

## Hypothèses

- Paramètres du réseau : valeurs démo, faute de relevés de refroidissement chronométrés (A26).
- Pertes cuivre du stator au bobinage, recalculées avec sa température ; pertes fer et Joule du
  rotor à la carcasse ; pertes mécaniques et onduleur hors du réseau ; R_r' non corrigée (A27).
- Durée de vie par la règle des 10 K, avec L_ref à la température de classe ; ordre de grandeur
  seulement (A28).
- Avec R_s = 0 (moteur de référence), la carte n'a pas de pertes cuivre au stator : le bobinage
  n'est chauffé que par la carcasse et les résultats n'ont pas de sens.

## Avec votre moteur

Moteur utilisé par la chaîne : {{moteur:source}}.

| Grandeur | Valeur |
|---|---|
| R_s nulle (pas de pertes cuivre au stator) | {{moteur:r1_nul}} |
| R_s à la limite de la classe F ({{moteur:t_classe}} °C) | {{moteur:r1_classe:4}} Ω |

## Questions pour s'entraîner

**Q1.** Pourquoi deux constantes de temps et non une seule ?

??? Voir la réponse
Le réseau a deux nœuds qui stockent de la chaleur (bobinage et carcasse) : un système linéaire
d'ordre 2 a deux valeurs propres, donc deux constantes de temps.
???

**Q2.** Le bobinage passe de 130 °C à 140 °C. Comment varie la durée de vie de l'isolant ?

??? Voir la réponse
Elle est divisée par deux environ, d'après la règle des 10 K.
???

**Q3.** Pourquoi la durée de vie calculée n'est-elle qu'un ordre de grandeur ?

??? Voir la réponse
La règle est empirique, et la température utilisée est la moyenne du bobinage : le point le plus
chaud est plus chaud et vieillit plus vite.
???

[→ Ouvrir l'onglet 5](evlab://onglet/thermique)
