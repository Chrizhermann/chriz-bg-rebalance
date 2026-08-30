-- Synthetic stamped manifest for the fake-EEex readiness tests.
--
-- The resource names mirror the audited SCS 35.21 / SR 4.19 install, but this
-- file is test data: the production installer must regenerate and validate
-- every row from the target game's SPELL.IDS and instant-prebuff mapping.
return {
    schema_version = 1,
    minimum_duration = 2400,
    maintenance_cadence_ticks = 15,
    contact_rearm_seconds = 6,
    defaults = {
        ambient_enabled = 1,
        urgent_enabled = 1,
        external_owner = 0,
        scs_caster_grade = 1,
    },
    grades = {
        minimum = 0,
        baseline = 1,
        reserved_maximum = 3,
    },
    ambient_spells = {
        {
            key = "CLERIC_IMPERVIOUS_SANCTITY_OF_MIND",
            resref = "sppr735",
            delivery = "dwsp735",
            duration = 2880,
            minimum_grade = 1,
            self_target = 1,
            defensive = 1,
        },
        {
            key = "CLERIC_IRONSKIN",
            resref = "sppr506",
            delivery = "dwsp506",
            duration = 2400,
            minimum_grade = 1,
            self_target = 1,
            defensive = 1,
        },
        {
            key = "WIZARD_ARMOR",
            resref = "spwi102",
            delivery = "dwsw102",
            duration = 2400,
            minimum_grade = 1,
            self_target = 1,
            defensive = 1,
        },
        {
            key = "WIZARD_MIND_BLANK",
            resref = "spwi802",
            delivery = "dwsw802",
            duration = 7200,
            minimum_grade = 1,
            self_target = 1,
            defensive = 1,
        },
        {
            key = "WIZARD_NON_DETECTION",
            resref = "spwi310",
            delivery = "dwsw310",
            duration = 2400,
            minimum_grade = 1,
            self_target = 1,
            defensive = 1,
        },
        {
            key = "WIZARD_STONE_SKIN",
            resref = "spwi408",
            delivery = "dwsw408",
            duration = 2400,
            minimum_grade = 1,
            self_target = 1,
            defensive = 1,
        },
    },
    urgent_candidates = {
        {
            key = "WIZARD_ABSOLUTE_IMMUNITY",
            resref = "spwi907",
            genuine_weapon_immunity = 1,
        },
        {
            key = "WIZARD_IMPROVED_MANTLE",
            resref = "spwi808",
            genuine_weapon_immunity = 0,
        },
        {
            key = "WIZARD_MANTLE",
            resref = "spwi708",
            genuine_weapon_immunity = 1,
        },
        {
            key = "WIZARD_PROTECTION_FROM_MAGIC_WEAPONS",
            resref = "spwi611",
            genuine_weapon_immunity = 1,
        },
    },
    overrides = {
        cbr_grade_zero = { grade = 0 },
        cbr_sparse_include = {
            grade = 1,
            include = { WIZARD_MIND_BLANK = 1 },
        },
        cbr_sparse_exclude = {
            grade = 1,
            exclude = { WIZARD_STONE_SKIN = 1 },
        },
        cbr_reserved_grade = { grade = 3 },
    },
}
