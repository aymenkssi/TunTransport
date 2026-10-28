# Mettre TunTransport en ligne sur le VPS de Neon Strike

Guide pas à pas, dans l'ordre. Compter environ 1 h, plus l'attente DNS.
TunTransport s'installe **à côté** de Neon Strike, sans le modifier : il a son propre dossier, sa propre base
MongoDB et ses propres routeurs Traefik (`tt-api`, `tt-site`). Neon Strike continue de tourner pendant toute l'installation.

Résultat attendu :

| Adresse | Contenu |
|---|---|
| `https://api.tuntransport.academy/api/` | API de l'application |
| `https://api.tuntransport.academy/admin` | Page d'administration |
| `https://tuntransport.academy` | Site + `/privacy` (politique de confidentialité) |

---

## Étape 1 — Le domaine (chez le registrar)

Au 28 octobre 2026, `tuntransport.academy` n'existe pas encore dans le DNS.

1. Achetez le domaine (ou vérifiez que l'achat est validé) chez votre registrar.
2. Relevez l'IP du VPS de Neon Strike. C'est la même que celle de `api.gameneonstrike.com` :
   ```bash
   ping -c1 api.gameneonstrike.com
   ```
3. Dans la zone DNS de `tuntransport.academy`, créez :

   | Type | Nom | Valeur | TTL |
   |---|---|---|---|
   | A | `@` | IP du VPS | 3600 |
   | A | `www` | IP du VPS | 3600 |
   | A | `api` | IP du VPS | 3600 |

   Supprimez les éventuels enregistrements A ou AAAA par défaut du registrar (page de parking).
4. Attendez que ces trois commandes renvoient l'IP du VPS (de quelques minutes à quelques heures) :
   ```bash
   ping -c1 tuntransport.academy
   ping -c1 www.tuntransport.academy
   ping -c1 api.tuntransport.academy
   ```
   **Ne lancez pas l'étape 5 avant** : Traefik ne peut obtenir les certificats HTTPS que si le DNS pointe déjà vers le VPS.

## Étape 2 — Vérifier le VPS

```bash
ssh root@IP_DU_VPS

free -h          # mémoire : TunTransport ajoute environ 300 Mo (API + MongoDB)
df -h /          # garder au moins 3 Go libres
docker ps        # Neon Strike et Traefik tournent
```

Si `free -h` montre moins de 400 Mo disponibles (colonne *available*), ajoutez un fichier d'échange de 2 Go avant de continuer :
```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Relevez les réglages Traefik déjà utilisés par Neon Strike, vous les recopierez à l'étape 3 :
```bash
grep -E '^(COMPOSE_FILE|TRAEFIK_)' /opt/apps/neon-strike/deploy/.env
```
Normalement : `TRAEFIK_NETWORK=web`, `TRAEFIK_ENTRYPOINT=websecure`, `TRAEFIK_CERTRESOLVER=letsencrypt`.

## Étape 3 — Récupérer et configurer TunTransport

```bash
apt install -y python3 git              # python3 sert à importer les lignes (souvent déjà installé)
git clone https://github.com/aymenkssi/TunTransport.git /opt/apps/tuntransport
cd /opt/apps/tuntransport/deploy
cp .env.example .env

# Générer les deux secrets (notez-les dans votre gestionnaire de mots de passe)
echo "MONGO_PASSWORD=$(openssl rand -hex 24)"
echo "ADMIN_TOKEN=$(openssl rand -hex 32)"

nano .env
```

Dans `.env` :
- **décommentez** `COMPOSE_FILE=docker-compose.traefik.yml` (retirez le `#`) : c'est ce qui fait passer TunTransport par le Traefik de Neon Strike au lieu d'installer Caddy, qui entrerait en conflit sur les ports 80 et 443 ;
- `DOMAIN=api.tuntransport.academy` et `SITE_DOMAIN=tuntransport.academy` sont déjà remplis ;
- collez `MONGO_PASSWORD` et `ADMIN_TOKEN` générés ci-dessus ;
- `TRAEFIK_NETWORK`, `TRAEFIK_ENTRYPOINT`, `TRAEFIK_CERTRESOLVER` : les valeurs relevées à l'étape 2.

Enregistrez (Ctrl+O, Entrée, Ctrl+X), puis vérifiez :
```bash
docker compose config --services     # doit afficher : mongo, api, site (et pas caddy)
```

## Étape 4 — Importer les lignes de transport

```bash
cd /opt/apps/tuntransport/deploy
python3 ../tools/import_tunismapper.py --out data/network.json --cache data/.cache
```
Environ 4 minutes. La fin doit afficher `228 lignes {'train': 29, 'rfr': 3, 'metro': 7, 'bus': 189}`.

## Étape 5 — Lancer

```bash
docker compose up -d --build
docker compose ps                    # mongo "healthy", api et site "running"
docker compose logs api | tail       # doit contenir "Network loaded: 228 lines"
```

Vérifications (1 à 2 minutes après, le temps que Traefik obtienne les certificats) :
```bash
curl https://api.tuntransport.academy/api/
# {"message":"TunTransport API online","lines":228}
curl -sI https://tuntransport.academy/privacy | head -1
# HTTP/2 200
curl https://api.gameneonstrike.com/api/
# Neon Strike répond toujours normalement
```

Puis, dans le navigateur, ouvrez `https://api.tuntransport.academy/admin` et connectez-vous avec `ADMIN_TOKEN`. L'onglet **Réseau** doit indiquer 228 lignes.

## Étape 6 — Tâches automatiques

```bash
crontab -e
```
Ajoutez ces deux lignes à côté de celles de Neon Strike. Les horaires sont décalés pour ne pas tomber en même temps :
```
30 4 * * * cd /opt/apps/tuntransport/deploy && ./backup.sh >> backups/backup.log 2>&1
0 5 1 * * cd /opt/apps/tuntransport/deploy && ./update-network.sh >> data/update.log 2>&1
```
- Sauvegarde MongoDB chaque nuit (14 jours conservés dans `deploy/backups/`).
- Réimport des lignes le 1er de chaque mois (changements d'horaires).

Test immédiat de la sauvegarde : `./backup.sh` doit afficher `backup tuntransport-….gz OK`.

## Étape 7 — Compiler l'application (sur votre PC)

L'application appelle déjà `https://api.tuntransport.academy` (`frontend/eas.json`). Avec le même compte Expo que Neon Strike :

```bash
git clone https://github.com/aymenkssi/TunTransport.git
cd TunTransport/frontend
yarn install
npm install -g eas-cli          # si ce n'est pas déjà fait pour Neon Strike
eas login
eas init                        # crée le projet "tuntransport" sur expo.dev (répondre Oui)
yarn build:android:preview      # APK installable directement, ≈ 15 min dans le cloud
```
EAS donne un lien et un QR code : ouvrez-le sur le téléphone Android et installez l'APK (autorisez l'installation depuis cette source si Android le demande).

## Étape 8 — Premier essai sur le terrain

Commencez par une ligne de **métro** : les arrêts sont proches et la ligne est en site propre.

1. Sur le quai, ouvrez TunTransport → Métro → votre ligne → choisissez le **sens**.
2. Une fois dans la rame, touchez **Je suis dans ce véhicule** et autorisez la localisation « pendant l'utilisation de l'application ».
3. Au bout de 20 à 30 secondes, le statut doit passer de « Vérification du trajet… » à **« Position partagée »**.
4. Sur un second téléphone, ou dans `https://api.tuntransport.academy/admin` (onglet **En direct**), la rame apparaît.
5. Verrouillez l'écran pendant 2 ou 3 stations : la notification « Partage de trajet actif » reste affichée et la rame continue d'avancer.
6. À la descente, touchez **Arrêter le partage**. Sinon, l'arrêt est automatique 2 minutes après avoir quitté la ligne.

À noter pendant l'essai, pour régler les seuils :
- le temps avant « Position partagée » ;
- les éventuels « Non diffusé : hors du tracé ». C'est surtout probable sur les bus, dont le tracé est approximatif ;
- la consommation de batterie sur un trajet de 30 minutes.

## Étape 9 — Avant Google Play

- Remplacez `[NOM DU RESPONSABLE]` et `[ADRESSE E-MAIL DE CONTACT]` dans `deploy/site/privacy.html` et `deploy/site/index.html`, poussez la modification, puis sur le VPS : `cd /opt/apps/tuntransport && git pull` (le site est servi directement, sans redémarrage).
- Demandez à tunismapper.com l'autorisation d'utiliser leurs données de lignes.
- Play Console : site `https://tuntransport.academy`, confidentialité `https://tuntransport.academy/privacy`. Déclarez le service au premier plan de type « localisation », lancé par l'utilisateur pendant un trajet. L'application ne demande pas la localisation en arrière-plan.
- Build final : `yarn build:android:prod` (AAB).

---

## Mises à jour

À chaque nouvelle version poussée sur GitHub :
```bash
cd /opt/apps/tuntransport && git pull && cd deploy && docker compose up -d --build
```

## En cas de problème

| Symptôme | Cause probable | Solution |
|---|---|---|
| `curl` : erreur de certificat ou 404 de Traefik | DNS pas encore propagé, ou mauvais `TRAEFIK_*` | `ping api.tuntransport.academy`, revoir l'étape 3, puis `docker compose up -d` |
| `network … not found` au lancement | `TRAEFIK_NETWORK` incorrect | `docker network ls`, prendre le réseau du conteneur Traefik |
| `docker compose ps` affiche `caddy` | `COMPOSE_FILE` resté commenté | décommenter la ligne dans `.env`, `docker compose down`, puis `up -d --build` |
| API : `"lines": 0` | import non fait ou mauvais dossier | refaire l'étape 4 dans `deploy/`, puis `docker compose restart api` |
| `/admin` : « Admin disabled » | `ADMIN_TOKEN` vide ou trop court | 16 caractères au moins dans `.env`, puis `docker compose up -d` |
| Neon Strike ne répond plus | (ne devrait pas arriver : aucun fichier de Neon Strike n'est modifié) | `cd /opt/apps/neon-strike/deploy && docker compose ps`, journaux de Traefik |

Journaux : `docker compose logs -f api` (dans `/opt/apps/tuntransport/deploy`).
