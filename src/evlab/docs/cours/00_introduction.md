# Introduction : un moteur, une chaîne

EV-Traction Lab est un laboratoire virtuel de chaîne de traction de véhicule électrique à moteur
asynchrone. Ce cours énonce et explique chaque loi que l'application utilise, onglet par onglet,
dans la notation du cours de machines électriques du Pr Boughrara (ENP Alger).

## La chaîne

Un seul moteur traverse toute l'application :

1. **[Identification](evlab://page/identification)** — les essais en continu, à vide, à rotor
   bloqué et en charge donnent le schéma équivalent du moteur (R_s, R_μ, X_μ, l_s'ω_s, R_r').
2. **[Enveloppe](evlab://page/enveloppe)** — ce schéma, alimenté par un variateur (loi V/f puis
   défluxage), donne le couple maximal à chaque vitesse.
3. **[Rendement](evlab://page/rendement)** — le même schéma, sous la même loi, donne les pertes
   et le rendement en tout point de l'enveloppe.
4. **[Véhicule & WLTC](evlab://page/vehicule)** — un véhicule adapté au moteur roule un cycle ;
   la carte de rendement donne l'énergie prise à la batterie.
5. **[Thermique](evlab://page/thermique)** — les pertes du cycle chauffent le bobinage ; la
   température donne la durée de vie de l'isolant.
6. **[Bobinage](evlab://page/bobinage)** — le bobinage du stator, sa force magnétomotrice et le
   champ tournant qui est à l'origine de tout le fonctionnement.
7. **[Optimisation](evlab://page/optimisation)** — les réglages du variateur et du véhicule sont
   optimisés sur ces mêmes modèles.

Aucun onglet n'invente un autre moteur : si l'on identifie un nouveau moteur à l'onglet 1, tous
les autres onglets se recalculent avec lui.

## Comment lire une page d'onglet

Chaque page d'onglet a les mêmes parties :

- **Ce que fait cet onglet** — en quelques phrases.
- **Lois et explications** — chaque loi réellement utilisée par le code, regroupée par thème.
  Pour chaque loi : l'équation, le tableau de ses symboles, une explication, ce qu'elle montre,
  le fichier du code qui la calcule, un exemple chiffré et la référence dans le cours.
- **Hypothèses** — ce que le modèle néglige, et pourquoi c'est acceptable ici.
- **Avec votre moteur** — les valeurs du moteur que la chaîne utilise en ce moment.
- **Questions pour s'entraîner** — trois questions ; cliquez sur « Voir la réponse ».
- un lien vers l'onglet.

## Exemples et données

Chaque exemple dit sur quelles données il est calculé :

- **moteur de référence, sans bruit** : R_μ = {{ex:demo_ref_rf}} Ω, X_μ = {{ex:demo_ref_xm}} Ω,
  l_s'ω_s = {{ex:demo_ref_x}} Ω, R_r' = {{ex:demo_ref_r2}} Ω, R_s = 0, sous {{ex:ref_v}} V et
  50 Hz ;
- **fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω)** : essais synthétiques fabriqués à partir
  du même circuit, avec une résistance R_s et des pertes mécaniques ajoutées et
  {{ex:bruit_pct:2}} % de bruit sur chaque lecture ; le moteur qui en est identifié est celui de
  la démonstration.

Tous les nombres du cours sont calculés par le code de l'application au moment de l'affichage ;
aucun n'est recopié à la main.

## Références au cours

Le cours du Pr Boughrara est cité ainsi : « Cours Pr Boughrara, MAS A §5.2, p. 94 ». « Notions A »
désigne la partie sur les machines à courant alternatif (p. 4–27), « Synchrone B » et
« Synchrone C » les parties sur la machine synchrone (p. 28–81), « MAS A », « MAS B » et « MAS C »
les parties sur la machine asynchrone (p. 82–135). Les pages sont celles du fichier PDF. Les
sujets que le cours ne traite pas sont marqués « hors cours », avec une référence pour aller plus
loin ([Bibliographie](evlab://page/bibliographie)).

Pages générales : [Hypothèses et limites](evlab://page/hypotheses) ·
[Glossaire des symboles](evlab://page/glossaire) · [Notation : cours ↔ application](evlab://page/notation) ·
[Validation](evlab://page/validation).

[→ Ouvrir l'onglet 1](evlab://onglet/identification)
