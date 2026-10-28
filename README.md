# TunTransport

Application Android collaborative : les passagers partagent en temps réel la position du bus, métro ou
train qu'ils empruntent, pour que les autres sachent où il se trouve. Un « Waze des transports publics »
pour la Tunisie. Application Expo / React Native, backend FastAPI + MongoDB (même organisation que Neon Strike).

```
frontend/   Application mobile Expo SDK 54 (React Native 0.81, expo-router, TypeScript)
backend/    API FastAPI : lignes, trajets partagés, véhicules en direct, page /admin
deploy/     Docker Compose (API + MongoDB + Caddy ou Traefik), site web, sauvegardes — voir deploy/README.md
tools/      Import des lignes (métro, RFR, train, bus) depuis tunismapper.com
docs/       Conception : algorithmes, confidentialité, feuille de route
memory/     PRD et notes produit
```

## Prérequis

| Outil | Version |
|---|---|
| Node.js | 20 LTS ou 22 |
| Yarn | 1.22 (`corepack enable`) |
| Python | 3.11 |
| MongoDB | 6+ (local, Docker ou Atlas) |
| JDK | 17 (pour compiler Android en local) |
| Android Studio | SDK Android 35/36 + un émulateur, ou un téléphone en mode développeur |

## 1. Lignes de transport

```bash
python3 tools/import_tunismapper.py      # ≈ 4 min la première fois → backend/data/network.json (228 lignes)
```

## 2. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # renseigner MONGO_URL / DB_NAME / ADMIN_TOKEN
# MongoDB via Docker si besoin : docker run -d -p 27017:27017 --name mongo mongo:7
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Vérification : <http://localhost:8001/api/> renvoie `{"message": "TunTransport API online", "lines": 228}`.
Administration : <http://localhost:8001/admin> avec le `ADMIN_TOKEN` de `backend/.env`.

Tests (en mémoire, sans MongoDB) :

```bash
pip install -r requirements-dev.txt
pytest
```

## 3. Application mobile

```bash
cd frontend
yarn install
cp .env.example .env            # EXPO_PUBLIC_BACKEND_URL doit être joignable depuis le téléphone
```

Le partage de trajet utilise des modules natifs (service de localisation au premier plan), il faut donc un
*development build* plutôt qu'Expo Go :

```bash
yarn android                    # = expo run:android : génère android/, compile et installe sur l'émulateur/téléphone
yarn start:dev-client           # ensuite, pour les modifications JS/TS (rechargement à chaud)
```

Ou avec EAS (dans le cloud) : `yarn build:android:dev` (APK de développement), `yarn build:android:preview`
(APK à partager), `yarn build:android:prod` (AAB pour Google Play). Remplacez d'abord `https://api.example.com`
dans `eas.json` par l'adresse de votre API.

Version web, pratique pour tester l'interface : `yarn web` (le partage marche tant que la page reste ouverte).

Vérifications : `yarn typecheck` et `yarn lint`.

## Ce que fait l'application

- **Lignes** : 228 lignes (7 métro, 3 RFR, 29 train, 189 bus), recherche, filtre par mode, nombre de
  véhicules en direct par ligne.
- **Ligne** : carte (tracé, arrêts, véhicules en direct colorés par fiabilité, avec le nombre de passagers),
  choix du sens, horaires théoriques à chaque arrêt, temps d'arrivée des véhicules à l'arrêt touché.
- **Partage** : « Je suis dans ce véhicule » démarre un service de localisation au premier plan ; le serveur
  vérifie la trace (ligne et sens) avant de publier quoi que ce soit, regroupe les passagers d'un même véhicule
  et le marque « fiable » quand plusieurs le confirment. Arrêt d'un geste, automatique hors de la ligne
  (2 min) ou après 2 h.
- **Confidentialité** : aucun compte ; coordonnées GPS jamais enregistrées, seule la position du véhicule le
  long de la ligne est gardée 5 minutes ; « Supprimer mes données » dans l'écran À propos.

## Données

Lignes, arrêts, horaires et tracés : pages publiques de [tunismapper.com](https://www.tunismapper.com/lignes.php)
(l'API `/backend/` du site, exclue par son robots.txt, n'est pas utilisée). Le fichier généré n'est pas
versionné : le site n'indique pas de licence de réutilisation, il faut obtenir son accord avant de servir ces
données publiquement.

Limites des données sources :
- tracés réels pour 18 lignes seulement (trains, RFR A) ; ailleurs, le tracé relie les arrêts (affiché en
  pointillés, tolérance GPS élargie à 150 m) ;
- certains arrêts sont listés dans le désordre ou mal géolocalisés : l'importeur les remet en ordre et écarte
  du tracé ceux qui imposent un détour aberrant.
