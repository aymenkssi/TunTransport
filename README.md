# TunTransport

Application Android collaborative : les passagers partagent en temps réel la
position du bus, tramway ou métro qu'ils empruntent, pour que les autres
sachent où il se trouve. Un « Waze des transports publics ».

- [`docs/CONCEPTION.md`](docs/CONCEPTION.md) — fonctionnement, algorithmes,
  architecture, confidentialité et feuille de route.
- [`prototype/`](prototype/) — prototype Python (bibliothèque standard) du cœur
  algorithmique : validation ligne/sens, regroupement des passagers en
  véhicules, fiabilité, temps d'arrivée.

```sh
cd prototype && python3 -m unittest discover -s tests -v
```
