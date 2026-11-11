# 2 · Enveloppe couple–vitesse

## Ce que fait cet onglet

L'onglet calcule, pour chaque vitesse du rotor, le couple maximal que le moteur identifié peut
fournir quand il est alimenté par un variateur. Le variateur suit une loi tension–fréquence
(V/f) jusqu'à la fréquence nominale, puis garde la tension constante (défluxage), sous trois
limites : courant maximal, marge par rapport au décrochage et fréquence maximale. La courbe
obtenue est l'enveloppe couple–vitesse, avec ses trois zones de fonctionnement.

## Lois et explications

### Loi V/f et flux

#### Loi tension–fréquence du variateur

`V(f) = V_0 + (V_n − V_0) · f/f_n` pour `f ≤ f_n`, puis `V(f) = V_n` pour `f > f_n`

| Symbole | Signification | Unité |
|---|---|---|
| f, f_n | fréquence statorique et fréquence nominale | Hz |
| V_n | tension simple nominale | V |
| V_0 | tension à fréquence nulle (« boost ») | V |
| V(f) | tension simple appliquée par le variateur | V |

**Explication.** Sous le réseau, le moteur ne fonctionne qu'à une fréquence. Le variateur
change la fréquence pour changer la vitesse. Pour garder le même flux, il doit changer la
tension dans la même proportion : c'est la loi V/f. Au-delà de f_n, la tension ne peut plus
augmenter : le flux diminue comme 1/f, c'est le défluxage. Le boost V_0 compense la chute de
tension dans R_s aux très basses fréquences.

**Ce que ça montre.** Sous f_n, le couple disponible reste presque constant ; au-dessus, il
décroît, car le flux décroît.

**Dans l'application.** `core/drive.py` : `vf_voltage` ; réglage « Boost basse vitesse » de
l'onglet 2.

**Exemple** — moteur de référence, sans bruit ; variateur démo. V = {{ex:ref_v_f25}} V à
25 Hz, {{ex:ref_v_fn}} V à 50 Hz et {{ex:ref_v_f100}} V à 100 Hz.

**Dans le cours.** Hors cours (le cours étudie l'effet de la tension et de la fréquence à
tension fixe, MAS B §7.2 et §7.3, p. 119). Pour aller plus loin : Wildi, « Électrotechnique ».

#### Réactances proportionnelles à la fréquence

`X_μ(f) = X_μ · f/f_n`,  `l_s'ω(f) = l_s'ω_s · f/f_n` ;  R_s, R_r', R_μ constantes

| Symbole | Signification | Unité |
|---|---|---|
| X_μ, l_s'ω_s | réactances identifiées à f_n | Ω |
| X_μ(f), l_s'ω(f) | mêmes réactances à la fréquence f | Ω |

**Explication.** Une réactance est le produit d'une inductance par la pulsation : X = L·ω. Les
inductances dépendent de la géométrie et du nombre de spires, pas de la fréquence. Quand le
variateur change f, toutes les réactances changent donc dans le même rapport, tandis que les
résistances restent les mêmes.

**Ce que ça montre.** À basse fréquence, les réactances deviennent petites devant R_s : la
chute de tension dans R_s pèse plus, d'où le boost.

**Dans l'application.** `core/circuit.py` : `impedance` (fréquence f en paramètre) ; tous les
calculs des onglets 2 et 3.

**Exemple** — moteur de référence, sans bruit. l_s'ω vaut {{ex:ref_x_f100}} Ω à 100 Hz.

**Dans le cours.** Cours Pr Boughrara, MAS B §7.3, p. 119 (diagramme agrandi quand la fréquence
diminue, car les réactances diminuent).

#### Flux d'entrefer et rapport E/f

`E = 4,44 · N · f · Φ` ;  `flux relatif = (E/f) / (E_n/f_n)`

| Symbole | Signification | Unité |
|---|---|---|
| E | f.é.m. aux bornes de la branche magnétisante | V |
| N, Φ | spires d'une phase et flux par pôle | —, Wb |
| E_n | f.é.m. au point à vide nominal (g = 0, V_n, f_n) | V |

**Explication.** La f.é.m. induite dans une phase est proportionnelle à la fréquence et au flux.
Le rapport E/f mesure donc le flux dans l'entrefer. L'application le compare à sa valeur au point
nominal : un rapport proche de 1 signifie que le moteur travaille à son flux nominal, un rapport
plus grand qu'il serait saturé (ce que le modèle linéaire ne représente pas, hypothèse A33).

**Ce que ça montre.** En défluxage, le flux relatif tombe sous 1 ; un boost trop fort le fait
dépasser 1 à basse vitesse.

**Dans l'application.** `core/drive.py` : `rated_emf`, `flux_ratio` ; avertissement de boost de
l'onglet 2 et quatrième contrainte de l'onglet 7.

**Exemple** — moteur de référence, sans bruit ; variateur démo. E_n = {{ex:ref_en}} V ; à 100 Hz
et à vide, le flux relatif vaut {{ex:ref_flux_f100}} ; le maximum le long de l'enveloppe est
{{ex:ref_flux_max}}.

**Dans le cours.** Cours Pr Boughrara, MAS A §4, p. 86 (E₁ = 4,44·N₁·f₁·Φ).

### Fréquence, glissement et vitesse

#### Fréquence statorique choisie par le variateur

`f = p·Ω/(2π) + f_r`,  `g = f_r / f`

| Symbole | Signification | Unité |
|---|---|---|
| Ω | vitesse du rotor | rad/s |
| f_r | fréquence des courants rotoriques | Hz |
| g | glissement à la fréquence f | — |

**Explication.** À vitesse donnée, le variateur choisit la fréquence statorique un peu au-dessus
de la fréquence « synchrone » p·Ω/(2π) : la différence f_r est la fréquence vue par le rotor,
et le glissement vaut f_r/f. Augmenter f_r augmente le courant et le couple, jusqu'à la limite
la plus proche.

**Ce que ça montre.** Le moteur alimenté par variateur fonctionne toujours à faible f_r : il ne
passe jamais par les forts glissements du démarrage direct.

**Dans l'application.** `core/drive.py` : `envelope` ; colonnes fréquence et glissement de
l'enveloppe.

**Exemple** — moteur de référence, sans bruit ; variateur démo. À {{ex:ref_w_i_ex:4}} tr/min,
f = {{ex:ref_f_i_ex}} Hz, f_r = {{ex:ref_fr_i_ex}} Hz et g = {{ex:ref_g_i_ex}}.

**Dans le cours.** Cours Pr Boughrara, MAS A §4.1, p. 87 (f₂ = g·f₁).

### Limites du variateur

#### Couple de décrochage le long de la loi V/f

`Γ_bd(f) = Γ_max(V(f), f)` ;  couple autorisé : `marge · Γ_bd(f)`

| Symbole | Signification | Unité |
|---|---|---|
| Γ_bd(f) | couple de décrochage à la tension V(f) et à la fréquence f | N·m |
| marge | fraction utilisable du couple de décrochage | — |

**Explication.** La formule du couple maximal (onglet 1) s'applique à chaque fréquence avec la
tension de la loi V/f et des réactances ramenées à f. Sous f_n, V/f est constant et Γ_bd reste
presque constant ; au-dessus, la tension est fixe et Γ_bd décroît comme 1/f². Le variateur garde
une marge pour ne jamais approcher le décrochage.

**Ce que ça montre.** À haute vitesse, c'est le décrochage qui finit par limiter le couple.

**Dans l'application.** `core/drive.py` : `breakdown_torque`, `envelope` ; courbe « marge ·
décrochage » de l'onglet 2.

**Exemple** — moteur de référence, sans bruit ; variateur démo. Γ_bd = {{ex:ref_tbd_fn:4}} N·m à
50 Hz et {{ex:ref_tbd_f100}} N·m à 100 Hz ; marge = {{ex:marge}}.

**Dans le cours.** Cours Pr Boughrara, MAS A §7, p. 98 (couple maximal) ; la loi V/f est hors
cours.

#### Courant maximal et fréquence maximale

`I_s ≤ i_max`,  `f ≤ f_max`

| Symbole | Signification | Unité |
|---|---|---|
| i_max | courant maximal du variateur (valeur efficace par phase) | A |
| f_max | fréquence maximale du variateur | Hz |

**Explication.** Les composants du variateur supportent un courant limité : à basse vitesse,
c'est cette limite qui fixe le couple. La fréquence maximale fixe la vitesse maximale de
l'enveloppe, qui s'arrête quand f atteint f_max.

**Ce que ça montre.** Un i_max plus grand relève le couple à basse vitesse sans changer le
couple de décrochage.

**Dans l'application.** `core/drive.py` : `DriveSettings`, `envelope` ; réglages « Courant
max » et « Fréquence max » de l'onglet 2.

**Exemple** — variateur démo. i_max = {{ex:i_max}} A et f_max = {{ex:f_max}} Hz ; l'enveloppe du
moteur de référence s'arrête à {{ex:ref_wmax:4}} tr/min.

**Dans le cours.** Hors cours. Pour aller plus loin : Boldea, « Induction Machines Handbook ».

### Enveloppe et zones

#### Couple disponible et puissance

`Γ_dispo(Ω) = min(Γ_I, marge·Γ_bd, Γ_pic)`,  `P = Γ_dispo · Ω`

| Symbole | Signification | Unité |
|---|---|---|
| Γ_I | couple atteint quand le courant vaut i_max | N·m |
| Γ_pic | plus grand couple possible à cette vitesse | N·m |
| P | puissance électromagnétique disponible | W |

**Explication.** À chaque vitesse, le variateur augmente f_r tant qu'aucune limite n'est
atteinte ; le couple disponible est celui de la première limite rencontrée. La puissance est le
produit du couple par la vitesse.

**Ce que ça montre.** La puissance maximale est atteinte vers la vitesse de base, où se
rejoignent la zone à couple constant et la zone à puissance constante.

**Dans l'application.** `core/drive.py` : `envelope` ; courbes couple et puissance de
l'onglet 2, tuile « P max ».

**Exemple** — moteur de référence, sans bruit ; variateur démo. P_max = {{ex:ref_pmax}} W ; à
{{ex:ref_w_i_ex:4}} tr/min, le couple disponible vaut {{ex:ref_t_i_ex}} N·m.

**Dans le cours.** Hors cours (P = Γ·Ω : MAS C §5.5, p. 127).

#### Zones de fonctionnement

`n = d ln Γ / d ln Ω` : `n ≈ 0` (couple constant), `n ≈ −1` (puissance constante), plus raide
au-delà ; vitesse de base : dernier point où `n > −0,5`

| Symbole | Signification | Unité |
|---|---|---|
| n | pente de la courbe en échelles logarithmiques | — |

**Explication.** En échelles logarithmiques, une loi Γ = constante a une pente nulle et une loi
Γ·Ω = constante une pente de −1. L'application lit les limites de zones sur la courbe calculée,
au lieu de les imposer : la vitesse de base est le dernier point avant que la pente passe sous
−0,5, à mi-chemin entre les deux lois.

**Ce que ça montre.** Avec un rotor très résistif, la zone à puissance constante est courte ;
avec un i_max élevé, elle peut disparaître.

**Dans l'application.** `core/drive.py` : `envelope` (vitesse de base, fin de puissance
constante) ; tuiles et zones colorées de l'onglet 2.

**Exemple** — moteur de référence, sans bruit ; variateur démo. Vitesse de base
{{ex:ref_base:4}} tr/min ; fin de la puissance constante {{ex:ref_fin_pc:4}} tr/min.

**Dans le cours.** Hors cours. Pour aller plus loin : Boldea, « Induction Machines Handbook ».

## Hypothèses

- Réglages du variateur démo : i_max, boost, marge et f_max sont des valeurs démo (A16).
- Couple électromagnétique : les pertes mécaniques sont retirées dans l'onglet 3 (A17).
- Réactances ∝ f, résistances constantes (A2) ; R_μ constante dans l'enveloppe, sa variation
  avec f n'est prise en compte que dans la carte de rendement (A19).
- Circuit magnétique linéaire : X_μ ne dépend pas du flux ; la saturation n'est pas modélisée, le
  flux relatif E/f sert seulement d'alerte et de contrainte (A33).
- Limites de zones lues sur la courbe à mi-pente (A18).

## Avec votre moteur

Moteur utilisé par la chaîne : {{moteur:source}}.

| Grandeur | Valeur |
|---|---|
| V_n et f_n | {{moteur:v_n}} V et {{moteur:f_n}} Hz |
| Vitesse de synchronisme | {{moteur:n_s:4}} tr/min |
| E_n (f.é.m. nominale) | {{moteur:e_n}} V |
| Γ_bd à f_n et à 100 Hz | {{moteur:tbd_fn:4}} N·m et {{moteur:tbd_f100}} N·m |

## Questions pour s'entraîner

**Q1.** Pourquoi le variateur augmente-t-il la tension avec la fréquence sous f_n ?

??? Voir la réponse
Pour garder un flux constant : E = 4,44·N·f·Φ, donc à flux constant E (≈ V) doit croître comme f.
???

**Q2.** Que devient le couple de décrochage au-dessus de f_n, et pourquoi ?

??? Voir la réponse
Il décroît comme 1/f² environ : la tension reste V_n alors que les réactances croissent comme f,
et le couple maximal varie comme V²/(l_s'ω·ω).
???

**Q3.** Quelle limite fixe le couple à basse vitesse avec les réglages démo ?

??? Voir la réponse
Le courant maximal du variateur i_max : le couple de décrochage y est plus grand que le couple
que permet ce courant.
???

[→ Ouvrir l'onglet 2](evlab://onglet/enveloppe)
