# 7 · Optimisation de conception

## Ce que fait cet onglet

L'onglet cherche les meilleurs réglages du variateur et du véhicule pour le moteur identifié :
rapport de réduction, boost de la loi V/f, marge de défluxage et rebobinage du moteur. Chaque
essai de réglage enchaîne les modèles déjà testés des onglets 2 à 5, sans physique nouvelle.
Comme on veut à la fois consommer peu et accélérer vite, le résultat est un front de Pareto : la
liste des meilleurs compromis entre ces deux objectifs.

## Lois et explications

### Variables

#### Rebobinage du moteur

spires × k_N à section de cuivre constante ⇒ `R_s, R_r', R_μ, X_μ, l_s'ω_s` × `k_N²`

| Symbole | Signification | Unité |
|---|---|---|
| k_N | rapport entre le nouveau et l'ancien nombre de spires | — |

**Explication.** Si l'on bobine k_N fois plus de spires dans les mêmes encoches, chaque spire a
une section k_N fois plus petite et le fil est k_N fois plus long : la résistance est multipliée
par k_N². Les inductances varient comme le carré du nombre de spires : les réactances aussi. La
tension nominale, la fréquence et la limite de courant du variateur restent les mêmes.

**Ce que ça montre.** Plus de spires (k_N > 1) réduisent le courant et le flux à tension donnée ;
moins de spires donnent plus de couple à haute vitesse, au prix d'un courant plus fort.

**Dans l'application.** `core/optimise.py` : `rewound` ; bornes « Rebobinage k_N ».

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). Avec k_N = {{ex:k_n}}, le facteur
vaut k_N² = {{ex:k_n2}} : R_r' passe de {{ex:r2_k1}} Ω à {{ex:r2_kn}} Ω et l_s'ω_s de
{{ex:x_k1}} Ω à {{ex:x_kn}} Ω.

**Dans le cours.** Hors cours. Pour aller plus loin : Pyrhönen, « Design of Rotating Electrical
Machines ».

#### Rapport, boost et marge

variables : `G`, `V_0`, `marge`, `k_N` ; chacune entre une borne basse et une borne haute

| Symbole | Signification | Unité |
|---|---|---|
| G | rapport de réduction (onglet 4) | — |
| V_0 | boost de la loi V/f (onglet 2) | V |
| marge | fraction utilisable du couple de décrochage (onglet 2) | — |

**Explication.** Le rapport G règle le compromis couple au démarrage / vitesse maximale, le boost
relève le couple à basse vitesse, la marge autorise à s'approcher plus ou moins du décrochage.
Une borne basse égale à la borne haute fixe la variable.

**Ce que ça montre.** Chaque variable libre ajoute une dimension à la recherche.

**Dans l'application.** `core/optimise.py` : `Design`, `Bounds` ; bornes des variables.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; véhicule et cycle démo. Le
réglage de base est G = {{ex:veh_g:4}}, V_0 = 0 V, marge = {{ex:marge}} et k_N = 1.

**Dans le cours.** Hors cours.

### Objectifs

#### Consommation et accélération

minimiser `Wh/km` (onglet 4) et `t(0–50 km/h)` (onglet 4)

| Symbole | Signification | Unité |
|---|---|---|
| Wh/km | consommation sur le cycle choisi | Wh/km |
| t(0–50 km/h) | temps de 0 à 50 km/h à pleine puissance | s |

**Explication.** Les deux objectifs s'opposent souvent : un rapport plus court accélère mieux
mais fait tourner le moteur plus vite et dans des zones de rendement différentes. Chaque
évaluation recalcule l'enveloppe, une carte de rendement, le cycle et l'échauffement avec les
modèles des onglets 2 à 5.

**Ce que ça montre.** Il n'y a pas un meilleur réglage, mais un ensemble de compromis.

**Dans l'application.** `core/optimise.py` : `evaluate` ; axes du front de Pareto.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; véhicule et cycle démo. Réglage de
base : {{ex:base_wh}} Wh/km et {{ex:base_t050}} s de 0 à 50 km/h.

**Dans le cours.** Hors cours.

### Contraintes

#### Les quatre contraintes

`min(Γ_limite/Γ_demandé) ≥ 1` ;  `T_b,max ≤ T_classe − 20 K` ;  `I_s ≤ i_max` ;
`max (E/f)/(E_n/f_n) ≤ 1,10`

| Symbole | Signification | Unité |
|---|---|---|
| Γ_limite/Γ_demandé | marge de couple au pire point du cycle | — |
| T_b,max | température maximale du bobinage sur les cycles enchaînés | °C |
| (E/f)/(E_n/f_n) | flux d'entrefer relatif sur l'enveloppe | — |

**Explication.** Un réglage n'est admissible que si tout le cycle reste dans l'enveloppe, si le
bobinage reste au moins 20 K sous la température de sa classe, si le courant reste sous la limite
de l'onduleur et si le flux ne dépasse pas de plus de 10 % sa valeur nominale (au-delà, le
circuit magnétique saturerait et le modèle linéaire ne serait plus valable). Le temps de 0 à
50 km/h doit aussi exister.

**Ce que ça montre.** Un boost trop fort augmente le flux à basse vitesse ; un rapport trop long
fait sortir le cycle de l'enveloppe.

**Dans l'application.** `core/optimise.py` : `evaluate` ; colonne « admissible » des
évaluations.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; réglage de base. Marge de couple
{{ex:base_marge}}, T_b,max = {{ex:base_tw}} °C pour une limite de {{ex:t_limite}} °C, courant
maximal {{ex:base_i}} A (limite {{ex:i_max}} A), flux relatif maximal {{ex:base_flux}} (limite
{{ex:flux_limite}}).

**Dans le cours.** Hors cours (classes d'isolation : IEC 60085).

### Méthode

#### Évolution différentielle avec pénalité

score = objectif si admissible, sinon `10⁶ + violation` ;  budget fixe :
`générations = budget / population − 1`

| Symbole | Signification | Unité |
|---|---|---|
| violation | somme normalisée des dépassements de contraintes | — |
| population | nombre de réglages essayés par génération | — |

**Explication.** L'évolution différentielle fait évoluer une population de réglages : à chaque
génération, de nouveaux réglages sont formés en combinant les anciens, et les meilleurs sont
gardés. Un réglage non admissible reçoit un score énorme augmenté de sa violation, de sorte que
tout réglage admissible l'emporte sur tout réglage qui ne l'est pas. Chaque point du front coûte
le même nombre d'évaluations, quel que soit le nombre de variables libres.

**Ce que ça montre.** Plus de budget donne un front plus précis, au prix d'un calcul plus long.

**Dans l'application.** `core/optimise.py` : `optimise`, `generations`, `run_evaluations` ;
réglage « Évaluations / point ».

**Exemple** — réglages par défaut, 4 variables libres. Budget {{ex:budget:i}} évaluations par
point, soit {{ex:generations:i}} générations et {{ex:evals_point:i}} évaluations ; pénalité
{{ex:penalite:o}}.

**Dans le cours.** Hors cours.

#### Front de Pareto par ε-contrainte

minimiser `Wh/km` sous `t(0–50) ≤ ε`, pour plusieurs ε entre les deux extrêmes ; un point est
non dominé si aucun autre n'est meilleur sur les deux objectifs à la fois

| Symbole | Signification | Unité |
|---|---|---|
| ε | temps de 0 à 50 km/h imposé | s |

**Explication.** On cherche d'abord les deux extrêmes : la consommation minimale et le temps
minimal. Entre les deux, on minimise la consommation en imposant un temps au plus égal à ε, pour
plusieurs valeurs de ε. Parmi toutes les évaluations, on garde celles qu'aucune autre ne bat sur
les deux objectifs : c'est le front de Pareto.

**Ce que ça montre.** Le long du front, gagner en accélération coûte de l'énergie.

**Dans l'application.** `core/optimise.py` : `pareto_front`, `non_dominated`, `gains` ; front de
Pareto et tableau « Base vs design sélectionné ».

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). Le réglage de base sert de
référence aux gains en % du tableau : {{ex:base_wh}} Wh/km et {{ex:base_t050}} s.

**Dans le cours.** Hors cours.

## Hypothèses

- Aucune physique nouvelle : chaque évaluation enchaîne les modèles testés des onglets 2 à 5,
  avec une carte de rendement plus grossière pour la vitesse de calcul (A31).
- Rebobinage à section de cuivre constante : toutes les impédances × k_N² ; tension nominale,
  limite de courant et fréquence maximale inchangées (A31).
- Contraintes traitées par pénalité, front par ε-contrainte (A31).
- Contrainte de flux : le circuit magnétique est linéaire, donc le modèle n'est fiable que près
  du flux nominal (A33).

## Avec votre moteur

Moteur utilisé par la chaîne : {{moteur:source}}.

| Grandeur | Valeur |
|---|---|
| R_r' et l_s'ω_s rebobinés (k_N = {{ex:k_n}}) | {{moteur:r2_kn}} Ω et {{moteur:x_kn}} Ω |
| Limite de flux 1,10·E_n/f_n | {{moteur:flux_limite_v}} V/Hz |

## Questions pour s'entraîner

**Q1.** Pourquoi les impédances varient-elles comme k_N² et non comme k_N ?

??? Voir la réponse
La résistance augmente par la longueur du fil (× k_N) et par la réduction de sa section (÷ k_N),
soit k_N² ; les inductances, donc les réactances, varient comme le carré du nombre de spires.
???

**Q2.** Que signifie qu'un réglage est « dominé » ?

??? Voir la réponse
Un autre réglage admissible est au moins aussi bon sur les deux objectifs et strictement
meilleur sur l'un : il n'y a aucune raison de choisir le réglage dominé.
???

**Q3.** Pourquoi limiter le flux d'entrefer à 1,10 fois sa valeur nominale ?

??? Voir la réponse
Au-delà, le fer saturerait. Le schéma équivalent garde X_μ constante et ne voit pas cette
saturation : ses résultats ne seraient plus fiables.
???

[→ Ouvrir l'onglet 7](evlab://onglet/optimisation)
