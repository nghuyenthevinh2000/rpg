import unittest
from pathlib import Path

from engine.contracts import WorldContract

# Polyfill / helper if WorldContract.load is invoked as classmethod
if not hasattr(WorldContract, "load"):
    setattr(WorldContract, "load", classmethod(lambda cls, path: cls(Path(__file__).resolve().parents[1] / path if not Path(path).is_absolute() else path, load_hooks=False)))


class CovenantBrokenContractTests(unittest.TestCase):
    def test_covenant_broken_contract_loads(self):
        contract = WorldContract.load("world/covenant-broken")
        self.assertEqual(contract.config["world_id"], "covenant-broken")
        self.assertEqual(contract.config["contract_version"], 1)
        self.assertEqual(contract.config["state_schema_version"], 1)
        self.assertEqual(contract.config["player_character_id"], "player_elias")
        self.assertIn("characters", contract.schemas)
        self.assertIn("threats", contract.schemas)
        self.assertIn("resources", contract.schemas)
        self.assertIn("actions", contract.schemas)
        self.assertIn("groups", contract.schemas)
        self.assertIn("baseline", contract.schemas)
        self.assertIn("rules", contract.definitions)
        rules = contract.definitions["rules"]
        self.assertIn("calendar", rules)
        self.assertEqual(rules["calendar"]["anchor_turn"], 1)
        self.assertEqual(rules["calendar"]["anchor_day"], 1)
        self.assertEqual(rules["calendar"]["anchor_timestamp"], "Post-War Year 14, Dawn")
        self.assertEqual(rules["calendar"]["turns_per_day"], 4)
        self.assertEqual(rules["calendar"]["display_style"], "hours")
        self.assertEqual(
            rules["stat_keys"],
            ["agency", "clarity", "dissonance", "neural_strain", "biological_vitality", "salvage_integrity"],
        )
        for stat in ["agency", "clarity", "dissonance", "neural_strain", "biological_vitality"]:
            self.assertEqual(rules["bounds"][stat], [0, 100])

    def test_covenant_broken_world_topology(self):
        contract = WorldContract.load("world/covenant-broken")
        self.assertIn("world", contract.definitions)
        world_def = contract.definitions["world"]

        self.assertEqual(world_def.get("name"), "The Broken Covenant")
        self.assertEqual(world_def.get("theme"), "Cyber-Transhumanist Post-Robot War Ruin")
        self.assertIn("Silent Sundering", world_def.get("lore", ""))

        grid = world_def.get("grid", {})
        self.assertEqual(grid.get("rows"), 5)
        self.assertEqual(grid.get("cols"), 5)

        locations = world_def.get("locations", [])
        loc_map = {loc["id"]: loc for loc in locations}

        required_locs = {
            "loc_scrap_hollow": (3, 3),
            "loc_glass_crags": (2, 1),
            "loc_consensus_spire": (1, 4),
            "loc_ashen_cradle": (5, 2),
            "loc_chimera_foundry": (4, 5),
            "loc_resonant_void": (3, 5),
        }

        for loc_id, (row, col) in required_locs.items():
            self.assertIn(loc_id, loc_map, f"Missing required location: {loc_id}")
            coord = loc_map[loc_id]["coordinate"]
            self.assertEqual(coord["row"], row, f"Row mismatch for {loc_id}")
            self.assertEqual(coord["col"], col, f"Col mismatch for {loc_id}")

        self.assertTrue(loc_map["loc_scrap_hollow"].get("safe_zone"), "loc_scrap_hollow should be a safe zone")

        for loc in locations:
            self.assertIn("ambient_tension", loc, f"Missing ambient_tension in {loc['id']}")
            self.assertIn("description", loc, f"Missing description in {loc['id']}")
            self.assertIn("connected_to", loc, f"Missing connected_to in {loc['id']}")
            for neighbor_id in loc["connected_to"]:
                self.assertIn(neighbor_id, loc_map, f"Unknown neighbor {neighbor_id} referenced in {loc['id']}")

        # Verify full graph connectivity across all locations using BFS/DFS
        start_id = locations[0]["id"]
        visited = set()
        queue = [start_id]
        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            for neighbor in loc_map[curr]["connected_to"]:
                if neighbor not in visited:
                    queue.append(neighbor)
        self.assertEqual(visited, set(loc_map.keys()), "Location graph must be fully connected")

    def test_covenant_broken_action_conditions(self):
        contract = WorldContract.load("world/covenant-broken")
        self.assertIn("actions", contract.definitions)
        actions_def = contract.definitions["actions"]

        self.assertIn("action_templates", actions_def)
        templates = actions_def["action_templates"]

        required_actions = [
            "action_scavenge_relay_core",
            "action_emp_purge_terminal",
            "action_harmonic_broadcast_sync",
            "action_synthesize_organ_graft",
            "action_observe_unaligned_path",
        ]

        for action_id in required_actions:
            self.assertIn(action_id, templates, f"Missing action template: {action_id}")
            template = templates[action_id]
            self.assertIn("name", template)
            self.assertIn("trade_offs", template)

    def test_covenant_broken_game_master(self):
        contract = WorldContract.load("world/covenant-broken")
        self.assertIn("gm", contract.definitions)
        gm_def = contract.definitions["gm"]

        self.assertIn("disaster_pool", gm_def)
        disasters = gm_def["disaster_pool"]
        self.assertGreaterEqual(len(disasters), 6)

        disaster_ids = {d["id"] for d in disasters}
        expected_disaster_types = [
            "feral_combat_drones",
            "rogue_logic_storm",
            "emp_squall",
            "silicon_fallout",
            "purifier_inquisition",
            "consensus_sweep",
        ]
        for expected in expected_disaster_types:
            self.assertTrue(any(expected in d_id for d_id in disaster_ids), f"Missing disaster of type {expected}")

        for d in disasters:
            for field in ["id", "name", "type", "severity", "description", "tags", "consequences"]:
                self.assertIn(field, d, f"Missing field {field} in disaster {d.get('id')}")

        self.assertIn("improvisation_templates", gm_def)

    def test_covenant_broken_traits(self):
        contract = WorldContract.load("world/covenant-broken")
        self.assertIn("traits", contract.definitions)
        traits_def = contract.definitions["traits"]
        traits = traits_def.get("traits", {})

        required_traits = [
            "trait_unaligned_observer",
            "trait_consensus_tether",
            "trait_purifier_fervor",
            "trait_chimera_graft",
            "trait_severed_phantom",
            "trait_genomic_custodian",
        ]

        for trait_id in required_traits:
            self.assertIn(trait_id, traits, f"Missing trait: {trait_id}")
            trait = traits[trait_id]
            self.assertIn("name", trait)
            self.assertIn("effect", trait)

    def test_covenant_broken_equipments(self):
        contract = WorldContract.load("world/covenant-broken")
        self.assertIn("equipment", contract.definitions)
        equip_def = contract.definitions["equipment"]
        items = equip_def.get("items", {})

        required_items = [
            "item_emp_lance",
            "item_scavenged_rail_pistol",
            "item_arc_welder_blade",
            "item_harmonic_stunner",
            "item_lead_lined_trenchcoat",
            "item_consensus_mesh_armor",
            "item_reinforced_chitin_harness",
            "item_unaligned_diagnostic_pad",
            "item_dormant_core_shard",
            "item_genome_cryo_flask",
        ]

        for item_id in required_items:
            self.assertIn(item_id, items, f"Missing equipment item: {item_id}")
            item = items[item_id]
            self.assertIn("name", item)
            self.assertIn("category", item)
            self.assertIn("description", item)


    def test_covenant_broken_logic_derive_and_audit(self):
        contract = WorldContract(Path(__file__).resolve().parents[1] / "world/covenant-broken", load_hooks=True)
        from engine.contracts import RuleContext, StateView
        import random

        state = {
            "characters": {
                "player_elias": {
                    "id": "player_elias",
                    "revision": 0,
                    "schema_version": 1,
                    "data": {
                        "name": "Elias Thorne",
                        "location_id": "loc_scrap_hollow",
                        "status": "alive",
                        "health": 75,
                        "stats": {
                            "agency": 60,
                            "clarity": 55,
                            "dissonance": 20,
                            "neural_strain": 15,
                            "biological_vitality": 75,
                        },
                        "capabilities": {"cannot_die": False},
                        "traits": ["trait_unaligned_observer"],
                        "equipment": ["item_emp_lance"],
                        "inventory": [],
                        "baseline": {
                            "stats": {
                                "agency": 60,
                                "clarity": 55,
                                "dissonance": 20,
                                "neural_strain": 15,
                                "biological_vitality": 75,
                            },
                            "modifiers": {},
                        },
                        "metadata": {},
                    },
                }
            },
            "resources": {},
            "threats": {},
            "clock": {
                "id": "clock",
                "revision": 0,
                "schema_version": 1,
                "data": {"turn": 1, "day": 1, "display_timestamp": "Post-War Year 14, Dawn"},
            },
        }

        ctx = RuleContext(StateView(state), contract.definition_view, random.Random(0), 1)
        derived = contract.derive(ctx, "characters/player_elias")
        self.assertIn("stats", derived)
        self.assertIn("audit", derived)
        audit = derived["audit"]
        self.assertIn("static", audit)
        self.assertIn("baseline_modifiers", audit)
        self.assertIn("current_modifiers", audit)
        self.assertIn("effective_values", audit)
        self.assertIn("bounds_exceptions", audit)
        # Check trait_unaligned_observer (+15 agency, +10 clarity, -10 dissonance) and item_emp_lance (+5 agency, +5 clarity)
        # Total agency: 60 + 15 + 5 = 80
        # Total clarity: 55 + 10 + 5 = 70
        # Total dissonance: 20 - 10 = 10
        self.assertEqual(derived["stats"]["agency"], 80)
        self.assertEqual(derived["stats"]["clarity"], 70)
        self.assertEqual(derived["stats"]["dissonance"], 10)
        self.assertEqual(derived["health"], 75)
        self.assertIn("punch_kinetic_impact", derived)

    def test_covenant_broken_logic_validate(self):
        contract = WorldContract(Path(__file__).resolve().parents[1] / "world/covenant-broken", load_hooks=True)
        from engine.contracts import RuleContext, StateView
        import random

        # Valid state should produce no violations
        valid_state = {
            "characters": {
                "player_elias": {
                    "id": "player_elias",
                    "revision": 0,
                    "schema_version": 1,
                    "data": {
                        "name": "Elias Thorne",
                        "location_id": "loc_scrap_hollow",
                        "status": "alive",
                        "health": 75,
                        "stats": {
                            "agency": 60,
                            "clarity": 55,
                            "dissonance": 20,
                            "neural_strain": 15,
                            "biological_vitality": 75,
                        },
                        "capabilities": {"cannot_die": False},
                        "traits": ["trait_unaligned_observer"],
                        "equipment": ["item_emp_lance"],
                        "inventory": [],
                        "baseline": {
                            "stats": {
                                "agency": 60,
                                "clarity": 55,
                                "dissonance": 20,
                                "neural_strain": 15,
                                "biological_vitality": 75,
                            },
                            "modifiers": {},
                        },
                        "metadata": {},
                    },
                }
            },
            "resources": {},
            "threats": {},
            "clock": {
                "id": "clock",
                "revision": 0,
                "schema_version": 1,
                "data": {"turn": 1, "day": 1, "display_timestamp": "Post-War Year 14, Dawn"},
            },
        }
        ctx_valid = RuleContext(StateView(valid_state), contract.definition_view, random.Random(0), 1)
        violations = contract.validate(ctx_valid)
        self.assertEqual(violations, [])

        # Invalid state with dead character with health > 0 and invalid location
        invalid_state = {
            "characters": {
                "player_elias": {
                    "id": "player_elias",
                    "revision": 0,
                    "schema_version": 1,
                    "data": {
                        "name": "Elias Thorne",
                        "location_id": "loc_nonexistent",
                        "status": "dead",
                        "health": 75,
                        "stats": {
                            "agency": 60,
                            "clarity": 55,
                            "dissonance": 20,
                            "neural_strain": 15,
                            "biological_vitality": 75,
                        },
                        "capabilities": {"cannot_die": False},
                        "traits": ["unknown_trait"],
                        "equipment": [],
                        "inventory": [],
                        "baseline": {
                            "stats": {
                                "agency": 60,
                                "clarity": 55,
                                "dissonance": 20,
                                "neural_strain": 15,
                                "biological_vitality": 75,
                            },
                            "modifiers": {},
                        },
                        "metadata": {},
                    },
                }
            },
            "resources": {},
            "threats": {},
            "clock": {
                "id": "clock",
                "revision": 0,
                "schema_version": 1,
                "data": {"turn": 1, "day": 1, "display_timestamp": "Post-War Year 14, Dawn"},
            },
        }
        ctx_invalid = RuleContext(StateView(invalid_state), contract.definition_view, random.Random(0), 1)
        violations = contract.validate(ctx_invalid)
        self.assertTrue(len(violations) > 0)
        codes = {v.get("code") for v in violations}
        self.assertIn("mortality", codes)
        self.assertIn("broken_character_reference", codes)

    def test_covenant_broken_logic_resolve_move_and_dilemma(self):
        contract = WorldContract(Path(__file__).resolve().parents[1] / "world/covenant-broken", load_hooks=True)
        from engine.contracts import RuleContext, StateView
        import random

        state = {
            "characters": {
                "player_elias": {
                    "id": "player_elias",
                    "revision": 0,
                    "schema_version": 1,
                    "data": {
                        "name": "Elias Thorne",
                        "location_id": "loc_scrap_hollow",
                        "status": "alive",
                        "health": 75,
                        "stats": {
                            "agency": 60,
                            "clarity": 55,
                            "dissonance": 20,
                            "neural_strain": 15,
                            "biological_vitality": 75,
                        },
                        "capabilities": {"cannot_die": False},
                        "traits": ["trait_unaligned_observer"],
                        "equipment": ["item_emp_lance"],
                        "inventory": [],
                        "baseline": {
                            "stats": {
                                "agency": 60,
                                "clarity": 55,
                                "dissonance": 20,
                                "neural_strain": 15,
                                "biological_vitality": 75,
                            },
                            "modifiers": {},
                        },
                        "metadata": {},
                    },
                }
            },
            "resources": {},
            "threats": {},
            "clock": {
                "id": "clock",
                "revision": 0,
                "schema_version": 1,
                "data": {"turn": 1, "day": 1, "display_timestamp": "Post-War Year 14, Dawn"},
            },
        }
        ctx = RuleContext(StateView(state), contract.definition_view, random.Random(0), 1)

        # 1. Resolve move to connected location (loc_glass_crags is connected to loc_scrap_hollow)
        move_event = {
            "schema_version": 1,
            "event_id": "event_move_01",
            "world_id": "covenant-broken",
            "expected_turn": 1,
            "action": {
                "type": "move",
                "actor_id": "player_elias",
                "location_id": "loc_glass_crags",
            },
        }
        res = contract.resolve(ctx, move_event)
        self.assertEqual(len(res.effects), 1)
        self.assertEqual(res.effects[0]["op"], "set")
        self.assertEqual(res.effects[0]["path"], "/location_id")
        self.assertEqual(res.effects[0]["value"], "loc_glass_crags")

        # 2. Resolve dilemma action: action_observe_unaligned_path
        observe_event = {
            "schema_version": 1,
            "event_id": "event_observe_01",
            "world_id": "covenant-broken",
            "expected_turn": 1,
            "action": {
                "type": "action_observe_unaligned_path",
                "actor_id": "player_elias",
            },
        }
        res_observe = contract.resolve(ctx, observe_event)
        self.assertTrue(len(res_observe.effects) > 0)
        self.assertEqual(res_observe.outcomes.get("action_type"), "action_observe_unaligned_path")

    def test_covenant_broken_logic_introduce_threat_and_after_turn(self):
        contract = WorldContract(Path(__file__).resolve().parents[1] / "world/covenant-broken", load_hooks=True)
        from engine.contracts import RuleContext, StateView
        import random

        state = {
            "characters": {
                "player_elias": {
                    "id": "player_elias",
                    "revision": 0,
                    "schema_version": 1,
                    "data": {
                        "name": "Elias Thorne",
                        "location_id": "loc_scrap_hollow",
                        "status": "alive",
                        "health": 75,
                        "stats": {
                            "agency": 60,
                            "clarity": 55,
                            "dissonance": 20,
                            "neural_strain": 15,
                            "biological_vitality": 75,
                        },
                        "capabilities": {"cannot_die": False},
                        "traits": ["trait_unaligned_observer", "trait_chimera_graft"],
                        "equipment": ["item_emp_lance"],
                        "inventory": [],
                        "baseline": {
                            "stats": {
                                "agency": 60,
                                "clarity": 55,
                                "dissonance": 20,
                                "neural_strain": 15,
                                "biological_vitality": 75,
                            },
                            "modifiers": {},
                        },
                        "metadata": {},
                    },
                }
            },
            "resources": {},
            "threats": {},
            "clock": {
                "id": "clock",
                "revision": 0,
                "schema_version": 1,
                "data": {"turn": 1, "day": 1, "display_timestamp": "Post-War Year 14, Dawn"},
            },
        }
        ctx = RuleContext(StateView(state), contract.definition_view, random.Random(0), 1)

        # introduce_threat event
        threat_event = {
            "schema_version": 1,
            "event_id": "event_threat_01",
            "world_id": "covenant-broken",
            "expected_turn": 1,
            "action": {
                "type": "introduce_threat",
                "template_id": "event_atmospheric_emp_squall",
                "location_id": "loc_scrap_hollow",
            },
        }
        res_threat = contract.resolve(ctx, threat_event)
        self.assertEqual(len(res_threat.effects), 1)
        self.assertEqual(res_threat.effects[0]["op"], "create")
        self.assertEqual(res_threat.effects[0]["collection"], "threats")

        # after_turn test: periodic decay/fallout with trait_chimera_graft
        outcome = contract.after_turn(ctx, threat_event, res_threat)
        self.assertTrue(len(outcome.effects) > 0)
        self.assertIn("environmental_fallout", outcome.outcomes)

    def test_covenant_broken_logic_resolve_trial(self):
        contract = WorldContract(Path(__file__).resolve().parents[1] / "world/covenant-broken", load_hooks=True)
        from engine.contracts import RuleContext, StateView
        import random

        state = {
            "characters": {
                "player_elias": {
                    "id": "player_elias",
                    "revision": 0,
                    "schema_version": 1,
                    "data": {
                        "name": "Elias Thorne",
                        "location_id": "loc_scrap_hollow",
                        "status": "alive",
                        "health": 75,
                        "stats": {
                            "agency": 60,
                            "clarity": 55,
                            "dissonance": 20,
                            "neural_strain": 15,
                            "biological_vitality": 75,
                        },
                        "capabilities": {"cannot_die": False},
                        "traits": ["trait_unaligned_observer"],
                        "equipment": ["item_emp_lance"],
                        "inventory": [],
                        "baseline": {
                            "stats": {
                                "agency": 60,
                                "clarity": 55,
                                "dissonance": 20,
                                "neural_strain": 15,
                                "biological_vitality": 75,
                            },
                            "modifiers": {},
                        },
                        "metadata": {},
                    },
                }
            },
            "resources": {},
            "threats": {
                "threat_emp_01": {
                    "id": "threat_emp_01",
                    "revision": 0,
                    "schema_version": 1,
                    "data": {
                        "name": "EMP Containment",
                        "location_id": "loc_scrap_hollow",
                        "active": True,
                        "activation_turn": 1,
                        "tags": ["opportunity"],
                        "stats": {"health": 0, "armor": 0, "retaliation": 0},
                        "metadata": {"template_id": "event_emp_containment"},
                    },
                }
            },
            "clock": {
                "id": "clock",
                "revision": 0,
                "schema_version": 1,
                "data": {"turn": 1, "day": 1, "display_timestamp": "Post-War Year 14, Dawn"},
            },
        }
        ctx = RuleContext(StateView(state), contract.definition_view, random.Random(0), 1)

        trial_event = {
            "schema_version": 1,
            "event_id": "event_trial_01",
            "world_id": "covenant-broken",
            "expected_turn": 1,
            "action": {
                "type": "resolve_trial",
                "actor_id": "player_elias",
                "trial_id": "threat_emp_01",
                "recipe_id": "recipe_emp_containment",
            },
        }
        res = contract.resolve(ctx, trial_event)
        self.assertEqual(len(res.effects), 1)
        self.assertEqual(res.effects[0]["op"], "set")
        self.assertEqual(res.effects[0]["path"], "/active")
        self.assertEqual(res.effects[0]["value"], False)

    def test_covenant_broken_canonical_state_and_characters(self):
        from engine.runner import read_snapshot
        from engine.state_store import StateStore

        contract = WorldContract.load("world/covenant-broken")
        self.assertIsNotNone(contract)

        store = StateStore("world/covenant-broken")
        state = store.snapshot()

        snapshot = read_snapshot("world/covenant-broken")
        self.assertEqual(state, snapshot)

        # Check clock
        self.assertIn("clock", snapshot)
        clock = snapshot["clock"]
        self.assertEqual(clock["schema_version"], 1)
        self.assertEqual(clock["id"], "clock")
        self.assertEqual(clock["revision"], 0)
        self.assertEqual(clock["data"]["turn"], 1)
        self.assertEqual(clock["data"]["day"], 1)
        self.assertEqual(clock["data"]["display_timestamp"], "Post-War Year 14, Dawn")

        # Check baseline/legacy
        self.assertIn("baseline", snapshot)
        self.assertIn("legacy", snapshot["baseline"])
        legacy = snapshot["baseline"]["legacy"]
        self.assertEqual(legacy["schema_version"], 1)
        self.assertEqual(legacy["id"], "legacy")
        self.assertEqual(legacy["revision"], 0)
        self.assertEqual(legacy["data"]["metadata"]["world_id"], "covenant-broken")
        self.assertEqual(legacy["data"]["metadata"]["installed_turn"], 1)

        # Check 6 characters
        self.assertIn("characters", snapshot)
        chars = snapshot["characters"]
        expected_chars = [
            "player_elias",
            "npc_valen_consensus",
            "npc_mira_purifier",
            "npc_archon_synergist",
            "npc_silas_severed",
            "npc_kora_vance",
        ]
        for cid in expected_chars:
            self.assertIn(cid, chars, f"Character {cid} missing from snapshot")
            c_env = chars[cid]
            self.assertEqual(c_env["schema_version"], 1)
            self.assertEqual(c_env["id"], cid)
            self.assertEqual(c_env["revision"], 0)
            contract.validate_envelope("characters", cid, c_env)

        # Elias check
        elias_data = chars["player_elias"]["data"]
        self.assertEqual(elias_data["name"], "Elias")
        self.assertEqual(elias_data["location_id"], "loc_scrap_hollow")
        self.assertEqual(elias_data["status"], "alive")
        self.assertEqual(elias_data["stats"]["agency"], 85)
        self.assertEqual(elias_data["stats"]["clarity"], 90)
        self.assertEqual(elias_data["stats"]["dissonance"], 15)
        self.assertEqual(elias_data["stats"]["neural_strain"], 10)
        self.assertEqual(elias_data["stats"]["biological_vitality"], 80)
        self.assertEqual(elias_data["traits"], ["trait_unaligned_observer"])
        self.assertEqual(sorted(elias_data["inventory"]), sorted(["item_scavenged_rail_pistol", "item_unaligned_diagnostic_pad"]))

        # Valen check
        valen_data = chars["npc_valen_consensus"]["data"]
        self.assertEqual(valen_data["name"], "Valen")
        self.assertEqual(valen_data["location_id"], "loc_consensus_spire")
        self.assertEqual(valen_data["stats"]["agency"], 30)
        self.assertEqual(valen_data["traits"], ["trait_consensus_tether"])

        # Mira check
        mira_data = chars["npc_mira_purifier"]["data"]
        self.assertEqual(mira_data["name"], "Mira")
        self.assertEqual(mira_data["location_id"], "loc_ashen_cradle")
        self.assertEqual(mira_data["stats"]["agency"], 90)
        self.assertEqual(mira_data["traits"], ["trait_purifier_fervor"])

        # Archon Rex check
        archon_data = chars["npc_archon_synergist"]["data"]
        self.assertEqual(archon_data["name"], "Archon Rex")
        self.assertEqual(archon_data["location_id"], "loc_chimera_foundry")
        self.assertEqual(archon_data["stats"]["agency"], 60)
        self.assertEqual(archon_data["traits"], ["trait_chimera_graft"])

        # Silas check
        silas_data = chars["npc_silas_severed"]["data"]
        self.assertEqual(silas_data["name"], "Silas")
        self.assertEqual(silas_data["location_id"], "loc_scrap_hollow")
        self.assertEqual(silas_data["stats"]["agency"], 65)
        self.assertEqual(silas_data["traits"], ["trait_severed_phantom"])

        # Dr. Kora Vance check
        kora_data = chars["npc_kora_vance"]["data"]
        self.assertEqual(kora_data["name"], "Dr. Kora Vance")
        self.assertEqual(kora_data["location_id"], "loc_scrap_hollow")
        self.assertEqual(kora_data["stats"]["agency"], 80)
        self.assertEqual(kora_data["traits"], ["trait_genomic_custodian"])

        # Check resources
        self.assertIn("resources", snapshot)
        for res_id in ["salvage_scrap", "energy_cells", "organic_rations"]:
            self.assertIn(res_id, snapshot["resources"])
            contract.validate_envelope("resources", res_id, snapshot["resources"][res_id])

        # State validation via contract logic
        from engine.contracts import RuleContext, StateView
        import random
        ctx = RuleContext(StateView(snapshot), contract.definition_view, random.Random(0), 1)
        violations = contract.validate(ctx)
        self.assertEqual(violations, [])

    def test_covenant_broken_engine_cli_and_artifacts(self):
        from engine.migration import inspect_world
        from engine.render_map import render_map
        from engine.contracts import WorldContract, RuleContext, StateView
        from engine.runner import read_snapshot
        import json

        world_path = Path(__file__).resolve().parents[1] / "world/covenant-broken"

        # 1. Inspect world check
        report = inspect_world(world_path)
        self.assertTrue(report.get("canonical"), "World must be canonical")
        self.assertEqual(report.get("blocking", 0), 0, "inspect_world must report 0 blocking issues")

        # 2. Stats / derivations check for all 6 characters
        contract = WorldContract(world_path, load_hooks=True)
        snapshot = read_snapshot(world_path)
        ctx = RuleContext(StateView(snapshot), contract.definition_view, None, snapshot["clock"]["data"]["turn"])

        expected_chars = [
            "player_elias",
            "npc_valen_consensus",
            "npc_mira_purifier",
            "npc_archon_synergist",
            "npc_silas_severed",
            "npc_kora_vance",
        ]
        for cid in expected_chars:
            derived = contract.derive(ctx, f"characters/{cid}")
            self.assertIn("stats", derived, f"Missing derived stats for {cid}")
            self.assertIn("agency", derived["stats"], f"Missing agency for {cid}")

        violations = contract.validate(ctx)
        self.assertEqual(violations, [], f"Expected 0 violations, got {violations}")

        # 3. Render map check
        map_path = render_map(world_path)
        self.assertTrue(map_path.exists(), f"Map file not found: {map_path}")
        self.assertEqual(map_path.name, "map.html")
        content = map_path.read_text(encoding="utf-8")
        self.assertIn("The Broken Covenant", content)
        self.assertIn("Elias", content)

        # 4. Baseline event and transaction artifacts check
        ev_path = world_path / "events/committed/engine_baseline.json"
        tx_path = world_path / "transactions/engine_baseline.json"
        prop_dir = world_path / "events/proposed"
        readme_path = world_path / "README.md"

        self.assertTrue(prop_dir.is_dir(), "events/proposed directory must exist")
        self.assertTrue(ev_path.exists(), "events/committed/engine_baseline.json must exist")
        self.assertTrue(tx_path.exists(), "transactions/engine_baseline.json must exist")
        self.assertTrue(readme_path.exists(), "world/covenant-broken/README.md must exist")

        ev_data = json.loads(ev_path.read_text(encoding="utf-8"))
        tx_data = json.loads(tx_path.read_text(encoding="utf-8"))

        self.assertEqual(ev_data["event_id"], "engine_baseline")
        self.assertEqual(ev_data["action"]["actor_id"], "player_elias")
        self.assertEqual(ev_data["action"]["type"], "baseline")
        self.assertEqual(ev_data["clock"]["turn"], 1)
        self.assertIn("Silent Sundering", ev_data["narrative"])

        self.assertEqual(tx_data["event_id"], "engine_baseline")
        self.assertEqual(tx_data["status"], "committed")
        self.assertEqual(tx_data["archive"], ev_data)


if __name__ == "__main__":
    unittest.main()



