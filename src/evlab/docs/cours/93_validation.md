# Validation

Les lois de ce cours sont vérifiées par les tests automatiques de l'application (dossier
`tests/`). Les nombres ci-dessous sont recalculés à l'affichage par le même code que les onglets.

## Moteur de référence, sans bruit

Circuit en Γ : R_μ = {{ex:demo_ref_rf}} Ω, X_μ = {{ex:demo_ref_xm}} Ω, l_s'ω_s = {{ex:demo_ref_x}} Ω,
R_r' = {{ex:demo_ref_r2}} Ω, R_s = 0, V_s = {{ex:ref_v}} V, 50 Hz, p = 2.

| Ce qui est vérifié | Valeur attendue | Valeur calculée | Test |
|---|---|---|---|
| Glissement de décrochage, formule g_c = R_r'/(l_s'ω_s) | 0,5 | {{ex:ref_gc_closed:4}} | `tests/test_circuit.py` |
| Même point par recherche numérique de dΓ/dg = 0 | 0,5 | {{ex:ref_gc_num:4}} | `tests/test_circuit.py` |
| Couple maximal 3·p·V_s²/(2·l_s'ω_s·ω_s) | 126,3 N·m | {{ex:ref_tmax:4}} N·m | `tests/test_circuit.py` |
| Même couple par recherche numérique | 126,3 N·m | {{ex:ref_tmax_num:4}} N·m | `tests/test_circuit.py` |
| Vitesse à g = 0,1 | 1350 tr/min | {{ex:ref_n:4}} tr/min | `tests/test_circuit.py` |
| p_fer du schéma = 3·V_s²/R_μ (R_s = 0) | égales | {{ex:ref_pfer:4}} W et {{ex:ref_pfer_formule:4}} W | `tests/test_circuit.py` |

## Identification

| Ce qui est vérifié | Résultat | Test |
|---|---|---|
| Méthode exacte sur les fichiers démo générés sans bruit : R_r' et l_s'ω_s | {{ex:r2_exact_sans_bruit:4}} Ω et {{ex:x_exact_sans_bruit:4}} Ω (fabrication {{ex:demo_ref_r2}} et {{ex:demo_ref_x}} Ω) | `tests/test_identification.py` |
| Biais connu des formules classiques du rotor bloqué (moteur de référence) | R_r' {{ex:ref_e_r2_classique:s3}} %, l_s'ω_s {{ex:ref_e_x_classique:s2}} % | `tests/test_identification.py` |
| Ajustement sur les fichiers démo bruités : intervalle à 95 % de R_r' | [{{ex:r2_ci_bas}} ; {{ex:r2_ci_haut}}] Ω, contient {{ex:demo_ref_r2}} Ω | `tests/test_identification.py` |
| Loi du cuivre : R(75 °C)/R(20 °C) = (234,5 + 75)/254,5 | {{ex:r20_75:5}} | `tests/test_circuit.py` |
| Jeux de données de test (trois moteurs) dans les bornes statistiques | voir `data/tests/README.md` | `tests/test_datasets.py` |

## Bobinage (Z = 36, 2p = 4)

| Ce qui est vérifié | Valeur attendue | Valeur calculée | Test |
|---|---|---|---|
| y = 9 : k_w,1, k_w,5, k_w,7 | 0,9598 ; 0,2176 ; 0,1774 | {{ex:kw1_y9:4}} ; {{ex:kw5_y9:4}} ; {{ex:kw7_y9:4}} | `tests/test_winding.py` |
| y = 7 : k_d,1, k_p,1, k_w,1 | 0,9598 ; 0,9397 ; 0,9019 | {{ex:kd1:4}} ; {{ex:kp1_y7:4}} ; {{ex:kw1_y7:4}} | `tests/test_winding.py` |
| y = 7 : k_w,5, k_w,7 | −0,0378 ; −0,1359 | {{ex:kw5_y7:4}} ; {{ex:kw7_y7:4}} | `tests/test_winding.py` |
| Champ tournant = 3/2 du fondamental d'une phase | 1,5 | {{ex:rapport_tournant:4}} | `tests/test_winding.py` |

Les harmoniques de la FMM calculés par transformée de Fourier suivent k_w,ν/ν, et la f.é.m. de
l'exercice de référence du cours de bobinage est retrouvée (`tests/test_winding.py`).

## Enveloppe, rendement, véhicule, thermique

| Ce qui est vérifié | Résultat | Test |
|---|---|---|
| L'enveloppe donne le meilleur couple à chaque vitesse | comparée à un balayage complet | `tests/test_drive.py` |
| À 50 Hz, la carte redonne le rendement du schéma, quel que soit β | égalité | `tests/test_losses.py` |
| Bilan de puissance au meilleur point de la carte | η = {{ex:demo_eta_max}} % = P_u/P_abs = {{ex:best_eta_bilan}} % | `tests/test_losses.py` |
| Classe WLTC : 22 W/kg → classe {{ex:wltc_22:i}}, 22,1 → {{ex:wltc_22p:i}} ; 34 → {{ex:wltc_34:i}}, 34,1 → {{ex:wltc_34p:i}} | seuils 22 et 34 W/kg | `tests/test_vehicle.py` |
| Bilan d'énergie du cycle : batterie = énergie cinétique + résistances + pertes | fermé à 10⁻⁶ près | `tests/test_vehicle.py` |
| Essai de refroidissement simulé : constante retrouvée | τ = {{ex:tau_essai_min}} min pour {{ex:tau_lent_min}} min | `tests/test_thermal.py` |
| Constantes de temps = inverses des valeurs propres du réseau | égalité | `tests/test_thermal.py` |
| Règle des 10 K | L({{ex:t_moins_10}} °C) = {{ex:vie_moins_10:i}} h = 2 × L({{ex:t_classe_ex}} °C) | `tests/test_thermal.py` |
| Optimisation à une variable = balayage complet | à 1 % près | `tests/test_optimise.py` |

## Ce cours lui-même

Les tests du cours (`tests/test_cours_pages.py`, `tests/test_cours_valeurs.py`) vérifient que
chaque page s'affiche sans valeur manquante, que chaque fonction citée dans « Dans
l'application » existe dans `core/`, que chaque nombre d'un exemple est égal au résultat du code,
et que chaque lien mène quelque part.

[→ Ouvrir l'onglet 1](evlab://onglet/identification)
