# Kiwi

Application de gestion budgétaire et patrimoniale pour le ménage : comptes
personnels, comptes communs, investissements, actifs réels, et outils
fiscaux belges (TOB, précompte mobilier, taxe sur la plus-value).

## Stack

- **Backend** : Django 5.2 (multi-foyers dès le départ — `apps/accounts`)
- **Frontend** : templates Django + HTMX + Alpine.js + Chart.js (pas de SPA,
  pas de build JS à maintenir)
- **Style** : Tailwind CSS v4, compilé via le binaire standalone (aucune
  dépendance Node)
- **Base de données** : PostgreSQL en production, SQLite en dev par défaut
- **Tâches planifiées** : Celery + Redis (taux de change quotidiens, photo
  mensuelle du patrimoine)
- **Déploiement** : Docker Compose (web, db, redis, worker, beat, Caddy en
  reverse proxy avec HTTPS automatique)

## Applications

| App | Rôle |
|---|---|
| `accounts` | Utilisateurs, foyers, adhésions, invitations, isolation multi-foyers |
| `budget` | Comptes financiers, catégories, transactions, budgets prévisionnels, récurrences |
| `wealth` | Titres, opérations sur titres (FIFO), actifs réels, dettes, patrimoine net |
| `fx` | Devises et taux de change |
| `taxes` | Calculateurs fiscaux belges (TOB, précompte mobilier, plus-value) |
| `imports_app` | Import CSV de relevés bancaires (mapping de colonnes configurable) |
| `dashboard` | Tableau de bord avec graphiques (Chart.js) |

## Développement local (sans Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Le CSS Tailwind est déjà compilé dans `static/css/output.css`. Pour le
regénérer après une modification de `static_src/css/input.css` ou des
templates :

```bash
curl -sL -o /tmp/tailwindcss \
  https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64
chmod +x /tmp/tailwindcss
/tmp/tailwindcss -i static_src/css/input.css -o static/css/output.css --minify
```

### Tests

```bash
pytest
ruff check apps config manage.py
```

## Déploiement (Docker Compose)

```bash
cp .env.example .env   # éditez les secrets et le domaine
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

Caddy obtient automatiquement un certificat HTTPS pour `SITE_DOMAIN` (mettez
`localhost` pour un test local).

## Connexion par lien magique (passwordless)

En plus du login email/mot de passe classique, `/accounts/magic-login/`
permet de recevoir un lien de connexion par email. Le lien est à usage
unique et valable 15 minutes ; une fois cliqué, le navigateur reste connecté
**90 jours glissants** (le délai est repoussé à chaque visite, donc tant que
vous ouvrez l'app de temps en temps, vous ne vous reconnectez jamais).

En dev, aucun email n'est réellement envoyé : le contenu (et donc le lien)
s'affiche directement dans la console du serveur. En production, renseignez
les variables `EMAIL_*` du `.env` avec n'importe quel fournisseur SMTP
(Gmail SMTP, Resend, Mailgun, Postmark...).

## Budgets et transactions récurrentes

Les **budgets** se définissent par catégorie, par mois et par personne — chaque
membre a ses propres enveloppes, plus un budget « commun » (`owner = NULL`).

Les dépenses réelles sont rattachées à une personne **via le compte utilisé** :
une dépense sur un compte perso compte pour son propriétaire, une dépense sur
un compte joint compte pour le commun. Il n'y a donc rien à taguer à la saisie
ni à l'import.

Les **transactions récurrentes** (loyer, salaire, abonnements) sont
volontairement **prévisionnelles uniquement** : elles ne créent jamais de
transaction. Vos mouvements réels viennent de l'import bancaire ou de la
saisie manuelle — matérialiser les récurrences en plus doublonnerait chaque
loyer et chaque salaire. Elles alimentent la colonne « attendu » des budgets
et la liste des échéances à venir.

Les échéances sont calculées comme `date de début + n × période` plutôt qu'en
avançant de proche en proche : un loyer au 31 retombe au 28 en février puis
**revient** au 31, au lieu de dériver définitivement.

### Solde projeté en fin de mois

Le tableau de bord et la liste des comptes affichent un solde projeté,
décomposé plutôt que présenté comme un chiffre magique :

```
  solde d'aujourd'hui
+ transactions déjà saisies mais datées dans le futur
+ échéances récurrentes restantes
= solde projeté en fin de mois
```

Seules les échéances **strictement postérieures à aujourd'hui** sont
projetées : celles déjà passées ce mois-ci sont supposées présentes dans le
solde (importées ou saisies), les reprojeter les compterait deux fois. La
projection suppose donc vos imports bancaires à jour. Un compte qui passe
sous zéro d'ici la fin du mois est signalé en rouge.

## Périmètres : moi, le commun, et l'autre membre

Comptes, budgets et patrimoine sont regroupés par **périmètre**, dans le même
ordre partout, depuis votre session vers l'extérieur :

```
Moi  →  Commun au foyer  →  chaque autre membre
```

La même donnée se lit donc différemment selon la session : ce que Julien voit
comme « Moi », Marie le voit comme « Julien », et réciproquement. Seuls
l'étiquetage et l'ordre changent.

**Rien n'est masqué** : le foyer reste le périmètre de confiance, chaque membre
voit tout. `owner` dit à qui une chose appartient, pas qui a le droit de la
voir. Un compte perso sert à attribuer les dépenses au bon budget, pas à les
cacher au conjoint.

La page Patrimoine affiche le total **famille** consolidé, puis le détail par
périmètre. Les deux viennent des mêmes lignes : le consolidé est exactement la
somme des périmètres, jamais un calcul parallèle qui pourrait diverger.

## Calcul du patrimoine net

Le patrimoine net additionne les soldes des comptes, la valeur de marché des
positions en titres, les actifs réels, et soustrait les dettes. Tout est
converti dans la devise de référence du foyer via `apps/fx`.

Deux cas dégradent volontairement le calcul plutôt que de fausser
silencieusement le total — ils sont alors signalés en jaune sur la page
Patrimoine :

- une position sans cours connu est valorisée à son prix de revient ;
- un montant dans une devise sans taux de change disponible est compté tel
  quel, sans conversion.

## Cours de bourse automatiques

La source de données est **configurable** — c'est une décision de config, pas
un changement de code :

```bash
SECURITY_PRICE_PROVIDER=yahoo   # ou stooq, ou twelvedata
```

| Source | Clé API | Palier gratuit | Devise renvoyée | Notation |
|---|---|---|---|---|
| `yahoo` | non | illimité de fait | oui | `IWDA.AS` |
| `stooq` | **non** | illimité de fait | **non** | `iwda.nl` |
| `twelvedata` | oui | généreux | oui | `IWDA.AS` |

> Les paliers gratuits de ces services évoluent — vérifiez les conditions
> courantes sur leur site avant de vous engager.

**yahoo** a la meilleure couverture des ETF européens mais s'appuie sur une API
non officielle qui casse régulièrement. **stooq** ne demande aucune clé ni
inscription et sert du CSV brut : c'est le filet de secours le plus robuste
pour un usage léger, au prix de ne pas renvoyer la devise du cours.
**twelvedata** demande une clé (`TWELVEDATA_API_KEY`) mais renvoie la devise,
ce qui permet au garde-fou ci-dessous de fonctionner pleinement.

### Symboles

Renseignez le **symbole de cours** d'un titre dans l'admin Django. Il est
distinct de l'ISIN — aucun de ces fournisseurs ne sait chercher par ISIN — et
**propre à chaque source** : le même ETF est `IWDA.AS` chez Yahoo et
`iwda.nl` chez Stooq. Changer de fournisseur implique donc généralement de
revoir les symboles.

Un titre peut surcharger le fournisseur global via son champ **fournisseur de
cours** (utile si une ligne n'est cotée que par une seule source). Un titre
sans symbole reste en saisie manuelle, ce qui est parfaitement valable.

### Garde-fous

Kiwi **refuse** un cours dont la devise ne correspond pas à celle enregistrée
pour le titre : stocker un cours en USD sur une ligne libellée en EUR
fausserait tout le patrimoine sans prévenir. Les fournisseurs qui ne
communiquent pas la devise (Stooq) laissent Kiwi faire confiance à la config —
vérifiez donc la devise vous-même à la saisie.

Un échec sur un titre n'interrompt jamais les autres : la raison est écrite en
base et **affichée sur la page Patrimoine**, inutile d'aller lire les logs
Celery. Un cours de plus de 7 jours (`STALE_PRICE_AFTER_DAYS`) y est signalé
comme potentiellement périmé.

### Commandes

```bash
# rafraîchir tous les cours maintenant
python manage.py update_security_prices

# essayer une autre source sans toucher au .env
python manage.py update_security_prices --provider stooq

# récupérer l'historique — utile pour la valeur de référence au 31/12/2025
# que la taxe belge sur la plus-value utilise pour les positions antérieures
python manage.py backfill_security_prices --since 2025-12-01 --until 2026-01-15
```

Ajouter une source revient à écrire une classe dans
`apps/wealth/providers/` exposant `fetch_quote` et `fetch_history`, puis à
l'enregistrer dans le registre — rien d'autre dans l'application ne connaît
le fournisseur.

## Fiscalité belge — avertissement

Les calculateurs de `apps/taxes` sont fournis à titre indicatif. Les taux et
seuils (TOB, précompte mobilier, taxe sur la plus-value entrée en vigueur en
2026) sont stockés en base et modifiables depuis l'admin Django — vérifiez
toujours les valeurs en vigueur auprès du SPF Finances avant de vous y fier
pour une déclaration réelle.

Les plus-values sont calculées en FIFO. Modifier ou supprimer une opération
recalcule automatiquement toutes les ventes postérieures sur le même
titre — le coût de revient d'une vente dépendant de tout l'historique qui la
précède.

## Suites prévues (hors périmètre de cette première version)

- Connexion OAuth (Google)
- Répartition de l'exonération de plus-value par personne (actuellement
  agrégée au niveau du foyer)
- Conversion de devises par triangulation (aujourd'hui seuls les taux
  directs et inverses sont utilisés, ce qui couvre tous les cas EUR ↔ X)
