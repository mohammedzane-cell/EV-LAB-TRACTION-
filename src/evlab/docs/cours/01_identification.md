# 1 · Identification du schéma équivalent

## Ce que fait cet onglet

À partir des essais de laboratoire (essai en courant continu, essais à vide, essai à rotor
bloqué et points en charge), l'onglet retrouve les éléments du schéma équivalent monophasé de
la machine asynchrone : R_s, R_μ, X_μ, l_s'ω_s et R_r'. Deux voies sont comparées : les formules
classiques du cours, puis un ajustement par moindres carrés sur les points en charge. Le moteur
obtenu est ensuite celui de tous les autres onglets.

## Lois et explications

### Essais

#### Résistance d'une phase : essai en courant continu

`R_s = U_dc / (2·I_dc)`

| Symbole | Signification | Unité |
|---|---|---|
| U_dc | tension continue mesurée entre deux bornes | V |
| I_dc | courant continu injecté | A |
| R_s | résistance d'une phase du stator (couplage étoile) | Ω |

**Explication.** En continu, les inductances ne jouent aucun rôle : seule la résistance du
cuivre limite le courant. Entre deux bornes d'un stator couplé en étoile, le courant traverse
deux phases en série, d'où le facteur 2. C'est la résistance R_eq « entre deux bornes » du
cours, qui donne les pertes Joule du stator p_js = (3/2)·R_eq·I_s².

**Ce que ça montre.** Une erreur sur U_dc ou I_dc se reporte directement sur R_s, puis sur
toutes les pertes Joule du stator des onglets 3 et 5.

**Dans l'application.** `core/identification.py` : `r1_from_dc` ; champ « R1 (DC) » de
l'onglet 1.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). U_dc = {{ex:dc_u:4}} V et
I_dc = {{ex:dc_i:4}} A donnent R_s = {{ex:r1_froid:4}} Ω à {{ex:dc_t}} °C.

**Dans le cours.** Cours Pr Boughrara, MAS C §5.2, p. 126 (pertes Joule au stator,
résistance entre deux bornes).

#### Correction de la résistance avec la température

`R_s(T) = R_s(T_m) · (234,5 + T) / (234,5 + T_m)`

| Symbole | Signification | Unité |
|---|---|---|
| T_m | température du bobinage pendant la mesure en continu | °C |
| T | température du bobinage pendant les autres essais | °C |
| R_s(T_m), R_s(T) | résistance d'une phase à ces deux températures | Ω |

**Explication.** La résistance du cuivre croît presque linéairement avec la température ; la
droite passe par zéro vers −234,5 °C pour le cuivre recuit. La mesure en continu se fait à
froid, les essais à vide et à rotor bloqué bobinage chaud : il faut ramener R_s à la
température des essais avant de soustraire les pertes Joule.

**Ce que ça montre.** Entre {{ex:dc_t}} °C et {{ex:t_chaud}} °C, la résistance augmente de
{{ex:r1_hausse}} % ; sans cette correction, p_fer, p_méc et R_r' seraient faussées.

**Dans l'application.** `core/identification.py` : `r1_at_temperature` ; `core/circuit.py` :
`copper_resistance` ; champ « Température R1 » de l'onglet 1.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). R_s = {{ex:r1_froid:4}} Ω à
{{ex:dc_t}} °C devient R_s = {{ex:r1_chaud:4}} Ω à {{ex:t_chaud}} °C.

**Dans le cours.** Hors cours. Pour aller plus loin : Wildi, « Électrotechnique ».

#### Tension simple et couplage étoile

`V_s = U / √3`

| Symbole | Signification | Unité |
|---|---|---|
| U | tension composée mesurée entre deux phases | V |
| V_s | tension simple appliquée à une phase | V |

**Explication.** Le stator est couplé en étoile : chaque phase est branchée entre une ligne et
le point neutre. La tension entre deux lignes vaut alors √3 fois la tension d'une phase. Le
schéma équivalent décrit une seule phase et utilise donc la tension simple ; les puissances
mesurées restent les puissances triphasées totales.

**Ce que ça montre.** Oublier le √3 multiplierait toutes les impédances identifiées par 3.

**Dans l'application.** `core/identification.py` : `NoLoadTest.from_line`,
`LockedRotorTest.from_line` ; lecture des fichiers d'essais de l'onglet 1.

**Exemple** — moteur de référence, sans bruit. V_s = {{ex:ref_v}} V par phase correspond à
U = √3·V_s = {{ex:ref_u}} V entre phases (la plaque « 230/400 V » arrondit à 400 V).

**Dans le cours.** Couplage étoile (pas de section dédiée).

#### Essai à vide : séparation des pertes fer et mécaniques

`P'_0 = P_0 − 3·R_s·I_0²`  et  `P'_0 = a·U_0² + p_méc`

| Symbole | Signification | Unité |
|---|---|---|
| P_0, I_0, U_0 | puissance, courant et tension composée d'un point à vide | W, A, V |
| P'_0 | puissance à vide sans les pertes Joule du stator | W |
| a | pente de la droite (pertes fer ∝ U²) | W/V² |
| p_méc | pertes mécaniques (frottements et ventilation) | W |

**Explication.** À vide, le moteur absorbe presque uniquement ses pertes fer et ses pertes
mécaniques. Les pertes fer varient comme le carré de la tension (le flux est proportionnel à la
tension) ; les pertes mécaniques restent constantes tant que la vitesse reste proche du
synchronisme. En traçant P'_0 en fonction de U_0², on obtient une droite dont l'ordonnée à
l'origine donne p_méc. Le cours néglige les pertes Joule du stator à vide ; l'application les
retire (3·R_s·I_0²) avant le tracé.

**Ce que ça montre.** Plus les points à vide sont nombreux et étalés en tension, plus
l'extrapolation vers U = 0 est fiable.

**Dans l'application.** `core/identification.py` : `mechanical_losses` ; étape « p_méc » de
l'identification.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). Les {{ex:n_vide:i}} points à vide donnent
p_méc = {{ex:p_mec}} W ; les mêmes fichiers générés sans bruit donnent
{{ex:p_mec_sans_bruit}} W (valeur qui a servi à les fabriquer : {{ex:p_mec_ref}} W).

**Dans le cours.** Cours Pr Boughrara, MAS C §2, p. 121–122 (essai à vide, tracé en fonction
du carré de la tension).

#### Puissance réactive absorbée à vide

`Q_0 = √((3·V_s·I_0)² − P_0²)`

| Symbole | Signification | Unité |
|---|---|---|
| V_s, I_0 | tension simple et courant du point à vide nominal | V, A |
| P_0 | puissance active absorbée | W |
| Q_0 | puissance réactive absorbée | var |

**Explication.** La puissance apparente triphasée vaut 3·V_s·I_0. Elle se décompose en une
partie active P_0 et une partie réactive Q_0, liées par le triangle des puissances. À vide, la
puissance réactive sert presque entièrement à magnétiser la machine.

**Ce que ça montre.** Un moteur à vide a un facteur de puissance faible : Q_0 est bien plus
grand que P_0.

**Dans l'application.** `core/identification.py` : `no_load_branch`.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). Au point à vide nominal,
Q_0 = {{ex:q0:4}} var pour P_0 = {{ex:p0:4}} W.

**Dans le cours.** Cours Pr Boughrara, MAS C §5.1, p. 125 (relations entre P_s, Q_s et S_s).

#### Branche magnétisante : R_μ et X_μ

`R_μ = 3·E² / p_fer`  et  `X_μ = 3·E² / Q_0`,  avec `p_fer = P'_0 − p_méc`

| Symbole | Signification | Unité |
|---|---|---|
| p_fer | pertes fer au point à vide nominal | W |
| E | tension aux bornes de la branche magnétisante | V |
| R_μ | résistance qui représente les pertes fer | Ω |
| X_μ | réactance magnétisante | Ω |

**Explication.** Dans le schéma équivalent, les pertes fer sont représentées par une résistance
R_μ en parallèle sur X_μ : la puissance qu'elle dissipe, 3·E²/R_μ, vaut les pertes fer. De même,
la puissance réactive à vide est celle de X_μ. Le cours écrit p_fer = 3·V_s²/R_μ parce que sa
Figure 7 place la branche magnétisante directement aux bornes : elle voit alors toute la
tension V_s. Dans la disposition par défaut (R1 en premier), R_s est traversée par le courant
à vide et la branche ne voit que E = |V_s − R_s·I_0| : p_fer = 3·E²/R_μ. Les deux écritures
sont identiques quand R_s = 0. Les formules classiques prennent E ≈ V_s ; la méthode exacte
utilise E.

**Ce que ça montre.** Plus les pertes fer sont grandes, plus R_μ est petite ; plus le courant
magnétisant est grand, plus X_μ est petite.

**Dans l'application.** `core/identification.py` : `no_load_branch` (méthodes « classique »
et « exacte ») ; colonnes Rf et Xm du tableau de l'onglet 1.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). Formules classiques :
R_μ = {{ex:rf_classique}} Ω et X_μ = {{ex:xm_classique}} Ω ; méthode exacte :
R_μ = {{ex:rf_exact}} Ω et X_μ = {{ex:xm_exact}} Ω (fabrication : {{ex:demo_ref_rf}} Ω et
{{ex:demo_ref_xm}} Ω). Sur le moteur de référence sans bruit,
3·V_s²/R_μ = {{ex:ref_pfer_formule}} W et le schéma donne p_fer = {{ex:ref_pfer}} W : identiques,
car R_s = 0.

**Dans le cours.** Cours Pr Boughrara, MAS A §5.2, p. 94 (R_μ en parallèle sur X_μ) et MAS A
§6.2, p. 96 (p_fer = 3·V_s²/R_μ) ; MAS C §2, p. 122 (composante réactive du courant à vide).
La forme E = |V_s − R_s·I_0| est hors cours.

#### Rotor bloqué : formules classiques

`R_cc = P_cc / (3·I_cc²)`,  `Z_cc = V_cc / I_cc`,  `R_r' = R_cc − R_s`,  `l_s'ω_s = √(Z_cc² − R_cc²)`

| Symbole | Signification | Unité |
|---|---|---|
| V_cc, I_cc, P_cc | tension simple, courant et puissance de l'essai à rotor bloqué | V, A, W |
| R_cc, Z_cc | résistance et impédance vues de l'entrée à g = 1 | Ω |
| R_r' | résistance du rotor ramenée au stator | Ω |
| l_s'ω_s | réactance de fuites totale ramenée au stator | Ω |

**Explication.** Rotor bloqué, le glissement vaut 1 : la branche rotorique a une faible
impédance et, sous tension réduite, le courant magnétisant devient petit. On néglige donc la
branche magnétisante : le moteur se réduit à R_s + R_r' + j·l_s'ω_s en série. La partie active
de l'impédance mesurée donne R_s + R_r', sa partie réactive la réactance de fuites.

**Ce que ça montre.** Cette approximation sous-estime R_r' et l_s'ω_s, car |Z_μ| n'est que
{{ex:ref_zm_sur_z2:2}} fois plus grande que l'impédance du rotor à g = 1 sur le moteur de
référence (hypothèse A9).

**Dans l'application.** `core/identification.py` : `locked_rotor` (méthode « classique ») ;
ligne « Formules classiques » du tableau.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). R_r' = {{ex:r2_classique}} Ω et
l_s'ω_s = {{ex:x_classique}} Ω (valeurs qui ont servi à fabriquer les fichiers :
{{ex:demo_ref_r2}} Ω et {{ex:demo_ref_x}} Ω).

**Dans le cours.** Cours Pr Boughrara, MAS C §3, p. 123 (essai à rotor bloqué) et MAS A §6,
p. 94 (schéma de la Figure 7).

#### Rotor bloqué : inversion exacte du schéma

`Z_2 = 1 / (1/(Z_cc − R_s) − 1/Z_μ)`,  `Z_μ = R_μ ∥ j·X_μ` ;  `R_r' = Re(Z_2)`,  `l_s'ω_s = Im(Z_2)`

| Symbole | Signification | Unité |
|---|---|---|
| Z_cc | impédance complexe mesurée rotor bloqué | Ω |
| Z_μ | impédance de la branche magnétisante | Ω |
| Z_2 | impédance de la branche rotorique à g = 1 | Ω |

**Explication.** Au lieu de négliger la branche magnétisante, on la retire du calcul : on
enlève R_s, puis on « débranche » Z_μ, qui est en parallèle. Il reste exactement la branche
rotorique R_r' + j·l_s'ω_s. La méthode utilise R_μ et X_μ trouvées à vide.

**Ce que ça montre.** L'écart entre les deux méthodes mesure l'erreur de l'approximation
classique ; il grandit quand X_μ diminue.

**Dans l'application.** `core/identification.py` : `locked_rotor` (méthode « exacte »).

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). R_r' = {{ex:r2_exact}} Ω et
l_s'ω_s = {{ex:x_exact}} Ω. L'écart à {{ex:demo_ref_r2}} Ω vient du bruit, pas de la méthode : les
{{ex:bruit_pct:2}} % de bruit
sur U, I et P de l'unique point à rotor bloqué se reportent sur R_cc, et la soustraction de
R_s les amplifie. Les mêmes fichiers générés sans bruit donnent R_r' = {{ex:r2_exact_sans_bruit:4}} Ω
et l_s'ω_s = {{ex:x_exact_sans_bruit:4}} Ω.

**Dans le cours.** Hors cours (inversion du schéma de la disposition par défaut).

### Schéma équivalent

#### Courant statorique et facteur de puissance

`I_s = V_s / Z_s`,  `cos φ_s = Re(I_s) / |I_s|`

| Symbole | Signification | Unité |
|---|---|---|
| Z_s | impédance d'une phase vue de l'entrée, au glissement g | Ω |
| I_s | courant d'une phase du stator | A |
| cos φ_s | facteur de puissance | — |

**Explication.** Vu du réseau, le moteur se comporte comme une impédance qui dépend du
glissement. À vide (g → 0), la branche rotorique est presque ouverte : seul passe le courant
magnétisant, fortement déphasé. Quand g augmente, R_r'/g diminue : le courant augmente et
devient plus actif.

**Ce que ça montre.** Le courant augmente avec la charge ; au démarrage (g = 1), il devient
très grand.

**Dans l'application.** `core/circuit.py` : `impedance`, `stator_current`, `power_factor` ;
courbe courant–glissement de l'onglet 1.

**Exemple** — moteur de référence, sans bruit. À g = 0,1 : I_s = {{ex:ref_i1}} A et
cos φ_s = {{ex:ref_cos}}.

**Dans le cours.** Cours Pr Boughrara, MAS A §6.1.1, p. 95.

#### Courant rotorique : source vue par le rotor

`I_r' = |V_th| · g / |Z_th·g + R_r' + j·l_s'ω_s·g|`

| Symbole | Signification | Unité |
|---|---|---|
| V_th, Z_th | source équivalente vue par la branche rotorique (Thévenin) | V, Ω |
| I_r' | courant rotorique ramené au stator | A |
| g | glissement | — |

**Explication.** Vue de la branche rotorique, tout le reste du schéma se résume à une source
V_th en série avec une impédance Z_th. Dans le schéma du cours (Figure 7, branche magnétisante
aux bornes), V_th = V_s et Z_th = R_s. Dans la disposition par défaut (R1 en premier),
V_th = V_s·Z_μ/(R_s + Z_μ) et Z_th = R_s ∥ Z_μ.

**Ce que ça montre.** À g = 0 le courant rotorique est nul ; il croît avec g puis tend vers une
limite quand R_r'/g devient négligeable.

**Dans l'application.** `core/circuit.py` : `thevenin`, `rotor_current`.

**Exemple** — moteur de référence, sans bruit. À g = 0,1 : I_r' = {{ex:ref_i2}} A.

**Dans le cours.** Cours Pr Boughrara, MAS A §6.1.2, p. 95.

#### Glissement et vitesse du rotor

`g = (Ω_s − Ω) / Ω_s`,  `Ω_s = ω_s / p`

| Symbole | Signification | Unité |
|---|---|---|
| ω_s | pulsation des courants statoriques (2π·f) | rad/s |
| Ω_s | vitesse de synchronisme (vitesse du champ tournant) | rad/s |
| Ω | vitesse du rotor | rad/s |
| p | nombre de paires de pôles | — |

**Explication.** Le rotor tourne un peu moins vite que le champ : ce retard fait couper les
conducteurs du rotor par le champ, y induit des courants de fréquence g·f et produit le couple.
À la vitesse de synchronisme (g = 0), il n'y a plus ni courant rotorique ni couple.

**Ce que ça montre.** Un glissement de quelques pour cent suffit en fonctionnement nominal.

**Dans l'application.** `core/circuit.py` : `mechanical_speed`, `slip_from_speed` ; axe des
vitesses de l'onglet 1.

**Exemple** — moteur de référence, sans bruit. Ω_s = {{ex:ref_ws:4}} rad/s, soit
{{ex:ref_ns:4}} tr/min ; à g = 0,1, Ω = {{ex:ref_w:4}} rad/s, soit {{ex:ref_n:4}} tr/min.

**Dans le cours.** Cours Pr Boughrara, MAS A §4.1, p. 87.

### Couple et puissances

#### Couple électromagnétique

`Γ = (3·p/ω_s) · (R_r'/g) · I_r'²`

| Symbole | Signification | Unité |
|---|---|---|
| 3·(R_r'/g)·I_r'² | puissance transmise au rotor à travers l'entrefer, P_s' | W |
| Γ | couple électromagnétique | N·m |

**Explication.** La puissance transmise au rotor vaut 3·(R_r'/g)·I_r'². Le champ tourne à
Ω_s = ω_s/p : le couple est cette puissance divisée par Ω_s, d'où le nom de « couple
synchrone » donné par le cours. La part g·P_s' est perdue en effet Joule dans le rotor, le reste
(1 − g)·P_s' devient puissance mécanique.

**Ce que ça montre.** Aux faibles glissements, le couple est presque proportionnel à g : c'est
la partie utile, presque droite, de la caractéristique mécanique.

**Dans l'application.** `core/circuit.py` : `torque`, `operating_point` ; courbe
couple–glissement de l'onglet 1.

**Exemple** — moteur de référence, sans bruit. À g = 0,1 : Γ = {{ex:ref_couple}} N·m.

**Dans le cours.** Cours Pr Boughrara, MAS A §6.2 et §6.3, p. 96–97.

#### Couple utile sur l'arbre

`Γ_u = Γ − p_méc / Ω`

| Symbole | Signification | Unité |
|---|---|---|
| Γ_u | couple utile sur l'arbre | N·m |
| p_méc | pertes mécaniques | W |

**Explication.** Une partie de la puissance mécanique développée, (1 − g)·P_s', sert à vaincre
les frottements et la ventilation. Ce qui reste sur l'arbre est la puissance utile
P_u = Γ_u·Ω. Les points en charge mesurent le couple sur l'arbre : le modèle retire donc p_méc
avant de les comparer.

**Ce que ça montre.** À faible charge, p_méc pèse relativement plus : le couple utile est
nettement inférieur au couple électromagnétique.

**Dans l'application.** `core/identification.py` : `fit_load_points` (couple du modèle).

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). Avec p_méc = {{ex:p_mec}} W à
{{ex:demo_n_g02:4}} tr/min (point g = 0,02), le couple perdu vaut {{ex:demo_dt_g02}} N·m.

**Dans le cours.** Cours Pr Boughrara, MAS A §6.2.2, p. 96 et MAS C §5.5, p. 127.

#### Point de décrochage

`g_c = R_r' / √(R_th² + (X_th + l_s'ω_s)²)`,
`Γ_max = 3·p·|V_th|² / (2·ω_s·(R_th + √(R_th² + (X_th + l_s'ω_s)²)))`

| Symbole | Signification | Unité |
|---|---|---|
| g_c | glissement de décrochage (couple maximal) | — |
| Γ_max | couple maximal | N·m |
| R_th, X_th | partie réelle et partie imaginaire de Z_th | Ω |

**Explication.** Le couple passe par un maximum quand la résistance R_r'/g « s'adapte » à
l'impédance de la source vue du rotor : c'est le théorème du transfert maximal de puissance.
Avec R_s = 0, on retrouve les formules du cours g_c = R_r'/(l_s'ω_s) et
Γ_max = 3·p·V_s²/(2·l_s'ω_s·ω_s).

**Ce que ça montre.** Le couple maximal ne dépend pas de R_r' ; seul le glissement où il se
produit lui est proportionnel.

**Dans l'application.** `core/circuit.py` : `breakdown_slip`, `max_torque`, `breakdown` ;
point « C_max, g_c » de la courbe couple–glissement.

**Exemple** — moteur de référence, sans bruit. g_c = {{ex:ref_gc}} et
Γ_max = {{ex:ref_tmax:4}} N·m.

**Dans le cours.** Cours Pr Boughrara, MAS A §7, p. 98.

### Ajustement par moindres carrés

#### Ajustement sur les points en charge et intervalles de confiance

`min Σ_k ρ(r_k²)`,  `r_k = (modèle_k − mesure_k) / |mesure_k|` ;
`Cov = s²·(JᵀJ)⁻¹`,  intervalle à 95 % : `θ ± t·√Cov_ii`

| Symbole | Signification | Unité |
|---|---|---|
| r_k | écart relatif entre le modèle et une lecture (courant, couple, cos φ) | — |
| ρ | fonction « soft L1 » qui atténue les lectures aberrantes | — |
| θ | paramètres ajustés : X_μ, l_s'ω_s, R_r' | Ω |
| J | matrice des dérivées des écarts par rapport aux paramètres | — |
| s² | variance des écarts au point optimal | — |
| t | coefficient de Student à 95 % | — |

**Explication.** Les formules classiques n'utilisent qu'un point par essai ; les points en
charge en donnent beaucoup plus. On cherche les valeurs de X_μ, l_s'ω_s et R_r' pour lesquelles
le modèle reproduit au mieux les courants, couples et facteurs de puissance mesurés. R_s (essai
en continu) et R_μ (essai à vide) restent fixes, car les points en charge les déterminent mal.
La matrice de covariance donne un intervalle de confiance pour chaque paramètre et leurs
corrélations ρ_ij.

**Ce que ça montre.** Si deux paramètres sont très corrélés (|ρ| > 0,95), les mesures ne
permettent pas de les séparer : l'application affiche un avertissement.

**Dans l'application.** `core/identification.py` : `fit_load_points`, `check_correlation` ;
ligne « Optimisation » du tableau, infobulle « Intervalle de confiance à 95 % ».

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). R_r' = {{ex:r2_fit}} Ω, intervalle
à 95 % [{{ex:r2_ci_bas}} ; {{ex:r2_ci_haut}}] Ω, qui contient la valeur de fabrication
{{ex:demo_ref_r2}} Ω.

**Dans le cours.** Hors cours (le cours décrit l'essai en charge, MAS C §4, p. 124). Pour aller
plus loin : Boldea, « Induction Machines Handbook ».

#### Écart à la référence

`e = 100 · (valeur − référence) / référence`

| Symbole | Signification | Unité |
|---|---|---|
| e | écart relatif | % |

**Explication.** Pour les fichiers démo, le circuit qui a servi à fabriquer les mesures est
connu : l'onglet affiche l'écart de chaque méthode à ce circuit. Avec de vraies mesures, il
n'existe pas de référence et les écarts ne sont pas affichés.

**Ce que ça montre.** Un écart négatif signifie que la méthode sous-estime le paramètre.

**Dans l'application.** `core/identification.py` : `relative_error` ; pourcentages entre
parenthèses dans le tableau.

**Exemple** — fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω). R_r' des formules classiques :
e = {{ex:e_r2_classique:s3}} %.

**Dans le cours.** Hors cours.

## Hypothèses

- Le modèle reprend les hypothèses fondamentales du cours (MAS A §5.1, p. 88–89) : pas de
  saturation, champs à répartition sinusoïdale, machine symétrique, entrefer constant, pas
  d'effet de peau ; les pertes fer sont ajoutées par R_μ.
- Disposition par défaut (R1 en premier) ; le schéma de la Figure 7 du cours (branche
  magnétisante aux bornes) est la disposition « Bornes ». Les deux sont identiques quand
  R_s = 0 (A1).
- Couplage étoile, tensions simples (A5).
- Pertes mécaniques constantes près du synchronisme et pertes fer ∝ U² pour la séparation à
  vide ; ce n'est qu'approché quand R_s ≠ 0 (A8).
- Les formules classiques du rotor bloqué négligent la branche magnétisante : R_r'
  {{ex:ref_e_r2_classique:s3}} % et l_s'ω_s {{ex:ref_e_x_classique:s2}} % sur le moteur de
  référence, sans bruit (A9, A15).
- L'ajustement ne règle que X_μ, l_s'ω_s et R_r' ; R_s et R_μ viennent des essais en continu et
  à vide (A13). Ses intervalles de confiance n'incluent pas l'incertitude de R_s et R_μ (A14).
- C'est acceptable ici parce que chaque étape est vérifiée sur des données dont on connaît le
  circuit exact ([page Validation](evlab://page/validation)).

## Avec votre moteur

Moteur utilisé par la chaîne : {{moteur:source}}.

| Élément | Valeur |
|---|---|
| R_s (à {{moteur:t_r1}} °C) | {{moteur:r1:4}} Ω |
| R_μ | {{moteur:r_fe}} Ω |
| X_μ | {{moteur:x_m}} Ω |
| l_s'ω_s | {{moteur:x_leak}} Ω |
| R_r' | {{moteur:r2p}} Ω |
| p_méc | {{moteur:p_mech}} W |
| g_c et Γ_max | {{moteur:g_c}} et {{moteur:t_max:4}} N·m |

## Questions pour s'entraîner

**Q1.** Pourquoi divise-t-on U_dc par 2·I_dc et non par I_dc ?

??? Voir la réponse
Entre deux bornes d'un stator en étoile, le courant continu traverse deux phases en série : on
mesure 2·R_s.
???

**Q2.** À l'essai à vide, pourquoi trace-t-on P'_0 en fonction de U_0² plutôt que de U_0 ?

??? Voir la réponse
Les pertes fer sont proportionnelles au carré de la tension : en fonction de U_0², la courbe
devient une droite, et son ordonnée à l'origine (p_méc) se lit sans extrapolation hasardeuse.
???

**Q3.** La formule classique du rotor bloqué donne R_r' trop petite. Pourquoi ?

??? Voir la réponse
Elle néglige la branche magnétisante. En réalité, Z_μ est en parallèle sur la branche
rotorique et abaisse l'impédance mesurée Z_cc, donc la résistance qu'on en déduit.
???

[→ Ouvrir l'onglet 1](evlab://onglet/identification)
