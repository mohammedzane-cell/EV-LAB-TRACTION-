# Hypothèses et limites

Chaque modèle de l'application néglige quelque chose. Cette page reprend, en français simple,
toutes les hypothèses du fichier `docs/assumptions.md` (numéros A1 à A33). Une hypothèse n'est
gardée que si ni le schéma identifié ni une mesure ne peuvent fournir la valeur.

## Schéma équivalent (onglets 1 à 3)

- **A1 — Deux dispositions du schéma.** Par défaut, R1 en premier : R_s est en tête, puis la
  branche magnétisante R_μ ∥ X_μ, puis la branche rotorique. La disposition « Bornes » est celle
  de la Figure 7 du cours : la branche magnétisante directement aux bornes. Elles sont identiques
  quand R_s = 0.
- **A2 — Réactances proportionnelles à la fréquence** sous la loi V/f ; R_s, R_r' et R_μ restent
  constantes.
- **A3 — Pertes cuivre et pertes fer selon la disposition** : 3·R_s·I_s² et 3·E²/R_μ par défaut
  (E = V_s − R_s·I_s) ; 3·R_s·I_r'² et 3·V_s²/R_μ dans la disposition « Bornes ».
- **A4 — Loi du cuivre** : résistance nulle à −234,5 °C, référence à 20 °C.
- **A10 — Rendement du schéma seul** sans pertes mécaniques ; elles sont ajoutées à l'onglet 3.
- **A33 — Circuit magnétique linéaire** : X_μ et l_s'ω_s ne dépendent que de la fréquence, pas
  du flux ; pas de saturation. Le flux est suivi par E/f et limité à {{ex:flux_limite}} fois sa
  valeur nominale dans l'optimisation.

## Identification (onglet 1)

- **A5 — Essai en continu entre deux bornes** d'un stator couplé en étoile : R_s = U_dc/(2·I_dc).
- **A6 — Essai à vide à tension et fréquence nominales** : elles deviennent V_n et f_n du moteur
  identifié.
- **A7 — Sans essai en continu**, R_s est prise nulle.
- **A8 — Séparation des pertes à vide** : pertes mécaniques constantes près du synchronisme,
  pertes fer ∝ U². Avec R_s ≠ 0, l'extrapolation est légèrement biaisée (fichiers démo sans
  bruit : {{ex:p_mec_sans_bruit}} W pour {{ex:p_mec_ref}} W).
- **A9 — Formules classiques du rotor bloqué** : la branche magnétisante est négligée.
- **A11 — Méthode exacte** : elle inverse la disposition choisie ; les formules classiques sont
  les mêmes quelle que soit la disposition.
- **A12 — Point à vide utilisé** : le plus proche de la tension de plaque, à moins de 10 %.
- **A13 — Ajustement sur trois paramètres** (X_μ, l_s'ω_s, R_r') ; R_s et R_μ viennent des essais
  en continu et à vide, car les points en charge les déterminent mal.
- **A14 — Écarts relatifs à chaque lecture** dans l'ajustement ; intervalles de confiance
  linéarisés, sans l'incertitude de R_s et R_μ.
- **A15 — Biais des formules classiques** sur le moteur de référence sans bruit : R_r'
  {{ex:ref_e_r2_classique:s3}} %, l_s'ω_s {{ex:ref_e_x_classique:s2}} %.

## Variateur et enveloppe (onglet 2)

- **A16 — Réglages démo du variateur** : i_max = {{ex:i_max}} A, boost 0 V, marge
  {{ex:marge}}, f_max = {{ex:f_max}} Hz.
- **A17 — Enveloppe calculée vitesse par vitesse** : à chaque vitesse, le variateur choisit la
  fréquence rotorique qui donne le plus grand couple sous les trois limites ; couple
  électromagnétique ; fréquence statorique au moins égale à f_n/100 ; R_μ constante dans
  l'enveloppe.
- **A18 — Limites de zones lues sur la courbe**, à la pente −0,5 en échelles logarithmiques.

## Pertes et rendement (onglet 3)

- **A19 — Pertes fer de Steinmetz** avec β = {{ex:beta}}, appliquées par R_μ(f).
- **A20 — Pertes mécaniques a·Ω + b·Ω²**, part des frottements {{ex:part_frottements}}.
- **A21 — Pertes de l'onduleur démo** : P_0 = {{ex:inv_p0}} W et k = {{ex:inv_k}} %.

## Véhicule et cycle (onglet 4)

- **A22 — Véhicule démo** : quadricycle léger de {{ex:veh_m}} kg, C_x·S = {{ex:veh_cxs}} m²,
  C_rr = {{ex:veh_crr}}, rayon de roue {{ex:veh_r}} m, rendement de transmission {{ex:veh_eta}}.
- **A23 — Puissance nominale** = puissance maximale à l'arbre sur l'enveloppe ; rapport proposé
  sous G_max, avec la plus grande marge de couple sur le cycle.
- **A24 — Pertes lues sur la carte** par interpolation ; pertes en freinage prises égales aux
  pertes en traction au même |Γ| et à la même vitesse ; couple de récupération limité par
  l'enveloppe.
- **A25 — Cycle démo synthétique**, qui n'est pas un cycle WLTC, en attendant les fichiers
  officiels.
- **A30 — Temps de 0 à 50 km/h** sans l'inertie des pièces tournantes.

## Thermique (onglet 5)

- **A26 — Réseau thermique démo** : C_b = {{ex:th_cw:4}} J/K, C_c = {{ex:th_cs:4}} J/K,
  R_bc = {{ex:th_rws}} K/W, R_ca = {{ex:th_rsa}} K/W, air à {{ex:th_ta}} °C.
- **A27 — Répartition des pertes** : cuivre du stator au bobinage (recalculées avec sa
  température), fer et Joule du rotor à la carcasse ; pertes mécaniques et onduleur hors du
  réseau ; R_r' non corrigée en température.
- **A28 — Durée de vie de l'isolant** par la règle des 10 K, L_ref = {{ex:vie_classe:i}} h à la
  température de classe ; ordre de grandeur seulement.

## Bobinage et éléments finis (onglet 6)

- **A29 — Conducteurs au centre de l'encoche**, bobinage triphasé, courants équilibrés ;
  harmoniques pairs nuls.
- **A32 — Modèle par éléments finis** : géométrie démo, rotor lisse sans barres (état
  magnétisant, à vide) ; un courant élevé est une surexcitation, pas un point en charge.

## Optimisation (onglet 7)

- **A31 — Méthode** : pénalité de {{ex:penalite:o}} pour les réglages non admissibles, front par
  ε-contrainte, carte de rendement plus grossière ; limite du bobinage = température de classe
  − 20 K ; rebobinage à section de cuivre constante (impédances × k_N²).

## Limites générales

- Les fichiers démo et le cycle démo sont synthétiques : les résultats illustrent la méthode,
  pas un moteur réel.
- Les fichiers WLTC officiels et des mesures réelles de laboratoire ne sont pas encore dans
  l'application.

[→ Ouvrir l'onglet 1](evlab://onglet/identification)
