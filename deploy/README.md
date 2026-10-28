# Déployer le backend TunTransport sur un VPS

> **Installation sur le VPS de Neon Strike : suivez [INSTALLATION.md](INSTALLATION.md)**, le guide pas à pas complet. Ce fichier-ci décrit le dossier `deploy/` en général.

Ce dossier lance trois conteneurs avec Docker Compose :

| Service | Rôle | Exposé sur Internet |
|---|---|---|
| `caddy` | HTTPS automatique (Let's Encrypt) : sert l'API sur `api.tuntransport.academy` et le site sur `tuntransport.academy` | oui (ports 80 et 443) |
| `api` | API FastAPI : lignes, trajets partagés, véhicules en direct, administration | non (seulement via Caddy) |
| `mongo` | Base MongoDB 7 avec mot de passe, données dans un volume | non |

> **Votre VPS a déjà Traefik devant d'autres applications (comme pour Neon Strike) ?** Utilisez la variante `docker-compose.traefik.yml` : elle n'installe pas Caddy, n'ouvre aucun port et laisse Traefik router et certifier les domaines. Voir « Serveur avec Traefik » plus bas ; les autres étapes restent identiques.

**Prérequis** : un VPS Linux (Ubuntu 22.04/24.04 ou Debian 12, 1 vCPU et 1 Go de RAM suffisent), un nom de domaine, l'accès root en SSH, et `python3` (pour importer les lignes).

## 1. Nom de domaine `tuntransport.academy`

Dans la zone DNS du domaine, créez ces enregistrements en remplaçant `IP_DU_VPS` par l'adresse IPv4 du VPS :

| Type | Nom | Valeur |
|---|---|---|
| A | `@` (le domaine nu) | `IP_DU_VPS` |
| A | `www` | `IP_DU_VPS` |
| A | `api` | `IP_DU_VPS` |

Au 28 octobre 2026, `tuntransport.academy` ne résout pas encore (domaine pas encore enregistré, ou enregistrement en cours de propagation) : achetez-le ou vérifiez son statut chez le registrar, puis créez les 3 enregistrements.

Vérifiez que `ping api.tuntransport.academy` répond avec l'IP du VPS avant de continuer : Caddy en a besoin pour obtenir les certificats HTTPS.

## 2. Préparer le VPS

```bash
curl -fsSL https://get.docker.com | sh
apt install -y ufw python3
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable

git clone https://github.com/aymenkssi/TunTransport.git /opt/apps/tuntransport
cd /opt/apps/tuntransport/deploy
```

## 3. Configurer

```bash
cp .env.example .env
nano .env
```

- `DOMAIN=api.tuntransport.academy` et `SITE_DOMAIN=tuntransport.academy` (déjà remplis).
- `MONGO_PASSWORD` : un mot de passe long (`openssl rand -hex 24`).
- `ADMIN_TOKEN` : le jeton de la page d'administration (`openssl rand -hex 32`).

## 4. Importer les lignes

Les lignes, arrêts, tracés et horaires viennent de tunismapper.com. Ils ne sont pas dans le dépôt (voir « Données » dans le README principal) : on les importe sur le serveur.

```bash
./update-network.sh          # ≈ 4 min : crée data/network.json (228 lignes) puis redémarre l'API
```

Pour suivre les changements d'horaires, relancez-le chaque mois :

```bash
crontab -e                   # puis ajouter :
0 5 1 * * cd /opt/apps/tuntransport/deploy && ./update-network.sh >> data/update.log 2>&1
```

## 5. Lancer

```bash
docker compose up -d --build
docker compose ps                     # les 3 services doivent être "running"/"healthy"
curl https://api.tuntransport.academy/api/       # {"message":"TunTransport API online","lines":228}
```

Mise à jour après un `git pull` : `docker compose up -d --build`. Journaux : `docker compose logs -f api`.

## Serveur avec Traefik (variante)

1. Relevez dans la configuration de Traefik le **réseau** Docker partagé (`docker network ls`), l'**entrypoint HTTPS** (ex. `websecure`) et le **certresolver** (ex. `letsencrypt`).
2. Dans `deploy/.env`, décommentez `COMPOSE_FILE=docker-compose.traefik.yml` et renseignez `TRAEFIK_NETWORK`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER`. Sur le VPS de Neon Strike, ce sont `web`, `websecure` et `letsencrypt`.
3. `docker compose up -d --build`. Le projet s'appelle `tuntransport` et ses routeurs `tt-api` et `tt-site` : pas de conflit avec Neon Strike ni vos autres applications.

## 6. Application et site web

- L'application est déjà branchée sur `https://api.tuntransport.academy` pour tous les profils de build (`frontend/eas.json`).
- **Site** (`deploy/site/`) : page d'accueil et politique de confidentialité sur `https://tuntransport.academy/privacy`. **Avant la mise en ligne**, remplacez `[NOM DU RESPONSABLE]` et `[ADRESSE E-MAIL DE CONTACT]` dans `privacy.html` et `index.html`.
- **Play Console** → Fiche du Store : site `https://tuntransport.academy`, règles de confidentialité `https://tuntransport.academy/privacy`. Sécurité des données → Suppression : l'utilisateur supprime ses données depuis l'app (À propos → Supprimer mes données).
- **Play Console → Déclaration de service au premier plan** : l'app utilise un service de type `location` pendant un trajet que l'utilisateur lance lui-même ; elle ne demande pas la localisation en arrière-plan permanente (`ACCESS_BACKGROUND_LOCATION`).

## 7. Administration

Page : **https://api.tuntransport.academy/admin**, avec le `ADMIN_TOKEN` de `deploy/.env`. Le jeton reste dans l'onglet jusqu'à sa fermeture.

- **En direct** : véhicules signalés sur tout le réseau (ligne, sens, position, vitesse, nombre de passagers, âge, fiabilité), actualisés toutes les 10 s.
- **Statistiques** : utilisateurs, trajets en cours, du jour et des 7 derniers jours, trajets validés, contributeurs, trajets par jour sur 14 jours, lignes les plus partagées.
- **Réseau** : date d'import, lignes par mode, nombre de tracés reconstruits ; bouton pour recharger `data/network.json` après un import, sans redémarrer.

## 8. Sauvegardes

```bash
./backup.sh     # crée backups/tuntransport-AAAA-MM-JJ_HHMM.gz
crontab -e      # puis ajouter :
0 4 * * * cd /opt/apps/tuntransport/deploy && ./backup.sh >> backups/backup.log 2>&1
```

Les 14 dernières sauvegardes sont conservées. Restauration :

```bash
docker compose exec -T mongo mongorestore --gzip --archive=/backups/tuntransport-XXXX.gz \
  --username "$MONGO_USER" --password "$MONGO_PASSWORD" --authenticationDatabase admin --drop
```

## Ce que fait l'API

| Route | Rôle |
|---|---|
| `POST /api/users` | Crée un utilisateur anonyme et renvoie une clé secrète. Le serveur n'en garde qu'une empreinte (SHA-256). |
| `POST /api/users/me/delete` | Supprime l'utilisateur, ses trajets et sa position en cours. |
| `GET /api/lines` · `GET /api/lines/{id}` | Liste des lignes ; ligne complète (arrêts, tracé et arrêts de chaque sens, horaires). |
| `POST /api/lines/suggest` | Lignes et sens compatibles avec une trace GPS. |
| `POST /api/trips` | Le passager déclare sa ligne et son sens. Un seul trajet actif par utilisateur, 40 par jour au plus. |
| `POST /api/trips/{id}/positions` | Dernières positions GPS (≈ 60 s). Le serveur vérifie la trace (≥ 80 % des points près du tracé, bon sens, vitesse plausible) et ne publie que la position le long de la ligne. Coordonnées brutes jamais enregistrées. |
| `POST /api/trips/{id}/end` | Fin du trajet : la position disparaît immédiatement. Fin automatique après 2 h. |
| `GET /api/lines/{id}/vehicles?stop_id=` | Véhicules de la ligne : passagers regroupés par véhicule, position, nombre de passagers, âge, fiabilité (fiable / probable / obsolète), temps d'arrivée à l'arrêt demandé. |
| `GET /api/vehicles/live` | Tous les véhicules en direct du réseau, avec la ligne, sa couleur et son numéro (carte d'accueil de l'app). |
| `GET /api/live` | Nombre de véhicules en direct par ligne. |
| `/api/admin/…` et `/admin` | Administration (jeton `ADMIN_TOKEN` obligatoire). |
