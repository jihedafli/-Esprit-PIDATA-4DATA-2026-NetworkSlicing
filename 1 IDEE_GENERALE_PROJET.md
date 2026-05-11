# Idée générale du projet — Network Slicing 5G

> **Pour tout voir en langage simple (services, fichiers, liens) :** `GUIDE_SIMPLE_PROJET.md`

## Description (résumé)

**Projet académique et technique** qui illustre une **plateforme de bout en bout** pour le **découpage réseau 5G** : prédire la **qualité de service (QoS)**, estimer les **risques SLA**, **détecter des anomalies** sur les tranches, **centraliser la supervision** dans un tableau de bord opérateur, et **tracer les modèles** (versions, métriques). L’ensemble est déployé en **microservices Docker** (API, base MySQL, passerelle Nginx), avec des extensions **MLOps** (entraînement automatisé, **MLflow** pour le suivi des runs, CI GitHub) et **observabilité** (Elasticsearch, Kibana, Metricbeat). L’objectif pédagogique est de montrer comment passer des **données réseau** à un **système exploitable** : API, UI, alertes et bonnes pratiques d’ingénierie logicielle et ML.

---

## C’est quoi un SLA ?

**SLA** signifie **Service Level Agreement** (en français : **accord de niveau de service**, parfois appelé **contrat de niveau de service**). Il s’agit d’un **engagement** — souvent contractuel — entre celui qui **fournit** un service (par exemple l’opérateur réseau) et celui qui le **consomme** (entreprise, service interne, etc.). L’accord précise **ce qui est promis** et **comment on vérifie** que la promesse est tenue.

En pratique, un SLA s’appuie sur des **indicateurs mesurables**, par exemple :

- **disponibilité** du service (pourcentage de temps où il est utilisable) ;
- **latence** ou **délai** maximal acceptable ;
- **débit** ou **capacité** minimale ;
- **taux d’erreur** ou de perte de paquets admissible.

Si les mesures **dépassent** les limites fixées, on parle de **violation** ou de **non-conformité** au SLA ; l’accord peut prévoir des **pénalités**, des **credits**, ou au minimum une **priorisation** des actions correctives.

**Lien avec ce projet :** la prédiction **QoS** et les scores de **risque** estiment si une **tranche (slice)** risque de ne **pas** respecter le niveau de service attendu. D’où les notions de **conformité SLA**, de **violation** et d’**alertes** lorsque la situation devient critique (voir aussi le tableau de bord et le moteur d’alertes).

---

## C’est quoi un NOC ?

**NOC** signifie **Network Operations Center** (en français : **centre d’exploitation réseau** ou **centre d’opérations réseau**). C’est l’endroit — physique ou logique — où des **équipes** surveillent en continu **l’état du réseau** et des services qui en dépendent : disponibilité, incidents, alarmes, charge, liaisons, etc.

Les missions typiques d’un NOC :

- **superviser** des tableaux de bord et des flux d’alertes ;
- **détecter** une dégradation ou une panne le plus tôt possible ;
- **qualifier** l’incident (gravité, périmètre) ;
- **coordonner** les actions : escalade vers l’ingénierie, communication, tickets ;
- parfois appliquer des **actions d’exploitation** (seuils, bascules, paramètres opérationnels) selon les procédures.

On ne confond pas toujours **NOC** et **SOC** (*Security Operations Center*) : le NOC est centré sur la **disponibilité et la performance** du réseau et des services ; le SOC est centré sur la **cybersécurité** (intrusions, menaces). Les deux peuvent collaborer lorsqu’un incident réseau et un incident de sécurité se croisent.

**Lien avec ce projet :** le service **MS3** joue le rôle d’une **console opérateur** de type NOC : authentification, tableau de bord, vue des prédictions et anomalies, gestion des alertes et des opérations sur les tranches. En démo, l’accès peut passer par le préfixe **`/noc/`** derrière Nginx (voir `WORKFLOW_TEST_GUIDE.md` pour les URL exactes).

---

## Problème que le projet adresse

Les opérateurs et architectes 5G doivent **allouer des ressources par tranche (slice)** tout en garantissant des **SLA**. Il faut anticiper la dégradation (congestion, pertes, délais), repérer des **comportements anormaux** et donner une **vision consolidée** aux équipes NOC — sans tout mélanger dans un seul monolithe. Ce dépôt propose une **découpe en services** qui sépare clairement la prédiction QoS, la détection d’anomalies, le dashboard et la gestion de modèles.

---

## Idée générale (en une phrase)

> **Des modèles ML spécialisés** (QoS, anomalies) **exposés par des API**, **persistés et agrégés** dans **MySQL**, **consommés** par un **dashboard** et une **passerelle web**, le tout **conteneurisé**, **testé en CI** et **supervisable** avec une stack Elastic optionnelle.

---

## Les briques principales

| Brique | Rôle dans l’idée du projet |
|--------|----------------------------|
| **MS1** | Cœur « prédiction » : QoS 5G, congestion, UI et documentation API ; écrit l’historique des prédictions. |
| **MS2** | « Sécurité réseau / qualité » : signale des tranches suspectes (modèles dans `ml/`). |
| **MS3** | Console **type NOC** : login, résumés, alertes, opérations sur les tranches. |
| **MS5** | « Gouvernance ML » : registre des modèles, métriques, artefacts. |
| **MySQL** | Source de vérité partagée pour prédictions, anomalies, alertes, logs métier. |
| **Nginx** | Point d’entrée unique (HTTP/HTTPS), routage vers les services, page workflow statique. |
| **Stack Elastic** | Compréhension **infra** (métriques machine / Docker) et option **ML** (indexation de `metadata.json` après entraînement). |
| **MLflow** | Suivi d’expériences et artefacts — **composant requis** du volet MLOps / entraînement. |
| **CI / GitHub Actions** | Qualité du code, tests, entraînement « smoke » sur petit jeu de données, CD manuel possible. |

---

## Modèles ML et analyse de conformité SLA

Cette section précise **ce que recouvrent** les briques « Random Forest · XGBoost · MLP », « Isolation Forest + Autoencoder » et « analyse de conformité SLA » dans **ce dépôt** (MS1, MS2, entraînement sous `scripts/train_models.py`, artefacts dans `ml/`).

### Random Forest, XGBoost et MLP (réseau de neurones)

**Rôle :** trois modèles **supervisés** entraînés sur des données de trafic / tranches 5G pour la **prédiction associée au QoS et au type de tranche** côté **MS1**. Ils partagent la **même entrée** (métriques : perte de paquets, délai, indicateurs de service, etc.) et la **même liste de caractéristiques** (`ml/features.pkl`), avec normalisation lorsque le pipeline l’utilise (`ml/scaler.pkl`).

| Modèle | Idée courte |
|--------|-------------|
| **Random Forest** | Ensemble d’arbres de décision ; souvent robuste et interprétable, adapté aux relations non linéaires entre métriques et étiquette / score. |
| **XGBoost** | Boosting sur arbres ; très utilisé sur données tabulaires, utile pour comparer ou compléter la forêt aléatoire. |
| **MLP** (*Multi-Layer Perceptron*) | Petit réseau de neurones « classique » sur les mêmes features ; peut capturer des motifs différents des modèles à arbres. |

**Dans le code :** l’inférence est centralisée dans `slice_inference.py` (chargement de `rf_model.pkl`, `xgb_model.pkl`, `mlp_model.pkl`). L’**entraînement** et le suivi **MLflow** passent par `scripts/train_models.py`. L’intérêt pédagogique : **plusieurs algorithmes** pour une même famille de problèmes, avec **traçabilité** (MLflow, MS5) et exposition **API / UI**.

### Isolation Forest et autoencoder (détection d’anomalies)

**Rôle :** le service **MS2** signale des tranches ou des profils de métriques **anormaux** par rapport à ce qui a été observé à l’entraînement, sans se limiter à une classification supervisée « classe A vs B ».

| Approche | Idée courte |
|----------|-------------|
| **Isolation Forest** | Méthode classique d’anomalie sur données tabulaires : les points « rares » sont plus faciles à isoler dans l’espace des features. |
| **Autoencoder** | Le modèle apprend à **reconstruire** des exemples considérés comme normaux ; une **erreur de reconstruction** élevée sur un nouvel échantillon suggère un comportement anormal. |

Les deux peuvent être **combinés** (scores, seuils, logique métier) pour renforcer la détection. Les artefacts attendus côté projet se trouvent sous `ml/` (par ex. modèles `.h5` / `.pkl` selon le pipeline). Les résultats alimentent la **supervision NOC** (**MS3**) : anomalies visibles sur le tableau de bord et dans les flux d’alertes.

### Analyse de conformité SLA

**Ce n’est pas un quatrième « gros » modèle ML isolé** : c’est l’**interprétation** des métriques (prédites ou observées) par rapport à des **références et seuils** alignés sur les engagements de service (délai, perte de paquets, charge / congestion, etc.), par tranche ou type de service.

- **MS1** produit notamment un **score QoS**, un **niveau de congestion** et met en regard **délai / PLR** (et le reste du contexte) avec des **références SLA** configurables (voir variables d’environnement et le moteur de congestion).
- L’**historique** permet d’agréger une vue de **conformité** : par exemple le taux de prédictions conformes aux objectifs (voir les statistiques exposées par l’API MS1, dont `/predict/stats`).

En résumé : **RF / XGB / MLP** et **MS2** répondent à « **quelle situation de QoS / quelle anomalie ?** » ; l’**analyse de conformité SLA** répond à « **est-ce acceptable au regard des engagements ?** » et soutient **alertes**, **NOC** et pilotage.

### Différences entre ces briques et pourquoi les utiliser

**Random Forest, XGBoost et MLP** répondent tous à une question de **prédiction supervisée** : à partir des mêmes métriques réseau, ils estiment une cible apprise sur des **données étiquetées** (type de tranche / dimension QoS du pipeline d’entraînement). Ils **diffèrent par la façon** d’apprendre cette relation :

| Modèle | En quoi il diffère des autres | Intérêt typique |
|--------|-------------------------------|-----------------|
| **Random Forest** | Nombreux arbres votent ; chaque arbre découpe l’espace des features en règles hiérarchiques. | Base **robuste** et lisible, bon compromis vitesse / qualité sur données tabulaires. |
| **XGBoost** | Les arbres sont ajoutés **séquentiellement** pour corriger les erreurs des précédents (*boosting*). | Souvent très performant sur données tabulaires ; référence fréquente en industrie. |
| **MLP** | Couches de neurones combinent les entrées de façon **dense** et non arborescente. | Peut capturer des motifs **lisses** ou globaux que les arbres découpent autrement. |

**Pourquoi en utiliser trois dans ce projet :** même jeu de features et même famille de problème, mais **biais d’apprentissage différents** → comparaison des comportements, des erreurs et de la robustesse ; cela colle à un objectif **pédagogique et MLOps** (plusieurs modèles versionnés, MLflow, MS5). En exploitation réelle on pourrait ne **déployer qu’un modèle principal** ; ici l’architecture permet **comparaison** ou **stratégie d’ensemble**.

**Isolation Forest et autoencoder (MS2)** ne remplacent pas les trois classifieurs : ils ciblent une question **d’anomalie** — un profil de tranche ou de métriques **atypique** par rapport au comportement « normal » observé à l’entraînement, sans se réduire à une étiquette supervisée du même type que MS1.

| Approche | Différence principale avec RF / XGB / MLP |
|----------|-------------------------------------------|
| **Isolation Forest** | Pas de cible classe-à-classe : on repère les points **isolés** / rares dans l’espace des features. |
| **Autoencoder** | Apprentissage de la **reconstruction** du normal ; l’anomalie se lit sur une **erreur de reconstruction** élevée. |

**Pourquoi les utiliser en plus de MS1 :** MS1 répond surtout à « **quelle prédiction de QoS / tranche selon le modèle supervisé ?** » ; MS2 répond à « **ce comportement est-il suspect ou rare ?** » — utile pour **qualité de service**, dérives ou scénarios **hors distribution**, alimentant le **NOC** (MS3).

**Analyse de conformité SLA** n’est pas un quatrième algorithme de même nature : elle **interprète** délais, pertes, congestion, etc. à la lumière de **seuils et références contractuelles** (SLA). Le ML **apprend des motifs dans les données** ; le volet SLA **juge** si les indicateurs **respectent les engagements** — les deux peuvent diverger (bon score modèle mais KPI contractuel non tenu, ou l’inverse selon les définitions).

**Pourquoi l’utiliser :** les opérateurs raisonnent en **contrats et pénalités**, pas seulement en score ML ; la conformité relie les sorties techniques aux **alertes**, aux **statistiques d’historique** (ex. taux de conformité) et au **pilotage**.

**Synthèse en une phrase :** **RF / XGB / MLP** = plusieurs façons de **prédire** la même cible supervisée ; **Isolation Forest + autoencoder** = façons de détecter l’**anormal** ; **SLA** = **couche métier / exploitation** qui vérifie si les résultats sont **acceptables au regard des accords de niveau de service**.

---

## Flux de données (simplifié)

1. **Entrée** : métriques réseau (perte, délai, type de tranche, etc.) via API ou formulaires UI.
2. **MS1 / MS2** : inférence ML → scores, labels, niveaux de risque.
3. **Persistance** : enregistrement en base pour historique et tableaux de bord.
4. **MS3** : agrégation pour l’affichage et les alertes (e-mail selon configuration SMTP).
5. **MS5 / scripts** : enregistrement ou versioning des modèles après réentraînement.
6. **Supervision** : health checks sur chaque service ; optionnellement métriques dans Elasticsearch / Kibana.

---

## Public visé

- **Étudiants** (ex. PIDATA 4DATA) : comprendre microservices, ML en production, Docker et CI.
- **Relecteurs techniques** : voir une architecture cohérente documentée (`Roadmap.md`, `INFRASTRUCTURE.md`, `EXPLICATION_CODE_PROJET.md`).
- **Démonstration** : lancer la stack, parcourir le workflow UI et les API documentées.

---

## Documentation à consulter ensuite

| Document | Contenu |
|----------|---------|
| `GUIDE_SIMPLE_PROJET.md` | Vue d’ensemble **simple** : chaque service, chaque dossier important, quoi lire ensuite. |
| `Roadmap.md` | Objectifs détaillés, architecture schématique, structure du dépôt. |
| `INFRASTRUCTURE.md` | Services Docker, ports, volumes, Nginx, commandes utiles. |
| `FILE_MANIFEST.md` | Inventaire des fichiers liés à l’infrastructure. |
| `EXPLICATION_CODE_PROJET.md` | Rôle de chaque module et interactions entre services. |
| `GUIDE_CI_MLOPS_ETUDIANT.md` | CI, image `ci`, Makefile, outils de qualité. |
| `WORKFLOW_TEST_GUIDE.md` | Parcours navigateur, jeux de données, tests end-to-end. |

---

**Contexte** : projet Esprit — PIDATA 4DATA (2025-2026), thème **5G network slicing** et analytique prédictive.  
**Auteur principal (référence Roadmap)** : Jihed Afli.
