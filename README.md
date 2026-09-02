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
| `budget` | Comptes financiers, catégories, transactions |
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

## Fiscalité belge — avertissement

Les calculateurs de `apps/taxes` sont fournis à titre indicatif. Les taux et
seuils (TOB, précompte mobilier, taxe sur la plus-value entrée en vigueur en
2026) sont stockés en base et modifiables depuis l'admin Django — vérifiez
toujours les valeurs en vigueur auprès du SPF Finances avant de vous y fier
pour une déclaration réelle.

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

- Transactions récurrentes / budgets prévisionnels
- Récupération automatique des cours de bourse
- Connexion OAuth (Google)
- Répartition de l'exonération de plus-value par personne (actuellement
  agrégée au niveau du foyer)
- Conversion de devises par triangulation (aujourd'hui seuls les taux
  directs et inverses sont utilisés, ce qui couvre tous les cas EUR ↔ X)
