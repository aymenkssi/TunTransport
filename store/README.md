# Publier TransTunisLive sur Google Play

Ce dossier contient tout ce qu'il faut pour publier l'application : les images de la fiche, les textes en français, anglais et arabe, les réponses aux formulaires de la Play Console, et la procédure pas à pas.

| Étape | Où | Durée |
|---|---|---|
| 0. Avant de commencer (checklist) | serveur, site, AdMob | 30 min |
| 1. Créer l'application | Play Console | 5 min |
| 2. Remplir « Contenu de l'application » | Play Console → Règles et programmes | 45 min |
| 3. Fiche du Store (textes + images de ce dossier) | Play Console → Croissance → Présence sur le Store | 20 min |
| 4. Construire l'AAB et l'envoyer en test interne | `eas build` puis Play Console | 30 min |
| 5. Test fermé (comptes personnels récents : 12 testeurs, 14 jours) | Play Console → Tester et publier | 14 jours |
| 6. Production | Play Console | examen Google : 1 à 7 jours |
| 7. Relier l'application à AdMob | AdMob | 5 min |

---

## 0. Avant de commencer

- [ ] **Politique de confidentialité** : dans `deploy/site/privacy.html`, remplacer `[NOM DU RESPONSABLE]` et `[ADRESSE E-MAIL DE CONTACT]`, puis mettre le site à jour sur le VPS (`cd ~/TunTransport && git pull && cd deploy && docker compose up -d --build`).
- [ ] Vérifier que ces adresses répondent :
  - https://tuntransport.academy/privacy (politique de confidentialité, obligatoire)
  - https://tuntransport.academy/app-ads.txt (doit contenir `google.com, pub-7488746561313974, DIRECT, f08c47fec0942fa0`)
  - https://api.tuntransport.academy/api/lines (l'API répond, les lignes sont chargées)
- [ ] Une **adresse e-mail de contact** publique (elle s'affiche sur la fiche). Une adresse dédiée est conseillée, par exemple contact@tuntransport.academy.
- [ ] **Données des lignes** : elles viennent de tunismapper.com. Demander une autorisation écrite (un e-mail suffit) avant la publication, et garder la réponse.
- [ ] **AdMob** : les identifiants réels sont déjà dans l'application (`frontend/app.json` et `frontend/src/ads/index.ts`). Les vraies publicités ne s'affichent que dans le build `production`.
- [ ] Faire un dernier test avec un APK `preview` sur un vrai téléphone, dans un vrai bus ou métro : partage, carte en direct, itinéraire, suggestion.

## 1. Créer l'application

Play Console (https://play.google.com/console), même compte développeur que Neon Strike → **Créer une application** :

| Champ | Valeur |
|---|---|
| Nom de l'application | `TransTunisLive` |
| Langue par défaut | Français (France) – fr-FR |
| Application ou jeu | Application |
| Gratuite ou payante | Gratuite (définitif : une application gratuite ne peut plus devenir payante) |
| Déclarations | cocher les deux (Règles du programme pour les développeurs, lois d'exportation des États-Unis) |

Le nom du paquet est fixé au premier envoi d'AAB : `com.aymenkssi.tuntransport`. Il ne pourra plus jamais changer.

## 2. Contenu de l'application

Play Console → **Règles et programmes → Contenu de l'application**. Remplir chaque section comme ci-dessous.

### Règles de confidentialité
```
https://tuntransport.academy/privacy
```

### Accès à l'application
**Toutes les fonctionnalités sont disponibles sans accès spécial** (pas de compte ni de connexion : l'identifiant est anonyme et créé automatiquement).

### Annonces
**Oui, mon application contient des annonces** (AdMob : bannières et interstitiels).

### Classification du contenu (questionnaire IARC)
- Adresse e-mail : `contact@tuntransport.academy`.
- Catégorie : **Toutes les autres catégories d'applications** (ni jeu, ni réseau social).
- Réponses :
  - Violence, sexualité, langage grossier, drogues, jeux d'argent : **Non** partout.
  - Les utilisateurs peuvent-ils interagir ou échanger du contenu entre eux ? **Non** (les suggestions ne vont qu'à l'équipe, rien n'est publié entre utilisateurs).
  - L'application partage-t-elle la position actuelle de l'utilisateur avec d'autres utilisateurs ? **Oui** (pendant un partage, les autres voient le véhicule, donc indirectement l'endroit où se trouve le passager ; mieux vaut le déclarer).
  - Achats numériques : **Non**.
  - Navigateur web ou moteur de recherche non restreint : **Non**.
- Résultat attendu : classification « Tout public » / PEGI 3 avec la mention « Partage de la position ».

### Public cible et contenu
- Tranches d'âge : **18 ans et plus** (conseillé pour la première version : avec des publicités, inclure les moins de 18 ans impose des contraintes supplémentaires sur les annonces). On pourra ajouter 16-17 ans plus tard.
- L'application pourrait-elle attirer les enfants ? **Non**.

### Application d'information
**Non**, ce n'est pas une application d'actualités.

### Applications gouvernementales
**Non** : l'application n'est pas développée par un gouvernement ni en son nom. La description le dit clairement (application indépendante, non affiliée à la Transtu ni à la SNCFT).

### Fonctionnalités financières, santé
**Aucune** (cocher « Mon application ne propose aucune de ces fonctionnalités »).

### Identifiant publicitaire
**Oui**, l'application utilise l'identifiant publicitaire. Utilisation : **Publicité ou marketing** (SDK Google Mobile Ads). La permission `com.google.android.gms.permission.AD_ID` est ajoutée automatiquement par le SDK AdMob.

### Sécurité des données
Questions générales :

| Question | Réponse |
|---|---|
| L'application collecte-t-elle ou partage-t-elle des données ? | **Oui** |
| Toutes les données sont-elles chiffrées en transit ? | **Oui** (HTTPS uniquement) |
| Les utilisateurs peuvent-ils demander la suppression de leurs données ? | **Oui** (À propos → Supprimer mes données, ou par e-mail) |
| Création de compte | **Mon application ne permet pas de créer de compte** |

Types de données à cocher :

| Catégorie → type | Collectée | Partagée | Éphémère | Obligatoire ? | Finalités |
|---|---|---|---|---|---|
| Position → **Position exacte** | Oui | Non | **Oui** (coordonnées traitées puis jetées, seule la position du véhicule sur la ligne reste 5 min) | Facultative (seulement si l'utilisateur partage un trajet ou demande « Ma position ») | Fonctionnalités de l'application ; Prévention de la fraude, sécurité et conformité |
| Position → **Position approximative** | Oui | Non | Oui | Facultative | Fonctionnalités de l'application |
| Informations personnelles → **Adresse e-mail** | Oui | Non | Non | Facultative (contact laissé dans une suggestion) | Communications du développeur |
| Informations personnelles → **Numéro de téléphone** | Oui | Non | Non | Facultative (idem) | Communications du développeur |
| Messages → **Autres contenus générés par l'utilisateur** | Oui | Non | Non | Facultative (texte des suggestions et signalements) | Fonctionnalités de l'application ; Communications du développeur |
| Activité dans l'application → **Autres actions** | Oui | Non | Non | Obligatoire (trajets partagés : ligne, sens, horaires ; signalements) | Fonctionnalités de l'application ; Prévention de la fraude, sécurité et conformité |
| Informations et performances de l'application → **Diagnostics** | Oui | Non | Non | Obligatoire (version de l'application et plateforme, envoyées avec chaque requête) | Fonctionnalités de l'application ; Analyse |
| Identifiants de l'appareil ou autres → **Identifiants de l'appareil ou autres** | Oui | **Oui** | Non | Obligatoire | Fonctionnalités (identifiant anonyme TransTunisLive) ; Publicité ou marketing et Prévention de la fraude (identifiant publicitaire, via le SDK AdMob) |

Notes :
- « Partagée » ne concerne que l'identifiant publicitaire, transmis à Google par le SDK AdMob. La position et les trajets ne sont jamais transmis à la régie publicitaire.
- Si Google signale que le SDK AdMob collecte aussi la **position approximative** (adresse IP) ou des **informations de diagnostic** pour la publicité, ajouter la finalité « Publicité ou marketing » à ces lignes et cocher « Partagée ». Référence : https://developers.google.com/admob/android/privacy/play-data-disclosure

### Autorisations de service de premier plan (Android 14)
L'application utilise un **service de premier plan de type `location`** pour envoyer la position pendant un trajet partagé, écran éteint. Google demande de le déclarer.

- Type : **Localisation**
- Cas d'usage : **Navigation / partage de position déclenché par l'utilisateur**
- Description :
  ```
  Quand l'utilisateur touche « Je suis dans ce véhicule », l'application partage la position du bus, du métro ou du train dans lequel il voyage, pour que les autres voyageurs le voient sur la carte en temps réel. Le partage continue écran éteint grâce à un service de premier plan avec une notification permanente « Partage de trajet actif ». Il s'arrête quand l'utilisateur touche « Arrêter le partage », automatiquement quand il quitte la ligne depuis 2 minutes (il est descendu), ou après la durée maximale d'un trajet. Aucune localisation n'a lieu en dehors d'un partage démarré par l'utilisateur, et l'application ne demande pas la localisation en arrière-plan (ACCESS_BACKGROUND_LOCATION).
  ```
- **Lien vers une vidéo** (YouTube, en « non répertoriée », 30 à 60 s), filmée sur un vrai téléphone :
  1. Ouvrir l'application, onglet Lignes, ouvrir une ligne (par exemple Métro 1).
  2. Toucher **« Je suis dans ce véhicule »**, accepter la localisation « Pendant l'utilisation de l'application », puis **autoriser les notifications**.
  3. Montrer le bandeau « Vous partagez… » et la **notification « Partage de trajet actif »** dans le volet.
  4. Appuyer sur **Accueil** (l'application passe en arrière-plan), ouvrir une autre application, dérouler le volet : la notification est toujours là, le partage continue. (Ne pas verrouiller l'écran : sur la plupart des téléphones, cela arrête l'enregistreur d'écran.)
  5. Toucher **« Arrêter le partage »** : la notification disparaît.

### Autorisations de localisation
L'application ne demande **pas** la localisation en arrière-plan : aucune déclaration « Accès à la position en arrière-plan » n'est nécessaire. Si la Play Console la demande quand même, c'est qu'un AAB contient `ACCESS_BACKGROUND_LOCATION` : ce ne doit pas être le cas (voir `frontend/app.json`, `isAndroidBackgroundLocationEnabled: false`).

Permissions Android du build (vérifiées) : `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_LOCATION`, `POST_NOTIFICATIONS` (demandée au premier partage, pour afficher la notification du service sur Android 13+), `INTERNET`, `VIBRATE`, et celles ajoutées par AdMob (`AD_ID`, `ACCESS_ADSERVICES_*`, `ACCESS_NETWORK_STATE`, `WAKE_LOCK`). Les permissions inutiles ajoutées par certaines bibliothèques (stockage, superposition d'écran, biométrie) sont retirées par `blockedPermissions` dans `frontend/app.json`.

## 3. Fiche du Store

Play Console → **Croissance → Présence sur le Store → Fiche principale du Store**.

### Images

| Fichier | Emplacement | Exigence Google |
|---|---|---|
| `icon-512.png` | Icône de l'application | PNG 512 × 512, 1 Mo max ; Google arrondit les coins |
| `feature-graphic-1024x500.jpg` | Image de présentation (fiche française) | JPEG ou PNG 24 bits, 1024 × 500 |
| `feature-graphic-1024x500-en.jpg` | Image de présentation (traduction anglaise) | idem |
| `feature-graphic-1024x500-ar.jpg` | Image de présentation (traduction arabe) | idem |
| `screenshots/fr/*.jpg` | Captures du téléphone (fiche française et arabe) | 2 à 8 images, 1080 × 1920 |
| `screenshots/en/*.jpg` | Captures du téléphone (traduction anglaise) | idem |

- Envoyer les captures **dans l'ordre des numéros** : la première est la plus vue.
- Les captures sont prises dans la vraie application (version web, mêmes écrans que sur Android), avec des véhicules partagés en test. L'interface est en français dans toutes les langues de fiche, puisque l'application est en français.
- Tablettes : facultatif, les mêmes captures conviennent.

### Coordonnées
| Champ | Valeur |
|---|---|
| Adresse e-mail | `contact@tuntransport.academy` |
| Site web | `https://tuntransport.academy` |
| Téléphone | facultatif (laisser vide) |

### Catégorie et tags
Play Console → **Paramètres du Store** :
- Catégorie : **Cartes et navigation**
- Tags (jusqu'à 5) : Transports en commun, Navigation, Cartes, Trafic, Itinéraires

### Textes – Français (fr-FR)

**Nom de l'application** (30 caractères max) :
```
TransTunisLive : bus et métro
```

**Description courte** (80 caractères max) :
```
Bus, métro, TGM et trains de Tunis en temps réel, partagés par les voyageurs.
```

**Description complète** (4000 caractères max) :
```
Où est mon bus ? Quand arrive le métro ? TransTunisLive est le « Waze » des transports en commun du Grand Tunis : les voyageurs à bord partagent la position du véhicule, et tout le monde le voit avancer sur la carte en temps réel.

• CARTE EN DIRECT : bus, métro léger, TGM, RFR et trains qui roulent en ce moment, avec la ligne, la direction, la vitesse et le nombre de passagers qui les confirment.
• ARRIVÉES À VOTRE ARRÊT : touchez un arrêt pour savoir dans combien de minutes arrive le prochain véhicule, avec les horaires théoriques quand personne ne partage.
• PARTAGEZ EN UN GESTE : dans le bus ? Touchez « Je suis dans ce véhicule ». Votre téléphone aide les autres voyageurs tant que vous êtes à bord, et s'arrête tout seul quand vous descendez.
• ITINÉRAIRES : de n'importe quelle adresse à n'importe quelle autre, avec les correspondances, la marche à pied et l'heure de départ de votre choix. Aussi en voiture ou à pied.
• RECHERCHE D'ADRESSE INTELLIGENTE : rues, quartiers, hôpitaux, écoles… même avec une faute de frappe (« hyppocrate », « avicene »…).
• 228 LIGNES : métro léger, bus Transtu, TGM, RFR et trains de banlieue, avec leurs arrêts et leur tracé.
• FIABLE : chaque position est vérifiée (elle doit suivre la ligne, à une vitesse de véhicule) et confirmée par les autres passagers. Les fausses déclarations sont écartées automatiquement.
• VOTRE AVIS COMPTE : signalez une erreur sur une ligne ou proposez une idée directement depuis l'application.

RESPECT DE LA VIE PRIVÉE
• Pas de compte, pas d'inscription : un identifiant anonyme suffit.
• Votre position n'est utilisée que pendant un trajet que vous partagez vous-même, jamais en dehors.
• Le serveur ne garde pas vos coordonnées GPS : seulement la position du véhicule sur la ligne, effacée après 5 minutes.
• Les autres voient un véhicule, jamais une personne.
• Supprimez toutes vos données en un geste depuis l'application.

Application gratuite, financée par la publicité (jamais pendant un trajet partagé).

TransTunisLive est une application indépendante, non affiliée à la Transtu, à la SNCFT ni à aucun organisme public. Données des lignes : tunismapper.com. Cartes : © contributeurs OpenStreetMap. Les horaires théoriques sont indicatifs : plus il y a de voyageurs qui partagent, plus les informations en direct sont précises.
```

### Textes – Anglais (en-US)
Fiche principale du Store → **Gérer les traductions → Ajouter des traductions → Anglais (États-Unis) – en-US**.

**App name**:
```
TransTunisLive: Bus & Metro
```

**Short description**:
```
Tunis buses, metro, TGM and trains in real time, shared by riders.
```

**Full description**:
```
Where is my bus? When is the metro coming? TransTunisLive is the "Waze" of public transport in Greater Tunis: riders on board share the vehicle's position, and everyone sees it move on the map in real time.

• LIVE MAP: buses, light metro, TGM, RFR and trains running right now, with the line, direction, speed and how many riders confirm them.
• ARRIVALS AT YOUR STOP: tap a stop to see in how many minutes the next vehicle arrives, with timetables when nobody is sharing.
• SHARE IN ONE TAP: on the bus? Tap "Je suis dans ce véhicule" (I'm on this vehicle). Your phone helps other riders while you are on board, and stops by itself when you get off.
• ROUTE PLANNER: from any address to any other, with transfers, walking and the departure time you choose. By car or on foot too.
• SMART ADDRESS SEARCH: streets, neighborhoods, hospitals, schools… even with a typo.
• 228 LINES: light metro, Transtu buses, TGM, RFR and suburban trains, with their stops and routes.
• RELIABLE: every position is checked (it must follow the line at vehicle speed) and confirmed by other riders. False reports are filtered out automatically.
• YOUR FEEDBACK MATTERS: report a mistake on a line or suggest an idea right from the app.

PRIVACY FIRST
• No account, no sign-up: an anonymous ID is enough.
• Your location is only used during a ride you choose to share, never otherwise.
• The server does not keep your GPS coordinates: only the vehicle's position along the line, deleted after 5 minutes.
• Others see a vehicle, never a person.
• Delete all your data in one tap from the app.

Free app, supported by ads (never during a shared ride). The app interface is in French.

TransTunisLive is an independent app, not affiliated with Transtu, SNCFT or any public body. Line data: tunismapper.com. Maps: © OpenStreetMap contributors. Timetables are indicative: the more riders share, the more accurate the live information.
```

### Textes – Arabe (ar)
Gérer les traductions → **Arabe – ar**. Images : `feature-graphic-1024x500-ar.jpg` et les captures `screenshots/fr/`.

**اسم التطبيق**:
```
TransTunisLive: الحافلة والمترو
```

**وصف قصير**:
```
الحافلات والمترو و TGM والقطارات في تونس مباشرة، بمشاركة الركاب.
```

**الوصف الكامل**:
```
أين الحافلة؟ متى يصل المترو؟ TransTunisLive هو «Waze» النقل العمومي في تونس الكبرى: الركاب على متن العربة يشاركون موقعها، والجميع يراها تتقدم على الخريطة مباشرة.

• خريطة مباشرة: الحافلات والمترو الخفيف و TGM و RFR والقطارات التي تسير الآن، مع الخط والاتجاه والسرعة وعدد الركاب الذين يؤكدونها.
• الوصول إلى محطتك: المس محطة لتعرف بعد كم دقيقة تصل العربة القادمة، مع المواعيد النظرية عندما لا يشارك أحد.
• شارك بلمسة واحدة: في الحافلة؟ المس «Je suis dans ce véhicule». هاتفك يساعد الركاب الآخرين طوال الرحلة ويتوقف تلقائيًا عند نزولك.
• حساب المسار: من أي عنوان إلى آخر، مع التحويلات والمشي ووقت الانطلاق الذي تختاره. وأيضًا بالسيارة أو مشيًا.
• بحث ذكي عن العناوين: شوارع وأحياء ومستشفيات ومدارس… حتى مع خطأ في الكتابة.
• 228 خطًا: المترو الخفيف وحافلات شركة النقل بتونس و TGM و RFR وقطارات الضواحي، مع محطاتها ومساراتها.
• موثوق: كل موقع يتم التحقق منه (يجب أن يتبع الخط بسرعة عربة) ويؤكده ركاب آخرون. التصريحات الكاذبة تُستبعد تلقائيًا.

احترام الخصوصية
• بدون حساب وبدون تسجيل.
• لا يُستعمل موقعك إلا أثناء رحلة تختار مشاركتها.
• لا يحتفظ الخادم بإحداثياتك: فقط موقع العربة على الخط، ويُحذف بعد 5 دقائق.
• يرى الآخرون عربة، وليس شخصًا.
• احذف كل بياناتك بلمسة واحدة من التطبيق.

تطبيق مجاني مموّل بالإعلانات (لا إعلانات أثناء رحلة مشتركة). واجهة التطبيق باللغة الفرنسية.

TransTunisLive تطبيق مستقل، غير تابع لشركة النقل بتونس (Transtu) ولا للشركة الوطنية للسكك الحديدية التونسية ولا لأي هيكل عمومي. بيانات الخطوط: tunismapper.com. الخرائط: © مساهمو OpenStreetMap.
```

## 4. Construire l'AAB et le premier envoi

Sur ton PC, dans `frontend/` :

```bash
git pull
yarn install
yarn build:android:prod      # = eas build -p android --profile production
```

- Le profil `production` produit un **AAB** (`.aab`), avec les **vraies publicités** (`EXPO_PUBLIC_AD_MODE=production`) et un `versionCode` incrémenté automatiquement par EAS.
- Attention : la commande est `build:android:prod` (et pas `build:android:production`).
- EAS gère la **clé de signature** : la première fois, accepter « Generate a new Android Keystore ». Google Play App Signing re-signe ensuite l'application ; garder la clé d'importation chez EAS (`eas credentials` permet de la télécharger en sauvegarde).

**Premier envoi : à la main** (Google refuse l'envoi par API tant qu'aucun AAB n'a été envoyé dans la console) :
1. Télécharger le `.aab` depuis la page du build sur expo.dev.
2. Play Console → **Tester et publier → Tests → Test interne → Créer une release**.
3. Accepter **Signature d'application par Google Play**.
4. Glisser le `.aab`, nom de release `1.0.0 (1)`, notes de version ci-dessous, **Enregistrer → Examiner la release → Lancer le déploiement**.
5. Onglet **Testeurs** : créer une liste avec ton adresse Gmail, copier le lien d'inscription, l'ouvrir sur le téléphone et installer depuis le Play Store.

**Envois suivants : automatiques** avec `eas submit` :
1. Google Cloud Console → créer un **compte de service**, puis une clé JSON ; Play Console → **Utilisateurs et autorisations → Inviter** l'adresse du compte de service avec le droit « Publier en test » (guide : https://github.com/expo/fyi/blob/main/creating-google-service-account.md).
2. Enregistrer la clé dans `frontend/google-play-service-account.json` (déjà dans `.gitignore` : ne jamais la commiter ni la coller dans un chat).
3. Après chaque build : `yarn submit:android` → l'AAB arrive en **brouillon** sur la piste **test interne** (réglé dans `eas.json`). Il reste à le lancer ou à le promouvoir dans la Play Console.

### Notes de version 1.0.0

```
<fr-FR>
Première version de TransTunisLive :
• carte en direct des bus, métros, TGM, RFR et trains partagés par les voyageurs ;
• arrivées en temps réel à votre arrêt ;
• itinéraires en transports, en voiture ou à pied ;
• recherche d'adresse tolérante aux fautes ;
• suggestions et signalements depuis l'application.
</fr-FR>
<en-US>
First release of TransTunisLive:
• live map of buses, metros, TGM, RFR and trains shared by riders;
• real-time arrivals at your stop;
• public transport, car and walking routes;
• typo-tolerant address search;
• suggestions and reports from the app.
</en-US>
<ar>
الإصدار الأول من TransTunisLive:
• خريطة مباشرة للحافلات والمترو و TGM و RFR والقطارات بمشاركة الركاب؛
• مواعيد الوصول المباشرة إلى محطتك؛
• حساب المسار بالنقل العمومي أو بالسيارة أو مشيًا؛
• بحث عن العناوين يتحمل الأخطاء؛
• اقتراحات وتبليغات من داخل التطبيق.
</ar>
```

## 5. Test fermé (avant la production)

Les **comptes développeur personnels créés après le 13 novembre 2023** doivent faire un **test fermé avec au moins 12 testeurs inscrits pendant 14 jours d'affilée** avant de pouvoir demander l'accès à la production. Si le compte de Neon Strike a déjà fait ce parcours, l'accès production est déjà acquis : passer directement à l'étape 6.

1. **Tester et publier → Tests → Test fermé → Alpha → Gérer la piste**.
2. **Pays** : Tunisie.
3. **Testeurs** : une liste d'adresses Gmail (au moins 12 personnes, l'idéal : des gens qui prennent vraiment le bus ou le métro à Tunis, c'est le meilleur test de l'application). Envoyer le lien d'inscription.
4. **Créer une release** : promouvoir la release du test interne (ou envoyer un nouvel AAB).
5. Laisser tourner 14 jours. Les testeurs doivent rester inscrits et ouvrir l'application de temps en temps. Lire leurs retours dans **l'admin web → Suggestions**.
6. Ensuite : **Tableau de bord → Demander l'accès à la production**, et répondre au questionnaire (comment le test s'est passé, ce qui a été corrigé, pourquoi l'application est prête).

## 6. Production

1. **Tester et publier → Production → Pays/régions** : **Tunisie** (on peut ajouter la France, l'Italie, l'Allemagne… pour la diaspora qui rentre l'été).
2. **Créer une release** → promouvoir la release testée → notes de version → **Examiner la release**.
3. Corriger les éventuels avertissements, puis **Lancer le déploiement en production**. Commencer à 100 % (déploiement progressif inutile pour une première version).
4. Examen par Google : quelques heures à 7 jours. Surveiller **Vue d'ensemble de la publication** et les e-mails.

Après la publication :
- Lien public : https://play.google.com/store/apps/details?id=com.aymenkssi.tuntransport
- Mettre ce lien sur le site (`deploy/site/index.html`).

## 7. AdMob

1. AdMob → **Applications → TransTunisLive → Paramètres de l'application → Ajouter une plate-forme de téléchargement d'applications** → Google Play, chercher « TransTunisLive » (possible seulement une fois l'application publiée).
2. AdMob vérifie ensuite `app-ads.txt` sur le site du développeur : le champ **Site web** de la fiche Play doit être exactement `https://tuntransport.academy` (l'explorateur d'AdMob lit `https://tuntransport.academy/app-ads.txt`). La vérification prend jusqu'à 24 h.
3. **Confidentialité et messages** : le message de consentement RGPD (UMP) est déjà géré par l'application ; vérifier qu'il est **publié** dans AdMob.
4. Ne jamais cliquer sur ses propres annonces : pour tester, utiliser un build `preview` (annonces de test).

## Mises à jour

1. Changer `"version"` dans `frontend/app.json` (par exemple `1.0.1`) ; le `versionCode` est incrémenté automatiquement par EAS.
2. `yarn build:android:prod` puis `yarn submit:android`.
3. Play Console : promouvoir la release du test interne vers la production, avec des notes de version.

## Refus fréquents et solutions

| Message de Google | Cause | Solution |
|---|---|---|
| « Politique de confidentialité non valide » | lien inaccessible ou placeholders `[…]` encore présents | compléter `privacy.html`, redéployer le site |
| « Déclaration de service de premier plan incomplète » | vidéo absente ou ne montrant pas la notification | refaire la vidéo selon le scénario de la section 2 |
| « Métadonnées trompeuses / usurpation » | l'application semble officielle | garder la mention « application indépendante, non affiliée à la Transtu ni à la SNCFT », ne pas utiliser leurs logos |
| « Sécurité des données incohérente » | une donnée envoyée par le SDK AdMob non déclarée | compléter selon la page Google indiquée dans la section Sécurité des données |
| « Fonctionnalité limitée » (test fermé) | testeurs inactifs | demander aux testeurs d'utiliser l'application pendant les 14 jours |
