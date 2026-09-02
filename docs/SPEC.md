# AI Build Intelligence — spécification définitive

> Document destiné à Claude Code.
> **Stack : Next.js / React / TypeScript (front) — Python / FastAPI / Pydantic / SQLAlchemy (back) — PostgreSQL + pgvector.**
> Les sections 0 à 5 priment sur toute interprétation ultérieure.

---

## 0. Principe directeur — à consulter en cas de doute d'arbitrage

> **Ne pas optimiser pour démontrer des technologies individuelles.**
> Ne pas construire « ma démo RAG », « ma démo d'agent », « mon calculateur PoB ».
> Construire **un produit unique où ces technologies sont nécessaires pour répondre correctement à la question de l'utilisateur.**

```
Natural language → Reasoning / tool selection → Structured retrieval
→ Knowledge retrieval → Deterministic computation → Comparison / ranking
→ Evidence / provenance → Natural-language answer
```

**Simple interface. Complex intelligence underneath.**

**Récit portfolio visé :**
> *I built an AI system that understands builds across multiple games by combining structured game data, deterministic game-specific calculation engines, versioned RAG knowledge, tool-calling agents, provenance, and natural-language interaction.*

---

## 1. Positionnement

**Ce n'est ni un chatbot de builds, ni une base de builds.** C'est un **Build Intelligence Engine dont le LLM est l'interface en langage naturel.**

> *Understand what makes a build work, how strong it really is, and what to change.*

L'utilisateur formule une demande ; le système fait le reste. Il ne doit jamais avoir à connaître l'existence du RAG, des agents, des outils, de PoB, des embeddings ou des pipelines.

---

## 2. Les trois couches d'intelligence

```
                    BUILD INTELLIGENCE
                           │
          ┌────────────────┼────────────────┐
     STRUCTURED         COMPUTATION       KNOWLEDGE
       DATA               ENGINE             RAG
     What is it?        How strong?      Why / how?
       Build DB        PoB / PoB2 / …     pgvector
```

**Données structurées** — objets, compétences, gemmes, arbres, classe, statistiques, configuration, version, patch, saison.

**Calcul déterministe** — DPS, vie effective, résistances, résultats dépendants de la configuration. **Spécifique au jeu.**

**RAG / connaissance** — patch notes officiels, mécaniques, sources publiques autorisées, interactions et synergies, contexte historique, raisons des changements de meta.

> **Le RAG est une couche d'intelligence centrale, jamais une fonctionnalité de chatbot ajoutée tardivement.**

---

## 3. Critical engineering principles

1. **Never invent numerical values.**
2. **Every displayed value needs provenance.**
3. **RAG is a core intelligence layer, not a generic chatbot feature.**
4. **Calculations are deterministic and game-specific.**
5. **LLM orchestrates; it does not become the source of truth.**
6. **Knowledge must be patch/version aware.**
7. **Knowledge must be game-aware — see § 6.**
8. **Build history must never be overwritten.**
9. **Unknown is a valid result.**
10. **Do not scrape commercial build-guide platforms such as Maxroll/Mobalytics.**
11. **Do not depend on undocumented/private APIs.**
12. **Do not assume public accessibility grants redistribution rights.**
13. **Do not add Redis/workers unless actual scale requires them.**
14. **The shared engine must contain no game-specific assumptions.**
15. **Never simulate a modified calculation with an LLM or an approximate formula.**

### Ce que le LLM peut et ne peut pas

**Peut** : comprendre la demande, choisir les outils, récupérer la connaissance, synthétiser, raisonner sur les sorties d'outils.

**Ne peut pas** : inventer des statistiques d'objet, des changements de patch, un DPS, une performance ; fabriquer une source ; prétendre à une vérification sans preuve.

Sans donnée fiable : **`unknown` / evidence insuffisante.** Jamais un nombre plausible.

### Provenance — concept de domaine de premier ordre

`observed` · `calculated` · `estimated` · `claimed`

```
91.4M DPS                          GR 150
→ calculated                       → observed
→ PoB version X                    → leaderboard evidence
→ build snapshot Y                 → season X
→ patch 3.27
```

`estimated` n'existe **que** si une méthodologie explicite et défendable existe. `claimed` est optionnel et ne doit **jamais** conditionner la découverte d'un build. **Le score de correspondance obéit à la même règle** : `calculated` par un scoreur déterministe aux pondérations exposées.

---

## 4. Ordre stratégique et matrice de faisabilité

```
PoE                    PoE2                   Diablo III
build complexe    →    jeu proche        →    modèle de données
+ calcul               réutilisation           fondamentalement
déterministe           d'architecture          différent
```

Chaque étape démontre une chose que les autres ne démontrent pas : **PoE prouve la profondeur, PoE2 prouve l'abstraction, D3 prouve l'automatisation.**

> **Statut de vérification.** Lignes ✔︎ vérifiées sur sources primaires. Lignes ≈ = appréciations, pas vérifications. Une spécification qui impose la provenance de chaque chiffre s'applique sa propre discipline.

| Critère | PoE | **PoE2** | Diablo III | WoW | Diablo IV | Last Epoch | FF XIV |
|---|---|---|---|---|---|---|---|
| ✔︎ Données publiques | Ladder ; builds d'autrui ❌ | Idem PoE | **Leaderboard + héros** | Talents ❌ depuis 11.2 | In-game seul | Communautaire | Aucune API |
| ✔︎ Risque CGU | Faible via codes partagés | Faible | Faible ; non commercial imposé | Faible | — | — | **Tiers interdits** |
| ≈ Richesse de build | **Très élevée** | **Très élevée** | Moyenne | Élevée | Moyenne | Élevée | Faible |
| ✔︎ Moteur déterministe | **`pobapi` + PoB headless** | **PoB2 via `pob2-mcp` / `pob-mcp`** | Inutile (perf observée) | Aucun | Aucun | Aucun | Aucun |
| ✔︎ Données de performance | Ladder, indirect | Ladder, indirect | **GR `observed` direct** | M+ observés | Partiel | Communautaire | Aucun |
| ✔︎ Patch / version | Riches | Riches | Officiels | Officiels | Officiels | Officiels | Officiels |
| ≈ Assets et structures | **Arbre = pièce maîtresse** | **Arbre** | Sets, plus plat | Talents | Moyen | Arbres | Faible |
| ≈ Connaissance pour RAG | **Très abondante** | Plus jeune, moins fournie | Abondante, stabilisée | Abondante | Moyenne | Moyenne | Moyenne |
| ✔︎ Automatisation | Corpus par codes publics | Corpus par codes publics | **Ingestion ladder complète** | Bloquée | Impossible | Impossible | Impossible |
| ≈ Complexité | Élevée | Élevée, **formats instables** | Modérée | Modérée | — | — | — |
| **Verdict** | ✅ **Phase 1** | ✅ **Phase 2** | ✅ **Phase 3** | ❌ | ❌ | ❌ | ❌ |

**Réserve PoE2 assumée :** jeu plus jeune, formats plus mouvants, outillage communautaire moins mûr, corpus plus petit. À gérer par le versionnage, pas à découvrir en route.

**Contraintes permanentes.** Données Blizzard : ni vendues, ni concédées, ni transférées, ni marketing. Assets sous droits : rien de redistribué dans le dépôt, rendu dégradé prévu.

---

## 5. Moteurs de calcul — distinction structurante

**Faisabilité vérifiée, ne pas repasser de temps à la re-prouver.** `pobapi` (Python) pour PoE ; exécution headless via le pont JSON `api-stdio` ; `pob-mcp` et Savecraft en production ; `pob2-mcp` pour PoE2.

L'architecture doit **explicitement distinguer deux capacités de difficulté très différente** :

### A. Analyser un build existant
```
Build code → Parse → Normalized Build → Read existing calculated values
```
Problème de parsing et d'intégration.

### B. Recalculer un build modifié
```
Existing Build → Apply modifications → Generate modified engine state
→ Headless engine → Recalculate → New calculated values
```
Substantiellement plus complexe. **Requis pour :**
> « Remove these nodes and add these seven. This gives +18% damage. »

**Règles :**
- La phase initiale peut se contenter de A.
- Toute fonctionnalité annonçant un résultat calculé **après modification** passe par le vrai pipeline headless.
- **Ne jamais simuler un résultat modifié avec un LLM ou une formule approximative.**
- **Valider la boucle complète lecture → modification → recalcul avant de promettre l'optimisation automatique.**

---

## 6. RAG game-aware — le point technique le plus fin du projet

**PoE et PoE2 partagent massivement leur vocabulaire** : mêmes noms de compétences, mêmes noms d'objets, mécaniques différentes. Une question PoE2 qui remonte un passage PoE1 produit une réponse **plausible et fausse** — précisément ce que la discipline de provenance vise à empêcher.

> **Le filtrage par métadonnées de jeu n'est pas une option d'hygiène, c'est une condition de correction.**

Métadonnées obligatoires sur chaque chunk :
```
game · version · patch · season/league · class · source · published_at · retrieved_at
```

**Éval concrète et démontrable :** poser une question PoE2, vérifier qu'**aucun** passage PoE1 n'a été récupéré — et réciproquement. Test automatisable, à mettre en CI. C'est un des meilleurs artefacts du projet.

---

## 7. Corpus de builds — obligatoire, indépendant des utilisateurs

`search_builds()` suppose un corpus interrogeable. Importer un build n'en crée pas un.

| Besoin | Ressource |
|---|---|
| « Analyze my PoB » | Un seul build — collage utilisateur |
| « Find me the best build under 20 divines » | **Corpus** |

**Le corpus ne doit pas dépendre des soumissions utilisateur.** Le collage d'un code est une fonctionnalité distincte et optionnelle.

**Ingestion source-agnostique**, identique pour PoE et PoE2 :
```
Permitted public source → Fetcher → Parser → Build extraction
→ Normalization → Validation → Version / patch tagging → Build corpus
```

Source initiale : **codes publiés volontairement sur les forums officiels.**

### Règles d'ingestion — juridiques et techniques

L'accessibilité publique **n'implique pas** le droit de copier et rediffuser. L'ingestion doit : respecter les conditions de la source ; respecter `robots.txt` et les limites de débit ; conserver l'attribution ; stocker les URL sources ; **éviter de copier de la prose sous droits non nécessaire** ; ne jamais scraper Maxroll ou Mobalytics ; ne jamais dépendre d'API non documentées ou privées.

> **Le système stocke la représentation structurée du build et sa provenance — il ne reproduit pas des guides tiers.**
> **Une source qui ne peut être ingérée légalement ou techniquement à l'échelle ne doit pas devenir une dépendance dure.**

---

## 8. Architecture

```
                    USER → Natural Language → LLM / Agent
                                   │
              ┌────────────────────┼────────────────────┐
         Build Search          Knowledge            Calculations
           Build DB            pgvector          PoB / PoB2 / D3
              └────────────────────┼────────────────────┘
                          Build Intelligence
                                   ▼
                            LLM synthesis → USER ANSWER
```

```
                    BUILD INTELLIGENCE ENGINE
                              │
                 ┌────────────┼────────────┐
                PoE          PoE2        Diablo III
                 │            │            │
                PoB          PoB2       D3-specific
                 └────────────┼────────────┘
                     Common intelligence
                   RAG + Agent + Provenance
```

### Répartition adaptateur / socle commun

| L'adaptateur possède | Le socle commun possède |
|---|---|
| Parsing de build | `Build`, `BuildSnapshot`, `BuildVariant` |
| Compétences, objets | `Evidence`, `Provenance` |
| Structures d'arbre | `Patch`, `Knowledge` |
| Gestion version / patch | Récupération de connaissance |
| Intégration du calcul | Orchestration agent / outils |
| Validation de build | Comparaison de builds |
| Métriques de performance | Scoring déterministe |
| Mécaniques spécifiques | Interface en langage naturel |

```
backend/app/games/
    poe/
    poe2/
    diablo3/
```

### Critère de validation de l'abstraction — mesurable

> **Ajouter PoE2 ne doit toucher que `games/poe2/` et la configuration, sans modifier une ligne du domaine commun.**
> Le volume de code nouveau est la mesure. **Si ajouter PoE2 exige de dupliquer l'essentiel du système, l'architecture est trop PoE-spécifique** — et il faut la corriger avant d'aller plus loin, pas après.

C'est un excellent chiffre de README.

---

## 9. Phases

### Phase 1 — Tranche verticale PoE
Import PoB · build normalisé · **corpus de builds** · calculs · arbre passif · connaissance versionnée · RAG · agent et tool-calling · UX en langage naturel · modification de build avec **recalcul réel**.

Outils exposés au modèle :
```
search_builds()   get_build()      get_patch_changes()   get_performance()
calculate_build() compare_builds() get_item()            get_skill()
get_tree()        search_knowledge()
```

L'utilisateur ne choisit **jamais** un outil.
```
"I already have Mageblood. Find me a tanky Lightning Strike build
 for mapping and bosses, under 20 divines excluding the Mageblood."
   ↓ Extract constraints → Search corpus → Retrieve knowledge
   → Calculate candidates → Compare → Rank deterministically → Explain
```
Dix opérations internes, **une seule interaction perçue.**

### Phase 2 — Adaptateur PoE2
Réutiliser le moteur existant. Ajouter : parsing et import PoE2, corpus PoE2, données de jeu, représentation d'arbre, intégration du calcul PoB2, connaissance patch/version, RAG PoE2, outils spécifiques.

**Expérience utilisateur strictement identique.** *« Find me a tanky PoE2 build for mapping and bosses under my budget »* déclenche la même chaîne — l'utilisateur ignore si le système a utilisé PoB, PoB2, le RAG ou dix étapes internes.

### Phase 3 — Adaptateur Diablo III
Modèle de données fondamentalement différent : **ingestion automatique du ladder**, performance `observed`, clustering automatique en archétypes, découverte de builds à partir des populations de joueurs, métriques natives du jeu.

*Réserves D3 :* jointure leaderboard → héros documentée comme problématique ; les données du héros reflètent son **état actuel**, pas son état au moment de la course — à horodater et afficher comme incertitude.

---

## 10. UX — tout le technique est invisible

Ne jamais exposer « RAG », « agent », « tool call », « embedding », « vector search », « PoB pipeline ».

```
User: "I want a fast mapper that can also kill bosses,
       under 20 divines and max 5 buttons."
        ↓
Best match — Lightning Strike Champion          94% match
91.4M DPS · 82k effective HP · ~18 divines      calculated · PoB X
Mapping: Excellent · Bossing: Excellent · Complexity: Low
Why this build? [explication courte]
[View build] [Analyze] [Compare]
```

**La complexité appartient à l'architecture, pas au modèle mental de l'utilisateur.**

---

## 11. Direction et identité visuelle

Ni air généré par IA, ni landing page SaaS générique. Un outil sophistiqué d'analyse et d'intelligence de jeu.

> **Game data terminal + premium build planner + technical intelligence interface.**

**À éviter** : sections héros SaaS ; **dégradés violets « IA »** ; langage visuel shadcn brut ; cartes trop arrondies ; typographie marketing surdimensionnée ; Inter, Roboto, polices système ; graphismes IA décoratifs ; blanc excessif ; interface pilotée par emojis.

**Recherché** : interface **dense mais lisible**, communiquant données, confiance, version, patch, performance, relations et preuves. Hiérarchie forte sur les chiffres, **traitement monospace**.

**La provenance fait partie du langage visuel et du résultat lui-même — jamais reléguée dans une page « sources ».**
```
91.4M DPS              Patch 3.27           n=412 builds
calculated · PoB X     verified 2h ago      observed
```

**Animation intentionnelle** : transitions de classement, de recalcul, changements de build, **diffs d'arbre**, rendu progressif. **Ressorts plutôt que fondus.** Respecter `prefers-reduced-motion`.

**Chaque état majeur dessiné** : chargement, aucun résultat, evidence insuffisante, données périmées, échec de calcul, corpus vide, code invalide, source indisponible.

**Ne pas faire générer le design.**

---

## 12. Infrastructure

```
Next.js · FastAPI · PostgreSQL + pgvector · moteurs headless · cron / scripts
```

**Pas de Redis, pas de Celery** tant que la charge réelle ne le justifie pas. Le domaine reste indépendant de tout framework IA — LangGraph, LlamaIndex ou LangChain peuvent servir ponctuellement, **jamais devenir l'architecture**.

---

## 13. Vérification

1. **Chaîne de provenance** — pour toute valeur affichée, remonter source, statut, moteur, version. Un `float` nu exposé est un échec.
2. **Chemin `unknown`** — une métrique sans provenance valide s'affiche comme inconnue.
3. **Isolation entre jeux** — une question PoE2 ne récupère aucun passage PoE1, et réciproquement. **Automatisé en CI.**
4. **Boucle de recalcul** — une modification d'arbre produit un résultat issu du vrai moteur, rejouable.
5. **Conscience du patch** — un build de 3.26 interrogé sous 3.27 mentionne les changements intervenus.
6. **Cohérence du raffinement** — « make it tankier », « I already own Mageblood » modifient le classement de façon explicable.
7. **Coût d'ajout d'un jeu** — l'adaptateur PoE2 ne modifie pas le domaine commun. Mesuré et publié.
8. **Cas dégradés** — code invalide, classe non couverte, moteur indisponible, corpus vide, source injoignable.
9. **Jugement expert** — cinq intentions confrontées à ce que recommanderait un joueur expérimenté.
10. Lighthouse, responsive, dark mode, navigation clavier.

---

## 14. Risques

- **Le recalcul (§ 5 B) est le risque technique principal.** Prototyper tôt ; il conditionne la fonctionnalité la plus visible.
- **La contamination croisée PoE / PoE2 est le risque de correction principal.** Vocabulaire partagé, mécaniques différentes : une réponse fausse y sera parfaitement plausible.
- **Le corpus conditionne la recherche de builds.** Sans ingestion des codes publics, `search_builds()` n'a rien à interroger.
- **PoE2 est plus jeune** : formats mouvants, corpus plus petit, outillage moins mûr.
- **Aucune source ne doit devenir une dépendance dure** si elle ne peut être ingérée légalement ou techniquement à l'échelle.
- **La fraîcheur est critique** : une meta périmée présentée comme actuelle est immédiatement visible par n'importe quel joueur.
- **Le périmètre est large.** La Phase 1 forme déjà un artefact complet et démontrable ; les Phases 2 et 3 sont des incréments, pas des prérequis.

---

## 15. Première action concrète

Avant toute modélisation : **installer `pobapi`, parser un code PoB réel, afficher DPS et vie.** Une soirée. Ce point de départ valide la brique la plus structurante et transforme la spécification en code.

---

# Annexe — Comment on est arrivé ici

> Quatorze pistes ont été explorées et écartées avant celle-ci. Cette annexe existe pour deux raisons : ne pas rouvrir un débat déjà tranché dans trois semaines, et documenter les critères qui ont émergé — ils restent valables pour juger toute évolution du projet.

## A.1 Les pistes écartées

| # | Piste | Cause d'élimination | Vérifié ? |
|---|---|---|---|
| 1 | **RenovScope** — dashboard open data sur une adresse française | Usage ponctuel, aucune récurrence | — |
| 2 | **Overlap** — éligibilité réelle des offres remote | Himalayas expose déjà `locationRestrictions` et `timezoneRestrictions`, gratuitement | ✅ API |
| 3 | **Spoilerline** — récupération bornée par la progression (manga/anime) | MAL et AniList possèdent l'habitude ; sur une œuvre ancienne la garantie ne tient pas, le modèle spoile depuis sa mémoire paramétrique | — |
| 4 | **Waypoint** — compagnon de progression JRPG | Même faille : jeu trop connu, RAG décoratif car le modèle connaît déjà le corpus | — |
| 5 | **Scry** — capture d'écran de jeu → interface générée | **Une capture de jeu est déjà une interface** ; la régénérer n'ajoute rien. Friction capture → transfert → téléversement disproportionnée | — |
| 6 | **Consensus d'avis Steam** | Fréquence trop faible, douleur trop faible | — |
| 7 | **Visas Thaïlande** — veille réglementaire citée | THIM, l'app officielle, couvre déjà rapport 90 jours, e-Extension, documents | ✅ roadmap |
| 8 | **Migration de dépendances** — agent ouvrant des PR | GitHub a livré l'assignation des alertes Dependabot à des agents IA ; Hypermod et Codemod.com occupent le reste | ✅ |
| 9 | **Assistant doc versionné pour devs** | Context7 est déjà branché dans Claude Code et consorts | ✅ |
| 10 | **Chatbot juridique / administratif FR** | Juribot, Justiweb, Legiia, OpenLegi, comprendre-mes-droits, chatlegalia — et Légifrance a intégré une recherche sémantique en 2025 | ✅ |
| 11 | **Copropriété** | ANIL et ADIL : gratuit, officiel, financé par l'État, permanences départementales | ✅ |
| 12 | **Relevé de chantier manuscrit** (BTP) | Recoupe le chatbot Obat en développement | — |
| 13 | **Capture de tableau blanc physique** | Miro Stickies Capture fait déjà photo → post-it éditables + OCR manuscrit | ✅ |
| 14 | **Suivi nutritionnel conversationnel** | MacroFactor fait déjà la saisie en langage naturel **et** la calibration adaptative par courbe de poids | ✅ |
| 15 | **Handhelds** — preuves vidéo horodatées | Créneau réellement libre, mais corpus vidéo lourd et ToS grise ; rien à accumuler | ✅ comparateurs |
| 16 | **Accessibilité / RGAA / EAA** | Écarté volontairement : encombrement juridique (sanctions, mises en demeure) | ✅ |
| 17 | **Café de spécialité** | Meilleur candidat « accumulation », mais écarté par préférence | — |
| 18 | **Litige loyer / résiliation d'abonnements** | Douleur réelle sans leader, mais problème de calcul et non d'IA ; fréquence quasi nulle | ✅ |

## A.2 Le constat central

**Tout besoin réel, fréquent et solvable est déjà servi en 2026, souvent gratuitement.** Cinq pistes sont mortes face à un acteur *financé* (Himalayas, Bureau de l'Immigration thaïlandaise, GitHub, Miro, MacroFactor) — ce n'est pas de la malchance, c'est une régularité économique.

Corollaire : les trois critères **utile + récurrent + inoccupé** sont mutuellement incompatibles pour un projet solo. Il faut en relâcher un. **Ici, c'est « inoccupé »** — Mobalytics et Maxroll existent, et le projet ne prétend pas les remplacer.

## A.3 Les critères qui ont émergé, et qui restent applicables

**L'entrée ne doit pas déjà être une interface.** Photographier un écran pour en régénérer un autre n'apporte rien (piste 5).

**Le RAG n'est justifié que si le corpus échappe au modèle** — trop volumineux, trop granulaire, ou trop récent pour être mémorisé, *et* mal atteignable par une recherche web. Un corpus public bien indexé est déjà couvert par un modèle généraliste (pistes 9, 10). Ici, la fraîcheur par patch et la granularité des builds satisfont ce critère.

**Le calcul ne doit jamais venir du modèle.** C'est ce qui a fait basculer le projet d'un « chatbot de builds » vers un moteur déterministe avec provenance (§ 3).

**Les listes publiques de besoins non satisfaits sont un mauvais terrain de chasse** — Ask HN, r/SomebodyMakeThis. Toute idée valable y reçoit une réponse « ça existe déjà » dans l'heure ; celles qui n'en reçoivent pas sont non satisfaites parce que trop étroites. Vérifié sur deux fils : une douzaine d'idées, zéro exploitable.

**Les quatre faiblesses de Google Lens**, réutilisables comme grille de différenciation face à tout assistant généraliste : large et superficiel ; rend des liens plutôt qu'une interface composée ; cherche dans tout le web plutôt qu'un corpus curé et cité ; **et n'a aucune mémoire**.

## A.4 Le pivot méthodologique

Après onze tours de « chercher un problème puis y coller de l'IA », la recherche a été **inversée** : partir de la technique à démontrer, le domaine devenant un prétexte choisi pour être beau, tenable et légalement praticable. C'est ce retournement qui a produit le projet actuel — et c'est pourquoi le § 0 dit que la valeur vient de l'intégration, pas de la nouveauté du sujet.
