# 6 · Bobinage, force magnétomotrice et champ tournant

## Ce que fait cet onglet

L'onglet construit le bobinage triphasé à deux couches d'un stator à partir du nombre
d'encoches Z, du nombre de pôles 2p et du pas des bobines y. Il en calcule les facteurs de
bobinage, la force magnétomotrice (FMM) d'une phase et son spectre, la f.é.m. d'une phase, et
anime le champ tournant créé par trois courants équilibrés. Une fenêtre optionnelle compare ce
champ à un calcul par éléments finis.

## Lois et explications

### Géométrie du bobinage

#### Encoches par pôle et par phase, pas polaire et angle entre encoches

`q = Z / (2p·m)`,  `τ = Z / (2p)`,  `α = 2π·p / Z`

| Symbole | Signification | Unité |
|---|---|---|
| Z | nombre d'encoches du stator | — |
| 2p, m | nombre de pôles et nombre de phases (3) | — |
| q | encoches par pôle et par phase (appelé m dans le cours) | — |
| τ | pas polaire, en encoches | — |
| α | angle électrique entre deux encoches voisines | rad |

**Explication.** Sur un pas polaire, chacune des trois phases occupe q encoches voisines : c'est
une « bande » de phase. Deux encoches voisines sont décalées d'un angle électrique α, car le
champ se répète p fois sur un tour. Un bobinage régulier demande que q soit entier.

**Ce que ça montre.** Plus q est grand, plus la FMM se rapproche d'une sinusoïde.

**Dans l'application.** `core/winding.py` : `Winding` ; champs « Encoches Z » et « Pôles 2p ».

**Exemple** — bobinage par défaut : Z = 36, 2p = 4, y = 7. q = {{ex:w_q:i}}, τ = {{ex:w_tau:i}}
encoches et α = {{ex:w_alpha}}° électriques.

**Dans le cours.** Cours Pr Boughrara, Notions A §5.1, p. 17 (bobinages triphasés).

#### Tableau des encoches et spires par phase

couche haute : bandes `A+ C− B+ A− C+ B−` de q encoches ; couche basse = couche haute décalée de
y encoches, signe inversé ;  `N = (Z/m)·N_c / a`

| Symbole | Signification | Unité |
|---|---|---|
| y | pas des bobines, en encoches (entier) | — |
| N_c | spires par bobine | — |
| a | voies en parallèle | — |
| N | spires en série par phase | — |

**Explication.** Chaque bobine a un côté aller dans la couche haute d'une encoche et un côté
retour dans la couche basse de l'encoche située y encoches plus loin. Dans un bobinage à deux
couches, il y a autant de bobines que d'encoches, soit Z/m bobines par phase. Le pas y doit être
un nombre entier d'encoches : un « pas de 5/6 » vaudrait 7,5 encoches pour 36 encoches et
4 pôles, ce qui est impossible.

**Ce que ça montre.** Raccourcir le pas (y < τ) décale les deux couches et mélange les phases
dans certaines encoches.

**Dans l'application.** `core/winding.py` : `slot_table`, `slot_conductors`, `turns_per_phase` ;
tableau des encoches de l'onglet 6.

**Exemple** — bobinage par défaut : Z = 36, 2p = 4, y = 7. Avec N_c = {{ex:w_nc:i}} spires par
bobine, N = {{ex:n_phase:i}} spires par phase.

**Dans le cours.** Cours Pr Boughrara, Notions A §5.1, p. 17 ; le bobinage à pas raccourci est
hors cours.

### Facteurs de bobinage

#### Facteur de distribution

`k_d,ν = sin(ν·q·α/2) / (q·sin(ν·α/2))`

| Symbole | Signification | Unité |
|---|---|---|
| ν | rang de l'harmonique (1 = fondamental) | — |
| k_d,ν | facteur de distribution | — |

**Explication.** Les q encoches d'une bande portent des f.é.m. égales mais décalées de α. Leur
somme vectorielle est plus petite que q fois une f.é.m. : le rapport est le facteur de
distribution. Pour les harmoniques, le décalage vaut ν·α et les f.é.m. se compensent beaucoup
plus.

**Ce que ça montre.** Distribuer le bobinage sur plusieurs encoches réduit fortement les
harmoniques en ne coûtant que quelques pour cent sur le fondamental.

**Dans l'application.** `core/winding.py` : `distribution_factor` ; tableau « Facteurs de
bobinage ».

**Exemple** — bobinage par défaut : Z = 36, 2p = 4, y = 7. k_d,1 = {{ex:kd1:4}}.

**Dans le cours.** Cours Pr Boughrara, Synchrone B §3.2, p. 37 (K_d, noté avec m encoches par
pôle et par phase).

#### Facteur de pas et facteur de bobinage

`k_p,ν = sin(ν·(y/τ)·π/2)`,  `k_w,ν = k_d,ν · k_p,ν`

| Symbole | Signification | Unité |
|---|---|---|
| k_p,ν | facteur de pas (de raccourcissement) | — |
| k_w,ν | facteur de bobinage | — |

**Explication.** Une bobine dont les deux côtés sont distants de y < τ encoches n'embrasse pas
tout le flux d'un pôle : sa f.é.m. est multipliée par k_p. Pour l'harmonique ν, l'angle est ν fois
plus grand et k_p peut devenir très petit, voire changer de signe. Le facteur de bobinage
combine distribution et pas.

**Ce que ça montre.** Un pas de 7/9 sacrifie un peu de fondamental pour réduire beaucoup les
harmoniques 5 et 7.

**Dans l'application.** `core/winding.py` : `pitch_factor`, `winding_factor` ; tableau
« Facteurs de bobinage » (y = τ et y choisi).

**Exemple** — bobinage par défaut, Z = 36, 2p = 4. Pas diamétral y = 9 : k_w,1 = {{ex:kw1_y9:4}},
k_w,5 = {{ex:kw5_y9:4}}, k_w,7 = {{ex:kw7_y9:4}} ; pas raccourci y = 7 : k_p,1 = {{ex:kp1_y7:4}},
k_w,1 = {{ex:kw1_y7:4}}, k_w,5 = {{ex:kw5_y7:4}}, k_w,7 = {{ex:kw7_y7:4}}.

**Dans le cours.** Hors cours (le cours ne traite que la distribution). Pour aller plus loin :
Pyrhönen, « Design of Rotating Electrical Machines ».

### FMM et champ tournant

#### FMM en escalier d'une phase et ses harmoniques

FMM d'une phase : saut de `i·(conducteurs de l'encoche)` à chaque encoche ;
harmonique ν : `|F_ν| / |F_1| = |k_w,ν| / (ν·|k_w,1|)` (ν impair, zéro pour ν pair)

| Symbole | Signification | Unité |
|---|---|---|
| F(θ) | FMM d'une phase le long de l'entrefer | A·tr |
| F_ν | amplitude de l'harmonique ν | A·tr |

**Explication.** Le théorème d'Ampère dit que la FMM augmente, à chaque passage devant une
encoche, du courant total qu'elle contient : la FMM d'une phase est une fonction en escalier.
Sa décomposition en série de Fourier donne des harmoniques d'amplitude proportionnelle à
k_w,ν/ν. Les bandes A+ et A− sont distantes d'un pas polaire avec des signes opposés : la FMM a
une symétrie de demi-onde et ses harmoniques pairs sont nuls.

**Ce que ça montre.** L'escalier est d'autant plus proche d'une sinusoïde que q est grand et que
le pas est bien choisi.

**Dans l'application.** `core/winding.py` : `phase_mmf`, `mmf_spectrum`, `analytical_spectrum` ;
spectre de la FMM d'une phase.

**Exemple** — bobinage par défaut : Z = 36, 2p = 4, y = 7 ; 1 A, N_c = {{ex:w_nc:i}}. Le palier le
plus haut de l'escalier vaut {{ex:f_phase_max}} A·tr et son fondamental {{ex:f1_phase}} A·tr ;
harmoniques 5 et 7 : {{ex:h5_y7:2}} % et {{ex:h7_y7:2}} % du fondamental.

**Dans le cours.** Cours Pr Boughrara, Notions A §6.1 et §6.2, p. 23–24 (FMM d'une bobine et
d'un bobinage monophasé) ; les harmoniques en k_w,ν/ν sont hors cours.

#### Champ tournant de trois courants équilibrés

`F(θ, t) = Σ_k i_k(t)·N_k(θ)`,  `i_k = I·cos(ω·t − 2πk/3)` ⇒ fondamental
`(3/2)·F_1·cos(ω·t − p·θ)`, vitesse `Ω = ω/p`

| Symbole | Signification | Unité |
|---|---|---|
| i_k | courant de la phase k (A, B, C) | A |
| F_1 | fondamental de la FMM d'une phase pour le courant crête I | A·tr |
| Ω | vitesse de rotation du champ | rad/s |

**Explication.** Chaque phase crée une FMM fixe dans l'espace dont l'amplitude oscille dans le
temps. Trois phases décalées de 120° dans l'espace, parcourues par des courants décalés de 120°
dans le temps, donnent une onde d'amplitude constante, 3/2 fois celle d'une phase, qui tourne à
Ω = ω/p (théorème de Ferraris ; le théorème de Leblanc décompose chaque champ alternatif en
deux champs tournants).

**Ce que ça montre.** Le champ tourne d'autant moins vite que le nombre de pôles est grand.

**Dans l'application.** `core/winding.py` : `rotating_field` ; animation « FMM d'entrefer
tournante ».

**Exemple** — bobinage par défaut : Z = 36, 2p = 4, y = 7 ; 1 A crête, 50 Hz. Fondamental
tournant {{ex:f_tournant}} A·tr, soit {{ex:rapport_tournant:3}} fois celui d'une phase.

**Dans le cours.** Cours Pr Boughrara, Notions A §4.2 à §4.6, p. 9–14 (champ tournant, théorème
de Leblanc) et §6.3–6.4, p. 25–26 (FMM triphasée, Ω = ω/p).

### F.é.m. et entrefer

#### F.é.m. d'une phase

`E = 4,44 · f · N · k_w,1 · Φ`

| Symbole | Signification | Unité |
|---|---|---|
| f | fréquence | Hz |
| N | spires en série par phase | — |
| Φ | flux par pôle | Wb |
| E | f.é.m. efficace d'une phase | V |

**Explication.** Un flux sinusoïdal Φ·sin(ωt) induit dans N spires la f.é.m. N·ω·Φ en valeur
crête, soit 2π/√2 ≈ 4,44 fois N·f·Φ en valeur efficace. Le bobinage réel distribué et raccourci
embrasse un peu moins de flux : on multiplie par k_w,1.

**Ce que ça montre.** La f.é.m. est proportionnelle à la fréquence et au flux : à flux constant,
elle croît comme la vitesse.

**Dans l'application.** `core/winding.py` : `emf`, `pole_pairs_from_speed`,
`turns_from_conductors` ; bloc « Force électromotrice ».

**Exemple** — bobinage par défaut : Z = 36, 2p = 4, y = 7. Avec N = {{ex:n_phase:i}} spires,
Φ = {{ex:w_flux}} Wb et 50 Hz : E = {{ex:emf:4}} V ; à 1500 tr/min et 50 Hz,
p = {{ex:p_vitesse:i}}.

**Dans le cours.** Cours Pr Boughrara, MAS A §4, p. 86–87 (E₁ = 4,44·N₁·f₁·Φ, à multiplier par le
coefficient de bobinage) et Synchrone B §3.1–3.2, p. 37.

#### Effet des encoches sur l'entrefer : facteur de Carter

`k_c = τ_s / (τ_s − γ·e)`,  `γ = (4/π)·[u·atan(u) − ln √(1 + u²)]`,  `u = b_0/(2e)` ;
`B = μ_0·F / (k_c·e)`

| Symbole | Signification | Unité |
|---|---|---|
| τ_s | pas dentaire à l'alésage | m |
| b_0 | ouverture d'encoche | m |
| e | entrefer mécanique | m |
| k_c | facteur de Carter | — |
| B | induction dans l'entrefer | T |

**Explication.** Les ouvertures d'encoches allongent le chemin du flux : tout se passe comme si
l'entrefer valait k_c·e au lieu de e. L'induction d'une FMM F à travers l'entrefer vaut alors
μ_0·F/(k_c·e), si l'on néglige la FMM consommée dans le fer. La fenêtre « Animation FEM » compare
cette valeur au calcul par éléments finis.

**Ce que ça montre.** Des encoches plus ouvertes ou un entrefer plus petit augmentent k_c.

**Dans l'application.** `core/winding.py` : `carter_factor`, `gap_flux_density` ; fenêtre
« Animation FEM ».

**Exemple** — géométrie démo de la fenêtre FEM, y = 7, N_c = {{ex:w_nc:i}}. τ_s = {{ex:pas_dentaire_mm}} mm,
b_0 = {{ex:ouverture_mm}} mm, e = {{ex:entrefer_mm}} mm : k_c = {{ex:carter:4}} ; à
{{ex:i_crete}} A crête, F_1 = {{ex:f1_6a}} A·tr donne B = {{ex:b_lisse}} T sans encoches et
{{ex:b_entrefer}} T avec Carter.

**Dans le cours.** Hors cours. Pour aller plus loin : Pyrhönen, « Design of Rotating Electrical
Machines » ; manuel de FEMM 4.2.

## Hypothèses

- Conducteurs d'une encoche concentrés au centre de l'encoche ; bobinage triphasé à deux
  couches, nombre entier d'encoches par pôle et par phase (A29).
- Courants triphasés équilibrés et sinusoïdaux ; les harmoniques de temps ne sont pas étudiés.
- La FMM est calculée sans saturation ni ouverture d'encoche ; le facteur de Carter n'est
  utilisé que pour comparer au calcul par éléments finis (géométrie démo, A32).

## Avec votre moteur

Moteur utilisé par la chaîne : {{moteur:source}}.

| Grandeur | Valeur |
|---|---|
| Paires de pôles p | {{moteur:p:i}} |
| Vitesse du champ tournant | {{moteur:n_s:4}} tr/min |
| F.é.m. nominale E_n | {{moteur:e_n}} V |

## Questions pour s'entraîner

**Q1.** Pourquoi un pas de « 5/6 » est-il impossible avec 36 encoches et 4 pôles ?

??? Voir la réponse
Le pas polaire vaut τ = 9 encoches : 5/6 de 9 font 7,5 encoches, or un côté de bobine doit être
dans une encoche entière.
???

**Q2.** Pourquoi les harmoniques pairs de la FMM sont-ils nuls ?

??? Voir la réponse
Les bandes A+ et A− sont distantes d'un pas polaire avec des courants de signes opposés : la FMM
vérifie F(θ + π/p) = −F(θ), ce qui annule tous les harmoniques pairs.
???

**Q3.** Que devient la vitesse du champ tournant si l'on passe de 4 à 8 pôles à 50 Hz ?

??? Voir la réponse
Elle est divisée par deux : Ω = ω/p passe de 1500 à 750 tr/min.
???

[→ Ouvrir l'onglet 6](evlab://onglet/bobinage)
