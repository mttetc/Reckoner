# PoB fixtures

| File | Origin | Licence | Notes |
|---|---|---|---|
| `elementalist_bv_2019.txt` | `data/import_code.txt` from ppoelzl/PathOfBuildingAPI (also pastebin `bQRjfedq`) | MIT | Witch Elementalist, Blade Vortex, PoB 1.4-era export: no `treeVersion`, tree only as `<URL>` |
| `scion_import_lvl1_2019.txt` | `data/test_code.txt` from ppoelzl/PathOfBuildingAPI | MIT | Scion level 1, `treeVersion=3_8`, negative DPS (import artefact) |
| `slayer_lightning_strike_3_27.txt` | https://pobb.in/pDpVti8TKiH0 (public paste, raw endpoint) | Public PoB code, attribution kept via URL | Duelist Slayer, Crit Lightning Strike, `treeVersion=3_27`, modern `SkillSet` / `ItemSet` / `ConfigSet` layout |
| `void_sphere_pathfinder_3_29.txt` | https://pobb.in/Y4GeYw6xilVx, linked from official forum thread 3498215 | Public PoB code, attribution kept via URL | Ranger Pathfinder. Five `SkillSet`s with `activeSkillSet=2`; the export's selected socket group is Withering Step so `TotalDPS=0` while `FullDPS` is 19.4M with a four-row `<FullDPSSkill>` breakdown |
| `srs_guardian_3_23.txt` | https://pobb.in/AxRqm73W_VRm, linked from official forum thread 3971163 | Public PoB code, attribution kept via URL | Templar Guardian, Summon Raging Spirit. Carries `<MinionStat>` rows (minion DPS and life); player `TotalDPS=0` |
| `ballista_chieftain_3_29.txt` | https://pobb.in/r1KlFvPpXi5H, linked from official forum thread 3998264 | Public PoB code, attribution kept via URL | Marauder Chieftain, Artillery Ballista. Export has **no** `TotalDPS` row at all; socket groups with `mainActiveSkill="nil"`, item-granted groups (`source="Item:…"`) and an `Explode` group |

Fixtures are the structured build representation only (a PoB export code), never third-party guide
prose. Codes linked from the official forum are used as parser inputs; the threads themselves are not
reproduced.
