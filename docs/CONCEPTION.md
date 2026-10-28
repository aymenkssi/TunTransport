# TunTransport — Document de conception

> Un « Waze des transports publics » : les passagers partagent la position du
> véhicule dans lequel ils se trouvent, les autres voient où il est en temps réel.

## 1. Principe

| Étape | Côté passager « émetteur » | Côté serveur | Côté utilisateur « observateur » |
|---|---|---|---|
| 1 | Choisit ligne + sens (ou accepte une suggestion) et active le partage | — | — |
| 2 | Envoie un point GPS toutes les 5 à 10 s | Vérifie que la trace colle à la ligne (§3.1) | — |
| 3 | — | Regroupe les passagers en véhicules (§3.2), calcule la fiabilité (§3.3) | Voit le véhicule sur la carte, son sens, l'âge de la position |
| 4 | Fin du trajet (manuelle ou détectée) → arrêt immédiat | Supprime les positions | Le véhicule disparaît après 5 min sans données |

## 2. Le problème central : le GPS localise le téléphone, pas le véhicule

Il faut répondre à trois questions, dans cet ordre :

1. **Le passager est-il vraiment dans un véhicule de la ligne déclarée ?**
   (et pas à pied, en voiture, ou sur une ligne parallèle)
2. **Dans quel sens ?**
3. **Dans quel véhicule ?** (deux bus de la même ligne peuvent se suivre à 200 m)

La réponse repose sur une donnée indispensable : **le tracé de chaque ligne**
(polyligne ordonnée par sens) et la position de ses arrêts. Toute la logique
travaille ensuite en **une dimension** : l'abscisse curviligne le long du tracé
(« le bus est à 3 420 m du terminus »). C'est ce qui rend le regroupement et
les ETA simples et robustes.

### Où trouver les tracés (contexte tunisien)
- **OpenStreetMap** : relations `route=bus`, `route=tram` (métro léger de Tunis),
  `route=train` (TGM, banlieue Sud) — couverture partielle, à vérifier ligne par ligne.
- **GTFS** de l'opérateur s'il est publié (Transtu, SNCFT, sociétés régionales).
- **Crowdsourcing** : à défaut, enregistrer les traces des premiers trajets
  partagés sur une ligne et en déduire le tracé (validation manuelle au début).
- Les **louages** n'ont pas de tracé fixe ni d'horaires : à traiter plus tard,
  comme des trajets origine → destination plutôt que des lignes.

## 3. Algorithmes (prototypés dans `prototype/`)

### 3.1 Validation ligne / sens — `line_matching.py`
Sur les dernières ~60 s de points :
- on écarte les points dont la précision GPS est > 50 m ;
- on projette chaque point sur le tracé → (abscisse, écart latéral) ;
- **≥ 80 % des points à moins de 40 m du tracé** (ou de la précision annoncée) ;
- **l'abscisse ne recule pas** de plus de 30 m → sinon, mauvais sens ;
- vitesse ≤ 120 km/h → sinon, données aberrantes.

`suggest_lines()` utilise le même test sur toutes les lignes proches pour
**proposer automatiquement** la ligne : le passager n'a plus qu'à confirmer
(moins de friction, moins d'erreurs de saisie).

Limites connues, à traiter ensuite : lignes qui partagent un tronçon (la
suggestion reste ambiguë tant que les tracés ne divergent pas — on garde
alors le choix du passager), piéton qui marche le long de la ligne (vitesse
faible soutenue + arrêts hors des arrêts officiels).

### 3.2 Regroupement en véhicules — `vehicles.py`
Pour chaque (ligne, sens) :
- chaque passager actif fournit sa dernière abscisse et sa vitesse ;
- toutes les positions sont ramenées au même instant (extrapolation bornée à 60 s) ;
- on trie le long du tracé et on **coupe** là où deux passagers consécutifs sont
  à plus de **120 m** l'un de l'autre **ou** ont des vitesses qui diffèrent de
  plus de **4 m/s** (un bus à l'arrêt, un autre qui le double) ;
- chaque groupe = un véhicule (position médiane, vitesse médiane, dispersion).

Évolution prévue : garder un identifiant stable de véhicule d'une mise à jour à
l'autre (appariement au véhicule précédent le plus proche), nécessaire pour les
notifications « votre bus approche ».

### 3.3 Fiabilité — `reliability()`
`score = fraîcheur × confirmation × accord`
- fraîcheur : 1 jusqu'à 30 s, puis décroît jusqu'à 0 à 2 min ;
- confirmation : 1 passager → 0,5 ; 2 → 0,75 ; 3 → 0,875 ;
- accord : 1 si les passagers sont au même endroit, 0,5 s'ils sont dispersés.

Statuts affichés : **fiable** (≥ 0,6), **probable**, **obsolète** (> 2 min),
**expiré** (> 5 min, plus affiché).

À ajouter : réputation par utilisateur (part de ses trajets confirmés par
d'autres), pour pondérer les contributions et limiter les faux signalements.

### 3.4 Temps estimé — `eta_seconds()`
`ETA = (abscisse de l'arrêt − abscisse extrapolée du véhicule) / vitesse`,
vitesse bornée entre 2 et 20 m/s (un bus à l'arrêt n'a pas un ETA infini ;
vitesse par défaut ≈ 18 km/h). Étape suivante : apprendre la vitesse
moyenne **par tronçon et par heure** à partir des trajets passés.

## 4. Architecture proposée

```
App Android (Kotlin, Jetpack Compose)
 ├─ Carte : MapLibre + tuiles OpenStreetMap (évite le coût Google Maps)
 ├─ Partage : Foreground Service + FusedLocationProvider (5–10 s)
 └─ Temps réel : WebSocket (abonnement aux lignes visibles à l'écran)
        │
Backend (Kotlin/Ktor ou Python/FastAPI)
 ├─ Ingestion des positions → validation (§3.1)
 ├─ Boucle toutes les 2–5 s : regroupement + fiabilité (§3.2, §3.3)
 ├─ Diffusion des véhicules par ligne (WebSocket / Redis Pub/Sub)
 ├─ Redis : état « chaud » avec TTL (positions éphémères)
 └─ PostgreSQL + PostGIS : lignes, tracés, arrêts, statistiques anonymisées
```

Côté Android, points d'attention :
- **Foreground Service** avec notification permanente « Vous partagez la
  position du bus 32 — Arrêter » (obligatoire sur Android 10+, et rassurant) ;
- permission `ACCESS_FINE_LOCATION` uniquement « pendant l'utilisation » :
  le partage est toujours lancé explicitement, pas besoin de la localisation
  en arrière-plan permanente ;
- **arrêt automatique** : trace qui quitte le tracé pendant > 2 min, vitesse de
  marche prolongée, ou durée maximale (ex. 2 h) ;
- batterie : intervalle adaptatif (plus long quand le véhicule est à l'arrêt).

## 5. Confidentialité (intégrée dès la conception)
- Partage **volontaire**, démarré et arrêté en un geste.
- Les observateurs voient **un véhicule**, jamais un utilisateur : pas de
  pseudonyme, pas de nombre exact de passagers (« confirmé par plusieurs »).
- Positions brutes conservées **en mémoire avec TTL** (quelques minutes), puis
  supprimées ; on ne garde durablement que des agrégats anonymes (vitesses par
  tronçon).
- On n'envoie que les points **sur le tracé** ; le début et la fin du trajet
  (domicile, travail) ne sont jamais diffusés : la diffusion démarre après
  validation (§3.1) et s'arrête dès que le passager quitte la ligne.
- Identifiant de session aléatoire par trajet, non lié au compte côté diffusion.
- Conformité : loi organique tunisienne n° 2004-63 (INPDP) et RGPD si
  ouverture à l'Europe.

## 6. Le vrai défi produit : le démarrage à froid
Une carte vide n'attire personne. Pistes :
- lancer sur **quelques lignes très fréquentées** (ex. métro léger de Tunis,
  TGM, 2–3 lignes de bus) plutôt que tout le réseau ;
- afficher les **horaires théoriques** quand aucun passager ne partage ;
- récompenser les contributeurs (badges, classement, « vous avez aidé 37 personnes ») ;
- partenariats avec des universités / associations de quartier pour les premiers utilisateurs ;
- à terme, intérêt pour l'opérateur (données de fréquentation et de retards).

## 7. Feuille de route
1. **MVP (6–8 semaines)** : 3–5 lignes, choix manuel de ligne, partage GPS,
   carte en direct, statut de fiabilité, arrêt automatique.
2. **V1** : suggestion automatique de ligne, ETA aux arrêts, notifications
   « mon bus approche », identifiants stables de véhicules.
3. **V2** : ETA appris sur l'historique, réputation des contributeurs,
   signalements (bondé, panne, déviation), louages.
