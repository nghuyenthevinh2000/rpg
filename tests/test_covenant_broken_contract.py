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


if __name__ == "__main__":
    unittest.main()

