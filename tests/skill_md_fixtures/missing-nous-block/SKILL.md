---
name: missing-nous-block
description: Skill without adjacent nous.yaml; parser must fail.
---

# Missing Nous Block

This directory has SKILL.md but no nous.yaml or nous.yml.
The parse_skill_dir call must raise SkillMDError.
