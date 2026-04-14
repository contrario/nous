import re

path = "/opt/aetherlang_agents/nous/nous.lark"
with open(path, "r") as f:
    content = f.read()

old_mitosis = '''mitosis_block: MITOSIS "{" mitosis_field* "}"
mitosis_field: "trigger" ":" expr              -> mitosis_trigger
             | "max_clones" ":" INT            -> mitosis_max_clones
             | "cooldown" ":" duration_lit     -> mitosis_cooldown
             | "clone_tier" ":" TIER           -> mitosis_clone_tier
             | "verify" ":" BOOL              -> mitosis_verify'''

new_mitosis = '''mitosis_block: MITOSIS "{" mitosis_field* "}"
mitosis_field: "trigger" ":" expr              -> mitosis_trigger
             | "max_clones" ":" INT            -> mitosis_max_clones
             | "cooldown" ":" duration_lit     -> mitosis_cooldown
             | "clone_tier" ":" TIER           -> mitosis_clone_tier
             | "verify" ":" BOOL              -> mitosis_verify
             | "retire_trigger" ":" expr       -> mitosis_retire_trigger
             | "retire_cooldown" ":" duration_lit -> mitosis_retire_cooldown
             | "min_clones" ":" INT            -> mitosis_min_clones'''

if old_mitosis in content:
    content = content.replace(old_mitosis, new_mitosis)
    with open(path, "w") as f:
        f.write(content)
    print("PATCH 1 OK — grammar updated with retire fields")
else:
    print("PATCH 1 SKIP — pattern not found")
