# Service d’alertes par e-mail (`alert_service.py`)

Petit module Python (pas une API HTTP) qui envoie des **notifications par SMTP** lorsque l’application veut alerter un opérateur.

## Classe `AlertService`

### `__init__(self)`

Charge la configuration depuis `config.py` : adresse destinataire, serveur SMTP, port, identifiant et mot de passe. Ces valeurs viennent en général des **variables d’environnement**.

### `send_email_alert(self, subject, message, severity="INFO")`

- **Rôle** : construit un e-mail (sujet préfixé par la sévérité, corps avec horodatage et message) et l’envoie via **TLS** (`starttls`) + authentification SMTP.
- **Si la config est incomplète** (pas d’e-mail destinataire ou pas d’utilisateur SMTP) : affiche un message en console et retourne `False` sans envoyer.
- **En cas de succès** : retourne `True`.
- **En cas d’erreur réseau ou SMTP** : affiche l’erreur, retourne `False`.

## Instance globale

**`alert_service`** : une instance unique réutilisable (`AlertService()`), pour importer simplement `alert_service` ailleurs dans le projet et appeler `send_email_alert(...)`.
