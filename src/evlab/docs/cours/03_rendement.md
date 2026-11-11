# 3 · Rendement et carte des pertes

## Ce que fait cet onglet

Pour chaque couple et chaque vitesse à l'intérieur de l'enveloppe, l'onglet résout le point de
fonctionnement du même schéma équivalent, sous la même loi V/f, et calcule toutes les pertes :
cuivre, fer, mécaniques et onduleur. Il en tire le rendement et trace la carte η(Γ, Ω), avec
l'enveloppe et les points du cycle de l'onglet 4.

## Lois et explications

### Pertes cuivre

#### Pertes Joule au stator et au rotor

`p_js = 3·R_s(T_b)·I_s²`,  `p_jr = 3·R_r'·I_r'² = g·P_s'`

| Symbole | Signification | Unité |
|---|---|---|
| R_s(T_b) | résistance d'une phase à la température du bobinage T_b | Ω |
| I_s, I_r' | courants statorique et rotorique ramené | A |
| p_js, p_jr | pertes Joule au stator et au rotor | W |
| P_s' | puissance transmise au rotor | W |

**Explication.** Chaque phase dissipe R·I² : trois phases au stator, trois au rotor. Au rotor,
ces pertes valent exactement la fraction g de la puissance transmise par l'entrefer : plus le
moteur glisse, plus il chauffe son rotor. R_s est ramenée à la température de fonctionnement du
bobinage par la loi du cuivre (page 1).

**Ce que ça montre.** Les pertes cuivre croissent comme le carré du courant, donc presque comme
le carré du couple : elles dominent à fort couple.

**Dans l'application.** `core/losses.py` : `stator_resistance`, `efficiency_map` ;
`core/circuit.py` : `operating_point`.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). R_s vaut {{ex:demo_r1_tw:4}} Ω
à {{ex:demo_tw}} °C ; au point de meilleur rendement, p_js = {{ex:best_p_cu1}} W et
p_jr = {{ex:best_p_cu2}} W.

**Dans le cours.** Cours Pr Boughrara, MAS C §5.2 et §5.4, p. 126 (p_js = 3·R_s·I_s²,
p_jr = g·P_s').

### Pertes fer

#### Loi de Steinmetz ramenée à R_μ(f)

`p_fer ∝ f^β·B²` avec `B ∝ E/f`  ⇒  `R_μ(f) = R_μ · (f/f_n)^(2−β)`

| Symbole | Signification | Unité |
|---|---|---|
| β | exposant de fréquence des pertes fer (hystérésis : 1, courants de Foucault : 2) | — |
| B | induction dans les tôles | T |
| R_μ(f) | résistance de pertes fer à la fréquence f | Ω |

**Explication.** Les pertes fer viennent de l'hystérésis (∝ f·B²) et des courants de Foucault
(∝ f²·B²) ; on les résume par une loi en f^β avec β entre 1 et 2. L'essai à vide ne donne R_μ
qu'à f_n. Comme p_fer = 3·E²/R_μ et que B suit E/f, faire varier R_μ comme (f/f_n)^(2−β) suffit
pour que les pertes suivent la loi de Steinmetz, tout en gardant les courants du schéma
cohérents. À f_n, rien ne change.

**Ce que ça montre.** Au-dessus de f_n, R_μ augmente : à tension fixe, les pertes fer augmentent
moins vite que la fréquence.

**Dans l'application.** `core/losses.py` : `iron_resistance` ; réglage « Exposant β fer » de
l'onglet 3.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). Avec β = {{ex:beta}},
R_μ = {{ex:demo_rf}} Ω à 50 Hz devient {{ex:demo_rf_f100}} Ω à 100 Hz ; au point de meilleur
rendement ({{ex:best_f}} Hz), p_fer = {{ex:best_p_fe}} W.

**Dans le cours.** Le cours donne p_fer = 3·V_s²/R_μ et néglige les pertes fer du rotor (MAS A
§6.2, p. 96 ; MAS C §5.4, p. 126). La loi de Steinmetz est hors cours. Pour aller plus loin :
Pyrhönen, « Design of Rotating Electrical Machines ».

### Pertes mécaniques et onduleur

#### Pertes mécaniques en fonction de la vitesse

`P_méc(Ω) = a·Ω + b·Ω²`,  avec `a·Ω_0 = s·p_méc` et `b·Ω_0² = (1 − s)·p_méc`

| Symbole | Signification | Unité |
|---|---|---|
| Ω_0 | vitesse de synchronisme nominale, où p_méc a été mesurée | rad/s |
| s | part des frottements (∝ Ω) dans p_méc | — |
| a, b | coefficients de frottement et de ventilation | W·s, W·s² |

**Explication.** Les frottements des roulements créent un couple presque constant, donc une
puissance ∝ Ω ; la ventilation crée une puissance ∝ Ω². L'essai à vide ne mesure p_méc qu'à une
vitesse : la loi passe par ce point, et la part s des frottements est une hypothèse.

**Ce que ça montre.** À deux fois la vitesse nominale, les pertes mécaniques font plus que
doubler.

**Dans l'application.** `core/losses.py` : `mechanical_loss` ; réglage « Part frottements ».

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). P_méc = {{ex:demo_pmec_w0}} W à
{{ex:demo_n0:4}} tr/min et {{ex:demo_pmec_2w0}} W au double de cette vitesse.

**Dans le cours.** Le cours les prend constantes près de la vitesse nominale (MAS C §5.4,
p. 127). La loi en a·Ω + b·Ω² est hors cours.

#### Pertes de l'onduleur

`P_ond = P_0 + k·P_moteur`

| Symbole | Signification | Unité |
|---|---|---|
| P_0 | pertes fixes (commande, commutation à vide) | W |
| k | part proportionnelle à la puissance absorbée par le moteur | — |

**Explication.** Les interrupteurs de l'onduleur ont des pertes de conduction et de commutation
qui croissent avec la puissance transmise, plus une consommation fixe. Le modèle le plus simple
est une droite ; ses deux coefficients sont des valeurs démo.

**Ce que ça montre.** Aux faibles puissances, P_0 fait chuter le rendement de la chaîne.

**Dans l'application.** `core/losses.py` : `efficiency_map` ; réglages « Onduleur fixe » et
« Onduleur proportionnel ».

**Exemple** — valeurs démo. P_0 = {{ex:inv_p0}} W et k = {{ex:inv_k}} % ; au point de meilleur
rendement, P_ond = {{ex:best_p_inv}} W.

**Dans le cours.** Hors cours.

### Rendement

#### Couple sur l'arbre

`Γ_arbre = Γ − P_méc(Ω)/Ω`

| Symbole | Signification | Unité |
|---|---|---|
| Γ | couple électromagnétique | N·m |
| Γ_arbre | couple disponible sur l'arbre | N·m |

**Explication.** La carte est tracée en couple sur l'arbre, celui que voit la transmission du
véhicule. Le couple électromagnétique de l'enveloppe est diminué du couple perdu en frottements
et ventilation.

**Ce que ça montre.** L'écart entre les deux couples grandit avec la vitesse, comme P_méc.

**Dans l'application.** `core/losses.py` : `shaft_torque_limit` ; enveloppe tracée sur la carte.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). À {{ex:demo_n_mid:4}} tr/min,
Γ = {{ex:demo_t_em_mid}} N·m et Γ_arbre = {{ex:demo_t_arbre_mid}} N·m.

**Dans le cours.** Cours Pr Boughrara, MAS A §6.2.2, p. 96 (P_u = P_méc − p_méc).

#### Bilan de puissance et rendement

`P_abs = P_u + p_js + p_jr + p_fer + P_méc + P_ond`,  `η = P_u / P_abs`

| Symbole | Signification | Unité |
|---|---|---|
| P_u | puissance utile sur l'arbre, Γ_arbre·Ω | W |
| P_abs | puissance absorbée côté continu (moteur + onduleur) | W |
| η | rendement de la chaîne onduleur + moteur | — |

**Explication.** Toute la puissance absorbée ressort soit en puissance utile, soit en pertes :
c'est le bilan de puissance du cours, complété par l'onduleur. Le rendement est le rapport de
la puissance utile à la puissance absorbée.

**Ce que ça montre.** Le rendement est mauvais à faible couple (pertes fixes) et à très fort
couple (pertes cuivre) : son maximum se trouve à charge moyenne et vitesse élevée.

**Dans l'application.** `core/losses.py` : `efficiency_map`, `best_point` ; carte η(Γ, n) et
point de meilleur rendement.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). Meilleur point :
η = {{ex:demo_eta_max}} % à {{ex:demo_t_best}} N·m et {{ex:demo_n_best:4}} tr/min, soit
P_u = {{ex:best_p_out:4}} W pour P_abs = {{ex:best_p_in:4}} W ({{ex:best_eta_bilan}} %).

**Dans le cours.** Cours Pr Boughrara, MAS C §5.6 et §5.7, p. 127–128.

## Hypothèses

- Même schéma, même loi V/f et mêmes limites que l'onglet 2 ; un point n'est valide que s'il
  respecte i_max et la marge au décrochage avec le schéma de la carte (A17).
- Pertes fer de Steinmetz avec β = 1,5, valeur typique des tôles : l'essai à vide ne donne R_μ
  qu'à f_n (A19).
- Part des frottements 0,5 dans p_méc : une seule mesure de p_méc est disponible (A20).
- Pertes de l'onduleur : valeurs démo (A21).
- R_s corrigée à la température du bobinage ; R_r' n'est pas corrigée (A27).

## Avec votre moteur

Moteur utilisé par la chaîne : {{moteur:source}}.

| Grandeur | Valeur |
|---|---|
| R_s à la température de la carte | {{moteur:r1_tw:4}} Ω |
| R_μ à 100 Hz (β = 1,5) | {{moteur:rf_f100}} Ω |
| Pertes fer nominales 3·E_n²/R_μ | {{moteur:p_fer_n}} W |
| p_méc | {{moteur:p_mech}} W |

## Questions pour s'entraîner

**Q1.** Pourquoi le rendement chute-t-il à faible couple ?

??? Voir la réponse
Les pertes fer, mécaniques et fixes de l'onduleur ne dépendent presque pas du couple : quand la
puissance utile devient petite, elles en représentent une grande part.
???

**Q2.** Que vaut l'effet de β à la fréquence nominale ?

??? Voir la réponse
Aucun : R_μ(f_n) = R_μ quel que soit β. L'exposant ne change les pertes fer qu'aux autres
fréquences.
???

**Q3.** Pourquoi les pertes Joule du rotor valent-elles g·P_s' ?

??? Voir la réponse
La puissance transmise au rotor est 3·(R_r'/g)·I_r'² et les pertes Joule du rotor 3·R_r'·I_r'² :
leur rapport vaut exactement g.
???

[→ Ouvrir l'onglet 3](evlab://onglet/rendement)
