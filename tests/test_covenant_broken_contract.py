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


if __name__ == "__main__":
    unittest.main()
