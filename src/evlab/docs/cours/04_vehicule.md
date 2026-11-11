# 4 · Véhicule et cycle WLTC

## Ce que fait cet onglet

L'onglet construit un véhicule adapté au moteur identifié (en démo, un quadricycle léger), lit
sa classe WLTC d'après son rapport puissance/masse et propose un rapport de réduction qui garde
tout le cycle dans l'enveloppe. Il simule ensuite le cycle seconde par seconde et calcule
l'énergie prise à la batterie, la consommation en Wh/km et l'énergie récupérée au freinage.

## Lois et explications

### Dynamique du véhicule

#### Force à la roue

`F = m·a + ½·ρ·C_x·S·v² + C_rr·m·g·cos θ + m·g·sin θ`

| Symbole | Signification | Unité |
|---|---|---|
| m | masse du véhicule (avec conducteur) | kg |
| a, v | accélération et vitesse du véhicule | m/s², m/s |
| ρ | masse volumique de l'air | kg/m³ |
| C_x·S | surface frontale × coefficient de traînée | m² |
| C_rr | coefficient de résistance au roulement | — |
| θ | pente de la route | rad |

**Explication.** C'est le principe fondamental de la dynamique appliqué au véhicule : la force
motrice doit accélérer la masse et vaincre trois résistances. La traînée aérodynamique croît
comme le carré de la vitesse, la résistance au roulement est presque constante, et la pente
ajoute la composante du poids le long de la route. Véhicule arrêté et immobile, la force est
nulle (les freins le tiennent).

**Ce que ça montre.** En ville, l'inertie domine (accélérations fréquentes) ; sur route, la
traînée aérodynamique devient la plus grande résistance.

**Dans l'application.** `core/vehicle.py` : `road_force` ; paramètres du véhicule de
l'onglet 4.

**Exemple** — véhicule démo. m = {{ex:veh_m}} kg, C_x·S = {{ex:veh_cxs}} m², C_rr = {{ex:veh_crr}} :
à {{ex:ex_v_kmh}} km/h avec a = {{ex:ex_a}} m/s² sur route plate, F = {{ex:ex_force:4}} N.

**Dans le cours.** Hors cours. Pour aller plus loin : Ehsani, « Modern Electric, Hybrid
Electric and Fuel Cell Vehicles ».

### Transmission

#### Vitesse et couple du moteur

`ω_m = G·v/r` ;  `Γ = F·r/(G·η_g)` en traction,  `Γ = F·r·η_g/G` en freinage

| Symbole | Signification | Unité |
|---|---|---|
| G | rapport de réduction (vitesse moteur / vitesse roue) | — |
| r | rayon dynamique de la roue | m |
| η_g | rendement de la transmission | — |
| ω_m, Γ | vitesse et couple du moteur | rad/s, N·m |

**Explication.** Le réducteur multiplie la vitesse de la roue par G et divise le couple par G.
En traction, il faut fournir un peu plus de couple pour compenser les pertes du réducteur ; en
freinage récupératif, le moteur en reçoit un peu moins. Le couple de freinage récupéré est
limité par l'enveloppe ; le reste va aux freins à friction.

**Ce que ça montre.** Un rapport G plus grand donne plus de couple à la roue au démarrage mais
fait tourner le moteur plus vite, plus loin dans le défluxage.

**Dans l'application.** `core/vehicle.py` : `motor_speed`, `motor_torque`, `simulate`.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; véhicule démo. Avec
G = {{ex:veh_g:4}}, r = {{ex:veh_r}} m et η_g = {{ex:veh_eta}}, la force de l'exemple précédent
demande Γ = {{ex:ex_couple}} N·m à {{ex:ex_n_mot:4}} tr/min.

**Dans le cours.** Hors cours (P_u = Γ_u·Ω, MAS C §5.5, p. 127).

### Classe WLTC et dimensionnement

#### Puissance nominale et classe WLTC

`P_n = max_Ω (Γ_arbre·Ω)`,  `RPM = P_n / m` ;  classe 1 si RPM ≤ 22 W/kg, 2 si ≤ 34 W/kg, 3 au-delà

| Symbole | Signification | Unité |
|---|---|---|
| P_n | puissance nominale du moteur (maximum sur l'enveloppe) | W |
| RPM | rapport puissance/masse | W/kg |

**Explication.** La procédure WLTP choisit le cycle d'essai selon le rapport puissance/masse du
véhicule : un véhicule peu puissant roule le cycle de classe 1, moins rapide. Pour un véhicule
électrique, la puissance retenue est la puissance maximale du moteur, lue ici sur l'enveloppe à
l'arbre.

**Ce que ça montre.** Alourdir le véhicule ou réduire le moteur peut faire changer de classe,
donc de cycle.

**Dans l'application.** `core/vehicle.py` : `rated_power`, `wltc_class`, `wltc_class_for` ;
encadré « Classe WLTC et cycle ».

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; véhicule démo.
P_n = {{ex:p_rated:4}} W, RPM = {{ex:pmr}} W/kg, classe {{ex:classe:i}}.

**Dans le cours.** Hors cours. Pour aller plus loin : UN GTR No. 15 (procédure WLTP).

#### Rapport de réduction proposé

`G_max = 0,95·r·Ω_max / v_max`, puis `G` ≤ `G_max` qui maximise `min(Γ_limite/Γ_demandé)` sur le
cycle

| Symbole | Signification | Unité |
|---|---|---|
| Ω_max, v_max | vitesse maximale de l'enveloppe et du cycle | rad/s, m/s |
| Γ_limite/Γ_demandé | marge de couple à un point du cycle | — |

**Explication.** Le rapport le plus long compatible avec la vitesse maximale du cycle place
celle-ci juste sous Ω_max. En dessous, l'application essaie plusieurs rapports et garde celui
qui laisse la plus grande marge de couple au pire point du cycle : un rapport trop long manque
de couple au démarrage, un rapport trop court pousse le moteur dans le défluxage.

**Ce que ça montre.** Une marge inférieure à 1 signifie qu'un point du cycle sort de l'enveloppe.

**Dans l'application.** `core/vehicle.py` : `size_vehicle`, `torque_margin` ; bouton
« Proposer ».

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; véhicule et cycle démo.
G_max = {{ex:veh_g_max:4}}, G proposé = {{ex:veh_g:4}}, marge au pire point
{{ex:marge_cycle}}.

**Dans le cours.** Hors cours. Pour aller plus loin : Ehsani, « Modern Electric, Hybrid
Electric and Fuel Cell Vehicles ».

### Énergie et performances

#### Puissance batterie et consommation

`P_batt = Γ·ω_m + P_pertes(|Γ|, ω_m) + P_aux` ;  `Wh/km = ∫P_batt dt / distance`

| Symbole | Signification | Unité |
|---|---|---|
| P_pertes | pertes moteur + onduleur lues sur la carte de l'onglet 3 | W |
| P_aux | puissance des auxiliaires | W |
| P_batt | puissance prise à la batterie (négative en récupération) | W |

**Explication.** À chaque seconde, la batterie fournit la puissance mécanique du moteur plus
ses pertes et celles de l'onduleur, plus les auxiliaires. En freinage, Γ·ω_m devient négatif :
la batterie se recharge. L'énergie du cycle est la somme de ces puissances, et la consommation
l'énergie divisée par la distance parcourue.

**Ce que ça montre.** La récupération rend une partie de l'énergie cinétique, d'autant plus que
le cycle comporte de nombreux freinages.

**Dans l'application.** `core/vehicle.py` : `simulate` ; tuiles « Consommation » et
« Récupéré ».

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; véhicule et cycle démo.
{{ex:cycle_km}} km parcourus, {{ex:cycle_wh_total:4}} Wh pris à la batterie, soit {{ex:cycle_wh}} Wh/km ;
{{ex:cycle_regen}} % de l'énergie de traction récupérée.

**Dans le cours.** Hors cours. Pour aller plus loin : Ehsani, « Modern Electric, Hybrid
Electric and Fuel Cell Vehicles ».

#### Temps de 0 à 50 km/h

`t = ∫₀^v m·dv / (F_max(v) − F_rés(v))`

| Symbole | Signification | Unité |
|---|---|---|
| F_max | force maximale à la roue, depuis l'enveloppe à l'arbre | N |
| F_rés | résistances aérodynamique, de roulement et de pente | N |

**Explication.** À pleine puissance, l'accélération vaut (F_max − F_rés)/m ; le temps pour
gagner dv est m·dv divisé par la force nette. On additionne ces temps de l'arrêt à 50 km/h.

**Ce que ça montre.** Plus de couple à basse vitesse (rapport G plus grand, boost) réduit ce
temps ; une plus grande masse l'allonge.

**Dans l'application.** `core/vehicle.py` : `acceleration_time` ; second objectif de
l'onglet 7.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω) ; véhicule démo.
t(0–50 km/h) = {{ex:t_0_50}} s.

**Dans le cours.** Hors cours.

## Hypothèses

- Véhicule démo : quadricycle léger (L7e), masse, C_x·S, C_rr, rayon, rendement de la
  transmission et auxiliaires de l'hypothèse A22.
- Puissance nominale = puissance maximale à l'arbre sur l'enveloppe (A23).
- Pertes lues sur la carte par interpolation ; pertes en génératrice prises égales aux pertes
  en moteur au même |Γ| et à la même vitesse (A24).
- Cycle démo synthétique (pas un cycle WLTC) tant que les fichiers WLTC officiels ne sont pas
  dans data/ (A25).
- Temps de 0 à 50 km/h sans l'inertie des pièces tournantes (A30).

## Avec votre moteur

Moteur utilisé par la chaîne : {{moteur:source}} (véhicule démo de {{moteur:masse}} kg).

| Grandeur | Valeur |
|---|---|
| Puissance nominale P_n | {{moteur:p_nom:4}} W |
| Rapport puissance/masse | {{moteur:pmr}} W/kg |
| Classe WLTC | {{moteur:classe:i}} |

## Questions pour s'entraîner

**Q1.** Pourquoi la traînée aérodynamique compte-t-elle peu dans un cycle urbain ?

??? Voir la réponse
Elle croît comme v² : aux faibles vitesses de la ville, elle est petite devant la force
d'accélération m·a et la résistance au roulement.
???

**Q2.** Que se passe-t-il si le rapport G est trop long ?

??? Voir la réponse
Le couple à la roue manque au démarrage et dans les accélérations : des points du cycle sortent
de l'enveloppe (marge < 1).
???

**Q3.** Pourquoi la puissance batterie devient-elle négative ?

??? Voir la réponse
Au freinage récupératif, le moteur fonctionne en génératrice : Γ·ω_m est négatif et dépasse les
pertes et les auxiliaires, la batterie se recharge.
???

[→ Ouvrir l'onglet 4](evlab://onglet/vehicule)
