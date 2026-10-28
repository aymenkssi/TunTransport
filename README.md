# TunTransport

Application Android collaborative : les passagers partagent en temps réel la
position du bus, tramway ou métro qu'ils empruntent, pour que les autres
sachent où il se trouve. Un « Waze des transports publics ».

| Dossier | Contenu |
|---|---|
| [`docs/CONCEPTION.md`](docs/CONCEPTION.md) | Fonctionnement, algorithmes, architecture, confidentialité, feuille de route |
| [`android/`](android/) | Application Android (Kotlin, Jetpack Compose, MapLibre) |
| [`tools/`](tools/) | Import des lignes depuis [tunismapper.com](https://www.tunismapper.com/lignes.php) |
| [`prototype/`](prototype/) | Prototype Python du cœur algorithmique (référence des tests) |

## Démarrer

```sh
# 1. Générer le réseau embarqué (≈ 4 min la première fois, pages mises en cache ensuite)
python3 tools/import_tunismapper.py
#    → android/app/src/main/assets/network.json

# 2. Compiler et tester l'application (SDK Android requis, voir local.properties)
cd android && ./gradlew testDebugUnitTest assembleDebug
#    → android/app/build/outputs/apk/debug/app-debug.apk

# Tests de l'importeur et du prototype
(cd tools && python3 -m unittest -v)
(cd prototype && python3 -m unittest discover -s tests -v)
```

## Ce que fait l'application aujourd'hui

- Liste des 228 lignes (7 métro, 3 RFR, 29 train, 189 bus), recherche et filtre par mode.
- Carte (fond OpenStreetMap) avec le tracé et les arrêts de la ligne choisie, dans chaque sens.
- Prochains passages théoriques à chaque arrêt.
- Partage de position : service au premier plan, validation de la trace sur la
  ligne et le sens déclarés, rien n'est diffusé tant que la trace n'est pas
  validée, arrêt automatique hors de la ligne (2 min) ou après 2 h.

Pas encore de serveur : les positions validées sont seulement journalisées
(`LogTripReporter`). Voir la feuille de route dans `docs/CONCEPTION.md`.

## Données

Les lignes, arrêts, horaires et tracés viennent des pages publiques de
tunismapper.com (lignes métro, RFR, train et bus). Le fichier généré n'est pas
versionné : le site n'indique pas de licence de réutilisation, il faut obtenir
son accord avant de redistribuer ces données dans l'application.

Limites connues des données sources :
- tracés réels seulement pour 18 lignes (trains, RFR A) ; ailleurs, le tracé est
  reconstruit en reliant les arrêts (affiché en pointillés, tolérance GPS élargie
  à 150 m) ;
- certains arrêts sont listés dans le désordre ou mal géolocalisés : l'importeur
  les remet en ordre et écarte du tracé ceux qui imposent un détour aberrant.
